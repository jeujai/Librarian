"""
Preservation Property Tests — Property 2: Non-Noisy Query Behavior Unchanged

These tests capture the CURRENT (correct) behavior of the unfixed code for
inputs that do NOT trigger the bug condition. They must PASS on unfixed code,
confirming the baseline behavior we need to preserve after the fix.

Preservation scope:
- Queries with only specific named entities (no generic verb phrases)
- Multi-concept coverage bonus for genuinely distinct concepts
- Lexical fallback when semantic matching is unavailable
- has_kg_matches=False when no concepts match
- Related chunk hop-distance-decayed scoring capped at _max_related_chunks

**Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5**
"""

import math
from typing import Any, Dict, List

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from multimodal_librarian.components.kg_retrieval.query_decomposer import (
    QueryDecomposer,
)
from multimodal_librarian.models.kg_retrieval import (
    ChunkSourceMapping,
    QueryDecomposition,
    RetrievalSource,
    RetrievedChunk,
)
from multimodal_librarian.services.kg_retrieval_service import KGRetrievalService

# =============================================================================
# Constants — specific named-entity concepts (NO generic verb phrases)
# =============================================================================

SPECIFIC_ENTITY_CONCEPTS = [
    "Chelsea",
    "Venezuela",
    "Neo4j",
    "GraphRAG",
    "Kubernetes",
    "PostgreSQL",
    "Amazon Web Services",
    "TensorFlow",
    "PyTorch",
    "Elasticsearch",
]


# =============================================================================
# Hypothesis strategies
# =============================================================================

def specific_concept_names_strategy(min_size=1, max_size=5):
    """Strategy generating lists of specific named-entity concept names."""
    return st.lists(
        st.sampled_from(SPECIFIC_ENTITY_CONCEPTS),
        min_size=min_size,
        max_size=max_size,
        unique=True,
    )


def similarity_score_strategy():
    """Strategy for similarity scores in the realistic range (0.80-0.95)."""
    return st.floats(
        min_value=0.80,
        max_value=0.95,
        allow_nan=False,
        allow_infinity=False,
    )


def hop_distance_strategy():
    """Strategy for hop distances (1-3 hops)."""
    return st.integers(min_value=1, max_value=3)


def hop_decay_strategy():
    """Strategy for hop_distance_decay factor."""
    return st.floats(
        min_value=0.3,
        max_value=0.9,
        allow_nan=False,
        allow_infinity=False,
    )


def max_related_chunks_strategy():
    """Strategy for max_related_chunks cap."""
    return st.integers(min_value=5, max_value=100)


# =============================================================================
# Helpers
# =============================================================================

def _build_service(
    hop_distance_decay: float = 0.5,
    max_related_chunks: int = 50,
) -> KGRetrievalService:
    """Build a KGRetrievalService with no external clients."""
    return KGRetrievalService(
        neo4j_client=None,
        vector_client=None,
        model_client=None,
        hop_distance_decay=hop_distance_decay,
        max_related_chunks=max_related_chunks,
    )


def _build_chunk(
    chunk_id: str,
    content: str,
    source: RetrievalSource = RetrievalSource.DIRECT_CONCEPT,
) -> RetrievedChunk:
    """Build a minimal RetrievedChunk for testing."""
    return RetrievedChunk(
        chunk_id=chunk_id,
        content=content,
        source=source,
    )


def _build_source_mapping(
    chunk_id: str,
    concept_id: str,
    concept_name: str,
    match_score: float,
    hop_distance: int = 0,
    source: RetrievalSource = RetrievalSource.DIRECT_CONCEPT,
) -> ChunkSourceMapping:
    """Build a ChunkSourceMapping."""
    return ChunkSourceMapping(
        chunk_id=chunk_id,
        source_concept_id=concept_id,
        source_concept_name=concept_name,
        retrieval_source=source,
        hop_distance=hop_distance,
        match_score=match_score,
    )


def _build_concept_hit(
    concept_id: str,
    concept_name: str,
    similarity: float,
) -> Dict[str, Any]:
    """Build a concept hit dict with Lucene-scaled match_score."""
    return {
        "concept_id": concept_id,
        "concept_name": concept_name,
        "match_score": similarity * 10.0,
    }


# =============================================================================
# Test Class: Multi-Concept Coverage Bonus Preservation
# =============================================================================

