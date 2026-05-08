"""Auth API endpoints — register, login, refresh, /me, password, profile."""

import logging
import smtplib
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from pydantic import BaseModel

from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
    verify_password_reset_token,
)
from app.core.dependencies import get_current_user
from app.core.rate_limit import limiter
from app.models.dictionary import StudyLevel
from app.models.user import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ProfileUpdateRequest,
    RegistrationRole,
    ResetPasswordRequest,
    UserCreate,
    UserResponse,
)
from app.services.database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Auth"])


# --- Request/Response schemas ---
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_oid(value: str, field: str) -> ObjectId:
    """Parse a dictionary id supplied by the client.

    Returns 400 instead of 500 when the value is not a valid ObjectId
    so registration / profile updates surface a usable error message.
    """
    try:
        return ObjectId(value)
    except (InvalidId, ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid {field}",
        )


async def _user_to_response(user: dict[str, Any]) -> UserResponse:
    """Build the API representation of a user, resolving dictionary names."""
    db = get_database()

    faculty_name: Optional[str] = None
    if user.get("faculty_id"):
        faculty = await db.faculties.find_one(
            {"_id": user["faculty_id"]}, {"name": 1}
        )
        if faculty:
            # ``name`` is optional defensive — the projection requests
            # it, but partial test fixtures sometimes return only _id.
            faculty_name = faculty.get("name")

    group_name: Optional[str] = None
    if user.get("group_id"):
        group = await db.groups.find_one(
            {"_id": user["group_id"]}, {"name": 1}
        )
        if group:
            group_name = group.get("name")

    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        full_name=user.get("full_name", ""),
        role=user["role"],
        faculty_id=str(user["faculty_id"]) if user.get("faculty_id") else None,
        faculty_name=faculty_name,
        group_id=str(user["group_id"]) if user.get("group_id") else None,
        group_name=group_name,
        year=user.get("year"),
        level=user.get("level"),
        department=user.get("department"),
        position=user.get("position"),
        is_approved=bool(user.get("is_approved", False)),
        is_active=bool(user.get("is_active", True)),
        created_at=user.get("created_at") or datetime.now(timezone.utc),
        updated_at=user.get("updated_at"),
    )


# --- Endpoints ---
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, user_data: UserCreate):
    """Register a new user (student or teacher).

    Both students and teachers are placed in pending state — an admin
    must verify the supplied faculty/group/year/level before the
    account is allowed to log in. This guarantees the audience used by
    retrieval is a vetted fact, not user-supplied.
    """
    db = get_database()

    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )

    # Resolve and validate dictionary references.
    faculty_oid = _safe_oid(user_data.faculty_id, "faculty_id")
    if not await db.faculties.find_one({"_id": faculty_oid}, {"_id": 1}):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Faculty does not exist",
        )

    group_oid: Optional[ObjectId] = None
    if user_data.role == RegistrationRole.student:
        # Mandatory by validator on UserCreate, but recheck the existence
        # of the group + that it belongs to the chosen faculty.
        group_oid = _safe_oid(user_data.group_id or "", "group_id")
        group_doc = await db.groups.find_one({"_id": group_oid})
        if not group_doc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Group does not exist",
            )
        if group_doc["faculty_id"] != faculty_oid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Group does not belong to the selected faculty",
            )
        if group_doc["level"] != user_data.level.value:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Group's study level does not match the selected level",
            )

    now = datetime.now(timezone.utc)

    user_doc: dict[str, Any] = {
        "email": user_data.email,
        "hashed_password": hash_password(user_data.password),
        "full_name": user_data.full_name,
        "role": user_data.role.value if hasattr(user_data.role, "value") else user_data.role,
        "faculty_id": faculty_oid,
        "group_id": group_oid,
        "year": user_data.year if user_data.role == RegistrationRole.student else None,
        "level": (
            user_data.level.value
            if user_data.role == RegistrationRole.student and user_data.level
            else None
        ),
        "department": user_data.department,
        "position": user_data.position,
        # Both students and teachers wait for an admin — only admins
        # bypass this gate, and admins are seeded out of band.
        "is_approved": False,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }

    result = await db.users.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id
    return await _user_to_response(user_doc)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    """Login with email and password, returns JWT tokens."""
    db = get_database()
    user = await db.users.find_one({"email": form_data.username})
    if not user or not verify_password(form_data.password, user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is blocked",
        )

    if not user.get("is_approved", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is pending approval",
        )

    token_data = {"sub": user["email"], "role": user["role"]}

    # Track login event
    from app.services.analytics import track_event
    await track_event("login", str(user["_id"]), user["role"])

    return TokenResponse(
        access_token=create_access_token(data=token_data),
        refresh_token=create_refresh_token(data=token_data),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
@limiter.limit("10/minute")
async def refresh_token(request: Request, body: RefreshRequest):
    """Refresh access token using refresh token."""
    try:
        payload = decode_token(body.refresh_token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from exc

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is not a refresh token",
        )

    email = payload.get("sub")
    db = get_database()
    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Block refresh for deactivated or unapproved accounts —
    # mirrors the check in get_current_user so revoked users cannot
    # keep minting access tokens from a stolen / stale refresh token.
    if not user.get("is_active", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account deactivated",
        )
    if not user.get("is_approved", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account pending administrator approval",
        )

    token_data = {"sub": user["email"], "role": user["role"]}
    return AccessTokenResponse(
        access_token=create_access_token(data=token_data),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict[str, Any] = Depends(get_current_user)):
    """Get current user profile."""
    return await _user_to_response(current_user)


# --- Password management ---
@router.put("/password")
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Change current user's password."""
    if not verify_password(body.current_password, current_user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Поточний пароль невірний",
        )

    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Новий пароль має відрізнятися від поточного",
        )

    db = get_database()
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"hashed_password": hash_password(body.new_password), "updated_at": now}},
    )
    return {"message": "Пароль успішно змінено"}


