"""
Local Development Database Configuration for Multimodal Librarian

This module provides configuration management for local development database services
(PostgreSQL, Neo4j, and Milvus) running in Docker containers.

The configuration is designed to work seamlessly with docker-compose.local.yml
and provides the same interface as AWSNativeConfig for consistent usage.
"""

import logging
import os
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class ConfigurationError(Exception):
    """Base exception for configuration errors."""
    pass


class ValidationError(ConfigurationError):
    """Exception raised when configuration validation fails."""
    pass


class ConnectivityError(ConfigurationError):
    """Exception raised when connectivity checks fail."""
    pass


class ResourceError(ConfigurationError):
    """Exception raised when resource checks fail."""
    pass


class LocalDatabaseConfig(BaseSettings):
    """
    Configuration manager for local development database services.
    
    This class handles configuration for:
    - PostgreSQL (relational database)
    - Neo4j (graph database)
    - Milvus (vector database)
    
    All settings can be overridden via environment variables with the ML_ prefix.
    
    Example:
        ```python
        # Use default configuration
        config = LocalDatabaseConfig()
        
        # Override via environment variables
        os.environ['ML_POSTGRES_HOST'] = 'custom-postgres'
        os.environ['ML_NEO4J_PASSWORD'] = 'custom-password'
        config = LocalDatabaseConfig()
        ```
    """
    
    # Environment identification
    database_type: Literal["local"] = "local"
    environment: str = Field(default="local", description="Environment name")
    
    # PostgreSQL Configuration
    postgres_host: str = Field(default="localhost", description="PostgreSQL host")
    postgres_port: int = Field(default=5432, description="PostgreSQL port")
    postgres_db: str = Field(default="multimodal_librarian", description="PostgreSQL database name")
    postgres_user: str = Field(default="ml_user", description="PostgreSQL username")
    postgres_password: str = Field(default="ml_password", description="PostgreSQL password")
    postgres_pool_size: int = Field(default=10, description="PostgreSQL connection pool size")
    postgres_max_overflow: int = Field(default=20, description="PostgreSQL max overflow connections")
    postgres_pool_recycle: int = Field(default=3600, description="PostgreSQL pool recycle time (seconds)")
    
    # Neo4j Configuration
    neo4j_host: str = Field(default="localhost", description="Neo4j host")
    neo4j_port: int = Field(default=7687, description="Neo4j Bolt port")
    neo4j_http_port: int = Field(default=7474, description="Neo4j HTTP port")
    neo4j_user: str = Field(default="neo4j", description="Neo4j username")
    neo4j_password: str = Field(default="ml_password", description="Neo4j password")
    neo4j_pool_size: int = Field(default=100, description="Neo4j connection pool size")
    neo4j_max_connection_lifetime: int = Field(default=3600, description="Neo4j max connection lifetime (seconds)")
    
    # Milvus Configuration
    milvus_host: str = Field(default="localhost", description="Milvus host")
    milvus_port: int = Field(default=19530, description="Milvus port")
    milvus_user: str = Field(default="", description="Milvus username (optional)")
    milvus_password: str = Field(default="", description="Milvus password (optional)")
    milvus_default_collection: str = Field(default="documents", description="Default Milvus collection name")
    milvus_index_type: str = Field(default="AUTO", description="Milvus index type (AUTO for dynamic selection)")
    milvus_metric_type: str = Field(default="L2", description="Milvus distance metric")
    milvus_nlist: int = Field(default=1024, description="Milvus index parameter nlist (for IVF indexes)")
    milvus_nprobe: int = Field(default=10, description="Milvus search parameter nprobe (for IVF indexes)")
    milvus_ef: int = Field(default=64, description="Milvus search parameter ef (for HNSW index)")
    milvus_m: int = Field(default=16, description="Milvus index parameter M (for HNSW index)")
    milvus_ef_construction: int = Field(default=200, description="Milvus index parameter efConstruction (for HNSW index)")
    milvus_auto_optimize: bool = Field(default=True, description="Enable automatic index optimization")
    milvus_optimization_interval: int = Field(default=3600, description="Optimization check interval in seconds")
    
    # Redis Configuration (for caching)
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_password: str = Field(default="", description="Redis password (optional)")
    redis_max_connections: int = Field(default=10, description="Redis max connections")
    cache_ttl: int = Field(default=3600, description="Cache TTL in seconds")
    
    # Feature Flags
    enable_relational_db: bool = Field(default=True, description="Enable PostgreSQL")
    enable_vector_search: bool = Field(default=True, description="Enable Milvus vector search")
    enable_graph_db: bool = Field(default=True, description="Enable Neo4j graph database")
    enable_redis_cache: bool = Field(default=True, description="Enable Redis caching")
    enable_document_upload: bool = Field(default=True, description="Enable document upload functionality")
    enable_knowledge_graph: bool = Field(default=True, description="Enable knowledge graph features")
    enable_ai_chat: bool = Field(default=True, description="Enable AI chat functionality")
    enable_export_functionality: bool = Field(default=True, description="Enable export features")
    enable_analytics: bool = Field(default=True, description="Enable analytics")
    enable_user_management: bool = Field(default=False, description="Enable user management (disabled for local dev)")
    
    # Application Configuration
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    api_workers: int = Field(default=1, description="Number of API workers")
    debug: bool = Field(default=True, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    
    # File Storage Configuration
    upload_dir: str = Field(default="/app/uploads", description="Upload directory")
    media_dir: str = Field(default="/app/media", description="Media directory")
    export_dir: str = Field(default="/app/exports", description="Export directory")
    backup_dir: str = Field(default="/app/backups", description="Backup directory")
    log_dir: str = Field(default="/app/logs", description="Log directory")
    max_file_size: int = Field(default=10 * 1024 * 1024 * 1024, description="Max file size in bytes (10GB - effectively unlimited)")
    max_files_per_upload: int = Field(default=10, description="Max files per upload")
    
    # Security Configuration
    secret_key: str = Field(default="local-dev-secret-key-change-in-production", description="Application secret key")
    require_auth: bool = Field(default=False, description="Require authentication")
    enable_registration: bool = Field(default=True, description="Enable user registration")
    session_timeout: int = Field(default=86400, description="Session timeout in seconds")
    rate_limit_per_minute: int = Field(default=100, description="Rate limit per minute")
    
    # Hot Reload Configuration
    enable_hot_reload: bool = Field(default=True, description="Enable hot reload for development")
    watchdog_enabled: bool = Field(default=True, description="Enable file watching")
    reload_dirs: str = Field(default="/app/src", description="Directories to watch for changes")
    reload_delay: float = Field(default=1.0, description="Reload delay in seconds")
    
    # Connection Settings
    connection_timeout: int = Field(default=60, description="Database connection timeout (seconds)")
    query_timeout: int = Field(default=30, description="Database query timeout (seconds)")
    max_retries: int = Field(default=3, description="Maximum connection retry attempts")
    retry_delay: float = Field(default=1.0, description="Delay between retry attempts (seconds)")
    retry_backoff_factor: float = Field(default=2.0, description="Backoff factor for retry delays")
    
    # Performance Settings
    connection_pooling: bool = Field(default=True, description="Enable connection pooling")
    query_caching: bool = Field(default=True, description="Enable query result caching")
    enable_query_logging: bool = Field(default=False, description="Enable SQL/Cypher query logging")
    
    # Connection Pool Optimization Settings
    enable_pool_optimization: bool = Field(default=True, description="Enable automatic connection pool optimization")
    pool_optimization_strategy: str = Field(default="balanced", description="Pool optimization strategy (conservative, balanced, aggressive)")
    pool_monitoring_interval: int = Field(default=30, description="Pool monitoring interval in seconds")
    pool_optimization_interval: int = Field(default=300, description="Pool optimization interval in seconds")
    enable_auto_pool_optimization: bool = Field(default=False, description="Enable automatic pool optimization")
    pool_target_utilization: float = Field(default=0.7, description="Target pool utilization (0.0-1.0)")
    pool_connection_timeout_threshold: float = Field(default=5.0, description="Connection timeout threshold for warnings")
    pool_stale_connection_threshold: int = Field(default=3600, description="Stale connection threshold in seconds")
    
    # Advanced Pool Settings
    postgres_pool_pre_ping: bool = Field(default=True, description="Enable PostgreSQL pool pre-ping")
    postgres_pool_reset_on_return: str = Field(default="commit", description="PostgreSQL pool reset behavior")
    neo4j_connection_acquisition_timeout: int = Field(default=60, description="Neo4j connection acquisition timeout")
    neo4j_max_transaction_retry_time: int = Field(default=30, description="Neo4j max transaction retry time")
    milvus_connection_pool_size: int = Field(default=10, description="Milvus connection pool size")
    milvus_connection_timeout: int = Field(default=60, description="Milvus connection timeout")
    
    # Pool Health Monitoring
    enable_pool_health_monitoring: bool = Field(default=True, description="Enable pool health monitoring")
    pool_health_check_interval: int = Field(default=60, description="Pool health check interval in seconds")
    pool_leak_detection: bool = Field(default=True, description="Enable connection leak detection")
    pool_performance_tracking: bool = Field(default=True, description="Enable pool performance tracking")
    
    # Health Check Settings
    enable_health_checks: bool = Field(default=True, description="Enable connection health checks")
    health_check_interval: int = Field(default=30, description="Health check interval (seconds)")
    health_check_timeout: int = Field(default=10, description="Health check timeout (seconds)")
    health_check_retries: int = Field(default=3, description="Health check retry attempts")
    
    # Embedding Configuration
    embedding_dimension: int = Field(default=768, description="Vector embedding dimension")
    embedding_model: str = Field(default="BAAI/bge-base-en-v1.5", description="Embedding model name")
    
    # Docker Configuration (for health checks and service discovery)
    docker_network: str = Field(default="multimodal-librarian_default", description="Docker network name")
    docker_compose_file: str = Field(default="docker-compose.local.yml", description="Docker compose file")
    
    class Config:
        env_file = ".env.local"
        env_prefix = "ML_"
        case_sensitive = False
        extra = "ignore"  # Allow extra fields from .env.local
        
    @field_validator('postgres_port', 'neo4j_port', 'neo4j_http_port', 'milvus_port', 'redis_port', 'api_port')
    @classmethod
    def validate_ports(cls, v):
        """Validate port numbers are in valid range."""
        if not (1 <= v <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got {v}")
        return v
    
    @field_validator('connection_timeout', 'query_timeout')
    @classmethod
    def validate_timeouts(cls, v):
        """Validate timeout values are positive."""
        if v <= 0:
            raise ValueError(f"Timeout must be positive, got {v}")
        return v
    
    @field_validator('postgres_pool_size', 'postgres_max_overflow', 'neo4j_pool_size', 'redis_max_connections', 'api_workers')
    @classmethod
    def validate_pool_sizes(cls, v):
        """Validate pool sizes are positive."""
        if v <= 0:
            raise ValueError(f"Pool size must be positive, got {v}")
        return v
    
    @field_validator('embedding_dimension')
    @classmethod
    def validate_embedding_dimension(cls, v):
        """Validate embedding dimension is positive."""
        if v <= 0:
            raise ValueError(f"Embedding dimension must be positive, got {v}")
        return v
    
    @field_validator('max_file_size', 'session_timeout', 'cache_ttl')
    @classmethod
    def validate_positive_integers(cls, v):
        """Validate positive integer values."""
        if v <= 0:
            raise ValueError(f"Value must be positive, got {v}")
        return v
    
    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}, got {v}")
        return v.upper()
    
    @field_validator('milvus_metric_type')
    @classmethod
    def validate_milvus_metric(cls, v):
        """Validate Milvus metric type."""
        valid_metrics = ['L2', 'IP', 'COSINE', 'HAMMING', 'JACCARD']
        if v.upper() not in valid_metrics:
            raise ValueError(f"Milvus metric type must be one of {valid_metrics}, got {v}")
        return v.upper()
    
    @field_validator('milvus_index_type')
    @classmethod
    def validate_milvus_index(cls, v):
        """Validate Milvus index type."""
        valid_indexes = ['AUTO', 'FLAT', 'IVF_FLAT', 'IVF_SQ8', 'IVF_PQ', 'HNSW', 'ANNOY']
        if v.upper() not in valid_indexes:
            raise ValueError(f"Milvus index type must be one of {valid_indexes}, got {v}")
        return v.upper()
    
    @field_validator('pool_optimization_strategy')
    @classmethod
    def validate_pool_optimization_strategy(cls, v):
        """Validate pool optimization strategy."""
        valid_strategies = ['conservative', 'balanced', 'aggressive', 'custom']
        if v.lower() not in valid_strategies:
            raise ValueError(f"Pool optimization strategy must be one of {valid_strategies}, got {v}")
        return v.lower()
    
    @field_validator('pool_target_utilization')
    @classmethod
    def validate_pool_target_utilization(cls, v):
        """Validate pool target utilization."""
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"Pool target utilization must be between 0.0 and 1.0, got {v}")
        return v
    
    @field_validator('pool_connection_timeout_threshold')
    @classmethod
    def validate_pool_connection_timeout_threshold(cls, v):
        """Validate pool connection timeout threshold."""
        if v <= 0:
            raise ValueError(f"Pool connection timeout threshold must be positive, got {v}")
        return v
    
    @field_validator('postgres_pool_reset_on_return')
    @classmethod
    def validate_postgres_pool_reset_on_return(cls, v):
        """Validate PostgreSQL pool reset behavior."""
        valid_values = ['commit', 'rollback', None]
        if v not in valid_values:
            raise ValueError(f"PostgreSQL pool reset behavior must be one of {valid_values}, got {v}")
        return v
    
    @model_validator(mode='after')
    def validate_configuration_consistency(self):
        """Validate configuration consistency and dependencies."""
        # Skip validation in test mode (when environment is 'test' or when explicitly disabled)
        if (hasattr(self, '_skip_validation') and self._skip_validation) or \
           (hasattr(self, 'environment') and self.environment == 'test'):
            return self
        
        errors = []
        
        # Check port conflicts
        ports_in_use = []
        if self.enable_relational_db:
            ports_in_use.append(('PostgreSQL', self.postgres_port))
        if self.enable_graph_db:
            ports_in_use.append(('Neo4j Bolt', self.neo4j_port))
            ports_in_use.append(('Neo4j HTTP', self.neo4j_http_port))
        if self.enable_vector_search:
            ports_in_use.append(('Milvus', self.milvus_port))
        if self.enable_redis_cache:
            ports_in_use.append(('Redis', self.redis_port))
        
        ports_in_use.append(('API', self.api_port))
        
        # Check for port conflicts
        port_numbers = [port for _, port in ports_in_use]
        if len(port_numbers) != len(set(port_numbers)):
            port_counts = {}
            for service, port in ports_in_use:
                if port in port_counts:
                    port_counts[port].append(service)
                else:
                    port_counts[port] = [service]
            
            conflicts = {port: services for port, services in port_counts.items() if len(services) > 1}
            for port, services in conflicts.items():
                errors.append(f"Port {port} is used by multiple services: {', '.join(services)}")
        
        # Check feature dependencies (only if features are enabled)
        if self.enable_knowledge_graph and not self.enable_graph_db:
            errors.append("Knowledge graph features require graph database to be enabled")
        
        if self.enable_ai_chat and not (self.enable_vector_search or self.enable_relational_db):
            errors.append("AI chat requires at least vector search or relational database")
        
        if self.enable_export_functionality and not self.enable_relational_db:
            errors.append("Export functionality requires relational database for metadata")
        
        if self.enable_analytics and not self.enable_relational_db:
            errors.append("Analytics requires relational database for data storage")
        
        # Check resource constraints
        total_pool_connections = 0
        if self.enable_relational_db:
            total_pool_connections += self.postgres_pool_size + self.postgres_max_overflow
        if self.enable_graph_db:
            total_pool_connections += self.neo4j_pool_size
        if self.enable_redis_cache:
            total_pool_connections += self.redis_max_connections
        
        if total_pool_connections > 500:
            errors.append(f"Total connection pool size ({total_pool_connections}) may exceed system limits")
        
        # Check directory paths
        directories = [
            self.upload_dir, self.media_dir, self.export_dir, 
            self.backup_dir, self.log_dir
        ]
        
        for directory in directories:
            if not directory.startswith('/'):
                errors.append(f"Directory path must be absolute: {directory}")
        
        # Check embedding model compatibility
        if self.enable_vector_search and self.embedding_model:
            # Known models and their expected dimensions
            model_dimensions = {
                'sentence-transformers/all-MiniLM-L6-v2': 384,
                'sentence-transformers/all-mpnet-base-v2': 768,
                'sentence-transformers/all-distilroberta-v1': 768,
                'sentence-transformers/paraphrase-MiniLM-L6-v2': 384,
                'BAAI/bge-base-en-v1.5': 768,
                'bge-base-en-v1.5': 768,
            }
            
            if self.embedding_model in model_dimensions:
                expected_dim = model_dimensions[self.embedding_model]
                if self.embedding_dimension != expected_dim:
                    # Check if strict validation is enabled
                    strict_validation = getattr(self, '_strict_validation', False)
                    if strict_validation:
                        errors.append(
                            f"Embedding dimension {self.embedding_dimension} doesn't match "
                            f"model {self.embedding_model} expected dimension {expected_dim}"
                        )
        
        if errors:
            raise ValueError(f"Configuration validation failed: {'; '.join(errors)}")
        
        return self
    
    @classmethod
    def create_test_config(cls, **kwargs):
        """
        Create a configuration for testing that bypasses strict validation.
        
        This method allows creating configurations with non-standard settings
        for testing purposes without triggering validation errors.
        
        Args:
            **kwargs: Configuration parameters to override
            
        Returns:
            LocalDatabaseConfig instance with validation bypassed
        """
        # Set default test values that disable features to avoid dependency errors
        test_defaults = {
            'environment': 'test',
            'enable_knowledge_graph': False,
            'enable_ai_chat': False,
            'enable_export_functionality': False,
            'enable_analytics': False,
            '_skip_validation': True
        }
        
        # Merge with provided kwargs, giving priority to kwargs
        config_data = {**test_defaults, **kwargs}
        
        # Create instance with validation bypassed
        instance = cls.model_construct(**config_data)
        instance._skip_validation = True
        
        return instance
    
    def get_backend_type(self) -> str:
        """Get the backend type (always 'local' for this config)."""
        return "local"
    
    def is_local_enabled(self) -> bool:
        """Check if local development mode is enabled (always True)."""
        return True
    
    def is_aws_native_enabled(self) -> bool:
        """Check if AWS-native mode is enabled (always False for local config)."""
        return False
    
    def get_postgres_connection_string(self, async_driver: bool = True, include_pool_params: bool = False) -> str:
        """
        Get PostgreSQL connection string for local development.
        
        This method generates connection strings optimized for local development
        with Docker containers. It supports both async and sync drivers and
        can include connection pool parameters.
        
        Args:
            async_driver: Whether to use async driver (asyncpg) or sync (psycopg2)
            include_pool_params: Whether to include connection pool parameters in URL
            
        Returns:
            PostgreSQL connection string with appropriate driver and parameters
            
        Example:
            # Async connection string
            postgresql+asyncpg://ml_user:ml_password@localhost:5432/multimodal_librarian
            
            # Sync connection string with pool params
            postgresql+psycopg2://ml_user:ml_password@localhost:5432/multimodal_librarian?pool_size=10&max_overflow=20
        """
        # Choose driver based on async_driver parameter
        if async_driver:
            driver = "postgresql+asyncpg"
        else:
            driver = "postgresql+psycopg2"
        
        # Build base connection string
        connection_string = (
            f"{driver}://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )
        
        # Add connection pool parameters if requested (mainly for sync connections)
        if include_pool_params and not async_driver:
            params = []
            params.append(f"pool_size={self.postgres_pool_size}")
            params.append(f"max_overflow={self.postgres_max_overflow}")
            params.append(f"pool_recycle={self.postgres_pool_recycle}")
            params.append(f"pool_timeout={self.connection_timeout}")
            
            if params:
                connection_string += "?" + "&".join(params)
        
        return connection_string
    
    def get_neo4j_uri(self, protocol: str = "bolt") -> str:
        """
        Get Neo4j connection URI for local development.
        
        This method generates Neo4j connection URIs optimized for local development
        with Docker containers. It supports multiple protocols and includes
        connection parameters for optimal performance.
        
        Args:
            protocol: Connection protocol ("bolt", "neo4j", "bolt+s", "neo4j+s")
            
        Returns:
            Neo4j connection URI with specified protocol (without credentials)
            
        Example:
            bolt://localhost:7687
            neo4j://localhost:7687
            
        Note:
            Credentials should be passed separately via the auth parameter
            when creating the driver, not embedded in the URI.
        """
        # Validate protocol
        valid_protocols = ["bolt", "neo4j", "bolt+s", "neo4j+s"]
        if protocol not in valid_protocols:
            raise ValueError(f"Invalid protocol '{protocol}'. Must be one of: {valid_protocols}")
        
        # For local development, we typically don't use TLS
        if protocol.endswith("+s") and self.neo4j_host in ["localhost", "127.0.0.1", "neo4j"]:
            logger.warning(f"Using TLS protocol '{protocol}' with local host '{self.neo4j_host}' - this may cause connection issues")
        
        # Build URI without authentication (credentials passed separately via auth parameter)
        return f"{protocol}://{self.neo4j_host}:{self.neo4j_port}"
    
    def get_neo4j_http_uri(self, secure: bool = False) -> str:
        """
        Get Neo4j HTTP URI for browser access and REST API.
        
        This method generates Neo4j HTTP URIs for browser access and REST API
        operations. It supports both HTTP and HTTPS protocols.
        
        Args:
            secure: Whether to use HTTPS (True) or HTTP (False)
            
        Returns:
            Neo4j HTTP URI for browser/REST access
            
        Example:
            http://localhost:7474
            https://localhost:7473
        """
        protocol = "https" if secure else "http"
        
        # For local development, warn about HTTPS usage
        if secure and self.neo4j_host in ["localhost", "127.0.0.1", "neo4j"]:
            logger.warning(f"Using HTTPS with local host '{self.neo4j_host}' - ensure Neo4j is configured for TLS")
        
        return f"{protocol}://{self.neo4j_host}:{self.neo4j_http_port}"
    
    def get_milvus_connection_config(self) -> Dict[str, Any]:
        """
        Get Milvus connection configuration for local development.
        
        This method returns a configuration dictionary for connecting to Milvus
        with all necessary parameters for local development setup.
        
        Returns:
            Dictionary with Milvus connection parameters
            
        Example:
            {
                "host": "localhost",
                "port": 19530,
                "user": "",
                "password": "",
                "secure": False,
                "timeout": 60
            }
        """
        return {
            "host": self.milvus_host,
            "port": self.milvus_port,
            "user": self.milvus_user,
            "password": self.milvus_password,
            "secure": False,  # Local development typically doesn't use TLS
            "timeout": self.connection_timeout,
            "pool_size": 10,  # Default pool size for local development
            "retry_attempts": self.max_retries
        }
    
    def get_milvus_uri(self) -> str:
        """
        Get Milvus connection URI for local development.
        
        This method generates a Milvus connection URI that can be used
        for connection string-based configurations.
        
        Returns:
            Milvus connection URI
            
        Example:
            milvus://localhost:19530
            milvus://user:password@localhost:19530
        """
        if self.milvus_user and self.milvus_password:
            return f"milvus://{self.milvus_user}:{self.milvus_password}@{self.milvus_host}:{self.milvus_port}"
        else:
            return f"milvus://{self.milvus_host}:{self.milvus_port}"
    
    def get_redis_connection_string(self, include_auth: bool = True) -> str:
        """
        Get Redis connection string for local development.
        
        This method generates Redis connection strings optimized for local
        development with Docker containers.
        
        Args:
            include_auth: Whether to include authentication in the connection string
            
        Returns:
            Redis connection string
            
        Example:
            redis://localhost:6379/0
            redis://:password@localhost:6379/0
        """
        # Build connection string
        if include_auth and self.redis_password:
            # Redis uses empty username with password
            connection_string = f"redis://:{self.redis_password}@{self.redis_host}:{self.redis_port}/{self.redis_db}"
        else:
            connection_string = f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
        
        return connection_string
    
    def get_redis_connection_config(self) -> Dict[str, Any]:
        """
        Get Redis connection configuration for local development.
        
        This method returns a configuration dictionary for connecting to Redis
        with all necessary parameters for local development setup.
        
        Returns:
            Dictionary with Redis connection parameters
            
        Example:
            {
                "host": "localhost",
                "port": 6379,
                "db": 0,
                "password": None,
                "max_connections": 10,
                "socket_timeout": 30,
                "socket_connect_timeout": 30
            }
        """
        return {
            "host": self.redis_host,
            "port": self.redis_port,
            "db": self.redis_db,
            "password": self.redis_password if self.redis_password else None,
            "max_connections": self.redis_max_connections,
            "socket_timeout": self.connection_timeout,
            "socket_connect_timeout": self.connection_timeout,
            "retry_on_timeout": True,
            "health_check_interval": 30
        }
    
    def get_relational_db_config(self) -> Dict[str, Any]:
        """
        Get relational database configuration.
        
        Returns:
            Configuration dictionary for PostgreSQL
        """
        pool_config = self.get_connection_pool_config()["postgres"]
        retry_config = self.get_retry_config()["postgres"]
        health_config = self.get_health_monitoring_config()["postgres"]
        
        return {
            "type": "postgresql",
            "host": self.postgres_host,
            "port": self.postgres_port,
            "database": self.postgres_db,
            "user": self.postgres_user,
            "password": self.postgres_password,
            "connection_string": self.get_postgres_connection_string(async_driver=True),
            "sync_connection_string": self.get_postgres_connection_string(async_driver=False),
            "connection_string_with_pool": self.get_postgres_connection_string(async_driver=False, include_pool_params=True),
            "pool_size": self.postgres_pool_size,
            "max_overflow": self.postgres_max_overflow,
            "pool_recycle": self.postgres_pool_recycle,
            "timeout": self.connection_timeout,
            "max_retries": self.max_retries,
            "echo": self.enable_query_logging,
            "pool_config": pool_config,
            "retry_config": retry_config,
            "health_config": health_config
        }
    
    def get_graph_db_config(self) -> Dict[str, Any]:
        """
        Get graph database configuration.
        
        Returns:
            Configuration dictionary for Neo4j
        """
        pool_config = self.get_connection_pool_config()["neo4j"]
        retry_config = self.get_retry_config()["neo4j"]
        health_config = self.get_health_monitoring_config()["neo4j"]
        
        return {
            "type": "neo4j",
            "uri": self.get_neo4j_uri(protocol="bolt"),
            "neo4j_uri": self.get_neo4j_uri(protocol="neo4j"),
            "http_uri": self.get_neo4j_http_uri(secure=False),
            "https_uri": self.get_neo4j_http_uri(secure=True),
            "host": self.neo4j_host,
            "port": self.neo4j_port,
            "http_port": self.neo4j_http_port,
            "user": self.neo4j_user,
            "password": self.neo4j_password,
            "pool_size": self.neo4j_pool_size,
            "max_connection_lifetime": self.neo4j_max_connection_lifetime,
            "timeout": self.connection_timeout,
            "max_retries": self.max_retries,
            "encrypted": False,  # Local development typically doesn't use encryption
            "trust": True,  # Trust local certificates
            "pool_config": pool_config,
            "retry_config": retry_config,
            "health_config": health_config
        }
    
    def get_vector_db_config(self) -> Dict[str, Any]:
        """
        Get vector database configuration.
        
        Returns:
            Configuration dictionary for Milvus
        """
        milvus_config = self.get_milvus_connection_config()
        pool_config = self.get_connection_pool_config()["milvus"]
        retry_config = self.get_retry_config()["milvus"]
        health_config = self.get_health_monitoring_config()["milvus"]
        
        return {
            "type": "milvus",
            "host": self.milvus_host,
            "port": self.milvus_port,
            "user": self.milvus_user,
            "password": self.milvus_password,
            "uri": self.get_milvus_uri(),
            "connection_config": milvus_config,
            "default_collection": self.milvus_default_collection,
            "index_type": self.milvus_index_type,
            "metric_type": self.milvus_metric_type,
            "nlist": self.milvus_nlist,
            "nprobe": self.milvus_nprobe,
            "ef": self.milvus_ef,
            "m": self.milvus_m,
            "ef_construction": self.milvus_ef_construction,
            "auto_optimize": self.milvus_auto_optimize,
            "optimization_interval": self.milvus_optimization_interval,
            "embedding_dimension": self.embedding_dimension,
            "embedding_model": self.embedding_model,
            "timeout": self.connection_timeout,
            "max_retries": self.max_retries,
            "secure": False,  # Local development typically doesn't use TLS
            "pool_config": pool_config,
            "retry_config": retry_config,
            "health_config": health_config
        }
    
    def get_redis_config(self) -> Dict[str, Any]:
        """
        Get Redis cache configuration.
        
        Returns:
            Configuration dictionary for Redis
        """
        redis_config = self.get_redis_connection_config()
        pool_config = self.get_connection_pool_config()["redis"]
        retry_config = self.get_retry_config()["redis"]
        health_config = self.get_health_monitoring_config()["redis"]
        
        return {
            "type": "redis",
            "host": self.redis_host,
            "port": self.redis_port,
            "db": self.redis_db,
            "password": self.redis_password,
            "connection_string": self.get_redis_connection_string(include_auth=True),
            "connection_string_no_auth": self.get_redis_connection_string(include_auth=False),
            "connection_config": redis_config,
            "max_connections": self.redis_max_connections,
            "ttl": self.cache_ttl,
            "timeout": self.connection_timeout,
            "max_retries": self.max_retries,
            "pool_config": pool_config,
            "retry_config": retry_config,
            "health_config": health_config
        }
    
    def get_application_config(self) -> Dict[str, Any]:
        """
        Get application configuration.
        
        Returns:
            Application configuration dictionary
        """
        return {
            "host": self.api_host,
            "port": self.api_port,
            "workers": self.api_workers,
            "debug": self.debug,
            "log_level": self.log_level,
            "secret_key": self.secret_key,
            "require_auth": self.require_auth,
            "enable_registration": self.enable_registration,
            "session_timeout": self.session_timeout,
            "rate_limit_per_minute": self.rate_limit_per_minute
        }
    
    def get_storage_config(self) -> Dict[str, Any]:
        """
        Get file storage configuration.
        
        Returns:
            Storage configuration dictionary
        """
        return {
            "upload_dir": self.upload_dir,
            "media_dir": self.media_dir,
            "export_dir": self.export_dir,
            "backup_dir": self.backup_dir,
            "log_dir": self.log_dir,
            "max_file_size": self.max_file_size,
            "max_files_per_upload": self.max_files_per_upload
        }
    
    def get_development_config(self) -> Dict[str, Any]:
        """
        Get development-specific configuration.
        
        Returns:
            Development configuration dictionary
        """
        return {
            "hot_reload": self.enable_hot_reload,
            "watchdog_enabled": self.watchdog_enabled,
            "reload_dirs": self.reload_dirs,
            "reload_delay": self.reload_delay,
            "debug": self.debug,
            "log_level": self.log_level
        }
    
    def get_connection_pool_config(self) -> Dict[str, Any]:
        """
        Get connection pooling configuration for all databases.
        
        Returns:
            Connection pooling configuration dictionary
        """
        return {
            "enabled": self.connection_pooling,
            "optimization": {
                "enabled": self.enable_pool_optimization,
                "strategy": self.pool_optimization_strategy,
                "monitoring_interval": self.pool_monitoring_interval,
                "optimization_interval": self.pool_optimization_interval,
                "auto_optimization": self.enable_auto_pool_optimization,
                "target_utilization": self.pool_target_utilization,
                "connection_timeout_threshold": self.pool_connection_timeout_threshold,
                "stale_connection_threshold": self.pool_stale_connection_threshold,
                "health_monitoring": self.enable_pool_health_monitoring,
                "health_check_interval": self.pool_health_check_interval,
                "leak_detection": self.pool_leak_detection,
                "performance_tracking": self.pool_performance_tracking
            },
            "postgres": {
                "pool_size": self.postgres_pool_size,
                "max_overflow": self.postgres_max_overflow,
                "pool_recycle": self.postgres_pool_recycle,
                "pool_pre_ping": self.postgres_pool_pre_ping,
                "pool_timeout": self.connection_timeout,
                "pool_reset_on_return": self.postgres_pool_reset_on_return,
                "echo": self.enable_query_logging
            },
            "neo4j": {
                "max_connection_pool_size": self.neo4j_pool_size,
                "max_connection_lifetime": self.neo4j_max_connection_lifetime,
                "connection_acquisition_timeout": self.neo4j_connection_acquisition_timeout,
                "max_transaction_retry_time": self.neo4j_max_transaction_retry_time,
                "encrypted": False,  # Local development
                "trust": True,  # Trust local certificates
                "keep_alive": True
            },
            "milvus": {
                "pool_size": self.milvus_connection_pool_size,
                "timeout": self.milvus_connection_timeout,
                "retry_attempts": self.max_retries,
                "secure": False,  # Local development
                "auto_optimize": self.enable_pool_optimization
            },
            "redis": {
                "max_connections": self.redis_max_connections,
                "socket_timeout": self.connection_timeout,
                "socket_connect_timeout": self.connection_timeout,
                "retry_on_timeout": True,
                "health_check_interval": self.health_check_interval,
                "connection_pool_class": "BlockingConnectionPool"
            }
        }
    
    def get_retry_config(self) -> Dict[str, Any]:
        """
        Get connection retry configuration for all databases.
        
        Returns:
            Retry configuration dictionary
        """
        return {
            "enabled": True,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "backoff_factor": self.retry_backoff_factor,
            "retry_on_exceptions": [
                "ConnectionError",
                "TimeoutError", 
                "DatabaseError",
                "OperationalError"
            ],
            "postgres": {
                "max_retries": self.max_retries,
                "retry_delay": self.retry_delay,
                "backoff_factor": self.retry_backoff_factor,
                "retry_on_disconnect": True
            },
            "neo4j": {
                "max_retries": self.max_retries,
                "retry_delay": self.retry_delay,
                "backoff_factor": self.retry_backoff_factor,
                "retry_on_session_expired": True,
                "retry_on_transient_error": True
            },
            "milvus": {
                "max_retries": self.max_retries,
                "retry_delay": self.retry_delay,
                "backoff_factor": self.retry_backoff_factor,
                "retry_on_connection_error": True
            },
            "redis": {
                "max_retries": self.max_retries,
                "retry_delay": self.retry_delay,
                "backoff_factor": self.retry_backoff_factor,
                "retry_on_timeout": True,
                "retry_on_connection_error": True
            }
        }
    
    def get_health_monitoring_config(self) -> Dict[str, Any]:
        """
        Get health monitoring configuration for all databases.
        
        Returns:
            Health monitoring configuration dictionary
        """
        return {
            "enabled": self.enable_health_checks,
            "interval": self.health_check_interval,
            "timeout": self.health_check_timeout,
            "retries": self.health_check_retries,
            "postgres": {
                "enabled": self.enable_relational_db and self.enable_health_checks,
                "check_query": "SELECT 1",
                "timeout": self.health_check_timeout,
                "interval": self.health_check_interval,
                "pool_health_check": True
            },
            "neo4j": {
                "enabled": self.enable_graph_db and self.enable_health_checks,
                "check_query": "RETURN 1",
                "timeout": self.health_check_timeout,
                "interval": self.health_check_interval,
                "verify_connectivity": True
            },
            "milvus": {
                "enabled": self.enable_vector_search and self.enable_health_checks,
                "check_method": "list_collections",
                "timeout": self.health_check_timeout,
                "interval": self.health_check_interval,
                "verify_server_status": True
            },
            "redis": {
                "enabled": self.enable_redis_cache and self.enable_health_checks,
                "check_command": "PING",
                "timeout": self.health_check_timeout,
                "interval": self.health_check_interval,
                "verify_memory_usage": True
            }
        }
    def get_health_check_config(self) -> Dict[str, Any]:
        """
        Get health check configuration (legacy method for backward compatibility).
        
        Returns:
            Health check configuration
        """
        health_config = self.get_health_monitoring_config()
        return {
            "enabled": health_config["enabled"],
            "interval": health_config["interval"],
            "timeout": health_config["timeout"],
            "retries": health_config["retries"],
            "relational_db_enabled": self.enable_relational_db,
            "vector_search_enabled": self.enable_vector_search,
            "graph_db_enabled": self.enable_graph_db,
            "redis_cache_enabled": self.enable_redis_cache
        }
    
    def get_monitoring_config(self) -> Dict[str, Any]:
        """
        Get monitoring and logging configuration.
        
        Returns:
            Monitoring configuration
        """
        return {
            "query_logging": self.enable_query_logging,
            "performance_tracking": True,
            "error_tracking": True,
            "metrics_enabled": True,
            "log_level": "INFO" if not self.enable_query_logging else "DEBUG"
        }
    
    def get_docker_config(self) -> Dict[str, Any]:
        """
        Get Docker-related configuration.
        
        Returns:
            Docker configuration for service discovery and health checks
        """
        return {
            "network": self.docker_network,
            "compose_file": self.docker_compose_file,
            "services": {
                "postgres": {
                    "container_name": "multimodal-librarian-postgres",
                    "health_check_url": f"postgresql://{self.postgres_user}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
                },
                "neo4j": {
                    "container_name": "multimodal-librarian-neo4j",
                    "health_check_url": f"http://{self.neo4j_host}:{self.neo4j_http_port}/db/data/"
                },
                "milvus": {
                    "container_name": "multimodal-librarian-milvus",
                    "health_check_url": f"http://{self.milvus_host}:9091/healthz"
                },
                "redis": {
                    "container_name": "multimodal-librarian-redis",
                    "health_check_url": f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"
                }
            }
        }
    
    def validate_configuration(self) -> Dict[str, Any]:
        """
        Validate the current configuration.
        
        Returns:
            Validation results with any issues found
        """
        issues = []
        warnings = []
        
        try:
            # Run comprehensive validation
            validation_results = self._run_comprehensive_validation()
            issues.extend(validation_results.get('errors', []))
            warnings.extend(validation_results.get('warnings', []))
            
        except Exception as e:
            issues.append(f"Validation error: {str(e)}")
        
        return {
            "valid": len(issues) == 0,
            "backend": "local",
            "issues": issues,
            "warnings": warnings,
            "config": {
                "relational_db": self.get_relational_db_config() if self.enable_relational_db else None,
                "graph_db": self.get_graph_db_config() if self.enable_graph_db else None,
                "vector_db": self.get_vector_db_config() if self.enable_vector_search else None,
                "redis_cache": self.get_redis_config() if self.enable_redis_cache else None,
                "application": self.get_application_config(),
                "storage": self.get_storage_config(),
                "development": self.get_development_config(),
                "health_check": self.get_health_check_config(),
                "monitoring": self.get_monitoring_config(),
                "docker": self.get_docker_config()
            }
        }
    
    def _run_comprehensive_validation(self) -> Dict[str, List[str]]:
        """Run comprehensive configuration validation."""
        errors = []
        warnings = []
        
        # Basic service validation
        basic_results = self._validate_basic_configuration()
        errors.extend(basic_results.get('errors', []))
        warnings.extend(basic_results.get('warnings', []))
        
        # Security validation
        security_results = self._validate_security_configuration()
        errors.extend(security_results.get('errors', []))
        warnings.extend(security_results.get('warnings', []))
        
        # Resource validation
        resource_results = self._validate_resource_configuration()
        errors.extend(resource_results.get('errors', []))
        warnings.extend(resource_results.get('warnings', []))
        
        # Network validation
        network_results = self._validate_network_configuration()
        errors.extend(network_results.get('errors', []))
        warnings.extend(network_results.get('warnings', []))
        
        # File system validation
        filesystem_results = self._validate_filesystem_configuration()
        errors.extend(filesystem_results.get('errors', []))
        warnings.extend(filesystem_results.get('warnings', []))
        
        return {"errors": errors, "warnings": warnings}
    
    def _validate_basic_configuration(self) -> Dict[str, List[str]]:
        """Validate basic configuration settings."""
        errors = []
        warnings = []
        
        # Check if at least one database is enabled
        if not any([self.enable_relational_db, self.enable_vector_search, self.enable_graph_db]):
            errors.append("All database services are disabled - at least one must be enabled")
        
        # PostgreSQL validation
        if self.enable_relational_db:
            if not self.postgres_password or self.postgres_password in ["changeme", "password", "postgres"]:
                warnings.append("PostgreSQL using weak or default password")
            
            if self.postgres_pool_size > 50:
                warnings.append(f"PostgreSQL pool size ({self.postgres_pool_size}) is very large")
            
            if self.postgres_max_overflow > self.postgres_pool_size * 2:
                warnings.append("PostgreSQL max overflow is more than 2x pool size")
        
        # Neo4j validation
        if self.enable_graph_db:
            if not self.neo4j_password or self.neo4j_password in ["neo4j", "password"]:
                warnings.append("Neo4j using weak or default password")
            
            if self.neo4j_pool_size > 200:
                warnings.append(f"Neo4j pool size ({self.neo4j_pool_size}) is very large")
        
        # Milvus validation
        if self.enable_vector_search:
            if self.embedding_dimension not in [128, 256, 384, 512, 768, 1024, 1536, 2048]:
                warnings.append(f"Unusual embedding dimension: {self.embedding_dimension}")
            
            if self.milvus_nlist > 16384:
                warnings.append(f"Milvus nlist parameter ({self.milvus_nlist}) is very high")
        
        # Redis validation
        if self.enable_redis_cache:
            if self.redis_max_connections > 100:
                warnings.append(f"Redis max connections ({self.redis_max_connections}) is very high")
            
            if self.cache_ttl < 60:
                warnings.append(f"Cache TTL ({self.cache_ttl}s) is very short")
        
        return {"errors": errors, "warnings": warnings}
    
    def _validate_security_configuration(self) -> Dict[str, List[str]]:
        """Validate security-related configuration."""
        errors = []
        warnings = []
        
        # Check application security
        if self.debug and self.environment not in ["development", "dev", "local"]:
            warnings.append("Debug mode enabled in non-development environment")
        
        if self.secret_key == "local-dev-secret-key-change-in-production":
            warnings.append("Using default secret key - change for production")
        
        if len(self.secret_key) < 32:
            warnings.append("Secret key is shorter than recommended 32 characters")
        
        if not self.require_auth and self.environment not in ["development", "dev", "local"]:
            warnings.append("Authentication disabled in non-development environment")
        
        # Check password strength
        passwords_to_check = [
            ("PostgreSQL", self.postgres_password),
            ("Neo4j", self.neo4j_password),
            ("Redis", self.redis_password)
        ]
        
        for service, password in passwords_to_check:
            if password and len(password) < 8:
                warnings.append(f"{service} password is shorter than 8 characters")
        
        # Check rate limiting
        if self.rate_limit_per_minute > 1000:
            warnings.append(f"Rate limit ({self.rate_limit_per_minute}/min) is very high")
        elif self.rate_limit_per_minute < 10:
            warnings.append(f"Rate limit ({self.rate_limit_per_minute}/min) is very low")
        
        return {"errors": errors, "warnings": warnings}
    
    def _validate_resource_configuration(self) -> Dict[str, List[str]]:
        """Validate resource usage configuration."""
        errors = []
        warnings = []
        
        # Calculate total connection pool size
        total_pool_size = 0
        if self.enable_relational_db:
            total_pool_size += self.postgres_pool_size + self.postgres_max_overflow
        if self.enable_graph_db:
            total_pool_size += self.neo4j_pool_size
        if self.enable_redis_cache:
            total_pool_size += self.redis_max_connections
        
        if total_pool_size > 500:
            warnings.append(f"Total connection pool size ({total_pool_size}) may consume excessive resources")
        
        # Check file size limits - only warn if over 50GB (effectively unlimited is fine)
        if self.max_file_size > 50 * 1024 * 1024 * 1024:  # 50GB
            warnings.append(f"Max file size ({self.max_file_size / (1024*1024):.0f}MB) is extremely large")
        
        if self.max_files_per_upload > 100:
            warnings.append(f"Max files per upload ({self.max_files_per_upload}) is very high")
        
        # Check timeout values
        if self.connection_timeout > 300:  # 5 minutes
            warnings.append(f"Connection timeout ({self.connection_timeout}s) is very long")
        elif self.connection_timeout < 10:
            warnings.append(f"Connection timeout ({self.connection_timeout}s) is very short")
        
        if self.query_timeout > self.connection_timeout:
            warnings.append("Query timeout is longer than connection timeout")
        
        # Check session timeout
        if self.session_timeout > 86400 * 7:  # 1 week
            warnings.append(f"Session timeout ({self.session_timeout / 86400:.1f} days) is very long")
        elif self.session_timeout < 3600:  # 1 hour
            warnings.append(f"Session timeout ({self.session_timeout / 3600:.1f} hours) is very short")
        
        return {"errors": errors, "warnings": warnings}
    
    def _validate_network_configuration(self) -> Dict[str, List[str]]:
        """Validate network-related configuration."""
        errors = []
        warnings = []
        
        # Check if hosts are reachable (basic validation)
        hosts_to_check = []
        if self.enable_relational_db and self.postgres_host not in ["localhost", "127.0.0.1"]:
            hosts_to_check.append(("PostgreSQL", self.postgres_host, self.postgres_port))
        if self.enable_graph_db and self.neo4j_host not in ["localhost", "127.0.0.1"]:
            hosts_to_check.append(("Neo4j", self.neo4j_host, self.neo4j_port))
        if self.enable_vector_search and self.milvus_host not in ["localhost", "127.0.0.1"]:
            hosts_to_check.append(("Milvus", self.milvus_host, self.milvus_port))
        if self.enable_redis_cache and self.redis_host not in ["localhost", "127.0.0.1"]:
            hosts_to_check.append(("Redis", self.redis_host, self.redis_port))
        
        for service, host, port in hosts_to_check:
            if not self._is_valid_hostname(host):
                warnings.append(f"{service} host '{host}' may not be a valid hostname")
        
        # Check API configuration
        if self.api_host == "0.0.0.0" and self.environment not in ["development", "dev", "local"]:
            warnings.append("API listening on all interfaces (0.0.0.0) in non-development environment")
        
        if self.api_workers > 8:
            warnings.append(f"API workers ({self.api_workers}) is very high for local development")
        
        return {"errors": errors, "warnings": warnings}
    
    def _validate_filesystem_configuration(self) -> Dict[str, List[str]]:
        """Validate filesystem-related configuration."""
        errors = []
        warnings = []
        
        # Check directory paths
        directories = [
            ("Upload", self.upload_dir),
            ("Media", self.media_dir),
            ("Export", self.export_dir),
            ("Backup", self.backup_dir),
            ("Log", self.log_dir)
        ]
        
        for name, directory in directories:
            if not directory:
                errors.append(f"{name} directory path is empty")
                continue
            
            # Check if path is absolute
            if not os.path.isabs(directory):
                warnings.append(f"{name} directory '{directory}' is not an absolute path")
            
            # Check if directory exists or can be created
            try:
                Path(directory).mkdir(parents=True, exist_ok=True)
            except (OSError, PermissionError) as e:
                warnings.append(f"Cannot create {name.lower()} directory '{directory}': {e}")
        
        # Check Docker configuration
        if self.docker_compose_file and not os.path.exists(self.docker_compose_file):
            warnings.append(f"Docker compose file '{self.docker_compose_file}' not found")
        
        # Check reload directories for hot reload
        if self.enable_hot_reload:
            reload_dirs = self.reload_dirs.split(',') if ',' in self.reload_dirs else [self.reload_dirs]
            for reload_dir in reload_dirs:
                reload_dir = reload_dir.strip()
                if reload_dir and not os.path.exists(reload_dir):
                    warnings.append(f"Hot reload directory '{reload_dir}' not found")
        
        return {"errors": errors, "warnings": warnings}
    
    def _is_valid_hostname(self, hostname: str) -> bool:
        """Check if hostname is valid."""
        if not hostname:
            return False
        
        # Allow localhost and IP addresses
        if hostname in ["localhost", "127.0.0.1", "::1"]:
            return True
        
        # Basic hostname validation
        if len(hostname) > 253:
            return False
        
        # Check for valid characters
        import re
        hostname_pattern = re.compile(r'^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$')
        return bool(hostname_pattern.match(hostname))
    
    def validate_connectivity(self, timeout: int = 5) -> Dict[str, Any]:
        """
        Validate connectivity to configured services.
        
        Args:
            timeout: Connection timeout in seconds
            
        Returns:
            Dictionary with connectivity test results
        """
        results = {
            "overall_status": "unknown",
            "services": {},
            "errors": [],
            "warnings": []
        }
        
        services_to_test = []
        
        if self.enable_relational_db:
            services_to_test.append(("postgres", self.postgres_host, self.postgres_port))
        if self.enable_graph_db:
            services_to_test.append(("neo4j", self.neo4j_host, self.neo4j_port))
        if self.enable_vector_search:
            services_to_test.append(("milvus", self.milvus_host, self.milvus_port))
        if self.enable_redis_cache:
            services_to_test.append(("redis", self.redis_host, self.redis_port))
        
        successful_connections = 0
        total_services = len(services_to_test)
        
        for service_name, host, port in services_to_test:
            try:
                result = self._test_tcp_connection(host, port, timeout)
                results["services"][service_name] = result
                if result["connected"]:
                    successful_connections += 1
                else:
                    results["errors"].append(f"Cannot connect to {service_name} at {host}:{port}")
            except Exception as e:
                results["services"][service_name] = {
                    "connected": False,
                    "error": str(e),
                    "host": host,
                    "port": port
                }
                results["errors"].append(f"Error testing {service_name}: {e}")
        
        # Determine overall status
        if successful_connections == total_services:
            results["overall_status"] = "healthy"
        elif successful_connections > 0:
            results["overall_status"] = "partial"
            results["warnings"].append(f"Only {successful_connections}/{total_services} services are reachable")
        else:
            results["overall_status"] = "unhealthy"
            results["errors"].append("No services are reachable")
        
        return results
    
    def _test_tcp_connection(self, host: str, port: int, timeout: int) -> Dict[str, Any]:
        """Test TCP connection to a host and port."""
        result = {
            "connected": False,
            "host": host,
            "port": port,
            "response_time": None,
            "error": None
        }
        
        try:
            import time
            start_time = time.time()
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            
            connection_result = sock.connect_ex((host, port))
            
            end_time = time.time()
            result["response_time"] = round((end_time - start_time) * 1000, 2)  # ms
            
            if connection_result == 0:
                result["connected"] = True
            else:
                result["error"] = f"Connection failed with code {connection_result}"
            
            sock.close()
            
        except socket.gaierror as e:
            result["error"] = f"DNS resolution failed: {e}"
        except socket.timeout:
            result["error"] = f"Connection timeout after {timeout}s"
        except Exception as e:
            result["error"] = f"Connection error: {e}"
        
        return result
    
    def validate_docker_environment(self) -> Dict[str, Any]:
        """
        Validate Docker environment and services.
        
        Returns:
            Dictionary with Docker validation results
        """
        results = {
            "docker_available": False,
            "compose_available": False,
            "compose_file_exists": False,
            "services_status": {},
            "errors": [],
            "warnings": []
        }
        
        try:
            # Check if Docker is available
            docker_result = subprocess.run(
                ["docker", "--version"], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            if docker_result.returncode == 0:
                results["docker_available"] = True
            else:
                results["errors"].append("Docker is not available or not working")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            results["errors"].append("Docker command not found or timed out")
        
        try:
            # Check if Docker Compose is available
            compose_result = subprocess.run(
                ["docker-compose", "--version"], 
                capture_output=True, 
                text=True, 
                timeout=10
            )
            if compose_result.returncode == 0:
                results["compose_available"] = True
            else:
                # Try docker compose (newer syntax)
                compose_result = subprocess.run(
                    ["docker", "compose", "version"], 
                    capture_output=True, 
                    text=True, 
                    timeout=10
                )
                if compose_result.returncode == 0:
                    results["compose_available"] = True
                else:
                    results["errors"].append("Docker Compose is not available")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            results["errors"].append("Docker Compose command not found or timed out")
        
        # Check if compose file exists
        if os.path.exists(self.docker_compose_file):
            results["compose_file_exists"] = True
            
            # Try to validate compose file
            if results["compose_available"]:
                try:
                    validate_result = subprocess.run(
                        ["docker-compose", "-f", self.docker_compose_file, "config"],
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    if validate_result.returncode != 0:
                        results["warnings"].append(f"Docker compose file validation failed: {validate_result.stderr}")
                except (subprocess.TimeoutExpired, FileNotFoundError):
                    results["warnings"].append("Could not validate Docker compose file")
        else:
            results["errors"].append(f"Docker compose file not found: {self.docker_compose_file}")
        
        return results
    
    def validate_and_fix_configuration(self) -> Dict[str, Any]:
        """
        Validate configuration and attempt to fix common issues.
        
        Returns:
            Dictionary with validation results and applied fixes
        """
        results = {
            "validation": self.validate_configuration(),
            "fixes_applied": [],
            "fixes_failed": [],
            "recommendations": []
        }
        
        # Attempt to fix common issues
        if not results["validation"]["valid"]:
            for issue in results["validation"]["issues"]:
                fix_result = self._attempt_fix_issue(issue)
                if fix_result["fixed"]:
                    results["fixes_applied"].append(fix_result)
                else:
                    results["fixes_failed"].append(fix_result)
        
        # Generate recommendations for warnings
        for warning in results["validation"]["warnings"]:
            recommendation = self._generate_recommendation(warning)
            if recommendation:
                results["recommendations"].append(recommendation)
        
        return results
    
    def _attempt_fix_issue(self, issue: str) -> Dict[str, Any]:
        """Attempt to automatically fix a configuration issue."""
        fix_result = {
            "issue": issue,
            "fixed": False,
            "action": None,
            "error": None
        }
        
        try:
            # Port conflict fixes
            if "Port" in issue and "multiple services" in issue:
                fix_result["action"] = "Attempted to resolve port conflicts"
                # This would require more complex logic to reassign ports
                fix_result["fixed"] = False
                fix_result["error"] = "Automatic port conflict resolution not implemented"
            
            # Directory creation fixes
            elif "Cannot create" in issue and "directory" in issue:
                # Extract directory path from error message
                import re
                match = re.search(r"'([^']+)'", issue)
                if match:
                    directory = match.group(1)
                    try:
                        Path(directory).mkdir(parents=True, exist_ok=True)
                        fix_result["action"] = f"Created directory: {directory}"
                        fix_result["fixed"] = True
                    except Exception as e:
                        fix_result["error"] = f"Failed to create directory: {e}"
            
            # Other fixes can be added here
            else:
                fix_result["error"] = "No automatic fix available for this issue"
        
        except Exception as e:
            fix_result["error"] = f"Error during fix attempt: {e}"
        
        return fix_result
    
    def _generate_recommendation(self, warning: str) -> Optional[str]:
        """Generate a recommendation for a configuration warning."""
        if "password" in warning.lower():
            return "Consider using a strong, unique password with at least 12 characters including letters, numbers, and symbols"
        elif "pool size" in warning.lower():
            return "Consider reducing connection pool sizes for local development to conserve resources"
        elif "dimension" in warning.lower():
            return "Verify that the embedding dimension matches your chosen model's output dimension"
        elif "timeout" in warning.lower():
            return "Adjust timeout values based on your network conditions and performance requirements"
        elif "debug mode" in warning.lower():
            return "Disable debug mode in production environments for security and performance"
        elif "secret key" in warning.lower():
            return "Generate a new secret key using a cryptographically secure random generator"
        
        return None
    
    def get_environment_info(self) -> Dict[str, Any]:
        """
        Get environment information for debugging.
        
        Returns:
            Environment information
        """
        return {
            "backend_type": "local",
            "environment": self.environment,
            "relational_db_enabled": self.enable_relational_db,
            "vector_search_enabled": self.enable_vector_search,
            "graph_db_enabled": self.enable_graph_db,
            "redis_cache_enabled": self.enable_redis_cache,
            "services": {
                "postgres": f"{self.postgres_host}:{self.postgres_port}" if self.enable_relational_db else None,
                "neo4j": f"{self.neo4j_host}:{self.neo4j_port}" if self.enable_graph_db else None,
                "milvus": f"{self.milvus_host}:{self.milvus_port}" if self.enable_vector_search else None,
                "redis": f"{self.redis_host}:{self.redis_port}" if self.enable_redis_cache else None
            },
            "docker": {
                "network": self.docker_network,
                "compose_file": self.docker_compose_file
            }
        }
    
    def create_env_file_template(self, file_path: str = ".env.local.example") -> None:
        """
        Create an environment file template with all configuration options.
        
        Args:
            file_path: Path to create the template file
        """
        template_content = f"""# Local Development Configuration for Multimodal Librarian
# Copy this file to .env.local and customize as needed

# Environment
ML_ENVIRONMENT=development
ML_DATABASE_TYPE=local

# Application Configuration
ML_API_HOST={self.api_host}
ML_API_PORT={self.api_port}
ML_API_WORKERS={self.api_workers}
ML_DEBUG={str(self.debug).lower()}
ML_LOG_LEVEL={self.log_level}

# Security Configuration
ML_SECRET_KEY={self.secret_key}
ML_REQUIRE_AUTH={str(self.require_auth).lower()}
ML_ENABLE_REGISTRATION={str(self.enable_registration).lower()}
ML_SESSION_TIMEOUT={self.session_timeout}
ML_RATE_LIMIT_PER_MINUTE={self.rate_limit_per_minute}

# PostgreSQL Configuration
ML_POSTGRES_HOST={self.postgres_host}
ML_POSTGRES_PORT={self.postgres_port}
ML_POSTGRES_DB={self.postgres_db}
ML_POSTGRES_USER={self.postgres_user}
ML_POSTGRES_PASSWORD={self.postgres_password}
ML_POSTGRES_POOL_SIZE={self.postgres_pool_size}
ML_POSTGRES_MAX_OVERFLOW={self.postgres_max_overflow}

# Neo4j Configuration
ML_NEO4J_HOST={self.neo4j_host}
ML_NEO4J_PORT={self.neo4j_port}
ML_NEO4J_HTTP_PORT={self.neo4j_http_port}
ML_NEO4J_USER={self.neo4j_user}
ML_NEO4J_PASSWORD={self.neo4j_password}
ML_NEO4J_POOL_SIZE={self.neo4j_pool_size}

# Milvus Configuration
ML_MILVUS_HOST={self.milvus_host}
ML_MILVUS_PORT={self.milvus_port}
ML_MILVUS_USER={self.milvus_user}
ML_MILVUS_PASSWORD={self.milvus_password}
ML_MILVUS_DEFAULT_COLLECTION={self.milvus_default_collection}
ML_MILVUS_INDEX_TYPE={self.milvus_index_type}
ML_MILVUS_METRIC_TYPE={self.milvus_metric_type}
ML_MILVUS_NLIST={self.milvus_nlist}

# Redis Configuration
ML_REDIS_HOST={self.redis_host}
ML_REDIS_PORT={self.redis_port}
ML_REDIS_DB={self.redis_db}
ML_REDIS_PASSWORD={self.redis_password}
ML_REDIS_MAX_CONNECTIONS={self.redis_max_connections}
ML_CACHE_TTL={self.cache_ttl}

# Feature Flags
ML_ENABLE_RELATIONAL_DB={str(self.enable_relational_db).lower()}
ML_ENABLE_VECTOR_SEARCH={str(self.enable_vector_search).lower()}
ML_ENABLE_GRAPH_DB={str(self.enable_graph_db).lower()}
ML_ENABLE_REDIS_CACHE={str(self.enable_redis_cache).lower()}
ML_ENABLE_DOCUMENT_UPLOAD={str(self.enable_document_upload).lower()}
ML_ENABLE_KNOWLEDGE_GRAPH={str(self.enable_knowledge_graph).lower()}
ML_ENABLE_AI_CHAT={str(self.enable_ai_chat).lower()}
ML_ENABLE_EXPORT_FUNCTIONALITY={str(self.enable_export_functionality).lower()}
ML_ENABLE_ANALYTICS={str(self.enable_analytics).lower()}
ML_ENABLE_USER_MANAGEMENT={str(self.enable_user_management).lower()}

# File Storage Configuration
ML_UPLOAD_DIR={self.upload_dir}
ML_MEDIA_DIR={self.media_dir}
ML_EXPORT_DIR={self.export_dir}
ML_BACKUP_DIR={self.backup_dir}
ML_LOG_DIR={self.log_dir}
ML_MAX_FILE_SIZE={self.max_file_size}
ML_MAX_FILES_PER_UPLOAD={self.max_files_per_upload}

# Connection Settings
ML_CONNECTION_TIMEOUT={self.connection_timeout}
ML_QUERY_TIMEOUT={self.query_timeout}
ML_MAX_RETRIES={self.max_retries}
ML_RETRY_DELAY={self.retry_delay}
ML_RETRY_BACKOFF_FACTOR={self.retry_backoff_factor}

# Performance Settings
ML_CONNECTION_POOLING={str(self.connection_pooling).lower()}
ML_QUERY_CACHING={str(self.query_caching).lower()}
ML_ENABLE_QUERY_LOGGING={str(self.enable_query_logging).lower()}

# Health Check Settings
ML_ENABLE_HEALTH_CHECKS={str(self.enable_health_checks).lower()}
ML_HEALTH_CHECK_INTERVAL={self.health_check_interval}
ML_HEALTH_CHECK_TIMEOUT={self.health_check_timeout}
ML_HEALTH_CHECK_RETRIES={self.health_check_retries}

# Embedding Configuration
ML_EMBEDDING_DIMENSION={self.embedding_dimension}
ML_EMBEDDING_MODEL={self.embedding_model}

# Development Configuration
ML_ENABLE_HOT_RELOAD={str(self.enable_hot_reload).lower()}
ML_WATCHDOG_ENABLED={str(self.watchdog_enabled).lower()}
ML_RELOAD_DIRS={self.reload_dirs}
ML_RELOAD_DELAY={self.reload_delay}

# Docker Configuration
ML_DOCKER_NETWORK={self.docker_network}
ML_DOCKER_COMPOSE_FILE={self.docker_compose_file}
"""
        
        with open(file_path, 'w') as f:
            f.write(template_content)
        
        logger.info(f"Created environment template at {file_path}")


# Global configuration instance
_local_config: Optional[LocalDatabaseConfig] = None


def get_local_config() -> LocalDatabaseConfig:
    """Get or create global local configuration instance."""
    global _local_config
    
    if _local_config is None:
        _local_config = LocalDatabaseConfig()
    
    return _local_config


def reload_local_config() -> LocalDatabaseConfig:
    """Reload local configuration (useful for testing)."""
    global _local_config
    _local_config = None
    return get_local_config()


def create_local_env_template(file_path: str = ".env.local.example") -> None:
    """
    Create a local environment template file.
    
    Args:
        file_path: Path to create the template file
    """
    config = get_local_config()
    config.create_env_file_template(file_path)