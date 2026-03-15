"""Tests for rate limiting middleware."""

import pytest
from fastapi import FastAPI, Request
from httpx import AsyncClient, ASGITransport
from slowapi import Limiter
from slowapi.util import get_remote_address


class TestRateLimiting:
    """Rate limiter configuration tests."""

    def test_limiter_exists(self):
        """Rate limiter should be importable and configured."""
        from app.core.rate_limit import limiter

        assert isinstance(limiter, Limiter)

    def test_limiter_uses_remote_address(self):
        """Rate limiter should identify clients by IP."""
        from app.core.rate_limit import limiter

        assert limiter._key_func == get_remote_address

    @pytest.mark.asyncio
    async def test_rate_limited_endpoint_allows_normal_requests(self):
        """Normal requests within limit should succeed."""
        from app.core.rate_limit import limiter
        from slowapi import _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded

        test_app = FastAPI()
        test_app.state.limiter = limiter

        test_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

        @test_app.get("/test")
        @limiter.limit("10/minute")
        async def test_endpoint(request: Request):
            return {"ok": True}

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/test")
            assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_rate_limited_endpoint_blocks_excess_requests(self):
        """Requests exceeding rate limit should return 429."""
        from app.core.rate_limit import limiter
        from slowapi import _rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded

        test_app = FastAPI()
        test_app.state.limiter = limiter

        test_app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

        @test_app.get("/test-strict")
        @limiter.limit("2/minute")
        async def test_endpoint(request: Request):
            return {"ok": True}

        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # First 2 requests should succeed
            for _ in range(2):
                response = await client.get("/test-strict")
                assert response.status_code == 200

            # 3rd request should be rate limited
            response = await client.get("/test-strict")
            assert response.status_code == 429
