"""Input sanitization for user-provided questions sent to the LLM.

Light-weight defence against the most common prompt-injection patterns:

* Chat-template control markers such as ``<|im_start|>`` / ``<|endoftext|>``
  — if leaked into user input they can confuse the model about role
  boundaries.
* Obvious jailbreak prefaces such as "ignore previous instructions".

This is NOT a complete solution — adversarial inputs can always be crafted —
but it raises the bar meaningfully and produces a helpful error message for
ordinary misuse. For stronger guarantees the pipeline also relies on:

* A constrained system prompt that refuses to reveal itself.
* Retrieval grounding: the LLM answers only from retrieved context.
* Length limits enforced by :data:`MAX_QUESTION_LENGTH`.
"""

from __future__ import annotations

import re

MAX_QUESTION_LENGTH = 2000

# Chat-template / tokenizer control tokens. Presence in user input is almost
# always malicious or a copy-paste accident; strip them rather than fail so
# legitimate users are not blocked by pasted transcripts.
_CONTROL_TOKEN_PATTERN = re.compile(
    r"<\|(?:im_start|im_end|endoftext|system|user|assistant|fim_[a-z_]+|start|end)\|>",
    re.IGNORECASE,
)

# Jailbreak phrases that reliably appear only in prompt-injection attempts.
# Keep the list small and high-precision to avoid false positives on real
# academic questions (students may legitimately ask about "system design",
# "roles", etc.).
_JAILBREAK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions", re.I),
    re.compile(r"disregard\s+(?:all\s+)?(?:previous|prior|above)\s+instructions", re.I),
    re.compile(r"forget\s+(?:all\s+)?(?:previous|prior|above)\s+instructions", re.I),
    re.compile(r"you\s+are\s+now\s+(?:a\s+)?(?:new|different)\s+(?:ai|assistant|system)", re.I),
    re.compile(r"reveal\s+(?:the\s+)?system\s+prompt", re.I),
    re.compile(r"print\s+(?:the\s+)?system\s+prompt", re.I),
    re.compile(r"repeat\s+(?:the\s+)?(?:above|system)\s+(?:text|prompt|message)", re.I),
)


class UnsafeQuestionError(ValueError):
    """Raised when a user question matches a known prompt-injection pattern."""


def sanitize_question(raw: str) -> str:
    """Return a cleaned question ready for the RAG chain.

    Raises:
        UnsafeQuestionError: on empty input, oversized input, or detected
            jailbreak patterns. Callers should translate this into an HTTP
            400 with a generic user-facing message.
    """
    if raw is None:
        raise UnsafeQuestionError("Question cannot be empty")

    # Strip zero-width characters that are sometimes used to smuggle tokens
    # past simple pattern checks.
    cleaned = re.sub(r"[\u200B-\u200D\uFEFF]", "", raw).strip()

    if not cleaned:
        raise UnsafeQuestionError("Question cannot be empty")

    if len(cleaned) > MAX_QUESTION_LENGTH:
        raise UnsafeQuestionError(
            f"Question exceeds the maximum length of {MAX_QUESTION_LENGTH} characters"
        )

    # Strip control tokens silently — they are never legitimate user input.
    cleaned = _CONTROL_TOKEN_PATTERN.sub(" ", cleaned).strip()
    if not cleaned:
        raise UnsafeQuestionError("Question cannot be empty")

    for pattern in _JAILBREAK_PATTERNS:
        if pattern.search(cleaned):
            raise UnsafeQuestionError(
                "Question contains content that is not allowed"
            )

    return cleaned
