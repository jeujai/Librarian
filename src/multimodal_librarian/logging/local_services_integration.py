"""
Local Services Logging Integration

This module integrates local services structured logging with the main application,
providing startup/shutdown hooks, health monitoring integration, and API endpoints
for monitoring local services.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any
from contextlib import asynccontextmanager

from ..config import get_settings
from ..logging_config import get_logger
from .local_services_logger import get_local_services_logger, start_local_services_monitoring, stop_local_services_monitoring
from ..monitoring.structured_logging_service import log_info_structured, log_error_structured, log_warning_structured
from ..config.local_logging_config import get_local_logging_config


class LocalServicesLoggingIntegration:
    """
    Integration layer for local services logging with the main application.
    
    Handles:
    - Startup and shutdown of local services monitoring
    - Integration with application health checks
    - Coordination with structured logging service
    - Error alerting and notifications
    """
    
    def __init__(self):
        """Initialize the integration layer."""
        self.settings = get_settings()
        self.logger = get_logger("local_services_integration")
        self.logging_config = get_local_logging_config()
        self.local_services_logger = get_local_services_logger()
        
        # Integration state
        self._integration_active = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self._health_check_task: Optional[asyncio.Task] = None
        
        self.logger.info("LocalServicesLoggingIntegration initialized")
    
    async def start_integration(self) -> None:
        """Start the local services logging integration."""
        if self._integration_active:
            self.logger.warning("Local services logging integration already active")
            return
        
        if not self.logging_config.enable_local_logging:
            self.logger.info("Local services logging disabled in configuration")
            return
        
        try:
            self._integration_active = True
            
            # Start local services monitoring
            await start_local_services_monitoring()
            
            # Start integration monitoring tasks
            self._monitoring_task = asyncio.create_task(self._integration_monitoring_loop())
            
            if self.logging_config.enable_health_monitoring:
                self._health_check_task = asyncio.create_task(self._health_monitoring_loop())
            
            # Log integration start
            log_info_structured(
                service="local_services_integration",
                operation="start_integration",
                message="Started local services logging integration",
                metadata={
                    'health_monitoring_enabled': self.logging_config.enable_health_monitoring,
                    'performance_metrics_enabled': self.logging_config.enable_performance_metrics,
                    'error_alerting_enabled': self.logging_config.enable_error_alerting,
                    'monitored_services': list(self.logging_config.service_configs.keys())
                },
                tags={'category': 'integration', 'action': 'start'}
            )
            
            self.logger.info("Local services logging integration started successfully")
            
        except Exception as e:
            self._integration_active = False
            self.logger.error(f"Failed to start local services logging integration: {e}")
            
            log_error_structured(
                service="local_services_integration",
                operation="start_integration_error",
                message=f"Failed to start integration: {str(e)}",
                error_type=type(e).__name__,
                stack_trace=str(e),
                tags={'category': 'integration_error', 'action': 'start_failed'}
            )
            raise
    
    async def stop_integration(self) -> None:
        """Stop the local services logging integration."""
        if not self._integration_active:
            return
        
        try:
            self._integration_active = False
            
            # Cancel monitoring tasks
            if self._monitoring_task and not self._monitoring_task.done():
                self._monitoring_task.cancel()
                try:
                    await self._monitoring_task
                except asyncio.CancelledError:
                    pass
            
            if self._health_check_task and not self._health_check_task.done():
                self._health_check_task.cancel()
                try:
                    await self._health_check_task
                except asyncio.CancelledError:
                    pass
            
            # Stop local services monitoring
            await stop_local_services_monitoring()
            
            # Log integration stop
            log_info_structured(
                service="local_services_integration",
                operation="stop_integration",
                message="Stopped local services logging integration",
                tags={'category': 'integration', 'action': 'stop'}
            )
            
            self.logger.info("Local services logging integration stopped successfully")
            
        except Exception as e:
            self.logger.error(f"Error stopping local services logging integration: {e}")
            
            log_error_structured(
                service="local_services_integration",
                operation="stop_integration_error",
                message=f"Error stopping integration: {str(e)}",
                error_type=type(e).__name__,
                stack_trace=str(e),
                tags={'category': 'integration_error', 'action': 'stop_failed'}
            )
    
    async def _integration_monitoring_loop(self) -> None:
        """Main integration monitoring loop."""
        while self._integration_active:
            try:
                # Check integration health
                await self._check_integration_health()
                
                # Process any pending alerts
                await self._process_error_alerts()
                
                # Update integration metrics
                await self._update_integration_metrics()
                
                # Sleep for monitoring interval
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                self.logger.error(f"Error in integration monitoring loop: {e}")
                await asyncio.sleep(30)
    
    async def _health_monitoring_loop(self) -> None:
        """Health monitoring loop for local services."""
        while self._integration_active:
            try:
                # Get service health metrics
                service_metrics = self.local_services_logger.get_service_metrics()
                
                # Check for unhealthy services
                await self._check_service_health(service_metrics)
                
                # Log health summary
                await self._log_health_summary(service_metrics)
                
                # Sleep for health check interval
                await asyncio.sleep(self.logging_config.health_check_interval_seconds)
                
            except Exception as e:
                self.logger.error(f"Error in health monitoring loop: {e}")
                await asyncio.sleep(self.logging_config.health_check_interval_seconds)
    
    async def _check_integration_health(self) -> None:
        """Check the health of the integration itself."""
        try:
            # Check if local services logger is responsive
            metrics = self.local_services_logger.get_service_metrics()
            
            # Check processing stats
            processing_stats = metrics.get('processing_stats', {})
            logs_per_second = processing_stats.get('logs_per_second', 0)
            parsing_errors = processing_stats.get('parsing_errors', 0)
            
            # Alert on high error rate
            if parsing_errors > 10:  # More than 10 parsing errors
                log_warning_structured(
                    service="local_services_integration",
                    operation="high_parsing_errors",
                    message=f"High number of log parsing errors detected: {parsing_errors}",
                    metadata={'parsing_errors': parsing_errors, 'logs_per_second': logs_per_second},
                    tags={'category': 'integration_warning', 'issue': 'parsing_errors'}
                )
            
            # Alert on low processing rate (if logs are expected)
            if logs_per_second == 0 and metrics.get('monitoring_active', False):
                log_warning_structured(
                    service="local_services_integration",
                    operation="no_log_processing",
                    message="No logs being processed despite monitoring being active",
                    metadata=processing_stats,
                    tags={'category': 'integration_warning', 'issue': 'no_processing'}
                )
        
        except Exception as e:
            log_error_structured(
                service="local_services_integration",
                operation="integration_health_check_error",
                message=f"Error checking integration health: {str(e)}",
                error_type=type(e).__name__,
                stack_trace=str(e),
                tags={'category': 'integration_error', 'issue': 'health_check_failed'}
            )
    
    async def _process_error_alerts(self) -> None:
        """Process any pending error alerts from local services."""
        if not self.logging_config.enable_error_alerting:
            return
        
        try:
            # Get recent service logs with errors
            service_logs = self.local_services_logger.get_service_logs(hours=1, limit=1000)
            
            # Count errors by service
            error_counts = {}
            for log_entry in service_logs:
                if log_entry.get('error_info'):
                    service_name = log_entry['service_name']
                    error_counts[service_name] = error_counts.get(service_name, 0) + 1
            
            # Check error thresholds
            for service_name, error_count in error_counts.items():
                if error_count >= self.logging_config.error_alert_threshold:
                    log_error_structured(
                        service="local_services_integration",
                        operation="service_error_threshold_exceeded",
                        message=f"Service {service_name} exceeded error threshold: {error_count} errors in last hour",
                        metadata={
                            'service_name': service_name,
                            'error_count': error_count,
                            'threshold': self.logging_config.error_alert_threshold
                        },
                        tags={'category': 'service_alert', 'service': service_name, 'alert_type': 'error_threshold'}
                    )
        
        except Exception as e:
            self.logger.error(f"Error processing error alerts: {e}")
    
    async def _update_integration_metrics(self) -> None:
        """Update integration-specific metrics."""
        try:
            # Get current metrics
            service_metrics = self.local_services_logger.get_service_metrics()
            
            # Log integration metrics
            log_info_structured(
                service="local_services_integration",
                operation="integration_metrics_update",
                message="Integration metrics update",
                metadata={
                    'integration_active': self._integration_active,
                    'monitoring_task_running': self._monitoring_task and not self._monitoring_task.done(),
                    'health_check_task_running': self._health_check_task and not self._health_check_task.done(),
                    'service_metrics': service_metrics
                },
                tags={'category': 'integration_metrics'}
            )
        
        except Exception as e:
            self.logger.debug(f"Error updating integration metrics: {e}")
    
    async def _check_service_health(self, service_metrics: Dict[str, Any]) -> None:
        """Check health of individual services and alert on issues."""
        try:
            processing_stats = service_metrics.get('processing_stats', {})
            service_data = service_metrics.get('service_metrics', {})
            
            # Check each service
            for service_key, metrics in service_data.items():
                service_name = service_key.split('_')[0]  # Extract service name
                error_count = metrics.get('error_count', 0)
                log_count = metrics.get('log_count', 0)
                
                # Calculate error rate
                error_rate = (error_count / max(log_count, 1)) * 100
                
                # Alert on high error rate
                if error_rate > 10:  # More than 10% error rate
                    log_warning_structured(
                        service="local_services_integration",
                        operation="high_service_error_rate",
                        message=f"High error rate detected for {service_name}: {error_rate:.1f}%",
                        metadata={
                            'service_name': service_name,
                            'error_rate_percent': error_rate,
                            'error_count': error_count,
                            'log_count': log_count
                        },
                        tags={'category': 'service_warning', 'service': service_name, 'issue': 'high_error_rate'}
                    )
        
        except Exception as e:
            self.logger.error(f"Error checking service health: {e}")
    
    async def _log_health_summary(self, service_metrics: Dict[str, Any]) -> None:
        """Log a summary of service health."""
        try:
            processing_stats = service_metrics.get('processing_stats', {})
            service_data = service_metrics.get('service_metrics', {})
            monitored_services = service_metrics.get('monitored_services', [])
            
            # Create health summary
            health_summary = {
                'total_services': len(monitored_services),
                'services_with_logs': len(service_data),
                'total_logs_processed': processing_stats.get('logs_processed', 0),
                'logs_per_second': processing_stats.get('logs_per_second', 0),
                'parsing_errors': processing_stats.get('parsing_errors', 0),
                'monitoring_active': service_metrics.get('monitoring_active', False)
            }
            
            # Add per-service summary
            service_summary = {}
            for service_key, metrics in service_data.items():
                service_name = service_key.split('_')[0]
                service_summary[service_name] = {
                    'log_count': metrics.get('log_count', 0),
                    'error_count': metrics.get('error_count', 0),
                    'last_updated': metrics.get('last_updated')
                }
            
            health_summary['services'] = service_summary
            
            # Log health summary (at debug level to avoid spam)
            self.logger.debug(f"Local services health summary: {health_summary}")
        
        except Exception as e:
            self.logger.error(f"Error creating health summary: {e}")
    
    def get_integration_status(self) -> Dict[str, Any]:
        """Get the current status of the integration."""
        try:
            service_metrics = self.local_services_logger.get_service_metrics()
            
            return {
                'integration_active': self._integration_active,
                'monitoring_task_running': self._monitoring_task and not self._monitoring_task.done(),
                'health_check_task_running': self._health_check_task and not self._health_check_task.done(),
                'configuration': {
                    'enable_local_logging': self.logging_config.enable_local_logging,
                    'enable_health_monitoring': self.logging_config.enable_health_monitoring,
                    'enable_performance_metrics': self.logging_config.enable_performance_metrics,
                    'enable_error_alerting': self.logging_config.enable_error_alerting,
                    'health_check_interval_seconds': self.logging_config.health_check_interval_seconds,
                    'error_alert_threshold': self.logging_config.error_alert_threshold
                },
                'service_metrics': service_metrics,
                'monitored_services': list(self.logging_config.service_configs.keys())
            }
        
        except Exception as e:
            return {
                'integration_active': self._integration_active,
                'error': str(e),
                'error_type': type(e).__name__
            }
    
    async def restart_monitoring(self) -> None:
        """Restart the local services monitoring."""
        try:
            log_info_structured(
                service="local_services_integration",
                operation="restart_monitoring",
                message="Restarting local services monitoring",
                tags={'category': 'integration', 'action': 'restart'}
            )
            
            # Stop current monitoring
            await self.stop_integration()
            
            # Wait a moment
            await asyncio.sleep(2)
            
            # Start monitoring again
            await self.start_integration()
            
            log_info_structured(
                service="local_services_integration",
                operation="restart_monitoring_complete",
                message="Successfully restarted local services monitoring",
                tags={'category': 'integration', 'action': 'restart_complete'}
            )
        
        except Exception as e:
            log_error_structured(
                service="local_services_integration",
                operation="restart_monitoring_error",
                message=f"Failed to restart monitoring: {str(e)}",
                error_type=type(e).__name__,
                stack_trace=str(e),
                tags={'category': 'integration_error', 'action': 'restart_failed'}
            )
            raise


# Global integration instance
_local_services_integration: Optional[LocalServicesLoggingIntegration] = None


def get_local_services_integration() -> LocalServicesLoggingIntegration:
    """Get the global local services logging integration instance."""
    global _local_services_integration
    if _local_services_integration is None:
        _local_services_integration = LocalServicesLoggingIntegration()
    return _local_services_integration


@asynccontextmanager
async def local_services_logging_lifespan():
    """Context manager for local services logging lifecycle."""
    integration = get_local_services_integration()
    
    try:
        # Start integration
        await integration.start_integration()
        yield integration
    finally:
        # Stop integration
        await integration.stop_integration()


async def start_local_services_integration() -> None:
    """Start the local services logging integration."""
    integration = get_local_services_integration()
    await integration.start_integration()


async def stop_local_services_integration() -> None:
    """Stop the local services logging integration."""
    integration = get_local_services_integration()
    await integration.stop_integration()


def get_local_services_status() -> Dict[str, Any]:
    """Get the status of local services logging."""
    integration = get_local_services_integration()
    return integration.get_integration_status()


async def restart_local_services_monitoring() -> None:
    """Restart local services monitoring."""
    integration = get_local_services_integration()
    await integration.restart_monitoring()