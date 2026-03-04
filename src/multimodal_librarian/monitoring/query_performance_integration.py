"""
Query Performance Monitoring Integration

This module provides integration utilities to automatically enable query performance
monitoring in database clients. It integrates with the database client factory and
dependency injection system to provide seamless monitoring without code changes.

The integration automatically wraps database clients with performance monitoring
decorators and initializes the monitoring system based on configuration.

Example Usage:
    ```python
    from multimodal_librarian.monitoring.query_performance_integration import (
        initialize_query_monitoring, enable_monitoring_for_factory
    )
    
    # Initialize global monitoring
    await initialize_query_monitoring()
    
    # Enable monitoring for database factory
    factory = DatabaseClientFactory(config)
    monitored_factory = enable_monitoring_for_factory(factory)
    ```

Integration Points:
    - Database client factory integration
    - Dependency injection integration
    - Application startup integration
    - Health check integration
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List, Callable
from contextlib import asynccontextmanager

from .query_performance_monitor import (
    QueryPerformanceMonitor, initialize_global_monitor, get_global_monitor,
    shutdown_global_monitor
)
from .query_performance_decorators import (
    QueryPerformanceIntegration, enable_postgresql_monitoring,
    enable_neo4j_monitoring, enable_milvus_monitoring
)
from ..config.query_performance_config import (
    QueryPerformanceConfig, get_query_performance_config
)

logger = logging.getLogger(__name__)


class QueryMonitoringManager:
    """
    Manager for query performance monitoring integration.
    
    This class handles the lifecycle of query performance monitoring,
    including initialization, configuration, and integration with
    database clients and the application.
    """
    
    def __init__(self, config: Optional[QueryPerformanceConfig] = None):
        """
        Initialize the monitoring manager.
        
        Args:
            config: Query performance configuration (uses default if None)
        """
        self.config = config or get_query_performance_config()
        self.monitor: Optional[QueryPerformanceMonitor] = None
        self.integration: Optional[QueryPerformanceIntegration] = None
        self.is_initialized = False
        self._wrapped_clients: List[Any] = []
        self._alert_handlers: List[Callable] = []
    
    async def initialize(self) -> bool:
        """
        Initialize query performance monitoring.
        
        Returns:
            True if monitoring was successfully initialized
        """
        if self.is_initialized:
            logger.warning("Query monitoring already initialized")
            return True
        
        if not self.config.monitoring_enabled:
            logger.info("Query performance monitoring is disabled")
            return False
        
        try:
            # Initialize the global monitor
            monitor_kwargs = self.config.to_monitor_kwargs()
            self.monitor = await initialize_global_monitor(**monitor_kwargs)
            
            # Create integration helper
            self.integration = QueryPerformanceIntegration(self.monitor)
            
            # Set up alert handlers
            await self._setup_alert_handlers()
            
            # Set up metrics export if enabled
            if self.config.enable_metrics_export:
                await self._setup_metrics_export()
            
            self.is_initialized = True
            
            logger.info(
                f"Query performance monitoring initialized with level: {self.config.monitoring_level}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize query monitoring: {e}")
            return False
    
    async def shutdown(self) -> None:
        """Shutdown query performance monitoring."""
        if not self.is_initialized:
            return
        
        try:
            # Stop metrics export
            if hasattr(self, '_export_task') and self._export_task:
                self._export_task.cancel()
                try:
                    await self._export_task
                except asyncio.CancelledError:
                    pass
            
            # Shutdown global monitor
            await shutdown_global_monitor()
            
            # Clear references
            self.monitor = None
            self.integration = None
            self._wrapped_clients.clear()
            self._alert_handlers.clear()
            
            self.is_initialized = False
            
            logger.info("Query performance monitoring shutdown")
            
        except Exception as e:
            logger.error(f"Error during monitoring shutdown: {e}")
    
    def wrap_database_client(self, client, database_type: str):
        """
        Wrap a database client with performance monitoring.
        
        Args:
            client: Database client instance to wrap
            database_type: Type of database (postgresql, neo4j, milvus)
            
        Returns:
            Wrapped client with monitoring enabled
        """
        if not self.is_initialized or not self.integration:
            logger.warning("Monitoring not initialized - returning unwrapped client")
            return client
        
        if not self.config.should_monitor_database(database_type):
            logger.debug(f"Monitoring disabled for {database_type} - returning unwrapped client")
            return client
        
        try:
            # Use appropriate wrapper based on database type
            if database_type.lower() == "postgresql":
                wrapped_client = enable_postgresql_monitoring(client, self.monitor)
            elif database_type.lower() == "neo4j":
                wrapped_client = enable_neo4j_monitoring(client, self.monitor)
            elif database_type.lower() == "milvus":
                wrapped_client = enable_milvus_monitoring(client, self.monitor)
            else:
                # Generic wrapper
                wrapped_client = self.integration.wrap_client_methods(client, database_type)
            
            # Track wrapped clients
            self._wrapped_clients.append(wrapped_client)
            
            logger.debug(f"Wrapped {database_type} client with performance monitoring")
            return wrapped_client
            
        except Exception as e:
            logger.error(f"Failed to wrap {database_type} client: {e}")
            return client
    
    def get_performance_stats(self, database_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get performance statistics.
        
        Args:
            database_type: Specific database type (optional)
            
        Returns:
            Performance statistics
        """
        if not self.monitor:
            return {}
        
        try:
            # This would need to be made synchronous or we need an async version
            # For now, return cached stats if available
            return self.monitor._stats_cache.get(database_type, {})
        except Exception as e:
            logger.error(f"Failed to get performance stats: {e}")
            return {}
    
    async def _setup_alert_handlers(self) -> None:
        """Set up alert handlers based on configuration."""
        if not self.config.enable_alerts or not self.monitor:
            return
        
        alert_settings = self.config.get_alert_settings()
        
        # Set up log handler
        if "log" in alert_settings["channels"]:
            self.monitor.add_alert_callback(self._log_alert_handler)
        
        # Set up webhook handler
        if "webhook" in alert_settings["channels"] and alert_settings["webhook_url"]:
            webhook_handler = self._create_webhook_handler(alert_settings["webhook_url"])
            self.monitor.add_alert_callback(webhook_handler)
        
        logger.debug(f"Set up alert handlers: {alert_settings['channels']}")
    
    def _log_alert_handler(self, alert) -> None:
        """Handle alerts by logging them."""
        severity_map = {
            "low": logging.INFO,
            "medium": logging.WARNING,
            "high": logging.ERROR,
            "critical": logging.CRITICAL
        }
        
        log_level = severity_map.get(alert.severity, logging.WARNING)
        
        logger.log(
            log_level,
            f"Query Performance Alert [{alert.alert_type}]: {alert.message} "
            f"(Database: {alert.database_type.value})"
        )
        
        # Log recommendations if available
        if alert.recommendations:
            logger.info(f"Recommendations: {'; '.join(alert.recommendations)}")
    
    def _create_webhook_handler(self, webhook_url: str) -> Callable:
        """Create webhook alert handler."""
        async def webhook_handler(alert):
            try:
                import aiohttp
                
                payload = {
                    "alert_id": alert.alert_id,
                    "alert_type": alert.alert_type,
                    "severity": alert.severity,
                    "message": alert.message,
                    "timestamp": alert.timestamp.isoformat(),
                    "database_type": alert.database_type.value,
                    "recommendations": alert.recommendations
                }
                
                if alert.query_metrics:
                    payload["query_info"] = {
                        "query_id": alert.query_metrics.query_id,
                        "duration_ms": alert.query_metrics.duration_ms,
                        "query_type": alert.query_metrics.query_type.value,
                        "error": alert.query_metrics.error
                    }
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(webhook_url, json=payload, timeout=10) as response:
                        if response.status != 200:
                            logger.warning(f"Webhook alert failed: {response.status}")
                        
            except Exception as e:
                logger.error(f"Failed to send webhook alert: {e}")
        
        return webhook_handler
    
    async def _setup_metrics_export(self) -> None:
        """Set up automatic metrics export."""
        if not self.monitor:
            return
        
        export_settings = self.config.get_export_settings()
        
        async def export_task():
            while self.is_initialized:
                try:
                    await asyncio.sleep(export_settings["interval_minutes"] * 60)
                    
                    if not self.is_initialized:
                        break
                    
                    # Export metrics
                    import os
                    from datetime import datetime
                    
                    os.makedirs(export_settings["directory"], exist_ok=True)
                    
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"query_metrics_{timestamp}.{export_settings['format']}"
                    filepath = os.path.join(export_settings["directory"], filename)
                    
                    success = await self.monitor.export_metrics(
                        filepath, format=export_settings["format"]
                    )
                    
                    if success:
                        logger.info(f"Exported query metrics to {filepath}")
                    else:
                        logger.warning("Failed to export query metrics")
                        
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in metrics export task: {e}")
        
        # Start export task
        self._export_task = asyncio.create_task(export_task())
        logger.debug(f"Started metrics export task (interval: {export_settings['interval_minutes']} minutes)")


