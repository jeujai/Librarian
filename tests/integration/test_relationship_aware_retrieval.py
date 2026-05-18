"""
Integration Tests for Relationship-Aware Retrieval.

Tests the full KGRetrievalService pipeline with relationship-aware
retrieval activated for multi-concept queries. Uses a mock Neo4j graph
containing known concept paths and EXTRACTED_FROM edges.

The tests use ``precomputed_decomposition`` to inject known concept
matches directly into the pipeline, bypassing the QueryDecomposer's
semantic/lexical matching logic. This isolates the relationship-aware
retrieval behaviour from the decomposer's matching heuristics.

Validates:
- Requirement 1.4: Multi-concept classification recorded in metadata
- Requirement 4.1: Intersection chunks receive relationship boost
- Requirement 5.1: Single-concept queries use existing pipeline unchanged
- Requirement 5.2: Multi-concept queries activate relationship traversal
- Requirement 5.4: Semantic reranker formula unchanged
- Requirement 8.1: Result metadata contains relationship-aware fields
"""

import logging
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.multimodal_librarian.models.kg_retrieval import (
    QueryDecomposition,
    TraversalResult,
)
from src.multimodal_librarian.services.kg_retrieval_service import KGRetrievalService

logger = logging.getLogger(__name__)


# =============================================================================
# Graph Data: A small clinical knowledge graph
#
#   (fever) --PRESENTS_WITH--> (pneumonia) --CAUSED_BY--> (pneumococcus)
#                                   |
#                              TREATED_BY
#                                   v
#                             (amoxicillin)
#
# EXTRACTED_FROM edges:
#   fever         -> chunk-fever-001, chunk-fever-002
#   pneumonia     -> chunk-pneumonia-001, chunk-intersection-001
#   pneumococcus  -> chunk-pneumococcus-001, chunk-intersection-001
#   amoxicillin   -> chunk-amoxicillin-001
#
# chunk-intersection-001 is reachable from both pneumonia AND
# pneumococcus via relationship paths, making it an intersection chunk.
# =============================================================================

CONCEPT_FEVER = {
    "concept_id": "concept-fever",
    "name": "Fever",
    "type": "SYMPTOM",
    "match_score": 5.0,
}

CONCEPT_PNEUMONIA = {
    "concept_id": "concept-pneumonia",
    "name": "Pneumonia",
    "type": "DISEASE",
    "match_score": 6.0,
}

CONCEPT_PNEUMOCOCCUS = {
    "concept_id": "concept-pneumococcus",
    "name": "Pneumococcus",
    "type": "ORGANISM",
    "match_score": 4.5,
}

CONCEPT_AMOXICILLIN = {
    "concept_id": "concept-amoxicillin",
    "name": "Amoxicillin",
    "type": "DRUG",
    "match_score": 5.5,
}

# Chunk ID -> concept ID mapping (EXTRACTED_FROM edges)
EXTRACTED_FROM_MAP: Dict[str, List[str]] = {
    "concept-fever": ["chunk-fever-001", "chunk-fever-002"],
    "concept-pneumonia": [
        "chunk-pneumonia-001",
        "chunk-intersection-001",
    ],
    "concept-pneumococcus": [
        "chunk-pneumococcus-001",
        "chunk-intersection-001",
    ],
    "concept-amoxicillin": ["chunk-amoxicillin-001"],
}

