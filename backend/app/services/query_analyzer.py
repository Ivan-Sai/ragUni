"""LLM-driven query analyzer — the front door of the RAG pipeline.

Why this exists
===============

Keyword routers are brittle: they miss synonyms, mishandle negation,
and require constant maintenance as the corpus grows. State-of-the-art
RAG systems (OpenAI Assistants v2, Anthropic tool_use, Glean, Perplexity
Spaces) replace them with a small, fast LLM call that returns a
**structured analysis** of the user's intent. Downstream code reacts to
that analysis instead of pattern-matching the raw query.

This module is generic on purpose. It doesn't know about schedules,
exams, or any particular domain — it returns a free-form ``intent``
string and an ``entities`` dict that the orchestrator interprets.
Adding a new query type (course catalog, room booking, syllabus
lookup) requires zero changes here; just teach the orchestrator how
to react to the new intent.

Output schema
-------------

::

    {
      "intent": "schedule_lookup" | "exam_dates" | "person_lookup"
              | "concept_explanation" | "document_search" | "general",
      "confidence": 0.0..1.0,
      "is_personal": bool,            // does it refer to the user's own data?
      "entities": {
        "day_of_week":  str | null,   // canonical Ukrainian day name
        "date_range":   str | null,   // e.g. "2026-05-13" or "next week"
        "time":         str | null,
        "subject":      str | null,
        "teacher":      str | null,
        "room":         str | null,
        "record_type":  list[str] | null,  // ["exam"], ["class","lab"], ...
      },
      "reformulated_query": str,      // self-contained, pronoun-resolved
      "preferred_strategies": ["structured", "vector", "lexical"]
    }

Reformulated query lets us power query expansion / HyDE without a
second LLM round-trip. Preferred strategies let the orchestrator skip
expensive paths when the LLM is highly confident the answer lives in
exactly one source (e.g. ``["structured"]`` for ``"коли іспит з X?"``).

Cost / latency
--------------

One Deepseek call at temperature=0, max_tokens=350. ~200-500ms.
Result is cached per (question, history-tail-hash) so multi-turn
follow-ups share the same analysis where possible.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------


_KNOWN_INTENTS: set[str] = {
    "schedule_lookup",
    "exam_dates",
    "person_lookup",
    "concept_explanation",
    "document_search",
    "general",
}

_KNOWN_STRATEGIES: set[str] = {"structured", "vector", "lexical"}


@dataclass
class QueryAnalysis:
    """Structured understanding of one chat turn."""

    intent: str = "general"
    confidence: float = 0.0
    is_personal: bool = False
    entities: dict[str, Any] = field(default_factory=dict)
    reformulated_query: str = ""
    preferred_strategies: list[str] = field(default_factory=list)
    # Document types the analyzer thinks the answer lives in. Empty
    # list = no preference (search across all types). Used by the
    # retrieval orchestrator to filter candidate chunks via the
    # ``doc_type`` metadata field that the upload pipeline now
    # writes for every document.
    target_doc_types: list[str] = field(default_factory=list)
    raw: Optional[dict[str, Any]] = None  # debug / observability

    @property
    def needs_structured(self) -> bool:
        """Does this query benefit from a structured-data lookup?"""
        return (
            "structured" in self.preferred_strategies
            or self.intent in {"schedule_lookup", "exam_dates", "person_lookup"}
            or any(self.entities.values())
        )

    @property
    def has_temporal_constraint(self) -> bool:
        """Whether the query mentions a day / date / time. Used by the
        structured retriever to decide if it's safe to drop records
        that lack a ``day`` field."""
        return any(
            self.entities.get(key)
            for key in ("day_of_week", "date_range", "time")
        )


# ---------------------------------------------------------------------------
# LLM client (lazy singleton)
# ---------------------------------------------------------------------------


_analyzer_llm: Optional[ChatOpenAI] = None
_analyzer_lock = asyncio.Lock()


async def _get_llm() -> ChatOpenAI:
    """The analyzer uses temperature=0 deterministic decoding so the
    same query produces the same plan across requests. We allocate a
    dedicated client (rather than reusing the chat LLM) because the
    chat LLM may be bound with caller overrides we don't want here.
    """
    global _analyzer_llm
    if _analyzer_llm is None:
        async with _analyzer_lock:
            if _analyzer_llm is None:
                _analyzer_llm = ChatOpenAI(
                    model=settings.deepseek_model,
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_api_base,
                    temperature=0.0,
                    max_tokens=300,
                    # Tighter than the chat LLM — analyzer output is a
                    # tiny JSON blob and we'd rather time out fast and
                    # fall back to vector-only than block the whole
                    # chat pipeline behind a slow Deepseek round-trip.
                    request_timeout=10.0,
                )
                logger.info("Query analyzer LLM initialised")
    return _analyzer_llm


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


_SYSTEM_PROMPT = """You are a query analyzer for a university RAG system. Given a user question (Ukrainian, Russian, or English), output a single JSON object that tells the retrieval engine how to answer it.

