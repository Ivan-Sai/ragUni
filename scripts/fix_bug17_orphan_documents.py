"""Fix BUG-17: remove legacy documents without extracted_text + orphan chunks.

BUG-17 reproduction (from docs/MANUAL_TESTING_REPORT.md):
    Newly uploaded documents preview correctly, but the pre-existing
    test_doc.txt returns 404 because it predates the ``extracted_text``
    field that was later added to the documents schema. The preview
    endpoint raises 404 when ``extracted_text`` is missing.

This is Variant A from the diploma discussion: delete legacy documents
that lack the field (preview was already broken for them anyway) and
clean up any orphan chunks whose document_id no longer resolves.

Usage::

    cd ragUni && python scripts/fix_bug17_orphan_documents.py        # dry-run
    cd ragUni && python scripts/fix_bug17_orphan_documents.py --apply
    cd ragUni && python scripts/fix_bug17_orphan_documents.py --apply --yes

Default mode is dry-run: prints what *would* be deleted without
touching the DB. ``--apply`` performs the deletion (still asks for
confirmation unless ``--yes`` is passed).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make backend imports work when run from project root.
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.config import get_settings  # noqa: E402


def _confirm(prompt: str) -> bool:
    answer = input(f"{prompt} [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually delete records (default is dry-run).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip the interactive confirmation prompt.",
    )
    args = parser.parse_args()

    from pymongo import MongoClient

    settings = get_settings()
    client: MongoClient = MongoClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]
    docs = db["documents"]
    chunks = db["document_chunks"]

    # --- Phase 1: find legacy documents lacking ``extracted_text``.
    legacy_filter = {
        "$or": [
            {"extracted_text": {"$exists": False}},
            {"extracted_text": None},
            {"extracted_text": ""},
        ]
    }
    legacy_ids = [d["_id"] for d in docs.find(legacy_filter, {"_id": 1})]
    legacy_id_strs = {str(_id) for _id in legacy_ids}
    print(f"Legacy documents (missing extracted_text): {len(legacy_ids)}")
    if legacy_ids:
        sample = docs.find({"_id": {"$in": legacy_ids[:5]}}, {"filename": 1, "_id": 1})
        for d in sample:
            print(f"  - {d.get('filename', '<no name>')} ({d['_id']})")
        if len(legacy_ids) > 5:
            print(f"  ... and {len(legacy_ids) - 5} more")

    # --- Phase 2: count orphan chunks (document_id no longer resolves).
    all_doc_id_strs = {str(_id) for _id in docs.distinct("_id")}
    chunk_doc_ids = set(chunks.distinct("document_id"))
    orphan_doc_ids = chunk_doc_ids - all_doc_id_strs
    # After phase-1 deletion the legacy docs also become orphan-producers.
    orphan_after_phase1 = orphan_doc_ids | legacy_id_strs
    orphan_chunk_count = chunks.count_documents(
        {"document_id": {"$in": list(orphan_after_phase1)}}
    )
    print(f"Orphan chunks (after legacy doc removal): {orphan_chunk_count}")

    if not args.apply:
        print("\nDRY-RUN — nothing deleted. Pass --apply to actually delete.")
        client.close()
        return 0

    if not legacy_ids and orphan_chunk_count == 0:
        print("\nNothing to clean up.")
        client.close()
        return 0

    if not args.yes and not _confirm("Proceed with deletion?"):
        print("Aborted.")
        client.close()
        return 1

    # --- Phase 3: actually delete.
    if legacy_ids:
        doc_result = docs.delete_many({"_id": {"$in": legacy_ids}})
        print(f"Deleted {doc_result.deleted_count} legacy documents")

    if orphan_after_phase1:
        chunk_result = chunks.delete_many(
            {"document_id": {"$in": list(orphan_after_phase1)}}
        )
        print(f"Deleted {chunk_result.deleted_count} orphan chunks")

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
