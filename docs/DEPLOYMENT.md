# Deployment Guide

Reference for running ragUni outside of a developer laptop. Covers
production-grade deployment on a single VM or a small Kubernetes
cluster.

## 1. Prerequisites

* MongoDB Atlas cluster (M10 or larger) with Vector Search enabled.
* A Deepseek API key (or any OpenAI-compatible endpoint).
* A reverse proxy that terminates TLS (Caddy, nginx, Traefik).
* Docker 24+ or Kubernetes 1.28+.

## 2. Secrets

Never commit real secrets. All config is read from env vars; the backend
fails fast if `SECRET_KEY` or `DEEPSEEK_API_KEY` is missing or weak.

Generate a production JWT secret:

```bash
openssl rand -base64 48
```

Store secrets in your platform's secret manager (Docker secrets,
Kubernetes Secrets, AWS Secrets Manager, Azure Key Vault). Mount them as
env vars; do not bake them into images.

## 3. Minimum env vars

Backend:

| Variable              | Purpose                                            |
| --------------------- | -------------------------------------------------- |
| `MONGODB_URL`         | Full Atlas connection string.                      |
| `MONGODB_DB_NAME`     | Database name (default `university_knowledge`).    |
| `SECRET_KEY`          | JWT signing key, ≥ 32 random chars.                |
| `DEEPSEEK_API_KEY`    | LLM provider key.                                  |
| `CORS_ORIGINS`        | Comma-separated list of allowed frontend origins.  |
| `VECTOR_INDEX_NAME`   | Atlas vector-search index name.                    |
| `FULLTEXT_INDEX_NAME` | Atlas full-text index name (for hybrid search).    |

Frontend:

| Variable              | Purpose                                            |
| --------------------- | -------------------------------------------------- |
| `NEXT_PUBLIC_API_URL` | Public URL of the backend (scheme + host).         |
| `AUTH_SECRET`         | NextAuth signing key.                              |
| `AUTH_URL`            | Public URL of the frontend.                        |

`NEXT_PUBLIC_*` values are inlined at build time by Next.js — they must
be present when the frontend image is built, not only at runtime.

## 4. MongoDB Atlas setup

1. Create a database `university_knowledge`.
2. Create collection `embeddings`.
3. Create a Vector Search index named `vector_index`:

   ```json
   {
     "fields": [
       {
         "type": "vector",
         "path": "embedding",
         "numDimensions": 1024,
         "similarity": "cosine"
       },
       { "type": "filter", "path": "access_role" },
       { "type": "filter", "path": "access_faculty" }
     ]
   }
   ```
4. Create a full-text Search index named `text_index` on `text` if
   hybrid retrieval is enabled (`USE_HYBRID_SEARCH=true`).
5. See `docs/ATLAS_API_SETUP.md` for programmatic index management.

## 5. Docker Compose (single host)

The bundled `docker-compose.yml` runs the backend and frontend together.
For production harden it by:

* Using `env_file: .env.prod` with permissions `600`.
* Binding containers to an internal network only; exposing ports
  exclusively via the reverse proxy.
* Adding a `read_only: true` root FS where possible; both images
  already run as non-root (`appuser`, `nextjs`).
* Pinning image digests, not floating tags.

Example snippet:

```yaml
services:
  backend:
    image: raguni-backend@sha256:...
    restart: unless-stopped
    env_file: .env.prod
    healthcheck:
      test: ["CMD", "curl", "-fs", "http://localhost:8000/api/v1/chat/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    networks: [internal]
  frontend:
    image: raguni-frontend@sha256:...
    restart: unless-stopped
    env_file: .env.prod
    depends_on: [backend]
    networks: [internal, edge]
networks:
  internal: { internal: true }
  edge: {}
```

## 6. Kubernetes sketch

* One `Deployment` per service, 2 replicas minimum.
* `PodDisruptionBudget` with `minAvailable: 1`.
* `HorizontalPodAutoscaler` on CPU for the backend (LLM waits dominate
  latency, so scale gently — 70 % target CPU).
* `Service` type `ClusterIP`; expose via `Ingress` + cert-manager.
* Mount `SECRET_KEY`, `DEEPSEEK_API_KEY`, `MONGODB_URL` from a
  `Secret`. Mount `CORS_ORIGINS` from a `ConfigMap`.
* Liveness: `/api/v1/chat/health`. Readiness: same, but only ready
  after the Atlas connection succeeds.

## 7. Reverse proxy essentials

* Terminate TLS with a modern cert (Let's Encrypt via cert-manager or
  Caddy).
* Enable HTTP/2 — SSE streaming performs much better.
* Set `proxy_read_timeout 60s` (nginx) / `transport.read_timeout 60s`
  (Caddy) so long LLM responses are not cut off.
* Forward `X-Forwarded-For` and `X-Forwarded-Proto`; FastAPI reads
  these via `Request.client`.
* Set sensible body limits (`client_max_body_size 12M` for document
  uploads; backend enforces 10 MB internally).

## 8. Observability (recommended, not yet implemented)

* **Logs:** structured JSON to stdout; scrape with Loki or CloudWatch.
* **Metrics:** add `prometheus-fastapi-instrumentator`; expose
  `/metrics` only inside the cluster.
* **Tracing:** OpenTelemetry with a B3 / W3C propagator; one span per
  RAG stage (embed, search, LLM).
* **Error tracking:** Sentry SDK in both services; scrub PII (emails,
  questions).

These are tracked as open gaps in `docs/ARCHITECTURE.md`.

## 9. Backups & disaster recovery

* MongoDB Atlas continuous backup — enable and set a 7-day PITR window.
* Test restore quarterly: create a scratch cluster, restore a snapshot,
  run `scripts/smoke_test.py` against it.
* Embeddings are re-derivable from source documents; store originals in
  object storage (S3 / Cloudflare R2) with versioning on.

## 10. Runbook summary

| Incident                | First action                                            |
| ----------------------- | ------------------------------------------------------- |
| LLM 502 / timeout       | Check Deepseek status page; verify `DEEPSEEK_API_KEY`.  |
| MongoDB connection down | Verify Atlas IP allow-list; check `mongodb_url` value.  |
| 403 storm on `/me`      | Likely `SECRET_KEY` rotation without session bump.      |
| Rate-limit false trips  | In-memory limiter is per-process; confirm single replica or move to Redis. |
| SSE drops after ~30 s   | Increase proxy read timeout; ensure HTTP/2 is enabled.  |

## 11. Pre-deploy checklist

Before each production release:

* `cd backend && pytest --cov=app -v` passes.
* `cd frontend && npm run build` succeeds with zero type errors.
* No new `console.log` in frontend code.
* No new `print(` debug calls in backend code.
* `.env.example` updated if new env vars were added.
* CHANGELOG / release notes updated.
