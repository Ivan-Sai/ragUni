from typing import List
from fastembed import TextEmbedding
from app.config import get_settings

settings = get_settings()


class Vectorizer:
    """Text vectorization using FastEmbed"""

    def __init__(self):
        self.model = None
        self.model_name = settings.embedding_model

    def initialize(self):
        """Initialize the embedding model"""
        if self.model is None:
            print(f"Loading embedding model: {self.model_name}")
            self.model = TextEmbedding(model_name=self.model_name)
            print("✓ Embedding model loaded")

    async def embed_text(self, text: str) -> List[float]:
        """
        Create embedding for a single text

        Args:
            text: Input text to embed

        Returns:
            List of floats representing the embedding vector
        """
        if self.model is None:
            self.initialize()

        # FastEmbed returns a generator, convert to list
        embeddings = list(self.model.embed([text]))

        if embeddings and len(embeddings) > 0:
            return embeddings[0].tolist()
        else:
            raise ValueError("Failed to generate embedding")

    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """
        Create embeddings for multiple texts

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if self.model is None:
            self.initialize()

        # FastEmbed can batch process
        embeddings = list(self.model.embed(texts))
        return [emb.tolist() for emb in embeddings]

    async def search_similar(
        self,
        query_embedding: List[float],
        document_embeddings: List[List[float]],
        top_k: int = 5
    ) -> List[int]:
        """
        Find most similar documents using cosine similarity

        Args:
            query_embedding: Query vector
            document_embeddings: List of document vectors
            top_k: Number of top results to return

        Returns:
            List of indices of most similar documents
        """
        import numpy as np

        query_vec = np.array(query_embedding)
        doc_vecs = np.array(document_embeddings)

        # Calculate cosine similarity
        similarities = np.dot(doc_vecs, query_vec) / (
            np.linalg.norm(doc_vecs, axis=1) * np.linalg.norm(query_vec)
        )

        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1][:top_k]

        return top_indices.tolist()


# Global vectorizer instance
vectorizer = Vectorizer()
