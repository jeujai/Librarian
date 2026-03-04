"""
Tests for QueryDecomposition round-trip serialization.

Verifies that to_dict / from_dict preserves match_type and all other
fields in concept_matches.

Validates: Requirements 4.3
"""

from multimodal_librarian.models.kg_retrieval import QueryDecomposition


class TestQueryDecompositionRoundTrip:
    """Verify to_dict / from_dict preserves match_type in concept_matches."""

    def _make_decomposition(self, concept_matches):
        return QueryDecomposition(
            original_query="test query",
            entities=["entity1"],
            actions=["observed"],
            subjects=["team"],
            concept_matches=concept_matches,
            has_kg_matches=bool(concept_matches),
        )

    def test_round_trip_preserves_lexical_match_type(self):
        """match_type='lexical' survives to_dict -> from_dict."""
        matches = [
            {
                "concept_id": "c1",
                "name": "Concept One",
                "type": "ENTITY",
                "confidence": 0.9,
                "source_document": "doc1",
                "source_chunks": "chunk1,chunk2",
                "match_type": "lexical",
            }
        ]
        original = self._make_decomposition(matches)
        restored = QueryDecomposition.from_dict(original.to_dict())

        assert restored.concept_matches == original.concept_matches
        assert restored.concept_matches[0]["match_type"] == "lexical"

    def test_round_trip_preserves_semantic_match_type(self):
        """match_type='semantic' survives to_dict -> from_dict."""
        matches = [
            {
                "concept_id": "c2",
                "name": "Concept Two",
                "type": "TOPIC",
                "confidence": 0.85,
                "source_document": "doc2",
                "source_chunks": "chunk3",
                "match_type": "semantic",
                "similarity_score": 0.82,
            }
        ]
        original = self._make_decomposition(matches)
        restored = QueryDecomposition.from_dict(original.to_dict())

        assert restored.concept_matches == original.concept_matches
        assert restored.concept_matches[0]["match_type"] == "semantic"
        assert restored.concept_matches[0]["similarity_score"] == 0.82

    def test_round_trip_preserves_both_match_type(self):
        """match_type='both' survives to_dict -> from_dict."""
        matches = [
            {
                "concept_id": "c3",
                "name": "Concept Three",
                "type": "ENTITY",
                "confidence": 0.95,
                "source_document": "doc1",
                "source_chunks": "chunk1",
                "match_type": "both",
                "similarity_score": 0.91,
            }
        ]
        original = self._make_decomposition(matches)
        restored = QueryDecomposition.from_dict(original.to_dict())

        assert restored.concept_matches == original.concept_matches
        assert restored.concept_matches[0]["match_type"] == "both"

    def test_round_trip_preserves_mixed_match_types(self):
        """A list with all three match_type values round-trips correctly."""
        matches = [
            {"concept_id": "c1", "name": "A", "source_chunks": "s1", "match_type": "lexical"},
            {"concept_id": "c2", "name": "B", "source_chunks": "s2", "match_type": "semantic", "similarity_score": 0.75},
            {"concept_id": "c3", "name": "C", "source_chunks": "s3", "match_type": "both", "similarity_score": 0.88},
        ]
        original = self._make_decomposition(matches)
        restored = QueryDecomposition.from_dict(original.to_dict())

        assert restored.concept_matches == original.concept_matches
        for orig, rest in zip(original.concept_matches, restored.concept_matches):
            assert orig["match_type"] == rest["match_type"]

    def test_round_trip_preserves_all_top_level_fields(self):
        """All QueryDecomposition fields survive the round trip."""
        original = self._make_decomposition([
            {"concept_id": "c1", "name": "X", "source_chunks": "s1", "match_type": "semantic"},
        ])
        restored = QueryDecomposition.from_dict(original.to_dict())

        assert restored.original_query == original.original_query
        assert restored.entities == original.entities
        assert restored.actions == original.actions
        assert restored.subjects == original.subjects
        assert restored.has_kg_matches == original.has_kg_matches
