# Quick Start

## 1. MongoDB Atlas Setup

1. Sign up at https://www.mongodb.com/cloud/atlas
2. Create a free cluster (M0 Sandbox)
3. Create a database user
4. Add your IP to the whitelist (or `0.0.0.0/0` for development)
5. Copy the connection string

## 2. Deepseek API Key Setup

1. Sign up at https://platform.deepseek.com/
2. Navigate to the API Keys section
3. Create a new API key
4. Copy the key (it will only be shown once!)

## 3. Project Configuration

```bash
# 1. Create a virtual environment
python -m venv venv

# 2. Activate it
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# 3. Install dependencies
cd backend
pip install -r requirements.txt

# 4. Configure backend/.env
cp .env.example .env
# Open backend/.env and fill in:
# - MONGODB_URL (from step 1)
# - DEEPSEEK_API_KEY (from step 2)
# - SECRET_KEY (generate a random string of at least 32 characters)
```

## 4. Running the Server

```bash
# From the backend/ directory

# Option 1: Via Python
python run.py

# Option 2: Via uvicorn directly
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000/docs for the interactive API documentation.

## 5. Testing

### Via Swagger UI (recommended)

1. Open http://localhost:8000/docs
2. Find `POST /api/v1/documents/upload`
3. Click "Try it out"
4. Upload a PDF/DOCX/XLSX file
5. Then try `POST /api/v1/chat/ask`

### Via Python

```python
import requests

# Upload a document
with open("schedule.pdf", "rb") as f:
    files = {"file": f}
    r = requests.post("http://localhost:8000/api/v1/documents/upload", files=files)
    print(r.json())

# Ask a question
data = {"question": "When is the physics exam?"}
r = requests.post("http://localhost:8000/api/v1/chat/ask", json=data)
print(r.json()["answer"])
```

### Via cURL

```bash
# Upload a document
curl -X POST "http://localhost:8000/api/v1/documents/upload" \
  -F "file=@schedule.pdf"

# Ask a question
curl -X POST "http://localhost:8000/api/v1/chat/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "When is the physics exam?"}'
```

## Troubleshooting

### ModuleNotFoundError
```bash
# Make sure the virtual environment is activated
# Reinstall dependencies
cd backend
pip install -r requirements.txt
```

### MongoDB connection refused
```bash
# Verify:
# 1. The connection string is correct
# 2. Your IP address is in the whitelist
# 3. The password does not contain unescaped special characters
```

### Deepseek API error 401
```bash
# Verify that the API key is correct
# Make sure there are sufficient funds on your account balance
```

### FastEmbed takes a long time to load
```bash
# This is expected on the first run
# The model (~500 MB) is downloaded and cached
# Subsequent launches will be fast
```
