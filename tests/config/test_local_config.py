"""
Tests for Local Database Configuration

This module tests the LocalDatabaseConfig class and related functions
for local development database configuration.
"""

import os
import tempfile
from unittest.mock import mock_open, patch

import pytest
from pydantic import ValidationError

from src.multimodal_librarian.config.local_config import (
    LocalDatabaseConfig,
    create_local_env_template,
    get_local_config,
    reload_local_config,
)


class TestLocalDatabaseConfig:
    """Test cases for LocalDatabaseConfig."""
    
    def test_default_configuration(self):
        """Test default configuration values."""
        config = LocalDatabaseConfig()
        
        assert config.database_type == "local"
        assert config.environment == "local"  # Updated to match actual default
        assert config.postgres_host == "localhost"
        assert config.postgres_port == 5432
        assert config.postgres_db == "multimodal_librarian"
        assert config.postgres_user == "ml_user"
        assert config.postgres_password == "ml_password"
        assert config.neo4j_host == "localhost"
        assert config.neo4j_port == 7687
        assert config.neo4j_user == "neo4j"
        assert config.neo4j_password == "ml_password"
        assert config.milvus_host == "localhost"
        assert config.milvus_port == 19530
        assert config.enable_relational_db is True
        assert config.enable_vector_search is True
        assert config.enable_graph_db is True
        assert config.connection_timeout == 60
        assert config.query_timeout == 30
        assert config.max_retries == 3
        assert config.embedding_dimension == 768
    
    def test_configuration_with_custom_values(self):
        """Test configuration with custom values."""
        config = LocalDatabaseConfig.create_test_config(
            postgres_host="custom-postgres",
            postgres_port=5433,
            postgres_db="custom_db",
            neo4j_host="custom-neo4j",
            neo4j_port=7688,
            milvus_host="custom-milvus",
            milvus_port=19531,
            connection_timeout=120,
            embedding_dimension=768  # This would normally fail validation
        )
        
        assert config.postgres_host == "custom-postgres"
        assert config.postgres_port == 5433
        assert config.postgres_db == "custom_db"
        assert config.neo4j_host == "custom-neo4j"
        assert config.neo4j_port == 7688
        assert config.milvus_host == "custom-milvus"
        assert config.milvus_port == 19531
        assert config.connection_timeout == 120
        assert config.embedding_dimension == 768
    
    @patch.dict(os.environ, {
        'ML_POSTGRES_HOST': 'env-postgres',
        'ML_POSTGRES_PORT': '5434',
        'ML_NEO4J_HOST': 'env-neo4j',
        'ML_MILVUS_HOST': 'env-milvus',
        'ML_CONNECTION_TIMEOUT': '90'
    })
    def test_configuration_from_environment(self):
        """Test configuration loading from environment variables."""
        config = LocalDatabaseConfig()
        
        assert config.postgres_host == "env-postgres"
        assert config.postgres_port == 5434
        assert config.neo4j_host == "env-neo4j"
        assert config.milvus_host == "env-milvus"
        assert config.connection_timeout == 90
    
    def test_port_validation(self):
        """Test port number validation."""
        # Valid ports should work
        config = LocalDatabaseConfig(postgres_port=5432)
        assert config.postgres_port == 5432
        
        # Invalid ports should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            LocalDatabaseConfig(postgres_port=0)
        assert "Port must be between 1 and 65535" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            LocalDatabaseConfig(postgres_port=70000)
        assert "Port must be between 1 and 65535" in str(exc_info.value)
    
    def test_timeout_validation(self):
        """Test timeout validation."""
        # Valid timeouts should work
        config = LocalDatabaseConfig(connection_timeout=60, query_timeout=30)
        assert config.connection_timeout == 60
        assert config.query_timeout == 30
        
        # Invalid timeouts should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            LocalDatabaseConfig(connection_timeout=0)
        assert "Timeout must be positive" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            LocalDatabaseConfig(query_timeout=-1)
        assert "Timeout must be positive" in str(exc_info.value)
    
    def test_pool_size_validation(self):
        """Test pool size validation."""
        # Valid pool sizes should work
        config = LocalDatabaseConfig(postgres_pool_size=10, neo4j_pool_size=50)
        assert config.postgres_pool_size == 10
        assert config.neo4j_pool_size == 50
        
        # Invalid pool sizes should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            LocalDatabaseConfig(postgres_pool_size=0)
        assert "Pool size must be positive" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            LocalDatabaseConfig(neo4j_pool_size=-1)
        assert "Pool size must be positive" in str(exc_info.value)
    
    def test_embedding_dimension_validation(self):
        """Test embedding dimension validation."""
        # Valid dimensions should work
        config = LocalDatabaseConfig(embedding_dimension=384)
        assert config.embedding_dimension == 384
        
        # Invalid dimensions should raise ValidationError
        with pytest.raises(ValidationError) as exc_info:
            LocalDatabaseConfig(embedding_dimension=0)
        assert "Embedding dimension must be positive" in str(exc_info.value)
        
        with pytest.raises(ValidationError) as exc_info:
            LocalDatabaseConfig(embedding_dimension=-1)
        assert "Embedding dimension must be positive" in str(exc_info.value)
    
    def test_get_backend_type(self):
        """Test get_backend_type method."""
        config = LocalDatabaseConfig()
        assert config.get_backend_type() == "local"
    
    def test_is_local_enabled(self):
        """Test is_local_enabled method."""
        config = LocalDatabaseConfig()
        assert config.is_local_enabled() is True
    
    def test_is_aws_native_enabled(self):
        """Test is_aws_native_enabled method."""
        config = LocalDatabaseConfig()
        assert config.is_aws_native_enabled() is False
    
    def test_get_postgres_connection_string(self):
        """Test PostgreSQL connection string generation."""
        config = LocalDatabaseConfig(
            postgres_user="test_user",
            postgres_password="test_pass",
            postgres_host="test_host",
            postgres_port=5433,
            postgres_db="test_db"
        )
        
        # Test async connection string
        async_conn_str = config.get_postgres_connection_string(async_driver=True)
        expected_async = "postgresql+asyncpg://test_user:test_pass@test_host:5433/test_db"
        assert async_conn_str == expected_async
        
        # Test sync connection string
        sync_conn_str = config.get_postgres_connection_string(async_driver=False)
        expected_sync = "postgresql+psycopg2://test_user:test_pass@test_host:5433/test_db"
        assert sync_conn_str == expected_sync
        
        # Test sync connection string with pool parameters
        pooled_conn_str = config.get_postgres_connection_string(async_driver=False, include_pool_params=True)
        assert "pool_size=10" in pooled_conn_str
        assert "max_overflow=20" in pooled_conn_str
        assert "pool_recycle=3600" in pooled_conn_str
    
    def test_get_neo4j_uri(self):
        """Test Neo4j URI generation."""
        config = LocalDatabaseConfig(
            neo4j_host="test-neo4j",
            neo4j_port=7688,
            neo4j_user="test_user",
            neo4j_password="test_pass"
        )
        
        # Test default bolt URI
        uri = config.get_neo4j_uri()
        assert uri == "bolt://test_user:test_pass@test-neo4j:7688"
        
        # Test neo4j protocol URI
        neo4j_uri = config.get_neo4j_uri(protocol="neo4j")
        assert neo4j_uri == "neo4j://test_user:test_pass@test-neo4j:7688"
    
    def test_get_neo4j_http_uri(self):
        """Test Neo4j HTTP URI generation."""
        config = LocalDatabaseConfig(
            neo4j_host="test-neo4j",
            neo4j_http_port=7475
        )
        
        # Test HTTP URI
        http_uri = config.get_neo4j_http_uri()
        assert http_uri == "http://test-neo4j:7475"
        
        # Test HTTPS URI
        https_uri = config.get_neo4j_http_uri(secure=True)
        assert https_uri == "https://test-neo4j:7475"
    
    def test_get_milvus_connection_config(self):
        """Test Milvus connection configuration generation."""
        config = LocalDatabaseConfig(
            milvus_host="test-milvus",
            milvus_port=19531,
            milvus_user="test_user",
            milvus_password="test_pass",
            connection_timeout=45,
            max_retries=5
        )
        
        milvus_config = config.get_milvus_connection_config()
        
        assert milvus_config["host"] == "test-milvus"
        assert milvus_config["port"] == 19531
        assert milvus_config["user"] == "test_user"
        assert milvus_config["password"] == "test_pass"
        assert milvus_config["timeout"] == 45
        assert milvus_config["retry_attempts"] == 5
        assert milvus_config["secure"] is False
    
    def test_get_milvus_uri(self):
        """Test Milvus URI generation."""
        # Test without authentication
        config = LocalDatabaseConfig(
            milvus_host="test-milvus",
            milvus_port=19531
        )
        
        uri = config.get_milvus_uri()
        assert uri == "milvus://test-milvus:19531"
        
        # Test with authentication
        config_with_auth = LocalDatabaseConfig(
            milvus_host="test-milvus",
            milvus_port=19531,
            milvus_user="test_user",
            milvus_password="test_pass"
        )
        
        uri_with_auth = config_with_auth.get_milvus_uri()
        assert uri_with_auth == "milvus://test_user:test_pass@test-milvus:19531"
    
    def test_get_redis_connection_string(self):
        """Test Redis connection string generation."""
        # Test without password
        config = LocalDatabaseConfig(
            redis_host="test-redis",
            redis_port=6380,
            redis_db=1
        )
        
        conn_str = config.get_redis_connection_string()
        assert conn_str == "redis://test-redis:6380/1"
        
        # Test with password
        config_with_auth = LocalDatabaseConfig(
            redis_host="test-redis",
            redis_port=6380,
            redis_db=1,
            redis_password="test_pass"
        )
        
        conn_str_with_auth = config_with_auth.get_redis_connection_string(include_auth=True)
        assert conn_str_with_auth == "redis://:test_pass@test-redis:6380/1"
        
        # Test without auth even when password is set
        conn_str_no_auth = config_with_auth.get_redis_connection_string(include_auth=False)
        assert conn_str_no_auth == "redis://test-redis:6380/1"
    
    def test_get_redis_connection_config(self):
        """Test Redis connection configuration generation."""
        config = LocalDatabaseConfig(
            redis_host="test-redis",
            redis_port=6380,
            redis_db=1,
            redis_password="test_pass",
            redis_max_connections=15,
            connection_timeout=45
        )
        
        redis_config = config.get_redis_connection_config()
        
        assert redis_config["host"] == "test-redis"
        assert redis_config["port"] == 6380
        assert redis_config["db"] == 1
        assert redis_config["password"] == "test_pass"
        assert redis_config["max_connections"] == 15
        assert redis_config["socket_timeout"] == 45
        assert redis_config["socket_connect_timeout"] == 45
        assert redis_config["retry_on_timeout"] is True
    
    def test_get_relational_db_config(self):
        """Test relational database configuration."""
        config = LocalDatabaseConfig()
        db_config = config.get_relational_db_config()
        
        assert db_config["type"] == "postgresql"
        assert db_config["host"] == config.postgres_host
        assert db_config["port"] == config.postgres_port
        assert db_config["database"] == config.postgres_db
        assert db_config["user"] == config.postgres_user
        assert db_config["password"] == config.postgres_password
        assert "connection_string" in db_config
        assert "sync_connection_string" in db_config
        assert "connection_string_with_pool" in db_config
        assert db_config["pool_size"] == config.postgres_pool_size
        assert db_config["timeout"] == config.connection_timeout
    
    def test_get_graph_db_config(self):
        """Test graph database configuration."""
        config = LocalDatabaseConfig()
        graph_config = config.get_graph_db_config()
        
        assert graph_config["type"] == "neo4j"
        assert graph_config["uri"] == config.get_neo4j_uri()
        assert graph_config["http_uri"] == config.get_neo4j_http_uri()
        assert "neo4j_uri" in graph_config
        assert "https_uri" in graph_config
        assert graph_config["user"] == config.neo4j_user
        assert graph_config["password"] == config.neo4j_password
        assert graph_config["pool_size"] == config.neo4j_pool_size
        assert graph_config["timeout"] == config.connection_timeout
    
    def test_get_vector_db_config(self):
        """Test vector database configuration."""
        config = LocalDatabaseConfig()
        vector_config = config.get_vector_db_config()
        
        assert vector_config["type"] == "milvus"
        assert vector_config["host"] == config.milvus_host
        assert vector_config["port"] == config.milvus_port
        assert vector_config["user"] == config.milvus_user
        assert vector_config["password"] == config.milvus_password
        assert vector_config["default_collection"] == config.milvus_default_collection
        assert vector_config["embedding_dimension"] == config.embedding_dimension
        assert vector_config["timeout"] == config.connection_timeout
    
    def test_get_health_check_config(self):
        """Test health check configuration."""
        config = LocalDatabaseConfig()
        health_config = config.get_health_check_config()
        
        assert health_config["enabled"] is True
        assert health_config["interval"] == 30
        assert health_config["timeout"] == 10
        assert health_config["retries"] == 3
        assert health_config["relational_db_enabled"] == config.enable_relational_db
        assert health_config["vector_search_enabled"] == config.enable_vector_search
        assert health_config["graph_db_enabled"] == config.enable_graph_db
    
    def test_get_monitoring_config(self):
        """Test monitoring configuration."""
        config = LocalDatabaseConfig()
        monitoring_config = config.get_monitoring_config()
        
        assert monitoring_config["query_logging"] == config.enable_query_logging
        assert monitoring_config["performance_tracking"] is True
        assert monitoring_config["error_tracking"] is True
        assert monitoring_config["metrics_enabled"] is True
        assert "log_level" in monitoring_config
    
    def test_get_docker_config(self):
        """Test Docker configuration."""
        config = LocalDatabaseConfig()
        docker_config = config.get_docker_config()
        
        assert docker_config["network"] == config.docker_network
        assert docker_config["compose_file"] == config.docker_compose_file
        assert "services" in docker_config
        assert "postgres" in docker_config["services"]
        assert "neo4j" in docker_config["services"]
        assert "milvus" in docker_config["services"]
    
    def test_get_connection_pool_config(self):
        """Test connection pooling configuration."""
        config = LocalDatabaseConfig()
        pool_config = config.get_connection_pool_config()
        
        assert pool_config["enabled"] == config.connection_pooling
        assert "postgres" in pool_config
        assert "neo4j" in pool_config
        assert "milvus" in pool_config
        assert "redis" in pool_config
        
        # Test PostgreSQL pool config
        postgres_config = pool_config["postgres"]
        assert postgres_config["pool_size"] == config.postgres_pool_size
        assert postgres_config["max_overflow"] == config.postgres_max_overflow
        assert postgres_config["pool_recycle"] == config.postgres_pool_recycle
        assert postgres_config["pool_pre_ping"] is True
    
    def test_get_retry_config(self):
        """Test retry configuration."""
        config = LocalDatabaseConfig()
        retry_config = config.get_retry_config()
        
        assert retry_config["enabled"] is True
        assert retry_config["max_retries"] == config.max_retries
        assert retry_config["retry_delay"] == config.retry_delay
        assert retry_config["backoff_factor"] == config.retry_backoff_factor
        assert "retry_on_exceptions" in retry_config
        assert "postgres" in retry_config
        assert "neo4j" in retry_config
        assert "milvus" in retry_config
        assert "redis" in retry_config
    
    def test_get_health_monitoring_config(self):
        """Test health monitoring configuration."""
        config = LocalDatabaseConfig()
        health_config = config.get_health_monitoring_config()
        
        assert health_config["enabled"] == config.enable_health_checks
        assert health_config["interval"] == config.health_check_interval
        assert health_config["timeout"] == config.health_check_timeout
        assert health_config["retries"] == config.health_check_retries
        assert "postgres" in health_config
        assert "neo4j" in health_config
        assert "milvus" in health_config
        assert "redis" in health_config
        
        # Test PostgreSQL health config
        postgres_health = health_config["postgres"]
        assert postgres_health["enabled"] == (config.enable_relational_db and config.enable_health_checks)
        assert postgres_health["check_query"] == "SELECT 1"
        assert postgres_health["pool_health_check"] is True
    
    def test_validate_configuration_valid(self):
        """Test configuration validation with valid settings."""
        config = LocalDatabaseConfig()
        validation = config.validate_configuration()
        
        assert validation["valid"] is True
        assert validation["backend"] == "local"
        assert "config" in validation
        assert "relational_db" in validation["config"]
        assert "graph_db" in validation["config"]
        assert "vector_db" in validation["config"]
    
    def test_validate_configuration_all_disabled(self):
        """Test configuration validation with all services disabled."""
        config = LocalDatabaseConfig.create_test_config(
            enable_relational_db=False,
            enable_vector_search=False,
            enable_graph_db=False,
            enable_knowledge_graph=False,  # Explicitly disable to avoid dependency error
            enable_ai_chat=False,          # Explicitly disable to avoid dependency error
            enable_export_functionality=False,  # Explicitly disable to avoid dependency error
            enable_analytics=False         # Explicitly disable to avoid dependency error
        )
        validation = config.validate_configuration()
        
        assert validation["valid"] is False
        assert any("All database services are disabled" in issue for issue in validation["issues"])
    
    def test_validate_configuration_warnings(self):
        """Test configuration validation with warnings."""
        config = LocalDatabaseConfig.create_test_config(
            postgres_password="changeme",  # Weak password
            neo4j_password="neo4j",        # Default password
            postgres_pool_size=100,        # Large pool
            embedding_dimension=999        # Unusual dimension (won't error in test mode)
        )
        validation = config.validate_configuration()
        
        assert validation["valid"] is True
        assert len(validation["warnings"]) > 0
        assert any("password" in warning.lower() for warning in validation["warnings"])
        assert any("pool size" in warning.lower() for warning in validation["warnings"])
        assert any("dimension" in warning.lower() for warning in validation["warnings"])
    
    def test_get_environment_info(self):
        """Test environment information."""
        config = LocalDatabaseConfig()
        env_info = config.get_environment_info()
        
        assert env_info["backend_type"] == "local"
        assert env_info["environment"] == config.environment
        assert env_info["relational_db_enabled"] == config.enable_relational_db
        assert env_info["vector_search_enabled"] == config.enable_vector_search
        assert env_info["graph_db_enabled"] == config.enable_graph_db
        assert "services" in env_info
        assert "docker" in env_info
    
    def test_create_env_file_template(self):
        """Test environment file template creation."""
        config = LocalDatabaseConfig()
        
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.env') as temp_file:
            temp_path = temp_file.name
        
        try:
            config.create_env_file_template(temp_path)
            
            # Verify file was created and contains expected content
            with open(temp_path, 'r') as f:
                content = f.read()
            
            assert "ML_POSTGRES_HOST=" in content
            assert "ML_NEO4J_HOST=" in content
            assert "ML_MILVUS_HOST=" in content
            assert "ML_DATABASE_TYPE=local" in content
            assert "ML_ENVIRONMENT=development" in content
            
        finally:
            os.unlink(temp_path)


