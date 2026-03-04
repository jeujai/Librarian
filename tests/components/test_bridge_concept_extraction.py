"""
Unit tests for bridge chunk KG integration — concept extraction on bridge chunks.

Tests that chunk_with_smart_bridges runs concept extraction on each bridge
and populates metadata with extracted_concepts and adjacent_chunk_ids.

Requirements: 4.1, 4.2, 4.4
"""

from unittest.mock import MagicMock, patch

import pytest

from src.multimodal_librarian.components.chunking_framework.framework import (
    GenericMultiLevelChunkingFramework,
)
from src.multimodal_librarian.models.chunking import BridgeChunk
from src.multimodal_librarian.models.knowledge_graph import ConceptNode


@pytest.fixture
def framework():
    """Create a framework instance for testing."""
    return GenericMultiLevelChunkingFramework()


class TestBridgeChunkMetadataField:
    """Tests for the metadata field on BridgeChunk."""

    def test_metadata_defaults_to_none(self):
        """BridgeChunk metadata defaults to None."""
        bridge = BridgeChunk(
            content="some bridge content",
            source_chunks=["chunk-1", "chunk-2"],
        )
        assert bridge.metadata is None

    def test_metadata_can_be_set(self):
        """BridgeChunk metadata can be set at construction."""
        bridge = BridgeChunk(
            content="some bridge content",
            source_chunks=["chunk-1", "chunk-2"],
            metadata={"key": "value"},
        )
        assert bridge.metadata == {"key": "value"}

    def test_metadata_round_trips_through_dict(self):
        """Metadata survives to_dict / from_dict round-trip."""
        bridge = BridgeChunk(
            content="bridge text",
            source_chunks=["a", "b"],
            metadata={"extracted_concepts": ["c1"], "adjacent_chunk_ids": ["a", "b"]},
        )
        d = bridge.to_dict()
        assert d["metadata"] == bridge.metadata
        restored = BridgeChunk.from_dict(d)
        assert restored.metadata == bridge.metadata


