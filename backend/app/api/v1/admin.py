"""Admin API endpoints — user management, teacher approvals, analytics."""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from app.core.dependencies import get_current_user, require_role
from app.core.rate_limit import limiter
from app.models.audit import (
    AuditAction,
    AuditLogFilter,
    AuditLogListResponse,
)
from app.models.user import UserResponse, UserRole
from app.services.audit_log import list_entries as audit_list_entries
from app.services.audit_log import record_action as audit_record_action
from app.services.database import get_database

router = APIRouter(tags=["Admin"])


# --- Request schemas ---
class BlockRequest(BaseModel):
    is_active: bool


class RoleChangeRequest(BaseModel):
    role: UserRole


class UsersListResponse(BaseModel):
    users: list[UserResponse]
    total: int


class AdminActionResponse(BaseModel):
    message: str
    user_id: str


def _user_doc_to_response(user: dict[str, Any]) -> UserResponse:
    """Convert a MongoDB user document into a safe UserResponse.

    Guarantees that internal-only fields (hashed_password, is_rejected, etc.)
    are never leaked to API clients, regardless of what the DB query returned.
    """
    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        full_name=user.get("full_name", ""),
        role=user["role"],
        faculty=user.get("faculty"),
        group=user.get("group"),
        year=user.get("year"),
        department=user.get("department"),
        position=user.get("position"),
        is_approved=bool(user.get("is_approved", False)),
        is_active=bool(user.get("is_active", True)),
        created_at=user.get("created_at") or datetime.now(timezone.utc),
        updated_at=user.get("updated_at"),
    )


# --- Dependencies ---
admin_only = require_role("admin")


def _parse_object_id(value: str) -> ObjectId:
    """Parse string to ObjectId, raise 400 on invalid."""
    try:
        return ObjectId(value)
    except (InvalidId, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user identifier",
        )


# --- Endpoints ---
@router.get("/users", response_model=UsersListResponse)
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict[str, Any] = Depends(admin_only),
) -> UsersListResponse:
    """List all users (admin only)."""
    db = get_database()
    cursor = db.users.find({}, {"hashed_password": 0}).skip(skip).limit(limit)
    users = await cursor.to_list(length=limit)
    total = await db.users.count_documents({})

    return UsersListResponse(
        users=[_user_doc_to_response(u) for u in users],
        total=total,
    )


@router.get("/users/pending", response_model=list[UserResponse])
async def list_pending_teachers(
    current_user: dict[str, Any] = Depends(admin_only),
) -> list[UserResponse]:
    """List pending teacher approvals (admin only)."""
    db = get_database()
    cursor = db.users.find(
        {"role": "teacher", "is_approved": False},
        {"hashed_password": 0},
    )
    users = await cursor.to_list(length=100)
    return [_user_doc_to_response(u) for u in users]


@router.put("/users/{user_id}/approve", response_model=AdminActionResponse)
async def approve_teacher(
    user_id: str, current_user: dict[str, Any] = Depends(admin_only)
) -> AdminActionResponse:
    """Approve a pending teacher (admin only)."""
    oid = _parse_object_id(user_id)
    db = get_database()
    user = await db.users.find_one({"_id": oid})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.get("is_approved"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is already approved",
        )

    await db.users.update_one(
        {"_id": oid},
        {"$set": {"is_approved": True, "updated_at": datetime.now(timezone.utc)}},
    )
    await audit_record_action(
        actor=current_user,
        action=AuditAction.USER_APPROVED,
        resource_type="user",
        resource_id=user_id,
        metadata={"target_email": user.get("email"), "target_role": user.get("role")},
    )
    return AdminActionResponse(message="Teacher approved", user_id=user_id)


