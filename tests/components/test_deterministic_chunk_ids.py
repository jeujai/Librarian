"""
Unit tests for deterministic chunk ID generation and change mapping.

Tests cover:
- _generate_chunk_id determinism (same inputs → same output)
- _generate_chunk_id uniqueness (different inputs → different output)
- _generate_chunk_id raises ValueError on empty content
- _generate_chunk_id produces valid UUID
- ChunkChangeMapping computation (added, removed, unchanged sets)
- ChunkChangeMapping with None previous_chunk_ids (should be None)
"""

import uuid

import pytest

from src.multimodal_librarian.components.chunking_framework.framework import (
    ChunkChangeMapping,
    GenericMultiLevelChunkingFramework,
)
from src.multimodal_librarian.models.core import DocumentContent


class TestGenerateChunkId:
    """Tests for _generate_chunk_id method."""

    def setup_method(self):
        self.framework = GenericMultiLevelChunkingFramework()

    def test_determinism_same_inputs_same_output(self):
        """Same document_id and content always produce the same ID."""
        doc_id = "doc-123"
        content = "This is some chunk content for testing."
        id1 = self.framework._generate_chunk_id(doc_id, content)
        id2 = self.framework._generate_chunk_id(doc_id, content)
        assert id1 == id2

    def test_uniqueness_different_content(self):
        """Different content produces different IDs."""
        doc_id = "doc-123"
        id1 = self.framework._generate_chunk_id(doc_id, "content A")
        id2 = self.framework._generate_chunk_id(doc_id, "content B")
        assert id1 != id2

    def test_uniqueness_different_document_id(self):
        """Different document_id produces different IDs."""
        content = "same content"
        id1 = self.framework._generate_chunk_id("doc-1", content)
        id2 = self.framework._generate_chunk_id("doc-2", content)
        assert id1 != id2

    def test_raises_on_empty_content(self):
        """Empty content raises ValueError."""
        with pytest.raises(ValueError, match="empty content"):
            self.framework._generate_chunk_id("doc-1", "")

    def test_produces_valid_uuid(self):
        """Output is a valid UUID string."""
        result = self.framework._generate_chunk_id("doc-1", "hello")
        parsed = uuid.UUID(result)
        assert str(parsed) == result

    def test_uuid_version_4_bits(self):
        """Generated UUID has version 4 bits set."""
        result = self.framework._generate_chunk_id("doc-1", "hello")
        parsed = uuid.UUID(result)
        assert parsed.version == 4

    def test_passes_processed_chunk_validation(self):
        """Generated ID passes ProcessedChunk __post_init__ UUID check."""
        from src.multimodal_librarian.components.chunking_framework.framework import (
            ProcessedChunk,
        )
        chunk_id = self.framework._generate_chunk_id("doc-1", "test")
        # Should not raise
        chunk = ProcessedChunk(
            id=chunk_id,
            content="test",
            start_position=0,
            end_position=4,
        )
        assert chunk.id == chunk_id


class TestChunkChangeMapping:
    """Tests for ChunkChangeMapping computation in process_document."""

    def setup_method(self):
        self.framework = GenericMultiLevelChunkingFramework()

    def test_no_previous_ids_returns_none(self):
        """When previous_chunk_ids is None, chunk_change_mapping is None."""
        doc = DocumentContent(
            text="A simple test document with enough words.",
            images=[], tables=[],
            metadata={'title': 'Test'}, structure=None
        )
        result = self.framework.process_document(
            doc, document_id="test-doc"
        )
        assert result.chunk_change_mapping is None

    def test_identical_reprocessing_all_unchanged(self):
        """Re-processing identical content yields all unchanged IDs."""
        doc = DocumentContent(
            text="A simple test document with enough words to chunk.",
            images=[], tables=[],
            metadata={'title': 'Test'}, structure=None
        )
        # First pass
        result1 = self.framework.process_document(
            doc, document_id="test-doc"
        )
        first_ids = {c.id for c in result1.chunks}

        # Second pass with previous IDs
        result2 = self.framework.process_document(
            doc, document_id="test-doc",
            previous_chunk_ids=first_ids
        )
        mapping = result2.chunk_change_mapping
        assert mapping is not None
        assert len(mapping.added) == 0
        assert len(mapping.removed) == 0
        assert set(mapping.unchanged) == first_ids

    def test_different_content_produces_changes(self):
        """Different content produces added and removed IDs."""
        doc1 = DocumentContent(
            text="Original document content for first processing run.",
            images=[], tables=[],
            metadata={'title': 'Test'}, structure=None
        )
        doc2 = DocumentContent(
            text="Completely different document content for second run.",
            images=[], tables=[],
            metadata={'title': 'Test'}, structure=None
        )
        result1 = self.framework.process_document(
            doc1, document_id="test-doc"
        )
        first_ids = {c.id for c in result1.chunks}

        result2 = self.framework.process_document(
            doc2, document_id="test-doc",
            previous_chunk_ids=first_ids
        )
        mapping = result2.chunk_change_mapping
        assert mapping is not None
        new_ids = {c.id for c in result2.chunks}
        assert set(mapping.added) == new_ids - first_ids
        assert set(mapping.removed) == first_ids - new_ids
        assert set(mapping.unchanged) == new_ids & first_ids

    def test_empty_previous_ids_all_added(self):
        """Empty previous set means all new IDs are added."""
        doc = DocumentContent(
            text="Some document content.",
            images=[], tables=[],
            metadata={'title': 'Test'}, structure=None
        )
        result = self.framework.process_document(
            doc, document_id="test-doc",
            previous_chunk_ids=set()
        )
        mapping = result.chunk_change_mapping
        assert mapping is not None
        new_ids = {c.id for c in result.chunks}
        assert set(mapping.added) == new_ids
        assert len(mapping.removed) == 0
        assert len(mapping.unchanged) == 0

    def test_change_mapping_set_invariants(self):
        """added ∪ unchanged == new_set, removed ∪ unchanged == prev_set."""
        doc1 = DocumentContent(
            text="First version of the document content here.",
            images=[], tables=[],
            metadata={'title': 'Test'}, structure=None
        )
        doc2 = DocumentContent(
            text="Second version with modified document content.",
            images=[], tables=[],
            metadata={'title': 'Test'}, structure=None
        )
        result1 = self.framework.process_document(
            doc1, document_id="test-doc"
        )
        prev_ids = {c.id for c in result1.chunks}

        result2 = self.framework.process_document(
            doc2, document_id="test-doc",
            previous_chunk_ids=prev_ids
        )
        mapping = result2.chunk_change_mapping
        new_ids = {c.id for c in result2.chunks}

        assert set(mapping.added) | set(mapping.unchanged) == new_ids
        assert set(mapping.removed) | set(mapping.unchanged) == prev_ids
        assert len(set(mapping.added) & set(mapping.removed)) == 0
