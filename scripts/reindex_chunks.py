"""Re-embed every document's chunks with the current vector_store config.

Why this exists:
    The embedding model was switched to use E5 ``query:`` / ``passage:``
    prefixes. Documents indexed before that change live in MongoDB with
    embeddings that no longer match queries. Running this script wipes
    the chunk collection and re-embeds from each document's stored
    ``extracted_text``.

Usage:
    cd backend
    python ../scripts/reindex_chunks.py
    # or with a filter:
    python ../scripts/reindex_chunks.py --only filename.pdf

Idempotent: deletes existing chunks for the targeted documents before
inserting the new ones, so safe to re-run.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# Allow importing the FastAPI app from the scripts/ directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


async def main(filename_filter: str | None) -> None:
    from bson import ObjectId

    from app.config import get_settings
    from app.services.database import (
        close_mongo_connection,
        connect_to_mongo,
        get_database,
    )
    from app.services.vector_store import vector_store_service

    settings = get_settings()
    print(f"Embedding model: {settings.embedding_model}")
    print(f"Chunk size:      {settings.chunk_size}")
    print(f"Chunk overlap:   {settings.chunk_overlap}")
    print()

    await connect_to_mongo()
    vector_store_service.initialize()

    db = get_database()
    query: dict = {}
    if filename_filter:
        query["filename"] = filename_filter

    cursor = db.documents.find(query)
    documents = await cursor.to_list(length=None)
    if not documents:
        print("No documents matched the filter; nothing to do.")
        await close_mongo_connection()
        return

    total = len(documents)
    print(f"Re-embedding {total} document(s)…")

    started = time.time()
    for index, doc in enumerate(documents, start=1):
        filename = doc.get("filename", "<unknown>")
        text = doc.get("extracted_text")
        if not text or not text.strip():
            print(f"  [{index}/{total}] {filename!r}: skipped — no extracted_text")
            continue

        # 1. Wipe stale chunks for this document.
        deleted = await vector_store_service.delete_by_metadata(
            {"source_file": filename}
        )

        # 2. Re-embed using the document's existing metadata, with the
        #    document_id stamped into each chunk for clickable sources.
        metadata = dict(doc.get("metadata") or {})
        metadata.setdefault("source_file", filename)
        metadata.setdefault("file_type", doc.get("file_type", ""))
        metadata.setdefault("access_level", doc.get("access_level", "public"))
        metadata.setdefault("faculty", doc.get("faculty"))
        metadata["document_id"] = str(doc["_id"])

        chunk_ids = await vector_store_service.add_document_with_chunking(
            text,
            metadata,
            file_type=doc.get("file_type"),
        )

        # 3. Refresh the chunk_ids and total_chunks pointers on the
        #    parent document so the admin dashboard / preview reflect
        #    the new layout.
        await db.documents.update_one(
            {"_id": doc["_id"]},
            {
                "$set": {
                    "chunk_ids": chunk_ids,
                    "total_chunks": len(chunk_ids),
                    "metadata": metadata,
                }
            },
        )

        print(
            f"  [{index}/{total}] {filename!r}: deleted {deleted}, "
            f"inserted {len(chunk_ids)} chunks"
        )

    elapsed = time.time() - started
    print()
    print(f"Done in {elapsed:.1f}s.")

    await close_mongo_connection()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        dest="filename",
        default=None,
        help="Re-embed only the document with this exact filename.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    # Make sure required env vars are set; pydantic-settings will load
    # backend/.env automatically when run from backend/, but the script
    # may also be invoked from the project root.
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    args = _parse_args()
    asyncio.run(main(args.filename))
