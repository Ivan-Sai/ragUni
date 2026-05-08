"""Faculty / Group dictionary API.

* Read endpoints are open to any authenticated user — needed during
  registration and in the document upload form.
* Write endpoints (create / update / delete) are admin-only.

The router is mounted under ``/api/v1/dictionaries`` in ``main.py``.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.dependencies import get_current_user, require_role
from app.core.rate_limit import limiter
from app.models.dictionary import (
    FacultyCreate,
    FacultyResponse,
    FacultyUpdate,
    GroupCreate,
    GroupResponse,
    GroupUpdate,
    StudyLevel,
)
from app.services import dictionary as dict_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Dictionaries"])

admin_only = require_role("admin")


# ---------------------------------------------------------------------------
# Faculty endpoints
# ---------------------------------------------------------------------------


@router.get("/faculties", response_model=list[FacultyResponse])
async def list_faculties(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[FacultyResponse]:
    """List all faculties — visible to any authenticated user."""
    return await dict_service.list_faculties()


@router.get("/faculties/public", response_model=list[FacultyResponse])
async def list_faculties_public() -> list[FacultyResponse]:
    """Public read used during registration before a user has a token."""
    return await dict_service.list_faculties()


@router.post(
    "/faculties",
    response_model=FacultyResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def create_faculty(
    request: Request,
    payload: FacultyCreate,
    current_user: dict[str, Any] = Depends(admin_only),
) -> FacultyResponse:
    try:
        return await dict_service.create_faculty(payload)
    except dict_service.DuplicateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.put("/faculties/{faculty_id}", response_model=FacultyResponse)
@limiter.limit("30/minute")
async def update_faculty(
    request: Request,
    faculty_id: str,
    payload: FacultyUpdate,
    current_user: dict[str, Any] = Depends(admin_only),
) -> FacultyResponse:
    try:
        return await dict_service.update_faculty(faculty_id, payload)
    except dict_service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except dict_service.DuplicateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.delete(
    "/faculties/{faculty_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit("30/minute")
async def delete_faculty(
    request: Request,
    faculty_id: str,
    current_user: dict[str, Any] = Depends(admin_only),
) -> None:
    try:
        await dict_service.delete_faculty(faculty_id)
    except dict_service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except dict_service.InUseError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


# ---------------------------------------------------------------------------
# Group endpoints
# ---------------------------------------------------------------------------


@router.get("/groups", response_model=list[GroupResponse])
async def list_groups(
    faculty_id: str | None = Query(None),
    level: StudyLevel | None = Query(None),
    current_user: dict[str, Any] = Depends(get_current_user),
) -> list[GroupResponse]:
    """List groups, optionally filtered by faculty and study level."""
    return await dict_service.list_groups(faculty_id=faculty_id, level=level)


@router.get("/groups/public", response_model=list[GroupResponse])
async def list_groups_public(
    faculty_id: str | None = Query(None),
    level: StudyLevel | None = Query(None),
) -> list[GroupResponse]:
    """Public list used during registration before a user has a token."""
    return await dict_service.list_groups(faculty_id=faculty_id, level=level)


@router.post(
    "/groups",
    response_model=GroupResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("30/minute")
async def create_group(
    request: Request,
    payload: GroupCreate,
    current_user: dict[str, Any] = Depends(admin_only),
) -> GroupResponse:
    try:
        return await dict_service.create_group(payload)
    except dict_service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except dict_service.DuplicateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))


@router.put("/groups/{group_id}", response_model=GroupResponse)
@limiter.limit("30/minute")
async def update_group(
    request: Request,
    group_id: str,
    payload: GroupUpdate,
    current_user: dict[str, Any] = Depends(admin_only),
) -> GroupResponse:
    try:
        return await dict_service.update_group(group_id, payload)
    except dict_service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except dict_service.DuplicateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    except dict_service.DictionaryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.delete(
    "/groups/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
@limiter.limit("30/minute")
async def delete_group(
    request: Request,
    group_id: str,
    current_user: dict[str, Any] = Depends(admin_only),
) -> None:
    try:
        await dict_service.delete_group(group_id)
    except dict_service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except dict_service.InUseError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
