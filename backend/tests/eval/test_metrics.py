"""Unit tests for the pure metric functions.

These tests guarantee the formulas are right — any later change to the
eval harness is checked against the known math below.
"""

from __future__ import annotations

import math

import pytest

from tests.eval.metrics import (
    aggregate,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
)


class TestRecallAtK:
    def test_all_relevant_retrieved(self):
        assert recall_at_k(["a", "b", "c"], ["a", "b"], k=3) == 1.0

    def test_partial_recall(self):
        # 1 of 2 relevant chunks in top-2.
        assert recall_at_k(["a", "x"], ["a", "b"], k=2) == 0.5

    def test_zero_when_none_retrieved(self):
        assert recall_at_k(["x", "y"], ["a", "b"], k=2) == 0.0

    def test_empty_relevant_is_one(self):
        # Refusal questions have no relevant chunks — retrieval must not
        # be penalised for returning unrelated chunks.
        assert recall_at_k(["x", "y"], [], k=5) == 1.0

    def test_k_larger_than_retrieved(self):
        assert recall_at_k(["a"], ["a", "b"], k=10) == 0.5

    def test_k_zero_returns_zero(self):
        assert recall_at_k(["a"], ["a"], k=0) == 0.0


class TestPrecisionAtK:
    def test_all_relevant_in_top_k(self):
        assert precision_at_k(["a", "b", "c"], ["a", "b", "c"], k=3) == 1.0

    def test_half_relevant(self):
        assert precision_at_k(["a", "x", "b", "y"], ["a", "b"], k=4) == 0.5

    def test_empty_retrieved(self):
        assert precision_at_k([], ["a"], k=3) == 0.0


class TestReciprocalRank:
    def test_first_hit_is_one(self):
        assert reciprocal_rank(["a", "b"], ["a"]) == 1.0

    def test_second_hit_is_half(self):
        assert reciprocal_rank(["x", "a"], ["a"]) == 0.5

    def test_no_hit_is_zero(self):
        assert reciprocal_rank(["x", "y"], ["a"]) == 0.0


class TestNdcgAtK:
    def test_perfect_ranking_is_one(self):
        assert ndcg_at_k(["a", "b", "c"], ["a", "b", "c"], k=3) == pytest.approx(1.0)

    def test_reversed_ranking_less_than_perfect(self):
        # Only 1 relevant chunk out of 3 slots; still a valid nDCG value.
        assert 0 < ndcg_at_k(["x", "y", "a"], ["a"], k=3) < 1.0

    def test_known_value_single_relevant_rank_two(self):
        # relevant at rank 2 -> DCG = 1/log2(3); IDCG = 1/log2(2) = 1.
        expected = 1.0 / math.log2(3)
        assert ndcg_at_k(["x", "a"], ["a"], k=2) == pytest.approx(expected)

    def test_empty_relevant_is_zero(self):
        # The "refusal" case is handled separately by recall; nDCG is 0.
        assert ndcg_at_k(["x", "y"], [], k=3) == 0.0


class TestAggregate:
    def test_mean(self):
        assert aggregate([1.0, 0.5, 0.0]) == pytest.approx(0.5)

    def test_empty(self):
        assert aggregate([]) == 0.0