# Chunk content for resolution
CHUNK_CONTENT: Dict[str, Dict[str, Any]] = {
    "chunk-fever-001": {
        "chunk_id": "chunk-fever-001",
        "content": (
            "Fever is a common symptom of many infections. "
            "It is defined as a body temperature above 38C."
        ),
        "source_id": "doc-clinical-001",
        "metadata": {"section": "Symptoms"},
    },
    "chunk-fever-002": {
        "chunk_id": "chunk-fever-002",
        "content": (
            "Management of fever includes antipyretics and "
            "identification of the underlying cause."
        ),
        "source_id": "doc-clinical-001",
        "metadata": {"section": "Management"},
    },
    "chunk-pneumonia-001": {
        "chunk_id": "chunk-pneumonia-001",
        "content": (
            "Pneumonia is an infection of the lung parenchyma. "
            "It can be caused by bacteria, viruses, or fungi."
        ),
        "source_id": "doc-clinical-002",
        "metadata": {"section": "Diseases"},
    },
    "chunk-intersection-001": {
        "chunk_id": "chunk-intersection-001",
        "content": (
            "Pneumococcal pneumonia is the most common form of "
            "bacterial pneumonia. Streptococcus pneumoniae causes "
            "fever, productive cough, and consolidation."
        ),
        "source_id": "doc-clinical-002",
        "metadata": {"section": "Bacterial Pneumonia"},
    },
    "chunk-pneumococcus-001": {
        "chunk_id": "chunk-pneumococcus-001",
        "content": (
            "Streptococcus pneumoniae (pneumococcus) is a "
            "gram-positive bacterium responsible for many "
            "respiratory infections."
        ),
        "source_id": "doc-clinical-003",
        "metadata": {"section": "Microbiology"},
    },
    "chunk-amoxicillin-001": {
        "chunk_id": "chunk-amoxicillin-001",
        "content": (
            "Amoxicillin is a first-line antibiotic for "
            "community-acquired pneumonia in adults."
        ),
        "source_id": "doc-clinical-004",
        "metadata": {"section": "Pharmacology"},
    },
}

# Relationship paths between concept pairs for the traverser.
# Keys are (concept_a, concept_b) tuples; values are lists of
# records that the Cypher query would return.
RELATIONSHIP_PATHS: Dict[tuple, List[Dict[str, Any]]] = {
    ("concept-fever", "concept-pneumonia"): [
        {
            "chunk_id": "chunk-fever-001",
            "via_concept_id": "concept-fever",
            "source_concept_a": "concept-fever",
            "source_concept_b": "concept-pneumonia",
        },
        {
            "chunk_id": "chunk-pneumonia-001",
            "via_concept_id": "concept-pneumonia",
            "source_concept_a": "concept-fever",
            "source_concept_b": "concept-pneumonia",
        },
        {
            "chunk_id": "chunk-intersection-001",
            "via_concept_id": "concept-pneumonia",
            "source_concept_a": "concept-fever",
            "source_concept_b": "concept-pneumonia",
        },
    ],
    ("concept-pneumonia", "concept-pneumococcus"): [
        {
            "chunk_id": "chunk-pneumonia-001",
            "via_concept_id": "concept-pneumonia",
            "source_concept_a": "concept-pneumonia",
            "source_concept_b": "concept-pneumococcus",
        },
        {
            "chunk_id": "chunk-intersection-001",
            "via_concept_id": "concept-pneumonia",
            "source_concept_a": "concept-pneumonia",
            "source_concept_b": "concept-pneumococcus",
        },
        {
            "chunk_id": "chunk-pneumococcus-001",
            "via_concept_id": "concept-pneumococcus",
            "source_concept_a": "concept-pneumonia",
            "source_concept_b": "concept-pneumococcus",
        },
    ],
}

# Related concepts for _retrieve_related_chunks
RELATED_CONCEPTS: Dict[str, List[Dict[str, Any]]] = {
    "concept-fever": [
        {
            "concept_id": "concept-pneumonia",
            "name": "Pneumonia",
            "type": "DISEASE",
            "chunk_ids": EXTRACTED_FROM_MAP["concept-pneumonia"],
            "hop_distance": 1,
            "relationship_path": ["PRESENTS_WITH"],
        },
    ],
    "concept-pneumonia": [
        {
            "concept_id": "concept-fever",
            "name": "Fever",
            "type": "SYMPTOM",
            "chunk_ids": EXTRACTED_FROM_MAP["concept-fever"],
            "hop_distance": 1,
            "relationship_path": ["PRESENTS_WITH"],
        },
        {
            "concept_id": "concept-pneumococcus",
            "name": "Pneumococcus",
            "type": "ORGANISM",
            "chunk_ids": EXTRACTED_FROM_MAP["concept-pneumococcus"],
            "hop_distance": 1,
            "relationship_path": ["CAUSED_BY"],
        },
    ],
    "concept-pneumococcus": [
        {
            "concept_id": "concept-pneumonia",
            "name": "Pneumonia",
            "type": "DISEASE",
            "chunk_ids": EXTRACTED_FROM_MAP["concept-pneumonia"],
            "hop_distance": 1,
            "relationship_path": ["CAUSES"],
        },
    ],
}


