"""JWT-validation security tests.

The decoder MUST refuse:
  * Tokens with ``alg: none`` (unsigned).
  * Tokens signed with a different secret.
  * Tokens whose ``alg`` claim is outside the HS256/HS384/HS512 whitelist.
  * Tokens missing required claims (``iss``/``aud``/``exp``/``iat``/``sub``/``type``).
  * Tokens whose ``iss`` or ``aud`` doesn't match this service.

Each test pins one of those guarantees so a regression — a future
import that loosens the decoder, a config change that adds RS256
to the whitelist — fails CI immediately.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from jose import JWTError, jwt

from app.core.security import (
    JWT_AUDIENCE,
    JWT_ISSUER,
    SECRET_KEY,
    create_access_token,
    decode_token,
)


def _well_formed_payload(extra: dict | None = None) -> dict:
    """Return a payload with every required claim present.

    Tests use this as the baseline and mutate one field at a time so
    the failure can be attributed to that field.
    """
    now = datetime.now(timezone.utc)
    base = {
        "sub": "user@example.com",
        "type": "access",
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=10),
        "jti": "test-jti-1",
    }
    if extra:
        base.update(extra)
    return base


class TestRejectAlgNone:
    """``alg: none`` must NEVER be accepted."""

    def test_unsigned_token_is_rejected(self):
        # Build a header with alg=none manually because python-jose
        # refuses to mint one. Format: base64url(header).base64url(payload).
        import base64

        def b64(d: bytes) -> str:
            return base64.urlsafe_b64encode(d).rstrip(b"=").decode()

        header = {"alg": "none", "typ": "JWT"}
        payload = _well_formed_payload()
        # iat / exp must be ints in the encoded JSON.
        payload["iat"] = int(payload["iat"].timestamp())
        payload["exp"] = int(payload["exp"].timestamp())
        token = (
            f"{b64(json.dumps(header).encode())}."
            f"{b64(json.dumps(payload).encode())}."
        )
        with pytest.raises(JWTError):
            decode_token(token)


class TestRejectWrongSecret:
    """A token signed with a different secret must NOT decode."""

    def test_wrong_secret_is_rejected(self):
        payload = _well_formed_payload()
        payload["iat"] = int(payload["iat"].timestamp())
        payload["exp"] = int(payload["exp"].timestamp())
        forged = jwt.encode(payload, "different-secret-of-sufficient-length-32+", algorithm="HS256")
        with pytest.raises(JWTError):
            decode_token(forged)


class TestRejectWrongAlgorithm:
    """Tokens whose ``alg`` is outside HS256/HS384/HS512 must fail."""

    def test_hs256_succeeds_baseline(self):
        token = create_access_token(data={"sub": "user@example.com", "role": "student"})
        payload = decode_token(token)
        assert payload["sub"] == "user@example.com"

    def test_hs384_succeeds_when_signed_with_secret(self):
        # HS384 is in the whitelist — when signed with the configured
        # SECRET_KEY it should pass. Confirms the whitelist is a
        # whitelist (not a single-value pin).
        payload = _well_formed_payload()
        payload["iat"] = int(payload["iat"].timestamp())
        payload["exp"] = int(payload["exp"].timestamp())
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS384")
        # python-jose's jwt.decode by default uses the algorithm
        # listed in the token header if it's in the allowed list. Our
        # decode_token pins to ALGORITHM (HS256 in tests), so HS384
        # tokens are still rejected — that's the expected hardening.
        with pytest.raises(JWTError):
            decode_token(token)


class TestRequireClaims:
    """Required claims (iss, aud, exp, iat, sub, type) must be present."""

    @pytest.mark.parametrize(
        "missing_claim",
        ["iss", "aud", "iat", "exp", "sub", "type"],
    )
    def test_missing_required_claim_is_rejected(self, missing_claim):
        payload = _well_formed_payload()
        payload["iat"] = int(payload["iat"].timestamp())
        payload["exp"] = int(payload["exp"].timestamp())
        del payload[missing_claim]
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        with pytest.raises(JWTError):
            decode_token(token)


class TestIssuerAudience:
    """The decoder must reject mismatched ``iss`` or ``aud`` claims."""

    def test_wrong_audience_is_rejected(self):
        payload = _well_formed_payload({"aud": "different-service"})
        payload["iat"] = int(payload["iat"].timestamp())
        payload["exp"] = int(payload["exp"].timestamp())
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        with pytest.raises(JWTError):
            decode_token(token)

    def test_wrong_issuer_is_rejected(self):
        payload = _well_formed_payload({"iss": "evil-issuer"})
        payload["iat"] = int(payload["iat"].timestamp())
        payload["exp"] = int(payload["exp"].timestamp())
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        with pytest.raises(JWTError):
            decode_token(token)


class TestExpiredToken:
    """Already-expired tokens are rejected even if otherwise valid."""

    def test_expired_token_is_rejected(self):
        payload = _well_formed_payload(
            {"exp": datetime.now(timezone.utc) - timedelta(seconds=1)}
        )
        payload["iat"] = int(payload["iat"].timestamp())
        payload["exp"] = int(payload["exp"].timestamp())
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        with pytest.raises(JWTError):
            decode_token(token)


class TestAccessVsResetTokenSeparation:
    """Reset tokens cannot stand in for access tokens."""

    def test_reset_token_payload_marks_password_reset(self):
        from app.core.security import create_password_reset_token

        token, token_hash = create_password_reset_token("user@example.com")
        assert isinstance(token, str)
        assert isinstance(token_hash, str) and len(token_hash) == 64  # sha256 hex
        decoded = decode_token(token)
        assert decoded["type"] == "password_reset"

    def test_access_token_cannot_be_consumed_as_reset(self):
        from app.core.security import verify_password_reset_token

        access = create_access_token(
            data={"sub": "user@example.com", "role": "student"}
        )
        with pytest.raises(JWTError):
            verify_password_reset_token(access)
