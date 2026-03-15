"""Tests for Pydantic models — User model validation."""

import pytest
from datetime import datetime, timezone


class TestUserModel:
    """User model validation tests."""

    def test_student_creation_valid(self):
        """Student with all required fields should be valid."""
        from app.models.user import UserCreate

        user = UserCreate(
            email="student@knu.ua",
            password="SecurePass123!",
            full_name="Іван Петренко",
            role="student",
            faculty="Факультет комп'ютерних наук",
            group="КН-41",
            year=4,
        )
        assert user.email == "student@knu.ua"
        assert user.role == "student"
        assert user.faculty == "Факультет комп'ютерних наук"
        assert user.group == "КН-41"
        assert user.year == 4

    def test_teacher_creation_valid(self):
        """Teacher with all required fields should be valid."""
        from app.models.user import UserCreate

        user = UserCreate(
            email="teacher@knu.ua",
            password="SecurePass123!",
            full_name="Олена Іваненко",
            role="teacher",
            faculty="Факультет комп'ютерних наук",
            department="Кафедра КІ",
            position="Доцент",
        )
        assert user.email == "teacher@knu.ua"
        assert user.role == "teacher"
        assert user.department == "Кафедра КІ"
        assert user.position == "Доцент"

    def test_admin_creation_valid(self):
        """Admin with minimal fields should be valid."""
        from app.models.user import UserCreate

        user = UserCreate(
            email="admin@knu.ua",
            password="SecurePass123!",
            full_name="Адмін Системи",
            role="admin",
            faculty="Загальний",
        )
        assert user.role == "admin"

    def test_invalid_role_rejected(self):
        """Invalid role should raise validation error."""
        from app.models.user import UserCreate

        with pytest.raises(ValueError):
            UserCreate(
                email="user@knu.ua",
                password="SecurePass123!",
                full_name="Test User",
                role="superadmin",
                faculty="Test",
            )

    def test_invalid_email_rejected(self):
        """Invalid email format should raise validation error."""
        from app.models.user import UserCreate

        with pytest.raises(ValueError):
            UserCreate(
                email="not-an-email",
                password="SecurePass123!",
                full_name="Test User",
                role="student",
                faculty="Test",
            )

    def test_short_password_rejected(self):
        """Password shorter than 8 characters should be rejected."""
        from app.models.user import UserCreate

        with pytest.raises(ValueError):
            UserCreate(
                email="user@knu.ua",
                password="short",
                full_name="Test User",
                role="student",
                faculty="Test",
            )

    def test_empty_full_name_rejected(self):
        """Empty full name should be rejected."""
        from app.models.user import UserCreate

        with pytest.raises(ValueError):
            UserCreate(
                email="user@knu.ua",
                password="SecurePass123!",
                full_name="",
                role="student",
                faculty="Test",
            )

    def test_user_in_db_model(self):
        """UserInDB should have hashed_password and metadata fields."""
        from app.models.user import UserInDB

        user = UserInDB(
            email="user@knu.ua",
            hashed_password="$2b$12$fakehash",
            full_name="Тест Юзер",
            role="student",
            faculty="Test",
            is_approved=True,
            is_active=True,
        )
        assert user.hashed_password == "$2b$12$fakehash"
        assert user.is_approved is True
        assert user.is_active is True
        assert isinstance(user.created_at, datetime)

    def test_teacher_not_approved_by_default(self):
        """Teacher UserInDB should not be approved by default."""
        from app.models.user import UserInDB

        user = UserInDB(
            email="teacher@knu.ua",
            hashed_password="$2b$12$fakehash",
            full_name="Олена",
            role="teacher",
            faculty="Test",
        )
        assert user.is_approved is False

    def test_student_approved_by_default(self):
        """Student UserInDB should be approved by default."""
        from app.models.user import UserInDB

        user = UserInDB(
            email="student@knu.ua",
            hashed_password="$2b$12$fakehash",
            full_name="Іван",
            role="student",
        )
        assert user.is_approved is True

    def test_user_response_no_password(self):
        """UserResponse should not expose password fields."""
        from app.models.user import UserResponse

        user = UserResponse(
            id="507f1f77bcf86cd799439011",
            email="user@knu.ua",
            full_name="Тест",
            role="student",
            faculty="Test",
            is_approved=True,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        data = user.model_dump()
        assert "password" not in data
        assert "hashed_password" not in data
        assert "id" in data
