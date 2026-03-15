"""Atlas Search Index Manager — automatic creation of vector + full-text indexes.

Uses PyMongo driver (collection.create_search_index) which works on M0/free-tier
clusters without Atlas Admin API keys.
"""

import logging
from typing import Optional

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class AtlasIndexManager:
    """Manages MongoDB Atlas Search indexes (vector + full-text)."""

    def __init__(self, client: MongoClient) -> None:
        self._client = client

    def _get_collection(self, database: str, collection: str):
        return self._client[database][collection]

    def _index_exists(self, collection, index_name: str) -> bool:
        """Check if a search index already exists."""
        try:
            for index in collection.list_search_indexes(index_name):
                return True
        except OperationFailure:
            pass
        return False

    def ensure_vector_index(
        self,
        database: str,
        collection: str,
        index_name: str,
        vector_dimension: int,
        wait_for_ready: bool = False,
    ) -> bool:
        """Create vector search index if it doesn't exist.

        Returns True if index exists or was created successfully.
        """
        coll = self._get_collection(database, collection)

        if self._index_exists(coll, index_name):
            logger.info("Vector search index '%s' already exists", index_name)
            return True

        try:
            from pymongo_search_utils.index import create_vector_search_index

            create_vector_search_index(
                collection=coll,
                index_name=index_name,
                path="embedding",
                dimensions=vector_dimension,
                similarity="cosine",
                filters=["access_level", "faculty", "source_file"],
                wait_until_complete=120.0 if wait_for_ready else None,
            )
            logger.info("Vector search index '%s' created", index_name)
            return True

        except OperationFailure as e:
            if "already exists" in str(e):
                logger.info("Vector search index '%s' already exists", index_name)
                return True
            logger.error("Failed to create vector search index: %s", e)
            return False
        except ImportError:
            logger.warning("pymongo_search_utils not installed, skipping vector index creation")
            return False
        except ConnectionFailure as e:
            logger.error("Connection error creating vector search index: %s", e)
            return False

    def ensure_fulltext_index(
        self,
        database: str,
        collection: str,
        index_name: str,
        wait_for_ready: bool = False,
    ) -> bool:
        """Create full-text search index if it doesn't exist.

        Required for hybrid search (vector + full-text with RRF).
        Returns True if index exists or was created successfully.
        """
        coll = self._get_collection(database, collection)

        if self._index_exists(coll, index_name):
            logger.info("Full-text search index '%s' already exists", index_name)
            return True

        try:
            from pymongo_search_utils.index import create_fulltext_search_index

            create_fulltext_search_index(
                collection=coll,
                index_name=index_name,
                field="text",
                wait_until_complete=120.0 if wait_for_ready else None,
            )
            logger.info("Full-text search index '%s' created", index_name)
            return True

        except OperationFailure as e:
            if "already exists" in str(e):
                logger.info("Full-text search index '%s' already exists", index_name)
                return True
            logger.error("Failed to create full-text search index: %s", e)
            return False
        except ImportError:
            logger.warning("pymongo_search_utils not installed, skipping fulltext index creation")
            return False
        except ConnectionFailure as e:
            logger.error("Connection error creating full-text search index: %s", e)
            return False


def get_atlas_manager() -> Optional[AtlasIndexManager]:
    """Create AtlasIndexManager using sync PyMongo client.

    Returns None if MongoDB URL is not configured.
    """
    if not settings.mongodb_url:
        return None

    try:
        client = MongoClient(settings.mongodb_url)
        return AtlasIndexManager(client)
    except ConnectionFailure as e:
        logger.warning("Could not create Atlas index manager: %s", e)
        return None
