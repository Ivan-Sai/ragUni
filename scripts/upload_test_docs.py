"""
Upload all test documents from test_docs/ to the RAG service.
Uses only standard library (no pip install needed).
Run: cd backend && python ../scripts/upload_test_docs.py
"""
import http.client
import json
import mimetypes
import os
import sys
import uuid
from pathlib import Path

API_HOST = "localhost"
API_PORT = 8000
API_PREFIX = "/api/v1"

TEST_DOCS_DIR = Path(__file__).parent.parent / "test_docs"

MIME_MAP = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain",
}


def make_request(method: str, path: str, headers: dict = None,
                 body: bytes = None) -> tuple[int, dict]:
    """Make HTTP request and return (status, json_body)."""
    conn = http.client.HTTPConnection(API_HOST, API_PORT, timeout=120)
    conn.request(method, f"{API_PREFIX}{path}", body=body, headers=headers or {})
    resp = conn.getresponse()
    status = resp.status
    raw = resp.read().decode("utf-8")
    conn.close()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"raw": raw}
    return status, data


def login() -> str:
    """Login and return access token."""
    boundary = uuid.uuid4().hex
    body_parts = []
    for field, value in [("username", "admin@test.com"), ("password", "AdminPass1234")]:
        body_parts.append(f"--{boundary}\r\n")
        body_parts.append(f'Content-Disposition: form-data; name="{field}"\r\n\r\n')
        body_parts.append(f"{value}\r\n")
    body_parts.append(f"--{boundary}--\r\n")
    body = "".join(body_parts).encode("utf-8")

    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    status, data = make_request("POST", "/auth/login", headers=headers, body=body)

    if status != 200:
        print(f"Login failed: {status} {data}")
        sys.exit(1)

    token = data["access_token"]
    print(f"Logged in as admin@test.com\n")
    return token


def upload_file(token: str, filepath: Path) -> dict:
    """Upload a single file using multipart/form-data."""
    boundary = uuid.uuid4().hex
    mime = MIME_MAP.get(filepath.suffix.lower(), "application/octet-stream")

    with open(filepath, "rb") as f:
        file_content = f.read()

    # Build multipart body manually
    parts = []

    # File field
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{filepath.name}"\r\n'.encode()
    )
    parts.append(f"Content-Type: {mime}\r\n\r\n".encode())
    parts.append(file_content)
    parts.append(b"\r\n")

    # access_level field
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(b'Content-Disposition: form-data; name="access_level"\r\n\r\n')
    parts.append(b"public\r\n")

    # End boundary
    parts.append(f"--{boundary}--\r\n".encode())

    body = b"".join(parts)
    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Authorization": f"Bearer {token}",
        "Content-Length": str(len(body)),
    }

    status, data = make_request("POST", "/documents/upload", headers=headers, body=body)

    result = {"name": filepath.name, "status": status, "size": len(file_content)}
    if status == 201:
        result["chunks"] = data.get("total_chunks") or data.get("chunks_count")
        result["id"] = data.get("id") or data.get("document_id")
    else:
        result["detail"] = data.get("detail", str(data))

    return result


def main():
    if not TEST_DOCS_DIR.exists():
        print(f"Test docs directory not found: {TEST_DOCS_DIR}")
        sys.exit(1)

    files = sorted(f for f in TEST_DOCS_DIR.iterdir() if f.is_file())
    print(f"Found {len(files)} files in {TEST_DOCS_DIR}")

    token = login()

    results = []
    for filepath in files:
        print(
            f"  Uploading: {filepath.name} ({filepath.stat().st_size:,} bytes)...",
            end=" ",
            flush=True,
        )
        result = upload_file(token, filepath)
        results.append(result)

        if result["status"] == 201:
            print(f"OK ({result.get('chunks', '?')} chunks)")
        else:
            print(f"FAILED ({result['status']}: {result.get('detail', '?')})")

    success = [r for r in results if r["status"] == 201]
    failed = [r for r in results if r["status"] != 201]

    print(f"\n{'='*60}")
    print(f"Upload complete: {len(success)}/{len(results)} succeeded")

    if failed:
        print(f"\nFailed uploads:")
        for r in failed:
            print(f"  {r['name']}: {r['status']} - {r.get('detail', '?')}")

    total_chunks = sum(r.get("chunks", 0) or 0 for r in success)
    print(f"Total chunks created: {total_chunks}")


if __name__ == "__main__":
    main()
