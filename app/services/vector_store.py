"""
LangChain-based Vector Store Service
Uses MongoDB Atlas Vector Search for efficient semantic search
"""
from typing import List, Dict, Optional
from langchain_mongodb import MongoDBAtlasVectorSearch
from langchain_community.embeddings import FastEmbedEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document as LangChainDocument
from pymongo import MongoClient
from pymongo.collection import Collection
from app.config import get_settings

settings = get_settings()


class VectorStoreService:
    """
    LangChain-powered vector store with MongoDB Atlas

    Features:
    - Automatic embedding generation with FastEmbed
    - MongoDB Atlas Vector Search for scalable similarity search
    - Smart text chunking with RecursiveCharacterTextSplitter
    - Metadata management
    """

    def __init__(self):
        self._client: Optional[MongoClient] = None
        self._collection: Optional[Collection] = None
        self._embeddings = None
        self._vector_store = None
        self._text_splitter = None

    def initialize(self):
        """Initialize the vector store service"""
        if self._vector_store is not None:
            return

        print("🔧 Initializing LangChain Vector Store...")

        # MongoDB client (synchronous for LangChain compatibility)
        self._client = MongoClient(settings.mongodb_url)
        self._collection = self._client[settings.mongodb_db_name]["document_chunks"]

        # FastEmbed embeddings (multilingual-e5-large, 1024d)
        print(f"📦 Loading embedding model: {settings.embedding_model}")
        self._embeddings = FastEmbedEmbeddings(
            model_name=settings.embedding_model
        )

        # MongoDB Atlas Vector Search
        self._vector_store = MongoDBAtlasVectorSearch(
            collection=self._collection,
            embedding=self._embeddings,
            index_name="vector_index",
            text_key="text",
            embedding_key="embedding",
            relevance_score_fn="cosine"
        )

        # Text splitter with smart chunking
        self._text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""]
        )

        print("✓ Vector Store initialized")

    @property
    def vector_store(self) -> MongoDBAtlasVectorSearch:
        """Get vector store instance"""
        if self._vector_store is None:
            self.initialize()
        return self._vector_store

    @property
    def text_splitter(self) -> RecursiveCharacterTextSplitter:
        """Get text splitter instance"""
        if self._text_splitter is None:
            self.initialize()
        return self._text_splitter

    def chunk_text(self, text: str) -> List[str]:
        """
        Split text into semantic chunks

        Args:
            text: Input text to chunk

        Returns:
            List of text chunks
        """
        if not text or len(text.strip()) == 0:
            return []

        chunks = self.text_splitter.split_text(text)
        return chunks

    def add_documents(
        self,
        texts: List[str],
        metadatas: List[Dict],
        batch_size: int = 100
    ) -> List[str]:
        """
        Add documents to vector store with automatic embedding

        Args:
            texts: List of text chunks
            metadatas: List of metadata dicts for each chunk
            batch_size: Batch size for processing

        Returns:
            List of document IDs
        """
        if len(texts) != len(metadatas):
            raise ValueError("texts and metadatas must have same length")

        # Process in batches to avoid memory issues
        all_ids = []
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i + batch_size]
            batch_metadatas = metadatas[i:i + batch_size]

            # Add to vector store (automatically creates embeddings!)
            ids = self.vector_store.add_texts(
                texts=batch_texts,
                metadatas=batch_metadatas
            )
            all_ids.extend(ids)

        return all_ids

    def add_document_with_chunking(
        self,
        text: str,
        metadata: Dict
    ) -> List[str]:
        """
        Add document with automatic chunking and embedding

        Args:
            text: Document text
            metadata: Base metadata for the document

        Returns:
            List of chunk IDs
        """
        # Chunk text
        chunks = self.chunk_text(text)

        if not chunks:
            raise ValueError("No chunks created from text")

        # Create metadata for each chunk
        chunk_metadatas = [
            {
                **metadata,
                "chunk_index": idx,
                "total_chunks": len(chunks),
                "chunk_length": len(chunk)
            }
            for idx, chunk in enumerate(chunks)
        ]

        # Add to vector store
        ids = self.add_documents(chunks, chunk_metadatas)

        return ids

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter: Optional[Dict] = None
    ) -> List[LangChainDocument]:
        """
        Search for similar documents

        Args:
            query: Search query
            k: Number of results to return
            filter: Optional metadata filter

        Returns:
            List of LangChain Document objects with content and metadata
        """
        # Automatic embedding + search!
        results = self.vector_store.similarity_search(
            query=query,
            k=k,
            filter=filter
        )

        return results

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 5,
        filter: Optional[Dict] = None
    ) -> List[tuple]:
        """
        Search with similarity scores

        Args:
            query: Search query
            k: Number of results
            filter: Optional metadata filter

        Returns:
            List of (Document, score) tuples
        """
        results = self.vector_store.similarity_search_with_score(
            query=query,
            k=k,
            filter=filter
        )

        return results

    def delete_by_metadata(self, filter: Dict) -> int:
        """
        Delete documents by metadata filter

        Args:
            filter: MongoDB filter query

        Returns:
            Number of deleted documents
        """
        result = self._collection.delete_many(filter)
        return result.deleted_count

    def get_stats(self) -> Dict:
        """Get vector store statistics"""
        total_chunks = self._collection.count_documents({})

        # Get unique documents count
        pipeline = [
            {"$group": {"_id": "$source_file"}},
            {"$count": "unique_files"}
        ]
        result = list(self._collection.aggregate(pipeline))
        unique_files = result[0]["unique_files"] if result else 0

        return {
            "total_chunks": total_chunks,
            "unique_documents": unique_files,
            "embedding_model": settings.embedding_model,
            "embedding_dimension": settings.vector_dimension,
            "chunk_size": settings.chunk_size,
            "chunk_overlap": settings.chunk_overlap
        }


# Global singleton instance
vector_store_service = VectorStoreService()
