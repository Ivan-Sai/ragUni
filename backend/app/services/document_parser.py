"""Document parsing for upload — extracts plain text from PDF/DOCX/XLSX/TXT.

For PDF we use pdfplumber rather than PyPDF2 because the corpus has a
lot of tabular content (exam schedules, grade sheets, course timetables)
that PyPDF2 streams as a flat text run with column boundaries lost.
pdfplumber extracts tables as 2D cell arrays and we serialise them as
Markdown so the embedding model and LLM see the row/column structure.
"""

from __future__ import annotations

import io
import logging
import re
from zipfile import BadZipFile

import pandas as pd
import pdfplumber
from docx import Document as DocxDocument

logger = logging.getLogger(__name__)

# Maximum page count we will attempt — guards against hostile / huge PDFs
# without an explicit upload-side check breaking parsing midway.
_MAX_PDF_PAGES = 500


class DocumentParser:
    """Parser for different document formats."""

    @staticmethod
    async def parse_pdf(file_content: bytes) -> str:
        """Parse a PDF into a text representation that preserves tables.

        Algorithm per page:
          1. Extract every table with pdfplumber and convert each to a
             Markdown table (with merged-parent headers flattened — see
             ``_table_to_markdown``).
          2. Extract the page's plain prose, then strip out any spans
             that belong to a table we already serialised — otherwise
             every table cell would appear twice (once flat, once
             structured).
          3. Emit the page header, the prose, and the Markdown tables
             with explicit ``--- Table ---`` delimiters so the chunker
             can keep tables intact when possible.

        Tables that span multiple pages — common for Ukrainian exam
        schedules — only carry their column headers on the first page.
        We thread the last seen header set forward so a continuation
        page's table reuses them instead of falling back to col1..colN.
        """
        try:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                if len(pdf.pages) > _MAX_PDF_PAGES:
                    raise ValueError(
                        f"PDF has {len(pdf.pages)} pages, "
                        f"maximum supported is {_MAX_PDF_PAGES}",
                    )

                page_texts: list[str] = []
                last_headers: list[str] | None = None
                for page_num, page in enumerate(pdf.pages, 1):
                    page_block, last_headers = _render_page(
                        page, page_num, last_headers
                    )
                    if page_block:
                        page_texts.append(page_block)

                return "\n".join(page_texts)

        except ValueError:
            raise
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Error reading PDF: %s", type(exc).__name__)
            raise ValueError("Could not read PDF file.") from exc
        except Exception as exc:  # noqa: BLE001 — pdfplumber wraps many libs
            # pdfplumber can surface a wide menagerie of internal errors
            # (pdfminer.PSEOF, struct.error, ...) on malformed input —
            # treat them all as "this file is broken" rather than 500ing.
            logger.warning("pdfplumber failed: %s: %s", type(exc).__name__, exc)
            raise ValueError(
                "Could not parse PDF file. The file may be corrupted or encrypted."
            ) from exc

    @staticmethod
    async def extract_schedule_cells(file_content: bytes) -> "list[CellEvent]":
        """Extract pre-attributed schedule cells from a PDF.

        Used by the schedule extractor as the deterministic primary
        path: walks every pdfplumber table, applies the same
        vertical-text destacking we use for the markdown render,
        then asks ``schedule_table_parser`` to identify column→group
        mappings and emit one ``CellEvent`` per (group, day, time)
        slot.

        Multi-page tables: a Ukrainian week-grid PDF typically
        prints the column header (groups, years, levels) on page 1
        and lets pages 2/3 continue with raw data rows. We detect
        this by parsing each table separately first; if a later
        table comes back ``parsed_successfully=False`` but the same
        column layout was learned from an earlier table, we re-run
        it with the earlier columns threaded in as a fallback header.

        Returns an empty list when no table on any page parses as a
        schedule grid; the caller should fall back to LLM-only
        extraction in that case.
        """
        from app.services.schedule_table_parser import (  # local import: avoids circular deps
            CellEvent,
            parse_schedule_table,
            parse_schedule_table_with_columns,
        )

        cells: list[CellEvent] = []
        last_columns = None  # threaded header for continuation pages
        try:
            with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                for page in pdf.pages:
                    for table in page.extract_tables() or []:
                        if len(table) < 2 or max(len(r) for r in table) < 3:
                            continue
                        rows = [
                            [(c or "").replace("\n", " ").strip() for c in row]
                            for row in table
                        ]
                        rows = _destack_vertical_text(rows)
                        result = parse_schedule_table(rows)
                        if result.parsed_successfully:
                            cells.extend(result.cells)
                            last_columns = result.columns
                        elif last_columns:
                            # Continuation page: reuse the header
                            # learned from a previous table on this
                            # document.
                            result2 = parse_schedule_table_with_columns(
                                rows, last_columns,
                            )
                            if result2.parsed_successfully:
                                cells.extend(result2.cells)
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning(
                "extract_schedule_cells: pdfplumber error %s",
                type(exc).__name__,
            )
            return []
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "extract_schedule_cells failed (%s): %s",
                type(exc).__name__,
                exc,
            )
            return []

        logger.info(
            "extract_schedule_cells: %d pre-attributed cells",
            len(cells),
        )
        return cells

    @staticmethod
    async def parse_docx(file_content: bytes) -> str:
        """Parse DOCX file and extract text + tables."""
        try:
            docx_file = io.BytesIO(file_content)
            doc = DocxDocument(docx_file)

            text_parts: list[str] = []

            for para in doc.paragraphs:
                if para.text.strip():
                    text_parts.append(para.text)

            for table in doc.tables:
                table_text: list[str] = []
                for row in table.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells)
                    if row_text:
                        table_text.append(row_text)
                if table_text:
                    text_parts.append("\n--- Table ---")
                    text_parts.extend(table_text)
                    text_parts.append("--- End of table ---\n")

            return "\n\n".join(text_parts)

        except BadZipFile:
            logger.warning("Invalid DOCX file (bad ZIP structure)")
            raise ValueError("Could not parse DOCX file. The file may be corrupted.")
        except (KeyError, OSError) as exc:
            logger.warning("Error reading DOCX: %s", type(exc).__name__)
            raise ValueError("Could not read DOCX file.") from exc

    @staticmethod
    async def parse_xlsx(file_content: bytes) -> str:
        """Parse XLSX file and extract text."""
        try:
            xlsx_file = io.BytesIO(file_content)
            excel_file = pd.ExcelFile(xlsx_file)

            text_parts: list[str] = []
            for sheet_name in excel_file.sheet_names:
                df = pd.read_excel(excel_file, sheet_name=sheet_name)
                text_parts.append(f"\n--- Sheet: {sheet_name} ---")

                df = df.fillna("")

                header = " | ".join(str(col) for col in df.columns)
                text_parts.append(header)
                text_parts.append("-" * len(header))
                for _, row in df.iterrows():
                    text_parts.append(" | ".join(str(val) for val in row.values))

                text_parts.append(f"--- End of sheet {sheet_name} ---\n")

            return "\n".join(text_parts)

        except BadZipFile:
            logger.warning("Invalid XLSX file (bad ZIP structure)")
            raise ValueError("Could not parse XLSX file. The file may be corrupted.")
        except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
            logger.warning("Error parsing XLSX data: %s", type(exc).__name__)
            raise ValueError("Could not parse spreadsheet data.") from exc
        except (KeyError, OSError) as exc:
            logger.warning("Error reading XLSX: %s", type(exc).__name__)
            raise ValueError("Could not read XLSX file.") from exc

    @classmethod
    async def parse_file(cls, file_content: bytes, file_type: str) -> str:
        """Parse file based on its type."""
        file_type = file_type.lower()
        if file_type == "pdf":
            return await cls.parse_pdf(file_content)
        if file_type == "docx":
            return await cls.parse_docx(file_content)
        if file_type == "xlsx":
            return await cls.parse_xlsx(file_content)
        if file_type == "txt":
            text = file_content.decode("utf-8", errors="replace")
            if "�" in text:
                logger.warning("File contains invalid UTF-8 characters that were replaced")
            return text
        raise ValueError(f"Unsupported file type: {file_type}")


