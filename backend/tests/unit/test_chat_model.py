"""Tests for ChatHistory model."""

import pytest
from datetime import datetime


class TestChatHistoryModel:
    """Chat history model for storing conversation sessions."""

    def test_create_chat_session(self):
        """ChatSession should store user_id and messages."""
        from app.models.chat import ChatSession, ChatMessage

        session = ChatSession(
            user_id="507f1f77bcf86cd799439011",
            session_id="abc-123",
            title="Питання про розклад",
            messages=[
                ChatMessage(role="user", content="Який розклад?"),
                ChatMessage(role="assistant", content="Розклад на понеділок..."),
            ],
        )
        assert session.user_id == "507f1f77bcf86cd799439011"
        assert len(session.messages) == 2
        assert session.messages[0].role == "user"

    def test_chat_message_with_sources(self):
        """ChatMessage should support optional sources list."""
        from app.models.chat import ChatMessage
        from app.models.document import SourceCitation

        msg = ChatMessage(
            role="assistant",
            content="Відповідь",
            sources=[SourceCitation(source_file="doc.pdf", chunk_index=3)],
        )
        assert len(msg.sources) == 1
        assert msg.sources[0].source_file == "doc.pdf"

    def test_chat_message_has_timestamp(self):
        """ChatMessage should have a timestamp."""
        from app.models.chat import ChatMessage

        msg = ChatMessage(role="user", content="Hello")
        assert isinstance(msg.timestamp, datetime)

    def test_chat_session_has_timestamps(self):
        """ChatSession should have created_at and updated_at."""
        from app.models.chat import ChatSession

        session = ChatSession(
            user_id="507f1f77bcf86cd799439011",
            session_id="abc-123",
        )
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.updated_at, datetime)
