"""Latency benchmark for the RAG pipeline.

Runs the whole pipeline N times on a fixed warm-up question (the first
run primes caches) and reports p50 / p95 / p99 per stage.

The stage breakdown matches the targets quoted in docs/EVALUATION.md
section 5.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path


WARMUP_QUESTION = (
    "Що таке факультет та які його обов'язки згідно з положенням?"
)


async def _one_run(question: str) -> dict[str, float]:
    """Run the pipeline once and return per-stage wall-clock milliseconds."""
    from app.api.v1.chat import (
        extract_sources,
        format_docs,
        get_llm,
        rag_prompt,
    )
    from app.services.vector_store import vector_store_service
    from langchain_core.output_parsers import StrOutputParser

    pre_filter = vector_store_service.build_access_filter("student", None)
    retriever = vector_store_service.get_retriever(
        search_type="mmr",
        k=5,
        pre_filter=pre_filter or None,
        fetch_k=20,
        lambda_mult=0.7,
    )

    t0 = time.perf_counter()
    docs = await retriever.ainvoke(question)
    t_retrieve = (time.perf_counter() - t0) * 1000.0

    context = format_docs(docs)
    _ = extract_sources(docs)

    t1 = time.perf_counter()
    llm = await get_llm()
    chain = rag_prompt | llm | StrOutputParser()
    answer = await chain.ainvoke({"context": context, "question": question})
    t_llm = (time.perf_counter() - t1) * 1000.0

    return {
        "retrieve_ms": t_retrieve,
        "llm_ms": t_llm,
        "total_ms": t_retrieve + t_llm,
        "answer_len": float(len(answer)),
    }


async def run(iterations: int, out_path: Path) -> None:
    # Warm-up to prime LLM client + embedding model.
    await _one_run(WARMUP_QUESTION)

    samples: list[dict[str, float]] = []
    for _ in range(iterations):
        samples.append(await _one_run(WARMUP_QUESTION))

    def pct(values: list[float], p: float) -> float:
        if not values:
            return 0.0
        values = sorted(values)
        k = int(round((p / 100.0) * (len(values) - 1)))
        return values[k]

    report_lines = [
        f"# Latency benchmark — {datetime.now(timezone.utc).isoformat()}",
        "",
        f"Iterations: **{iterations}** (plus 1 warm-up).",
        "",
        "| Stage     | p50       | p95       | p99       |",
        "| --------- | --------- | --------- | --------- |",
    ]
    for stage in ("retrieve_ms", "llm_ms", "total_ms"):
        values = [s[stage] for s in samples]
        report_lines.append(
            f"| {stage:<9} | {statistics.median(values):8.1f} | "
            f"{pct(values, 95):8.1f} | {pct(values, 99):8.1f} |"
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Benchmark RAG pipeline latency")
    p.add_argument("--iterations", type=int, default=10)
    p.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parent
        / "reports"
        / f"latency-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.md",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(run(args.iterations, args.out))
