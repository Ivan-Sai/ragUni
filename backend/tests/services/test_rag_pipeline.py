"""Tests for RAG pipeline — chat.py functions."""

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from langchain_core.documents import Document as LCDocument
from app.api.v1.chat import format_docs, extract_sources, run_rag_chain


class TestFormatDocs:
    """Test document formatting for RAG context."""

    def test_empty_docs(self):
        assert format_docs([]) == ""

    def test_single_doc(self):
        doc = LCDocument(
            page_content="Test content",
            metadata={"source_file": "test.pdf", "chunk_index": 0},
        )
        result = format_docs([doc])
        assert "test.pdf" in result
        assert "Test content" in result
        assert "Джерело 1" in result

    def test_multiple_docs_separated(self):
        docs = [
            LCDocument(page_content="First", metadata={"source_file": "a.pdf", "chunk_index": 0}),
            LCDocument(page_content="Second", metadata={"source_file": "b.pdf", "chunk_index": 1}),
        ]
        result = format_docs(docs)
        assert "Джерело 1" in result
        assert "Джерело 2" in result
        assert "---" in result  # separator

    def test_missing_metadata_uses_defaults(self):
        doc = LCDocument(page_content="No meta", metadata={})
        result = format_docs([doc])
        assert "Невідомий документ" in result


class TestExtractSources:
    """Test source extraction for response."""

    def test_empty_docs(self):
        assert extract_sources([]) == []

    def test_deduplicates_sources(self):
        doc1 = LCDocument(page_content="A", metadata={"source_file": "test.pdf", "chunk_index": 0})
        doc2 = LCDocument(page_content="B", metadata={"source_file": "test.pdf", "chunk_index": 0})
        sources = extract_sources([doc1, doc2])
        assert len(sources) == 1

    def test_truncates_long_preview(self):
        doc = LCDocument(
            page_content="x" * 300,
            metadata={"source_file": "test.pdf", "chunk_index": 0},
        )
        sources = extract_sources([doc])
        assert len(sources[0]["text"]) < 300
        assert sources[0]["text"].endswith("...")

    def test_preserves_short_preview(self):
        doc = LCDocument(
            page_content="Short text",
            metadata={"source_file": "test.pdf", "chunk_index": 0},
        )
        sources = extract_sources([doc])
        assert sources[0]["text"] == "Short text"

    def test_source_fields(self):
        doc = LCDocument(
            page_content="Content",
            metadata={"source_file": "doc.pdf", "chunk_index": 3},
        )
        sources = extract_sources([doc])
        assert sources[0]["source_file"] == "doc.pdf"
        assert sources[0]["chunk_index"] == 3


