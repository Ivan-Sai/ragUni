"""
Document upload and management API with LangChain integration.

Handles document ingestion into the vector store:
- Parse documents (PDF, DOCX, XLSX)
- Chunk text with LangChain text splitter
- Generate embeddings automatically
- Store in MongoDB Atlas Vector Search
- Access control via access_level and faculty fields
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

import magic
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from typing import Optional

from app.config import get_settings
from app.core.dependencies import get_current_user, require_role
from app.core.rate_limit import limiter
from app.models.document import DocumentResponse
from app.services.database import get_database
from app.services.document_parser import DocumentParser
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
    ],
    "xlsx": [
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/octet-stream",
    ],
    "txt": ["text/plain"],
}


@router.post("/upload", response_model=DocumentResponse, status_code=201)
@limiter.limit("10/minute")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    access_level: str = Form(default="public"),
    faculty: Optional[str] = Form(default=None),
    current_user: dict[str, Any] = Depends(require_role("teacher", "admin")),
):
    """
    Upload and process a document with LangChain.

    Only teachers and admins can upload documents.

    **Access levels:**
    - public: visible to everyone
    - faculty: visible to users of the same faculty
    - restricted: visible to teachers and admins only
    """
    # Validate access_level
    if access_level not in VALID_ACCESS_LEVELS:
        raise HTTPException(
            status_code=400,
            detail="access_level must be one of: public, faculty, restricted",
        )

    if access_level == "faculty" and not faculty:
        raise HTTPException(
            status_code=400,
            detail="Faculty is required when access_level is 'faculty'",
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

        now = datetime.now(timezone.utc)
        user_id = str(current_user["_id"])

        # Metadata stored with each chunk in vector store (no PII)
        chunk_metadata = {
            "source_file": file.filename,
            "file_type": file_extension,
            "access_level": access_level,
            "faculty": faculty,
            "uploaded_at": now.isoformat(),
            "uploaded_by_id": user_id,
            "original_size": len(file_content),
            "text_length": len(text),
        }

        # Add to vector store (async — runs in thread pool)
        logger.info(
            "Chunking (size=%d, overlap=%d) and embedding...",
            settings.chunk_size,
            settings.chunk_overlap,
        )
        chunk_ids = await vector_store_service.add_document_with_chunking(text, chunk_metadata)

        logger.info("Created %d chunks with embeddings", len(chunk_ids))

        # Save document record to MongoDB
        db = get_database()
        document_data = {
            "filename": file.filename,
            "file_type": file_extension,
            "access_level": access_level,
            "faculty": faculty,
            "uploaded_at": now,
            "uploaded_by_id": user_id,
            "total_chunks": len(chunk_ids),
            "chunk_ids": chunk_ids,
            "metadata": chunk_metadata,
        }

        result = await db.documents.insert_one(document_data)
        document_id = str(result.inserted_id)

        logger.info("Document saved: %s (id=%s)", file.filename, document_id)

        return DocumentResponse(
            id=document_id,
            filename=file.filename,
            file_type=file_extension,
            access_level=access_level,
            faculty=faculty,
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


@router.get("/list")
async def list_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Get list of uploaded documents with pagination, filtered by access control."""
    db = get_database()
    user_role = current_user.get("role", "student")
    user_faculty = current_user.get("faculty")

    # Build access filter for documents
    access_filter: dict[str, Any] = {}
    if user_role == "student":
        conditions = [{"access_level": "public"}]
        if user_faculty:
            conditions.append(
                {"$and": [{"access_level": "faculty"}, {"faculty": user_faculty}]}
            )
        access_filter = {"$or": conditions}
    elif user_role == "teacher":
        conditions = [
            {"access_level": "public"},
            {"access_level": "restricted"},
        ]
        if user_faculty:
            conditions.append(
                {"$and": [{"access_level": "faculty"}, {"faculty": user_faculty}]}
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
            "faculty": 1,
            "uploaded_at": 1,
            "total_chunks": 1,
        },
    ).sort("uploaded_at", -1).skip(skip).limit(limit)

    documents = []
    async for doc in cursor:
        documents.append(
            {
                "id": str(doc["_id"]),
                "filename": doc.get("filename"),
                "file_type": doc.get("file_type"),
                "access_level": doc.get("access_level", "public"),
                "faculty": doc.get("faculty"),
                "uploaded_at": doc.get("uploaded_at"),
                "total_chunks": doc.get("total_chunks", 0),
            }
        )

    return {"documents": documents, "total": total}


@router.delete("/{document_id}")
@limiter.limit("20/minute")
async def delete_document(
    request: Request,
    document_id: str,
    current_user: dict[str, Any] = Depends(require_role("teacher", "admin")),
):
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

        # Delete chunks from vector store (async)
        logger.info("Deleting chunks for document: %s", document_id)
        deleted_count = await vector_store_service.delete_by_metadata(
            {"source_file": filename}
        )
        logger.info("Deleted %d chunks from vector store", deleted_count)

        # Delete document record
        result = await db.documents.delete_one({"_id": oid})

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Document not found")

        logger.info("Document deleted: %s", document_id)

        return {
            "message": "Document deleted",
            "filename": filename,
            "chunks_deleted": deleted_count,
        }

    except HTTPException:
        raise
    except RuntimeError as e:
        logger.error("Error deleting document: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/stats")
async def get_statistics(current_user: dict[str, Any] = Depends(get_current_user)):
    """Get statistics about documents and vector store."""
    db = get_database()

    doc_count = await db.documents.count_documents({})

    vector_stats = await vector_store_service.get_stats()

    pipeline = [{"$group": {"_id": "$file_type", "count": {"$sum": 1}}}]
    file_types = {}
    async for item in db.documents.aggregate(pipeline):
        file_types[item["_id"]] = item["count"]

    return {
        "documents": {"total": doc_count, "by_type": file_types},
        "vector_store": vector_stats,
    }
