"""Tests for Atlas Search Index Manager."""

import pytest
from unittest.mock import patch, MagicMock
from pymongo.errors import OperationFailure

from app.services.atlas_client import AtlasIndexManager, get_atlas_manager


class TestAtlasIndexManager:
    """Test AtlasIndexManager index creation logic."""

    def setup_method(self):
        self.mock_client = MagicMock()
        self.manager = AtlasIndexManager(self.mock_client)
        self.mock_coll = MagicMock()
        self.mock_client.__getitem__.return_value.__getitem__.return_value = self.mock_coll

    def test_vector_index_skips_if_exists(self):
        """Should not create index if it already exists."""
        self.mock_coll.list_search_indexes.return_value = iter([{"name": "vector_index", "status": "READY"}])

        result = self.manager.ensure_vector_index("db", "coll", "vector_index", 1024)

        assert result is True
        self.mock_coll.create_search_index.assert_not_called()

    def test_vector_index_creates_when_missing(self):
        """Should create vector index when it doesn't exist."""
        self.mock_coll.list_search_indexes.return_value = iter([])

        with patch("pymongo_search_utils.index.create_vector_search_index"):
            result = self.manager.ensure_vector_index("db", "coll", "vector_index", 1024)

        assert result is True

    def test_vector_index_handles_already_exists_error(self):
        """Should return True if OperationFailure says 'already exists'."""
        self.mock_coll.list_search_indexes.return_value = iter([])

        with patch(
            "pymongo_search_utils.index.create_vector_search_index",
            side_effect=OperationFailure("Index already exists"),
        ):
            result = self.manager.ensure_vector_index("db", "coll", "vector_index", 1024)

        assert result is True

    def test_vector_index_handles_creation_error(self):
        """Should return False on unexpected errors."""
        from pymongo.errors import ConnectionFailure
        self.mock_coll.list_search_indexes.return_value = iter([])

        with patch(
            "pymongo_search_utils.index.create_vector_search_index",
            side_effect=ConnectionFailure("Connection refused"),
        ):
            result = self.manager.ensure_vector_index("db", "coll", "vector_index", 1024)

        assert result is False

    def test_fulltext_index_skips_if_exists(self):
        """Should not create full-text index if it already exists."""
        self.mock_coll.list_search_indexes.return_value = iter([{"name": "text_index", "status": "READY"}])

        result = self.manager.ensure_fulltext_index("db", "coll", "text_index")

        assert result is True
        self.mock_coll.create_search_index.assert_not_called()

    def test_fulltext_index_creates_when_missing(self):
        """Should create full-text index when it doesn't exist."""
        self.mock_coll.list_search_indexes.return_value = iter([])

        with patch("pymongo_search_utils.index.create_fulltext_search_index"):
            result = self.manager.ensure_fulltext_index("db", "coll", "text_index")

        assert result is True

    def test_fulltext_index_handles_error(self):
        """Should return False on errors."""
        self.mock_coll.list_search_indexes.return_value = iter([])

        with patch(
            "pymongo_search_utils.index.create_fulltext_search_index",
            side_effect=OperationFailure("Quota exceeded"),
        ):
            result = self.manager.ensure_fulltext_index("db", "coll", "text_index")

        assert result is False


class TestGetAtlasManager:
    """Test factory function."""

    def test_returns_manager_with_valid_url(self):
        with patch("app.services.atlas_client.MongoClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            manager = get_atlas_manager()
            assert manager is not None
            assert isinstance(manager, AtlasIndexManager)

    def test_returns_none_on_connection_error(self):
        from pymongo.errors import ConnectionFailure
        with patch("app.services.atlas_client.MongoClient", side_effect=ConnectionFailure("DNS failed")):
            manager = get_atlas_manager()
            assert manager is None
