"""
Tests for Configuration Factory

This module tests the ConfigurationFactory class and related functions
for environment detection and configuration creation.
"""

import pytest
import os
from unittest.mock import Mock, patch, mock_open
from typing import Dict, Any

from src.multimodal_librarian.config.config_factory import (
    ConfigurationFactory, EnvironmentInfo, get_database_config, detect_environment,
    get_environment_summary, clear_configuration_cache, reset_configuration_factory,
    get_configuration_factory
)


class TestEnvironmentDetection:
    """Test cases for environment detection."""
    
    def setup_method(self):
        """Reset environment before each test."""
        # Store original environment
        self.original_env = dict(os.environ)
        
        # Clear relevant environment variables
        env_vars_to_clear = [
            'ML_ENVIRONMENT', 'ML_DATABASE_TYPE', 'AWS_DEFAULT_REGION', 'AWS_REGION',
            'NEPTUNE_CLUSTER_ENDPOINT', 'OPENSEARCH_DOMAIN_ENDPOINT',
            'ML_POSTGRES_HOST', 'ML_NEO4J_HOST', 'ML_MILVUS_HOST',
            'POSTGRES_HOST', 'NEO4J_HOST', 'MILVUS_HOST',
            'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_PROFILE',
            'AWS_EXECUTION_ENV', 'AWS_LAMBDA_FUNCTION_NAME'
        ]
        
        for var in env_vars_to_clear:
            os.environ.pop(var, None)
    
    def teardown_method(self):
        """Restore original environment after each test."""
        os.environ.clear()
        os.environ.update(self.original_env)
    
    def test_detect_local_environment_explicit(self):
        """Test detection of local environment with explicit variables."""
        os.environ['ML_DATABASE_TYPE'] = 'local'
        
        factory = ConfigurationFactory()
        env_info = factory.detect_environment()
        
        assert env_info.detected_type == "local"
        assert env_info.confidence >= 0.9
        assert 'ML_DATABASE_TYPE' in env_info.indicators
        assert env_info.indicators['ML_DATABASE_TYPE'] == 'local'
    
    def test_detect_aws_environment_explicit(self):
        """Test detection of AWS environment with explicit variables."""
        os.environ['ML_DATABASE_TYPE'] = 'aws'
        os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
        
        factory = ConfigurationFactory()
        env_info = factory.detect_environment()
        
        assert env_info.detected_type == "aws"
        assert env_info.confidence >= 0.9
        assert 'ML_DATABASE_TYPE' in env_info.indicators
        assert env_info.indicators['ML_DATABASE_TYPE'] == 'aws'
    
    def test_detect_local_environment_by_hosts(self):
        """Test detection of local environment by database hosts."""
        os.environ['ML_POSTGRES_HOST'] = 'localhost'
        os.environ['ML_NEO4J_HOST'] = 'localhost'
        os.environ['ML_MILVUS_HOST'] = 'localhost'
        
        factory = ConfigurationFactory()
        env_info = factory.detect_environment()
        
        assert env_info.detected_type == "local"
        assert env_info.confidence > 0.5
        assert 'POSTGRES_HOST' in env_info.indicators
        assert 'NEO4J_HOST' in env_info.indicators
        assert 'MILVUS_HOST' in env_info.indicators
    
    def test_detect_aws_environment_by_endpoints(self):
        """Test detection of AWS environment by service endpoints."""
        os.environ['NEPTUNE_CLUSTER_ENDPOINT'] = 'neptune.cluster-xyz.us-east-1.neptune.amazonaws.com'
        os.environ['OPENSEARCH_DOMAIN_ENDPOINT'] = 'search-domain.us-east-1.es.amazonaws.com'
        os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'
        
        factory = ConfigurationFactory()
        env_info = factory.detect_environment()
        
        assert env_info.detected_type == "aws"
        assert env_info.confidence > 0.5
        assert 'NEPTUNE_ENDPOINT' in env_info.indicators
        assert 'OPENSEARCH_ENDPOINT' in env_info.indicators
        assert 'AWS_REGION' in env_info.indicators
    
    def test_detect_aws_runtime_environment(self):
        """Test detection of AWS runtime environment (ECS/Lambda)."""
        os.environ['AWS_EXECUTION_ENV'] = 'AWS_ECS_FARGATE'
        
        factory = ConfigurationFactory()
        env_info = factory.detect_environment()
        
        assert env_info.detected_type == "aws"
        assert env_info.confidence >= 0.6
        assert 'AWS_RUNTIME' in env_info.indicators
    
    @patch('os.path.exists')
    def test_detect_local_environment_by_files(self, mock_exists):
        """Test detection of local environment by file presence."""
        def exists_side_effect(path):
            return path in ['docker-compose.local.yml', '.env.local']
        
        mock_exists.side_effect = exists_side_effect
        
        factory = ConfigurationFactory()
        env_info = factory.detect_environment()
        
        assert env_info.detected_type == "local"
        assert 'DOCKER_COMPOSE_LOCAL' in env_info.indicators
        assert 'ENV_LOCAL_FILE' in env_info.indicators
    
    def test_detect_ambiguous_environment(self):
        """Test detection when environment is ambiguous."""
        # Set both local and AWS indicators
        os.environ['ML_POSTGRES_HOST'] = 'localhost'  # Local indicator
        os.environ['AWS_DEFAULT_REGION'] = 'us-east-1'  # AWS indicator
        
        factory = ConfigurationFactory()
        env_info = factory.detect_environment()
        
        # Should still make a decision but with warnings
        assert env_info.detected_type in ["local", "aws"]
        assert len(env_info.warnings) > 0
        assert any("ambiguous" in warning.lower() for warning in env_info.warnings)
    
    def test_detect_environment_with_no_indicators(self):
        """Test detection when no clear indicators are present."""
        factory = ConfigurationFactory()
        env_info = factory.detect_environment()
        
        # Should default to local with low confidence
        assert env_info.detected_type == "local"
        assert env_info.confidence < 0.5
        assert len(env_info.warnings) > 0
    
    def test_detect_environment_ml_environment_variations(self):
        """Test detection with various ML_ENVIRONMENT values."""
        test_cases = [
            ('development', 'local'),
            ('dev', 'local'),
            ('local', 'local'),
            ('production', 'aws'),
            ('prod', 'aws'),
            ('aws', 'aws')
        ]
        
        for env_value, expected_type in test_cases:
            # Clear environment and set test value
            for var in ['ML_ENVIRONMENT', 'ML_DATABASE_TYPE']:
                os.environ.pop(var, None)
            
            os.environ['ML_ENVIRONMENT'] = env_value
            
            factory = ConfigurationFactory()
            env_info = factory.detect_environment()
            
            assert env_info.detected_type == expected_type, f"Failed for ML_ENVIRONMENT={env_value}"
            assert env_info.confidence >= 0.8


