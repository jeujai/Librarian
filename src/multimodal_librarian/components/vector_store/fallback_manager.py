"""
Fallback Manager for Search Services.

This module provides health monitoring, automatic fallback detection, and notification
for search service failures to ensure system reliability.
"""

import logging
import asyncio
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
import uuid

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """Service status enumeration."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNKNOWN = "unknown"


class FallbackReason(Enum):
    """Reasons for fallback activation."""
    HEALTH_CHECK_FAILED = "health_check_failed"
    RESPONSE_TIME_EXCEEDED = "response_time_exceeded"
    ERROR_RATE_EXCEEDED = "error_rate_exceeded"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    MANUAL_TRIGGER = "manual_trigger"


@dataclass
class HealthMetrics:
    """Health metrics for a service."""
    service_name: str
    status: ServiceStatus
    last_check: datetime
    response_time_ms: float
    error_rate: float
    success_rate: float
    total_requests: int
    failed_requests: int
    uptime_percentage: float
    memory_usage_mb: Optional[float] = None
    cpu_usage_percent: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'service_name': self.service_name,
            'status': self.status.value,
            'last_check': self.last_check.isoformat(),
            'response_time_ms': self.response_time_ms,
            'error_rate': self.error_rate,
            'success_rate': self.success_rate,
            'total_requests': self.total_requests,
            'failed_requests': self.failed_requests,
            'uptime_percentage': self.uptime_percentage,
            'memory_usage_mb': self.memory_usage_mb,
            'cpu_usage_percent': self.cpu_usage_percent
        }


@dataclass
class FallbackEvent:
    """Fallback event information."""
    event_id: str
    timestamp: datetime
    service_name: str
    reason: FallbackReason
    metrics: HealthMetrics
    fallback_service: str
    message: str
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'event_id': self.event_id,
            'timestamp': self.timestamp.isoformat(),
            'service_name': self.service_name,
            'reason': self.reason.value,
            'metrics': self.metrics.to_dict(),
            'fallback_service': self.fallback_service,
            'message': self.message,
            'resolved': self.resolved,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None
        }


@dataclass
class FallbackConfig:
    """Configuration for fallback detection."""
    # Health check intervals
    health_check_interval_seconds: int = 30
    health_check_timeout_seconds: int = 5
    
    # Performance thresholds
    max_response_time_ms: float = 2000.0
    max_error_rate: float = 0.1  # 10%
    min_success_rate: float = 0.9  # 90%
    
    # Failure detection
    consecutive_failures_threshold: int = 3
    failure_window_minutes: int = 5
    
    # Recovery detection
    consecutive_successes_threshold: int = 5
    recovery_window_minutes: int = 2
    
    # Resource thresholds
    max_memory_usage_mb: Optional[float] = 2048.0
    max_cpu_usage_percent: Optional[float] = 80.0
    
    # Notification settings
    enable_notifications: bool = True
    notification_cooldown_minutes: int = 15


class FallbackManager:
    """
    Manages fallback detection and automatic service switching.
    
    Provides health monitoring, automatic fallback triggers, and notifications
    for search service failures.
    """
    
    def __init__(self, config: Optional[FallbackConfig] = None):
        """
        Initialize fallback manager.
        
        Args:
            config: Fallback configuration
        """
        self.config = config or FallbackConfig()
        
        # Service registry
        self.services: Dict[str, Any] = {}
        self.service_metrics: Dict[str, HealthMetrics] = {}
        self.service_history: Dict[str, List[HealthMetrics]] = {}
        
        # Fallback state
        self.active_fallbacks: Dict[str, FallbackEvent] = {}
        self.fallback_history: List[FallbackEvent] = []
        
        # Notification callbacks
        self.notification_callbacks: List[Callable[[FallbackEvent], None]] = []
        self.last_notification: Dict[str, datetime] = {}
        
        # Monitoring task
        self._monitoring_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        logger.info("Fallback manager initialized")
    
    def register_service(self, name: str, service: Any, is_primary: bool = False) -> None:
        """
        Register a service for monitoring.
        
        Args:
            name: Service name
            service: Service instance
            is_primary: Whether this is the primary service
        """
        self.services[name] = {
            'instance': service,
            'is_primary': is_primary,
            'registered_at': datetime.now()
        }
        
        # Initialize metrics
        self.service_metrics[name] = HealthMetrics(
            service_name=name,
            status=ServiceStatus.UNKNOWN,
            last_check=datetime.now(),
            response_time_ms=0.0,
            error_rate=0.0,
            success_rate=1.0,
            total_requests=0,
            failed_requests=0,
            uptime_percentage=100.0
        )
        
        self.service_history[name] = []
        
        logger.info(f"Registered service '{name}' (primary: {is_primary})")
    
    def add_notification_callback(self, callback: Callable[[FallbackEvent], None]) -> None:
        """
        Add a notification callback for fallback events.
        
        Args:
            callback: Function to call when fallback events occur
        """
        self.notification_callbacks.append(callback)
        logger.info("Added notification callback")
    
    async def start_monitoring(self) -> None:
        """Start the health monitoring task."""
        if self._monitoring_task and not self._monitoring_task.done():
            logger.warning("Monitoring already running")
            return
        
        self._shutdown_event.clear()
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Started health monitoring")
    
    async def stop_monitoring(self) -> None:
        """Stop the health monitoring task."""
        self._shutdown_event.set()
        
        if self._monitoring_task:
            try:
                await asyncio.wait_for(self._monitoring_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._monitoring_task.cancel()
                logger.warning("Monitoring task cancelled due to timeout")
        
        logger.info("Stopped health monitoring")
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        logger.info("Health monitoring loop started")
        
        while not self._shutdown_event.is_set():
            try:
                # Check all registered services
                for service_name in self.services.keys():
                    await self._check_service_health(service_name)
                
                # Wait for next check interval
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.config.health_check_interval_seconds
                )
                
            except asyncio.TimeoutError:
                # Normal timeout, continue monitoring
                continue
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(5)  # Brief pause before retrying
        
        logger.info("Health monitoring loop stopped")
    
    async def _check_service_health(self, service_name: str) -> None:
        """
        Check health of a specific service.
        
        Args:
            service_name: Name of service to check
        """
        if service_name not in self.services:
            logger.warning(f"Service '{service_name}' not registered")
            return
        
        service_info = self.services[service_name]
        service = service_info['instance']
        
        start_time = datetime.now()
        is_healthy = False
        
        try:
            # Perform health check with timeout
            health_check_result = await asyncio.wait_for(
                self._perform_health_check(service),
                timeout=self.config.health_check_timeout_seconds
            )
            
            response_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            is_healthy = health_check_result
            
            # Update metrics
            await self._update_service_metrics(
                service_name, 
                is_healthy, 
                response_time_ms
            )
            
        except asyncio.TimeoutError:
            response_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            logger.warning(f"Health check timeout for service '{service_name}'")
            await self._update_service_metrics(service_name, False, response_time_ms)
            await self._handle_service_failure(
                service_name, 
                FallbackReason.RESPONSE_TIME_EXCEEDED,
                "Health check timeout"
            )
            
        except Exception as e:
            response_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            logger.error(f"Health check failed for service '{service_name}': {e}")
            await self._update_service_metrics(service_name, False, response_time_ms)
            await self._handle_service_failure(
                service_name,
                FallbackReason.HEALTH_CHECK_FAILED,
                str(e)
            )
    
    async def _perform_health_check(self, service: Any) -> bool:
        """
        Perform health check on a service.
        
        Args:
            service: Service instance to check
            
        Returns:
            True if healthy, False otherwise
        """
        # Try different health check methods
        if hasattr(service, 'health_check'):
            if asyncio.iscoroutinefunction(service.health_check):
                return await service.health_check()
            else:
                return service.health_check()
        
        # Fallback: try a basic operation
        if hasattr(service, 'get_performance_stats'):
            service.get_performance_stats()
            return True
        
        # If no health check method available, assume healthy
        logger.debug(f"No health check method available for service, assuming healthy")
        return True
    
    async def _update_service_metrics(
        self, 
        service_name: str, 
        is_healthy: bool, 
        response_time_ms: float
    ) -> None:
        """
        Update service metrics based on health check result.
        
        Args:
            service_name: Name of the service
            is_healthy: Whether the service is healthy
            response_time_ms: Response time in milliseconds
        """
        current_metrics = self.service_metrics[service_name]
        
        # Update basic metrics
        current_metrics.last_check = datetime.now()
        current_metrics.response_time_ms = response_time_ms
        current_metrics.total_requests += 1
        
        if not is_healthy:
            current_metrics.failed_requests += 1
        
        # Calculate rates
        if current_metrics.total_requests > 0:
            current_metrics.error_rate = current_metrics.failed_requests / current_metrics.total_requests
            current_metrics.success_rate = 1.0 - current_metrics.error_rate
        
        # Determine status
        if is_healthy and response_time_ms <= self.config.max_response_time_ms:
            if current_metrics.error_rate <= self.config.max_error_rate:
                current_metrics.status = ServiceStatus.HEALTHY
            else:
                current_metrics.status = ServiceStatus.DEGRADED
        else:
            current_metrics.status = ServiceStatus.FAILED
        
        # Create a copy for history to avoid reference issues
        history_entry = HealthMetrics(
            service_name=current_metrics.service_name,
            status=current_metrics.status,
            last_check=current_metrics.last_check,
            response_time_ms=current_metrics.response_time_ms,
            error_rate=current_metrics.error_rate,
            success_rate=current_metrics.success_rate,
            total_requests=current_metrics.total_requests,
            failed_requests=current_metrics.failed_requests,
            uptime_percentage=current_metrics.uptime_percentage,
            memory_usage_mb=current_metrics.memory_usage_mb,
            cpu_usage_percent=current_metrics.cpu_usage_percent
        )
        
        # Add to history
        self.service_history[service_name].append(history_entry)
        
        # Keep only recent history (last 100 entries)
        if len(self.service_history[service_name]) > 100:
            self.service_history[service_name] = self.service_history[service_name][-100:]
        
        # Check for fallback conditions
        await self._evaluate_fallback_conditions(service_name)
    
    async def _evaluate_fallback_conditions(self, service_name: str) -> None:
        """
        Evaluate whether fallback should be triggered for a service.
        
        Args:
            service_name: Name of the service to evaluate
        """
        metrics = self.service_metrics[service_name]
        
        # Skip if already in fallback
        if service_name in self.active_fallbacks:
            await self._evaluate_recovery_conditions(service_name)
            return
        
        # Check various fallback conditions
        fallback_reason = None
        message = ""
        
        # Response time threshold
        if metrics.response_time_ms > self.config.max_response_time_ms:
            fallback_reason = FallbackReason.RESPONSE_TIME_EXCEEDED
            message = f"Response time {metrics.response_time_ms:.1f}ms exceeds threshold {self.config.max_response_time_ms}ms"
        
        # Error rate threshold
        elif metrics.error_rate > self.config.max_error_rate:
            fallback_reason = FallbackReason.ERROR_RATE_EXCEEDED
            message = f"Error rate {metrics.error_rate:.1%} exceeds threshold {self.config.max_error_rate:.1%}"
        
        # Service status
        elif metrics.status == ServiceStatus.FAILED:
            fallback_reason = FallbackReason.HEALTH_CHECK_FAILED
            message = "Service health check failed"
        
        # Consecutive failures - check if we have enough history and all recent entries are failures
        elif self._check_consecutive_failures(service_name):
            fallback_reason = FallbackReason.HEALTH_CHECK_FAILED
            message = f"Consecutive failures exceeded threshold ({self.config.consecutive_failures_threshold})"
        
        # Trigger fallback if conditions met
        if fallback_reason:
            await self._handle_service_failure(service_name, fallback_reason, message)
    
    async def _evaluate_recovery_conditions(self, service_name: str) -> None:
        """
        Evaluate whether a service has recovered from fallback.
        
        Args:
            service_name: Name of the service to evaluate
        """
        metrics = self.service_metrics[service_name]
        
        # Check recovery conditions
        if (metrics.status == ServiceStatus.HEALTHY and 
            metrics.response_time_ms <= self.config.max_response_time_ms and
            metrics.error_rate <= self.config.max_error_rate and
            self._check_consecutive_successes(service_name)):
            
            await self._handle_service_recovery(service_name)
    
    def _check_consecutive_failures(self, service_name: str) -> bool:
        """
        Check if service has consecutive failures exceeding threshold.
        
        Args:
            service_name: Name of the service
            
        Returns:
            True if consecutive failures exceed threshold
        """
        history = self.service_history[service_name]
        if len(history) < self.config.consecutive_failures_threshold:
            return False
        
        # Check recent entries
        recent_entries = history[-self.config.consecutive_failures_threshold:]
        return all(entry.status == ServiceStatus.FAILED for entry in recent_entries)
    
    def _check_consecutive_successes(self, service_name: str) -> bool:
        """
        Check if service has consecutive successes exceeding threshold.
        
        Args:
            service_name: Name of the service
            
        Returns:
            True if consecutive successes exceed threshold
        """
        history = self.service_history[service_name]
        if len(history) < self.config.consecutive_successes_threshold:
            return False
        
        # Check recent entries
        recent_entries = history[-self.config.consecutive_successes_threshold:]
        return all(entry.status == ServiceStatus.HEALTHY for entry in recent_entries)
    
    async def _handle_service_failure(
        self, 
        service_name: str, 
        reason: FallbackReason, 
        message: str
    ) -> None:
        """
        Handle service failure by triggering fallback.
        
        Args:
            service_name: Name of the failed service
            reason: Reason for fallback
            message: Descriptive message
        """
        if service_name in self.active_fallbacks:
            return  # Already in fallback
        
        # Find fallback service
        fallback_service = self._find_fallback_service(service_name)
        if not fallback_service:
            logger.error(f"No fallback service available for '{service_name}'")
            return
        
        # Create fallback event
        event = FallbackEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            service_name=service_name,
            reason=reason,
            metrics=self.service_metrics[service_name],
            fallback_service=fallback_service,
            message=message
        )
        
        # Activate fallback
        self.active_fallbacks[service_name] = event
        self.fallback_history.append(event)
        
        logger.warning(f"Fallback activated for '{service_name}': {message}")
        
        # Send notifications
        await self._send_notifications(event)
    
    async def _handle_service_recovery(self, service_name: str) -> None:
        """
        Handle service recovery from fallback.
        
        Args:
            service_name: Name of the recovered service
        """
        if service_name not in self.active_fallbacks:
            return  # Not in fallback
        
        # Mark event as resolved
        event = self.active_fallbacks[service_name]
        event.resolved = True
        event.resolved_at = datetime.now()
        
        # Remove from active fallbacks
        del self.active_fallbacks[service_name]
        
        logger.info(f"Service '{service_name}' recovered from fallback")
        
        # Send recovery notification
        await self._send_notifications(event)
    
    def _find_fallback_service(self, failed_service: str) -> Optional[str]:
        """
        Find an appropriate fallback service.
        
        Args:
            failed_service: Name of the failed service
            
        Returns:
            Name of fallback service or None if not available
        """
        # Simple strategy: find any healthy non-primary service
        for name, info in self.services.items():
            if (name != failed_service and 
                name not in self.active_fallbacks and
                self.service_metrics[name].status == ServiceStatus.HEALTHY):
                return name
        
        # If no healthy service, return any available service
        for name, info in self.services.items():
            if name != failed_service and name not in self.active_fallbacks:
                return name
        
        return None
    
    async def _send_notifications(self, event: FallbackEvent) -> None:
        """
        Send notifications for fallback events.
        
        Args:
            event: Fallback event to notify about
        """
        if not self.config.enable_notifications:
            return
        
        # Check notification cooldown
        cooldown_key = f"{event.service_name}_{event.reason.value}"
        now = datetime.now()
        
        if cooldown_key in self.last_notification:
            time_since_last = now - self.last_notification[cooldown_key]
            if time_since_last < timedelta(minutes=self.config.notification_cooldown_minutes):
                return  # Still in cooldown
        
        # Update last notification time
        self.last_notification[cooldown_key] = now
        
        # Send notifications
        for callback in self.notification_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"Notification callback failed: {e}")
    
    def get_service_status(self, service_name: str) -> Optional[HealthMetrics]:
        """
        Get current status of a service.
        
        Args:
            service_name: Name of the service
            
        Returns:
            Current health metrics or None if not found
        """
        return self.service_metrics.get(service_name)
    
    def get_all_service_status(self) -> Dict[str, HealthMetrics]:
        """Get status of all registered services."""
        return self.service_metrics.copy()
    
    def get_active_fallbacks(self) -> Dict[str, FallbackEvent]:
        """Get all active fallback events."""
        return self.active_fallbacks.copy()
    
    def get_fallback_history(self, hours: int = 24) -> List[FallbackEvent]:
        """
        Get fallback history for the specified time period.
        
        Args:
            hours: Number of hours to look back
            
        Returns:
            List of fallback events
        """
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [
            event for event in self.fallback_history 
            if event.timestamp >= cutoff_time
        ]
    
    def is_service_in_fallback(self, service_name: str) -> bool:
        """
        Check if a service is currently in fallback mode.
        
        Args:
            service_name: Name of the service
            
        Returns:
            True if service is in fallback
        """
        return service_name in self.active_fallbacks
    
    def get_fallback_statistics(self) -> Dict[str, Any]:
        """Get fallback statistics and metrics."""
        total_events = len(self.fallback_history)
        active_events = len(self.active_fallbacks)
        
        # Calculate statistics by reason
        reason_stats = {}
        for event in self.fallback_history:
            reason = event.reason.value
            if reason not in reason_stats:
                reason_stats[reason] = {'count': 0, 'resolved': 0}
            reason_stats[reason]['count'] += 1
            if event.resolved:
                reason_stats[reason]['resolved'] += 1
        
        return {
            'total_fallback_events': total_events,
            'active_fallbacks': active_events,
            'registered_services': len(self.services),
            'healthy_services': sum(
                1 for metrics in self.service_metrics.values() 
                if metrics.status == ServiceStatus.HEALTHY
            ),
            'reason_statistics': reason_stats,
            'average_recovery_time_minutes': self._calculate_average_recovery_time()
        }
    
    def _calculate_average_recovery_time(self) -> Optional[float]:
        """Calculate average recovery time for resolved events."""
        resolved_events = [
            event for event in self.fallback_history 
            if event.resolved and event.resolved_at
        ]
        
        if not resolved_events:
            return None
        
        total_time = sum(
            (event.resolved_at - event.timestamp).total_seconds() 
            for event in resolved_events
        )
        
        return total_time / len(resolved_events) / 60  # Convert to minutes
    
    async def manual_fallback(self, service_name: str, message: str = "Manual fallback triggered") -> bool:
        """
        Manually trigger fallback for a service.
        
        Args:
            service_name: Name of the service
            message: Reason for manual fallback
            
        Returns:
            True if fallback was triggered successfully
        """
        if service_name not in self.services:
            logger.error(f"Service '{service_name}' not registered")
            return False
        
        if service_name in self.active_fallbacks:
            logger.warning(f"Service '{service_name}' already in fallback")
            return False
        
        await self._handle_service_failure(
            service_name,
            FallbackReason.MANUAL_TRIGGER,
            message
        )
        
        return True
    
    async def manual_recovery(self, service_name: str) -> bool:
        """
        Manually trigger recovery for a service.
        
        Args:
            service_name: Name of the service
            
        Returns:
            True if recovery was triggered successfully
        """
        if service_name not in self.active_fallbacks:
            logger.warning(f"Service '{service_name}' not in fallback")
            return False
        
        await self._handle_service_recovery(service_name)
        return True