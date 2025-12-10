"""
Document upload and management API with LangChain integration

Handles document ingestion into the vector store:
- Parse documents (PDF, DOCX, XLSX)
- Chunk text with LangChain text splitter
- Generate embeddings automatically
- Store in MongoDB Atlas Vector Search
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from datetime import datetime
from bson import ObjectId

from app.models.document import DocumentResponse
from app.services.database import get_database
from app.services.document_parser import DocumentParser
from app.services.vector_store import vector_store_service
from app.config import get_settings

router = APIRouter()
settings = get_settings()


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(file: UploadFile = File(...)):
    """
    Upload and process a document with LangChain

    **Process:**
    1. Validate file type and size
    2. Parse document text (PDF/DOCX/XLSX)
    3. Chunk text using RecursiveCharacterTextSplitter (LangChain)
    4. Generate embeddings automatically (FastEmbed)
    5. Store in MongoDB Atlas with vector search support

    **Supported formats:** PDF, DOCX, XLSX
    """

    # Validate file type
    allowed_extensions = ["pdf", "docx", "xlsx"]
    file_extension = file.filename.split(".")[-1].lower()

    if file_extension not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(allowed_extensions)}"
        )

    try:
        # Read file content
        file_content = await file.read()

        # Validate file size
        if len(file_content) > settings.max_upload_size:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size: {settings.max_upload_size / (1024*1024)}MB"
            )

        print(f"\n📄 Processing: {file.filename}")

        # Parse document
        print("📝 Parsing document...")
        text = await DocumentParser.parse_file(file_content, file_extension)

        if not text or len(text.strip()) == 0:
            raise HTTPException(
                status_code=400,
                detail="No text content found in document"
            )

        print(f"✓ Extracted {len(text)} characters")

        # Prepare metadata
        metadata = {
            "source_file": file.filename,
            "file_type": file_extension,
            "uploaded_at": datetime.utcnow().isoformat(),
            "original_size": len(file_content),
            "text_length": len(text)
        }

        # Add to vector store (chunking + embedding автоматически!)
        print(f"🔧 Chunking with LangChain (size={settings.chunk_size}, overlap={settings.chunk_overlap})...")
        chunk_ids = vector_store_service.add_document_with_chunking(text, metadata)

        print(f"✓ Created {len(chunk_ids)} chunks with embeddings")

        # Save document record to MongoDB
        db = get_database()
        document_data = {
            "filename": file.filename,
            "file_type": file_extension,
            "uploaded_at": datetime.utcnow(),
            "total_chunks": len(chunk_ids),
            "chunk_ids": chunk_ids,
            "metadata": metadata
        }

        result = await db.documents.insert_one(document_data)
        document_id = str(result.inserted_id)

        print(f"✅ Document saved with ID: {document_id}")

        return DocumentResponse(
            id=document_id,
            filename=file.filename,
            file_type=file_extension,
            uploaded_at=document_data["uploaded_at"],
            total_chunks=len(chunk_ids),
            message=f"Document processed successfully! Created {len(chunk_ids)} searchable chunks."
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"❌ Error processing document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/list")
async def list_documents():
    """
    Get list of all uploaded documents

    Returns metadata for each document including:
    - Filename
    - File type
    - Upload date
    - Number of chunks
    """

    db = get_database()
    documents = []

    cursor = db.documents.find({}, {
        "filename": 1,
        "file_type": 1,
        "uploaded_at": 1,
        "total_chunks": 1
    }).sort("uploaded_at", -1)  # Most recent first

    async for doc in cursor:
        documents.append({
            "id": str(doc["_id"]),
            "filename": doc.get("filename"),
            "file_type": doc.get("file_type"),
            "uploaded_at": doc.get("uploaded_at"),
            "total_chunks": doc.get("total_chunks", 0)
        })

    return {
        "documents": documents,
        "total": len(documents)
    }


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    """
    Delete a document and its chunks from vector store

    This will:
    1. Delete all chunks from MongoDB Atlas Vector Search
    2. Delete document metadata from database
    """

    db = get_database()

    try:
        # Find document
        doc = await db.documents.find_one({"_id": ObjectId(document_id)})

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        filename = doc.get("filename")

        # Delete chunks from vector store
        print(f"🗑️  Deleting chunks for: {filename}")
        deleted_count = vector_store_service.delete_by_metadata({
            "source_file": filename
        })
        print(f"✓ Deleted {deleted_count} chunks from vector store")

        # Delete document record
        result = await db.documents.delete_one({"_id": ObjectId(document_id)})

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Document not found")

        print(f"✅ Document deleted: {filename}")

        return {
            "message": "Document deleted successfully",
            "filename": filename,
            "chunks_deleted": deleted_count
        }

    except Exception as e:
        print(f"❌ Error deleting document: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stats")
async def get_statistics():
    """
    Get statistics about documents and vector store
    """

    db = get_database()

    # Document count
    doc_count = await db.documents.count_documents({})

    # Get vector store stats
    vector_store_service.initialize()
    vector_stats = vector_store_service.get_stats()

    # File type breakdown
    pipeline = [
        {"$group": {
            "_id": "$file_type",
            "count": {"$sum": 1}
        }}
    ]
    file_types = {}
    async for item in db.documents.aggregate(pipeline):
        file_types[item["_id"]] = item["count"]

    return {
        "documents": {
            "total": doc_count,
            "by_type": file_types
        },
        "vector_store": vector_stats
    }
