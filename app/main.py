from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.services.database import connect_to_mongo, close_mongo_connection
from app.services.vectorizer import vectorizer
from app.api.v1 import documents, chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan events for startup and shutdown"""
    # Startup
    print("🚀 Starting University Knowledge API...")
    await connect_to_mongo()
    # vectorizer.initialize()  # Temporarily disabled - initialize on first use
    print("✓ All services initialized")
    yield
    # Shutdown
    print("Shutting down...")
    await close_mongo_connection()


# Create FastAPI app
app = FastAPI(
    title="University Knowledge API",
    description="RAG-based API for university document knowledge base",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "University Knowledge API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "upload_document": "POST /api/v1/documents/upload",
            "list_documents": "GET /api/v1/documents/list",
            "delete_document": "DELETE /api/v1/documents/{document_id}",
            "ask_question": "POST /api/v1/chat/ask",
            "health_check": "GET /api/v1/chat/health"
        }
    }


@app.get("/health")
async def health():
    """Simple health check"""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
