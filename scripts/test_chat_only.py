"""Test chat queries against the existing schedule (no re-upload)."""

from __future__ import annotations

import asyncio
import json
import sys

import httpx

sys.path.insert(0, r"C:\Users\vania\ragUni\backend")
from app.core.security import create_access_token  # noqa: E402

BASE = "http://localhost:8001/api/v1"
STUDENT_EMAIL = "vaniasai05@gmail.com"


async def main() -> int:
    token = create_access_token(data={"sub": STUDENT_EMAIL, "role": "student"})

    async with httpx.AsyncClient(timeout=180.0) as client:
        for q in [
            "який у мене розклад в четвер?",
            "що у мене в понеділок?",
            "коли у мене Системне програмне забезпечення?",
            "хто веде Розробку інтерфейсів користувача?",
        ]:
            sys.stdout.buffer.write(f"\n=== Q: {q} ===\n".encode("utf-8"))
            resp = await client.post(
                f"{BASE}/chat/ask",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={"question": q},
            )
            data = resp.json()
            sys.stdout.buffer.write(
                json.dumps(
                    {
                        "answer": data["answer"][:400],
                        "grounded": data.get("grounded"),
                        "n_sources": len(data.get("sources", [])),
                        "first_source": (
                            data["sources"][0]["text"][:150]
                            if data.get("sources")
                            else None
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                ).encode("utf-8")
            )
            sys.stdout.buffer.write(b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
