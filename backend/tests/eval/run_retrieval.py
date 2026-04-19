"""Retrieval-only evaluation runner.

Runs every dataset entry through the vector store's retriever (no LLM
call), collects the retrieved chunk IDs, and computes Recall@k,
Precision@k, MRR and nDCG@k. Writes a Markdown report under
``backend/tests/eval/reports/``.

Usage::

    cd backend
    python -m tests.eval.run_retrieval --k 5 --out reports/retrieval.md

Run only against a live MongoDB Atlas Vector Search — the script needs a
populated ``embeddings`` collection.
"""

from __future__ import annotations

import argparse
import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from tests.eval.loader import load_entries
from tests.eval.metrics import (
    aggregate,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)
from tests.eval.models import RetrievalResult


async def _retrieve(
    question: str,
    role: str,
    faculty: str | None,
    k: int,
) -> tuple[list[str], float]:
    """Call the live retriever once and return (chunk_ids, ms).

    Imported lazily so the module loads fine in environments without a
    configured MongoDB connection (CI, tests).
    """
    from app.services.vector_store import vector_store_service

    pre_filter = vector_store_service.build_access_filter(role, faculty)
    retriever = vector_store_service.get_retriever(
        search_type="mmr",
        k=k,
        pre_filter=pre_filter or None,
        fetch_k=k * 4,
        lambda_mult=0.7,
    )
    start = time.perf_counter()
    docs = await retriever.ainvoke(question)
    took_ms = (time.perf_counter() - start) * 1000.0

    chunk_ids = [
        str(d.metadata.get("chunk_id") or d.metadata.get("_id", ""))
        for d in docs
    ]
    return chunk_ids, took_ms


async def run(k: int, out_path: Path) -> None:
    entries = load_entries()
    results: list[RetrievalResult] = []

    for entry in entries:
        retrieved, took_ms = await _retrieve(
            entry.question, entry.role, entry.faculty, k
        )
        results.append(
            RetrievalResult(
                question=entry.question,
                retrieved_chunk_ids=retrieved,
                relevant_chunk_ids=entry.relevant_chunks,
                took_ms=took_ms,
            )
        )

    report = _render_markdown(results, k=k)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote {out_path}")
    print(report)


def _render_markdown(results: list[RetrievalResult], k: int) -> str:
    """Format aggregate + per-question tables as Markdown."""
    if not results:
        return "# Retrieval evaluation\n\nNo dataset entries found.\n"

    recalls = [
        recall_at_k(r.retrieved_chunk_ids, r.relevant_chunk_ids, k) for r in results
    ]
    precisions = [
        precision_at_k(r.retrieved_chunk_ids, r.relevant_chunk_ids, k) for r in results
    ]
    mrrs = [
        reciprocal_rank(r.retrieved_chunk_ids, r.relevant_chunk_ids) for r in results
    ]
    ndcgs = [
        ndcg_at_k(r.retrieved_chunk_ids, r.relevant_chunk_ids, k) for r in results
    ]
    latencies = [r.took_ms for r in results]

    header = [
        f"# Retrieval evaluation — {datetime.now(timezone.utc).isoformat()}",
        "",
        f"Dataset size: **{len(results)}** | k = **{k}**",
        "",
        "## Aggregate metrics",
        "",
        f"| Metric        | Value  |",
        f"| ------------- | ------ |",
        f"| Recall@{k}    | {aggregate(recalls):.3f} |",
        f"| Precision@{k} | {aggregate(precisions):.3f} |",
        f"| MRR           | {aggregate(mrrs):.3f} |",
        f"| nDCG@{k}      | {aggregate(ndcgs):.3f} |",
        f"| Latency p50   | {mean(latencies):.1f} ms |",
        "",
        "## Per-question results",
        "",
        f"| Question | Recall@{k} | P@{k} | RR | nDCG@{k} | Latency |",
        "| -------- | ---------- | ----- | -- | -------- | ------- |",
    ]
    rows = [
        f"| {_truncate(r.question, 60)} "
        f"| {recall_at_k(r.retrieved_chunk_ids, r.relevant_chunk_ids, k):.2f} "
        f"| {precision_at_k(r.retrieved_chunk_ids, r.relevant_chunk_ids, k):.2f} "
        f"| {reciprocal_rank(r.retrieved_chunk_ids, r.relevant_chunk_ids):.2f} "
        f"| {ndcg_at_k(r.retrieved_chunk_ids, r.relevant_chunk_ids, k):.2f} "
        f"| {r.took_ms:.1f} ms |"
        for r in results
    ]
    return "\n".join(header + rows) + "\n"


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run retrieval-only RAG evaluation")
    p.add_argument("--k", type=int, default=5)
    p.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parent
        / "reports"
        / f"retrieval-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.md",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(run(args.k, args.out))
