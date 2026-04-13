"""
Integration tests for the proper-noun chunk filter in
KGRetrievalService and the selective drop logic in RAGService.

Tests verify:
1. KGRetrievalService passes filtered set to reranker
   when filter returns non-None
2. KGRetrievalService falls back to unfiltered candidates
   when filter returns None
3. Filter is called after _aggregate_and_deduplicate and
   before rerank (call order)
4. Filter exception -> KGRetrievalService falls back to
   unfiltered candidates
5. RAGService selective drop retains proper-noun chunks
   alongside web results

Validates: Requirements 7.2, 7.3, 7.5, 7.8, 7.10
"""

import logging
from dataclasses import dataclass
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.multimodal_librarian.components.kg_retrieval.relevance_detector import (  # noqa: E501
    ConceptSpecificityResult,
    QueryTermCoverageResult,
    RelevanceDetector,
    RelevanceVerdict,
    ScoreDistributionResult,
)
from src.multimodal_librarian.models.kg_retrieval import (
    QueryDecomposition,
    RetrievalSource,
    RetrievedChunk,
)
from src.multimodal_librarian.services.kg_retrieval_service import KGRetrievalService
from src.multimodal_librarian.services.rag_service import DocumentChunk, RAGService

logger = logging.getLogger(__name__)


# =============================================================================
# Helpers
# =============================================================================


def _make_retrieved_chunk(
    chunk_id: str,
    content: str,
    final_score: float = 0.5,
    source: RetrievalSource = RetrievalSource.DIRECT_CONCEPT,
) -> RetrievedChunk:
    """Create a RetrievedChunk with minimal fields."""
    return RetrievedChunk(
        chunk_id=chunk_id,
        content=content,
        source=source,
        final_score=final_score,
        kg_relevance_score=0.8,
        semantic_score=final_score,
    )


def _make_document_chunk(
    chunk_id: str,
    content: str,
    similarity_score: float = 0.6,
) -> DocumentChunk:
    """Create a DocumentChunk with minimal fields."""
    return DocumentChunk(
        chunk_id=chunk_id,
        document_id="doc-001",
        document_title="Test Document",
        content=content,
        similarity_score=similarity_score,
    )


def _make_irrelevant_verdict(
    proper_nouns: List[str],
) -> RelevanceVerdict:
    """Create an irrelevant verdict with proper nouns."""
    return RelevanceVerdict(
        is_relevant=False,
        confidence_adjustment_factor=0.3,
        score_distribution=ScoreDistributionResult(
            variance=0.0001,
            spread=0.01,
            is_semantic_floor=True,
            chunk_count=5,
        ),
        concept_specificity=ConceptSpecificityResult(
            per_concept_scores={"generic": 0.2},
            average_specificity=0.2,
            is_low_specificity=True,
            high_specificity_count=0,
            low_specificity_count=1,
        ),
        query_term_coverage=QueryTermCoverageResult(
            proper_nouns=proper_nouns,
            covered_nouns=[],
            uncovered_nouns=proper_nouns,
            coverage_ratio=0.0,
            has_proper_noun_gap=True,
        ),
        reasoning="Test: irrelevant with proper-noun gap",
    )


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_chunks() -> List[RetrievedChunk]:
    """Candidate chunks — some contain 'Venezuela'."""
    return [
        _make_retrieved_chunk(
            "c1",
            "The president gave a speech about policy.",
            0.7,
        ),
        _make_retrieved_chunk(
            "c2",
            "Venezuela's economy has been struggling.",
            0.5,
        ),
        _make_retrieved_chunk(
            "c3",
            "Global trade patterns shifted in 2023.",
            0.6,
        ),
        _make_retrieved_chunk(
            "c4",
            "We discussed Venezuela in our last meeting.",
            0.4,
        ),
        _make_retrieved_chunk(
            "c5",
            "The committee reviewed budget proposals.",
            0.55,
        ),
    ]


