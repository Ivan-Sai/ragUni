"""Refresh-token allowlist (server-side revocation list).

Why this exists
===============

Plain JWT refresh tokens are stateless — once issued, every server
that knows ``SECRET_KEY`` will accept them until ``exp`` passes. That
makes "log out" or "force logout after password change" impossible to
implement by inspecting the JWT alone.

The fix is a tiny database-backed allowlist: every refresh token we
mint has its ``jti`` stored here with the user's id, the SHA-256 of
the token (so a DB read does not reveal a usable token), an expiry,
and a ``revoked`` flag. ``/auth/refresh`` looks up the presented
token's ``jti`` and refuses anything missing or revoked.

Two operations revoke tokens:

* ``revoke(jti)`` — single token, called by ``/auth/logout``.
* ``revoke_all_for_user(user_id)`` — every outstanding token for a
  user, called on password change / reset / role change.

The collection has a TTL index on ``expires_at`` so expired entries
self-clean — no growing list of dead jtis.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from app.core.security import hash_token
# Module-level import so tests patching `app.services.database.get_database`
# affect the calls below too.
from app.services import database as _database


COLLECTION = "refresh_tokens"


async def store(
    *,
    jti: str,
    user_id: str,
    raw_token: str,
    expires_at: datetime,
) -> None:
    """Persist a freshly minted refresh token's jti + token hash."""
    db = _database.get_database()
    await db[COLLECTION].insert_one(
        {
            "jti": jti,
            "user_id": user_id,
            "token_hash": hash_token(raw_token),
            "expires_at": expires_at,
            "revoked": False,
            "created_at": datetime.now(timezone.utc),
        }
    )


async def is_active(*, jti: str, raw_token: str) -> bool:
    """Return True iff the (jti, token) pair is in the allowlist,
    not revoked, and not yet expired.

    Comparing token hashes (not jti alone) defeats a token whose ``jti``
    matches a still-active entry but whose payload was forged — an
    attacker would need both the secret AND the original raw token to
    reproduce the hash.
    """
    db = _database.get_database()
    doc = await db[COLLECTION].find_one({"jti": jti, "revoked": False})
    if not doc:
        return False
    if doc.get("token_hash") != hash_token(raw_token):
        return False
    expires_at: Optional[datetime] = doc.get("expires_at")
    if expires_at is None:
        return False
    # Mongo stores naive UTC datetimes — coerce both sides.
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at > datetime.now(timezone.utc)


async def revoke(*, jti: str) -> None:
    """Mark a single token revoked (logout)."""
    db = _database.get_database()
    await db[COLLECTION].update_one(
        {"jti": jti},
        {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc)}},
    )


async def revoke_all_for_user(*, user_id: str) -> int:
    """Revoke every outstanding refresh token for a user.

    Called on password change, password reset and role change so a
    stolen refresh token cannot be used to keep minting access tokens
    after the credential it was paired with has been invalidated.

    Returns the number of tokens revoked.
    """
    db = _database.get_database()
    result = await db[COLLECTION].update_many(
        {"user_id": user_id, "revoked": False},
        {"$set": {"revoked": True, "revoked_at": datetime.now(timezone.utc)}},
    )
    return result.modified_count


__all__ = [
    "COLLECTION",
    "store",
    "is_active",
    "revoke",
    "revoke_all_for_user",
]
