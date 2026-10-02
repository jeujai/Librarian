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


class TestSentenceReanchorAfterConceptShift:
    """A concept-protection shift snaps to the nearest sentence boundary so the
    split lands on a sentence end rather than mid-sentence.

    Requirements: 3.1, 3.2, 3.4 (sentence + concept contiguity together)
    """

    def _single_concept_extractor(self, framework, name, confidence=0.9):
        """Mock the extractor to return exactly one multi-word concept."""
        mock_extractor = MagicMock()
        mock_extractor.extract_concepts_regex.return_value = [
            ConceptNode(
                concept_id=f"mw_{name.replace(' ', '_')}",
                concept_name=name,
                concept_type="MULTI_WORD",
                confidence=confidence,
            )
        ]
        framework._concept_extractor = mock_extractor
        framework._extract_domain_concepts = MagicMock(return_value=[])

    def test_forward_shift_snaps_to_sentence_end(self, framework):
        """Shifting past a concept also lands on the following sentence end."""
        self._single_concept_extractor(framework, "knowledge graph")

        pre = "we study the knowledge"
        post = "graph in detail. Then we move"
        result = framework._adjust_boundary_for_concept_contiguity(
            pre_boundary_text=pre,
            post_boundary_text=post,
            boundary_word_index=4,
            max_chunk_size=200,
            current_chunk_size=4,
            overlap_window=5,
        )
        # "knowledge graph" spans [3, 5); the raw forward shift would stop at
        # 5, but the sentence ends at "detail." (overlap word 6) so the
        # boundary snaps to 7 to end the sentence cleanly.
        assert result == 7

    def test_backward_shift_snaps_to_sentence_end(self, framework):
        """A backward shift lands on the sentence end before the concept start."""
        self._single_concept_extractor(framework, "knowledge graph")

        pre = "Alpha done. Beta knowledge"
        post = "graph gamma"
        result = framework._adjust_boundary_for_concept_contiguity(
            pre_boundary_text=pre,
            post_boundary_text=post,
            boundary_word_index=4,
            max_chunk_size=4,       # forward shift would exceed the cap
            current_chunk_size=4,
            overlap_window=5,
        )
        # Forward shift fails (4 + 1 > 4).  Raw backward shift would stop at
        # the concept start (3), but the sentence ends at "done." (word 2), so
        # the boundary snaps back to 2.
        assert result == 2

    def test_forward_shift_snaps_to_newline_list_boundary(self, framework):
        """A forward shift anchors to a newline list marker, not just a period."""
        self._single_concept_extractor(framework, "knowledge graph")

        pre = "we study the knowledge"
        post = "graph in detail\n- Then we move on"
        result = framework._adjust_boundary_for_concept_contiguity(
            pre_boundary_text=pre,
            post_boundary_text=post,
            boundary_word_index=4,
            max_chunk_size=200,
            current_chunk_size=4,
            overlap_window=20,
        )
        # "knowledge graph" spans [3, 5).  The bulleted item starts after
        # "detail" (overlap word 6); with newlines preserved the boundary
        # snaps to 7 (before the bullet) instead of stopping at the raw
        # concept edge (5).
        assert result == 7

    def test_no_sentence_end_keeps_concept_edge(self, framework):
        """With no punctuation in the window, the boundary stays at the edge."""
        self._single_concept_extractor(framework, "knowledge graph")

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
        # No sentence boundary exists, so the forward shift stops at the
        # concept edge (5) as before.
        assert result == 5


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

    def test_overlapping_concepts_resolved_iteratively(self, framework):
        """Overlapping concepts that both span the boundary are each kept
        whole — the boundary shifts past them in turn."""
        mock_extractor = MagicMock()
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
        framework._concept_extractor = mock_extractor

        bisections = []
        pre = "x data model"
        post = "knowledge graph y"
        # overlap = ["x","data","model","knowledge","graph","y"], boundary 3.
        # "data model knowledge" spans [1,4) and "model knowledge graph"
        # spans [2,5); both straddle the boundary.
        result = framework._adjust_boundary_for_concept_contiguity(
            pre_boundary_text=pre,
            post_boundary_text=post,
            boundary_word_index=3,
            max_chunk_size=200,
            current_chunk_size=3,
            overlap_window=5,
            unresolved_bisections=bisections,
        )
        # The boundary shifts past the 0.9 concept (to 4), then past the 0.5
        # concept (to 5), keeping "data model knowledge graph" whole.  Neither
        # concept is left bisected, so nothing is recorded as unresolved.
        assert result == 5
        assert bisections == []

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


