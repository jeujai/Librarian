"""
Configuration management module for Multimodal Librarian.

This module provides configuration management capabilities including
hot reloading from AWS Secrets Manager and Parameter Store, and
environment switching for local development.
"""

from .config import (
    Settings, 
    get_settings, 
    reload_settings,
    get_environment_type,
    is_local_development,
    is_aws_production,
    validate_environment_configuration
)
from .hot_reload import (
    ConfigHotReloader,
    get_config_reloader,
    initialize_config_reloader,
    shutdown_config_reloader,
    ConfigurableComponent,
)

__all__ = [
    'Settings',
    'get_settings',
    'reload_settings',
    'get_environment_type',
    'is_local_development',
    'is_aws_production',
    'validate_environment_configuration',
    'ConfigHotReloader',
    'get_config_reloader',
    'initialize_config_reloader',
    'shutdown_config_reloader',
    'ConfigurableComponent',
]