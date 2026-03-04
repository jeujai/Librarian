"""
Tests for Enhanced Configuration Validation and Error Handling

This module tests the enhanced validation and error handling functionality
added to the local development configuration system.
"""

import pytest
import os
import tempfile
import socket
from unittest.mock import patch, Mock, mock_open
from pydantic import ValidationError

from src.multimodal_librarian.config.local_config import (
    LocalDatabaseConfig, ConfigurationError, ValidationError as ConfigValidationError,
    ConnectivityError, ResourceError
)
from src.multimodal_librarian.config.config_factory import (
    ConfigurationFactory, EnvironmentInfo, EnvironmentDetectionError,
    ConfigurationFactoryError, ConfigurationImportError, ConfigurationValidationError
)


class TestEnhancedLocalConfigValidation:
    """Test enhanced validation functionality in LocalDatabaseConfig."""
    
    def test_model_validator_port_conflicts(self):
        """Test model validator catches port conflicts."""
        with pytest.raises(ValidationError) as exc_info:
            LocalDatabaseConfig(
                postgres_port=5432,
                neo4j_port=5432,  # Same port as PostgreSQL
                enable_relational_db=True,
                enable_graph_db=True
            )
        
        assert "Port 5432 is used by multiple services" in str(exc_info.value)
    
    def test_model_validator_feature_dependencies(self):
        """Test model validator catches feature dependency issues."""
        with pytest.raises(ValidationError) as exc_info:
            LocalDatabaseConfig(
                enable_knowledge_graph=True,
                enable_graph_db=False  # Knowledge graph requires graph DB
            )
        
        assert "Knowledge graph features require graph database" in str(exc_info.value)
    
    def test_model_validator_embedding_dimension_mismatch(self):
        """Test model validator catches embedding dimension mismatches in strict mode."""
        # Test that strict validation mode catches embedding dimension mismatches
        # We need to create a config that will trigger the validation during construction
        with pytest.raises(ValueError) as exc_info:
            # Create a config with mismatched embedding dimensions
            # We'll use model_construct to bypass normal validation, then manually trigger it
            config_data = {
                'embedding_model': "sentence-transformers/all-MiniLM-L6-v2",
                'embedding_dimension': 768,  # Should be 384 for this model
                'enable_vector_search': True,
                'enable_knowledge_graph': False,  # Disable to avoid dependency error
                'enable_ai_chat': False,          # Disable to avoid dependency error
                'enable_export_functionality': False,  # Disable to avoid dependency error
                'enable_analytics': False,        # Disable to avoid dependency error
                '_strict_validation': True        # Enable strict validation
            }
            
            # Create instance and manually set strict validation
            config = LocalDatabaseConfig.model_construct(**config_data)
            config._strict_validation = True
            
            # Manually trigger the model validator
            config.validate_configuration_consistency()
        
        assert "doesn't match model" in str(exc_info.value)
    
    def test_comprehensive_validation_basic_configuration(self):
        """Test comprehensive validation of basic configuration."""
        config = LocalDatabaseConfig(
            postgres_password="weak",  # Should trigger warning
            postgres_pool_size=100,    # Should trigger warning
            enable_relational_db=True,
            enable_vector_search=False,
            enable_graph_db=False,
            enable_knowledge_graph=False,  # Disable to avoid dependency error
            enable_ai_chat=True,  # Should work with relational DB
            enable_export_functionality=True,  # Should work with relational DB
            enable_analytics=True  # Should work with relational DB
        )
        
        validation = config.validate_configuration()
        
        assert validation["valid"] is True  # Should be valid despite warnings
        assert len(validation["warnings"]) > 0
        assert any("password" in warning.lower() for warning in validation["warnings"])
        assert any("pool size" in warning.lower() for warning in validation["warnings"])
    
    def test_comprehensive_validation_all_services_disabled(self):
        """Test validation fails when all services are disabled."""
        config = LocalDatabaseConfig(
            enable_relational_db=False,
            enable_vector_search=False,
            enable_graph_db=False,
            enable_knowledge_graph=False,  # Disable dependent features
            enable_ai_chat=False,
            enable_export_functionality=False,
            enable_analytics=False
        )
        
        validation = config.validate_configuration()
        
        assert validation["valid"] is False
        assert any("All database services are disabled" in issue for issue in validation["issues"])
    
    def test_security_configuration_validation(self):
        """Test security configuration validation."""
        config = LocalDatabaseConfig(
            debug=True,
            environment="production",  # Debug in production should warn
            secret_key="short",        # Short secret key should warn
            postgres_password="123",   # Short password should warn
            require_auth=False         # No auth in production should warn
        )
        
        validation = config.validate_configuration()
        
        warnings = validation["warnings"]
        assert any("debug mode" in warning.lower() for warning in warnings)
        assert any("secret key" in warning.lower() for warning in warnings)
        assert any("password" in warning.lower() for warning in warnings)
        assert any("authentication" in warning.lower() for warning in warnings)
    
    def test_resource_configuration_validation(self):
        """Test resource configuration validation."""
        # Create config with smaller pool sizes first to avoid model validation error
        config = LocalDatabaseConfig(
            postgres_pool_size=50,
            postgres_max_overflow=100,
            neo4j_pool_size=50,
            redis_max_connections=50,
            enable_knowledge_graph=False,  # Disable to avoid dependency issues
            enable_ai_chat=True,  # Works with relational DB
            enable_export_functionality=True,  # Works with relational DB
            enable_analytics=True  # Works with relational DB
        )
        
        # Now update the values that should trigger warnings
        config.postgres_pool_size = 200
        config.postgres_max_overflow = 400
        config.neo4j_pool_size = 300
        config.redis_max_connections = 100
        config.max_file_size = 2 * 1024 * 1024 * 1024  # 2GB
        config.connection_timeout = 600  # 10 minutes
        config.session_timeout = 86400 * 14  # 2 weeks
        
        validation = config.validate_configuration()
        
        warnings = validation["warnings"]
        assert any("connection pool size" in warning.lower() for warning in warnings)
        assert any("file size" in warning.lower() for warning in warnings)
        assert any("timeout" in warning.lower() for warning in warnings)
    
    def test_network_configuration_validation(self):
        """Test network configuration validation."""
        config = LocalDatabaseConfig(
            postgres_host="invalid..hostname",
            api_host="0.0.0.0",
            environment="production",
            api_workers=16
        )
        
        validation = config.validate_configuration()
        
        warnings = validation["warnings"]
        assert any("hostname" in warning.lower() for warning in warnings)
        assert any("all interfaces" in warning.lower() for warning in warnings)
        assert any("workers" in warning.lower() for warning in warnings)
    
    @patch('pathlib.Path.mkdir')
    def test_filesystem_configuration_validation(self, mock_mkdir):
        """Test filesystem configuration validation."""
        mock_mkdir.side_effect = PermissionError("Permission denied")
        
        # Create config with valid dependencies first
        config = LocalDatabaseConfig(
            enable_knowledge_graph=False,  # Disable to avoid dependency issues
            enable_ai_chat=True,  # Works with relational DB
            enable_export_functionality=True,  # Works with relational DB
            enable_analytics=True  # Works with relational DB
        )
        
        # Update paths that should trigger warnings
        config.upload_dir = "relative/path"  # Should warn about relative path
        config.media_dir = "/valid/absolute/path"
        
        validation = config.validate_configuration()
        
        warnings = validation["warnings"]
        assert any("not an absolute path" in warning for warning in warnings)
        assert any("Cannot create" in warning for warning in warnings)
    
    @patch('socket.socket')
    def test_connectivity_validation_success(self, mock_socket):
        """Test successful connectivity validation."""
        mock_sock = Mock()
        mock_sock.connect_ex.return_value = 0  # Success
        mock_socket.return_value = mock_sock
        
        config = LocalDatabaseConfig()
        connectivity = config.validate_connectivity()
        
        assert connectivity["overall_status"] == "healthy"
        assert "postgres" in connectivity["services"]
        assert connectivity["services"]["postgres"]["connected"] is True
    
    @patch('socket.socket')
    def test_connectivity_validation_failure(self, mock_socket):
        """Test connectivity validation with connection failures."""
        mock_sock = Mock()
        mock_sock.connect_ex.return_value = 1  # Connection refused
        mock_socket.return_value = mock_sock
        
        config = LocalDatabaseConfig()
        connectivity = config.validate_connectivity()
        
        assert connectivity["overall_status"] == "unhealthy"
        assert len(connectivity["errors"]) > 0
        assert "postgres" in connectivity["services"]
        assert connectivity["services"]["postgres"]["connected"] is False
    
    @patch('socket.socket')
    def test_connectivity_validation_timeout(self, mock_socket):
        """Test connectivity validation with timeout."""
        mock_sock = Mock()
        mock_sock.connect_ex.side_effect = socket.timeout("Connection timeout")
        mock_socket.return_value = mock_sock
        
        config = LocalDatabaseConfig()
        connectivity = config.validate_connectivity(timeout=1)
        
        assert connectivity["overall_status"] == "unhealthy"
        assert "postgres" in connectivity["services"]
        assert "timeout" in connectivity["services"]["postgres"]["error"].lower()
    
    @patch('subprocess.run')
    def test_docker_environment_validation_success(self, mock_run):
        """Test successful Docker environment validation."""
        # Mock successful Docker and Docker Compose commands
        mock_run.side_effect = [
            Mock(returncode=0, stdout="Docker version 20.10.0"),  # docker --version
            Mock(returncode=0, stdout="docker-compose version 1.29.0"),  # docker-compose --version
            Mock(returncode=0, stdout="version: '3.8'")  # docker-compose config
        ]
        
        with patch('os.path.exists', return_value=True):
            config = LocalDatabaseConfig()
            docker_validation = config.validate_docker_environment()
        
        assert docker_validation["docker_available"] is True
        assert docker_validation["compose_available"] is True
        assert docker_validation["compose_file_exists"] is True
        assert len(docker_validation["errors"]) == 0
    
    @patch('subprocess.run')
    def test_docker_environment_validation_failure(self, mock_run):
        """Test Docker environment validation with failures."""
        # Mock failed Docker command, then failed docker-compose command, then failed docker compose command
        mock_run.side_effect = [
            Mock(returncode=1, stderr="Docker not found"),  # docker --version fails
            Mock(returncode=1, stderr="docker-compose not found"),  # docker-compose --version fails
            Mock(returncode=1, stderr="docker compose not found")  # docker compose version fails
        ]
        
        with patch('os.path.exists', return_value=False):
            config = LocalDatabaseConfig()
            docker_validation = config.validate_docker_environment()
        
        assert docker_validation["docker_available"] is False
        assert docker_validation["compose_available"] is False
        assert docker_validation["compose_file_exists"] is False
        assert len(docker_validation["errors"]) > 0
    
    def test_validate_and_fix_configuration(self):
        """Test configuration validation with automatic fixes."""
        with patch('pathlib.Path.mkdir') as mock_mkdir:
            config = LocalDatabaseConfig(
                upload_dir="/test/upload",
                media_dir="/test/media"
            )
            
            # Mock directory creation to succeed
            mock_mkdir.return_value = None
            
            results = config.validate_and_fix_configuration()
            
            assert "validation" in results
            assert "fixes_applied" in results
            assert "recommendations" in results
    
    def test_hostname_validation(self):
        """Test hostname validation helper method."""
        config = LocalDatabaseConfig()
        
        # Valid hostnames
        assert config._is_valid_hostname("localhost") is True
        assert config._is_valid_hostname("127.0.0.1") is True
        assert config._is_valid_hostname("example.com") is True
        assert config._is_valid_hostname("sub.example.com") is True
        
        # Invalid hostnames
        assert config._is_valid_hostname("") is False
        assert config._is_valid_hostname("invalid..hostname") is False
        assert config._is_valid_hostname("a" * 300) is False  # Too long


