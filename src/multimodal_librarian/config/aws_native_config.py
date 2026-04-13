"""
AWS-Native Database Configuration for Multimodal Librarian

This module provides configuration management for AWS-Native database services
(Amazon Neptune, Amazon OpenSearch, and Amazon RDS PostgreSQL) for production deployment.

This configuration is designed for production use with AWS-managed services
and provides the same interface as LocalDatabaseConfig for consistent usage.
"""

import logging
import os
from typing import Any, Dict, Literal, Optional

from pydantic import ConfigDict, Field, field_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class AWSNativeConfig(BaseSettings):
    """
    Configuration manager for AWS-Native database services.
    
    This class handles configuration for:
    - Amazon Neptune (graph database)
    - Amazon OpenSearch (vector database)
    - Amazon RDS PostgreSQL (relational database)
    - AWS Secrets Manager (credentials)
    - AWS CloudWatch (monitoring)
    
    All settings can be overridden via environment variables.
    
    Example:
        ```python
        # Use default configuration
        config = AWSNativeConfig()
        
        # Override via environment variables
        os.environ['AWS_DEFAULT_REGION'] = 'us-west-2'
        os.environ['NEPTUNE_CLUSTER_ENDPOINT'] = 'my-cluster.cluster-xyz.us-west-2.neptune.amazonaws.com'
        config = AWSNativeConfig()
        ```
    """
    
    # Environment identification
    database_type: Literal["aws"] = "aws"
    environment: str = Field(default="production", description="Environment name")
    
    # AWS Configuration
    region: str = Field(default="us-east-1", description="AWS region")
    aws_profile: Optional[str] = Field(default=None, description="AWS profile name")
    
    # Neptune Configuration (Graph Database)
    neptune_endpoint: Optional[str] = Field(default=None, description="Neptune cluster endpoint")
    neptune_port: int = Field(default=8182, description="Neptune port")
    neptune_secret_name: str = Field(
        default="multimodal-librarian/aws-native/neptune",
        description="Neptune credentials secret name"
    )
    neptune_iam_auth: bool = Field(default=True, description="Use IAM authentication for Neptune")
    neptune_ssl: bool = Field(default=True, description="Use SSL for Neptune connections")
    
    # OpenSearch Configuration (Vector Database)
    opensearch_endpoint: Optional[str] = Field(default=None, description="OpenSearch domain endpoint")
    opensearch_port: int = Field(default=443, description="OpenSearch port")
    opensearch_secret_name: str = Field(
        default="multimodal-librarian/aws-native/opensearch",
        description="OpenSearch credentials secret name"
    )
    opensearch_use_ssl: bool = Field(default=True, description="Use SSL for OpenSearch")
    opensearch_verify_certs: bool = Field(default=True, description="Verify SSL certificates")
    opensearch_index_prefix: str = Field(default="ml", description="Index prefix for OpenSearch")
    
    # RDS PostgreSQL Configuration (Relational Database)
    rds_endpoint: Optional[str] = Field(default=None, description="RDS PostgreSQL endpoint")
    rds_port: int = Field(default=5432, description="RDS PostgreSQL port")
    rds_database: str = Field(default="multimodal_librarian", description="PostgreSQL database name")
    rds_secret_name: str = Field(
        default="multimodal-librarian/aws-native/rds",
        description="RDS credentials secret name"
    )
    rds_ssl_mode: str = Field(default="require", description="PostgreSQL SSL mode")
    rds_pool_size: int = Field(default=20, description="RDS connection pool size")
    rds_max_overflow: int = Field(default=40, description="RDS max overflow connections")
    rds_pool_recycle: int = Field(default=3600, description="RDS pool recycle time (seconds)")
    
    # Feature Flags
    enable_relational_db: bool = Field(default=True, description="Enable RDS PostgreSQL")
    enable_vector_search: bool = Field(default=True, description="Enable OpenSearch vector search")
    enable_graph_db: bool = Field(default=True, description="Enable Neptune graph database")
    enable_document_upload: bool = Field(default=True, description="Enable document upload functionality")
    enable_knowledge_graph: bool = Field(default=True, description="Enable knowledge graph features")
    enable_ai_chat: bool = Field(default=True, description="Enable AI chat functionality")
    enable_export_functionality: bool = Field(default=True, description="Enable export features")
    enable_analytics: bool = Field(default=True, description="Enable analytics")
    enable_user_management: bool = Field(default=True, description="Enable user management")
    
    # Application Configuration
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    api_workers: int = Field(default=4, description="Number of API workers")
    debug: bool = Field(default=False, description="Enable debug mode")
    log_level: str = Field(default="INFO", description="Logging level")
    
    # AWS S3 Configuration (File Storage)
    s3_bucket: Optional[str] = Field(default=None, description="S3 bucket for file storage")
    s3_region: Optional[str] = Field(default=None, description="S3 bucket region")
    s3_prefix: str = Field(default="multimodal-librarian", description="S3 key prefix")
    s3_upload_prefix: str = Field(default="uploads", description="S3 upload prefix")
    s3_media_prefix: str = Field(default="media", description="S3 media prefix")
    s3_export_prefix: str = Field(default="exports", description="S3 export prefix")
    s3_backup_prefix: str = Field(default="backups", description="S3 backup prefix")
    max_file_size: int = Field(default=10 * 1024 * 1024 * 1024, description="Max file size in bytes (10GB - effectively unlimited)")
    max_files_per_upload: int = Field(default=10, description="Max files per upload")
    
    # Security Configuration
    secret_key_secret_name: str = Field(
        default="multimodal-librarian/aws-native/app-secrets",
        description="Application secrets secret name"
    )
    require_auth: bool = Field(default=True, description="Require authentication")
    enable_registration: bool = Field(default=False, description="Enable user registration")
    session_timeout: int = Field(default=86400, description="Session timeout in seconds")
    rate_limit_per_minute: int = Field(default=1000, description="Rate limit per minute")
    
    # Connection Settings
    connection_timeout: int = Field(default=60, description="Database connection timeout (seconds)")
    query_timeout: int = Field(default=30, description="Database query timeout (seconds)")
    max_retries: int = Field(default=3, description="Maximum connection retry attempts")
    
    # Performance Settings
    connection_pooling: bool = Field(default=True, description="Enable connection pooling")
    query_caching: bool = Field(default=True, description="Enable query result caching")
    enable_query_logging: bool = Field(default=False, description="Enable SQL/Cypher query logging")
    
    # Embedding Configuration
    embedding_dimension: int = Field(default=768, description="Vector embedding dimension")
    embedding_model: str = Field(default="BAAI/bge-base-en-v1.5", description="Embedding model name")
    
    # CloudWatch Configuration
    cloudwatch_log_group: str = Field(
        default="/aws/ecs/multimodal-librarian",
        description="CloudWatch log group"
    )
    cloudwatch_log_stream_prefix: str = Field(default="app", description="CloudWatch log stream prefix")
    enable_cloudwatch_metrics: bool = Field(default=True, description="Enable CloudWatch metrics")
    enable_xray_tracing: bool = Field(default=True, description="Enable AWS X-Ray tracing")
    
    # Auto Scaling Configuration
    enable_auto_scaling: bool = Field(default=True, description="Enable ECS auto scaling")
    min_capacity: int = Field(default=1, description="Minimum ECS task count")
    max_capacity: int = Field(default=10, description="Maximum ECS task count")
    target_cpu_utilization: int = Field(default=70, description="Target CPU utilization for scaling")
    target_memory_utilization: int = Field(default=80, description="Target memory utilization for scaling")
    
    # Backup Configuration
    enable_automated_backups: bool = Field(default=True, description="Enable automated backups")
    backup_retention_days: int = Field(default=30, description="Backup retention period in days")
    backup_schedule: str = Field(default="0 2 * * *", description="Backup schedule (cron format)")
    
    # Cost Optimization
    enable_cost_optimization: bool = Field(default=True, description="Enable cost optimization features")
    use_spot_instances: bool = Field(default=False, description="Use EC2 spot instances for ECS")
    enable_resource_tagging: bool = Field(default=True, description="Enable resource tagging for cost tracking")
    
    model_config = ConfigDict(
        env_file=".env.aws",
        case_sensitive=False,
        extra="ignore"
    )
        
    @field_validator('rds_port', 'neptune_port', 'opensearch_port', 'api_port')
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
    
    @field_validator('rds_pool_size', 'rds_max_overflow', 'api_workers', 'min_capacity', 'max_capacity')
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
    
    @field_validator('max_file_size', 'session_timeout', 'backup_retention_days')
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
    
    @field_validator('rds_ssl_mode')
    @classmethod
    def validate_ssl_mode(cls, v):
        """Validate PostgreSQL SSL mode."""
        valid_modes = ['disable', 'allow', 'prefer', 'require', 'verify-ca', 'verify-full']
        if v.lower() not in valid_modes:
            raise ValueError(f"SSL mode must be one of {valid_modes}, got {v}")
        return v.lower()
    
    @field_validator('target_cpu_utilization', 'target_memory_utilization')
    @classmethod
    def validate_utilization_percentages(cls, v):
        """Validate utilization percentages."""
        if not (1 <= v <= 100):
            raise ValueError(f"Utilization percentage must be between 1 and 100, got {v}")
        return v
        
    
    def get_backend_type(self) -> str:
        """Get the backend type (always 'aws' for this config)."""
        return "aws"
    
    def is_aws_native_enabled(self) -> bool:
        """Check if AWS-native mode is enabled (always True)."""
        return True
    
    def is_local_enabled(self) -> bool:
        """Check if local development mode is enabled (always False for AWS config)."""
        return False
    
    def get_rds_connection_string(self, async_driver: bool = True) -> str:
        """
        Get RDS PostgreSQL connection string.
        
        Args:
            async_driver: Whether to use async driver (asyncpg) or sync (psycopg2)
            
        Returns:
            PostgreSQL connection string (without credentials - use Secrets Manager)
        """
        driver = "postgresql+asyncpg" if async_driver else "postgresql+psycopg2"
        # Note: Credentials should be retrieved from Secrets Manager
        return (
            f"{driver}://{{username}}:{{password}}"
            f"@{self.rds_endpoint}:{self.rds_port}/{self.rds_database}"
        )
    
    def get_relational_db_config(self) -> Dict[str, Any]:
        """
        Get relational database configuration.
        
        Returns:
            Configuration dictionary for RDS PostgreSQL
        """
        return {
            "type": "rds_postgresql",
            "endpoint": self.rds_endpoint,
            "port": self.rds_port,
            "database": self.rds_database,
            "secret_name": self.rds_secret_name,
            "ssl_mode": self.rds_ssl_mode,
            "region": self.region,
            "pool_size": self.rds_pool_size,
            "max_overflow": self.rds_max_overflow,
            "pool_recycle": self.rds_pool_recycle,
            "timeout": self.connection_timeout,
            "max_retries": self.max_retries
        }
    
    def get_graph_db_config(self) -> Dict[str, Any]:
        """
        Get graph database configuration.
        
        Returns:
            Configuration dictionary for Neptune
        """
        return {
            "type": "neptune",
            "endpoint": self.neptune_endpoint,
            "port": self.neptune_port,
            "secret_name": self.neptune_secret_name,
            "region": self.region,
            "iam_auth": self.neptune_iam_auth,
            "ssl": self.neptune_ssl,
            "timeout": self.connection_timeout,
            "max_retries": self.max_retries
        }
    
    def get_vector_db_config(self) -> Dict[str, Any]:
        """
        Get vector database configuration.
        
        Returns:
            Configuration dictionary for OpenSearch
        """
        return {
            "type": "opensearch",
            "endpoint": self.opensearch_endpoint,
            "port": self.opensearch_port,
            "secret_name": self.opensearch_secret_name,
            "region": self.region,
            "use_ssl": self.opensearch_use_ssl,
            "verify_certs": self.opensearch_verify_certs,
            "index_prefix": self.opensearch_index_prefix,
            "embedding_dimension": self.embedding_dimension,
            "embedding_model": self.embedding_model,
            "timeout": self.connection_timeout,
            "max_retries": self.max_retries
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
            "secret_key_secret_name": self.secret_key_secret_name,
            "require_auth": self.require_auth,
            "enable_registration": self.enable_registration,
            "session_timeout": self.session_timeout,
            "rate_limit_per_minute": self.rate_limit_per_minute
        }
    
    def get_storage_config(self) -> Dict[str, Any]:
        """
        Get file storage configuration.
        
        Returns:
            S3 storage configuration dictionary
        """
        return {
            "type": "s3",
            "bucket": self.s3_bucket,
            "region": self.s3_region or self.region,
            "prefix": self.s3_prefix,
            "upload_prefix": self.s3_upload_prefix,
            "media_prefix": self.s3_media_prefix,
            "export_prefix": self.s3_export_prefix,
            "backup_prefix": self.s3_backup_prefix,
            "max_file_size": self.max_file_size,
            "max_files_per_upload": self.max_files_per_upload
        }
    
    def get_cloudwatch_config(self) -> Dict[str, Any]:
        """
        Get CloudWatch configuration.
        
        Returns:
            CloudWatch configuration dictionary
        """
        return {
            "log_group": self.cloudwatch_log_group,
            "log_stream_prefix": self.cloudwatch_log_stream_prefix,
            "metrics_enabled": self.enable_cloudwatch_metrics,
            "xray_tracing": self.enable_xray_tracing,
            "region": self.region
        }
    
    def get_auto_scaling_config(self) -> Dict[str, Any]:
        """
        Get auto scaling configuration.
        
        Returns:
            Auto scaling configuration dictionary
        """
        return {
            "enabled": self.enable_auto_scaling,
            "min_capacity": self.min_capacity,
            "max_capacity": self.max_capacity,
            "target_cpu_utilization": self.target_cpu_utilization,
            "target_memory_utilization": self.target_memory_utilization
        }
    
    def get_backup_config(self) -> Dict[str, Any]:
        """
        Get backup configuration.
        
        Returns:
            Backup configuration dictionary
        """
        return {
            "enabled": self.enable_automated_backups,
            "retention_days": self.backup_retention_days,
            "schedule": self.backup_schedule,
            "s3_bucket": self.s3_bucket,
            "s3_prefix": f"{self.s3_prefix}/{self.s3_backup_prefix}",
            "region": self.region
        }
    
    def get_health_check_config(self) -> Dict[str, Any]:
        """
        Get health check configuration.
        
        Returns:
            Health check configuration
        """
        return {
            "enabled": True,
            "interval": 30,  # seconds
            "timeout": 10,   # seconds
            "retries": 3,
            "relational_db_enabled": self.enable_relational_db,
            "vector_search_enabled": self.enable_vector_search,
            "graph_db_enabled": self.enable_graph_db
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
            "metrics_enabled": self.enable_cloudwatch_metrics,
            "cloudwatch_enabled": True,
            "xray_tracing": self.enable_xray_tracing,
            "log_level": self.log_level
        }
    
    def get_cost_optimization_config(self) -> Dict[str, Any]:
        """
        Get cost optimization configuration.
        
        Returns:
            Cost optimization settings
        """
        return {
            "enabled": self.enable_cost_optimization,
            "connection_pooling": self.connection_pooling,
            "query_caching": self.query_caching,
            "batch_operations": True,
            "lazy_loading": True,
            "resource_monitoring": True,
            "use_spot_instances": self.use_spot_instances,
            "resource_tagging": self.enable_resource_tagging,
            "auto_scaling": self.enable_auto_scaling
        }
    
    def validate_configuration(self) -> Dict[str, Any]:
        """
        Validate the current configuration.
        
        Returns:
            Validation results with any issues found
        """
        issues = []
        warnings = []
        
        # Check AWS region
        if not self.region:
            issues.append("AWS region not configured")
        
        # Check RDS configuration (only require endpoint in production)
        if self.enable_relational_db:
            if not self.rds_endpoint and self.environment == "production":
                issues.append("RDS endpoint not configured for relational database")
            elif not self.rds_endpoint:
                warnings.append("RDS endpoint not configured - relational database will not work")
            
            if not self.rds_secret_name:
                warnings.append("RDS secret name not configured")
            
            if self.rds_pool_size > 100:
                warnings.append("RDS pool size is very large, may consume excessive connections")
        
        # Check Neptune configuration (only require endpoint in production)
        if self.enable_graph_db:
            if not self.neptune_endpoint and self.environment == "production":
                issues.append("Neptune endpoint not configured for graph database")
            elif not self.neptune_endpoint:
                warnings.append("Neptune endpoint not configured - graph database will not work")
            
            if not self.neptune_secret_name:
                warnings.append("Neptune secret name not configured")
        
        # Check OpenSearch configuration (only require endpoint in production)
        if self.enable_vector_search:
            if not self.opensearch_endpoint and self.environment == "production":
                issues.append("OpenSearch endpoint not configured for vector search")
            elif not self.opensearch_endpoint:
                warnings.append("OpenSearch endpoint not configured - vector search will not work")
            
            if not self.opensearch_secret_name:
                warnings.append("OpenSearch secret name not configured")
            
            if self.embedding_dimension not in [128, 256, 384, 512, 768, 1024, 1536]:
                warnings.append(f"Unusual embedding dimension: {self.embedding_dimension}")
        
        # Check feature flags
        if not any([self.enable_relational_db, self.enable_graph_db, self.enable_vector_search]):
            issues.append("All database services are disabled")
        
        # Check S3 configuration
        if not self.s3_bucket:
            warnings.append("S3 bucket not configured - file storage may not work")
        
        # Check application configuration
        if self.debug and self.environment == "production":
            warnings.append("Debug mode enabled in production environment")
        
        if not self.require_auth and self.environment == "production":
            warnings.append("Authentication disabled in production environment")
        
        # Check auto scaling configuration
        if self.enable_auto_scaling:
            if self.min_capacity >= self.max_capacity:
                issues.append("Auto scaling min_capacity must be less than max_capacity")
            
            if self.max_capacity > 50:
                warnings.append("Very high max_capacity for auto scaling, monitor costs")
        
        # Check backup configuration
        if self.enable_automated_backups and not self.s3_bucket:
            warnings.append("Automated backups enabled but no S3 bucket configured")
        
        return {
            "valid": len(issues) == 0,
            "backend": "aws",
            "issues": issues,
            "warnings": warnings,
            "config": {
                "relational_db": self.get_relational_db_config() if self.enable_relational_db else None,
                "graph_db": self.get_graph_db_config() if self.enable_graph_db else None,
                "vector_db": self.get_vector_db_config() if self.enable_vector_search else None,
                "application": self.get_application_config(),
                "storage": self.get_storage_config(),
                "cloudwatch": self.get_cloudwatch_config(),
                "auto_scaling": self.get_auto_scaling_config(),
                "backup": self.get_backup_config(),
                "health_check": self.get_health_check_config(),
                "monitoring": self.get_monitoring_config(),
                "cost_optimization": self.get_cost_optimization_config()
            }
        }
    
    def get_environment_info(self) -> Dict[str, Any]:
        """
        Get environment information for debugging.
        
        Returns:
            Environment information
        """
        return {
            "backend_type": "aws",
            "environment": self.environment,
            "region": self.region,
            "relational_db_enabled": self.enable_relational_db,
            "vector_search_enabled": self.enable_vector_search,
            "graph_db_enabled": self.enable_graph_db,
            "services": {
                "rds": f"{self.rds_endpoint}:{self.rds_port}" if self.rds_endpoint else None,
                "neptune": f"{self.neptune_endpoint}:{self.neptune_port}" if self.neptune_endpoint else None,
                "opensearch": f"{self.opensearch_endpoint}:{self.opensearch_port}" if self.opensearch_endpoint else None,
                "s3": self.s3_bucket
            },
            "features": {
                "auto_scaling": self.enable_auto_scaling,
                "automated_backups": self.enable_automated_backups,
                "cost_optimization": self.enable_cost_optimization,
                "cloudwatch_metrics": self.enable_cloudwatch_metrics,
                "xray_tracing": self.enable_xray_tracing
            },
            "environment_variables": {
                "AWS_REGION": bool(self.region),
                "NEPTUNE_CLUSTER_ENDPOINT": bool(self.neptune_endpoint),
                "OPENSEARCH_DOMAIN_ENDPOINT": bool(self.opensearch_endpoint),
                "RDS_ENDPOINT": bool(self.rds_endpoint),
                "S3_BUCKET": bool(self.s3_bucket)
            }
        }
    
    def create_env_file_template(self, file_path: str = ".env.aws.example") -> None:
        """
        Create an environment file template with all configuration options.
        
        Args:
            file_path: Path to create the template file
        """
        template_content = f"""# AWS Production Configuration for Multimodal Librarian
# Copy this file to .env.aws and customize as needed

# Environment
ENVIRONMENT=production
DATABASE_TYPE=aws

# AWS Configuration
AWS_DEFAULT_REGION={self.region}
AWS_PROFILE={self.aws_profile or ""}

# Application Configuration
API_HOST={self.api_host}
API_PORT={self.api_port}
API_WORKERS={self.api_workers}
DEBUG={str(self.debug).lower()}
LOG_LEVEL={self.log_level}

# Security Configuration
SECRET_KEY_SECRET_NAME={self.secret_key_secret_name}
REQUIRE_AUTH={str(self.require_auth).lower()}
ENABLE_REGISTRATION={str(self.enable_registration).lower()}
SESSION_TIMEOUT={self.session_timeout}
RATE_LIMIT_PER_MINUTE={self.rate_limit_per_minute}

# RDS PostgreSQL Configuration
RDS_ENDPOINT={self.rds_endpoint or ""}
RDS_PORT={self.rds_port}
RDS_DATABASE={self.rds_database}
RDS_SECRET_NAME={self.rds_secret_name}
RDS_SSL_MODE={self.rds_ssl_mode}
RDS_POOL_SIZE={self.rds_pool_size}
RDS_MAX_OVERFLOW={self.rds_max_overflow}

# Neptune Configuration
NEPTUNE_CLUSTER_ENDPOINT={self.neptune_endpoint or ""}
NEPTUNE_PORT={self.neptune_port}
NEPTUNE_SECRET_NAME={self.neptune_secret_name}
NEPTUNE_IAM_AUTH={str(self.neptune_iam_auth).lower()}
NEPTUNE_SSL={str(self.neptune_ssl).lower()}

# OpenSearch Configuration
OPENSEARCH_DOMAIN_ENDPOINT={self.opensearch_endpoint or ""}
OPENSEARCH_PORT={self.opensearch_port}
OPENSEARCH_SECRET_NAME={self.opensearch_secret_name}
OPENSEARCH_USE_SSL={str(self.opensearch_use_ssl).lower()}
OPENSEARCH_VERIFY_CERTS={str(self.opensearch_verify_certs).lower()}
OPENSEARCH_INDEX_PREFIX={self.opensearch_index_prefix}

# S3 Configuration
S3_BUCKET={self.s3_bucket or ""}
S3_REGION={self.s3_region or ""}
S3_PREFIX={self.s3_prefix}
S3_UPLOAD_PREFIX={self.s3_upload_prefix}
S3_MEDIA_PREFIX={self.s3_media_prefix}
S3_EXPORT_PREFIX={self.s3_export_prefix}
S3_BACKUP_PREFIX={self.s3_backup_prefix}
MAX_FILE_SIZE={self.max_file_size}
MAX_FILES_PER_UPLOAD={self.max_files_per_upload}

# Feature Flags
ENABLE_RELATIONAL_DB={str(self.enable_relational_db).lower()}
ENABLE_VECTOR_SEARCH={str(self.enable_vector_search).lower()}
ENABLE_GRAPH_DB={str(self.enable_graph_db).lower()}
ENABLE_DOCUMENT_UPLOAD={str(self.enable_document_upload).lower()}
ENABLE_KNOWLEDGE_GRAPH={str(self.enable_knowledge_graph).lower()}
ENABLE_AI_CHAT={str(self.enable_ai_chat).lower()}
ENABLE_EXPORT_FUNCTIONALITY={str(self.enable_export_functionality).lower()}
ENABLE_ANALYTICS={str(self.enable_analytics).lower()}
ENABLE_USER_MANAGEMENT={str(self.enable_user_management).lower()}

# Connection Settings
CONNECTION_TIMEOUT={self.connection_timeout}
QUERY_TIMEOUT={self.query_timeout}
MAX_RETRIES={self.max_retries}

# Performance Settings
CONNECTION_POOLING={str(self.connection_pooling).lower()}
QUERY_CACHING={str(self.query_caching).lower()}
ENABLE_QUERY_LOGGING={str(self.enable_query_logging).lower()}

# Embedding Configuration
EMBEDDING_DIMENSION={self.embedding_dimension}
EMBEDDING_MODEL={self.embedding_model}

# CloudWatch Configuration
CLOUDWATCH_LOG_GROUP={self.cloudwatch_log_group}
CLOUDWATCH_LOG_STREAM_PREFIX={self.cloudwatch_log_stream_prefix}
ENABLE_CLOUDWATCH_METRICS={str(self.enable_cloudwatch_metrics).lower()}
ENABLE_XRAY_TRACING={str(self.enable_xray_tracing).lower()}

# Auto Scaling Configuration
ENABLE_AUTO_SCALING={str(self.enable_auto_scaling).lower()}
MIN_CAPACITY={self.min_capacity}
MAX_CAPACITY={self.max_capacity}
TARGET_CPU_UTILIZATION={self.target_cpu_utilization}
TARGET_MEMORY_UTILIZATION={self.target_memory_utilization}

# Backup Configuration
ENABLE_AUTOMATED_BACKUPS={str(self.enable_automated_backups).lower()}
BACKUP_RETENTION_DAYS={self.backup_retention_days}
BACKUP_SCHEDULE={self.backup_schedule}

# Cost Optimization
ENABLE_COST_OPTIMIZATION={str(self.enable_cost_optimization).lower()}
USE_SPOT_INSTANCES={str(self.use_spot_instances).lower()}
ENABLE_RESOURCE_TAGGING={str(self.enable_resource_tagging).lower()}
"""
        
        with open(file_path, 'w') as f:
            f.write(template_content)
        
        logger.info(f"Created AWS environment template at {file_path}")


# Global configuration instance
_aws_native_config: Optional[AWSNativeConfig] = None


def get_aws_native_config() -> AWSNativeConfig:
    """Get or create global AWS-Native configuration instance."""
    global _aws_native_config
    
    if _aws_native_config is None:
        _aws_native_config = AWSNativeConfig()
    
    return _aws_native_config


def reload_aws_native_config() -> AWSNativeConfig:
    """Reload AWS-Native configuration (useful for testing)."""
    global _aws_native_config
    _aws_native_config = None
    return get_aws_native_config()


def create_aws_env_template(file_path: str = ".env.aws.example") -> None:
    """
    Create an AWS environment template file.
    
    Args:
        file_path: Path to create the template file
    """
    config = get_aws_native_config()
    config.create_env_file_template(file_path)