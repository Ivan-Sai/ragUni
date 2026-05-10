"""Regression gate for retrieval quality.

Loads the frozen baseline from ``baseline.json`` and asserts that the
current retriever scores at least that well on the eval dataset. The
test needs a live MongoDB Atlas Vector Search with the eval corpus
loaded — set ``EVAL_REGRESSION=1`` to enable it. The bit costs a few
seconds per CI run when on, so it's opt-in.

To refresh the baseline after a corpus change::

    python scripts/build_eval_baseline.py --skip-upload
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from statistics import mean

import pytest


_BASELINE = Path(__file__).parent / "baseline.json"


def _has_placeholders() -> bool:
    """If the dataset still uses TBD IDs, skip — refresh first."""
    dataset = Path(__file__).parent / "dataset.jsonl"
    text = dataset.read_text(encoding="utf-8") if dataset.exists() else ""
    return "TBD_chunk_" in text


def _has_opt_in() -> bool:
    return os.environ.get("EVAL_REGRESSION", "").lower() in ("1", "true")


@pytest.mark.skipif(
    _has_placeholders() or not _has_opt_in(),
    reason="Set EVAL_REGRESSION=1 (and ensure Atlas + corpus available) "
    "to enable the retrieval regression gate.",
)
@pytest.mark.asyncio
async def test_retrieval_meets_baseline():
    from tests.eval.loader import load_entries
    from tests.eval.metrics import (
        aggregate, ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank,
    )
    from tests.eval.run_retrieval import _retrieve

    baseline = json.loads(_BASELINE.read_text(encoding="utf-8"))
    thresholds = baseline["thresholds"]
    k = int(baseline.get("k", 5))

    entries = load_entries()
    recalls, precisions, mrrs, ndcgs = [], [], [], []
    for entry in entries:
        retrieved, _took = await _retrieve(
            entry.question, entry.role, entry.faculty, k
        )
        recalls.append(recall_at_k(retrieved, entry.relevant_chunks, k))
        precisions.append(precision_at_k(retrieved, entry.relevant_chunks, k))
        mrrs.append(reciprocal_rank(retrieved, entry.relevant_chunks))
        ndcgs.append(ndcg_at_k(retrieved, entry.relevant_chunks, k))

    aggregates = {
        f"recall_at_{k}": aggregate(recalls),
        f"precision_at_{k}": aggregate(precisions),
        "mrr": aggregate(mrrs),
        f"ndcg_at_{k}": aggregate(ndcgs),
    }

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
