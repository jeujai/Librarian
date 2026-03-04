"""
Tests for Local Development Health Check API

This module tests the comprehensive health check endpoints for local development
database services including PostgreSQL, Neo4j, Milvus, and Redis.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import HTTPException

from multimodal_librarian.main import app
from multimodal_librarian.api.routers.health_local import (
    get_local_database_factory,
    comprehensive_local_health_check,
    _check_postgres_health,
    _check_neo4j_health,
    _check_milvus_health,
    _check_redis_health
)


class TestLocalHealthCheckEndpoints:
    """Test local health check endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_local_config(self):
        """Mock local database configuration."""
        config = MagicMock()
        config.database_type = "local"
        config.enable_relational_db = True
        config.enable_graph_db = True
        config.enable_vector_search = True
        config.enable_redis_cache = True
        config.postgres_host = "localhost"
        config.postgres_port = 5432
        config.neo4j_host = "localhost"
        config.neo4j_port = 7687
        config.milvus_host = "localhost"
        config.milvus_port = 19530
        config.redis_host = "localhost"
        config.redis_port = 6379
        config.docker_compose_file = "docker-compose.local.yml"
        config.docker_network = "multimodal-librarian_default"
        return config
    
    @pytest.fixture
    def mock_database_factory(self, mock_local_config):
        """Mock database factory."""
        factory = MagicMock()
        factory.config = mock_local_config
        
        # Mock database clients
        factory.get_relational_client.return_value = AsyncMock()
        factory.get_graph_client.return_value = AsyncMock()
        factory.get_vector_client.return_value = AsyncMock()
        factory.get_cache_client.return_value = AsyncMock()
        
        return factory
    
    def test_health_local_endpoint_not_available_in_non_local_env(self, client):
        """Test that local health endpoints are not available in non-local environments."""
        with patch('multimodal_librarian.api.routers.health_local.get_database_config') as mock_get_config:
            # Mock non-local config
            config = MagicMock()
            config.database_type = "aws"
            mock_get_config.return_value = config
            
            response = client.get("/api/health/local/")
            assert response.status_code == 404
            assert "only available in local development environment" in response.json()["detail"]
    
    @patch('multimodal_librarian.api.routers.health_local.get_database_config')
    def test_get_local_database_factory_success(self, mock_get_config, mock_local_config):
        """Test successful creation of local database factory."""
        mock_get_config.return_value = mock_local_config
        
        # This should not raise an exception
        factory = asyncio.run(get_local_database_factory())
        assert factory is not None
    
    @patch('multimodal_librarian.api.routers.health_local.get_database_config')
    def test_get_local_database_factory_non_local_environment(self, mock_get_config):
        """Test that factory creation fails in non-local environment."""
        config = MagicMock()
        config.database_type = "aws"
        mock_get_config.return_value = config
        
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_local_database_factory())
        
        assert exc_info.value.status_code == 404
        assert "only available in local development environment" in str(exc_info.value.detail)
    
    @pytest.mark.asyncio
    async def test_comprehensive_local_health_check_all_healthy(self, mock_database_factory):
        """Test comprehensive health check when all services are healthy."""
        # Mock successful health checks
        with patch('multimodal_librarian.api.routers.health_local._check_postgres_health') as mock_postgres, \
             patch('multimodal_librarian.api.routers.health_local._check_neo4j_health') as mock_neo4j, \
             patch('multimodal_librarian.api.routers.health_local._check_milvus_health') as mock_milvus, \
             patch('multimodal_librarian.api.routers.health_local._check_redis_health') as mock_redis, \
             patch('multimodal_librarian.api.routers.health_local._get_docker_info') as mock_docker:
            
            # Configure mock returns
            mock_postgres.return_value = {"status": "healthy", "service": "postgres"}
            mock_neo4j.return_value = {"status": "healthy", "service": "neo4j"}
            mock_milvus.return_value = {"status": "healthy", "service": "milvus"}
            mock_redis.return_value = {"status": "healthy", "service": "redis"}
            mock_docker.return_value = {"containers": {}}
            
            response = await comprehensive_local_health_check(mock_database_factory)
            
            # Extract content from JSONResponse
            result = response.body.decode('utf-8')
            import json
            result_data = json.loads(result)
            
            assert result_data["overall_status"] == "healthy"
            assert result_data["summary"]["healthy_services"] == 4
            assert result_data["summary"]["all_healthy"] is True
            assert "postgres" in result_data["services"]
            assert "neo4j" in result_data["services"]
            assert "milvus" in result_data["services"]
            assert "redis" in result_data["services"]
    
    @pytest.mark.asyncio
    async def test_comprehensive_local_health_check_some_unhealthy(self, mock_database_factory):
        """Test comprehensive health check when some services are unhealthy."""
        with patch('multimodal_librarian.api.routers.health_local._check_postgres_health') as mock_postgres, \
             patch('multimodal_librarian.api.routers.health_local._check_neo4j_health') as mock_neo4j, \
             patch('multimodal_librarian.api.routers.health_local._check_milvus_health') as mock_milvus, \
             patch('multimodal_librarian.api.routers.health_local._check_redis_health') as mock_redis, \
             patch('multimodal_librarian.api.routers.health_local._get_docker_info') as mock_docker:
            
            # Configure mock returns - some healthy, some unhealthy
            mock_postgres.return_value = {"status": "healthy", "service": "postgres"}
            mock_neo4j.return_value = {"status": "unhealthy", "service": "neo4j", "error": "Connection failed"}
            mock_milvus.return_value = {"status": "healthy", "service": "milvus"}
            mock_redis.return_value = {"status": "degraded", "service": "redis", "issues": ["Slow response"]}
            mock_docker.return_value = {"containers": {}}
            
            response = await comprehensive_local_health_check(mock_database_factory)
            
            # Extract content from JSONResponse
            result = response.body.decode('utf-8')
            import json
            result_data = json.loads(result)
            
            assert result_data["overall_status"] in ["degraded", "critical"]
            assert result_data["summary"]["healthy_services"] == 2
            assert result_data["summary"]["unhealthy_services"] == 1
            assert result_data["summary"]["degraded_services"] == 1
            assert result_data["summary"]["all_healthy"] is False
    
    @pytest.mark.asyncio
    async def test_check_postgres_health_success(self, mock_database_factory):
        """Test PostgreSQL health check success."""
        # Mock successful PostgreSQL operations
        mock_client = AsyncMock()
        mock_client.execute.side_effect = [
            [(1,)],  # SELECT 1
            [("PostgreSQL 15.0",)],  # version()
            [("10 MB",)],  # database size
            [(5,)]  # connection count
        ]
        mock_database_factory.get_relational_client.return_value = mock_client
        
        result = await _check_postgres_health(mock_database_factory)
        
        assert result["service"] == "postgres"
        assert result["status"] == "healthy"
        assert "connectivity" in result["details"]
        assert "version" in result["details"]
        assert "connectivity_time_ms" in result["metrics"]
        assert len(result["issues"]) == 0
    
    @pytest.mark.asyncio
    async def test_check_postgres_health_failure(self, mock_database_factory):
        """Test PostgreSQL health check failure."""
        # Mock failed PostgreSQL connection
        mock_client = AsyncMock()
        mock_client.execute.side_effect = Exception("Connection refused")
        mock_database_factory.get_relational_client.return_value = mock_client
        
        result = await _check_postgres_health(mock_database_factory)
        
        assert result["service"] == "postgres"
        assert result["status"] == "unhealthy"
        assert "error" in result
        assert "Connection refused" in result["error"]
        assert len(result["issues"]) > 0
    
    @pytest.mark.asyncio
    async def test_check_neo4j_health_success(self, mock_database_factory):
        """Test Neo4j health check success."""
        # Mock successful Neo4j operations
        mock_client = AsyncMock()
        mock_client.execute_query.side_effect = [
            [{"test": 1}],  # RETURN 1
            [{"name": "Neo4j Kernel", "versions": ["5.15.0"]}],  # version info
            [{"nodeCount": 100, "relCount": 200}]  # stats
        ]
        mock_database_factory.get_graph_client.return_value = mock_client
        
        result = await _check_neo4j_health(mock_database_factory)
        
        assert result["service"] == "neo4j"
        assert result["status"] == "healthy"
        assert "connectivity" in result["details"]
        assert "version" in result["details"]
        assert "node_count" in result["metrics"]
        assert "relationship_count" in result["metrics"]
        assert len(result["issues"]) == 0
    
    @pytest.mark.asyncio
    async def test_check_milvus_health_success(self, mock_database_factory):
        """Test Milvus health check success."""
        # Mock successful Milvus operations
        mock_client = AsyncMock()
        mock_client.list_collections = AsyncMock(return_value=["documents", "embeddings"])
        mock_client.get_server_version = AsyncMock(return_value="2.3.4")
        mock_client.describe_collection = AsyncMock(return_value={"schema": {"fields": []}})
        mock_database_factory.get_vector_client.return_value = mock_client
        
        result = await _check_milvus_health(mock_database_factory)
        
        assert result["service"] == "milvus"
        assert result["status"] == "healthy"
        assert "connectivity" in result["details"]
        assert "version" in result["details"]
        assert result["metrics"]["collection_count"] == 2
        assert len(result["issues"]) == 0
    
    @pytest.mark.asyncio
    async def test_check_redis_health_success(self, mock_database_factory):
        """Test Redis health check success."""
        # Mock successful Redis operations
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_client.info = AsyncMock(return_value={
            "redis_version": "7.0.0",
            "used_memory_human": "1.5M",
            "connected_clients": 3,
            "total_commands_processed": 1000
        })
        mock_client.set = AsyncMock(return_value=True)
        mock_client.get = AsyncMock(return_value="test_value")
        mock_client.delete = AsyncMock(return_value=1)
        mock_database_factory.get_cache_client.return_value = mock_client
        
        result = await _check_redis_health(mock_database_factory)
        
        assert result["service"] == "redis"
        assert result["status"] == "healthy"
        assert "connectivity" in result["details"]
        assert "version" in result["details"]
        assert "used_memory" in result["metrics"]
        assert "connected_clients" in result["metrics"]
        assert len(result["issues"]) == 0


