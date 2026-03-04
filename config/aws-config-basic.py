"""
AWS configuration management for the Multimodal Librarian application.

This module provides centralized configuration management that integrates with
AWS Secrets Manager and Parameter Store for secure and flexible configuration
in the learning deployment.
"""

import os
import logging
from typing import Dict, Any, Optional, Union
from functools import lru_cache
from dataclasses import dataclass, field

# Add the project root to the Python path for imports
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.multimodal_librarian.aws.secrets_manager_basic import get_secrets_manager


@dataclass
class DatabaseConfig:
    """Database configuration."""
    host: str
    port: int
    username: str
    password: str
    database: str
    engine: str = 'postgresql'
    
    @property
    def url(self) -> str:
        """Get database URL."""
        return f"{self.engine}://{self.username}:{self.password}@{self.host}:{self.port}/{self.database}"


@dataclass
class RedisConfig:
    """Redis configuration."""
    host: str
    port: int
    username: str = 'redis'
    auth_token: str = ''
    
    @property
    def url(self) -> str:
        """Get Redis URL."""
        if self.auth_token:
            return f"redis://:{self.auth_token}@{self.host}:{self.port}/0"
        else:
            return f"redis://{self.host}:{self.port}/0"


@dataclass
class Neo4jConfig:
    """Neo4j configuration."""
    host: str
    port: int
    username: str
    password: str
    
    @property
    def url(self) -> str:
        """Get Neo4j URL."""
        return f"bolt://{self.host}:{self.port}"


@dataclass
class ApiKeysConfig:
    """API keys configuration."""
    gemini_api_key: str = ''
    openai_api_key: str = ''
    google_api_key: str = ''
    
    def get_key(self, service: str) -> Optional[str]:
        """Get API key for a specific service."""
        key_mapping = {
            'gemini': self.gemini_api_key,
            'openai': self.openai_api_key,
            'google': self.google_api_key
        }
        return key_mapping.get(service.lower())


@dataclass
class AppConfig:
    """Application configuration."""
    debug: bool = False
    log_level: str = 'INFO'
    max_workers: int = 4
    timeout: int = 30


@dataclass
class MLConfig:
    """Machine Learning configuration."""
    batch_size: int = 32
    model_path: str = '/models'
    max_chunk_size: int = 1000
    embedding_dimension: int = 768


@dataclass
class ChatConfig:
    """Chat configuration."""
    max_connections: int = 100
    message_limit: int = 1000
    session_timeout: int = 3600


@dataclass
class PerformanceConfig:
    """Performance configuration."""
    cache_ttl: int = 300
    max_concurrent_requests: int = 50
    request_rate_limit: int = 100


@dataclass
class SecurityConfig:
    """Security configuration."""
    jwt_expiry: int = 3600
    max_login_attempts: int = 5
    session_timeout: int = 1800


@dataclass
class AWSConfig:
    """Complete AWS configuration."""
    database: DatabaseConfig
    redis: RedisConfig
    neo4j: Neo4jConfig
    api_keys: ApiKeysConfig
    app: AppConfig = field(default_factory=AppConfig)
    ml: MLConfig = field(default_factory=MLConfig)
    chat: ChatConfig = field(default_factory=ChatConfig)
    performance: PerformanceConfig = field(default_factory=PerformanceConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)


