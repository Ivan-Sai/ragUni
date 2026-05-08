# RAG architecture

This is the production RAG pipeline. The design follows 2026-era best
practices: an LLM-driven document classifier on ingest, type-specific
extractors and chunkers, Anthropic Contextual Retrieval, an LLM query
analyser, multi-strategy retrieval with RRF fusion, LLM cross-encoder
reranking, and a self-correction pass — assembled out of small
composable services so each piece can evolve independently.

## Why the design looks this way

Earlier versions of this system pushed every document through a single
extractor and every query through a keyword router. Both broke as soon
as the corpus diverged: schedules with vertical text confused the
parser, regulations with no row structure produced empty
``structured_records``, and queries like "як перевестися на іншу
спеціальність" returned timetable fragments because the keyword router
fell back to vector-search-everything.

The fix is two complementary pipelines that meet in the vector store:

1. **Ingest-side specialisation** (this document, "Ingest pipeline")
   classifies each document and runs the right extractor + chunker for
   its type, then prepends an Anthropic-style document-context line to
   every chunk before embedding.
2. **Query-side specialisation** ("Retrieval pipeline") uses a query
   analyser to extract intent + entities + target document types, runs
   structured / vector / lexical retrieval in parallel, fuses with RRF,
   and reranks with the LLM cross-encoder. A self-correction pass
   guards against hallucinated "no information" answers.

Both pipelines share the same audience-filter mechanism so a chunk
written for one group never reaches a student in another.

## Ingest pipeline

```
        Upload PDF / DOCX / XLSX / TXT
                     │
                     ▼
         ┌──────────────────────┐
         │  document_parser     │  pdfplumber + de-stack
         │                      │  vertical text + table
         │                      │  serialisation
         └──────────┬───────────┘
                    ▼
         ┌──────────────────────┐
         │  document_classifier │  one LLM call →
         │                      │  schedule | regulation |
         │                      │  curriculum | prose |
         │                      │  exam_protocol | tabular
         └──────────┬───────────┘
                    ▼
         ┌──────────────────────┐
         │  generate_document_  │  one LLM call → ≤30-word
         │  context             │  doc summary used as
         │                      │  Anthropic Contextual
         │                      │  Retrieval prefix
         └──────────┬───────────┘
                    ▼
         ┌──────────────────────┐
         │  extractor_registry  │  type-specific Extractor:
         │                      │  • schedule → row LLM extract
         │                      │  • regulation → section split
         │                      │  • curriculum → heading split
         │                      │  • prose / tabular / unknown
         │                      │    → recursive split
         └──────────┬───────────┘
                    ▼
         ┌──────────────────────┐
         │  vector_store        │  doc_type, target_group_ids,
         │                      │  target_years, target_level,
         │                      │  faculty_id stamped on every
         │                      │  chunk for retrieval filters
         └──────────────────────┘
```

### Components

| File | Role |
|---|---|
| `services/document_parser.py` | Raw text + table extraction. De-stacks vertically-written labels (Ukrainian schedules print "понеділок" letter-by-letter). |
| `services/document_classifier.py` | One LLM call assigns a `doc_type` from a fixed vocabulary. Falls back to `unknown` (= prose path) on any failure. |
| `services/extractor_registry.py` | Strategy registry. Each `Extractor` subclass owns one type's prompt, schema, and chunking strategy, and returns a uniform `ExtractionResult`. |
| `services/extractor_registry.generate_document_context` | Anthropic Contextual Retrieval (Sept 2024). One LLM call per document → ~+35% retrieval accuracy when prepended to each chunk before embedding. |
| `services/llm_extractor.py` | Schedule-row LLM extractor reused by `_ScheduleExtractor`. |
| `api/v1/documents.py` | Orchestrates the full ingest pipeline and stamps `doc_type`, `doc_type_confidence`, `document_context`, plus the audience metadata, onto each chunk. |

### Extractors today

