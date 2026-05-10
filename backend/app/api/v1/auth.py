"""Auth API endpoints — register, login, refresh, logout, /me, password, profile.

Security model
--------------

* ``/login`` is gated by per-IP rate limit (slowapi) AND per-user
  account lockout (``services.account_lockout``). The combination
  defeats both single-IP brute-force and distributed credential
  stuffing.
* ``/refresh`` checks the presented refresh token against a server-
  side allowlist (``services.refresh_tokens``). A ``/logout`` revokes
  the current refresh token; a password change or admin role change
  revokes every refresh token for the user.
* Password reset tokens are hashed before being stored on the user
  document — a database read does not yield a usable token. Reset
  also revokes all refresh tokens.
* Every minted JWT carries ``iss``, ``aud``, ``iat``, ``jti`` and
  ``exp``; every decode requires them. See ``core.security`` for the
  algorithm whitelist.
"""

import logging
import smtplib
from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from pydantic import BaseModel

from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
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
from app.services import account_lockout, refresh_tokens
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


class LogoutRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MessageResponse(BaseModel):
    message: str


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


def _normalise_email(email: str) -> str:
    """Case-fold the email so ``Alice@x.com`` and ``alice@x.com`` are
    the same account. EmailStr already validates the syntax."""
    return email.strip().lower()


async def _user_to_response(user: dict[str, Any]) -> UserResponse:
    """Build the API representation of a user, resolving dictionary names."""
    db = get_database()

    faculty_name: Optional[str] = None
    if user.get("faculty_id"):
        faculty = await db.faculties.find_one(
            {"_id": user["faculty_id"]}, {"name": 1}
        )
        if faculty:
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


async def _issue_token_pair(user: dict[str, Any]) -> TokenResponse:
    """Mint an access + refresh token pair and persist the refresh
    token's jti in the allowlist."""
    token_data = {"sub": user["email"], "role": user["role"]}
    access = create_access_token(data=token_data)
    refresh, jti = create_refresh_token(data=token_data)
    # Decode our own token to read the exact ``exp`` we put in — keeps
    # the persisted expiry in lock-step with the JWT claim.
    payload = decode_token(refresh)
    expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc)
    await refresh_tokens.store(
        jti=jti,
        user_id=str(user["_id"]),
        raw_token=refresh,
        expires_at=expires_at,
    )
    return TokenResponse(access_token=access, refresh_token=refresh)


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

    email = _normalise_email(user_data.email)
    existing = await db.users.find_one({"email": email})
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
        "email": email,
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
    """Login with email and password, returns JWT tokens.

    Defends against credential stuffing with a per-account lockout
    layered on top of the per-IP rate limit. Five failed attempts
    within 15 minutes lock the account for 15 minutes.
    """
    db = get_database()
    email = _normalise_email(form_data.username)
    user = await db.users.find_one({"email": email})

    # Generic credential failure — same response whether the email is
    # unknown or the password wrong. Don't leak which.
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not user:
        raise invalid_credentials

    # Refuse early when the account is currently locked. Surfacing the
    # remaining seconds gives the legitimate user something useful;
    # an attacker just learns "still locked" which they could deduce
    # from a 423 anyway.
    locked = account_lockout.check_locked(user)
    if locked.locked:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account temporarily locked due to too many failed attempts",
            headers={"Retry-After": str(locked.seconds_remaining)},
        )

    if not verify_password(form_data.password, user["hashed_password"]):
        new_status = await account_lockout.record_failed_attempt(user)
        if new_status.locked:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Account temporarily locked due to too many failed attempts",
                headers={"Retry-After": str(new_status.seconds_remaining)},
            )
        raise invalid_credentials

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

    # Successful auth — wipe the failure counter so a future blip
    # doesn't compound with old failures.
    await account_lockout.clear(user)

    # Track login event (background — don't slow the user-facing
    # response if analytics has issues).
    from app.services.analytics import track_event
    await track_event("login", str(user["_id"]), user["role"])

    return await _issue_token_pair(user)


@router.post("/refresh", response_model=AccessTokenResponse)
@limiter.limit("10/minute")
async def refresh_token(request: Request, body: RefreshRequest):
    """Refresh access token using a refresh token.

    The presented refresh token must be in the server-side allowlist
    AND not revoked. Logout / password change / admin role change all
    invalidate refresh tokens, so a stolen token loses its value the
    moment any of those actions are taken.
    """
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid refresh token",
    )
    try:
        payload = decode_token(body.refresh_token)
    except JWTError as exc:
        raise invalid from exc

    if payload.get("type") != "refresh":
        raise invalid

    jti = payload.get("jti")
    if not jti:
        raise invalid
    if not await refresh_tokens.is_active(jti=jti, raw_token=body.refresh_token):
        raise invalid

    email = payload.get("sub")
    db = get_database()
    user = await db.users.find_one({"email": email})
    if not user:
        # Token references a non-existent user — defensively revoke
        # the jti so it cannot be reused.
        await refresh_tokens.revoke(jti=jti)
        raise invalid

    # Block refresh for deactivated or unapproved accounts —
    # mirrors the check in get_current_user so revoked users cannot
    # keep minting access tokens from a stolen / stale refresh token.
    if not user.get("is_active", False):
        await refresh_tokens.revoke(jti=jti)
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


