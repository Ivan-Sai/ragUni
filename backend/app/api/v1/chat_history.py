"""Chat history endpoints + SSE streaming chat with real RAG pipeline."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from langchain_core.output_parsers import StrOutputParser
from pydantic import BaseModel

from app.config import get_settings
from app.core.dependencies import get_current_user
from app.core.rate_limit import limiter
from app.services.database import get_database
from app.services.vector_store import vector_store_service
from app.api.v1.chat import (
    format_docs,
    extract_sources,
    get_llm,
    rag_prompt,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Chat"])
settings = get_settings()


# --- Request schemas ---
class AskRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


# --- SSE streaming RAG ---
async def generate_rag_stream(
    question: str, user: dict[str, Any], session_id: str
) -> AsyncGenerator[dict, None]:
    """Stream RAG response as SSE events with real pipeline."""
    db = get_database()

    try:
        # Build access filter
        user_role = user.get("role", "student")
        user_faculty = user.get("faculty")
        pre_filter = vector_store_service.build_access_filter(user_role, user_faculty)

        # Check documents exist
        doc_count = await db.documents.count_documents({})
        if doc_count == 0:
            yield {"event": "token", "data": "The knowledge base has no documents yet."}
            yield {"event": "done", "data": ""}
            return

        # Choose retriever: hybrid (vector + full-text RRF) or MMR
        if settings.use_hybrid_search:
            try:
                retriever = vector_store_service.get_hybrid_retriever(
                    k=settings.top_k_results,
                    pre_filter=pre_filter or None,
                )
            except (ValueError, RuntimeError):
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

        # Retrieve with timeout
        try:
            docs = await asyncio.wait_for(
                retriever.ainvoke(question),
                timeout=float(settings.llm_timeout_seconds),
            )
        except asyncio.TimeoutError:
            yield {"event": "error", "data": "Search took too long"}
            return

        context = format_docs(docs)
        sources = extract_sources(docs)

        # Send session ID so the frontend can track the conversation
        yield {"event": "session_id", "data": session_id}

        # Send sources first
        if sources:
            yield {"event": "sources", "data": sources}

        # Build LCEL chain for streaming
        llm = await get_llm()
        chain = rag_prompt | llm | StrOutputParser()

        # Stream tokens
        full_answer = ""
        async for chunk in chain.astream({"context": context, "question": question}):
            full_answer += chunk
            yield {"event": "token", "data": chunk}

        # Save to chat history
        user_id = str(user["_id"])
        now = datetime.now(timezone.utc)

        # Check if session exists
        existing = await db.chat_history.find_one(
            {"session_id": session_id, "user_id": user_id}
        )

        message_pair = [
            {"role": "user", "content": question, "timestamp": now.isoformat()},
            {
                "role": "assistant",
                "content": full_answer,
                "sources": sources,
                "timestamp": now.isoformat(),
            },
        ]

        if existing:
            # Append to existing session
            await db.chat_history.update_one(
                {"session_id": session_id, "user_id": user_id},
                {
                    "$push": {"messages": {"$each": message_pair}},
                    "$set": {"updated_at": now},
                },
            )
        else:
            # Create new session
            title = question[:80] + ("..." if len(question) > 80 else "")
            await db.chat_history.insert_one(
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "title": title,
                    "messages": message_pair,
                    "created_at": now,
                    "updated_at": now,
                }
            )

        yield {"event": "done", "data": ""}

    except asyncio.TimeoutError:
        logger.error("SSE stream timed out")
        yield {"event": "error", "data": "Response timeout exceeded"}
    except RuntimeError as e:
        logger.error("SSE stream runtime error: %s", e, exc_info=True)
        yield {"event": "error", "data": "Error processing request"}
    except HTTPException as e:
        logger.error("SSE stream HTTP error: %s", e.detail)
        yield {"event": "error", "data": "Error processing request"}


async def sse_event_generator(events: AsyncGenerator) -> AsyncGenerator[str, None]:
    """Format events as SSE text stream."""
    async for event in events:
        event_type = event.get("event", "message")
        data = event.get("data", "")
        yield f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


# --- Endpoints ---
@router.post("/ask/stream")
@limiter.limit("20/minute")
async def ask_question_stream(
    body: AskRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Ask a question with SSE streaming response."""
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    if len(question) > 5000:
        raise HTTPException(status_code=400, detail="Question too long. Maximum 5000 characters")

    session_id = body.session_id or str(uuid.uuid4())
    logger.info("SSE question (session %s, role=%s)", session_id, current_user.get("role"))

    stream = generate_rag_stream(question, current_user, session_id)
    return StreamingResponse(
        sse_event_generator(stream),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Session-Id": session_id,
        },
    )


@router.get("/history")
@limiter.limit("30/minute")
async def get_history(
    request: Request,
    skip: int = 0,
    limit: int = 50,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """List user's chat sessions."""
    db = get_database()
    user_id = str(current_user["_id"])
    cursor = db.chat_history.find(
        {"user_id": user_id},
        {"messages": 0},
    ).sort("updated_at", -1).skip(skip).limit(limit)

    sessions = await cursor.to_list(length=limit)
    for s in sessions:
        s["_id"] = str(s["_id"])

    return sessions


@router.get("/history/{session_id}")
@limiter.limit("30/minute")
async def get_session(
    request: Request,
    session_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Get a specific chat session with messages."""
    db = get_database()
    user_id = str(current_user["_id"])
    session = await db.chat_history.find_one(
        {"session_id": session_id, "user_id": user_id}
    )
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    session["_id"] = str(session["_id"])
    return session


@router.delete("/history/{session_id}")
@limiter.limit("20/minute")
async def delete_session(
    request: Request,
    session_id: str,
    current_user: dict[str, Any] = Depends(get_current_user),
):
    """Delete a chat session."""
    db = get_database()
    user_id = str(current_user["_id"])
    result = await db.chat_history.delete_one(
        {"session_id": session_id, "user_id": user_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    return {"message": "Session deleted"}
