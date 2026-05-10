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
    """Connect to MongoDB and ensure required indexes exist.

    Behaviour by environment:

    * In **production** (``settings.environment == "production"``) any
      connect / index-create failure is fatal — the lifespan hook
      re-raises and uvicorn exits with non-zero. Starting an API that
      cannot reach its database means every request returns 500 and
      the orchestrator never knows the deploy failed.
    * In **development** the connect failure is downgraded to a warning
      so a developer can boot the service against a missing local
      Mongo and still iterate on imports / type checks.
    """
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

    except (ConnectionFailure, ConfigurationError, OperationFailure) as e:
        if settings.environment == "production":
            logger.error("MongoDB unreachable during startup: %s", e)
            # Fail-fast in production — the orchestrator should restart
            # us / fail the deploy rather than serve 500s.
            raise
        logger.warning("Could not connect to MongoDB: %s", e)
        logger.warning("Service will start but database operations will fail")


async def create_database_indexes():
    """Create standard database indexes for optimal performance"""
    try:
        await db.db.documents.create_index([("filename", 1)])
        await db.db.documents.create_index([("uploaded_at", -1)])
        await db.db.documents.create_index([("file_type", 1), ("uploaded_at", -1)])
        await db.db.documents.create_index([("access_level", 1)])
        # Audience targeting indexes — used by the document list filter
        # so admins/teachers can quickly review documents per group.
        await db.db.documents.create_index([("target_group_ids", 1)])
        await db.db.documents.create_index([("target_years", 1)])
        await db.db.documents.create_index([("target_level", 1)])

        # Chat history indexes
        await db.db.chat_history.create_index([("user_id", 1), ("updated_at", -1)])
        await db.db.chat_history.create_index([("session_id", 1), ("user_id", 1)], unique=True)

        # User indexes
        await db.db.users.create_index([("email", 1)], unique=True)
        # Used by dictionary delete-guard to detect users still pointing
        # at a faculty/group the admin tries to remove.
        await db.db.users.create_index([("faculty_id", 1)])
        await db.db.users.create_index([("group_id", 1)])

        # Faculty/Group reference dictionaries.
        # Case-insensitive uniqueness via the *_lower mirror field — the
        # service writes the value once and queries against the indexed
        # mirror, sidestepping MongoDB's lack of true case-insensitive
        # unique indexes outside collation indexes (which would still
        # require us to specify collation on every query).
        await db.db.faculties.create_index([("name_lower", 1)], unique=True)
        await db.db.groups.create_index(
            [("faculty_id", 1), ("name_lower", 1)], unique=True
        )
        await db.db.groups.create_index([("level", 1)])

        # Analytics indexes
        await db.db.analytics_events.create_index([("timestamp", -1)])
        await db.db.analytics_events.create_index([("event_type", 1), ("timestamp", -1)])

        # Feedback indexes
        await db.db.feedback.create_index(
            [("user_id", 1), ("session_id", 1), ("message_index", 1)],
            unique=True,
        )
        await db.db.feedback.create_index([("created_at", -1)])

        # Audit log — primary access patterns are "newest first" and
        # "filtered by actor / resource". TTL keeps the collection
        # bounded so a long-running deployment doesn't blow up storage.
        await db.db.audit_logs.create_index([("timestamp", -1)])
        await db.db.audit_logs.create_index(
            [("resource_type", 1), ("resource_id", 1), ("timestamp", -1)]
        )
        await db.db.audit_logs.create_index([("actor_id", 1), ("timestamp", -1)])
        # 365-day retention. If you need longer for compliance, raise
        # this and document the new policy.
        await db.db.audit_logs.create_index(
            [("timestamp", 1)], expireAfterSeconds=365 * 24 * 3600
        )

        # Document chunks — joined back to the document via document_id
        # for delete operations and against source_file for legacy
        # lookups. Both should be indexed.
        await db.db.document_chunks.create_index([("document_id", 1)])
        await db.db.document_chunks.create_index([("source_file", 1)])

        # Documents — uploader lookup for the per-user "your uploads"
        # listing, plus uploader-scoped delete-permission check.
        await db.db.documents.create_index([("uploaded_by_id", 1)])

        # Refresh-token allowlist — checked on every /auth/refresh by
        # ``jti``, periodically swept by TTL so revoked / expired
        # entries don't accumulate forever.
        await db.db.refresh_tokens.create_index([("jti", 1)], unique=True)
        await db.db.refresh_tokens.create_index([("user_id", 1)])
        await db.db.refresh_tokens.create_index(
            [("expires_at", 1)], expireAfterSeconds=0
        )

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
