"""End-to-end integration tests for the full RAG pipeline.

Tests the complete flow: register → login → upload doc → ask question → chat history.
All external services (MongoDB, LLM, embeddings) are mocked.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport


@pytest.fixture
def mock_user_doc():
    """A user document as it would appear in MongoDB."""
    from app.core.security import hash_password

    return {
        "_id": ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa"),
        "email": "student@knu.ua",
        "hashed_password": hash_password("TestPass123!"),
        "full_name": "Тест Студент",
        "role": "student",
        "faculty": "CS",
        "group": "КН-41",
        "year": 4,
        "department": None,
        "position": None,
        "is_approved": True,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


@pytest.fixture
def mock_admin_doc():
    """An admin user document."""
    from app.core.security import hash_password

    return {
        "_id": ObjectId("bbbbbbbbbbbbbbbbbbbbbbbb"),
        "email": "admin@knu.ua",
        "hashed_password": hash_password("AdminPass123!"),
        "full_name": "Адмін",
        "role": "admin",
        "faculty": "CS",
        "is_approved": True,
        "is_active": True,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }


@pytest.fixture
def mock_db_collections():
    """Create mock MongoDB collections with proper Motor behavior."""
    users = MagicMock()
    users.find_one = AsyncMock(return_value=None)
    users.insert_one = AsyncMock()
    users.count_documents = AsyncMock(return_value=0)

    documents = MagicMock()
    documents.find_one = AsyncMock(return_value=None)
    documents.insert_one = AsyncMock()
    documents.count_documents = AsyncMock(return_value=0)
    documents.delete_one = AsyncMock()

    chat_history = MagicMock()
    chat_history.find_one = AsyncMock(return_value=None)
    chat_history.insert_one = AsyncMock()
    chat_history.update_one = AsyncMock()
    chat_history.delete_one = AsyncMock()

    mock = MagicMock()
    feedback = MagicMock()
    feedback.delete_many = AsyncMock()

    mock.users = users
    mock.documents = documents
    mock.chat_history = chat_history
    mock.feedback = feedback

    return mock


@pytest.fixture
def e2e_app(mock_db_collections):
    """Create FastAPI app with all routers and mocked DB."""
    from starlette.middleware.cors import CORSMiddleware
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    from fastapi import FastAPI
    from app.api.v1.auth import router as auth_router
    from app.api.v1.admin import router as admin_router
    from app.api.v1.chat import router as chat_router
    from app.api.v1.chat_history import router as chat_history_router
    from app.api.v1.documents import router as documents_router

    # Use a fresh limiter with high limits so tests don't get rate-limited
    test_limiter = Limiter(key_func=get_remote_address, enabled=False)

    app = FastAPI()
    app.state.limiter = test_limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    app.include_router(auth_router, prefix="/api/v1/auth")
    app.include_router(admin_router, prefix="/api/v1/admin")
    app.include_router(chat_router, prefix="/api/v1/chat")
    app.include_router(chat_history_router, prefix="/api/v1/chat")
    app.include_router(documents_router, prefix="/api/v1/documents")

    return app


@pytest.fixture
async def client(e2e_app, mock_db_collections):
    """Async HTTP client with all dependencies mocked."""
    from app.core.rate_limit import limiter

    transport = ASGITransport(app=e2e_app)
    original_enabled = limiter.enabled
    limiter.enabled = False
    try:
        with (
            patch("app.api.v1.auth.get_database", return_value=mock_db_collections),
            patch("app.api.v1.admin.get_database", return_value=mock_db_collections),
            patch("app.api.v1.chat.get_database", return_value=mock_db_collections),
            patch("app.api.v1.chat_history.get_database", return_value=mock_db_collections),
            patch("app.api.v1.documents.get_database", return_value=mock_db_collections),
            patch("app.core.dependencies.get_user_by_email", new_callable=AsyncMock) as mock_get_user,
        ):
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                ac._mock_db = mock_db_collections
                ac._mock_get_user = mock_get_user
                yield ac
    finally:
        limiter.enabled = original_enabled


class TestAuthFlow:
    """Test registration → login → /me flow."""

    @pytest.mark.asyncio
    async def test_register_student(self, client, mock_db_collections):
        mock_db_collections.users.find_one.return_value = None
        mock_db_collections.users.insert_one.return_value = MagicMock(
            inserted_id=ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa")
        )

        resp = await client.post("/api/v1/auth/register", json={
            "email": "new@knu.ua",
            "password": "SecurePass123!",
            "full_name": "Нова Студентка",
            "role": "student",
            "faculty": "CS",
        })

        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "new@knu.ua"
        assert data["role"] == "student"
        assert data["is_approved"] is True

    @pytest.mark.asyncio
    async def test_register_teacher_not_approved(self, client, mock_db_collections):
        mock_db_collections.users.find_one.return_value = None
        mock_db_collections.users.insert_one.return_value = MagicMock(
            inserted_id=ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa")
        )

        resp = await client.post("/api/v1/auth/register", json={
            "email": "teacher@knu.ua",
            "password": "SecurePass123!",
            "full_name": "Новий Викладач",
            "role": "teacher",
            "faculty": "CS",
        })

        assert resp.status_code == 201
        assert resp.json()["is_approved"] is False

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client, mock_db_collections):
        mock_db_collections.users.find_one.return_value = {"email": "exists@knu.ua"}

        resp = await client.post("/api/v1/auth/register", json={
            "email": "exists@knu.ua",
            "password": "SecurePass123!",
            "full_name": "Дублікат",
            "role": "student",
            "faculty": "CS",
        })

        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_login_success(self, client, mock_db_collections, mock_user_doc):
        mock_db_collections.users.find_one.return_value = mock_user_doc

        resp = await client.post("/api/v1/auth/login", data={
            "username": "student@knu.ua",
            "password": "TestPass123!",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client, mock_db_collections, mock_user_doc):
        mock_db_collections.users.find_one.return_value = mock_user_doc

        resp = await client.post("/api/v1/auth/login", data={
            "username": "student@knu.ua",
            "password": "WrongPassword!",
        })

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_me_with_valid_token(self, client, mock_user_doc):
        client._mock_get_user.return_value = mock_user_doc

        from app.core.security import create_access_token
        token = create_access_token(data={"sub": "student@knu.ua", "role": "student"})

        resp = await client.get("/api/v1/auth/me", headers={
            "Authorization": f"Bearer {token}",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == "student@knu.ua"
        assert data["role"] == "student"

    @pytest.mark.asyncio
    async def test_me_without_token(self, client):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401


class TestDocumentUpload:
    """Test document upload flow."""

    @pytest.mark.asyncio
    async def test_student_cannot_upload(self, client, mock_user_doc):
        client._mock_get_user.return_value = mock_user_doc

        from app.core.security import create_access_token
        token = create_access_token(data={"sub": "student@knu.ua", "role": "student"})

        resp = await client.post(
            "/api/v1/documents/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.txt", b"test content", "text/plain")},
            data={"access_level": "public"},
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_upload(self, client, mock_db_collections, mock_admin_doc):
        client._mock_get_user.return_value = mock_admin_doc
        mock_db_collections.documents.insert_one.return_value = MagicMock(
            inserted_id=ObjectId("cccccccccccccccccccccccc")
        )

        from app.core.security import create_access_token
        token = create_access_token(data={"sub": "admin@knu.ua", "role": "admin"})

        with patch("app.api.v1.documents.vector_store_service") as mock_vs:
            mock_vs.add_document_with_chunking = AsyncMock(return_value=["id1"])

            resp = await client.post(
                "/api/v1/documents/upload",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("test.txt", "Тестовий документ для перевірки".encode("utf-8"), "text/plain")},
                data={"access_level": "public"},
            )

        assert resp.status_code == 201
        data = resp.json()
        assert data["filename"] == "test.txt"
        assert data["total_chunks"] == 1

    @pytest.mark.asyncio
    async def test_unsupported_file_type(self, client, mock_admin_doc):
        client._mock_get_user.return_value = mock_admin_doc

        from app.core.security import create_access_token
        token = create_access_token(data={"sub": "admin@knu.ua", "role": "admin"})

        resp = await client.post(
            "/api/v1/documents/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("test.exe", b"binary content", "application/octet-stream")},
            data={"access_level": "public"},
        )

        assert resp.status_code == 400


class TestRAGPipeline:
    """Test question-answering RAG flow."""

    @pytest.mark.asyncio
    async def test_ask_with_no_documents(self, client, mock_db_collections, mock_admin_doc):
        """When no documents exist, should return 'no documents' message."""
        client._mock_get_user.return_value = mock_admin_doc
        mock_db_collections.documents.count_documents.return_value = 0

        from app.core.security import create_access_token
        token = create_access_token(data={"sub": "admin@knu.ua", "role": "admin"})

        resp = await client.post(
            "/api/v1/chat/ask",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "Коли був заснований університет?"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert "немає документів" in data["answer"]
        assert data["sources"] == []

    @pytest.mark.asyncio
    async def test_ask_with_documents(self, client, mock_db_collections, mock_admin_doc):
        """Full RAG flow with mocked retriever and LLM."""
        client._mock_get_user.return_value = mock_admin_doc
        mock_db_collections.documents.count_documents.return_value = 5

        from app.core.security import create_access_token
        from langchain_core.documents import Document as LCDocument

        token = create_access_token(data={"sub": "admin@knu.ua", "role": "admin"})

        mock_doc = LCDocument(
            page_content="Університет заснований у 1834 році.",
            metadata={"source_file": "history.pdf", "chunk_index": 0},
        )

        # Mock the entire run_rag_chain to avoid LCEL chain complexity
        with patch("app.api.v1.chat.run_rag_chain", new_callable=AsyncMock) as mock_rag:
            mock_rag.return_value = {
                "answer": "Згідно з документом, університет був заснований у 1834 році.",
                "sources": [{"source_file": "history.pdf", "chunk_index": 0, "text": "Університет заснований у 1834 році."}],
                "docs": [mock_doc],
            }

            resp = await client.post(
                "/api/v1/chat/ask",
                headers={"Authorization": f"Bearer {token}"},
                json={"question": "Коли був заснований університет?"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "1834" in data["answer"]
        assert len(data["sources"]) == 1
        assert data["sources"][0]["source_file"] == "history.pdf"
        assert data["processing_time"] > 0

    @pytest.mark.asyncio
    async def test_ask_empty_question_rejected(self, client, mock_admin_doc):
        client._mock_get_user.return_value = mock_admin_doc

        from app.core.security import create_access_token
        token = create_access_token(data={"sub": "admin@knu.ua", "role": "admin"})

        resp = await client.post(
            "/api/v1/chat/ask",
            headers={"Authorization": f"Bearer {token}"},
            json={"question": "   "},
        )

        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_ask_unauthenticated(self, client):
        resp = await client.post(
            "/api/v1/chat/ask",
            json={"question": "test"},
        )
        assert resp.status_code == 401


class TestChatHistory:
    """Test chat history CRUD."""

    @pytest.mark.asyncio
    async def test_get_empty_history(self, client, mock_db_collections, mock_user_doc):
        client._mock_get_user.return_value = mock_user_doc

        from app.core.security import create_access_token
        token = create_access_token(data={"sub": "student@knu.ua", "role": "student"})

        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.skip = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db_collections.chat_history.find = MagicMock(return_value=mock_cursor)

        resp = await client.get(
            "/api/v1/chat/history",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_get_session_not_found(self, client, mock_db_collections, mock_user_doc):
        client._mock_get_user.return_value = mock_user_doc
        mock_db_collections.chat_history.find_one.return_value = None

        from app.core.security import create_access_token
        token = create_access_token(data={"sub": "student@knu.ua", "role": "student"})

        resp = await client.get(
            "/api/v1/chat/history/nonexistent-session",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_session(self, client, mock_db_collections, mock_user_doc):
        client._mock_get_user.return_value = mock_user_doc
        mock_db_collections.chat_history.delete_one.return_value = MagicMock(deleted_count=1)

        from app.core.security import create_access_token
        token = create_access_token(data={"sub": "student@knu.ua", "role": "student"})

        resp = await client.delete(
            "/api/v1/chat/history/session-123",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200


class TestAccessControl:
    """Test role-based access control across endpoints."""

    @pytest.mark.asyncio
    async def test_student_cannot_access_admin(self, client, mock_user_doc):
        client._mock_get_user.return_value = mock_user_doc

        from app.core.security import create_access_token
        token = create_access_token(data={"sub": "student@knu.ua", "role": "student"})

        resp = await client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_list_users(self, client, mock_db_collections, mock_admin_doc):
        client._mock_get_user.return_value = mock_admin_doc
        mock_db_collections.users.count_documents.return_value = 1

        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[{
            "_id": ObjectId("aaaaaaaaaaaaaaaaaaaaaaaa"),
            "email": "user@knu.ua",
            "role": "student",
        }])
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_db_collections.users.find = MagicMock(return_value=mock_cursor)

        from app.core.security import create_access_token
        token = create_access_token(data={"sub": "admin@knu.ua", "role": "admin"})

        resp = await client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["users"]) == 1
