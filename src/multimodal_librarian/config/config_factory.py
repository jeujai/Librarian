"""
Configuration Factory for Multimodal Librarian

This module provides a factory for creating database configuration objects
based on the environment. It supports both local development and AWS production
configurations with automatic environment detection and validation.

The factory implements environment-based configuration selection and provides
a unified interface for accessing database configuration regardless of the
underlying environment.

Example Usage:
    ```python
    from multimodal_librarian.config.config_factory import get_database_config
    
    # Automatic environment detection
    config = get_database_config()
    
    # Explicit environment selection
    config = get_database_config(environment="local")
    config = get_database_config(environment="aws")
    
    # Use configuration with database factory
    from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
    factory = DatabaseClientFactory(config)
    ```
"""

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Union

logger = logging.getLogger(__name__)

# Type aliases
EnvironmentType = Literal["local", "aws", "auto"]
ConfigType = Union["LocalDatabaseConfig", "AWSNativeConfig"]


class ConfigurationFactoryError(Exception):
    """Base exception for configuration factory errors."""
    pass


class EnvironmentDetectionError(ConfigurationFactoryError):
    """Exception raised when environment detection fails."""
    pass


class ConfigurationValidationError(ConfigurationFactoryError):
    """Exception raised when configuration validation fails."""
    pass


class ConfigurationImportError(ConfigurationFactoryError):
    """Exception raised when configuration modules cannot be imported."""
    pass


@dataclass
class EnvironmentInfo:
    """Information about the detected environment."""
    detected_type: str
    confidence: float  # 0.0 to 1.0
    indicators: Dict[str, Any]
    warnings: List[str]
    errors: List[str] = None
    
    def __post_init__(self):
        """Initialize errors list if not provided."""
        if self.errors is None:
            self.errors = []
    
    def is_reliable(self, min_confidence: float = 0.7) -> bool:
        """Check if detection is reliable based on confidence threshold."""
        return self.confidence >= min_confidence and len(self.errors) == 0
    
    def has_issues(self) -> bool:
        """Check if there are any errors or warnings."""
        return len(self.errors) > 0 or len(self.warnings) > 0


