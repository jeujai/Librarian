"""
Tests for KnowledgeGraphBuilder._reconcile_cross_references method.

Validates: Requirements 5.2, 5.3
"""

import pytest

from multimodal_librarian.components.knowledge_graph.kg_builder import (
    KnowledgeGraphBuilder,
)
from multimodal_librarian.models.kg_retrieval import CrossReference


@pytest.fixture
def builder():
    return KnowledgeGraphBuilder()


def _make_ref(source_chunk_id, target_type, target_label, raw_text=""):
    return CrossReference(
        source_chunk_id=source_chunk_id,
        reference_type="explicit",
        target_type=target_type,
        target_label=target_label,
        raw_text=raw_text or f"see {target_type} {target_label}",
    )


class TestSuccessfulResolution:
    """Target found in chunk metadata."""

    def test_single_match(self, builder):
        refs = [_make_ref("chunk-A", "section", "3.1")]
        meta = {"chunk-B": {"section": "3.1"}}
        result = builder._reconcile_cross_references(refs, meta)
        assert result[0].resolved_chunk_ids == ["chunk-B"]

    def test_chapter_match(self, builder):
        refs = [_make_ref("chunk-A", "chapter", "4")]
        meta = {"chunk-B": {"chapter": "4"}}
        result = builder._reconcile_cross_references(refs, meta)
        assert result[0].resolved_chunk_ids == ["chunk-B"]

    def test_figure_match(self, builder):
        refs = [_make_ref("chunk-A", "figure", "12")]
        meta = {"chunk-B": {"figure": "12"}}
        result = builder._reconcile_cross_references(refs, meta)
        assert result[0].resolved_chunk_ids == ["chunk-B"]

    def test_table_match(self, builder):
        refs = [_make_ref("chunk-A", "table", "2.3")]
        meta = {"chunk-B": {"table": "2.3"}}
        result = builder._reconcile_cross_references(refs, meta)
        assert result[0].resolved_chunk_ids == ["chunk-B"]

    def test_page_match(self, builder):
        refs = [_make_ref("chunk-A", "page", "42")]
        meta = {"chunk-B": {"page": "42"}}
        result = builder._reconcile_cross_references(refs, meta)
        assert result[0].resolved_chunk_ids == ["chunk-B"]


class TestUnresolvedReference:
    """Target not found in metadata."""

    def test_no_matching_metadata(self, builder):
        refs = [_make_ref("chunk-A", "section", "99")]
        meta = {"chunk-B": {"section": "1.0"}}
        result = builder._reconcile_cross_references(refs, meta)
        assert result[0].resolved_chunk_ids is None

    def test_wrong_target_type(self, builder):
        refs = [_make_ref("chunk-A", "chapter", "3.1")]
        meta = {"chunk-B": {"section": "3.1"}}
        result = builder._reconcile_cross_references(refs, meta)
        assert result[0].resolved_chunk_ids is None


class TestMultipleChunksMatchingSameTarget:
    """Multiple chunks share the same section/chapter label."""

    def test_two_chunks_same_section(self, builder):
        refs = [_make_ref("chunk-A", "section", "2")]
        meta = {
            "chunk-B": {"section": "2"},
            "chunk-C": {"section": "2"},
        }
        result = builder._reconcile_cross_references(refs, meta)
        assert set(result[0].resolved_chunk_ids) == {"chunk-B", "chunk-C"}


class TestEmptyInputs:
    """Empty cross_references or chunk_metadata."""

    def test_empty_cross_references(self, builder):
        result = builder._reconcile_cross_references([], {"c1": {"section": "1"}})
        assert result == []

    def test_empty_chunk_metadata(self, builder):
        refs = [_make_ref("chunk-A", "section", "1")]
        result = builder._reconcile_cross_references(refs, {})
        assert result[0].resolved_chunk_ids is None

    def test_both_empty(self, builder):
        result = builder._reconcile_cross_references([], {})
        assert result == []


class TestReferencesEdgeCreated:
    """REFERENCES edges are created in self.relationships."""

    def test_edge_created_on_resolution(self, builder):
        refs = [_make_ref("chunk-A", "section", "3.1")]
        meta = {"chunk-B": {"section": "3.1"}}
        builder._reconcile_cross_references(refs, meta)

        edge_key = "chunk-A_REFERENCES_chunk-B"
        assert edge_key in builder.relationships
        edge = builder.relationships[edge_key]
        assert edge.predicate == "REFERENCES"
        assert edge.subject_concept == "chunk-A"
        assert edge.object_concept == "chunk-B"
        assert edge.confidence == 0.8
        assert "chunk-A" in edge.evidence_chunks

    def test_no_edge_for_unresolved(self, builder):
        refs = [_make_ref("chunk-A", "section", "99")]
        meta = {"chunk-B": {"section": "1"}}
        builder._reconcile_cross_references(refs, meta)
        assert len(builder.relationships) == 0

    def test_no_duplicate_edges(self, builder):
        refs = [
            _make_ref("chunk-A", "section", "3.1"),
            _make_ref("chunk-A", "section", "3.1"),
        ]
        meta = {"chunk-B": {"section": "3.1"}}
        builder._reconcile_cross_references(refs, meta)
        # Both refs resolve to same edge key — should only have one edge
        assert len(builder.relationships) == 1

    def test_multiple_target_chunks_create_multiple_edges(self, builder):
        refs = [_make_ref("chunk-A", "section", "2")]
        meta = {
            "chunk-B": {"section": "2"},
            "chunk-C": {"section": "2"},
        }
        builder._reconcile_cross_references(refs, meta)
        assert "chunk-A_REFERENCES_chunk-B" in builder.relationships
        assert "chunk-A_REFERENCES_chunk-C" in builder.relationships


class TestMetadataLabelCoercion:
    """Numeric metadata labels are coerced to strings for matching."""

    def test_integer_label_in_metadata(self, builder):
        refs = [_make_ref("chunk-A", "page", "42")]
        meta = {"chunk-B": {"page": 42}}  # int, not str
        result = builder._reconcile_cross_references(refs, meta)
        assert result[0].resolved_chunk_ids == ["chunk-B"]
