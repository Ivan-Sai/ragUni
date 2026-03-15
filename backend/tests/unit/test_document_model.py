"""Tests for updated Document model with access_level field."""

import pytest


class TestDocumentAccessLevel:
    """Document model should support access_level and faculty fields."""

    def test_document_with_public_access(self):
        """Document with public access_level should be valid."""
        from app.models.document import Document

        doc = Document(
            filename="test.pdf",
            file_type="pdf",
            access_level="public",
        )
        assert doc.access_level == "public"

    def test_document_with_faculty_access(self):
        """Document with faculty-specific access should be valid."""
        from app.models.document import Document

        doc = Document(
            filename="schedule.xlsx",
            file_type="xlsx",
            access_level="faculty:Факультет КН",
            faculty="Факультет КН",
        )
        assert doc.access_level == "faculty:Факультет КН"
        assert doc.faculty == "Факультет КН"

    def test_document_with_teachers_only_access(self):
        """Document with teachers_only access should be valid."""
        from app.models.document import Document

        doc = Document(
            filename="methods.docx",
            file_type="docx",
            access_level="teachers_only",
        )
        assert doc.access_level == "teachers_only"

    def test_document_default_access_level(self):
        """Document without access_level should default to 'public'."""
        from app.models.document import Document

        doc = Document(filename="test.pdf", file_type="pdf")
        assert doc.access_level == "public"

    def test_document_chunk_has_access_level(self):
        """DocumentChunk should also have access_level metadata."""
        from app.models.document import DocumentChunk

        chunk = DocumentChunk(
            text="Sample text",
            chunk_index=0,
            embedding=[0.1] * 1024,
            access_level="public",
            faculty=None,
        )
        assert chunk.access_level == "public"
