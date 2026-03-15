from openai import AsyncOpenAI, APIError, APIConnectionError, APITimeoutError
from app.config import get_settings

settings = get_settings()


class DeepseekLLM:
    """Deepseek LLM integration using OpenAI-compatible API"""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_api_base,
            timeout=float(settings.llm_timeout_seconds),
        )
        self.model = settings.deepseek_model

    async def generate_answer(
        self,
        question: str,
        context: list[dict[str, str]],
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> str:
        """Generate answer using Deepseek with RAG context."""

        # Build context string from chunks
        context_text = "\n\n".join([
            f"[Source {i+1} - {chunk['source']}]:\n{chunk['text']}"
            for i, chunk in enumerate(context)
        ])

        system_prompt = """You are an intelligent university assistant that helps students and faculty find information.

Your task:
- Answer questions based on the provided context from university documents
- Be precise and specific
- If the context does not contain the answer, say so honestly
- Answer in the same language as the user's question
- Cite information sources in your answer

Response format:
1. A concise and clear answer to the question
2. Additional details if needed
3. Reference to sources (e.g., "according to the schedule" or "as stated in the course guide")"""

        user_prompt = f"""Context from university documents:

{context_text}

---

Student question: {question}

Provide an answer based on the given context. If the information is insufficient, say so."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=max_tokens,
                temperature=temperature
            )

            if not response.choices:
                raise RuntimeError("Deepseek API returned empty response")

            content = response.choices[0].message.content
            if not content:
                raise RuntimeError("Deepseek API returned empty content")

            return content

        except APITimeoutError as e:
            raise RuntimeError("LLM request timed out") from e
        except APIConnectionError as e:
            raise RuntimeError("Could not connect to LLM service") from e
        except APIError as e:
            raise RuntimeError(f"LLM service error (status {e.status_code})") from e

    async def generate_simple_answer(
        self,
        question: str,
        max_tokens: int = 500,
        temperature: float = 0.7
    ) -> str:
        """Generate answer without RAG context (fallback)."""

        system_prompt = """You are a university assistant. Answer briefly and to the point in the same language as the user's question.
If you do not know the answer, say that the relevant documents need to be uploaded."""

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question}
                ],
                max_tokens=max_tokens,
                temperature=temperature
            )

            if not response.choices:
                raise RuntimeError("Deepseek API returned empty response")

            content = response.choices[0].message.content
            if not content:
                raise RuntimeError("Deepseek API returned empty content")

            return content

        except APITimeoutError as e:
            raise RuntimeError("LLM request timed out") from e
        except APIConnectionError as e:
            raise RuntimeError("Could not connect to LLM service") from e
        except APIError as e:
            raise RuntimeError(f"LLM service error (status {e.status_code})") from e


# Global LLM instance
llm = DeepseekLLM()
