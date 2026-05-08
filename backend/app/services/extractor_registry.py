"""Type-specific extractors and chunkers — universal document pipeline.

Why this exists
===============

Class schedules, regulations, syllabi, lecture notes and grade
spreadsheets are all *technically* PDFs, but they share almost
nothing structurally. A timetable wants row-by-row LLM extraction
into ``{day, time, group, subject, teacher, room}`` records; a
regulation wants to stay as natural language but be split at
``Стаття 1.``, ``Пункт 1.1`` boundaries; a lecture note wants
semantic chunks with overlap and an Anthropic-style document
context line prepended for embedding accuracy.

This module is a registry. The classifier picks a ``doc_type`` and
this module hands out the matching ``Extractor`` implementation,
each producing the same output shape (``ExtractionResult``) so the
upload endpoint can stay extractor-agnostic.

Adding a new type means writing one new ``Extractor`` subclass and
adding it to ``_REGISTRY`` — no changes elsewhere.

Output contract
---------------

Every extractor returns an ``ExtractionResult``:

* ``chunks`` — list of ``(text, metadata)`` pairs ready to embed.
  ``text`` is the embedding payload (already prefixed with
  document-context where applicable). ``metadata`` is the per-chunk
  payload that lands in MongoDB and powers retrieval filters.
* ``records`` — optional structured records for the
  ``documents.structured_records`` field. Empty for prose-style
  extractors that don't produce row-level data.
* ``method`` — short identifier for observability and document-list
  badges in the admin UI.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from langchain_openai import ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config import get_settings
from app.services.llm_extractor import (
    extract_structured_records,
    records_as_chunks,
)

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Output type
# ---------------------------------------------------------------------------


@dataclass
class ExtractionResult:
    """Output of one extractor run.

    Attributes
    ----------
    chunks
        ``(text, metadata)`` pairs to feed into the vector store.
        ``text`` already carries any document-context prefix.
    records
        Optional structured records — only populated by row-style
        extractors (schedule, exam_protocol).
    method
        Short tag for observability ("schedule_llm", "regulation_llm",
        "prose_recursive", …). Stored on the document record so the
        admin UI can label how each document was processed.
    """

    chunks: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)
    method: str = ""


# ---------------------------------------------------------------------------
# Anthropic Contextual Retrieval
# ---------------------------------------------------------------------------

# Generated lazily so the LLM client is created only when an extractor
# actually needs it. Cached for the life of the process.
_context_llm: Optional[ChatOpenAI] = None
_context_lock = asyncio.Lock()


async def _get_context_llm() -> ChatOpenAI:
    global _context_llm
    if _context_llm is None:
        async with _context_lock:
            if _context_llm is None:
                _context_llm = ChatOpenAI(
                    model=settings.deepseek_model,
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_api_base,
                    temperature=0.0,
                    max_tokens=120,
                    request_timeout=15.0,
                )
                logger.info("Contextual-retrieval LLM initialised")
    return _context_llm


async def generate_document_context(
    full_text: str,
    *,
    filename: str,
    doc_type: str,
    max_chars: int = 4000,
) -> str:
    """Anthropic Contextual Retrieval (Sept 2024).

    The LLM produces ONE short sentence that situates each chunk
    within the wider document. Prepending that sentence to the chunk
    before embedding has been measured at ~35 % retrieval-accuracy
    uplift across mixed-corpus benchmarks (Anthropic blog post
    "Introducing Contextual Retrieval", 19 Sep 2024).

    We compute the context **once per document**, not per chunk, and
    cache the result on the document record. This trades a tiny bit
    of accuracy (some chunks gain less from a global summary than a
    chunk-specific one) for an order-of-magnitude lower cost — one
    LLM call instead of one per chunk.

    Returns an empty string on any LLM failure; the caller then
    skips prefixing and the pipeline still works (just without the
    accuracy uplift).
    """
    if not full_text.strip():
        return ""

    head = full_text[:max_chars].strip()
    prompt = (
        "You are summarising a Ukrainian university document so that any "
        "chunk of it can be retrieved with the right context.\n\n"
        f"Filename: {filename}\n"
        f"Document type: {doc_type}\n\n"
        f"Document head:\n{head}\n\n"
        "Write ONE sentence (≤ 30 Ukrainian words) describing what this "
        "document is about — the audience, the academic period if any, "
        "and the high-level subject. No introduction, no markdown, just "
        "the sentence."
    )
    try:
        llm = await _get_context_llm()
        response = await asyncio.wait_for(
            llm.ainvoke([("human", prompt)]),
            timeout=15.0,
        )
        content = (getattr(response, "content", None) or str(response)).strip()
        # Some models emit "Sentence:" or quotes; strip them.
        content = re.sub(r"^['\"\s:]+|['\"\s]+$", "", content)
        if len(content) > 280:
            content = content[:280].rstrip() + "…"
        logger.info("Document context generated: %s", content[:120])
        return content
    except asyncio.TimeoutError:
        logger.warning("Document-context generation timed out for %s", filename)
    except (ValueError, RuntimeError, OSError) as exc:
        logger.warning(
            "Document-context generation failed for %s: %s", filename, exc
        )
    return ""


# ---------------------------------------------------------------------------
# Extractor base + implementations
# ---------------------------------------------------------------------------


class Extractor(ABC):
    """Strategy interface. One subclass per ``doc_type``."""

    method: str = "abstract"

    @abstractmethod
    async def extract(
        self,
        *,
        text: str,
        filename: str,
        document_context: str,
    ) -> ExtractionResult:
        """Produce chunks (and optional records) from ``text``.

        ``document_context`` is the cached one-liner from
        ``generate_document_context``. Implementations may prepend it
        to each chunk before embedding (Anthropic Contextual
        Retrieval) or ignore it for row-style chunks where the
        context comes from the row's structured fields.
        """


class _ScheduleExtractor(Extractor):
    """Hybrid schedule extractor.

    Strategy:

    1. **Deterministic per-column attribution**: ``schedule_table_parser``
       inspects each pdfplumber 2-D table, identifies the
       column→group mapping from the header band, and emits one
       ``CellEvent`` per (group, day, time) slot. Group / year /
       level / day / time are guaranteed correct because they come
       from the table structure, not from LLM column-counting.
    2. **Per-cell LLM refinement**: each cell's free-form text
       (teacher + subject + room + lesson_kind, smushed together by
       pdfplumber) is sent through a tiny LLM call that splits it
       into ``{teacher, subject, room, lesson_kind}``. This is a
       *much* easier task than 'identify column from this 12-cell
       wide row of mixed content', and parses one cell at a time.
    3. **Fallback**: when the parser cannot identify the table
       structure (rare layouts, scanned PDFs), we fall back to the
       legacy LLM-only extractor.

    Field tests on the ФРЕКС schedule went from 11 СА(4) records
    (with мasters / wrong groups mixed in) to one record per
    real cell — column attribution is now perfect.
    """

    method = "schedule_deterministic"

    def __init__(self, file_content_provider=None):
        # Set by the upload endpoint via ``set_file_content`` so the
        # extractor can call back into pdfplumber on the same bytes.
        # We keep this off the public interface — only schedule
        # extraction needs the raw PDF, the others operate on text.
        self._file_content_provider = file_content_provider

    def set_file_content(self, file_bytes: bytes) -> None:
        self._file_bytes = file_bytes

    async def extract(
        self,
        *,
        text: str,
        filename: str,
        document_context: str,
    ) -> ExtractionResult:
        # Try the deterministic parser first.
        cells: list = []
        if hasattr(self, "_file_bytes") and self._file_bytes:
            from app.services.document_parser import DocumentParser

            cells = await DocumentParser.extract_schedule_cells(self._file_bytes)

        if cells:
            records = await _refine_cells_with_llm(cells, filename=filename)
            if records:
                pairs = records_as_chunks(records)
                prefixed: list[tuple[str, dict[str, Any]]] = []
                for body, meta in pairs:
                    content = (
                        f"{document_context}\n\n{body}"
                        if document_context
                        else body
                    )
                    prefixed.append((content, meta))
                return ExtractionResult(
                    chunks=prefixed,
                    records=records,
                    method=self.method,
                )

        # Fallback: LLM-only extraction on the markdown text.
        logger.info(
            "Schedule extractor: deterministic path empty, falling back to LLM-only"
        )
        records = await extract_structured_records(text, filename=filename)
        if not records:
            return ExtractionResult(method="schedule_llm_fallback")

        pairs = records_as_chunks(records)
        prefixed: list[tuple[str, dict[str, Any]]] = []
        for body, meta in pairs:
            content = (
                f"{document_context}\n\n{body}" if document_context else body
            )
            prefixed.append((content, meta))
        return ExtractionResult(
            chunks=prefixed,
            records=records,
            method="schedule_llm_fallback",
        )


# ---------------------------------------------------------------------------
# Per-cell LLM refinement
# ---------------------------------------------------------------------------


_REFINEMENT_BATCH_SIZE = 25
_REFINEMENT_TIMEOUT_S = 60.0


def _cell_to_minimal_record(cell) -> dict[str, Any]:
    """Fallback when the LLM cannot refine a cell — keep the raw
    text as the subject so the data is still searchable."""
    return {
        "type": "class",
        "day": cell.day,
        "time": cell.time,
        "group": cell.group,
        "year": cell.year,
        "level": cell.level,
        "subject": cell.raw_text,
    }


async def _refine_one_batch(
    batch_cells: list,
    batch_offset: int,
) -> list[dict[str, Any]]:
    """Refine a small batch of cells with one LLM call.

    On any failure (timeout, network error, malformed JSON) we
    return minimal records with the raw cell text as the subject,
    so the user always sees their schedule data even when Deepseek
    is unreachable. Catching ``Exception`` is intentional — the
    upstream stack throws ``openai.APITimeoutError`` /
    ``APIConnectionError`` etc. which don't share a common base
    class with the standard library exceptions, and we never want
    a transient API hiccup to take down the whole upload.
    """
    items = [
        {"id": idx, "text": cell.raw_text}
        for idx, cell in enumerate(batch_cells)
    ]
    prompt = (
        "You receive a JSON array of university-schedule CELL TEXTS. Each cell "
        "describes ONE class slot's teacher / subject / room / lesson kind, "
        "smushed together by the PDF parser.\n\n"
        "For each cell, output a JSON object with:\n"
        "  id (int, copied)\n"
        "  subject (string, the course name)\n"
        "  teacher (string|null, surname + initials if present)\n"
        "  room (string|null, audience number / cabinet, e.g. 'ауд.45', 'каф.')\n"
        "  lesson_kind (string|null, e.g. 'лек.', 'лаб.', 'сем.', 'пр.')\n\n"
        "Output ONLY a JSON array, no prose, no markdown. Empty cells map "
        "to {id, subject: null}. Keep Ukrainian text verbatim.\n\n"
        f"Input: {json.dumps(items, ensure_ascii=False)}"
    )

    try:
        llm = await _get_context_llm()
        response = await asyncio.wait_for(
            llm.ainvoke([("human", prompt)]),
            timeout=_REFINEMENT_TIMEOUT_S,
        )
        content = getattr(response, "content", None) or str(response)
        json_text = content.strip()
        if "[" in json_text:
            json_text = json_text[json_text.find("[") : json_text.rfind("]") + 1]
        parsed = json.loads(json_text)
        if not isinstance(parsed, list):
            raise ValueError("refinement returned non-list")
    except Exception as exc:  # noqa: BLE001 — see docstring
        logger.warning(
            "Per-cell refinement batch (offset=%d, n=%d) failed: %s — "
            "emitting raw cells",
            batch_offset,
            len(batch_cells),
            exc,
        )
        return [_cell_to_minimal_record(cell) for cell in batch_cells]

    by_id: dict[int, dict[str, Any]] = {}
    for item in parsed:
        if isinstance(item, dict) and isinstance(item.get("id"), int):
            by_id[item["id"]] = item

    records: list[dict[str, Any]] = []
    for idx, cell in enumerate(batch_cells):
        refined = by_id.get(idx, {})
        subject = refined.get("subject") or cell.raw_text
        if not subject:
            continue
        records.append({
            "type": "class",
            "day": cell.day,
            "time": cell.time,
            "group": cell.group,
            "year": cell.year,
            "level": cell.level,
            "subject": subject,
            "teacher": refined.get("teacher"),
            "room": refined.get("room"),
            "lesson_kind": refined.get("lesson_kind"),
        })
    return records


async def _refine_cells_with_llm(
    cells: list,  # list[CellEvent]
    *,
    filename: str,
) -> list[dict[str, Any]]:
    """Refine pre-attributed cells into structured records.

    Cells are split into batches (~25 per call) and all batches run
    concurrently — Deepseek struggles with prompts that bundle 90+
    cells (response truncation, timeouts), so smaller parallel
    requests both finish faster and survive transient failures
    independently.
    """
    if not cells:
        return []

    batches = [
        cells[i : i + _REFINEMENT_BATCH_SIZE]
        for i in range(0, len(cells), _REFINEMENT_BATCH_SIZE)
    ]
    results = await asyncio.gather(
        *(
            _refine_one_batch(batch, i * _REFINEMENT_BATCH_SIZE)
            for i, batch in enumerate(batches)
        )
    )
    flat: list[dict[str, Any]] = [r for batch in results for r in batch]
    logger.info(
        "Per-cell refinement: %d cells in %d batches -> %d records",
        len(cells),
        len(batches),
        len(flat),
    )
    return flat


class _ExamProtocolExtractor(_ScheduleExtractor):
    """Exam timetables share enough structure with class schedules
    that the same LLM extractor and chunking strategy apply. Method
    label differs so the admin UI can colour them separately."""

    method = "exam_protocol_llm"


class _RegulationExtractor(Extractor):
    """Section-aware splitting for policy documents.

    Regulations are written as numbered articles / clauses ("Стаття
    1.", "1.1.", "Пункт 4."). Splitting at those boundaries keeps
    each chunk a self-contained rule, which is what users want to
    cite. Chunks longer than 1500 chars are subsplit by paragraph.
    """

    method = "regulation_section"

    _SECTION_RE = re.compile(
        r"(?m)^\s*(?:"
        r"(?:Стаття|Розділ|Пункт|Глава|Article|Section|Chapter)\s+\d+(?:\.\d+)*\.?"
        r"|(?:\d+\.){1,3}\s+\S"
        r")"
    )

    async def extract(
        self,
        *,
        text: str,
        filename: str,
        document_context: str,
    ) -> ExtractionResult:
        sections = self._split_sections(text)
        if not sections:
            # Fall back to recursive splitting when no headings detected.
            sections = _RecursiveProseExtractor.split_recursive(text)

        chunks: list[tuple[str, dict[str, Any]]] = []
        for index, section in enumerate(sections):
            body = section.strip()
            if not body:
                continue
            content = (
                f"{document_context}\n\n{body}" if document_context else body
            )
            meta: dict[str, Any] = {
                "chunk_index": index,
                "total_chunks": len(sections),
                "chunk_length": len(body),
                "extractor_method": self.method,
            }
            chunks.append((content, meta))
        return ExtractionResult(chunks=chunks, method=self.method)

    @classmethod
    def _split_sections(cls, text: str) -> list[str]:
        """Split at heading-like markers, keeping each heading with
        its body. If no heading matches we return [] so the caller
        falls back to recursive splitting."""
        matches = list(cls._SECTION_RE.finditer(text))
        if len(matches) < 2:
            return []
        starts = [m.start() for m in matches]
        ends = starts[1:] + [len(text)]
        sections: list[str] = []
        # Preamble before the first match (if any) is its own chunk.
        if starts[0] > 0:
            preamble = text[: starts[0]].strip()
            if preamble:
                sections.append(preamble)
        for s, e in zip(starts, ends):
            piece = text[s:e].strip()
            if piece:
                sections += cls._cap_long_section(piece)
        return sections

    @staticmethod
    def _cap_long_section(section: str, max_chars: int = 1500) -> list[str]:
        """Subsplit any section that grew past the soft cap so a
        single chunk never balloons past the embedder's comfort
        zone."""
        if len(section) <= max_chars:
            return [section]
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=max_chars,
            chunk_overlap=150,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        return splitter.split_text(section)


class _CurriculumExtractor(Extractor):
    """Course catalogues / syllabi — heading-based chunking similar
    to regulations, with awareness of "Змістовий модуль", "Тема",
    "Програмні результати навчання" markers.
    """

    method = "curriculum_section"

    _HEADING_RE = re.compile(
        r"(?m)^\s*(?:"
        r"Змістовий\s+модуль\s+\d+"
        r"|Тема\s+\d+"
        r"|Розділ\s+\d+"
        r"|Лекція\s+\d+"
        r"|Семінар\s+\d+"
        r"|Програмні\s+результати"
        r"|Очікувані\s+результати"
        r"|Силабус"
        r"|Робоча\s+програма"
        r"|Дисципліна"
        r"|(?:\d+\.){1,3}\s+\S"
        r")",
        flags=re.IGNORECASE,
    )

    async def extract(
        self,
        *,
        text: str,
        filename: str,
        document_context: str,
    ) -> ExtractionResult:
        # Reuse the regulation splitting machinery — only the regex
        # differs. We monkey-replace the SECTION_RE for one call by
        # subclassing the helper.
        matches = list(self._HEADING_RE.finditer(text))
        if len(matches) < 2:
            sections = _RecursiveProseExtractor.split_recursive(text)
        else:
            starts = [m.start() for m in matches]
            ends = starts[1:] + [len(text)]
            sections = []
            if starts[0] > 0 and text[: starts[0]].strip():
                sections.append(text[: starts[0]].strip())
            for s, e in zip(starts, ends):
                piece = text[s:e].strip()
                if piece:
                    sections += _RegulationExtractor._cap_long_section(piece)

        chunks: list[tuple[str, dict[str, Any]]] = []
        for index, section in enumerate(sections):
            body = section.strip()
            if not body:
                continue
            content = (
                f"{document_context}\n\n{body}" if document_context else body
            )
            meta: dict[str, Any] = {
                "chunk_index": index,
                "total_chunks": len(sections),
                "chunk_length": len(body),
                "extractor_method": self.method,
            }
            chunks.append((content, meta))
        return ExtractionResult(chunks=chunks, method=self.method)


class _RecursiveProseExtractor(Extractor):
    """Default chunker for free-form text — recursive split with
    overlap, plus the document context line prepended for embedding.
    Used for prose, lecture notes, announcements, and any document
    the classifier wasn't sure about.
    """

    method = "prose_recursive"

    async def extract(
        self,
        *,
        text: str,
        filename: str,
        document_context: str,
    ) -> ExtractionResult:
        pieces = self.split_recursive(text)
        chunks: list[tuple[str, dict[str, Any]]] = []
        for index, piece in enumerate(pieces):
            content = (
                f"{document_context}\n\n{piece}"
                if document_context
                else piece
            )
            meta: dict[str, Any] = {
                "chunk_index": index,
                "total_chunks": len(pieces),
                "chunk_length": len(piece),
                "extractor_method": self.method,
            }
            chunks.append((content, meta))
        return ExtractionResult(chunks=chunks, method=self.method)

    @staticmethod
    def split_recursive(text: str) -> list[str]:
        if not text.strip():
            return []
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""],
        )
        return splitter.split_text(text)


class _TabularExtractor(_RecursiveProseExtractor):
    """Generic table without schedule structure (grade lists,
    contact directories). Falls back to recursive split for now —
    future iteration can add row-aware chunking once we see a
    representative sample of these documents.
    """

    method = "tabular_recursive"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


_REGISTRY: dict[str, Extractor] = {
    "schedule": _ScheduleExtractor(),
    "exam_protocol": _ExamProtocolExtractor(),
    "regulation": _RegulationExtractor(),
    "curriculum": _CurriculumExtractor(),
    "prose": _RecursiveProseExtractor(),
    "tabular": _TabularExtractor(),
    # Unknown type is the same path as prose — recursive split with
    # contextual prefix is the most robust default we have.
    "unknown": _RecursiveProseExtractor(),
}


def get_extractor(doc_type: str) -> Extractor:
    """Look up the extractor for a ``doc_type``. Falls back to the
    prose extractor for any unfamiliar label so partial rollouts of
    new types remain safe."""
    return _REGISTRY.get(doc_type, _REGISTRY["prose"])


__all__ = [
    "ExtractionResult",
    "Extractor",
    "generate_document_context",
    "get_extractor",
]
