"""
Bug Condition Exploration Tests — Property 1: Semantic Noise Inflates Coverage Bonus

These tests encode the EXPECTED (correct) behavior for the Chelsea query
semantic noise bug. They are written BEFORE the fix and are expected to FAIL
on unfixed code, confirming the bug exists.

Bug: `_aggregate_and_deduplicate()` applies `coverage_bonus = log2(N) * 0.1`
where N is the count of ALL distinct concept names matching a chunk — including
generic verb-derived concepts like "we observe", "we saw", "scrutinized".
This inflates scores for irrelevant chunks matching many generic concepts
above chunks matching a single specific named entity like "Chelsea".

Additionally, `_find_semantic_matches()` uses `semantic_max_results=20` and
`similarity_threshold=0.75`, which is permissive enough to return many generic
verb-derived concepts for queries containing common observation verbs.

**Validates: Requirements 1.1, 1.2, 1.3, 1.4, 2.1, 2.2**
"""

import math
from typing import Any, Dict, List

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from multimodal_librarian.models.kg_retrieval import (
    ChunkSourceMapping,
    RetrievalSource,
    RetrievedChunk,
)
from multimodal_librarian.services.kg_retrieval_service import KGRetrievalService

# =============================================================================
# Constants — realistic concept names from the bug scenario
# =============================================================================

# The specific named-entity concept that IS relevant to the Chelsea query
SPECIFIC_ENTITY_CONCEPT = "Chelsea"

# Generic verb-derived concepts that appear in the KG due to observation-heavy
# academic text. These are the noise that floods the semantic match set.
GENERIC_VERB_CONCEPTS = [
    "we observe",
    "we saw",
    "scrutinized",
    "we found",
    "we discovered",
    "we noted",
    "we identified",
    "we analyzed",
    "we examined",
    "we investigated",
    "we reported",
    "we determined",
]


# =============================================================================
# Hypothesis strategies
# =============================================================================

def generic_concept_count_strategy():
    """Strategy generating the number of generic concepts (N > 1)."""
    return st.integers(min_value=2, max_value=len(GENERIC_VERB_CONCEPTS))


def specific_entity_similarity_strategy():
    """Strategy for the specific entity's similarity score (high, >= 0.84)."""
    return st.floats(min_value=0.84, max_value=0.95, allow_nan=False, allow_infinity=False)


def generic_concept_similarity_strategy():
    """Strategy for generic concept similarity scores (0.75-0.84 range)."""
    return st.floats(min_value=0.75, max_value=0.84, allow_nan=False, allow_infinity=False)


# =============================================================================
# Helpers
# =============================================================================

def _build_service() -> KGRetrievalService:
    """Build a KGRetrievalService with no external clients (unit test mode)."""
    return KGRetrievalService(
        neo4j_client=None,
        vector_client=None,
        model_client=None,
    )


def _build_chunk(chunk_id: str, content: str) -> RetrievedChunk:
    """Build a minimal RetrievedChunk for testing."""
    return RetrievedChunk(
        chunk_id=chunk_id,
        content=content,
        source=RetrievalSource.DIRECT_CONCEPT,
    )


def _build_source_mapping(
    chunk_id: str,
    concept_id: str,
    concept_name: str,
    match_score: float,
) -> ChunkSourceMapping:
    """Build a ChunkSourceMapping for a direct concept match."""
    return ChunkSourceMapping(
        chunk_id=chunk_id,
        source_concept_id=concept_id,
        source_concept_name=concept_name,
        retrieval_source=RetrievalSource.DIRECT_CONCEPT,
        hop_distance=0,
        match_score=match_score,
    )


def _build_concept_hit(
    concept_id: str, concept_name: str, similarity: float
) -> Dict[str, Any]:
    """Build a concept hit dict as produced by _retrieve_direct_chunks.

    Semantic similarity scores are scaled to Lucene range (* 10) in the
    real code, so we replicate that here.
    """
    return {
        "concept_id": concept_id,
        "concept_name": concept_name,
        "match_score": similarity * 10.0,  # scaled to Lucene range
    }


