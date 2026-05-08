"""Reference dictionaries — Faculty and Group.

These collections hold admin-curated lists from which users pick during
registration and admins pick when tagging documents. Storing IDs (not
strings) on users and documents means an admin can rename a group
later and every reference stays consistent automatically.

Group → Faculty is a hard FK relationship (every group belongs to one
faculty). The level field on Group narrows the choice down further so
a master-level student is not offered bachelor-only groups.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from bson import ObjectId
from pydantic import BaseModel, Field

from app.models.document import PyObjectId


class StudyLevel(str, Enum):
    bachelor = "bachelor"
    master = "master"
    phd = "phd"


# ---------------------------------------------------------------------------
# Faculty
# ---------------------------------------------------------------------------


class FacultyCreate(BaseModel):
    """Payload to create a faculty."""

    name: str = Field(..., min_length=1, max_length=200)


class FacultyUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


class FacultyInDB(BaseModel):
    """Faculty as stored in MongoDB."""

    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }


class FacultyResponse(BaseModel):
    """Public projection of a faculty."""

    id: str
    name: str
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------


class GroupCreate(BaseModel):
    """Payload to create a study group."""

    name: str = Field(..., min_length=1, max_length=100)
    faculty_id: str = Field(..., min_length=1)
    level: StudyLevel


class GroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    faculty_id: Optional[str] = Field(None, min_length=1)
    level: Optional[StudyLevel] = None


class GroupInDB(BaseModel):
    """Group as stored in MongoDB."""

    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    name: str
    faculty_id: PyObjectId
    level: StudyLevel
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }


class GroupResponse(BaseModel):
    """Public projection of a group, including the faculty name for display."""

    id: str
    name: str
    faculty_id: str
    faculty_name: Optional[str] = None
    level: StudyLevel
    created_at: datetime
    updated_at: datetime


def group_doc_to_response(
    doc: dict,
    faculty_name: Optional[str] = None,
) -> GroupResponse:
    """Build a GroupResponse from a MongoDB document.

    ``faculty_name`` is resolved by the caller (a single bulk lookup is
    cheaper than one query per group), and is optional because admin
    flows occasionally edit a group without needing the name back.
    """
    return GroupResponse(
        id=str(doc["_id"]),
        name=doc["name"],
        faculty_id=str(doc["faculty_id"]),
        faculty_name=faculty_name,
        level=StudyLevel(doc["level"]),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


def faculty_doc_to_response(doc: dict) -> FacultyResponse:
    return FacultyResponse(
        id=str(doc["_id"]),
        name=doc["name"],
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


__all__ = [
    "StudyLevel",
    "FacultyCreate",
    "FacultyUpdate",
    "FacultyInDB",
    "FacultyResponse",
    "GroupCreate",
    "GroupUpdate",
    "GroupInDB",
    "GroupResponse",
    "faculty_doc_to_response",
    "group_doc_to_response",
]
