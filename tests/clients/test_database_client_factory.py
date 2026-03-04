"""
Tests for Database Client Factory

This module tests the DatabaseClientFactory class and related configuration
management functionality for both local and AWS environments.
"""

import pytest
import asyncio
import os
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any

from src.multimodal_librarian.clients.database_client_factory import (
    DatabaseClientFactory, get_database_factory, close_global_factory, reset_global_factory
)
from src.multimodal_librarian.clients.protocols import (
    RelationalStoreClient, VectorStoreClient, GraphStoreClient,
    DatabaseClientError, ConnectionError, ConfigurationError, ValidationError
)
from src.multimodal_librarian.config.local_config import LocalDatabaseConfig
from src.multimodal_librarian.config.config_factory import get_database_config


class MockLocalPostgreSQLClient:
    """Mock local PostgreSQL client for testing."""
    
    def __init__(self, **kwargs):
        self.connection_params = kwargs
        self.connected = False
    
    async def connect(self):
        self.connected = True
    
    async def disconnect(self):
        self.connected = False
    
    async def health_check(self):
        return {"status": "healthy", "response_time": 0.05}


class MockMilvusClient:
    """Mock Milvus client for testing."""
    
    def __init__(self, **kwargs):
        self.connection_params = kwargs
        self.connected = False
    
    async def connect(self):
        self.connected = True
    
    async def disconnect(self):
        self.connected = False
    
    async def health_check(self):
        return {"status": "healthy", "response_time": 0.03}


class MockNeo4jClient:
    """Mock Neo4j client for testing."""
    
    def __init__(self, **kwargs):
        self.connection_params = kwargs
        self.connected = False
    
    async def connect(self):
        self.connected = True
    
    async def disconnect(self):
        self.connected = False
    
    async def health_check(self):
        return {"status": "healthy", "response_time": 0.04}


@pytest.fixture
def local_config():
    """Create a local database configuration for testing."""
    return LocalDatabaseConfig(
        postgres_host="localhost",
        postgres_port=5432,
        postgres_db="test_db",
        postgres_user="test_user",
        postgres_password="test_password",
        neo4j_host="localhost",
        neo4j_port=7687,
        neo4j_user="neo4j",
        neo4j_password="test_password",
        milvus_host="localhost",
        milvus_port=19530,
        enable_relational_db=True,
        enable_vector_search=True,
        enable_graph_db=True
    )


@pytest.fixture
def mock_aws_config():
    """Create a mock AWS configuration for testing."""
    config = Mock()
    config.database_type = "aws"
    config.connection_timeout = 60
    config.query_timeout = 30
    config.max_retries = 3
    config.enable_relational_db = True
    config.enable_vector_search = True
    config.enable_graph_db = True
    return config


@pytest.fixture
def factory_with_local_config(local_config):
    """Create a factory with local configuration."""
    return DatabaseClientFactory(local_config)


@pytest.fixture
def factory_with_aws_config(mock_aws_config):
    """Create a factory with AWS configuration."""
    return DatabaseClientFactory(mock_aws_config)