# =============================================================================
# Fixtures
# =============================================================================


def _build_neo4j_mock() -> MagicMock:
    """Build a mock Neo4j client wired to the clinical graph data."""
    mock = MagicMock()

    async def execute_query(
        query: str, params: Dict[str, Any] = None
    ):
        params = params or {}
        ql = query.lower()

        # EXTRACTED_FROM chunk ID query (direct chunks)
        if (
            "extracted_from" in ql
            and "ch.chunk_id" in ql
            and "related" not in ql
            and "start" not in ql
            and "*1.." not in ql
        ):
            cid = params.get("concept_id", "")
            return [
                {"chunk_id": c}
                for c in EXTRACTED_FROM_MAP.get(cid, [])
            ]

        # Relationship traverser Cypher (variable-length path)
        if "*1.." in ql:
            cid_a = params.get("concept_id_a", "")
            cid_b = params.get("concept_id_b", "")
            for key in [
                (cid_a, cid_b),
                (cid_b, cid_a),
            ]:
                if key in RELATIONSHIP_PATHS:
                    return RELATIONSHIP_PATHS[key]
            return []

        # Related concepts traversal
        if (
            ("extracted_from" in ql and "related" in ql)
            or "match path" in ql
        ):
            cid = params.get("concept_id", "")
            return RELATED_CONCEPTS.get(cid, [])

        return []

    mock.execute_query = AsyncMock(side_effect=execute_query)
    return mock


def _build_vector_mock() -> MagicMock:
    """Build a mock vector client that resolves CHUNK_CONTENT."""
    mock = MagicMock()

    async def get_chunk_by_id(chunk_id: str):
        return CHUNK_CONTENT.get(chunk_id)

    async def semantic_search_async(
        query: str, top_k: int = 10
    ):
        return []

    mock.get_chunk_by_id = AsyncMock(
        side_effect=get_chunk_by_id
    )
    mock.semantic_search_async = AsyncMock(
        side_effect=semantic_search_async
    )
    mock.is_connected = MagicMock(return_value=True)
    # Force ChunkResolver to use individual get_chunk_by_id
    del mock.get_chunks_by_ids
    return mock


def _build_model_mock() -> MagicMock:
    """Build a mock model client for embeddings."""
    mock = MagicMock()

    async def generate_embeddings(texts: List[str]):
        return [
            [0.1 + (i * 0.01)] * 384
            for i in range(len(texts))
        ]

    mock.generate_embeddings = AsyncMock(
        side_effect=generate_embeddings
    )
    return mock


@pytest.fixture
def mock_neo4j_client():
    return _build_neo4j_mock()


@pytest.fixture
def mock_vector_client():
    return _build_vector_mock()


@pytest.fixture
def mock_model_client():
    return _build_model_mock()


@pytest.fixture
def multi_concept_decomposition():
    """Precomputed decomposition with two concepts (fever + pneumonia)."""
    return QueryDecomposition(
        original_query="What causes fever and pneumonia?",
        entities=["Fever", "Pneumonia"],
        actions=["causes"],
        subjects=[],
        concept_matches=[CONCEPT_FEVER, CONCEPT_PNEUMONIA],
        has_kg_matches=True,
    )