class TestMultiConceptCoveragePreservation:
    """
    Verify that _aggregate_and_deduplicate() applies the correct
    coverage_bonus formula for chunks matching genuinely distinct
    specific named-entity concepts (no generic verb phrases).

    On UNFIXED code these tests PASS — confirming baseline behavior.

    **Validates: Requirements 3.2, 3.5**
    """

    @given(
        concept_names=specific_concept_names_strategy(
            min_size=1, max_size=5,
        ),
        base_sim=similarity_score_strategy(),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_property_coverage_bonus_formula_for_specific_concepts(
        self,
        concept_names: List[str],
        base_sim: float,
    ):
        """
        Property: For all chunk-concept-hit sets where all matched
        concepts are genuinely distinct specific named entities,
        _aggregate_and_deduplicate() applies:
            coverage_bonus = log2(num_concepts) * 0.1

        This must hold for 1..5 distinct specific concepts.
        """
        service = _build_service()
        num_concepts = len(concept_names)

        chunk_id = "chunk-multi-concept"
        chunk = _build_chunk(chunk_id, "Content about multiple entities")
        direct_chunks = [chunk]
        related_chunks: List[RetrievedChunk] = []

        # Build concept hits — all specific named entities
        concept_hits: List[Dict[str, Any]] = []
        for i, name in enumerate(concept_names):
            concept_hits.append(
                _build_concept_hit(f"concept-{i}", name, base_sim)
            )

        chunk_concept_hits = {chunk_id: concept_hits}

        source_mappings = {
            chunk_id: _build_source_mapping(
                chunk_id,
                "concept-0",
                concept_names[0],
                base_sim * 10.0,
            ),
        }

        result = service._aggregate_and_deduplicate(
            direct_chunks,
            related_chunks,
            source_mappings,
            chunk_concept_hits,
        )

        assert len(result) == 1
        scored_chunk = result[0]

        # Expected: base_score = sim*10/10 = sim (clamped to [0.1, 1.0])
        expected_base = min(1.0, max(0.1, base_sim))
        expected_bonus = math.log2(max(1, num_concepts)) * 0.1
        expected_score = min(1.0, expected_base + expected_bonus)

        assert abs(scored_chunk.kg_relevance_score - expected_score) < 1e-9, (
            f"Coverage bonus mismatch for {num_concepts} specific concepts. "
            f"Expected score={expected_score:.6f} "
            f"(base={expected_base:.6f} + bonus={expected_bonus:.6f}), "
            f"got {scored_chunk.kg_relevance_score:.6f}"
        )

    def test_concrete_two_specific_concepts_coverage_bonus(self):
        """
        Concrete case: chunk matching 2 genuinely distinct concepts
        ("Chelsea" + "Venezuela") gets coverage_bonus = log2(2)*0.1 = 0.1.

        **Validates: Requirement 3.2**
        """
        service = _build_service()

        chunk_id = "chunk-chelsea-venezuela"
        chunk = _build_chunk(
            chunk_id,
            "Comparing Chelsea and Venezuela observations...",
        )

        sim_chelsea = 0.8454
        sim_venezuela = 0.8700

        concept_hits = [
            _build_concept_hit("c-chelsea", "Chelsea", sim_chelsea),
            _build_concept_hit("c-venezuela", "Venezuela", sim_venezuela),
        ]

        source_mappings = {
            chunk_id: _build_source_mapping(
                chunk_id, "c-chelsea", "Chelsea", sim_chelsea * 10.0,
            ),
        }

        result = service._aggregate_and_deduplicate(
            [chunk], [], source_mappings, {chunk_id: concept_hits},
        )

        assert len(result) == 1
        scored = result[0]

        # base_score = max(0.8454, 0.8700) = 0.8700
        expected_base = 0.8700
        # coverage_bonus = log2(2) * 0.1 = 0.1
        expected_bonus = math.log2(2) * 0.1
        expected_score = min(1.0, expected_base + expected_bonus)

        assert abs(scored.kg_relevance_score - expected_score) < 1e-9, (
            f"Expected {expected_score:.6f}, got "
            f"{scored.kg_relevance_score:.6f}"
        )

    def test_single_specific_concept_zero_bonus(self):
        """
        A chunk matching exactly 1 specific concept gets
        coverage_bonus = log2(1)*0.1 = 0.0.

        **Validates: Requirement 3.2**
        """
        service = _build_service()

        chunk_id = "chunk-neo4j-only"
        chunk = _build_chunk(chunk_id, "Neo4j graph database content")
        sim = 0.9100

        concept_hits = [
            _build_concept_hit("c-neo4j", "Neo4j", sim),
        ]

        source_mappings = {
            chunk_id: _build_source_mapping(
                chunk_id, "c-neo4j", "Neo4j", sim * 10.0,
            ),
        }

        result = service._aggregate_and_deduplicate(
            [chunk], [], source_mappings, {chunk_id: concept_hits},
        )

        assert len(result) == 1
        scored = result[0]

        expected_base = min(1.0, max(0.1, sim))
        expected_bonus = 0.0  # log2(1) * 0.1 = 0.0
        expected_score = min(1.0, expected_base + expected_bonus)

        assert abs(scored.kg_relevance_score - expected_score) < 1e-9, (
            f"Single concept should get zero bonus. "
            f"Expected {expected_score:.6f}, "
            f"got {scored.kg_relevance_score:.6f}"
        )

    def test_no_concept_hits_uses_source_mapping_fallback(self):
        """
        When chunk_concept_hits is empty for a chunk, the score
        falls back to source_mapping.match_score / 10.0.

        **Validates: Requirement 3.2**
        """
        service = _build_service()

        chunk_id = "chunk-no-hits"
        chunk = _build_chunk(chunk_id, "Some content")
        raw_score = 7.5

        source_mappings = {
            chunk_id: _build_source_mapping(
                chunk_id, "c-x", "SomeConcept", raw_score,
            ),
        }

        # Empty concept hits for this chunk
        result = service._aggregate_and_deduplicate(
            [chunk], [], source_mappings, {},
        )

        assert len(result) == 1
        scored = result[0]

        expected = min(1.0, max(0.1, raw_score / 10.0))
        assert abs(scored.kg_relevance_score - expected) < 1e-9, (
            f"Fallback score mismatch. Expected {expected:.6f}, "
            f"got {scored.kg_relevance_score:.6f}"
        )


# =============================================================================
# Test Class: Lexical Fallback Preservation
# =============================================================================

class TestLexicalFallbackPreservation:
    """
    Verify that when _model_server_client is None, semantic matching
    is skipped and lexical fallback behavior is unchanged.

    On UNFIXED code these tests PASS — confirming baseline behavior.

    **Validates: Requirement 3.3**
    """

    def test_semantic_matches_empty_when_no_model_server(self):
        """
        _find_semantic_matches() returns [] when model_server_client
        is None, regardless of query content.

        **Validates: Requirement 3.3**
        """
        import asyncio

        decomposer = QueryDecomposer(
            neo4j_client=None,
            model_server_client=None,
            semantic_enabled=True,
        )

        result = asyncio.get_event_loop().run_until_complete(
            decomposer._find_semantic_matches("What about Chelsea?")
        )

        assert result == [], (
            f"Expected empty list when model_server_client is None, "
            f"got {result}"
        )

    def test_semantic_matches_empty_when_semantic_disabled(self):
        """
        _find_semantic_matches() returns [] when semantic_enabled=False.

        **Validates: Requirement 3.3**
        """
        import asyncio

        decomposer = QueryDecomposer(
            neo4j_client=None,
            model_server_client=object(),  # non-None but unused
            semantic_enabled=False,
        )

        result = asyncio.get_event_loop().run_until_complete(
            decomposer._find_semantic_matches("What about Chelsea?")
        )

        assert result == [], (
            f"Expected empty list when semantic_enabled=False, "
            f"got {result}"
        )

    @given(
        query=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "Z"),
            ),
            min_size=3,
            max_size=50,
        ),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_property_no_model_server_always_returns_empty(
        self, query: str,
    ):
        """
        Property: For ALL queries, _find_semantic_matches() returns []
        when model_server_client is None.

        **Validates: Requirement 3.3**
        """
        import asyncio

        decomposer = QueryDecomposer(
            neo4j_client=None,
            model_server_client=None,
        )

        result = asyncio.get_event_loop().run_until_complete(
            decomposer._find_semantic_matches(query)
        )

        assert result == [], (
            f"Expected empty list for query '{query}' when "
            f"model_server_client is None, got {len(result)} results"
        )