Output ONLY the JSON, no markdown fences, no commentary.

JSON schema:
{
  "intent": "schedule_lookup" | "exam_dates" | "person_lookup" | "concept_explanation" | "document_search" | "general",
  "confidence": 0.0..1.0,
  "is_personal": boolean,
  "entities": {
    "day_of_week":  "понеділок"|"вівторок"|"середа"|"четвер"|"п'ятниця"|"субота"|"неділя"|null,
    "date_range":   string|null,
    "time":         string|null,
    "subject":      string|null,
    "teacher":      string|null,
    "room":         string|null,
    "record_type":  ["class"|"exam"|"credit"|"consultation"|"lab"|"lecture"]|null
  },
  "reformulated_query": string,
  "preferred_strategies": ["structured"|"vector"|"lexical"],
  "target_doc_types": ["schedule"|"exam_protocol"|"regulation"|"curriculum"|"prose"|"tabular"]
}

Rules:

1. INTENT
   - schedule_lookup: weekly classes, "розклад", "пара", "коли заняття"
   - exam_dates: exams, credits, consultations, "іспит", "залік", "сесія"
   - person_lookup: contact / role of a teacher, dean, etc.
   - concept_explanation: "що таке X", "поясни Y", "розкажи про Z"
   - document_search: "знайди документ про", "де я можу прочитати"
   - general: anything else / unclear

2. CONFIDENCE: 0.9+ when the query unambiguously fits one intent. 0.5 when it could be two. < 0.5 when unclear.

3. IS_PERSONAL: true when the query references the user's own data — pronouns ("мій", "у мене", "my", "у нас"), implicit context ("коли іспит" = "коли мій іспит"), or asking for personal schedule/grades. False for generic factual questions.

4. ENTITIES: extract only values that appear (or are clearly implied) in the query. Day names go in canonical Ukrainian form even if user wrote them in Russian/English. Subject / teacher / room: copy verbatim from the query without translation. record_type: derive from intent + verbs ("складати залік" → ["credit"]). Set null when not mentioned.

5. REFORMULATED_QUERY: rewrite the original question as a self-contained, profile-agnostic sentence in Ukrainian. Resolve pronouns. Expand abbreviations. This goes into the embedder, so words matter.

6. PREFERRED_STRATEGIES: in priority order.
   - "structured" first when entities contain at least one of {day_of_week, date_range, time, subject, teacher, room, record_type}.
   - "vector" first for concept_explanation / document_search.
   - "lexical" added when the query mentions a specific name, number, or quoted phrase.
   Always include at least one strategy.

7. TARGET_DOC_TYPES: which document types the answer most likely lives in. Empty list = search everywhere.
   - schedule_lookup → ["schedule"]
   - exam_dates → ["exam_protocol", "schedule"]
   - person_lookup → ["schedule", "curriculum", "regulation"] (teachers can appear in any of these)
   - concept_explanation → ["curriculum", "prose"]
   - document_search → [] (search everywhere)
   - "Як перевестися на іншу спеціальність?" / policy questions → ["regulation"]
   - "Що таке МПЛ / робоча програма" → ["curriculum"]
   - When unsure, return [] rather than guessing — the retrieval falls back to all types.

Examples:

Q: "какое у меня роспписание в четверг?"
A: {"intent":"schedule_lookup","confidence":0.95,"is_personal":true,"entities":{"day_of_week":"четвер","date_range":null,"time":null,"subject":null,"teacher":null,"room":null,"record_type":["class"]},"reformulated_query":"розклад занять студента у четвер","preferred_strategies":["structured","vector"]}

Q: "коли іспит з математичної логіки?"
A: {"intent":"exam_dates","confidence":0.92,"is_personal":true,"entities":{"day_of_week":null,"date_range":null,"time":null,"subject":"математична логіка","teacher":null,"room":null,"record_type":["exam"]},"reformulated_query":"дата іспиту з математичної логіки","preferred_strategies":["structured","vector"]}