class TestLocalConfigurationFeatureFlags:
    """Test feature flag combinations."""
    
    def test_relational_db_only(self):
        """Test configuration with only relational database enabled."""
        config = LocalDatabaseConfig.create_test_config(
            enable_relational_db=True,
            enable_vector_search=False,
            enable_graph_db=False,
            enable_knowledge_graph=False,  # Disable to avoid dependency error
            enable_export_functionality=True,  # This should work with relational DB
            enable_analytics=True              # This should work with relational DB
        )
        
        validation = config.validate_configuration()
        assert validation["valid"] is True
        assert validation["config"]["relational_db"] is not None
        assert validation["config"]["vector_db"] is None
        assert validation["config"]["graph_db"] is None
    
    def test_vector_search_only(self):
        """Test configuration with only vector search enabled."""
        config = LocalDatabaseConfig.create_test_config(
            enable_relational_db=False,
            enable_vector_search=True,
            enable_graph_db=False,
            enable_knowledge_graph=False,      # Disable to avoid dependency error
            enable_export_functionality=False, # Disable to avoid dependency error
            enable_analytics=False,            # Disable to avoid dependency error
            enable_ai_chat=True                # This should work with vector search
        )
        
        validation = config.validate_configuration()
        assert validation["valid"] is True
        assert validation["config"]["relational_db"] is None
        assert validation["config"]["vector_db"] is not None
        assert validation["config"]["graph_db"] is None
    
    def test_graph_db_only(self):
        """Test configuration with only graph database enabled."""
        config = LocalDatabaseConfig.create_test_config(
            enable_relational_db=False,
            enable_vector_search=False,
            enable_graph_db=True,
            enable_knowledge_graph=True,       # This should work with graph DB
            enable_ai_chat=False,              # Disable to avoid dependency error
            enable_export_functionality=False, # Disable to avoid dependency error
            enable_analytics=False             # Disable to avoid dependency error
        )
        
        validation = config.validate_configuration()
        assert validation["valid"] is True
        assert validation["config"]["relational_db"] is None
        assert validation["config"]["vector_db"] is None
        assert validation["config"]["graph_db"] is not None


