"""Sentry and Prometheus initialisation.

Both integrations are *optional*: the app must start even if the SDK
packages are not installed (e.g. in CI or in a minimal test environment).
When the corresponding environment variables are empty, the init helpers
are no-ops.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


def init_sentry(
    dsn: Optional[str],
    environment: str,
    release: Optional[str] = None,
    traces_sample_rate: float = 0.1,
) -> bool:
    """Initialise Sentry if a DSN is configured and the SDK is importable.

    Returns True when Sentry was successfully initialised.
    """
    if not dsn:
        logger.info("Sentry disabled (no SENTRY_DSN configured)")
        return False

    try:
        import sentry_sdk  # type: ignore[import-not-found]
        from sentry_sdk.integrations.fastapi import FastApiIntegration  # type: ignore[import-not-found]
        from sentry_sdk.integrations.starlette import StarletteIntegration  # type: ignore[import-not-found]
    except ImportError:
        logger.warning(
            "Sentry DSN is set but the 'sentry-sdk' package is not installed"
        )
        return False

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        traces_sample_rate=traces_sample_rate,
        # PII never leaves the service — emails, questions, tokens.
        send_default_pii=False,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
        ],
    )
    logger.info("Sentry initialised (environment=%s)", environment)
    return True


def init_prometheus(app: "FastAPI", enabled: bool) -> bool:
    """Mount a ``/metrics`` endpoint exposing Prometheus counters.

    Returns True when the instrumentator was attached.
    """
    if not enabled:
        logger.info("Prometheus metrics disabled (ENABLE_METRICS=false)")
        return False

    try:
        from prometheus_fastapi_instrumentator import Instrumentator  # type: ignore[import-not-found]
    except ImportError:
        logger.warning(
            "ENABLE_METRICS=true but 'prometheus-fastapi-instrumentator' "
            "is not installed"
        )
        return False

    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        excluded_handlers=["/metrics", "/health"],
    )
    instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
    logger.info("Prometheus instrumentator mounted at /metrics")
    return True