@pytest.fixture
def mock_relevance_detector():
    """Mock RelevanceDetector with controllable filter."""
    detector = MagicMock(spec=RelevanceDetector)
    detector.filter_chunks_by_proper_nouns = MagicMock(
        return_value=None,
    )
    return detector


@pytest.fixture
def mock_neo4j_client():
    """Minimal mock Neo4j client."""
    mock = MagicMock()
    mock.execute_query = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def mock_vector_client():
    """Minimal mock vector client."""
    mock = MagicMock()
    mock.get_chunk_by_id = AsyncMock(return_value=None)
    mock.semantic_search_async = AsyncMock(return_value=[])
    mock.is_connected = MagicMock(return_value=True)
    # Prevent auto-creation of get_chunks_by_ids
    del mock.get_chunks_by_ids
    return mock


@pytest.fixture
def mock_model_client():
    """Minimal mock model client for embeddings."""
    mock = MagicMock()
    mock.generate_embeddings = AsyncMock(
        side_effect=lambda texts: [[0.1] * 384 for _ in texts],
    )
    return mock


def _query_decomposition(query: str = "Tell me about Venezuela"):
    """Helper to build a QueryDecomposition."""
    return QueryDecomposition(
        original_query=query,
        entities=["Venezuela"],
        has_kg_matches=True,
        concept_matches=[
            {"name": "venezuela", "concept_id": "c-ven"},
        ],
    )


# =============================================================================
# Test 1: Filter returns non-None -> reranker gets filtered set
# Validates: Requirements 7.2, 7.5
# =============================================================================


class TestFilteredSetPassedToReranker:
    """KGRetrievalService passes filtered set to reranker
    when filter returns non-None."""

    @pytest.mark.asyncio
    async def test_reranker_receives_filtered_chunks(
        self,
        sample_chunks,
        mock_relevance_detector,
        mock_neo4j_client,
        mock_vector_client,
        mock_model_client,
    ):
        venezuela_chunks = [
            c
            for c in sample_chunks
            if "venezuela" in c.content.lower()
        ]
        mock_relevance_detector.filter_chunks_by_proper_nouns \
            .return_value = venezuela_chunks

        service = KGRetrievalService(
            neo4j_client=mock_neo4j_client,
            vector_client=mock_vector_client,
            model_client=mock_model_client,
            relevance_detector=mock_relevance_detector,
        )

        with patch.object(
            service,
            "_decompose_query_safe",
            new_callable=AsyncMock,
        ) as mock_decompose, patch.object(
            service,
            "_stage1_kg_retrieval",
            new_callable=AsyncMock,
        ) as mock_stage1, patch.object(
            service._semantic_reranker,
            "rerank",
            new_callable=AsyncMock,
        ) as mock_rerank:
            mock_decompose.return_value = _query_decomposition()
            mock_stage1.return_value = (sample_chunks, {})
            mock_rerank.return_value = venezuela_chunks

            await service.retrieve(
                "Tell me about Venezuela",
            )

            # Filter called with full candidate set
            mock_relevance_detector \
                .filter_chunks_by_proper_nouns \
                .assert_called_once_with(
                    sample_chunks,
                    "Tell me about Venezuela",
                    adaptive_threshold=1.0,
                )

            # Reranker got the FILTERED set (2), not full (5)
            passed = mock_rerank.call_args[0][0]
            assert len(passed) == len(venezuela_chunks)
            assert all(
                "venezuela" in c.content.lower()
                for c in passed
            )


# =============================================================================
# Test 2: Filter returns None -> reranker gets unfiltered set
# Validates: Requirements 7.3
# =============================================================================


