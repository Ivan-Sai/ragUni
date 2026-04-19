"""Pure functions that compute retrieval quality metrics.

These are intentionally dependency-free so they can be unit-tested in
isolation without a live vector store. Every function takes plain
sequences and returns a single float.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def recall_at_k(
    retrieved: Sequence[str],
    relevant: Sequence[str],
    k: int,
) -> float:
    """Fraction of ``relevant`` items present in the first ``k`` retrieved.

    Defined as 1.0 when ``relevant`` is empty — there is nothing to miss,
    so any retrieval trivially recalls everything.
    """
    if not relevant:
        return 1.0
    if k <= 0:
        return 0.0
    top_k = set(retrieved[:k])
    hits = sum(1 for r in relevant if r in top_k)
    return hits / len(relevant)


def precision_at_k(
    retrieved: Sequence[str],
    relevant: Sequence[str],
    k: int,
) -> float:
    """Fraction of the top-k that is relevant."""
    if k <= 0 or not retrieved:
        return 0.0
    relevant_set = set(relevant)
    top_k = retrieved[:k]
    hits = sum(1 for r in top_k if r in relevant_set)
    return hits / min(k, len(top_k))


def reciprocal_rank(
    retrieved: Sequence[str],
    relevant: Sequence[str],
) -> float:
    """1 / rank of the first relevant result, 0 if none found."""
    relevant_set = set(relevant)
    for rank, doc_id in enumerate(retrieved, start=1):
        if doc_id in relevant_set:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(
    retrieved: Sequence[str],
    relevant: Sequence[str],
    k: int,
) -> float:
    """Normalised discounted cumulative gain over the top-k.

    Binary relevance (1 if in ``relevant``, else 0) with the standard
    log2-based discount.
    """
    if k <= 0 or not relevant:
        return 0.0
    relevant_set = set(relevant)
    top_k = retrieved[:k]

    dcg = 0.0
    for rank, doc_id in enumerate(top_k, start=1):
        if doc_id in relevant_set:
            dcg += 1.0 / math.log2(rank + 1)

    ideal_hits = min(len(relevant_set), k)
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def aggregate(values: Sequence[float]) -> float:
    """Arithmetic mean. Returns 0.0 for an empty sequence."""
    if not values:
        return 0.0
    return sum(values) / len(values)
