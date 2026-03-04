"""
Query Performance Monitoring Configuration

This module provides configuration classes and utilities for query performance
monitoring in the local development environment. It integrates with the existing
configuration system and provides environment-specific settings.

The configuration supports different monitoring levels, thresholds, and
integration options for various database types.

Example Usage:
    ```python
    from multimodal_librarian.config.query_performance_config import QueryPerformanceConfig
    
    # Load configuration
    config = QueryPerformanceConfig()
    
    # Initialize monitoring with config
    monitor = QueryPerformanceMonitor(
        slow_query_threshold_ms=config.slow_query_threshold_ms,
        high_cpu_threshold=config.high_cpu_threshold,
        high_memory_threshold_mb=config.high_memory_threshold_mb
    )
    ```

Integration with Local Config:
    The query performance configuration integrates with the existing
    LocalDatabaseConfig to provide database-specific monitoring settings.
"""

import os
from typing import Dict, List, Optional, Any, Literal
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from dataclasses import dataclass
from enum import Enum


class MonitoringLevel(str, Enum):
    """Monitoring levels for query performance."""
    DISABLED = "disabled"
    BASIC = "basic"
    DETAILED = "detailed"
    COMPREHENSIVE = "comprehensive"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class DatabaseMonitoringConfig:
    """Configuration for monitoring a specific database type."""
    enabled: bool = True
    monitoring_level: MonitoringLevel = MonitoringLevel.DETAILED
    slow_query_threshold_ms: float = 1000.0
    very_slow_query_threshold_ms: float = 5000.0
    high_cpu_threshold: float = 80.0
    high_memory_threshold_mb: float = 1000.0
    error_rate_threshold: float = 0.05  # 5% error rate
    
    # Database-specific settings
    track_query_plans: bool = False
    track_index_usage: bool = True
    track_resource_usage: bool = True
    
    # Sampling settings
    sample_rate: float = 1.0  # 100% sampling by default
    sample_slow_queries_only: bool = False


