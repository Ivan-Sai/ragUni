"""End-to-end baseline builder for the retrieval-eval suite.

What it does
============

1. Uploads a fixed set of schedule / session PDFs through the admin
   API (so they go through the production ingest pipeline:
   classify → contextualise → extract → chunk → embed).
2. For each pre-defined test question, queries MongoDB directly to
   find the chunks that contain the answer (by structured-record
   audience match for schedules, by text substring for prose docs).
3. Writes those chunk IDs into ``backend/tests/eval/dataset.jsonl``.
4. Runs ``backend/tests/eval/run_retrieval.py`` which scores the
   live retriever against the dataset and produces aggregate metrics.
5. Saves those metrics into ``backend/tests/eval/baseline.json`` so
   ``test_retrieval_meets_baseline`` has a concrete floor to gate
   against.

Run only after wipe_chunks.py — the script assumes a clean corpus.

Usage::

    cd /c/Users/vania/ragUni && python scripts/build_eval_baseline.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import httpx

# Backend imports
_REPO = Path(__file__).resolve().parent.parent
_BACKEND = _REPO / "backend"
sys.path.insert(0, str(_BACKEND))


BASE = "http://127.0.0.1:8000/api/v1"
ADMIN_EMAIL = "admin@test.com"
ADMIN_PASSWORD = "AdminPass1234"

DOWNLOADS = Path(r"C:\Users\vania\Downloads")

# Each entry: (filename, access_level)
PDFS_TO_UPLOAD: list[tuple[str, str]] = [
    ("F7-KI-_123-KI-2025-2026_2-sem-1_2.pdf", "public"),
    ("E6_PFNM_1_kurs_bakalavr_105_PFNM_2_kurs_bakalavr_2025_2026_2_sem-1.pdf", "public"),
    ("105_PFNM_3_4_kurs_bakalavr_2025_2026_2_sem-1_2.pdf", "public"),
    ("G5_EEKPTR_172_TKRT_bakalavr_2025_2026_2_sem-1_2.pdf", "public"),
    ("G5_EEKPTR_172_TKRT_magistry_2025_2026_2_sem_2.pdf", "public"),
    ("20-11-2025-GRAFIK-sesiyi-ZALIKY-2025-2026-n.r.-1-semestr-1-4-bak.-1-2-mag.pdf", "public"),
    ("GRAFIK-SESIYI-magistry-2-kurs-2-semestr-2025-2026-n.r (1).pdf", "public"),
]


@dataclass
class TestCase:
    """One eval entry — question + ground-truth filter for finding chunks."""

    question: str
    gold_answer: str
    role: str
    tags: list[str]
    # MongoDB filter applied to ``document_chunks`` to find the
    # chunks whose contents constitute the ground-truth answer.
    chunk_filter: dict[str, Any]
    # Hard cap on how many ground-truth chunks we keep — picking
    # the top N by (filter match) for sparse cases. None = all.
    limit: Optional[int] = 10


# Test questions — designed to be diverse across:
#   - Faculty-wide schedule types (regular schedule vs session zaliky)
#   - Specialities (KI, PFNM, TKRT)
#   - Levels (bachelor, master)
#   - Days of the week
#   - Subject lookup vs day lookup vs teacher lookup
#
# Ground-truth chunks are identified by Mongo filter on TOP-LEVEL
# fields stamped by the schedule extractor (group_label, year_label,
# level_label, doc_type, source_file). Day / subject / teacher live
# inside the chunk's text body (formatted as ``; day: X; time: Y;``)
# so we use a ``text`` regex match for those.
TEST_CASES: list[TestCase] = [
    # ---- Subject lookup (the strong path: subject names are
    # distinctive enough that pure vector retrieval handles them well).
    TestCase(
        question="Коли проводиться Програмування вбудованих систем у групи СА бакалаври 4 курс?",
        gold_answer="Програмування вбудованих систем у середу — лекція о 12:20–13:05 та лабораторна о 14:05–14:50.",
        role="student",
        tags=["subject", "schedule"],
        chunk_filter={
            "doc_type": "schedule",
            "text": {"$regex": "вбудованих систем", "$options": "i"},
        },
    ),
    TestCase(
        question="Технології проектування комп'ютерних систем — викладач і час",
        gold_answer="Технології проектування комп'ютерних систем веде Барабанов О.В. (лекція в четвер).",
        role="student",
        tags=["teacher", "schedule"],
        chunk_filter={
            "doc_type": "schedule",
            "text": {"$regex": "проектування комп", "$options": "i"},
        },
        limit=5,
    ),
    TestCase(
        question="Інтерфейси систем обміну даними розклад",
        gold_answer="Інтерфейси систем обміну даними — лекція у вівторок 10:35–11:20, викладач Бойко Ю.В.",
        role="student",
        tags=["subject", "schedule"],
        chunk_filter={
            "doc_type": "schedule",
            "text": {"$regex": "Інтерфейси систем обміну даними", "$options": "i"},
        },
        limit=5,
    ),
    TestCase(
        question="Розробка інтерфейсів користувача — коли і де",
        gold_answer="Розробка інтерфейсів користувача — лабораторна у понеділок 10:35–11:20.",
        role="student",
        tags=["subject", "schedule"],
        chunk_filter={
            "doc_type": "schedule",
            "text": {"$regex": "Розробка інтерфейсів користувача", "$options": "i"},
        },
        limit=5,
    ),
    TestCase(
        question="Мікропроцесорна техніка — розклад занять",
        gold_answer="Мікропроцесорна техніка — лекція у четвер та лабораторна у вівторок.",
        role="student",
        tags=["subject", "schedule"],
        chunk_filter={
            "doc_type": "schedule",
            "text": {"$regex": "Мікропроцесорна техніка", "$options": "i"},
        },
        limit=5,
    ),
    TestCase(
        question="Периферійні пристрої — коли пара",
        gold_answer="Периферійні пристрої — лабораторна у понеділок 12:20–13:05, лекція у середу.",
        role="student",
        tags=["subject", "schedule"],
        chunk_filter={
            "doc_type": "schedule",
            "text": {"$regex": "Периферійні пристрої", "$options": "i"},
        },
        limit=5,
    ),

    # ---- Source-anchored queries (specific PDF filename / specialty).
    # ``limit=5`` matches the retriever's k so a perfect retrieval
    # gives recall=1.0 (otherwise we'd compare top-5 against 100+
    # ground-truth chunks and recall caps out near zero).
    TestCase(
        question="графік заліків для бакалаврів 2025-2026",
        gold_answer="Графік заліків для бакалаврів 1-4 курс та магістрів наведено у відповідному документі.",
        role="student",
        tags=["session", "exam"],
        chunk_filter={
            "source_file": {"$regex": "GRAFIK.*ZALIKY", "$options": "i"},
        },
        limit=5,
    ),
    TestCase(
        question="розклад спеціальність 105 ПФНМ 1 курс бакалавр",
        gold_answer="Розклад для 1 курсу спеціальності 105 ПФНМ наведено у документі E6_PFNM_1_kurs_bakalavr.",
        role="student",
        tags=["schedule", "specialty"],
        chunk_filter={
            "source_file": {"$regex": "PFNM_1_kurs_bakalavr", "$options": "i"},
        },
        limit=5,
    ),
    TestCase(
        question="розклад спеціальність 105 ПФНМ 3 4 курс бакалавр",
        gold_answer="Розклад для 3 і 4 курсу спеціальності 105 ПФНМ наведено у документі 105_PFNM_3_4_kurs.",
        role="student",
        tags=["schedule", "specialty"],
        chunk_filter={
            "source_file": {"$regex": "PFNM_3_4_kurs", "$options": "i"},
        },
        limit=5,
    ),
    TestCase(
        question="розклад магістрів 172 ТКРТ телекомунікації",
        gold_answer="Розклад магістрів спеціальності 172 ТКРТ наведено у документі G5_EEKPTR_172_TKRT_magistry.",
        role="student",
        tags=["schedule", "master"],
        chunk_filter={
            "source_file": {"$regex": "TKRT_magistry", "$options": "i"},
        },
        limit=5,
    ),
    TestCase(
        question="розклад бакалаврів 172 ТКРТ телекомунікації радіотехніка",
        gold_answer="Розклад бакалаврів спеціальності 172 ТКРТ наведено у документі G5_EEKPTR_172_TKRT_bakalavr.",
        role="student",
        tags=["schedule", "bachelor"],
        chunk_filter={
            "source_file": {"$regex": "TKRT_bakalavr", "$options": "i"},
        },
        limit=5,
    ),
    TestCase(
        question="графік сесії магістрів 2 курс 2 семестр",
        gold_answer="Графік сесії для магістрів 2 курсу другого семестру наведено у документі GRAFIK-SESIYI-magistry-2-kurs.",
        role="student",
        tags=["session", "master"],
        chunk_filter={
            "source_file": {"$regex": "SESIYI-magistry-2-kurs", "$options": "i"},
        },
        limit=5,
    ),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def out(msg: str) -> None:
    sys.stdout.buffer.write((msg + "\n").encode("utf-8"))
    sys.stdout.flush()


async def admin_login(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        f"{BASE}/auth/login",
        data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


async def get_first_faculty(client: httpx.AsyncClient, token: str) -> dict:
    resp = await client.get(
        f"{BASE}/dictionaries/faculties",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    faculties = resp.json()
    if not faculties:
        raise RuntimeError("No faculties in dictionary — create one first")
    return faculties[0]


async def upload_pdf(
    client: httpx.AsyncClient, token: str, pdf_path: Path, faculty_id: str
) -> dict:
    files = {"file": (pdf_path.name, pdf_path.read_bytes(), "application/pdf")}
    data = {
        "access_level": "public",
        "faculty_id": faculty_id,
        "target_group_ids": "[]",
        "target_years": "[]",
    }
    resp = await client.post(
        f"{BASE}/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
        data=data,
        timeout=600.0,
    )
    resp.raise_for_status()
    return resp.json()


def find_relevant_chunks(test_case: TestCase) -> list[str]:
    """Look up ground-truth chunk IDs for a test case via direct
    Mongo query. Returns at most ``test_case.limit`` chunk _id
    strings, picked in insertion order so the IDs are stable."""
    from app.config import get_settings
    from pymongo import MongoClient

    s = get_settings()
    client = MongoClient(s.mongodb_url)
    try:
        coll = client[s.mongodb_db_name]["document_chunks"]
        cursor = coll.find(test_case.chunk_filter, {"_id": 1})
        if test_case.limit:
            cursor = cursor.limit(test_case.limit)
        return [str(d["_id"]) for d in cursor]
    finally:
        client.close()


def write_dataset(entries: list[dict]) -> Path:
    """Write the dataset.jsonl with the freshly-discovered chunk IDs."""
    path = _BACKEND / "tests" / "eval" / "dataset.jsonl"
    lines = [
        "# ragUni evaluation dataset — JSONL.",
        "# Lines starting with \"#\" are comments and blank lines are skipped.",
        "#",
        "# Each record:",
        "#   question         - natural-language question (uk or en)",
        "#   relevant_chunks  - IDs of chunks that contain the answer",
        "#   gold_answer      - concise human reference answer",
        "#   faculty          - faculty scope (null = university-wide)",
        "#   role             - role the question is asked under",
        "#   tags             - free-form labels: \"factual\", \"temporal\", \"access\", ...",
        "#",
        "# Generated by scripts/build_eval_baseline.py — re-run that script",
        "# after a corpus change to refresh the chunk IDs.",
        "",
    ]
    for entry in entries:
        lines.append(json.dumps(entry, ensure_ascii=False))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out(f"Wrote {path}")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main(skip_upload: bool = False) -> int:
    if skip_upload:
        out("=== STAGE 1: SKIPPED (--skip-upload) ===")
    else:
        out("=== STAGE 1: Upload PDFs through the admin API ===")
        async with httpx.AsyncClient() as client:
            token = await admin_login(client)
            out(f"  admin login OK")
            faculty = await get_first_faculty(client, token)
            out(f"  faculty: {faculty['name']} ({faculty['id']})")

            for fname, _ in PDFS_TO_UPLOAD:
                path = DOWNLOADS / fname
                if not path.exists():
                    out(f"  SKIP missing: {fname}")
                    continue
                out(f"  uploading {fname} ({path.stat().st_size // 1024} KB)…")
                result = await upload_pdf(client, token, path, faculty["id"])
                out(
                    f"    chunks={result['total_chunks']}  "
                    f"id={result['id']}"
                )

    out("\n=== STAGE 2: Build dataset.jsonl ===")
    entries: list[dict] = []
    skipped = 0
    for tc in TEST_CASES:
        relevant = find_relevant_chunks(tc)
        if not relevant:
            out(f"  SKIP no chunks for: {tc.question[:60]!r}")
            skipped += 1
            continue
        out(f"  {len(relevant)} chunks for: {tc.question[:60]}")
        entries.append({
            "question": tc.question,
            "relevant_chunks": relevant,
            "gold_answer": tc.gold_answer,
            "faculty": None,
            "role": tc.role,
            "tags": tc.tags,
        })
    out(f"\n  total dataset entries: {len(entries)}   skipped: {skipped}")
    if not entries:
        out("ERROR: no dataset entries built — aborting")
        return 1
    write_dataset(entries)

    out("\n=== STAGE 3: Run retrieval evaluation ===")
    from tests.eval.metrics import (
        aggregate, ndcg_at_k, precision_at_k, recall_at_k, reciprocal_rank,
    )
    from tests.eval.loader import load_entries
    from tests.eval.run_retrieval import _retrieve

    k = 5
    loaded = load_entries()
    recalls, precisions, mrrs, ndcgs = [], [], [], []
    for entry in loaded:
        retrieved, took = await _retrieve(entry.question, entry.role, entry.faculty, k)
        recalls.append(recall_at_k(retrieved, entry.relevant_chunks, k))
        precisions.append(precision_at_k(retrieved, entry.relevant_chunks, k))
        mrrs.append(reciprocal_rank(retrieved, entry.relevant_chunks))
        ndcgs.append(ndcg_at_k(retrieved, entry.relevant_chunks, k))
        out(
            f"  Q: {entry.question[:60]}  "
            f"R@{k}={recalls[-1]:.2f}  P@{k}={precisions[-1]:.2f}  "
            f"RR={mrrs[-1]:.2f}  nDCG@{k}={ndcgs[-1]:.2f}  ({took:.0f} ms)"
        )

    aggregates = {
        f"recall_at_{k}": round(aggregate(recalls), 3),
        f"precision_at_{k}": round(aggregate(precisions), 3),
        "mrr": round(aggregate(mrrs), 3),
        f"ndcg_at_{k}": round(aggregate(ndcgs), 3),
    }
    out(f"\n  aggregate: {json.dumps(aggregates, indent=2)}")

    out("\n=== STAGE 4: Save baseline.json ===")
    # Set thresholds to 0.9× the observed metrics — gives a small
    # tolerance band for natural fluctuation while still catching
    # genuine regressions. Round to 2 decimals so the JSON stays
    # human-readable.
    thresholds = {
        metric: round(value * 0.9, 2) if value > 0 else 0.0
        for metric, value in aggregates.items()
    }
    baseline = {
        "_comment": (
            "Frozen baseline — generated by scripts/build_eval_baseline.py "
            "against a corpus of 7 schedule/session PDFs. Thresholds are "
            "set to 90% of the observed metrics so CI catches genuine "
            "regression while tolerating embedding non-determinism."
        ),
        "k": k,
        "observed": aggregates,
        "thresholds": thresholds,
    }
    baseline_path = _BACKEND / "tests" / "eval" / "baseline.json"
    baseline_path.write_text(
        json.dumps(baseline, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    out(f"  wrote {baseline_path}")
    out(json.dumps(baseline, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip the PDF upload stage — useful when re-running to "
        "rebuild dataset.jsonl + baseline against an already-loaded "
        "corpus.",
    )
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(skip_upload=args.skip_upload)))
