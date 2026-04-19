# RAG Evaluation Methodology

This document describes how the quality of the university RAG pipeline is
measured. A diploma committee will typically ask *"how do you know the
system works?"* — this file is the evidence.

## 1. Why evaluation matters

A RAG system has two failure modes that classic software tests cannot
catch:

1. **Retrieval failure** — the right chunks exist in the index but the
   retriever does not return them, so the LLM has no evidence to cite.
2. **Generation failure** — the retriever returns good chunks but the LLM
   ignores them, hallucinates, or cites the wrong source.

We therefore measure retrieval and generation separately, plus an
end-to-end user-centric metric.

## 2. Evaluation dataset

Curated by hand from the target corpus (university regulations, exam
schedules, program catalogs).

| Field             | Description                                              |
| ----------------- | -------------------------------------------------------- |
| `question`        | Question in Ukrainian or English (natural phrasing).     |
| `relevant_chunks` | IDs of chunks that genuinely contain the answer.         |
| `gold_answer`     | Concise human-written answer, citing the source.         |
| `faculty`         | Faculty scope — used to verify access-control filtering. |
| `role`            | `student` / `teacher` / `admin`.                         |

**Target size for defense:** ≥ 50 questions covering each document type
(PDF syllabus, DOCX regulations, XLSX schedules) and each role.

Store under `backend/tests/eval/dataset.jsonl`. Never commit raw student
PII.

## 3. Retrieval metrics

Run retrieval only (no LLM) and compare retrieved chunk IDs against
`relevant_chunks`.

| Metric              | Definition                                                    | Target  |
| ------------------- | ------------------------------------------------------------- | ------- |
| **Recall@5**        | Fraction of queries where at least one relevant chunk is in top-5. | ≥ 0.85  |
| **Precision@5**     | Mean fraction of relevant chunks among the top-5 returned.   | ≥ 0.40  |
| **MRR**             | Mean reciprocal rank of the first relevant chunk.             | ≥ 0.65  |
| **nDCG@10**         | Rank-weighted relevance over top-10.                          | ≥ 0.70  |
| **Access-filter accuracy** | Fraction of queries where no cross-role / cross-faculty chunk leaks. | **1.00** (non-negotiable) |

The access-filter metric is a security metric, not a quality metric — any
leak is a defect, not a degradation.

## 4. Generation metrics

Run the full pipeline and compare the generated answer against
`gold_answer`.

| Metric                | What it captures                                    |
| --------------------- | --------------------------------------------------- |
| **Citation accuracy** | Does the answer cite a source from the retrieved context? |
| **Faithfulness**      | Does every claim in the answer follow from the context? |
| **Answer relevance**  | Does the answer actually address the question?      |
| **Refusal accuracy**  | For out-of-scope questions, does the system refuse? |

Faithfulness and answer-relevance are scored with **LLM-as-judge**
(Deepseek, a separate call with a strict rubric) plus a sample of human
spot-checks. Target: ≥ 0.80 faithfulness, ≥ 0.80 answer-relevance, 1.00
refusal on adversarial questions.

## 5. Latency & throughput

Measured on a cold and warm vector store, local MongoDB Atlas M10.

| Stage                       | Target p50 | Target p95 |
| --------------------------- | ---------- | ---------- |
| Embedding (FastEmbed, CPU)  |   ~40 ms   |   ~90 ms   |
| Vector search (top-5, MMR)  |   ~120 ms  |   ~300 ms  |
| LLM streaming first token   |   ~800 ms  |  ~1800 ms  |
| Full answer (300 tokens)    |   ~3 s     |   ~7 s     |

Record real numbers from `backend/scripts/bench_rag.py` once run on the
defense machine.

## 6. Chunking ablation

Repeat the retrieval metrics over a grid to justify the chosen defaults:

* `chunk_size ∈ {500, 1000, 1500, 2000}`
* `chunk_overlap ∈ {0, 100, 200, 400}`
* `top_k ∈ {3, 5, 10}`

Present as a table; highlight the chosen configuration.

## 7. Embedding-model comparison

Justify the choice of `intfloat/multilingual-e5-large` against at least
two baselines on the same dataset:

* `paraphrase-multilingual-MiniLM-L12-v2` (faster, smaller).
* `text-embedding-3-small` via OpenAI (cloud, paid).

Report Recall@5 and MRR on both; argue the trade-off (quality vs cost vs
latency vs data-locality).

## 8. How to run

Once implemented, evaluation is reproducible:

```bash
cd backend
python -m tests.eval.run_retrieval        # metrics section 3
python -m tests.eval.run_generation       # metrics section 4
python -m tests.eval.run_latency          # metrics section 5
```

Results land in `backend/tests/eval/reports/YYYY-MM-DD.md`. Include the
latest report in the thesis appendix.

## 9. Deliverables for defense

1. Filled table of metrics (sections 3–5) on ≥ 50 questions.
2. Chunking ablation table (section 6).
3. Embedding comparison table (section 7).
4. 3 failure-case studies with root cause and proposed fix.
