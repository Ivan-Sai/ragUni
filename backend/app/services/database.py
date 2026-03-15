import logging

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import ConnectionFailure, OperationFailure, ConfigurationError
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class Database:
    """MongoDB database connection manager"""

    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None


db = Database()


async def connect_to_mongo():
    """Connect to MongoDB"""
    try:
        db.client = AsyncIOMotorClient(
            settings.mongodb_url,
            maxPoolSize=settings.mongodb_max_pool_size,
            minPoolSize=settings.mongodb_min_pool_size,
            maxIdleTimeMS=30000,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=20000,
        )
        db.db = db.client[settings.mongodb_db_name]

        # Test connection
        await db.client.admin.command('ping')
        logger.info("Connected to MongoDB Atlas")

        await create_database_indexes()
        await ensure_vector_search_index()

    except (ConnectionFailure, ConfigurationError) as e:
        logger.warning("Could not connect to MongoDB: %s", e)
        logger.warning("Service will start but database operations will fail")
    except OperationFailure as e:
        logger.warning("MongoDB operation failed during startup: %s", e)


async def create_database_indexes():
    """Create standard database indexes for optimal performance"""
    try:
        await db.db.documents.create_index([("filename", 1)])
        await db.db.documents.create_index([("uploaded_at", -1)])
        await db.db.documents.create_index([("file_type", 1), ("uploaded_at", -1)])
        await db.db.documents.create_index([("access_level", 1)])

        # Chat history indexes
        await db.db.chat_history.create_index([("user_id", 1), ("updated_at", -1)])
        await db.db.chat_history.create_index([("session_id", 1), ("user_id", 1)], unique=True)

        # User indexes
        await db.db.users.create_index([("email", 1)], unique=True)

        logger.info("Database indexes created")

    except OperationFailure as e:
        logger.warning("Could not create indexes: %s", e)


async def ensure_vector_search_index():
    """Automatically create MongoDB Atlas Vector Search index if Atlas API is configured."""
    try:
        collection_names = await db.db.list_collection_names()
        if "document_chunks" not in collection_names:
            logger.info("Creating collection 'document_chunks'...")
            await db.db.create_collection("document_chunks")
            logger.info("Collection 'document_chunks' created")

        from app.services.atlas_client import get_atlas_manager

        atlas_manager = get_atlas_manager()

        if not atlas_manager:
            logger.info("Atlas API not configured — skipping automatic vector index creation")
            return

        # Vector search index
        vector_ok = atlas_manager.ensure_vector_index(
            database=settings.mongodb_db_name,
            collection="document_chunks",
            index_name=settings.vector_index_name,
            vector_dimension=settings.vector_dimension,
            wait_for_ready=False,
        )
        if vector_ok:
            logger.info("Vector Search index ready")

        # Full-text search index (required for hybrid search)
        fulltext_ok = atlas_manager.ensure_fulltext_index(
            database=settings.mongodb_db_name,
            collection="document_chunks",
            index_name=settings.fulltext_index_name,
            wait_for_ready=False,
        )
        if fulltext_ok:
            logger.info("Full-text Search index ready")

    except ImportError:
        logger.debug("Atlas client not available")
    except OperationFailure as e:
        logger.warning("Error ensuring vector search index: %s", e)
    except ConnectionFailure as e:
        logger.warning("Connection error while ensuring vector search index: %s", e)


async def close_mongo_connection():
    """Close MongoDB connection"""
    if db.client:
        db.client.close()
        logger.info("Closed MongoDB connection")


def get_database() -> AsyncIOMotorDatabase:
    """Get database instance. Raises RuntimeError if not connected."""
    if db.db is None:
        raise RuntimeError(
            "Database is not initialized. Ensure connect_to_mongo() was called during startup."
        )
    return db.db
