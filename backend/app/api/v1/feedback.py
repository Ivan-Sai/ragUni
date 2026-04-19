"""Feedback endpoints — thumbs up/down on assistant answers."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Query, status

from app.core.dependencies import get_current_user, require_role
from app.core.rate_limit import limiter
from app.models.feedback import FeedbackCreate, FeedbackResponse, FeedbackStats
from app.services.database import get_database

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Feedback"])


@router.post("/feedback", response_model=FeedbackResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def submit_feedback(
    request: Request,
    body: FeedbackCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Submit or update feedback on an assistant message."""
    db = get_database()
    user_id = str(current_user["_id"])

    # Verify session belongs to user
    session = await db.chat_history.find_one(
        {"session_id": body.session_id, "user_id": user_id}
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сесію не знайдено",
        )

    # Verify message_index is valid (assistant messages are at odd indices)
    messages = session.get("messages", [])
    if body.message_index >= len(messages):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Невірний індекс повідомлення",
        )
    if messages[body.message_index].get("role") != "assistant":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Відгук можна залишити лише на відповідь асистента",
        )

    now = datetime.now(timezone.utc)

    # Upsert — user can change their vote
    result = await db.feedback.find_one_and_update(
        {
            "user_id": user_id,
            "session_id": body.session_id,
            "message_index": body.message_index,
        },
        {
            "$set": {
                "feedback_type": body.feedback_type.value,
                "comment": body.comment,
                "updated_at": now,
            },
            "$setOnInsert": {
                "user_id": user_id,
                "session_id": body.session_id,
                "message_index": body.message_index,
                "created_at": now,
            },
        },
        upsert=True,
        return_document=True,
    )

    return FeedbackResponse(
        id=str(result["_id"]),
        session_id=result["session_id"],
        message_index=result["message_index"],
        feedback_type=result["feedback_type"],
        comment=result.get("comment"),
        created_at=result["created_at"],
    )


@router.get("/feedback/stats", response_model=FeedbackStats)
@limiter.limit("20/minute")
async def get_feedback_stats(
    request: Request,
    current_user: dict[str, Any] = Depends(require_role("admin")),
):
    """Get aggregated feedback statistics (admin only)."""
    db = get_database()

    pipeline = [
        {
            "$group": {
                "_id": None,
                "total": {"$sum": 1},
                "thumbs_up": {
                    "$sum": {"$cond": [{"$eq": ["$feedback_type", "thumbs_up"]}, 1, 0]}
                },
                "thumbs_down": {
                    "$sum": {"$cond": [{"$eq": ["$feedback_type", "thumbs_down"]}, 1, 0]}
                },
            }
        }
    ]

    results = await db.feedback.aggregate(pipeline).to_list(length=1)

    if not results:
        return FeedbackStats(
            total_feedback=0, thumbs_up=0, thumbs_down=0, satisfaction_rate=0.0
        )

    data = results[0]
    total = data["total"]
    thumbs_up = data["thumbs_up"]
    rate = (thumbs_up / total * 100) if total > 0 else 0.0

    return FeedbackStats(
        total_feedback=total,
        thumbs_up=thumbs_up,
        thumbs_down=data["thumbs_down"],
        satisfaction_rate=round(rate, 1),
    )


@router.get("/feedback/recent")
@limiter.limit("20/minute")
async def get_recent_feedback(
    request: Request,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(require_role("admin")),
):
    """List recent feedback entries (admin only)."""
    db = get_database()

    cursor = (
        db.feedback.find()
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    items = await cursor.to_list(length=limit)
    for item in items:
        item["_id"] = str(item["_id"])

    return items