class ConfigurationFactory:
    """
    Factory for creating database configuration objects.
    
    This factory automatically detects the environment and creates the
    appropriate configuration object. It supports both local development
    and AWS production environments.
    
    Environment Detection:
        The factory uses multiple indicators to detect the environment:
        - Environment variables (ML_ENVIRONMENT, ML_DATABASE_TYPE)
        - AWS-specific environment variables (AWS_REGION, etc.)
        - Docker environment detection
        - File system indicators (.env.local, docker-compose.yml)
    
    Configuration Validation:
        All created configurations are validated to ensure they have
        the required settings for their environment.
    """
    
    def __init__(self):
        """Initialize the configuration factory."""
        self._cached_config: Optional[ConfigType] = None
        self._cached_environment: Optional[str] = None
    
    def detect_environment(self) -> EnvironmentInfo:
        """
        Detect the current environment based on various indicators.
        
        This method analyzes the environment to determine whether we're
        running in local development or AWS production mode.
        
        Returns:
            EnvironmentInfo with detection results and confidence score
            
        Raises:
            EnvironmentDetectionError: If detection fails critically
            
        Example:
            ```python
            factory = ConfigurationFactory()
            env_info = factory.detect_environment()
            
            print(f"Detected: {env_info.detected_type} (confidence: {env_info.confidence:.2f})")
            for indicator, value in env_info.indicators.items():
                print(f"  {indicator}: {value}")
            ```
        """
        indicators = {}
        warnings = []
        errors = []
        local_score = 0.0
        aws_score = 0.0
        
        try:
            # Check explicit environment variables
            ml_environment = os.getenv('ML_ENVIRONMENT', '').lower()
            ml_database_type = os.getenv('ML_DATABASE_TYPE', '').lower()
            
            if ml_environment:
                indicators['ML_ENVIRONMENT'] = ml_environment
                if ml_environment in ['local', 'development', 'dev']:
                    local_score += 0.8
                elif ml_environment in ['aws', 'production', 'prod']:
                    aws_score += 0.8
                else:
                    warnings.append(f"Unknown ML_ENVIRONMENT value: {ml_environment}")
            
            if ml_database_type:
                indicators['ML_DATABASE_TYPE'] = ml_database_type
                if ml_database_type == 'local':
                    local_score += 0.9
                elif ml_database_type == 'aws':
                    aws_score += 0.9
                else:
                    warnings.append(f"Unknown ML_DATABASE_TYPE value: {ml_database_type}")
            
            # Check AWS-specific environment variables
            aws_region = os.getenv('AWS_DEFAULT_REGION') or os.getenv('AWS_REGION')
            neptune_endpoint = os.getenv('NEPTUNE_CLUSTER_ENDPOINT')
            opensearch_endpoint = os.getenv('OPENSEARCH_DOMAIN_ENDPOINT')
            
            if aws_region:
                indicators['AWS_REGION'] = aws_region
                aws_score += 0.3
                
                # Validate AWS region format
                if not self._is_valid_aws_region(aws_region):
                    warnings.append(f"AWS region '{aws_region}' has invalid format")
            
            if neptune_endpoint:
                indicators['NEPTUNE_ENDPOINT'] = bool(neptune_endpoint)
                aws_score += 0.4
                
                # Validate Neptune endpoint format
                if not self._is_valid_neptune_endpoint(neptune_endpoint):
                    warnings.append("Neptune endpoint format appears invalid")
            
            if opensearch_endpoint:
                indicators['OPENSEARCH_ENDPOINT'] = bool(opensearch_endpoint)
                aws_score += 0.4
                
                # Validate OpenSearch endpoint format
                if not self._is_valid_opensearch_endpoint(opensearch_endpoint):
                    warnings.append("OpenSearch endpoint format appears invalid")
            
            # Check local development indicators
            postgres_host = os.getenv('ML_POSTGRES_HOST', os.getenv('POSTGRES_HOST', ''))
            neo4j_host = os.getenv('ML_NEO4J_HOST', os.getenv('NEO4J_HOST', ''))
            milvus_host = os.getenv('ML_MILVUS_HOST', os.getenv('MILVUS_HOST', ''))
            
            if postgres_host in ['localhost', '127.0.0.1', 'postgres']:
                indicators['POSTGRES_HOST'] = postgres_host
                local_score += 0.3
            elif postgres_host and not self._is_local_host(postgres_host):
                indicators['POSTGRES_HOST'] = postgres_host
                aws_score += 0.2
            
            if neo4j_host in ['localhost', '127.0.0.1', 'neo4j']:
                indicators['NEO4J_HOST'] = neo4j_host
                local_score += 0.3
            elif neo4j_host and not self._is_local_host(neo4j_host):
                indicators['NEO4J_HOST'] = neo4j_host
                aws_score += 0.2
            
            if milvus_host in ['localhost', '127.0.0.1', 'milvus']:
                indicators['MILVUS_HOST'] = milvus_host
                local_score += 0.3
            elif milvus_host and not self._is_local_host(milvus_host):
                indicators['MILVUS_HOST'] = milvus_host
                aws_score += 0.2
            
            # Check for Docker environment
            if os.path.exists('docker-compose.local.yml'):
                indicators['DOCKER_COMPOSE_LOCAL'] = True
                local_score += 0.2
            
            if os.path.exists('.env.local'):
                indicators['ENV_LOCAL_FILE'] = True
                local_score += 0.2
            
            # Check for AWS credentials/configuration
            aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
            aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
            aws_profile = os.getenv('AWS_PROFILE')
            
            if aws_access_key or aws_secret_key or aws_profile:
                indicators['AWS_CREDENTIALS'] = True
                aws_score += 0.2
                
                # Validate AWS credentials format
                if aws_access_key and not self._is_valid_aws_access_key(aws_access_key):
                    warnings.append("AWS access key format appears invalid")
            
            # Check for ECS/Lambda environment (AWS runtime indicators)
            aws_execution_env = os.getenv('AWS_EXECUTION_ENV')
            lambda_function = os.getenv('AWS_LAMBDA_FUNCTION_NAME')
            
            if aws_execution_env or lambda_function:
                indicators['AWS_RUNTIME'] = True
                aws_score += 0.6
                
                if aws_execution_env:
                    indicators['AWS_EXECUTION_ENV'] = aws_execution_env
                if lambda_function:
                    indicators['AWS_LAMBDA_FUNCTION'] = lambda_function
            
            # Additional validation checks
            self._validate_environment_consistency(indicators, warnings, errors)
            
        except Exception as e:
            errors.append(f"Error during environment detection: {str(e)}")
            logger.exception("Environment detection failed")
        
        # Determine environment based on scores
        if local_score > aws_score:
            detected_type = "local"
            confidence = min(local_score, 1.0)
        elif aws_score > local_score:
            detected_type = "aws"
            confidence = min(aws_score, 1.0)
        else:
            detected_type = "local"  # Default to local
            confidence = 0.1
            warnings.append("Unable to clearly detect environment, defaulting to local")
        
        # Add warnings for ambiguous situations
        if abs(local_score - aws_score) < 0.2 and max(local_score, aws_score) > 0.3:
            warnings.append("Environment detection is ambiguous, consider setting ML_DATABASE_TYPE explicitly")
        
        if confidence < 0.5:
            warnings.append("Low confidence in environment detection, verify configuration")
        
        # Check for critical errors
        if len(errors) > 0:
            confidence = min(confidence, 0.3)  # Reduce confidence if there are errors
        
        return EnvironmentInfo(
            detected_type=detected_type,
            confidence=confidence,
            indicators=indicators,
            warnings=warnings,
            errors=errors
        )
    
    def _is_valid_aws_region(self, region: str) -> bool:
        """Validate AWS region format."""
        import re

        # AWS regions follow pattern: us-east-1, eu-west-2, etc.
        pattern = r'^[a-z]{2,3}-[a-z]+-\d+$'
        return bool(re.match(pattern, region))
    
    def _is_valid_neptune_endpoint(self, endpoint: str) -> bool:
        """Validate Neptune endpoint format."""
        return (
            endpoint.endswith('.neptune.amazonaws.com') or
            endpoint.endswith('.cluster-ro.neptune.amazonaws.com') or
            'neptune' in endpoint.lower()
        )
    
    def _is_valid_opensearch_endpoint(self, endpoint: str) -> bool:
        """Validate OpenSearch endpoint format."""
        return (
            '.es.amazonaws.com' in endpoint or
            '.opensearch.amazonaws.com' in endpoint or
            'search-' in endpoint
        )
    
    def _is_valid_aws_access_key(self, access_key: str) -> bool:
        """Validate AWS access key format."""
        import re

        # AWS access keys are 20 characters, start with AKIA, ASIA, or AROA
        pattern = r'^(AKIA|ASIA|AROA)[A-Z0-9]{16}$'
        return bool(re.match(pattern, access_key))
    
    def _is_local_host(self, host: str) -> bool:
        """Check if host is a local host."""
        return host in ['localhost', '127.0.0.1', '::1', '0.0.0.0']
    
    def _validate_environment_consistency(self, indicators: Dict[str, Any], warnings: List[str], errors: List[str]) -> None:
        """Validate consistency between environment indicators."""
        # Check for conflicting indicators
        has_local_indicators = any(key in indicators for key in ['DOCKER_COMPOSE_LOCAL', 'ENV_LOCAL_FILE'])
        has_aws_indicators = any(key in indicators for key in ['AWS_RUNTIME', 'NEPTUNE_ENDPOINT', 'OPENSEARCH_ENDPOINT'])
        
        if has_local_indicators and has_aws_indicators:
            warnings.append("Mixed local and AWS indicators detected - environment may be misconfigured")
        
        # Check for missing required indicators
        ml_db_type = indicators.get('ML_DATABASE_TYPE')
        if ml_db_type == 'aws':
            if not any(key in indicators for key in ['AWS_REGION', 'AWS_CREDENTIALS', 'AWS_RUNTIME']):
                warnings.append("AWS database type specified but no AWS configuration found")
        elif ml_db_type == 'local':
            if not any(key in indicators for key in ['POSTGRES_HOST', 'NEO4J_HOST', 'MILVUS_HOST', 'DOCKER_COMPOSE_LOCAL']):
                warnings.append("Local database type specified but no local service configuration found")
    
    def create_config(self, environment: EnvironmentType = "auto") -> ConfigType:
        """
        Create a database configuration for the specified environment.
        
        Args:
            environment: Environment type to create config for:
                        - "auto": Automatically detect environment
                        - "local": Force local development configuration
                        - "aws": Force AWS production configuration
                        
        Returns:
            Database configuration object (LocalDatabaseConfig or AWSNativeConfig)
            
        Raises:
            EnvironmentDetectionError: If environment detection fails
            ConfigurationImportError: If required configuration module is not available
            ConfigurationValidationError: If configuration validation fails
            
        Example:
            ```python
            factory = ConfigurationFactory()
            
            # Auto-detect environment
            config = factory.create_config("auto")
            
            # Force specific environment
            local_config = factory.create_config("local")
            aws_config = factory.create_config("aws")
            ```
        """
        # Determine target environment
        if environment == "auto":
            try:
                env_info = self.detect_environment()
                target_env = env_info.detected_type
                
                # Check for critical detection errors
                if env_info.errors:
                    error_msg = f"Environment detection failed: {'; '.join(env_info.errors)}"
                    logger.error(error_msg)
                    raise EnvironmentDetectionError(error_msg)
                
                # Log warnings
                if env_info.warnings:
                    for warning in env_info.warnings:
                        logger.warning(f"Environment detection: {warning}")
                
                # Check confidence level
                if not env_info.is_reliable():
                    warning_msg = (
                        f"Low confidence environment detection: {target_env} "
                        f"(confidence: {env_info.confidence:.2f}). "
                        f"Consider setting ML_DATABASE_TYPE explicitly."
                    )
                    logger.warning(warning_msg)
                
                logger.info(
                    f"Auto-detected environment: {target_env} "
                    f"(confidence: {env_info.confidence:.2f})"
                )
                
            except Exception as e:
                error_msg = f"Failed to detect environment: {str(e)}"
                logger.error(error_msg)
                raise EnvironmentDetectionError(error_msg) from e
        else:
            target_env = environment
            logger.info(f"Using explicit environment: {target_env}")
        
        # Validate environment type
        if target_env not in ["local", "aws"]:
            raise ValueError(f"Unknown environment type: {target_env}")
        
        # Create appropriate configuration
        try:
            if target_env == "local":
                return self._create_local_config()
            elif target_env == "aws":
                return self._create_aws_config()
        except Exception as e:
            error_msg = f"Failed to create {target_env} configuration: {str(e)}"
            logger.error(error_msg)
            raise ConfigurationFactoryError(error_msg) from e
    
    def _create_local_config(self) -> "LocalDatabaseConfig":
        """Create local development configuration with enhanced error handling."""
        try:
            from .local_config import LocalDatabaseConfig
            
            logger.debug("Creating local development configuration")
            config = LocalDatabaseConfig()
            
            # Run comprehensive validation
            validation = config.validate_configuration()
            
            # Handle validation results
            if not validation["valid"]:
                error_msg = f"Local configuration validation failed: {validation['issues']}"
                logger.error(error_msg)
                raise ConfigurationValidationError(error_msg)
            
            # Log warnings
            if validation["warnings"]:
                for warning in validation["warnings"]:
                    logger.warning(f"Local configuration: {warning}")
            
            # Additional connectivity validation (optional)
            try:
                connectivity = config.validate_connectivity(timeout=2)
                if connectivity["overall_status"] == "unhealthy":
                    logger.warning("Local services are not reachable - ensure Docker services are running")
                elif connectivity["overall_status"] == "partial":
                    logger.warning(f"Some local services are not reachable: {connectivity['errors']}")
            except Exception as e:
                logger.debug(f"Connectivity check failed (non-critical): {e}")
            
            # Docker environment validation (optional)
            try:
                docker_validation = config.validate_docker_environment()
                if docker_validation["errors"]:
                    logger.warning(f"Docker environment issues: {docker_validation['errors']}")
            except Exception as e:
                logger.debug(f"Docker validation failed (non-critical): {e}")
            
            logger.info("Successfully created local development configuration")
            return config
            
        except ImportError as e:
            error_msg = (
                "Local database configuration not available. "
                "Ensure local development dependencies are installed."
            )
            logger.error(f"{error_msg} Error: {e}")
            raise ConfigurationImportError(error_msg) from e
        except (ConfigurationValidationError, ConfigurationFactoryError):
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            error_msg = f"Unexpected error creating local configuration: {str(e)}"
            logger.error(error_msg)
            raise ConfigurationFactoryError(error_msg) from e
    
    def _create_aws_config(self) -> "AWSNativeConfig":
        """Create AWS production configuration with enhanced error handling."""
        try:
            from .aws_native_config import AWSNativeConfig
            
            logger.debug("Creating AWS production configuration")
            config = AWSNativeConfig()
            
            # Run validation
            validation = config.validate_configuration()
            
            # Handle validation results
            if not validation["valid"]:
                error_msg = f"AWS configuration validation failed: {validation['issues']}"
                logger.error(error_msg)
                raise ConfigurationValidationError(error_msg)
            
            # Log warnings
            if validation["warnings"]:
                for warning in validation["warnings"]:
                    logger.warning(f"AWS configuration: {warning}")
            
            logger.info("Successfully created AWS production configuration")
            return config
            
        except ImportError as e:
            error_msg = (
                "AWS database configuration not available. "
                "Ensure AWS dependencies are installed and properly configured."
            )
            logger.error(f"{error_msg} Error: {e}")
            raise ConfigurationImportError(error_msg) from e
        except (ConfigurationValidationError, ConfigurationFactoryError):
            # Re-raise our custom exceptions
            raise
        except Exception as e:
            error_msg = f"Unexpected error creating AWS configuration: {str(e)}"
            logger.error(error_msg)
            raise ConfigurationFactoryError(error_msg) from e
    
    def get_cached_config(self, environment: EnvironmentType = "auto") -> ConfigType:
        """
        Get cached configuration or create new one.
        
        This method caches the configuration to avoid repeated creation
        and environment detection overhead.
        
        Args:
            environment: Environment type (same as create_config)
            
        Returns:
            Cached or newly created configuration
        """
        # Check if we need to create new config
        if (self._cached_config is None or 
            self._cached_environment != environment or
            (environment == "auto" and self._should_refresh_auto_detection())):
            
            self._cached_config = self.create_config(environment)
            self._cached_environment = environment
        
        return self._cached_config
    
    def _should_refresh_auto_detection(self) -> bool:
        """
        Check if auto-detection should be refreshed.
        
        This method checks if environment variables have changed
        since the last auto-detection.
        
        IMPORTANT: This now returns False to prevent repeated environment
        detection which triggers blocking Docker validation subprocess calls.
        The Docker validation can take 10-30 seconds and blocks the event loop,
        causing server freezes when health checks are called repeatedly.
        
        If you need to force re-detection, call clear_cache() first.
        """
        # Return False to use cached config and avoid blocking Docker validation
        # The Docker validation uses subprocess.run() which blocks the event loop
        return False
    
    def clear_cache(self) -> None:
        """Clear cached configuration (useful for testing)."""
        self._cached_config = None
        self._cached_environment = None
        logger.debug("Cleared configuration cache")
    
    def validate_environment_setup(self, environment: EnvironmentType = "auto") -> Dict[str, Any]:
        """
        Validate the complete environment setup including configuration and connectivity.
        
        Args:
            environment: Environment type to validate
            
        Returns:
            Comprehensive validation results
        """
        results = {
            "environment": environment,
            "detection": None,
            "configuration": None,
            "connectivity": None,
            "docker": None,
            "overall_status": "unknown",
            "issues": [],
            "warnings": [],
            "recommendations": []
        }
        
        try:
            # Environment detection
            if environment == "auto":
                env_info = self.detect_environment()
                results["detection"] = {
                    "detected_type": env_info.detected_type,
                    "confidence": env_info.confidence,
                    "indicators": env_info.indicators,
                    "warnings": env_info.warnings,
                    "errors": env_info.errors
                }
                
                if env_info.errors:
                    results["issues"].extend(env_info.errors)
                if env_info.warnings:
                    results["warnings"].extend(env_info.warnings)
                
                target_env = env_info.detected_type
            else:
                target_env = environment
            
            # Configuration validation
            try:
                config = self.create_config(target_env)
                config_validation = config.validate_configuration()
                results["configuration"] = config_validation
                
                if not config_validation["valid"]:
                    results["issues"].extend(config_validation["issues"])
                if config_validation["warnings"]:
                    results["warnings"].extend(config_validation["warnings"])
                
                # Additional validations for local environment
                if target_env == "local" and hasattr(config, 'validate_connectivity'):
                    try:
                        connectivity = config.validate_connectivity()
                        results["connectivity"] = connectivity
                        
                        if connectivity["overall_status"] == "unhealthy":
                            results["issues"].extend(connectivity["errors"])
                        elif connectivity["overall_status"] == "partial":
                            results["warnings"].extend(connectivity["warnings"])
                    except Exception as e:
                        results["warnings"].append(f"Connectivity validation failed: {e}")
                    
                    try:
                        docker_validation = config.validate_docker_environment()
                        results["docker"] = docker_validation
                        
                        if docker_validation["errors"]:
                            results["warnings"].extend(docker_validation["errors"])
                    except Exception as e:
                        results["warnings"].append(f"Docker validation failed: {e}")
                
            except Exception as e:
                results["issues"].append(f"Configuration creation failed: {e}")
        
        except Exception as e:
            results["issues"].append(f"Environment validation failed: {e}")
        
        # Determine overall status
        if len(results["issues"]) == 0:
            if len(results["warnings"]) == 0:
                results["overall_status"] = "healthy"
            else:
                results["overall_status"] = "warning"
        else:
            results["overall_status"] = "error"
        
        # Generate recommendations
        results["recommendations"] = self._generate_validation_recommendations(results)
        
        return results
    
    def _generate_validation_recommendations(self, validation_results: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on validation results."""
        recommendations = []
        
        # Environment detection recommendations
        detection = validation_results.get("detection")
        if detection and detection.get("confidence", 1.0) < 0.7:
            recommendations.append(
                "Set ML_DATABASE_TYPE environment variable explicitly to avoid detection ambiguity"
            )
        
        # Configuration recommendations
        config = validation_results.get("configuration")
        if config and config.get("warnings"):
            for warning in config["warnings"]:
                if "password" in warning.lower():
                    recommendations.append("Update database passwords to use strong, unique values")
                elif "pool size" in warning.lower():
                    recommendations.append("Consider reducing connection pool sizes for local development")
                elif "debug mode" in warning.lower():
                    recommendations.append("Disable debug mode in production environments")
        
        # Connectivity recommendations
        connectivity = validation_results.get("connectivity")
        if connectivity and connectivity.get("overall_status") != "healthy":
            recommendations.append("Ensure all required services are running (try 'docker-compose up -d')")
        
        # Docker recommendations
        docker = validation_results.get("docker")
        if docker:
            if not docker.get("docker_available"):
                recommendations.append("Install Docker to use local development environment")
            elif not docker.get("compose_available"):
                recommendations.append("Install Docker Compose to manage local services")
            elif not docker.get("compose_file_exists"):
                recommendations.append("Create docker-compose.local.yml file for local services")
        
        return recommendations
    
    def get_environment_summary(self) -> Dict[str, Any]:
        """
        Get a summary of the current environment configuration.
        
        Returns:
            Dictionary with environment information and configuration summary
        """
        env_info = self.detect_environment()
        
        summary = {
            "detection": {
                "detected_type": env_info.detected_type,
                "confidence": env_info.confidence,
                "indicators": env_info.indicators,
                "warnings": env_info.warnings
            }
        }
        
        # Add configuration info if available
        if self._cached_config:
            if hasattr(self._cached_config, 'get_environment_info'):
                summary["configuration"] = self._cached_config.get_environment_info()
            else:
                summary["configuration"] = {
                    "type": getattr(self._cached_config, 'database_type', 'unknown'),
                    "backend": getattr(self._cached_config, 'get_backend_type', lambda: 'unknown')()
                }
        
        return summary


# Global factory instance
_global_factory: Optional[ConfigurationFactory] = None


def get_configuration_factory() -> ConfigurationFactory:
    """Get or create global configuration factory instance."""
    global _global_factory
    
    if _global_factory is None:
        _global_factory = ConfigurationFactory()
    
    return _global_factory


def get_database_config(environment: EnvironmentType = "auto") -> ConfigType:
    """
    Get database configuration for the specified environment.
    
    This is the main entry point for getting database configuration.
    It uses the global factory instance and caches results for performance.
    
    Args:
        environment: Environment type:
                    - "auto": Automatically detect environment (default)
                    - "local": Force local development configuration
                    - "aws": Force AWS production configuration
                    
    Returns:
        Database configuration object (LocalDatabaseConfig or AWSNativeConfig)
        
    Raises:
        ImportError: If required configuration module is not available
        ValueError: If environment detection fails or configuration is invalid
        
    Example:
        ```python
        # Most common usage - auto-detect environment
        config = get_database_config()
        
        # Force specific environment
        local_config = get_database_config("local")
        aws_config = get_database_config("aws")
        
        # Use with database factory
        from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
        factory = DatabaseClientFactory(config)
        ```
    """
    factory = get_configuration_factory()
    return factory.get_cached_config(environment)


def detect_environment() -> EnvironmentInfo:
    """
    Detect the current environment.
    
    This is a convenience function that uses the global factory
    to detect the environment.
    
    Returns:
        EnvironmentInfo with detection results
        
    Example:
        ```python
        env_info = detect_environment()
        print(f"Environment: {env_info.detected_type}")
        print(f"Confidence: {env_info.confidence:.2f}")
        
        if env_info.warnings:
            print("Warnings:")
            for warning in env_info.warnings:
                print(f"  - {warning}")
        ```
    """
    factory = get_configuration_factory()
    return factory.detect_environment()


def get_environment_summary() -> Dict[str, Any]:
    """
    Get a summary of the current environment and configuration.
    
    Returns:
        Dictionary with comprehensive environment information
        
    Example:
        ```python
        summary = get_environment_summary()
        print(f"Detected: {summary['detection']['detected_type']}")
        print(f"Confidence: {summary['detection']['confidence']:.2f}")
        
        if 'configuration' in summary:
            config_info = summary['configuration']
            print(f"Backend: {config_info.get('backend_type', 'unknown')}")
        ```
    """
    factory = get_configuration_factory()
    return factory.get_environment_summary()


def clear_configuration_cache() -> None:
    """
    Clear the configuration cache.
    
    This forces the next call to get_database_config() to recreate
    the configuration and re-detect the environment. Useful for
    testing or when environment variables change at runtime.
    
    Example:
        ```python
        # Change environment variable
        os.environ['ML_DATABASE_TYPE'] = 'aws'
        
        # Clear cache to pick up changes
        clear_configuration_cache()
        
        # Get new configuration
        config = get_database_config()
        ```
    """
    factory = get_configuration_factory()
    factory.clear_cache()


def reset_configuration_factory() -> None:
    """
    Reset the global configuration factory (useful for testing).
    
    This clears the global factory instance, forcing a new one
    to be created on the next call to get_configuration_factory().
    """
    global _global_factory
    _global_factory = None