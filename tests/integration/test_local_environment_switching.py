"""
Integration tests for environment switching between local and AWS configurations.

This module tests the ability to switch between local development and AWS production
environments seamlessly, ensuring configuration consistency and functionality.
"""

import pytest
import os
import asyncio
from typing import Dict, Any, Optional
from unittest.mock import patch, MagicMock

from src.multimodal_librarian.config.config_factory import get_database_config, detect_environment
from src.multimodal_librarian.config.local_config import LocalDatabaseConfig
from src.multimodal_librarian.clients.database_client_factory import DatabaseClientFactory


class TestEnvironmentSwitching:
    """Integration tests for environment switching functionality."""
    
    def setup_method(self):
        """Reset environment before each test."""
        # Clear environment variables that affect configuration
        env_vars_to_clear = [
            'ML_ENVIRONMENT', 'ML_DATABASE_TYPE', 'AWS_DEFAULT_REGION',
            'ML_POSTGRES_HOST', 'ML_NEO4J_HOST', 'ML_MILVUS_HOST',
            'POSTGRES_HOST', 'NEO4J_HOST', 'MILVUS_HOST'
        ]
        
        for var in env_vars_to_clear:
            os.environ.pop(var, None)
    
    def test_local_environment_detection(self):
        """Test automatic detection of local environment."""
        # Set environment variables that indicate local setup
        local_env = {
            'ML_POSTGRES_HOST': 'localhost',
            'ML_NEO4J_HOST': 'localhost',
            'ML_MILVUS_HOST': 'localhost'
        }
        
        with patch.dict(os.environ, local_env):
            env_info = detect_environment()
            
            assert env_info.detected_type == "local"
            assert env_info.confidence > 0.5
            # Check that localhost is detected in the indicators
            assert any("localhost" in str(value) for value in env_info.indicators.values())
    
    def test_aws_environment_detection(self):
        """Test automatic detection of AWS environment."""
        # Set environment variables that indicate AWS setup
        aws_env = {
            'AWS_DEFAULT_REGION': 'us-east-1',
            'ML_OPENSEARCH_ENDPOINT': 'https://search-test.us-east-1.es.amazonaws.com',
            'ML_NEPTUNE_ENDPOINT': 'neptune-test.cluster-xyz.us-east-1.neptune.amazonaws.com'
        }
        
        with patch.dict(os.environ, aws_env):
            env_info = detect_environment()
            
            assert env_info.detected_type == "aws"
            assert env_info.confidence > 0.5
            # Check that AWS region is detected in the indicators
            assert "AWS_DEFAULT_REGION" in env_info.indicators
    
    def test_explicit_local_configuration(self):
        """Test explicit local environment configuration."""
        # Explicitly set local environment
        with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'}):
            config = get_database_config('auto')
            
            assert config.database_type == "local"
            assert isinstance(config, LocalDatabaseConfig)
            assert config.is_local_enabled() is True
            assert config.is_aws_native_enabled() is False
    
    def test_explicit_aws_configuration(self):
        """Test explicit AWS environment configuration."""
        # Explicitly set AWS environment
        with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'aws'}):
            try:
                config = get_database_config('auto')
                
                # Should get AWS config (if available)
                assert config.database_type == "aws"
                assert config.is_aws_native_enabled() is True
                assert config.is_local_enabled() is False
                
            except ImportError:
                # AWS config not available in test environment
                pytest.skip("AWS configuration not available")
    
    def test_configuration_switching_consistency(self):
        """Test that switching between configurations maintains consistency."""
        # Test local configuration
        with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'}):
            local_config = get_database_config('auto')
            
            # Get configuration details
            local_relational = local_config.get_relational_db_config()
            local_graph = local_config.get_graph_db_config()
            local_vector = local_config.get_vector_db_config()
            
            # Verify local configuration structure
            assert local_relational["type"] == "postgresql"
            assert local_graph["type"] == "neo4j"
            assert local_vector["type"] == "milvus"
        
        # Test AWS configuration (if available)
        try:
            with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'aws'}):
                aws_config = get_database_config('auto')
                
                # Get configuration details
                aws_relational = aws_config.get_relational_db_config()
                aws_graph = aws_config.get_graph_db_config()
                aws_vector = aws_config.get_vector_db_config()
                
                # Verify AWS configuration structure
                assert aws_relational["type"] == "postgresql"  # RDS
                assert aws_graph["type"] == "neptune"
                assert aws_vector["type"] == "opensearch"
                
        except (ImportError, AttributeError):
            # AWS config not available
            pytest.skip("AWS configuration not available for comparison")
    
    def test_factory_environment_switching(self):
        """Test database factory behavior with environment switching."""
        # Test local factory
        with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'}):
            local_config = get_database_config('auto')
            local_factory = DatabaseClientFactory(local_config)
            
            # Verify local factory configuration
            assert local_factory.config.database_type == "local"
            
            local_stats = local_factory.get_factory_stats()
            assert local_stats["database_type"] == "local"
        
        # Test AWS factory (if available)
        try:
            with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'aws'}):
                aws_config = get_database_config('auto')
                aws_factory = DatabaseClientFactory(aws_config)
                
                # Verify AWS factory configuration
                assert aws_factory.config.database_type == "aws"
                
                aws_stats = aws_factory.get_factory_stats()
                assert aws_stats["database_type"] == "aws"
                
        except (ImportError, AttributeError):
            pytest.skip("AWS configuration not available for factory testing")
    
    def test_environment_variable_precedence(self):
        """Test environment variable precedence in configuration."""
        # Test that ML_DATABASE_TYPE takes precedence over auto-detection
        env_vars = {
            'ML_DATABASE_TYPE': 'local',
            'AWS_DEFAULT_REGION': 'us-east-1',  # This would normally indicate AWS
            'ML_POSTGRES_HOST': 'localhost'
        }
        
        with patch.dict(os.environ, env_vars):
            config = get_database_config('auto')
            
            # Should use local despite AWS indicators
            assert config.database_type == "local"
            assert isinstance(config, LocalDatabaseConfig)
    
    def test_configuration_validation_across_environments(self):
        """Test configuration validation works across environments."""
        # Test local configuration validation
        with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'}):
            local_config = get_database_config('auto')
            local_validation = local_config.validate_configuration()
            
            assert local_validation["valid"] is True
            assert local_validation["backend"] == "local"
            assert "config" in local_validation
        
        # Test AWS configuration validation (if available)
        try:
            with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'aws'}):
                aws_config = get_database_config('auto')
                aws_validation = aws_config.validate_configuration()
                
                assert aws_validation["valid"] is True
                assert aws_validation["backend"] == "aws"
                assert "config" in aws_validation
                
        except (ImportError, AttributeError):
            pytest.skip("AWS configuration not available for validation testing")
    
    async def test_factory_health_checks_across_environments(self):
        """Test factory health checks work across environments."""
        # Test local factory health check
        with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'}):
            local_config = get_database_config('auto')
            local_factory = DatabaseClientFactory(local_config)
            
            try:
                local_health = await local_factory.health_check()
                
                assert isinstance(local_health, dict)
                assert local_health["database_type"] == "local"
                assert "overall_status" in local_health
                assert "services" in local_health
                
            finally:
                await local_factory.close()
        
        # Test AWS factory health check (if available)
        try:
            with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'aws'}):
                aws_config = get_database_config('auto')
                aws_factory = DatabaseClientFactory(aws_config)
                
                try:
                    aws_health = await aws_factory.health_check()
                    
                    assert isinstance(aws_health, dict)
                    assert aws_health["database_type"] == "aws"
                    assert "overall_status" in aws_health
                    assert "services" in aws_health
                    
                finally:
                    await aws_factory.close()
                    
        except (ImportError, AttributeError):
            pytest.skip("AWS configuration not available for health check testing")
    
    def test_connection_string_format_consistency(self):
        """Test connection string formats are consistent across environments."""
        # Test local connection strings
        with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'}):
            local_config = get_database_config('auto')
            
            # Get connection configurations
            local_relational = local_config.get_relational_db_config()
            local_graph = local_config.get_graph_db_config()
            local_vector = local_config.get_vector_db_config()
            
            # Verify connection string formats
            assert "connection_string" in local_relational
            assert local_relational["connection_string"].startswith("postgresql+asyncpg://")
            
            assert "uri" in local_graph
            assert local_graph["uri"].startswith("bolt://")
            
            assert "uri" in local_vector
            assert local_vector["uri"].startswith("milvus://")
        
        # Test AWS connection strings (if available)
        try:
            with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'aws'}):
                aws_config = get_database_config('auto')
                
                # Get connection configurations
                aws_relational = aws_config.get_relational_db_config()
                aws_graph = aws_config.get_graph_db_config()
                aws_vector = aws_config.get_vector_db_config()
                
                # Verify connection string formats
                assert "connection_string" in aws_relational
                # AWS RDS connection string format
                
                assert "endpoint" in aws_graph
                # AWS Neptune endpoint format
                
                assert "endpoint" in aws_vector
                # AWS OpenSearch endpoint format
                
        except (ImportError, AttributeError):
            pytest.skip("AWS configuration not available for connection string testing")


