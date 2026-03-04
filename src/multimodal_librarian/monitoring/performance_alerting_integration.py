"""
Performance Alerting Integration

This module provides integration between the local performance alerting system
and the main application. It handles initialization, configuration, and lifecycle
management of performance alerting in the local development environment.

Features:
- Automatic initialization of performance alerting
- Integration with existing monitoring infrastructure
- Configuration management for alert thresholds
- Lifecycle management (startup/shutdown)
- Health check integration
"""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime

from .local_performance_alerting import (
    LocalPerformanceAlerting,
    PerformanceAlertType,
    PerformanceThreshold,
    PerformanceAlertRule,
    get_local_performance_alerting,
    start_local_performance_alerting,
    stop_local_performance_alerting
)
from .performance_tracker import PerformanceTracker
from .local_performance_metrics import LocalPerformanceMetricsCollector
from .query_performance_monitor import QueryPerformanceMonitor
from .local_alerting_system import get_local_alerting_system
from ..config.local_config import LocalDatabaseConfig
from ..clients.database_factory import DatabaseClientFactory
from ..logging_config import get_logger

logger = get_logger("performance_alerting_integration")


class PerformanceAlertingIntegration:
    """
    Integration manager for performance alerting in local development.
    
    This class manages the lifecycle and configuration of performance alerting,
    ensuring proper integration with the existing monitoring infrastructure.
    """
    
    def __init__(self, config: Optional[LocalDatabaseConfig] = None):
        self.config = config or LocalDatabaseConfig()
        self.logger = get_logger("performance_alerting_integration")
        
        # Integration state
        self._integration_active = False
        self._initialization_task: Optional[asyncio.Task] = None
        
        # Component references
        self._performance_alerting: Optional[LocalPerformanceAlerting] = None
        self._performance_tracker: Optional[PerformanceTracker] = None
        self._metrics_collector: Optional[LocalPerformanceMetricsCollector] = None
        self._query_monitor: Optional[QueryPerformanceMonitor] = None
        self._database_factory: Optional[DatabaseClientFactory] = None
        
        # Configuration
        self._custom_thresholds: Dict[str, Any] = {}
        
        self.logger.info("Performance alerting integration initialized")
    
    async def start_integration(
        self,
        database_factory: Optional[DatabaseClientFactory] = None,
        performance_tracker: Optional[PerformanceTracker] = None,
        metrics_collector: Optional[LocalPerformanceMetricsCollector] = None,
        query_monitor: Optional[QueryPerformanceMonitor] = None
    ) -> None:
        """Start performance alerting integration."""
        if self._integration_active:
            self.logger.warning("Performance alerting integration is already active")
            return
        
        try:
            self.logger.info("Starting performance alerting integration...")
            
            # Store component references
            self._database_factory = database_factory
            self._performance_tracker = performance_tracker
            self._metrics_collector = metrics_collector
            self._query_monitor = query_monitor
            
            # Initialize performance alerting system
            self._performance_alerting = get_local_performance_alerting(self.config)
            
            # Apply custom configuration if available
            await self._apply_custom_configuration()
            
            # Start the alerting system with monitoring components
            await self._performance_alerting.start_alerting(
                performance_tracker=performance_tracker,
                metrics_collector=metrics_collector,
                query_monitor=query_monitor
            )
            
            # Start background initialization task
            self._initialization_task = asyncio.create_task(
                self._background_initialization()
            )
            
            self._integration_active = True
            self.logger.info("Performance alerting integration started successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to start performance alerting integration: {e}")
            raise
    
    async def stop_integration(self) -> None:
        """Stop performance alerting integration."""
        if not self._integration_active:
            return
        
        try:
            self.logger.info("Stopping performance alerting integration...")
            
            # Cancel background tasks
            if self._initialization_task:
                self._initialization_task.cancel()
                try:
                    await self._initialization_task
                except asyncio.CancelledError:
                    pass
            
            # Stop performance alerting
            if self._performance_alerting:
                await self._performance_alerting.stop_alerting()
            
            self._integration_active = False
            self.logger.info("Performance alerting integration stopped")
            
        except Exception as e:
            self.logger.error(f"Failed to stop performance alerting integration: {e}")
    
    async def _background_initialization(self) -> None:
        """Background initialization of performance alerting components."""
        try:
            # Wait a bit for other systems to initialize
            await asyncio.sleep(30)
            
            # Initialize monitoring components if not provided
            if not self._performance_tracker:
                self._performance_tracker = await self._initialize_performance_tracker()
            
            if not self._metrics_collector and self._database_factory:
                self._metrics_collector = await self._initialize_metrics_collector()
            
            if not self._query_monitor:
                self._query_monitor = await self._initialize_query_monitor()
            
            # Update alerting system with new components
            if self._performance_alerting:
                await self._performance_alerting.stop_alerting()
                await self._performance_alerting.start_alerting(
                    performance_tracker=self._performance_tracker,
                    metrics_collector=self._metrics_collector,
                    query_monitor=self._query_monitor
                )
            
            self.logger.info("Background initialization of performance alerting completed")
            
        except asyncio.CancelledError:
            self.logger.info("Background initialization cancelled")
        except Exception as e:
            self.logger.error(f"Error in background initialization: {e}")
    
    async def _initialize_performance_tracker(self) -> Optional[PerformanceTracker]:
        """Initialize performance tracker if not provided."""
        try:
            from .performance_tracker import PerformanceTracker
            
            tracker = PerformanceTracker()
            await tracker.start_monitoring()
            
            self.logger.info("Initialized performance tracker for alerting")
            return tracker
            
        except Exception as e:
            self.logger.warning(f"Failed to initialize performance tracker: {e}")
            return None
    
    async def _initialize_metrics_collector(self) -> Optional[LocalPerformanceMetricsCollector]:
        """Initialize metrics collector if not provided."""
        try:
            from .local_performance_metrics import LocalPerformanceMetricsCollector
            
            collector = LocalPerformanceMetricsCollector(
                database_factory=self._database_factory,
                config=self.config
            )
            await collector.start_collection()
            
            self.logger.info("Initialized metrics collector for alerting")
            return collector
            
        except Exception as e:
            self.logger.warning(f"Failed to initialize metrics collector: {e}")
            return None
    
    async def _initialize_query_monitor(self) -> Optional[QueryPerformanceMonitor]:
        """Initialize query performance monitor if not provided."""
        try:
            from .query_performance_monitor import QueryPerformanceMonitor
            
            monitor = QueryPerformanceMonitor()
            await monitor.start_monitoring()
            
            self.logger.info("Initialized query monitor for alerting")
            return monitor
            
        except Exception as e:
            self.logger.warning(f"Failed to initialize query monitor: {e}")
            return None
    
    async def _apply_custom_configuration(self) -> None:
        """Apply custom configuration to performance alerting."""
        try:
            if not self._performance_alerting:
                return
            
            # Apply local development specific thresholds
            await self._configure_local_development_thresholds()
            
            # Apply any user-defined custom thresholds
            if self._custom_thresholds:
                await self._apply_user_thresholds()
            
            self.logger.info("Applied custom configuration to performance alerting")
            
        except Exception as e:
            self.logger.warning(f"Failed to apply custom configuration: {e}")
    
    async def _configure_local_development_thresholds(self) -> None:
        """Configure thresholds optimized for local development."""
        if not self._performance_alerting:
            return
        
        # Adjust thresholds for local development environment
        # These are more lenient than production thresholds
        
        # Database query thresholds - more lenient for local development
        db_query_rule = PerformanceAlertRule(
            alert_type=PerformanceAlertType.SLOW_DATABASE_QUERY,
            service_pattern=r"(postgres|neo4j|milvus|redis)",
            thresholds=[
                PerformanceThreshold(
                    metric_name="query_response_time_ms",
                    threshold_value=10000.0,  # 10 seconds (more lenient for local)
                    comparison="greater_than",
                    window_minutes=5,
                    min_samples=3,
                    severity=AlertSeverity.MEDIUM,
                    cooldown_minutes=15
                )
            ],
            description="Database queries are taking longer than expected in local development",
            remediation_steps=[
                "Check if containers have sufficient resources",
                "Review Docker container resource limits",
                "Check for competing processes on development machine",
                "Consider optimizing development data set size"
            ]
        )
        
        self._performance_alerting.update_alert_rule(
            PerformanceAlertType.SLOW_DATABASE_QUERY,
            db_query_rule
        )
        
        # Memory usage thresholds - adjusted for local containers
        memory_rule = PerformanceAlertRule(
            alert_type=PerformanceAlertType.CONTAINER_MEMORY_LIMIT_EXCEEDED,
            service_pattern=r".*",
            thresholds=[
                PerformanceThreshold(
                    metric_name="memory_usage_percent",
                    threshold_value=95.0,  # 95% (more lenient for local)
                    comparison="greater_than",
                    window_minutes=5,
                    min_samples=3,
                    severity=AlertSeverity.HIGH,
                    cooldown_minutes=20
                )
            ],
            description="Container is approaching memory limits in local development",
            remediation_steps=[
                "Increase Docker container memory limits",
                "Check docker-compose.yml resource configuration",
                "Close unnecessary applications on development machine",
                "Consider using smaller development datasets"
            ]
        )
        
        self._performance_alerting.update_alert_rule(
            PerformanceAlertType.CONTAINER_MEMORY_LIMIT_EXCEEDED,
            memory_rule
        )
        
        # Startup time thresholds - aligned with requirements
        startup_rule = PerformanceAlertRule(
            alert_type=PerformanceAlertType.STARTUP_TIME_EXCESSIVE,
            service_pattern=r".*",
            thresholds=[
                PerformanceThreshold(
                    metric_name="startup_time_seconds",
                    threshold_value=120.0,  # 2 minutes (requirement)
                    comparison="greater_than",
                    window_minutes=1,
                    min_samples=1,
                    severity=AlertSeverity.HIGH,
                    cooldown_minutes=30
                )
            ],
            description="Service startup time exceeds local development requirements",
            remediation_steps=[
                "Check Docker container resource allocation",
                "Review service initialization processes",
                "Optimize database connection initialization",
                "Consider parallel service startup",
                "Check for network connectivity issues"
            ]
        )
        
        self._performance_alerting.update_alert_rule(
            PerformanceAlertType.STARTUP_TIME_EXCESSIVE,
            startup_rule
        )
    
    async def _apply_user_thresholds(self) -> None:
        """Apply user-defined custom thresholds."""
        # This would load custom thresholds from configuration files
        # For now, it's a placeholder for future extensibility
        pass
    
    def configure_custom_threshold(
        self,
        alert_type: PerformanceAlertType,
        metric_name: str,
        threshold_value: float,
        comparison: str = "greater_than",
        severity: str = "medium"
    ) -> None:
        """Configure a custom threshold for performance alerting."""
        try:
            from .alerting_service import AlertSeverity
            
            # Convert severity string to AlertSeverity enum
            severity_mapping = {
                "low": AlertSeverity.LOW,
                "medium": AlertSeverity.MEDIUM,
                "high": AlertSeverity.HIGH,
                "critical": AlertSeverity.CRITICAL
            }
            
            severity_enum = severity_mapping.get(severity.lower())
            if severity_enum is None:
                raise ValueError(f"Invalid severity: {severity}. Must be one of {list(severity_mapping.keys())}")
            
            # Store custom threshold
            threshold_key = f"{alert_type.value}_{metric_name}"
            self._custom_thresholds[threshold_key] = {
                "alert_type": alert_type,
                "metric_name": metric_name,
                "threshold_value": threshold_value,
                "comparison": comparison,
                "severity": severity_enum
            }
            
            self.logger.info(f"Configured custom threshold: {threshold_key}")
            
        except Exception as e:
            self.logger.error(f"Failed to configure custom threshold: {e}")
            raise
    
    def get_alerting_status(self) -> Dict[str, Any]:
        """Get current status of performance alerting."""
        status = {
            "integration_active": self._integration_active,
            "alerting_system_active": False,
            "components_initialized": {
                "performance_tracker": self._performance_tracker is not None,
                "metrics_collector": self._metrics_collector is not None,
                "query_monitor": self._query_monitor is not None
            },
            "custom_thresholds_count": len(self._custom_thresholds),
            "timestamp": datetime.now().isoformat()
        }
        
        if self._performance_alerting:
            status["alerting_system_active"] = self._performance_alerting._alerting_active
            status["alert_rules_count"] = len(self._performance_alerting.get_alert_rules())
        
        return status
    
    async def restart_alerting(self) -> None:
        """Restart performance alerting system."""
        try:
            self.logger.info("Restarting performance alerting system...")
            
            if self._integration_active:
                await self.stop_integration()
            
            await self.start_integration(
                database_factory=self._database_factory,
                performance_tracker=self._performance_tracker,
                metrics_collector=self._metrics_collector,
                query_monitor=self._query_monitor
            )
            
            self.logger.info("Performance alerting system restarted successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to restart performance alerting: {e}")
            raise