# ---------------------------------------------------------------------------
# Internal helpers — PDF page rendering
# ---------------------------------------------------------------------------


def _render_page(
    page,
    page_num: int,
    inherited_headers: list[str] | None,
) -> tuple[str, list[str] | None]:
    """Render one pdfplumber page; returns (text, headers-for-next-page)."""
    parts: list[str] = [f"--- Page {page_num} ---"]

    raw_tables = page.find_tables()
    table_bboxes = [t.bbox for t in raw_tables]

    # 1. Prose first (everything outside the table bounding boxes).
    prose = _extract_prose_outside_tables(page, table_bboxes)
    if prose.strip():
        parts.append(prose.strip())

    # 2. Tables — each as Markdown so headers + columns survive
    #    chunking and the LLM can read it as structured data.
    last_headers = inherited_headers
    for index, table_obj in enumerate(raw_tables, 1):
        rows = table_obj.extract()
        markdown, headers = _table_to_markdown(
            rows, fallback_headers=last_headers
        )
        if headers:
            last_headers = headers
        if markdown:
            parts.append(f"\n--- Table {index} ---\n{markdown}\n--- End of table ---")

    return "\n".join(parts), last_headers


def _extract_prose_outside_tables(page, table_bboxes: list[tuple]) -> str:
    """Page text minus any character that lies inside a detected table."""
    if not table_bboxes:
        return page.extract_text() or ""

    def _outside_tables(obj) -> bool:
        # `obj` is a pdfplumber character with x0/x1/top/bottom keys.
        cx = (obj["x0"] + obj["x1"]) / 2.0
        cy = (obj["top"] + obj["bottom"]) / 2.0
        for x0, top, x1, bottom in table_bboxes:
            if x0 <= cx <= x1 and top <= cy <= bottom:
                return False
        return True

    filtered = page.filter(_outside_tables)
    return filtered.extract_text() or ""