# Global monitoring manager instance
_global_manager: Optional[QueryMonitoringManager] = None


def get_monitoring_manager() -> Optional[QueryMonitoringManager]:
    """Get the global monitoring manager instance."""
    return _global_manager


async def initialize_query_monitoring(
    config: Optional[QueryPerformanceConfig] = None
) -> Optional[QueryMonitoringManager]:
    """
    Initialize global query performance monitoring.
    
    Args:
        config: Query performance configuration (uses default if None)
        
    Returns:
        Monitoring manager instance if successful, None otherwise
    """
    global _global_manager
    
    if _global_manager is not None:
        logger.warning("Query monitoring already initialized")
        return _global_manager
    
    _global_manager = QueryMonitoringManager(config)
    success = await _global_manager.initialize()
    
    if not success:
        _global_manager = None
        return None
    
    return _global_manager


async def shutdown_query_monitoring() -> None:
    """Shutdown global query performance monitoring."""
    global _global_manager
    
    if _global_manager is not None:
        await _global_manager.shutdown()
        _global_manager = None


def enable_monitoring_for_factory(factory):
    """
    Enable query performance monitoring for a database client factory.
    
    This function wraps the factory's client creation methods to automatically
    enable monitoring for all created clients.
    
    Args:
        factory: Database client factory instance
        
    Returns:
        Factory with monitoring enabled
    """
    manager = get_monitoring_manager()
    if not manager or not manager.is_initialized:
        logger.warning("Monitoring not initialized - returning unwrapped factory")
        return factory
    
    # Store original methods
    original_get_relational = getattr(factory, 'get_relational_client', None)
    original_get_vector = getattr(factory, 'get_vector_client', None)
    original_get_graph = getattr(factory, 'get_graph_client', None)
    
    # Wrap relational client method
    if original_get_relational:
        async def monitored_get_relational_client():
            client = await original_get_relational()
            return manager.wrap_database_client(client, "postgresql")
        
        factory.get_relational_client = monitored_get_relational_client
    
    # Wrap vector client method
    if original_get_vector:
        async def monitored_get_vector_client():
            client = await original_get_vector()
            return manager.wrap_database_client(client, "milvus")
        
        factory.get_vector_client = monitored_get_vector_client
    
    # Wrap graph client method
    if original_get_graph:
        async def monitored_get_graph_client():
            client = await original_get_graph()
            return manager.wrap_database_client(client, "neo4j")
        
        factory.get_graph_client = monitored_get_graph_client
    
    logger.debug("Enabled monitoring for database client factory")
    return factory