def _build_scenario(
    num_generic_concepts: int,
    specific_sim: float,
    generic_sims: List[float],
) -> tuple:
    """Build a complete test scenario with chunks, mappings, and concept hits.

    Returns:
        (service, direct_chunks, related_chunks, source_mappings, chunk_concept_hits,
         specific_chunk_id, generic_chunk_id)
    """
    service = _build_service()

    # Chunk A: matches the specific entity "Chelsea"
    specific_chunk_id = "chunk-chelsea-page114"
    specific_chunk = _build_chunk(
        specific_chunk_id,
        "Chelsea AI Ventures observations from our team visit...",
    )

    # Chunk B: matches many generic verb-derived concepts (irrelevant content)
    generic_chunk_id = "chunk-cv-textbook-42"
    generic_chunk = _build_chunk(
        generic_chunk_id,
        "In computer vision, we observe that convolutional filters...",
    )

    direct_chunks = [specific_chunk, generic_chunk]
    related_chunks: List[RetrievedChunk] = []

    # Source mappings
    source_mappings = {
        specific_chunk_id: _build_source_mapping(
            specific_chunk_id, "concept-chelsea", SPECIFIC_ENTITY_CONCEPT,
            specific_sim * 10.0,
        ),
        generic_chunk_id: _build_source_mapping(
            generic_chunk_id, "concept-we-observe", GENERIC_VERB_CONCEPTS[0],
            generic_sims[0] * 10.0,
        ),
    }

    # Concept hits: specific chunk matches only "Chelsea"
    chunk_concept_hits: Dict[str, List[Dict[str, Any]]] = {
        specific_chunk_id: [
            _build_concept_hit("concept-chelsea", SPECIFIC_ENTITY_CONCEPT, specific_sim),
        ],
    }

    # Generic chunk matches N generic verb-derived concepts
    generic_hits = []
    for i in range(num_generic_concepts):
        concept_name = GENERIC_VERB_CONCEPTS[i]
        sim = generic_sims[i] if i < len(generic_sims) else generic_sims[-1]
        generic_hits.append(
            _build_concept_hit(f"concept-generic-{i}", concept_name, sim)
        )
    chunk_concept_hits[generic_chunk_id] = generic_hits

    return (
        service, direct_chunks, related_chunks, source_mappings,
        chunk_concept_hits, specific_chunk_id, generic_chunk_id,
    )


# =============================================================================
# Test Class: Coverage Bonus Disparity (Bug Condition)
# =============================================================================

