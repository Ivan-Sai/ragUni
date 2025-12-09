from pydantic_settings import BaseSettings
from functools import lru_cache


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

    # Chunking Configuration
    chunk_size: int = 512
    chunk_overlap: int = 50

    # Application Settings
    max_upload_size: int = 10 * 1024 * 1024  # 10MB
    top_k_results: int = 5

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
