from fastapi import APIRouter, HTTPException
import time
from typing import List, Dict

from app.models.document import ChatRequest, ChatResponse
from app.services.database import get_database
from app.services.vectorizer import vectorizer
from app.services.llm import llm
from app.config import get_settings

router = APIRouter()
settings = get_settings()


async def retrieve_relevant_chunks(question: str, top_k: int = None) -> List[Dict]:
    """
    Retrieve most relevant document chunks for a question

    Args:
        question: User's question
        top_k: Number of chunks to retrieve

    Returns:
        List of relevant chunks with metadata
    """
    if top_k is None:
        top_k = settings.top_k_results

    db = get_database()

    # Create embedding for the question
    question_embedding = await vectorizer.embed_text(question)

    # Get all documents with their chunks
    all_chunks = []
    cursor = db.documents.find({}, {
        "filename": 1,
        "file_type": 1,
        "chunks": 1
    })

    async for doc in cursor:
        for chunk in doc.get("chunks", []):
            all_chunks.append({
                "text": chunk["text"],
                "embedding": chunk["embedding"],
                "source": doc["filename"],
                "chunk_index": chunk["chunk_index"]
            })

    if not all_chunks:
        return []

    # Calculate similarities using vectorizer
    chunk_embeddings = [chunk["embedding"] for chunk in all_chunks]
    similar_indices = await vectorizer.search_similar(
        question_embedding,
        chunk_embeddings,
        top_k=min(top_k, len(all_chunks))
    )

    # Get the most relevant chunks
    relevant_chunks = []
    for idx in similar_indices:
        chunk = all_chunks[idx]
        relevant_chunks.append({
            "text": chunk["text"],
            "source": chunk["source"],
            "chunk_index": chunk["chunk_index"]
        })

    return relevant_chunks


@router.post("/ask", response_model=ChatResponse)
async def ask_question(request: ChatRequest):
    """
    Ask a question and get an answer using RAG

    This endpoint:
    1. Creates embedding for the question
    2. Finds most relevant document chunks
    3. Sends question + context to Deepseek LLM
    4. Returns generated answer with sources
    """

    start_time = time.time()

    try:
        # Validate question
        if not request.question or len(request.question.strip()) == 0:
            raise HTTPException(status_code=400, detail="Question cannot be empty")

        print(f"Question: {request.question}")

        # Retrieve relevant chunks
        print("Retrieving relevant chunks...")
        relevant_chunks = await retrieve_relevant_chunks(request.question)

        if not relevant_chunks:
            # No documents in database - use fallback
            print("No documents found, using fallback")
            answer = await llm.generate_simple_answer(
                request.question,
                max_tokens=request.max_tokens,
                temperature=request.temperature
            )

            processing_time = time.time() - start_time

            return ChatResponse(
                answer=answer,
                sources=[],
                processing_time=processing_time
            )

        print(f"Found {len(relevant_chunks)} relevant chunks")

        # Generate answer with context
        print("Generating answer with Deepseek...")
        answer = await llm.generate_answer(
            question=request.question,
            context=relevant_chunks,
            max_tokens=request.max_tokens,
            temperature=request.temperature
        )

        processing_time = time.time() - start_time

        # Prepare sources for response
        sources = [
            {
                "source": chunk["source"],
                "chunk_index": chunk["chunk_index"],
                "preview": chunk["text"][:200] + "..." if len(chunk["text"]) > 200 else chunk["text"]
            }
            for chunk in relevant_chunks
        ]

        print(f"✓ Answer generated in {processing_time:.2f}s")

        return ChatResponse(
            answer=answer,
            sources=sources,
            processing_time=processing_time
        )

    except Exception as e:
        print(f"Error processing question: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing question: {str(e)}")


@router.get("/health")
async def health_check():
    """Health check endpoint"""

    db = get_database()

    # Count documents
    doc_count = await db.documents.count_documents({})

    # Count total chunks
    pipeline = [
        {"$project": {"total_chunks": 1}},
        {"$group": {"_id": None, "total": {"$sum": "$total_chunks"}}}
    ]

    cursor = db.documents.aggregate(pipeline)
    result = await cursor.to_list(length=1)
    chunk_count = result[0]["total"] if result else 0

    return {
        "status": "healthy",
        "database": "connected",
        "documents_count": doc_count,
        "chunks_count": chunk_count,
        "embedding_model": settings.embedding_model,
        "llm_model": settings.deepseek_model
    }
