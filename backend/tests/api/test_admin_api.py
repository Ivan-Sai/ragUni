"""Tests for admin API endpoints — user management, approvals."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from bson import ObjectId
from datetime import datetime


@pytest.fixture
def mock_db():
    """Mock MongoDB collections for admin tests.

    Motor's find() returns cursor synchronously, to_list()/find_one() are async.
    """
    mock_users = MagicMock()
    mock_users.find_one = AsyncMock()
    mock_users.insert_one = AsyncMock()
    mock_users.update_one = AsyncMock()
    mock_users.delete_one = AsyncMock()
    mock_users.count_documents = AsyncMock()
    mock = MagicMock()
    mock.users = mock_users
    with patch("app.api.v1.admin.get_database", return_value=mock):
        yield mock


@pytest.fixture
def admin_headers():
    """Auth headers for admin user."""
    from app.core.security import create_access_token

    token = create_access_token(data={"sub": "admin@knu.ua", "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def student_headers():
    """Auth headers for student user."""
    from app.core.security import create_access_token

    token = create_access_token(data={"sub": "student@knu.ua", "role": "student"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def mock_admin_user():
    return {
        "_id": ObjectId("507f1f77bcf86cd799439099"),
        "email": "admin@knu.ua",
        "role": "admin",
        "is_active": True,
        "is_approved": True,
        "full_name": "Admin",
        "faculty": "General",
    }


@pytest.fixture
def mock_get_admin(mock_admin_user):
    """Patch get_user_by_email to return admin user."""
    with patch("app.core.dependencies.get_user_by_email", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_admin_user
        yield mock_get


@pytest.fixture
def mock_get_student():
    """Patch get_user_by_email to return student user."""
    student = {
        "_id": ObjectId("507f1f77bcf86cd799439098"),
        "email": "student@knu.ua",
        "role": "student",
        "is_active": True,
        "is_approved": True,
        "full_name": "Student",
    }
    with patch("app.core.dependencies.get_user_by_email", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = student
        yield mock_get


class TestListUsers:
    """GET /api/v1/admin/users"""

    @pytest.mark.asyncio
    async def test_admin_can_list_users(self, client, mock_db, admin_headers, mock_get_admin):
        """Admin can list all users."""
        mock_cursor = MagicMock()
        mock_cursor.skip.return_value = mock_cursor
        mock_cursor.limit.return_value = mock_cursor
        mock_cursor.to_list = AsyncMock(return_value=[
            {
                "_id": ObjectId("507f1f77bcf86cd799439011"),
                "email": "user1@knu.ua",
                "full_name": "User 1",
                "role": "student",
                "faculty": "CS",
                "is_approved": True,
                "is_active": True,
                "created_at": datetime.now(),
            }
        ])
        mock_db.users.find.return_value = mock_cursor
        mock_db.users.count_documents = AsyncMock(return_value=1)

        response = await client.get("/api/v1/admin/users", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_student_cannot_list_users(self, client, student_headers, mock_get_student):
        """Student should get 403 when trying to list users."""
        response = await client.get("/api/v1/admin/users", headers=student_headers)
        assert response.status_code == 403


class TestPendingTeachers:
    """GET /api/v1/admin/users/pending"""

    @pytest.mark.asyncio
    async def test_list_pending_teachers(self, client, mock_db, admin_headers, mock_get_admin):
        """Admin can list pending teacher approvals."""
        mock_cursor = AsyncMock()
        mock_cursor.to_list = AsyncMock(return_value=[
            {
                "_id": ObjectId("507f1f77bcf86cd799439012"),
                "email": "teacher@knu.ua",
                "full_name": "Teacher",
                "role": "teacher",
                "faculty": "CS",
                "is_approved": False,
                "is_active": True,
                "created_at": datetime.now(),
            }
        ])
        mock_db.users.find.return_value = mock_cursor

        response = await client.get("/api/v1/admin/users/pending", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["is_approved"] is False


class TestApproveTeacher:
    """PUT /api/v1/admin/users/{id}/approve"""

    @pytest.mark.asyncio
    async def test_approve_teacher(self, client, mock_db, admin_headers, mock_get_admin):
        """Admin can approve a pending teacher."""
        user_id = "507f1f77bcf86cd799439012"
        mock_db.users.find_one.return_value = {
            "_id": ObjectId(user_id),
            "email": "teacher@knu.ua",
            "role": "teacher",
            "is_approved": False,
        }
        mock_db.users.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        response = await client.put(
            f"/api/v1/admin/users/{user_id}/approve",
            headers=admin_headers,
        )
        assert response.status_code == 200
        mock_db.users.update_one.assert_called_once()

    @pytest.mark.asyncio
    async def test_approve_nonexistent_user_404(self, client, mock_db, admin_headers, mock_get_admin):
        """Approving non-existent user returns 404."""
        user_id = "507f1f77bcf86cd799439099"
        mock_db.users.find_one.return_value = None

        response = await client.put(
            f"/api/v1/admin/users/{user_id}/approve",
            headers=admin_headers,
        )
        assert response.status_code == 404


class TestBlockUser:
    """PUT /api/v1/admin/users/{id}/block"""

    @pytest.mark.asyncio
    async def test_block_user(self, client, mock_db, admin_headers, mock_get_admin):
        """Admin can block a user."""
        user_id = "507f1f77bcf86cd799439012"
        mock_db.users.find_one.return_value = {
            "_id": ObjectId(user_id),
            "email": "user@knu.ua",
            "role": "student",
            "is_active": True,
        }
        mock_db.users.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        response = await client.put(
            f"/api/v1/admin/users/{user_id}/block",
            headers=admin_headers,
            json={"is_active": False},
        )
        assert response.status_code == 200


class TestChangeRole:
    """PUT /api/v1/admin/users/{id}/role"""

    @pytest.mark.asyncio
    async def test_change_user_role(self, client, mock_db, admin_headers, mock_get_admin):
        """Admin can change a user's role."""
        user_id = "507f1f77bcf86cd799439012"
        mock_db.users.find_one.return_value = {
            "_id": ObjectId(user_id),
            "email": "user@knu.ua",
            "role": "student",
        }
        mock_db.users.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

        response = await client.put(
            f"/api/v1/admin/users/{user_id}/role",
            headers=admin_headers,
            json={"role": "teacher"},
        )
        assert response.status_code == 200