@router.post("/logout", response_model=MessageResponse)
@limiter.limit("30/minute")
async def logout(request: Request, body: LogoutRequest):
    """Revoke the supplied refresh token.

    Accepts an invalid / unknown / expired token silently (returns 200)
    so a logged-out user clicking "logout" again gets the expected UX
    instead of an error. The corresponding access token expires on
    its own short TTL — there is intentionally no allowlist for access
    tokens because they live ≤30 minutes.
    """
    try:
        payload = decode_token(body.refresh_token)
        jti = payload.get("jti")
        if jti and payload.get("type") == "refresh":
            await refresh_tokens.revoke(jti=jti)
    except JWTError:
        # Don't reveal whether the token was valid; the logout result
        # is the same either way.
        pass
    return MessageResponse(message="Logged out")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict[str, Any] = Depends(get_current_user)):
    """Get current user profile."""
    return await _user_to_response(current_user)


# --- Password management ---
@router.put("/password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Change current user's password.

    On success, every outstanding refresh token for this user is
    revoked — the user (and any attacker holding a stolen refresh
    token) must re-authenticate. The action is recorded in the audit
    log.
    """
    if not verify_password(body.current_password, current_user["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must differ from the current one",
        )

    db = get_database()
    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": {"hashed_password": hash_password(body.new_password), "updated_at": now}},
    )

    revoked = await refresh_tokens.revoke_all_for_user(
        user_id=str(current_user["_id"])
    )

    # Audit the action — don't log the password itself or any other PII.
    from app.services import audit_log
    from app.models.audit import AuditAction
    await audit_log.record_action(
        actor=current_user,
        action=AuditAction.PASSWORD_CHANGED,
        resource_type="user",
        resource_id=str(current_user["_id"]),
        metadata={"refresh_tokens_revoked": revoked},
    )

    return MessageResponse(message="Password changed successfully")


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("3/minute")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
):
    """Request a password reset link.

    Always returns 200 with an identical message regardless of whether
    the email exists, defeating user-enumeration via response body.
    The DB lookup + email send is moved to a background task so the
    response time is constant — closing the timing-side-channel that
    a synchronous send would open.
    """
    email = _normalise_email(body.email)
    background_tasks.add_task(_send_reset_email_if_exists, email)
    return MessageResponse(
        message=(
            "If this email is registered, a password reset link has been sent"
        )
    )


async def _send_reset_email_if_exists(email: str) -> None:
    """Background helper for /forgot-password — runs after the response
    is sent. Storing the SHA-256 of the token (not the token itself)
    means a DB read does not give an attacker a usable reset
    credential."""
    db = get_database()
    user = await db.users.find_one({"email": email})
    if not user:
        return

    token, token_hash = create_password_reset_token(email)
    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"password_reset_token_hash": token_hash}},
    )
    from app.services.email import send_password_reset_email
    try:
        await send_password_reset_email(email, token)
    except (OSError, smtplib.SMTPException) as e:
        # Log without leaking the email content into the message itself.
        logger.error(
            "Failed to send password reset email: %s",
            type(e).__name__,
            exc_info=True,
        )


@router.post("/reset-password", response_model=MessageResponse)
@limiter.limit("5/minute")
async def reset_password(request: Request, body: ResetPasswordRequest):
    """Reset password using a reset token.

    Three layers of validation:
      1. The JWT must be well-formed and not expired.
      2. The SHA-256 of the presented token must match the hash stored
         on the user document (defeats DB-read token theft, defeats
         reuse after the user requested another reset).
      3. After success, the stored hash is unset (one-shot) and every
         refresh token for the user is revoked.
    """
    invalid = HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Reset token is invalid or expired",
    )
    try:
        email = verify_password_reset_token(body.token)
    except JWTError:
        raise invalid

    db = get_database()
    user = await db.users.find_one({"email": _normalise_email(email)})
    if not user:
        raise invalid

    stored_hash = user.get("password_reset_token_hash")
    if not stored_hash or stored_hash != hash_token(body.token):
        raise invalid

    now = datetime.now(timezone.utc)
    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "hashed_password": hash_password(body.new_password),
                "updated_at": now,
            },
            # One-shot: drop the hash so the same token cannot be
            # replayed.
            "$unset": {"password_reset_token_hash": ""},
        },
    )

    # Force everyone who held a refresh token for this account to
    # re-authenticate — the password has changed.
    revoked = await refresh_tokens.revoke_all_for_user(
        user_id=str(user["_id"])
    )

    from app.services import audit_log
    from app.models.audit import AuditAction
    await audit_log.record_action(
        actor=user,
        action=AuditAction.PASSWORD_CHANGED,
        resource_type="user",
        resource_id=str(user["_id"]),
        metadata={"via": "reset", "refresh_tokens_revoked": revoked},
    )

    return MessageResponse(message="Password reset successfully")


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
            detail="No fields to update",
        )

    update_fields["updated_at"] = datetime.now(timezone.utc)

    db = get_database()
    await db.users.update_one(
        {"_id": current_user["_id"]},
        {"$set": update_fields},
    )

    updated_user = await db.users.find_one({"_id": current_user["_id"]})
    return await _user_to_response(updated_user)