class TestKnownConceptPrefetch:
    """Regression tests for the prefetched known-concept vocabulary path.

    ``known_concept_names`` holds vetted multi-word names (UMLS + seed/
    canonical/frozen librarian concepts) that the boundary-contiguity check
    keeps whole even when the regex/spaCy sources miss them.
    """

    def test_match_known_concepts_returns_vetted_concepts(self, framework):
        """Vetted multi-word names present in text yield KNOWN_CONCEPT nodes."""
        framework.known_concept_names = {
            "hepatitis b surface antigen",
            "work restrictions",
        }
        concepts = framework._match_known_concepts(
            "tests for hepatitis b surface antigen and work restrictions"
        )
        assert {c.concept_name for c in concepts} == {
            "hepatitis b surface antigen",
            "work restrictions",
        }
        for c in concepts:
            assert c.concept_type == "KNOWN_CONCEPT"
            assert c.confidence == 0.92
            assert c.concept_id == f"public:{c.concept_name}"

    def test_match_known_concepts_empty_when_no_vocab(self, framework):
        """No prefetched vocabulary yields no matches."""
        assert framework.known_concept_names == set()
        assert framework._match_known_concepts("hepatitis b surface antigen") == []

    def test_match_known_concepts_beyond_five_grams(self, framework):
        """A vetted concept longer than five words is still matched."""
        framework.known_concept_names = {
            "attention deficit hyperactivity disorder combined type",
        }
        concepts = framework._match_known_concepts(
            "diagnosis of attention deficit hyperactivity disorder "
            "combined type today"
        )
        assert {c.concept_name for c in concepts} == {
            "attention deficit hyperactivity disorder combined type",
        }

    @pytest.mark.parametrize(
        "token, expected",
        [
            ("procedure", "procedure"),
            ("procedures", "procedure"),
            ("guideline", "guideline"),
            ("guidelines", "guideline"),
            ("restriction", "restriction"),
            ("restrictions", "restriction"),
            ("activity", "activity"),
            ("activities", "activity"),
            ("category", "category"),
            ("categories", "category"),
            ("process", "process"),
            ("processes", "process"),
            ("box", "box"),
            ("boxes", "box"),
            # Invariant plurals / short words are left alone.
            ("analysis", "analysis"),
            ("status", "status"),
            ("mass", "mass"),
            ("iii", "iii"),
        ],
    )
    def test_singularize_token(self, framework, token, expected):
        assert framework._singularize_token(token) == expected

    def test_match_known_concepts_pluralization_robust(self, framework):
        """A singular surface form still matches its plural in the text."""
        framework.known_concept_names = {"exposure prone procedure"}
        concepts = framework._match_known_concepts(
            "the exposure prone procedures require review"
        )
        assert {c.concept_name for c in concepts} == {
            "exposure prone procedures",
        }
        assert concepts[0].concept_type == "KNOWN_CONCEPT"

    def test_match_known_concepts_ies_plural(self, framework):
        """'ies' plurals (activities) still match their singular form."""
        framework.known_concept_names = {
            "category iii",
            "patient-care activity",
        }
        concepts = framework._match_known_concepts(
            "category III and patient-care activities"
        )
        assert {c.concept_name for c in concepts} == {
            "category iii",
            "patient-care activities",
        }

    def test_match_known_concepts_hyphen_insensitive(self, framework):
        """Hyphenated and unhyphenated forms collapse to one key."""
        framework.known_concept_names = {"exposure-prone procedures"}
        concepts = framework._match_known_concepts(
            "the exposure prone procedure is documented"
        )
        assert {c.concept_name for c in concepts} == {
            "exposure prone procedure",
        }

    def test_match_known_concepts_hyphen_and_plural_together(self, framework):
        """A hyphenated plural name matches an unhyphenated singular text."""
        framework.known_concept_names = {"exposure prone procedure"}
        concepts = framework._match_known_concepts(
            "the exposure-prone procedures are documented"
        )
        assert {c.concept_name for c in concepts} == {
            "exposure-prone procedures",
        }

    def test_known_concept_protects_boundary(self, framework):
        """A prefetched concept spanning the boundary shifts it forward,
        even when regex and spaCy sources return nothing."""
        mock_extractor = MagicMock()
        mock_extractor.extract_concepts_regex.return_value = []
        framework._concept_extractor = mock_extractor
        framework._extract_domain_concepts = MagicMock(return_value=[])
        framework.known_concept_names = {"hepatitis b surface antigen"}

        pre = "we study the hepatitis b surface"
        post = "antigen in detail today now"
        result = framework._adjust_boundary_for_concept_contiguity(
            pre_boundary_text=pre,
            post_boundary_text=post,
            boundary_word_index=5,
            max_chunk_size=200,
            current_chunk_size=5,
            overlap_window=5,
        )
        # "hepatitis b surface antigen" spans [2, 6) in the overlap; the
        # boundary (index 5) is inside, so it shifts forward by one word.
        assert result == 6

    def test_known_concept_kept_whole_across_hard_split(self, framework):
        """A concept spanning the no-boundary hard-split is kept whole by
        pulling lookahead words into the current chunk."""
        from src.multimodal_librarian.models.chunking import (
            ChunkingRequirements,
            ContentProfile,
        )
        from src.multimodal_librarian.models.core import ContentType

        # Isolate the known-concept source: no regex, no spaCy.
        mock_extractor = MagicMock()
        mock_extractor.extract_concepts_regex.return_value = []
        framework._concept_extractor = mock_extractor
        framework._extract_domain_concepts = MagicMock(return_value=[])
        framework.known_concept_names = {"surface antigen positivity"}

        profile = ContentProfile(
            content_type=ContentType.GENERAL,
            chunking_requirements=ChunkingRequirements(
                preferred_chunk_size=5,
                max_chunk_size=10,
            ),
        )
        domain_config = framework.get_or_create_domain_config(profile)

        # No punctuation / newlines, so _find_semantic_boundary returns 0 and
        # the hard-split branch runs.  The buffer ends at "surface" (word 4)
        # with "antigen positivity" in the lookahead.
        text = "a b c d surface antigen positivity x y z"
        chunks, _ = framework._perform_primary_chunking(
            text, profile, domain_config, document_id="test"
        )

        contents = [c.content for c in chunks]
        assert "a b c d surface antigen positivity" in contents
