"""Tests for chat API — history endpoints and SSE streaming."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bson import ObjectId
from datetime import datetime, timezone


@pytest.fixture
def chat_mock_db():
    """Mock MongoDB for chat history tests."""
    mock = MagicMock()
    mock.chat_history = MagicMock()
    mock.chat_history.find_one = AsyncMock()
    mock.chat_history.insert_one = AsyncMock()
    mock.chat_history.update_one = AsyncMock()
    mock.chat_history.delete_one = AsyncMock()
    mock.documents = MagicMock()
    mock.documents.count_documents = AsyncMock(return_value=5)
    with patch("app.api.v1.chat_history.get_database", return_value=mock):
        yield mock


class TestChatHistory:
    """Chat history CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_get_history_list(self, client, chat_mock_db, auth_headers, mock_get_user):
        """Authenticated user can list their chat sessions."""
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {
                "_id": ObjectId("507f1f77bcf86cd799439022"),
                "user_id": "507f1f77bcf86cd799439011",
                "session_id": "sess-1",
                "title": "Розклад",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
        ])
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.skip = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        chat_mock_db.chat_history.find.return_value = mock_cursor

        response = await client.get("/api/v1/chat/history", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

    @pytest.mark.asyncio
    async def test_get_session_by_id(self, client, chat_mock_db, auth_headers, mock_get_user):
        """User can fetch a specific chat session."""
        session_id = "sess-1"
        chat_mock_db.chat_history.find_one.return_value = {
            "_id": ObjectId("507f1f77bcf86cd799439022"),
            "user_id": "507f1f77bcf86cd799439011",
            "session_id": session_id,
            "title": "Test",
            "messages": [
                {"role": "user", "content": "Hi", "timestamp": datetime.now(timezone.utc).isoformat()},
            ],
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

        response = await client.get(
            f"/api/v1/chat/history/{session_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] == session_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_session_404(self, client, chat_mock_db, auth_headers, mock_get_user):
        """Fetching non-existent session returns 404."""
        chat_mock_db.chat_history.find_one.return_value = None

        response = await client.get(
            "/api/v1/chat/history/nonexistent",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_session(self, client, chat_mock_db, auth_headers, mock_get_user):
        """User can delete their own chat session."""
        chat_mock_db.chat_history.delete_one.return_value = MagicMock(deleted_count=1)

        response = await client.delete(
            "/api/v1/chat/history/sess-1",
            headers=auth_headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_unauthenticated_access_401(self, client):
        """Unauthenticated access to history returns 401."""
        response = await client.get("/api/v1/chat/history")
        assert response.status_code == 401


class TestSSEStreaming:
    """POST /api/v1/chat/ask/stream with SSE streaming."""

    @pytest.mark.asyncio
    async def test_ask_stream_returns_sse(self, client, chat_mock_db, auth_headers, mock_get_user):
        """Ask stream endpoint should return SSE streaming response."""
        with patch("app.api.v1.chat_history.generate_rag_stream") as mock_stream:

            async def fake_stream(question, user, session_id):
                yield {"event": "token", "data": "Відповідь "}
                yield {"event": "token", "data": "на питання"}
                yield {"event": "done", "data": ""}

            mock_stream.return_value = fake_stream("test", {}, "sess-1")

            response = await client.post(
                "/api/v1/chat/ask/stream",
                json={"question": "Який розклад?"},
                headers=auth_headers,
            )
            assert response.status_code == 200
            assert "text/event-stream" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_ask_stream_empty_question_400(self, client, chat_mock_db, auth_headers, mock_get_user):
        """Empty question should return 400."""
        response = await client.post(
            "/api/v1/chat/ask/stream",
            json={"question": "   "},
            headers=auth_headers,
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_ask_stream_unauthenticated_401(self, client):
        """Unauthenticated access to ask/stream returns 401."""
        response = await client.post(
            "/api/v1/chat/ask/stream",
            json={"question": "Test?"},
        )
        assert response.status_code == 401
