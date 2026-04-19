"""Full-pipeline generation evaluation with LLM-as-judge.

For each dataset entry:

1. Run the production ``run_rag_chain`` to get an answer + sources.
2. Ask a judge LLM (reusing the same Deepseek client) to score the
   generated answer against the gold answer on two axes:
     * faithfulness — every claim is grounded in the retrieved context.
     * answer_relevance — the answer actually addresses the question.
3. Emit a Markdown report with per-question scores and the aggregate.

Judge scores are deliberately coarse (0.0, 0.5, 1.0) — fine-grained
scoring is not reproducible with a single LLM call; a human spot-check
sample remains the ground truth.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from tests.eval.loader import load_entries
from tests.eval.metrics import aggregate
from tests.eval.models import GenerationResult

JUDGE_SYSTEM_PROMPT = """You are an evaluator of RAG answers. Score the \
generated answer against the gold reference on two axes:

* faithfulness: 1.0 if every factual claim in the generated answer is \
supported by the gold reference (or is a safe refusal). 0.5 if partially \
supported. 0.0 if the answer invents facts.
* answer_relevance: 1.0 if the generated answer addresses the question. \
0.5 if partially relevant. 0.0 if off-topic.

Reply with a single JSON object:
{"faithfulness": <float>, "answer_relevance": <float>, "reason": "<short reason>"}
"""

JUDGE_USER_TEMPLATE = """QUESTION:
{question}

GOLD REFERENCE:
{gold}

GENERATED ANSWER:
{generated}
"""


async def _run_rag(question: str, role: str, faculty: str | None) -> tuple[str, list[str], float]:
    from app.api.v1.chat import run_rag_chain

    start = time.perf_counter()
    result = await run_rag_chain(question=question, user_role=role, user_faculty=faculty)
    took_ms = (time.perf_counter() - start) * 1000.0
    citations = [s.get("source_file", "") for s in result.get("sources", [])]
    return result["answer"], citations, took_ms


async def _judge(
    question: str, gold: str, generated: str
) -> tuple[float | None, float | None]:
    """Return (faithfulness, answer_relevance) from the judge LLM."""
    from app.api.v1.chat import get_llm

    llm = await get_llm()
    messages = [
        ("system", JUDGE_SYSTEM_PROMPT),
        (
            "human",
            JUDGE_USER_TEMPLATE.format(question=question, gold=gold, generated=generated),
        ),
    ]
    response = await llm.ainvoke(messages)
    raw = response.content if hasattr(response, "content") else str(response)
    try:
        payload = json.loads(_extract_json(raw))
        return float(payload["faithfulness"]), float(payload["answer_relevance"])
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None, None


def _extract_json(text: str) -> str:
    """Pull the first {...} JSON object out of the judge's reply."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("no JSON object in judge response")
    return text[start : end + 1]


async def run(out_path: Path) -> None:
    entries = load_entries()
    results: list[GenerationResult] = []

    for entry in entries:
        answer, citations, took_ms = await _run_rag(
            entry.question, entry.role, entry.faculty
        )
        faithfulness, relevance = await _judge(
            entry.question, entry.gold_answer, answer
        )
        results.append(
            GenerationResult(
                question=entry.question,
                gold_answer=entry.gold_answer,
                generated_answer=answer,
                citations=citations,
                faithfulness=faithfulness,
                answer_relevance=relevance,
                took_ms=took_ms,
            )
        )

    report = _render(results)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"Wrote {out_path}")


def _render(results: list[GenerationResult]) -> str:
    faith_scores = [r.faithfulness for r in results if r.faithfulness is not None]
    rel_scores = [r.answer_relevance for r in results if r.answer_relevance is not None]
    latencies = [r.took_ms for r in results]

    lines = [
        f"# Generation evaluation — {datetime.now(timezone.utc).isoformat()}",
        "",
        f"Dataset size: **{len(results)}**  |  judged: **{len(faith_scores)}**",
        "",
        "## Aggregate",
        "",
        "| Metric               | Value |",
        "| -------------------- | ----- |",
        f"| Faithfulness         | {aggregate(faith_scores):.3f} |",
        f"| Answer relevance     | {aggregate(rel_scores):.3f} |",
        f"| Latency mean         | {aggregate(latencies):.1f} ms |",
        "",
        "## Per-question",
        "",
        "| Question | Faithfulness | Relevance | Latency |",
        "| -------- | ------------ | --------- | ------- |",
    ]
    for r in results:
        lines.append(
            f"| {(r.question[:57] + '…') if len(r.question) > 60 else r.question} "
            f"| {r.faithfulness if r.faithfulness is not None else '—'} "
            f"| {r.answer_relevance if r.answer_relevance is not None else '—'} "
            f"| {r.took_ms:.1f} ms |"
        )
    return "\n".join(lines) + "\n"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run generation + judge RAG evaluation")
    p.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).parent
        / "reports"
        / f"generation-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.md",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(run(args.out))
