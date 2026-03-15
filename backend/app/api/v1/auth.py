"""Auth API endpoints — register, login, refresh, /me."""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from pydantic import BaseModel

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.dependencies import get_current_user
from app.core.rate_limit import limiter
from app.models.user import UserCreate, UserResponse
from app.services.database import get_database

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

    token_data = {"sub": user["email"], "role": user["role"]}
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
