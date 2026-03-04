"""
Integration tests for Database Client Factory

This module tests the complete integration of the database client factory
with configuration management and environment detection.
"""

import pytest
import os
import asyncio
from unittest.mock import patch, Mock

from src.multimodal_librarian.config.config_factory import get_database_config, detect_environment
from src.multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
from src.multimodal_librarian.config.local_config import LocalDatabaseConfig


class TestDatabaseFactoryIntegration:
    """Integration tests for the complete database factory system."""
    
    def setup_method(self):
        """Reset environment before each test."""
        # Clear relevant environment variables
        env_vars_to_clear = [
            'ML_ENVIRONMENT', 'ML_DATABASE_TYPE', 'AWS_DEFAULT_REGION',
            'ML_POSTGRES_HOST', 'ML_NEO4J_HOST', 'ML_MILVUS_HOST'
        ]
        
        for var in env_vars_to_clear:
            os.environ.pop(var, None)
    
    def test_end_to_end_local_factory_creation(self):
        """Test complete end-to-end factory creation for local environment."""
        # Set environment for local development
        os.environ['ML_DATABASE_TYPE'] = 'local'
        
        # Get configuration via factory
        config = get_database_config('auto')
        
        # Create database client factory
        factory = DatabaseClientFactory(config)
        
        # Verify factory is properly configured
        assert factory.config.database_type == "local"
        assert isinstance(factory.config, LocalDatabaseConfig)
        
        # Verify factory stats
        stats = factory.get_factory_stats()
        assert stats['database_type'] == 'local'
        assert stats['cached_clients'] == []
        assert not stats['closed']
        
        # Verify configuration sections
        assert factory.config.enable_relational_db is True
        assert factory.config.enable_vector_search is True
        assert factory.config.enable_graph_db is True
    
    def test_environment_detection_and_config_creation(self):
        """Test environment detection leading to correct config creation."""
        # Test local environment detection
        os.environ['ML_POSTGRES_HOST'] = 'localhost'
        os.environ['ML_NEO4J_HOST'] = 'localhost'
        os.environ['ML_MILVUS_HOST'] = 'localhost'
        
        # Detect environment
        env_info = detect_environment()
        assert env_info.detected_type == "local"
        assert env_info.confidence > 0.5
        
        # Create config based on detection
        config = get_database_config('auto')
        assert config.database_type == "local"
        
        # Create factory
        factory = DatabaseClientFactory(config)
        assert factory.config.database_type == "local"
    
    def test_configuration_validation_integration(self):
        """Test that configuration validation works in the complete flow."""
        # Create config with custom settings
        config = LocalDatabaseConfig(
            postgres_host="test-postgres",
            neo4j_host="test-neo4j",
            milvus_host="test-milvus",
            connection_timeout=120
        )
        
        # Validate configuration
        validation = config.validate_configuration()
        assert validation['valid'] is True
        
        # Create factory with validated config
        factory = DatabaseClientFactory(config)
        
        # Verify factory uses the custom settings
        assert factory.config.postgres_host == "test-postgres"
        assert factory.config.neo4j_host == "test-neo4j"
        assert factory.config.milvus_host == "test-milvus"
        assert factory.config.connection_timeout == 120
    
    def test_factory_with_disabled_services(self):
        """Test factory behavior with some services disabled."""
        config = LocalDatabaseConfig(
            enable_relational_db=True,
            enable_vector_search=False,  # Disabled
            enable_graph_db=True
        )
        
        factory = DatabaseClientFactory(config)
        
        # Should be able to create factory even with disabled services
        assert factory.config.enable_relational_db is True
        assert factory.config.enable_vector_search is False
        assert factory.config.enable_graph_db is True
        
        stats = factory.get_factory_stats()
        assert stats['configuration']['enable_vector_search'] is False
    
    async def test_factory_health_check_integration(self):
        """Test factory health check with no actual clients."""
        config = LocalDatabaseConfig(
            # Disable all services to avoid actual client creation
            enable_relational_db=False,
            enable_vector_search=False,
            enable_graph_db=False
        )
        
        factory = DatabaseClientFactory(config)
        
        # Health check should work even with no services enabled
        health = await factory.health_check()
        
        assert health['database_type'] == 'local'
        assert health['overall_status'] == 'healthy'  # No services to fail
        assert len(health['services']) == 0
        assert 'timestamp' in health
        assert 'response_time' in health
    
    def test_multiple_factory_instances(self):
        """Test creating multiple factory instances with different configs."""
        # Create first factory with local config
        local_config = LocalDatabaseConfig(postgres_host="local-postgres")
        local_factory = DatabaseClientFactory(local_config)
        
        # Create second factory with different local config
        custom_config = LocalDatabaseConfig(postgres_host="custom-postgres")
        custom_factory = DatabaseClientFactory(custom_config)
        
        # Verify they are independent
        assert local_factory != custom_factory
        assert local_factory.config.postgres_host == "local-postgres"
        assert custom_factory.config.postgres_host == "custom-postgres"
    
    def test_factory_configuration_methods(self):
        """Test all configuration getter methods work correctly."""
        config = LocalDatabaseConfig()
        factory = DatabaseClientFactory(config)
        
        # Test all configuration methods
        relational_config = config.get_relational_db_config()
        graph_config = config.get_graph_db_config()
        vector_config = config.get_vector_db_config()
        health_config = config.get_health_check_config()
        monitoring_config = config.get_monitoring_config()
        docker_config = config.get_docker_config()
        
        # Verify all return dictionaries with expected keys
        assert isinstance(relational_config, dict)
        assert 'type' in relational_config
        assert relational_config['type'] == 'postgresql'
        
        assert isinstance(graph_config, dict)
        assert 'type' in graph_config
        assert graph_config['type'] == 'neo4j'
        
        assert isinstance(vector_config, dict)
        assert 'type' in vector_config
        assert vector_config['type'] == 'milvus'
        
        assert isinstance(health_config, dict)
        assert 'enabled' in health_config
        
        assert isinstance(monitoring_config, dict)
        assert 'query_logging' in monitoring_config
        
        assert isinstance(docker_config, dict)
        assert 'services' in docker_config
    
    def test_factory_error_handling(self):
        """Test factory error handling with invalid configurations."""
        # Test with invalid database type
        invalid_config = Mock()
        invalid_config.database_type = "invalid"
        
        with pytest.raises(Exception):  # Should raise ValidationError
            DatabaseClientFactory(invalid_config)
        
        # Test with missing database_type
        missing_config = Mock()
        # Remove database_type attribute
        if hasattr(missing_config, 'database_type'):
            delattr(missing_config, 'database_type')
        
        with pytest.raises(Exception):  # Should raise ConfigurationError
            DatabaseClientFactory(missing_config)
    
    async def test_factory_lifecycle_management(self):
        """Test complete factory lifecycle from creation to cleanup."""
        config = LocalDatabaseConfig()
        factory = DatabaseClientFactory(config)
        
        # Verify initial state
        assert not factory._closed
        assert len(factory._clients) == 0
        
        # Close factory
        await factory.close()
        
        # Verify closed state
        assert factory._closed
        assert len(factory._clients) == 0
        
        # Verify factory cannot be used after closing
        with pytest.raises(Exception):  # Should raise DatabaseClientError
            await factory.get_relational_client()
    
    def test_configuration_environment_variable_override(self):
        """Test that environment variables properly override configuration."""
        # Set environment variables
        test_env = {
            'ML_POSTGRES_HOST': 'env-postgres',
            'ML_POSTGRES_PORT': '5433',
            'ML_NEO4J_HOST': 'env-neo4j',
            'ML_MILVUS_HOST': 'env-milvus',
            'ML_CONNECTION_TIMEOUT': '90'
        }
        
        with patch.dict(os.environ, test_env):
            config = LocalDatabaseConfig()
            factory = DatabaseClientFactory(config)
            
            # Verify environment variables were used
            assert factory.config.postgres_host == "env-postgres"
            assert factory.config.postgres_port == 5433
            assert factory.config.neo4j_host == "env-neo4j"
            assert factory.config.milvus_host == "env-milvus"
            assert factory.config.connection_timeout == 90
    
    def test_factory_repr_and_string_methods(self):
        """Test factory string representation methods."""
        config = LocalDatabaseConfig()
        factory = DatabaseClientFactory(config)
        
        # Test __repr__
        repr_str = repr(factory)
        assert "DatabaseClientFactory" in repr_str
        assert "database_type='local'" in repr_str
        assert "closed=False" in repr_str
        
        # Test that repr is informative
        assert "cached_clients=[]" in repr_str


