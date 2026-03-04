"""
Property-based and unit tests for SemanticReranker semantic pre-filter.

Tests cover:
- Property 2: Custom weights are respected
- Unit tests for edge cases and configuration

Feature: kg-retrieval-semantic-prefilter
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from multimodal_librarian.components.kg_retrieval.semantic_reranker import (
    SemanticReranker,
)
from multimodal_librarian.models.kg_retrieval import RetrievalSource, RetrievedChunk

# =============================================================================
# Helpers
# =============================================================================

def _make_chunk(
    chunk_id: str = "c1",
    content: str = "text",
    kg_score: float = 1.0,
    embedding: list | None = None,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        content=content,
        source=RetrievalSource.DIRECT_CONCEPT,
        kg_relevance_score=kg_score,
        embedding=embedding,
    )


def _make_mock_model_client(dim: int = 8):
    """Return a mock model client whose generate_embeddings returns a random unit vector."""
    client = MagicMock()

    async def _gen(texts, normalize=True):
        vecs = []
        for _ in texts:
            v = np.random.randn(dim).astype(float)
            v = v / (np.linalg.norm(v) + 1e-12)
            vecs.append(v.tolist())
        return vecs

    client.generate_embeddings = AsyncMock(side_effect=_gen)
    return client


# =============================================================================
# Property 2: Custom weights are respected
# Validates: Requirements 2.1, 2.2, 2.3
# =============================================================================

# Strategy: non-negative weight pairs
_weight_st = st.floats(min_value=0.0, max_value=10.0, allow_nan=False, allow_infinity=False)


@settings(max_examples=100, deadline=None)
@given(
    kg_w=_weight_st,
    sem_w=_weight_st,
    kg_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
    sem_score=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_property2_custom_weights_respected(kg_w, sem_w, kg_score, sem_score):
    """
    Property 2: Custom weights are respected.

    For any pair of non-negative floats (kg_w, sem_w), a SemanticReranker
    initialized with those weights should compute
    final_score = kg_w * kg_relevance_score + sem_w * semantic_score
    for every chunk it reranks.

    **Validates: Requirements 2.1, 2.2, 2.3**
    """
    reranker = SemanticReranker(model_client=None, kg_weight=kg_w, semantic_weight=sem_w)

    # Verify weights stored correctly
    assert reranker.kg_weight == kg_w
    assert reranker.semantic_weight == sem_w

    # Verify final score formula
    expected = kg_w * kg_score + sem_w * sem_score
    actual = reranker._calculate_final_score(kg_score, sem_score)
    assert abs(actual - expected) < 1e-9, f"Expected {expected}, got {actual}"


# =============================================================================
# Unit tests for edge cases and configuration
# Validates: Requirements 1.3, 1.4, 2.1, 4.2
# =============================================================================


class TestSemanticRerankerDefaults:
    """Test default weight values and constants."""

    def test_default_kg_weight_is_0_7(self):
        assert SemanticReranker.DEFAULT_KG_WEIGHT == 0.7

    def test_default_semantic_weight_is_0_3(self):
        assert SemanticReranker.DEFAULT_SEMANTIC_WEIGHT == 0.3

    def test_max_chunks_for_reranking_is_50(self):
        assert SemanticReranker.MAX_CHUNKS_FOR_RERANKING == 50

    def test_instance_uses_default_weights(self):
        reranker = SemanticReranker()
        assert reranker.kg_weight == 0.7
        assert reranker.semantic_weight == 0.3


class TestPrefilterEdgeCases:
    """Test _prefilter_chunks edge cases."""

    def test_prefilter_passes_all_when_at_limit(self):
        """When chunk count == MAX_CHUNKS_FOR_RERANKING, all pass through."""
        dim = 4
        query_emb = np.ones(dim, dtype=np.float64)
        chunks = [
            _make_chunk(
                chunk_id=f"c{i}",
                embedding=np.random.randn(dim).tolist(),
            )
            for i in range(SemanticReranker.MAX_CHUNKS_FOR_RERANKING)
        ]
        reranker = SemanticReranker()
        result = reranker._prefilter_chunks(chunks, query_emb)
        assert len(result) == len(chunks)

    def test_prefilter_all_chunks_missing_embeddings(self):
        """When all chunks lack embeddings, return first MAX_CHUNKS_FOR_RERANKING."""
        chunks = [
            _make_chunk(chunk_id=f"c{i}", embedding=None)
            for i in range(SemanticReranker.MAX_CHUNKS_FOR_RERANKING + 10)
        ]
        reranker = SemanticReranker()
        query_emb = np.ones(4, dtype=np.float64)
        result = reranker._prefilter_chunks(chunks, query_emb)
        assert len(result) == SemanticReranker.MAX_CHUNKS_FOR_RERANKING


class TestRerankEdgeCases:
    """Test rerank method edge cases."""

    def test_empty_chunks_returns_empty(self):
        reranker = SemanticReranker()
        result = asyncio.get_event_loop().run_until_complete(
            reranker.rerank([], "some query")
        )
        assert result == []

    def test_empty_query_falls_back_to_kg_scores(self):
        """Empty query should fall back to KG score ordering."""
        chunks = [
            _make_chunk(chunk_id="low", kg_score=0.2),
            _make_chunk(chunk_id="high", kg_score=0.9),
        ]
        reranker = SemanticReranker()
        result = asyncio.get_event_loop().run_until_complete(
            reranker.rerank(chunks, "")
        )
        # Should be sorted by kg_relevance_score descending
        assert result[0].chunk_id == "high"
        assert result[0].final_score == result[0].kg_relevance_score

    def test_no_model_client_falls_back_to_kg_scores(self):
        """Without model client, reranker sorts by KG score and sets final_score = kg_score."""
        chunks = [
            _make_chunk(chunk_id="a", kg_score=0.3),
            _make_chunk(chunk_id="b", kg_score=0.8),
            _make_chunk(chunk_id="c", kg_score=0.5),
        ]
        reranker = SemanticReranker(model_client=None)
        result = asyncio.get_event_loop().run_until_complete(
            reranker.rerank(chunks, "test query", top_k=10)
        )
        assert [c.chunk_id for c in result] == ["b", "c", "a"]
        for c in result:
            assert c.final_score == c.kg_relevance_score
