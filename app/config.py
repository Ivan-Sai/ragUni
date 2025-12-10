from pydantic_settings import BaseSettings
from pydantic import validator
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # MongoDB Configuration
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "university_knowledge"

    # Deepseek API Configuration
    deepseek_api_key: str
    deepseek_api_base: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # Embedding Configuration
    embedding_model: str = "intfloat/multilingual-e5-large"
    vector_dimension: int = 1024

    # Chunking Configuration (optimized for RAG)
    chunk_size: int = 1000  # Increased for better context
    chunk_overlap: int = 200  # Increased for better continuity

    # Vector Search Configuration
    vector_index_name: str = "vector_index"

    # MongoDB Atlas API Configuration (for automatic index creation)
    atlas_public_key: Optional[str] = None
    atlas_private_key: Optional[str] = None
    atlas_project_id: Optional[str] = None
    atlas_cluster_name: Optional[str] = None

    # Application Settings
    max_upload_size: int = 10 * 1024 * 1024  # 10MB
    top_k_results: int = 5

    # LLM Settings
    llm_temperature: float = 0.7
    llm_max_tokens: int = 1000

    class Config:
        env_file = ".env"
        case_sensitive = False

    @validator('deepseek_api_key')
    def validate_api_key(cls, v):
        """Validate API key is set"""
        if not v or v == 'your_deepseek_api_key_here':
            raise ValueError(
                '❌ DEEPSEEK_API_KEY must be set in .env file. '
                'Get your key from https://platform.deepseek.com/'
            )
        return v

    def get_masked_api_key(self) -> str:
        """Return masked API key for safe logging"""
        if len(self.deepseek_api_key) > 8:
            return f"{self.deepseek_api_key[:4]}...{self.deepseek_api_key[-4:]}"
        return "***"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
