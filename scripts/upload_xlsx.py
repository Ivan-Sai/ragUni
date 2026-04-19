"""Upload the 3 XLSX files that failed due to MIME validation."""

import http.client
import json
import uuid
import os

API_HOST = "127.0.0.1"
API_PORT = 8000

# Login
boundary = uuid.uuid4().hex
body = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="username"\r\n\r\n'
    f"admin@test.com\r\n"
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="password"\r\n\r\n'
    f"AdminPass1234\r\n"
    f"--{boundary}--\r\n"
)
conn = http.client.HTTPConnection(API_HOST, API_PORT, timeout=30)
conn.request("POST", "/api/v1/auth/login", body.encode(), {
    "Content-Type": f"multipart/form-data; boundary={boundary}"
})
token = json.loads(conn.getresponse().read())["access_token"]
conn.close()
print("Logged in")

xlsx_files = [
    "course_schedule_2025_2026.xlsx",
    "research_funding_2025.xlsx",
    "student_performance_report.xlsx",
]

for fname in xlsx_files:
    path = os.path.join("..", "test_docs", fname)
    with open(path, "rb") as f:
        content = f.read()
    boundary = uuid.uuid4().hex
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    file_part = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{fname}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + content + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="access_level"\r\n\r\n'
        f"public\r\n"
        f"--{boundary}--\r\n"
    ).encode()
    conn = http.client.HTTPConnection(API_HOST, API_PORT, timeout=60)
    conn.request("POST", "/api/v1/documents/upload", file_part, {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Authorization": f"Bearer {token}",
    })
    resp = conn.getresponse()
    data = json.loads(resp.read())
    conn.close()
    if resp.status == 200:
        print(f"  {fname}: OK ({data.get('total_chunks', '?')} chunks)")
    else:
        print(f"  {fname}: FAILED ({resp.status}: {data})")
