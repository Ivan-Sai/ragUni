"""CRUD for the Faculty / Group reference collections.

Kept as a small service module so both the admin API endpoints and the
public registration endpoint share the same validation and rename
semantics. The store enforces:

* Faculty name uniqueness (case-insensitive).
* Group name uniqueness within a faculty.
* Group cannot exist without an existing faculty.
* Faculty deletion is blocked while any group or user still references
  it — clients must reassign or remove dependants first.
"""

from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from app.models.dictionary import (
    FacultyCreate,
    FacultyResponse,
    FacultyUpdate,
    GroupCreate,
    GroupResponse,
    GroupUpdate,
    StudyLevel,
    faculty_doc_to_response,
    group_doc_to_response,
)
from app.services.database import get_database


class DictionaryError(Exception):
    """Base error for dictionary CRUD."""


class NotFoundError(DictionaryError):
    pass


class DuplicateError(DictionaryError):
    pass


class InUseError(DictionaryError):
    pass


def _safe_oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, ValueError, TypeError) as exc:
        raise NotFoundError("Invalid identifier") from exc


# ---------------------------------------------------------------------------
# Faculty
# ---------------------------------------------------------------------------


async def list_faculties() -> list[FacultyResponse]:
    db = get_database()
    cursor = db.faculties.find({}).sort("name", ASCENDING)
    docs = await cursor.to_list(length=1000)
    return [faculty_doc_to_response(d) for d in docs]


async def get_faculty(faculty_id: str) -> FacultyResponse:
    db = get_database()
    doc = await db.faculties.find_one({"_id": _safe_oid(faculty_id)})
    if not doc:
        raise NotFoundError("Faculty not found")
    return faculty_doc_to_response(doc)


