"""
Unit tests for concept bisection detection and boundary adjustment.

Tests the _adjust_boundary_for_concept_contiguity method on
GenericMultiLevelChunkingFramework and its integration into
_perform_primary_chunking.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

from unittest.mock import MagicMock, patch

import pytest

from src.multimodal_librarian.components.chunking_framework.framework import (
    GenericMultiLevelChunkingFramework,
    UnresolvedBisection,
)
from src.multimodal_librarian.models.knowledge_graph import ConceptNode


@pytest.fixture
def framework():
    """Create a framework instance for testing."""
    return GenericMultiLevelChunkingFramework()


class TestGetConceptExtractor:
    """Tests for lazy ConceptExtractor initialization."""

    def test_lazy_init_creates_extractor(self, framework):
        """ConceptExtractor is created on first call."""
        assert not hasattr(framework, '_concept_extractor') or \
            framework._concept_extractor is None
        extractor = framework._get_concept_extractor()
        assert extractor is not None

    def test_lazy_init_returns_same_instance(self, framework):
        """Subsequent calls return the cached instance."""
        first = framework._get_concept_extractor()
        second = framework._get_concept_extractor()
        assert first is second


class TestAdjustBoundaryForConceptContiguity:
    """Tests for _adjust_boundary_for_concept_contiguity."""

    def test_no_concepts_returns_unchanged(self, framework):
        """When no concepts span the boundary, return it unchanged."""
        mock_extractor = MagicMock()
        mock_extractor.extract_concepts_regex.return_value = []
        framework._concept_extractor = mock_extractor

        pre = "the quick brown fox jumps over the lazy dog today"
        post = "and then it ran away very fast into the woods"
        result = framework._adjust_boundary_for_concept_contiguity(
            pre_boundary_text=pre,
            post_boundary_text=post,
            boundary_word_index=10,
            max_chunk_size=200,
            current_chunk_size=10,
            overlap_window=5,
        )
        assert result == 10

    def test_spanning_concept_shifts_forward(self, framework):
        """A multi-word concept spanning the boundary shifts it forward."""
        # Place "knowledge graph" so it spans the boundary.
        # overlap_pre picks last 5 words of pre, overlap_post picks
        # first 5 words of post.
        pre = "we study the knowledge"
        post = "graph in detail today now"
        result = framework._adjust_boundary_for_concept_contiguity(
            pre_boundary_text=pre,
            post_boundary_text=post,
            boundary_word_index=4,
            max_chunk_size=200,
            current_chunk_size=4,
            overlap_window=5,
        )
        # "knowledge" is at index 3 in overlap, "graph" at index 4.
        # boundary_in_overlap = len(overlap_pre) = 4.
        # concept spans [3, 5). boundary 4 is inside.
        # shift_forward = 5 - 4 = 1 → new boundary = 4 + 1 = 5
        assert result == 5

    def test_shift_backward_when_forward_exceeds_max(self, framework):
        """If shifting forward exceeds max_chunk_size, shift backward."""
        pre = "we study the knowledge"
        post = "graph in detail today now"
        result = framework._adjust_boundary_for_concept_contiguity(
            pre_boundary_text=pre,
            post_boundary_text=post,
            boundary_word_index=4,
            max_chunk_size=4,       # tight limit — can't shift forward
            current_chunk_size=4,
            overlap_window=5,
        )
        # shift_forward = 1, but 4 + 1 > 4 (max), so shift backward.
        # shift_backward = 4 - 3 = 1 → new boundary = 4 - 1 = 3
        assert result == 3

    def test_highest_confidence_concept_wins(self, framework):
        """When multiple concepts span the boundary, highest confidence wins."""
        # Mock the concept extractor to return two spanning concepts
        mock_extractor = MagicMock()
        concept_low = ConceptNode(
            concept_id="mw_data_model",
            concept_name="data model",
            concept_type="MULTI_WORD",
            confidence=0.5,
        )
        concept_high = ConceptNode(
            concept_id="mw_knowledge_graph",
            concept_name="knowledge graph",
            concept_type="MULTI_WORD",
            confidence=0.9,
        )
        mock_extractor.extract_concepts_regex.return_value = [
            concept_low, concept_high,
        ]
        framework._concept_extractor = mock_extractor

        # Both concepts span the boundary at position 4 in overlap
        # "data model knowledge graph stuff"
        # overlap_pre = ["data", "model", "knowledge"]  (3 words)
        # overlap_post = ["graph", "stuff"]  (2 words)
        # boundary_in_overlap = 3
        pre = "data model knowledge"
        post = "graph stuff"
        result = framework._adjust_boundary_for_concept_contiguity(
            pre_boundary_text=pre,
            post_boundary_text=post,
            boundary_word_index=3,
            max_chunk_size=200,
            current_chunk_size=3,
            overlap_window=5,
        )
        # "knowledge graph" spans [2, 4), boundary_in_overlap=3
        # shift_forward = 4 - 3 = 1 → new boundary = 3 + 1 = 4
        assert result == 4

    def test_exception_returns_original_boundary(self, framework):
        """If concept extraction raises, return original boundary."""
        mock_extractor = MagicMock()
        mock_extractor.extract_concepts_regex.side_effect = RuntimeError(
            "boom"
        )
        framework._concept_extractor = mock_extractor

        result = framework._adjust_boundary_for_concept_contiguity(
            pre_boundary_text="some text here",
            post_boundary_text="more text there",
            boundary_word_index=3,
            max_chunk_size=200,
            current_chunk_size=3,
            overlap_window=5,
        )
        assert result == 3

    def test_single_word_concepts_ignored(self, framework):
        """Single-word concepts cannot be bisected — boundary unchanged."""
        mock_extractor = MagicMock()
        single_word = ConceptNode(
            concept_id="entity_python",
            concept_name="Python",
            concept_type="ENTITY",
            confidence=0.9,
        )
        mock_extractor.extract_concepts_regex.return_value = [single_word]
        framework._concept_extractor = mock_extractor

        result = framework._adjust_boundary_for_concept_contiguity(
            pre_boundary_text="we use Python",
            post_boundary_text="for scripting tasks",
            boundary_word_index=3,
            max_chunk_size=200,
            current_chunk_size=3,
            overlap_window=5,
        )
        assert result == 3

    def test_empty_overlap_returns_unchanged(self, framework):
        """Empty pre or post text returns boundary unchanged."""
        result = framework._adjust_boundary_for_concept_contiguity(
            pre_boundary_text="",
            post_boundary_text="some words here",
            boundary_word_index=0,
            max_chunk_size=200,
            current_chunk_size=0,
            overlap_window=5,
        )
        assert result == 0


class TestUnresolvedBisectionRecording:
    """Tests for unresolved bisection recording in
    _adjust_boundary_for_concept_contiguity.

    Requirements: 1.1, 1.2, 1.4
    """

    def test_none_list_skips_recording(self, framework):
        """When unresolved_bisections is None, nothing is recorded."""
        mock_extractor = MagicMock()
        concept = ConceptNode(
            concept_id="mw_knowledge_graph",
            concept_name="knowledge graph",
            concept_type="MULTI_WORD",
            confidence=0.9,
        )
        mock_extractor.extract_concepts_regex.return_value = [concept]
        framework._concept_extractor = mock_extractor

        # Force fallback (both shifts fail) to trigger recording path
        result = framework._adjust_boundary_for_concept_contiguity(
            pre_boundary_text="knowledge",
            post_boundary_text="graph",
            boundary_word_index=1,
            max_chunk_size=1,
            current_chunk_size=1,
            overlap_window=5,
            unresolved_bisections=None,
        )
        # Should not raise — backward compatible
        assert result == 1

    def test_no_spanning_concepts_records_nothing(self, framework):
        """When no concepts span the boundary, list stays empty."""
        mock_extractor = MagicMock()
        mock_extractor.extract_concepts_regex.return_value = []
        framework._concept_extractor = mock_extractor

        bisections = []
        framework._adjust_boundary_for_concept_contiguity(
            pre_boundary_text="hello world foo",
            post_boundary_text="bar baz qux",
            boundary_word_index=3,
            max_chunk_size=200,
            current_chunk_size=3,
            overlap_window=5,
            unresolved_bisections=bisections,
        )
        assert bisections == []

    def test_resolved_concept_not_recorded(self, framework):
        """A concept resolved by forward shift is not recorded."""
        mock_extractor = MagicMock()
        concept = ConceptNode(
            concept_id="mw_knowledge_graph",
            concept_name="knowledge graph",
            concept_type="MULTI_WORD",
            confidence=0.9,
        )
        mock_extractor.extract_concepts_regex.return_value = [concept]
        framework._concept_extractor = mock_extractor

        pre = "we study the knowledge"
        post = "graph in detail today now"
        bisections = []
        framework._adjust_boundary_for_concept_contiguity(
            pre_boundary_text=pre,
            post_boundary_text=post,
            boundary_word_index=4,
            max_chunk_size=200,
            current_chunk_size=4,
            overlap_window=5,
            unresolved_bisections=bisections,
        )
        # Only one spanning concept and it was resolved
        assert bisections == []

    def test_fallback_records_best_concept(self, framework):
        """When both shifts fail, the best concept is recorded."""
        mock_extractor = MagicMock()
        concept = ConceptNode(
            concept_id="mw_knowledge_graph",
            concept_name="knowledge graph",
            concept_type="MULTI_WORD",
            confidence=0.85,
        )
        mock_extractor.extract_concepts_regex.return_value = [concept]
        framework._concept_extractor = mock_extractor

        bisections = []
        # boundary_word_index=1, max_chunk_size=1, current_chunk_size=1
        # forward shift: 1+1=2 > 1 → fail
        # backward shift: 1-0=1 but new_boundary=0 → not > 0 → fail
        result = framework._adjust_boundary_for_concept_contiguity(
            pre_boundary_text="knowledge",
            post_boundary_text="graph",
            boundary_word_index=1,
            max_chunk_size=1,
            current_chunk_size=1,
            overlap_window=5,
            unresolved_bisections=bisections,
        )
        assert result == 1  # unchanged
        assert len(bisections) == 1
        assert bisections[0].concept_name == "knowledge graph"
        assert bisections[0].concept_confidence == 0.85
        assert bisections[0].boundary_index == 1

    def test_multiple_concepts_records_unresolved_others(self, framework):
        """When multiple concepts span, non-best ones are recorded."""
        mock_extractor = MagicMock()
        concept_low = ConceptNode(
            concept_id="mw_data_model",
            concept_name="data model",
            concept_type="MULTI_WORD",
            confidence=0.5,
        )
        concept_high = ConceptNode(
            concept_id="mw_knowledge_graph",
            concept_name="knowledge graph",
            concept_type="MULTI_WORD",
            confidence=0.9,
        )
        mock_extractor.extract_concepts_regex.return_value = [
            concept_low, concept_high,
        ]
        framework._concept_extractor = mock_extractor

        bisections = []
        # overlap_pre = ["foo", "data"], overlap_post = ["model", "knowledge", "graph", "bar"]
        # boundary_in_overlap = 2
        # "data model" at [1, 3) → spans boundary (1 < 2 < 3) ✓
        # "knowledge graph" at [3, 5) → does NOT span boundary (3 < 2 is false)
        # Actually we need BOTH to span. Let's use a different layout.
        #
        # overlap_pre = ["the", "data", "knowledge"]
        # overlap_post = ["model", "graph", "end"]
        # boundary_in_overlap = 3
        # "data model": need consecutive "data","model" — at [1] and [3]? No, not consecutive.
        #
        # Better: mock returns concepts that both happen to span.
        # Use overlap where both concepts straddle the boundary:
        # overlap_pre = ["data", "knowledge"], overlap_post = ["model", "graph"]
        # boundary_in_overlap = 2
        # "data" at 0, "model" at 2 → not consecutive in overlap
        #
        # Simplest: make the mock return concepts whose tokens DO appear
        # consecutively spanning the boundary.
        # overlap = ["x", "data", "model", "knowledge", "graph", "y"]
        # boundary_in_overlap = 3 (between "model" and "knowledge")
        # "data model" at [1,3) → spans? 1 < 3 < 3 → NO (3 is not < 3)
        #
        # boundary_in_overlap = 2 (between "model" and "knowledge"... wait)
        # Let's be precise:
        # pre = "x data", post = "model knowledge graph y"
        # overlap_pre = ["x", "data"], overlap_post = ["model", "knowledge", "graph", "y"]
        # boundary_in_overlap = 2
        # "data model" at [1, 3) → 1 < 2 < 3 ✓
        # "knowledge graph" at [3, 5) → 3 < 2 is false → NO
        #
        # We need both at the same boundary. That requires overlapping
        # multi-word concepts. Let's use:
        # pre = "x data model", post = "knowledge graph y"
        # overlap_pre = ["x", "data", "model"]
        # overlap_post = ["knowledge", "graph", "y"]
        # boundary_in_overlap = 3
        # "data model" at [1, 3) → 1 < 3 < 3 → NO
        # "model knowledge" at [2, 4) → 2 < 3 < 4 → YES
        # "knowledge graph" at [3, 5) → 3 < 3 → NO
        #
        # Hard to get two concepts spanning the same boundary with real
        # token positions. Use a 3-word concept trick:
        # concept_a = "model knowledge graph" (3 tokens) at [2, 5)
        # concept_b = "data model knowledge" (3 tokens) at [1, 4)
        # Both span boundary_in_overlap=3.
        concept_a = ConceptNode(
            concept_id="mw_a",
            concept_name="model knowledge graph",
            concept_type="MULTI_WORD",
            confidence=0.5,
        )
        concept_b = ConceptNode(
            concept_id="mw_b",
            concept_name="data model knowledge",
            concept_type="MULTI_WORD",
            confidence=0.9,
        )
        mock_extractor.extract_concepts_regex.return_value = [
            concept_a, concept_b,
        ]

        pre = "x data model"
        post = "knowledge graph y"
        # overlap_pre = ["x", "data", "model"], overlap_post = ["knowledge", "graph", "y"]
        # boundary_in_overlap = 3
        # "model knowledge graph" at [2, 5) → 2 < 3 < 5 ✓
        # "data model knowledge" at [1, 4) → 1 < 3 < 4 ✓
        framework._adjust_boundary_for_concept_contiguity(
            pre_boundary_text=pre,
            post_boundary_text=post,
            boundary_word_index=3,
            max_chunk_size=200,
            current_chunk_size=3,
            overlap_window=5,
            unresolved_bisections=bisections,
        )
        # "data model knowledge" (0.9) is the best → resolved.
        # "model knowledge graph" (0.5) is recorded as unresolved.
        assert len(bisections) == 1
        assert bisections[0].concept_name == "model knowledge graph"
        assert bisections[0].concept_confidence == 0.5

    def test_exception_records_nothing(self, framework):
        """If concept extraction raises, no bisections are recorded."""
        mock_extractor = MagicMock()
        mock_extractor.extract_concepts_regex.side_effect = RuntimeError(
            "boom"
        )
        framework._concept_extractor = mock_extractor

        bisections = []
        framework._adjust_boundary_for_concept_contiguity(
            pre_boundary_text="some text here",
            post_boundary_text="more text there",
            boundary_word_index=3,
            max_chunk_size=200,
            current_chunk_size=3,
            overlap_window=5,
            unresolved_bisections=bisections,
        )
        assert bisections == []


class TestPerformPrimaryChunkingBisections:
    """Tests for unresolved bisection accumulation in
    _perform_primary_chunking.

    Requirements: 1.3
    """

    def test_returns_tuple(self, framework):
        """_perform_primary_chunking returns (chunks, bisections_dict)."""
        from src.multimodal_librarian.models.chunking import (
            ChunkingRequirements,
            ContentProfile,
        )
        from src.multimodal_librarian.models.core import ContentType

        profile = ContentProfile(
            content_type=ContentType.GENERAL,
            chunking_requirements=ChunkingRequirements(
                preferred_chunk_size=10,
            ),
        )
        domain_config = framework.get_or_create_domain_config(profile)
        result = framework._perform_primary_chunking(
            "word " * 5, profile, domain_config, document_id="test"
        )
        assert isinstance(result, tuple)
        assert len(result) == 2
        chunks, bisections = result
        assert isinstance(chunks, list)
        assert isinstance(bisections, dict)

    def test_bisection_ids_backfilled(self, framework):
        """chunk_before_id and chunk_after_id are filled after chunking."""
        from src.multimodal_librarian.models.chunking import (
            ChunkingRequirements,
            ContentProfile,
        )
        from src.multimodal_librarian.models.core import ContentType

        # Mock concept extractor to force an unresolved bisection
        mock_extractor = MagicMock()
        concept = ConceptNode(
            concept_id="mw_knowledge_graph",
            concept_name="knowledge graph",
            concept_type="MULTI_WORD",
            confidence=0.9,
        )
        mock_extractor.extract_concepts_regex.return_value = [concept]
        framework._concept_extractor = mock_extractor

        # Build text where "knowledge graph" spans a boundary
        # and both shifts fail (tight max_chunk_size)
        profile = ContentProfile(
            content_type=ContentType.GENERAL,
            chunking_requirements=ChunkingRequirements(
                preferred_chunk_size=3,
                max_chunk_size=3,
            ),
        )
        domain_config = framework.get_or_create_domain_config(profile)
        text = "we study the knowledge graph in detail today now end"
        chunks, bisections = framework._perform_primary_chunking(
            text, profile, domain_config, document_id="test"
        )

        # If any bisections were recorded, verify IDs are filled
        for boundary_idx, bis_list in bisections.items():
            for bis in bis_list:
                if boundary_idx < len(chunks) - 1:
                    assert bis.chunk_before_id != ""
                    assert bis.chunk_after_id != ""
                    assert bis.chunk_before_id == chunks[boundary_idx].id
                    assert bis.chunk_after_id == chunks[boundary_idx + 1].id
