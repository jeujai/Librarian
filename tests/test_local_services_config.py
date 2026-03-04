"""
Tests for local services configuration.

This module tests that the test configuration for local services
is working correctly and that tests can connect to local services.
"""

import pytest
import os
import asyncio
from unittest.mock import patch

from tests.test_config_local import (
    LocalServiceTestConfig, 
    create_test_environment_patch,
    create_test_document_data,
    create_test_conversation_data,
    create_test_vector_data,
    create_test_graph_data,
)


class TestLocalServiceConfiguration:
    """Test local service configuration setup."""
    
    def test_local_service_config_creation(self):
        """Test that local service config can be created."""
        config = LocalServiceTestConfig()
        
        assert config.postgres_config['host'] == 'localhost'
        assert config.postgres_config['port'] == 5432
        assert config.postgres_config['database'] == 'multimodal_librarian_test'
        
        assert config.neo4j_config['host'] == 'localhost'
        assert config.neo4j_config['port'] == 7687
        
        assert config.milvus_config['host'] == 'localhost'
        assert config.milvus_config['port'] == 19530
        
        assert config.redis_config['host'] == 'localhost'
        assert config.redis_config['port'] == 6379
    
    def test_service_config_retrieval(self):
        """Test retrieving individual service configurations."""
        config = LocalServiceTestConfig()
        
        postgres_config = config.get_service_config('postgres')
        assert postgres_config['host'] == 'localhost'
        assert postgres_config['database'] == 'multimodal_librarian_test'
        
        neo4j_config = config.get_service_config('neo4j')
        assert neo4j_config['uri'] == 'bolt://localhost:7687'
        
        # Test invalid service
        invalid_config = config.get_service_config('invalid')
        assert invalid_config == {}
    
    def test_all_configs_retrieval(self):
        """Test retrieving all service configurations."""
        config = LocalServiceTestConfig()
        all_configs = config.get_all_configs()
        
        assert 'postgres' in all_configs
        assert 'neo4j' in all_configs
        assert 'milvus' in all_configs
        assert 'redis' in all_configs
        
        assert len(all_configs) == 4
    
    def test_environment_patch_creation(self):
        """Test creating environment variable patch."""
        env_patch = create_test_environment_patch()
        
        assert env_patch['ML_ENVIRONMENT'] == 'test'
        assert env_patch['ML_DATABASE_TYPE'] == 'local'
        assert env_patch['POSTGRES_DB'] == 'multimodal_librarian_test'
        assert env_patch['NEO4J_HOST'] == 'localhost'
        assert env_patch['MILVUS_HOST'] == 'localhost'
        assert env_patch['REDIS_HOST'] == 'localhost'
        
        # Check that external API keys are disabled
        assert env_patch['OPENAI_API_KEY'] == ''
        assert env_patch['GOOGLE_API_KEY'] == ''
        assert env_patch['ANTHROPIC_API_KEY'] == ''


class TestTestDataFactories:
    """Test the test data factory functions."""
    
    def test_document_data_factory(self):
        """Test document data factory."""
        doc_data = create_test_document_data()
        
        assert 'id' in doc_data
        assert 'title' in doc_data
        assert 'content' in doc_data
        assert 'metadata' in doc_data
        
        assert doc_data['id'] == 'test-doc-1'
        assert doc_data['title'] == 'Test Document'
        assert isinstance(doc_data['metadata'], dict)
        assert 'author' in doc_data['metadata']
    
    def test_conversation_data_factory(self):
        """Test conversation data factory."""
        conv_data = create_test_conversation_data()
        
        assert 'thread_id' in conv_data
        assert 'user_id' in conv_data
        assert 'messages' in conv_data
        
        assert conv_data['thread_id'] == 'test-thread-1'
        assert isinstance(conv_data['messages'], list)
        assert len(conv_data['messages']) == 2
        
        # Check message structure
        message = conv_data['messages'][0]
        assert 'id' in message
        assert 'content' in message
        assert 'role' in message
        assert 'timestamp' in message
    
    def test_vector_data_factory(self):
        """Test vector data factory."""
        vector_data = create_test_vector_data()
        
        assert 'id' in vector_data
        assert 'vector' in vector_data
        assert 'metadata' in vector_data
        
        assert vector_data['id'] == 'test-vector-1'
        assert isinstance(vector_data['vector'], list)
        assert len(vector_data['vector']) == 384  # Standard embedding dimension
        
        # Check metadata structure
        metadata = vector_data['metadata']
        assert 'document_id' in metadata
        assert 'chunk_index' in metadata
        assert 'text' in metadata
    
    def test_graph_data_factory(self):
        """Test graph data factory."""
        graph_data = create_test_graph_data()
        
        assert 'nodes' in graph_data
        assert 'relationships' in graph_data
        
        assert isinstance(graph_data['nodes'], list)
        assert isinstance(graph_data['relationships'], list)
        assert len(graph_data['nodes']) == 2
        assert len(graph_data['relationships']) == 1
        
        # Check node structure
        node = graph_data['nodes'][0]
        assert 'id' in node
        assert 'label' in node
        assert 'properties' in node
        
        # Check relationship structure
        rel = graph_data['relationships'][0]
        assert 'from' in rel
        assert 'to' in rel
        assert 'type' in rel
        assert 'properties' in rel


