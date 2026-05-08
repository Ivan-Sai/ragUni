"""LLM-based structured-record extraction for complex tabular PDFs.

Some documents — class schedules, exam timetables, multi-page grade
sheets — survive ``pdfplumber`` extraction as garbled clusters of cell
fragments because their visual structure has no machine-readable
analogue (vertically-spelled days, multi-line cells, merged headers
across pages).  When the admin marks an upload as "complex schedule",
this module sends the raw extracted text to the configured chat LLM
with a strict instruction to emit a JSON array of self-contained
records.  Those records are then serialised into one-line statements
that embed cleanly and let RAG answer "коли іспит з X для групи Y"
without needing a vision model.

Costs roughly the same per document as a single chat answer (~$0.005
on Deepseek for ~15 KB of input). Time-bound to ``llm_timeout_seconds``
× 3 since structured generation tends to be slower than chat.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from langchain_openai import ChatOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# Dedicated LLM client for extraction — the chat-side singleton uses a
# 30 s request timeout which is too tight for structured generation on
# multi-thousand-char inputs. We allocate a separate client at 3× that
# budget and a much higher max-tokens cap so the JSON response can run
# to completion.
_EXTRACTION_TIMEOUT_S = max(120.0, float(settings.llm_timeout_seconds) * 3)
_extractor_llm: Optional[ChatOpenAI] = None
_extractor_lock = asyncio.Lock()


async def _get_extractor_llm() -> ChatOpenAI:
    global _extractor_llm
    if _extractor_llm is None:
        async with _extractor_lock:
            if _extractor_llm is None:
                _extractor_llm = ChatOpenAI(
                    model=settings.deepseek_model,
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_api_base,
                    temperature=0.0,
                    max_tokens=_MAX_COMPLETION_TOKENS,
                    request_timeout=_EXTRACTION_TIMEOUT_S,
                )
                logger.info(
                    "Extraction LLM initialised (timeout=%.0fs)",
                    _EXTRACTION_TIMEOUT_S,
                )
    return _extractor_llm

# Per-call input cap. ~7 KB on Ukrainian text fits in roughly 2.5K
# tokens, leaving room for a JSON response that's typically 2-3× the
# input size in characters. Larger documents are split into
# overlapping windows so no record is dropped at a boundary.
#
# Why so small: structured JSON output for dense schedules expands
# the response heavily — every cell becomes ``"key": "value", ``.
# A 14 KB schedule produces ~30 KB of JSON which would overflow even
# the 8K-token completion cap. Keeping windows small keeps each
# response well below the cap so JSON arrays close cleanly.
_MAX_INPUT_CHARS = 7_500
_WINDOW_OVERLAP_CHARS = 800

# Hard cap on the output. Deepseek-chat max_tokens ceiling is 8192;
# we set 8000 to stay within budget and let JSON arrays close.
_MAX_COMPLETION_TOKENS = 8_000

EXTRACTION_SYSTEM_PROMPT = """You are a structured-data extractor for Ukrainian university documents.

The user message contains text extracted from a PDF — typically a class schedule, exam timetable, credit list, or curriculum table whose visual structure has been lost during extraction.

Identify every distinct record (one row of the original table) and output a JSON array. Each element is a self-contained dictionary describing one record.

Use these conventional shapes when applicable, but invent fields if the document needs them:

* Class slot:
  {"type": "class", "group": "СА", "year": 4, "level": "bachelor", "day": "понеділок", "time": "8:40-9:25", "subject": "Розробка інтерфейсів користувача", "teacher": "...", "room": "ауд. 38", "lesson_kind": "лаб."}

* Exam:
  {"type": "exam", "group": "КСМ", "year": 1, "level": "master", "subject": "...", "consultation_date": "13.05.2026", "consultation_time": "12:00", "consultation_room": "ауд. 8", "exam_date": "14.05.2026", "exam_time": "10:00", "exam_room": "ауд. 8", "teacher": "..."}

* Credit / залік:
  {"type": "credit", "group": "БМФІІ", "year": 2, "level": "master", "subject": "Семінар з медичної фізики", "date": "13.05.2026", "time": "12:20", "room": "ауд. 37", "teacher": "доц. Нетреба А.В."}

