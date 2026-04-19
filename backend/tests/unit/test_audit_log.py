"""Tests for the audit log service.

The service has two contracts we care about:

1. ``record_action`` is never allowed to raise, no matter what goes
   wrong with the database — a failing audit write must not block a
   successful business operation.
2. ``list_entries`` applies filters correctly and returns newest-first.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

from app.models.audit import AuditAction, AuditLogFilter
from app.services import audit_log


@pytest.fixture
def admin_actor():
    return {
        "_id": ObjectId("507f1f77bcf86cd799439099"),
        "email": "admin@knu.ua",
        "role": "admin",
    }


@pytest.fixture
def mock_audit_db():
    mock_collection = MagicMock()
    mock_collection.insert_one = AsyncMock()
    mock_collection.find = MagicMock()
    mock_collection.count_documents = AsyncMock(return_value=0)

    db = MagicMock()
    db.__getitem__.return_value = mock_collection

    with patch("app.services.audit_log.get_database", return_value=db):
        yield mock_collection


class TestRecordAction:
    @pytest.mark.asyncio
    async def test_persists_entry(self, admin_actor, mock_audit_db):
        await audit_log.record_action(
            actor=admin_actor,
            action=AuditAction.USER_APPROVED,
            resource_type="user",
            resource_id="507f1f77bcf86cd799439012",
            metadata={"target_email": "t@knu.ua"},
        )
        mock_audit_db.insert_one.assert_awaited_once()
        persisted = mock_audit_db.insert_one.call_args.args[0]
        assert persisted["action"] == "user.approved"
        assert persisted["actor_role"] == "admin"
        assert persisted["resource_id"] == "507f1f77bcf86cd799439012"
        assert persisted["metadata"]["target_email"] == "t@knu.ua"

    @pytest.mark.asyncio
    async def test_never_raises_on_db_failure(self, admin_actor, mock_audit_db):
        """A failing audit write must not propagate to the caller."""
        mock_audit_db.insert_one.side_effect = RuntimeError("mongo is down")

        # Must not raise:
        await audit_log.record_action(
            actor=admin_actor,
            action=AuditAction.USER_BLOCKED,
            resource_type="user",
            resource_id="abc",
        )

    @pytest.mark.asyncio
    async def test_defaults_missing_actor_fields(self, mock_audit_db):
        """An actor dict missing _id / role still produces a record."""
        await audit_log.record_action(
            actor={},
            action=AuditAction.CHAT_SESSION_DELETED,
            resource_type="chat_session",
            resource_id="sess-1",
        )
        persisted = mock_audit_db.insert_one.call_args.args[0]
        assert persisted["actor_id"] == "unknown"
        assert persisted["actor_role"] == "unknown"


class TestListEntries:
    @pytest.mark.asyncio
    async def test_applies_filters(self, mock_audit_db):
        mock_audit_db.count_documents = AsyncMock(return_value=0)
        chain = MagicMock()
        chain.sort.return_value = chain
        chain.skip.return_value = chain
        chain.limit.return_value = chain
        chain.to_list = AsyncMock(return_value=[])
        mock_audit_db.find.return_value = chain

        filters = AuditLogFilter(
            actor_id="507f1f77bcf86cd799439099",
            action=AuditAction.USER_APPROVED,
            resource_type="user",
        )
        entries, total = await audit_log.list_entries(filters, skip=0, limit=20)

        assert entries == []
        assert total == 0
        query = mock_audit_db.find.call_args.args[0]
        assert query["actor_id"] == "507f1f77bcf86cd799439099"
        assert query["action"] == "user.approved"
        assert query["resource_type"] == "user"

    @pytest.mark.asyncio
    async def test_returns_newest_first_and_maps_fields(self, mock_audit_db):
        now = datetime(2025, 4, 1, 12, 0, tzinfo=timezone.utc)
        doc = {
            "_id": ObjectId("507f1f77bcf86cd799439055"),
            "timestamp": now,
            "actor_id": "507f1f77bcf86cd799439099",
            "actor_role": "admin",
            "action": "user.approved",
            "resource_type": "user",
            "resource_id": "507f1f77bcf86cd799439012",
            "metadata": {"target_email": "t@knu.ua"},
        }
        chain = MagicMock()
        chain.sort.return_value = chain
        chain.skip.return_value = chain
        chain.limit.return_value = chain
        chain.to_list = AsyncMock(return_value=[doc])
        mock_audit_db.find.return_value = chain
        mock_audit_db.count_documents = AsyncMock(return_value=1)

        entries, total = await audit_log.list_entries(AuditLogFilter(), 0, 10)
        chain.sort.assert_called_once_with("timestamp", -1)
        assert total == 1
        assert entries[0].id == "507f1f77bcf86cd799439055"
        assert entries[0].action == AuditAction.USER_APPROVED
        assert entries[0].metadata == {"target_email": "t@knu.ua"}
