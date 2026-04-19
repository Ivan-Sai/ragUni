from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field, GetCoreSchemaHandler
from pydantic_core import core_schema
from bson import ObjectId


class PyObjectId(ObjectId):
    """Custom ObjectId type compatible with Pydantic v2."""

    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type: type, _handler: GetCoreSchemaHandler) -> core_schema.CoreSchema:
        return core_schema.no_info_plain_validator_function(
            cls._validate,
            serialization=core_schema.to_string_ser_schema(),
        )

    @classmethod
    def _validate(cls, v: object) -> ObjectId:
        if isinstance(v, ObjectId):
            return v
        if isinstance(v, str) and ObjectId.is_valid(v):
            return ObjectId(v)
        raise ValueError(f"Invalid ObjectId: {v}")


class DocumentChunk(BaseModel):
    """Single chunk of a document with its vector embedding"""

    chunk_id: str = Field(default_factory=lambda: str(ObjectId()))
    text: str
    chunk_index: int = Field(ge=0)
    embedding: list[float]
    access_level: str = "public"
    faculty: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class Document(BaseModel):
    """Document model stored in MongoDB"""

    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    filename: str
    file_type: str  # pdf, xlsx, docx
    access_level: str = "public"
    faculty: Optional[str] = None
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    chunks: list[DocumentChunk] = Field(default_factory=list)
    total_chunks: int = 0
    metadata: dict = Field(default_factory=dict)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }


class DocumentResponse(BaseModel):
    """Response model for document operations"""

    id: str
    filename: str
    file_type: str
    access_level: str = "public"
    faculty: Optional[str] = None
    uploaded_at: datetime
    total_chunks: int
    message: str


class ChatRequest(BaseModel):
    """Request model for chat endpoint"""

    question: str = Field(..., min_length=1, max_length=5000)
    session_id: Optional[str] = None
    max_tokens: int = Field(default=1000, ge=1, le=4000)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)


class SourceCitation(BaseModel):
    """Source citation in chat response."""
    source_file: str
    file_type: str = ""
    chunk_index: int = 0
    total_chunks: int = 0
    text: str = ""


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""

    answer: str
    sources: list[SourceCitation]
    processing_time: float
