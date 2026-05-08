"""Deterministic schedule-table parser.

Why this exists
===============

Pure-LLM extraction of multi-column university timetables fails
predictably on column attribution: pdfplumber serialises a 12-column
table as markdown rows where each cell is separated by ``|``, and a
slot like ``Прикладна теорія цифрових автоматів`` ends up in the
МА(4) column or the СА(2) column or the КСМ column depending on how
the LLM counts pipes. Field tests on the ФРЕКС schedule produced
0 records correctly attributed to the user's group despite all
records being correctly extracted in some other group.

The fix is to take column attribution OUT of the LLM's hands. This
module reads the raw 2-D table from pdfplumber, detects which row
holds the group labels, builds a deterministic
``column_index → group`` map, and walks data rows pairing each
non-empty cell with its column's group + the row's day + time.

Output is a pre-attributed list of "cell events" the LLM extractor
then refines into final records — its only job left is to clean up
multi-line cell text (separating teacher from subject, finding the
``ауд.``, etc.). LLM column attribution is gone.

Limitations
-----------

* Works on tables where the schedule structure is "rows = time
  slots, columns = groups, cells = subject text". This is the
  standard Ukrainian university format. Other layouts (per-day
  column, calendar grid) fall through to the LLM-only path.
* Multi-line cells: the parser merges consecutive table rows that
  belong to the same time slot by detecting "anchor" rows (those
  that start a new time slot). Anchor detection uses the time
  column pattern.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------


# A time slot like "8:40-9:25", "8:40–9:25", "0840-0925", "08:40 09:25",
# possibly two consecutive slots glued together ("8:40-9:25 9:30-10:15").
_TIME_RE = re.compile(
    r"\d{1,2}[:\.]?\d{2}\s*[\-–—−]\s*\d{1,2}[:\.]?\d{2}",
    flags=re.UNICODE,
)


# Day-of-week vocabulary (canonical Ukrainian + variants). Used to
# detect the day column and to forward-fill day labels.
_DAY_VARIANTS: dict[str, str] = {
    "понеділок": "понеділок", "понеділка": "понеділок", "понедельник": "понеділок",
    "monday": "понеділок", "пн": "понеділок",
    "вівторок": "вівторок", "вівторка": "вівторок", "вторник": "вівторок",
    "tuesday": "вівторок", "вт": "вівторок",
    "середа": "середа", "среда": "середа", "wednesday": "середа", "ср": "середа",
    "четвер": "четвер", "четверг": "четвер", "thursday": "четвер", "чт": "четвер",
    "п'ятниця": "п'ятниця", "пятниця": "п'ятниця", "пятница": "п'ятниця",
    "п’ятниця": "п'ятниця", "friday": "п'ятниця", "пт": "п'ятниця",
    "субота": "субота", "суббота": "субота", "saturday": "субота", "сб": "субота",
    "неділя": "неділя", "воскресенье": "неділя", "sunday": "неділя", "нд": "неділя",
}


def _canonical_day(value: str) -> Optional[str]:
    if not value:
        return None
    normalised = re.sub(r"[\s\-_,.]+", "", value.lower())
    return _DAY_VARIANTS.get(normalised)


# Group-label heuristics. A "group" cell typically contains a short
# code (uppercase letters / digits / spaces / hyphens) optionally
# followed by ``(NNстуд.)`` annotation. The annotation is stripped
# before storing the canonical label.
_STUDENT_COUNT_RE = re.compile(r"\s*\(\s*\d+\s*студ\.?\s*\)\s*", flags=re.UNICODE)


def _strip_student_count(label: str) -> str:
    return _STUDENT_COUNT_RE.sub("", label).strip()


# Year-row pattern: cells like "1 бакалавр", "2 магістр", "1 курс".
_YEAR_ROW_RE = re.compile(
    r"^\s*(?P<year>\d)\s+(?P<level>бакалавр|магістр|магистр|phd|аспірант)\b",
    flags=re.IGNORECASE | re.UNICODE,
)

_LEVEL_CANONICAL = {
    "бакалавр": "bachelor",
    "магістр": "master",
    "магистр": "master",
    "phd": "phd",
    "аспірант": "phd",
}


# ---------------------------------------------------------------------------
# Output dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ColumnSpec:
    """One non-day, non-time column from the table header."""

    index: int
    group: str
    year: Optional[int] = None
    level: Optional[str] = None


@dataclass
class CellEvent:
    """One pre-attributed cell ready for LLM refinement.

    ``raw_text`` is the merged content of one (group, time, day) slot
    after combining the multiple table rows that belong to the same
    time slot.
    """

    day: Optional[str]
    time: Optional[str]
    group: str
    year: Optional[int]
    level: Optional[str]
    raw_text: str


@dataclass
class ScheduleParseResult:
    """Complete output of one table parse.

    ``cells`` lists every non-empty (group, time, day) cell. Empty
    when ``parsed_successfully`` is false; the caller should fall
    back to the LLM-only extraction path in that case.
    """

    parsed_successfully: bool = False
    cells: list[CellEvent] = field(default_factory=list)
    columns: list[ColumnSpec] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


def _detect_time_column(rows: list[list[str]]) -> Optional[int]:
    """Find the column whose cells contain time-slot patterns.

    Counts how many cells in each column match the time regex; the
    column with the highest hit-count is the time column. Returns
    None if no column has at least 2 hits — that means the table
    isn't a schedule grid.
    """
    if not rows:
        return None
    width = max(len(r) for r in rows)
    best_col, best_hits = None, 0
    for c in range(min(width, 4)):  # day/time live near the left edge
        hits = sum(
            1
            for row in rows
            if c < len(row) and _TIME_RE.search(row[c] or "")
        )
        if hits > best_hits:
            best_col, best_hits = c, hits
    return best_col if (best_hits >= 2) else None


def _detect_day_column(rows: list[list[str]], time_col: int) -> Optional[int]:
    """Find the column that holds destacked day names.

    The day column is typically just to the left of the time column
    (col 0 when time is col 1). Heuristic: pick the column with the
    most ``_canonical_day`` hits among non-time columns left of /
    equal to ``time_col``. Single-day pages (one day per pdfplumber
    table) are common in university schedules — accept any column
    with at least one day match rather than requiring two.
    """
    candidates = list(range(time_col + 1))
    best_col, best_hits = None, 0
    for c in candidates:
        hits = sum(
            1
            for row in rows
            if c < len(row) and _canonical_day(row[c] or "")
        )
        if hits > best_hits:
            best_col, best_hits = c, hits
    return best_col if best_hits >= 1 else None


def _detect_header_band(
    rows: list[list[str]],
    time_col: int,
) -> tuple[int, list[ColumnSpec]]:
    """Identify the top header band and build the column→group map.

    Walks down from row 0 until it hits the first data row (one whose
    time column matches a time-slot pattern). Within the header
    band:

    * The row that holds the group labels is the LAST header row
      (closest to the data) whose cells right of the time column are
      mostly short codes / abbreviations.
    * The year/level row is the row above the group row whose cells
      match the ``_YEAR_ROW_RE`` pattern.

    Returns ``(header_height, column_specs)`` where header_height is
    the number of top rows to skip before data.
    """
    if not rows:
        return 0, []

    width = max(len(r) for r in rows)

    header_height = 0
    for r_idx, row in enumerate(rows):
        cell = row[time_col] if time_col < len(row) else ""
        if _TIME_RE.search(cell or ""):
            header_height = r_idx
            break
    else:
        # No time slots found at all — not a schedule.
        return 0, []

    if header_height == 0:
        return 0, []

    header_band = rows[:header_height]

    # Year/level forward-fill across the row.
    year_levels: dict[int, tuple[int, str]] = {}
    for r in header_band:
        last_year_level: Optional[tuple[int, str]] = None
        for c in range(len(r)):
            cell = (r[c] or "").strip()
            match = _YEAR_ROW_RE.match(cell)
            if match:
                year = int(match.group("year"))
                level_raw = match.group("level").lower()
                last_year_level = (year, _LEVEL_CANONICAL.get(level_raw, level_raw))
                year_levels[c] = last_year_level
            elif last_year_level and not cell:
                # A year-row cell legitimately leaves the lower
                # sub-cells blank (merged span); forward-fill so the
                # group below inherits.
                year_levels[c] = last_year_level

    # Group row: we pick the LAST header row in which most non-empty
    # right-of-time cells look like short group codes (no year word,
    # no time pattern, ≤30 chars).
    group_row_idx = None
    best_score = 0
    for r_idx in range(header_height - 1, -1, -1):
        row = header_band[r_idx]
        score = 0
        for c in range(time_col + 1, width):
            cell = (row[c] or "").strip() if c < len(row) else ""
            if not cell:
                continue
            if _YEAR_ROW_RE.match(cell):
                continue
            if _TIME_RE.search(cell):
                continue
            if len(cell) > 40:
                continue
            score += 1
        if score > best_score:
            best_score = score
            group_row_idx = r_idx
    if group_row_idx is None:
        return header_height, []

    group_row = header_band[group_row_idx]
    columns: list[ColumnSpec] = []
    for c in range(time_col + 1, width):
        cell = (group_row[c] or "").strip() if c < len(group_row) else ""
        if not cell:
            continue
        group = _strip_student_count(cell)
        if not group or len(group) > 30:
            continue
        # Forward-fill year/level from earlier columns when the year
        # row spans (e.g. "2 бакалавр" covers both МА and СА columns
        # via merged cell).
        year_level = year_levels.get(c)
        if not year_level:
            # Walk left looking for the nearest year_level column.
            for left in range(c, -1, -1):
                if left in year_levels:
                    year_level = year_levels[left]
                    break
        year = year_level[0] if year_level else None
        level = year_level[1] if year_level else None
        columns.append(ColumnSpec(index=c, group=group, year=year, level=level))

    return header_height, columns


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse_schedule_table(rows: list[list[str]]) -> ScheduleParseResult:
    """Try to parse one pdfplumber table as a schedule grid.

    Returns ``parsed_successfully=False`` when any of the structural
    checks fail (no time column, no day column, no group row); the
    caller falls back to the LLM-only path.
    """
    if not rows:
        return ScheduleParseResult()

    # Normalise: ensure rectangular and strip all cells.
    width = max(len(r) for r in rows)
    norm: list[list[str]] = [
        [(cell or "").strip() for cell in row] + [""] * (width - len(row))
        for row in rows
    ]

    time_col = _detect_time_column(norm)
    if time_col is None:
        return ScheduleParseResult()
    day_col = _detect_day_column(norm, time_col)
    header_height, columns = _detect_header_band(norm, time_col)
    if not columns:
        return ScheduleParseResult()

    # Walk data rows, group consecutive rows by anchor (a row is an
    # anchor when its time column has a time-slot match). Cells of
    # non-anchor rows are appended to the latest anchor's per-column
    # buffers.
    current_day: Optional[str] = None
    current_time: Optional[str] = None
    buffers: dict[int, list[str]] = {}

    cells: list[CellEvent] = []

    def flush() -> None:
        if not buffers:
            return
        for col in columns:
            parts = buffers.get(col.index)
            if not parts:
                continue
            text = " ".join(p for p in parts if p).strip()
            if not text:
                continue
            cells.append(
                CellEvent(
                    day=current_day,
                    time=current_time,
                    group=col.group,
                    year=col.year,
                    level=col.level,
                    raw_text=text,
                )
            )

    for row_idx in range(header_height, len(norm)):
        row = norm[row_idx]

        # Day column: forward-fill — a day cell is set on the row
        # that starts the day, the rest of the day's rows leave it
        # blank.
        if day_col is not None and day_col < len(row):
            day_label = _canonical_day(row[day_col])
            if day_label:
                current_day = day_label

        # Time column: detect anchor.
        time_cell = row[time_col] if time_col < len(row) else ""
        time_match = _TIME_RE.search(time_cell or "")
        if time_match:
            # Flush the previous slot before starting a new one.
            flush()
            current_time = time_match.group(0).strip()
            buffers = {col.index: [] for col in columns}

        # Append per-column data.
        for col in columns:
            if col.index < len(row) and row[col.index]:
                buffers.setdefault(col.index, []).append(row[col.index])

    # Final flush for the last slot.
    flush()

    parsed_successfully = bool(cells) and current_time is not None
    logger.info(
        "Deterministic schedule parser: %d cells, %d columns, success=%s",
        len(cells),
        len(columns),
        parsed_successfully,
    )
    return ScheduleParseResult(
        parsed_successfully=parsed_successfully,
        cells=cells,
        columns=columns,
    )


def parse_schedule_table_with_columns(
    rows: list[list[str]],
    columns: list[ColumnSpec],
) -> ScheduleParseResult:
    """Parse a continuation table using a header learned earlier.

    Multi-page Ukrainian schedules print the column header (groups,
    years, levels) once on page 1 and let pages 2/3 continue with
    raw data rows. ``parse_schedule_table`` would refuse those
    continuation tables for lack of a header band; this entrypoint
    accepts an externally-supplied ``columns`` list and walks the
    rows the same way ``parse_schedule_table`` would after the
    header band.

    Returns ``parsed_successfully=False`` only when no time-slot
    anchor is found at all; otherwise emits one ``CellEvent`` per
    (group, day, time) cell as usual.
    """
    if not rows or not columns:
        return ScheduleParseResult()

    width = max(len(r) for r in rows)
    norm: list[list[str]] = [
        [(cell or "").strip() for cell in row] + [""] * (width - len(row))
        for row in rows
    ]

    time_col = _detect_time_column(norm)
    if time_col is None:
        return ScheduleParseResult()
    day_col = _detect_day_column(norm, time_col)

    current_day: Optional[str] = None
    current_time: Optional[str] = None
    buffers: dict[int, list[str]] = {}
    cells: list[CellEvent] = []

    def flush() -> None:
        if not buffers:
            return
        for col in columns:
            parts = buffers.get(col.index)
            if not parts:
                continue
            text = " ".join(p for p in parts if p).strip()
            if not text:
                continue
            cells.append(
                CellEvent(
                    day=current_day,
                    time=current_time,
                    group=col.group,
                    year=col.year,
                    level=col.level,
                    raw_text=text,
                )
            )

    for row in norm:
        if day_col is not None and day_col < len(row):
            day_label = _canonical_day(row[day_col])
            if day_label:
                current_day = day_label

        time_cell = row[time_col] if time_col < len(row) else ""
        time_match = _TIME_RE.search(time_cell or "")
        if time_match:
            flush()
            current_time = time_match.group(0).strip()
            buffers = {col.index: [] for col in columns}

        for col in columns:
            if col.index < len(row) and row[col.index]:
                buffers.setdefault(col.index, []).append(row[col.index])

    flush()

    return ScheduleParseResult(
        parsed_successfully=bool(cells) and current_time is not None,
        cells=cells,
        columns=columns,
    )


__all__ = [
    "CellEvent",
    "ColumnSpec",
    "ScheduleParseResult",
    "parse_schedule_table",
    "parse_schedule_table_with_columns",
]
