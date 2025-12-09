from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from bson import ObjectId


class PyObjectId(ObjectId):
    """Custom ObjectId type for Pydantic"""

    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid ObjectId")
        return ObjectId(v)

    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema):
        field_schema.update(type="string")


class DocumentChunk(BaseModel):
    """Single chunk of a document with its vector embedding"""

    chunk_id: str = Field(default_factory=lambda: str(ObjectId()))
    text: str
    chunk_index: int
    embedding: List[float]
    metadata: dict = Field(default_factory=dict)


class Document(BaseModel):
    """Document model stored in MongoDB"""

    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    filename: str
    file_type: str  # pdf, xlsx, docx
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    chunks: List[DocumentChunk] = Field(default_factory=list)
    total_chunks: int = 0
    metadata: dict = Field(default_factory=dict)

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class DocumentResponse(BaseModel):
    """Response model for document operations"""

    id: str
    filename: str
    file_type: str
    uploaded_at: datetime
    total_chunks: int
    message: str


class ChatRequest(BaseModel):
    """Request model for chat endpoint"""

    question: str
    max_tokens: int = 1000
    temperature: float = 0.7


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""

    answer: str
    sources: List[dict]
    processing_time: float