class TestConfigurationFactory:
    """Test cases for ConfigurationFactory."""
    
    def setup_method(self):
        """Reset factory before each test."""
        reset_configuration_factory()
    
    def teardown_method(self):
        """Clean up after each test."""
        reset_configuration_factory()
    
    @patch('src.multimodal_librarian.config.config_factory.LocalDatabaseConfig')
    def test_create_local_config(self, mock_config_class):
        """Test creating local configuration."""
        mock_config = Mock()
        mock_config.validate_configuration.return_value = {"valid": True, "warnings": []}
        mock_config_class.return_value = mock_config
        
        factory = ConfigurationFactory()
        config = factory.create_config("local")
        
        assert config == mock_config
        mock_config_class.assert_called_once()
        mock_config.validate_configuration.assert_called_once()
    
    @patch('src.multimodal_librarian.config.config_factory.AWSNativeConfig')
    def test_create_aws_config(self, mock_config_class):
        """Test creating AWS configuration."""
        mock_config = Mock()
        mock_config.validate_configuration.return_value = {"valid": True, "warnings": []}
        mock_config_class.return_value = mock_config
        
        factory = ConfigurationFactory()
        config = factory.create_config("aws")
        
        assert config == mock_config
        mock_config_class.assert_called_once()
        mock_config.validate_configuration.assert_called_once()
    
    @patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'})
    @patch('src.multimodal_librarian.config.config_factory.LocalDatabaseConfig')
    def test_create_config_auto_detect(self, mock_config_class):
        """Test creating configuration with auto-detection."""
        mock_config = Mock()
        mock_config.validate_configuration.return_value = {"valid": True, "warnings": []}
        mock_config_class.return_value = mock_config
        
        factory = ConfigurationFactory()
        config = factory.create_config("auto")
        
        assert config == mock_config
        mock_config_class.assert_called_once()
    
    def test_create_config_invalid_environment(self):
        """Test creating configuration with invalid environment."""
        factory = ConfigurationFactory()
        
        with pytest.raises(ValueError) as exc_info:
            factory.create_config("invalid")
        
        assert "Unknown environment type" in str(exc_info.value)
    
    @patch('src.multimodal_librarian.config.config_factory.LocalDatabaseConfig')
    def test_create_config_validation_failure(self, mock_config_class):
        """Test creating configuration when validation fails."""
        mock_config = Mock()
        mock_config.validate_configuration.return_value = {
            "valid": False, 
            "issues": ["Missing required setting"]
        }
        mock_config_class.return_value = mock_config
        
        factory = ConfigurationFactory()
        
        with pytest.raises(ValueError) as exc_info:
            factory.create_config("local")
        
        assert "Invalid local configuration" in str(exc_info.value)
    
    @patch('src.multimodal_librarian.config.config_factory.LocalDatabaseConfig')
    def test_create_config_with_warnings(self, mock_config_class):
        """Test creating configuration with validation warnings."""
        mock_config = Mock()
        mock_config.validate_configuration.return_value = {
            "valid": True, 
            "warnings": ["Using default password"]
        }
        mock_config_class.return_value = mock_config
        
        factory = ConfigurationFactory()
        
        # Should succeed but log warnings
        config = factory.create_config("local")
        assert config == mock_config
    
    def test_create_config_import_error(self):
        """Test creating configuration when import fails."""
        factory = ConfigurationFactory()
        
        with patch('src.multimodal_librarian.config.config_factory.LocalDatabaseConfig', side_effect=ImportError("Module not found")):
            with pytest.raises(ImportError) as exc_info:
                factory.create_config("local")
            
            assert "Local database configuration not available" in str(exc_info.value)
    
    @patch('src.multimodal_librarian.config.config_factory.LocalDatabaseConfig')
    def test_get_cached_config(self, mock_config_class):
        """Test configuration caching."""
        mock_config = Mock()
        mock_config.validate_configuration.return_value = {"valid": True, "warnings": []}
        mock_config_class.return_value = mock_config
        
        factory = ConfigurationFactory()
        
        # First call should create config
        config1 = factory.get_cached_config("local")
        assert config1 == mock_config
        assert mock_config_class.call_count == 1
        
        # Second call should return cached config
        config2 = factory.get_cached_config("local")
        assert config2 == config1
        assert mock_config_class.call_count == 1  # No additional calls
    
    @patch('src.multimodal_librarian.config.config_factory.LocalDatabaseConfig')
    def test_clear_cache(self, mock_config_class):
        """Test clearing configuration cache."""
        mock_config = Mock()
        mock_config.validate_configuration.return_value = {"valid": True, "warnings": []}
        mock_config_class.return_value = mock_config
        
        factory = ConfigurationFactory()
        
        # Create cached config
        config1 = factory.get_cached_config("local")
        
        # Clear cache
        factory.clear_cache()
        
        # Next call should create new config
        config2 = factory.get_cached_config("local")
        assert mock_config_class.call_count == 2  # Two separate creations
    
    @patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'})
    @patch('src.multimodal_librarian.config.config_factory.LocalDatabaseConfig')
    def test_get_environment_summary(self, mock_config_class):
        """Test getting environment summary."""
        mock_config = Mock()
        mock_config.validate_configuration.return_value = {"valid": True, "warnings": []}
        mock_config.get_environment_info.return_value = {"backend_type": "local"}
        mock_config_class.return_value = mock_config
        
        factory = ConfigurationFactory()
        
        # Create cached config first
        factory.get_cached_config("auto")
        
        summary = factory.get_environment_summary()
        
        assert "detection" in summary
        assert "configuration" in summary
        assert summary["detection"]["detected_type"] == "local"
        assert summary["configuration"]["backend_type"] == "local"


