"""Tests for security module — password hashing and JWT tokens."""

import pytest
from datetime import timedelta


class TestPasswordHashing:
    """Password hashing with bcrypt."""

    def test_hash_password_returns_hash(self):
        """hash_password should return a bcrypt hash string."""
        from app.core.security import hash_password

        result = hash_password("SecurePass123!")
        assert result != "SecurePass123!"
        assert result.startswith("$2b$")

    def test_verify_correct_password(self):
        """verify_password should return True for correct password."""
        from app.core.security import hash_password, verify_password

        hashed = hash_password("SecurePass123!")
        assert verify_password("SecurePass123!", hashed) is True

    def test_verify_wrong_password(self):
        """verify_password should return False for wrong password."""
        from app.core.security import hash_password, verify_password

        hashed = hash_password("SecurePass123!")
        assert verify_password("WrongPassword!", hashed) is False

    def test_different_passwords_different_hashes(self):
        """Same password hashed twice should produce different hashes (salt)."""
        from app.core.security import hash_password

        hash1 = hash_password("SecurePass123!")
        hash2 = hash_password("SecurePass123!")
        assert hash1 != hash2


class TestJWTTokens:
    """JWT token creation and validation."""

    def test_create_access_token(self):
        """create_access_token should return a JWT string."""
        from app.core.security import create_access_token

        token = create_access_token(data={"sub": "user@knu.ua", "role": "student"})
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_valid_token(self):
        """decode_token should return the payload for a valid token."""
        from app.core.security import create_access_token, decode_token

        token = create_access_token(data={"sub": "user@knu.ua", "role": "student"})
        payload = decode_token(token)
        assert payload["sub"] == "user@knu.ua"
        assert payload["role"] == "student"
        assert payload["type"] == "access"

    def test_decode_expired_token_raises(self):
        """decode_token should raise for expired token."""
        from app.core.security import create_access_token, decode_token

        token = create_access_token(
            data={"sub": "user@knu.ua"},
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(Exception):
            decode_token(token)

    def test_decode_invalid_token_raises(self):
        """decode_token should raise for invalid/tampered token."""
        from app.core.security import decode_token

        with pytest.raises(Exception):
            decode_token("invalid.token.string")

    def test_create_refresh_token(self):
        """create_refresh_token should create a token with type=refresh."""
        from app.core.security import create_refresh_token, decode_token

        token = create_refresh_token(data={"sub": "user@knu.ua"})
        payload = decode_token(token)
        assert payload["type"] == "refresh"

    def test_access_token_has_expiry(self):
        """Access token payload should contain 'exp' claim."""
        from app.core.security import create_access_token, decode_token

        token = create_access_token(data={"sub": "user@knu.ua"})
        payload = decode_token(token)
        assert "exp" in payload
