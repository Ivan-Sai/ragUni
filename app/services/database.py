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
        # Note: Indexes will be created on first use if needed
    except Exception as e:
        print(f"Warning: Could not connect to MongoDB: {e}")
        print("Service will start but database operations will fail")


async def close_mongo_connection():
    """Close MongoDB connection"""
    if db.client:
        db.client.close()
        print("✓ Closed MongoDB connection")


def get_database() -> AsyncIOMotorDatabase:
    """Get database instance"""
    return db.db
