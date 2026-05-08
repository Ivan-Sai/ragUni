"""Chat history endpoints + SSE streaming chat with real RAG pipeline."""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from langchain_core.output_parsers import StrOutputParser
from pydantic import BaseModel

from app.config import get_settings
from app.core.dependencies import get_current_user
from app.core.rate_limit import limiter
from app.models.audit import AuditAction
from app.services.audit_log import record_action as audit_record_action
from app.services.database import get_database
from app.services.input_sanitizer import input_sanitizer
from app.services.vector_store import vector_store_service
from app.api.v1.chat import (
    NO_ANSWER_TEXT,
    _attach_document_ids,
    _dedup_chunks,
    _structured_records_as_sources,
    extract_sources,
    format_chat_history,
    format_docs,
    get_llm,
    rag_prompt,
    rag_prompt_with_history,
)
from app.services.query_analyzer import analyze_query
from app.services.retrieval_orchestrator import format_structured_context, retrieve

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
    start_time = time.time()

    try:
        # Prompt injection check
        is_injection, pattern = input_sanitizer.detect_injection(question)
        if is_injection:
            yield {
                "event": "error",
                "data": "Ваше питання містить неприпустимі інструкції",
            }
            return
        question = input_sanitizer.sanitize(question)

        # Build access + audience filter (mirrors /ask). The
        # ``target_doc_types`` slot is filled in *after* the analyzer
        # runs (the analyzer may narrow retrieval to e.g. regulation
        # docs only); placeholder here keeps the call signature
        # symmetric with the sync /ask path.
        user_role = user.get("role", "student")

        # Check documents exist
        doc_count = await db.documents.count_documents({})
        if doc_count == 0:
            yield {"event": "token", "data": "В базі знань поки немає документів."}
            yield {"event": "done", "data": ""}
            return

        # New 2026-grade pipeline: query analyzer + multi-strategy
        # retrieval orchestrator + reranker. See chat.run_rag_chain
        # for the architecture rationale. Mirrored here so the SSE
        # endpoint shares the same behaviour as the sync /ask path.

        # Load conversation history early — the analyzer uses it for
        # pronoun resolution on follow-up questions.
        existing_session = await db.chat_history.find_one(
            {"session_id": session_id, "user_id": str(user["_id"])},
            {"messages": {"$slice": -settings.max_conversation_messages}},
        )
        prior_messages = existing_session["messages"] if existing_session else []

        analysis = await analyze_query(question, chat_history=prior_messages)

        if analysis.is_personal and (user.get("year") or user.get("level")):
            suffix_parts: list[str] = []
            if user.get("level"):
                suffix_parts.append(str(user["level"]))
            if user.get("year"):
                suffix_parts.append(f"{user['year']} курс")
            if suffix_parts:
                analysis.reformulated_query = (
                    f"{analysis.reformulated_query or question}"
                    f" (для студента {' '.join(suffix_parts)})"
                ).strip()

        # Filter is built AFTER the analyzer so target_doc_types
        # narrowing is applied — e.g. policy questions only hit
        # regulation documents.
        pre_filter = vector_store_service.build_access_filter(
            user_role=user_role,
            user_faculty_id=str(user["faculty_id"]) if user.get("faculty_id") else None,
            user_group_id=str(user["group_id"]) if user.get("group_id") else None,
            user_year=user.get("year"),
            user_level=user.get("level"),
            target_doc_types=analysis.target_doc_types or None,
        )

        try:
            retrieval = await retrieve(
                query=question,
                analysis=analysis,
                pre_filter=pre_filter,
                user_role=user_role,
                user_faculty_id=str(user["faculty_id"]) if user.get("faculty_id") else None,
                user_group_id=str(user["group_id"]) if user.get("group_id") else None,
                user_year=user.get("year"),
                user_level=user.get("level"),
                initial_k=30,
                final_k=settings.top_k_results,
            )
        except HTTPException as exc:
            yield {"event": "error", "data": exc.detail}
            return

        docs = retrieval.docs
        structured_records = retrieval.structured_records

        if not docs and not structured_records:
            logger.info("SSE no-answer guard: 0 docs across strategies")
            yield {"event": "session_id", "data": session_id}
            yield {"event": "token", "data": NO_ANSWER_TEXT}
            yield {"event": "done", "data": ""}
            return

        if structured_records:
            context = format_structured_context(structured_records)
            sources = _structured_records_as_sources(structured_records)
        else:
            scored = [d.metadata["score"] for d in docs if "score" in d.metadata]
            if scored and max(scored) < settings.no_answer_score_threshold:
                logger.info(
                    "SSE no-answer guard tripped: top=%.2f",
                    max(scored),
                )
                yield {"event": "session_id", "data": session_id}
                yield {"event": "token", "data": NO_ANSWER_TEXT}
                yield {"event": "done", "data": ""}
                return
            docs = _dedup_chunks(docs)
            context = format_docs(docs)
            sources = extract_sources(docs)
        sources = await _attach_document_ids(sources)

        # Send session ID so the frontend can track the conversation
        yield {"event": "session_id", "data": session_id}

        # Send sources first
        if sources:
            yield {"event": "sources", "data": sources}

        # ``prior_messages`` was loaded earlier (the analyzer needed
        # it for pronoun resolution). Reuse here to avoid a second
        # round trip to Mongo.

        # Build LCEL chain — use history-aware prompt when prior messages exist
        llm = await get_llm()
        if prior_messages:
            history_text = format_chat_history(
                prior_messages, settings.max_conversation_messages
            )
            chain = rag_prompt_with_history | llm | StrOutputParser()
            chain_input = {
                "chat_history": history_text,
                "context": context,
                "question": question,
            }
        else:
            chain = rag_prompt | llm | StrOutputParser()
            chain_input = {"context": context, "question": question}

        # Stream tokens
        full_answer = ""
        async for chunk in chain.astream(chain_input):
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

        # Track analytics
        from app.services.analytics import track_event
        await track_event(
            "chat_query",
            user_id,
            user.get("role", "student"),
            {"response_time": round(time.time() - start_time, 2), "question_length": len(question)},
        )

        yield {"event": "done", "data": ""}

    except asyncio.TimeoutError:
        logger.error("SSE stream timed out")
        yield {"event": "error", "data": "Час очікування відповіді вичерпано"}
    except RuntimeError as e:
        logger.error("SSE stream runtime error: %s", e, exc_info=True)
        yield {"event": "error", "data": "Помилка при обробці запиту"}
    except HTTPException as e:
        logger.error("SSE stream HTTP error: %s", e.detail)
        yield {"event": "error", "data": "Помилка при обробці запиту"}
    except Exception as e:
        # Catch-all so that any unexpected backend failure (including
        # PyMongoError from Atlas Vector Search filter validation)
        # surfaces to the user as a clean error event instead of an
        # abruptly closed stream that leaves the UI hanging.
        logger.error(
            "SSE stream unhandled error (%s): %s",
            type(e).__name__,
            e,
            exc_info=True,
        )
        yield {"event": "error", "data": "Помилка при обробці запиту"}


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

    is_injection, _pattern = input_sanitizer.detect_injection(question)
    if is_injection:
        raise HTTPException(
            status_code=400,
            detail="Ваше питання містить неприпустимі інструкції",
        )
    question = input_sanitizer.sanitize(question)

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
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
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

    # Clean up associated feedback
    await db.feedback.delete_many({"session_id": session_id, "user_id": user_id})

    await audit_record_action(
        actor=current_user,
        action=AuditAction.CHAT_SESSION_DELETED,
        resource_type="chat_session",
        resource_id=session_id,
    )
    return {"message": "Session deleted"}