class TestGlobalConfigurationFunctions:
    """Test cases for global configuration functions."""
    
    def setup_method(self):
        """Reset global state before each test."""
        reset_configuration_factory()
    
    def teardown_method(self):
        """Clean up after each test."""
        reset_configuration_factory()
    
    @patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'})
    @patch('src.multimodal_librarian.config.config_factory.LocalDatabaseConfig')
    def test_get_database_config_auto(self, mock_config_class):
        """Test getting database config with auto-detection."""
        mock_config = Mock()
        mock_config.validate_configuration.return_value = {"valid": True, "warnings": []}
        mock_config_class.return_value = mock_config
        
        config = get_database_config("auto")
        
        assert config == mock_config
        mock_config_class.assert_called_once()
    
    @patch('src.multimodal_librarian.config.config_factory.LocalDatabaseConfig')
    def test_get_database_config_explicit(self, mock_config_class):
        """Test getting database config with explicit environment."""
        mock_config = Mock()
        mock_config.validate_configuration.return_value = {"valid": True, "warnings": []}
        mock_config_class.return_value = mock_config
        
        config = get_database_config("local")
        
        assert config == mock_config
        mock_config_class.assert_called_once()
    
    @patch('src.multimodal_librarian.config.config_factory.LocalDatabaseConfig')
    def test_get_database_config_caching(self, mock_config_class):
        """Test that get_database_config caches results."""
        mock_config = Mock()
        mock_config.validate_configuration.return_value = {"valid": True, "warnings": []}
        mock_config_class.return_value = mock_config
        
        # Multiple calls should return same instance
        config1 = get_database_config("local")
        config2 = get_database_config("local")
        
        assert config1 == config2
        assert mock_config_class.call_count == 1
    
    @patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'})
    def test_detect_environment_function(self):
        """Test the detect_environment convenience function."""
        env_info = detect_environment()
        
        assert isinstance(env_info, EnvironmentInfo)
        assert env_info.detected_type == "local"
        assert env_info.confidence >= 0.9
    
    @patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'})
    @patch('src.multimodal_librarian.config.config_factory.LocalDatabaseConfig')
    def test_get_environment_summary_function(self, mock_config_class):
        """Test the get_environment_summary convenience function."""
        mock_config = Mock()
        mock_config.validate_configuration.return_value = {"valid": True, "warnings": []}
        mock_config.get_environment_info.return_value = {"backend_type": "local"}
        mock_config_class.return_value = mock_config
        
        # Create config first
        get_database_config("auto")
        
        summary = get_environment_summary()
        
        assert "detection" in summary
        assert "configuration" in summary
    
    @patch('src.multimodal_librarian.config.config_factory.LocalDatabaseConfig')
    def test_clear_configuration_cache_function(self, mock_config_class):
        """Test the clear_configuration_cache convenience function."""
        mock_config = Mock()
        mock_config.validate_configuration.return_value = {"valid": True, "warnings": []}
        mock_config_class.return_value = mock_config
        
        # Create cached config
        get_database_config("local")
        
        # Clear cache
        clear_configuration_cache()
        
        # Next call should create new config
        get_database_config("local")
        
        assert mock_config_class.call_count == 2
    
    def test_get_configuration_factory_singleton(self):
        """Test that get_configuration_factory returns singleton."""
        factory1 = get_configuration_factory()
        factory2 = get_configuration_factory()
        
        assert factory1 == factory2
        assert isinstance(factory1, ConfigurationFactory)
    
    def test_reset_configuration_factory_function(self):
        """Test the reset_configuration_factory function."""
        factory1 = get_configuration_factory()
        reset_configuration_factory()
        factory2 = get_configuration_factory()
        
        assert factory1 != factory2