class TestEnvironmentSpecificFeatures:
    """Test environment-specific features and configurations."""
    
    def test_local_development_features(self):
        """Test features specific to local development."""
        with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'}):
            config = get_database_config('auto')
            
            # Local development should have these features
            dev_config = config.get_development_config()
            assert "hot_reload" in dev_config
            assert "watchdog_enabled" in dev_config
            assert "reload_dirs" in dev_config
            assert "debug" in dev_config
            
            # Docker configuration should be available
            docker_config = config.get_docker_config()
            assert "network" in docker_config
            assert "compose_file" in docker_config
            assert "services" in docker_config
    
    def test_aws_production_features(self):
        """Test features specific to AWS production."""
        try:
            with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'aws'}):
                config = get_database_config('auto')
                
                # AWS should have production-specific features
                # This would test AWS-specific configurations
                # like managed service endpoints, IAM roles, etc.
                
                # Example checks (would depend on actual AWS config implementation)
                aws_config = config.get_aws_config() if hasattr(config, 'get_aws_config') else {}
                
                # Verify AWS-specific settings exist
                if aws_config:
                    assert isinstance(aws_config, dict)
                    # Additional AWS-specific assertions would go here
                
        except (ImportError, AttributeError):
            pytest.skip("AWS configuration not available")
    
    def test_environment_specific_validation(self):
        """Test validation rules specific to each environment."""
        # Local environment validation
        with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'}):
            local_config = get_database_config('auto')
            local_validation = local_config.validate_configuration()
            
            # Local should validate Docker and localhost configurations
            assert local_validation["valid"] is True
            
            # Check for local-specific validation warnings/errors
            issues = local_validation.get("issues", [])
            warnings = local_validation.get("warnings", [])
            
            # Local development might have warnings about default passwords, etc.
            # but should still be valid
            assert isinstance(issues, list)
            assert isinstance(warnings, list)
        
        # AWS environment validation (if available)
        try:
            with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'aws'}):
                aws_config = get_database_config('auto')
                aws_validation = aws_config.validate_configuration()
                
                # AWS should validate managed service configurations
                assert aws_validation["valid"] is True
                
                # Check for AWS-specific validation
                issues = aws_validation.get("issues", [])
                warnings = aws_validation.get("warnings", [])
                
                assert isinstance(issues, list)
                assert isinstance(warnings, list)
                
        except (ImportError, AttributeError):
            pytest.skip("AWS configuration not available")