class QueryPerformanceConfig(BaseSettings):
    """
    Configuration for query performance monitoring.
    
    This configuration class provides comprehensive settings for monitoring
    query performance across all database types in the local development
    environment.
    """
    
    # Global monitoring settings
    monitoring_enabled: bool = Field(
        default=True,
        description="Enable query performance monitoring globally"
    )
    
    monitoring_level: MonitoringLevel = Field(
        default=MonitoringLevel.DETAILED,
        description="Global monitoring level"
    )
    
    # Global thresholds
    slow_query_threshold_ms: float = Field(
        default=1000.0,
        description="Global slow query threshold in milliseconds"
    )
    
    very_slow_query_threshold_ms: float = Field(
        default=5000.0,
        description="Very slow query threshold in milliseconds"
    )
    
    high_cpu_threshold: float = Field(
        default=80.0,
        description="High CPU usage threshold percentage"
    )
    
    high_memory_threshold_mb: float = Field(
        default=1000.0,
        description="High memory usage threshold in MB"
    )
    
    error_rate_threshold: float = Field(
        default=0.05,
        description="Error rate threshold (0.05 = 5%)"
    )
    
    # Data retention settings
    max_metrics_history: int = Field(
        default=10000,
        description="Maximum number of query metrics to keep in memory"
    )
    
    stats_window_minutes: int = Field(
        default=60,
        description="Time window for statistics calculation in minutes"
    )
    
    alert_retention_hours: int = Field(
        default=6,
        description="How long to keep performance alerts in hours"
    )
    
    metrics_retention_hours: int = Field(
        default=24,
        description="How long to keep detailed metrics in hours"
    )
    
    # Monitoring behavior
    auto_start_monitoring: bool = Field(
        default=True,
        description="Automatically start monitoring when clients connect"
    )
    
    track_all_queries: bool = Field(
        default=True,
        description="Track all queries or only slow ones"
    )
    
    track_resource_usage: bool = Field(
        default=True,
        description="Track CPU and memory usage during queries"
    )
    
    track_query_plans: bool = Field(
        default=False,
        description="Track query execution plans (may impact performance)"
    )
    
    # Sampling settings
    sample_rate: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Sampling rate for query monitoring (0.0-1.0)"
    )
    
    sample_slow_queries_only: bool = Field(
        default=False,
        description="Only sample slow queries to reduce overhead"
    )
    
    # Database-specific settings
    postgresql_config: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "monitoring_level": "detailed",
            "slow_query_threshold_ms": 1000.0,
            "track_query_plans": False,
            "track_index_usage": True
        },
        description="PostgreSQL-specific monitoring configuration"
    )
    
    neo4j_config: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "monitoring_level": "detailed",
            "slow_query_threshold_ms": 2000.0,  # Graph queries can be slower
            "track_query_plans": True,  # Cypher PROFILE is useful
            "track_index_usage": True
        },
        description="Neo4j-specific monitoring configuration"
    )
    
    milvus_config: Dict[str, Any] = Field(
        default_factory=lambda: {
            "enabled": True,
            "monitoring_level": "detailed",
            "slow_query_threshold_ms": 500.0,  # Vector searches should be fast
            "track_query_plans": False,
            "track_index_usage": True
        },
        description="Milvus-specific monitoring configuration"
    )
    
    # Alert settings
    enable_alerts: bool = Field(
        default=True,
        description="Enable performance alerts"
    )
    
    alert_cooldown_minutes: int = Field(
        default=5,
        description="Cooldown period between similar alerts in minutes"
    )
    
    alert_channels: List[str] = Field(
        default_factory=lambda: ["log"],
        description="Alert channels (log, webhook, email, etc.)"
    )
    
    webhook_url: Optional[str] = Field(
        default=None,
        description="Webhook URL for alert notifications"
    )
    
    # Export settings
    enable_metrics_export: bool = Field(
        default=False,
        description="Enable automatic metrics export"
    )
    
    export_interval_minutes: int = Field(
        default=60,
        description="Interval for automatic metrics export in minutes"
    )
    
    export_format: Literal["json", "csv", "prometheus"] = Field(
        default="json",
        description="Format for metrics export"
    )
    
    export_directory: str = Field(
        default="./monitoring/exports",
        description="Directory for metrics export files"
    )
    
    # Integration settings
    integrate_with_startup_metrics: bool = Field(
        default=True,
        description="Integrate with existing startup metrics system"
    )
    
    integrate_with_health_checks: bool = Field(
        default=True,
        description="Integrate with health check system"
    )
    
    auto_wrap_clients: bool = Field(
        default=True,
        description="Automatically wrap database clients with monitoring"
    )
    
    # Development settings
    debug_monitoring: bool = Field(
        default=False,
        description="Enable debug logging for monitoring system"
    )
    
    log_all_queries: bool = Field(
        default=False,
        description="Log all queries (useful for debugging, may impact performance)"
    )
    
    log_slow_queries: bool = Field(
        default=True,
        description="Log slow queries for analysis"
    )
    
    class Config:
        env_file = ".env.local"
        env_prefix = "QUERY_PERF_"
        case_sensitive = False
        extra = "ignore"  # Ignore extra fields from environment
    
    @field_validator("sample_rate")
    @classmethod
    def validate_sample_rate(cls, v):
        """Validate sample rate is between 0 and 1."""
        if not 0.0 <= v <= 1.0:
            raise ValueError("Sample rate must be between 0.0 and 1.0")
        return v
    
    @field_validator("monitoring_level")
    @classmethod
    def validate_monitoring_level(cls, v):
        """Validate monitoring level."""
        if isinstance(v, str):
            try:
                return MonitoringLevel(v.lower())
            except ValueError:
                raise ValueError(f"Invalid monitoring level: {v}")
        return v
    
    def get_database_config(self, database_type: str) -> DatabaseMonitoringConfig:
        """
        Get monitoring configuration for a specific database type.
        
        Args:
            database_type: Database type (postgresql, neo4j, milvus)
            
        Returns:
            Database-specific monitoring configuration
        """
        # Get the appropriate config dict
        if database_type.lower() == "postgresql":
            config_dict = self.postgresql_config
        elif database_type.lower() == "neo4j":
            config_dict = self.neo4j_config
        elif database_type.lower() == "milvus":
            config_dict = self.milvus_config
        else:
            # Default configuration
            config_dict = {
                "enabled": self.monitoring_enabled,
                "monitoring_level": self.monitoring_level.value,
                "slow_query_threshold_ms": self.slow_query_threshold_ms
            }
        
        # Create DatabaseMonitoringConfig with fallbacks to global settings
        return DatabaseMonitoringConfig(
            enabled=config_dict.get("enabled", self.monitoring_enabled),
            monitoring_level=MonitoringLevel(
                config_dict.get("monitoring_level", self.monitoring_level.value)
            ),
            slow_query_threshold_ms=config_dict.get(
                "slow_query_threshold_ms", self.slow_query_threshold_ms
            ),
            very_slow_query_threshold_ms=config_dict.get(
                "very_slow_query_threshold_ms", self.very_slow_query_threshold_ms
            ),
            high_cpu_threshold=config_dict.get(
                "high_cpu_threshold", self.high_cpu_threshold
            ),
            high_memory_threshold_mb=config_dict.get(
                "high_memory_threshold_mb", self.high_memory_threshold_mb
            ),
            error_rate_threshold=config_dict.get(
                "error_rate_threshold", self.error_rate_threshold
            ),
            track_query_plans=config_dict.get(
                "track_query_plans", self.track_query_plans
            ),
            track_index_usage=config_dict.get(
                "track_index_usage", True
            ),
            track_resource_usage=config_dict.get(
                "track_resource_usage", self.track_resource_usage
            ),
            sample_rate=config_dict.get("sample_rate", self.sample_rate),
            sample_slow_queries_only=config_dict.get(
                "sample_slow_queries_only", self.sample_slow_queries_only
            )
        )
    
    def should_monitor_database(self, database_type: str) -> bool:
        """
        Check if monitoring is enabled for a specific database type.
        
        Args:
            database_type: Database type to check
            
        Returns:
            True if monitoring is enabled for this database type
        """
        if not self.monitoring_enabled:
            return False
        
        db_config = self.get_database_config(database_type)
        return db_config.enabled
    
    def get_monitoring_level(self, database_type: str) -> MonitoringLevel:
        """
        Get monitoring level for a specific database type.
        
        Args:
            database_type: Database type
            
        Returns:
            Monitoring level for the database type
        """
        db_config = self.get_database_config(database_type)
        return db_config.monitoring_level
    
    def should_sample_query(self, database_type: str, is_slow_query: bool = False) -> bool:
        """
        Determine if a query should be sampled for monitoring.
        
        Args:
            database_type: Database type
            is_slow_query: Whether this is a slow query
            
        Returns:
            True if the query should be monitored
        """
        if not self.should_monitor_database(database_type):
            return False
        
        db_config = self.get_database_config(database_type)
        
        # Always sample slow queries if slow-query-only sampling is enabled
        if db_config.sample_slow_queries_only and is_slow_query:
            return True
        
        # Skip non-slow queries if slow-query-only sampling is enabled
        if db_config.sample_slow_queries_only and not is_slow_query:
            return False
        
        # Apply sampling rate
        import random
        return random.random() < db_config.sample_rate
    
    def get_alert_settings(self) -> Dict[str, Any]:
        """Get alert configuration settings."""
        return {
            "enabled": self.enable_alerts,
            "cooldown_minutes": self.alert_cooldown_minutes,
            "channels": self.alert_channels,
            "webhook_url": self.webhook_url,
            "retention_hours": self.alert_retention_hours
        }
    
    def get_export_settings(self) -> Dict[str, Any]:
        """Get metrics export configuration settings."""
        return {
            "enabled": self.enable_metrics_export,
            "interval_minutes": self.export_interval_minutes,
            "format": self.export_format,
            "directory": self.export_directory
        }
    
    def to_monitor_kwargs(self) -> Dict[str, Any]:
        """
        Convert configuration to QueryPerformanceMonitor constructor arguments.
        
        Returns:
            Dictionary of arguments for QueryPerformanceMonitor constructor
        """
        return {
            "slow_query_threshold_ms": self.slow_query_threshold_ms,
            "high_cpu_threshold": self.high_cpu_threshold,
            "high_memory_threshold_mb": self.high_memory_threshold_mb,
            "max_metrics_history": self.max_metrics_history,
            "stats_window_minutes": self.stats_window_minutes
        }


