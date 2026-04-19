"""Structured JSON logging.

Switches the root logger to emit one JSON object per line. Every record
automatically carries the current ``request_id`` (from the
``request_context`` contextvar) so that logs can be correlated across
modules for a single request.

Activated in production via ``LOG_FORMAT=json`` (see ``app.config``).
The default ``text`` format is preserved for developer ergonomics.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.core.request_context import get_request_id

# Built-in LogRecord attributes we should not duplicate into the "extras"
# block. Anything NOT in this set and passed via ``extra={}`` is carried
# into the JSON output.
_BUILTIN_LOG_RECORD_FIELDS: frozenset[str] = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime", "taskName",
    }
)


class JsonFormatter(logging.Formatter):
    """Emit log records as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info

        # Carry any structured fields the caller passed via ``extra=``.
        for key, value in record.__dict__.items():
            if key in _BUILTIN_LOG_RECORD_FIELDS or key.startswith("_"):
                continue
            payload[key] = value

        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable text formatter that still shows the request id."""

    def __init__(self) -> None:
        super().__init__(
            fmt="%(asctime)s | %(levelname)-7s | %(name)s | [%(request_id)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        record.request_id = get_request_id()
        return super().format(record)


def configure_logging(log_format: str = "text", level: int = logging.INFO) -> None:
    """Install the chosen formatter on the root logger.

    Idempotent: safe to call from ``main.py`` on every import, and from
    tests that want a clean slate.
    """
    root = logging.getLogger()
    root.setLevel(level)

    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if log_format.lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(TextFormatter())

    root.addHandler(handler)
