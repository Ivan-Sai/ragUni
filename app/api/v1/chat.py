"""
Chat API with LangChain RAG (Retrieval-Augmented Generation)

This module provides intelligent question-answering using:
- MongoDB Atlas Vector Search for semantic retrieval
- LangChain for RAG orchestration
- Deepseek LLM for answer generation
"""
from fastapi import APIRouter, HTTPException
import time
from typing import List, Dict

from langchain_openai import ChatOpenAI
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from langchain_community.callbacks.manager import get_openai_callback

from app.models.document import ChatRequest, ChatResponse
from app.services.database import get_database
from app.services.vector_store import vector_store_service
from app.config import get_settings

router = APIRouter()
settings = get_settings()


# Initialize LLM (Deepseek via OpenAI-compatible API)
llm = ChatOpenAI(
    model=settings.deepseek_model,
    api_key=settings.deepseek_api_key,
    base_url=settings.deepseek_api_base,
    temperature=settings.llm_temperature,
    max_tokens=settings.llm_max_tokens
)

# RAG Prompt Template
prompt_template = """Ти - інтелектуальний асистент університету, який допомагає студентам та викладачам знаходити інформацію з документів.

**ВАЖЛИВІ ПРАВИЛА:**
1. Відповідай ТІЛЬКИ на основі наданого контексту
2. Якщо в контексті немає відповіді - чесно скажи "В наявних документах немає інформації про це"
3. ЗАВЖДИ вказуй джерела: "Згідно з [назва документа]..."
4. Будь точним з датами, цифрами, іменами
5. Відповідай українською мовою

**КОНТЕКСТ З ДОКУМЕНТІВ:**
{context}

**ПИТАННЯ СТУДЕНТА:**
{question}

**ТВОЯ ВІДПОВІДЬ:**"""

PROMPT = PromptTemplate(
    template=prompt_template,
    input_variables=["context", "question"]
)

# Initialize RAG chain (lazy initialization)
_qa_chain = None


def get_qa_chain():
    """Get or create QA chain"""
    global _qa_chain

    if _qa_chain is None:
        # Ensure vector store is initialized
        vector_store_service.initialize()

        # Create retriever from vector store
        retriever = vector_store_service.vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={
                "k": settings.top_k_results
            }
        )

        # Create RetrievalQA chain
        _qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",  # "stuff" - все чанки в один промпт
            retriever=retriever,
            return_source_documents=True,
            chain_type_kwargs={
                "prompt": PROMPT,
                "verbose": False
            }
        )

        print("✓ LangChain RAG chain initialized")

    return _qa_chain


@router.post("/ask", response_model=ChatResponse)
async def ask_question(request: ChatRequest):
    """
    Ask a question and get answer using LangChain RAG

    **Flow:**
    1. LangChain creates embedding for question
    2. MongoDB Atlas Vector Search finds relevant chunks
    3. LangChain formats prompt with context
    4. Deepseek LLM generates answer
    5. Returns answer with source documents
    """
    start_time = time.time()

    try:
        # Validate question
        if not request.question or len(request.question.strip()) == 0:
            raise HTTPException(status_code=400, detail="Question cannot be empty")

        print(f"\n📝 Question: {request.question}")

        # Check if we have any documents
        db = get_database()
        doc_count = await db.documents.count_documents({})

        if doc_count == 0:
            # No documents - return friendly message
            return ChatResponse(
                answer="В базі знань поки немає документів. "
                       "Будь ласка, завантажте документи через endpoint /api/v1/documents/upload",
                sources=[],
                processing_time=time.time() - start_time
            )

        # Get QA chain
        qa_chain = get_qa_chain()

        # Run RAG chain (всё автоматически!)
        print("🔍 Searching relevant documents...")
        print("🤖 Generating answer with Deepseek...")

        # Track token usage
        with get_openai_callback() as cb:
            result = qa_chain.invoke({"query": request.question})

            print(f"💰 Tokens used: {cb.total_tokens} (prompt: {cb.prompt_tokens}, completion: {cb.completion_tokens})")

        # Extract answer and sources
        answer = result["result"]
        source_documents = result.get("source_documents", [])

        # Format sources for response
        sources = []
        for doc in source_documents:
            metadata = doc.metadata
            sources.append({
                "source": metadata.get("source_file", "Unknown"),
                "chunk_index": metadata.get("chunk_index", 0),
                "preview": doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content
            })

        processing_time = time.time() - start_time
        print(f"✅ Answer generated in {processing_time:.2f}s")

        return ChatResponse(
            answer=answer,
            sources=sources,
            processing_time=processing_time
        )

    except Exception as e:
        print(f"❌ Error processing question: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error processing question: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """
    Health check endpoint with detailed system status
    """
    try:
        # Check database connection
        db = get_database()
        doc_count = await db.documents.count_documents({})

        # Get vector store stats
        vector_store_service.initialize()
        stats = vector_store_service.get_stats()

        # Check LLM availability (simple test)
        llm_status = "healthy"
        try:
            # Quick test call
            test_response = llm.invoke("test")
            if not test_response:
                llm_status = "degraded"
        except Exception as e:
            llm_status = f"unhealthy: {str(e)}"

        return {
            "status": "healthy",
            "components": {
                "database": "connected",
                "vector_store": "initialized",
                "llm": llm_status
            },
            "statistics": {
                "documents_count": doc_count,
                **stats
            },
            "configuration": {
                "embedding_model": settings.embedding_model,
                "llm_model": settings.deepseek_model,
                "chunk_size": settings.chunk_size,
                "chunk_overlap": settings.chunk_overlap,
                "top_k_results": settings.top_k_results
            }
        }

    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
