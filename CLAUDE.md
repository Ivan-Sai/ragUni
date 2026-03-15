# ragUni — University RAG Service

All work must be done in venv

## Project Overview
RAG service for universities: document uploading, vector search, AI-based question answering.

## Tech Stack
- **Backend:** FastAPI + LangChain + MongoDB Atlas Vector Search
- **Embeddings:** FastEmbed (intfloat/multilingual-e5-large, 1024 dim)
- **LLM:** Deepseek (OpenAI-compatible API)
- **DB:** MongoDB Atlas (Motor async driver)
- **Frontend:** Next.js 15 + React 19 + TypeScript + Tailwind + shadcn/ui

## Project Structure
```
ragUni/
├── backend/                # Python backend
│   ├── app/
│   │   ├── api/v1/         # FastAPI routers (documents, chat, auth, admin)
│   │   ├── core/           # Security (JWT), dependencies (RBAC)
│   │   ├── models/         # Pydantic models
│   │   ├── services/       # database, vector_store, document_parser, llm
│   │   └── utils/          # chunking, helpers
│   ├── tests/              # pytest test suite
│   ├── .env                # Backend env variables (not in git)
│   ├── .env.example
│   ├── Dockerfile
│   ├── pytest.ini
│   ├── requirements.txt
│   └── run.py
├── frontend/               # Next.js frontend
│   ├── src/
│   ├── .env.local          # Frontend env variables (not in git)
│   ├── .env.example
│   ├── Dockerfile
│   └── package.json
├── docs/                   # Documentation
├── scripts/                # One-off utility scripts
├── docker-compose.yml
└── CLAUDE.md
```

## Development Workflow
- **TDD is mandatory** — see .claude/skills/tdd.md
- Write a failing test FIRST, then implement
- Run `cd backend && pytest -v` to verify
- Mocks only for external dependencies (MongoDB, Deepseek API, FastEmbed)

## Architecture Decisions
- 3 roles: student, teacher, admin
- JWT auth (access + refresh tokens)
- Document access filtered by role + faculty in Vector Search
- SSE streaming for chat responses

## Running
```bash
# Backend dev server (from project root)
cd backend && uvicorn app.main:app --reload

# Backend tests
cd backend && pytest -v
cd backend && pytest --cov=app -v

# Frontend dev server
cd frontend && npm run dev
```

## Code Quality — ABSOLUTE RULE

**NEVER write hacky, shortcut, or "temporary" code. Every single line must be production-grade.**

This rule has NO exceptions. Violation = rewrite from scratch.

### Mandatory requirements:
- **No hardcoded values** — all config via env/settings, no default secrets
- **No `# type: ignore`, `as any`, `# noqa`, `# TODO: fix later`** — fix the problem immediately
- **No bare `except Exception`** — catch only specific exceptions
- **No `dict` instead of typed models** — always use Pydantic models / TypeScript interfaces
- **No silent error swallowing** — every error must be logged and handled properly
- **No internal detail leaks** — users see only safe, generic error messages
- **No security shortcuts** — validation at every level (input, auth, access control)
- **No code duplication** — DRY, but no premature abstractions
- **Every endpoint must have** rate limiting, proper status codes, typed request/response models
- **Every form must have** validation, loading states, error states, disabled states
- **Every API call must have** error handling, retry logic, timeout
- **Every component must have** error boundaries, loading skeletons, empty states

### Security — zero compromise:
- SECRET_KEY is required, no defaults — fail fast on startup if missing
- JWT refresh token flow must be fully implemented
- CORS strictly limited for production
- CSP headers are mandatory
- Input sanitization on every boundary (prompt injection, XSS, file validation)
- Rate limiting on all endpoints
- Log operations, NEVER log PII (emails, passwords, user questions)

### Pre-commit checklist:
- `cd backend && pytest --cov=app -v` — all tests pass
- `cd frontend && npm run build` — build with zero errors
- No `console.log` in production code
- No hardcoded URLs, keys, or secrets
- All new endpoints have tests

## Language policy

**Supported languages: English (default) + Ukrainian. Russian is strictly forbidden.**

### Code & backend:
- Code comments, docstrings, variable names — English only
- Log messages — English only
- API error messages — English only
- LLM system prompt — English (LLM responds in the user's language)

### Frontend:
- i18n via `next-intl` with two locales: `en` (default), `uk`
- All UI strings extracted to `frontend/messages/{en,uk}.json`
- No hardcoded UI text in components — always use `useTranslations()`

### Documentation:
- docs/, README, CLAUDE.md — English only

### Zero tolerance for Russian:
- No Russian text anywhere in the codebase
- This includes comments, strings, docs, translations, commit messages

## Conventions
- Language: Python 3.11+
- Async everywhere (FastAPI, Motor, async def)
- Pydantic v2 for models and settings
- API versioning: /api/v1/
