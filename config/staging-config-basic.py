#!/usr/bin/env python3
"""
Staging Configuration for Multimodal Librarian Learning Deployment

This module provides staging-specific configuration settings optimized for
production-like testing while maintaining cost efficiency. It includes
enhanced monitoring, security, and deployment capabilities.
"""

import os
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path

# Staging environment settings
ENVIRONMENT = "staging"
DEBUG = False  # Production-like setting
LOG_LEVEL = logging.INFO

# AWS Configuration for Staging
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_PROFILE = os.getenv("AWS_PROFILE", "default")

# Staging-specific resource naming
RESOURCE_PREFIX = "multimodal-librarian-staging"
STACK_NAME = "MultimodalLibrarianStagingStack"

@dataclass
class DatabaseConfig:
    """Staging database configuration."""
    host: str = os.getenv("DB_HOST", "localhost")
    port: int = int(os.getenv("DB_PORT", "5432"))
    database: str = os.getenv("DB_NAME", "multimodal_librarian_staging")
    username: str = os.getenv("DB_USERNAME", "staging_user")
    password: str = os.getenv("DB_PASSWORD", "staging_password")
    
    # Production-like settings
    pool_size: int = 10  # Larger pool for staging
    max_overflow: int = 20
    pool_timeout: int = 30
    pool_recycle: int = 3600
    echo: bool = False  # Disable SQL logging in staging
    
    # Connection retry settings
    connect_timeout: int = 10
    command_timeout: int = 60
    
    @property
    def url(self) -> str:
        """Database connection URL."""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

@dataclass
class RedisConfig:
    """Staging Redis configuration."""
    host: str = os.getenv("REDIS_HOST", "localhost")
    port: int = int(os.getenv("REDIS_PORT", "6379"))
    password: Optional[str] = os.getenv("REDIS_PASSWORD")
    db: int = int(os.getenv("REDIS_DB", "0"))
    
    # Production-like settings
    decode_responses: bool = True
    socket_timeout: int = 10
    socket_connect_timeout: int = 10
    max_connections: int = 50  # Larger pool for staging
    retry_on_timeout: bool = True
    health_check_interval: int = 30

@dataclass
class S3Config:
    """Staging S3 configuration."""
    bucket_name: str = os.getenv("S3_BUCKET_NAME", f"{RESOURCE_PREFIX}-storage")
    region: str = AWS_REGION
    
    # Production-like settings
    use_ssl: bool = True
    signature_version: str = "s3v4"
    max_pool_connections: int = 50
    
    # Enhanced lifecycle settings for staging
    lifecycle_rules: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.lifecycle_rules is None:
            self.lifecycle_rules = {
                "temp_files": {
                    "prefix": "temp/",
                    "expiration_days": 3
                },
                "staging_uploads": {
                    "prefix": "uploads/",
                    "expiration_days": 30
                },
                "logs": {
                    "prefix": "logs/",
                    "expiration_days": 7
                },
                "backups": {
                    "prefix": "backups/",
                    "transition_to_ia_days": 7,
                    "expiration_days": 90
                }
            }

@dataclass
class NeptuneConfig:
    """Staging Neptune (AWS-native graph database) configuration."""
    endpoint: str = os.getenv("NEPTUNE_ENDPOINT", "")
    port: int = int(os.getenv("NEPTUNE_PORT", "8182"))
    
    # Production-like settings
    use_ssl: bool = True
    max_connection_pool_size: int = 100
    connection_acquisition_timeout: int = 60
    
    # Performance settings
    fetch_size: int = 1000
    max_transaction_retry_time: int = 30

@dataclass
class OpenSearchConfig:
    """Staging OpenSearch (AWS-native vector database) configuration."""
    endpoint: str = os.getenv("OPENSEARCH_ENDPOINT", "")
    port: int = int(os.getenv("OPENSEARCH_PORT", "443"))
    
    # Production-like settings
    index_name: str = "multimodal_staging_index"
    use_ssl: bool = True
    verify_certs: bool = True
    
    # Performance settings
    dimension: int = 768
    search_params: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.search_params is None:
            self.search_params = {
                "size": 10,
                "min_score": 0.5
            }

