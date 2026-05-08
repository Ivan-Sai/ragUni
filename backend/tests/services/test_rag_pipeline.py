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
            page_content="x" * 600,
            metadata={"source_file": "test.pdf", "chunk_index": 0},
        )
        sources = extract_sources([doc])
        # With the new sentence-aware truncator the preview falls back
        # to a hard cut for repetitive input and ends with the typographic
        # ellipsis "…" instead of three dots.
        assert len(sources[0]["text"]) < 600
        assert sources[0]["text"].endswith("…")

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

    def _make_scored_doc(self, score: float = 0.9) -> LCDocument:
        """Build a doc whose metadata already contains a score, so the
        no-answer guard treats it as grounded."""
        return LCDocument(
            page_content="Test content",
            metadata={
                "source_file": "test.pdf",
                "chunk_index": 0,
                "score": score,
            },
        )

    def _stub_analysis(self, **overrides):
        """Build a QueryAnalysis stub for tests. We don't run the
        analyzer LLM during unit tests — analyze_query is mocked to
        return this synthetic analysis."""
        from app.services.query_analyzer import QueryAnalysis

        params = dict(
            intent="general",
            confidence=0.5,
            is_personal=False,
            entities={},
            reformulated_query="Тестове питання",
            preferred_strategies=["vector"],
        )
        params.update(overrides)
        return QueryAnalysis(**params)

    def _stub_retrieval(self, docs=None, structured=None):
        """Build a RetrievalResult stub the orchestrator would
        normally produce."""
        from app.services.retrieval_orchestrator import RetrievalResult

        return RetrievalResult(
            docs=docs or [],
            structured_records=structured or [],
            used_strategies=["vector"],
            counts_per_strategy={"vector": len(docs or [])},
        )

    @pytest.mark.asyncio
    async def test_initializes_and_calls_access_filter(self):
        """run_rag_chain must build the access filter and produce sources."""
        mock_chain = self._make_mock_chain()
        scored_doc = self._make_scored_doc()
        with (
            patch("app.api.v1.chat.vector_store_service") as mock_vs,
            patch("app.api.v1.chat.get_llm", new_callable=AsyncMock),
            patch("app.api.v1.chat.rag_prompt") as mock_prompt,
            patch(
                "app.api.v1.chat.analyze_query",
                new_callable=AsyncMock,
                return_value=self._stub_analysis(),
            ),
            patch(
                "app.api.v1.chat.retrieve",
                new_callable=AsyncMock,
                return_value=self._stub_retrieval(docs=[scored_doc]),
            ),
            patch(
                "app.api.v1.chat._attach_document_ids",
                new_callable=AsyncMock,
                side_effect=lambda s: s,
            ),
            patch("app.api.v1.chat.settings") as mock_settings,
        ):
            mock_settings.top_k_results = 5
            mock_settings.llm_timeout_seconds = 30
            mock_settings.no_answer_score_threshold = 0.55
            mock_settings.max_conversation_messages = 8
            mock_settings.source_preview_max_chars = 350
            mock_vs.build_access_filter = MagicMock(return_value={})
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            result = await run_rag_chain(
                "Тестове питання", "student", user_faculty_id="cs-id"
            )

            mock_vs.build_access_filter.assert_called_once_with(
                user_role="student",
                user_faculty_id="cs-id",
                user_group_id=None,
                user_year=None,
                user_level=None,
                target_doc_types=None,
            )
            assert result["grounded"] is True
            assert len(result["docs"]) == 1
            assert result["sources"]

    @pytest.mark.asyncio
    async def test_no_answer_guard_below_threshold(self):
        """Empty / low-score retrieval triggers the canned no-answer reply."""
        weak_doc = LCDocument(
            page_content="weak",
            metadata={"source_file": "x.pdf", "chunk_index": 0, "score": 0.1},
        )
        with (
            patch("app.api.v1.chat.vector_store_service") as mock_vs,
            patch(
                "app.api.v1.chat.analyze_query",
                new_callable=AsyncMock,
                return_value=self._stub_analysis(),
            ),
            patch(
                "app.api.v1.chat.retrieve",
                new_callable=AsyncMock,
                return_value=self._stub_retrieval(docs=[weak_doc]),
            ),
            patch("app.api.v1.chat.settings") as mock_settings,
        ):
            mock_settings.top_k_results = 5
            mock_settings.llm_timeout_seconds = 30
            mock_settings.no_answer_score_threshold = 0.55
            mock_settings.source_preview_max_chars = 350
            mock_vs.build_access_filter = MagicMock(return_value={})

            result = await run_rag_chain("Test", "student", user_faculty_id=None)

            assert result["grounded"] is False
            assert result["sources"] == []
            assert result["docs"] == []
            assert "переформулювати" in result["answer"]

    @pytest.mark.asyncio
    async def test_student_access_filter(self):
        """Student access filter is built from the user's profile and
        passed to the orchestrator unchanged."""
        mock_chain = self._make_mock_chain()
        scored_doc = self._make_scored_doc()
        student_filter = {"$or": [{"access_level": "public"}]}
        with (
            patch("app.api.v1.chat.vector_store_service") as mock_vs,
            patch("app.api.v1.chat.get_llm", new_callable=AsyncMock),
            patch("app.api.v1.chat.rag_prompt") as mock_prompt,
            patch(
                "app.api.v1.chat.analyze_query",
                new_callable=AsyncMock,
                return_value=self._stub_analysis(),
            ),
            patch(
                "app.api.v1.chat.retrieve",
                new_callable=AsyncMock,
                return_value=self._stub_retrieval(docs=[scored_doc]),
            ) as mock_retrieve,
            patch(
                "app.api.v1.chat._attach_document_ids",
                new_callable=AsyncMock,
                side_effect=lambda s: s,
            ),
            patch("app.api.v1.chat.settings") as mock_settings,
        ):
            mock_settings.top_k_results = 5
            mock_settings.llm_timeout_seconds = 30
            mock_settings.no_answer_score_threshold = 0.55
            mock_settings.source_preview_max_chars = 350
            mock_vs.build_access_filter = MagicMock(return_value=student_filter)
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            await run_rag_chain("Test", "student", user_faculty_id="cs-id")

            assert mock_retrieve.await_args.kwargs["pre_filter"] == student_filter

    @pytest.mark.asyncio
    async def test_admin_gets_no_filter(self):
        """Admin gets an empty access filter, which the orchestrator
        forwards verbatim."""
        mock_chain = self._make_mock_chain()
        scored_doc = self._make_scored_doc()
        with (
            patch("app.api.v1.chat.vector_store_service") as mock_vs,
            patch("app.api.v1.chat.get_llm", new_callable=AsyncMock),
            patch("app.api.v1.chat.rag_prompt") as mock_prompt,
            patch(
                "app.api.v1.chat.analyze_query",
                new_callable=AsyncMock,
                return_value=self._stub_analysis(),
            ),
            patch(
                "app.api.v1.chat.retrieve",
                new_callable=AsyncMock,
                return_value=self._stub_retrieval(docs=[scored_doc]),
            ) as mock_retrieve,
            patch(
                "app.api.v1.chat._attach_document_ids",
                new_callable=AsyncMock,
                side_effect=lambda s: s,
            ),
            patch("app.api.v1.chat.settings") as mock_settings,
        ):
            mock_settings.top_k_results = 5
            mock_settings.llm_timeout_seconds = 30
            mock_settings.no_answer_score_threshold = 0.55
            mock_settings.source_preview_max_chars = 350
            mock_vs.build_access_filter = MagicMock(return_value={})
            mock_prompt.__or__ = MagicMock(return_value=mock_chain)

            await run_rag_chain("Test", "admin")

            mock_vs.build_access_filter.assert_called_once_with(
                user_role="admin",
                user_faculty_id=None,
                user_group_id=None,
                user_year=None,
                user_level=None,
                target_doc_types=None,
            )
            assert mock_retrieve.await_args.kwargs["pre_filter"] == {}


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
