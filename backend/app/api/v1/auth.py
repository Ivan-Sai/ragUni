"""Auth API endpoints — register, login, refresh, /me, password, profile."""

import logging
import smtplib
from datetime import datetime, timezone
from typing import Any

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
from app.models.user import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ProfileUpdateRequest,
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


# --- Endpoints ---
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, user_data: UserCreate):
    """Register a new user (student or teacher)."""
    db = get_database()
    existing = await db.users.find_one({"email": user_data.email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )

    now = datetime.now(timezone.utc)
    is_approved = user_data.role != "teacher"

    user_doc = {
        "email": user_data.email,
        "hashed_password": hash_password(user_data.password),
        "full_name": user_data.full_name,
        "role": user_data.role.value if hasattr(user_data.role, "value") else user_data.role,
        "faculty": user_data.faculty,
        "group": user_data.group,
        "year": user_data.year,
        "department": user_data.department,
        "position": user_data.position,
        "is_approved": is_approved,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }

    result = await db.users.insert_one(user_doc)

    return UserResponse(
        id=str(result.inserted_id),
        email=user_doc["email"],
        full_name=user_doc["full_name"],
        role=user_doc["role"],
        faculty=user_doc["faculty"],
        group=user_doc["group"],
        year=user_doc["year"],
        department=user_doc["department"],
        position=user_doc["position"],
        is_approved=user_doc["is_approved"],
        is_active=user_doc["is_active"],
        created_at=user_doc["created_at"],
        updated_at=user_doc["updated_at"],
    )


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

    token_data = {"sub": user["email"], "role": user["role"]}
    return AccessTokenResponse(
        access_token=create_access_token(data=token_data),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict[str, Any] = Depends(get_current_user)):
    """Get current user profile."""
    return UserResponse(
        id=str(current_user["_id"]),
        email=current_user["email"],
        full_name=current_user.get("full_name", ""),
        role=current_user["role"],
        faculty=current_user.get("faculty"),
        group=current_user.get("group"),
        year=current_user.get("year"),
        department=current_user.get("department"),
        position=current_user.get("position"),
        is_approved=current_user.get("is_approved", False),
        is_active=current_user.get("is_active", True),
        created_at=current_user.get("created_at", datetime.now(timezone.utc)),
        updated_at=current_user.get("updated_at"),
    )


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
    """Update current user's profile fields."""
    user_role = current_user.get("role", "student")

    # Build update dict from non-None fields only
    update_fields: dict[str, Any] = {}
    for field_name in ("full_name", "faculty"):
        value = getattr(body, field_name)
        if value is not None:
            update_fields[field_name] = value

    # Role-specific fields
    if user_role == "student":
        for field_name in ("group", "year"):
            value = getattr(body, field_name)
            if value is not None:
                update_fields[field_name] = value
        if body.department is not None or body.position is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Students cannot update teacher fields",
            )
    elif user_role == "teacher":
        for field_name in ("department", "position"):
            value = getattr(body, field_name)
            if value is not None:
                update_fields[field_name] = value
        if body.group is not None or body.year is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Teachers cannot update student fields",
            )
    elif user_role == "admin":
        for field_name in ("group", "year", "department", "position"):
            value = getattr(body, field_name)
            if value is not None:
                update_fields[field_name] = value

    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Немає полів для оновлення",
        )

    now = datetime.now(timezone.utc)
    update_fields["updated_at"] = now

    db = get_database()
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": update_fields},
    )

    updated_user = await db.users.find_one({"_id": current_user["_id"]})
    return UserResponse(
        id=str(updated_user["_id"]),
        email=updated_user["email"],
        full_name=updated_user.get("full_name", ""),
        role=updated_user["role"],
        faculty=updated_user.get("faculty"),
        group=updated_user.get("group"),
        year=updated_user.get("year"),
        department=updated_user.get("department"),
        position=updated_user.get("position"),
        is_approved=updated_user.get("is_approved", False),
        is_active=updated_user.get("is_active", True),
        created_at=updated_user.get("created_at", datetime.now(timezone.utc)),
        updated_at=updated_user.get("updated_at"),
    )