class TestEnhancedConfigurationFactory:
    """Test enhanced configuration factory functionality."""
    
    def setup_method(self):
        """Reset environment before each test."""
        self.original_env = dict(os.environ)
        # Clear relevant environment variables
        env_vars_to_clear = [
            'ML_ENVIRONMENT', 'ML_DATABASE_TYPE', 'AWS_DEFAULT_REGION', 'AWS_REGION',
            'NEPTUNE_CLUSTER_ENDPOINT', 'OPENSEARCH_DOMAIN_ENDPOINT',
            'ML_POSTGRES_HOST', 'ML_NEO4J_HOST', 'ML_MILVUS_HOST',
            'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_EXECUTION_ENV'
        ]
        for var in env_vars_to_clear:
            os.environ.pop(var, None)
    
    def teardown_method(self):
        """Restore environment after each test."""
        os.environ.clear()
        os.environ.update(self.original_env)
    
    def test_enhanced_environment_detection_with_validation(self):
        """Test enhanced environment detection with validation."""
        os.environ['ML_DATABASE_TYPE'] = 'local'
        os.environ['AWS_REGION'] = 'invalid-region-format'  # Invalid format
        
        factory = ConfigurationFactory()
        env_info = factory.detect_environment()
        
        assert env_info.detected_type == "local"
        assert len(env_info.warnings) > 0
        assert any("invalid format" in warning.lower() for warning in env_info.warnings)
    
    def test_environment_detection_with_errors(self):
        """Test environment detection error handling."""
        with patch.object(ConfigurationFactory, '_validate_environment_consistency', side_effect=Exception("Test error")):
            factory = ConfigurationFactory()
            env_info = factory.detect_environment()
            
            assert len(env_info.errors) > 0
            assert env_info.confidence <= 0.3  # Reduced confidence due to errors
    
    def test_aws_region_validation(self):
        """Test AWS region format validation."""
        factory = ConfigurationFactory()
        
        # Valid regions
        assert factory._is_valid_aws_region("us-east-1") is True
        assert factory._is_valid_aws_region("eu-west-2") is True
        assert factory._is_valid_aws_region("ap-southeast-1") is True
        
        # Invalid regions
        assert factory._is_valid_aws_region("invalid-region") is False
        assert factory._is_valid_aws_region("us-east") is False
        assert factory._is_valid_aws_region("") is False
    
    def test_neptune_endpoint_validation(self):
        """Test Neptune endpoint format validation."""
        factory = ConfigurationFactory()
        
        # Valid endpoints
        assert factory._is_valid_neptune_endpoint("cluster.neptune.amazonaws.com") is True
        assert factory._is_valid_neptune_endpoint("cluster.cluster-ro.neptune.amazonaws.com") is True
        assert factory._is_valid_neptune_endpoint("test-neptune-cluster.com") is True
        
        # Invalid endpoints
        assert factory._is_valid_neptune_endpoint("invalid-endpoint.com") is False
        assert factory._is_valid_neptune_endpoint("") is False
    
    def test_aws_access_key_validation(self):
        """Test AWS access key format validation."""
        factory = ConfigurationFactory()
        
        # Valid access keys
        assert factory._is_valid_aws_access_key("AKIAIOSFODNN7EXAMPLE") is True
        assert factory._is_valid_aws_access_key("ASIAIOSFODNN7EXAMPLE") is True
        assert factory._is_valid_aws_access_key("AROAIOSFODNN7EXAMPLE") is True
        
        # Invalid access keys
        assert factory._is_valid_aws_access_key("INVALID_KEY_FORMAT") is False
        assert factory._is_valid_aws_access_key("AKIA123") is False  # Too short
        assert factory._is_valid_aws_access_key("") is False
    
    def test_create_config_with_detection_errors(self):
        """Test config creation when environment detection has errors."""
        with patch.object(ConfigurationFactory, 'detect_environment') as mock_detect:
            mock_detect.return_value = EnvironmentInfo(
                detected_type="local",
                confidence=0.5,
                indicators={},
                warnings=[],
                errors=["Critical detection error"]
            )
            
            factory = ConfigurationFactory()
            
            with pytest.raises(EnvironmentDetectionError) as exc_info:
                factory.create_config("auto")
            
            assert "Environment detection failed" in str(exc_info.value)
    
    def test_create_config_with_low_confidence(self):
        """Test config creation with low confidence detection."""
        with patch.object(ConfigurationFactory, 'detect_environment') as mock_detect:
            mock_detect.return_value = EnvironmentInfo(
                detected_type="local",
                confidence=0.3,  # Low confidence
                indicators={},
                warnings=["Low confidence warning"],
                errors=[]
            )
            
            with patch.object(ConfigurationFactory, '_create_local_config') as mock_create:
                mock_config = Mock()
                mock_create.return_value = mock_config
                
                factory = ConfigurationFactory()
                config = factory.create_config("auto")  # Should succeed but log warnings
                
                assert config == mock_config
    
    def test_create_local_config_with_connectivity_check(self):
        """Test local config creation with connectivity validation."""
        with patch.object(ConfigurationFactory, '_create_local_config') as mock_create:
            mock_config = Mock()
            mock_config.validate_configuration.return_value = {"valid": True, "warnings": []}
            mock_config.validate_connectivity.return_value = {
                "overall_status": "partial",
                "errors": ["Service X not reachable"]
            }
            mock_config.validate_docker_environment.return_value = {
                "errors": ["Docker not available"]
            }
            mock_create.return_value = mock_config
            
            factory = ConfigurationFactory()
            config = factory.create_config("local")
            
            assert config == mock_config
    
    def test_create_config_import_error_handling(self):
        """Test proper handling of import errors."""
        with patch.object(ConfigurationFactory, '_create_local_config', side_effect=ConfigurationImportError("Module not found")):
            factory = ConfigurationFactory()
            
            with pytest.raises(ConfigurationFactoryError) as exc_info:
                factory.create_config("local")
            
            assert "Module not found" in str(exc_info.value)
    
    def test_create_config_validation_error_handling(self):
        """Test proper handling of validation errors."""
        with patch.object(ConfigurationFactory, '_create_local_config', side_effect=ConfigurationValidationError("Critical validation error")):
            factory = ConfigurationFactory()
            
            with pytest.raises(ConfigurationFactoryError) as exc_info:
                factory.create_config("local")
            
            assert "Critical validation error" in str(exc_info.value)
    
    def test_validate_environment_setup_comprehensive(self):
        """Test comprehensive environment setup validation."""
        os.environ['ML_DATABASE_TYPE'] = 'local'
        
        with patch.object(ConfigurationFactory, 'create_config') as mock_create:
            mock_config = Mock()
            mock_config.validate_configuration.return_value = {
                "valid": True,
                "warnings": ["Test warning"],
                "issues": []
            }
            mock_config.validate_connectivity.return_value = {
                "overall_status": "healthy",
                "errors": [],
                "warnings": []
            }
            mock_config.validate_docker_environment.return_value = {
                "errors": [],
                "warnings": []
            }
            mock_create.return_value = mock_config
            
            factory = ConfigurationFactory()
            results = factory.validate_environment_setup("auto")
            
            assert results["overall_status"] == "warning"  # Due to config warning
            assert "detection" in results
            assert "configuration" in results
            assert "connectivity" in results
            assert "docker" in results
            assert len(results["recommendations"]) > 0
    
    def test_generate_validation_recommendations(self):
        """Test validation recommendation generation."""
        factory = ConfigurationFactory()
        
        validation_results = {
            "detection": {"confidence": 0.5},  # Low confidence
            "configuration": {
                "warnings": [
                    "PostgreSQL using weak password",
                    "Debug mode enabled in production"
                ]
            },
            "connectivity": {"overall_status": "unhealthy"},
            "docker": {
                "docker_available": False,
                "compose_available": True,
                "compose_file_exists": False
            }
        }
        
        recommendations = factory._generate_validation_recommendations(validation_results)
        
        assert len(recommendations) > 0
        assert any("ML_DATABASE_TYPE" in rec for rec in recommendations)
        assert any("password" in rec.lower() for rec in recommendations)
        assert any("debug mode" in rec.lower() for rec in recommendations)
        assert any("docker" in rec.lower() for rec in recommendations)