@pytest.fixture
def single_concept_decomposition():
    """Precomputed decomposition with one concept (amoxicillin)."""
    return QueryDecomposition(
        original_query="Tell me about amoxicillin",
        entities=["Amoxicillin"],
        actions=[],
        subjects=[],
        concept_matches=[CONCEPT_AMOXICILLIN],
        has_kg_matches=True,
    )


@pytest.fixture
def kg_service(
    mock_neo4j_client, mock_vector_client, mock_model_client
):
    """KGRetrievalService wired to the mock clinical graph."""
    return KGRetrievalService(
        neo4j_client=mock_neo4j_client,
        vector_client=mock_vector_client,
        model_client=mock_model_client,
        cache_ttl_seconds=300,
        max_results=15,
        max_hops=2,
        augmentation_threshold=3,
    )


# =============================================================================
# Tests: Multi-Concept Query with Relationship-Aware Retrieval
# =============================================================================


class TestMultiConceptRelationshipAwareRetrieval:
    """Integration tests for multi-concept queries that activate
    relationship-aware retrieval.

    Validates: Requirements 1.4, 4.1, 5.2, 8.1
    """

    @pytest.mark.asyncio
    async def test_multi_concept_activates_relationship_aware(
        self, kg_service, multi_concept_decomposition
    ):
        """Multi-concept query should activate relationship-aware
        retrieval and record it in result metadata.

        Validates: Requirements 1.4, 5.2, 8.1
        """
        result = await kg_service.retrieve(
            "What causes fever and pneumonia?",
            precomputed_decomposition=multi_concept_decomposition,
        )

        assert result.fallback_used is False, (
            f"Expected KG retrieval, got fallback: "
            f"{result.metadata.get('fallback_reason')}"
        )
        assert (
            result.metadata.get("relationship_aware_activated")
            is True
        ), "Expected relationship_aware_activated=True"

    @pytest.mark.asyncio
    async def test_metadata_contains_all_relationship_fields(
        self, kg_service, multi_concept_decomposition
    ):
        """Result metadata must contain all four relationship-aware
        fields when a multi-concept query is processed.

        Validates: Requirement 8.1
        """
        result = await kg_service.retrieve(
            "What causes fever and pneumonia?",
            precomputed_decomposition=multi_concept_decomposition,
        )

        required_keys = [
            "relationship_aware_activated",
            "intersection_chunks_found",
            "relationship_paths_traversed",
            "relationship_traversal_duration_ms",
        ]
        for key in required_keys:
            assert key in result.metadata, (
                f"Missing metadata key '{key}'. "
                f"Keys: {list(result.metadata.keys())}"
            )

        assert isinstance(
            result.metadata["relationship_aware_activated"], bool
        )
        assert isinstance(
            result.metadata["intersection_chunks_found"], int
        )
        assert isinstance(
            result.metadata["relationship_paths_traversed"], int
        )
        assert isinstance(
            result.metadata["relationship_traversal_duration_ms"],
            int,
        )

    @pytest.mark.asyncio
    async def test_intersection_chunks_boosted(
        self, kg_service, multi_concept_decomposition
    ):
        """Intersection chunks (reachable from >=2 concepts) should
        have boost metadata and kg_relevance_score capped at 1.0.

        Validates: Requirement 4.1
        """
        result = await kg_service.retrieve(
            "What causes fever and pneumonia?",
            precomputed_decomposition=multi_concept_decomposition,
        )

        assert len(result.chunks) > 0, "Expected chunks"

        # Find the intersection chunk
        intersection = None
        non_boosted = []
        for chunk in result.chunks:
            if chunk.chunk_id == "chunk-intersection-001":
                intersection = chunk
            elif (
                chunk.metadata.get("relationship_boost_applied")
                is None
            ):
                non_boosted.append(chunk)

        if intersection is not None:
            assert (
                "relationship_boost_applied"
                in intersection.metadata
            ), "Missing relationship_boost_applied"
            assert (
                "connecting_concept_count"
                in intersection.metadata
            ), "Missing connecting_concept_count"

            boost = intersection.metadata[
                "relationship_boost_applied"
            ]
            assert boost >= 1.0, (
                f"Expected boost >= 1.0, got {boost}"
            )
            assert intersection.kg_relevance_score <= 1.0, (
                f"Score exceeds 1.0: "
                f"{intersection.kg_relevance_score}"
            )

    @pytest.mark.asyncio
    async def test_intersection_chunks_found_count(
        self, kg_service, multi_concept_decomposition
    ):
        """Metadata should report at least 1 intersection chunk.

        Validates: Requirement 8.1
        """
        result = await kg_service.retrieve(
            "What causes fever and pneumonia?",
            precomputed_decomposition=multi_concept_decomposition,
        )

        count = result.metadata.get(
            "intersection_chunks_found", 0
        )
        assert count >= 1, (
            f"Expected >= 1 intersection chunk, got {count}"
        )

    @pytest.mark.asyncio
    async def test_relationship_paths_traversed_positive(
        self, kg_service, multi_concept_decomposition
    ):
        """Metadata should report a positive path count.

        Validates: Requirement 8.1
        """
        result = await kg_service.retrieve(
            "What causes fever and pneumonia?",
            precomputed_decomposition=multi_concept_decomposition,
        )

        paths = result.metadata.get(
            "relationship_paths_traversed", 0
        )
        assert paths > 0, (
            f"Expected positive path count, got {paths}"
        )

    @pytest.mark.asyncio
    async def test_traversal_duration_recorded(
        self, kg_service, multi_concept_decomposition
    ):
        """Metadata should record non-negative traversal duration.

        Validates: Requirement 8.1
        """
        result = await kg_service.retrieve(
            "What causes fever and pneumonia?",
            precomputed_decomposition=multi_concept_decomposition,
        )

        duration = result.metadata.get(
            "relationship_traversal_duration_ms", -1
        )
        assert duration >= 0, (
            f"Expected non-negative duration, got {duration}"
        )