class AWSConfigManager:
    """AWS configuration manager with secrets integration."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.secrets_manager = get_secrets_manager()
        self._config_cache: Optional[AWSConfig] = None
        self._cache_ttl = 300  # 5 minutes
        self._last_refresh = 0
    
    @lru_cache(maxsize=1)
    def get_config(self, force_refresh: bool = False) -> AWSConfig:
        """
        Get complete AWS configuration.
        
        Args:
            force_refresh: Force refresh from AWS services
            
        Returns:
            Complete AWS configuration
        """
        import time
        current_time = time.time()
        
        # Check if we need to refresh the cache
        if (force_refresh or 
            self._config_cache is None or 
            (current_time - self._last_refresh) > self._cache_ttl):
            
            self.logger.info("Refreshing AWS configuration from secrets and parameters")
            self._config_cache = self._load_config()
            self._last_refresh = current_time
        
        return self._config_cache
    
    def _load_config(self) -> AWSConfig:
        """Load configuration from AWS Secrets Manager and Parameter Store."""
        try:
            # Load secrets
            database_config = self._load_database_config()
            redis_config = self._load_redis_config()
            api_keys_config = self._load_api_keys_config()
            
            # Load parameters
            app_config = self._load_app_config()
            ml_config = self._load_ml_config()
            chat_config = self._load_chat_config()
            performance_config = self._load_performance_config()
            security_config = self._load_security_config()
            
            return AWSConfig(
                database=database_config,
                redis=redis_config,
                api_keys=api_keys_config,
                app=app_config,
                ml=ml_config,
                chat=chat_config,
                performance=performance_config,
                security=security_config
            )
            
        except Exception as e:
            self.logger.error(f"Error loading AWS configuration: {e}")
            # Fallback to local configuration
            return self._load_local_config()
    
    def _load_database_config(self) -> DatabaseConfig:
        """Load database configuration from secrets."""
        db_secret = self.secrets_manager.get_database_config()
        if not db_secret:
            raise ValueError("Database configuration not found in secrets")
        
        return DatabaseConfig(
            host=db_secret['host'],
            port=db_secret['port'],
            username=db_secret['username'],
            password=db_secret['password'],
            database=db_secret['dbname'],
            engine=db_secret.get('engine', 'postgresql')
        )
    
    def _load_redis_config(self) -> RedisConfig:
        """Load Redis configuration from secrets."""
        redis_secret = self.secrets_manager.get_redis_config()
        if not redis_secret:
            raise ValueError("Redis configuration not found in secrets")
        
        return RedisConfig(
            host=redis_secret['host'],
            port=redis_secret['port'],
            username=redis_secret.get('username', 'redis'),
            auth_token=redis_secret.get('auth_token', '')
        )
        )
    
    def _load_api_keys_config(self) -> ApiKeysConfig:
        """Load API keys configuration from secrets."""
        api_keys_secret = self.secrets_manager.get_api_keys()
        if not api_keys_secret:
            self.logger.warning("API keys not found in secrets, using empty configuration")
            return ApiKeysConfig()
        
        return ApiKeysConfig(
            gemini_api_key=api_keys_secret.get('gemini_api_key', ''),
            openai_api_key=api_keys_secret.get('openai_api_key', ''),
            google_api_key=api_keys_secret.get('google_api_key', '')
        )
    
    def _load_app_config(self) -> AppConfig:
        """Load application configuration from parameters."""
        return AppConfig(
            debug=self._get_bool_parameter('app/debug', False),
            log_level=self._get_parameter('app/log_level', 'INFO'),
            max_workers=self._get_int_parameter('app/max_workers', 4),
            timeout=self._get_int_parameter('app/timeout', 30)
        )
    
    def _load_ml_config(self) -> MLConfig:
        """Load ML configuration from parameters."""
        return MLConfig(
            batch_size=self._get_int_parameter('ml/batch_size', 32),
            model_path=self._get_parameter('ml/model_path', '/models'),
            max_chunk_size=self._get_int_parameter('ml/max_chunk_size', 1000),
            embedding_dimension=self._get_int_parameter('ml/embedding_dimension', 768)
        )
    
    def _load_chat_config(self) -> ChatConfig:
        """Load chat configuration from parameters."""
        return ChatConfig(
            max_connections=self._get_int_parameter('chat/max_connections', 100),
            message_limit=self._get_int_parameter('chat/message_limit', 1000),
            session_timeout=self._get_int_parameter('chat/session_timeout', 3600)
        )
    
    def _load_performance_config(self) -> PerformanceConfig:
        """Load performance configuration from parameters."""
        return PerformanceConfig(
            cache_ttl=self._get_int_parameter('performance/cache_ttl', 300),
            max_concurrent_requests=self._get_int_parameter('performance/max_concurrent_requests', 50),
            request_rate_limit=self._get_int_parameter('performance/request_rate_limit', 100)
        )
    
    def _load_security_config(self) -> SecurityConfig:
        """Load security configuration from parameters."""
        return SecurityConfig(
            jwt_expiry=self._get_int_parameter('security/jwt_expiry', 3600),
            max_login_attempts=self._get_int_parameter('security/max_login_attempts', 5),
            session_timeout=self._get_int_parameter('security/session_timeout', 1800)
        )
    
    def _get_parameter(self, param_name: str, default: str) -> str:
        """Get string parameter with default."""
        value = self.secrets_manager.get_parameter(param_name)
        return value if value is not None else default
    
    def _get_int_parameter(self, param_name: str, default: int) -> int:
        """Get integer parameter with default."""
        value = self.secrets_manager.get_parameter(param_name)
        if value is not None:
            try:
                return int(value)
            except ValueError:
                self.logger.warning(f"Invalid integer value for parameter {param_name}: {value}")
        return default
    
    def _get_bool_parameter(self, param_name: str, default: bool) -> bool:
        """Get boolean parameter with default."""
        value = self.secrets_manager.get_parameter(param_name)
        if value is not None:
            return value.lower() in ('true', '1', 'yes', 'on')
        return default
    
    def _load_local_config(self) -> AWSConfig:
        """Load configuration from local environment variables (fallback)."""
        self.logger.info("Loading configuration from local environment variables")
        
        return AWSConfig(
            database=DatabaseConfig(
                host=os.getenv('DB_HOST', 'localhost'),
                port=int(os.getenv('DB_PORT', '5432')),
                username=os.getenv('DB_USER', 'postgres'),
                password=os.getenv('DB_PASSWORD', 'password'),
                database=os.getenv('DB_NAME', 'multimodal_librarian')
            ),
            redis=RedisConfig(
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', '6379')),
                auth_token=os.getenv('REDIS_PASSWORD', '')
            ),
            neo4j=Neo4jConfig(
                host=os.getenv('NEO4J_HOST', 'localhost'),
                port=int(os.getenv('NEO4J_PORT', '7687')),
                username=os.getenv('NEO4J_USER', 'neo4j'),
                password=os.getenv('NEO4J_PASSWORD', 'password')
            ),
            api_keys=ApiKeysConfig(
                gemini_api_key=os.getenv('GEMINI_API_KEY', ''),
                openai_api_key=os.getenv('OPENAI_API_KEY', ''),
                google_api_key=os.getenv('GOOGLE_API_KEY', '')
            ),
            app=AppConfig(
                debug=os.getenv('DEBUG', 'false').lower() == 'true',
                log_level=os.getenv('LOG_LEVEL', 'INFO'),
                max_workers=int(os.getenv('MAX_WORKERS', '4')),
                timeout=int(os.getenv('REQUEST_TIMEOUT', '30'))
            ),
            ml=MLConfig(
                batch_size=int(os.getenv('ML_BATCH_SIZE', '32')),
                model_path=os.getenv('ML_MODEL_PATH', '/models'),
                max_chunk_size=int(os.getenv('MAX_CHUNK_SIZE', '1000')),
                embedding_dimension=int(os.getenv('EMBEDDING_DIMENSION', '768'))
            ),
            chat=ChatConfig(
                max_connections=int(os.getenv('MAX_WEBSOCKET_CONNECTIONS', '100')),
                message_limit=int(os.getenv('CHAT_MESSAGE_LIMIT', '1000')),
                session_timeout=int(os.getenv('CHAT_SESSION_TIMEOUT', '3600'))
            ),
            performance=PerformanceConfig(
                cache_ttl=int(os.getenv('CACHE_TTL', '300')),
                max_concurrent_requests=int(os.getenv('MAX_CONCURRENT_REQUESTS', '50')),
                request_rate_limit=int(os.getenv('REQUEST_RATE_LIMIT', '100'))
            ),
            security=SecurityConfig(
                jwt_expiry=int(os.getenv('JWT_EXPIRY', '3600')),
                max_login_attempts=int(os.getenv('MAX_LOGIN_ATTEMPTS', '5')),
                session_timeout=int(os.getenv('SESSION_TIMEOUT', '1800'))
            )
        )
    
    def refresh_config(self) -> AWSConfig:
        """Force refresh configuration from AWS."""
        self.get_config.cache_clear()  # Clear LRU cache
        return self.get_config(force_refresh=True)
    
    def validate_config(self) -> Dict[str, bool]:
        """Validate configuration completeness."""
        config = self.get_config()
        validation_results = {}
        
        # Validate database config
        validation_results['database'] = all([
            config.database.host,
            config.database.username,
            config.database.password,
            config.database.database
        ])
        
        # Validate Redis config
        validation_results['redis'] = all([
            config.redis.host,
            config.redis.port > 0
        ])
        
        # Validate Neo4j config
        validation_results['neo4j'] = all([
            config.neo4j.host,
            config.neo4j.username,
            config.neo4j.password
        ])
        
        # Validate API keys (at least one should be present)
        validation_results['api_keys'] = any([
            config.api_keys.gemini_api_key,
            config.api_keys.openai_api_key,
            config.api_keys.google_api_key
        ])
        
        return validation_results
    
    def get_database_url(self) -> str:
        """Get database URL."""
        config = self.get_config()
        return config.database.url
    
    def get_redis_url(self) -> str:
        """Get Redis URL."""
        config = self.get_config()
        return config.redis.url
    
    def get_neo4j_url(self) -> str:
        """Get Neo4j URL."""
        config = self.get_config()
        return config.neo4j.url
    
    def get_api_key(self, service: str) -> Optional[str]:
        """Get API key for a specific service."""
        config = self.get_config()
        return config.api_keys.get_key(service)


# Global configuration manager instance
_config_manager: Optional[AWSConfigManager] = None

def get_aws_config_manager() -> AWSConfigManager:
    """Get the global AWS configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = AWSConfigManager()
    return _config_manager


