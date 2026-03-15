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

            logger.info("Loading embedding model: %s", settings.embedding_model)
            self._embeddings = FastEmbedEmbeddings(
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
        user_faculty: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build a MongoDB pre_filter based on user role and faculty.

        Access levels:
        - public: visible to everyone
        - faculty: visible to users of the same faculty + teachers/admins
        - restricted: visible to teachers and admins only
        """
        # Validate role
        if user_role not in _VALID_ROLES:
            logger.warning("Unknown role '%s', defaulting to student access", user_role)
            user_role = "student"

        if user_role == "admin":
            # Admins see everything
            return {}

        if user_role == "teacher":
            # Teachers see public + restricted + their faculty docs
            conditions: list[dict] = [
                {"access_level": "public"},
                {"access_level": "restricted"},
            ]
            if user_faculty:
                conditions.append(
                    {"$and": [{"access_level": "faculty"}, {"faculty": user_faculty}]}
                )
            return {"$or": conditions}

        # Students: public + their own faculty docs
        conditions = [{"access_level": "public"}]
        if user_faculty:
            conditions.append(
                {"$and": [{"access_level": "faculty"}, {"faculty": user_faculty}]}
            )
        return {"$or": conditions}

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def chunk_text(self, text: str) -> list[str]:
        """Split text into semantic chunks."""
        if not text or not text.strip():
            return []
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
    ) -> list[str]:
        """Chunk text + add to vector store (blocking)."""
        chunks = self.chunk_text(text)
        if not chunks:
            raise ValueError("No chunks created from text")

        chunk_metadatas = [
            {
                **metadata,
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "chunk_length": len(chunk),
            }
            for idx, chunk in enumerate(chunks)
        ]
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
    ) -> list[str]:
        """Chunk + add document — async-safe wrapper."""
        return await asyncio.to_thread(
            self._add_document_with_chunking_sync, text, metadata
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
