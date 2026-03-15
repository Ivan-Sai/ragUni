"""Rate limiting configuration using SlowAPI."""

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.requests import Request

# Default rate limits per endpoint category
DEFAULT_RATE_LIMIT = "60/minute"
AUTH_RATE_LIMIT = "10/minute"
CHAT_RATE_LIMIT = "30/minute"
UPLOAD_RATE_LIMIT = "10/minute"

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[DEFAULT_RATE_LIMIT],
    storage_uri="memory://",
)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Custom handler that returns a structured JSON response on rate limit."""
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "message": "Rate limit exceeded. Please try again later.",
                "status_code": 429,
            }
        },
    )


def register_rate_limiter(app: FastAPI) -> None:
    """Register the rate limiter and its error handler on the FastAPI app."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
