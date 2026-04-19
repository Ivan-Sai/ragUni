"""Dataset entry + result models for the RAG evaluation harness."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class EvalEntry(BaseModel):
    """A single evaluation question + ground truth."""

    question: str
    relevant_chunks: list[str] = Field(
        ...,
        description="Chunk IDs that contain the answer. Evaluation passes "
        "only if at least one is retrieved.",
    )
    gold_answer: str = Field(..., description="Concise human-written answer.")
    faculty: Optional[str] = Field(
        default=None,
        description="Faculty scope. Used to verify access filtering.",
    )
    role: str = Field(
        default="student",
        description="Role the question is asked under.",
    )
    tags: list[str] = Field(default_factory=list)


class RetrievalResult(BaseModel):
    """Outcome of a single retrieval-only run."""

    question: str
    retrieved_chunk_ids: list[str]
    relevant_chunk_ids: list[str]
    took_ms: float


class GenerationResult(BaseModel):
    """Outcome of a full RAG run with judged faithfulness."""

    question: str
    gold_answer: str
    generated_answer: str
    citations: list[str] = Field(default_factory=list)
    faithfulness: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="LLM-as-judge score, 0..1. None when not judged.",
    )
    answer_relevance: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    took_ms: float
