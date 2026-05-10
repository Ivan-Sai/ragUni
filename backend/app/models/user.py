"""User models for authentication and RBAC.

The profile schema is enforced by role:

* Students must register with a known faculty, group, year and study
  level. These fields drive the hard-filter on retrieval, so they
  cannot be missing.
* Teachers must register with a known faculty (department / position
  remain optional).
* Admins are created out-of-band and have no required dictionary
  fields.

Profile dictionary fields (``faculty_id``, ``group_id``, ``year``,
``level``) are intentionally **immutable** for non-admin users — once
registered, only an admin can correct them. This is enforced at the
endpoint layer, not on the model itself.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.models.dictionary import StudyLevel


class UserRole(str, Enum):
    student = "student"
    teacher = "teacher"
    admin = "admin"


class RegistrationRole(str, Enum):
    """Roles allowed during self-registration. Admin accounts are created by existing admins only."""

    student = "student"
    teacher = "teacher"


class UserCreate(BaseModel):
    """Schema for user registration."""

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v

    # Bounded so a malicious registration cannot smuggle a multi-MB
    # body through and inflate the users collection / audit metadata.
    full_name: str = Field(..., min_length=1, max_length=200)
    role: RegistrationRole

    # Faculty is mandatory for both roles — it drives access control.
    faculty_id: str = Field(..., min_length=1, max_length=64)

    # Student-specific (mandatory when role == student).
    group_id: Optional[str] = Field(None, max_length=64)
    year: Optional[int] = Field(None, ge=1, le=6)
    level: Optional[StudyLevel] = None

    # Teacher-specific (free text, not in dictionary).
    department: Optional[str] = Field(None, max_length=200)
    position: Optional[str] = Field(None, max_length=200)

    @model_validator(mode="after")
    def enforce_role_specific_fields(self) -> "UserCreate":
        if self.role == RegistrationRole.student:
            missing = [
                name
                for name, value in (
                    ("group_id", self.group_id),
                    ("year", self.year),
                    ("level", self.level),
                )
                if value in (None, "")
            ]
            if missing:
                raise ValueError(
                    "Students must provide " + ", ".join(missing)
                )
        return self


class UserInDB(BaseModel):
    """User as stored in MongoDB."""

    email: str
    hashed_password: str
    full_name: str
    role: UserRole = UserRole.student

    # Dictionary references (stored as ObjectId strings on the document).
    faculty_id: Optional[str] = None
    group_id: Optional[str] = None
    year: Optional[int] = None
    level: Optional[StudyLevel] = None

    # Teacher-specific free-text fields.
    department: Optional[str] = None
    position: Optional[str] = None

    is_approved: Optional[bool] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def set_default_approval(self):
        """Every freshly registered user starts unapproved.

        Admins explicitly approve students AND teachers — see
        ``api/v1/auth.register``. Admin accounts are pre-approved when
        seeded via the dedicated script.
        """
        if self.is_approved is None:
            self.is_approved = self.role == UserRole.admin
        return self


class ChangePasswordRequest(BaseModel):
    """Schema for changing password."""

    current_password: str = Field(..., min_length=8, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password_complexity(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class ForgotPasswordRequest(BaseModel):
    """Schema for initiating password reset."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Schema for resetting password with token."""

    token: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_new_password_complexity(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class ProfileUpdateRequest(BaseModel):
    """Profile fields a non-admin user can self-update.

    Dictionary fields (``faculty_id``, ``group_id``, ``year``,
    ``level``) are intentionally absent — only admins may change those
    via the dedicated admin endpoint, so the registered audience for a
    student stays a verified fact.
    """

    full_name: Optional[str] = Field(None, min_length=1, max_length=200)
    department: Optional[str] = Field(None, max_length=200)
    position: Optional[str] = Field(None, max_length=200)


class AdminUserUpdateRequest(BaseModel):
    """Profile fields an admin can change for any user.

    Lets the admin correct a wrong faculty / group / year / level on
    behalf of the student — there is no self-service path for those.
    """

    full_name: Optional[str] = Field(None, min_length=1, max_length=200)
    faculty_id: Optional[str] = Field(None, max_length=64)
    group_id: Optional[str] = Field(None, max_length=64)
    year: Optional[int] = Field(None, ge=1, le=6)
    level: Optional[StudyLevel] = None
    department: Optional[str] = Field(None, max_length=200)
    position: Optional[str] = Field(None, max_length=200)


class UserResponse(BaseModel):
    """User data returned in API responses (no password)."""

    id: str
    email: str
    full_name: str
    role: UserRole
    faculty_id: Optional[str] = None
    faculty_name: Optional[str] = None
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    year: Optional[int] = None
    level: Optional[StudyLevel] = None
    department: Optional[str] = None
    position: Optional[str] = None
    is_approved: bool
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