# Global instance
_performance_alerting_integration: Optional[PerformanceAlertingIntegration] = None


def get_performance_alerting_integration(
    config: Optional[LocalDatabaseConfig] = None
) -> PerformanceAlertingIntegration:
    """Get the global performance alerting integration instance."""
    global _performance_alerting_integration
    if _performance_alerting_integration is None:
        _performance_alerting_integration = PerformanceAlertingIntegration(config)
    return _performance_alerting_integration


async def initialize_performance_alerting(
    config: Optional[LocalDatabaseConfig] = None,
    database_factory: Optional[DatabaseClientFactory] = None,
    performance_tracker: Optional[PerformanceTracker] = None,
    metrics_collector: Optional[LocalPerformanceMetricsCollector] = None,
    query_monitor: Optional[QueryPerformanceMonitor] = None
) -> None:
    """Initialize performance alerting for local development."""
    integration = get_performance_alerting_integration(config)
    await integration.start_integration(
        database_factory=database_factory,
        performance_tracker=performance_tracker,
        metrics_collector=metrics_collector,
        query_monitor=query_monitor
    )


async def shutdown_performance_alerting() -> None:
    """Shutdown performance alerting integration."""
    if _performance_alerting_integration:
        await _performance_alerting_integration.stop_integration()


async def restart_performance_alerting() -> None:
    """Restart performance alerting integration."""
    if _performance_alerting_integration:
        await _performance_alerting_integration.restart_alerting()