"""
Integration tests for local development setup.

This module tests the complete integration of the local development environment
including Docker services, database connectivity, and application functionality.
"""

import pytest
import asyncio
import os
import time
import subprocess
from typing import Dict, Any, Optional
from unittest.mock import patch

from src.multimodal_librarian.config.local_config import LocalDatabaseConfig
from src.multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
from src.multimodal_librarian.config.config_factory import get_database_config


class TestLocalSetupIntegration:
    """Integration tests for local development setup."""
    
    @pytest.fixture(scope="class")
    def local_config(self):
        """Create local configuration for testing."""
        return LocalDatabaseConfig.create_test_config(
            postgres_host="localhost",
            neo4j_host="localhost", 
            milvus_host="localhost",
            redis_host="localhost"
        )
    
    @pytest.fixture(scope="class")
    def database_factory(self, local_config):
        """Create database factory with local configuration."""
        return DatabaseClientFactory(local_config)
    
    def test_local_configuration_creation(self, local_config):
        """Test that local configuration is created correctly."""
        assert local_config.database_type == "local"
        assert local_config.postgres_host == "localhost"
        assert local_config.neo4j_host == "localhost"
        assert local_config.milvus_host == "localhost"
        assert local_config.redis_host == "localhost"
    
    def test_configuration_validation(self, local_config):
        """Test configuration validation for local setup."""
        validation = local_config.validate_configuration()
        
        # Should be valid for test configuration
        assert validation["valid"] is True
        assert validation["backend"] == "local"
        assert "config" in validation
        
        # Check that all expected configuration sections are present
        config = validation["config"]
        assert "relational_db" in config
        assert "graph_db" in config
        assert "vector_db" in config
        assert "application" in config
        assert "storage" in config
        assert "development" in config
        assert "health_check" in config
        assert "monitoring" in config
        assert "docker" in config
    
    def test_database_factory_creation(self, database_factory):
        """Test database factory creation with local configuration."""
        assert database_factory is not None
        assert database_factory.config.database_type == "local"
        
        # Test factory stats
        stats = database_factory.get_factory_stats()
        assert stats["database_type"] == "local"
        assert "cached_clients" in stats
        assert "closed" in stats
        assert stats["closed"] is False
    
    def test_connection_string_generation(self, local_config):
        """Test connection string generation for local services."""
        # PostgreSQL connection strings
        async_conn = local_config.get_postgres_connection_string(async_driver=True)
        sync_conn = local_config.get_postgres_connection_string(async_driver=False)
        
        assert "postgresql+asyncpg://" in async_conn
        assert "postgresql+psycopg2://" in sync_conn
        assert "localhost:5432" in async_conn
        assert "localhost:5432" in sync_conn
        
        # Neo4j URI
        neo4j_uri = local_config.get_neo4j_uri()
        assert neo4j_uri.startswith("bolt://")
        assert "localhost:7687" in neo4j_uri
        
        # Milvus URI
        milvus_uri = local_config.get_milvus_uri()
        assert milvus_uri.startswith("milvus://")
        assert "localhost:19530" in milvus_uri
        
        # Redis connection string
        redis_conn = local_config.get_redis_connection_string()
        assert redis_conn.startswith("redis://")
        assert "localhost:6379" in redis_conn
    
    def test_service_configuration_methods(self, local_config):
        """Test all service configuration methods."""
        # Test relational DB config
        postgres_config = local_config.get_relational_db_config()
        assert postgres_config["type"] == "postgresql"
        assert postgres_config["host"] == "localhost"
        assert postgres_config["port"] == 5432
        assert "connection_string" in postgres_config
        assert "pool_config" in postgres_config
        
        # Test graph DB config
        neo4j_config = local_config.get_graph_db_config()
        assert neo4j_config["type"] == "neo4j"
        assert neo4j_config["host"] == "localhost"
        assert neo4j_config["port"] == 7687
        assert "uri" in neo4j_config
        assert "pool_config" in neo4j_config
        
        # Test vector DB config
        milvus_config = local_config.get_vector_db_config()
        assert milvus_config["type"] == "milvus"
        assert milvus_config["host"] == "localhost"
        assert milvus_config["port"] == 19530
        assert "connection_config" in milvus_config
        assert "pool_config" in milvus_config
        
        # Test Redis config
        redis_config = local_config.get_redis_config()
        assert redis_config["type"] == "redis"
        assert redis_config["host"] == "localhost"
        assert redis_config["port"] == 6379
        assert "connection_config" in redis_config
    
    def test_docker_configuration(self, local_config):
        """Test Docker-related configuration."""
        docker_config = local_config.get_docker_config()
        
        assert "network" in docker_config
        assert "compose_file" in docker_config
        assert "services" in docker_config
        
        services = docker_config["services"]
        assert "postgres" in services
        assert "neo4j" in services
        assert "milvus" in services
        assert "redis" in services
        
        # Check service configurations
        for service_name, service_config in services.items():
            assert "container_name" in service_config
            assert "health_check_url" in service_config
    
    def test_health_check_configuration(self, local_config):
        """Test health check configuration."""
        health_config = local_config.get_health_check_config()
        
        assert "enabled" in health_config
        assert "interval" in health_config
        assert "timeout" in health_config
        assert "retries" in health_config
        
        # Check service-specific health checks
        assert "relational_db_enabled" in health_config
        assert "vector_search_enabled" in health_config
        assert "graph_db_enabled" in health_config
        assert "redis_cache_enabled" in health_config
    
    def test_monitoring_configuration(self, local_config):
        """Test monitoring configuration."""
        monitoring_config = local_config.get_monitoring_config()
        
        assert "query_logging" in monitoring_config
        assert "performance_tracking" in monitoring_config
        assert "error_tracking" in monitoring_config
        assert "metrics_enabled" in monitoring_config
        assert "log_level" in monitoring_config
    
    def test_development_configuration(self, local_config):
        """Test development-specific configuration."""
        dev_config = local_config.get_development_config()
        
        assert "hot_reload" in dev_config
        assert "watchdog_enabled" in dev_config
        assert "reload_dirs" in dev_config
        assert "reload_delay" in dev_config
        assert "debug" in dev_config
        assert "log_level" in dev_config
    
    def test_storage_configuration(self, local_config):
        """Test storage configuration."""
        storage_config = local_config.get_storage_config()
        
        assert "upload_dir" in storage_config
        assert "media_dir" in storage_config
        assert "export_dir" in storage_config
        assert "backup_dir" in storage_config
        assert "log_dir" in storage_config
        assert "max_file_size" in storage_config
        assert "max_files_per_upload" in storage_config
    
    def test_application_configuration(self, local_config):
        """Test application configuration."""
        app_config = local_config.get_application_config()
        
        assert "host" in app_config
        assert "port" in app_config
        assert "workers" in app_config
        assert "debug" in app_config
        assert "log_level" in app_config
        assert "secret_key" in app_config
        assert "require_auth" in app_config
    
    async def test_factory_health_check(self, database_factory):
        """Test factory health check functionality."""
        # This test doesn't require actual database connections
        # since we're using test configuration with services disabled
        health = await database_factory.health_check()
        
        assert isinstance(health, dict)
        assert "database_type" in health
        assert "overall_status" in health
        assert "services" in health
        assert "timestamp" in health
        assert "response_time" in health
        
        assert health["database_type"] == "local"
    
    def test_environment_variable_override(self):
        """Test that environment variables properly override configuration."""
        test_env = {
            'ML_POSTGRES_HOST': 'test-postgres',
            'ML_POSTGRES_PORT': '5433',
            'ML_NEO4J_HOST': 'test-neo4j',
            'ML_MILVUS_HOST': 'test-milvus',
            'ML_REDIS_HOST': 'test-redis',
            'ML_CONNECTION_TIMEOUT': '90'
        }
        
        with patch.dict(os.environ, test_env):
            config = LocalDatabaseConfig()
            
            assert config.postgres_host == "test-postgres"
            assert config.postgres_port == 5433
            assert config.neo4j_host == "test-neo4j"
            assert config.milvus_host == "test-milvus"
            assert config.redis_host == "test-redis"
            assert config.connection_timeout == 90
    
    def test_config_factory_integration(self):
        """Test integration with config factory."""
        with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'}):
            config = get_database_config('auto')
            
            assert config.database_type == 'local'
            assert isinstance(config, LocalDatabaseConfig)
    
    def test_configuration_serialization(self, local_config):
        """Test configuration can be serialized and deserialized."""
        # Test that configuration can be converted to dict
        config_dict = local_config.model_dump()
        
        assert isinstance(config_dict, dict)
        assert config_dict["database_type"] == "local"
        assert "postgres_host" in config_dict
        assert "neo4j_host" in config_dict
        assert "milvus_host" in config_dict
        
        # Test that configuration can be recreated from dict
        new_config = LocalDatabaseConfig(**config_dict)
        assert new_config.database_type == local_config.database_type
        assert new_config.postgres_host == local_config.postgres_host
    
    async def test_factory_lifecycle(self, database_factory):
        """Test complete factory lifecycle."""
        # Test initial state
        assert not database_factory._closed
        
        # Test health check
        health = await database_factory.health_check()
        assert health["overall_status"] in ["healthy", "partial", "unhealthy"]
        
        # Test closing
        await database_factory.close()
        assert database_factory._closed
        
        # Test that factory cannot be used after closing
        with pytest.raises(Exception):
            await database_factory.health_check()


