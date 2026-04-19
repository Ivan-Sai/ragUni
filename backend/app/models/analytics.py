"""Analytics models for usage tracking."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AnalyticsEvent(BaseModel):
    """Single analytics event."""

    event_type: str
    user_id: str
    user_role: str
    metadata: dict = Field(default_factory=dict)
    timestamp: datetime


class DayCount(BaseModel):
    date: str
    count: int


class AnalyticsSummary(BaseModel):
    """Aggregated analytics for admin dashboard."""

    total_queries: int
    total_logins: int
    total_uploads: int
    queries_per_day: list[DayCount]
    active_users_per_day: list[DayCount]
    avg_response_time: Optional[float] = None