@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(request: Request, body: ForgotPasswordRequest):
    """Request a password reset link.

    Always returns 200 to prevent email enumeration.
    """
    db = get_database()
    user = await db.users.find_one({"email": body.email})

    generic_message = "If this email is registered, a password reset link has been sent"

    if not user:
        return {"message": generic_message}

    token = create_password_reset_token(body.email)
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_reset_token": token}},
    )
    from app.services.email import send_password_reset_email
    try:
        await send_password_reset_email(body.email, token)
    except (OSError, smtplib.SMTPException) as e:
        logger.error("Failed to send password reset email: %s", e, exc_info=True)

    return {"message": generic_message}


@router.post("/reset-password")
@limiter.limit("5/minute")
async def reset_password(request: Request, body: ResetPasswordRequest):
    """Reset password using a reset token."""
    try:
        email = verify_password_reset_token(body.token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Токен скидання недійсний або протермінований",
        )

    db = get_database()
    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Користувача не знайдено",
        )

    # Verify the token matches what was stored (prevent reuse)
    if user.get("password_reset_token") != body.token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Токен скидання вже використано",
        )

    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "hashed_password": hash_password(body.new_password),
                "updated_at": now,
            },
            "$unset": {"password_reset_token": ""},
        },
    )
    return {"message": "Пароль успішно скинуто"}


# --- Profile ---
@router.put("/profile", response_model=UserResponse)
@limiter.limit("10/minute")
async def update_profile(
    request: Request,
    body: ProfileUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Update the user's own non-dictionary profile fields.

    Dictionary fields (faculty / group / year / level) cannot be changed
    self-service — only an admin may correct them via the admin
    endpoint. This keeps the audience used by retrieval verified.
    """
    user_role = current_user.get("role", "student")

    update_fields: dict[str, Any] = {}

    if body.full_name is not None:
        update_fields["full_name"] = body.full_name

    if user_role in ("teacher", "admin"):
        if body.department is not None:
            update_fields["department"] = body.department
        if body.position is not None:
            update_fields["position"] = body.position
    elif body.department is not None or body.position is not None:
        # Students cannot set teacher-only fields.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Students cannot update teacher fields",
        )

    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Немає полів для оновлення",
        )

    update_fields["updated_at"] = datetime.now(timezone.utc)

    db = get_database()
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": update_fields},
    )

    updated_user = await db.users.find_one({"_id": current_user["_id"]})
    return await _user_to_response(updated_user)