class TestDatabaseClientFactory:
    """Test cases for DatabaseClientFactory."""
    
    def test_factory_initialization_with_local_config(self, local_config):
        """Test factory initialization with local configuration."""
        factory = DatabaseClientFactory(local_config)
        
        assert factory.config == local_config
        assert factory.config.database_type == "local"
        assert not factory._closed
        assert len(factory._clients) == 0
    
    def test_factory_initialization_with_aws_config(self, mock_aws_config):
        """Test factory initialization with AWS configuration."""
        factory = DatabaseClientFactory(mock_aws_config)
        
        assert factory.config == mock_aws_config
        assert factory.config.database_type == "aws"
        assert not factory._closed
        assert len(factory._clients) == 0
    
    def test_factory_initialization_with_invalid_config(self):
        """Test factory initialization with invalid configuration."""
        invalid_config = Mock()
        # Missing database_type attribute
        
        with pytest.raises(ConfigurationError) as exc_info:
            DatabaseClientFactory(invalid_config)
        
        assert "database_type" in str(exc_info.value)
    
    def test_factory_initialization_with_invalid_database_type(self):
        """Test factory initialization with invalid database type."""
        invalid_config = Mock()
        invalid_config.database_type = "invalid"
        
        with pytest.raises(ValidationError) as exc_info:
            DatabaseClientFactory(invalid_config)
        
        assert "Invalid database_type" in str(exc_info.value)
    
    @patch('src.multimodal_librarian.clients.database_client_factory.LocalPostgreSQLClient')
    async def test_get_relational_client_local(self, mock_client_class, factory_with_local_config):
        """Test getting relational client for local environment."""
        mock_client = MockLocalPostgreSQLClient()
        mock_client_class.return_value = mock_client
        
        client = await factory_with_local_config.get_relational_client()
        
        assert client == mock_client
        assert mock_client.connected
        assert "relational" in factory_with_local_config._clients
        
        # Test caching - should return same instance
        client2 = await factory_with_local_config.get_relational_client()
        assert client2 == client
    
    @patch('src.multimodal_librarian.clients.database_client_factory.MilvusClient')
    async def test_get_vector_client_local(self, mock_client_class, factory_with_local_config):
        """Test getting vector client for local environment."""
        mock_client = MockMilvusClient()
        mock_client_class.return_value = mock_client
        
        client = await factory_with_local_config.get_vector_client()
        
        assert client == mock_client
        assert mock_client.connected
        assert "vector" in factory_with_local_config._clients
    
    @patch('src.multimodal_librarian.clients.database_client_factory.Neo4jClient')
    async def test_get_graph_client_local(self, mock_client_class, factory_with_local_config):
        """Test getting graph client for local environment."""
        mock_client = MockNeo4jClient()
        mock_client_class.return_value = mock_client
        
        client = await factory_with_local_config.get_graph_client()
        
        assert client == mock_client
        assert mock_client.connected
        assert "graph" in factory_with_local_config._clients
    
    async def test_get_client_when_disabled(self, local_config):
        """Test getting client when service is disabled."""
        local_config.enable_relational_db = False
        factory = DatabaseClientFactory(local_config)
        
        with pytest.raises(ConfigurationError) as exc_info:
            await factory.get_relational_client()
        
        assert "disabled" in str(exc_info.value)
    
    async def test_get_client_when_factory_closed(self, factory_with_local_config):
        """Test getting client when factory is closed."""
        await factory_with_local_config.close()
        
        with pytest.raises(DatabaseClientError) as exc_info:
            await factory_with_local_config.get_relational_client()
        
        assert "closed" in str(exc_info.value)
    
    @patch('src.multimodal_librarian.clients.database_client_factory.LocalPostgreSQLClient')
    async def test_client_creation_failure(self, mock_client_class, factory_with_local_config):
        """Test handling of client creation failure."""
        mock_client_class.side_effect = Exception("Connection failed")
        
        with pytest.raises(ConnectionError) as exc_info:
            await factory_with_local_config.get_relational_client()
        
        assert "Failed to create" in str(exc_info.value)
        assert "relational" not in factory_with_local_config._clients
    
    @patch('src.multimodal_librarian.clients.database_client_factory.LocalPostgreSQLClient')
    @patch('src.multimodal_librarian.clients.database_client_factory.MilvusClient')
    @patch('src.multimodal_librarian.clients.database_client_factory.Neo4jClient')
    async def test_health_check_all_healthy(self, mock_neo4j, mock_milvus, mock_postgres, factory_with_local_config):
        """Test health check when all services are healthy."""
        # Setup mocks
        mock_postgres.return_value = MockLocalPostgreSQLClient()
        mock_milvus.return_value = MockMilvusClient()
        mock_neo4j.return_value = MockNeo4jClient()
        
        health = await factory_with_local_config.health_check()
        
        assert health["overall_status"] == "healthy"
        assert health["database_type"] == "local"
        assert len(health["services"]) == 3
        assert all(service["status"] == "healthy" for service in health["services"].values())
    
    @patch('src.multimodal_librarian.clients.database_client_factory.LocalPostgreSQLClient')
    async def test_health_check_with_failure(self, mock_client_class, factory_with_local_config):
        """Test health check when one service fails."""
        # Disable other services to focus on one
        factory_with_local_config.config.enable_vector_search = False
        factory_with_local_config.config.enable_graph_db = False
        
        mock_client = MockLocalPostgreSQLClient()
        mock_client.health_check = AsyncMock(side_effect=Exception("Health check failed"))
        mock_client_class.return_value = mock_client
        
        health = await factory_with_local_config.health_check()
        
        assert health["overall_status"] == "unhealthy"
        assert health["services"]["relational"]["status"] == "unhealthy"
        assert "Health check failed" in health["services"]["relational"]["error"]
    
    def test_get_factory_stats(self, factory_with_local_config):
        """Test getting factory statistics."""
        stats = factory_with_local_config.get_factory_stats()
        
        assert stats["database_type"] == "local"
        assert stats["cached_clients"] == []
        assert not stats["closed"]
        assert "configuration" in stats
    
    @patch('src.multimodal_librarian.clients.database_client_factory.LocalPostgreSQLClient')
    @patch('src.multimodal_librarian.clients.database_client_factory.MilvusClient')
    @patch('src.multimodal_librarian.clients.database_client_factory.Neo4jClient')
    async def test_close_factory(self, mock_neo4j, mock_milvus, mock_postgres, factory_with_local_config):
        """Test closing the factory and cleaning up resources."""
        # Setup mocks
        mock_postgres.return_value = MockLocalPostgreSQLClient()
        mock_milvus.return_value = MockMilvusClient()
        mock_neo4j.return_value = MockNeo4jClient()
        
        # Create clients
        await factory_with_local_config.get_relational_client()
        await factory_with_local_config.get_vector_client()
        await factory_with_local_config.get_graph_client()
        
        assert len(factory_with_local_config._clients) == 3
        
        # Close factory
        await factory_with_local_config.close()
        
        assert factory_with_local_config._closed
        assert len(factory_with_local_config._clients) == 0
    
    @patch('src.multimodal_librarian.clients.database_client_factory.LocalPostgreSQLClient')
    @patch('src.multimodal_librarian.clients.database_client_factory.MilvusClient')
    @patch('src.multimodal_librarian.clients.database_client_factory.Neo4jClient')
    async def test_get_all_clients_context_manager(self, mock_neo4j, mock_milvus, mock_postgres, factory_with_local_config):
        """Test the get_all_clients context manager."""
        # Setup mocks
        mock_postgres.return_value = MockLocalPostgreSQLClient()
        mock_milvus.return_value = MockMilvusClient()
        mock_neo4j.return_value = MockNeo4jClient()
        
        async with factory_with_local_config.get_all_clients() as clients:
            assert "relational" in clients
            assert "vector" in clients
            assert "graph" in clients
            
            # All clients should be connected
            assert clients["relational"].connected
            assert clients["vector"].connected
            assert clients["graph"].connected
    
    async def test_get_all_clients_with_disabled_services(self, local_config):
        """Test get_all_clients with some services disabled."""
        local_config.enable_vector_search = False
        factory = DatabaseClientFactory(local_config)
        
        with patch('src.multimodal_librarian.clients.database_client_factory.LocalPostgreSQLClient') as mock_postgres, \
             patch('src.multimodal_librarian.clients.database_client_factory.Neo4jClient') as mock_neo4j:
            
            mock_postgres.return_value = MockLocalPostgreSQLClient()
            mock_neo4j.return_value = MockNeo4jClient()
            
            async with factory.get_all_clients() as clients:
                assert "relational" in clients
                assert "vector" not in clients  # Disabled
                assert "graph" in clients
    
    def test_factory_repr(self, factory_with_local_config):
        """Test factory string representation."""
        repr_str = repr(factory_with_local_config)
        
        assert "DatabaseClientFactory" in repr_str
        assert "database_type='local'" in repr_str
        assert "closed=False" in repr_str