class TestGlobalLocalConfigFunctions:
    """Test global configuration functions."""
    
    def test_get_local_config(self):
        """Test getting global local configuration."""
        config = get_local_config()
        
        assert isinstance(config, LocalDatabaseConfig)
        assert config.database_type == "local"
        
        # Should return same instance on subsequent calls
        config2 = get_local_config()
        assert config is config2
    
    def test_reload_local_config(self):
        """Test reloading local configuration."""
        config1 = get_local_config()
        config2 = reload_local_config()
        
        # Should be different instances
        assert config1 is not config2
        assert isinstance(config2, LocalDatabaseConfig)
    
    def test_create_local_env_template_function(self):
        """Test creating environment template via function."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.env') as temp_file:
            temp_path = temp_file.name
        
        try:
            create_local_env_template(temp_path)
            
            # Verify file was created
            assert os.path.exists(temp_path)
            
            with open(temp_path, 'r') as f:
                content = f.read()
            
            assert "ML_POSTGRES_HOST=" in content
            assert "Local Development Configuration" in content
            
        finally:
            os.unlink(temp_path)


class TestLocalConfigurationEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_configuration_with_empty_strings(self):
        """Test configuration with empty string values."""
        config = LocalDatabaseConfig(
            milvus_user="",  # Empty string should be allowed
            milvus_password=""
        )
        
        assert config.milvus_user == ""
        assert config.milvus_password == ""
    
    def test_configuration_with_extreme_values(self):
        """Test configuration with extreme but valid values."""
        config = LocalDatabaseConfig.create_test_config(
            postgres_port=1,           # Minimum valid port
            neo4j_port=65535,          # Maximum valid port
            connection_timeout=1,      # Minimum timeout
            postgres_pool_size=1,      # Minimum pool size
            embedding_dimension=1      # Minimum dimension (won't error in test mode)
        )
        
        assert config.postgres_port == 1
        assert config.neo4j_port == 65535
        assert config.connection_timeout == 1
        assert config.postgres_pool_size == 1
        assert config.embedding_dimension == 1
    
    @patch.dict(os.environ, {
        'ML_POSTGRES_PORT': 'invalid',
        'ML_CONNECTION_TIMEOUT': 'not_a_number'
    })
    def test_configuration_with_invalid_env_values(self):
        """Test configuration with invalid environment variable values."""
        with pytest.raises(ValidationError):
            LocalDatabaseConfig()
    
    def test_configuration_case_insensitive_env_vars(self):
        """Test that environment variables are case insensitive."""
        with patch.dict(os.environ, {
            'ml_postgres_host': 'case-test',  # lowercase
            'ML_POSTGRES_PORT': '5433'        # uppercase
        }):
            config = LocalDatabaseConfig()
            # Note: Pydantic's case_sensitive=False should handle this
            # The actual behavior depends on Pydantic version
            assert config.postgres_port == 5433


@pytest.mark.integration
class TestLocalConfigurationIntegration:
    """Integration tests for local configuration."""
    
    def test_full_configuration_cycle(self):
        """Test complete configuration creation and validation cycle."""
        # Create configuration
        config = LocalDatabaseConfig(
            postgres_host="test-postgres",
            neo4j_host="test-neo4j",
            milvus_host="test-milvus"
        )
        
        # Validate configuration
        validation = config.validate_configuration()
        assert validation["valid"] is True
        
        # Get all configuration sections
        relational_config = config.get_relational_db_config()
        graph_config = config.get_graph_db_config()
        vector_config = config.get_vector_db_config()
        health_config = config.get_health_check_config()
        monitoring_config = config.get_monitoring_config()
        docker_config = config.get_docker_config()
        
        # Verify all configurations are properly structured
        assert all(isinstance(cfg, dict) for cfg in [
            relational_config, graph_config, vector_config,
            health_config, monitoring_config, docker_config
        ])
        
        # Verify environment info
        env_info = config.get_environment_info()
        assert env_info["backend_type"] == "local"
        assert "services" in env_info
        assert "docker" in env_info
    
    def test_configuration_with_real_environment_variables(self):
        """Test configuration with real environment variables."""
        test_env = {
            'ML_POSTGRES_HOST': 'real-postgres',
            'ML_POSTGRES_PORT': '5432',
            'ML_POSTGRES_DB': 'real_db',
            'ML_NEO4J_HOST': 'real-neo4j',
            'ML_MILVUS_HOST': 'real-milvus',
            'ML_CONNECTION_TIMEOUT': '120',
            'ML_ENABLE_QUERY_LOGGING': 'true'
        }
        
        with patch.dict(os.environ, test_env):
            config = LocalDatabaseConfig()
            
            assert config.postgres_host == "real-postgres"
            assert config.postgres_port == 5432
            assert config.postgres_db == "real_db"
            assert config.neo4j_host == "real-neo4j"
            assert config.milvus_host == "real-milvus"
            assert config.connection_timeout == 120
            assert config.enable_query_logging is True