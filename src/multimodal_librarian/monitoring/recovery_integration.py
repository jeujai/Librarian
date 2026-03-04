"""
Recovery Integration Module - Connects recovery workflows with health monitoring.

This module provides integration between:
- Health monitoring system
- Recovery workflow manager
- Error logging service
- Recovery notification service

It automatically triggers recovery workflows based on health status changes
and error patterns, providing seamless automatic recovery capabilities.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
import threading

from ..config import get_settings
from ..logging_config import get_logger
from .service_health_monitor import ServiceHealthMonitor, HealthStatus
from .health_check_system import get_health_check_system
from .error_logging_service import get_error_logging_service, ErrorCategory, ErrorSeverity
from .recovery_workflow_manager import get_recovery_workflow_manager, RecoveryPriority
from .recovery_notification_service import (
    get_recovery_notification_service, 
    RecoveryNotificationType, 
    RecoveryNotificationPriority
)


@dataclass
class RecoveryTrigger:
    """Recovery trigger configuration."""
    trigger_id: str
    name: str
    description: str
    service_name: str
    conditions: Dict[str, Any]
    recovery_priority: RecoveryPriority
    enabled: bool = True


class RecoveryIntegrationService:
    """
    Integration service that connects health monitoring with recovery workflows.
    
    Automatically triggers recovery workflows based on:
    - Health status changes
    - Error patterns and thresholds
    - Service failure conditions
    - Performance degradation
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = get_logger("recovery_integration")
        
        # Service dependencies
        self.health_check_system = get_health_check_system()
        self.error_logging_service = get_error_logging_service()
        self.recovery_workflow_manager = get_recovery_workflow_manager()
        self.recovery_notification_service = get_recovery_notification_service()
        
        # Integration state
        self._integration_active = False
        self._monitoring_task = None
        self._trigger_conditions: Dict[str, RecoveryTrigger] = {}
        
        # Tracking
        self._last_health_status: Dict[str, HealthStatus] = {}
        self._error_pattern_tracking: Dict[str, Dict[str, Any]] = {}
        self._recovery_cooldowns: Dict[str, datetime] = {}
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Initialize default triggers
        self._initialize_default_triggers()
        
        # Register health callbacks
        self._register_health_callbacks()
        
        self.logger.info("Recovery integration service initialized")
    
    def _initialize_default_triggers(self) -> None:
        """Initialize default recovery triggers."""
        
        # Database service triggers
        self.add_recovery_trigger(RecoveryTrigger(
            trigger_id="database_consecutive_failures",
            name="Database Consecutive Failures",
            description="Trigger recovery after consecutive database failures",
            service_name="database",
            conditions={
                "consecutive_failures": 3,
                "error_categories": [ErrorCategory.DATABASE_ERROR.value],
                "health_status": [HealthStatus.UNHEALTHY.value, HealthStatus.CRITICAL.value]
            },
            recovery_priority=RecoveryPriority.HIGH
        ))
        
        # Search service triggers
        self.add_recovery_trigger(RecoveryTrigger(
            trigger_id="search_service_degradation",
            name="Search Service Degradation",
            description="Trigger recovery when search service degrades",
            service_name="search_service",
            conditions={
                "consecutive_failures": 5,
                "error_categories": [ErrorCategory.SERVICE_FAILURE.value],
                "health_status": [HealthStatus.DEGRADED.value, HealthStatus.UNHEALTHY.value]
            },
            recovery_priority=RecoveryPriority.MEDIUM
        ))
        
        # Vector store triggers
        self.add_recovery_trigger(RecoveryTrigger(
            trigger_id="vector_store_connection_failure",
            name="Vector Store Connection Failure",
            description="Trigger recovery for vector store connection issues",
            service_name="vector_store",
            conditions={
                "consecutive_failures": 3,
                "error_categories": [ErrorCategory.SERVICE_FAILURE.value, ErrorCategory.NETWORK_ERROR.value],
                "health_status": [HealthStatus.CRITICAL.value, HealthStatus.DOWN.value]
            },
            recovery_priority=RecoveryPriority.HIGH
        ))
        
        # AI service triggers
        self.add_recovery_trigger(RecoveryTrigger(
            trigger_id="ai_service_timeout",
            name="AI Service Timeout",
            description="Trigger recovery for AI service timeouts",
            service_name="ai_services",
            conditions={
                "consecutive_failures": 4,
                "error_categories": [ErrorCategory.EXTERNAL_SERVICE_ERROR.value, ErrorCategory.NETWORK_ERROR.value],
                "health_status": [HealthStatus.UNHEALTHY.value]
            },
            recovery_priority=RecoveryPriority.MEDIUM
        ))
        
        # Cache service triggers
        self.add_recovery_trigger(RecoveryTrigger(
            trigger_id="cache_service_failure",
            name="Cache Service Failure",
            description="Trigger recovery for cache service failures",
            service_name="cache",
            conditions={
                "consecutive_failures": 5,
                "error_categories": [ErrorCategory.SERVICE_FAILURE.value],
                "health_status": [HealthStatus.DEGRADED.value, HealthStatus.UNHEALTHY.value]
            },
            recovery_priority=RecoveryPriority.LOW
        ))
        
        # System resource triggers
        self.add_recovery_trigger(RecoveryTrigger(
            trigger_id="memory_exhaustion",
            name="Memory Exhaustion",
            description="Trigger recovery for memory exhaustion",
            service_name="system_resources",
            conditions={
                "error_categories": [ErrorCategory.RESOURCE_EXHAUSTION.value],
                "error_severity": [ErrorSeverity.CRITICAL.value]
            },
            recovery_priority=RecoveryPriority.CRITICAL
        ))
    
    def _register_health_callbacks(self) -> None:
        """Register callbacks with health monitoring system."""
        
        # Register with service health monitor
        health_monitor = self.health_check_system.health_monitor
        
        async def on_health_status_change(service_name: str, new_status: HealthStatus) -> None:
            """Handle health status changes."""
            await self._handle_health_status_change(service_name, new_status)
        
        # Register callback for all monitored services
        services = ["database", "vector_store", "search_service", "ai_services", "cache", "system_resources"]
        for service in services:
            health_monitor.register_health_callback(service, on_health_status_change)
    
    def add_recovery_trigger(self, trigger: RecoveryTrigger) -> bool:
        """Add a recovery trigger."""
        try:
            with self._lock:
                self._trigger_conditions[trigger.trigger_id] = trigger
            
            self.logger.info(f"Added recovery trigger: {trigger.name} for service: {trigger.service_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add recovery trigger: {e}")
            return False
    
    def remove_recovery_trigger(self, trigger_id: str) -> bool:
        """Remove a recovery trigger."""
        try:
            with self._lock:
                if trigger_id in self._trigger_conditions:
                    trigger = self._trigger_conditions[trigger_id]
                    del self._trigger_conditions[trigger_id]
                    self.logger.info(f"Removed recovery trigger: {trigger.name}")
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to remove recovery trigger: {e}")
            return False
    
    async def _handle_health_status_change(self, service_name: str, new_status: HealthStatus) -> None:
        """Handle health status changes and trigger recovery if needed."""
        
        with self._lock:
            old_status = self._last_health_status.get(service_name, HealthStatus.UNKNOWN)
            self._last_health_status[service_name] = new_status
        
        # Log status change
        self.logger.info(f"Health status changed for {service_name}: {old_status.value} -> {new_status.value}")
        
        # Check if recovery should be triggered
        if await self._should_trigger_recovery_for_health_change(service_name, old_status, new_status):
            await self._trigger_recovery_for_service(
                service_name, 
                f"Health status changed to {new_status.value}",
                health_status=new_status
            )
    
    async def _should_trigger_recovery_for_health_change(self, service_name: str, 
                                                       old_status: HealthStatus, 
                                                       new_status: HealthStatus) -> bool:
        """Determine if recovery should be triggered based on health status change."""
        
        # Don't trigger recovery for improvements
        if new_status.value < old_status.value:  # Assuming lower enum values are better
            return False
        
        # Check cooldown period
        if self._is_in_recovery_cooldown(service_name):
            self.logger.info(f"Service {service_name} is in recovery cooldown, skipping trigger")
            return False
        
        # Check if any triggers apply
        with self._lock:
            applicable_triggers = [
                trigger for trigger in self._trigger_conditions.values()
                if (trigger.service_name == service_name and 
                    trigger.enabled and
                    new_status.value in trigger.conditions.get("health_status", []))
            ]
        
        return len(applicable_triggers) > 0
    
    def _is_in_recovery_cooldown(self, service_name: str) -> bool:
        """Check if service is in recovery cooldown period."""
        
        if service_name not in self._recovery_cooldowns:
            return False
        
        cooldown_end = self._recovery_cooldowns[service_name]
        return datetime.now() < cooldown_end
    
    async def _trigger_recovery_for_service(self, service_name: str, trigger_reason: str,
                                          health_status: Optional[HealthStatus] = None,
                                          error_category: Optional[ErrorCategory] = None) -> None:
        """Trigger recovery workflows for a service."""
        
        # Find applicable triggers
        with self._lock:
            applicable_triggers = [
                trigger for trigger in self._trigger_conditions.values()
                if trigger.service_name == service_name and trigger.enabled
            ]
        
        if not applicable_triggers:
            self.logger.info(f"No recovery triggers found for service: {service_name}")
            return
        
        # Get service health information
        service_health = self.health_check_system.health_monitor.get_service_health(service_name)
        
        # Check trigger conditions
        for trigger in applicable_triggers:
            if await self._check_trigger_conditions(trigger, service_health, health_status, error_category):
                # Determine recovery priority
                priority = trigger.recovery_priority
                
                # Send notification about recovery trigger
                await self.recovery_notification_service.send_recovery_notification(
                    notification_type=RecoveryNotificationType.RECOVERY_STARTED,
                    service_name=service_name,
                    workflow_id="auto_triggered",
                    attempt_id="pending",
                    title=f"Recovery Triggered: {trigger.name}",
                    message=f"Recovery workflow triggered for {service_name}: {trigger_reason}",
                    priority=self._map_recovery_priority_to_notification_priority(priority),
                    metadata={
                        'trigger_id': trigger.trigger_id,
                        'trigger_reason': trigger_reason,
                        'service_health': service_health
                    }
                )
                
                # Trigger recovery workflow
                attempt_ids = await self.recovery_workflow_manager.trigger_recovery(
                    service_name=service_name,
                    trigger_reason=f"{trigger.name}: {trigger_reason}",
                    health_status=health_status,
                    error_category=error_category,
                    priority=priority
                )
                
                if attempt_ids:
                    # Set recovery cooldown
                    self._recovery_cooldowns[service_name] = datetime.now() + timedelta(minutes=30)
                    
                    self.logger.info(f"Triggered recovery for {service_name}: {len(attempt_ids)} attempts started")
                else:
                    self.logger.warning(f"Failed to trigger recovery for {service_name}")
    
    async def _check_trigger_conditions(self, trigger: RecoveryTrigger, 
                                      service_health: Dict[str, Any],
                                      health_status: Optional[HealthStatus],
                                      error_category: Optional[ErrorCategory]) -> bool:
        """Check if trigger conditions are met."""
        
        conditions = trigger.conditions
        
        # Check health status condition
        if "health_status" in conditions and health_status:
            if health_status.value not in conditions["health_status"]:
                return False
        
        # Check error category condition
        if "error_categories" in conditions and error_category:
            if error_category.value not in conditions["error_categories"]:
                return False
        
        # Check consecutive failures condition
        if "consecutive_failures" in conditions:
            consecutive_failures = service_health.get("statistics", {}).get("consecutive_failures", 0)
            if consecutive_failures < conditions["consecutive_failures"]:
                return False
        
        # Check error severity condition
        if "error_severity" in conditions:
            # This would require additional error context
            # For now, we'll assume it's met if error_category is provided
            if not error_category:
                return False
        
        return True
    
    def _map_recovery_priority_to_notification_priority(self, 
                                                       recovery_priority: RecoveryPriority) -> RecoveryNotificationPriority:
        """Map recovery priority to notification priority."""
        
        mapping = {
            RecoveryPriority.LOW: RecoveryNotificationPriority.LOW,
            RecoveryPriority.MEDIUM: RecoveryNotificationPriority.MEDIUM,
            RecoveryPriority.HIGH: RecoveryNotificationPriority.HIGH,
            RecoveryPriority.CRITICAL: RecoveryNotificationPriority.CRITICAL
        }
        
        return mapping.get(recovery_priority, RecoveryNotificationPriority.MEDIUM)
    
    async def monitor_error_patterns(self) -> None:
        """Monitor error patterns and trigger recovery if needed."""
        
        # Get recent error summary
        error_summary = self.error_logging_service.get_error_summary(hours=1)
        
        # Check for error pattern triggers
        for service_name, error_count in error_summary.get("errors_by_service", {}).items():
            if error_count >= 5:  # Threshold for error-based recovery
                
                # Check if we should trigger recovery
                if not self._is_in_recovery_cooldown(service_name):
                    
                    # Determine error category
                    error_categories = error_summary.get("error_categories", {})
                    primary_category = max(error_categories.items(), key=lambda x: x[1])[0] if error_categories else None
                    
                    if primary_category:
                        error_category = ErrorCategory(primary_category)
                        
                        await self._trigger_recovery_for_service(
                            service_name=service_name,
                            trigger_reason=f"High error rate: {error_count} errors in last hour",
                            error_category=error_category
                        )
    
    async def validate_recovery_success(self, service_name: str, attempt_id: str) -> bool:
        """Validate that recovery was successful."""
        
        try:
            # Run health check for the service
            health_report = await self.health_check_system.run_all_checks()
            
            # Check if service is now healthy
            service_result = health_report.results.get(service_name)
            if service_result:
                status = HealthStatus(service_result.get('status', 'unknown'))
                
                if status == HealthStatus.HEALTHY:
                    # Send success notification
                    await self.recovery_notification_service.send_recovery_notification(
                        notification_type=RecoveryNotificationType.RECOVERY_SUCCESS,
                        service_name=service_name,
                        workflow_id="validation",
                        attempt_id=attempt_id,
                        title=f"Recovery Validated: {service_name}",
                        message=f"Recovery validation successful for {service_name}. Service is now healthy.",
                        priority=RecoveryNotificationPriority.LOW,
                        metadata={'validation_status': status.value}
                    )
                    
                    return True
                else:
                    # Send failure notification
                    await self.recovery_notification_service.send_recovery_notification(
                        notification_type=RecoveryNotificationType.RECOVERY_FAILED,
                        service_name=service_name,
                        workflow_id="validation",
                        attempt_id=attempt_id,
                        title=f"Recovery Validation Failed: {service_name}",
                        message=f"Recovery validation failed for {service_name}. Service status: {status.value}",
                        priority=RecoveryNotificationPriority.HIGH,
                        metadata={'validation_status': status.value}
                    )
                    
                    return False
            
            return False
            
        except Exception as e:
            self.logger.error(f"Recovery validation failed for {service_name}: {e}")
            return False
    
    def start_integration(self) -> None:
        """Start the recovery integration service."""
        
        if self._integration_active:
            self.logger.warning("Recovery integration is already active")
            return
        
        self._integration_active = True
        self._monitoring_task = asyncio.create_task(self._background_monitoring())
        
        # Start dependent services
        self.health_check_system.start_monitoring(interval=60)
        self.recovery_workflow_manager.start_processing()
        
        self.logger.info("Started recovery integration service")
    
    def stop_integration(self) -> None:
        """Stop the recovery integration service."""
        
        self._integration_active = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
        
        # Stop dependent services
        self.health_check_system.stop_monitoring()
        self.recovery_workflow_manager.stop_processing()
        
        self.logger.info("Stopped recovery integration service")
    
    async def _background_monitoring(self) -> None:
        """Background monitoring task."""
        
        while self._integration_active:
            try:
                # Monitor error patterns
                await self.monitor_error_patterns()
                
                # Clean up old cooldowns
                current_time = datetime.now()
                expired_cooldowns = [
                    service for service, cooldown_end in self._recovery_cooldowns.items()
                    if current_time >= cooldown_end
                ]
                
                for service in expired_cooldowns:
                    del self._recovery_cooldowns[service]
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Exception in recovery integration monitoring: {e}")
                await asyncio.sleep(300)
    
    def get_integration_status(self) -> Dict[str, Any]:
        """Get recovery integration status."""
        
        with self._lock:
            return {
                'integration_active': self._integration_active,
                'registered_triggers': len(self._trigger_conditions),
                'active_cooldowns': len(self._recovery_cooldowns),
                'triggers': [
                    {
                        'trigger_id': trigger.trigger_id,
                        'name': trigger.name,
                        'service_name': trigger.service_name,
                        'enabled': trigger.enabled,
                        'priority': trigger.recovery_priority.value
                    }
                    for trigger in self._trigger_conditions.values()
                ],
                'cooldowns': {
                    service: cooldown_end.isoformat()
                    for service, cooldown_end in self._recovery_cooldowns.items()
                },
                'last_health_status': {
                    service: status.value
                    for service, status in self._last_health_status.items()
                }
            }
    
    def get_recovery_metrics(self) -> Dict[str, Any]:
        """Get recovery integration metrics."""
        
        # Get metrics from dependent services
        recovery_stats = self.recovery_workflow_manager.get_recovery_statistics()
        notification_stats = self.recovery_notification_service.get_notification_statistics()
        
        return {
            'recovery_workflows': recovery_stats,
            'recovery_notifications': notification_stats,
            'integration_status': self.get_integration_status()
        }


# Global recovery integration service instance
_recovery_integration_service = None


def get_recovery_integration_service() -> RecoveryIntegrationService:
    """Get the global recovery integration service instance."""
    global _recovery_integration_service
    if _recovery_integration_service is None:
        _recovery_integration_service = RecoveryIntegrationService()
    return _recovery_integration_service


# Convenience functions
async def trigger_manual_recovery(service_name: str, reason: str, 
                                priority: RecoveryPriority = RecoveryPriority.MEDIUM) -> List[str]:
    """Manually trigger recovery for a service."""
    integration_service = get_recovery_integration_service()
    return await integration_service.recovery_workflow_manager.trigger_recovery(
        service_name=service_name,
        trigger_reason=f"Manual trigger: {reason}",
        priority=priority
    )


async def validate_service_recovery(service_name: str, attempt_id: str) -> bool:
    """Validate that service recovery was successful."""
    integration_service = get_recovery_integration_service()
    return await integration_service.validate_recovery_success(service_name, attempt_id)