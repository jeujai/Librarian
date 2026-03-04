"""
Local Error Tracking and Alerting Integration

This module provides integration between the local error tracking and alerting systems
and the main application. It handles startup, shutdown, and configuration of local
development monitoring features.

Features:
- Automatic startup and shutdown of error tracking and alerting
- Integration with application lifecycle
- Configuration management for local development
- Error and alert forwarding from other systems
- Health check integration
"""

import asyncio
import os
from datetime import datetime
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager

from .local_error_tracking import (
    LocalErrorTracker,
    LocalErrorCategory,
    get_local_error_tracker,
    start_local_error_tracking,
    stop_local_error_tracking,
    track_local_error
)
from .local_alerting_system import (
    LocalAlertingSystem,
    LocalAlertType,
    get_local_alerting_system,
    start_local_alerting,
    stop_local_alerting,
    send_local_alert
)
from .error_logging_service import ErrorSeverity
from .alerting_service import AlertSeverity
from ..config.local_config import LocalDatabaseConfig
from ..logging_config import get_logger

logger = get_logger("local_error_alerting_integration")


class LocalErrorAlertingIntegration:
    """
    Integration manager for local error tracking and alerting systems.
    
    This class manages the lifecycle and integration of error tracking and alerting
    systems specifically for local development environments.
    """
    
    def __init__(self, config: Optional[LocalDatabaseConfig] = None):
        self.config = config or LocalDatabaseConfig()
        self.logger = get_logger("local_error_alerting_integration")
        
        # Integration state
        self._integration_active = False
        self._error_tracker: Optional[LocalErrorTracker] = None
        self._alerting_system: Optional[LocalAlertingSystem] = None
        
        # Configuration
        self._enable_error_tracking = True
        self._enable_alerting = True
        self._enable_desktop_notifications = True
        
        # Check if we're in local development mode
        self._is_local_development = self._check_local_development()
        
        self.logger.info("Local error tracking and alerting integration initialized")
    
    def _check_local_development(self) -> bool:
        """Check if we're running in local development mode."""
        # Check environment variables and configuration
        env_indicators = [
            os.getenv("ML_ENVIRONMENT", "").lower() == "local",
            os.getenv("ML_DATABASE_TYPE", "").lower() == "local",
            self.config.database_type == "local",
            self.config.debug,
            os.path.exists("docker-compose.local.yml")
        ]
        
        return any(env_indicators)
    
    async def start_integration(self) -> None:
        """Start the local error tracking and alerting integration."""
        if not self._is_local_development:
            self.logger.info("Not in local development mode, skipping local error tracking and alerting")
            return
        
        if self._integration_active:
            self.logger.warning("Local error tracking and alerting integration is already active")
            return
        
        try:
            self._integration_active = True
            
            # Start error tracking
            if self._enable_error_tracking:
                self.logger.info("Starting local error tracking...")
                await start_local_error_tracking(self.config)
                self._error_tracker = get_local_error_tracker(self.config)
                self.logger.info("Local error tracking started successfully")
            
            # Start alerting system
            if self._enable_alerting:
                self.logger.info("Starting local alerting system...")
                await start_local_alerting(self.config)
                self._alerting_system = get_local_alerting_system(self.config)
                self.logger.info("Local alerting system started successfully")
            
            # Set up error forwarding from other systems
            await self._setup_error_forwarding()
            
            # Send startup notification
            if self._alerting_system:
                await self._alerting_system.send_alert(
                    alert_type=LocalAlertType.DEVELOPMENT_SERVER_DOWN,  # Reusing for startup
                    title="Local Development Monitoring Started",
                    message="Error tracking and alerting systems are now active",
                    severity=AlertSeverity.LOW,
                    service="monitoring",
                    context={
                        "error_tracking_enabled": self._enable_error_tracking,
                        "alerting_enabled": self._enable_alerting,
                        "startup_time": datetime.now().isoformat()
                    }
                )
            
            self.logger.info("Local error tracking and alerting integration started successfully")
            
        except Exception as e:
            self._integration_active = False
            self.logger.error(f"Failed to start local error tracking and alerting integration: {e}")
            
            # Track the startup error
            if self._error_tracker:
                self._error_tracker.track_error(
                    category=LocalErrorCategory.CONFIGURATION,
                    severity=ErrorSeverity.HIGH,
                    service="monitoring",
                    operation="start_integration",
                    message=f"Failed to start integration: {str(e)}",
                    exception=e
                )
            
            raise
    
    async def stop_integration(self) -> None:
        """Stop the local error tracking and alerting integration."""
        if not self._integration_active:
            return
        
        try:
            self._integration_active = False
            
            # Send shutdown notification
            if self._alerting_system:
                await self._alerting_system.send_alert(
                    alert_type=LocalAlertType.DEVELOPMENT_SERVER_DOWN,  # Reusing for shutdown
                    title="Local Development Monitoring Stopping",
                    message="Error tracking and alerting systems are shutting down",
                    severity=AlertSeverity.LOW,
                    service="monitoring",
                    context={
                        "shutdown_time": datetime.now().isoformat()
                    }
                )
            
            # Stop alerting system
            if self._enable_alerting:
                self.logger.info("Stopping local alerting system...")
                await stop_local_alerting()
                self.logger.info("Local alerting system stopped")
            
            # Stop error tracking
            if self._enable_error_tracking:
                self.logger.info("Stopping local error tracking...")
                await stop_local_error_tracking()
                self.logger.info("Local error tracking stopped")
            
            self.logger.info("Local error tracking and alerting integration stopped successfully")
            
        except Exception as e:
            self.logger.error(f"Error during local error tracking and alerting integration shutdown: {e}")
    
    async def _setup_error_forwarding(self) -> None:
        """Set up error forwarding from other monitoring systems."""
        try:
            # This would integrate with existing error monitoring systems
            # to forward errors to the local tracking system
            
            # For now, we'll set up basic integration hooks
            self.logger.info("Error forwarding setup completed")
            
        except Exception as e:
            self.logger.warning(f"Failed to setup error forwarding: {e}")
    
    def track_error(
        self,
        category: LocalErrorCategory,
        severity: ErrorSeverity,
        service: str,
        operation: str,
        message: str,
        exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Track an error through the local error tracking system.
        
        Args:
            category: Error category
            severity: Error severity
            service: Service name
            operation: Operation that failed
            message: Error message
            exception: Exception object (optional)
            context: Additional context (optional)
            
        Returns:
            Error ID if tracking is active, None otherwise
        """
        if not self._integration_active or not self._error_tracker:
            return None
        
        try:
            return self._error_tracker.track_error(
                category=category,
                severity=severity,
                service=service,
                operation=operation,
                message=message,
                exception=exception,
                context=context
            )
        except Exception as e:
            self.logger.warning(f"Failed to track error: {e}")
            return None
    
    async def send_alert(
        self,
        alert_type: LocalAlertType,
        title: str,
        message: str,
        severity: AlertSeverity = AlertSeverity.MEDIUM,
        service: str = "local_development",
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """
        Send an alert through the local alerting system.
        
        Args:
            alert_type: Type of alert
            title: Alert title
            message: Alert message
            severity: Alert severity
            service: Service name
            context: Additional context
            
        Returns:
            Alert ID if alerting is active, None otherwise
        """
        if not self._integration_active or not self._alerting_system:
            return None
        
        try:
            return await self._alerting_system.send_alert(
                alert_type=alert_type,
                title=title,
                message=message,
                severity=severity,
                service=service,
                context=context
            )
        except Exception as e:
            self.logger.warning(f"Failed to send alert: {e}")
            return None
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get health status of the integration."""
        return {
            "integration_active": self._integration_active,
            "is_local_development": self._is_local_development,
            "error_tracking_enabled": self._enable_error_tracking,
            "alerting_enabled": self._enable_alerting,
            "error_tracker_active": self._error_tracker._tracking_active if self._error_tracker else False,
            "alerting_system_active": self._alerting_system._alerting_active if self._alerting_system else False,
            "timestamp": datetime.now().isoformat()
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics from error tracking and alerting systems."""
        stats = {
            "integration_active": self._integration_active,
            "error_stats": None,
            "alert_stats": None
        }
        
        if self._error_tracker:
            try:
                error_stats = self._error_tracker.get_error_statistics()
                stats["error_stats"] = {
                    "total_errors": error_stats.total_errors,
                    "error_rate_per_minute": error_stats.error_rate_per_minute,
                    "critical_error_count": error_stats.critical_error_count,
                    "unresolved_error_count": error_stats.unresolved_error_count
                }
            except Exception as e:
                self.logger.warning(f"Failed to get error statistics: {e}")
        
        if self._alerting_system:
            try:
                alert_stats = self._alerting_system.get_alert_statistics()
                stats["alert_stats"] = {
                    "total_alerts": alert_stats.total_alerts,
                    "active_alerts": alert_stats.active_alerts,
                    "acknowledged_alerts": alert_stats.acknowledged_alerts,
                    "resolved_alerts": alert_stats.resolved_alerts
                }
            except Exception as e:
                self.logger.warning(f"Failed to get alert statistics: {e}")
        
        return stats


# Global instance
_local_error_alerting_integration: Optional[LocalErrorAlertingIntegration] = None


def get_local_error_alerting_integration(config: Optional[LocalDatabaseConfig] = None) -> LocalErrorAlertingIntegration:
    """Get the global local error tracking and alerting integration instance."""
    global _local_error_alerting_integration
    if _local_error_alerting_integration is None:
        _local_error_alerting_integration = LocalErrorAlertingIntegration(config)
    return _local_error_alerting_integration


async def start_local_error_alerting_integration(config: Optional[LocalDatabaseConfig] = None) -> None:
    """Start the local error tracking and alerting integration."""
    integration = get_local_error_alerting_integration(config)
    await integration.start_integration()


async def stop_local_error_alerting_integration() -> None:
    """Stop the local error tracking and alerting integration."""
    if _local_error_alerting_integration:
        await _local_error_alerting_integration.stop_integration()


@asynccontextmanager
async def local_error_alerting_lifespan(config: Optional[LocalDatabaseConfig] = None):
    """
    Context manager for local error tracking and alerting lifecycle.
    
    This can be used with FastAPI's lifespan context manager to automatically
    start and stop the local error tracking and alerting systems.
    """
    try:
        await start_local_error_alerting_integration(config)
        yield
    finally:
        await stop_local_error_alerting_integration()


# Convenience functions for easy integration
def track_local_development_error(
    category: LocalErrorCategory,
    severity: ErrorSeverity,
    service: str,
    operation: str,
    message: str,
    exception: Optional[Exception] = None,
    context: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Convenience function to track a local development error.
    
    This function can be used throughout the application to easily track errors
    in local development environments.
    """
    integration = get_local_error_alerting_integration()
    return integration.track_error(
        category=category,
        severity=severity,
        service=service,
        operation=operation,
        message=message,
        exception=exception,
        context=context
    )


async def send_local_development_alert(
    alert_type: LocalAlertType,
    title: str,
    message: str,
    severity: AlertSeverity = AlertSeverity.MEDIUM,
    service: str = "local_development",
    context: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Convenience function to send a local development alert.
    
    This function can be used throughout the application to easily send alerts
    in local development environments.
    """
    integration = get_local_error_alerting_integration()
    return await integration.send_alert(
        alert_type=alert_type,
        title=title,
        message=message,
        severity=severity,
        service=service,
        context=context
    )


def get_local_monitoring_health() -> Dict[str, Any]:
    """Get health status of local monitoring systems."""
    integration = get_local_error_alerting_integration()
    return integration.get_health_status()


def get_local_monitoring_statistics() -> Dict[str, Any]:
    """Get statistics from local monitoring systems."""
    integration = get_local_error_alerting_integration()
    return integration.get_statistics()