@pytest.mark.unit
class TestEnvironmentConfiguration:
    """Test environment configuration for tests."""
    
    def test_test_environment_fixture(self, test_environment):
        """Test that test environment fixture sets correct variables."""
        # Check that environment variables are set
        assert os.getenv('ML_ENVIRONMENT') == 'test'
        assert os.getenv('ML_DATABASE_TYPE') == 'local'
        assert os.getenv('DEBUG') == 'true'
        
        # Check database configuration
        assert os.getenv('POSTGRES_HOST') == 'localhost'
        assert os.getenv('POSTGRES_DB') == 'multimodal_librarian_test'
        assert os.getenv('NEO4J_HOST') == 'localhost'
        assert os.getenv('MILVUS_HOST') == 'localhost'
        assert os.getenv('REDIS_HOST') == 'localhost'
        assert os.getenv('REDIS_DB') == '1'
    
    def test_local_test_config_fixture(self, local_test_config):
        """Test that local test config fixture works."""
        if local_test_config is None:
            pytest.skip("Local test config not available")
        
        assert local_test_config.postgres_host == 'localhost'
        assert local_test_config.postgres_db == 'multimodal_librarian_test'
        assert local_test_config.neo4j_host == 'localhost'
        assert local_test_config.milvus_host == 'localhost'
        assert local_test_config.redis_host == 'localhost'
        assert local_test_config.redis_db == 1
        
        # Check test optimizations
        assert local_test_config.connection_timeout == 10
        assert local_test_config.query_timeout == 5
        assert local_test_config.max_retries == 1
        assert local_test_config.enable_health_checks is False
    
    def test_docker_compose_services_fixture(self, docker_compose_services):
        """Test that Docker Compose services fixture provides correct info."""
        assert 'postgres' in docker_compose_services
        assert 'neo4j' in docker_compose_services
        assert 'milvus' in docker_compose_services
        assert 'redis' in docker_compose_services
        
        # Check PostgreSQL config
        postgres_config = docker_compose_services['postgres']
        assert postgres_config['host'] == 'localhost'
        assert postgres_config['port'] == 5432
        assert postgres_config['database'] == 'multimodal_librarian_test'
        
        # Check Neo4j config
        neo4j_config = docker_compose_services['neo4j']
        assert neo4j_config['host'] == 'localhost'
        assert neo4j_config['port'] == 7687
        assert neo4j_config['uri'] == 'bolt://localhost:7687'


@pytest.mark.unit
class TestServiceAvailabilityChecks:
    """Test service availability checking utilities."""
    
    def test_check_service_availability_fixture(self, check_service_availability):
        """Test that service availability checker works."""
        check_service = check_service_availability['check_service']
        check_all_services = check_service_availability['check_all_services']
        
        # Test checking a service that should not be available
        # (using a port that's unlikely to be in use)
        assert check_service('localhost', 65432, timeout=0.1) is False
        
        # Test checking all services
        test_services = {
            'test_service': {'host': 'localhost', 'port': 65432}
        }
        results = check_all_services(test_services)
        assert 'test_service' in results
        assert results['test_service'] is False
    
    def test_skip_if_no_local_services_fixture(self, skip_if_no_local_services):
        """Test that skip fixture is callable."""
        # This should not raise an exception
        # The actual skipping behavior is tested in integration tests
        assert callable(skip_if_no_local_services)


