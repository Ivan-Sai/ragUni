"""Tests for Document model — access_level, faculty_id and audience targeting."""

from bson import ObjectId


SAMPLE_FACULTY_ID = str(ObjectId())
SAMPLE_GROUP_ID = str(ObjectId())


class TestDocumentAccessLevel:
    """Document model should support access_level and faculty_id fields."""

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
            access_level="faculty",
            faculty_id=SAMPLE_FACULTY_ID,
        )
        assert doc.access_level == "faculty"
        assert doc.faculty_id == SAMPLE_FACULTY_ID

    def test_document_with_restricted_access(self):
        """Document with restricted access should be valid."""
        from app.models.document import Document

        doc = Document(
            filename="methods.docx",
            file_type="docx",
            access_level="restricted",
        )
        assert doc.access_level == "restricted"

    def test_document_default_access_level(self):
        """Document without access_level should default to 'public'."""
        from app.models.document import Document

        doc = Document(filename="test.pdf", file_type="pdf")
        assert doc.access_level == "public"

    def test_document_default_audience_is_empty(self):
        """target_* fields default to empty / null = visible to everyone."""
        from app.models.document import Document

        doc = Document(filename="test.pdf", file_type="pdf")
        assert doc.target_group_ids == []
        assert doc.target_years == []
        assert doc.target_level is None

    def test_document_audience_targeting(self):
        """Audience fields should round-trip through the model."""
        from app.models.document import Document

        doc = Document(
            filename="schedule.pdf",
            file_type="pdf",
            access_level="faculty",
            faculty_id=SAMPLE_FACULTY_ID,
            target_group_ids=[SAMPLE_GROUP_ID],
            target_years=[3, 4],
            target_level="bachelor",
        )
        assert doc.target_group_ids == [SAMPLE_GROUP_ID]
        assert doc.target_years == [3, 4]
        assert doc.target_level == "bachelor"

    def test_document_chunk_has_access_level(self):
        """DocumentChunk should also have access_level metadata."""
        from app.models.document import DocumentChunk

        chunk = DocumentChunk(
            text="Sample text",
            chunk_index=0,
            embedding=[0.1] * 1024,
            access_level="public",
            faculty_id=None,
        )
        assert chunk.access_level == "public"
