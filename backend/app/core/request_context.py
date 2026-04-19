"""Per-request context stored in a contextvar.

Stores the request_id so that log records emitted anywhere during a
request handler can include it without having to thread it through
every function signature.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Return the current request's id, or ``"-"`` outside a request."""
    return _request_id_var.get()


def set_request_id(value: str | None = None) -> str:
    """Set the current request id. Returns the value that was stored.

    If ``value`` is ``None`` a new UUID4 prefixed with ``req_`` is
    generated. Callers that receive a trusted request id from an upstream
    proxy (e.g. ``X-Request-ID``) should pass it in verbatim.
    """
    resolved = value if value else f"req_{uuid.uuid4().hex[:12]}"
    _request_id_var.set(resolved)
    return resolved
