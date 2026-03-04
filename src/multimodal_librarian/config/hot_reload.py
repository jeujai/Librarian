"""
Configuration Hot Reloading Module

This module provides hot configuration reloading capabilities to avoid service restarts
during configuration updates. It integrates with AWS Secrets Manager and Parameter Store
to dynamically reload configuration changes.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional, Callable
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class ConfigHotReloader:
    """
    Hot configuration reloader that monitors AWS Secrets Manager and Parameter Store
    for configuration changes and applies them without service restart.
    """
    
    def __init__(
        self,
        project_name: str = "multimodal-librarian",
        environment: str = "learning",
        region: str = "us-east-1",
        check_interval: int = 30,
    ):
        self.project_name = project_name
        self.environment = environment
        self.region = region
        self.check_interval = check_interval
        
        # AWS clients
        self.secrets_client = boto3.client('secretsmanager', region_name=region)
        self.ssm_client = boto3.client('ssm', region_name=region)
        
        # Configuration cache
        self.config_cache: Dict[str, Any] = {}
        self.last_updated: Dict[str, datetime] = {}
        self.config_callbacks: Dict[str, Callable] = {}
        
        # Control flags
        self.running = False
        self.reload_task: Optional[asyncio.Task] = None
        
        logger.info(f"ConfigHotReloader initialized for {project_name}-{environment}")
    
    def register_callback(self, config_key: str, callback: Callable[[Any], None]):
        """
        Register a callback function to be called when a specific configuration changes.
        
        Args:
            config_key: The configuration key to monitor
            callback: Function to call when config changes (receives new config value)
        """
        self.config_callbacks[config_key] = callback
        logger.info(f"Registered callback for config key: {config_key}")
    
    async def start(self):
        """Start the hot reloading service."""
        if self.running:
            logger.warning("ConfigHotReloader is already running")
            return
        
        self.running = True
        logger.info("Starting configuration hot reloading service")
        
        # Initial load
        await self.load_all_configs()
        
        # Start monitoring task
        self.reload_task = asyncio.create_task(self._monitor_configs())
    
    async def stop(self):
        """Stop the hot reloading service."""
        if not self.running:
            return
        
        self.running = False
        logger.info("Stopping configuration hot reloading service")
        
        if self.reload_task:
            self.reload_task.cancel()
            try:
                await self.reload_task
            except asyncio.CancelledError:
                pass
    
    async def load_all_configs(self):
        """Load all configurations from AWS services."""
        await asyncio.gather(
            self._load_secrets(),
            self._load_parameters(),
            return_exceptions=True
        )
    
    async def _load_secrets(self):
        """Load secrets from AWS Secrets Manager."""
        secret_names = [
            f"{self.project_name}/{self.environment}/api-keys",
            f"{self.project_name}/{self.environment}/database",
            f"{self.project_name}/{self.environment}/neo4j",
            f"{self.project_name}/{self.environment}/redis",
        ]
        
        for secret_name in secret_names:
            try:
                response = self.secrets_client.get_secret_value(SecretId=secret_name)
                secret_value = json.loads(response['SecretString'])
                
                # Check if configuration has changed
                if self._has_config_changed(secret_name, secret_value):
                    self.config_cache[secret_name] = secret_value
                    self.last_updated[secret_name] = datetime.utcnow()
                    
                    # Trigger callback if registered
                    if secret_name in self.config_callbacks:
                        try:
                            await self._safe_callback(secret_name, secret_value)
                        except Exception as e:
                            logger.error(f"Callback failed for {secret_name}: {e}")
                    
                    logger.info(f"Reloaded secret: {secret_name}")
                
            except ClientError as e:
                if e.response['Error']['Code'] == 'ResourceNotFoundException':
                    logger.warning(f"Secret not found: {secret_name}")
                else:
                    logger.error(f"Failed to load secret {secret_name}: {e}")
            except Exception as e:
                logger.error(f"Unexpected error loading secret {secret_name}: {e}")
    
    async def _load_parameters(self):
        """Load parameters from AWS Systems Manager Parameter Store."""
        parameter_prefix = f"/{self.project_name}/{self.environment}/"
        
        try:
            paginator = self.ssm_client.get_paginator('get_parameters_by_path')
            
            for page in paginator.paginate(
                Path=parameter_prefix,
                Recursive=True,
                WithDecryption=True
            ):
                for param in page.get('Parameters', []):
                    param_name = param['Name']
                    param_value = param['Value']
                    
                    # Try to parse as JSON, fallback to string
                    try:
                        param_value = json.loads(param_value)
                    except (json.JSONDecodeError, TypeError):
                        pass  # Keep as string
                    
                    # Check if configuration has changed
                    if self._has_config_changed(param_name, param_value):
                        self.config_cache[param_name] = param_value
                        self.last_updated[param_name] = datetime.utcnow()
                        
                        # Trigger callback if registered
                        if param_name in self.config_callbacks:
                            try:
                                await self._safe_callback(param_name, param_value)
                            except Exception as e:
                                logger.error(f"Callback failed for {param_name}: {e}")
                        
                        logger.info(f"Reloaded parameter: {param_name}")
        
        except ClientError as e:
            logger.error(f"Failed to load parameters: {e}")
        except Exception as e:
            logger.error(f"Unexpected error loading parameters: {e}")
    
    def _has_config_changed(self, key: str, new_value: Any) -> bool:
        """Check if configuration has changed."""
        if key not in self.config_cache:
            return True
        
        return self.config_cache[key] != new_value
    
    async def _safe_callback(self, key: str, value: Any):
        """Safely execute callback function."""
        callback = self.config_callbacks[key]
        
        if asyncio.iscoroutinefunction(callback):
            await callback(value)
        else:
            # Run sync callback in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, callback, value)
    
    async def _monitor_configs(self):
        """Monitor configurations for changes."""
        while self.running:
            try:
                await self.load_all_configs()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in config monitoring loop: {e}")
                await asyncio.sleep(self.check_interval)
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""
        return self.config_cache.get(key, default)
    
    def get_secret(self, secret_name: str, key: str = None, default: Any = None) -> Any:
        """
        Get secret value by secret name and optional key.
        
        Args:
            secret_name: Name of the secret (without project/environment prefix)
            key: Optional key within the secret JSON
            default: Default value if not found
        """
        full_secret_name = f"{self.project_name}/{self.environment}/{secret_name}"
        secret_data = self.config_cache.get(full_secret_name, {})
        
        if key:
            return secret_data.get(key, default)
        return secret_data if secret_data else default
    
    def get_parameter(self, param_name: str, default: Any = None) -> Any:
        """
        Get parameter value by parameter name.
        
        Args:
            param_name: Name of the parameter (without project/environment prefix)
            default: Default value if not found
        """
        full_param_name = f"/{self.project_name}/{self.environment}/{param_name}"
        return self.config_cache.get(full_param_name, default)
    
    def get_api_key(self, service: str, default: str = None) -> str:
        """
        Get API key for a specific service.
        
        Args:
            service: Service name (gemini, openai, google)
            default: Default value if not found
        """
        api_keys = self.get_secret("api-keys", default={})
        key_name = f"{service}_api_key"
        return api_keys.get(key_name, default)
    
    def get_database_config(self) -> Dict[str, Any]:
        """Get database configuration."""
        return self.get_secret("database", default={})
    
    def get_redis_config(self) -> Dict[str, Any]:
        """Get Redis configuration."""
        return self.get_secret("redis", default={})


# Global instance for easy access
_global_reloader: Optional[ConfigHotReloader] = None


def get_config_reloader() -> ConfigHotReloader:
    """Get the global configuration reloader instance."""
    global _global_reloader
    if _global_reloader is None:
        _global_reloader = ConfigHotReloader()
    return _global_reloader


async def initialize_config_reloader(
    project_name: str = "multimodal-librarian",
    environment: str = "learning",
    region: str = "us-east-1",
    check_interval: int = 30,
) -> ConfigHotReloader:
    """
    Initialize and start the global configuration reloader.
    
    Args:
        project_name: Project name
        environment: Environment name
        region: AWS region
        check_interval: Check interval in seconds
    
    Returns:
        ConfigHotReloader instance
    """
    global _global_reloader
    
    if _global_reloader is not None:
        await _global_reloader.stop()
    
    _global_reloader = ConfigHotReloader(
        project_name=project_name,
        environment=environment,
        region=region,
        check_interval=check_interval,
    )
    
    await _global_reloader.start()
    return _global_reloader


async def shutdown_config_reloader():
    """Shutdown the global configuration reloader."""
    global _global_reloader
    if _global_reloader is not None:
        await _global_reloader.stop()
        _global_reloader = None


# Example usage and integration helpers
class ConfigurableComponent:
    """
    Base class for components that support hot configuration reloading.
    """
    
    def __init__(self, config_key: str):
        self.config_key = config_key
        self.reloader = get_config_reloader()
        self.reloader.register_callback(config_key, self._on_config_change)
    
    async def _on_config_change(self, new_config: Any):
        """Override this method to handle configuration changes."""
        logger.info(f"Configuration changed for {self.config_key}: {new_config}")
        await self.reload_config(new_config)
    
    async def reload_config(self, new_config: Any):
        """Override this method to implement configuration reloading logic."""
        pass


# Example integration with existing components
async def setup_ml_training_config_reload():
    """Example of setting up config reload for ML training components."""
    reloader = get_config_reloader()
    
    async def on_api_keys_change(new_keys: Dict[str, str]):
        """Handle API key changes for ML training."""
        logger.info("API keys updated, refreshing ML training clients")
        # Here you would update your ML training clients with new API keys
        # This avoids the need to restart the service
    
    reloader.register_callback(
        f"{reloader.project_name}/{reloader.environment}/api-keys",
        on_api_keys_change
    )


async def setup_database_config_reload():
    """Example of setting up config reload for database connections."""
    reloader = get_config_reloader()
    
    async def on_database_config_change(new_config: Dict[str, Any]):
        """Handle database configuration changes."""
        logger.info("Database configuration updated")
        # Here you would update connection pools, etc.
        # This allows for connection string updates without restart
    
    reloader.register_callback(
        f"{reloader.project_name}/{reloader.environment}/database",
        on_database_config_change
    )