@pytest.mark.asyncio
class TestAsyncLocalSetupIntegration:
    """Async integration tests for local setup."""
    
    async def test_concurrent_configuration_access(self):
        """Test concurrent access to configuration."""
        async def create_config():
            return LocalDatabaseConfig.create_test_config()
        
        # Create multiple configurations concurrently
        configs = await asyncio.gather(*[create_config() for _ in range(5)])
        
        # All should be valid and independent
        assert len(configs) == 5
        for config in configs:
            assert config.database_type == "local"
    
    async def test_concurrent_factory_operations(self):
        """Test concurrent factory operations."""
        config = LocalDatabaseConfig.create_test_config()
        factory = DatabaseClientFactory(config)
        
        try:
            # Run multiple health checks concurrently
            health_checks = [factory.health_check() for _ in range(3)]
            results = await asyncio.gather(*health_checks)
            
            # All should succeed
            assert len(results) == 3
            for result in results:
                assert isinstance(result, dict)
                assert "overall_status" in result
        finally:
            await factory.close()


class TestLocalSetupConnectivity:
    """Tests for local setup connectivity (when services are available)."""
    
    def test_connectivity_validation_structure(self):
        """Test connectivity validation returns proper structure."""
        config = LocalDatabaseConfig.create_test_config()
        
        # Test connectivity validation (will fail but structure should be correct)
        connectivity = config.validate_connectivity(timeout=1)
        
        assert isinstance(connectivity, dict)
        assert "overall_status" in connectivity
        assert "services" in connectivity
        assert "errors" in connectivity
        assert "warnings" in connectivity
        
        # Status should be one of the expected values
        assert connectivity["overall_status"] in ["healthy", "partial", "unhealthy", "unknown"]
    
    def test_docker_environment_validation_structure(self):
        """Test Docker environment validation returns proper structure."""
        config = LocalDatabaseConfig.create_test_config()
        
        # Test Docker validation (may fail but structure should be correct)
        docker_validation = config.validate_docker_environment()
        
        assert isinstance(docker_validation, dict)
        assert "docker_available" in docker_validation
        assert "compose_available" in docker_validation
        assert "compose_file_exists" in docker_validation
        assert "services_status" in docker_validation
        assert "errors" in docker_validation
        assert "warnings" in docker_validation
    
    def test_comprehensive_validation(self):
        """Test comprehensive configuration validation."""
        config = LocalDatabaseConfig.create_test_config()
        
        # Test validation and fix
        validation_result = config.validate_and_fix_configuration()
        
        assert isinstance(validation_result, dict)
        assert "validation" in validation_result
        assert "fixes_applied" in validation_result
        assert "fixes_failed" in validation_result
        assert "recommendations" in validation_result
        
        # Validation should have proper structure
        validation = validation_result["validation"]
        assert "valid" in validation
        assert "backend" in validation
        assert validation["backend"] == "local"


