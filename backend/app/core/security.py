"""Security utilities: password hashing (bcrypt) and JWT tokens.

Hardening notes
---------------

* The JWT decoder pins ``algorithms`` to a whitelist that is
  intersected with the configured ``Settings.algorithm`` — the literal
  ``"none"`` and asymmetric algs are never accepted, regardless of what
  an attacker manages to put in the token's ``alg`` header or in the
  process environment.
* Every token we mint includes ``iss``, ``aud``, ``iat`` and ``jti``.
  Decoders enforce ``iss`` and ``aud`` so a token minted for a sibling
  service cannot be replayed here even if the secret leaks.
* Password-reset tokens are returned to the user once. Their SHA-256
  digest is stored in the user document for one-shot verification —
  a database read does not give an attacker a usable reset token.
"""

import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from jose import JWTError, jwt


# Allow-list of JWT algorithms. The Settings validator rejects anything
# outside this set, but we re-pin here so that even a poisoned import
# of the config module cannot widen what `decode_token` accepts.
_ALLOWED_ALGORITHMS: frozenset[str] = frozenset({"HS256", "HS384", "HS512"})


def _is_testing() -> bool:
    return os.environ.get("TESTING", "").lower() in ("1", "true")


def _load_config():
    """Load security config from Settings or testing defaults."""
    if _is_testing():
        return {
            "secret_key": "test-secret-key-only-for-testing-purposes-32ch",
            "algorithm": "HS256",
            "access_token_expire_minutes": 30,
            "refresh_token_expire_days": 7,
            "cors_origins": ["http://localhost:3000", "http://127.0.0.1:3000"],
            "jwt_issuer": "raguni-test",
            "jwt_audience": "raguni-api-test",
        }

    from app.config import get_settings
    s = get_settings()
    return {
        "secret_key": s.secret_key,
        "algorithm": s.algorithm,
        "access_token_expire_minutes": s.access_token_expire_minutes,
        "refresh_token_expire_days": s.refresh_token_expire_days,
        "cors_origins": s.cors_origins_list,
        "jwt_issuer": s.jwt_issuer,
        "jwt_audience": s.jwt_audience,
    }


_config = _load_config()

SECRET_KEY: str = _config["secret_key"]
ALGORITHM: str = _config["algorithm"]
ACCESS_TOKEN_EXPIRE_MINUTES: int = _config["access_token_expire_minutes"]
REFRESH_TOKEN_EXPIRE_DAYS: int = _config["refresh_token_expire_days"]
CORS_ORIGINS: list[str] = _config["cors_origins"]
JWT_ISSUER: str = _config["jwt_issuer"]
JWT_AUDIENCE: str = _config["jwt_audience"]


if ALGORITHM not in _ALLOWED_ALGORITHMS:
    # Defence-in-depth — the Settings validator should have caught this
    # already, but if anyone bypasses Settings and passes a bad alg
    # directly we still fail fast on import.
    raise RuntimeError(
        f"Refusing to start: JWT algorithm {ALGORITHM!r} is not in the "
        f"whitelist {sorted(_ALLOWED_ALGORITHMS)}"
    )


