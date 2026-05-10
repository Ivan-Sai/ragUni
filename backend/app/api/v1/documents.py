"""
Document upload and management API with LangChain integration.

Handles document ingestion into the vector store:
- Parse documents (PDF, DOCX, XLSX)
- Chunk text with LangChain text splitter
- Generate embeddings automatically
- Store in MongoDB Atlas Vector Search
- Access control via access_level + faculty
- Audience targeting via target_group_ids / target_years / target_level
  → all chunks of a document inherit these so the retrieval pre-filter
  can hard-filter by the user's profile.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import magic
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form

from app.config import get_settings
from app.core.dependencies import get_current_user, require_role
from app.core.rate_limit import limiter
from app.models.dictionary import StudyLevel
from app.models.document import DocumentResponse
from app.models.responses import (
    DeleteResponse,
    DocumentListResponse,
    DocumentPreviewResponse,
    DocumentStatsResponse,
    DocumentsBlock,
)
from app.services.database import get_database
from app.services.document_classifier import classify_document
from app.services.document_parser import DocumentParser
from app.services.extractor_registry import (
    generate_document_context,
    get_extractor,
)
from app.services.vector_store import vector_store_service

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

VALID_ACCESS_LEVELS = {"public", "faculty", "restricted"}

# MIME validation: DOCX/XLSX use specific OOXML types only
ALLOWED_MIMES = {
    "pdf": ["application/pdf"],
    "docx": [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/octet-stream",
        "application/zip",
    ],
    "xlsx": [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
        "application/zip",
    ],
    "txt": ["text/plain"],
}


def _parse_id_list(raw: Optional[str], field: str) -> list[str]:
    """Parse a JSON-encoded list of ObjectId strings supplied via Form.

    Form fields cannot natively carry arrays — clients send a JSON
    string and we deserialise here. Empty / null / [] are all valid
    and mean "no constraint on this dimension".
    """
    if not raw or raw.strip() == "":
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail=f"{field} must be a JSON array of strings",
        )
    if not isinstance(parsed, list):
        raise HTTPException(
            status_code=400,
            detail=f"{field} must be a JSON array of strings",
        )
    out: list[str] = []
    for item in parsed:
        if not isinstance(item, str) or not item.strip():
            raise HTTPException(
                status_code=400,
                detail=f"{field} contains an invalid identifier",
            )
        try:
            ObjectId(item)
        except (InvalidId, ValueError):
            raise HTTPException(
                status_code=400,
                detail=f"{field} contains an invalid identifier",
            )
        out.append(item)
    return out


def _parse_year_list(raw: Optional[str]) -> list[int]:
    if not raw or raw.strip() == "":
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="target_years must be a JSON array of integers",
        )
    if not isinstance(parsed, list):
        raise HTTPException(
            status_code=400,
            detail="target_years must be a JSON array of integers",
        )
    out: list[int] = []
    for item in parsed:
        if not isinstance(item, int) or item < 1 or item > 6:
            raise HTTPException(
                status_code=400,
                detail="target_years contains a value outside the 1-6 range",
            )
        out.append(item)
    return out


async def _validate_audience(
    faculty_id: str,
    target_group_ids: list[str],
    target_level: Optional[str],
) -> tuple[list[str], list[str]]:
    """Verify that every referenced group exists, belongs to the faculty,
    and matches the chosen level. Returns ``(group_ids, group_names)``
    so the response can show the names without a second lookup.
    """
    db = get_database()

    if not await db.faculties.find_one({"_id": ObjectId(faculty_id)}, {"_id": 1}):
        raise HTTPException(status_code=400, detail="Faculty does not exist")

    if not target_group_ids:
        return [], []

    oids = [ObjectId(gid) for gid in target_group_ids]
    groups: list[dict] = []
    async for grp in db.groups.find({"_id": {"$in": oids}}):
        groups.append(grp)

    if len(groups) != len(target_group_ids):
        raise HTTPException(
            status_code=400,
            detail="One or more target groups do not exist",
        )

    faculty_oid = ObjectId(faculty_id)
    bad = [g for g in groups if g["faculty_id"] != faculty_oid]
    if bad:
        raise HTTPException(
            status_code=400,
            detail="One or more target groups do not belong to the selected faculty",
        )

    if target_level:
        wrong_level = [g for g in groups if g["level"] != target_level]
        if wrong_level:
            raise HTTPException(
                status_code=400,
                detail="One or more target groups do not match the selected study level",
            )

    return target_group_ids, [g["name"] for g in groups]


async def _resolve_groups_by_label(
    faculty_id: str,
    labels: set[str],
) -> dict[str, str]:
    """Map raw group labels (as written by the LLM) to canonical group_ids.

    Compared case-insensitively against the dictionary so minor
    formatting differences ("ІКСМ-1" vs "іксм-1") still match.
    Unknown labels are simply omitted from the returned map — the
    caller falls back to the document-level tags for those rows.
    """
    if not labels:
        return {}
    db = get_database()
    cursor = db.groups.find(
        {"faculty_id": ObjectId(faculty_id)},
        {"_id": 1, "name": 1, "name_lower": 1},
    )
    by_lower: dict[str, str] = {}
    async for doc in cursor:
        by_lower[doc.get("name_lower") or doc["name"].lower()] = str(doc["_id"])

    mapping: dict[str, str] = {}
    for label in labels:
        normalised = label.strip().lower()
        if normalised in by_lower:
            mapping[label] = by_lower[normalised]
    return mapping


@router.post("/upload", response_model=DocumentResponse, status_code=201)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    access_level: str = Form(default="public"),
    faculty_id: str = Form(...),
    target_group_ids: str = Form(default=""),
    target_years: str = Form(default=""),
    target_level: Optional[str] = Form(default=None),
    current_user: dict[str, Any] = Depends(require_role("teacher", "admin")),
):
    """
    Upload and process a document with LangChain.

    Only teachers and admins can upload documents.

    **Access levels:**
    - public: visible to everyone
    - faculty: visible to users of the same faculty
    - restricted: visible to teachers and admins only

    **Audience targeting** (mandatory in the form):
    - ``faculty_id`` — id of the faculty this document belongs to.
    - ``target_group_ids`` — JSON array of group ObjectIds. Empty array
      means "for all groups in the faculty".
    - ``target_years`` — JSON array of years (1–6). Empty array means
      "for all years".
    - ``target_level`` — bachelor / master / phd / null=any.
    """
    # Validate access_level
    if access_level not in VALID_ACCESS_LEVELS:
        raise HTTPException(
            status_code=400,
            detail="access_level must be one of: public, faculty, restricted",
        )

    # Faculty is now mandatory for every document — drives access scoping.
    try:
        ObjectId(faculty_id)
    except (InvalidId, ValueError):
        raise HTTPException(status_code=400, detail="Invalid faculty_id")

    parsed_group_ids = _parse_id_list(target_group_ids, "target_group_ids")
    parsed_years = _parse_year_list(target_years)
    parsed_level: Optional[str] = None
    if target_level:
        try:
            parsed_level = StudyLevel(target_level).value
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="target_level must be one of: bachelor, master, phd",
            )

    group_ids, group_names = await _validate_audience(
        faculty_id, parsed_group_ids, parsed_level
    )

    # Validate file type (safe extension extraction)
    allowed_extensions = ["pdf", "docx", "xlsx", "txt"]
    basename = os.path.basename(file.filename or "")
    _, ext = os.path.splitext(basename)
    file_extension = ext[1:].lower() if ext else ""

    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format. Allowed: {', '.join(allowed_extensions)}",
        )

    try:
        file_content = await file.read()

        # Validate actual file content via magic bytes
        detected_mime = magic.from_buffer(file_content[:2048], mime=True)
        expected_mimes = ALLOWED_MIMES.get(file_extension, [])
        if detected_mime not in expected_mimes:
            logger.warning(
                "MIME mismatch: file=%s extension=%s detected=%s",
                file.filename, file_extension, detected_mime,
            )
            raise HTTPException(
                status_code=400,
                detail=f"File content does not match extension '.{file_extension}'",
            )

        if len(file_content) > settings.max_upload_size:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum: {settings.max_upload_size / (1024 * 1024):.0f}MB",
            )

        logger.info("Processing document: %s", file.filename)

        # Parse document
        text = await DocumentParser.parse_file(file_content, file_extension)

        if not text or not text.strip():
            raise HTTPException(
                status_code=400,
                detail="Could not extract text from document",
            )

        # Validate extracted text size
        if len(text) > settings.max_extracted_text_size:
            raise HTTPException(
                status_code=400,
                detail="Extracted text is too large to process",
            )

        logger.info("Extracted %d characters from %s", len(text), file.filename)

        # Reserve a document id up-front so each chunk can carry it in
        # its metadata. The frontend uses this id to open the source
        # document directly from a citation card without an extra
        # filename → id lookup.
        document_oid = ObjectId()
        now = datetime.now(timezone.utc)
        user_id = str(current_user["_id"])

        # Document-level audience that every chunk inherits unless an
        # LLM-extracted record overrides it (per-row). Empty / null
        # values are intentionally OMITTED — Atlas pre_filter cannot
        # express "list is empty" (no $size operator), so retrieval
        # treats a missing field as "no constraint".
        doc_audience: dict[str, Any] = {}
        if group_ids:
            doc_audience["target_group_ids"] = group_ids
        if parsed_years:
            doc_audience["target_years"] = parsed_years
        if parsed_level:
            doc_audience["target_level"] = parsed_level

        # Common metadata stored with each chunk in the vector store.
        base_chunk_metadata: dict[str, Any] = {
            "source_file": file.filename,
            "file_type": file_extension,
            "access_level": access_level,
            "faculty_id": faculty_id,
            "uploaded_at": now.isoformat(),
            "uploaded_by_id": user_id,
            "original_size": len(file_content),
            "text_length": len(text),
            "document_id": str(document_oid),
            **doc_audience,
        }

        # ------------------------------------------------------------------
        # Universal document pipeline: classify → contextualise →
        # type-specific extract → adaptive chunk → index. The
        # classifier picks the right extractor automatically; admins
        # never need to label uploads as "schedule" or "regulation"
        # by hand. See docs/architecture-rag.md for the full
        # rationale.
        # ------------------------------------------------------------------
        classification = await classify_document(text, filename=file.filename or "")
        doc_type = classification.doc_type

        # Contextual Retrieval (Anthropic, Sept 2024). One LLM call
        # per document, ~+35 % retrieval accuracy when prepended to
        # each chunk before embedding.
        document_context = await generate_document_context(
            text,
            filename=file.filename or "",
            doc_type=doc_type,
        )

        extractor = get_extractor(doc_type)
        # ``file_content`` is passed per-call rather than via a setter
        # so the registry-level extractor instance stays stateless and
        # safe under concurrent uploads. The schedule extractor uses
        # the raw bytes for its deterministic per-column parser; the
        # other extractors ignore them.
        result = await extractor.extract(
            text=text,
            filename=file.filename or "",
            document_context=document_context,
            file_content=file_content,
        )

        structured_records = result.records
        records_count = len(structured_records)
        extraction_method = result.method

        # For row-style extractors (schedule / exam_protocol) we
        # resolve LLM-emitted group labels against the dictionary
        # AFTER extraction, so the per-row audience metadata uses
        # canonical group ids. The per-record meta the extractor
        # produced already carries year_label / level_label.
        if structured_records:
            labels = {
                meta.get("group_label")
                for _, meta in result.chunks
                if isinstance(meta.get("group_label"), str)
                and meta["group_label"].lower() not in {"усі групи", "all groups"}
            }
            label_to_id = await _resolve_groups_by_label(faculty_id, labels)
        else:
            label_to_id = {}

        texts_for_store: list[str] = []
        metas_for_store: list[dict[str, Any]] = []
        for index, (rendered, per_chunk_meta) in enumerate(result.chunks):
            chunk_meta: dict[str, Any] = {
                **base_chunk_metadata,
                **per_chunk_meta,
                "doc_type": doc_type,
                "chunk_index": index,
                "total_chunks": len(result.chunks),
                "chunk_length": len(rendered),
            }

            # Row-style audience overrides — only relevant for
            # schedule / exam_protocol records that carry per-row
            # group / year / level fields.
            label = per_chunk_meta.get("group_label")
            if isinstance(label, str):
                normalised = label.lower()
                if normalised in {"усі групи", "all groups"}:
                    row_group_ids: list[str] = list(group_ids)
                elif label in label_to_id:
                    row_group_ids = [label_to_id[label]]
                else:
                    row_group_ids = list(group_ids)
                if row_group_ids:
                    chunk_meta["target_group_ids"] = row_group_ids
                else:
                    chunk_meta.pop("target_group_ids", None)

            row_year = per_chunk_meta.get("year_label")
            if isinstance(row_year, int):
                chunk_meta["target_years"] = [row_year]
            row_level = per_chunk_meta.get("level_label")
            if isinstance(row_level, str) and row_level in {"bachelor", "master", "phd"}:
                chunk_meta["target_level"] = row_level

            texts_for_store.append(rendered)
            metas_for_store.append(chunk_meta)

        if not texts_for_store:
            # Extractor produced nothing usable — fall back to the
            # legacy recursive chunker on the raw text so we never
            # leave a document un-indexed.
            logger.warning(
                "Extractor %s produced 0 chunks for %s, falling back to raw recursive split",
                extraction_method,
                file.filename,
            )
            chunk_ids = await vector_store_service.add_document_with_chunking(
                text, base_chunk_metadata, file_type=file_extension,
            )
            extraction_method = f"{extraction_method}_fallback_raw"
        else:
            chunk_ids = await vector_store_service.add_documents(
                texts_for_store, metas_for_store
            )

        structured_text = (
            "\n\n".join(t for t, _ in result.chunks) if structured_records else None
        )

        logger.info(
            "Indexed %d chunks for %s (doc_type=%s method=%s records=%d)",
            len(chunk_ids),
            file.filename,
            doc_type,
            extraction_method,
            records_count,
        )

        # Save document record to MongoDB (including extracted text for preview)
        db = get_database()
        document_data = {
            "_id": document_oid,
            "filename": file.filename,
            "file_type": file_extension,
            "access_level": access_level,
            "faculty_id": ObjectId(faculty_id),
            "target_group_ids": [ObjectId(gid) for gid in group_ids],
            "target_years": parsed_years,
            "target_level": parsed_level,
            "uploaded_at": now,
            "uploaded_by_id": user_id,
            "total_chunks": len(chunk_ids),
            "chunk_ids": chunk_ids,
            "metadata": base_chunk_metadata,
            # Original parser output — used for the preview modal so
            # users always see the source as it appeared in the PDF.
            "extracted_text": text,
            "structured_text": structured_text,
            # Raw JSON records (list of dicts) — kept so the preview UI
            # can render them as proper cards instead of having to
            # parse the rendered string.
            "structured_records": structured_records,
            "extraction_method": extraction_method,
            "structured_records_count": records_count,
            # Universal-pipeline metadata — see architecture-rag.md.
            "doc_type": doc_type,
            "doc_type_confidence": getattr(classification, "confidence", None),
            "doc_type_reasoning": getattr(classification, "reasoning", ""),
            "document_context": document_context,
        }

        await db.documents.insert_one(document_data)
        document_id = str(document_oid)

        logger.info("Document saved: %s (id=%s)", file.filename, document_id)

        # Track upload event
        from app.services.analytics import track_event
        await track_event(
            "document_upload",
            str(current_user["_id"]),
            current_user.get("role", "admin"),
            {"filename": file.filename, "file_type": file_extension, "chunks": len(chunk_ids)},
        )

        # Resolve faculty name for the response (single lookup — cheap).
        fac = await db.faculties.find_one(
            {"_id": ObjectId(faculty_id)}, {"name": 1}
        )

        return DocumentResponse(
            id=document_id,
            filename=file.filename,
            file_type=file_extension,
            access_level=access_level,
            faculty_id=faculty_id,
            faculty_name=fac["name"] if fac else None,
            target_group_ids=group_ids,
            target_group_names=group_names,
            target_years=parsed_years,
            target_level=parsed_level,
            uploaded_at=now,
            total_chunks=len(chunk_ids),
            message=f"Document processed. Created {len(chunk_ids)} chunks for search.",
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.error("Error processing document: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/list", response_model=DocumentListResponse)
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DocumentListResponse:
    """Get list of uploaded documents with pagination, filtered by access control."""
    db = get_database()
    user_role = current_user.get("role", "student")
    user_faculty_id = current_user.get("faculty_id")

    # Build access filter for documents (no audience filter at the list
    # level — students still see all documents flagged for their group,
    # access-wise).
    access_filter: dict[str, Any] = {}
    if user_role == "student":
        conditions = [{"access_level": "public"}]
        if user_faculty_id:
            conditions.append(
                {"$and": [{"access_level": "faculty"}, {"faculty_id": user_faculty_id}]}
            )
        access_filter = {"$or": conditions}
    elif user_role == "teacher":
        conditions = [
            {"access_level": "public"},
            {"access_level": "restricted"},
        ]
        if user_faculty_id:
            conditions.append(
                {"$and": [{"access_level": "faculty"}, {"faculty_id": user_faculty_id}]}
            )
        access_filter = {"$or": conditions}
    # admin: no filter (sees everything)

    total = await db.documents.count_documents(access_filter)

    cursor = db.documents.find(
        access_filter,
        {
            "filename": 1,
            "file_type": 1,
            "access_level": 1,
            "faculty_id": 1,
            "target_group_ids": 1,
            "target_years": 1,
            "target_level": 1,
            "uploaded_at": 1,
            "total_chunks": 1,
        },
    ).sort("uploaded_at", -1).skip(skip).limit(limit)

    documents: list[DocumentResponse] = []
    async for doc in cursor:
        documents.append(
            DocumentResponse(
                id=str(doc["_id"]),
                filename=doc.get("filename", ""),
                file_type=doc.get("file_type", ""),
                access_level=doc.get("access_level", "public"),
                faculty_id=(
                    str(doc["faculty_id"]) if doc.get("faculty_id") else None
                ),
                faculty_name=None,
                target_group_ids=[
                    str(g) for g in doc.get("target_group_ids", []) or []
                ],
                target_group_names=[],
                target_years=doc.get("target_years", []) or [],
                target_level=doc.get("target_level"),
                uploaded_at=doc.get("uploaded_at"),
                total_chunks=doc.get("total_chunks", 0),
                message="",
            )
        )

    return DocumentListResponse(documents=documents, total=total)


@router.delete("/{document_id}", response_model=DeleteResponse)
@limiter.limit("20/minute")
async def delete_document(
    request: Request,
    document_id: str,
    current_user: dict[str, Any] = Depends(require_role("teacher", "admin")),
) -> DeleteResponse:
    """Delete a document and its chunks from vector store."""
    db = get_database()

    try:
        oid = ObjectId(document_id)
    except (InvalidId, ValueError):
        raise HTTPException(status_code=400, detail="Invalid document identifier")

    try:
        doc = await db.documents.find_one({"_id": oid})

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        # Ownership check: teachers can only delete their own documents
        user_role = current_user.get("role")
        user_id = str(current_user["_id"])
        if user_role != "admin" and doc.get("uploaded_by_id") != user_id:
            raise HTTPException(status_code=403, detail="You can only delete your own documents")

        filename = doc.get("filename")

        # Delete chunks from vector store. Joining on the immutable
        # document_id (not on filename) means deleting upload A
        # cannot accidentally remove the chunks of upload B even if
        # both happen to share a filename — historically that was the
        # IDOR-style hole here.
        logger.info("Deleting chunks for document: %s", document_id)
        deleted_count = await vector_store_service.delete_by_document_id(
            document_id
        )
        logger.info("Deleted %d chunks from vector store", deleted_count)

        # Delete document record
        result = await db.documents.delete_one({"_id": oid})

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Document not found")

        logger.info("Document deleted: %s", document_id)

        return DeleteResponse(
            message="Document deleted",
            filename=filename,
            chunks_deleted=deleted_count,
        )

    except HTTPException:
        raise
    except RuntimeError as e:
        logger.error("Error deleting document: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{document_id}/preview", response_model=DocumentPreviewResponse)
@limiter.limit("30/minute")
async def preview_document(
    request: Request,
    document_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DocumentPreviewResponse:
    """Get the extracted text of a document for preview."""
    db = get_database()

    try:
        oid = ObjectId(document_id)
    except (InvalidId, ValueError):
        raise HTTPException(status_code=400, detail="Invalid document identifier")

    doc = await db.documents.find_one({"_id": oid})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Access control
    user_role = current_user.get("role", "student")
    user_faculty_id = current_user.get("faculty_id")
    access_level = doc.get("access_level", "public")
    doc_faculty_id = doc.get("faculty_id")

    if user_role == "student":
        if access_level == "restricted":
            raise HTTPException(status_code=403, detail="Access denied")
        if access_level == "faculty" and doc_faculty_id != user_faculty_id:
            raise HTTPException(status_code=403, detail="Access denied")
    elif user_role == "teacher":
        if access_level == "faculty" and doc_faculty_id != user_faculty_id:
            raise HTTPException(status_code=403, detail="Access denied")

    extracted_text = doc.get("extracted_text")
    if not extracted_text:
        raise HTTPException(
            status_code=404,
            detail="Preview not available for this document",
        )

    return DocumentPreviewResponse(
        id=str(doc["_id"]),
        filename=doc.get("filename"),
        file_type=doc.get("file_type"),
        total_chunks=doc.get("total_chunks", 0),
        text=extracted_text,
        structured_text=doc.get("structured_text"),
        structured_records=doc.get("structured_records") or [],
        extraction_method=doc.get("extraction_method", "raw"),
        structured_records_count=doc.get("structured_records_count", 0),
    )


@router.get("/stats", response_model=DocumentStatsResponse)
async def get_statistics(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> DocumentStatsResponse:
    """Get statistics about documents and vector store."""
    db = get_database()

    doc_count = await db.documents.count_documents({})

    vector_stats = await vector_store_service.get_stats()

    pipeline = [{"$group": {"_id": "$file_type", "count": {"$sum": 1}}}]
    file_types: dict[str, int] = {}
    async for item in db.documents.aggregate(pipeline):
        file_types[item["_id"]] = item["count"]

    return DocumentStatsResponse(
        documents=DocumentsBlock(total=doc_count, by_type=file_types),
        vector_store=vector_stats,
    )
