from fastapi import APIRouter, UploadFile, File, HTTPException
from datetime import datetime
from bson import ObjectId

from app.models.document import DocumentResponse, DocumentChunk
from app.services.database import get_database
from app.services.document_parser import DocumentParser
from app.services.vectorizer import vectorizer
from app.utils.chunking import chunk_text
from app.config import get_settings

router = APIRouter()
settings = get_settings()


@router.post("/upload", response_model=DocumentResponse)
async def upload_document(file: UploadFile = File(...)):
    """
    Upload and process a document (PDF, DOCX, XLSX)

    This endpoint:
    1. Validates file type and size
    2. Parses the document and extracts text
    3. Chunks the text into smaller pieces
    4. Creates embeddings for each chunk
    5. Stores everything in MongoDB
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

        # Parse document
        print(f"Parsing {file.filename}...")
        text = await DocumentParser.parse_file(file_content, file_extension)

        if not text or len(text.strip()) == 0:
            raise HTTPException(
                status_code=400,
                detail="No text content found in document"
            )

        # Chunk text
        print("Chunking text...")
        chunks = chunk_text(text)

        if not chunks:
            raise HTTPException(
                status_code=400,
                detail="Failed to chunk document"
            )

        # Create embeddings
        print(f"Creating embeddings for {len(chunks)} chunks...")
        embeddings = await vectorizer.embed_texts(chunks)

        # Create document chunks
        document_chunks = []
        for idx, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            doc_chunk = DocumentChunk(
                text=chunk,
                chunk_index=idx,
                embedding=embedding,
                metadata={
                    "length": len(chunk),
                    "source_file": file.filename
                }
            )
            document_chunks.append(doc_chunk.dict())

        # Save to MongoDB
        db = get_database()
        document_data = {
            "filename": file.filename,
            "file_type": file_extension,
            "uploaded_at": datetime.utcnow(),
            "chunks": document_chunks,
            "total_chunks": len(document_chunks),
            "metadata": {
                "original_size": len(file_content),
                "text_length": len(text)
            }
        }

        result = await db.documents.insert_one(document_data)
        document_id = str(result.inserted_id)

        print(f"✓ Document saved with ID: {document_id}")

        return DocumentResponse(
            id=document_id,
            filename=file.filename,
            file_type=file_extension,
            uploaded_at=document_data["uploaded_at"],
            total_chunks=len(document_chunks),
            message=f"Document processed successfully. Created {len(document_chunks)} chunks."
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Error processing document: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/list")
async def list_documents():
    """Get list of all uploaded documents"""

    db = get_database()
    documents = []

    cursor = db.documents.find({}, {
        "filename": 1,
        "file_type": 1,
        "uploaded_at": 1,
        "total_chunks": 1
    })

    async for doc in cursor:
        documents.append({
            "id": str(doc["_id"]),
            "filename": doc.get("filename"),
            "file_type": doc.get("file_type"),
            "uploaded_at": doc.get("uploaded_at"),
            "total_chunks": doc.get("total_chunks", 0)
        })

    return {"documents": documents, "total": len(documents)}


@router.delete("/{document_id}")
async def delete_document(document_id: str):
    """Delete a document by ID"""

    db = get_database()

    try:
        result = await db.documents.delete_one({"_id": ObjectId(document_id)})

        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Document not found")

        return {"message": "Document deleted successfully"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
