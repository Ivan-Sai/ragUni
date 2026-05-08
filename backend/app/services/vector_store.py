"""
Vector Store Service — MongoDB Atlas Vector Search with LangChain.

Features:
- Async-safe operations via asyncio.to_thread
- MMR (Maximal Marginal Relevance) for diverse results
- Score thresholding to filter low-quality matches
- Access control via pre_filter (role + faculty)
- Thread-safe lazy initialization
"""

import asyncio
import logging
import re
import threading
from typing import Any, Optional

from langchain_community.embeddings import FastEmbedEmbeddings
from langchain_core.documents import Document as LangChainDocument
from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_mongodb.retrievers import MongoDBAtlasHybridSearchRetriever
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pymongo import MongoClient
from pymongo.collection import Collection

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Valid roles for access filter validation
_VALID_ROLES = {"student", "teacher", "admin"}


class _E5PrefixedEmbeddings(FastEmbedEmbeddings):
    """FastEmbed wrapper that adds the E5 instruction prefixes.

    The intfloat/multilingual-e5-* family was trained with explicit
    role markers: ``query:`` for user queries and ``passage:`` for the
    documents being indexed. Without these prefixes cosine scores
    cluster very tightly (~0.88-0.92 across topical and off-topic
    chunks alike), which destroys the ranking signal — adding them
    restores ~0.6-0.95 spread on the same data. Cheap to apply, hard
    to undo without a reindex, so do it once and stick with it.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return super().embed_documents([f"passage: {t}" for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return super().embed_query(f"query: {text}")


class VectorStoreService:
    """LangChain-powered vector store with MongoDB Atlas Vector Search."""

    def __init__(self) -> None:
        self._client: Optional[MongoClient] = None
        self._collection: Optional[Collection] = None
        self._embeddings: Optional[FastEmbedEmbeddings] = None
        self._vector_store: Optional[MongoDBAtlasVectorSearch] = None
        self._text_splitter: Optional[RecursiveCharacterTextSplitter] = None
        self._init_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Thread-safe lazy initialization."""
        if self._vector_store is not None:
            return

        with self._init_lock:
            # Double-check after acquiring lock
            if self._vector_store is not None:
                return

            logger.info("Initializing LangChain Vector Store...")

            self._client = MongoClient(settings.mongodb_url)
            self._collection = self._client[settings.mongodb_db_name]["document_chunks"]

            logger.info(
                "Loading embedding model: %s (E5 prefix-aware)",
                settings.embedding_model,
            )
            self._embeddings = _E5PrefixedEmbeddings(
                model_name=settings.embedding_model,
            )

            self._vector_store = MongoDBAtlasVectorSearch(
                collection=self._collection,
                embedding=self._embeddings,
                index_name=settings.vector_index_name,
                text_key="text",
                embedding_key="embedding",
                relevance_score_fn="cosine",
            )

            self._text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
                length_function=len,
                separators=["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""],
            )

            logger.info("Vector Store initialized")

    @property
    def vector_store(self) -> MongoDBAtlasVectorSearch:
        if self._vector_store is None:
            self.initialize()
        return self._vector_store

    @property
    def text_splitter(self) -> RecursiveCharacterTextSplitter:
        if self._text_splitter is None:
            self.initialize()
        return self._text_splitter

    @property
    def embeddings(self) -> FastEmbedEmbeddings:
        if self._embeddings is None:
            self.initialize()
        return self._embeddings

    # ------------------------------------------------------------------
    # Access control filter builder
    # ------------------------------------------------------------------

    @staticmethod
    def build_access_filter(
        user_role: str = "student",
        user_faculty_id: Optional[str] = None,
        user_group_id: Optional[str] = None,
        user_year: Optional[int] = None,
        user_level: Optional[str] = None,
        target_doc_types: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Build a MongoDB pre_filter for Atlas Vector Search.

        Two layers run in series:

        1. **Access** — by role and faculty. Public is visible to all,
           faculty-scoped is visible to its faculty (+ teachers/admins),
           restricted is visible to teachers/admins only.
        2. **Audience** — for students only. A chunk passes if its
           ``target_group_ids`` contains the user's group OR is empty
           (= "for all groups"); same logic for ``target_years`` and
           ``target_level``. Empty list / null on a chunk means "no
           constraint on this dimension".

        Teachers and admins are exempt from the audience layer. They
        help students across groups and need to see every record.
        """
        # Validate role
        if user_role not in _VALID_ROLES:
            logger.warning("Unknown role '%s', defaulting to student access", user_role)
            user_role = "student"

        # ---- Access layer -------------------------------------------------
        if user_role == "admin":
            access_filter: dict[str, Any] = {}
        elif user_role == "teacher":
            conditions: list[dict] = [
                {"access_level": "public"},
                {"access_level": "restricted"},
            ]
            if user_faculty_id:
                conditions.append(
                    {"$and": [{"access_level": "faculty"}, {"faculty_id": user_faculty_id}]}
                )
            access_filter = {"$or": conditions}
        else:
            # Students: public + own-faculty.
            conditions = [{"access_level": "public"}]
            if user_faculty_id:
                conditions.append(
                    {"$and": [{"access_level": "faculty"}, {"faculty_id": user_faculty_id}]}
                )
            access_filter = {"$or": conditions}

        # Teachers and admins skip the audience filter, but they
        # still benefit from doc_type narrowing when the analyzer
        # asked for it.
        if user_role != "student":
            if target_doc_types:
                doc_type_clause = {"doc_type": {"$in": list(target_doc_types)}}
                if access_filter:
                    return {"$and": [access_filter, doc_type_clause]}
                return doc_type_clause
            return access_filter

        # ---- Audience layer (students only) -------------------------------
        # Atlas Vector Search ``pre_filter`` only accepts a small set of
        # operators (equals, in, range, exists, all) — ``$size`` is NOT
        # one of them. To express "target list is empty" we drop the
        # field from chunk metadata at write time and check
        # ``$exists: false`` here. Equality on an array field is
        # interpreted by MongoDB as element-match, so ``target_group_ids:
        # <user_group_id>`` matches any chunk whose array contains it.
        audience_clauses: list[dict] = []

        if user_group_id:
            audience_clauses.append({
                "$or": [
                    {"target_group_ids": user_group_id},
                    {"target_group_ids": {"$exists": False}},
                ]
            })

        if user_year is not None:
            audience_clauses.append({
                "$or": [
                    {"target_years": user_year},
                    {"target_years": {"$exists": False}},
                ]
            })

        if user_level:
            audience_clauses.append({
                "$or": [
                    {"target_level": user_level},
                    {"target_level": {"$exists": False}},
                ]
            })

        if target_doc_types:
            audience_clauses.append(
                {"doc_type": {"$in": list(target_doc_types)}}
            )

        if not audience_clauses:
            return access_filter

        if not access_filter:
            return {"$and": audience_clauses} if len(audience_clauses) > 1 else audience_clauses[0]

        return {"$and": [access_filter, *audience_clauses]}

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def chunk_text(self, text: str) -> list[str]:
        """Split text into semantic chunks (default chunk size)."""
        if not text or not text.strip():
            return []
        return self.text_splitter.split_text(text)

    def chunk_text_for_type(self, text: str, file_type: Optional[str]) -> list[str]:
        """Split text using a chunk strategy tuned to the file type.

        XLSX rows are short and tabular, so the default 1000-char chunker
        ends up splitting tables mid-row. For spreadsheets we use a smaller
        window so a 20-row table stays as one or two chunks instead of five.
        """
        if not text or not text.strip():
            return []
        if (file_type or "").lower() == "xlsx":
            xlsx_splitter = RecursiveCharacterTextSplitter(
                chunk_size=settings.chunk_size_xlsx,
                chunk_overlap=settings.chunk_overlap_xlsx,
                length_function=len,
                # Prioritise table boundaries before falling back to
                # sentence and word breaks.
                separators=[
                    "\n--- End of sheet",
                    "\n--- Sheet:",
                    "\n\n",
                    "\n",
                    " | ",
                    ". ",
                    " ",
                    "",
                ],
            )
            return xlsx_splitter.split_text(text)
        return self.text_splitter.split_text(text)

    # ------------------------------------------------------------------
    # Document CRUD (synchronous — call via asyncio.to_thread)
    # ------------------------------------------------------------------

    def _add_documents_sync(
        self,
        texts: list[str],
        metadatas: list[dict],
        batch_size: int = 100,
    ) -> list[str]:
        """Add documents to vector store (blocking)."""
        if len(texts) != len(metadatas):
            raise ValueError("texts and metadatas must have same length")

        all_ids: list[str] = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i : i + batch_size]
            batch_metadatas = metadatas[i : i + batch_size]
            ids = self.vector_store.add_texts(
                texts=batch_texts,
                metadatas=batch_metadatas,
            )
            all_ids.extend(ids)
            logger.debug("Added batch %d–%d (%d chunks)", i, i + len(batch_texts), len(ids))

        return all_ids

    def _add_document_with_chunking_sync(
        self,
        text: str,
        metadata: dict,
        file_type: Optional[str] = None,
    ) -> list[str]:
        """Chunk text + add to vector store (blocking)."""
        ftype = (file_type or metadata.get("file_type") or "").lower()
        chunks = self.chunk_text_for_type(text, ftype)
        if not chunks:
            raise ValueError("No chunks created from text")

        chunk_metadatas: list[dict] = []
        # For PDF input, parse_pdf prefixes each page with a "--- Page N ---"
        # marker — recover the page number per chunk by tracking the
        # latest marker we saw in the original text up to the chunk's
        # position.
        page_markers: list[tuple[int, int]] = []  # (offset, page_number)
        if ftype == "pdf":
            for match in re.finditer(r"--- Page (\d+) ---", text):
                page_markers.append((match.start(), int(match.group(1))))

        cursor = 0
        for idx, chunk in enumerate(chunks):
            page = None
            if page_markers:
                # Find chunk start in the original text starting from
                # cursor — RecursiveCharacterTextSplitter overlaps a
                # little, but the chunk content remains a substring of
                # the source.
                start = text.find(chunk[:80], cursor)
                if start == -1:
                    start = cursor
                cursor = max(cursor, start)
                # Latest marker offset <= start.
                for offset, page_num in page_markers:
                    if offset <= start:
                        page = page_num
                    else:
                        break

            entry: dict = {
                **metadata,
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "chunk_length": len(chunk),
            }
            if page is not None:
                entry["page"] = page
            chunk_metadatas.append(entry)

        return self._add_documents_sync(chunks, chunk_metadatas)

    # ------------------------------------------------------------------
    # Async wrappers (safe for FastAPI)
    # ------------------------------------------------------------------

    async def add_documents(
        self,
        texts: list[str],
        metadatas: list[dict],
        batch_size: int = 100,
    ) -> list[str]:
        """Add documents — async-safe wrapper."""
        return await asyncio.to_thread(
            self._add_documents_sync, texts, metadatas, batch_size
        )

    async def add_document_with_chunking(
        self,
        text: str,
        metadata: dict,
        file_type: Optional[str] = None,
    ) -> list[str]:
        """Chunk + add document — async-safe wrapper."""
        return await asyncio.to_thread(
            self._add_document_with_chunking_sync, text, metadata, file_type
        )

    # ------------------------------------------------------------------
    # Search (async-safe)
    # ------------------------------------------------------------------

    async def similarity_search(
        self,
        query: str,
        k: int = 5,
        pre_filter: Optional[dict] = None,
        score_threshold: Optional[float] = None,
    ) -> list[LangChainDocument]:
        """Similarity search with score thresholding.

        Returns only documents above the score threshold.
        """
        if score_threshold is None:
            score_threshold = settings.vector_score_threshold

        results_with_scores = await self.similarity_search_with_score(
            query=query, k=k, pre_filter=pre_filter
        )

        filtered = [
            doc
            for doc, score in results_with_scores
            if score >= score_threshold
        ]
        logger.info(
            "Search: %d results above threshold %.2f (out of %d)",
            len(filtered),
            score_threshold,
            len(results_with_scores),
        )
        return filtered

    async def similarity_search_with_score(
        self,
        query: str,
        k: int = 5,
        pre_filter: Optional[dict] = None,
    ) -> list[tuple[LangChainDocument, float]]:
        """Search with cosine similarity scores — async-safe."""

        def _search() -> list[tuple[LangChainDocument, float]]:
            return self.vector_store.similarity_search_with_score(
                query=query,
                k=k,
                pre_filter=pre_filter,
            )

        return await asyncio.to_thread(_search)

    async def mmr_search(
        self,
        query: str,
        k: int = 5,
        fetch_k: int = 20,
        lambda_mult: float = 0.7,
        pre_filter: Optional[dict] = None,
    ) -> list[LangChainDocument]:
        """Maximal Marginal Relevance search for diverse results.

        Args:
            lambda_mult: 0 = max diversity, 1 = max relevance (default 0.7).
        """

        def _search() -> list[LangChainDocument]:
            return self.vector_store.max_marginal_relevance_search(
                query=query,
                k=k,
                fetch_k=fetch_k,
                lambda_mult=lambda_mult,
                pre_filter=pre_filter,
            )

        results = await asyncio.to_thread(_search)
        logger.info("MMR search: %d results (fetch_k=%d, lambda=%.2f)", len(results), fetch_k, lambda_mult)
        return results

    # ------------------------------------------------------------------
    # Retriever factory (for LCEL chains)
    # ------------------------------------------------------------------

    def get_retriever(
        self,
        search_type: str = "mmr",
        k: int = 5,
        pre_filter: Optional[dict] = None,
        score_threshold: Optional[float] = None,
        fetch_k: int = 20,
        lambda_mult: float = 0.7,
    ):
        """Create a LangChain retriever with access control.

        search_type: 'similarity', 'mmr', or 'similarity_score_threshold'
        """
        if score_threshold is None:
            score_threshold = settings.vector_score_threshold

        search_kwargs: dict[str, Any] = {"k": k}

        if pre_filter:
            search_kwargs["pre_filter"] = pre_filter

        if search_type == "mmr":
            search_kwargs["fetch_k"] = fetch_k
            search_kwargs["lambda_mult"] = lambda_mult
        elif search_type == "similarity_score_threshold":
            search_kwargs["score_threshold"] = score_threshold

        return self.vector_store.as_retriever(
            search_type=search_type,
            search_kwargs=search_kwargs,
        )

    # ------------------------------------------------------------------
    # Hybrid Search retriever (vector + full-text with RRF)
    # ------------------------------------------------------------------

    def get_hybrid_retriever(
        self,
        k: int = 5,
        pre_filter: Optional[dict] = None,
        vector_penalty: float = 60.0,
        fulltext_penalty: float = 60.0,
    ):
        """Create a hybrid retriever combining vector + full-text search.

        Uses Reciprocal Rank Fusion (RRF) to merge results from both searches.
        Requires a full-text Atlas Search index named settings.fulltext_index_name.
        """
        return MongoDBAtlasHybridSearchRetriever(
            vectorstore=self.vector_store,
            search_index_name=settings.fulltext_index_name,
            k=k,
            pre_filter=pre_filter,
            vector_penalty=vector_penalty,
            fulltext_penalty=fulltext_penalty,
        )

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_by_metadata(self, filter_query: dict) -> int:
        """Delete documents by metadata filter — async-safe."""

        def _delete() -> int:
            result = self._collection.delete_many(filter_query)
            return result.deleted_count

        return await asyncio.to_thread(_delete)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    async def get_stats(self) -> dict:
        """Get vector store statistics — async-safe."""

        def _stats() -> dict:
            if self._collection is None:
                return {
                    "total_chunks": 0,
                    "unique_documents": 0,
                    "embedding_model": settings.embedding_model,
                    "embedding_dimension": settings.vector_dimension,
                    "chunk_size": settings.chunk_size,
                    "chunk_overlap": settings.chunk_overlap,
                }

            total_chunks = self._collection.count_documents({})
            pipeline = [
                {"$group": {"_id": "$source_file"}},
                {"$count": "unique_files"},
            ]
            result = list(self._collection.aggregate(pipeline))
            unique_files = result[0]["unique_files"] if result else 0

            return {
                "total_chunks": total_chunks,
                "unique_documents": unique_files,
                "embedding_model": settings.embedding_model,
                "embedding_dimension": settings.vector_dimension,
                "chunk_size": settings.chunk_size,
                "chunk_overlap": settings.chunk_overlap,
            }

        return await asyncio.to_thread(_stats)


# Global singleton
vector_store_service = VectorStoreService()