class TestEnvironmentDetectionEdgeCases:
    """Test edge cases in environment detection."""
    
    def setup_method(self):
        """Clear environment before each test."""
        self.original_env = dict(os.environ)
        for var in os.environ.copy():
            if var.startswith(('ML_', 'AWS_', 'NEPTUNE_', 'OPENSEARCH_', 'POSTGRES_', 'NEO4J_', 'MILVUS_')):
                del os.environ[var]
    
    def teardown_method(self):
        """Restore environment after each test."""
        os.environ.clear()
        os.environ.update(self.original_env)
    
    def test_docker_host_detection(self):
        """Test detection of Docker service hosts."""
        os.environ['ML_POSTGRES_HOST'] = 'postgres'  # Docker service name
        os.environ['ML_NEO4J_HOST'] = 'neo4j'
        os.environ['ML_MILVUS_HOST'] = 'milvus'
        
        factory = ConfigurationFactory()
        env_info = factory.detect_environment()
        
        assert env_info.detected_type == "local"
        assert env_info.confidence > 0.5
    
    def test_aws_credentials_detection(self):
        """Test detection of AWS credentials."""
        os.environ['AWS_ACCESS_KEY_ID'] = 'AKIAIOSFODNN7EXAMPLE'
        os.environ['AWS_SECRET_ACCESS_KEY'] = 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'
        
        factory = ConfigurationFactory()
        env_info = factory.detect_environment()
        
        assert 'AWS_CREDENTIALS' in env_info.indicators
    
    def test_aws_profile_detection(self):
        """Test detection of AWS profile."""
        os.environ['AWS_PROFILE'] = 'production'
        
        factory = ConfigurationFactory()
        env_info = factory.detect_environment()
        
        assert 'AWS_CREDENTIALS' in env_info.indicators
    
    def test_lambda_environment_detection(self):
        """Test detection of AWS Lambda environment."""
        os.environ['AWS_LAMBDA_FUNCTION_NAME'] = 'my-function'
        
        factory = ConfigurationFactory()
        env_info = factory.detect_environment()
        
        assert env_info.detected_type == "aws"
        assert env_info.confidence >= 0.6
        assert 'AWS_RUNTIME' in env_info.indicators
    
    def test_mixed_host_indicators(self):
        """Test with mixed local and remote host indicators."""
        os.environ['ML_POSTGRES_HOST'] = 'localhost'  # Local
        os.environ['ML_NEO4J_HOST'] = 'remote-neo4j.example.com'  # Remote
        os.environ['ML_MILVUS_HOST'] = '127.0.0.1'  # Local
        
        factory = ConfigurationFactory()
        env_info = factory.detect_environment()
        
        # Should still detect as local due to localhost indicators
        assert env_info.detected_type == "local"
        assert 'POSTGRES_HOST' in env_info.indicators
        assert 'MILVUS_HOST' in env_info.indicators
    
    def test_confidence_scoring(self):
        """Test confidence scoring with various indicator combinations."""
        test_cases = [
            # (env_vars, expected_min_confidence)
            ({'ML_DATABASE_TYPE': 'local'}, 0.9),
            ({'ML_ENVIRONMENT': 'development'}, 0.8),
            ({'ML_POSTGRES_HOST': 'localhost'}, 0.3),
            ({'AWS_EXECUTION_ENV': 'AWS_ECS_FARGATE'}, 0.6),
            ({'ML_DATABASE_TYPE': 'local', 'ML_POSTGRES_HOST': 'localhost'}, 0.9),
        ]
        
        for env_vars, expected_min_confidence in test_cases:
            # Clear and set environment
            for var in list(os.environ.keys()):
                if var.startswith(('ML_', 'AWS_')):
                    del os.environ[var]
            
            for var, value in env_vars.items():
                os.environ[var] = value
            
            factory = ConfigurationFactory()
            env_info = factory.detect_environment()
            
            assert env_info.confidence >= expected_min_confidence, \
                f"Confidence {env_info.confidence} < {expected_min_confidence} for {env_vars}"


