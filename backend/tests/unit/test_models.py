"""Tests for Pydantic models — User model validation."""

import pytest
from datetime import datetime, timezone
from bson import ObjectId


SAMPLE_FACULTY_ID = str(ObjectId())
SAMPLE_GROUP_ID = str(ObjectId())


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
            faculty_id=SAMPLE_FACULTY_ID,
            group_id=SAMPLE_GROUP_ID,
            year=4,
            level="bachelor",
        )
        assert user.email == "student@knu.ua"
        assert user.role == "student"
        assert user.faculty_id == SAMPLE_FACULTY_ID
        assert user.group_id == SAMPLE_GROUP_ID
        assert user.year == 4
        assert user.level.value == "bachelor"

    def test_teacher_creation_valid(self):
        """Teacher with the required faculty_id should be valid."""
        from app.models.user import UserCreate

        user = UserCreate(
            email="teacher@knu.ua",
            password="SecurePass123!",
            full_name="Олена Іваненко",
            role="teacher",
            faculty_id=SAMPLE_FACULTY_ID,
            department="Кафедра КІ",
            position="Доцент",
        )
        assert user.email == "teacher@knu.ua"
        assert user.role == "teacher"
        assert user.department == "Кафедра КІ"
        assert user.position == "Доцент"

    def test_student_missing_group_id_rejected(self):
        """A student must supply group_id, year and level."""
        from app.models.user import UserCreate

        with pytest.raises(ValueError):
            UserCreate(
                email="student@knu.ua",
                password="SecurePass123!",
                full_name="Іван",
                role="student",
                faculty_id=SAMPLE_FACULTY_ID,
                # group_id / year / level missing
            )

    def test_admin_role_rejected_in_registration(self):
        """Admin role should be rejected in UserCreate (registration model)."""
        from app.models.user import UserCreate

        with pytest.raises(ValueError):
            UserCreate(
                email="admin@knu.ua",
                password="SecurePass123!",
                full_name="Admin User",
                role="admin",
                faculty_id=SAMPLE_FACULTY_ID,
            )

    def test_invalid_role_rejected(self):
        """Invalid role should raise validation error."""
        from app.models.user import UserCreate

        with pytest.raises(ValueError):
            UserCreate(
                email="user@knu.ua",
                password="SecurePass123!",
                full_name="Test User",
                role="superadmin",
                faculty_id=SAMPLE_FACULTY_ID,
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
                faculty_id=SAMPLE_FACULTY_ID,
                group_id=SAMPLE_GROUP_ID,
                year=1,
                level="bachelor",
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
                faculty_id=SAMPLE_FACULTY_ID,
                group_id=SAMPLE_GROUP_ID,
                year=1,
                level="bachelor",
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
                faculty_id=SAMPLE_FACULTY_ID,
                group_id=SAMPLE_GROUP_ID,
                year=1,
                level="bachelor",
            )

    def test_user_in_db_model(self):
        """UserInDB should have hashed_password and metadata fields."""
        from app.models.user import UserInDB

        user = UserInDB(
            email="user@knu.ua",
            hashed_password="$2b$12$fakehash",
            full_name="Тест Юзер",
            role="student",
            faculty_id=SAMPLE_FACULTY_ID,
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
            faculty_id=SAMPLE_FACULTY_ID,
        )
        assert user.is_approved is False

    def test_student_not_approved_by_default(self):
        """Both students and teachers wait for an admin to approve them."""
        from app.models.user import UserInDB

        user = UserInDB(
            email="student@knu.ua",
            hashed_password="$2b$12$fakehash",
            full_name="Іван",
            role="student",
        )
        assert user.is_approved is False

    def test_admin_approved_by_default(self):
        """Admin accounts are seeded out-of-band and start approved."""
        from app.models.user import UserInDB

        user = UserInDB(
            email="admin@knu.ua",
            hashed_password="$2b$12$fakehash",
            full_name="Адмін",
            role="admin",
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
            faculty_id=SAMPLE_FACULTY_ID,
            is_approved=True,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        data = user.model_dump()
        assert "password" not in data
        assert "hashed_password" not in data
        assert "id" in data