@router.put("/users/{user_id}/reject", response_model=AdminActionResponse)
async def reject_teacher(
    user_id: str, current_user: dict[str, Any] = Depends(admin_only)
) -> AdminActionResponse:
    """Reject a pending teacher (admin only). Marks as rejected instead of deleting."""
    oid = _parse_object_id(user_id)
    db = get_database()
    user = await db.users.find_one({"_id": oid})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if user.get("is_approved"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reject an already approved user",
        )

    await db.users.update_one(
        {"_id": oid},
        {"$set": {"is_rejected": True, "is_active": False, "updated_at": datetime.now(timezone.utc)}},
    )
    await audit_record_action(
        actor=current_user,
        action=AuditAction.USER_REJECTED,
        resource_type="user",
        resource_id=user_id,
        metadata={"target_email": user.get("email")},
    )
    return AdminActionResponse(message="Application rejected", user_id=user_id)


@router.put("/users/{user_id}/block", response_model=AdminActionResponse)
async def block_user(
    user_id: str,
    request: BlockRequest,
    current_user: dict[str, Any] = Depends(admin_only),
) -> AdminActionResponse:
    """Block or unblock a user (admin only)."""
    oid = _parse_object_id(user_id)

    if oid == current_user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot block yourself",
        )

    db = get_database()
    user = await db.users.find_one({"_id": oid})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Guard against admins locking themselves out of the panel.
    if str(user["_id"]) == str(current_user["_id"]) and not request.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot deactivate their own account",
        )

    await db.users.update_one(
        {"_id": oid},
        {"$set": {"is_active": request.is_active, "updated_at": datetime.now(timezone.utc)}},
    )

    action = "unblocked" if request.is_active else "blocked"
    await audit_record_action(
        actor=current_user,
        action=(
            AuditAction.USER_UNBLOCKED
            if request.is_active
            else AuditAction.USER_BLOCKED
        ),
        resource_type="user",
        resource_id=user_id,
        metadata={"target_email": user.get("email")},
    )
    return AdminActionResponse(message=f"User {action}", user_id=user_id)


@router.put("/users/{user_id}/role", response_model=AdminActionResponse)
async def change_user_role(
    user_id: str,
    request: RoleChangeRequest,
    current_user: dict[str, Any] = Depends(admin_only),
) -> AdminActionResponse:
    """Change a user's role (admin only)."""
    oid = _parse_object_id(user_id)
    db = get_database()

    user = await db.users.find_one({"_id": oid})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    # Prevent an admin from demoting themselves — avoids accidental loss of
    # admin access when only one administrator exists in the system.
    if (
        str(user["_id"]) == str(current_user["_id"])
        and request.role != UserRole.admin
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Administrators cannot demote their own account",
        )

    previous_role = user.get("role")
    await db.users.update_one(
        {"_id": oid},
        {"$set": {"role": request.role.value, "updated_at": datetime.now(timezone.utc)}},
    )
    await audit_record_action(
        actor=current_user,
        action=AuditAction.USER_ROLE_CHANGED,
        resource_type="user",
        resource_id=user_id,
        metadata={
            "target_email": user.get("email"),
            "previous_role": previous_role,
            "new_role": request.role.value,
        },
    )
    return AdminActionResponse(
        message=f"Role changed to {request.role.value}", user_id=user_id
    )


# --- Audit log viewing ---
@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    actor_id: str | None = Query(None),
    action: str | None = Query(None),
    resource_type: str | None = Query(None),
    resource_id: str | None = Query(None),
    current_user: dict[str, Any] = Depends(admin_only),
) -> AuditLogListResponse:
    """List audit log entries, newest first (admin only)."""
    # Parse the action string into the enum lazily so we can return a
    # clean 400 on unknown values instead of a 500.
    parsed_action = None
    if action:
        try:
            parsed_action = AuditAction(action)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unknown audit action",
            )

    filters = AuditLogFilter(
        actor_id=actor_id,
        action=parsed_action,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    entries, total = await audit_list_entries(filters, skip=skip, limit=limit)
    return AuditLogListResponse(
        entries=entries,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/analytics")
@limiter.limit("20/minute")
async def get_analytics(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    current_user: dict[str, Any] = Depends(admin_only),
):
    """Get usage analytics (admin only)."""
    from app.services.analytics import get_summary

    return await get_summary(days=days)
