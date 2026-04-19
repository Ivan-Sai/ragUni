# ragUni — Architecture Overview

This document describes the system shape, the data flow, and the key
design decisions. It is the primary reference a thesis committee or a
new contributor should read first.

## 1. Context

A university assistant that lets students and staff ask natural-language
questions and answers them from the institution's own documents
(regulations, syllabi, schedules, announcements). Answers must be
grounded in real sources, respect role-based access, and be available in
Ukrainian and English.

## 2. High-level diagram

```
 ┌───────────────┐     HTTPS      ┌────────────────────┐
 │  Next.js 15   │ ──────────────▶│  FastAPI backend   │
 │  (React 19)   │◀────── SSE ────│  (LangChain LCEL)  │
 └───────┬───────┘                └──────┬─────────────┘
         │                               │
     NextAuth                     ┌──────┼───────────┬─────────────┐
     (JWT, http)                  │      │           │             │
                                  ▼      ▼           ▼             ▼
                          ┌──────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐
                          │ MongoDB  │ │ Vector │ │ FastEmbed│ │ Deepseek │
                          │ Atlas    │ │ Search │ │ (E5-L)   │ │ LLM API  │
                          └──────────┘ └────────┘ └──────────┘ └──────────┘
```

* **Authentication:** JWT access + refresh tokens issued by the backend;
  the frontend holds them inside a NextAuth session.
* **Authorisation:** RBAC with three roles (`student`, `teacher`,
  `admin`) enforced both at the API boundary (`require_role`) and inside
  vector search via a `pre_filter`.
* **Chat:** questions are embedded, top-k chunks are retrieved by
  MongoDB Atlas Vector Search (with optional hybrid RRF), the LCEL chain
  then formats the prompt and streams tokens from Deepseek over SSE.

## 3. Source tree

See [CLAUDE.md](../CLAUDE.md) for the canonical file layout. Key
modules:

| Path                                   | Responsibility                                   |
| -------------------------------------- | ------------------------------------------------ |
| `backend/app/api/v1/auth.py`           | Register / login / refresh / me.                 |
| `backend/app/api/v1/admin.py`          | User management, teacher approvals.              |
| `backend/app/api/v1/documents.py`      | Upload, list, delete documents.                  |
| `backend/app/api/v1/chat.py`           | One-shot `/ask`, LCEL RAG chain.                 |
| `backend/app/api/v1/chat_history.py`   | SSE streaming, chat session persistence.         |
| `backend/app/core/security.py`         | Password hashing, JWT encode/decode.             |
| `backend/app/core/dependencies.py`     | `get_current_user`, `require_role`.              |
| `backend/app/services/vector_store.py` | Vector search + access filter builder.           |
| `backend/app/services/document_parser.py` | PDF / DOCX / XLSX extraction.                 |
| `backend/app/utils/prompt_safety.py`   | Prompt-injection sanitization.                   |
| `frontend/src/lib/auth.ts`             | NextAuth config, JWT refresh flow.               |
| `frontend/src/lib/api.ts`              | Typed API client.                                |
| `frontend/src/lib/env.ts`              | Fail-fast env validation.                        |

## 4. Request lifecycle: "student asks a question"

1. Browser submits `POST /api/v1/chat/ask/stream` with a Bearer JWT.
2. `get_current_user` decodes the JWT, loads the user, verifies
   `is_active` **and** `is_approved`.
3. `sanitize_question` strips control tokens and blocks obvious
   jailbreaks.
4. `vector_store_service.build_access_filter(role, faculty)` builds a
   MongoDB filter so the user cannot see chunks outside their role or
   faculty.
5. Hybrid (vector + full-text RRF) or MMR retrieval returns top-k chunks
   with a timeout.
6. LCEL chain (prompt → Deepseek → `StrOutputParser`) streams tokens.
7. Each SSE frame is persisted into `chat_history` so the conversation
   survives a page refresh.

## 5. Architecture Decision Records (ADRs)

Short, self-contained. Each ADR follows: *context → decision →
consequences*. Expand any of these in the thesis if the committee digs
deeper.