@dataclass
class APIConfig:
    """Staging API configuration."""
    host: str = os.getenv("API_HOST", "0.0.0.0")
    port: int = int(os.getenv("API_PORT", "8000"))
    
    # Production-like settings
    reload: bool = False  # Disable auto-reload in staging
    workers: int = 2  # Multiple workers for staging
    log_level: str = "info"
    access_log: bool = True
    
    # CORS settings for staging
    cors_origins: list = [
        "https://staging.multimodal-librarian.com",
        "http://localhost:3000"  # For testing
    ]
    cors_methods: list = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    cors_headers: list = ["*"]
    
    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 100
    rate_limit_window: int = 60

@dataclass
class MLConfig:
    """Staging ML configuration."""
    # Model settings for staging
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    chunk_size: int = 1024  # Larger chunks for staging
    chunk_overlap: int = 100
    
    # Training settings
    batch_size: int = 16  # Larger batch for staging
    max_epochs: int = 10
    learning_rate: float = 0.001
    
    # Resource limits for staging
    max_memory_gb: int = 8
    max_cpu_cores: int = 4
    
    # Performance monitoring
    enable_metrics: bool = True
    metrics_interval: int = 60

@dataclass
class LoggingConfig:
    """Staging logging configuration."""
    level: str = "INFO"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
    
    # Production-like settings
    console_output: bool = True
    file_output: bool = True
    log_file: str = "logs/multimodal_librarian_staging.log"
    
    # CloudWatch logging (enabled for staging)
    cloudwatch_enabled: bool = True
    cloudwatch_group: str = "/aws/ecs/multimodal-librarian-staging"
    cloudwatch_stream: str = "application"
    
    # Log rotation
    max_file_size: str = "100MB"
    backup_count: int = 5

@dataclass
class SecurityConfig:
    """Staging security configuration."""
    # Production-like security
    secret_key: str = os.getenv("SECRET_KEY", "staging-secret-key-from-secrets-manager")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30  # Shorter for staging
    
    # Production-like settings
    allow_http: bool = False  # HTTPS only in staging
    csrf_protection: bool = True
    rate_limiting: bool = True
    
    # Security headers
    security_headers: Dict[str, str] = None
    
    def __post_init__(self):
        if self.security_headers is None:
            self.security_headers = {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "X-XSS-Protection": "1; mode=block",
                "Strict-Transport-Security": "max-age=31536000; includeSubDomains"
            }

@dataclass
class BlueGreenConfig:
    """Blue-green deployment configuration."""
    enabled: bool = True
    
    # Target group configuration
    blue_target_group_arn: str = os.getenv("BLUE_TARGET_GROUP_ARN", "")
    green_target_group_arn: str = os.getenv("GREEN_TARGET_GROUP_ARN", "")
    
    # Health check settings
    health_check_path: str = "/health"
    health_check_interval: int = 30
    health_check_timeout: int = 5
    healthy_threshold: int = 2
    unhealthy_threshold: int = 3
    
    # Deployment settings
    deployment_timeout: int = 600  # 10 minutes
    rollback_on_failure: bool = True
    
    # Traffic shifting
    traffic_shift_percentage: int = 100
    traffic_shift_interval: int = 60