# Recognisable Ukrainian "marker" words that appear vertically in
# university documents. Used to validate the orientation of a
# de-stacked column — if the assembled string matches one of these
# (or a substring thereof), we assume the run was a real label.
_VERTICAL_MARKER_WORDS: tuple[str, ...] = (
    "понеділок", "вівторок", "середа", "четвер", "пятниця", "п'ятниця",
    "субота", "неділя",
    "години", "год", "час",
    "дні", "день", "тиждень",
    "група", "групи",
)


def _normalise_for_match(s: str) -> str:
    """Strip apostrophes / spaces / diacritics so vertically-stacked
    words compare equal to their dictionary form."""
    out = s.lower().replace(" ", "").replace("'", "").replace("’", "")
    return out


def _pick_destacked_orientation(chars_top_down: list[str]) -> str | None:
    """Decide whether to read a stacked column top-to-bottom,
    bottom-to-top, or neither. Returns the assembled label, or None
    when nothing recognisable comes out either way.

    University tables print day names both ways depending on the
    publishing tool — Word tends to bottom-up, plain LaTeX top-down.
    We try both and accept the first that contains any of the
    recognised marker words as a substring. This is permissive on
    purpose: a false-positive de-stack only loses one cell of data,
    while a false-negative keeps the LLM blind to entire rows.
    """
    if len(chars_top_down) < 3:
        return None
    top_down = "".join(chars_top_down)
    bottom_up = "".join(reversed(chars_top_down))

    for candidate in (bottom_up, top_down):
        norm = _normalise_for_match(candidate)
        for marker in _VERTICAL_MARKER_WORDS:
            marker_norm = _normalise_for_match(marker)
            if marker_norm and marker_norm in norm:
                return candidate
    return None


