"""
Chat API — LCEL-based RAG pipeline.

Flow:
1. Build access-control filter from user context
2. Retrieve relevant chunks via MMR search (MongoDB Atlas Vector Search)
3. Format context + question into prompt
4. Stream answer from Deepseek LLM
5. Return answer with source citations
"""

import asyncio
import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from langchain_core.documents import Document as LCDocument
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.config import get_settings
from app.core.dependencies import get_current_user
from app.core.rate_limit import limiter
from app.models.document import ChatRequest, ChatResponse
from app.services.database import get_database
from app.services.vector_store import vector_store_service

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()


# ---------------------------------------------------------------------------
# LLM (lazy singleton — not created at import time, thread-safe)
# ---------------------------------------------------------------------------
_llm: Optional[ChatOpenAI] = None
_llm_lock = asyncio.Lock()


async def get_llm() -> ChatOpenAI:
    """Get or create LLM instance (lazy, async-safe)."""
    global _llm
    if _llm is None:
        async with _llm_lock:
            if _llm is None:
                _llm = ChatOpenAI(
                    model=settings.deepseek_model,
                    api_key=settings.deepseek_api_key,
                    base_url=settings.deepseek_api_base,
                    temperature=settings.llm_temperature,
                    max_tokens=settings.llm_max_tokens,
                    request_timeout=float(settings.llm_timeout_seconds),
                )
                logger.info("LLM initialized: %s", settings.deepseek_model)
    return _llm


# ---------------------------------------------------------------------------
# RAG Prompt
# ---------------------------------------------------------------------------
RAG_SYSTEM_PROMPT = """You are an intelligent university assistant that helps students and faculty find information from documents.

**IMPORTANT RULES:**
1. Answer ONLY based on the provided context
2. If the context does not contain the answer, honestly say "The available documents do not contain information about this"
3. ALWAYS cite sources: "According to [document name]..."
4. Be precise with dates, numbers, and names
5. Answer in the same language as the user's question
6. Structure your answer: use lists and paragraphs for readability"""

RAG_USER_TEMPLATE = """**CONTEXT FROM DOCUMENTS:**
{context}

**QUESTION:**
{question}"""

rag_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", RAG_SYSTEM_PROMPT),
        ("human", RAG_USER_TEMPLATE),
    ]
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def format_docs(docs: list[LCDocument]) -> str:
    """Format retrieved documents into a single context string."""
    parts: list[str] = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source_file", "Unknown document")
        chunk_idx = doc.metadata.get("chunk_index", "?")
        parts.append(
            f"[Source {i}: {source}, chunk {chunk_idx}]\n{doc.page_content}"
        )
    return "\n\n---\n\n".join(parts)


def extract_sources(docs: list[LCDocument]) -> list[dict[str, Any]]:
    """Extract source metadata for the response."""
    sources: list[dict] = []
    seen: set[str] = set()
    for doc in docs:
        meta = doc.metadata
        key = f"{meta.get('source_file', '')}:{meta.get('chunk_index', 0)}"
        if key in seen:
            continue
        seen.add(key)
        preview = doc.page_content
        if len(preview) > 200:
            preview = preview[:200] + "..."
        sources.append(
            {
                "source_file": meta.get("source_file", "Unknown"),
                "file_type": meta.get("file_type", ""),
                "chunk_index": meta.get("chunk_index", 0),
                "total_chunks": meta.get("total_chunks", 0),
                "text": preview,
            }
        )
    return sources