### ADR-001 — FastAPI over Django REST Framework

**Context.** The backend is I/O bound (MongoDB + LLM + embedding). Both
are mature Python frameworks.

**Decision.** FastAPI.

**Consequences.** First-class async support (crucial for SSE + LLM
streaming), Pydantic for typed request/response models, lower boilerplate
than DRF. Trade-off: less admin-panel tooling than Django, but the
project's admin is custom anyway.

### ADR-002 — MongoDB Atlas Vector Search over pgvector / Weaviate

**Context.** We need a store for both documents and embeddings, with
filterable metadata for role/faculty scoping.

**Decision.** MongoDB Atlas Vector Search.

**Consequences.** One database instead of two (document store + vector
store), managed HNSW index, native `$vectorSearch` with pre-filter
support that is essential for row-level security. Trade-off: cloud
vendor lock-in and a minimum instance size — acceptable for a
university deployment, documented in `docs/DEPLOYMENT.md`.

### ADR-003 — FastEmbed + multilingual-e5-large

**Context.** The corpus is mostly Ukrainian with English technical terms
interleaved. Students on the defense committee will test it in both
languages.

**Decision.** `intfloat/multilingual-e5-large` (1024-dim) via FastEmbed.

**Consequences.** Strong multilingual recall, runs CPU-only in the
backend container (no GPU required). Trade-off: higher memory footprint
than MiniLM; the E5 prefix convention (`passage: ` / `query: `) must be
preserved — see `backend/app/services/vector_store.py`.

### ADR-004 — Deepseek over OpenAI / Anthropic

**Context.** The project is a student diploma with a small budget; the
LLM must be OpenAI-compatible for LCEL reuse.

**Decision.** Deepseek (`deepseek-chat`) via its OpenAI-compatible API.

**Consequences.** Low cost per token, acceptable Ukrainian quality,
works out of the box with `langchain-openai`. Trade-off: no long-term
SLA commitment comparable to OpenAI; the `deepseek_api_base` is
configurable so a swap to another OpenAI-compatible provider is a
single env-var change.

### ADR-005 — SSE instead of WebSockets for chat streaming

**Context.** We need to stream LLM tokens from backend to browser.

**Decision.** Server-Sent Events over HTTPS.

**Consequences.** One-way streaming is all we need; SSE reuses normal
HTTP/2 connections, survives most corporate proxies, and integrates
directly with FastAPI's `StreamingResponse`. Trade-off: the client
cannot send mid-stream; this is acceptable because the user interaction
model is request → stream → done.

### ADR-006 — JWT with refresh tokens over server-side sessions

**Context.** The frontend is a separate Next.js deployment; sessions
must survive page reloads and cross-origin calls.

**Decision.** JWT access (30 min) + refresh (7 days) tokens. Refresh
tokens are re-validated against the database on every use — a
deactivated or unapproved account cannot mint new access tokens.

**Consequences.** Stateless backend, easy horizontal scaling.
Trade-off: revocation is not instant — mitigated by the DB check in
`/refresh` and the short access-token lifetime.

## 6. Security posture (summary)

Detailed review in [docs/SECURITY.md](SECURITY.md) (TODO). Highlights:

* Passwords hashed with bcrypt; no plaintext logs.
* `SECRET_KEY` required at startup, fails fast if < 32 chars or default.
* CORS explicitly listed, CSP in Next.js middleware.
* Rate limiting via `slowapi` on auth, chat, admin endpoints.
* RBAC enforced twice: at the API layer and inside vector search.
* Prompt-injection sanitizer on every user question.
* File-type validation + size limit on uploads.
* Frontend env is validated eagerly — no silent localhost fallbacks in
  production.

## 7. Known gaps

Tracked explicitly — the thesis should acknowledge them:

* Audit log (who approved whom, who deleted which chat) — not yet
  persisted.
* Rate-limit storage is in-process — replace with Redis for multi-node
  deployments.
* No automatic DB migrations; schema evolution is ad-hoc.
* No Sentry / OpenTelemetry wiring.
* RAG evaluation harness described in `docs/EVALUATION.md` is a
  specification, not yet code.
