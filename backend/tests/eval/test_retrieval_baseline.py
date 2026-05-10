"""Regression gate for retrieval quality.

Loads the frozen baseline from ``baseline.json`` and asserts that the
current retrieval pipeline scores at least that well on the eval
dataset. The actual retrieval call requires a live MongoDB Atlas
Vector Search with the eval corpus loaded — until that exists, the
test is skipped (not failed) so CI stays green for normal commits.

When the corpus + real chunk IDs land:

  1. Drop the skip marker below.
  2. Run ``python -m tests.eval.run_retrieval --k 5 --out reports/baseline.md``
     once and copy the aggregate metrics into ``baseline.json``.
  3. Subsequent runs gate against those numbers.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


_BASELINE = Path(__file__).parent / "baseline.json"


def _has_placeholders() -> bool:
    """Skip the regression gate while the dataset still uses TBD IDs."""
    dataset = Path(__file__).parent / "dataset.jsonl"
    text = dataset.read_text(encoding="utf-8") if dataset.exists() else ""
    return "TBD_chunk_" in text


def _has_corpus() -> bool:
    """Skip when not pointed at a real Atlas — the regression needs a
    populated index. Set ``EVAL_REGRESSION=1`` in the environment to
    opt in once the corpus is loaded."""
    return os.environ.get("EVAL_REGRESSION", "").lower() in ("1", "true")


@pytest.mark.skipif(
    _has_placeholders() or not _has_corpus(),
    reason="Eval corpus / real chunk IDs not yet available; "
    "set EVAL_REGRESSION=1 once the corpus is loaded",
)
@pytest.mark.asyncio
async def test_retrieval_meets_baseline():
    from tests.eval.run_retrieval import main as run_retrieval

    baseline = json.loads(_BASELINE.read_text(encoding="utf-8"))
    thresholds = baseline["thresholds"]
    k = int(baseline.get("k", 5))

    # The runner returns aggregate metrics as a dict.
    aggregates = await run_retrieval(k=k, write_report=False)
    failures: list[str] = []
    for metric, expected in thresholds.items():
        actual = aggregates.get(metric)
        if actual is None:
            failures.append(f"{metric} missing from aggregates")
        elif actual < expected:
            failures.append(
                f"{metric}: {actual:.3f} < baseline {expected:.3f}"
            )
    assert not failures, "Retrieval regressed:\n  " + "\n  ".join(failures)