# ---------------------------------------------------------------------------
# RAG chain runner (reused by chat_history SSE endpoint)
# ---------------------------------------------------------------------------
async def run_rag_chain(
    question: str,
    user_role: str = "student",
    user_faculty: Optional[str] = None,
) -> dict[str, Any]:
    """Execute the full RAG pipeline and return answer + sources.

    Returns:
        {"answer": str, "sources": list[dict], "docs": list[Document]}
    """
    # Build access filter
    pre_filter = vector_store_service.build_access_filter(user_role, user_faculty)
    logger.info("Access filter for role=%s: %s", user_role, pre_filter)

    # Choose retriever: hybrid (vector + full-text RRF) or MMR
    if settings.use_hybrid_search:
        try:
            retriever = vector_store_service.get_hybrid_retriever(
                k=settings.top_k_results,
                pre_filter=pre_filter or None,
            )
            logger.info("Using hybrid search (vector + full-text RRF)")
        except (ValueError, RuntimeError) as e:
            logger.warning("Hybrid search unavailable (%s), falling back to MMR", e)
            retriever = vector_store_service.get_retriever(
                search_type="mmr",
                k=settings.top_k_results,
                pre_filter=pre_filter or None,
                fetch_k=settings.top_k_results * 4,
                lambda_mult=0.7,
            )
    else:
        retriever = vector_store_service.get_retriever(
            search_type="mmr",
            k=settings.top_k_results,
            pre_filter=pre_filter or None,
            fetch_k=settings.top_k_results * 4,
            lambda_mult=0.7,
        )

    # Retrieve documents with timeout
    try:
        docs = await asyncio.wait_for(
            retriever.ainvoke(question),
            timeout=float(settings.llm_timeout_seconds),
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Search request timed out")

    context = format_docs(docs)

    # LCEL chain: prompt → LLM → parse
    llm = await get_llm()
    chain = rag_prompt | llm | StrOutputParser()

    # Run chain with timeout
    try:
        answer = await asyncio.wait_for(
            chain.ainvoke({"context": context, "question": question}),
            timeout=float(settings.llm_timeout_seconds),
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="LLM request timed out")

    return {
        "answer": answer,
        "sources": extract_sources(docs),
        "docs": docs,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@router.post("/ask", response_model=ChatResponse)
@limiter.limit("20/minute")
async def ask_question(
    body: ChatRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """
    Ask a question using RAG pipeline.

    Requires authentication. Results are filtered by user role and faculty.
    """
    start_time = time.time()

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    logger.info("Processing question (user_role=%s)", current_user.get("role"))

    try:
        # Check if we have documents
        db = get_database()
        doc_count = await db.documents.count_documents({})

        if doc_count == 0:
            return ChatResponse(
                answer="The knowledge base has no documents yet. "
                       "Please upload documents via the admin panel.",
                sources=[],
                processing_time=time.time() - start_time,
            )

        # Run RAG
        result = await run_rag_chain(
            question=question,
            user_role=current_user.get("role", "student"),
            user_faculty=current_user.get("faculty"),
        )

        processing_time = time.time() - start_time
        logger.info("Answer generated in %.2fs", processing_time)

        return ChatResponse(
            answer=result["answer"],
            sources=result["sources"],
            processing_time=processing_time,
        )

    except HTTPException:
        raise
    except RuntimeError as e:
        logger.error("RAG pipeline error: %s", e, exc_info=True)
        raise HTTPException(status_code=502, detail="Failed to generate answer")
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="Request timed out")


@router.get("/health")
async def health_check():
    """Health check with system status (read-only)."""
    try:
        db = get_database()
        doc_count = await db.documents.count_documents({})

        stats = await vector_store_service.get_stats()

        llm_status = "configured"
        try:
            await get_llm()
        except (ValueError, RuntimeError):
            llm_status = "unhealthy"

        return {
            "status": "healthy",
            "components": {
                "database": "connected",
                "vector_store": "initialized" if vector_store_service._vector_store else "not_initialized",
                "llm": llm_status,
            },
            "statistics": {
                "documents_count": doc_count,
                **stats,
            },
            "configuration": {
                "embedding_model": settings.embedding_model,
                "llm_model": settings.deepseek_model,
                "chunk_size": settings.chunk_size,
                "chunk_overlap": settings.chunk_overlap,
                "top_k_results": settings.top_k_results,
            },
        }

    except RuntimeError:
        return {"status": "unhealthy", "error": "Service not fully initialized"}
