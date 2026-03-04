#!/usr/bin/env python3
"""
Development Configuration for Multimodal Librarian Learning Deployment

This module provides development-specific configuration settings optimized for
learning and cost efficiency. It includes development database settings,
debugging options, and AWS service configurations.
"""

import os
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass
from pathlib import Path

# Development environment settings
ENVIRONMENT = "development"
DEBUG = True
LOG_LEVEL = logging.DEBUG

# AWS Configuration for Development
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
AWS_PROFILE = os.getenv("AWS_PROFILE", "default")

# Development-specific resource naming
RESOURCE_PREFIX = "multimodal-librarian-dev"
STACK_NAME = "MultimodalLibrarianDevStack"

@dataclass
class DatabaseConfig:
    """Development database configuration."""
    host: str = os.getenv("DB_HOST", "localhost")
    port: int = int(os.getenv("DB_PORT", "5432"))
    database: str = os.getenv("DB_NAME", "multimodal_librarian_dev")
    username: str = os.getenv("DB_USERNAME", "dev_user")
    password: str = os.getenv("DB_PASSWORD", "dev_password")
    
    # Development-specific settings
    pool_size: int = 5  # Smaller pool for dev
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600
    echo: bool = True  # Enable SQL logging in dev
    
    @property
    def url(self) -> str:
        """Database connection URL."""
        return f"postgresql://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"

@dataclass
class RedisConfig:
    """Development Redis configuration."""
    host: str = os.getenv("REDIS_HOST", "localhost")
    port: int = int(os.getenv("REDIS_PORT", "6379"))
    password: Optional[str] = os.getenv("REDIS_PASSWORD")
    db: int = int(os.getenv("REDIS_DB", "0"))
    
    # Development-specific settings
    decode_responses: bool = True
    socket_timeout: int = 5
    socket_connect_timeout: int = 5
    max_connections: int = 10  # Smaller pool for dev

@dataclass
class S3Config:
    """Development S3 configuration."""
    bucket_name: str = os.getenv("S3_BUCKET_NAME", f"{RESOURCE_PREFIX}-storage")
    region: str = AWS_REGION
    
    # Development-specific settings
    use_ssl: bool = True
    signature_version: str = "s3v4"
    max_pool_connections: int = 10
    
    # Lifecycle settings for cost optimization
    lifecycle_rules: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.lifecycle_rules is None:
            self.lifecycle_rules = {
                "temp_files": {
                    "prefix": "temp/",
                    "expiration_days": 1
                },
                "dev_uploads": {
                    "prefix": "uploads/",
                    "expiration_days": 7
                },
                "logs": {
                    "prefix": "logs/",
                    "expiration_days": 3
                }
            }

@dataclass
class NeptuneConfig:
    """Development Neptune (AWS-native graph database) configuration."""
    endpoint: str = os.getenv("NEPTUNE_ENDPOINT", "")
    port: int = int(os.getenv("NEPTUNE_PORT", "8182"))
    
    # Development-specific settings
    use_ssl: bool = True
    max_connection_pool_size: int = 50
    connection_acquisition_timeout: int = 60

@dataclass
class OpenSearchConfig:
    """Development OpenSearch (AWS-native vector database) configuration."""
    endpoint: str = os.getenv("OPENSEARCH_ENDPOINT", "")
    port: int = int(os.getenv("OPENSEARCH_PORT", "443"))
    
    # Development-specific settings
    index_name: str = "multimodal_dev_index"
    use_ssl: bool = True
    verify_certs: bool = True
    dimension: int = 768  # Standard embedding dimension

@dataclass
class APIConfig:
    """Development API configuration."""
    host: str = os.getenv("API_HOST", "0.0.0.0")
    port: int = int(os.getenv("API_PORT", "8000"))
    
    # Development-specific settings
    reload: bool = True  # Enable auto-reload in dev
    workers: int = 1  # Single worker for dev
    log_level: str = "debug"
    access_log: bool = True
    
    # CORS settings for development
    cors_origins: list = ["http://localhost:3000", "http://localhost:8080", "http://127.0.0.1:8000"]
    cors_methods: list = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    cors_headers: list = ["*"]

@dataclass
class MLConfig:
    """Development ML configuration."""
    # Model settings optimized for development
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"  # Smaller model for dev
    chunk_size: int = 512  # Smaller chunks for faster processing
    chunk_overlap: int = 50
    
    # Training settings
    batch_size: int = 8  # Smaller batch for dev
    max_epochs: int = 5  # Fewer epochs for dev
    learning_rate: float = 0.001
    
    # Resource limits for development
    max_memory_gb: int = 4
    max_cpu_cores: int = 2