Q: "хто веде комп'ютерну схемотехніку?"
A: {"intent":"person_lookup","confidence":0.85,"is_personal":false,"entities":{"day_of_week":null,"date_range":null,"time":null,"subject":"комп'ютерна схемотехніка","teacher":null,"room":null,"record_type":null},"reformulated_query":"викладач курсу комп'ютерної схемотехніки","preferred_strategies":["structured","vector"]}

Q: "що таке нейронна мережа?"
A: {"intent":"concept_explanation","confidence":0.97,"is_personal":false,"entities":{"day_of_week":null,"date_range":null,"time":null,"subject":null,"teacher":null,"room":null,"record_type":null},"reformulated_query":"визначення нейронної мережі","preferred_strategies":["vector","lexical"]}

Q: "розкажи більше"
A: {"intent":"general","confidence":0.3,"is_personal":false,"entities":{"day_of_week":null,"date_range":null,"time":null,"subject":null,"teacher":null,"room":null,"record_type":null},"reformulated_query":"розкажи більше про попередню тему","preferred_strategies":["vector"]}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_JSON_OBJECT_RE = re.compile(r"\{.*\}", flags=re.DOTALL)


async def analyze_query(
    question: str,
    chat_history: Optional[list[dict[str, Any]]] = None,
) -> QueryAnalysis:
    """Run the analyzer LLM and return a parsed analysis.

    Falls back to a permissive ``general`` analysis on any error
    (timeout, JSON parse failure, model returns garbage). The chain
    must remain answer-capable even if the analyzer is down.
    """
    user_prompt = _build_user_prompt(question, chat_history)
    try:
        llm = await _get_llm()
        response = await asyncio.wait_for(
            llm.ainvoke([("system", _SYSTEM_PROMPT), ("human", user_prompt)]),
            timeout=12.0,
        )
        content = getattr(response, "content", None) or str(response)
        parsed = _parse_json_payload(content)
        analysis = _coerce_analysis(parsed)
        analysis.raw = parsed
        logger.info(
            "Query analysis: intent=%s conf=%.2f personal=%s strategies=%s entities=%s",
            analysis.intent,
            analysis.confidence,
            analysis.is_personal,
            analysis.preferred_strategies,
            {k: v for k, v in analysis.entities.items() if v},
        )
        return analysis
    except asyncio.TimeoutError:
        logger.warning("Query analyzer timed out, falling back to keyword analysis")
    except (ValueError, RuntimeError, OSError) as exc:
        logger.warning(
            "Query analyzer failed (%s), falling back to keyword analysis", exc
        )

    return _keyword_fallback_analysis(question)


# ---------------------------------------------------------------------------
# Keyword fallback (used when the LLM analyzer is unavailable or slow)
# ---------------------------------------------------------------------------


_DAY_PATTERNS: dict[str, str] = {
    r"\bпонеділок\w*\b|\bпонедельн\w+\b|\bmonday\b": "понеділок",
    r"\bвівторок\w*\b|\bвторник\w*\b|\btuesday\b": "вівторок",
    r"\bсереда\w*\b|\bсреду?\w*\b|\bwednesday\b": "середа",
    r"\bчетвер\w*\b|\bthursday\b": "четвер",
    r"\bп'?ятниц\w*\b|\bпятниц\w*\b|\bfriday\b": "п'ятниця",
    r"\bсубот\w*\b|\bsaturday\b": "субота",
    r"\bнеділ\w*\b|\bвоскресенье\b|\bsunday\b": "неділя",
}

_SCHEDULE_KEYWORDS = (
    "розклад", "расписание", "schedule",
    "пара", "пары", "пари", "lecture",
    "заняття", "занятие", "class",
    "лекці", "лекци",
)

_EXAM_KEYWORDS = (
    "іспит", "экзамен", "exam",
    "залік", "зачет", "credit",
    "сесі", "session",
    "консульта", "consultation",
)

_PERSONAL_KEYWORDS = (
    "мій", "моя", "моє", "мої", "у мене",
    "мой", "моя", "моё", "мои", "у меня",
    "my", "i have", "we have", "у нас",
)