class StagingConfig:
    """Main staging configuration class."""
    
    def __init__(self):
        self.environment = ENVIRONMENT
        self.debug = DEBUG
        self.log_level = LOG_LEVEL
        
        # Initialize configuration components
        self.database = DatabaseConfig()
        self.redis = RedisConfig()
        self.s3 = S3Config()
        self.neptune = NeptuneConfig()
        self.opensearch = OpenSearchConfig()
        self.api = APIConfig()
        self.ml = MLConfig()
        self.logging = LoggingConfig()
        self.security = SecurityConfig()
        self.blue_green = BlueGreenConfig()
        
        # AWS-specific settings
        self.aws_region = AWS_REGION
        self.aws_profile = AWS_PROFILE
        self.resource_prefix = RESOURCE_PREFIX
        self.stack_name = STACK_NAME
        
        # Staging features
        self.features = {
            "auto_reload": False,
            "debug_toolbar": False,
            "sql_echo": False,
            "detailed_errors": False,
            "mock_external_apis": False,
            "seed_data": False,
            "performance_monitoring": True,
            "security_scanning": True,
            "blue_green_deployment": True,
            "automated_testing": True
        }
        
        # Monitoring and alerting
        self.monitoring = {
            "enabled": True,
            "metrics_collection": True,
            "custom_metrics": True,
            "alerting": True,
            "dashboard": True,
            "log_aggregation": True,
            "distributed_tracing": True
        }
        
        # Cost optimization for staging
        self.cost_optimization = {
            "auto_shutdown": {
                "enabled": False,  # Keep staging running
                "schedule": None
            },
            "resource_limits": {
                "max_monthly_cost": 200.0,  # Higher limit for staging
                "alert_threshold": 0.8
            },
            "rightsizing": {
                "enabled": True,
                "check_interval": "weekly"
            }
        }
        
        # Promotion settings
        self.promotion = {
            "source_environment": "development",
            "validation_required": True,
            "approval_required": True,
            "rollback_enabled": True,
            "smoke_tests": True,
            "performance_tests": True
        }
    
    def get_database_url(self) -> str:
        """Get database connection URL."""
        return self.database.url
    
    def get_redis_url(self) -> str:
        """Get Redis connection URL."""
        if self.redis.password:
            return f"redis://:{self.redis.password}@{self.redis.host}:{self.redis.port}/{self.redis.db}"
        return f"redis://{self.redis.host}:{self.redis.port}/{self.redis.db}"
    
    def get_s3_config(self) -> Dict[str, Any]:
        """Get S3 configuration dictionary."""
        return {
            "bucket_name": self.s3.bucket_name,
            "region_name": self.s3.region,
            "use_ssl": self.s3.use_ssl,
            "signature_version": self.s3.signature_version,
            "config": {
                "max_pool_connections": self.s3.max_pool_connections
            }
        }
    
    def get_neptune_config(self) -> Dict[str, Any]:
        """Get Neptune configuration dictionary."""
        return {
            "endpoint": self.neptune.endpoint,
            "port": self.neptune.port,
            "use_ssl": self.neptune.use_ssl,
            "max_connection_pool_size": self.neptune.max_connection_pool_size,
            "connection_acquisition_timeout": self.neptune.connection_acquisition_timeout,
            "fetch_size": self.neptune.fetch_size
        }
    
    def get_opensearch_config(self) -> Dict[str, Any]:
        """Get OpenSearch configuration dictionary."""
        return {
            "endpoint": self.opensearch.endpoint,
            "port": self.opensearch.port,
            "index_name": self.opensearch.index_name,
            "use_ssl": self.opensearch.use_ssl,
            "verify_certs": self.opensearch.verify_certs,
            "dimension": self.opensearch.dimension,
            "search_params": self.opensearch.search_params
        }
    
    def get_blue_green_config(self) -> Dict[str, Any]:
        """Get blue-green deployment configuration."""
        return {
            "enabled": self.blue_green.enabled,
            "blue_target_group_arn": self.blue_green.blue_target_group_arn,
            "green_target_group_arn": self.blue_green.green_target_group_arn,
            "health_check": {
                "path": self.blue_green.health_check_path,
                "interval": self.blue_green.health_check_interval,
                "timeout": self.blue_green.health_check_timeout,
                "healthy_threshold": self.blue_green.healthy_threshold,
                "unhealthy_threshold": self.blue_green.unhealthy_threshold
            },
            "deployment": {
                "timeout": self.blue_green.deployment_timeout,
                "rollback_on_failure": self.blue_green.rollback_on_failure
            }
        }
    
    def setup_logging(self) -> None:
        """Setup logging configuration for staging."""
        # Create logs directory if it doesn't exist
        log_dir = Path(self.logging.log_file).parent
        log_dir.mkdir(exist_ok=True)
        
        # Configure logging
        logging.basicConfig(
            level=getattr(logging, self.logging.level),
            format=self.logging.format,
            handlers=[
                logging.StreamHandler() if self.logging.console_output else None,
                logging.FileHandler(self.logging.log_file) if self.logging.file_output else None
            ]
        )
        
        # Set specific logger levels for staging
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("boto3").setLevel(logging.ERROR)
        logging.getLogger("botocore").setLevel(logging.ERROR)
        logging.getLogger("urllib3").setLevel(logging.ERROR)
    
    def validate_config(self) -> bool:
        """Validate staging configuration."""
        errors = []
        
        # Check required environment variables
        required_vars = ["AWS_REGION"]
        for var in required_vars:
            if not os.getenv(var):
                errors.append(f"Missing required environment variable: {var}")
        
        # Validate database configuration
        if not self.database.host:
            errors.append("Database host not configured")
        
        # Validate S3 configuration
        if not self.s3.bucket_name:
            errors.append("S3 bucket name not configured")
        
        # Validate blue-green configuration
        if self.blue_green.enabled:
            if not self.blue_green.blue_target_group_arn:
                errors.append("Blue target group ARN not configured")
            if not self.blue_green.green_target_group_arn:
                errors.append("Green target group ARN not configured")
        
        if errors:
            for error in errors:
                logging.error(f"Configuration error: {error}")
            return False
        
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "environment": self.environment,
            "debug": self.debug,
            "database": {
                "url": self.get_database_url(),
                "pool_size": self.database.pool_size,
                "echo": self.database.echo
            },
            "redis": {
                "url": self.get_redis_url()
            },
            "s3": self.get_s3_config(),
            "neptune": self.get_neptune_config(),
            "opensearch": self.get_opensearch_config(),
            "api": {
                "host": self.api.host,
                "port": self.api.port,
                "reload": self.api.reload,
                "workers": self.api.workers,
                "rate_limit_enabled": self.api.rate_limit_enabled
            },
            "blue_green": self.get_blue_green_config(),
            "features": self.features,
            "monitoring": self.monitoring,
            "cost_optimization": self.cost_optimization,
            "promotion": self.promotion
        }

