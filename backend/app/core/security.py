"""Security utilities: password hashing (bcrypt) and JWT tokens."""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
from jose import JWTError, jwt


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
        }

    from app.config import get_settings
    s = get_settings()
    return {
        "secret_key": s.secret_key,
        "algorithm": s.algorithm,
        "access_token_expire_minutes": s.access_token_expire_minutes,
        "refresh_token_expire_days": s.refresh_token_expire_days,
        "cors_origins": s.cors_origins_list,
    }


_config = _load_config()

SECRET_KEY: str = _config["secret_key"]
ALGORITHM: str = _config["algorithm"]
ACCESS_TOKEN_EXPIRE_MINUTES: int = _config["access_token_expire_minutes"]
REFRESH_TOKEN_EXPIRE_DAYS: int = _config["refresh_token_expire_days"]
CORS_ORIGINS: list[str] = _config["cors_origins"]


# --- Password hashing ---
def hash_password(password: str) -> str:
    """Hash a plain-text password with bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# --- JWT tokens ---
def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_refresh_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token. Raises on invalid/expired."""
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


# --- Password reset tokens ---
_PASSWORD_RESET_EXPIRE_MINUTES = 15


def create_password_reset_token(email: str) -> str:
    """Create a short-lived JWT for password reset."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=_PASSWORD_RESET_EXPIRE_MINUTES)
    to_encode = {"sub": email, "type": "password_reset", "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def verify_password_reset_token(token: str) -> str:
    """Decode a password-reset JWT and return the email.

    Raises ``JWTError`` on invalid/expired tokens or wrong token type.
    """
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("type") != "password_reset":
        raise JWTError("Token is not a password reset token")
    email: str | None = payload.get("sub")
    if not email:
        raise JWTError("Token missing subject")
    return email
