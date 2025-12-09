from typing import List, Dict
from openai import AsyncOpenAI
from app.config import get_settings

settings = get_settings()


class DeepseekLLM:
    """Deepseek LLM integration using OpenAI-compatible API"""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_api_base
        )
        self.model = settings.deepseek_model

    async def generate_answer(
        self,
        question: str,
        context: List[Dict[str, str]],
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> str:
        """
        Generate answer using Deepseek with RAG context

        Args:
            question: User's question
            context: List of relevant document chunks with metadata
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature

        Returns:
            Generated answer
        """

        # Build context string from chunks
        context_text = "\n\n".join([
            f"[Джерело {i+1} - {chunk['source']}]:\n{chunk['text']}"
            for i, chunk in enumerate(context)
        ])

        # Create system prompt
        system_prompt = """Ти - інтелектуальний асистент університету, який допомагає студентам та викладачам знаходити інформацію.

Твоя задача:
- Відповідати на питання на основі наданого контексту з документів університету
- Бути точним та конкретним
- Якщо в контексті немає відповіді, чесно сказати про це
- Відповідати українською мовою
- Посилатися на джерела інформації у відповіді

Формат відповіді:
1. Коротка та зрозуміла відповідь на питання
2. При потребі - додаткова деталізація
3. Вказівка на джерела (наприклад: "згідно з розкладом" або "як вказано в методичці")"""

        # Create user prompt
        user_prompt = f"""Контекст з документів університету:

{context_text}

---

Питання студента: {question}

Дай відповідь на основі наданого контексту. Якщо інформації недостатньо, скажи про це."""

        try:
            # Call Deepseek API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                max_tokens=max_tokens,
                temperature=temperature
            )

            answer = response.choices[0].message.content

            return answer

        except Exception as e:
            raise Exception(f"Error calling Deepseek API: {str(e)}")

    async def generate_simple_answer(
        self,
        question: str,
        max_tokens: int = 500,
        temperature: float = 0.7
    ) -> str:
        """
        Generate answer without RAG context (fallback)

        Args:
            question: User's question
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature

        Returns:
            Generated answer
        """

        system_prompt = """Ти - помічник університету. Відповідай коротко та по суті українською мовою.
Якщо не знаєш відповіді на питання, скажи що потрібно завантажити відповідні документи."""

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

            answer = response.choices[0].message.content

            return answer

        except Exception as e:
            raise Exception(f"Error calling Deepseek API: {str(e)}")


# Global LLM instance
llm = DeepseekLLM()
