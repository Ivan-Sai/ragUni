"""Load the JSONL evaluation dataset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from app.models.user import UserRole

from tests.eval.models import EvalEntry

DEFAULT_DATASET_PATH = Path(__file__).parent / "dataset.jsonl"


def iter_entries(path: Path | None = None) -> Iterator[EvalEntry]:
    """Yield every :class:`EvalEntry` in the dataset file.

    Lines that start with ``#`` or are blank are skipped so the dataset
    file can include comments.
    """
    dataset_path = path or DEFAULT_DATASET_PATH
    with dataset_path.open("r", encoding="utf-8") as f:
        for line_number, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{dataset_path}:{line_number}: invalid JSON: {exc}"
                ) from exc
            entry = EvalEntry.model_validate(data)
            # Fail loudly on invalid roles so typos in the dataset don't
            # masquerade as legitimate "student" questions.
            if entry.role not in {r.value for r in UserRole}:
                raise ValueError(
                    f"{dataset_path}:{line_number}: unknown role "
                    f"{entry.role!r}"
                )
            yield entry


def load_entries(path: Path | None = None) -> list[EvalEntry]:
    """Eagerly load every dataset entry into a list."""
    return list(iter_entries(path))