@dataclass
class LoggingConfig:
    """Development logging configuration."""
    level: str = "DEBUG"
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # Development-specific settings
    console_output: bool = True
    file_output: bool = True
    log_file: str = "logs/multimodal_librarian_dev.log"
    
    # CloudWatch logging (optional for dev)
    cloudwatch_enabled: bool = False
    cloudwatch_group: str = "/aws/ecs/multimodal-librarian-dev"
    cloudwatch_stream: str = "application"

@dataclass
class SecurityConfig:
    """Development security configuration."""
    # Relaxed security for development
    secret_key: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    
    # Development-specific settings
    allow_http: bool = True  # Allow HTTP in dev
    csrf_protection: bool = False  # Disable CSRF in dev
    rate_limiting: bool = False  # Disable rate limiting in dev

class DevelopmentConfig:
    """Main development configuration class."""
    
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
        
        # AWS-specific settings
        self.aws_region = AWS_REGION
        self.aws_profile = AWS_PROFILE
        self.resource_prefix = RESOURCE_PREFIX
        self.stack_name = STACK_NAME
        
        # Development features
        self.features = {
            "auto_reload": True,
            "debug_toolbar": True,
            "sql_echo": True,
            "detailed_errors": True,
            "mock_external_apis": False,  # Set to True to mock external API calls
            "seed_data": True,
            "cost_monitoring": True
        }
        
        # Cost optimization settings
        self.cost_optimization = {
            "auto_shutdown": {
                "enabled": True,
                "schedule": "0 22 * * 1-5",  # Shutdown at 10 PM on weekdays
                "startup_schedule": "0 8 * * 1-5"  # Start at 8 AM on weekdays
            },
            "resource_limits": {
                "max_monthly_cost": 50.0,  # $50 monthly limit
                "alert_threshold": 0.8  # Alert at 80% of limit
            }
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
            "connection_acquisition_timeout": self.neptune.connection_acquisition_timeout
        }
    
    def get_opensearch_config(self) -> Dict[str, Any]:
        """Get OpenSearch configuration dictionary."""
        return {
            "endpoint": self.opensearch.endpoint,
            "port": self.opensearch.port,
            "index_name": self.opensearch.index_name,
            "use_ssl": self.opensearch.use_ssl,
            "verify_certs": self.opensearch.verify_certs,
            "dimension": self.opensearch.dimension
        }
    
    def setup_logging(self) -> None:
        """Setup logging configuration for development."""
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
        
        # Set specific logger levels for development
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
        logging.getLogger("boto3").setLevel(logging.WARNING)
        logging.getLogger("botocore").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    def validate_config(self) -> bool:
        """Validate development configuration."""
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
                "workers": self.api.workers
            },
            "features": self.features,
            "cost_optimization": self.cost_optimization
        }

# Global development configuration instance
dev_config = DevelopmentConfig()

# Convenience functions for common configuration access
def get_database_url() -> str:
    """Get database connection URL."""
    return dev_config.get_database_url()

def get_redis_url() -> str:
    """Get Redis connection URL."""
    return dev_config.get_redis_url()

def get_s3_config() -> Dict[str, Any]:
    """Get S3 configuration."""
    return dev_config.get_s3_config()

def is_development() -> bool:
    """Check if running in development environment."""
    return dev_config.environment == "development"

def setup_development_logging() -> None:
    """Setup development logging."""
    dev_config.setup_logging()

# Initialize logging when module is imported
if __name__ != "__main__":
    setup_development_logging()

# Example usage and testing
if __name__ == "__main__":
    print("Development Configuration for Multimodal Librarian")
    print("=" * 50)
    
    # Validate configuration
    if dev_config.validate_config():
        print("✅ Configuration validation passed")
    else:
        print("❌ Configuration validation failed")
    
    # Display configuration summary
    config_dict = dev_config.to_dict()
    
    print(f"\nEnvironment: {config_dict['environment']}")
    print(f"Debug Mode: {config_dict['debug']}")
    print(f"Database URL: {config_dict['database']['url']}")
    print(f"Redis URL: {config_dict['redis']['url']}")
    print(f"S3 Bucket: {config_dict['s3']['bucket_name']}")
    print(f"API Host: {config_dict['api']['host']}:{config_dict['api']['port']}")
    
    print("\nFeatures:")
    for feature, enabled in config_dict['features'].items():
        status = "✅" if enabled else "❌"
        print(f"  {status} {feature}")
    
    print("\nCost Optimization:")
    cost_opt = config_dict['cost_optimization']
    print(f"  Auto Shutdown: {'✅' if cost_opt['auto_shutdown']['enabled'] else '❌'}")
    print(f"  Monthly Limit: ${cost_opt['resource_limits']['max_monthly_cost']}")
    print(f"  Alert Threshold: {cost_opt['resource_limits']['alert_threshold'] * 100}%")