"""
Tests for enhanced local development health check API endpoints.

This module tests the enhanced database connectivity monitoring features
including connection pool monitoring, real-time monitoring, and performance metrics.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime

from multimodal_librarian.main import app
from multimodal_librarian.config.local_config import LocalDatabaseConfig
from multimodal_librarian.clients.database_factory import DatabaseClientFactory


@pytest.fixture
def mock_local_config():
    """Create a mock local configuration for testing."""
    config = LocalDatabaseConfig.create_test_config(
        database_type="local",
        enable_relational_db=True,
        enable_graph_db=True,
        enable_vector_search=True,
        enable_redis_cache=True
    )
    return config


@pytest.fixture
def mock_database_factory(mock_local_config):
    """Create a mock database factory for testing."""
    factory = MagicMock(spec=DatabaseClientFactory)
    factory.config = mock_local_config
    
    # Mock database clients
    factory.get_relational_client.return_value = AsyncMock()
    factory.get_graph_client.return_value = AsyncMock()
    factory.get_vector_client.return_value = AsyncMock()
    factory.get_cache_client.return_value = AsyncMock()
    
    return factory


@pytest.fixture
def client_with_mocks(mock_database_factory):
    """Test client with mocked database factory."""
    from multimodal_librarian.api.routers.health_local import get_local_database_factory
    
    app.dependency_overrides[get_local_database_factory] = lambda: mock_database_factory
    
    with TestClient(app) as client:
        yield client
    
    app.dependency_overrides.clear()


class TestEnhancedConnectivityMonitoring:
    """Test enhanced database connectivity monitoring."""
    
    def test_enhanced_connectivity_basic(self, client_with_mocks, mock_database_factory):
        """Test basic enhanced connectivity monitoring."""
        # Mock successful database connections
        mock_database_factory.get_relational_client.return_value.execute = AsyncMock(return_value=[[1]])
        mock_database_factory.get_graph_client.return_value.execute_query = AsyncMock(return_value=[{"test": 1}])
        mock_database_factory.get_vector_client.return_value.list_collections = AsyncMock(return_value=["test_collection"])
        mock_database_factory.get_cache_client.return_value.ping = AsyncMock(return_value=True)
        
        response = client_with_mocks.get("/api/health/local/connectivity")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["check_type"] == "enhanced_connectivity"
        assert data["monitoring_mode"] == "snapshot"
        assert "services" in data
        assert "summary" in data
        assert data["summary"]["total_checked"] == 4
        assert data["summary"]["connected"] >= 0
        assert "overall_connectivity" in data
    
    def test_enhanced_connectivity_with_pool_stats(self, client_with_mocks, mock_database_factory):
        """Test enhanced connectivity monitoring with pool statistics."""
        # Mock successful database connections
        mock_database_factory.get_relational_client.return_value.execute = AsyncMock(return_value=[[1]])
        mock_database_factory.get_graph_client.return_value.execute_query = AsyncMock(return_value=[{"test": 1}])
        mock_database_factory.get_vector_client.return_value.list_collections = AsyncMock(return_value=["test_collection"])
        mock_database_factory.get_cache_client.return_value.ping = AsyncMock(return_value=True)
        
        response = client_with_mocks.get("/api/health/local/connectivity?include_pool_stats=true")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["check_type"] == "enhanced_connectivity"
        assert "services" in data
        
        # Check that services have pool statistics
        for service_name, service_data in data["services"].items():
            if service_data.get("connected", False):
                # Pool stats should be included (or error if not available)
                assert "pool_stats" in service_data or "pool_stats_error" in service_data
    
    def test_enhanced_connectivity_with_performance(self, client_with_mocks, mock_database_factory):
        """Test enhanced connectivity monitoring with performance metrics."""
        # Mock successful database connections
        mock_database_factory.get_relational_client.return_value.execute = AsyncMock(return_value=[[1]])
        mock_database_factory.get_graph_client.return_value.execute_query = AsyncMock(return_value=[{"test": 1}])
        mock_database_factory.get_vector_client.return_value.list_collections = AsyncMock(return_value=["test_collection"])
        mock_database_factory.get_cache_client.return_value.ping = AsyncMock(return_value=True)
        
        response = client_with_mocks.get("/api/health/local/connectivity?include_performance=true")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["check_type"] == "enhanced_connectivity"
        assert "services" in data
        
        # Check that services have performance metrics
        for service_name, service_data in data["services"].items():
            if service_data.get("connected", False):
                # Performance metrics should be included (or error if not available)
                assert "performance" in service_data or "performance_error" in service_data
    
    def test_enhanced_connectivity_continuous_monitoring(self, client_with_mocks, mock_database_factory):
        """Test enhanced connectivity monitoring with continuous monitoring."""
        # Mock successful database connections
        mock_database_factory.get_relational_client.return_value.execute = AsyncMock(return_value=[[1]])
        mock_database_factory.get_graph_client.return_value.execute_query = AsyncMock(return_value=[{"test": 1}])
        mock_database_factory.get_vector_client.return_value.list_collections = AsyncMock(return_value=["test_collection"])
        mock_database_factory.get_cache_client.return_value.ping = AsyncMock(return_value=True)
        
        response = client_with_mocks.get("/api/health/local/connectivity?continuous_monitoring=true")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["check_type"] == "enhanced_connectivity"
        assert data["monitoring_mode"] == "continuous"
        assert "monitoring" in data
    
    def test_enhanced_connectivity_with_failures(self, client_with_mocks, mock_database_factory):
        """Test enhanced connectivity monitoring with database failures."""
        # Mock database connection failures
        mock_database_factory.get_relational_client.return_value.execute = AsyncMock(
            side_effect=Exception("PostgreSQL connection failed")
        )
        mock_database_factory.get_graph_client.return_value.execute_query = AsyncMock(
            side_effect=Exception("Neo4j connection failed")
        )
        mock_database_factory.get_vector_client.return_value.list_collections = AsyncMock(return_value=["test_collection"])
        mock_database_factory.get_cache_client.return_value.ping = AsyncMock(return_value=True)
        
        response = client_with_mocks.get("/api/health/local/connectivity")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["check_type"] == "enhanced_connectivity"
        assert data["summary"]["failed"] >= 2  # PostgreSQL and Neo4j should fail
        assert len(data["alerts"]) >= 2  # Should have alerts for failures
        assert len(data["recommendations"]) > 0  # Should have recommendations


class TestConnectionPoolMonitoring:
    """Test connection pool monitoring functionality."""
    
    def test_pool_monitoring_basic(self, client_with_mocks, mock_database_factory):
        """Test basic connection pool monitoring."""
        # Mock successful database connections
        mock_database_factory.get_relational_client.return_value.execute = AsyncMock(return_value=[[1]])
        mock_database_factory.get_graph_client.return_value.execute_query = AsyncMock(return_value=[{"test": 1}])
        mock_database_factory.get_vector_client.return_value.list_collections = AsyncMock(return_value=["test_collection"])
        mock_database_factory.get_cache_client.return_value.ping = AsyncMock(return_value=True)
        
        response = client_with_mocks.get("/api/health/local/pools")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["monitoring_type"] == "connection_pools"
        assert "services" in data
        assert "summary" in data
        assert data["summary"]["total_pools"] == 4
        assert "alerts" in data
        assert "recommendations" in data
    
    def test_pool_monitoring_with_history(self, client_with_mocks, mock_database_factory):
        """Test connection pool monitoring with historical data."""
        # Mock successful database connections
        mock_database_factory.get_relational_client.return_value.execute = AsyncMock(return_value=[[1]])
        mock_database_factory.get_graph_client.return_value.execute_query = AsyncMock(return_value=[{"test": 1}])
        mock_database_factory.get_vector_client.return_value.list_collections = AsyncMock(return_value=["test_collection"])
        mock_database_factory.get_cache_client.return_value.ping = AsyncMock(return_value=True)
        
        response = client_with_mocks.get("/api/health/local/pools?include_history=true")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["monitoring_type"] == "connection_pools"
        assert "services" in data
        
        # Check that services have historical data
        for service_name, service_data in data["services"].items():
            if service_data.get("status") == "healthy":
                assert "history" in service_data or "error" in service_data
    
    def test_pool_monitoring_detailed_stats(self, client_with_mocks, mock_database_factory):
        """Test connection pool monitoring with detailed statistics."""
        # Mock successful database connections
        mock_database_factory.get_relational_client.return_value.execute = AsyncMock(return_value=[[1]])
        mock_database_factory.get_graph_client.return_value.execute_query = AsyncMock(return_value=[{"test": 1}])
        mock_database_factory.get_vector_client.return_value.list_collections = AsyncMock(return_value=["test_collection"])
        mock_database_factory.get_cache_client.return_value.ping = AsyncMock(return_value=True)
        
        response = client_with_mocks.get("/api/health/local/pools?detailed_stats=true")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["monitoring_type"] == "connection_pools"
        assert "services" in data
        
        # Check that services have detailed statistics
        for service_name, service_data in data["services"].items():
            if service_data.get("status") == "healthy":
                assert "detailed_stats" in service_data or "error" in service_data


class TestRealtimeConnectivityMonitoring:
    """Test real-time connectivity monitoring functionality."""
    
    def test_realtime_monitoring_basic(self, client_with_mocks, mock_database_factory):
        """Test basic real-time connectivity monitoring."""
        # Mock successful database connections
        mock_database_factory.get_relational_client.return_value.execute = AsyncMock(return_value=[[1]])
        mock_database_factory.get_graph_client.return_value.execute_query = AsyncMock(return_value=[{"test": 1}])
        mock_database_factory.get_vector_client.return_value.list_collections = AsyncMock(return_value=["test_collection"])
        mock_database_factory.get_cache_client.return_value.ping = AsyncMock(return_value=True)
        
        # Use short duration for testing
        response = client_with_mocks.get("/api/health/local/connectivity/realtime?duration_seconds=10&interval_seconds=2")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["monitoring_type"] == "realtime"
        assert data["duration_seconds"] == 10
        assert data["interval_seconds"] == 2
        assert "data_points" in data
        assert len(data["data_points"]) >= 1  # Should have at least one data point
        assert "summary" in data
        assert "services" in data
        assert "alerts" in data
    
    def test_realtime_monitoring_parameters(self, client_with_mocks, mock_database_factory):
        """Test real-time monitoring parameter validation."""
        # Test invalid duration (too short)
        response = client_with_mocks.get("/api/health/local/connectivity/realtime?duration_seconds=5")
        assert response.status_code == 422  # Validation error
        
        # Test invalid duration (too long)
        response = client_with_mocks.get("/api/health/local/connectivity/realtime?duration_seconds=400")
        assert response.status_code == 422  # Validation error
        
        # Test invalid interval (too short)
        response = client_with_mocks.get("/api/health/local/connectivity/realtime?interval_seconds=0")
        assert response.status_code == 422  # Validation error
        
        # Test invalid interval (too long)
        response = client_with_mocks.get("/api/health/local/connectivity/realtime?interval_seconds=35")
        assert response.status_code == 422  # Validation error


class TestConnectivityRecommendations:
    """Test connectivity monitoring recommendations."""
    
    def test_recommendations_generation(self, client_with_mocks, mock_database_factory):
        """Test that recommendations are generated based on monitoring results."""
        # Mock successful database connections
        mock_database_factory.get_relational_client.return_value.execute = AsyncMock(return_value=[[1]])
        mock_database_factory.get_graph_client.return_value.execute_query = AsyncMock(return_value=[{"test": 1}])
        mock_database_factory.get_vector_client.return_value.list_collections = AsyncMock(return_value=["test_collection"])
        mock_database_factory.get_cache_client.return_value.ping = AsyncMock(return_value=True)
        
        response = client_with_mocks.get("/api/health/local/connectivity")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "recommendations" in data
        assert isinstance(data["recommendations"], list)
        assert len(data["recommendations"]) > 0
    
    def test_recommendations_with_failures(self, client_with_mocks, mock_database_factory):
        """Test recommendations when there are connectivity failures."""
        # Mock database connection failures
        mock_database_factory.get_relational_client.return_value.execute = AsyncMock(
            side_effect=Exception("Connection failed")
        )
        mock_database_factory.get_graph_client.return_value.execute_query = AsyncMock(
            side_effect=Exception("Connection failed")
        )
        mock_database_factory.get_vector_client.return_value.list_collections = AsyncMock(
            side_effect=Exception("Connection failed")
        )
        mock_database_factory.get_cache_client.return_value.ping = AsyncMock(
            side_effect=Exception("Connection failed")
        )
        
        response = client_with_mocks.get("/api/health/local/connectivity")
        
        assert response.status_code == 200
        data = response.json()
        
        assert "recommendations" in data
        assert len(data["recommendations"]) > 0
        
        # Should have recommendations for fixing failed services
        recommendations_text = " ".join(data["recommendations"])
        assert "restart" in recommendations_text.lower() or "check" in recommendations_text.lower()


class TestHealthCheckIntegration:
    """Test integration with existing health check system."""
    
    def test_comprehensive_health_check_includes_connectivity(self, client_with_mocks, mock_database_factory):
        """Test that comprehensive health check includes connectivity information."""
        # Mock successful database connections
        mock_database_factory.get_relational_client.return_value.execute = AsyncMock(return_value=[[1]])
        mock_database_factory.get_graph_client.return_value.execute_query = AsyncMock(return_value=[{"test": 1}])
        mock_database_factory.get_vector_client.return_value.list_collections = AsyncMock(return_value=["test_collection"])
        mock_database_factory.get_cache_client.return_value.ping = AsyncMock(return_value=True)
        
        response = client_with_mocks.get("/api/health/local/")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["environment"] == "local"
        assert "services" in data
        assert "summary" in data
        assert "recommendations" in data
    
    def test_individual_service_health_checks(self, client_with_mocks, mock_database_factory):
        """Test individual service health check endpoints."""
        # Mock successful database connections
        mock_database_factory.get_relational_client.return_value.execute = AsyncMock(return_value=[[1]])
        mock_database_factory.get_graph_client.return_value.execute_query = AsyncMock(return_value=[{"test": 1}])
        mock_database_factory.get_vector_client.return_value.list_collections = AsyncMock(return_value=["test_collection"])
        mock_database_factory.get_cache_client.return_value.ping = AsyncMock(return_value=True)
        
        # Test individual service endpoints
        endpoints = [
            "/api/health/local/postgres",
            "/api/health/local/neo4j", 
            "/api/health/local/milvus",
            "/api/health/local/redis"
        ]
        
        for endpoint in endpoints:
            response = client_with_mocks.get(endpoint)
            assert response.status_code == 200
            data = response.json()
            assert "service" in data
            assert "status" in data
            assert "timestamp" in data