| `doc_type` | Extractor | Chunking strategy | Schema |
|---|---|---|---|
| `schedule` | `_ScheduleExtractor` | one chunk per LLM-extracted record | `{type, group, year, level, day, time, subject, teacher, room, …}` |
| `exam_protocol` | `_ExamProtocolExtractor` | same as schedule, different `method` tag | same |
| `regulation` | `_RegulationExtractor` | split at `Стаття N`, `Розділ N`, `1.1.` etc.; cap sections at 1500 chars | none (free text) |
| `curriculum` | `_CurriculumExtractor` | split at `Змістовий модуль`, `Тема`, `Лекція`, `Силабус`, `Робоча програма` | none |
| `prose` / `tabular` / `unknown` | `_RecursiveProseExtractor` | LangChain RecursiveCharacterTextSplitter with the global chunk size | none |

Adding a new doc_type means writing one new `Extractor` subclass and
registering it in `_REGISTRY`. Nothing else needs to change.

```
┌─────────────────────────────────────────────────────────────────┐
│                       USER QUESTION                              │
└────────────────────────────────┬────────────────────────────────┘
                                 ▼
                ┌───────────────────────────────────┐
                │  1.  QueryAnalyzer                │
                │     services/query_analyzer.py    │
                └───────────────────────────────────┘
                                 │
            QueryAnalysis { intent, entities,
                            reformulated_query,
                            preferred_strategies,
                            is_personal }
                                 │
                                 ▼
                ┌───────────────────────────────────┐
                │  2.  RetrievalOrchestrator        │
                │     services/retrieval_orchestrator
                │                                   │
                │   ┌─────────┐  ┌─────────┐  ┌────┐│
                │   │structured│  │ vector  │  │ BM25││
                │   │ Mongo   │  │ Atlas   │  │ Atlas││
                │   └────┬────┘  └────┬────┘  └──┬──┘│
                │        │            │          │   │
                │        └────► RRF merge ◄─────┘    │
                │                  │                 │
                │                  ▼                 │
                │            top-50 candidates       │
                └────────────────┬──────────────────┘
                                 ▼
                ┌───────────────────────────────────┐
                │  3.  LLM cross-encoder rerank     │
                │     services/reranker.py          │
                │     top-50 → top-15               │
                └────────────────┬──────────────────┘
                                 ▼
                ┌───────────────────────────────────┐
                │  4.  Answer generation            │
                │     api/v1/chat.run_rag_chain     │
                │     prompt | LLM | parser          │
                └────────────────┬──────────────────┘
                                 ▼
                ┌───────────────────────────────────┐
                │  5.  Self-correction              │
                │     IF answer == "no info"        │
                │      AND structured records exist │
                │      → retry with assertive prompt│
                └────────────────┬──────────────────┘
                                 ▼
                          FINAL ANSWER
```

## Component reference

### 1. `services/query_analyzer.py`

A small Deepseek call (~300ms, temperature 0) classifies the question
into `intent`, extracts `entities` (day, date, subject, teacher, room),
flags whether the query is personal (refers to the user's own data),
and emits a `reformulated_query` with pronouns resolved. Falls back to
a vector-only `general` analysis on any failure path so RAG remains
operational even if the analyzer is down.

This module is **generic**: the rest of the pipeline reacts to the
analysis, but the analyzer itself doesn't know about schedules, exams,
or any specific domain. New query types are added by teaching the
orchestrator how to react, not by editing this file.

### 2. `services/retrieval_orchestrator.py`

Runs the strategies the analyzer flagged in parallel, fuses their
ranked outputs with **Reciprocal Rank Fusion** (`k=60`), and returns a
single ordered list. Always tries `structured` whenever the analyzer
extracted any entities — structured retrieval is cheap, deterministic,
and frequently the only path that answers timetable / exam questions
correctly.

Strategies:

| Name        | Backend                   | Best for                          |
|-------------|---------------------------|-----------------------------------|
| structured  | `documents.structured_records` direct query | "коли іспит з X?", "розклад в четвер" |
| vector      | Atlas Vector Search       | semantic similarity, paraphrases  |
| lexical     | Atlas Hybrid Retriever    | rare terms, surnames, doc titles  |

### 3. `services/structured_retriever.py`

Entity-driven Mongo lookup over the `structured_records` field that
`llm_extractor.py` populates at upload time. Filters by:

* The user's audience: faculty, group, year, level (mirrors
  `vector_store.build_access_filter` so it can never expose data the
  vector path would refuse).