class QueryPerformanceConfigFactory:
    """
    Factory for creating query performance configurations.
    
    This factory provides different configuration presets for various
    development scenarios and environments.
    """
    
    @staticmethod
    def create_development_config() -> QueryPerformanceConfig:
        """Create configuration optimized for development."""
        return QueryPerformanceConfig(
            monitoring_enabled=True,
            monitoring_level=MonitoringLevel.DETAILED,
            slow_query_threshold_ms=1000.0,
            track_resource_usage=True,
            track_query_plans=False,  # Avoid performance impact
            sample_rate=1.0,  # Monitor all queries in development
            enable_alerts=True,
            alert_channels=["log"],
            debug_monitoring=True,
            log_slow_queries=True
        )
    
    @staticmethod
    def create_testing_config() -> QueryPerformanceConfig:
        """Create configuration optimized for testing."""
        return QueryPerformanceConfig(
            monitoring_enabled=True,
            monitoring_level=MonitoringLevel.BASIC,
            slow_query_threshold_ms=2000.0,  # More lenient for tests
            track_resource_usage=False,  # Reduce overhead
            track_query_plans=False,
            sample_rate=0.1,  # Sample 10% of queries
            enable_alerts=False,  # No alerts during tests
            debug_monitoring=False,
            log_slow_queries=False
        )
    
    @staticmethod
    def create_performance_testing_config() -> QueryPerformanceConfig:
        """Create configuration optimized for performance testing."""
        return QueryPerformanceConfig(
            monitoring_enabled=True,
            monitoring_level=MonitoringLevel.COMPREHENSIVE,
            slow_query_threshold_ms=500.0,  # Strict thresholds
            track_resource_usage=True,
            track_query_plans=True,  # Detailed analysis
            sample_rate=1.0,  # Monitor everything
            enable_alerts=True,
            enable_metrics_export=True,
            export_interval_minutes=5,  # Frequent exports
            debug_monitoring=True
        )
    
    @staticmethod
    def create_minimal_config() -> QueryPerformanceConfig:
        """Create minimal configuration with low overhead."""
        return QueryPerformanceConfig(
            monitoring_enabled=True,
            monitoring_level=MonitoringLevel.BASIC,
            slow_query_threshold_ms=5000.0,  # Only very slow queries
            track_resource_usage=False,
            track_query_plans=False,
            sample_rate=0.01,  # Sample 1% of queries
            sample_slow_queries_only=True,
            enable_alerts=False,
            debug_monitoring=False,
            max_metrics_history=1000  # Smaller history
        )
    
    @staticmethod
    def create_disabled_config() -> QueryPerformanceConfig:
        """Create configuration with monitoring disabled."""
        return QueryPerformanceConfig(
            monitoring_enabled=False,
            monitoring_level=MonitoringLevel.DISABLED,
            enable_alerts=False,
            enable_metrics_export=False,
            debug_monitoring=False
        )
    
    @staticmethod
    def from_environment() -> QueryPerformanceConfig:
        """Create configuration from environment variables."""
        return QueryPerformanceConfig()
    
    @staticmethod
    def from_dict(config_dict: Dict[str, Any]) -> QueryPerformanceConfig:
        """Create configuration from dictionary."""
        return QueryPerformanceConfig(**config_dict)


def get_query_performance_config(
    environment: Optional[str] = None,
    config_override: Optional[Dict[str, Any]] = None
) -> QueryPerformanceConfig:
    """
    Get query performance configuration for the current environment.
    
    Args:
        environment: Environment name (development, testing, performance, minimal)
        config_override: Optional configuration overrides
        
    Returns:
        Query performance configuration
    """
    # Determine environment
    if environment is None:
        environment = os.getenv("ML_ENVIRONMENT", "development").lower()
    
    # Create base configuration
    if environment == "testing":
        config = QueryPerformanceConfigFactory.create_testing_config()
    elif environment == "performance":
        config = QueryPerformanceConfigFactory.create_performance_testing_config()
    elif environment == "minimal":
        config = QueryPerformanceConfigFactory.create_minimal_config()
    elif environment == "disabled":
        config = QueryPerformanceConfigFactory.create_disabled_config()
    else:
        # Default to development
        config = QueryPerformanceConfigFactory.create_development_config()
    
    # Apply overrides if provided
    if config_override:
        for key, value in config_override.items():
            if hasattr(config, key):
                setattr(config, key, value)
    
    return config


# Default configuration instance
default_config = QueryPerformanceConfigFactory.from_environment()