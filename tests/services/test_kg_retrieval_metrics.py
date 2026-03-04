"""Tests for KGRetrievalService retrieval quality metrics.

Covers:
- RetrievalMetrics dataclass creation
- evaluate_retrieval with empty ground truth
- evaluate_retrieval metrics computation (mocked retrieve)
- evaluate_retrieval with threshold overrides (applied and restored)
- evaluate_retrieval F1 formula correctness
- evaluate_retrieval with empty retrieved set (precision = 0.0)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from multimodal_librarian.models.kg_retrieval import (
    KGRetrievalResult,
    RetrievalSource,
    RetrievedChunk,
)
from multimodal_librarian.services.kg_retrieval_service import (
    KGRetrievalService,
    RetrievalMetrics,
)


def _make_chunk(chunk_id: str) -> RetrievedChunk:
    """Helper to create a RetrievedChunk with minimal fields."""
    return RetrievedChunk(
        chunk_id=chunk_id,
        content=f"content for {chunk_id}",
        source=RetrievalSource.DIRECT_CONCEPT,
    )


def _make_service() -> KGRetrievalService:
    """Create a KGRetrievalService without real clients."""
    service = KGRetrievalService.__new__(KGRetrievalService)
    service._neo4j_client = None
    service._vector_client = None
    service._model_client = None
    service._max_results = 15
    service._max_hops = 2
    service._cache_ttl = 300
    service._source_chunks_cache = {}
    service._cache_hits = 0
    service._cache_misses = 0
    service._total_queries = 0
    return service


class TestRetrievalMetrics:
    """Tests for the RetrievalMetrics dataclass."""

    def test_creation(self):
        metrics = RetrievalMetrics(
            recall=0.8,
            precision=0.6,
            f1_score=0.685,
            true_positives=4,
            retrieved_count=6,
            ground_truth_count=5,
        )
        assert metrics.recall == 0.8
        assert metrics.precision == 0.6
        assert metrics.f1_score == 0.685
        assert metrics.true_positives == 4
        assert metrics.retrieved_count == 6
        assert metrics.ground_truth_count == 5

    def test_zero_metrics(self):
        metrics = RetrievalMetrics(
            recall=0.0,
            precision=0.0,
            f1_score=0.0,
            true_positives=0,
            retrieved_count=0,
            ground_truth_count=0,
        )
        assert metrics.recall == 0.0
        assert metrics.precision == 0.0
        assert metrics.f1_score == 0.0


class TestEvaluateRetrieval:
    """Tests for KGRetrievalService.evaluate_retrieval."""

    @pytest.mark.asyncio
    async def test_empty_ground_truth_returns_zeros(self):
        service = _make_service()
        result = await service.evaluate_retrieval(
            query="test query",
            ground_truth_chunk_ids=[],
        )
        assert result['recall'] == 0.0
        assert result['precision'] == 0.0
        assert result['f1_score'] == 0.0
        assert result['true_positives'] == 0
        assert result['retrieved_count'] == 0
        assert result['ground_truth_count'] == 0
        assert result['retrieval_result'] is None

    @pytest.mark.asyncio
    async def test_perfect_retrieval(self):
        """All ground truth chunks are retrieved, nothing extra."""
        service = _make_service()
        chunks = [_make_chunk("c1"), _make_chunk("c2"), _make_chunk("c3")]
        mock_result = KGRetrievalResult(chunks=chunks)
        service.retrieve = AsyncMock(return_value=mock_result)

        result = await service.evaluate_retrieval(
            query="test",
            ground_truth_chunk_ids=["c1", "c2", "c3"],
        )
        assert result['recall'] == 1.0
        assert result['precision'] == 1.0
        assert result['f1_score'] == 1.0
        assert result['true_positives'] == 3
        assert result['retrieved_count'] == 3
        assert result['ground_truth_count'] == 3

    @pytest.mark.asyncio
    async def test_partial_overlap_metrics(self):
        """Retrieved 3 chunks, 2 are relevant out of 4 ground truth."""
        service = _make_service()
        chunks = [_make_chunk("c1"), _make_chunk("c2"), _make_chunk("c5")]
        mock_result = KGRetrievalResult(chunks=chunks)
        service.retrieve = AsyncMock(return_value=mock_result)

        result = await service.evaluate_retrieval(
            query="test",
            ground_truth_chunk_ids=["c1", "c2", "c3", "c4"],
        )
        # 2 true positives out of 4 ground truth => recall = 0.5
        assert result['recall'] == 0.5
        # 2 true positives out of 3 retrieved => precision = 2/3
        assert abs(result['precision'] - 2 / 3) < 1e-9
        # F1 = 2 * 0.5 * (2/3) / (0.5 + 2/3)
        expected_f1 = 2 * 0.5 * (2 / 3) / (0.5 + 2 / 3)
        assert abs(result['f1_score'] - expected_f1) < 1e-9
        assert result['true_positives'] == 2

    @pytest.mark.asyncio
    async def test_empty_retrieved_set(self):
        """No chunks retrieved => precision = 0.0."""
        service = _make_service()
        mock_result = KGRetrievalResult(chunks=[])
        service.retrieve = AsyncMock(return_value=mock_result)

        result = await service.evaluate_retrieval(
            query="test",
            ground_truth_chunk_ids=["c1", "c2"],
        )
        assert result['recall'] == 0.0
        assert result['precision'] == 0.0
        assert result['f1_score'] == 0.0
        assert result['retrieved_count'] == 0
        assert result['ground_truth_count'] == 2

    @pytest.mark.asyncio
    async def test_no_overlap(self):
        """Retrieved chunks have zero overlap with ground truth."""
        service = _make_service()
        chunks = [_make_chunk("x1"), _make_chunk("x2")]
        mock_result = KGRetrievalResult(chunks=chunks)
        service.retrieve = AsyncMock(return_value=mock_result)

        result = await service.evaluate_retrieval(
            query="test",
            ground_truth_chunk_ids=["c1", "c2", "c3"],
        )
        assert result['recall'] == 0.0
        assert result['precision'] == 0.0
        assert result['f1_score'] == 0.0
        assert result['true_positives'] == 0

    @pytest.mark.asyncio
    async def test_f1_formula(self):
        """Verify F1 = 2*P*R / (P+R) for known values."""
        service = _make_service()
        # 2 retrieved, 1 relevant, ground truth has 3
        chunks = [_make_chunk("c1"), _make_chunk("x1")]
        mock_result = KGRetrievalResult(chunks=chunks)
        service.retrieve = AsyncMock(return_value=mock_result)

        result = await service.evaluate_retrieval(
            query="test",
            ground_truth_chunk_ids=["c1", "c2", "c3"],
        )
        precision = 1 / 2  # 1 TP out of 2 retrieved
        recall = 1 / 3     # 1 TP out of 3 ground truth
        expected_f1 = 2 * precision * recall / (precision + recall)
        assert abs(result['f1_score'] - expected_f1) < 1e-9

    @pytest.mark.asyncio
    async def test_threshold_overrides_applied_and_restored(self):
        """Threshold overrides are applied during eval and restored after."""
        service = _make_service()
        mock_result = KGRetrievalResult(
            chunks=[_make_chunk("c1")]
        )
        service.retrieve = AsyncMock(return_value=mock_result)

        mock_settings = MagicMock()
        mock_settings.target_embedding_tokens = 256
        mock_settings.pmi_threshold = 5.0

        with patch(
            "multimodal_librarian.config.get_settings",
            return_value=mock_settings,
        ):
            result = await service.evaluate_retrieval(
                query="test",
                ground_truth_chunk_ids=["c1"],
                threshold_overrides={
                    "target_embedding_tokens": 384,
                    "pmi_threshold": 3.0,
                },
            )

        # Overrides were applied (setattr called)
        assert result['threshold_config'] == {
            "target_embedding_tokens": 384,
            "pmi_threshold": 3.0,
        }
        # Original values restored
        assert mock_settings.target_embedding_tokens == 256
        assert mock_settings.pmi_threshold == 5.0

    @pytest.mark.asyncio
    async def test_threshold_overrides_restored_on_exception(self):
        """Threshold overrides are restored even if retrieve raises."""
        service = _make_service()
        service.retrieve = AsyncMock(
            side_effect=RuntimeError("connection failed")
        )

        mock_settings = MagicMock()
        mock_settings.target_embedding_tokens = 256

        with patch(
            "multimodal_librarian.config.get_settings",
            return_value=mock_settings,
        ):
            with pytest.raises(RuntimeError, match="connection failed"):
                await service.evaluate_retrieval(
                    query="test",
                    ground_truth_chunk_ids=["c1"],
                    threshold_overrides={
                        "target_embedding_tokens": 512,
                    },
                )

        # Original value restored despite exception
        assert mock_settings.target_embedding_tokens == 256

    @pytest.mark.asyncio
    async def test_unknown_threshold_key_logged(self):
        """Unknown threshold override keys are warned, not applied."""
        service = _make_service()
        mock_result = KGRetrievalResult(
            chunks=[_make_chunk("c1")]
        )
        service.retrieve = AsyncMock(return_value=mock_result)

        mock_settings = MagicMock(spec=[])
        # spec=[] means hasattr returns False for everything

        with patch(
            "multimodal_librarian.config.get_settings",
            return_value=mock_settings,
        ), patch(
            "multimodal_librarian.services.kg_retrieval_service.logger"
        ) as mock_logger:
            await service.evaluate_retrieval(
                query="test",
                ground_truth_chunk_ids=["c1"],
                threshold_overrides={"nonexistent_key": 42},
            )
            mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_default_threshold_config(self):
        """Without overrides, threshold_config is 'defaults'."""
        service = _make_service()
        mock_result = KGRetrievalResult(
            chunks=[_make_chunk("c1")]
        )
        service.retrieve = AsyncMock(return_value=mock_result)

        result = await service.evaluate_retrieval(
            query="test",
            ground_truth_chunk_ids=["c1"],
        )
        assert result['threshold_config'] == 'defaults'

    @pytest.mark.asyncio
    async def test_top_k_passed_to_retrieve(self):
        """top_k parameter is forwarded to self.retrieve."""
        service = _make_service()
        mock_result = KGRetrievalResult(chunks=[])
        service.retrieve = AsyncMock(return_value=mock_result)

        await service.evaluate_retrieval(
            query="test query",
            ground_truth_chunk_ids=["c1"],
            top_k=25,
        )
        service.retrieve.assert_called_once_with(
            "test query", top_k=25
        )
