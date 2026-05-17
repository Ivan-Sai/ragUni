"""Unit tests for the structured-records audience + entity filters.

This is the highest-risk module from a leakage standpoint: a wrong
``and`` / ``or`` here would let user A's query return user B's
schedule. The tests pin the audience filter (``group``, ``year``,
``level``) and the entity filter (``day``, ``subject``, ``teacher``,
``room``) one constraint at a time so a regression in any of them
fails its own test.
"""

from __future__ import annotations

import pytest

from app.services.query_analyzer import QueryAnalysis
from app.services.structured_retriever import (
    _record_matches_audience,
    _record_matches_entities,
)


# ---------------------------------------------------------------------------
# Audience filter
# ---------------------------------------------------------------------------


class TestAudienceFilter:
    """Drops records whose group / year / level differ from the user."""

    def test_record_for_other_group_is_dropped(self):
        record = {"group": "ІКСМ", "year": 4, "level": "bachelor"}
        assert not _record_matches_audience(
            record,
            user_group_name="СА",
            user_year=4,
            user_level="bachelor",
        )

    def test_record_for_other_year_is_dropped(self):
        record = {"group": "СА", "year": 2, "level": "bachelor"}
        assert not _record_matches_audience(
            record,
            user_group_name="СА",
            user_year=4,
            user_level="bachelor",
        )

    def test_record_for_other_level_is_dropped(self):
        record = {"group": "СА", "year": 1, "level": "master"}
        assert not _record_matches_audience(
            record,
            user_group_name="СА",
            user_year=1,
            user_level="bachelor",
        )

    def test_matching_record_passes(self):
        record = {"group": "СА", "year": 4, "level": "bachelor"}
        assert _record_matches_audience(
            record,
            user_group_name="СА",
            user_year=4,
            user_level="bachelor",
        )

    def test_universal_group_label_passes_for_anyone(self):
        record = {"group": "усі групи", "year": 4, "level": "bachelor"}
        assert _record_matches_audience(
            record,
            user_group_name="СА",
            user_year=4,
            user_level="bachelor",
        )

    def test_record_without_group_passes(self):
        record = {"year": 4, "level": "bachelor"}
        assert _record_matches_audience(
            record,
            user_group_name="СА",
            user_year=4,
            user_level="bachelor",
        )

    def test_record_year_string_is_coerced(self):
        record = {"group": "СА", "year": "4", "level": "bachelor"}
        assert _record_matches_audience(
            record,
            user_group_name="СА",
            user_year=4,
            user_level="bachelor",
        )


# ---------------------------------------------------------------------------
# Entity filter — temporal
# ---------------------------------------------------------------------------


def _analysis(
    *,
    day: str | None = None,
    subject: str | None = None,
    teacher: str | None = None,
) -> QueryAnalysis:
    """Build a synthetic QueryAnalysis with one entity populated."""
    entities = {}
    if day:
        entities["day_of_week"] = day
    if subject:
        entities["subject"] = subject
    if teacher:
        entities["teacher"] = teacher
    return QueryAnalysis(
        intent="schedule_lookup",
        confidence=1.0,
        entities=entities,
    )


class TestEntityFilterTemporal:

    def test_day_match_passes(self):
        record = {"day": "вівторок", "subject": "Math"}
        analysis = _analysis(day="вівторок")
        assert _record_matches_entities(record, analysis=analysis)

    def test_day_mismatch_drops(self):
        record = {"day": "середа", "subject": "Math"}
        analysis = _analysis(day="вівторок")
        assert not _record_matches_entities(record, analysis=analysis)

    def test_record_without_day_drops_when_query_asks_for_day(self):
        # Critical: we must NOT serve a no-day record on a "what's
        # on Tuesday?" query — the LLM would falsely claim the
        # subject is on Tuesday.
        record = {"subject": "Math"}
        analysis = _analysis(day="вівторок")
        assert not _record_matches_entities(record, analysis=analysis)

    def test_friday_with_apostrophe_matches_canonical_record(self):
        # Regression: ``_normalise`` strips the apostrophe, so the
        # day-normaliser dict must be keyed on the normalised form.
        # Previously the dict had ``"п'ятниця"`` as key, but the
        # lookup applied ``_normalise`` to the input → ``"пятниця"``,
        # which was NOT in the dict → ``_canonical_day`` returned
        # ``None`` → no day filter applied → wrong-day records leaked.
        record = {"day": "п'ятниця", "subject": "Math"}
        for variant in ["п'ятниця", "П'ятниця", "П’ятниця", "пятница", "friday", "пт"]:
            analysis = _analysis(day=variant)
            assert _record_matches_entities(record, analysis=analysis), (
                f"Friday variant {variant!r} failed to match canonical record"
            )


# ---------------------------------------------------------------------------
# Entity filter — subject / teacher (fuzzy substring)
# ---------------------------------------------------------------------------


class TestEntityFilterSubjectTeacher:

    def test_subject_substring_match_passes(self):
        record = {"subject": "Програмування вбудованих систем"}
        analysis = _analysis(subject="програмування")
        assert _record_matches_entities(record, analysis=analysis)

    def test_subject_mismatch_drops(self):
        record = {"subject": "Математичний аналіз"}
        analysis = _analysis(subject="фізика")
        assert not _record_matches_entities(record, analysis=analysis)

    def test_teacher_substring_match_passes(self):
        record = {"teacher": "Бойко Юрій Володимирович"}
        analysis = _analysis(teacher="бойко")
        assert _record_matches_entities(record, analysis=analysis)

    def test_teacher_mismatch_drops(self):
        record = {"teacher": "Іваненко П.О."}
        analysis = _analysis(teacher="петренко")
        assert not _record_matches_entities(record, analysis=analysis)
