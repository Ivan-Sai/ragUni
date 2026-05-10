"""Integrity + schema tests for the eval dataset.

These tests don't run retrieval — that needs a populated MongoDB
corpus. What they DO ensure:

* Every entry parses, has the required fields and recognised tags.
* No two entries share the same question (would skew aggregates).
* Either ``relevant_chunks`` is non-empty OR the ``refusal`` tag is
  present — silently empty positive examples produce inflated scores.
* The placeholder chunk IDs (``TBD_chunk_*``) are flagged so that
  CI surfaces "your eval dataset still uses placeholders" the moment
  someone attempts to use it for real measurements.

When the real chunk IDs land, drop ``TestPlaceholderMarker.test_no_placeholders``
or convert it from xfail to a hard assertion.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


_DATASET = Path(__file__).parent / "dataset.jsonl"

_REQUIRED_FIELDS = {
    "question",
    "relevant_chunks",
    "gold_answer",
    "role",
    "tags",
}

_KNOWN_ROLES = {"student", "teacher", "admin"}


def _entries() -> list[dict]:
    """Parse the dataset, skipping comment / blank lines."""
    out: list[dict] = []
    for line in _DATASET.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        out.append(json.loads(line))
    return out


class TestSchema:

    def test_dataset_is_present(self):
        assert _DATASET.exists(), f"Eval dataset missing at {_DATASET}"

    def test_every_entry_has_required_fields(self):
        for i, entry in enumerate(_entries()):
            missing = _REQUIRED_FIELDS - set(entry.keys())
            assert not missing, f"entry #{i} missing fields {missing}: {entry}"

    def test_role_is_recognised(self):
        for i, entry in enumerate(_entries()):
            assert entry["role"] in _KNOWN_ROLES, (
                f"entry #{i} has unknown role {entry['role']!r}"
            )

    def test_relevant_chunks_is_list(self):
        for i, entry in enumerate(_entries()):
            assert isinstance(entry["relevant_chunks"], list), (
                f"entry #{i} relevant_chunks is not a list"
            )

    def test_questions_are_unique(self):
        questions = [e["question"] for e in _entries()]
        seen: set[str] = set()
        dups: list[str] = []
        for q in questions:
            if q in seen:
                dups.append(q)
            seen.add(q)
        assert not dups, f"duplicate questions in dataset: {dups}"


class TestSemantic:

    def test_empty_relevant_chunks_only_for_refusal(self):
        for i, entry in enumerate(_entries()):
            if not entry["relevant_chunks"]:
                tags = set(entry.get("tags") or [])
                assert "refusal" in tags or "out-of-scope" in tags, (
                    f"entry #{i} has empty relevant_chunks but is not "
                    f"tagged as refusal/out-of-scope"
                )


class TestPlaceholderMarker:
    """Reject any future re-introduction of TBD placeholder chunk IDs.

    The dataset is populated with real chunk ``_id`` strings (see
    ``scripts/build_eval_baseline.py``). If a regression / mistake
    re-adds a placeholder (``TBD_chunk_*``), this test fails loudly
    so the maintainer knows to refresh the dataset against a real
    corpus before trusting the retrieval metrics.
    """

    def test_no_placeholders(self):
        bad: list[str] = []
        for entry in _entries():
            for cid in entry["relevant_chunks"]:
                if isinstance(cid, str) and cid.startswith("TBD_"):
                    bad.append(cid)
        assert not bad, f"placeholder chunk IDs still present: {bad}"
