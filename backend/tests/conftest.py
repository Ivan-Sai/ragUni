"""Shared test fixtures for ragUni."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from bson import ObjectId

# Set test env vars before anything imports config.
# SECRET_KEY is validated to be >=32 chars and not start with "change-me",
# so we use a dedicated high-entropy value that is obviously a test key.
os.environ.setdefault("DEEPSEEK_API_KEY", "test-key-for-testing")
os.environ.setdefault(
    "SECRET_KEY",
    "test-secret-key-for-unit-tests-only-do-not-use-in-prod-0000",
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def mock_db():
    """Mock MongoDB database returned by get_database()."""
    mock = MagicMock()

    # Documents collection
    mock.documents = MagicMock()
    mock.documents.count_documents = AsyncMock(return_value=0)
    mock.documents.find_one = AsyncMock(return_value=None)
    mock.documents.insert_one = AsyncMock()
    mock.documents.delete_one = AsyncMock()

    # Chat history collection
    mock.chat_history = MagicMock()
    mock.chat_history.find_one = AsyncMock(return_value=None)
    mock.chat_history.insert_one = AsyncMock()
    mock.chat_history.update_one = AsyncMock()
    mock.chat_history.delete_one = AsyncMock()

    # Users collection
    mock.users = MagicMock()
    mock.users.find_one = AsyncMock(return_value=None)
    mock.users.update_one = AsyncMock()
    mock.users.insert_one = AsyncMock()

    # Refresh-token allowlist collection (used by /auth/login,
    # /auth/refresh, /auth/logout, password change/reset).
    mock_refresh = MagicMock()
    mock_refresh.insert_one = AsyncMock()
    mock_refresh.find_one = AsyncMock(return_value=None)
    mock_refresh.update_one = AsyncMock()
    mock_refresh.update_many = AsyncMock(return_value=MagicMock(modified_count=0))

    # `db["refresh_tokens"]` should also resolve to the mock — accessing
    # any unknown collection via __getitem__ returns a MagicMock by
    # default, but we wire the canonical one explicitly so assertions
    # against it work.
    mock.__getitem__.side_effect = lambda name: (
        mock_refresh if name == "refresh_tokens" else MagicMock()
    )

    with patch("app.services.database.get_database", return_value=mock):
        yield mock


@pytest.fixture
def student_user():
    return {
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "email": "student@knu.ua",
        "role": "student",
        "is_active": True,
        "is_approved": True,
        "full_name": "Test Student",
        "faculty": "CS",
    }


@pytest.fixture
def teacher_user():
    return {
        "_id": ObjectId("507f1f77bcf86cd799439012"),
        "email": "teacher@knu.ua",
        "role": "teacher",
        "is_active": True,
        "is_approved": True,
        "full_name": "Test Teacher",
        "faculty": "CS",
    }


@pytest.fixture
def admin_user():
    return {
        "_id": ObjectId("507f1f77bcf86cd799439013"),
        "email": "admin@knu.ua",
        "role": "admin",
        "is_active": True,
        "is_approved": True,
        "full_name": "Test Admin",
    }


@pytest.fixture
def auth_headers():
    from app.core.security import create_access_token

    token = create_access_token(data={"sub": "student@knu.ua", "role": "student"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def teacher_auth_headers():
    from app.core.security import create_access_token

    token = create_access_token(data={"sub": "teacher@knu.ua", "role": "teacher"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def admin_auth_headers():
    from app.core.security import create_access_token

    token = create_access_token(data={"sub": "admin@knu.ua", "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_get_user(student_user):
    with patch("app.core.dependencies.get_user_by_email", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = student_user
        yield mock_get


@pytest.fixture
def mock_get_teacher(teacher_user):
    with patch("app.core.dependencies.get_user_by_email", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = teacher_user
        yield mock_get


@pytest.fixture
def mock_get_admin(admin_user):
    with patch("app.core.dependencies.get_user_by_email", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = admin_user
        yield mock_get


@pytest.fixture
async def client():
    """Async test client with all routers (no heavy deps)."""
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from app.api.v1.auth import router as auth_router
    from app.api.v1.admin import router as admin_router
    from app.api.v1.chat_history import router as chat_router

    app = FastAPI()
    app.include_router(auth_router, prefix="/api/v1/auth")
    app.include_router(admin_router, prefix="/api/v1/admin")
    app.include_router(chat_router, prefix="/api/v1/chat")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
