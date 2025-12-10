from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config import get_settings

settings = get_settings()


class Database:
    """MongoDB database connection manager"""

    client: AsyncIOMotorClient = None
    db: AsyncIOMotorDatabase = None


db = Database()


async def connect_to_mongo():
    """Connect to MongoDB"""
    try:
        # Simple connection like in NestJS - let Motor/PyMongo handle SSL automatically
        db.client = AsyncIOMotorClient(settings.mongodb_url)
        db.db = db.client[settings.mongodb_db_name]

        # Test connection
        await db.client.admin.command('ping')
        print("✓ Connected to MongoDB Atlas")

        # Create indexes in background (non-blocking)
        await create_database_indexes()

        # Automatically create Vector Search index if Atlas API configured
        await ensure_vector_search_index()

    except Exception as e:
        print(f"Warning: Could not connect to MongoDB: {e}")
        print("Service will start but database operations will fail")


async def create_database_indexes():
    """Create standard database indexes for optimal performance"""
    try:
        # Index for filename lookup
        await db.db.documents.create_index([("filename", 1)])

        # Index for upload date (for sorting)
        await db.db.documents.create_index([("uploaded_at", -1)])

        # Composite index for file type and date
        await db.db.documents.create_index([
            ("file_type", 1),
            ("uploaded_at", -1)
        ])

        print("✓ Database indexes created")

    except Exception as e:
        print(f"⚠️  Could not create indexes: {e}")


async def ensure_vector_search_index():
    """
    Automatically create MongoDB Atlas Vector Search index

    This requires Atlas API credentials to be configured in .env:
    - ATLAS_PUBLIC_KEY
    - ATLAS_PRIVATE_KEY
    - ATLAS_PROJECT_ID
    - ATLAS_CLUSTER_NAME

    If credentials are not set, the function will skip index creation
    and you'll need to create it manually.
    """
    try:
        # First, ensure the collection exists (Atlas API requires collection to exist)
        collection_names = await db.db.list_collection_names()
        if "document_chunks" not in collection_names:
            print("📦 Creating collection 'document_chunks'...")
            await db.db.create_collection("document_chunks")
            print("✓ Collection 'document_chunks' created")

        from app.services.atlas_client import get_atlas_manager

        atlas_manager = get_atlas_manager()

        if not atlas_manager:
            print("⚠️  Atlas API not configured. Skipping automatic vector index creation.")
            print("   To enable automatic index creation, set Atlas API credentials in .env")
            print("   Or create the vector search index manually (see VECTOR_SEARCH_SETUP.md)")
            return

        # Ensure vector index exists
        # wait_for_ready=False means it will create index but not wait for it to build
        # (index builds in background, takes 1-2 minutes)
        success = atlas_manager.ensure_vector_index(
            database=settings.mongodb_db_name,
            collection="document_chunks",
            index_name=settings.vector_index_name,
            vector_dimension=settings.vector_dimension,
            wait_for_ready=False  # Don't block startup
        )

        if success:
            print("✓ Vector Search index ready")
        else:
            print("⚠️  Could not ensure vector search index")
            print("   Please create it manually (see VECTOR_SEARCH_SETUP.md)")

    except ImportError:
        print("⚠️  Atlas client not available")
    except Exception as e:
        print(f"⚠️  Error ensuring vector search index: {e}")


async def close_mongo_connection():
    """Close MongoDB connection"""
    if db.client:
        db.client.close()
        print("✓ Closed MongoDB connection")


def get_database() -> AsyncIOMotorDatabase:
    """Get database instance"""
    return db.db
