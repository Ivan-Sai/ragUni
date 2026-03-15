# MongoDB Atlas Vector Search Setup

## CRITICAL PREREQUISITE

A Vector Search Index in MongoDB Atlas is **required** for the LangChain integration to function.

Without this index, vector search will not work!

---

## Step 1: Sign in to MongoDB Atlas

1. Open https://cloud.mongodb.com/
2. Navigate to your project
3. Select your cluster (Cluster0, or whatever you named it)

---

## Step 2: Create a Search Index

### Option A: Via the UI (Recommended)

1. In the left-hand menu, select **"Atlas Search"**
2. Click **"Create Search Index"**
3. Select **"JSON Editor"**
4. Click **"Next"**

### Configure the Index:

**Database:** `university_knowledge`
**Collection:** `document_chunks`
**Index Name:** `vector_index`

**JSON Definition:**

```json
{
  "fields": [
    {
      "type": "vector",
      "path": "embedding",
      "numDimensions": 1024,
      "similarity": "cosine"
    },
    {
      "type": "filter",
      "path": "source_file"
    },
    {
      "type": "filter",
      "path": "file_type"
    },
    {
      "type": "filter",
      "path": "uploaded_at"
    }
  ]
}
```

5. Click **"Next"**
6. Click **"Create Search Index"**

---

### Option B: Via MongoDB Shell (Advanced)

```javascript
db.document_chunks.createSearchIndex(
  "vector_index",
  "vectorSearch",
  {
    fields: [
      {
        type: "vector",
        path: "embedding",
        numDimensions: 1024,
        similarity: "cosine"
      },
      {
        type: "filter",
        path: "source_file"
      },
      {
        type: "filter",
        path: "file_type"
      }
    ]
  }
);
```

---

## Step 3: Verification

After creating the index:

1. Wait 1-2 minutes (the index is built asynchronously)
2. The status should change to **"Active"**
3. Restart your application

```bash
cd backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Testing

### 1. Upload a test document:

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@test.pdf"
```

### 2. Ask a question:

```bash
curl -X POST http://localhost:8000/api/v1/chat/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is in the document?"}'
```

### 3. Check the health endpoint:

```bash
curl http://localhost:8000/api/v1/chat/health
```

Expected response:
```json
{
  "status": "healthy",
  "components": {
    "vector_store": "initialized",
    ...
  }
}
```

---

## Key Parameters

### numDimensions: 1024
- This is the vector dimensionality of **intfloat/multilingual-e5-large**
- **DO NOT change** this parameter!
- Must match `VECTOR_DIMENSION` in `backend/.env`

### similarity: "cosine"
- Cosine similarity is the standard for text search
- Alternatives: `"euclidean"`, `"dotProduct"`

### Filter Fields
- `source_file` — filter by specific file
- `file_type` — filter by type (pdf, docx, xlsx)
- `uploaded_at` — time-based filter

---

## Troubleshooting

### Error: "index not found"

**Problem:** The Vector Search Index has not been created or is not active

**Solution:**
1. Verify that the index exists in the Atlas UI
2. Check the index status (it should be "Active")
3. Confirm the index name is `vector_index`
4. Confirm the collection is `document_chunks`

### Error: "dimension mismatch"

**Problem:** Vector dimensionality does not match

**Solution:**
1. Verify `numDimensions` in the index is set to 1024
2. Verify `VECTOR_DIMENSION` in `backend/.env` is set to 1024
3. Recreate the index with the correct parameters

### Slow Search

**Problem:** Vector search is performing slowly

**Solution:**
1. Make sure the index is active and fully built
2. Check the cluster tier (M0 free tier is slower)
3. Consider upgrading to M10+ for production workloads

---

## Additional Resources

- [MongoDB Atlas Vector Search Documentation](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-overview/)
- [LangChain MongoDB Integration](https://python.langchain.com/docs/integrations/vectorstores/mongodb_atlas)
- [FastEmbed Documentation](https://qdrant.github.io/fastembed/)

---

## Production Optimization

### Recommendations:

1. **Upgrade the cluster tier** (M10+) for better performance
2. **Add more filter fields** for flexible search:
   ```json
   {
     "type": "filter",
     "path": "chunk_index"
   }
   ```
3. **Monitoring:** Enable Performance Advisor in Atlas
4. **Backup:** Configure automatic backups

### Advanced: Multiple Indexes

Create multiple indexes for different use cases:
- `vector_index` — primary search
- `semantic_index` — semantic search with different parameters
- `filtered_index` — with additional filters

---

## Checklist

- [ ] Vector Search Index created
- [ ] Index name = `vector_index`
- [ ] Collection = `document_chunks`
- [ ] numDimensions = 1024
- [ ] similarity = "cosine"
- [ ] Index status = Active
- [ ] Application restarted
- [ ] Test document uploaded
- [ ] Vector search is working

**Once all items are complete, your RAG system is ready to go.**
