"""Analytics service for tracking usage events."""

import logging
from datetime import datetime, timedelta, timezone

from app.services.database import get_database

logger = logging.getLogger(__name__)


async def track_event(
    event_type: str,
    user_id: str,
    user_role: str,
    metadata: dict | None = None,
) -> None:
    """Record an analytics event. Fire-and-forget — errors are logged, not raised."""
    try:
        db = get_database()
        await db.analytics_events.insert_one(
            {
                "event_type": event_type,
                "user_id": user_id,
                "user_role": user_role,
                "metadata": metadata or {},
                "timestamp": datetime.now(timezone.utc),
            }
        )
    except RuntimeError:
        logger.debug("Analytics: database not available, skipping event")
    except Exception:
        logger.warning("Analytics: failed to track event %s", event_type, exc_info=True)


async def get_summary(days: int = 30) -> dict:
    """Get aggregated analytics summary for the last N days."""
    db = get_database()
    since = datetime.now(timezone.utc) - timedelta(days=days)

    # Total counts
    total_queries = await db.analytics_events.count_documents(
        {"event_type": "chat_query", "timestamp": {"$gte": since}}
    )
    total_logins = await db.analytics_events.count_documents(
        {"event_type": "login", "timestamp": {"$gte": since}}
    )
    total_uploads = await db.analytics_events.count_documents(
        {"event_type": "document_upload", "timestamp": {"$gte": since}}
    )

    # Queries per day
    queries_per_day = await db.analytics_events.aggregate(
        [
            {"$match": {"event_type": "chat_query", "timestamp": {"$gte": since}}},
            {
                "$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
            {"$project": {"date": "$_id", "count": 1, "_id": 0}},
        ]
    ).to_list(length=days)

    # Active users per day
    active_users_per_day = await db.analytics_events.aggregate(
        [
            {"$match": {"timestamp": {"$gte": since}}},
            {
                "$group": {
                    "_id": {
                        "date": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}},
                        "user_id": "$user_id",
                    },
                }
            },
            {"$group": {"_id": "$_id.date", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}},
            {"$project": {"date": "$_id", "count": 1, "_id": 0}},
        ]
    ).to_list(length=days)

    # Average response time
    avg_pipeline = await db.analytics_events.aggregate(
        [
            {
                "$match": {
                    "event_type": "chat_query",
                    "timestamp": {"$gte": since},
                    "metadata.response_time": {"$exists": True},
                }
            },
            {"$group": {"_id": None, "avg": {"$avg": "$metadata.response_time"}}},
        ]
    ).to_list(length=1)

    avg_response_time = round(avg_pipeline[0]["avg"], 2) if avg_pipeline else None

    return {
        "total_queries": total_queries,
        "total_logins": total_logins,
        "total_uploads": total_uploads,
        "queries_per_day": queries_per_day,
        "active_users_per_day": active_users_per_day,
        "avg_response_time": avg_response_time,
    }
