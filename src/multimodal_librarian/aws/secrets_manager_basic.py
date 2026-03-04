"""
AWS Secrets Manager integration for secure configuration management.

This module provides basic AWS Secrets Manager integration for the learning deployment,
allowing secure storage and retrieval of API keys, database credentials, and other
sensitive configuration data.
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from functools import lru_cache

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from ..config import get_settings


class SecretsManagerBasic:
    """Basic AWS Secrets Manager integration for secure configuration."""
    
    def __init__(self):
        self.settings = get_settings()
        self.project_name = getattr(self.settings, 'project_name', 'multimodal-librarian')
        self.environment = getattr(self.settings, 'environment', 'learning')
        self.region = getattr(self.settings, 'aws_region', 'us-east-1')
        
        # Logger for this module (initialize first)
        self.logger = logging.getLogger(__name__)
        
        # Initialize AWS client
        self.secrets_client = None
        self.ssm_client = None
        self._initialize_clients()
        
        # Cache for secrets to avoid repeated API calls
        self._secrets_cache = {}
        self._cache_ttl = 300  # 5 minutes cache TTL
    
    def _initialize_clients(self):
        """Initialize AWS clients if running in AWS environment."""
        try:
            # Check if we're running in AWS (ECS, EC2, Lambda)
            if self._is_aws_environment():
                self.secrets_client = boto3.client('secretsmanager', region_name=self.region)
                self.ssm_client = boto3.client('ssm', region_name=self.region)
                self.logger.info("AWS Secrets Manager and SSM clients initialized")
            else:
                self.logger.info("Not in AWS environment, using local configuration")
        except (NoCredentialsError, ClientError) as e:
            self.logger.warning(f"Could not initialize AWS clients: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error initializing AWS clients: {e}")
    
    def _is_aws_environment(self) -> bool:
        """Check if running in AWS environment."""
        # Check for ECS metadata endpoint
        if os.environ.get('ECS_CONTAINER_METADATA_URI_V4'):
            return True
        
        # Check for EC2 metadata endpoint
        try:
            import requests
            response = requests.get(
                'http://169.254.169.254/latest/meta-data/instance-id',
                timeout=2
            )
            return response.status_code == 200
        except:
            pass
        
        # Check for Lambda environment
        if os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
            return True
        
        # Check for explicit AWS environment variable
        if os.environ.get('AWS_ENVIRONMENT') == 'true':
            return True
        
        return False
    
    def get_secret(self, secret_name: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Retrieve a secret from AWS Secrets Manager.
        
        Args:
            secret_name: Name of the secret to retrieve
            use_cache: Whether to use cached values
            
        Returns:
            Dictionary containing secret values or None if not found
        """
        if not self.secrets_client:
            return self._get_local_secret(secret_name)
        
        # Check cache first
        if use_cache and secret_name in self._secrets_cache:
            cached_secret = self._secrets_cache[secret_name]
            if self._is_cache_valid(cached_secret):
                self.logger.debug(f"Using cached secret: {secret_name}")
                return cached_secret['value']
        
        try:
            # Construct full secret name
            full_secret_name = f"{self.project_name}/{self.environment}/{secret_name}"
            
            response = self.secrets_client.get_secret_value(SecretId=full_secret_name)
            secret_value = json.loads(response['SecretString'])
            
            # Cache the secret
            if use_cache:
                self._secrets_cache[secret_name] = {
                    'value': secret_value,
                    'timestamp': self._get_current_timestamp()
                }
            
            self.logger.debug(f"Retrieved secret from AWS: {secret_name}")
            return secret_value
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                self.logger.warning(f"Secret not found: {secret_name}")
            elif error_code == 'InvalidRequestException':
                self.logger.error(f"Invalid request for secret: {secret_name}")
            elif error_code == 'InvalidParameterException':
                self.logger.error(f"Invalid parameter for secret: {secret_name}")
            else:
                self.logger.error(f"Error retrieving secret {secret_name}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error retrieving secret {secret_name}: {e}")
            return None
    
    def _get_local_secret(self, secret_name: str) -> Optional[Dict[str, Any]]:
        """Fallback to local environment variables when not in AWS."""
        self.logger.debug(f"Using local environment for secret: {secret_name}")
        
        if secret_name == 'database':
            return {
                'username': os.getenv('DB_USER', 'postgres'),
                'password': os.getenv('DB_PASSWORD', 'password'),
                'host': os.getenv('DB_HOST', 'localhost'),
                'port': int(os.getenv('DB_PORT', '5432')),
                'dbname': os.getenv('DB_NAME', 'multimodal_librarian'),
                'engine': 'postgres'
            }
        elif secret_name == 'api-keys':
            return {
                'gemini_api_key': os.getenv('GEMINI_API_KEY', ''),
                'openai_api_key': os.getenv('OPENAI_API_KEY', ''),
                'google_api_key': os.getenv('GOOGLE_API_KEY', '')
            }
        elif secret_name == 'redis':
            return {
                'username': os.getenv('REDIS_USER', 'redis'),
                'auth_token': os.getenv('REDIS_PASSWORD', ''),
                'host': os.getenv('REDIS_HOST', 'localhost'),
                'port': int(os.getenv('REDIS_PORT', '6379'))
            }
        else:
            self.logger.warning(f"Unknown secret name: {secret_name}")
            return None
    
    def get_parameter(self, parameter_name: str, use_cache: bool = True) -> Optional[str]:
        """
        Retrieve a parameter from AWS Systems Manager Parameter Store.
        
        Args:
            parameter_name: Name of the parameter to retrieve
            use_cache: Whether to use cached values
            
        Returns:
            Parameter value as string or None if not found
        """
        if not self.ssm_client:
            return self._get_local_parameter(parameter_name)
        
        # Check cache first
        cache_key = f"param_{parameter_name}"
        if use_cache and cache_key in self._secrets_cache:
            cached_param = self._secrets_cache[cache_key]
            if self._is_cache_valid(cached_param):
                self.logger.debug(f"Using cached parameter: {parameter_name}")
                return cached_param['value']
        
        try:
            # Construct full parameter name
            full_param_name = f"/{self.project_name}/{self.environment}/{parameter_name}"
            
            response = self.ssm_client.get_parameter(
                Name=full_param_name,
                WithDecryption=True
            )
            param_value = response['Parameter']['Value']
            
            # Cache the parameter
            if use_cache:
                self._secrets_cache[cache_key] = {
                    'value': param_value,
                    'timestamp': self._get_current_timestamp()
                }
            
            self.logger.debug(f"Retrieved parameter from AWS: {parameter_name}")
            return param_value
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ParameterNotFound':
                self.logger.warning(f"Parameter not found: {parameter_name}")
            else:
                self.logger.error(f"Error retrieving parameter {parameter_name}: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error retrieving parameter {parameter_name}: {e}")
            return None
    
    def _get_local_parameter(self, parameter_name: str) -> Optional[str]:
        """Fallback to local environment variables for parameters."""
        self.logger.debug(f"Using local environment for parameter: {parameter_name}")
        
        # Map parameter names to environment variables
        param_mapping = {
            'app/debug': 'DEBUG',
            'app/log_level': 'LOG_LEVEL',
            'app/max_workers': 'MAX_WORKERS',
            'app/timeout': 'REQUEST_TIMEOUT',
            'ml/batch_size': 'ML_BATCH_SIZE',
            'ml/model_path': 'ML_MODEL_PATH',
            'chat/max_connections': 'MAX_WEBSOCKET_CONNECTIONS',
            'chat/message_limit': 'CHAT_MESSAGE_LIMIT'
        }
        
        env_var = param_mapping.get(parameter_name)
        if env_var:
            return os.getenv(env_var)
        else:
            # Try direct environment variable lookup
            env_name = parameter_name.upper().replace('/', '_')
            return os.getenv(env_name)
    
    def put_secret(self, secret_name: str, secret_value: Dict[str, Any]) -> bool:
        """
        Store or update a secret in AWS Secrets Manager.
        
        Args:
            secret_name: Name of the secret to store
            secret_value: Dictionary containing secret values
            
        Returns:
            True if successful, False otherwise
        """
        if not self.secrets_client:
            self.logger.warning("Cannot store secret: not in AWS environment")
            return False
        
        try:
            # Construct full secret name
            full_secret_name = f"{self.project_name}/{self.environment}/{secret_name}"
            
            # Try to update existing secret first
            try:
                self.secrets_client.update_secret(
                    SecretId=full_secret_name,
                    SecretString=json.dumps(secret_value)
                )
                self.logger.info(f"Updated existing secret: {secret_name}")
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    # Secret doesn't exist, create it
                    self.secrets_client.create_secret(
                        Name=full_secret_name,
                        SecretString=json.dumps(secret_value),
                        Description=f"Secret for {secret_name} in {self.environment} environment"
                    )
                    self.logger.info(f"Created new secret: {secret_name}")
                else:
                    raise
            
            # Clear cache for this secret
            if secret_name in self._secrets_cache:
                del self._secrets_cache[secret_name]
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error storing secret {secret_name}: {e}")
            return False
    
    def put_parameter(self, parameter_name: str, parameter_value: str, 
                     parameter_type: str = 'String', secure: bool = False) -> bool:
        """
        Store or update a parameter in AWS Systems Manager Parameter Store.
        
        Args:
            parameter_name: Name of the parameter to store
            parameter_value: Value of the parameter
            parameter_type: Type of parameter (String, StringList, SecureString)
            secure: Whether to use SecureString type
            
        Returns:
            True if successful, False otherwise
        """
        if not self.ssm_client:
            self.logger.warning("Cannot store parameter: not in AWS environment")
            return False
        
        try:
            # Construct full parameter name
            full_param_name = f"/{self.project_name}/{self.environment}/{parameter_name}"
            
            # Determine parameter type
            if secure:
                param_type = 'SecureString'
            else:
                param_type = parameter_type
            
            self.ssm_client.put_parameter(
                Name=full_param_name,
                Value=parameter_value,
                Type=param_type,
                Overwrite=True,
                Description=f"Parameter for {parameter_name} in {self.environment} environment"
            )
            
            # Clear cache for this parameter
            cache_key = f"param_{parameter_name}"
            if cache_key in self._secrets_cache:
                del self._secrets_cache[cache_key]
            
            self.logger.info(f"Stored parameter: {parameter_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error storing parameter {parameter_name}: {e}")
            return False
    
    def _is_cache_valid(self, cached_item: Dict[str, Any]) -> bool:
        """Check if cached item is still valid."""
        current_time = self._get_current_timestamp()
        return (current_time - cached_item['timestamp']) < self._cache_ttl
    
    def _get_current_timestamp(self) -> float:
        """Get current timestamp."""
        import time
        return time.time()
    
    def clear_cache(self):
        """Clear the secrets cache."""
        self._secrets_cache.clear()
        self.logger.info("Secrets cache cleared")
    
    def get_database_config(self) -> Optional[Dict[str, Any]]:
        """Get database configuration from secrets."""
        return self.get_secret('database')
    
    def get_api_keys(self) -> Optional[Dict[str, str]]:
        """Get API keys from secrets."""
        return self.get_secret('api-keys')
    
    def get_redis_config(self) -> Optional[Dict[str, Any]]:
        """Get Redis configuration from secrets."""
        return self.get_secret('redis')
    
    def get_app_config(self) -> Dict[str, Any]:
        """Get application configuration from parameters."""
        config = {}
        
        # Application settings
        config['debug'] = self.get_parameter('app/debug') == 'true'
        config['log_level'] = self.get_parameter('app/log_level') or 'INFO'
        config['max_workers'] = int(self.get_parameter('app/max_workers') or '4')
        config['timeout'] = int(self.get_parameter('app/timeout') or '30')
        
        # ML settings
        config['ml_batch_size'] = int(self.get_parameter('ml/batch_size') or '32')
        config['ml_model_path'] = self.get_parameter('ml/model_path') or '/models'
        
        # Chat settings
        config['max_connections'] = int(self.get_parameter('chat/max_connections') or '100')
        config['message_limit'] = int(self.get_parameter('chat/message_limit') or '1000')
        
        return config
    
    def validate_secrets(self) -> Dict[str, bool]:
        """Validate that all required secrets are available."""
        validation_results = {}
        
        # Check database secret
        db_config = self.get_database_config()
        validation_results['database'] = db_config is not None and all(
            key in db_config for key in ['username', 'password', 'host', 'port', 'dbname']
        )
        
        # Check API keys secret
        api_keys = self.get_api_keys()
        validation_results['api_keys'] = api_keys is not None and any(
            api_keys.get(key) for key in ['gemini_api_key', 'openai_api_key', 'google_api_key']
        )
        
        # Check Redis secret
        redis_config = self.get_redis_config()
        validation_results['redis'] = redis_config is not None and all(
            key in redis_config for key in ['host', 'port']
        )
        
        return validation_results