def _keyword_fallback_analysis(question: str) -> QueryAnalysis:
    """Tiny regex-driven analyzer used when the LLM call fails.

    The contract with the rest of the pipeline is identical to the
    LLM path: we return a ``QueryAnalysis`` that drives structured
    retrieval. The regex coverage is deliberately tight — only the
    common Ukrainian / Russian / English signals we have data on —
    so a false positive cannot fabricate entities the user did not
    actually mention.
    """
    text = question.lower()
    entities: dict[str, Any] = {}

    # Day-of-week detection.
    for pattern, canonical in _DAY_PATTERNS.items():
        if re.search(pattern, text, flags=re.IGNORECASE | re.UNICODE):
            entities["day_of_week"] = canonical
            break

    is_schedule = any(kw in text for kw in _SCHEDULE_KEYWORDS)
    is_exam = any(kw in text for kw in _EXAM_KEYWORDS)
    is_personal = any(kw in text for kw in _PERSONAL_KEYWORDS)

    if is_exam:
        intent = "exam_dates"
        target_doc_types = ["exam_protocol", "schedule"]
        entities["record_type"] = ["exam", "credit", "consultation"]
    elif is_schedule or "day_of_week" in entities:
        intent = "schedule_lookup"
        target_doc_types = ["schedule"]
        entities.setdefault("record_type", ["class"])
    else:
        intent = "general"
        target_doc_types = []

    strategies = ["structured", "vector"] if entities else ["vector"]

    return QueryAnalysis(
        intent=intent,
        confidence=0.6 if entities else 0.3,
        is_personal=is_personal or "day_of_week" in entities,
        entities=entities,
        reformulated_query=question,
        preferred_strategies=strategies,
        target_doc_types=target_doc_types,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _build_user_prompt(
    question: str,
    chat_history: Optional[list[dict[str, Any]]],
) -> str:
    """Pack the question + the last few turns into a small prompt.

    History is included only when the question itself is short or
    pronoun-heavy; otherwise the analyzer can resolve everything from
    the question alone and we save tokens.
    """
    if not chat_history or len(question) > 30:
        return question
    tail = chat_history[-4:]
    rendered = "\n".join(
        f"{('user' if m.get('role') == 'user' else 'assistant')}: {m.get('content', '')[:300]}"
        for m in tail
    )
    return f"Recent dialogue:\n{rendered}\n\nCurrent question: {question}"


def _parse_json_payload(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of an LLM response.

    The system prompt asks for raw JSON but models occasionally wrap
    it in markdown fences or prepend prose; the regex finds the first
    ``{...}`` block, which is good enough.
    """
    text = text.strip()
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        raise ValueError("analyzer returned no JSON object")
    return json.loads(match.group(0))


def _coerce_analysis(payload: dict[str, Any]) -> QueryAnalysis:
    """Validate and normalise the LLM payload, keeping defaults.

    Unknown intents collapse to ``general`` rather than raising — the
    rest of the pipeline degrades gracefully under that fallback.
    """
    raw_intent = str(payload.get("intent", "")).strip().lower()
    intent = raw_intent if raw_intent in _KNOWN_INTENTS else "general"

    confidence = payload.get("confidence", 0.0)
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence = 0.0

    is_personal = bool(payload.get("is_personal", False))

    entities_raw = payload.get("entities") or {}
    if not isinstance(entities_raw, dict):
        entities_raw = {}
    entities: dict[str, Any] = {}
    for key in (
        "day_of_week", "date_range", "time", "subject",
        "teacher", "room", "record_type",
    ):
        value = entities_raw.get(key)
        if value in (None, "", []):
            continue
        if key == "record_type" and isinstance(value, list):
            entities[key] = [str(v).strip().lower() for v in value if v]
        else:
            entities[key] = str(value).strip()

    reformulated = str(payload.get("reformulated_query") or "").strip()

    strategies_raw = payload.get("preferred_strategies") or []
    if isinstance(strategies_raw, str):
        strategies_raw = [strategies_raw]
    strategies = [
        s for s in (str(x).strip().lower() for x in strategies_raw)
        if s in _KNOWN_STRATEGIES
    ]
    if not strategies:
        strategies = ["vector"]

    doc_types_raw = payload.get("target_doc_types") or []
    if isinstance(doc_types_raw, str):
        doc_types_raw = [doc_types_raw]
    target_doc_types = [
        t for t in (str(x).strip().lower() for x in doc_types_raw)
        if t in {
            "schedule", "exam_protocol", "regulation",
            "curriculum", "prose", "tabular",
        }
    ]

    return QueryAnalysis(
        intent=intent,
        confidence=confidence,
        is_personal=is_personal,
        entities=entities,
        reformulated_query=reformulated,
        preferred_strategies=strategies,
        target_doc_types=target_doc_types,
    )


__all__ = ["QueryAnalysis", "analyze_query"]
