"""Chat history models for conversation storage."""

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models.document import SourceCitation


class ChatMessage(BaseModel):
    """Single message in a chat session."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)
    sources: list[SourceCitation] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ChatSession(BaseModel):
    """Chat session containing messages."""

    user_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    title: Optional[str] = None
    messages: list[ChatMessage] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