@pytest.mark.integration
@pytest.mark.local_services
class TestLocalServiceIntegration:
    """Integration tests for local service configuration."""
    
    def test_service_connectivity(self, docker_compose_services, check_service_availability):
        """Test connectivity to local services."""
        check_service = check_service_availability['check_service']
        
        for service_name, config in docker_compose_services.items():
            # Try to connect to each service
            # This will be skipped if services are not running
            is_available = check_service(config['host'], config['port'], timeout=2.0)
            
            if is_available:
                print(f"✅ {service_name} is available at {config['host']}:{config['port']}")
            else:
                print(f"⚠️  {service_name} is not available at {config['host']}:{config['port']}")
    
    async def test_local_database_factory_creation(self, local_database_factory):
        """Test that local database factory can be created."""
        # This test will be skipped if local config is not available
        # or if the database factory cannot be imported
        
        assert local_database_factory is not None
        
        # Test factory stats
        stats = local_database_factory.get_factory_stats()
        assert stats['database_type'] == 'local'
        assert 'cached_clients' in stats
        assert 'closed' in stats
    
    async def test_local_postgres_client_creation(self, local_postgres_client):
        """Test that local PostgreSQL client can be created and connected."""
        # This test will be skipped if PostgreSQL is not available
        
        assert local_postgres_client is not None
        
        # Test basic health check
        health = await local_postgres_client.health_check()
        assert health is not None
        assert 'status' in health
    
    async def test_local_neo4j_client_creation(self, local_neo4j_client):
        """Test that local Neo4j client can be created and connected."""
        # This test will be skipped if Neo4j is not available
        
        assert local_neo4j_client is not None
        
        # Test basic health check
        health = await local_neo4j_client.health_check()
        assert health is not None
        assert 'status' in health
    
    async def test_local_milvus_client_creation(self, local_milvus_client):
        """Test that local Milvus client can be created and connected."""
        # This test will be skipped if Milvus is not available
        
        assert local_milvus_client is not None
        
        # Test basic health check
        health = await local_milvus_client.health_check()
        assert health is not None
        assert 'status' in health


class TestConfigurationValidation:
    """Test configuration validation for local services."""
    
    def test_configuration_completeness(self):
        """Test that all required configuration is present."""
        config = LocalServiceTestConfig()
        all_configs = config.get_all_configs()
        
        required_services = ['postgres', 'neo4j', 'milvus', 'redis']
        for service in required_services:
            assert service in all_configs
            service_config = all_configs[service]
            assert 'host' in service_config
            assert 'port' in service_config
            assert 'timeout' in service_config
    
    def test_test_database_names(self):
        """Test that test database names are different from production."""
        from tests.test_config_local import TEST_DATABASE_NAMES
        
        # Ensure test databases have different names
        assert TEST_DATABASE_NAMES['postgres'] == 'multimodal_librarian_test'
        assert TEST_DATABASE_NAMES['milvus'] == 'test_knowledge_chunks'
        assert TEST_DATABASE_NAMES['redis'] == 1  # Different Redis DB
        
        # Ensure they're not using production names
        assert TEST_DATABASE_NAMES['postgres'] != 'multimodal_librarian'
        assert TEST_DATABASE_NAMES['milvus'] != 'knowledge_chunks'
        assert TEST_DATABASE_NAMES['redis'] != 0
    
    def test_test_timeouts(self):
        """Test that test timeouts are reasonable."""
        from tests.test_config_local import TEST_TIMEOUTS
        
        assert TEST_TIMEOUTS['connection'] <= 10  # Fast for tests
        assert TEST_TIMEOUTS['query'] <= 5       # Fast for tests
        assert TEST_TIMEOUTS['health_check'] <= 3  # Very fast for tests
    
    def test_test_retry_settings(self):
        """Test that test retry settings are optimized for speed."""
        from tests.test_config_local import TEST_RETRY_SETTINGS
        
        assert TEST_RETRY_SETTINGS['max_retries'] == 1  # Minimal retries for tests
        assert TEST_RETRY_SETTINGS['retry_delay'] <= 0.1  # Fast retries
        assert TEST_RETRY_SETTINGS['backoff_factor'] == 1.0  # No exponential backoff