"""Tests for auth dependencies — get_current_user and require_role."""

import pytest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException


class TestGetCurrentUser:
    """get_current_user dependency extracts user from JWT token."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self):
        """Valid token with existing user should return user dict."""
        from app.core.security import create_access_token
        from app.core.dependencies import get_current_user

        token = create_access_token(data={"sub": "user@knu.ua", "role": "student"})

        mock_user = {
            "_id": "507f1f77bcf86cd799439011",
            "email": "user@knu.ua",
            "role": "student",
            "is_active": True,
            "is_approved": True,
            "full_name": "Test User",
            "faculty": "CS",
        }

        with patch("app.core.dependencies.get_user_by_email", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_user
            user = await get_current_user(token=token)
            assert user["email"] == "user@knu.ua"
            mock_get.assert_called_once_with("user@knu.ua")

    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        """Invalid token should raise HTTPException 401."""
        from app.core.dependencies import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(token="invalid.token")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_user_not_found_raises_401(self):
        """Token for non-existent user should raise HTTPException 401."""
        from app.core.security import create_access_token
        from app.core.dependencies import get_current_user

        token = create_access_token(data={"sub": "ghost@knu.ua", "role": "student"})

        with patch("app.core.dependencies.get_user_by_email", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = None
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token=token)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_user_raises_403(self):
        """Inactive user should raise HTTPException 403."""
        from app.core.security import create_access_token
        from app.core.dependencies import get_current_user

        token = create_access_token(data={"sub": "blocked@knu.ua", "role": "student"})

        mock_user = {
            "_id": "507f1f77bcf86cd799439011",
            "email": "blocked@knu.ua",
            "role": "student",
            "is_active": False,
            "is_approved": True,
        }

        with patch("app.core.dependencies.get_user_by_email", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_user
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token=token)
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_unapproved_teacher_raises_403(self):
        """Unapproved teacher should raise HTTPException 403."""
        from app.core.security import create_access_token
        from app.core.dependencies import get_current_user

        token = create_access_token(data={"sub": "teacher@knu.ua", "role": "teacher"})

        mock_user = {
            "_id": "507f1f77bcf86cd799439011",
            "email": "teacher@knu.ua",
            "role": "teacher",
            "is_active": True,
            "is_approved": False,
        }

        with patch("app.core.dependencies.get_user_by_email", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_user
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token=token)
            assert exc_info.value.status_code == 403


class TestRequireRole:
    """require_role dependency factory checks user role."""

    def test_allowed_role_passes(self):
        """User with allowed role should pass."""
        from app.core.dependencies import require_role

        checker = require_role("admin", "teacher")
        user = {"role": "admin", "email": "admin@knu.ua"}
        result = checker(current_user=user)
        assert result == user

    def test_denied_role_raises_403(self):
        """User without required role should raise HTTPException 403."""
        from app.core.dependencies import require_role

        checker = require_role("admin")
        user = {"role": "student", "email": "student@knu.ua"}
        with pytest.raises(HTTPException) as exc_info:
            checker(current_user=user)
        assert exc_info.value.status_code == 403
