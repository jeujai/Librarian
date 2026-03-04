"""
Tests for factory-based dependency injection system.

This module tests the new factory-based dependencies that support both
local development and AWS production environments.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from fastapi import FastAPI, Depends, HTTPException

from multimodal_librarian.api.dependencies.services import (
    get_database_factory,
    get_database_factory_optional,
    get_relational_client,
    get_relational_client_optional,
    get_vector_client,
    get_vector_client_optional,
    get_graph_client,
    get_graph_client_optional,
    get_rag_service,
    get_cached_rag_service,
    get_vector_store,
    get_environment_info,
    is_factory_based_environment,
    migrate_to_factory_based,
    clear_all_caches,
)

# Configure pytest-asyncio
pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_local_config():
    """Mock local database configuration."""
    config = MagicMock()
    config.database_type = "local"
    config.enable_relational_db = True
    config.enable_vector_search = True
    config.enable_graph_db = True
    return config


@pytest.fixture
def mock_aws_config():
    """Mock AWS database configuration."""
    config = MagicMock()
    config.database_type = "aws"
    config.enable_relational_db = True
    config.enable_vector_search = True
    config.enable_graph_db = True
    return config


@pytest.fixture
def mock_database_factory():
    """Mock database client factory."""
    factory = MagicMock()
    factory.get_relational_client = AsyncMock()
    factory.get_vector_client = AsyncMock()
    factory.get_graph_client = AsyncMock()
    factory.close = AsyncMock()
    return factory


@pytest.fixture
def mock_clients():
    """Mock database clients."""
    relational_client = MagicMock()
    relational_client.connect = AsyncMock()
    relational_client.health_check = AsyncMock(return_value=True)
    
    vector_client = MagicMock()
    vector_client.connect = AsyncMock()
    vector_client.health_check = AsyncMock(return_value=True)
    
    graph_client = MagicMock()
    graph_client.connect = AsyncMock()
    graph_client.health_check = AsyncMock(return_value=True)
    
    return {
        "relational": relational_client,
        "vector": vector_client,
        "graph": graph_client
    }


@pytest.fixture(autouse=True)
def clear_dependency_cache():
    """Clear dependency cache before and after each test."""
    clear_all_caches()
    yield
    clear_all_caches()


class TestDatabaseFactory:
    """Test database factory dependency."""
    
    @patch('multimodal_librarian.api.dependencies.services.get_database_config')
    @patch('multimodal_librarian.clients.database_client_factory.DatabaseClientFactory')
    async def test_get_database_factory_success(self, mock_factory_class, mock_get_config, mock_local_config):
        """Test successful database factory creation."""
        mock_get_config.return_value = mock_local_config
        mock_factory_instance = MagicMock()
        mock_factory_class.return_value = mock_factory_instance
        
        factory = await get_database_factory()
        
        assert factory == mock_factory_instance
        mock_get_config.assert_called_once_with("auto")
        mock_factory_class.assert_called_once_with(mock_local_config)
    
    @patch('multimodal_librarian.api.dependencies.services.get_database_config')
    async def test_get_database_factory_failure(self, mock_get_config):
        """Test database factory creation failure."""
        mock_get_config.side_effect = Exception("Configuration error")
        
        with pytest.raises(HTTPException) as exc_info:
            await get_database_factory()
        
        assert exc_info.value.status_code == 503
        assert "Database factory service unavailable" in exc_info.value.detail
    
    @patch('multimodal_librarian.api.dependencies.services.get_database_factory')
    async def test_get_database_factory_optional_success(self, mock_get_factory, mock_database_factory):
        """Test optional database factory success."""
        mock_get_factory.return_value = mock_database_factory
        
        factory = await get_database_factory_optional()
        
        assert factory == mock_database_factory
    
    @patch('multimodal_librarian.api.dependencies.services.get_database_factory')
    async def test_get_database_factory_optional_failure(self, mock_get_factory):
        """Test optional database factory graceful failure."""
        mock_get_factory.side_effect = HTTPException(status_code=503, detail="Service unavailable")
        
        factory = await get_database_factory_optional()
        
        assert factory is None


class TestDatabaseClients:
    """Test database client dependencies."""
    
    async def test_get_relational_client_success(self, mock_database_factory, mock_clients):
        """Test successful relational client creation."""
        mock_database_factory.get_relational_client.return_value = mock_clients["relational"]
        
        with patch('multimodal_librarian.api.dependencies.services.get_database_factory', return_value=mock_database_factory):
            client = await get_relational_client()
        
        assert client == mock_clients["relational"]
        mock_database_factory.get_relational_client.assert_called_once()
    
    async def test_get_relational_client_failure(self, mock_database_factory):
        """Test relational client creation failure."""
        mock_database_factory.get_relational_client.side_effect = Exception("Connection failed")
        
        with patch('multimodal_librarian.api.dependencies.services.get_database_factory', return_value=mock_database_factory):
            with pytest.raises(HTTPException) as exc_info:
                await get_relational_client()
        
        assert exc_info.value.status_code == 503
        assert "Relational database service unavailable" in exc_info.value.detail
    
    async def test_get_vector_client_success(self, mock_database_factory, mock_clients):
        """Test successful vector client creation."""
        mock_database_factory.get_vector_client.return_value = mock_clients["vector"]
        
        with patch('multimodal_librarian.api.dependencies.services.get_database_factory', return_value=mock_database_factory):
            client = await get_vector_client()
        
        assert client == mock_clients["vector"]
        mock_database_factory.get_vector_client.assert_called_once()
    
    async def test_get_graph_client_success(self, mock_database_factory, mock_clients):
        """Test successful graph client creation."""
        mock_database_factory.get_graph_client.return_value = mock_clients["graph"]
        
        with patch('multimodal_librarian.api.dependencies.services.get_database_factory', return_value=mock_database_factory):
            client = await get_graph_client()
        
        assert client == mock_clients["graph"]
        mock_database_factory.get_graph_client.assert_called_once()
    
    async def test_optional_clients_graceful_degradation(self):
        """Test that optional clients return None when factory is unavailable."""
        with patch('multimodal_librarian.api.dependencies.services.get_database_factory_optional', return_value=None):
            relational_client = await get_relational_client_optional()
            vector_client = await get_vector_client_optional()
            graph_client = await get_graph_client_optional()
        
        assert relational_client is None
        assert vector_client is None
        assert graph_client is None


class TestRAGServiceIntegration:
    """Test RAG service integration with factory-based clients."""
    
    @patch('multimodal_librarian.api.dependencies.services.get_ai_service')
    @patch('multimodal_librarian.api.dependencies.services.get_vector_client_optional')
    async def test_get_rag_service_with_factory_client(self, mock_get_vector_client, mock_get_ai_service, mock_clients):
        """Test RAG service creation with factory-based vector client."""
        mock_get_vector_client.return_value = mock_clients["vector"]
        mock_ai_service = MagicMock()
        mock_get_ai_service.return_value = mock_ai_service
        
        with patch('multimodal_librarian.api.dependencies.services.RAGService') as mock_rag_class:
            mock_rag_instance = MagicMock()
            mock_rag_class.return_value = mock_rag_instance
            
            rag_service = await get_rag_service()
        
        assert rag_service == mock_rag_instance
        mock_rag_class.assert_called_once_with(
            vector_client=mock_clients["vector"],
            ai_service=mock_ai_service
        )
    
    @patch('multimodal_librarian.api.dependencies.services.get_ai_service')
    @patch('multimodal_librarian.api.dependencies.services.get_vector_client_optional')
    async def test_get_rag_service_no_vector_client(self, mock_get_vector_client, mock_get_ai_service):
        """Test RAG service graceful degradation when vector client unavailable."""
        mock_get_vector_client.return_value = None
        mock_ai_service = MagicMock()
        mock_get_ai_service.return_value = mock_ai_service
        
        rag_service = await get_rag_service()
        
        assert rag_service is None
    
    @patch('multimodal_librarian.api.dependencies.services.get_ai_service')
    @patch('multimodal_librarian.api.dependencies.services.get_vector_client_optional')
    async def test_get_cached_rag_service_with_factory_client(self, mock_get_vector_client, mock_get_ai_service, mock_clients):
        """Test cached RAG service creation with factory-based vector client."""
        mock_get_vector_client.return_value = mock_clients["vector"]
        mock_ai_service = MagicMock()
        mock_get_ai_service.return_value = mock_ai_service
        
        with patch('multimodal_librarian.api.dependencies.services.CachedRAGService') as mock_cached_rag_class:
            mock_cached_rag_instance = MagicMock()
            mock_cached_rag_class.return_value = mock_cached_rag_instance
            
            cached_rag_service = await get_cached_rag_service()
        
        assert cached_rag_service == mock_cached_rag_instance
        mock_cached_rag_class.assert_called_once_with(
            vector_client=mock_clients["vector"],
            ai_service=mock_ai_service
        )


class TestVectorStoreIntegration:
    """Test VectorStore integration with factory-based clients."""
    
    @patch('multimodal_librarian.api.dependencies.services.get_vector_client')
    async def test_get_vector_store_with_factory_client(self, mock_get_vector_client, mock_clients):
        """Test VectorStore creation with factory-based vector client."""
        mock_get_vector_client.return_value = mock_clients["vector"]
        
        with patch('multimodal_librarian.api.dependencies.services.VectorStore') as mock_vector_store_class:
            mock_vector_store_instance = MagicMock()
            mock_vector_store_instance.connect = MagicMock()
            mock_vector_store_class.return_value = mock_vector_store_instance
            
            vector_store = await get_vector_store()
        
        assert vector_store == mock_vector_store_instance
        mock_vector_store_class.assert_called_once_with(vector_client=mock_clients["vector"])
        mock_vector_store_instance.connect.assert_called_once()


class TestEnvironmentHelpers:
    """Test environment detection and migration helpers."""
    
    @patch('multimodal_librarian.api.dependencies.services.detect_environment')
    def test_get_environment_info(self, mock_detect_environment):
        """Test environment information retrieval."""
        mock_env_info = MagicMock()
        mock_env_info.detected_type = "local"
        mock_detect_environment.return_value = mock_env_info
        
        with patch('multimodal_librarian.api.dependencies.services.get_database_config') as mock_get_config:
            mock_config = MagicMock()
            mock_config.enable_relational_db = True
            mock_config.enable_vector_search = True
            mock_config.enable_graph_db = False
            mock_get_config.return_value = mock_config
            
            info = get_environment_info()
        
        assert info["detected_environment"] == "local"
        assert "relational" in info["available_clients"]
        assert "vector" in info["available_clients"]
        assert "graph" not in info["available_clients"]
    
    @patch('multimodal_librarian.api.dependencies.services.detect_environment')
    def test_is_factory_based_environment(self, mock_detect_environment):
        """Test factory-based environment detection."""
        mock_env_info = MagicMock()
        mock_env_info.confidence = 0.8
        mock_detect_environment.return_value = mock_env_info
        
        result = is_factory_based_environment()
        
        assert result is True
        
        # Test low confidence
        mock_env_info.confidence = 0.3
        result = is_factory_based_environment()
        
        assert result is False
    
    @patch('multimodal_librarian.api.dependencies.services.get_database_factory')
    @patch('multimodal_librarian.api.dependencies.services.get_relational_client_optional')
    @patch('multimodal_librarian.api.dependencies.services.get_vector_client_optional')
    @patch('multimodal_librarian.api.dependencies.services.get_graph_client_optional')
    async def test_migrate_to_factory_based_success(
        self, mock_get_graph, mock_get_vector, mock_get_relational, mock_get_factory,
        mock_database_factory, mock_clients
    ):
        """Test successful migration to factory-based dependencies."""
        mock_get_factory.return_value = mock_database_factory
        mock_get_relational.return_value = mock_clients["relational"]
        mock_get_vector.return_value = mock_clients["vector"]
        mock_get_graph.return_value = mock_clients["graph"]
        
        result = await migrate_to_factory_based()
        
        assert result["success"] is True
        assert "database_factory" in result["initialized_clients"]
        assert "relational" in result["initialized_clients"]
        assert "vector" in result["initialized_clients"]
        assert "graph" in result["initialized_clients"]
        assert len(result["errors"]) == 0
    
    @patch('multimodal_librarian.api.dependencies.services.get_database_factory')
    async def test_migrate_to_factory_based_failure(self, mock_get_factory):
        """Test migration failure when factory initialization fails."""
        mock_get_factory.side_effect = Exception("Factory initialization failed")
        
        result = await migrate_to_factory_based()
        
        assert result["success"] is False
        assert len(result["errors"]) > 0
        assert "Failed to initialize database factory" in result["errors"][0]


class TestEndToEndIntegration:
    """Test end-to-end integration with FastAPI."""
    
    def test_fastapi_integration(self, mock_database_factory, mock_clients):
        """Test that factory-based dependencies work in FastAPI endpoints."""
        app = FastAPI()
        
        @app.get("/test-relational")
        async def test_relational(client = Depends(get_relational_client_optional)):
            if client is None:
                return {"status": "unavailable"}
            return {"status": "available", "client_type": type(client).__name__}
        
        @app.get("/test-vector")
        async def test_vector(client = Depends(get_vector_client_optional)):
            if client is None:
                return {"status": "unavailable"}
            return {"status": "available", "client_type": type(client).__name__}
        
        @app.get("/test-graph")
        async def test_graph(client = Depends(get_graph_client_optional)):
            if client is None:
                return {"status": "unavailable"}
            return {"status": "available", "client_type": type(client).__name__}
        
        # Test with mocked dependencies
        app.dependency_overrides[get_relational_client_optional] = lambda: mock_clients["relational"]
        app.dependency_overrides[get_vector_client_optional] = lambda: mock_clients["vector"]
        app.dependency_overrides[get_graph_client_optional] = lambda: mock_clients["graph"]
        
        with TestClient(app) as client:
            # Test relational endpoint
            response = client.get("/test-relational")
            assert response.status_code == 200
            assert response.json()["status"] == "available"
            
            # Test vector endpoint
            response = client.get("/test-vector")
            assert response.status_code == 200
            assert response.json()["status"] == "available"
            
            # Test graph endpoint
            response = client.get("/test-graph")
            assert response.status_code == 200
            assert response.json()["status"] == "available"
        
        # Clean up overrides
        app.dependency_overrides.clear()
    
    def test_graceful_degradation_in_fastapi(self):
        """Test graceful degradation when clients are unavailable."""
        app = FastAPI()
        
        @app.get("/test-optional")
        async def test_optional(
            relational = Depends(get_relational_client_optional),
            vector = Depends(get_vector_client_optional),
            graph = Depends(get_graph_client_optional)
        ):
            return {
                "relational_available": relational is not None,
                "vector_available": vector is not None,
                "graph_available": graph is not None
            }
        
        # Test with no dependencies available
        app.dependency_overrides[get_relational_client_optional] = lambda: None
        app.dependency_overrides[get_vector_client_optional] = lambda: None
        app.dependency_overrides[get_graph_client_optional] = lambda: None
        
        with TestClient(app) as client:
            response = client.get("/test-optional")
            assert response.status_code == 200
            data = response.json()
            assert data["relational_available"] is False
            assert data["vector_available"] is False
            assert data["graph_available"] is False
        
        # Clean up overrides
        app.dependency_overrides.clear()


if __name__ == "__main__":
    pytest.main([__file__])