class TestFallbackWhenFilterReturnsNone:
    """KGRetrievalService falls back to unfiltered candidates
    when filter returns None."""

    @pytest.mark.asyncio
    async def test_reranker_receives_full_set(
        self,
        sample_chunks,
        mock_relevance_detector,
        mock_neo4j_client,
        mock_vector_client,
        mock_model_client,
    ):
        mock_relevance_detector.filter_chunks_by_proper_nouns \
            .return_value = None

        service = KGRetrievalService(
            neo4j_client=mock_neo4j_client,
            vector_client=mock_vector_client,
            model_client=mock_model_client,
            relevance_detector=mock_relevance_detector,
        )

        with patch.object(
            service,
            "_decompose_query_safe",
            new_callable=AsyncMock,
        ) as mock_decompose, patch.object(
            service,
            "_stage1_kg_retrieval",
            new_callable=AsyncMock,
        ) as mock_stage1, patch.object(
            service._semantic_reranker,
            "rerank",
            new_callable=AsyncMock,
        ) as mock_rerank:
            decomp = QueryDecomposition(
                original_query="how is the weather today",
                entities=[],
                has_kg_matches=True,
                concept_matches=[
                    {"name": "weather", "concept_id": "c-w"},
                ],
            )
            mock_decompose.return_value = decomp
            mock_stage1.return_value = (sample_chunks, {})
            mock_rerank.return_value = sample_chunks[:3]

            await service.retrieve(
                "how is the weather today",
            )

            passed = mock_rerank.call_args[0][0]
            assert len(passed) == len(sample_chunks)


# =============================================================================
# Test 3: Call order — filter between aggregate and rerank
# Validates: Requirements 7.5
# =============================================================================


class TestFilterCallOrder:
    """Filter called after _aggregate_and_deduplicate,
    before rerank."""

    @pytest.mark.asyncio
    async def test_order_is_stage1_filter_rerank(
        self,
        sample_chunks,
        mock_relevance_detector,
        mock_neo4j_client,
        mock_vector_client,
        mock_model_client,
    ):
        call_order: List[str] = []

        def _filter_side_effect(chunks, query, adaptive_threshold=1.0):
            call_order.append("filter")
            return None

        mock_relevance_detector \
            .filter_chunks_by_proper_nouns \
            .side_effect = _filter_side_effect

        service = KGRetrievalService(
            neo4j_client=mock_neo4j_client,
            vector_client=mock_vector_client,
            model_client=mock_model_client,
            relevance_detector=mock_relevance_detector,
        )

        async def _stage1(*a, **kw):
            call_order.append("stage1")
            return (sample_chunks, {})

        async def _rerank(chunks, query, top_k, **kwargs):
            call_order.append("rerank")
            return chunks[:3]

        with patch.object(
            service,
            "_decompose_query_safe",
            new_callable=AsyncMock,
        ) as mock_decompose, patch.object(
            service,
            "_stage1_kg_retrieval",
            new=AsyncMock(side_effect=_stage1),
        ), patch.object(
            service._semantic_reranker,
            "rerank",
            new=AsyncMock(side_effect=_rerank),
        ):
            mock_decompose.return_value = _query_decomposition()

            await service.retrieve(
                "Tell me about Venezuela",
            )

            assert call_order == [
                "stage1",
                "filter",
                "rerank",
            ]


# =============================================================================
# Test 4: Filter exception -> fallback to unfiltered
# Validates: Requirements 7.8
# =============================================================================