@asynccontextmanager
async def query_monitoring_context(config: Optional[QueryPerformanceConfig] = None):
    """
    Context manager for query performance monitoring.
    
    This context manager automatically initializes and shuts down query
    performance monitoring for the duration of the context.
    
    Args:
        config: Query performance configuration (uses default if None)
        
    Example:
        ```python
        async with query_monitoring_context() as manager:
            # Monitoring is active
            factory = DatabaseClientFactory(config)
            monitored_factory = enable_monitoring_for_factory(factory)
            
            # Use monitored factory...
        # Monitoring is automatically shut down
        ```
    """
    manager = None
    try:
        manager = await initialize_query_monitoring(config)
        yield manager
    finally:
        if manager:
            await shutdown_query_monitoring()


def integrate_with_health_checks(health_check_system):
    """
    Integrate query performance monitoring with health check system.
    
    This function adds query performance metrics to the health check system
    to provide comprehensive monitoring information.
    
    Args:
        health_check_system: Health check system instance
    """
    manager = get_monitoring_manager()
    if not manager or not manager.monitor:
        logger.warning("Monitoring not available for health check integration")
        return
    
    async def query_performance_health_check():
        """Health check for query performance monitoring."""
        try:
            if not manager.is_initialized:
                return {
                    "status": "unhealthy",
                    "error": "Query monitoring not initialized"
                }
            
            # Get monitoring status
            status = manager.monitor.get_monitoring_status()
            
            # Get recent alerts
            recent_alerts = await manager.monitor.get_recent_alerts(limit=5)
            critical_alerts = [a for a in recent_alerts if a.severity == "critical"]
            
            # Determine overall health
            if critical_alerts:
                health_status = "degraded"
            elif not status["is_monitoring"]:
                health_status = "unhealthy"
            else:
                health_status = "healthy"
            
            return {
                "status": health_status,
                "monitoring_active": status["is_monitoring"],
                "total_queries_tracked": status["total_queries_tracked"],
                "total_alerts": status["total_alerts"],
                "critical_alerts": len(critical_alerts),
                "queries_by_database": status["queries_by_database"]
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    # Add to health check system
    if hasattr(health_check_system, 'add_check'):
        health_check_system.add_check("query_performance", query_performance_health_check)
    
    logger.debug("Integrated query performance monitoring with health checks")


def get_monitoring_dashboard_data() -> Dict[str, Any]:
    """
    Get data for monitoring dashboard.
    
    Returns:
        Dictionary with monitoring dashboard data
    """
    manager = get_monitoring_manager()
    if not manager or not manager.monitor:
        return {"monitoring_enabled": False}
    
    try:
        # Get basic status
        status = manager.monitor.get_monitoring_status()
        
        # Get performance stats (this would need to be async in real implementation)
        # For now, return cached data
        stats = {}
        for db_type, cached_stats in manager.monitor._stats_cache.items():
            stats[db_type.value] = {
                "total_queries": getattr(cached_stats, 'total_queries', 0),
                "avg_query_time_ms": getattr(cached_stats, 'avg_query_time_ms', 0),
                "slow_query_count": getattr(cached_stats, 'slow_query_count', 0),
                "error_rate": getattr(cached_stats, 'error_rate', 0)
            }
        
        return {
            "monitoring_enabled": True,
            "status": status,
            "performance_stats": stats,
            "config": {
                "monitoring_level": manager.config.monitoring_level.value,
                "slow_query_threshold_ms": manager.config.slow_query_threshold_ms,
                "sample_rate": manager.config.sample_rate
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get dashboard data: {e}")
        return {"monitoring_enabled": True, "error": str(e)}


# Convenience functions for common integration patterns

async def auto_initialize_monitoring():
    """
    Automatically initialize monitoring based on environment configuration.
    
    This function is designed to be called during application startup
    to automatically set up query performance monitoring.
    """
    config = get_query_performance_config()
    
    if config.auto_start_monitoring:
        manager = await initialize_query_monitoring(config)
        if manager:
            logger.info("Query performance monitoring auto-initialized")
        else:
            logger.warning("Failed to auto-initialize query performance monitoring")


def create_monitoring_middleware(database_type: str):
    """
    Create monitoring middleware for custom database clients.
    
    Args:
        database_type: Type of database
        
    Returns:
        Monitoring middleware function
    """
    manager = get_monitoring_manager()
    if not manager or not manager.integration:
        # Return no-op middleware
        @asynccontextmanager
        async def noop_middleware(query, params=None):
            yield None
        return noop_middleware
    
    return manager.integration.create_monitoring_middleware(database_type)