"""Reset test data before switching to the faculty/group dictionary model.

Drops everything that depends on the old free-text ``faculty`` /
``group`` user fields:

* ``document_chunks``       — every embedded fragment.
* ``documents``             — document records.
* ``chat_history``          — citations reference deleted documents.
* ``feedback``              — same reason.
* ``analytics_events``      — keeps the dashboards consistent.
* every non-admin user      — students and teachers must re-register
                              against the new mandatory faculty / group
                              fields.

The admin account survives so the operator can still log in and seed
faculties + groups before reopening registration.

Run with ``python scripts/reset_for_dictionaries.py``. Asks for an
explicit ``yes`` confirmation because it is destructive.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Make ``backend.app`` importable when the script runs from the repo
# root. Mirrors the convention used by other scripts in this folder.
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.services.database import (  # noqa: E402  (path setup must run first)
    close_mongo_connection,
    connect_to_mongo,
    get_database,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("reset")


async def _wipe() -> None:
    db = get_database()

    chunks_count = await db.document_chunks.count_documents({})
    docs_count = await db.documents.count_documents({})
    history_count = await db.chat_history.count_documents({})
    feedback_count = await db.feedback.count_documents({})
    events_count = await db.analytics_events.count_documents({})
    users_to_drop = await db.users.count_documents({"role": {"$ne": "admin"}})
    admins = await db.users.count_documents({"role": "admin"})

    logger.info(
        "Will delete: %d chunks, %d documents, %d chat sessions, "
        "%d feedback rows, %d analytics events, %d non-admin users",
        chunks_count,
        docs_count,
        history_count,
        feedback_count,
        events_count,
        users_to_drop,
    )
    logger.info("Will keep: %d admin user(s)", admins)

    await db.document_chunks.delete_many({})
    await db.documents.delete_many({})
    await db.chat_history.delete_many({})
    await db.feedback.delete_many({})
    await db.analytics_events.delete_many({})
    await db.users.delete_many({"role": {"$ne": "admin"}})

    # Drop any leftover legacy fields on the surviving admin records so
    # the new schema is enforced uniformly. Admins do not need a
    # faculty/group, but if a previous run set free-text values they
    # would now confuse the type system.
    await db.users.update_many(
        {"role": "admin"},
        {"$unset": {"faculty": "", "group": ""}},
    )

    logger.info("Database reset complete")


async def main(skip_prompt: bool) -> int:
    if not skip_prompt:
        if not sys.stdin.isatty():
            # Avoid silently wiping a remote DB from CI or a piped command.
            logger.error(
                "Interactive confirmation required; run from a terminal "
                "or pass --yes to skip the prompt"
            )
            return 2

        print(
            "This will WIPE document chunks, documents, chat history, feedback,\n"
            "analytics, and every non-admin user from the configured MongoDB.\n"
        )
        answer = input("Type 'yes' to continue: ").strip().lower()
        if answer != "yes":
            logger.info("Aborted")
            return 1

    await connect_to_mongo()
    try:
        await _wipe()
    finally:
        await close_mongo_connection()
    return 0


if __name__ == "__main__":
    skip = "--yes" in sys.argv or "-y" in sys.argv
    raise SystemExit(asyncio.run(main(skip_prompt=skip)))