class TestLocalSetupEnvironmentInfo:
    """Tests for local setup environment information."""
    
    def test_environment_info(self):
        """Test environment information gathering."""
        config = LocalDatabaseConfig.create_test_config()
        
        env_info = config.get_environment_info()
        
        assert isinstance(env_info, dict)
        assert env_info["backend_type"] == "local"
        assert "environment" in env_info
        assert "services" in env_info
        assert "docker" in env_info
        
        # Check services information
        services = env_info["services"]
        assert isinstance(services, dict)
        
        # Check Docker information
        docker = env_info["docker"]
        assert "network" in docker
        assert "compose_file" in docker
    
    def test_env_file_template_creation(self, tmp_path):
        """Test environment file template creation."""
        config = LocalDatabaseConfig.create_test_config()
        
        # Create template in temporary directory
        template_path = tmp_path / ".env.local.test"
        config.create_env_file_template(str(template_path))
        
        # Check that file was created
        assert template_path.exists()
        
        # Check file content
        content = template_path.read_text()
        assert "ML_ENVIRONMENT=" in content
        assert "ML_DATABASE_TYPE=" in content
        assert "ML_POSTGRES_HOST=" in content
        assert "ML_NEO4J_HOST=" in content
        assert "ML_MILVUS_HOST=" in content
        assert "ML_REDIS_HOST=" in content
    
    def test_configuration_methods_coverage(self):
        """Test that all configuration methods are accessible."""
        config = LocalDatabaseConfig.create_test_config()
        
        # Test all getter methods
        methods_to_test = [
            "get_backend_type",
            "is_local_enabled", 
            "is_aws_native_enabled",
            "get_postgres_connection_string",
            "get_neo4j_uri",
            "get_neo4j_http_uri",
            "get_milvus_connection_config",
            "get_milvus_uri",
            "get_redis_connection_string",
            "get_redis_connection_config",
            "get_relational_db_config",
            "get_graph_db_config",
            "get_vector_db_config",
            "get_redis_config",
            "get_application_config",
            "get_storage_config",
            "get_development_config",
            "get_connection_pool_config",
            "get_retry_config",
            "get_health_monitoring_config",
            "get_health_check_config",
            "get_monitoring_config",
            "get_docker_config",
            "validate_configuration",
            "get_environment_info"
        ]
        
        for method_name in methods_to_test:
            method = getattr(config, method_name)
            assert callable(method), f"Method {method_name} should be callable"
            
            # Call method and verify it returns something
            if method_name in ["get_postgres_connection_string", "get_neo4j_uri", "get_neo4j_http_uri", 
                              "get_milvus_uri", "get_redis_connection_string"]:
                result = method()
            else:
                result = method()
            
            assert result is not None, f"Method {method_name} should return a value"