@pytest.mark.integration
class TestConfigurationFactoryIntegration:
    """Integration tests for configuration factory."""
    
    def setup_method(self):
        """Reset state before each test."""
        reset_configuration_factory()
    
    def teardown_method(self):
        """Clean up after each test."""
        reset_configuration_factory()
    
    @patch.dict(os.environ, {'ML_DATABASE_TYPE': 'local'}, clear=False)
    def test_end_to_end_local_config_creation(self):
        """Test end-to-end local configuration creation."""
        config = get_database_config("auto")
        
        assert hasattr(config, 'database_type')
        assert config.database_type == "local"
        assert hasattr(config, 'postgres_host')
        assert hasattr(config, 'neo4j_host')
        assert hasattr(config, 'milvus_host')
    
    def test_environment_detection_with_real_environment(self):
        """Test environment detection with real environment variables."""
        env_info = detect_environment()
        
        assert isinstance(env_info, EnvironmentInfo)
        assert env_info.detected_type in ["local", "aws"]
        assert 0.0 <= env_info.confidence <= 1.0
        assert isinstance(env_info.indicators, dict)
        assert isinstance(env_info.warnings, list)
    
    def test_configuration_factory_singleton_behavior(self):
        """Test that configuration factory behaves as singleton."""
        factory1 = get_configuration_factory()
        factory2 = get_configuration_factory()
        
        assert factory1 is factory2
        
        # Reset and verify new instance
        reset_configuration_factory()
        factory3 = get_configuration_factory()
        
        assert factory3 is not factory1