class TestLocalHealthCheckIntegration:
    """Integration tests for local health check endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @patch.dict('os.environ', {'ML_ENVIRONMENT': 'local'})
    @patch('multimodal_librarian.api.routers.health_local.get_database_config')
    @patch('multimodal_librarian.api.routers.health_local.DatabaseClientFactory')
    def test_local_health_endpoint_integration(self, mock_factory_class, mock_get_config, client):
        """Test integration of local health endpoint."""
        # Mock configuration
        config = MagicMock()
        config.database_type = "local"
        config.enable_relational_db = True
        config.enable_graph_db = True
        config.enable_vector_search = True
        config.enable_redis_cache = True
        mock_get_config.return_value = config
        
        # Mock factory and clients
        mock_factory = MagicMock()
        mock_factory.config = config
        mock_factory_class.return_value = mock_factory
        
        # Mock successful database operations
        mock_postgres = AsyncMock()
        mock_postgres.execute = AsyncMock(return_value=[(1,)])
        mock_factory.get_relational_client.return_value = mock_postgres
        
        mock_neo4j = AsyncMock()
        mock_neo4j.execute_query = AsyncMock(return_value=[{"test": 1}])
        mock_factory.get_graph_client.return_value = mock_neo4j
        
        mock_milvus = AsyncMock()
        mock_milvus.list_collections = AsyncMock(return_value=["test_collection"])
        mock_factory.get_vector_client.return_value = mock_milvus
        
        mock_redis = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)
        mock_factory.get_cache_client.return_value = mock_redis
        
        # Test the endpoint
        response = client.get("/api/health/local/")
        
        # Should return 200 for healthy services
        assert response.status_code in [200, 503]  # May be 503 if mocked services fail
        
        data = response.json()
        assert "environment" in data
        assert "overall_status" in data
        assert "services" in data
        assert "summary" in data
    
    @patch.dict('os.environ', {'ML_ENVIRONMENT': 'local'})
    @patch('multimodal_librarian.api.routers.health_local.get_database_config')
    def test_individual_service_endpoints(self, mock_get_config, client):
        """Test individual service health check endpoints."""
        # Mock configuration
        config = MagicMock()
        config.database_type = "local"
        mock_get_config.return_value = config
        
        # Test individual endpoints (they should at least not return 404)
        endpoints = [
            "/api/health/local/postgres",
            "/api/health/local/neo4j", 
            "/api/health/local/milvus",
            "/api/health/local/redis",
            "/api/health/local/connectivity",
            "/api/health/local/performance",
            "/api/health/local/dependencies"
        ]
        
        for endpoint in endpoints:
            response = client.get(endpoint)
            # Should not be 404 (endpoint exists) but may be 503 (service unavailable)
            assert response.status_code != 404, f"Endpoint {endpoint} returned 404"


class TestLocalHealthCheckHelpers:
    """Test helper functions for local health checks."""
    
    def test_is_service_enabled(self):
        """Test service enablement checking."""
        from multimodal_librarian.api.routers.health_local import _is_service_enabled
        
        config = MagicMock()
        config.enable_relational_db = True
        config.enable_graph_db = False
        config.enable_vector_search = True
        config.enable_redis_cache = False
        
        assert _is_service_enabled("postgres", config) is True
        assert _is_service_enabled("neo4j", config) is False
        assert _is_service_enabled("milvus", config) is True
        assert _is_service_enabled("redis", config) is False
        assert _is_service_enabled("unknown", config) is False
    
    def test_generate_health_recommendations(self):
        """Test health recommendation generation."""
        from multimodal_librarian.api.routers.health_local import _generate_health_recommendations
        
        # Test healthy status
        healthy_report = {
            "overall_status": "healthy",
            "services": {
                "postgres": {"status": "healthy"},
                "neo4j": {"status": "healthy"}
            },
            "docker_info": {"containers": {"postgres": {"status": "Up"}}}
        }
        
        recommendations = _generate_health_recommendations(healthy_report)
        assert "All services are healthy - no action needed" in recommendations
        
        # Test unhealthy status
        unhealthy_report = {
            "overall_status": "unhealthy",
            "services": {
                "postgres": {"status": "unhealthy"},
                "neo4j": {"status": "degraded", "issues": ["Slow response time"]}
            },
            "docker_info": {"error": "Docker not accessible"}
        }
        
        recommendations = _generate_health_recommendations(unhealthy_report)
        assert any("URGENT" in rec for rec in recommendations)
        assert any("PostgreSQL" in rec for rec in recommendations)
        assert any("Docker" in rec for rec in recommendations)


if __name__ == "__main__":
    pytest.main([__file__])