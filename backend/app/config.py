from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic import field_validator, ConfigDict, Field
from functools import lru_cache
from typing import Optional

# Backend root: backend/app/config.py → ../backend/.env
_backend_root = Path(__file__).resolve().parent.parent
_env_file = str(_backend_root / ".env") if (_backend_root / ".env").exists() else ".env"


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # MongoDB Configuration
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "university_knowledge"
    mongodb_max_pool_size: int = Field(default=10, ge=1, le=100)
    mongodb_min_pool_size: int = Field(default=2, ge=0, le=20)

    # Security
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, gt=0, le=1440)
    refresh_token_expire_days: int = Field(default=7, gt=0, le=90)

    # CORS
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

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
    fulltext_index_name: str = "text_index"
    use_hybrid_search: bool = True
    vector_score_threshold: float = Field(default=0.55, ge=0.0, le=1.0)

    # MongoDB Atlas API Configuration (for automatic index creation)
    atlas_public_key: Optional[str] = None
    atlas_private_key: Optional[str] = None
    atlas_project_id: Optional[str] = None
    atlas_cluster_name: Optional[str] = None

    # Application Settings
    max_upload_size: int = 10 * 1024 * 1024  # 10MB
    max_extracted_text_size: int = 50 * 1024 * 1024  # 50MB
    top_k_results: int = 5

    # LLM Settings
    llm_temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    llm_max_tokens: int = Field(default=1000, ge=1, le=8000)
    llm_timeout_seconds: int = Field(default=30, gt=0, le=120)

    # Observability
    environment: str = Field(default="development")
    log_format: str = Field(default="text", description="text | json")
    log_level: str = Field(default="INFO")
    sentry_dsn: Optional[str] = None
    sentry_traces_sample_rate: float = Field(default=0.1, ge=0.0, le=1.0)
    release: Optional[str] = None
    enable_metrics: bool = Field(
        default=False,
        description="When True, mount a /metrics Prometheus endpoint",
    )

    # Password reset
    password_reset_expire_minutes: int = Field(default=15, gt=0, le=60)

    # Email (Gmail SMTP)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_email: Optional[str] = None
    smtp_password: Optional[str] = None
    frontend_url: str = "http://localhost:3000"

    # Conversation context
    max_conversation_messages: int = Field(default=10, ge=2, le=30)

    model_config = ConfigDict(env_file=_env_file, case_sensitive=False, extra="ignore")

    @field_validator('secret_key')
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Validate secret key is set and sufficiently long."""
        if not v or v.startswith("change-me"):
            raise ValueError(
                'SECRET_KEY must be set to a strong random string '
                '(at least 32 characters) in .env file.'
            )
        if len(v) < 32:
            raise ValueError(
                'SECRET_KEY must be at least 32 characters long.'
            )
        return v

    @field_validator('deepseek_api_key')
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Validate API key is set"""
        if not v or v == 'your_deepseek_api_key_here':
            raise ValueError(
                'DEEPSEEK_API_KEY must be set in .env file. '
                'Get your key from https://platform.deepseek.com/'
            )
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def get_masked_api_key(self) -> str:
        """Return masked API key for safe logging"""
        return "[REDACTED]"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