@pytest.mark.asyncio
class TestAsyncFactoryIntegration:
    """Async integration tests for database factory."""
    
    async def test_async_factory_operations(self):
        """Test async operations of the factory."""
        config = LocalDatabaseConfig(
            # Disable services to avoid actual connections
            enable_relational_db=False,
            enable_vector_search=False,
            enable_graph_db=False
        )
        
        factory = DatabaseClientFactory(config)
        
        try:
            # Test async health check
            health = await factory.health_check()
            assert isinstance(health, dict)
            assert 'overall_status' in health
            
            # Test async close
            await factory.close()
            assert factory._closed
            
        except Exception as e:
            # Clean up on error
            if not factory._closed:
                await factory.close()
            raise
    
    async def test_concurrent_factory_operations(self):
        """Test concurrent operations on the factory."""
        config = LocalDatabaseConfig(
            enable_relational_db=False,
            enable_vector_search=False,
            enable_graph_db=False
        )
        
        factory = DatabaseClientFactory(config)
        
        try:
            # Run multiple health checks concurrently
            health_checks = [
                factory.health_check(),
                factory.health_check(),
                factory.health_check()
            ]
            
            results = await asyncio.gather(*health_checks)
            
            # All should succeed and return similar results
            assert len(results) == 3
            for result in results:
                assert isinstance(result, dict)
                assert 'overall_status' in result
            
        finally:
            await factory.close()


class TestFactoryConfigurationCompatibility:
    """Test compatibility between different configuration approaches."""
    
    def test_config_factory_and_database_factory_integration(self):
        """Test integration between config factory and database factory."""
        # Use config factory to get configuration
        os.environ['ML_DATABASE_TYPE'] = 'local'
        config = get_database_config('auto')
        
        # Use database factory with the configuration
        factory = DatabaseClientFactory(config)
        
        # Verify they work together
        assert factory.config.database_type == 'local'
        assert isinstance(factory.config, LocalDatabaseConfig)
        
        # Verify configuration is properly validated
        validation = factory.config.validate_configuration()
        assert validation['valid'] is True
    
    def test_direct_config_and_factory_integration(self):
        """Test direct configuration creation with factory."""
        # Create configuration directly
        config = LocalDatabaseConfig(
            postgres_host="direct-postgres",
            neo4j_host="direct-neo4j"
        )
        
        # Use with factory
        factory = DatabaseClientFactory(config)
        
        # Verify integration
        assert factory.config.postgres_host == "direct-postgres"
        assert factory.config.neo4j_host == "direct-neo4j"
        
        # Verify factory methods work
        stats = factory.get_factory_stats()
        assert stats['database_type'] == 'local'