class TestGlobalFactoryFunctions:
    """Test cases for global factory functions."""
    
    def setup_method(self):
        """Reset global factory before each test."""
        reset_global_factory()
    
    def teardown_method(self):
        """Clean up after each test."""
        reset_global_factory()
    
    def test_get_database_factory_with_config(self, local_config):
        """Test getting global factory with configuration."""
        factory = get_database_factory(local_config)
        
        assert isinstance(factory, DatabaseClientFactory)
        assert factory.config == local_config
        
        # Should return same instance on subsequent calls
        factory2 = get_database_factory()
        assert factory2 == factory
    
    def test_get_database_factory_without_config_fails(self):
        """Test getting global factory without configuration fails."""
        with pytest.raises(ConfigurationError):
            get_database_factory()
    
    def test_get_database_factory_with_new_config_replaces(self, local_config, mock_aws_config):
        """Test that providing new config replaces existing factory."""
        factory1 = get_database_factory(local_config)
        factory2 = get_database_factory(mock_aws_config)
        
        assert factory1 != factory2
        assert factory2.config == mock_aws_config
    
    async def test_close_global_factory(self, local_config):
        """Test closing global factory."""
        factory = get_database_factory(local_config)
        
        await close_global_factory()
        
        assert factory._closed
        
        # Should be able to create new factory after closing
        new_factory = get_database_factory(local_config)
        assert new_factory != factory
        assert not new_factory._closed
    
    async def test_close_global_factory_when_none_exists(self):
        """Test closing global factory when none exists."""
        # Should not raise an error
        await close_global_factory()
    
    def test_reset_global_factory(self, local_config):
        """Test resetting global factory."""
        factory1 = get_database_factory(local_config)
        reset_global_factory()
        
        # Should create new factory instance
        factory2 = get_database_factory(local_config)
        assert factory1 != factory2