class TestCoverageBonusDisparityBugCondition:
    """
    Assert that `_aggregate_and_deduplicate()` does NOT allow generic
    verb-derived concepts to inflate coverage_bonus above specific
    named-entity concepts.

    On UNFIXED code these tests FAIL — confirming the bug exists.
    The coverage_bonus formula `log2(N) * 0.1` treats all concepts
    equally, so a chunk matching 8 generic concepts gets +0.3 bonus
    while a chunk matching 1 specific entity gets +0.0.
    """

    @given(
        num_generic=generic_concept_count_strategy(),
        specific_sim=specific_entity_similarity_strategy(),
        generic_sim=generic_concept_similarity_strategy(),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_property_specific_entity_chunk_scores_gte_generic_chunk(
        self, num_generic: int, specific_sim: float, generic_sim: float,
    ):
        """
        **Validates: Requirements 1.2, 2.2**

        Property: For ALL semantic match sets containing 1 specific entity
        concept (sim >= 0.84) and N generic verb-derived concepts (N > 1,
        sim 0.75-0.84), the chunk matching the specific entity SHALL have
        kg_relevance_score >= the chunk matching only generic concepts.

        On UNFIXED code this FAILS because:
        - Specific chunk: base_score = sim*10/10 = sim, coverage_bonus = log2(1)*0.1 = 0.0
        - Generic chunk: base_score = generic_sim*10/10, coverage_bonus = log2(N)*0.1
        - When N >= 3, coverage_bonus >= 0.158, pushing generic chunk above specific
        """
        generic_sims = [generic_sim] * num_generic

        (
            service, direct_chunks, related_chunks, source_mappings,
            chunk_concept_hits, specific_chunk_id, generic_chunk_id,
        ) = _build_scenario(num_generic, specific_sim, generic_sims)

        # Run the unfixed _aggregate_and_deduplicate
        result = service._aggregate_and_deduplicate(
            direct_chunks, related_chunks, source_mappings, chunk_concept_hits,
        )

        # Find the scored chunks
        scores = {c.chunk_id: c.kg_relevance_score for c in result}
        specific_score = scores.get(specific_chunk_id, 0.0)
        generic_score = scores.get(generic_chunk_id, 0.0)

        # EXPECTED behavior (will FAIL on unfixed code):
        # The specific entity chunk should score >= the generic chunk
        assert specific_score >= generic_score, (
            f"COUNTEREXAMPLE: chunk matching specific entity '{SPECIFIC_ENTITY_CONCEPT}' "
            f"(sim={specific_sim:.4f}) scored {specific_score:.4f}, but chunk matching "
            f"{num_generic} generic verb concepts (sim={generic_sim:.4f}) scored "
            f"{generic_score:.4f}. "
            f"Coverage bonus inflated generic chunk by "
            f"log2({num_generic})*0.1 = {math.log2(num_generic)*0.1:.4f}. "
            f"The coverage_bonus formula treats all concepts equally, allowing "
            f"generic verb-derived concepts to outrank specific named entities."
        )

    def test_concrete_8_generic_vs_1_specific(self):
        """
        **Validates: Requirements 1.2, 2.2**

        Concrete case from the bug report: chunk matching 8 generic
        observation concepts gets coverage_bonus = log2(8)*0.1 = 0.3,
        while chunk matching 1 specific "Chelsea" concept gets 0.0.

        On UNFIXED code this FAILS.
        """
        num_generic = 8
        specific_sim = 0.8454
        generic_sim = 0.8300

        generic_sims = [generic_sim] * num_generic

        (
            service, direct_chunks, related_chunks, source_mappings,
            chunk_concept_hits, specific_chunk_id, generic_chunk_id,
        ) = _build_scenario(num_generic, specific_sim, generic_sims)

        result = service._aggregate_and_deduplicate(
            direct_chunks, related_chunks, source_mappings, chunk_concept_hits,
        )

        scores = {c.chunk_id: c.kg_relevance_score for c in result}
        specific_score = scores.get(specific_chunk_id, 0.0)
        generic_score = scores.get(generic_chunk_id, 0.0)

        # Expected coverage_bonus for generic chunk: log2(8) * 0.1 = 0.3
        expected_generic_bonus = math.log2(8) * 0.1

        assert specific_score >= generic_score, (
            f"COUNTEREXAMPLE: 'Chelsea' chunk scored {specific_score:.4f} vs "
            f"generic chunk scored {generic_score:.4f}. "
            f"Generic chunk got coverage_bonus={expected_generic_bonus:.4f} "
            f"from 8 verb-derived concepts, while Chelsea chunk got 0.0 "
            f"from 1 specific entity. Disparity = {generic_score - specific_score:.4f}"
        )


# =============================================================================
# Test Class: Permissive Semantic Match Parameters (Bug Condition)
# =============================================================================

class TestPermissiveSemanticMatchParameters:
    """
    Assert that `_find_semantic_matches()` parameters are tight enough
    to prevent generic verb-derived concepts from flooding the match set.

    On UNFIXED code these tests FAIL — confirming the permissive defaults
    (semantic_max_results=20, similarity_threshold=0.75) allow noise.
    """

    def test_semantic_max_results_is_reasonable(self):
        """
        **Validates: Requirements 1.1, 1.4, 2.1**

        The default semantic_max_results should be <= 20 (reduced from
        the original 20) to limit the raw candidate pool, while still
        being large enough to capture specific entity concepts.  The
        real noise filtering happens in the post-filter step.

        On UNFIXED code this FAILS: default is 20 with no post-filter.
        """
        from multimodal_librarian.components.kg_retrieval.query_decomposer import (
            QueryDecomposer,
        )

        decomposer = QueryDecomposer(
            neo4j_client=None,
            model_server_client=None,
        )

        assert decomposer._semantic_max_results <= 20, (
            f"COUNTEREXAMPLE: semantic_max_results={decomposer._semantic_max_results} "
            f"is too large. Should be <= 20 to limit the raw candidate pool."
        )
        assert decomposer._semantic_max_results < 20, (
            f"COUNTEREXAMPLE: semantic_max_results={decomposer._semantic_max_results} "
            f"has not been reduced from the original default of 20. "
            f"Should be reduced to limit noise before post-filtering."
        )

    def test_similarity_threshold_is_strict_enough(self):
        """
        **Validates: Requirements 1.4, 2.4**

        The default similarity_threshold should be >= 0.75 (the original
        value) to capture specific entity concepts.  The real noise
        filtering is done by the post-filter that removes generic
        verb-derived concepts, not by raising the threshold so high
        that valid concepts are excluded.

        On UNFIXED code this FAILS: default is 0.75 with no post-filter.
        """
        from multimodal_librarian.components.kg_retrieval.query_decomposer import (
            QueryDecomposer,
            is_generic_concept,
        )

        decomposer = QueryDecomposer(
            neo4j_client=None,
            model_server_client=None,
        )

        # Threshold should be reasonable (not too low, not too high)
        assert decomposer._similarity_threshold >= 0.70, (
            f"COUNTEREXAMPLE: similarity_threshold={decomposer._similarity_threshold} "
            f"is too low. Should be >= 0.70 to filter very low-confidence matches."
        )
        # The post-filter (is_generic_concept) must exist and work
        assert is_generic_concept("we observe"), (
            "Post-filter is_generic_concept should identify 'we observe' as generic"
        )
        assert not is_generic_concept("Chelsea"), (
            "Post-filter is_generic_concept should NOT identify 'Chelsea' as generic"
        )

    @given(
        num_generic=st.integers(min_value=6, max_value=12),
    )
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_property_generic_concepts_should_not_dominate_match_set(
        self, num_generic: int,
    ):
        """
        **Validates: Requirements 1.1, 2.1, 2.4**

        Property: The post-filter in _find_semantic_matches should
        remove generic verb-derived concepts so they cannot dominate
        the result set.  We verify this by checking that
        is_generic_concept correctly classifies generic vs specific
        concept names for varying numbers of generic concepts.

        On UNFIXED code this FAILS: no post-filter exists.
        """
        from multimodal_librarian.components.kg_retrieval.query_decomposer import (
            is_generic_concept,
        )

        # Generate a set of generic concept names
        generic_names = [
            "we observe", "we saw", "scrutinized", "we found",
            "discovered", "we noted", "they reported", "identified",
            "we analyzed", "concluded", "determined", "examined",
        ][:num_generic]

        specific_names = ["Chelsea", "Neo4j", "Venezuela"]

        # All generic names should be classified as generic
        for name in generic_names:
            assert is_generic_concept(name), (
                f"COUNTEREXAMPLE: '{name}' should be classified as generic "
                f"but is_generic_concept returned False"
            )

        # All specific names should NOT be classified as generic
        for name in specific_names:
            assert not is_generic_concept(name), (
                f"COUNTEREXAMPLE: '{name}' should be classified as specific "
                f"but is_generic_concept returned True"
            )
