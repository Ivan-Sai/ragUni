"""Re-embed every existing chunk with the E5 ``passage:`` prefix.

Why this exists
===============

The retrieval-side wrapper ``_E5PrefixedEmbeddings`` always prepends
``query:`` to user queries (good — it's what E5 was trained for). But
on early ingest runs the wrapper was missing, so chunks landed in
Atlas as embeddings of the raw text, NOT ``"passage: " + text``.

Until those chunks are re-embedded the query and passage live in
slightly different sub-spaces of the model. Cosine still scores
above 0.5, so retrieval doesn't fail outright — it just silently
hurts ranking by ~10-15 percentage points on the dev set.

This script walks ``document_chunks`` in batches, recomputes the
embedding for every chunk that does not yet carry the
``e5_prefix_version`` marker, writes the new vector + the marker
back, and moves on. Safe to run multiple times — already-marked
chunks are skipped. Safe to interrupt — the next run resumes where
the previous one stopped because the marker is per-chunk.

Usage
-----

    cd backend && python -m scripts.reindex_e5_passage_prefix \\
        [--batch-size 100] [--limit 0]

Output: per-batch progress and a final summary line.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Make backend imports work when run from project root or backend/.
_BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.config import get_settings  # noqa: E402
from app.services.vector_store import _E5PrefixedEmbeddings  # noqa: E402

# Marker stamped on every chunk after re-embedding. Bump the value
# whenever the prefix scheme changes so a future migration can
# re-process only the previous-generation chunks.
PREFIX_VERSION = "e5-passage-v1"

logger = logging.getLogger("reindex_e5")


async def reindex(batch_size: int = 100, limit: int = 0) -> int:
    """Re-embed chunks lacking ``e5_prefix_version``. Returns count.

    The function intentionally uses the synchronous pymongo client
    that LangChain wraps — Motor isn't needed here, the script is
    a one-shot maintenance task and the simpler client gives us
    direct cursor control.
    """
    from pymongo import MongoClient  # local import keeps top tidy

    settings = get_settings()
    client: MongoClient = MongoClient(settings.mongodb_url)
    coll = client[settings.mongodb_db_name]["document_chunks"]

    embedder = _E5PrefixedEmbeddings(model_name=settings.embedding_model)

    query: dict = {
        "$or": [
            {"e5_prefix_version": {"$exists": False}},
            {"e5_prefix_version": {"$ne": PREFIX_VERSION}},
        ]
    }
    total_to_process = coll.count_documents(query)
    logger.info("Found %d chunks lacking %s marker", total_to_process, PREFIX_VERSION)
    if total_to_process == 0:
        return 0

    cap = limit if limit > 0 else total_to_process
    target = min(total_to_process, cap)

    cursor = coll.find(query, {"text": 1}).batch_size(batch_size)

    processed = 0
    pending_ids: list = []
    pending_texts: list[str] = []

    def flush() -> None:
        nonlocal processed
        if not pending_ids:
            return
        # embed_documents already prepends the "passage: " prefix.
        vectors = embedder.embed_documents(pending_texts)
        for chunk_id, vector in zip(pending_ids, vectors):
            coll.update_one(
                {"_id": chunk_id},
                {
                    "$set": {
                        "embedding": vector,
                        "e5_prefix_version": PREFIX_VERSION,
                    }
                },
            )
        processed += len(pending_ids)
        logger.info("Re-embedded %d / %d", processed, target)
        pending_ids.clear()
        pending_texts.clear()

    try:
        for doc in cursor:
            text = doc.get("text") or ""
            if not text.strip():
                # Skip empty chunks — mark them so we don't keep
                # revisiting them on every run.
                coll.update_one(
                    {"_id": doc["_id"]},
                    {"$set": {"e5_prefix_version": PREFIX_VERSION}},
                )
                processed += 1
                continue
            pending_ids.append(doc["_id"])
            pending_texts.append(text)
            if len(pending_ids) >= batch_size:
                flush()
            if processed >= cap:
                break
        flush()
    finally:
        client.close()

    logger.info("Done. Re-embedded %d chunks.", processed)
    return processed


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Chunks per embedding batch (default: 100)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Stop after N chunks (0 = no cap, default)",
    )
    p.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    n = asyncio.run(reindex(batch_size=args.batch_size, limit=args.limit))
    return 0 if n >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
