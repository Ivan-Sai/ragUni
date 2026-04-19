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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for startup and shutdown"""
    # Startup
    logger.info("Starting University Knowledge API...")
    await connect_to_mongo()

    # Initialize LangChain Vector Store (non-blocking — will retry on first request)
    try:
        from app.services.vector_store import vector_store_service
        vector_store_service.initialize()
    except (ConnectionFailure, OSError, ValueError) as e:
        logger.error("Vector store initialization failed: %s", type(e).__name__)
        logger.info("Vector store will attempt re-initialization on first request")

    logger.info("All services initialized")
    yield
    # Shutdown
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

# Security headers middleware
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'"
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
