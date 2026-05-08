"""LLM-driven document type classifier.

Why this exists
===============

A single one-size-fits-all extraction prompt cannot handle the
diversity of documents a university dumps into the knowledge base:
class schedules, exam protocols, regulations, syllabi, lecture
notes, announcements. Each type has its own structure, its own
relevant fields, and its own optimal chunking strategy. Sending a
regulation through the schedule-row extractor produces an empty
``structured_records`` array; sending a schedule through a
"semantic chunker for prose" loses the row-level addressing that
makes timetable retrieval work.

This module runs ONCE at upload time. It looks at the first ~6 KB
of the extracted text and asks the LLM to label the document as
one of a fixed set of types. The label drives everything
downstream: which extractor to use, which chunker to apply, which
metadata to attach, and (later) which retriever path the query
analyser will prefer.

Output
------

Returned ``DocumentClassification`` is intentionally narrow — the
type is an enum-like string, plus a confidence score and a free-
form ``reasoning`` field for observability. Adding a new type
requires updating this module and registering an extractor; the
rest of the pipeline degrades gracefully (unknown type → "prose"
fallback path) so partial rollouts of new types are safe.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from langchain_openai import ChatOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Type registry
# ---------------------------------------------------------------------------


# The vocabulary of document types we know how to handle. New types
# must be added here AND have a matching entry in
# ``services.extractor_registry`` before the classifier can route to
# them; until then the classifier still emits the type label, but
# the extractor falls back to the prose handler.
KNOWN_DOC_TYPES = (
    "schedule",         # weekly class timetable
    "exam_protocol",    # exam / credit / consultation dates
    "regulation",       # policy documents, procedures, rules
    "curriculum",       # course catalogues, syllabi, programmes
    "prose",            # lecture notes, articles, announcements
    "tabular",          # generic tables (grade lists, attendance)
    "unknown",          # could not classify with confidence
)


@dataclass
class DocumentClassification:
    """Label assigned to a document at upload time."""

    doc_type: str
    confidence: float
    reasoning: str = ""

    @property
    def is_known(self) -> bool:
        return self.doc_type in KNOWN_DOC_TYPES and self.doc_type != "unknown"


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------


_classifier_llm: Optional[ChatOpenAI] = None
_classifier_lock = asyncio.Lock()


async def _get_llm() -> ChatOpenAI:
    """Dedicated low-temperature client. Classification is purely a
    routing decision — sampling diversity would actively hurt."""
    global _classifier_llm
    if _classifier_llm is None:
        async with _classifier_lock:
            if _classifier_llm is None:
                _classifier_llm = ChatOpenAI(
                    model=settings.deepseek_model,
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_api_base,
                    temperature=0.0,
                    max_tokens=200,
                    request_timeout=20.0,
                )
                logger.info("Document classifier LLM initialised")
    return _classifier_llm


_SYSTEM_PROMPT = """You classify Ukrainian university documents into one of a fixed set of types so the RAG pipeline can pick the right extractor and chunker.

Output ONLY a JSON object, no markdown, no commentary.

Schema:
{
  "doc_type": "schedule" | "exam_protocol" | "regulation" | "curriculum" | "prose" | "tabular" | "unknown",
  "confidence": 0.0..1.0,
  "reasoning": "one short sentence"
}

Type definitions:

- schedule: weekly class timetable (rows = time slots, columns = groups, cells = subject + teacher + room). Keywords: "Розклад занять", day-of-week labels, time slots like "8:40-9:25".
- exam_protocol: exam / credit / consultation dates. Keywords: "Графік сесії", "Іспит", "Залік", "Консультація", explicit dates with "ауд."
- regulation: policy documents, procedures, internal rules. Keywords: "Положення про…", "Порядок", "Правила", numbered sections, no time slots, no per-group rows.
- curriculum: course catalogues, syllabi, learning outcomes. Keywords: "Робоча програма", "Силабус", "Освітня програма", "Кредити ЄКТС", learning outcomes / topics enumerations.
- prose: lecture notes, articles, announcements, free-form text without strong structure.
- tabular: a generic table that doesn't fit any of the above (grade lists, attendance, contact directories).
- unknown: cannot determine with reasonable confidence.

Rules:

1. If the text contains tables WITH day-of-week labels OR time-slot rows → schedule.
2. If the text mentions exam / credit dates without a weekly grid → exam_protocol.
3. Numbered sections + words like "затверджено", "наказ", "положення" → regulation.
4. "Дисципліна:", "програмні результати навчання", "змістовий модуль" → curriculum.
5. Plain paragraphs of running text → prose.
6. Mostly tables with no other context → tabular.
7. When two rules apply, pick the more specific one (schedule beats tabular).

Confidence guide:
- 0.9+: the document fits one type unambiguously.
- 0.5-0.7: borderline (e.g. a syllabus that contains a small schedule grid).
- < 0.5: emit "unknown" instead of guessing.

Examples:

DOCUMENT: "Розклад занять студентів факультету радіофізики на 2 семестр... понеділок 8:40-9:25 ІКСМ 1 Дядищева-Росовецька..."
A: {"doc_type":"schedule","confidence":0.97,"reasoning":"Weekly grid with day labels and time slots"}

DOCUMENT: "Графік сесії магістрів... 13.05.2026 12:00 консультація ауд. 8, 14.05.2026 10:00 іспит з квантової механіки..."
A: {"doc_type":"exam_protocol","confidence":0.93,"reasoning":"Explicit exam/consultation dates without weekly grid"}

DOCUMENT: "Положення про порядок переведення студентів... 1. Загальні положення 1.1 Це Положення визначає порядок..."
A: {"doc_type":"regulation","confidence":0.95,"reasoning":"Numbered sections of policy text"}

DOCUMENT: "Робоча програма дисципліни Машинне навчання. Змістовий модуль 1: Лінійні моделі. Програмні результати навчання..."
A: {"doc_type":"curriculum","confidence":0.92,"reasoning":"Course syllabus with modules and learning outcomes"}

DOCUMENT: "Лекція 5: Принципи побудови нейронних мереж. Перцептрон є базовою одиницею..."
A: {"doc_type":"prose","confidence":0.88,"reasoning":"Free-form lecture text"}
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_JSON_OBJECT_RE = re.compile(r"\{.*\}", flags=re.DOTALL)
_HEAD_CHARS = 6000  # how much of the document we send to the classifier


async def classify_document(
    extracted_text: str,
    filename: str = "",
) -> DocumentClassification:
    """Classify a document and return its type label.

    The classifier sees the first ~6 KB of the extracted text plus
    the filename — enough signal for a clean call without exploding
    cost. Falls back to ``unknown`` on any LLM error so the upload
    pipeline can still proceed (the prose extractor is a safe
    default for unclassified documents).
    """
    if not extracted_text or not extracted_text.strip():
        return DocumentClassification(doc_type="unknown", confidence=0.0)

    head = extracted_text[:_HEAD_CHARS].strip()
    user_prompt = (
        f"Filename: {filename or '(unknown)'}\n\n"
        f"Document head ({len(head)} chars):\n{head}"
    )

    try:
        llm = await _get_llm()
        response = await asyncio.wait_for(
            llm.ainvoke(
                [("system", _SYSTEM_PROMPT), ("human", user_prompt)],
            ),
            timeout=25.0,
        )
        content = getattr(response, "content", None) or str(response)
        parsed = _parse_json(content)
        result = _coerce_classification(parsed)
        logger.info(
            "Document classified: %s (conf=%.2f) %s",
            result.doc_type,
            result.confidence,
            filename or "<unnamed>",
        )
        return result
    except asyncio.TimeoutError:
        logger.warning("Classifier timed out for %s", filename or "<unnamed>")
    except (ValueError, RuntimeError, OSError) as exc:
        logger.warning(
            "Classifier failed for %s: %s",
            filename or "<unnamed>",
            exc,
        )

    return DocumentClassification(
        doc_type="unknown",
        confidence=0.0,
        reasoning="classifier unavailable",
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _parse_json(text: str) -> dict:
    match = _JSON_OBJECT_RE.search(text.strip())
    if not match:
        raise ValueError("classifier returned no JSON object")
    return json.loads(match.group(0))


def _coerce_classification(payload: dict) -> DocumentClassification:
    raw_type = str(payload.get("doc_type", "")).strip().lower()
    if raw_type not in KNOWN_DOC_TYPES:
        raw_type = "unknown"
    try:
        confidence = max(0.0, min(1.0, float(payload.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    reasoning = str(payload.get("reasoning") or "").strip()[:300]
    return DocumentClassification(
        doc_type=raw_type,
        confidence=confidence,
        reasoning=reasoning,
    )


__all__ = ["DocumentClassification", "KNOWN_DOC_TYPES", "classify_document"]