# Within-cell vertical stack: a single cell whose content is
# letter-by-letter separated by whitespace (e.g. "к о л і д е н о п"
# = "понеділок" reversed, or "я ц и н т я ’ п" = "п'ятниця"). The
# pattern allows apostrophes — Ukrainian names like п'ятниця print
# them as separate stack elements.
_STACK_CHAR_CLASS = r"(?:[^\W\d_]|[''’`])"
_WITHIN_CELL_STACK_RE = re.compile(
    rf"^{_STACK_CHAR_CLASS}(?:\s+{_STACK_CHAR_CLASS}){{3,}}$",
    flags=re.UNICODE,
)


def _within_cell_destack(cell: str) -> str:
    """Resolve a within-cell vertical stack to its proper word.

    Returns the cell unchanged when the content does not match the
    space-separated single-letter pattern, or when the assembled
    word does not look like a known marker. Conservative on
    purpose — this runs on every cell, so a false positive would
    eat real data.
    """
    stripped = cell.strip()
    if not _WITHIN_CELL_STACK_RE.match(stripped):
        return cell
    chars = stripped.split()
    label = _pick_destacked_orientation(chars)
    return label if label else cell


def _destack_vertical_text(rows: list[list[str]]) -> list[list[str]]:
    """Collapse vertically-written labels into a single cell per run.

    Two patterns are handled:

    * Across-row stack — many consecutive rows of single-char cells
      in the same column. Common when pdfplumber treats each line
      of vertical text as its own row.
    * Within-cell stack — a single cell whose content is the
      vertical word written as space-separated letters. Common when
      pdfplumber merges the visual stack into one logical cell.

    Both end up as the assembled word in the first relevant cell
    so the LLM extractor never sees the raw stack.
    """
    if not rows:
        return rows

    width = max(len(row) for row in rows)
    result = [list(row) + [""] * (width - len(row)) for row in rows]

    # Pass 1: within-cell destacking. Each cell handled independently
    # so this is order-free and idempotent.
    for r_idx in range(len(result)):
        for c_idx in range(width):
            result[r_idx][c_idx] = _within_cell_destack(result[r_idx][c_idx])

    for col_idx in range(width):
        run_indices: list[int] = []
        run_chars: list[str] = []

        def flush_run() -> None:
            nonlocal run_indices, run_chars
            try:
                # Pair up indices with their letter; drop the empties.
                paired = [
                    (idx, char)
                    for idx, char in zip(run_indices, run_chars)
                    if char
                ]
                if len(paired) < 4:
                    return
                label = _pick_destacked_orientation([c for _, c in paired])
                if not label:
                    return
                # Anchor the label at the FIRST non-empty letter row.
                # Placing it in run_indices[0] would lose the link to
                # the data the run sits next to (the day label belongs
                # next to its time slots, not at the top of the table).
                anchor = paired[0][0]
                result[anchor][col_idx] = label
                for idx, _ in paired[1:]:
                    result[idx][col_idx] = ""
            finally:
                run_indices = []
                run_chars = []

        for row_idx in range(len(result)):
            cell = result[row_idx][col_idx].strip()
            # A "stack candidate" is at most one Unicode word char.
            if len(cell) <= 1 and (not cell or cell.isalpha()):
                run_indices.append(row_idx)
                run_chars.append(cell)
            else:
                flush_run()
        flush_run()

    return result