class TestFactoryWithAWSConfig:
    """Test cases for factory with AWS configuration."""
    
    @patch('src.multimodal_librarian.clients.database_client_factory.AWSPostgreSQLClient')
    async def test_get_relational_client_aws(self, mock_client_class, factory_with_aws_config):
        """Test getting relational client for AWS environment."""
        mock_client = Mock()
        mock_client.connect = AsyncMock()
        mock_client_class.return_value = mock_client
        
        client = await factory_with_aws_config.get_relational_client()
        
        assert client == mock_client
        mock_client.connect.assert_called_once()
    
    @patch('src.multimodal_librarian.clients.database_client_factory.OpenSearchClient')
    async def test_get_vector_client_aws(self, mock_client_class, factory_with_aws_config):
        """Test getting vector client for AWS environment."""
        mock_client = Mock()
        mock_client.connect = AsyncMock()
        mock_client_class.return_value = mock_client
        
        client = await factory_with_aws_config.get_vector_client()
        
        assert client == mock_client
        mock_client.connect.assert_called_once()
    
    @patch('src.multimodal_librarian.clients.database_client_factory.NeptuneClient')
    async def test_get_graph_client_aws(self, mock_client_class, factory_with_aws_config):
        """Test getting graph client for AWS environment."""
        mock_client = Mock()
        mock_client.connect = AsyncMock()
        mock_client_class.return_value = mock_client
        
        client = await factory_with_aws_config.get_graph_client()
        
        assert client == mock_client
        mock_client.connect.assert_called_once()
    
    async def test_aws_client_import_error(self, factory_with_aws_config):
        """Test handling of AWS client import errors."""
        # AWS clients might not be available in local development
        with patch('src.multimodal_librarian.clients.database_client_factory.AWSPostgreSQLClient', side_effect=ImportError("AWS dependencies not available")):
            with pytest.raises(ConfigurationError) as exc_info:
                await factory_with_aws_config.get_relational_client()
            
            assert "AWS dependencies" in str(exc_info.value)


class TestFactoryErrorHandling:
    """Test cases for factory error handling."""
    
    def test_invalid_timeout_configuration(self):
        """Test factory with invalid timeout configuration."""
        config = Mock()
        config.database_type = "local"
        config.connection_timeout = -1  # Invalid
        
        with pytest.raises(ValidationError):
            DatabaseClientFactory(config)
    
    def test_invalid_query_timeout_configuration(self):
        """Test factory with invalid query timeout configuration."""
        config = Mock()
        config.database_type = "local"
        config.connection_timeout = 60
        config.query_timeout = 0  # Invalid
        
        with pytest.raises(ValidationError):
            DatabaseClientFactory(config)
    
    @patch('src.multimodal_librarian.clients.database_client_factory.LocalPostgreSQLClient')
    async def test_concurrent_client_creation(self, mock_client_class, factory_with_local_config):
        """Test concurrent client creation uses locking properly."""
        mock_client = MockLocalPostgreSQLClient()
        mock_client_class.return_value = mock_client
        
        # Create multiple concurrent requests for the same client
        tasks = [
            factory_with_local_config.get_relational_client(),
            factory_with_local_config.get_relational_client(),
            factory_with_local_config.get_relational_client()
        ]
        
        clients = await asyncio.gather(*tasks)
        
        # All should return the same cached instance
        assert all(client == clients[0] for client in clients)
        assert len(factory_with_local_config._clients) == 1
        
        # Client creation should only be called once due to caching
        mock_client_class.assert_called_once()


@pytest.mark.integration
class TestFactoryIntegration:
    """Integration tests for factory with real configuration."""
    
    def test_factory_with_real_local_config(self):
        """Test factory with real local configuration."""
        config = LocalDatabaseConfig()
        factory = DatabaseClientFactory(config)
        
        assert factory.config.database_type == "local"
        stats = factory.get_factory_stats()
        assert stats["database_type"] == "local"
    
    @patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'})
    def test_factory_with_config_from_environment(self):
        """Test factory with configuration from environment variables."""
        config = get_database_config()
        factory = DatabaseClientFactory(config)
        
        assert factory.config.database_type == "local"
    
    async def test_factory_health_check_with_no_clients(self, factory_with_local_config):
        """Test health check when no clients have been created yet."""
        # Disable all services to avoid client creation
        factory_with_local_config.config.enable_relational_db = False
        factory_with_local_config.config.enable_vector_search = False
        factory_with_local_config.config.enable_graph_db = False
        
        health = await factory_with_local_config.health_check()
        
        assert health["overall_status"] == "healthy"  # No services to check
        assert len(health["services"]) == 0