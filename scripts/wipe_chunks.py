"""Wipe the document_chunks collection (and optionally documents).

Used as a quick alternative to ``reindex_e5_passage_prefix.py`` when
the corpus is small / disposable: instead of re-embedding existing
chunks we just delete them all and re-upload the documents through
the API. New uploads automatically use the correct ``passage:``
prefix because the wrapper sits on the ingest path now.

Usage::

    cd backend && python -m scripts.wipe_chunks
    cd backend && python -m scripts.wipe_chunks --include-documents
    cd backend && python -m scripts.wipe_chunks --yes  # skip prompt

Always asks for confirmation unless ``--yes`` is passed.
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
        "--include-documents",
        action="store_true",
        help="Also wipe the documents collection (default: chunks only).",
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

    chunks = db["document_chunks"]
    chunk_count = chunks.count_documents({})

    docs_count = 0
    if args.include_documents:
        docs = db["documents"]
        docs_count = docs.count_documents({})

    print(f"About to delete {chunk_count} chunks from {settings.mongodb_db_name}.document_chunks")
    if args.include_documents:
        print(f"AND {docs_count} documents from {settings.mongodb_db_name}.documents")
    if not args.yes and not _confirm("Proceed?"):
        print("Aborted.")
        return 1

    chunks_result = chunks.delete_many({})
    print(f"Deleted {chunks_result.deleted_count} chunks")
    if args.include_documents:
        docs_result = db["documents"].delete_many({})
        print(f"Deleted {docs_result.deleted_count} documents")

    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
