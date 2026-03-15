"""Admin API endpoints — user management, teacher approvals."""

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.core.dependencies import get_current_user, require_role
from app.models.user import UserResponse, UserRole
from app.services.database import get_database

router = APIRouter(tags=["Admin"])


# --- Request schemas ---
class BlockRequest(BaseModel):
    is_active: bool


class RoleChangeRequest(BaseModel):
    role: UserRole


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
@router.get("/users")
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_user: dict[str, Any] = Depends(admin_only),
):
    """List all users (admin only)."""
    db = get_database()
    cursor = db.users.find({}, {"hashed_password": 0}).skip(skip).limit(limit)
    users = await cursor.to_list(length=limit)
    total = await db.users.count_documents({})

    for user in users:
        user["_id"] = str(user["_id"])

    return {"users": users, "total": total}


@router.get("/users/pending")
async def list_pending_teachers(current_user: dict[str, Any] = Depends(admin_only)):
    """List pending teacher approvals (admin only)."""
    db = get_database()
    cursor = db.users.find(
        {"role": "teacher", "is_approved": False},
        {"hashed_password": 0},
    )
    users = await cursor.to_list(length=100)

    for user in users:
        user["_id"] = str(user["_id"])

    return users


@router.put("/users/{user_id}/approve")
async def approve_teacher(user_id: str, current_user: dict[str, Any] = Depends(admin_only)):
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
    return {"message": "Teacher approved", "user_id": user_id}


@router.put("/users/{user_id}/reject")
async def reject_teacher(user_id: str, current_user: dict[str, Any] = Depends(admin_only)):
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
    return {"message": "Application rejected", "user_id": user_id}


@router.put("/users/{user_id}/block")
async def block_user(
    user_id: str,
    request: BlockRequest,
    current_user: dict[str, Any] = Depends(admin_only),
):
    """Block or unblock a user (admin only)."""
    oid = _parse_object_id(user_id)
    db = get_database()
    user = await db.users.find_one({"_id": oid})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await db.users.update_one(
        {"_id": oid},
        {"$set": {"is_active": request.is_active, "updated_at": datetime.now(timezone.utc)}},
    )

    action = "unblocked" if request.is_active else "blocked"
    return {"message": f"User {action}", "user_id": user_id}


@router.put("/users/{user_id}/role")
async def change_user_role(
    user_id: str,
    request: RoleChangeRequest,
    current_user: dict[str, Any] = Depends(admin_only),
):
    """Change a user's role (admin only)."""
    oid = _parse_object_id(user_id)
    db = get_database()

    user = await db.users.find_one({"_id": oid})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    await db.users.update_one(
        {"_id": oid},
        {"$set": {"role": request.role.value, "updated_at": datetime.now(timezone.utc)}},
    )
    return {"message": f"Role changed to {request.role.value}", "user_id": user_id}