async def create_faculty(payload: FacultyCreate) -> FacultyResponse:
    db = get_database()
    now = datetime.now(timezone.utc)
    doc = {
        "name": payload.name.strip(),
        "name_lower": payload.name.strip().lower(),
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = await db.faculties.insert_one(doc)
    except DuplicateKeyError as exc:
        raise DuplicateError("Faculty with this name already exists") from exc
    doc["_id"] = result.inserted_id
    return faculty_doc_to_response(doc)


async def update_faculty(faculty_id: str, payload: FacultyUpdate) -> FacultyResponse:
    db = get_database()
    oid = _safe_oid(faculty_id)
    new_name = payload.name.strip()
    try:
        result = await db.faculties.find_one_and_update(
            {"_id": oid},
            {
                "$set": {
                    "name": new_name,
                    "name_lower": new_name.lower(),
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            return_document=True,
        )
    except DuplicateKeyError as exc:
        raise DuplicateError("Faculty with this name already exists") from exc
    if not result:
        raise NotFoundError("Faculty not found")
    return faculty_doc_to_response(result)


async def delete_faculty(faculty_id: str) -> None:
    """Refuse to delete a faculty that still has groups or users.

    The user is expected to re-target dependants first; cascading the
    delete silently would orphan student profiles and document tags.
    """
    db = get_database()
    oid = _safe_oid(faculty_id)
    if await db.groups.count_documents({"faculty_id": oid}, limit=1):
        raise InUseError("Faculty has groups and cannot be deleted")
    if await db.users.count_documents({"faculty_id": oid}, limit=1):
        raise InUseError("Faculty has users and cannot be deleted")
    result = await db.faculties.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise NotFoundError("Faculty not found")


# ---------------------------------------------------------------------------
# Group
# ---------------------------------------------------------------------------


async def _resolve_faculty_names(
    faculty_ids: list[ObjectId],
) -> dict[ObjectId, str]:
    if not faculty_ids:
        return {}
    db = get_database()
    cursor = db.faculties.find(
        {"_id": {"$in": list(set(faculty_ids))}},
        {"_id": 1, "name": 1},
    )
    return {doc["_id"]: doc["name"] async for doc in cursor}


async def list_groups(
    faculty_id: Optional[str] = None,
    level: Optional[StudyLevel] = None,
) -> list[GroupResponse]:
    db = get_database()
    filter_doc: dict = {}
    if faculty_id:
        filter_doc["faculty_id"] = _safe_oid(faculty_id)
    if level:
        filter_doc["level"] = level.value
    cursor = db.groups.find(filter_doc).sort("name", ASCENDING)
    docs = await cursor.to_list(length=2000)
    name_map = await _resolve_faculty_names([d["faculty_id"] for d in docs])
    return [group_doc_to_response(d, name_map.get(d["faculty_id"])) for d in docs]


async def get_group(group_id: str) -> GroupResponse:
    db = get_database()
    doc = await db.groups.find_one({"_id": _safe_oid(group_id)})
    if not doc:
        raise NotFoundError("Group not found")
    name_map = await _resolve_faculty_names([doc["faculty_id"]])
    return group_doc_to_response(doc, name_map.get(doc["faculty_id"]))


async def create_group(payload: GroupCreate) -> GroupResponse:
    db = get_database()
    faculty_oid = _safe_oid(payload.faculty_id)
    if not await db.faculties.find_one({"_id": faculty_oid}, {"_id": 1}):
        raise NotFoundError("Faculty not found")

    now = datetime.now(timezone.utc)
    doc = {
        "name": payload.name.strip(),
        "name_lower": payload.name.strip().lower(),
        "faculty_id": faculty_oid,
        "level": payload.level.value,
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = await db.groups.insert_one(doc)
    except DuplicateKeyError as exc:
        raise DuplicateError("Group with this name already exists in the faculty") from exc

    doc["_id"] = result.inserted_id
    name_map = await _resolve_faculty_names([faculty_oid])
    return group_doc_to_response(doc, name_map.get(faculty_oid))


async def update_group(group_id: str, payload: GroupUpdate) -> GroupResponse:
    db = get_database()
    oid = _safe_oid(group_id)

    update_fields: dict = {}
    if payload.name is not None:
        new_name = payload.name.strip()
        update_fields["name"] = new_name
        update_fields["name_lower"] = new_name.lower()
    if payload.faculty_id is not None:
        new_faculty = _safe_oid(payload.faculty_id)
        if not await db.faculties.find_one({"_id": new_faculty}, {"_id": 1}):
            raise NotFoundError("Faculty not found")
        update_fields["faculty_id"] = new_faculty
    if payload.level is not None:
        update_fields["level"] = payload.level.value
    if not update_fields:
        raise DictionaryError("No fields to update")
    update_fields["updated_at"] = datetime.now(timezone.utc)

    try:
        result = await db.groups.find_one_and_update(
            {"_id": oid},
            {"$set": update_fields},
            return_document=True,
        )
    except DuplicateKeyError as exc:
        raise DuplicateError("Group with this name already exists in the faculty") from exc
    if not result:
        raise NotFoundError("Group not found")
    name_map = await _resolve_faculty_names([result["faculty_id"]])
    return group_doc_to_response(result, name_map.get(result["faculty_id"]))


async def delete_group(group_id: str) -> None:
    """Refuse to delete a group that still has users or document tags."""
    db = get_database()
    oid = _safe_oid(group_id)
    if await db.users.count_documents({"group_id": oid}, limit=1):
        raise InUseError("Group has users and cannot be deleted")
    if await db.documents.count_documents({"target_group_ids": oid}, limit=1):
        raise InUseError("Group is referenced by documents and cannot be deleted")
    result = await db.groups.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise NotFoundError("Group not found")


__all__ = [
    "DictionaryError",
    "NotFoundError",
    "DuplicateError",
    "InUseError",
    "list_faculties",
    "get_faculty",
    "create_faculty",
    "update_faculty",
    "delete_faculty",
    "list_groups",
    "get_group",
    "create_group",
    "update_group",
    "delete_group",
]
