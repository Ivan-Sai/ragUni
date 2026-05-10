"""Admin API endpoints — user management, approvals, dictionary edits, analytics."""

from datetime import datetime, timezone
from typing import Any, Optional

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
from app.models.dictionary import StudyLevel
from app.models.responses import AnalyticsSummaryResponse, DailyCount
from app.models.user import (
    AdminUserUpdateRequest,
    UserResponse,
    UserRole,
)
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


async def _resolve_dictionary_names(
    users: list[dict[str, Any]],
) -> tuple[dict[ObjectId, str], dict[ObjectId, str]]:
    """Bulk-resolve faculty/group names referenced by a batch of users.

    Returns ``({faculty_id: name}, {group_id: name})``. Empty maps when
    no user in the batch carries the corresponding id, so the per-user
    response builder can stay branch-free.
    """
    db = get_database()
    faculty_ids = {u["faculty_id"] for u in users if u.get("faculty_id")}
    group_ids = {u["group_id"] for u in users if u.get("group_id")}

    faculties: dict[ObjectId, str] = {}
    if faculty_ids:
        async for fac in db.faculties.find(
            {"_id": {"$in": list(faculty_ids)}},
            {"_id": 1, "name": 1},
        ):
            faculties[fac["_id"]] = fac["name"]

    groups: dict[ObjectId, str] = {}
    if group_ids:
        async for grp in db.groups.find(
            {"_id": {"$in": list(group_ids)}},
            {"_id": 1, "name": 1},
        ):
            groups[grp["_id"]] = grp["name"]

    return faculties, groups


def _user_doc_to_response(
    user: dict[str, Any],
    faculty_names: Optional[dict[ObjectId, str]] = None,
    group_names: Optional[dict[ObjectId, str]] = None,
) -> UserResponse:
    """Convert a MongoDB user document into a safe UserResponse.

    Internal-only fields (hashed_password, is_rejected, etc.) are
    never leaked to API clients regardless of what the DB query
    returned. Dictionary names are looked up once per batch by the
    caller and passed in via maps.
    """
    faculty_names = faculty_names or {}
    group_names = group_names or {}
    fac_id = user.get("faculty_id")
    grp_id = user.get("group_id")

    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        full_name=user.get("full_name", ""),
        role=user["role"],
        faculty_id=str(fac_id) if fac_id else None,
        faculty_name=faculty_names.get(fac_id) if fac_id else None,
        group_id=str(grp_id) if grp_id else None,
        group_name=group_names.get(grp_id) if grp_id else None,
        year=user.get("year"),
        level=user.get("level"),
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

    faculty_names, group_names = await _resolve_dictionary_names(users)

    return UsersListResponse(
        users=[
            _user_doc_to_response(u, faculty_names, group_names) for u in users
        ],
        total=total,
    )


@router.get("/users/pending", response_model=list[UserResponse])
async def list_pending_users(
    current_user: dict[str, Any] = Depends(admin_only),
) -> list[UserResponse]:
    """List users awaiting approval (admin only).

    Returns both pending students and pending teachers — both must be
    vetted before they can log in. ``is_rejected`` users are excluded
    so the panel surfaces only actionable items.
    """
    db = get_database()
    cursor = db.users.find(
        {
            "is_approved": False,
            "$or": [{"is_rejected": {"$exists": False}}, {"is_rejected": False}],
        },
        {"hashed_password": 0},
    )
    users = await cursor.to_list(length=200)
    faculty_names, group_names = await _resolve_dictionary_names(users)
    return [_user_doc_to_response(u, faculty_names, group_names) for u in users]


@router.put("/users/{user_id}/approve", response_model=AdminActionResponse)
async def approve_user(
    user_id: str, current_user: dict[str, Any] = Depends(admin_only)
) -> AdminActionResponse:
    """Approve a pending user (admin only) — works for both students and teachers."""
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
    return AdminActionResponse(message="User approved", user_id=user_id)