class TestRunRagChain:
    """Test run_rag_chain — focus on orchestration, not LCEL internals."""

    def _make_mock_retriever(self, docs=None):
        """Create a mock retriever."""
        if docs is None:
            docs = []
        mock_retriever = AsyncMock()
        mock_retriever.ainvoke = AsyncMock(return_value=docs)
        return mock_retriever

    def _make_mock_chain(self, answer="Відповідь"):
        """Create a mock LCEL chain with async ainvoke."""
        mock_chain = MagicMock()
        mock_chain.__or__ = MagicMock(return_value=mock_chain)
        mock_chain.ainvoke = AsyncMock(return_value=answer)
        return mock_chain

    def _setup_vs_mock(self, mock_vs, access_filter=None, docs=None):
        """Set up common vector_store_service mock."""
        if access_filter is None:
            access_filter = {}
        mock_vs.build_access_filter = MagicMock(return_value=access_filter)
        mock_vs.get_hybrid_retriever = MagicMock(return_value=self._make_mock_retriever(docs))
        mock_vs.get_retriever = MagicMock(return_value=self._make_mock_retriever(docs))

    @pytest.mark.asyncio
    async def test_initializes_and_calls_access_filter(self):
        """run_rag_chain must build access filter."""
        mock_doc = LCDocument(
            page_content="Test content",
            metadata={"source_file": "test.pdf", "chunk_index": 0},
        )

        mock_chain = self._make_mock_chain()
        with (
            patch("app.api.v1.chat.vector_store_service") as mock_vs,
            patch("app.api.v1.chat.get_llm", new_callable=AsyncMock),
            patch("app.api.v1.chat.rag_prompt") as mock_prompt,
            patch("app.api.v1.chat.settings") as mock_settings,
        ):
            mock_settings.use_hybrid_search = True
            mock_settings.top_k_results = 5
            mock_settings.llm_timeout_seconds = 30
            self._setup_vs_mock(mock_vs, access_filter={}, docs=[mock_doc])
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            result = await run_rag_chain("Тестове питання", "student", "CS")

            mock_vs.build_access_filter.assert_called_once_with("student", "CS")
            assert "sources" in result
            assert "docs" in result
            assert len(result["docs"]) == 1

    @pytest.mark.asyncio
    async def test_hybrid_search_preferred(self):
        """When use_hybrid_search=True, hybrid retriever is used first."""
        mock_chain = self._make_mock_chain()
        with (
            patch("app.api.v1.chat.vector_store_service") as mock_vs,
            patch("app.api.v1.chat.get_llm", new_callable=AsyncMock),
            patch("app.api.v1.chat.rag_prompt") as mock_prompt,
            patch("app.api.v1.chat.settings") as mock_settings,
        ):
            mock_settings.use_hybrid_search = True
            mock_settings.top_k_results = 5
            mock_settings.llm_timeout_seconds = 30
            self._setup_vs_mock(mock_vs)
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            await run_rag_chain("Test", "student")

            mock_vs.get_hybrid_retriever.assert_called_once()
            mock_vs.get_retriever.assert_not_called()

    @pytest.mark.asyncio
    async def test_hybrid_fallback_to_mmr(self):
        """When hybrid search raises ValueError/RuntimeError, falls back to MMR retriever."""
        mock_chain = self._make_mock_chain()
        with (
            patch("app.api.v1.chat.vector_store_service") as mock_vs,
            patch("app.api.v1.chat.get_llm", new_callable=AsyncMock),
            patch("app.api.v1.chat.rag_prompt") as mock_prompt,
            patch("app.api.v1.chat.settings") as mock_settings,
        ):
            mock_settings.use_hybrid_search = True
            mock_settings.top_k_results = 5
            mock_settings.llm_timeout_seconds = 30
            self._setup_vs_mock(mock_vs)
            mock_vs.get_hybrid_retriever = MagicMock(side_effect=ValueError("No index"))
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            await run_rag_chain("Test", "student")

            mock_vs.get_retriever.assert_called_once()
            call_kwargs = mock_vs.get_retriever.call_args[1]
            assert call_kwargs["search_type"] == "mmr"

    @pytest.mark.asyncio
    async def test_mmr_when_hybrid_disabled(self):
        """When use_hybrid_search=False, MMR retriever is used directly."""
        mock_chain = self._make_mock_chain()
        with (
            patch("app.api.v1.chat.vector_store_service") as mock_vs,
            patch("app.api.v1.chat.get_llm", new_callable=AsyncMock),
            patch("app.api.v1.chat.rag_prompt") as mock_prompt,
            patch("app.api.v1.chat.settings") as mock_settings,
        ):
            mock_settings.use_hybrid_search = False
            mock_settings.top_k_results = 5
            mock_settings.llm_timeout_seconds = 30
            self._setup_vs_mock(mock_vs)
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            await run_rag_chain("Test", "student")

            mock_vs.get_hybrid_retriever.assert_not_called()
            mock_vs.get_retriever.assert_called_once()
            call_kwargs = mock_vs.get_retriever.call_args[1]
            assert call_kwargs["search_type"] == "mmr"

    @pytest.mark.asyncio
    async def test_student_access_filter(self):
        """Student should get student-specific filter passed to retriever."""
        mock_chain = self._make_mock_chain()
        with (
            patch("app.api.v1.chat.vector_store_service") as mock_vs,
            patch("app.api.v1.chat.get_llm", new_callable=AsyncMock),
            patch("app.api.v1.chat.rag_prompt") as mock_prompt,
            patch("app.api.v1.chat.settings") as mock_settings,
        ):
            mock_settings.use_hybrid_search = True
            mock_settings.top_k_results = 5
            mock_settings.llm_timeout_seconds = 30
            student_filter = {"$or": [{"access_level": "public"}]}
            self._setup_vs_mock(mock_vs, access_filter=student_filter)
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            await run_rag_chain("Test", "student", "CS")

            call_kwargs = mock_vs.get_hybrid_retriever.call_args[1]
            assert call_kwargs["pre_filter"] == student_filter

    @pytest.mark.asyncio
    async def test_admin_gets_no_filter(self):
        """Admin should get empty filter -> passed as None to retriever."""
        mock_chain = self._make_mock_chain()
        with (
            patch("app.api.v1.chat.vector_store_service") as mock_vs,
            patch("app.api.v1.chat.get_llm", new_callable=AsyncMock),
            patch("app.api.v1.chat.rag_prompt") as mock_prompt,
            patch("app.api.v1.chat.settings") as mock_settings,
        ):
            mock_settings.use_hybrid_search = True
            mock_settings.top_k_results = 5
            mock_settings.llm_timeout_seconds = 30
            self._setup_vs_mock(mock_vs, access_filter={})
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            await run_rag_chain("Test", "admin")

            mock_vs.build_access_filter.assert_called_once_with("admin", None)
            call_kwargs = mock_vs.get_hybrid_retriever.call_args[1]
            assert call_kwargs["pre_filter"] is None


class TestLLMInit:
    """Test lazy LLM initialization."""

    @pytest.mark.asyncio
    async def test_get_llm_creates_singleton(self):
        import app.api.v1.chat as chat_module

        chat_module._llm = None  # Reset
        with patch("app.api.v1.chat.ChatOpenAI") as mock_cls:
            mock_cls.return_value = MagicMock()
            llm1 = await chat_module.get_llm()
            llm2 = await chat_module.get_llm()
            assert llm1 is llm2
            mock_cls.assert_called_once()  # Only created once

        chat_module._llm = None  # Clean up
