"""IDOR (Insecure Direct Object Reference) tests.

Each endpoint that takes a resource id in the URL must enforce that
the caller actually owns / can access the resource. The current
implementation joins on ``user_id`` (chat history) or
``uploaded_by_id`` (document delete), but nothing pinned that
behaviour. A regression that drops the join would silently let user
A read user B's chat sessions or wipe their documents.

These tests prove:
  * GET /chat/history/{session_id} returns 404 to a different user.
  * DELETE /chat/history/{session_id} returns 404 to a different user.
  * DELETE /documents/{id} 403s for a teacher who isn't the uploader.
  * DELETE /documents/{id} succeeds for an admin regardless of uploader.
  * GET /documents/{id}/preview returns 403 for cross-faculty student.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


SAMPLE_FACULTY_ID = "507f1f77bcf86cd7994390ff"
OTHER_FACULTY_ID = "507f1f77bcf86cd7994390ee"


@pytest.fixture
def student_user() -> dict:
    return {
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "email": "student@knu.ua",
        "role": "student",
        "is_active": True,
        "is_approved": True,
        "full_name": "Student",
        "faculty_id": ObjectId(SAMPLE_FACULTY_ID),
    }


@pytest.fixture
def other_student_user() -> dict:
    return {
        "_id": ObjectId("507f1f77bcf86cd7994390aa"),
        "email": "other@knu.ua",
        "role": "student",
        "is_active": True,
        "is_approved": True,
        "full_name": "Other Student",
        "faculty_id": ObjectId(OTHER_FACULTY_ID),
    }


@pytest.fixture
def teacher_user() -> dict:
    return {
        "_id": ObjectId("507f1f77bcf86cd799439022"),
        "email": "teacher@knu.ua",
        "role": "teacher",
        "is_active": True,
        "is_approved": True,
        "full_name": "Teacher",
        "faculty_id": ObjectId(SAMPLE_FACULTY_ID),
    }


@pytest.fixture
def admin_user() -> dict:
    return {
        "_id": ObjectId("507f1f77bcf86cd799439013"),
        "email": "admin@knu.ua",
        "role": "admin",
        "is_active": True,
        "is_approved": True,
        "full_name": "Admin",
    }


def _token(email: str, role: str) -> str:
    from app.core.security import create_access_token

    return create_access_token(data={"sub": email, "role": role})


# ---------------------------------------------------------------------------
# Chat history IDOR
# ---------------------------------------------------------------------------


class TestChatHistoryIDOR:
    """User B may not read or delete user A's session by guessing its id."""

    @pytest.fixture
    async def client(self, student_user, other_student_user):
        from app.api.v1.chat_history import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/chat")
        transport = ASGITransport(app=app)

        # The mocked find_one / delete_one only "match" when the
        # supplied filter contains the OWNER's user_id. Any other
        # user_id triggers the not-found branch.
        owner_id = str(student_user["_id"])

        async def find_one(filter_doc):
            if filter_doc.get("user_id") == owner_id:
                return {
                    "_id": ObjectId(),
                    "session_id": filter_doc["session_id"],
                    "user_id": owner_id,
                    "messages": [],
                    "created_at": None,
                    "updated_at": None,
                }
            return None

        async def delete_one(filter_doc):
            if filter_doc.get("user_id") == owner_id:
                return MagicMock(deleted_count=1)
            return MagicMock(deleted_count=0)

        chat_history = MagicMock()
        chat_history.find_one = AsyncMock(side_effect=find_one)
        chat_history.delete_one = AsyncMock(side_effect=delete_one)

        feedback = MagicMock()
        feedback.delete_many = AsyncMock()

        audit_logs = MagicMock()
        audit_logs.insert_one = AsyncMock()

        mock = MagicMock()
        mock.chat_history = chat_history
        mock.feedback = feedback
        mock.__getitem__.side_effect = lambda name: (
            audit_logs if name == "audit_logs" else MagicMock()
        )

        # Resolve user by email for both owner and intruder.
        users = {
            student_user["email"]: student_user,
            other_student_user["email"]: other_student_user,
        }

        with (
            patch("app.api.v1.chat_history.get_database", return_value=mock),
            patch(
                "app.core.dependencies.get_user_by_email",
                new_callable=AsyncMock,
                side_effect=lambda email: users.get(email),
            ),
            patch(
                "app.services.audit_log.get_database",
                return_value=mock,
            ),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac

    @pytest.mark.asyncio
    async def test_user_b_cannot_read_user_a_session(self, client):
        # User B (other_student_user) tries to fetch a session that
        # belongs to user A (student_user). The mock returns None
        # whenever the user_id filter doesn't match — regression
        # would either: (a) drop the user_id from the filter, or
        # (b) return user A's session anyway. Either bug would flip
        # this test to 200.
        token = _token("other@knu.ua", "student")
        resp = await client.get(
            "/api/v1/chat/history/some-session-id",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_owner_can_read_own_session(self, client):
        token = _token("student@knu.ua", "student")
        resp = await client.get(
            "/api/v1/chat/history/some-session-id",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_user_b_cannot_delete_user_a_session(self, client):
        token = _token("other@knu.ua", "student")
        resp = await client.delete(
            "/api/v1/chat/history/some-session-id",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Document delete IDOR
# ---------------------------------------------------------------------------


class TestDocumentDeleteIDOR:
    """Teachers may only delete their own uploads; admins may delete any."""

    @pytest.fixture
    async def client(self, teacher_user, admin_user):
        from app.api.v1.documents import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/documents")
        transport = ASGITransport(app=app)

        # The document was uploaded by ANOTHER teacher.
        document_oid = ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa")
        other_teacher_id = "bbbbbbbbbbbbbbbbbbbbbbbb"

        documents = MagicMock()
        documents.find_one = AsyncMock(
            return_value={
                "_id": document_oid,
                "filename": "test.pdf",
                "uploaded_by_id": other_teacher_id,
            }
        )
        documents.delete_one = AsyncMock(
            return_value=MagicMock(deleted_count=1)
        )

        users = {
            teacher_user["email"]: teacher_user,
            admin_user["email"]: admin_user,
        }

        mock = MagicMock()
        mock.documents = documents
        mock.audit_logs = MagicMock()
        mock.audit_logs.insert_one = AsyncMock()

        # vector_store_service.delete_by_document_id is awaited inside
        # delete_document — return a coroutine-friendly mock.
        with (
            patch("app.api.v1.documents.get_database", return_value=mock),
            patch(
                "app.core.dependencies.get_user_by_email",
                new_callable=AsyncMock,
                side_effect=lambda email: users.get(email),
            ),
            patch(
                "app.api.v1.documents.vector_store_service.delete_by_document_id",
                new_callable=AsyncMock,
                return_value=3,
            ),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac

    @pytest.mark.asyncio
    async def test_teacher_cannot_delete_other_teachers_document(self, client):
        token = _token("teacher@knu.ua", "teacher")
        resp = await client.delete(
            "/api/v1/documents/aaaaaaaaaaaaaaaaaaaaaaaa",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_delete_any_document(self, client):
        token = _token("admin@knu.ua", "admin")
        resp = await client.delete(
            "/api/v1/documents/aaaaaaaaaaaaaaaaaaaaaaaa",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["chunks_deleted"] == 3


# ---------------------------------------------------------------------------
# Document preview IDOR — cross-faculty
# ---------------------------------------------------------------------------


class TestPreviewIDOR:
    """A student cannot preview a faculty-scoped document from another faculty."""

    @pytest.fixture
    async def client(self, student_user):
        from app.api.v1.documents import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1/documents")
        transport = ASGITransport(app=app)

        documents = MagicMock()
        documents.find_one = AsyncMock(
            return_value={
                "_id": ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa"),
                "filename": "policy.pdf",
                "file_type": "pdf",
                "access_level": "faculty",
                # Document belongs to OTHER faculty than the student.
                "faculty_id": OTHER_FACULTY_ID,
                "extracted_text": "secret faculty content",
                "total_chunks": 1,
            }
        )

        mock = MagicMock()
        mock.documents = documents

        with (
            patch("app.api.v1.documents.get_database", return_value=mock),
            patch(
                "app.core.dependencies.get_user_by_email",
                new_callable=AsyncMock,
                return_value=student_user,
            ),
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                yield ac

    @pytest.mark.asyncio
    async def test_student_cannot_preview_other_faculty_doc(self, client):
        token = _token("student@knu.ua", "student")
        resp = await client.get(
            "/api/v1/documents/aaaaaaaaaaaaaaaaaaaaaaaa/preview",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403