* The analyzer's entities: day, date, subject, teacher, room,
  record_type. Subject / teacher use case-insensitive substring match
  so `матлогіка` resolves to `Математична логіка`.
* Temporal soundness: when the query mentions a day/date, records that
  lack a `day` field are rejected — the previous keyword router kept
  them, leaking self-study slots into Thursday answers.

### 4. `services/reranker.py`

LLM cross-encoder over the top-50 candidates. Scores each
`(query, document)` pair on a 0-10 relevance scale and keeps the top
N (default 15). Uses Deepseek with `temperature=0` so the same input
produces a deterministic ordering. Caps candidates at 50 before
rerank — past that the marginal benefit shrinks while latency grows
linearly.

Failure path: returns the original top-N order. Reranking is a quality
improvement, not a correctness requirement.

### 5. `chat.run_rag_chain` self-correction

After the LLM produces an answer, a regex check detects the "no
information" failure mode (`немає інформації`, `не містить`, …). If
structured records were retrieved but the LLM still bailed out, we
retry with the same context plus a short reminder that the context is
authoritative for the user's audience. One extra LLM call in the worst
case; ~zero overhead when the first answer was substantive.

## Why each component matters

| Failure we saw | Component that fixes it |
|---|---|
| Keyword router missed `"коли у мене лекція"` because no day mentioned | LLM analyzer — works on intent, not surface keywords |
| Top-20 vector returned only Mon-Wed self-study, never Thursday | Structured retriever — pulls **all** records matching audience + day |
| Master KCM records leaking to bachelor СА student | Hard audience filter on every retrieval branch |
| LLM said "no info" while the schedule was right there in context | Self-correction retry with assertive prompt |
| Top result was a generic syllabus chunk instead of the schedule row | Cross-encoder rerank: ranks by semantic match, not embedding cosine |

## Operational notes

* All LLM components (analyzer, reranker) use a low timeout
  (15-20s) and degrade gracefully — RAG remains operational with
  vector-only retrieval if either is unavailable.
* The structured branch reads `documents.structured_records`, which
  is populated only when the admin uploaded with
  `use_llm_extraction=True`. For documents indexed as raw text, the
  orchestrator falls through to vector + lexical seamlessly.
* Embedding lookups use `analysis.reformulated_query` (pronoun-
  resolved) while the reranker uses the original question — the
  reranker is judging intent against the user's actual words, the
  embedder benefits from the cleaner phrasing.

## Files

```
backend/app/services/
  query_analyzer.py             ← new
  structured_retriever.py       ← new (replaces schedule_router.py)
  reranker.py                   ← new
  retrieval_orchestrator.py     ← new
  vector_store.py               ← existing, unchanged
  llm_extractor.py              ← existing, unchanged
backend/app/api/v1/
  chat.py                       ← rewired around orchestrator + self-correction
  chat_history.py               ← rewired around orchestrator (SSE)
```

## What's NOT in this iteration (future improvements)

These are well-understood next steps; they're deferred to keep the
diff manageable.

1. **Anthropic Contextual Retrieval** — prepend each chunk with a
   one-sentence document summary before embedding. Reported +35%
   retrieval accuracy. Requires a one-time backfill.
2. **Cohere Rerank v3 / BGE-Reranker-v2-m3** as a drop-in replacement
   for the LLM reranker. Lower latency, slightly better quality, but
   adds an external dependency.
3. **HyDE query expansion** — let the LLM hallucinate a plausible
   answer, embed *that*, retrieve with it. Useful for very short
   queries ("матлогіка?") where the question alone gives the embedder
   too little signal.
4. **Per-query evaluation harness** — log (query, retrieved chunks,
   final answer) triples and score offline. We can ship without it,
   but it should land before any prompt-engineering iteration.