# =============================================================================
# Test Class: has_kg_matches=False Preservation
# =============================================================================

class TestHasKgMatchesFalsePreservation:
    """
    Verify that has_kg_matches=False when no concepts match.

    On UNFIXED code these tests PASS — confirming baseline behavior.

    **Validates: Requirement 3.4**
    """

    def test_has_kg_matches_false_when_no_neo4j_client(self):
        """
        decompose() sets has_kg_matches=False when neo4j_client is None.

        **Validates: Requirement 3.4**
        """
        import asyncio

        decomposer = QueryDecomposer(
            neo4j_client=None,
            model_server_client=None,
        )

        result = asyncio.get_event_loop().run_until_complete(
            decomposer.decompose("Tell me about Chelsea")
        )

        assert result.has_kg_matches is False, (
            f"Expected has_kg_matches=False when neo4j_client is None, "
            f"got {result.has_kg_matches}"
        )
        assert result.concept_matches == [], (
            f"Expected empty concept_matches, "
            f"got {len(result.concept_matches)} matches"
        )

    def test_has_kg_matches_false_for_empty_query(self):
        """
        decompose() sets has_kg_matches=False for empty queries.

        **Validates: Requirement 3.4**
        """
        import asyncio

        decomposer = QueryDecomposer(
            neo4j_client=None,
            model_server_client=None,
        )

        result = asyncio.get_event_loop().run_until_complete(
            decomposer.decompose("")
        )

        assert result.has_kg_matches is False
        assert result.concept_matches == []

    @given(
        query=st.text(
            alphabet=st.characters(
                whitelist_categories=("L", "N", "Z"),
            ),
            min_size=1,
            max_size=80,
        ),
    )
    @settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_property_no_clients_means_no_kg_matches(
        self, query: str,
    ):
        """
        Property: For ALL queries, when both neo4j_client and
        model_server_client are None, has_kg_matches is always False.

        **Validates: Requirement 3.4**
        """
        import asyncio

        decomposer = QueryDecomposer(
            neo4j_client=None,
            model_server_client=None,
        )

        result = asyncio.get_event_loop().run_until_complete(
            decomposer.decompose(query)
        )

        assert result.has_kg_matches is False, (
            f"Expected has_kg_matches=False for query '{query[:40]}' "
            f"with no clients, got True"
        )