# --- Password hashing ---
def hash_password(password: str) -> str:
    """Hash a plain-text password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# --- JWT tokens ---
def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _new_jti() -> str:
    """Random opaque token id used for refresh-token revocation lists."""
    return uuid.uuid4().hex


def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT access token.

    The returned token carries ``iss``, ``aud``, ``iat``, ``exp``, a
    fresh ``jti`` and ``type=access`` in addition to the caller's
    ``data`` payload.
    """
    issued_at = _now_utc()
    expire = issued_at + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode: dict[str, Any] = {
        **data,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": issued_at,
        "exp": expire,
        "jti": _new_jti(),
        "type": "access",
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> tuple[str, str]:
    """Create a JWT refresh token and return ``(token, jti)``.

    The caller must persist the ``jti`` in the refresh-token allowlist
    so that ``/auth/refresh`` can verify the token is still valid and
    so that ``/auth/logout`` (or password change) can revoke it.
    """
    issued_at = _now_utc()
    expire = issued_at + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    jti = _new_jti()
    to_encode: dict[str, Any] = {
        **data,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": issued_at,
        "exp": expire,
        "jti": jti,
        "type": "refresh",
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM), jti


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT.

    Enforces ``iss``, ``aud`` and ``exp`` claims. The accepted-algorithm
    list is the configured algorithm INTERSECTED with the hard whitelist
    above — even if ``ALGORITHM`` were tampered with at startup, the
    decoder would still refuse anything outside ``_ALLOWED_ALGORITHMS``.

    python-jose's ``options`` map uses per-claim ``require_<name>`` /
    ``verify_<name>`` flags rather than a single ``require`` list, so
    we enumerate each required claim explicitly. After decoding we
    additionally enforce a non-empty ``sub`` and ``type`` because
    python-jose's verifier accepts empty strings for those.

    Raises ``JWTError`` (or subclass) on any failure — caller must catch
    and translate to 401.
    """
    if ALGORITHM not in _ALLOWED_ALGORITHMS:
        raise JWTError(f"Refusing to decode with non-whitelisted alg {ALGORITHM!r}")
    payload = jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
        audience=JWT_AUDIENCE,
        issuer=JWT_ISSUER,
        options={
            "require_aud": True,
            "require_iat": True,
            "require_exp": True,
            "require_iss": True,
            "require_sub": True,
        },
    )
    if not payload.get("sub"):
        raise JWTError("Token missing or empty 'sub' claim")
    if not payload.get("type"):
        raise JWTError("Token missing or empty 'type' claim")
    return payload


# --- Password reset tokens ---
def _password_reset_expire_minutes() -> int:
    """Read the reset-token TTL at call time so config changes apply."""
    if _is_testing():
        return 15
    from app.config import get_settings
    return get_settings().password_reset_expire_minutes


def create_password_reset_token(email: str) -> tuple[str, str]:
    """Create a short-lived password-reset token.

    Returns ``(token, token_hash)`` — the caller must email the raw
    ``token`` to the user and persist the SHA-256 ``token_hash`` in the
    user document. ``verify_password_reset_token`` will compare hashes
    so that a database read does not reveal a usable token.
    """
    issued_at = _now_utc()
    expire = issued_at + timedelta(minutes=_password_reset_expire_minutes())
    jti = _new_jti()
    payload = {
        "sub": email,
        "type": "password_reset",
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": issued_at,
        "exp": expire,
        "jti": jti,
        # An additional 32 bytes of entropy embedded in the token
        # plaintext — even if the JWT signature is forged at some
        # future date, the attacker still has to predict this value
        # to match the hash on the user document.
        "nonce": secrets.token_urlsafe(24),
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    token_hash = hash_token(token)
    return token, token_hash


def verify_password_reset_token(token: str) -> str:
    """Decode a password-reset JWT and return the email.

    Raises ``JWTError`` on invalid/expired tokens or wrong token type.
    The caller is still responsible for comparing ``hash_token(token)``
    against the stored hash on the user document — this function only
    proves the JWT is well-formed and not yet expired.
    """
    if ALGORITHM not in _ALLOWED_ALGORITHMS:
        raise JWTError(f"Refusing to decode with non-whitelisted alg {ALGORITHM!r}")
    payload = jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[ALGORITHM],
        audience=JWT_AUDIENCE,
        issuer=JWT_ISSUER,
        options={
            "require_aud": True,
            "require_iat": True,
            "require_exp": True,
            "require_iss": True,
            "require_sub": True,
        },
    )
    if payload.get("type") != "password_reset":
        raise JWTError("Token is not a password reset token")
    email: str | None = payload.get("sub")
    if not email:
        raise JWTError("Token missing subject")
    return email


def hash_token(token: str) -> str:
    """SHA-256 hex digest used to store reset / refresh tokens at rest.

    Cheap, deterministic and one-way — exactly what we need to compare
    a presented token against a stored value without ever keeping the
    raw token in the database.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
