"""
Cold Start Configuration for Multimodal Librarian

This module provides configuration optimizations specifically for
minimizing cold start times in local development environments.
"""

import os
from typing import Dict, Any, Optional
from pydantic import BaseSettings, Field


class ColdStartConfig(BaseSettings):
    """Configuration optimized for cold start performance."""
    
    # Cold start mode flag
    cold_start_optimization: bool = Field(
        default=False,
        env="COLD_START_OPTIMIZATION",
        description="Enable cold start optimizations"
    )
    
    # Startup mode
    startup_mode: str = Field(
        default="normal",
        env="STARTUP_MODE",
        description="Startup mode: fast, normal, full"
    )
    
    # Lazy loading settings
    lazy_load_models: bool = Field(
        default=True,
        env="LAZY_LOAD_MODELS",
        description="Enable lazy loading of ML models"
    )
    
    lazy_load_services: bool = Field(
        default=True,
        env="LAZY_LOAD_SERVICES",
        description="Enable lazy loading of services"
    )
    
    # Connection pool optimizations
    min_connection_pool_size: int = Field(
        default=2,
        env="MIN_CONNECTION_POOL_SIZE",
        description="Minimum connection pool size for cold start"
    )
    
    max_connection_pool_size: int = Field(
        default=10,
        env="MAX_CONNECTION_POOL_SIZE",
        description="Maximum connection pool size for cold start"
    )
    
    # Health check optimizations
    fast_health_checks: bool = Field(
        default=True,
        env="FAST_HEALTH_CHECKS",
        description="Enable fast health checks during startup"
    )
    
    health_check_timeout: float = Field(
        default=2.0,
        env="HEALTH_CHECK_TIMEOUT",
        description="Health check timeout in seconds"
    )
    
    # Background initialization
    background_init_enabled: bool = Field(
        default=True,
        env="BACKGROUND_INIT_ENABLED",
        description="Enable background initialization"
    )
    
    background_init_delay: float = Field(
        default=1.0,
        env="BACKGROUND_INIT_DELAY",
        description="Delay before starting background initialization"
    )
    
    # Model loading priorities
    essential_models: list = Field(
        default_factory=lambda: [
            "sentence-transformers/all-MiniLM-L6-v2"
        ],
        description="Essential models to load first"
    )
    
    deferred_models: list = Field(
        default_factory=lambda: [
            "spacy/en_core_web_sm"
        ],
        description="Models to load in background"
    )
    
    # Service startup priorities
    critical_services: list = Field(
        default_factory=lambda: [
            "health_check",
            "basic_api"
        ],
        description="Critical services to start first"
    )
    
    deferred_services: list = Field(
        default_factory=lambda: [
            "vector_search",
            "knowledge_graph",
            "ai_chat"
        ],
        description="Services to start in background"
    )
    
    class Config:
        env_file = ".env.local"
        env_prefix = "ML_"


def get_cold_start_config() -> ColdStartConfig:
    """Get cold start configuration."""
    return ColdStartConfig()


def is_cold_start_mode() -> bool:
    """Check if cold start optimization is enabled."""
    config = get_cold_start_config()
    return config.cold_start_optimization


def get_startup_priorities() -> Dict[str, Any]:
    """Get startup priorities for cold start optimization."""
    config = get_cold_start_config()
    
    return {
        "essential_models": config.essential_models,
        "deferred_models": config.deferred_models,
        "critical_services": config.critical_services,
        "deferred_services": config.deferred_services,
        "lazy_loading": {
            "models": config.lazy_load_models,
            "services": config.lazy_load_services
        },
        "connection_pools": {
            "min_size": config.min_connection_pool_size,
            "max_size": config.max_connection_pool_size
        },
        "health_checks": {
            "fast_mode": config.fast_health_checks,
            "timeout": config.health_check_timeout
        },
        "background_init": {
            "enabled": config.background_init_enabled,
            "delay": config.background_init_delay
        }
    }