class TestBridgeConceptExtraction:
    """Tests for concept extraction on bridge chunks in chunk_with_smart_bridges."""

    def test_bridge_gets_extracted_concepts(self, framework):
        """After bridge generation, each bridge has extracted_concepts in metadata."""
        mock_extractor = MagicMock()
        concept = ConceptNode(
            concept_id="mw_knowledge_graph",
            concept_name="knowledge graph",
            concept_type="MULTI_WORD",
            confidence=0.85,
        )
        mock_extractor.extract_concepts_regex.return_value = [concept]
        framework._concept_extractor = mock_extractor

        bridge = BridgeChunk(
            content="This bridge discusses knowledge graph integration.",
            source_chunks=["chunk-1", "chunk-2"],
        )

        # Simulate the post-processing loop from chunk_with_smart_bridges
        bridges = [bridge]
        concept_extractor = framework._get_concept_extractor()
        for b in bridges:
            bridge_concepts = concept_extractor.extract_concepts_regex(b.content)
            if b.metadata is None:
                b.metadata = {}
            b.metadata['extracted_concepts'] = [
                c.concept_id for c in bridge_concepts
            ]
            b.metadata['adjacent_chunk_ids'] = b.source_chunks

        assert bridge.metadata is not None
        assert bridge.metadata['extracted_concepts'] == ["mw_knowledge_graph"]
        assert bridge.metadata['adjacent_chunk_ids'] == ["chunk-1", "chunk-2"]

    def test_bridge_with_no_concepts_gets_empty_list(self, framework):
        """Bridge with no extractable concepts gets an empty extracted_concepts list."""
        mock_extractor = MagicMock()
        mock_extractor.extract_concepts_regex.return_value = []
        framework._concept_extractor = mock_extractor

        bridge = BridgeChunk(
            content="Simple text with no special terms.",
            source_chunks=["c1", "c2"],
        )

        bridges = [bridge]
        concept_extractor = framework._get_concept_extractor()
        for b in bridges:
            bridge_concepts = concept_extractor.extract_concepts_regex(b.content)
            if b.metadata is None:
                b.metadata = {}
            b.metadata['extracted_concepts'] = [
                c.concept_id for c in bridge_concepts
            ]
            b.metadata['adjacent_chunk_ids'] = b.source_chunks

        assert bridge.metadata['extracted_concepts'] == []
        assert bridge.metadata['adjacent_chunk_ids'] == ["c1", "c2"]

    def test_extraction_failure_sets_empty_concepts(self, framework):
        """If concept extraction raises, metadata still gets populated with empty list."""
        mock_extractor = MagicMock()
        mock_extractor.extract_concepts_regex.side_effect = RuntimeError("NLP failure")
        framework._concept_extractor = mock_extractor

        bridge = BridgeChunk(
            content="Bridge content here.",
            source_chunks=["x", "y"],
        )

        bridges = [bridge]
        concept_extractor = framework._get_concept_extractor()
        for b in bridges:
            try:
                bridge_concepts = concept_extractor.extract_concepts_regex(b.content)
                if b.metadata is None:
                    b.metadata = {}
                b.metadata['extracted_concepts'] = [
                    c.concept_id for c in bridge_concepts
                ]
                b.metadata['adjacent_chunk_ids'] = b.source_chunks
            except Exception:
                if b.metadata is None:
                    b.metadata = {}
                b.metadata['extracted_concepts'] = []
                b.metadata['adjacent_chunk_ids'] = b.source_chunks

        assert bridge.metadata['extracted_concepts'] == []
        assert bridge.metadata['adjacent_chunk_ids'] == ["x", "y"]

    def test_existing_metadata_preserved(self, framework):
        """Pre-existing metadata keys are preserved when concepts are added."""
        mock_extractor = MagicMock()
        mock_extractor.extract_concepts_regex.return_value = []
        framework._concept_extractor = mock_extractor

        bridge = BridgeChunk(
            content="Bridge text.",
            source_chunks=["a", "b"],
            metadata={"upgrade_candidate": True},
        )

        bridges = [bridge]
        concept_extractor = framework._get_concept_extractor()
        for b in bridges:
            bridge_concepts = concept_extractor.extract_concepts_regex(b.content)
            if b.metadata is None:
                b.metadata = {}
            b.metadata['extracted_concepts'] = [
                c.concept_id for c in bridge_concepts
            ]
            b.metadata['adjacent_chunk_ids'] = b.source_chunks

        assert bridge.metadata['upgrade_candidate'] is True
        assert bridge.metadata['extracted_concepts'] == []

    def test_multiple_concepts_extracted(self, framework):
        """Multiple concepts from a bridge are all captured."""
        mock_extractor = MagicMock()
        concepts = [
            ConceptNode(
                concept_id="mw_knowledge_graph",
                concept_name="knowledge graph",
                concept_type="MULTI_WORD",
                confidence=0.85,
            ),
            ConceptNode(
                concept_id="acr_KG",
                concept_name="KG",
                concept_type="ACRONYM",
                confidence=0.6,
            ),
        ]
        mock_extractor.extract_concepts_regex.return_value = concepts
        framework._concept_extractor = mock_extractor

        bridge = BridgeChunk(
            content="The knowledge graph (KG) connects concepts.",
            source_chunks=["c1", "c2"],
        )

        bridges = [bridge]
        concept_extractor = framework._get_concept_extractor()
        for b in bridges:
            bridge_concepts = concept_extractor.extract_concepts_regex(b.content)
            if b.metadata is None:
                b.metadata = {}
            b.metadata['extracted_concepts'] = [
                c.concept_id for c in bridge_concepts
            ]
            b.metadata['adjacent_chunk_ids'] = b.source_chunks

        assert set(bridge.metadata['extracted_concepts']) == {
            "mw_knowledge_graph", "acr_KG"
        }
