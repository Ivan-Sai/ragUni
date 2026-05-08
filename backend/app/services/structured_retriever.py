"""Structured-record retrieval driven by ``QueryAnalysis``.

Why this exists
===============

When the query analyzer extracts entities (day, subject, teacher,
room…), we can answer the question with a deterministic database
query instead of a stochastic vector search. The vector store is the
right tool for "explain X"; a Mongo lookup over
``documents.structured_records`` is the right tool for
"on Thursday at 10:35 in audience 38".

This module is **entity-driven**: it doesn't care which intent the
analyzer assigned, only which entities were extracted and which
audience filters apply to the calling user. As a result, adding a
new structured query type (e.g. *"who teaches X?"* → ``person_lookup``)
requires no code changes here as long as the analyzer fills in the
right entities.

Audience filtering
------------------

Every record is filtered against the user's profile before being
returned. Records that explicitly target a different group / year /
level are dropped; records with no constraint ("усі групи", missing
fields) pass through. This mirrors the access-control rules in
``vector_store.build_access_filter`` so structured retrieval cannot
expose data vector retrieval would refuse.

Quality safeguards
------------------

* When the query has a temporal constraint (``has_temporal_constraint``
  on ``QueryAnalysis``), we drop records lacking a ``day``/``date``
  field. The previous keyword router kept day-less records for
  *"Thursday"*, which leaked self-study slots into the answer.
* Subject / teacher matching is fuzzy: case-insensitive substring on
  normalised text. The LLM emits these verbatim from the source, so
  exact equality would miss obvious matches like
  ``"матлогіка"`` vs ``"математична логіка"``.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Optional

from bson import ObjectId

from app.services.database import get_database
from app.services.query_analyzer import QueryAnalysis

logger = logging.getLogger(__name__)


_NORMALISE_RE = re.compile(r"[^\w]+", flags=re.UNICODE)


def _normalise(value: Any) -> str:
    """Lowercase + strip non-word chars for forgiving comparison.

    NFKD-normalises so visually-equivalent Unicode encodings (e.g.
    pre-composed vs combining accents) compare equal.
    """
    if value is None:
        return ""
    folded = unicodedata.normalize("NFKD", str(value))
    return _NORMALISE_RE.sub("", folded).lower()


_DAY_NORMALISERS: dict[str, str] = {
    "понеділок": "понеділок", "понедельник": "понеділок", "monday": "понеділок", "пн": "понеділок",
    "вівторок": "вівторок", "вторник": "вівторок", "tuesday": "вівторок", "вт": "вівторок",
    "середа": "середа", "среда": "середа", "wednesday": "середа", "ср": "середа",
    "четвер": "четвер", "четверг": "четвер", "thursday": "четвер", "чт": "четвер",
    "п'ятниця": "п'ятниця", "пятница": "п'ятниця", "friday": "п'ятниця", "пт": "п'ятниця",
    "субота": "субота", "суббота": "субота", "saturday": "субота", "сб": "субота",
    "неділя": "неділя", "воскресенье": "неділя", "sunday": "неділя", "вс": "неділя",
}


def _canonical_day(value: Any) -> Optional[str]:
    """Map any day-of-week variant to its canonical Ukrainian form.

    Returns None when the value is empty or unrecognised; the caller
    treats that as "no day constraint", not "match nothing".
    """
    if not value:
        return None
    return _DAY_NORMALISERS.get(_normalise(value))


# ---------------------------------------------------------------------------
# Audience matching
# ---------------------------------------------------------------------------


_UNIVERSAL_GROUP_LABELS = {
    "усігрупи", "усіхгруп", "усіх", "всі", "всех", "all", "allgroups",
}


def _record_matches_audience(
    record: dict[str, Any],
    *,
    user_group_name: Optional[str],
    user_year: Optional[int],
    user_level: Optional[str],
) -> bool:
    """Return True iff the record belongs to the calling user's audience.

    A record's ``group`` is treated as "for everyone" when it equals
    one of ``_UNIVERSAL_GROUP_LABELS`` or is missing entirely. The
    ``year`` and ``level`` checks are exact when the record carries a
    value, no-op when it doesn't.
    """
    rec_group = record.get("group")
    if rec_group:
        rec_group_norm = _normalise(rec_group)
        if rec_group_norm not in _UNIVERSAL_GROUP_LABELS:
            if not user_group_name or _normalise(user_group_name) != rec_group_norm:
                return False

    rec_year = record.get("year")
    if isinstance(rec_year, str) and rec_year.strip().isdigit():
        rec_year = int(rec_year.strip())
    if isinstance(rec_year, int):
        if user_year is None or rec_year != user_year:
            return False

    rec_level = record.get("level")
    if isinstance(rec_level, str):
        rec_level_norm = rec_level.strip().lower()
        if rec_level_norm in {"bachelor", "master", "phd"}:
            if not user_level or rec_level_norm != user_level.lower():
                return False

    return True


# ---------------------------------------------------------------------------
# Entity matching
# ---------------------------------------------------------------------------


def _record_matches_entities(
    record: dict[str, Any],
    *,
    analysis: QueryAnalysis,
) -> bool:
    """Apply the entity filters extracted by the analyzer.

    Each entity is independent: a constraint is checked only when the
    analyzer produced a non-empty value for it, AND the record carries
    a value to compare against. Missing record fields fail the check
    only for *temporal* entities (day/date/time) — for everything else
    we can't tell, so we keep the record.
    """
    entities = analysis.entities

    # ---- Temporal --------------------------------------------------------
    target_day = _canonical_day(entities.get("day_of_week"))
    if target_day:
        rec_day = _canonical_day(record.get("day"))
        if rec_day:
            if rec_day != target_day:
                return False
        elif analysis.has_temporal_constraint:
            # The query asked about a specific day, but this record
            # does not carry a day field at all. Without a day we
            # cannot honestly say it applies to Thursday — reject so
            # the LLM does not claim it does.
            return False

    target_date = (entities.get("date_range") or "").strip()
    if target_date:
        rec_date_fields = (
            record.get("date"),
            record.get("exam_date"),
            record.get("consultation_date"),
        )
        if any(rec_date_fields):
            target_norm = _normalise(target_date)
            if not any(_normalise(d) and target_norm in _normalise(d) for d in rec_date_fields):
                return False

    # ---- Subject (fuzzy substring) --------------------------------------
    target_subject = entities.get("subject")
    if target_subject:
        rec_subject = record.get("subject")
        if rec_subject:
            target_norm = _normalise(target_subject)
            rec_norm = _normalise(rec_subject)
            if target_norm not in rec_norm and rec_norm not in target_norm:
                return False

    # ---- Teacher (fuzzy substring on surname) ----------------------------
    target_teacher = entities.get("teacher")
    if target_teacher:
        rec_teacher = record.get("teacher")
        if rec_teacher:
            target_norm = _normalise(target_teacher)
            rec_norm = _normalise(rec_teacher)
            if target_norm not in rec_norm and rec_norm not in target_norm:
                return False

    # ---- Room ------------------------------------------------------------
    target_room = entities.get("room")
    if target_room:
        rec_rooms = (
            record.get("room"),
            record.get("exam_room"),
            record.get("consultation_room"),
        )
        if any(rec_rooms):
            target_norm = _normalise(target_room)
            if not any(_normalise(r) and target_norm in _normalise(r) for r in rec_rooms):
                return False

    # ---- Record type -----------------------------------------------------
    target_types = entities.get("record_type")
    if isinstance(target_types, list) and target_types:
        rec_type = (record.get("type") or "").strip().lower()
        if rec_type and rec_type not in target_types:
            return False

    return True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def fetch_structured_records(
    analysis: QueryAnalysis,
    *,
    user_role: str,
    user_faculty_id: Optional[str],
    user_group_id: Optional[str],
    user_year: Optional[int],
    user_level: Optional[str],
    max_documents: int = 50,
    max_records_per_document: int = 500,
    hard_cap: int = 80,
) -> list[dict[str, Any]]:
    """Run a structured query and return matching records.

    Returns an empty list whenever the analysis carries no entities
    OR no record survived filtering. The orchestrator treats an empty
    result as "fall through to vector" so the user is never stuck with
    silence.
    """
    if not analysis.needs_structured:
        return []

    db = get_database()

    # Resolve the user's group label so it can be compared against
    # record.group strings inside structured_records.
    user_group_name: Optional[str] = None
    if user_group_id:
        try:
            grp = await db.groups.find_one(
                {"_id": ObjectId(user_group_id)}, {"name": 1}
            )
            if grp:
                user_group_name = grp.get("name")
        except (ValueError, TypeError):
            logger.warning("Invalid user_group_id passed to structured retriever")

    access_filter = _build_document_access_filter(user_role, user_faculty_id)

    filter_doc: dict[str, Any] = {
        "extraction_method": "llm",
        "structured_records_count": {"$gt": 0},
    }
    if access_filter:
        filter_doc = {"$and": [access_filter, filter_doc]}

    cursor = db.documents.find(
        filter_doc,
        {"structured_records": 1, "filename": 1},
    ).limit(max_documents)

    matched: list[dict[str, Any]] = []
    async for doc in cursor:
        records = doc.get("structured_records") or []
        for record in records[:max_records_per_document]:
            if not isinstance(record, dict):
                continue
            if not _record_matches_audience(
                record,
                user_group_name=user_group_name,
                user_year=user_year,
                user_level=user_level,
            ):
                continue
            if not _record_matches_entities(record, analysis=analysis):
                continue
            matched.append({**record, "_source_file": doc.get("filename", "")})
            if len(matched) >= hard_cap:
                logger.info(
                    "Structured retrieval hard cap (%d) reached, stopping",
                    hard_cap,
                )
                return matched

    logger.info(
        "Structured retrieval: intent=%s entities=%s -> %d records",
        analysis.intent,
        {k: v for k, v in analysis.entities.items() if v},
        len(matched),
    )
    return matched


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_document_access_filter(
    user_role: str,
    user_faculty_id: Optional[str],
) -> dict[str, Any]:
    """Mirror the access rules of vector_store.build_access_filter so
    structured retrieval can never surface a document the user could
    not reach via vector search.
    """
    if user_role == "admin":
        return {}

    if user_role == "teacher":
        conditions: list[dict] = [
            {"access_level": "public"},
            {"access_level": "restricted"},
        ]
        if user_faculty_id:
            conditions.append(
                {"$and": [{"access_level": "faculty"},
                          {"faculty_id": ObjectId(user_faculty_id)}]}
            )
        return {"$or": conditions}

    student_conditions: list[dict] = [{"access_level": "public"}]
    if user_faculty_id:
        student_conditions.append(
            {"$and": [{"access_level": "faculty"},
                      {"faculty_id": ObjectId(user_faculty_id)}]}
        )
    return {"$or": student_conditions}


# ---------------------------------------------------------------------------
# Context formatting (LLM input)
# ---------------------------------------------------------------------------


_PREFERRED_KEYS = (
    "type", "level", "course", "year", "group",
    "subject", "lesson_kind",
    "day", "date", "exam_date", "consultation_date",
    "time", "exam_time", "consultation_time",
    "room", "exam_room", "consultation_room",
    "teacher",
)


def _render_record(record: dict[str, Any]) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for key in _PREFERRED_KEYS:
        if key in record and record[key] not in (None, ""):
            seen.add(key)
            parts.append(f"{key}: {record[key]}")
    for key, value in record.items():
        if key in seen or key.startswith("_") or value in (None, ""):
            continue
        parts.append(f"{key}: {value}")
    return "; ".join(parts)


def format_records_as_context(records: list[dict[str, Any]]) -> str:
    """Render the matched records as numbered ``[Джерело N]`` blocks.

    The numbering matches the citations the prompt asks the LLM to
    emit, so the UI can resolve ``[3]`` markers in the answer to a
    specific record card.
    """
    blocks: list[str] = []
    for index, record in enumerate(records, 1):
        source = record.get("_source_file") or "structured-record"
        body = _render_record(record)
        if not body:
            continue
        blocks.append(f"[Джерело {index}: {source}, structured record {index}]\n{body}")
    return "\n\n---\n\n".join(blocks)


__all__ = ["fetch_structured_records", "format_records_as_context"]