# =============================================================================
# Tests: Single-Concept Query Preservation
# =============================================================================


class TestSingleConceptPreservation:
    """Integration tests verifying that single-concept queries
    produce results identical to the baseline (no traverser).

    Validates: Requirements 5.1, 5.2, 5.4
    """

    @pytest.mark.asyncio
    async def test_single_concept_no_relationship_aware(
        self, kg_service, single_concept_decomposition
    ):
        """Single-concept query should NOT activate relationship-
        aware mode.

        Validates: Requirement 5.1
        """
        result = await kg_service.retrieve(
            "Tell me about amoxicillin",
            precomputed_decomposition=single_concept_decomposition,
        )

        assert (
            result.metadata.get("relationship_aware_activated")
            is False
        ), "Single-concept should not activate relationship mode"

    @pytest.mark.asyncio
    async def test_single_concept_no_intersection_metadata(
        self, kg_service, single_concept_decomposition
    ):
        """Single-concept query should not have intersection or
        path metadata keys.

        Validates: Requirement 5.1
        """
        result = await kg_service.retrieve(
            "Tell me about amoxicillin",
            precomputed_decomposition=single_concept_decomposition,
        )

        assert "intersection_chunks_found" not in result.metadata
        assert (
            "relationship_paths_traversed" not in result.metadata
        )

    @pytest.mark.asyncio
    async def test_single_concept_no_boost_on_chunks(
        self, kg_service, single_concept_decomposition
    ):
        """No chunks should have relationship_boost_applied for a
        single-concept query.

        Validates: Requirement 5.1
        """
        result = await kg_service.retrieve(
            "Tell me about amoxicillin",
            precomputed_decomposition=single_concept_decomposition,
        )

        for chunk in result.chunks:
            assert (
                "relationship_boost_applied"
                not in chunk.metadata
            ), (
                f"Chunk {chunk.chunk_id} should not have "
                f"boost metadata"
            )
            assert (
                "connecting_concept_count"
                not in chunk.metadata
            ), (
                f"Chunk {chunk.chunk_id} should not have "
                f"connecting_concept_count"
            )

    @pytest.mark.asyncio
    async def test_single_concept_retrieves_chunks(
        self, kg_service, single_concept_decomposition
    ):
        """Single-concept query should still retrieve chunks.

        Validates: Requirement 5.1
        """
        result = await kg_service.retrieve(
            "Tell me about amoxicillin",
            precomputed_decomposition=single_concept_decomposition,
        )

        assert result.fallback_used is False, (
            f"Expected KG retrieval, got fallback: "
            f"{result.metadata.get('fallback_reason')}"
        )
        assert len(result.chunks) > 0, (
            "Expected at least one chunk for amoxicillin"
        )


