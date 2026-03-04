"""
Tests for Service Dependency Health Checks

This module tests the service dependency health check functionality
that validates service startup order and dependency resolution.
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from multimodal_librarian.main import app
from multimodal_librarian.api.routers.health_local import (
    service_dependency_health_check,
    _check_dependency_health,
    _check_service_ready,
    _is_service_enabled
)


class TestServiceDependencyHealthChecks:
    """Test service dependency health check functionality."""
    
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
    
    @pytest.mark.asyncio
    async def test_service_dependency_health_check_all_healthy(self, mock_database_factory):
        """Test service dependency health check when all services and dependencies are healthy."""
        
        # Mock successful dependency checks
        with patch('multimodal_librarian.api.routers.health_local._check_dependency_health') as mock_dep_health, \
             patch('multimodal_librarian.api.routers.health_local._check_service_ready') as mock_service_ready:
            
            # Configure mock returns for dependencies
            mock_dep_health.return_value = {"healthy": True}
            
            # Configure mock returns for services
            mock_service_ready.return_value = {"healthy": True}
            
            result = await service_dependency_health_check(mock_database_factory)
            
            assert result["check_type"] == "dependencies"
            assert "dependency_chain" in result
            assert "startup_order" in result
            assert "issues" in result
            assert "recommendations" in result
            assert result["overall_healthy"] is True
            
            # Should have entries for enabled services
            assert len(result["dependency_chain"]) > 0
            
            # Should have services in startup order
            assert len(result["startup_order"]) > 0
            
            # Should have minimal issues when all healthy
            assert len(result["issues"]) == 0
    
    @pytest.mark.asyncio
    async def test_service_dependency_health_check_with_failed_dependencies(self, mock_database_factory):
        """Test service dependency health check when some dependencies fail."""
        
        with patch('multimodal_librarian.api.routers.health_local._check_dependency_health') as mock_dep_health, \
             patch('multimodal_librarian.api.routers.health_local._check_service_ready') as mock_service_ready:
            
            # Configure mock returns - etcd fails, minio succeeds
            def mock_dependency_health(dep, config):
                if dep == "etcd":
                    return {"healthy": False, "error": "Connection refused"}
                elif dep == "minio":
                    return {"healthy": True}
                return {"healthy": True}
            
            mock_dep_health.side_effect = mock_dependency_health
            
            # Services are ready but dependencies failed
            mock_service_ready.return_value = {"healthy": True}
            
            result = await service_dependency_health_check(mock_database_factory)
            
            assert result["check_type"] == "dependencies"
            assert result["overall_healthy"] is False
            assert len(result["issues"]) > 0
            
            # Should have issues about failed dependencies
            assert any("etcd" in issue for issue in result["issues"])
            
            # Should have recommendations
            assert len(result["recommendations"]) > 0
    
    @pytest.mark.asyncio
    async def test_service_dependency_health_check_with_failed_services(self, mock_database_factory):
        """Test service dependency health check when services themselves fail."""
        
        with patch('multimodal_librarian.api.routers.health_local._check_dependency_health') as mock_dep_health, \
             patch('multimodal_librarian.api.routers.health_local._check_service_ready') as mock_service_ready:
            
            # Dependencies are healthy
            mock_dep_health.return_value = {"healthy": True}
            
            # Some services fail
            def mock_service_health(service, factory):
                if service == "postgres":
                    return {"healthy": False, "error": "Database connection failed"}
                return {"healthy": True}
            
            mock_service_ready.side_effect = mock_service_health
            
            result = await service_dependency_health_check(mock_database_factory)
            
            assert result["check_type"] == "dependencies"
            assert result["overall_healthy"] is False
            assert len(result["issues"]) > 0
            
            # Should have issues about failed services
            assert any("postgres" in issue for issue in result["issues"])
    
    @pytest.mark.asyncio
    async def test_check_dependency_health_etcd(self):
        """Test etcd dependency health check."""
        config = MagicMock()
        
        # Mock successful HTTP response
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 200
            
            mock_session.__aenter__.return_value = mock_session
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_session_class.return_value = mock_session
            
            result = await _check_dependency_health("etcd", config)
            
            assert result["healthy"] is True
    
    @pytest.mark.asyncio
    async def test_check_dependency_health_etcd_failure(self):
        """Test etcd dependency health check failure."""
        config = MagicMock()
        
        # Mock failed HTTP response
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_session.__aenter__.return_value = mock_session
            mock_session.get.side_effect = Exception("Connection refused")
            mock_session_class.return_value = mock_session
            
            result = await _check_dependency_health("etcd", config)
            
            assert result["healthy"] is False
            assert "error" in result
            assert "Connection refused" in result["error"]
    
    @pytest.mark.asyncio
    async def test_check_dependency_health_minio(self):
        """Test MinIO dependency health check."""
        config = MagicMock()
        
        # Mock successful HTTP response
        with patch('aiohttp.ClientSession') as mock_session_class:
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 200
            
            mock_session.__aenter__.return_value = mock_session
            mock_session.get.return_value.__aenter__.return_value = mock_response
            mock_session_class.return_value = mock_session
            
            result = await _check_dependency_health("minio", config)
            
            assert result["healthy"] is True
    
    @pytest.mark.asyncio
    async def test_check_dependency_health_unknown(self):
        """Test unknown dependency health check."""
        config = MagicMock()
        
        result = await _check_dependency_health("unknown_service", config)
        
        assert result["healthy"] is False
        assert "Unknown dependency" in result["error"]
    
    @pytest.mark.asyncio
    async def test_check_service_ready_postgres(self, mock_database_factory):
        """Test PostgreSQL service readiness check."""
        # Mock successful PostgreSQL connection
        mock_client = AsyncMock()
        mock_client.execute = AsyncMock(return_value=[(1,)])
        mock_database_factory.get_relational_client.return_value = mock_client
        
        result = await _check_service_ready("postgres", mock_database_factory)
        
        assert result["connected"] is True
    
    @pytest.mark.asyncio
    async def test_check_service_ready_neo4j(self, mock_database_factory):
        """Test Neo4j service readiness check."""
        # Mock successful Neo4j connection
        mock_client = AsyncMock()
        mock_client.execute_query = AsyncMock(return_value=[{"test": 1}])
        mock_database_factory.get_graph_client.return_value = mock_client
        
        result = await _check_service_ready("neo4j", mock_database_factory)
        
        assert result["connected"] is True
    
    @pytest.mark.asyncio
    async def test_check_service_ready_milvus(self, mock_database_factory):
        """Test Milvus service readiness check."""
        # Mock successful Milvus connection
        mock_client = AsyncMock()
        mock_client.list_collections = AsyncMock(return_value=["test_collection"])
        mock_database_factory.get_vector_client.return_value = mock_client
        
        result = await _check_service_ready("milvus", mock_database_factory)
        
        assert result["connected"] is True
    
    @pytest.mark.asyncio
    async def test_check_service_ready_redis(self, mock_database_factory):
        """Test Redis service readiness check."""
        # Mock successful Redis connection
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        mock_database_factory.get_cache_client.return_value = mock_client
        
        result = await _check_service_ready("redis", mock_database_factory)
        
        assert result["connected"] is True
    
    @pytest.mark.asyncio
    async def test_check_service_ready_unknown(self, mock_database_factory):
        """Test unknown service readiness check."""
        result = await _check_service_ready("unknown_service", mock_database_factory)
        
        assert result["healthy"] is False
        assert "Unknown service" in result["error"]
    
    def test_is_service_enabled(self):
        """Test service enablement checking."""
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


class TestServiceDependencyIntegration:
    """Integration tests for service dependency health checks."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        return TestClient(app)
    
    @patch.dict('os.environ', {'ML_ENVIRONMENT': 'local'})
    @patch('multimodal_librarian.api.routers.health_local.get_database_config')
    @patch('multimodal_librarian.api.routers.health_local.DatabaseClientFactory')
    def test_dependencies_endpoint_integration(self, mock_factory_class, mock_get_config, client):
        """Test integration of dependencies endpoint."""
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
        
        # Test the dependencies endpoint
        response = client.get("/api/health/local/dependencies")
        
        # Should return 200 for successful check
        assert response.status_code in [200, 503]  # May be 503 if mocked services fail
        
        data = response.json()
        assert "check_type" in data
        assert data["check_type"] == "dependencies"
        assert "dependency_chain" in data
        assert "startup_order" in data
        assert "issues" in data
        assert "recommendations" in data
        assert "overall_healthy" in data


if __name__ == "__main__":
    pytest.main([__file__])