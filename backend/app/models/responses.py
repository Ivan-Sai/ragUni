"""Shared response models for endpoints that previously returned raw dicts.

CLAUDE.md mandates typed Pydantic models on every endpoint response so
the OpenAPI schema is accurate and clients get end-to-end type safety.
This module centralises the small response envelopes that don't deserve
a home in a domain module — health checks, list pagination wrappers,
delete acknowledgements, etc.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.models.document import DocumentResponse


# ---------------------------------------------------------------------------
# Generic acks
# ---------------------------------------------------------------------------


class MessageResponse(BaseModel):
    """Plain ``{message: ...}`` envelope used by simple acks."""

    message: str


class DeleteResponse(BaseModel):
    """Acknowledgement for delete endpoints — message + counts."""

    message: str
    filename: Optional[str] = None
    chunks_deleted: int = Field(default=0, ge=0)


# ---------------------------------------------------------------------------
# Health / version
# ---------------------------------------------------------------------------


class HealthConfiguration(BaseModel):
    """Subset of settings safe to expose on the health endpoint.

    Intentionally narrow — model + chunk size, not API keys / secrets /
    cluster URIs. Anything sensitive belongs behind admin auth.
    """

    embedding_model: Optional[str] = None
    llm_model: Optional[str] = None


class HealthResponse(BaseModel):
    """Response of GET /api/v1/chat/health."""

    status: str
    timestamp: datetime
    documents_count: Optional[int] = None
    vector_store_initialized: bool = False
    configuration: Optional[HealthConfiguration] = None


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------


class DocumentListResponse(BaseModel):
    """Response of GET /api/v1/documents/list."""

    documents: list[DocumentResponse]
    total: int = Field(ge=0)


class DocumentPreviewResponse(BaseModel):
    """Response of GET /api/v1/documents/{id}/preview.

    Mirrors the shape returned by the live endpoint — both the raw
    text (``text``) and the type-specific structured view
    (``structured_text`` / ``structured_records``) so the UI can pick
    what to render based on ``extraction_method``.
    """

    id: str
    filename: Optional[str] = None
    file_type: Optional[str] = None
    total_chunks: int = Field(default=0, ge=0)
    text: str = ""
    structured_text: Optional[str] = None
    structured_records: list[dict[str, Any]] = Field(default_factory=list)
    extraction_method: str = "raw"
    structured_records_count: int = Field(default=0, ge=0)


class DocumentsBlock(BaseModel):
    """Aggregate counts of documents by type — nested in stats."""

    total: int = Field(default=0, ge=0)
    by_type: dict[str, int] = Field(default_factory=dict)


class DocumentStatsResponse(BaseModel):
    """Response of GET /api/v1/documents/stats."""

    documents: DocumentsBlock
    vector_store: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Chat history
# ---------------------------------------------------------------------------


class ChatSessionSummary(BaseModel):
    """One row in the chat-history list."""

    session_id: str
    title: Optional[str] = None
    last_message: Optional[str] = None
    message_count: int = Field(ge=0)
    created_at: datetime
    updated_at: datetime


class ChatHistoryListResponse(BaseModel):
    """Response of GET /api/v1/chat/history."""

    sessions: list[ChatSessionSummary]
    total: int = Field(ge=0)


class ChatMessage(BaseModel):
    """One message inside a session detail response."""

    role: str
    content: str
    timestamp: datetime
    sources: list[dict[str, Any]] = Field(default_factory=list)


class ChatSessionDetailResponse(BaseModel):
    """Response of GET /api/v1/chat/history/{session_id}."""

    session_id: str
    title: Optional[str] = None
    messages: list[ChatMessage]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class DailyCount(BaseModel):
    """One bucket of the per-day counters returned by analytics."""

    date: str
    count: int = Field(ge=0)


class AnalyticsSummaryResponse(BaseModel):
    """Response of GET /api/v1/admin/analytics."""

    total_queries: int = Field(ge=0)
    total_logins: int = Field(ge=0)
    total_uploads: int = Field(ge=0)
    queries_per_day: list[DailyCount] = Field(default_factory=list)
    active_users_per_day: list[DailyCount] = Field(default_factory=list)
    avg_response_time: Optional[float] = None