@router.put("/users/{user_id}/reject", response_model=AdminActionResponse)
async def reject_user(
    user_id: str, current_user: dict[str, Any] = Depends(admin_only)
) -> AdminActionResponse:
    """Reject a pending user (admin only). Marks as rejected instead of deleting."""
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


# ---------------------------------------------------------------------------
# Admin-only profile edits — the only path through which dictionary
# references on a user (faculty / group / year / level) can change.
# Self-service profile updates intentionally cannot touch these.
# ---------------------------------------------------------------------------


@router.put("/users/{user_id}", response_model=UserResponse)
@limiter.limit("30/minute")
async def admin_update_user(
    request: Request,
    user_id: str,
    body: AdminUserUpdateRequest,
    current_user: dict[str, Any] = Depends(admin_only),
) -> UserResponse:
    """Admin-only profile edit covering dictionary fields.

    The admin can correct any of the following on behalf of a user:
    full_name, faculty_id, group_id, year, level, department, position.
    Validates that ``faculty_id`` / ``group_id`` exist and that the
    group belongs to the chosen faculty AND matches the chosen level.
    """
    oid = _parse_object_id(user_id)
    db = get_database()

    user = await db.users.find_one({"_id": oid})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    update_fields: dict[str, Any] = {}

    if body.full_name is not None:
        update_fields["full_name"] = body.full_name
    if body.department is not None:
        update_fields["department"] = body.department
    if body.position is not None:
        update_fields["position"] = body.position
    if body.year is not None:
        update_fields["year"] = body.year
    if body.level is not None:
        update_fields["level"] = body.level.value

    # Resolve faculty / group references so we validate before writing.
    new_faculty_id: Optional[ObjectId] = None
    if body.faculty_id is not None:
        new_faculty_id = _parse_object_id(body.faculty_id)
        if not await db.faculties.find_one({"_id": new_faculty_id}, {"_id": 1}):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Faculty does not exist",
            )
        update_fields["faculty_id"] = new_faculty_id

    if body.group_id is not None:
        if body.group_id == "":
            update_fields["group_id"] = None
        else:
            new_group_id = _parse_object_id(body.group_id)
            group_doc = await db.groups.find_one({"_id": new_group_id})
            if not group_doc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Group does not exist",
                )
            # Cross-check the group against whichever faculty_id is
            # going to be persisted (incoming or existing).
            effective_faculty_id = new_faculty_id or user.get("faculty_id")
            if effective_faculty_id and group_doc["faculty_id"] != effective_faculty_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Group does not belong to the selected faculty",
                )
            # Cross-check the group level against whichever level is
            # going to be persisted (incoming or existing).
            effective_level = body.level.value if body.level else user.get("level")
            if effective_level and group_doc["level"] != effective_level:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Group's study level does not match the selected level",
                )
            update_fields["group_id"] = new_group_id

    if not update_fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    update_fields["updated_at"] = datetime.now(timezone.utc)

    await db.users.update_one({"_id": oid}, {"$set": update_fields})
    updated = await db.users.find_one({"_id": oid})
    faculty_names, group_names = await _resolve_dictionary_names([updated])
    return _user_doc_to_response(updated, faculty_names, group_names)


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


@router.get("/analytics", response_model=AnalyticsSummaryResponse)
@limiter.limit("20/minute")
async def get_analytics(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    current_user: dict[str, Any] = Depends(admin_only),
) -> AnalyticsSummaryResponse:
    """Get usage analytics (admin only)."""
    from app.services.analytics import get_summary

    summary = await get_summary(days=days)
    return AnalyticsSummaryResponse(
        total_queries=summary.get("total_queries", 0),
        total_logins=summary.get("total_logins", 0),
        total_uploads=summary.get("total_uploads", 0),
        queries_per_day=[
            DailyCount(date=row["date"], count=row["count"])
            for row in summary.get("queries_per_day", [])
        ],
        active_users_per_day=[
            DailyCount(date=row["date"], count=row["count"])
            for row in summary.get("active_users_per_day", [])
        ],
        avg_response_time=summary.get("avg_response_time"),
    )
