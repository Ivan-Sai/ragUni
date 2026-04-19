"""HTTP middlewares beyond the security headers already in ``app.main``."""

from __future__ import annotations

import logging
import time

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.request_context import set_request_id

logger = logging.getLogger("app.access")

_REQUEST_ID_HEADER = "X-Request-ID"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assign a request id, emit an access log, and echo the id back.

    * Honours an incoming ``X-Request-ID`` if an upstream proxy already
      generated one (so the id survives across service boundaries).
    * Stores the id in the request-scoped contextvar so every log
      record emitted during the async call chain is correlated.
    * Echoes the id back in the response so clients can quote it when
      reporting an issue.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        upstream_id = request.headers.get(_REQUEST_ID_HEADER)
        request_id = set_request_id(upstream_id)

        start = time.perf_counter()
        response: Response | None = None
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000.0
            logger.info(
                "%s %s -> %s (%.1f ms)",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
                extra={
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "http_status": status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            if response is not None:
                response.headers[_REQUEST_ID_HEADER] = request_id
