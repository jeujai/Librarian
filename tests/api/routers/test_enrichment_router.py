"""
Tests for the Enrichment Management API Router.

Tests the endpoints for cache statistics, cache clearing, circuit breaker
status, and document lookup by YAGO entity.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.multimodal_librarian.api.routers.enrichment import router
from src.multimodal_librarian.models.enrichment import CacheStats, CircuitState


@pytest.fixture
def mock_enrichment_cache():
    """Create a mock enrichment cache."""
    cache = MagicMock()
    cache.get_stats.return_value = CacheStats(
        yago_size=100,
        conceptnet_size=50,
        yago_hits=500,
        yago_misses=100,
        conceptnet_hits=200,
        conceptnet_misses=50,
        evictions=10
    )
    cache.clear = MagicMock()
    return cache


@pytest.fixture
def mock_enrichment_service():
    """Create a mock enrichment service."""
    service = MagicMock()
    service.find_documents_by_entity = AsyncMock(
        return_value=["doc1", "doc2", "doc3"]
    )
    return service


class TestCacheStatsEndpoint:
    """Tests for GET /api/enrichment/cache/stats endpoint."""

    def test_get_cache_stats_success(self, mock_enrichment_cache):
        """Test successful cache stats retrieval."""
        from fastapi import FastAPI

        from src.multimodal_librarian.api.dependencies import (
            get_enrichment_cache_optional,
        )

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_enrichment_cache_optional] = (
            lambda: mock_enrichment_cache
        )

        with TestClient(app) as client:
            response = client.get("/api/enrichment/cache/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["yago_size"] == 100
        assert data["conceptnet_size"] == 50
        assert data["total_size"] == 150
        assert data["yago_hits"] == 500
        assert data["yago_misses"] == 100
        assert data["conceptnet_hits"] == 200
        assert data["conceptnet_misses"] == 50
        assert data["evictions"] == 10
        assert "timestamp" in data

        app.dependency_overrides.clear()

    def test_get_cache_stats_service_unavailable(self):
        """Test cache stats when service is unavailable."""
        from fastapi import FastAPI

        from src.multimodal_librarian.api.dependencies import (
            get_enrichment_cache_optional,
        )

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_enrichment_cache_optional] = lambda: None

        with TestClient(app) as client:
            response = client.get("/api/enrichment/cache/stats")

        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"].lower()

        app.dependency_overrides.clear()


class TestCacheClearEndpoint:
    """Tests for POST /api/enrichment/cache/clear endpoint."""

    def test_clear_cache_success(self, mock_enrichment_cache):
        """Test successful cache clearing."""
        from fastapi import FastAPI

        from src.multimodal_librarian.api.dependencies import (
            get_enrichment_cache_optional,
        )

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_enrichment_cache_optional] = (
            lambda: mock_enrichment_cache
        )

        with TestClient(app) as client:
            response = client.post("/api/enrichment/cache/clear")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "cleared" in data["message"].lower()
        mock_enrichment_cache.clear.assert_called_once()

        app.dependency_overrides.clear()

    def test_clear_cache_service_unavailable(self):
        """Test cache clear when service is unavailable."""
        from fastapi import FastAPI

        from src.multimodal_librarian.api.dependencies import (
            get_enrichment_cache_optional,
        )

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_enrichment_cache_optional] = lambda: None

        with TestClient(app) as client:
            response = client.post("/api/enrichment/cache/clear")

        assert response.status_code == 503

        app.dependency_overrides.clear()


class TestCircuitBreakerStatusEndpoint:
    """Tests for GET /api/enrichment/circuit-breaker/status endpoint."""

    def test_get_circuit_breaker_status_success(self):
        """Test successful circuit breaker status retrieval."""
        from fastapi import FastAPI

        from src.multimodal_librarian.models.enrichment import (
            CircuitBreakerStats,
            CircuitState,
        )

        app = FastAPI()
        app.include_router(router)

        # Mock the circuit breaker registry
        with patch(
            "src.multimodal_librarian.api.routers.enrichment."
            "get_circuit_breaker_registry"
        ) as mock_registry:
            mock_reg = MagicMock()
            mock_reg.get_all_stats.return_value = {
                "yago": CircuitBreakerStats(
                    state=CircuitState.CLOSED,
                    failures=2,
                    successes=100
                ),
                "conceptnet": CircuitBreakerStats(
                    state=CircuitState.OPEN,
                    failures=5,
                    successes=50
                )
            }
            mock_yago_breaker = MagicMock()
            mock_yago_breaker.get_recovery_time.return_value = None
            mock_conceptnet_breaker = MagicMock()
            mock_conceptnet_breaker.get_recovery_time.return_value = None
            mock_reg.get.side_effect = lambda name: (
                mock_yago_breaker if name == "yago"
                else mock_conceptnet_breaker
            )
            mock_registry.return_value = mock_reg

            with TestClient(app) as client:
                response = client.get(
                    "/api/enrichment/circuit-breaker/status"
                )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["yago"]["state"] == "closed"
        assert data["yago"]["failures"] == 2
        assert data["conceptnet"]["state"] == "open"
        assert data["conceptnet"]["failures"] == 5


class TestDocumentLookupEndpoint:
    """Tests for GET /api/enrichment/documents/{q_number} endpoint."""

    def test_get_documents_by_entity_success(self, mock_enrichment_service):
        """Test successful document lookup by entity."""
        from fastapi import FastAPI

        from src.multimodal_librarian.api.dependencies import (
            get_enrichment_service_optional,
        )

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_enrichment_service_optional] = (
            lambda: mock_enrichment_service
        )

        with TestClient(app) as client:
            response = client.get("/api/enrichment/documents/Q42")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["q_number"] == "Q42"
        assert data["document_ids"] == ["doc1", "doc2", "doc3"]
        assert data["document_count"] == 3

        app.dependency_overrides.clear()

    def test_get_documents_invalid_q_number(self, mock_enrichment_service):
        """Test document lookup with invalid Q-number format."""
        from fastapi import FastAPI

        from src.multimodal_librarian.api.dependencies import (
            get_enrichment_service_optional,
        )

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_enrichment_service_optional] = (
            lambda: mock_enrichment_service
        )

        with TestClient(app) as client:
            # Test invalid format - no Q prefix
            response = client.get("/api/enrichment/documents/42")
            assert response.status_code == 400
            assert "invalid" in response.json()["detail"].lower()

            # Test invalid format - non-numeric after Q
            response = client.get("/api/enrichment/documents/Qabc")
            assert response.status_code == 400

        app.dependency_overrides.clear()

    def test_get_documents_service_unavailable(self):
        """Test document lookup when service is unavailable."""
        from fastapi import FastAPI

        from src.multimodal_librarian.api.dependencies import (
            get_enrichment_service_optional,
        )

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_enrichment_service_optional] = (
            lambda: None
        )

        with TestClient(app) as client:
            response = client.get("/api/enrichment/documents/Q42")

        assert response.status_code == 503

        app.dependency_overrides.clear()

    def test_get_documents_empty_result(self, mock_enrichment_service):
        """Test document lookup with no matching documents."""
        from fastapi import FastAPI

        from src.multimodal_librarian.api.dependencies import (
            get_enrichment_service_optional,
        )

        mock_enrichment_service.find_documents_by_entity = AsyncMock(
            return_value=[]
        )

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_enrichment_service_optional] = (
            lambda: mock_enrichment_service
        )

        with TestClient(app) as client:
            response = client.get("/api/enrichment/documents/Q999999")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["document_ids"] == []
        assert data["document_count"] == 0

        app.dependency_overrides.clear()
