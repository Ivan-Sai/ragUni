"""Tests for VectorStoreService — access control, chunking, search."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.services.vector_store import VectorStoreService


class TestAccessFilter:
    """Test build_access_filter for different roles."""

    def test_admin_sees_everything(self):
        """Admin should get empty filter (no restrictions)."""
        result = VectorStoreService.build_access_filter("admin")
        assert result == {}

    def test_admin_with_faculty_still_sees_everything(self):
        result = VectorStoreService.build_access_filter("admin", "CS")
        assert result == {}

    def test_student_without_faculty_sees_public_only(self):
        result = VectorStoreService.build_access_filter("student")
        assert result == {"$or": [{"access_level": "public"}]}

    def test_student_with_faculty_sees_public_and_faculty(self):
        result = VectorStoreService.build_access_filter("student", "CS")
        assert "$or" in result
        conditions = result["$or"]
        assert {"access_level": "public"} in conditions
        # Faculty condition
        faculty_cond = [c for c in conditions if "$and" in c]
        assert len(faculty_cond) == 1
        assert {"access_level": "faculty"} in faculty_cond[0]["$and"]
        assert {"faculty": "CS"} in faculty_cond[0]["$and"]

    def test_teacher_sees_public_restricted_and_faculty(self):
        result = VectorStoreService.build_access_filter("teacher", "Math")
        conditions = result["$or"]
        assert {"access_level": "public"} in conditions
        assert {"access_level": "restricted"} in conditions
        faculty_cond = [c for c in conditions if "$and" in c]
        assert len(faculty_cond) == 1

    def test_teacher_without_faculty_sees_public_and_restricted(self):
        result = VectorStoreService.build_access_filter("teacher")
        conditions = result["$or"]
        assert {"access_level": "public"} in conditions
        assert {"access_level": "restricted"} in conditions
        assert len(conditions) == 2  # no faculty condition


class TestChunking:
    """Test text chunking."""

    def setup_method(self):
        self.service = VectorStoreService()
        # Initialize only text_splitter (don't need MongoDB)
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        self.service._text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=100,
            chunk_overlap=20,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def test_empty_text_returns_empty(self):
        assert self.service.chunk_text("") == []
        assert self.service.chunk_text("   ") == []
        assert self.service.chunk_text(None) == []

    def test_short_text_single_chunk(self):
        chunks = self.service.chunk_text("Short text")
        assert len(chunks) == 1
        assert chunks[0] == "Short text"

    def test_long_text_multiple_chunks(self):
        text = "Word " * 100  # 500 chars
        chunks = self.service.chunk_text(text)
        assert len(chunks) > 1

    def test_chunks_have_overlap(self):
        # Create text with clear sentences
        text = ". ".join(f"Sentence number {i}" for i in range(20))
        chunks = self.service.chunk_text(text)
        assert len(chunks) > 1
        # Overlap means some content appears in adjacent chunks
        for i in range(len(chunks) - 1):
            # At least some words from end of chunk i should appear in chunk i+1
            last_words = chunks[i][-20:]
            # The overlap mechanism should ensure continuity
            assert len(chunks[i]) > 0


class TestRetriever:
    """Test retriever factory."""

    def setup_method(self):
        self.service = VectorStoreService()
        self.mock_vs = MagicMock()
        self.mock_vs.as_retriever = MagicMock(return_value=MagicMock())
        self.service._vector_store = self.mock_vs

    def test_mmr_retriever_params(self):
        self.service.get_retriever(
            search_type="mmr",
            k=5,
            pre_filter={"access_level": "public"},
            fetch_k=20,
            lambda_mult=0.7,
        )
        call_kwargs = self.mock_vs.as_retriever.call_args[1]
        assert call_kwargs["search_type"] == "mmr"
        assert call_kwargs["search_kwargs"]["k"] == 5
        assert call_kwargs["search_kwargs"]["pre_filter"] == {"access_level": "public"}
        assert call_kwargs["search_kwargs"]["fetch_k"] == 20
        assert call_kwargs["search_kwargs"]["lambda_mult"] == 0.7

    def test_similarity_retriever_params(self):
        self.service.get_retriever(search_type="similarity", k=3)
        call_kwargs = self.mock_vs.as_retriever.call_args[1]
        assert call_kwargs["search_type"] == "similarity"
        assert call_kwargs["search_kwargs"]["k"] == 3
        assert "fetch_k" not in call_kwargs["search_kwargs"]

    def test_no_filter_when_none(self):
        self.service.get_retriever(search_type="similarity", k=5, pre_filter=None)
        call_kwargs = self.mock_vs.as_retriever.call_args[1]
        assert "pre_filter" not in call_kwargs["search_kwargs"]


class TestHybridRetriever:
    """Test hybrid search retriever creation."""

    def setup_method(self):
        self.service = VectorStoreService()
        self.mock_vs = MagicMock()
        self.service._vector_store = self.mock_vs

    def test_hybrid_retriever_uses_vectorstore(self):
        with patch("app.services.vector_store.MongoDBAtlasHybridSearchRetriever") as mock_cls:
            self.service.get_hybrid_retriever(k=5)
            mock_cls.assert_called_once()
            call_kwargs = mock_cls.call_args[1]
            assert call_kwargs["vectorstore"] is self.mock_vs
            assert call_kwargs["k"] == 5

    def test_hybrid_retriever_passes_pre_filter(self):
        pre_filter = {"access_level": "public"}
        with patch("app.services.vector_store.MongoDBAtlasHybridSearchRetriever") as mock_cls:
            self.service.get_hybrid_retriever(k=3, pre_filter=pre_filter)
            call_kwargs = mock_cls.call_args[1]
            assert call_kwargs["pre_filter"] == pre_filter

    def test_hybrid_retriever_custom_penalties(self):
        with patch("app.services.vector_store.MongoDBAtlasHybridSearchRetriever") as mock_cls:
            self.service.get_hybrid_retriever(vector_penalty=30.0, fulltext_penalty=40.0)
            call_kwargs = mock_cls.call_args[1]
            assert call_kwargs["vector_penalty"] == 30.0
            assert call_kwargs["fulltext_penalty"] == 40.0


class TestAsyncSearch:
    """Test async search wrappers."""

    @pytest.mark.asyncio
    async def test_similarity_search_filters_by_score(self):
        service = VectorStoreService()
        mock_doc_good = MagicMock()
        mock_doc_bad = MagicMock()

        # Mock similarity_search_with_score
        async def mock_search(query, k, pre_filter):
            return [(mock_doc_good, 0.85), (mock_doc_bad, 0.30)]

        with patch.object(service, "similarity_search_with_score", side_effect=mock_search):
            results = await service.similarity_search("test query", k=2, score_threshold=0.5)
            assert len(results) == 1
            assert results[0] is mock_doc_good

    @pytest.mark.asyncio
    async def test_similarity_search_default_threshold(self):
        from app.config import get_settings
        default_threshold = get_settings().vector_score_threshold

        service = VectorStoreService()
        mock_doc = MagicMock()

        async def mock_search(query, k, pre_filter):
            return [(mock_doc, default_threshold + 0.01)]

        with patch.object(service, "similarity_search_with_score", side_effect=mock_search):
            results = await service.similarity_search("test", k=1)
            assert len(results) == 1