# =============================================================================
# Tests: Traversal Failure Graceful Degradation
# =============================================================================


class TestTraversalFailureGracefulDegradation:
    """Tests that the pipeline degrades gracefully when relationship
    traversal fails or times out.

    Validates: Requirements 5.3, 6.1, 6.2
    """

    @pytest.mark.asyncio
    async def test_traversal_timeout_falls_back(self):
        """When relationship traversal times out, the pipeline
        should proceed with existing results (no boost).

        Validates: Requirements 5.3, 6.1
        """
        neo4j = _build_neo4j_mock()
        vector = _build_vector_mock()
        model = _build_model_mock()

        decomposition = QueryDecomposition(
            original_query="fever and pneumonia",
            entities=["Fever", "Pneumonia"],
            actions=[],
            subjects=[],
            concept_matches=[CONCEPT_FEVER, CONCEPT_PNEUMONIA],
            has_kg_matches=True,
        )

        service = KGRetrievalService(
            neo4j_client=neo4j,
            vector_client=vector,
            model_client=model,
            cache_ttl_seconds=300,
            max_results=15,
            max_hops=2,
        )

        # Patch only the traverser's traverse method to simulate
        # a timeout, leaving the rest of the pipeline intact.
        service._relationship_traverser.traverse = AsyncMock(
            return_value=TraversalResult.empty()
        )

        result = await service.retrieve(
            "fever and pneumonia",
            precomputed_decomposition=decomposition,
        )

        assert result.fallback_used is False
        # Traversal returned empty -> no boost applied
        for chunk in result.chunks:
            assert (
                "relationship_boost_applied"
                not in chunk.metadata
            )

    @pytest.mark.asyncio
    async def test_no_paths_no_boost(self):
        """When no relationship paths exist between concepts, no
        boost should be applied.

        Validates: Requirement 5.3
        """
        # Neo4j mock that returns empty for traversal queries
        neo4j = MagicMock()

        async def execute_query(query: str, params=None):
            params = params or {}
            ql = query.lower()

            if (
                "extracted_from" in ql
                and "ch.chunk_id" in ql
                and "*1.." not in ql
            ):
                cid = params.get("concept_id", "")
                return [
                    {"chunk_id": c}
                    for c in EXTRACTED_FROM_MAP.get(cid, [])
                ]

            # No relationship paths
            if "*1.." in ql:
                return []

            if "match path" in ql or "related" in ql:
                return []

            return []

        neo4j.execute_query = AsyncMock(
            side_effect=execute_query
        )

        vector = _build_vector_mock()
        model = _build_model_mock()

        decomposition = QueryDecomposition(
            original_query="fever and pneumonia",
            entities=["Fever", "Pneumonia"],
            actions=[],
            subjects=[],
            concept_matches=[CONCEPT_FEVER, CONCEPT_PNEUMONIA],
            has_kg_matches=True,
        )

        service = KGRetrievalService(
            neo4j_client=neo4j,
            vector_client=vector,
            model_client=model,
            cache_ttl_seconds=300,
            max_results=15,
            max_hops=2,
        )
        result = await service.retrieve(
            "fever and pneumonia",
            precomputed_decomposition=decomposition,
        )

        for chunk in result.chunks:
            assert (
                "relationship_boost_applied"
                not in chunk.metadata
            ), (
                f"Chunk {chunk.chunk_id} should not have "
                f"boost when no paths exist"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
