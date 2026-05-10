"""Account lockout — per-user brute-force defence on /auth/login.

Why this exists
===============

The slowapi rate limit on ``/auth/login`` is per-IP and capped at
10/min. An attacker on a residential proxy network (each request
from a different IP) bypasses it trivially while the victim's
account has no friction at all — credential stuffing gets unlimited
guesses.

This module adds the missing per-account half of the defence:

* On every failed verify, increment ``failed_login_attempts`` on the
  user document and stamp ``last_failed_login``.
* When attempts reach ``MAX_ATTEMPTS`` within the
  ``FAILURE_WINDOW``, set ``locked_until = now + LOCKOUT_DURATION``.
* On every successful login, clear both fields.
* On every login attempt, refuse fast (HTTP 423 Locked) if
  ``locked_until`` is still in the future.

The combination — per-IP rate limit AND per-account lockout — costs
an attacker time on EVERY guess, regardless of how many IPs they
control.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

# Module-level import (rather than `from … import get_database`) so that
# unit tests patching `app.services.database.get_database` see the
# substitution take effect here too.
from app.services import database as _database


# Tunables — kept here rather than in Settings because they are
# security policy, not runtime configuration. Changing them requires a
# code change + review.
MAX_ATTEMPTS: int = 5
FAILURE_WINDOW: timedelta = timedelta(minutes=15)
LOCKOUT_DURATION: timedelta = timedelta(minutes=15)


@dataclass(frozen=True)
class LockoutStatus:
    """Result of `check_locked` — locked / not locked + remaining time."""

    locked: bool
    locked_until: Optional[datetime] = None

    @property
    def seconds_remaining(self) -> int:
        if not self.locked or self.locked_until is None:
            return 0
        delta = self.locked_until - datetime.now(timezone.utc)
        return max(0, int(delta.total_seconds()))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Mongo stores naive UTC datetimes — re-attach the tz so
    comparisons with tz-aware ``datetime.now`` don't raise."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def check_locked(user: dict[str, Any]) -> LockoutStatus:
    """Inspect the user doc and report current lockout status.

    Pure function — does not write to the DB. Call this BEFORE
    verifying the password so an attacker cannot probe the password
    while the account is locked.
    """
    locked_until = _coerce_aware(user.get("locked_until"))
    if locked_until and locked_until > _now():
        return LockoutStatus(locked=True, locked_until=locked_until)
    return LockoutStatus(locked=False)


async def record_failed_attempt(user: dict[str, Any]) -> LockoutStatus:
    """Increment the failure counter and lock the account if over the
    threshold within the failure window.

    Returns the resulting lockout status so the caller can include
    ``Retry-After`` in the 401/423 response.
    """
    db = _database.get_database()
    now = _now()

    last_failed = _coerce_aware(user.get("last_failed_login"))
    # Reset the counter if the previous failure was outside the window.
    if last_failed is None or now - last_failed > FAILURE_WINDOW:
        attempts = 1
    else:
        attempts = int(user.get("failed_login_attempts", 0)) + 1

    update: dict[str, Any] = {
        "failed_login_attempts": attempts,
        "last_failed_login": now,
    }
    locked_until: Optional[datetime] = None
    if attempts >= MAX_ATTEMPTS:
        locked_until = now + LOCKOUT_DURATION
        update["locked_until"] = locked_until
        # Reset the counter on lock so the next failure after the lock
        # expires starts fresh.
        update["failed_login_attempts"] = 0

    await db.users.update_one({"_id": user["_id"]}, {"$set": update})
    return LockoutStatus(
        locked=locked_until is not None,
        locked_until=locked_until,
    )


async def clear(user: dict[str, Any]) -> None:
    """Clear failure counter + lockout on successful login."""
    db = _database.get_database()
    await db.users.update_one(
        {"_id": user["_id"]},
        {
            "$unset": {
                "failed_login_attempts": "",
                "last_failed_login": "",
                "locked_until": "",
            }
        },
    )


__all__ = [
    "MAX_ATTEMPTS",
    "FAILURE_WINDOW",
    "LOCKOUT_DURATION",
    "LockoutStatus",
    "check_locked",
    "record_failed_attempt",
    "clear",
]