# Global staging configuration instance
staging_config = StagingConfig()

# Convenience functions for common configuration access
def get_database_url() -> str:
    """Get database connection URL."""
    return staging_config.get_database_url()

def get_redis_url() -> str:
    """Get Redis connection URL."""
    return staging_config.get_redis_url()

def get_s3_config() -> Dict[str, Any]:
    """Get S3 configuration."""
    return staging_config.get_s3_config()

def get_blue_green_config() -> Dict[str, Any]:
    """Get blue-green deployment configuration."""
    return staging_config.get_blue_green_config()

def is_staging() -> bool:
    """Check if running in staging environment."""
    return staging_config.environment == "staging"

def setup_staging_logging() -> None:
    """Setup staging logging."""
    staging_config.setup_logging()

# Initialize logging when module is imported
if __name__ != "__main__":
    setup_staging_logging()

# Example usage and testing
if __name__ == "__main__":
    print("Staging Configuration for Multimodal Librarian")
    print("=" * 50)
    
    # Validate configuration
    if staging_config.validate_config():
        print("✅ Configuration validation passed")
    else:
        print("❌ Configuration validation failed")
    
    # Display configuration summary
    config_dict = staging_config.to_dict()
    
    print(f"\nEnvironment: {config_dict['environment']}")
    print(f"Debug Mode: {config_dict['debug']}")
    print(f"Database URL: {config_dict['database']['url']}")
    print(f"Redis URL: {config_dict['redis']['url']}")
    print(f"S3 Bucket: {config_dict['s3']['bucket_name']}")
    print(f"API Host: {config_dict['api']['host']}:{config_dict['api']['port']}")
    print(f"Workers: {config_dict['api']['workers']}")
    
    print("\nFeatures:")
    for feature, enabled in config_dict['features'].items():
        status = "✅" if enabled else "❌"
        print(f"  {status} {feature}")
    
    print("\nMonitoring:")
    for monitor, enabled in config_dict['monitoring'].items():
        status = "✅" if enabled else "❌"
        print(f"  {status} {monitor}")
    
    print("\nBlue-Green Deployment:")
    bg_config = config_dict['blue_green']
    print(f"  Enabled: {'✅' if bg_config['enabled'] else '❌'}")
    print(f"  Health Check Path: {bg_config['health_check']['path']}")
    print(f"  Deployment Timeout: {bg_config['deployment']['timeout']}s")
    
    print("\nCost Optimization:")
    cost_opt = config_dict['cost_optimization']
    print(f"  Auto Shutdown: {'✅' if cost_opt['auto_shutdown']['enabled'] else '❌'}")
    print(f"  Monthly Limit: ${cost_opt['resource_limits']['max_monthly_cost']}")
    print(f"  Alert Threshold: {cost_opt['resource_limits']['alert_threshold'] * 100}%")
    
    print("\nPromotion Settings:")
    promotion = config_dict['promotion']
    print(f"  Source: {promotion['source_environment']}")
    print(f"  Validation Required: {'✅' if promotion['validation_required'] else '❌'}")
    print(f"  Approval Required: {'✅' if promotion['approval_required'] else '❌'}")