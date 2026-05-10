import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from contextlib import asynccontextmanager
from pymongo.errors import ConnectionFailure

from app.config import get_settings
from app.core.logging_config import configure_logging
from app.core.middleware import RequestIdMiddleware
from app.core.observability import init_prometheus, init_sentry

_settings = get_settings()
configure_logging(
    log_format=_settings.log_format,
    level=getattr(logging, _settings.log_level.upper(), logging.INFO),
)

# Sentry must be initialised before any router imports so unhandled
# exceptions at import time are also captured.
init_sentry(
    dsn=_settings.sentry_dsn,
    environment=_settings.environment,
    release=_settings.release,
    traces_sample_rate=_settings.sentry_traces_sample_rate,
)

logger = logging.getLogger(__name__)

from app.core.rate_limit import limiter, rate_limit_exceeded_handler, register_rate_limiter
from app.core.error_handler import register_error_handlers
from app.services.database import connect_to_mongo, close_mongo_connection
from app.api.v1 import documents, chat
from app.api.v1 import auth as auth_router_module
from app.api.v1 import admin as admin_router_module
from app.api.v1 import chat_history as chat_history_module
from app.api.v1 import feedback as feedback_module
from app.api.v1 import dictionaries as dictionaries_module


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for startup and shutdown.

    Startup is intentionally fail-fast in production: a deploy that
    cannot reach MongoDB or load the embedding model should NOT serve
    traffic — every subsequent request would 500 anyway. ``connect_to_mongo``
    re-raises in production, and we move the heavy embedder load
    (~2 GB, several seconds) into the startup hook via
    ``asyncio.to_thread`` so the first user request doesn't pay the
    cost on a cold worker.
    """
    import asyncio as _asyncio

    logger.info("Starting University Knowledge API...")
    await connect_to_mongo()

    # Warm the embedder + vector store. ``initialize`` is synchronous
    # and CPU-bound — running it in a worker thread keeps the event
    # loop responsive while the model downloads / loads.
    try:
        from app.services.vector_store import vector_store_service
        await _asyncio.to_thread(vector_store_service.initialize)
        logger.info("Embedding model warm; vector store ready")
    except (ConnectionFailure, OSError, ValueError) as e:
        if _settings.environment == "production":
            logger.error("Vector store initialization failed: %s", type(e).__name__)
            raise
        logger.warning("Vector store init failed in dev (%s) — will retry per request", type(e).__name__)

    logger.info("All services initialized")
    yield

    logger.info("Shutting down...")
    await close_mongo_connection()


# Create FastAPI app
app = FastAPI(
    title="University Knowledge API",
    description="RAG-based API for university document knowledge base",
    version="1.0.0",
    lifespan=lifespan
)

# Global error handlers
register_error_handlers(app)

# Rate limiting
register_rate_limiter(app)

# Security headers — the API only ever serves JSON / SSE responses,
# never HTML, so the frontend's nonce-based CSP doesn't apply. We keep
# a narrow set of hardening headers so /docs (Swagger UI) and any
# direct API consumer still benefit.
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if _settings.environment == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        # Strict CSP for the API surface: no scripts at all (this server
        # never returns HTML/JS bundles to a browser), can't be framed,
        # forms can only submit back to self.
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'none'"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Request id + access log. Installed AFTER the security-headers
# middleware so the request-id response header survives CORS
# preflights too. Starlette adds middlewares in reverse order of
# registration, so this runs first on the way in.
app.add_middleware(RequestIdMiddleware)

# CORS middleware
from app.core.security import CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Session-Id", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)

# Prometheus /metrics — off by default, enabled via ENABLE_METRICS=true.
init_prometheus(app, enabled=_settings.enable_metrics)

# Include routers
app.include_router(
    documents.router,
    prefix="/api/v1/documents",
    tags=["Documents"]
)

app.include_router(
    chat.router,
    prefix="/api/v1/chat",
    tags=["Chat"]
)

app.include_router(
    auth_router_module.router,
    prefix="/api/v1/auth",
    tags=["Auth"]
)

app.include_router(
    admin_router_module.router,
    prefix="/api/v1/admin",
    tags=["Admin"]
)

app.include_router(
    chat_history_module.router,
    prefix="/api/v1/chat",
    tags=["Chat History"]
)

app.include_router(
    feedback_module.router,
    prefix="/api/v1/chat",
    tags=["Feedback"]
)

app.include_router(
    dictionaries_module.router,
    prefix="/api/v1/dictionaries",
    tags=["Dictionaries"]
)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "University Knowledge API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "register": "POST /api/v1/auth/register",
            "login": "POST /api/v1/auth/login",
            "refresh": "POST /api/v1/auth/refresh",
            "me": "GET /api/v1/auth/me",
            "upload_document": "POST /api/v1/documents/upload",
            "list_documents": "GET /api/v1/documents/list",
            "delete_document": "DELETE /api/v1/documents/{document_id}",
            "ask_question": "POST /api/v1/chat/ask",
            "chat_history": "GET /api/v1/chat/history",
            "admin_users": "GET /api/v1/admin/users",
            "health_check": "GET /api/v1/chat/health",
        }
    }


APP_VERSION = "1.0.0"


@app.get("/api/v1/version")
async def version() -> dict[str, str]:
    """Return the deployed application version + git commit (if injected).

    Useful for debugging which release is live in a given environment.
    The git SHA is provided via the GIT_SHA env var at build / deploy
    time; locally it falls back to "dev".
    """
    import os
    return {
        "version": APP_VERSION,
        "git_sha": os.environ.get("GIT_SHA", "dev"),
        "environment": _settings.environment,
    }


@app.get("/health")
async def health():
    """Simple health check for Docker/load balancers."""
    from app.services.database import db
    if db.client is None:
        return {"status": "degraded", "database": "disconnected"}
    return {"status": "ok"}


if __name__ == "__main__":
    import os
    import uvicorn

    is_dev = os.environ.get("ENV", "development").lower() == "development"
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=is_dev,
    )