# =============================================================================
# Test Class: Related Chunk Scoring Preservation
# =============================================================================

class TestRelatedChunkScoringPreservation:
    """
    Verify that related chunks receive hop-distance-decayed scores
    and are capped at _max_related_chunks.

    On UNFIXED code these tests PASS — confirming baseline behavior.

    **Validates: Requirement 3.5**
    """

    @given(
        hop=hop_distance_strategy(),
        decay=hop_decay_strategy(),
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_property_related_chunk_score_is_decay_power_hop(
        self, hop: int, decay: float,
    ):
        """
        Property: For all related chunks, kg_relevance_score equals
        hop_distance_decay ** hop_distance.

        **Validates: Requirement 3.5**
        """
        service = _build_service(hop_distance_decay=decay)

        chunk_id = "chunk-related-1"
        related_chunk = _build_chunk(
            chunk_id,
            "Related content",
            source=RetrievalSource.RELATED_CONCEPT,
        )

        source_mappings = {
            chunk_id: _build_source_mapping(
                chunk_id,
                "c-related",
                "RelatedConcept",
                5.0,
                hop_distance=hop,
                source=RetrievalSource.RELATED_CONCEPT,
            ),
        }

        result = service._aggregate_and_deduplicate(
            [],  # no direct chunks
            [related_chunk],
            source_mappings,
            {},
        )

        assert len(result) == 1
        scored = result[0]

        expected_score = decay ** hop
        assert abs(scored.kg_relevance_score - expected_score) < 1e-9, (
            f"Related chunk score mismatch. "
            f"Expected decay^hop = {decay}^{hop} = {expected_score:.6f}, "
            f"got {scored.kg_relevance_score:.6f}"
        )

    @given(
        max_related=st.integers(min_value=2, max_value=10),
        total_related=st.integers(min_value=5, max_value=30),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_property_related_chunks_capped_at_max(
        self, max_related: int, total_related: int,
    ):
        """
        Property: The number of related chunks in the output never
        exceeds _max_related_chunks.

        **Validates: Requirement 3.5**
        """
        service = _build_service(max_related_chunks=max_related)

        related_chunks = []
        source_mappings: Dict[str, ChunkSourceMapping] = {}

        for i in range(total_related):
            cid = f"chunk-related-{i}"
            related_chunks.append(
                _build_chunk(
                    cid,
                    f"Related content {i}",
                    source=RetrievalSource.RELATED_CONCEPT,
                )
            )
            source_mappings[cid] = _build_source_mapping(
                cid,
                f"c-rel-{i}",
                f"RelatedConcept{i}",
                5.0,
                hop_distance=1,
                source=RetrievalSource.RELATED_CONCEPT,
            )

        result = service._aggregate_and_deduplicate(
            [],  # no direct chunks
            related_chunks,
            source_mappings,
            {},
        )

        expected_count = min(max_related, total_related)
        assert len(result) == expected_count, (
            f"Expected at most {max_related} related chunks "
            f"(from {total_related} total), got {len(result)}"
        )

    def test_concrete_related_chunks_sorted_by_hop_distance(self):
        """
        Related chunks are sorted by hop_distance ascending, so
        closer chunks are included first when capped.

        **Validates: Requirement 3.5**
        """
        service = _build_service(max_related_chunks=2)

        # 3 related chunks at hops 3, 1, 2
        chunks_data = [
            ("chunk-hop3", 3),
            ("chunk-hop1", 1),
            ("chunk-hop2", 2),
        ]

        related_chunks = []
        source_mappings: Dict[str, ChunkSourceMapping] = {}

        for cid, hop in chunks_data:
            related_chunks.append(
                _build_chunk(
                    cid,
                    f"Content at hop {hop}",
                    source=RetrievalSource.RELATED_CONCEPT,
                )
            )
            source_mappings[cid] = _build_source_mapping(
                cid,
                f"c-{cid}",
                f"Concept-{cid}",
                5.0,
                hop_distance=hop,
                source=RetrievalSource.RELATED_CONCEPT,
            )

        result = service._aggregate_and_deduplicate(
            [], related_chunks, source_mappings, {},
        )

        # Cap is 2, so only hop=1 and hop=2 should be included
        assert len(result) == 2
        result_ids = [c.chunk_id for c in result]
        assert "chunk-hop1" in result_ids, (
            "Closest chunk (hop=1) should be included"
        )
        assert "chunk-hop2" in result_ids, (
            "Second closest chunk (hop=2) should be included"
        )
        assert "chunk-hop3" not in result_ids, (
            "Farthest chunk (hop=3) should be excluded by cap"
        )

    def test_related_chunks_not_duplicated_with_direct(self):
        """
        If a chunk appears in both direct and related sets,
        only the direct version is kept (deduplication).

        **Validates: Requirement 3.5**
        """
        service = _build_service()

        shared_id = "chunk-shared"
        sim = 0.85

        direct_chunk = _build_chunk(shared_id, "Shared content")
        related_chunk = _build_chunk(
            shared_id,
            "Shared content",
            source=RetrievalSource.RELATED_CONCEPT,
        )

        concept_hits = [
            _build_concept_hit("c-entity", "Chelsea", sim),
        ]

        source_mappings = {
            shared_id: _build_source_mapping(
                shared_id, "c-entity", "Chelsea", sim * 10.0,
            ),
        }

        result = service._aggregate_and_deduplicate(
            [direct_chunk],
            [related_chunk],
            source_mappings,
            {shared_id: concept_hits},
        )

        # Should appear only once (from direct)
        assert len(result) == 1
        assert result[0].chunk_id == shared_id

        # Score should be from direct concept scoring, not hop decay
        expected_base = min(1.0, max(0.1, sim))
        expected_bonus = 0.0  # log2(1) * 0.1
        expected_score = min(1.0, expected_base + expected_bonus)
        assert abs(
            result[0].kg_relevance_score - expected_score
        ) < 1e-9


# =============================================================================
# Test Class: Named Entity Query Preservation
# =============================================================================

class TestNamedEntityQueryPreservation:
    """
    Verify that queries containing only specific named entities
    (no observation verbs) produce correctly ranked results.

    These tests exercise _aggregate_and_deduplicate() with realistic
    multi-chunk scenarios where all concepts are specific entities.

    On UNFIXED code these tests PASS — confirming baseline behavior.

    **Validates: Requirement 3.1**
    """

    @given(
        concept_names=specific_concept_names_strategy(
            min_size=2, max_size=4,
        ),
        sim=similarity_score_strategy(),
    )
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_property_intersection_chunk_scores_higher_than_single(
        self, concept_names: List[str], sim: float,
    ):
        """
        Property: A chunk matching N specific concepts always scores
        >= a chunk matching 1 specific concept (same base similarity),
        because coverage_bonus = log2(N)*0.1 >= log2(1)*0.1 = 0.

        **Validates: Requirement 3.1**
        """
        service = _build_service()

        # Chunk A: matches all N concepts
        multi_id = "chunk-multi"
        multi_chunk = _build_chunk(multi_id, "Multi-concept content")

        # Chunk B: matches only the first concept
        single_id = "chunk-single"
        single_chunk = _build_chunk(single_id, "Single-concept content")

        multi_hits = [
            _build_concept_hit(f"c-{i}", name, sim)
            for i, name in enumerate(concept_names)
        ]
        single_hits = [
            _build_concept_hit("c-0", concept_names[0], sim),
        ]

        source_mappings = {
            multi_id: _build_source_mapping(
                multi_id, "c-0", concept_names[0], sim * 10.0,
            ),
            single_id: _build_source_mapping(
                single_id, "c-0", concept_names[0], sim * 10.0,
            ),
        }

        chunk_concept_hits = {
            multi_id: multi_hits,
            single_id: single_hits,
        }

        result = service._aggregate_and_deduplicate(
            [multi_chunk, single_chunk],
            [],
            source_mappings,
            chunk_concept_hits,
        )

        scores = {c.chunk_id: c.kg_relevance_score for c in result}
        multi_score = scores[multi_id]
        single_score = scores[single_id]

        assert multi_score >= single_score, (
            f"Chunk matching {len(concept_names)} specific concepts "
            f"({multi_score:.6f}) should score >= chunk matching 1 "
            f"({single_score:.6f})"
        )

    def test_concrete_entity_only_query_ranking(self):
        """
        Concrete case: "Tell me about Neo4j" — a single specific
        entity query. The matching chunk should get the correct
        base score with zero coverage bonus.

        **Validates: Requirement 3.1**
        """
        service = _build_service()

        chunk_id = "chunk-neo4j-guide"
        chunk = _build_chunk(
            chunk_id, "Neo4j is a graph database..."
        )
        sim = 0.9200

        concept_hits = [
            _build_concept_hit("c-neo4j", "Neo4j", sim),
        ]

        source_mappings = {
            chunk_id: _build_source_mapping(
                chunk_id, "c-neo4j", "Neo4j", sim * 10.0,
            ),
        }

        result = service._aggregate_and_deduplicate(
            [chunk], [], source_mappings, {chunk_id: concept_hits},
        )

        assert len(result) == 1
        scored = result[0]

        # base = 0.92, bonus = log2(1)*0.1 = 0.0, total = 0.92
        expected = min(1.0, max(0.1, sim))
        assert abs(scored.kg_relevance_score - expected) < 1e-9

    def test_matched_concepts_stored_on_chunk(self):
        """
        _aggregate_and_deduplicate() stores the matched concept hits
        on the chunk's matched_concepts field.

        **Validates: Requirement 3.1**
        """
        service = _build_service()

        chunk_id = "chunk-with-concepts"
        chunk = _build_chunk(chunk_id, "Content")
        sim = 0.88

        concept_hits = [
            _build_concept_hit("c-a", "Chelsea", sim),
            _build_concept_hit("c-b", "Venezuela", sim),
        ]

        source_mappings = {
            chunk_id: _build_source_mapping(
                chunk_id, "c-a", "Chelsea", sim * 10.0,
            ),
        }

        result = service._aggregate_and_deduplicate(
            [chunk], [], source_mappings, {chunk_id: concept_hits},
        )

        assert len(result) == 1
        assert len(result[0].matched_concepts) == 2
        stored_names = {
            h["concept_name"] for h in result[0].matched_concepts
        }
        assert stored_names == {"Chelsea", "Venezuela"}

    def test_best_concept_name_set_on_chunk(self):
        """
        _aggregate_and_deduplicate() sets concept_name to the
        best-matching concept (highest match_score).

        **Validates: Requirement 3.1**
        """
        service = _build_service()

        chunk_id = "chunk-best-name"
        chunk = _build_chunk(chunk_id, "Content")

        concept_hits = [
            _build_concept_hit("c-low", "LowScore", 0.80),
            _build_concept_hit("c-high", "HighScore", 0.92),
        ]

        source_mappings = {
            chunk_id: _build_source_mapping(
                chunk_id, "c-low", "LowScore", 8.0,
            ),
        }

        result = service._aggregate_and_deduplicate(
            [chunk], [], source_mappings, {chunk_id: concept_hits},
        )

        assert len(result) == 1
        # Best hit is "HighScore" with match_score = 0.92 * 10 = 9.2
        assert result[0].concept_name == "HighScore"