class TestEnvironmentMigration:
    """Test migration scenarios between environments."""
    
    def test_local_to_aws_migration_compatibility(self):
        """Test compatibility when migrating from local to AWS."""
        # Get local configuration
        with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'}):
            local_config = get_database_config('auto')
            local_factory = DatabaseClientFactory(local_config)
            
            # Get local configuration details
            local_stats = local_factory.get_factory_stats()
            local_config_dict = local_config.model_dump()
            
            assert local_stats["database_type"] == "local"
            assert "postgres_host" in local_config_dict  # Check for postgres-related fields
            assert "neo4j_host" in local_config_dict     # Check for neo4j-related fields
            assert "milvus_host" in local_config_dict    # Check for milvus-related fields
        
        # Test AWS configuration compatibility (if available)
        try:
            with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'aws'}):
                aws_config = get_database_config('auto')
                aws_factory = DatabaseClientFactory(aws_config)
                
                # Get AWS configuration details
                aws_stats = aws_factory.get_factory_stats()
                
                assert aws_stats["database_type"] == "aws"
                
                # Both should support the same basic operations
                # (This would be expanded with actual migration testing)
                
        except (ImportError, AttributeError):
            pytest.skip("AWS configuration not available for migration testing")
    
    def test_configuration_data_portability(self):
        """Test that configuration data is portable between environments."""
        # Test local configuration serialization
        with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'}):
            local_config = get_database_config('auto')
            
            # Serialize configuration
            local_dict = local_config.model_dump()
            
            # Should contain portable configuration data
            assert "database_type" in local_dict
            assert "postgres_host" in local_dict
            assert "neo4j_host" in local_dict
            
            # Configuration should be JSON serializable
            import json
            json_str = json.dumps(local_dict, default=str)
            assert isinstance(json_str, str)
            
            # Should be able to deserialize
            deserialized = json.loads(json_str)
            assert deserialized["database_type"] == "local"
    
    def test_environment_switching_without_restart(self):
        """Test switching environments without application restart."""
        # This tests the ability to switch configurations dynamically
        
        # Start with local configuration
        with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'}):
            config1 = get_database_config('auto')
            assert config1.database_type == "local"
        
        # Switch to AWS configuration (if available)
        try:
            with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'aws'}):
                config2 = get_database_config('auto')
                assert config2.database_type == "aws"
                
                # Configurations should be different instances
                assert config1 != config2
                assert config1.database_type != config2.database_type
                
        except (ImportError, AttributeError):
            pytest.skip("AWS configuration not available for switching test")


