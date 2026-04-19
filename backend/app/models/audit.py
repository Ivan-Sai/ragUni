"""Audit log models.

Records *who did what to whom* for every privileged operation. The log is
append-only at the application level (there is no endpoint that mutates
past entries) and is intended as a forensic trail — if a teacher disputes
a rejection, or a student's chat disappears, the audit log explains it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class AuditAction(str, Enum):
    """Enumerated audit actions.

    Keep the list closed: adding an action requires a code change so we
    never store free-form strings that drift across releases.
    """

    USER_APPROVED = "user.approved"
    USER_REJECTED = "user.rejected"
    USER_BLOCKED = "user.blocked"
    USER_UNBLOCKED = "user.unblocked"
    USER_ROLE_CHANGED = "user.role_changed"

    DOCUMENT_UPLOADED = "document.uploaded"
    DOCUMENT_DELETED = "document.deleted"

    CHAT_SESSION_DELETED = "chat.session_deleted"


class AuditLogEntry(BaseModel):
    """Single audit record as stored in MongoDB."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor_id: str = Field(..., description="User id of the person performing the action")
    actor_role: str
    action: AuditAction
    resource_type: str = Field(..., description="e.g. 'user', 'document', 'chat_session'")
    resource_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditLogResponse(BaseModel):
    """Single audit record in API responses. Flattens timestamp to ISO string."""

    id: str
    timestamp: datetime
    actor_id: str
    actor_role: str
    action: AuditAction
    resource_type: str
    resource_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditLogListResponse(BaseModel):
    entries: list[AuditLogResponse]
    total: int
    skip: int
    limit: int


class AuditLogFilter(BaseModel):
    """Optional filters supported by the audit-log listing endpoint."""

    actor_id: Optional[str] = None
    action: Optional[AuditAction] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
