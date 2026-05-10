"""Unit tests for the query_analyzer LLM front-door.

The analyzer is the entry point of the RAG pipeline — every chat
request flows through it. Two failure modes have to be airtight:

1. **LLM responds with garbage / times out** — must fall back to the
   keyword-based analyzer instead of crashing the whole chain.
2. **Keyword fallback** — used both as the explicit fallback and in
   tests / dev when the LLM key is unavailable. Its day-of-week and
   intent classification on Ukrainian / English / Russian inputs
   must be deterministic.

These tests stub the LLM client itself rather than the network so
the assertions are stable regardless of Deepseek availability.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.services.query_analyzer import (
    QueryAnalysis,
    _coerce_analysis,
    _keyword_fallback_analysis,
    analyze_query,
)


# ---------------------------------------------------------------------------
# Keyword fallback
# ---------------------------------------------------------------------------


class TestKeywordFallback:
    """Pure-function path used when the LLM is unavailable."""

    @pytest.mark.parametrize(
        "question,day",
        [
            ("який у мене розклад на понеділок?", "понеділок"),
            ("розклад на вівторок", "вівторок"),
            ("середа", "середа"),
            ("schedule for friday", "п'ятниця"),
            ("у суботу є пари?", "субота"),
        ],
    )
    def test_detects_day_of_week(self, question, day):
        analysis = _keyword_fallback_analysis(question)
        assert analysis.entities.get("day_of_week") == day

    def test_classifies_schedule_intent(self):
        analysis = _keyword_fallback_analysis(
            "який у мене розклад на завтра?"
        )
        assert analysis.intent == "schedule_lookup"

    def test_classifies_exam_intent(self):
        analysis = _keyword_fallback_analysis("коли іспит з математики?")
        assert analysis.intent == "exam_dates"

    def test_personal_marker_set_for_first_person(self):
        analysis = _keyword_fallback_analysis("у мене сьогодні пара?")
        assert analysis.is_personal is True

    def test_unknown_query_returns_general_intent(self):
        analysis = _keyword_fallback_analysis(
            "What is the meaning of life?"
        )
        assert analysis.intent == "general"
        assert analysis.entities.get("day_of_week") is None


# ---------------------------------------------------------------------------
# Coerce — ensure malformed LLM JSON degrades to defaults instead of crashing
# ---------------------------------------------------------------------------


class TestCoerceAnalysis:
    """The LLM can return inventive shapes — the coercer must tolerate."""

    def test_empty_payload_returns_default(self):
        result = _coerce_analysis({})
        assert isinstance(result, QueryAnalysis)
        assert result.intent == "general"
        assert result.confidence == 0.0

    def test_unknown_intent_falls_back_to_general(self):
        result = _coerce_analysis({"intent": "made-up-intent"})
        assert result.intent == "general"

    def test_unknown_strategy_is_dropped(self):
        result = _coerce_analysis(
            {
                "intent": "schedule_lookup",
                "preferred_strategies": ["vector", "magic", "lexical"],
            }
        )
        assert "magic" not in result.preferred_strategies
        assert "vector" in result.preferred_strategies
        assert "lexical" in result.preferred_strategies

    def test_confidence_clamped(self):
        result = _coerce_analysis({"confidence": 5.0})
        assert 0.0 <= result.confidence <= 1.0


# ---------------------------------------------------------------------------
# analyze_query — async path with mocked LLM
# ---------------------------------------------------------------------------


class TestAnalyzeQuery:
    """End-to-end behaviour of the analyzer entry point."""

    @pytest.mark.asyncio
    async def test_llm_timeout_falls_back_to_keyword_analysis(self):
        # Make the LLM hang past the 12 s analyzer timeout — but
        # asyncio.wait_for() will surface TimeoutError and the
        # analyzer will return the keyword fallback.
        async def _hang(_messages):
            await asyncio.sleep(60)

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(side_effect=_hang)
        with patch(
            "app.services.query_analyzer._get_llm",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ):
            # The 12 s timeout would slow CI; patch wait_for to raise
            # immediately so we exercise the fallback branch without
            # actually waiting.
            with patch(
                "app.services.query_analyzer.asyncio.wait_for",
                new_callable=AsyncMock,
                side_effect=asyncio.TimeoutError(),
            ):
                analysis = await analyze_query(
                    "розклад на четвер?",
                    chat_history=None,
                )

        # Keyword fallback found "четвер" → day_of_week populated.
        assert analysis.entities.get("day_of_week") == "четвер"

    @pytest.mark.asyncio
    async def test_llm_garbage_response_falls_back_to_keyword(self):
        # The LLM "succeeds" but returns a response without parseable
        # JSON. The analyzer should swallow the ValueError raised by
        # _parse_json_payload and fall back to keyword analysis.
        bad_response = type("Resp", (), {"content": "I am sorry, I cannot help."})()

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=bad_response)
        with patch(
            "app.services.query_analyzer._get_llm",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ):
            analysis = await analyze_query(
                "розклад на вівторок?",
                chat_history=None,
            )

        assert analysis.entities.get("day_of_week") == "вівторок"

    @pytest.mark.asyncio
    async def test_llm_valid_response_round_trips(self):
        valid_payload = (
            '{"intent": "schedule_lookup", "confidence": 0.9, '
            '"is_personal": true, "entities": {"day_of_week": "п\'ятниця"}, '
            '"reformulated_query": "пари на пʼятницю", '
            '"preferred_strategies": ["structured", "vector"]}'
        )
        good_response = type("Resp", (), {"content": valid_payload})()

        mock_llm = AsyncMock()
        mock_llm.ainvoke = AsyncMock(return_value=good_response)
        with patch(
            "app.services.query_analyzer._get_llm",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ):
            analysis = await analyze_query("що у мене на пʼятницю?", chat_history=None)

        assert analysis.intent == "schedule_lookup"
        assert analysis.confidence == pytest.approx(0.9)
        assert analysis.is_personal is True
        assert analysis.entities.get("day_of_week") == "п'ятниця"
        assert "structured" in analysis.preferred_strategies