def get_aws_config(force_refresh: bool = False) -> AWSConfig:
    """Get AWS configuration."""
    return get_aws_config_manager().get_config(force_refresh)


# Convenience functions for common configuration access
def get_database_url() -> str:
    """Get database URL from AWS configuration."""
    return get_aws_config_manager().get_database_url()


def get_redis_url() -> str:
    """Get Redis URL from AWS configuration."""
    return get_aws_config_manager().get_redis_url()


def get_neo4j_url() -> str:
    """Get Neo4j URL from AWS configuration."""
    return get_aws_config_manager().get_neo4j_url()


def get_api_key(service: str) -> Optional[str]:
    """Get API key for a specific service from AWS configuration."""
    return get_aws_config_manager().get_api_key(service)


def validate_aws_config() -> Dict[str, bool]:
    """Validate AWS configuration completeness."""
    return get_aws_config_manager().validate_config()


def refresh_aws_config() -> AWSConfig:
    """Force refresh AWS configuration from AWS services."""
    return get_aws_config_manager().refresh_config()


# Configuration decorator for automatic AWS config injection
def inject_aws_config(func):
    """Decorator to inject AWS configuration as function argument."""
    def wrapper(*args, **kwargs):
        if 'aws_config' not in kwargs:
            kwargs['aws_config'] = get_aws_config()
        return func(*args, **kwargs)
    return wrapper


# Environment-aware configuration loading
def load_config_for_environment(environment: str = None) -> AWSConfig:
    """Load configuration for a specific environment."""
    if environment:
        # This would require environment-specific configuration loading
        # For now, we use the default configuration
        pass
    
    return get_aws_config()


# Configuration validation decorator
def require_valid_config(*required_components):
    """Decorator to ensure required configuration components are valid."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            validation_results = validate_aws_config()
            
            missing_components = [
                component for component in required_components 
                if not validation_results.get(component, False)
            ]
            
            if missing_components:
                raise ValueError(f"Missing or invalid configuration components: {missing_components}")
            
            return func(*args, **kwargs)
        return wrapper
    return decorator