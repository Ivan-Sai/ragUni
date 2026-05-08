"""LLM-based reranker — second-stage relevance scoring.

Why this exists
===============

Bi-encoder embeddings (E5, BGE, Cohere v3) score every document
chunk independently against the query. They are fast, but they miss
subtle semantic mismatches: a chunk with high lexical overlap and
high embedding similarity can still be irrelevant to the user's
actual intent. Cross-encoder reranking — feeding ``(query, document)``
pairs through an LLM that scores each pair — closes that gap and is
now a standard component of production RAG pipelines (Cohere Rerank
v3, Anthropic Contextual Retrieval, OpenAI Assistants v2).

This module implements an **LLM-as-reranker** because we already have
a fast Deepseek client and the cost of one extra ~500-token call is
acceptable. For a stricter latency budget the same interface could
plug in Cohere Rerank or a local BGE-Reranker-v2-m3 without touching
the orchestrator.

The reranker is **optional** by design. If it times out, returns
malformed JSON, or otherwise fails, ``rerank`` falls back to the
input ordering — RAG quality degrades to "without reranker" rather
than "broken".
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional

from langchain_core.documents import Document as LCDocument
from langchain_openai import ChatOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


_reranker_llm: Optional[ChatOpenAI] = None
_reranker_lock = asyncio.Lock()


async def _get_llm() -> ChatOpenAI:
    """Dedicated low-temperature client. The reranker is purely a
    classifier — sampling diversity is harmful here."""
    global _reranker_llm
    if _reranker_llm is None:
        async with _reranker_lock:
            if _reranker_llm is None:
                _reranker_llm = ChatOpenAI(
                    model=settings.deepseek_model,
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_api_base,
                    temperature=0.0,
                    max_tokens=600,
                    request_timeout=20.0,
                )
                logger.info("Reranker LLM initialised")
    return _reranker_llm


_SYSTEM_PROMPT = """You are a document reranker for a university RAG system.

Given a user question and a numbered list of candidate documents, output a JSON object that scores each candidate's relevance to the question on a 0-10 scale.

Output schema:
{"scores": [{"id": int, "score": float}, ...]}

- id: the candidate's number as shown in the input.
- score: 0 = unrelated, 5 = tangentially related, 10 = directly answers the question.
- Score every candidate even if you score it 0.
- Output ONLY the JSON object, no commentary, no markdown.

Rules:
1. Reward exact entity matches (day, date, subject name, teacher surname, room number).
2. Penalise candidates whose audience does not match the user's profile if mentioned.
3. A candidate that ANSWERS the question scores 8-10. A candidate that PROVIDES related context scores 4-7. A candidate that is off-topic scores 0-3.
4. Be strict — most candidates in a typical retrieval set are irrelevant.
"""


_JSON_RE = re.compile(r"\{.*\}", flags=re.DOTALL)


async def rerank(
    query: str,
    candidates: list[LCDocument],
    *,
    top_n: int = 15,
    timeout_seconds: float = 12.0,
) -> list[LCDocument]:
    """Score every candidate against the query and return the top-N.

    Falls back to ``candidates[:top_n]`` (no reranking, original
    order preserved) on any failure path. The orchestrator calls
    this between merging retrieval results and synthesising the
    answer — failure here should not block answer generation.
    """
    if not candidates:
        return []
    if len(candidates) <= top_n:
        # Fewer candidates than requested — reranking can't change
        # the selection, only the order. Skipping saves a round-trip.
        return candidates

    user_prompt = _build_user_prompt(query, candidates)
    try:
        llm = await _get_llm()
        response = await asyncio.wait_for(
            llm.ainvoke([("system", _SYSTEM_PROMPT), ("human", user_prompt)]),
            timeout=timeout_seconds,
        )
        content = getattr(response, "content", None) or str(response)
        scores = _parse_scores(content, len(candidates))
    except asyncio.TimeoutError:
        logger.warning("Reranker timed out, returning original top-%d", top_n)
        return candidates[:top_n]
    except (ValueError, RuntimeError, OSError) as exc:
        logger.warning("Reranker failed (%s), returning original top-%d", exc, top_n)
        return candidates[:top_n]

    # Stable sort: by score desc, ties broken by original index so
    # the bi-encoder ordering is preserved within score buckets.
    indexed = list(enumerate(candidates))
    indexed.sort(
        key=lambda pair: (-scores.get(pair[0], 0.0), pair[0]),
    )
    selected = [doc for _, doc in indexed[:top_n]]
    # Stamp the rerank score into metadata so downstream components
    # (UI, logging, evals) can inspect it.
    for original_index, doc in indexed[:top_n]:
        doc.metadata["rerank_score"] = float(scores.get(original_index, 0.0))
    logger.info(
        "Reranker: %d -> %d, top score=%.1f, threshold=%.1f",
        len(candidates),
        len(selected),
        max(scores.values(), default=0.0),
        scores.get(indexed[top_n - 1][0], 0.0) if len(indexed) >= top_n else 0.0,
    )
    return selected


def _build_user_prompt(query: str, candidates: list[LCDocument]) -> str:
    """Pack the query + candidates into the LLM input.

    Each candidate is truncated to ~400 chars — the reranker only
    needs enough text to judge relevance, and shorter prompts ship
    faster while keeping cost predictable.
    """
    lines = [f"Question: {query}", "", "Candidates:"]
    for index, doc in enumerate(candidates):
        body = doc.page_content.strip().replace("\n", " ")
        if len(body) > 400:
            body = body[:400] + "…"
        source = doc.metadata.get("source_file", "")
        lines.append(f"{index}: [{source}] {body}")
    return "\n".join(lines)


def _parse_scores(text: str, n_candidates: int) -> dict[int, float]:
    """Pull the score map out of the LLM response.

    Returns ``{candidate_index: score}``. Indices not present in the
    response are treated as score 0 by the caller.
    """
    match = _JSON_RE.search(text.strip())
    if not match:
        raise ValueError("reranker returned no JSON object")
    payload = json.loads(match.group(0))
    raw_scores = payload.get("scores")
    if not isinstance(raw_scores, list):
        raise ValueError("reranker JSON missing 'scores' array")

    scores: dict[int, float] = {}
    for entry in raw_scores:
        if not isinstance(entry, dict):
            continue
        try:
            idx = int(entry.get("id"))
            score = float(entry.get("score", 0.0))
        except (TypeError, ValueError):
            continue
        if 0 <= idx < n_candidates:
            scores[idx] = max(0.0, min(10.0, score))
    return scores


__all__ = ["rerank"]
