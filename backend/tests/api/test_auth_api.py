"""Tests for auth API endpoints — register, login, refresh, /me."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bson import ObjectId
from datetime import datetime


SAMPLE_FACULTY_ID = "507f1f77bcf86cd7994390ff"
SAMPLE_GROUP_ID = "507f1f77bcf86cd7994390fe"


@pytest.fixture
def mock_db():
    """Mock MongoDB collections for auth tests.

    Pre-stocks the faculty/group dictionary lookups that the
    register endpoint performs as part of validation, so each test
    only has to drive the user-collection behaviour it cares about.

    The patch list also covers ``account_lockout`` and
    ``refresh_tokens`` (login + refresh + logout call into both),
    plus ``audit_log`` so password-change tests don't try to write
    to a real Mongo. Each support module is patched at its own module
    binding (``from app.services import database as _database``
    inside the module) so the substitution actually takes effect.
    """
    mock_users = AsyncMock()
    mock_faculties = AsyncMock()
    mock_groups = AsyncMock()

    # Default: dictionary entries exist and are consistent with the
    # sample fixtures below.
    mock_faculties.find_one.return_value = {"_id": ObjectId(SAMPLE_FACULTY_ID)}
    mock_groups.find_one.return_value = {
        "_id": ObjectId(SAMPLE_GROUP_ID),
        "faculty_id": ObjectId(SAMPLE_FACULTY_ID),
        "level": "bachelor",
        "name": "КН-41",
    }

    mock = MagicMock()
    mock.users = mock_users
    mock.faculties = mock_faculties
    mock.groups = mock_groups

    # `db["refresh_tokens"]` — refresh-token allowlist collection.
    mock_refresh = MagicMock()
    mock_refresh.insert_one = AsyncMock()
    mock_refresh.find_one = AsyncMock(return_value=None)
    mock_refresh.update_one = AsyncMock()
    mock_refresh.update_many = AsyncMock(return_value=MagicMock(modified_count=0))
    mock.__getitem__.side_effect = lambda name: (
        mock_refresh if name == "refresh_tokens" else MagicMock()
    )

    # The new support services bind `database` at module top with
    # `from app.services import database as _database`. Patch each
    # binding so they all see the mock.
    fake_db_module = MagicMock()
    fake_db_module.get_database.return_value = mock

    with (
        patch("app.api.v1.auth.get_database", return_value=mock),
        patch("app.services.account_lockout._database", fake_db_module),
        patch("app.services.refresh_tokens._database", fake_db_module),
        patch(
            "app.services.audit_log.get_database",
            return_value=mock,
        ),
    ):
        yield mock


@pytest.fixture
def sample_student():
    return {
        "email": "student@knu.ua",
        "password": "SecurePass123!",
        "full_name": "Іван Петренко",
        "role": "student",
        "faculty_id": SAMPLE_FACULTY_ID,
        "group_id": SAMPLE_GROUP_ID,
        "year": 4,
        "level": "bachelor",
    }


@pytest.fixture
def sample_teacher():
    return {
        "email": "teacher@knu.ua",
        "password": "SecurePass123!",
        "full_name": "Олена Іваненко",
        "role": "teacher",
        "faculty_id": SAMPLE_FACULTY_ID,
        "department": "Кафедра КІ",
        "position": "Доцент",
    }


class TestRegister:
    """POST /api/v1/auth/register"""

    @pytest.mark.asyncio
    async def test_register_student_success(self, client, mock_db, sample_student):
        """Successful student registration returns 201 with user data."""
        mock_db.users.find_one.return_value = None  # no existing user
        mock_db.users.insert_one.return_value = MagicMock(
            inserted_id=ObjectId("507f1f77bcf86cd799439011")
        )

        response = await client.post("/api/v1/auth/register", json=sample_student)
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "student@knu.ua"
        assert data["role"] == "student"
        # Students wait for admin approval just like teachers.
        assert data["is_approved"] is False
        assert "password" not in data
        assert "hashed_password" not in data

    @pytest.mark.asyncio
    async def test_register_teacher_not_approved(self, client, mock_db, sample_teacher):
        """Teacher registration returns 201 but is_approved=False."""
        mock_db.users.find_one.return_value = None
        mock_db.users.insert_one.return_value = MagicMock(
            inserted_id=ObjectId("507f1f77bcf86cd799439012")
        )

        response = await client.post("/api/v1/auth/register", json=sample_teacher)
        assert response.status_code == 201
        data = response.json()
        assert data["role"] == "teacher"
        assert data["is_approved"] is False

    @pytest.mark.asyncio
    async def test_register_duplicate_email_returns_409(self, client, mock_db, sample_student):
        """Registration with existing email returns 409."""
        mock_db.users.find_one.return_value = {"email": "student@knu.ua"}

        response = await client.post("/api/v1/auth/register", json=sample_student)
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_register_admin_role_rejected(self, client, mock_db):
        """Attempting to register with admin role returns 422."""
        mock_db.users.find_one.return_value = None
        admin_data = {
            "email": "evil@knu.ua",
            "password": "SecurePass123!",
            "full_name": "Evil Admin",
            "role": "admin",
            "faculty_id": SAMPLE_FACULTY_ID,
        }
        response = await client.post("/api/v1/auth/register", json=admin_data)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_invalid_data_returns_422(self, client, mock_db):
        """Registration with invalid data returns 422."""
        response = await client.post("/api/v1/auth/register", json={"email": "bad"})
        assert response.status_code == 422


class TestLogin:
    """POST /api/v1/auth/login"""

    @pytest.mark.asyncio
    async def test_login_success(self, client, mock_db):
        """Successful login returns access and refresh tokens."""
        from app.core.security import hash_password

        hashed = hash_password("SecurePass123!")
        mock_db.users.find_one.return_value = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "email": "student@knu.ua",
            "hashed_password": hashed,
            "role": "student",
            "is_active": True,
            "is_approved": True,
            "full_name": "Test",
            "faculty_id": ObjectId(SAMPLE_FACULTY_ID),
        }

        response = await client.post(
            "/api/v1/auth/login",
            data={"username": "student@knu.ua", "password": "SecurePass123!"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client, mock_db):
        """Wrong password returns 401."""
        from app.core.security import hash_password

        mock_db.users.find_one.return_value = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "email": "student@knu.ua",
            "hashed_password": hash_password("CorrectPass123!"),
            "role": "student",
            "is_active": True,
            "is_approved": True,
        }

        response = await client.post(
            "/api/v1/auth/login",
            data={"username": "student@knu.ua", "password": "WrongPass123!"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client, mock_db):
        """Login with non-existent email returns 401."""
        mock_db.users.find_one.return_value = None

        response = await client.post(
            "/api/v1/auth/login",
            data={"username": "ghost@knu.ua", "password": "SecurePass123!"},
        )
        assert response.status_code == 401


class TestRefreshToken:
    """POST /api/v1/auth/refresh"""

    @pytest.mark.asyncio
    async def test_refresh_success(self, client, mock_db):
        """Valid refresh token returns new access token."""
        from app.core.security import create_refresh_token

        refresh, _jti = create_refresh_token(
            data={"sub": "student@knu.ua", "role": "student"}
        )

        mock_db.users.find_one.return_value = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "email": "student@knu.ua",
            "role": "student",
            "is_active": True,
            "is_approved": True,
        }

        with patch(
            "app.api.v1.auth.refresh_tokens.is_active",
            new_callable=AsyncMock,
            return_value=True,
        ):
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh},
            )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data

    @pytest.mark.asyncio
    async def test_refresh_with_access_token_fails(self, client, mock_db):
        """Using access token instead of refresh should fail."""
        from app.core.security import create_access_token

        access = create_access_token(data={"sub": "student@knu.ua"})

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": access},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_refresh_blocks_deactivated_user(self, client, mock_db):
        """A deactivated user must not be able to refresh their access token."""
        from app.core.security import create_refresh_token

        refresh, _jti = create_refresh_token(
            data={"sub": "blocked@knu.ua", "role": "student"}
        )

        mock_db.users.find_one.return_value = {
            "_id": ObjectId("507f1f77bcf86cd799439013"),
            "email": "blocked@knu.ua",
            "role": "student",
            "is_active": False,
            "is_approved": True,
        }

        with (
            patch(
                "app.api.v1.auth.refresh_tokens.is_active",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "app.api.v1.auth.refresh_tokens.revoke",
                new_callable=AsyncMock,
            ),
        ):
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh},
            )
        assert response.status_code == 403
        assert "deactivated" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_refresh_blocks_unapproved_teacher(self, client, mock_db):
        """An unapproved teacher must not be able to refresh their access token."""
        from app.core.security import create_refresh_token

        refresh, _jti = create_refresh_token(
            data={"sub": "pending@knu.ua", "role": "teacher"}
        )

        mock_db.users.find_one.return_value = {
            "_id": ObjectId("507f1f77bcf86cd799439014"),
            "email": "pending@knu.ua",
            "role": "teacher",
            "is_active": True,
            "is_approved": False,
        }

        with patch(
            "app.api.v1.auth.refresh_tokens.is_active",
            new_callable=AsyncMock,
            return_value=True,
        ):
            response = await client.post(
                "/api/v1/auth/refresh",
                json={"refresh_token": refresh},
            )
        assert response.status_code == 403
        assert "approval" in response.json()["detail"].lower()


class TestGetMe:
    """GET /api/v1/auth/me"""

    @pytest.mark.asyncio
    async def test_get_me_authenticated(self, client, mock_db):
        """Authenticated user can fetch their profile."""
        from app.core.security import create_access_token

        token = create_access_token(data={"sub": "student@knu.ua", "role": "student"})

        mock_user = {
            "_id": ObjectId("507f1f77bcf86cd799439011"),
            "email": "student@knu.ua",
            "full_name": "Іван Петренко",
            "role": "student",
            "faculty_id": ObjectId(SAMPLE_FACULTY_ID),
            "is_approved": True,
            "is_active": True,
            "created_at": datetime.now(),
        }

        with patch("app.core.dependencies.get_user_by_email", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_user
            response = await client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "student@knu.ua"

    @pytest.mark.asyncio
    async def test_get_me_no_token_returns_401(self, client):
        """Request without token returns 401."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401