# Global secrets manager instance
_secrets_manager = None

@lru_cache(maxsize=1)
def get_secrets_manager() -> SecretsManagerBasic:
    """Get the global secrets manager instance."""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManagerBasic()
    return _secrets_manager


# Convenience functions for common operations
def get_database_url() -> Optional[str]:
    """Get database URL from secrets."""
    secrets_manager = get_secrets_manager()
    db_config = secrets_manager.get_database_config()
    
    if not db_config:
        return None
    
    return (f"postgresql://{db_config['username']}:{db_config['password']}"
            f"@{db_config['host']}:{db_config['port']}/{db_config['dbname']}")


def get_redis_url() -> Optional[str]:
    """Get Redis URL from secrets."""
    secrets_manager = get_secrets_manager()
    redis_config = secrets_manager.get_redis_config()
    
    if not redis_config:
        return None
    
    auth_token = redis_config.get('auth_token', '')
    if auth_token:
        return f"redis://:{auth_token}@{redis_config['host']}:{redis_config['port']}/0"
    else:
        return f"redis://{redis_config['host']}:{redis_config['port']}/0"


def get_api_key(service: str) -> Optional[str]:
    """Get API key for a specific service."""
    secrets_manager = get_secrets_manager()
    api_keys = secrets_manager.get_api_keys()
    
    if not api_keys:
        return None
    
    key_mapping = {
        'gemini': 'gemini_api_key',
        'openai': 'openai_api_key',
        'google': 'google_api_key'
    }
    
    key_name = key_mapping.get(service.lower())
    if key_name:
        return api_keys.get(key_name)
    
    return None


# Configuration decorator for automatic secret injection
def inject_secrets(*secret_names):
    """Decorator to inject secrets as function arguments."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            secrets_manager = get_secrets_manager()
            
            for secret_name in secret_names:
                if secret_name not in kwargs:
                    secret_value = secrets_manager.get_secret(secret_name)
                    if secret_value:
                        kwargs[secret_name] = secret_value
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


# Configuration validation decorator
def validate_secrets_required(*required_secrets):
    """Decorator to validate that required secrets are available."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            secrets_manager = get_secrets_manager()
            validation_results = secrets_manager.validate_secrets()
            
            missing_secrets = [
                secret for secret in required_secrets 
                if not validation_results.get(secret, False)
            ]
            
            if missing_secrets:
                raise ValueError(f"Missing required secrets: {missing_secrets}")
            
            return func(*args, **kwargs)
        return wrapper
    return decorator