Rules:
1. Output ONLY the JSON array. No prose, no markdown code fences, no commentary.
2. Preserve Ukrainian text exactly as it appears in the source.
3. Skip decorative rows (column headers, group names that span the full row, blank rows).
4. Time formatting: ALWAYS use ``HH:MM`` with a colon, e.g. ``8:40-9:25``. Never ``0840-0925``. If a single record covers two consecutive pair slots, write the merged range like ``8:40-10:15`` rather than two ranges glued together.
5. Group field: every record MUST have a ``group`` value naming the cohort (the cell label, e.g. ``ІКСМ``, ``МА``, ``СА``, ``КСМ``, ``МІ``, ``СІ``). DO NOT append the year to the group name — keep the group identifier and the year strictly separate. If the slot applies to all groups on that level (e.g. ``самостійна робота``), set ``"group": "усі групи"`` and emit ONE record.
6. Year field: every record MUST have an integer ``year`` (1-6) inferred from the column header above the cell ("1 бакалавр" → 1, "2 бакалавр" → 2, "1 магістр" → 1, etc.). Magister and PhD years restart at 1.
7. Level field: every record MUST have ``level``: one of ``"bachelor"``, ``"master"``, ``"phd"``. Inferred from the same parent header — "бакалавр" → bachelor, "магістр" → master, "аспірант"/"PhD" → phd. NEVER use Ukrainian words for this field, only the three English values above.
8. If a value is genuinely unknown, use null — do NOT invent. But group / year / level are almost always inferable from the table structure, so try hard before falling back to null.
9. Be exhaustive: every meaningful row in the source must be one record.
10. If the document is not a table at all, return [] (empty array).
"""


class LLMExtractionError(RuntimeError):
    """Raised when the LLM response cannot be parsed into records."""


async def extract_structured_records(
    raw_text: str,
    *,
    filename: str = "",
) -> list[dict[str, Any]]:
    """Drive the LLM extraction and return a list of record dicts.

    Returns an empty list if extraction fails — callers must treat
    that as "fall back to raw text" rather than as an error, so this
    function never raises.
    """
    if not raw_text or not raw_text.strip():
        return []

    windows = list(_split_into_windows(raw_text))
    logger.info(
        "LLM extraction (%s): %d window(s), total %d chars (parallel)",
        filename or "<unnamed>",
        len(windows),
        len(raw_text),
    )

    # Each window is independent — run them concurrently. Sequential
    # extraction on a 3-window document used to take 3-5 minutes (one
    # round-trip to Deepseek per window); ``asyncio.gather`` collapses
    # that to one round-trip's worth of latency, ~30-90 s.
    async def _safe_extract(idx: int, window: str) -> list[dict[str, Any]]:
        try:
            return await _extract_window(window, filename=filename, index=idx)
        except (LLMExtractionError, asyncio.TimeoutError) as exc:
            logger.warning(
                "LLM extraction window %d/%d failed: %s",
                idx,
                len(windows),
                exc,
            )
            return []

    results = await asyncio.gather(
        *[_safe_extract(i, w) for i, w in enumerate(windows, 1)]
    )
    all_records: list[dict[str, Any]] = [r for batch in results for r in batch]

    logger.info(
        "LLM extraction (%s): produced %d total records",
        filename or "<unnamed>",
        len(all_records),
    )
    return all_records


def format_records_as_text(records: list[dict[str, Any]]) -> str:
    """Render extracted records as one block per record, separated by
    blank lines. The resulting text is intentionally newline-rich so
    ``RecursiveCharacterTextSplitter`` cuts cleanly between records and
    each chunk contains a small whole number of fully-described items.
    """
    if not records:
        return ""

    blocks: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        rendered = _render_record(record)
        if rendered:
            blocks.append(rendered)

    return "\n\n".join(blocks)


def records_as_chunks(records: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """Render every extracted record as its own ``(text, metadata)`` chunk.

    Used by the upload pipeline when ``use_llm_extraction=True``: each
    record becomes one vector-store entry, so the chunk's audience
    metadata can be derived from the record itself (group, level,
    record_type) instead of the document-wide tags the admin set on
    upload. This is the foundation of per-row hard-filtering.

    The metadata returned here is the **per-record** payload only —
    the caller merges document-level fields (faculty_id, source_file,
    document_id, etc.) on top.
    """
    chunks: list[tuple[str, dict[str, Any]]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        rendered = _render_record(record)
        if not rendered:
            continue

        meta: dict[str, Any] = {}

        # Group: LLM emits the source label verbatim ("ІКСМ", "СА",
        # "усі групи", ...). The caller resolves the label against the
        # faculty's groups dictionary; here we just preserve it so the
        # mapping step has something to work with.
        group_value = record.get("group")
        if isinstance(group_value, str) and group_value.strip():
            meta["group_label"] = group_value.strip()

        # Year: an integer 1-6 inferred from the column header. We
        # tolerate the LLM emitting it as a string and coerce to int
        # so the upload pipeline can plug it straight into target_years.
        year_value = record.get("year")
        if isinstance(year_value, int) and 1 <= year_value <= 6:
            meta["year_label"] = year_value
        elif isinstance(year_value, str) and year_value.strip().isdigit():
            year_int = int(year_value.strip())
            if 1 <= year_int <= 6:
                meta["year_label"] = year_int

        # Level: one of "bachelor" / "master" / "phd" — the prompt
        # forces the canonical English form. Anything else is dropped
        # so the document-level default applies.
        level_value = record.get("level")
        if isinstance(level_value, str):
            normalised = level_value.strip().lower()
            if normalised in {"bachelor", "master", "phd"}:
                meta["level_label"] = normalised

        if record.get("type"):
            meta["record_type"] = str(record["type"])

        chunks.append((rendered, meta))
    return chunks


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _split_into_windows(text: str) -> list[str]:
    """Slice ``text`` into overlapping windows of at most _MAX_INPUT_CHARS.

    A small overlap keeps records that straddle a boundary intact; the
    LLM emits each record once because the system prompt is set up to
    deduplicate by content.
    """
    if len(text) <= _MAX_INPUT_CHARS:
        return [text]

    step = _MAX_INPUT_CHARS - _WINDOW_OVERLAP_CHARS
    windows: list[str] = []
    cursor = 0
    while cursor < len(text):
        windows.append(text[cursor : cursor + _MAX_INPUT_CHARS])
        cursor += step
    return windows


async def _extract_window(
    window: str,
    *,
    filename: str,
    index: int,
    max_retries: int = 2,
) -> list[dict[str, Any]]:
    """Run the LLM on one window, retrying on parse failures.

    Long-context Deepseek calls occasionally return malformed JSON
    (truncation, code-fence markers, prose preamble). When that
    happens we retry with a shorter, more assertive prompt that
    explicitly demands a raw array. Each retry is a fresh LLM call
    — the model behaves differently with a different conversation
    history. After ``max_retries`` we surface the failure so the
    caller can move on to the next window without crashing.
    """
    llm = await _get_extractor_llm()

    base_user_prompt = (
        f"Document filename hint: {filename or 'unknown'}\n"
        f"Window: {index}\n\n"
        f"Source text:\n{window}"
    )

    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        if attempt == 1:
            user_prompt = base_user_prompt
        else:
            user_prompt = (
                base_user_prompt
                + "\n\n[RETRY: previous response was not a valid JSON array. "
                "Output ONLY the JSON array — no markdown fences, no "
                "explanation. Start with '[' and end with ']'. Empty "
                "documents return [].]"
            )

        response = await asyncio.wait_for(
            llm.ainvoke(
                [
                    ("system", EXTRACTION_SYSTEM_PROMPT),
                    ("human", user_prompt),
                ]
            ),
            timeout=_EXTRACTION_TIMEOUT_S + 10,
        )
        content = getattr(response, "content", None) or str(response)

        try:
            json_text = _extract_json_array(content)
            parsed = json.loads(json_text)
        except (LLMExtractionError, json.JSONDecodeError) as exc:
            last_error = exc
            logger.warning(
                "LLM extraction window %d attempt %d/%d failed: %s",
                index,
                attempt,
                max_retries,
                exc,
            )
            continue

        if not isinstance(parsed, list):
            last_error = LLMExtractionError("LLM response was not a JSON array")
            continue

        return [r for r in parsed if isinstance(r, dict)]

    raise LLMExtractionError(
        f"Window {index} failed after {max_retries} attempts: {last_error}"
    )


def _extract_json_array(text: str) -> str:
    """Pull the outermost ``[...]`` block out of an LLM reply.

    The system prompt asks for raw JSON but models occasionally wrap
    the output in markdown code fences or prefix it with prose like
    "Here is the extracted data:". Anchoring on the first ``[`` and
    the matching final ``]`` handles both cases without a strict
    parser.
    """
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end < start:
        raise LLMExtractionError("LLM response contains no JSON array")
    return text[start : end + 1]


def _render_record(record: dict[str, Any]) -> str:
    """Format one record as a short paragraph suitable for embedding.

    Keys come first in a stable, readable order: ``type`` heads the
    block, then identifying fields (group / level / subject), then
    the temporal coordinates, then the room and people. Unrecognised
    keys are kept after the standard ones in their original order.
    """
    if not record:
        return ""

    preferred_order = (
        "type",
        "level",
        "course",
        "group",
        "subject",
        "lesson_kind",
        "day",
        "date",
        "exam_date",
        "consultation_date",
        "time",
        "exam_time",
        "consultation_time",
        "room",
        "exam_room",
        "consultation_room",
        "teacher",
    )
    seen: set[str] = set()
    parts: list[str] = []
    for key in preferred_order:
        if key in record and record[key] not in (None, ""):
            seen.add(key)
            parts.append(f"{key}: {record[key]}")
    for key, value in record.items():
        if key in seen or value in (None, ""):
            continue
        parts.append(f"{key}: {value}")

    return "; ".join(parts)