def _table_to_markdown(
    rows: list[list[str | None]],
    fallback_headers: list[str] | None = None,
) -> tuple[str, list[str] | None]:
    """Serialise a table to Markdown.

    Returns ``(markdown, headers)`` where ``headers`` is the list used
    for this table's columns — callers thread it forward to the next
    page so a continuation table inherits the parent's column names
    instead of devolving to ``col1..colN``.

    Handles the merged-parent-header pattern common in Ukrainian
    university schedules — e.g. a single "Екзамени" cell spanning
    "Дата | Год. | Ауд." beneath.

    Also collapses vertically-written labels: timetables print day
    names as one character per cell down the leftmost column ("П", "О",
    "Н", "Е", "Д", …). pdfplumber returns them as separate cells, so
    the LLM extractor sees the day spelled letter-by-letter and never
    captures it. ``_destack_vertical_text`` reassembles those columns.
    """
    cleaned: list[list[str]] = [
        [(cell or "").replace("\n", " ").strip() for cell in row]
        for row in rows
        if row and any((cell or "").strip() for cell in row)
    ]
    if not cleaned:
        return "", None

    width = max(len(r) for r in cleaned)
    cleaned = [row + [""] * (width - len(row)) for row in cleaned]
    cleaned = _destack_vertical_text(cleaned)

    header_height = _detect_header_height(cleaned)
    if header_height == 0:
        if fallback_headers and len(fallback_headers) == width:
            headers = fallback_headers
        else:
            headers = [f"col{i + 1}" for i in range(width)]
        body = cleaned
    else:
        headers = _merge_headers(cleaned[:header_height], width)
        body = cleaned[header_height:]

    if not body:
        return "", headers

    md_lines: list[str] = []
    md_lines.append("| " + " | ".join(headers) + " |")
    md_lines.append("| " + " | ".join(["---"] * width) + " |")
    for row in body:
        md_lines.append("| " + " | ".join(cell or " " for cell in row) + " |")

    return "\n".join(md_lines), headers


def _looks_like_header_cell(cell: str) -> bool:
    """Heuristic: header cells are short pure-text labels.

    Empty cells are considered header-compatible because merged spans
    legitimately leave the lower-row sub-cells blank. A cell containing
    digits or longer-than-label text (>40 chars) is treated as data —
    that's how we tell a "Дата | Год. | Ауд." header row apart from a
    "13.05.2026 | 12:00 | ауд. 8" data row.
    """
    s = cell.strip()
    if not s:
        return True
    if len(s) > 40:
        return False
    if any(ch.isdigit() for ch in s):
        return False
    return True


def _detect_header_height(rows: list[list[str]]) -> int:
    """Return how many top rows form the table header (0..3).

    Walks down from the top until it finds the first row that does not
    look like a header. Returns 0 when row 0 is already data — common
    for tables that span pages and so don't repeat their header on
    continuation pages.
    """
    for i, row in enumerate(rows):
        if not all(_looks_like_header_cell(c) for c in row):
            return i
    return min(len(rows), 3)


def _merge_headers(header_rows: list[list[str]], width: int) -> list[str]:
    """Combine 0..3 header rows into a flat list of column names.

    The top row (if any) is forward-filled across empty cells so a
    "Консультації" parent that visually spans three sub-columns
    actually qualifies all three of them. Sub-labels from lower header
    rows are joined with spaces and wrapped in parentheses next to the
    parent, e.g. ``Дата (консультації)``.
    """
    if not header_rows:
        return [f"col{i + 1}" for i in range(width)]

    # Forward-fill the parent (top) row only — it's the row that
    # carries merged spans like Консультації / Екзамени.
    parents_raw = header_rows[0] + [""] * (width - len(header_rows[0]))
    filled_parents: list[str] = []
    last = ""
    for i in range(width):
        value = (parents_raw[i] or "").strip()
        if value:
            last = value
            filled_parents.append(value)
        else:
            filled_parents.append(last)

    # Lower header rows: concatenate their non-empty cells per column.
    sub_rows = header_rows[1:]
    out: list[str] = []
    for i in range(width):
        parts: list[str] = []
        for row in sub_rows:
            if i < len(row):
                cell = (row[i] or "").strip()
                if cell:
                    parts.append(cell)
        sub = " ".join(parts)
        parent = filled_parents[i]
        if sub and parent and sub.lower() != parent.lower():
            out.append(f"{sub} ({parent.lower()})")
        elif sub:
            out.append(sub)
        elif parent:
            out.append(parent)
        else:
            out.append(f"col{i + 1}")
    return out
