"""User models for authentication and RBAC."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


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

    full_name: str = Field(..., min_length=1)
    role: RegistrationRole
    faculty: str = Field(..., min_length=1)

    # Student-specific
    group: Optional[str] = None
    year: Optional[int] = Field(None, ge=1, le=6)

    # Teacher-specific
    department: Optional[str] = None
    position: Optional[str] = None


class UserInDB(BaseModel):
    """User as stored in MongoDB."""

    email: str
    hashed_password: str
    full_name: str
    role: UserRole = UserRole.student
    faculty: Optional[str] = None

    # Student-specific
    group: Optional[str] = None
    year: Optional[int] = None

    # Teacher-specific
    department: Optional[str] = None
    position: Optional[str] = None

    is_approved: Optional[bool] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def set_default_approval(self):
        """Students are approved by default, teachers need admin approval."""
        if self.is_approved is None:
            self.is_approved = self.role == UserRole.student
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
    """Schema for updating user profile."""

    full_name: Optional[str] = Field(None, min_length=1)
    faculty: Optional[str] = Field(None, min_length=1)

    # Student-specific
    group: Optional[str] = None
    year: Optional[int] = Field(None, ge=1, le=6)

    # Teacher-specific
    department: Optional[str] = None
    position: Optional[str] = None


class UserResponse(BaseModel):
    """User data returned in API responses (no password)."""

    id: str
    email: str
    full_name: str
    role: UserRole
    faculty: Optional[str] = None
    group: Optional[str] = None
    year: Optional[int] = None
    department: Optional[str] = None
    position: Optional[str] = None
    is_approved: bool
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