class TestConfigurationErrorHandling:
    """Test configuration error handling and custom exceptions."""
    
    def test_configuration_error_hierarchy(self):
        """Test that custom exceptions have proper hierarchy."""
        assert issubclass(ConfigurationError, Exception)
        assert issubclass(ConfigValidationError, ConfigurationError)
        assert issubclass(ConnectivityError, ConfigurationError)
        assert issubclass(ResourceError, ConfigurationError)
        
        assert issubclass(EnvironmentDetectionError, Exception)
        assert issubclass(ConfigurationValidationError, Exception)
        assert issubclass(ConfigurationImportError, Exception)
    
    def test_configuration_error_messages(self):
        """Test that custom exceptions carry proper error messages."""
        error_msg = "Test configuration error"
        
        config_error = ConfigurationError(error_msg)
        assert str(config_error) == error_msg
        
        validation_error = ConfigValidationError(error_msg)
        assert str(validation_error) == error_msg
        
        connectivity_error = ConnectivityError(error_msg)
        assert str(connectivity_error) == error_msg


@pytest.mark.integration
class TestConfigurationValidationIntegration:
    """Integration tests for configuration validation."""
    
    def test_full_validation_cycle_local_config(self):
        """Test complete validation cycle for local configuration."""
        # Create a configuration with some issues
        config = LocalDatabaseConfig(
            postgres_password="weak123",  # Weak password
            debug=True,
            environment="development",
            enable_relational_db=True,
            enable_vector_search=True,
            enable_graph_db=False,
            enable_knowledge_graph=False,  # Disable to avoid dependency error
            enable_ai_chat=True,  # Works with relational DB
            enable_export_functionality=True,  # Works with relational DB
            enable_analytics=True  # Works with relational DB
        )
        
        # Run comprehensive validation
        validation = config.validate_configuration()
        
        # Should be valid but have warnings
        assert validation["valid"] is True
        assert len(validation["warnings"]) > 0
        
        # Test connectivity (will likely fail in test environment)
        connectivity = config.validate_connectivity(timeout=1)
        assert "overall_status" in connectivity
        
        # Test Docker validation
        docker_validation = config.validate_docker_environment()
        assert "docker_available" in docker_validation
    
    def test_configuration_factory_end_to_end(self):
        """Test configuration factory end-to-end validation."""
        factory = ConfigurationFactory()
        
        # Test environment detection
        env_info = factory.detect_environment()
        assert isinstance(env_info, EnvironmentInfo)
        assert env_info.detected_type in ["local", "aws"]
        
        # Test comprehensive validation
        validation_results = factory.validate_environment_setup("auto")
        assert "overall_status" in validation_results
        assert validation_results["overall_status"] in ["healthy", "warning", "error"]
        
        # Should have recommendations
        assert "recommendations" in validation_results
        assert isinstance(validation_results["recommendations"], list)