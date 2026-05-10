"""Retrieval orchestrator — multi-strategy search + RRF + rerank.

Why this exists
===============

Modern production RAG (Glean, Notion AI, Perplexity Spaces) does not
hand the user's raw query to a single search engine. Instead the
question goes through several specialised retrievers in parallel and
the candidates are merged before being shown to the LLM:

* **Structured** — entity-driven Mongo lookup (`day`, `subject`,
  `teacher`...). Fast, exact, produces full audience-correct slices.
* **Vector** — semantic similarity. Catches paraphrases, synonyms,
  and queries with no extracted entities.
* **Lexical / hybrid** — full-text BM25 fused with vector via
  Reciprocal Rank Fusion. Strong on rare terms, surnames, document
  titles that embeddings under-weight.

The orchestrator runs whichever strategies the analyzer flagged as
relevant, **fuses their results via RRF**, optionally **reranks**
with the LLM cross-encoder, and returns a single ordered list of
chunks the answer-generator can consume. A failed strategy collapses
gracefully — the orchestrator logs and falls through to the others.

Output
------

``RetrievalResult.docs`` are LangChain ``Document`` objects, ready to
be formatted by ``chat.format_docs``. ``structured_records`` carries
the matched records when the structured branch ran (used to render
source citations).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from langchain_core.documents import Document as LCDocument

from app.config import get_settings
from app.services.query_analyzer import QueryAnalysis
from app.services.reranker import rerank
from app.services.structured_retriever import (
    fetch_structured_records,
    format_records_as_context,
)
from app.services.vector_store import vector_store_service

logger = logging.getLogger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class RetrievalResult:
    """Output of one orchestrator run."""

    docs: list[LCDocument] = field(default_factory=list)
    structured_records: list[dict[str, Any]] = field(default_factory=list)
    used_strategies: list[str] = field(default_factory=list)
    # Stats kept for logs / future evaluation harness.
    counts_per_strategy: dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------


_RRF_K = 60.0


def _rrf_merge(
    rankings: list[list[LCDocument]],
    *,
    keyer=lambda doc: (
        doc.metadata.get("source_file", ""),
        doc.metadata.get("chunk_index", -1),
    ),
) -> list[LCDocument]:
    """Reciprocal Rank Fusion — the standard ensemble for hybrid IR.

    Given multiple ranked lists of the SAME chunks (each list's order
    reflecting one strategy's confidence), assigns each chunk a score
    of ``Σ 1/(k+rank_i)`` summed across lists where it appears, with
    ``k=60`` (Wikipedia / TREC convention). Higher is better.

    Why not just concat? Concat doesn't compare strategies — vector's
    1st place and BM25's 1st place look the same as vector's 30th.
    RRF picks the consensus winners.
    """
    seen: dict[Any, dict[str, Any]] = {}
    for ranked_list in rankings:
        for rank, doc in enumerate(ranked_list, start=1):
            key = keyer(doc)
            entry = seen.setdefault(key, {"doc": doc, "score": 0.0})
            entry["score"] += 1.0 / (_RRF_K + rank)
    fused = sorted(seen.values(), key=lambda e: e["score"], reverse=True)
    return [entry["doc"] for entry in fused]


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


async def _run_structured(
    analysis: QueryAnalysis,
    user_kwargs: dict[str, Any],
) -> tuple[list[LCDocument], list[dict[str, Any]]]:
    """Convert structured records into Document objects compatible with
    the answer pipeline. We keep the raw records too because the UI
    renders different source-citation cards for them.
    """
    records = await fetch_structured_records(analysis, **user_kwargs)
    if not records:
        return [], []

    docs: list[LCDocument] = []
    for index, record in enumerate(records, 1):
        body = "; ".join(
            f"{k}: {v}"
            for k, v in record.items()
            if not str(k).startswith("_") and v not in (None, "")
        )
        meta = {
            "source_file": record.get("_source_file", "structured-record"),
            "chunk_index": index - 1,
            "total_chunks": len(records),
            # Synthetic high score so RRF gives structured matches
            # priority — these records have already been validated
            # against the user's audience and entity filters.
            "score": 0.95,
            "retrieval_strategy": "structured",
        }
        docs.append(LCDocument(page_content=body, metadata=meta))
    return docs, records


async def _run_vector(
    query: str,
    pre_filter: Optional[dict[str, Any]],
    *,
    k: int,
) -> list[LCDocument]:
    """Pure vector similarity, hard-filtered by ``vector_score_threshold``.

    Atlas Vector Search returns ``k`` nearest neighbours by cosine
    similarity. Without a hard score floor a query like
    "what is the timetable?" still produces 20 results — but the bottom
    half score 0.4-0.5 (off-topic noise). Letting that noise into the
    LLM prompt is exactly how grounded RAG starts hallucinating: the
    no-answer guard fires only when the *max* score is below threshold,
    so a single 0.56 chunk passes 19 noise chunks through.

    Filtering at the orchestrator boundary means RRF fusion only ever
    sees defensible vector matches, the reranker has fewer adversarial
    inputs, and the LLM context stays clean.
    """
    timeout = float(settings.llm_timeout_seconds)
    try:
        scored = await asyncio.wait_for(
            vector_store_service.similarity_search_with_score(
                query=query, k=k, pre_filter=pre_filter or None,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("Vector retrieval timed out")
        return []

    threshold = float(settings.vector_score_threshold)
    docs: list[LCDocument] = []
    dropped = 0
    for doc, score in scored:
        score_f = float(score)
        if score_f < threshold:
            dropped += 1
            continue
        doc.metadata["score"] = score_f
        doc.metadata["retrieval_strategy"] = "vector"
        docs.append(doc)
    if dropped:
        logger.debug(
            "Vector retrieval: dropped %d/%d below threshold %.2f",
            dropped,
            len(scored),
            threshold,
        )
    return docs


async def _run_hybrid(
    query: str,
    pre_filter: Optional[dict[str, Any]],
    *,
    k: int,
) -> list[LCDocument]:
    """Hybrid (vector + full-text BM25) retrieval via Atlas. Returns
    empty list if the full-text index is missing — orchestrator then
    falls back to plain vector for that strategy."""
    try:
        retriever = vector_store_service.get_hybrid_retriever(
            k=k, pre_filter=pre_filter or None,
        )
        docs = await asyncio.wait_for(
            retriever.ainvoke(query),
            timeout=float(settings.llm_timeout_seconds),
        )
        for doc in docs:
            # RRF rank score is not comparable to cosine; strip it so
            # downstream code does not mistake it for a similarity.
            doc.metadata.pop("score", None)
            doc.metadata["retrieval_strategy"] = "lexical"
        return docs
    except (ValueError, RuntimeError) as exc:
        logger.info("Hybrid retrieval unavailable: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def retrieve(
    *,
    query: str,
    analysis: QueryAnalysis,
    pre_filter: Optional[dict[str, Any]],
    user_role: str,
    user_faculty_id: Optional[str],
    user_group_id: Optional[str],
    user_year: Optional[int],
    user_level: Optional[str],
    initial_k: int = 30,
    final_k: int = 15,
    use_reranker: bool = True,
) -> RetrievalResult:
    """Run the full multi-strategy retrieval pipeline.

    1. Picks strategies from ``analysis.preferred_strategies`` (always
       running structured when entities are present, even if not
       listed, to maximise recall).
    2. Runs strategies concurrently — they hit different indexes / API
       paths so they don't contend.
    3. Fuses the rankings with RRF.
    4. Optionally reranks the top-50 with the LLM cross-encoder.
    5. Truncates to ``final_k``.

    The reformulated query is preferred for embedding lookups because
    it has pronouns resolved and abbreviations expanded; the original
    query is used for the reranker (it judges intent against the
    user's actual words).
    """
    user_kwargs = dict(
        user_role=user_role,
        user_faculty_id=user_faculty_id,
        user_group_id=user_group_id,
        user_year=user_year,
        user_level=user_level,
    )

    embed_query = analysis.reformulated_query or query
    strategies = list(analysis.preferred_strategies) or ["vector"]

    # Always try structured when the analyzer extracted entities — it
    # is cheap, deterministic, and frequently the only path that
    # answers timetable / exam questions correctly.
    if any(analysis.entities.values()) and "structured" not in strategies:
        strategies = ["structured", *strategies]

    pending: list[asyncio.Task] = []
    if "structured" in strategies:
        pending.append(asyncio.create_task(_run_structured(analysis, user_kwargs)))
    if "vector" in strategies:
        pending.append(asyncio.create_task(_run_vector(embed_query, pre_filter, k=initial_k)))
    if "lexical" in strategies and settings.use_hybrid_search:
        pending.append(asyncio.create_task(_run_hybrid(embed_query, pre_filter, k=initial_k)))

    if not pending:
        return RetrievalResult()

    results = await asyncio.gather(*pending, return_exceptions=True)

    rankings: list[list[LCDocument]] = []
    structured_records: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    used: list[str] = []

    for strategy, result in zip(
        [s for s in ("structured", "vector", "lexical") if s in strategies and (s != "lexical" or settings.use_hybrid_search)],
        results,
    ):
        if isinstance(result, BaseException):
            logger.warning("Strategy %s raised: %s", strategy, result)
            continue
        if strategy == "structured":
            docs, records = result
            structured_records = records
            if docs:
                rankings.append(docs)
                used.append(strategy)
                counts[strategy] = len(docs)
        else:
            docs = result
            if docs:
                rankings.append(docs)
                used.append(strategy)
                counts[strategy] = len(docs)

    if not rankings:
        return RetrievalResult(used_strategies=used, counts_per_strategy=counts)

    fused = _rrf_merge(rankings)

    # Hard limit on what the reranker sees — ranking longer lists is
    # quadratic in cost, and beyond 50 candidates the marginal benefit
    # is small.
    fused = fused[:50]

    if use_reranker and len(fused) > final_k:
        fused = await rerank(query, fused, top_n=final_k)
    else:
        fused = fused[:final_k]

    logger.info(
        "Retrieval: strategies=%s counts=%s fused=%d structured=%d",
        used,
        counts,
        len(fused),
        len(structured_records),
    )
    return RetrievalResult(
        docs=fused,
        structured_records=structured_records,
        used_strategies=used,
        counts_per_strategy=counts,
    )


# ---------------------------------------------------------------------------
# Re-export for callers
# ---------------------------------------------------------------------------


def format_structured_context(records: list[dict[str, Any]]) -> str:
    """Convenience pass-through so callers don't need a second import."""
    return format_records_as_context(records)


__all__ = ["RetrievalResult", "retrieve", "format_structured_context"]