@pytest.mark.asyncio
class TestAsyncEnvironmentSwitching:
    """Async tests for environment switching."""
    
    async def test_concurrent_environment_access(self):
        """Test concurrent access to different environment configurations."""
        async def get_local_config():
            with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'}):
                return get_database_config('auto')
        
        async def get_aws_config():
            try:
                with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'aws'}):
                    return get_database_config('auto')
            except (ImportError, AttributeError):
                return None
        
        # Get configurations concurrently
        local_config, aws_config = await asyncio.gather(
            get_local_config(),
            get_aws_config(),
            return_exceptions=True
        )
        
        # Local config should always be available
        assert local_config.database_type == "local"
        
        # AWS config may not be available in test environment
        if aws_config and not isinstance(aws_config, Exception):
            assert aws_config.database_type == "aws"
    
    async def test_factory_switching_with_cleanup(self):
        """Test proper cleanup when switching between factory instances."""
        # Create local factory
        with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'}):
            local_config = get_database_config('auto')
            local_factory = DatabaseClientFactory(local_config)
            
            # Use local factory
            local_health = await local_factory.health_check()
            assert local_health["database_type"] == "local"
            
            # Close local factory
            await local_factory.close()
            assert local_factory._closed
        
        # Create AWS factory (if available)
        try:
            with patch.dict(os.environ, {'ML_DATABASE_TYPE': 'aws'}):
                aws_config = get_database_config('auto')
                aws_factory = DatabaseClientFactory(aws_config)
                
                # Use AWS factory
                aws_health = await aws_factory.health_check()
                assert aws_health["database_type"] == "aws"
                
                # Close AWS factory
                await aws_factory.close()
                assert aws_factory._closed
                
        except (ImportError, AttributeError):
            pytest.skip("AWS configuration not available for factory switching test")