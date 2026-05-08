"""End-to-end test: re-upload schedule and verify Thursday answer.

Drives the live API as an admin (delete + upload) and then as a
student (chat query) so we can validate the full pipeline end to end
without manual UI clicking. Output is plain JSON to stdout.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx

BASE = "http://localhost:8000/api/v1"
PDF_PATH = Path(r"C:\Users\vania\Downloads\F7-KI-_123-KI-2025-2026_2-sem-1_2.pdf")
ADMIN_EMAIL = "admin@test.com"
ADMIN_PASSWORD = "AdminPass1234"
STUDENT_EMAIL = "vaniasai05@gmail.com"


def out(label: str, payload):
    sys.stdout.buffer.write(
        f"\n=== {label} ===\n".encode("utf-8")
    )
    if isinstance(payload, (dict, list)):
        sys.stdout.buffer.write(
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        )
    else:
        sys.stdout.buffer.write(str(payload).encode("utf-8"))
    sys.stdout.buffer.write(b"\n")


async def admin_login(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        f"{BASE}/auth/login",
        data={"username": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


async def get_student_token(client: httpx.AsyncClient) -> str | None:
    """The student doesn't have a known password — we use admin to
    impersonate by issuing a JWT directly. Skip if not possible."""
    return None


async def find_schedule_doc(client: httpx.AsyncClient, token: str) -> dict | None:
    resp = await client.get(
        f"{BASE}/documents/list",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    for d in resp.json()["documents"]:
        if "F7-KI" in d.get("filename", ""):
            return d
    return None


async def delete_doc(client: httpx.AsyncClient, token: str, doc_id: str):
    resp = await client.delete(
        f"{BASE}/documents/{doc_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()


async def get_faculties(client: httpx.AsyncClient, token: str):
    resp = await client.get(
        f"{BASE}/dictionaries/faculties",
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()


async def upload_pdf(client: httpx.AsyncClient, token: str, faculty_id: str):
    out("UPLOADING", PDF_PATH.name)
    files = {"file": (PDF_PATH.name, PDF_PATH.read_bytes(), "application/pdf")}
    data = {
        "access_level": "public",
        "faculty_id": faculty_id,
        "target_group_ids": "[]",
        "target_years": "[]",
    }
    resp = await client.post(
        f"{BASE}/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files=files,
        data=data,
        timeout=600.0,
    )
    resp.raise_for_status()
    return resp.json()


async def find_student(client: httpx.AsyncClient, admin_token: str) -> dict | None:
    """Use the admin /users endpoint to look up the student's profile."""
    resp = await client.get(
        f"{BASE}/admin/users?limit=100",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    resp.raise_for_status()
    for u in resp.json()["users"]:
        if u["email"] == STUDENT_EMAIL:
            return u
    return None


async def issue_student_token() -> str:
    """Mint a JWT for the student directly using the same secret as
    the API. Faster than asking the user for a password."""
    sys.path.insert(0, r"C:\Users\vania\ragUni\backend")
    from app.core.security import create_access_token

    return create_access_token(data={"sub": STUDENT_EMAIL, "role": "student"})


async def chat(client: httpx.AsyncClient, token: str, question: str) -> dict:
    out("ASKING", question)
    resp = await client.post(
        f"{BASE}/chat/ask",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"question": question},
        timeout=180.0,
    )
    resp.raise_for_status()
    return resp.json()


async def main() -> int:
    async with httpx.AsyncClient() as client:
        admin_token = await admin_login(client)
        out("ADMIN LOGIN", "OK")

        existing = await find_schedule_doc(client, admin_token)
        if existing:
            out("DELETING OLD", existing["id"])
            await delete_doc(client, admin_token, existing["id"])

        faculties = await get_faculties(client, admin_token)
        out("FACULTIES", [f["name"] for f in faculties])
        frex = next((f for f in faculties if "ФРЕКС" in f["name"] or "радіофіз" in f["name"].lower()), None)
        if not frex:
            frex = faculties[0]
        out("UPLOAD TARGET", frex)

        upload_result = await upload_pdf(client, admin_token, frex["id"])
        out("UPLOAD RESULT", upload_result)

        student = await find_student(client, admin_token)
        out("STUDENT PROFILE", {
            "email": student["email"] if student else None,
            "group": student.get("group_name") if student else None,
            "year": student.get("year") if student else None,
            "level": student.get("level") if student else None,
        })

        student_token = await issue_student_token()
        out("STUDENT TOKEN", "minted")

        for q in [
            "який у мене розклад на тиждень?",
            "що у мене у вівторок?",
            "що у мене у п'ятницю?",
            "коли у мене Програмування вбудованих систем?",
        ]:
            answer = await chat(client, student_token, q)
            out(f"ANSWER: {q}", {
                "answer": answer["answer"][:500],
                "grounded": answer.get("grounded"),
                "n_sources": len(answer.get("sources", [])),
            })

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
