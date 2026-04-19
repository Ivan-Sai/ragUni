"""Feedback models for answer quality tracking."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FeedbackType(str, Enum):
    thumbs_up = "thumbs_up"
    thumbs_down = "thumbs_down"


class FeedbackCreate(BaseModel):
    """Schema for submitting feedback on an assistant message."""

    session_id: str = Field(..., min_length=1)
    message_index: int = Field(..., ge=0)
    feedback_type: FeedbackType
    comment: Optional[str] = Field(None, max_length=500)


class FeedbackResponse(BaseModel):
    """Feedback record returned in API responses."""

    id: str
    session_id: str
    message_index: int
    feedback_type: FeedbackType
    comment: Optional[str] = None
    created_at: datetime


class FeedbackStats(BaseModel):
    """Aggregated feedback statistics."""

    total_feedback: int
    thumbs_up: int
    thumbs_down: int
    satisfaction_rate: float
