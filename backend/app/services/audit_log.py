"""Audit log service — append-only record of privileged actions.

The service deliberately *never* raises on failure when called from a
business endpoint: if audit writes fail we log the error but do not
block the user operation, because losing an audit entry is strictly
better than rolling back an approval that already happened.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.models.audit import (
    AuditAction,
    AuditLogEntry,
    AuditLogFilter,
    AuditLogResponse,
)
from app.services.database import get_database

logger = logging.getLogger(__name__)

_COLLECTION = "audit_logs"


async def record_action(
    *,
    actor: dict[str, Any],
    action: AuditAction,
    resource_type: str,
    resource_id: str,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Persist an audit entry. Never raises — logs on failure."""
    try:
        db = get_database()
        entry = AuditLogEntry(
            actor_id=str(actor.get("_id", "unknown")),
            actor_role=str(actor.get("role", "unknown")),
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            metadata=metadata or {},
        )
        await db[_COLLECTION].insert_one(entry.model_dump())
    except Exception as exc:  # noqa: BLE001 — deliberate: never block caller
        # Catching broadly is justified *only here*: audit persistence must
        # not break business flows. The failure is logged so ops can alert.
        logger.error(
            "Failed to write audit log entry: action=%s resource=%s:%s (%s)",
            action.value,
            resource_type,
            resource_id,
            type(exc).__name__,
        )


async def list_entries(
    filters: AuditLogFilter,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[AuditLogResponse], int]:
    """List entries matching the filter, newest-first."""
    db = get_database()

    query: dict[str, Any] = {}
    if filters.actor_id:
        query["actor_id"] = filters.actor_id
    if filters.action:
        query["action"] = filters.action.value
    if filters.resource_type:
        query["resource_type"] = filters.resource_type
    if filters.resource_id:
        query["resource_id"] = filters.resource_id

    total = await db[_COLLECTION].count_documents(query)
    cursor = (
        db[_COLLECTION]
        .find(query)
        .sort("timestamp", -1)
        .skip(skip)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)

    entries = [
        AuditLogResponse(
            id=str(doc["_id"]),
            timestamp=doc.get("timestamp", datetime.now(timezone.utc)),
            actor_id=doc["actor_id"],
            actor_role=doc["actor_role"],
            action=doc["action"],
            resource_type=doc["resource_type"],
            resource_id=doc["resource_id"],
            metadata=doc.get("metadata", {}),
        )
        for doc in docs
    ]
    return entries, total