class TestFilterExceptionFallback:
    """Filter exception -> KGRetrievalService falls back to
    unfiltered candidates."""

    @pytest.mark.asyncio
    async def test_reranker_gets_full_set_on_exception(
        self,
        sample_chunks,
        mock_relevance_detector,
        mock_neo4j_client,
        mock_vector_client,
        mock_model_client,
    ):
        mock_relevance_detector \
            .filter_chunks_by_proper_nouns \
            .side_effect = RuntimeError("spaCy model crashed")

        service = KGRetrievalService(
            neo4j_client=mock_neo4j_client,
            vector_client=mock_vector_client,
            model_client=mock_model_client,
            relevance_detector=mock_relevance_detector,
        )

        with patch.object(
            service,
            "_decompose_query_safe",
            new_callable=AsyncMock,
        ) as mock_decompose, patch.object(
            service,
            "_stage1_kg_retrieval",
            new_callable=AsyncMock,
        ) as mock_stage1, patch.object(
            service._semantic_reranker,
            "rerank",
            new_callable=AsyncMock,
        ) as mock_rerank:
            mock_decompose.return_value = _query_decomposition()
            mock_stage1.return_value = (sample_chunks, {})
            mock_rerank.return_value = sample_chunks[:3]

            # Should NOT raise
            result = await service.retrieve(
                "Tell me about Venezuela",
            )

            # Reranker got the FULL unfiltered set
            passed = mock_rerank.call_args[0][0]
            assert len(passed) == len(sample_chunks)
            assert result is not None
            assert result.chunks is not None


# =============================================================================
# Test 5: RAGService selective drop retains proper-noun chunks
# Validates: Requirements 7.10
# =============================================================================


class TestRAGServiceSelectiveDrop:
    """RAGService selective drop retains proper-noun chunks
    alongside web results."""

    @pytest.mark.asyncio
    async def test_selective_drop_keeps_proper_noun_chunks(
        self,
    ):
        librarian_chunks = [
            _make_document_chunk(
                "lib-1",
                "The president discussed policy changes.",
                0.4,
            ),
            _make_document_chunk(
                "lib-2",
                "Venezuela's economy was a key topic.",
                0.35,
            ),
            _make_document_chunk(
                "lib-3",
                "Global trade patterns shifted.",
                0.38,
            ),
            _make_document_chunk(
                "lib-4",
                "We talked about Venezuela last week.",
                0.32,
            ),
        ]

        mock_detector = MagicMock(spec=RelevanceDetector)
        verdict = _make_irrelevant_verdict(["Venezuela"])
        mock_detector.evaluate = MagicMock(return_value=verdict)

        # Fake SearXNG result
        @dataclass
        class FakeSearXNGResult:
            title: str
            url: str
            content: str
            score: float
            engine: str

        mock_searxng = MagicMock()
        mock_searxng.search = AsyncMock(return_value=[
            FakeSearXNGResult(
                title="Venezuela - Wikipedia",
                url="https://en.wikipedia.org/wiki/Venezuela",
                content="Venezuela is in South America.",
                score=5.0,
                engine="google",
            ),
        ])

        mock_vector = MagicMock()
        mock_vector.is_connected = MagicMock(return_value=True)
        mock_ai = MagicMock()

        rag = RAGService(
            vector_client=mock_vector,
            ai_service=mock_ai,
            relevance_detector=mock_detector,
            searxng_client=mock_searxng,
        )

        decomp = QueryDecomposition(
            original_query="Tell me about Venezuela",
            entities=["Venezuela"],
            has_kg_matches=True,
            concept_matches=[
                {"name": "venezuela", "concept_id": "c-ven"},
            ],
        )

        result = await rag._post_processing_phase(
            query="Tell me about Venezuela",
            librarian_chunks=librarian_chunks,
            query_decomposition=decomp,
        )

        mock_detector.evaluate.assert_called_once()
        mock_searxng.search.assert_called_once()

        retained_lib = [
            c for c in result
            if c.source_type != "web_search"
        ]
        web = [
            c for c in result
            if c.source_type == "web_search"
        ]

        assert len(web) >= 1

        # Only Venezuela-containing chunks retained
        for c in retained_lib:
            assert "venezuela" in c.content.lower(), (
                f"Chunk '{c.chunk_id}' retained without "
                f"'Venezuela': {c.content}"
            )

        retained_ids = {c.chunk_id for c in retained_lib}
        # No Venezuela -> dropped
        assert "lib-1" not in retained_ids
        assert "lib-3" not in retained_ids
        # Contains Venezuela -> kept
        assert "lib-2" in retained_ids
        assert "lib-4" in retained_ids
