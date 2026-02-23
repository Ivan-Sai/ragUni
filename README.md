# ragUni - University Knowledge Base with RAG

An intelligent question-answering system for universities, powered by **Retrieval-Augmented Generation (RAG)**. Upload institutional documents (schedules, syllabi, policies) and get accurate, source-cited answers in natural language.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB_Atlas-Vector_Search-47A248?logo=mongodb&logoColor=white)
![LangChain](https://img.shields.io/badge/LangChain-0.3-1C3C3C?logo=langchain&logoColor=white)

---

## The Problem

University students constantly struggle to find answers buried in dozens of PDFs, Word docs, and spreadsheets: *"When is the physics exam?"*, *"What's the schedule for session week?"*, *"Where do I find the thesis requirements?"*. Information is scattered, hard to search, and often in complex table formats.

## The Solution

**ragUni** ingests university documents, splits them into semantic chunks, generates vector embeddings, and stores everything in MongoDB Atlas. When a student asks a question, the system performs a vector similarity search to find the most relevant passages, then feeds them as context to an LLM that generates a precise, source-cited answer.

---

## Architecture

```
                        ┌─────────────────────────────────────────────┐
                        │              ragUni Pipeline                 │
                        └─────────────────────────────────────────────┘

  ╔══════════════╗      ┌──────────────┐      ┌──────────────────────┐
  ║  PDF / DOCX  ║─────▶│  Document    │─────▶│  Text Chunking       │
  ║  / XLSX      ║      │  Parser      │      │  (1000 chars, 200    │
  ╚══════════════╝      └──────────────┘      │   overlap)           │
                                               └─────────┬────────────┘
                                                         │
                                                         ▼
                                               ┌──────────────────────┐
                                               │  FastEmbed           │
                                               │  multilingual-e5-    │
                                               │  large (1024-dim)    │
                                               └─────────┬────────────┘
                                                         │
                                                         ▼
                                               ┌──────────────────────┐
                                               │  MongoDB Atlas       │
                                               │  Vector Search       │
                                               └──────────────────────┘
                                                         ▲
                                                         │ cosine
                                                         │ similarity
  ╔══════════════╗      ┌──────────────┐      ┌─────────┴────────────┐
  ║  Student     ║─────▶│  Question    │─────▶│  Retrieve Top-K      │
  ║  Question    ║      │  Embedding   │      │  Relevant Chunks     │
  ╚══════════════╝      └──────────────┘      └─────────┬────────────┘
                                                         │
                                                         ▼
                                               ┌──────────────────────┐
                                               │  Deepseek LLM        │
                                               │  Context + Question   │
                                               │  → Answer + Sources   │
                                               └──────────────────────┘
```

---

## Key Features

- **Multi-format ingestion** - Upload PDF, DOCX, and XLSX files via REST API
- **Multilingual embeddings** - Uses `intfloat/multilingual-e5-large` (100+ languages, including Ukrainian) with local inference via FastEmbed
- **Vector search** - MongoDB Atlas Vector Search with cosine similarity for fast, semantic retrieval
- **RAG pipeline** - LangChain orchestration connecting retrieval to Deepseek LLM for answer generation
- **Source attribution** - Every answer includes references to the exact document chunks it was derived from
- **Async by design** - Built on FastAPI + Motor (async MongoDB driver) for high concurrency
- **Auto-generated docs** - Swagger UI and ReDoc available out of the box

---

## Tech Stack

| Layer | Technology |
|---|---|
| **API Framework** | FastAPI + Uvicorn |
| **Database** | MongoDB Atlas (documents, vectors) |
| **Embedding Model** | `intfloat/multilingual-e5-large` via FastEmbed (local, 1024-dim) |
| **LLM** | Deepseek Chat (via OpenAI-compatible API) |
| **RAG Orchestration** | LangChain + LangChain-MongoDB |
| **Document Parsing** | PyPDF2, python-docx, Pandas + Openpyxl |
| **Validation** | Pydantic v2 |

---

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/Ivan-Sai/ragUni.git
cd ragUni

python -m venv venv
source venv/bin/activate   # Linux/Mac
venv\Scripts\activate      # Windows

pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Fill in your credentials:

```env
MONGODB_URL=mongodb+srv://<user>:<password>@cluster.mongodb.net/
DEEPSEEK_API_KEY=your_key_here
```

### 3. Run

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is now live at `http://localhost:8000` with interactive docs at `/docs`.

---

## API Reference

### Documents

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/documents/upload` | Upload and process a document (PDF/DOCX/XLSX) |
| `GET` | `/api/v1/documents/list` | List all uploaded documents with chunk counts |
| `DELETE` | `/api/v1/documents/{id}` | Remove a document and its chunks |

### Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/chat/ask` | Ask a question and get a RAG-generated answer |
| `GET` | `/api/v1/chat/health` | System health check (DB, models, counts) |

### Example: Ask a question

```bash
curl -X POST http://localhost:8000/api/v1/chat/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "When is the physics exam?", "max_tokens": 1000}'
```

```json
{
  "answer": "According to the exam schedule, the physics exam is on January 15 at 10:00 in room 205...",
  "sources": [
    {
      "source": "exam_schedule.pdf",
      "chunk_index": 3,
      "preview": "January 15 — Physics (room 205)..."
    }
  ],
  "processing_time": 2.34
}
```

---

## Project Structure

```
ragUni/
├── app/
│   ├── main.py                 # FastAPI application & lifespan events
│   ├── config.py               # Pydantic settings from .env
│   ├── models/
│   │   └── document.py         # Request/response schemas
│   ├── services/
│   │   ├── database.py         # Async MongoDB connection (Motor)
│   │   ├── document_parser.py  # PDF / DOCX / XLSX text extraction
│   │   ├── vectorizer.py       # FastEmbed embedding generation
│   │   ├── vector_store.py     # LangChain MongoDB vector store
│   │   └── llm.py              # Deepseek LLM integration
│   ├── api/v1/
│   │   ├── documents.py        # Document CRUD endpoints
│   │   └── chat.py             # Question-answering endpoint
│   └── utils/
│       └── chunking.py         # Text splitting with configurable overlap
├── requirements.txt
├── run.py
├── .env.example
└── README.md
```

---

## Configuration

All settings are managed via environment variables (`.env`):

| Variable | Description | Default |
|----------|-------------|---------|
| `MONGODB_URL` | MongoDB Atlas connection string | *required* |
| `MONGODB_DB_NAME` | Database name | `university_knowledge` |
| `DEEPSEEK_API_KEY` | Deepseek API key | *required* |
| `DEEPSEEK_MODEL` | LLM model name | `deepseek-chat` |
| `CHUNK_SIZE` | Characters per chunk | `1000` |
| `CHUNK_OVERLAP` | Overlap between chunks | `200` |
| `EMBEDDING_MODEL` | Embedding model | `intfloat/multilingual-e5-large` |
| `VECTOR_DIMENSION` | Embedding dimensions | `1024` |
| `TOP_K_RESULTS` | Retrieved chunks per query | `5` |

---

## Performance

| Stage | Latency |
|-------|---------|
| Embedding generation | ~100ms per chunk (local) |
| Vector search | 50-100ms |
| LLM answer generation | 1-3s |
| **End-to-end response** | **2-4s** |
