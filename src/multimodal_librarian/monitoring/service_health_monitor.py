"""
Enhanced Service Health Monitor with automatic restart capabilities.

This module provides comprehensive service health monitoring with:
- Circuit breaker pattern for failure detection
- Automatic service restart capabilities
- Graceful degradation management
- Health trend analysis and alerting

IMPORTANT: This module uses asyncio.Lock instead of threading.Lock to avoid
deadlocks when mixing synchronous locks with async operations.
"""

import asyncio
from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from ..config import get_settings
from ..logging_config import get_logger


class HealthStatus(Enum):
    """Health status enumeration."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"
    DOWN = "down"
    UNKNOWN = "unknown"


class ServiceHealthMonitor:
    """
    Enhanced service health monitor with automatic restart capabilities.
    
    Uses circuit breaker pattern to prevent cascading failures
    and enables automatic recovery with restart capabilities.
    
    IMPORTANT: Uses asyncio.Lock instead of threading.Lock to avoid deadlocks
    when async operations are performed while holding the lock.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = get_logger("service_health_monitor")
        
        # Service statistics tracking
        self.stats = defaultdict(lambda: {
            'success_count': 0,
            'failure_count': 0,
            'last_success': None,
            'last_failure': None,
            'consecutive_failures': 0,
            'restart_count': 0,
            'last_restart': None,
            'status': HealthStatus.UNKNOWN,
            'degradation_level': 0  # 0-100 scale
        })
        
        # Configurable thresholds
        self.thresholds = {
            'failure_rate': 0.5,           # 50% failure rate triggers fallback
            'consecutive_failures': 3,      # 3 consecutive failures trigger fallback
            'recovery_time': 300,          # 5 minutes before retry
            'restart_threshold': 5,        # 5 consecutive failures trigger restart
            'max_restarts_per_hour': 3,    # Maximum restarts per hour
            'degradation_threshold': 0.3,  # 30% failure rate triggers degradation
            'critical_threshold': 0.8      # 80% failure rate is critical
        }
        
        # Service restart handlers
        self.restart_handlers: Dict[str, Callable] = {}
        
        # Graceful degradation handlers
        self.degradation_handlers: Dict[str, Callable] = {}
        
        # Health check callbacks
        self.health_callbacks: Dict[str, List[Callable]] = defaultdict(list)
        
        # Async lock for async-safe operations (replaces threading.Lock)
        # This prevents deadlocks when async operations are awaited while holding the lock
        self._lock: Optional[asyncio.Lock] = None
        
        # Background monitoring
        self._monitoring_active = False
        self._monitoring_task = None
    
    def _get_lock(self) -> asyncio.Lock:
        """Get or create the asyncio lock.
        
        Lazily creates the lock to ensure it's created in the correct event loop.
        """
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock
        
    def register_restart_handler(self, service_name: str, handler: Callable) -> None:
        """Register a restart handler for a service."""
        self.restart_handlers[service_name] = handler
        self.logger.info(f"Registered restart handler for service: {service_name}")
    
    def register_degradation_handler(self, service_name: str, handler: Callable) -> None:
        """Register a graceful degradation handler for a service."""
        self.degradation_handlers[service_name] = handler
        self.logger.info(f"Registered degradation handler for service: {service_name}")
    
    def register_health_callback(self, service_name: str, callback: Callable) -> None:
        """Register a callback for health status changes."""
        self.health_callbacks[service_name].append(callback)
        self.logger.info(f"Registered health callback for service: {service_name}")
    
    async def record_success(self, service_name: str) -> None:
        """Record successful service operation.
        
        This is now an async method to properly use asyncio.Lock.
        """
        async with self._get_lock():
            stats = self.stats[service_name]
            stats['success_count'] += 1
            stats['last_success'] = datetime.now()
            stats['consecutive_failures'] = 0
            
            # Update health status
            old_status = stats['status']
            stats['status'] = self._calculate_health_status(service_name)
            stats['degradation_level'] = self._calculate_degradation_level(service_name)
            
            # Trigger callbacks if status changed (outside lock via task)
            if old_status != stats['status']:
                # Schedule callback outside the lock context
                asyncio.create_task(
                    self._safe_trigger_health_callbacks(service_name, stats['status'])
                )
    
    def record_success_sync(self, service_name: str) -> None:
        """Synchronous version of record_success for non-async contexts.
        
        This version doesn't use locking and should only be used when
        async context is not available.
        """
        stats = self.stats[service_name]
        stats['success_count'] += 1
        stats['last_success'] = datetime.now()
        stats['consecutive_failures'] = 0
        
        # Update health status
        old_status = stats['status']
        stats['status'] = self._calculate_health_status(service_name)
        stats['degradation_level'] = self._calculate_degradation_level(service_name)
        
        # Trigger callbacks if status changed
        if old_status != stats['status']:
            self._trigger_health_callbacks(service_name, stats['status'])
    
    async def record_failure(self, service_name: str, error: Optional[str] = None) -> None:
        """Record failed service operation.
        
        This is now an async method to properly use asyncio.Lock.
        """
        should_restart = False
        should_degrade = False
        status_changed = False
        new_status = None
        
        async with self._get_lock():
            stats = self.stats[service_name]
            stats['failure_count'] += 1
            stats['last_failure'] = datetime.now()
            stats['consecutive_failures'] += 1
            
            # Update health status
            old_status = stats['status']
            stats['status'] = self._calculate_health_status(service_name)
            stats['degradation_level'] = self._calculate_degradation_level(service_name)
            
            self.logger.warning(
                f"Service failure recorded for {service_name}: "
                f"consecutive={stats['consecutive_failures']}, error={error}"
            )
            
            # Check if restart is needed
            should_restart = self._should_restart_service(service_name)
            
            # Check if degradation is needed
            if not should_restart:
                should_degrade = self._should_degrade_service(service_name)
            
            # Check if status changed
            if old_status != stats['status']:
                status_changed = True
                new_status = stats['status']
        
        # Create async tasks OUTSIDE the lock to avoid deadlock
        if should_restart:
            asyncio.create_task(self._attempt_service_restart(service_name))
        elif should_degrade:
            asyncio.create_task(self._trigger_graceful_degradation(service_name))
        
        # Trigger callbacks outside the lock
        if status_changed:
            asyncio.create_task(
                self._safe_trigger_health_callbacks(service_name, new_status)
            )
    
    def record_failure_sync(self, service_name: str, error: Optional[str] = None) -> None:
        """Synchronous version of record_failure for non-async contexts.
        
        This version doesn't use locking and should only be used when
        async context is not available.
        """
        stats = self.stats[service_name]
        stats['failure_count'] += 1
        stats['last_failure'] = datetime.now()
        stats['consecutive_failures'] += 1
        
        # Update health status
        old_status = stats['status']
        stats['status'] = self._calculate_health_status(service_name)
        stats['degradation_level'] = self._calculate_degradation_level(service_name)
        
        self.logger.warning(
            f"Service failure recorded for {service_name}: "
            f"consecutive={stats['consecutive_failures']}, error={error}"
        )
        
        # Check if status changed and trigger callbacks
        if old_status != stats['status']:
            self._trigger_health_callbacks(service_name, stats['status'])
    
    def should_fallback(self, service_name: str) -> bool:
        """Determine if service should fallback based on health metrics.
        
        This is a synchronous read-only operation that doesn't need locking.
        """
        stats = self.stats[service_name]
        
        # Check consecutive failures
        if stats['consecutive_failures'] >= self.thresholds['consecutive_failures']:
            return True
        
        # Check failure rate
        total_operations = stats['success_count'] + stats['failure_count']
        if total_operations >= 10:  # Minimum operations for rate calculation
            failure_rate = stats['failure_count'] / total_operations
            if failure_rate >= self.thresholds['failure_rate']:
                return True
        
        return False
    
    def can_retry(self, service_name: str) -> bool:
        """Check if enough time has passed to retry failed service.
        
        This is a synchronous read-only operation that doesn't need locking.
        """
        stats = self.stats[service_name]
        if not stats['last_failure']:
            return True
        
        time_since_failure = (datetime.now() - stats['last_failure']).total_seconds()
        return time_since_failure >= self.thresholds['recovery_time']
    
    def get_service_health(self, service_name: str) -> Dict[str, Any]:
        """Get comprehensive health information for a service.
        
        This is a synchronous read-only operation that doesn't need locking.
        """
        stats = self.stats[service_name]
        total_operations = stats['success_count'] + stats['failure_count']
        
        return {
            'service_name': service_name,
            'status': stats['status'].value,
            'degradation_level': stats['degradation_level'],
            'statistics': {
                'success_count': stats['success_count'],
                'failure_count': stats['failure_count'],
                'total_operations': total_operations,
                'success_rate': (stats['success_count'] / max(1, total_operations)) * 100,
                'consecutive_failures': stats['consecutive_failures'],
                'restart_count': stats['restart_count']
            },
            'timestamps': {
                'last_success': stats['last_success'].isoformat() if stats['last_success'] else None,
                'last_failure': stats['last_failure'].isoformat() if stats['last_failure'] else None,
                'last_restart': stats['last_restart'].isoformat() if stats['last_restart'] else None
            },
            'thresholds': {
                'can_retry': self.can_retry(service_name),
                'should_fallback': self.should_fallback(service_name),
                'should_restart': self._should_restart_service(service_name),
                'should_degrade': self._should_degrade_service(service_name)
            }
        }
    
    def get_all_services_health(self) -> Dict[str, Any]:
        """Get health information for all monitored services.
        
        This is a synchronous read-only operation that doesn't need locking.
        """
        services_health = {}
        overall_status = HealthStatus.HEALTHY
        
        for service_name in list(self.stats.keys()):
            service_health = self.get_service_health(service_name)
            services_health[service_name] = service_health
            
            # Determine overall status
            service_status = HealthStatus(service_health['status'])
            if service_status in [HealthStatus.CRITICAL, HealthStatus.DOWN]:
                overall_status = HealthStatus.CRITICAL
            elif service_status == HealthStatus.UNHEALTHY and overall_status != HealthStatus.CRITICAL:
                overall_status = HealthStatus.UNHEALTHY
            elif service_status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                overall_status = HealthStatus.DEGRADED
        
        return {
            'overall_status': overall_status.value,
            'services': services_health,
            'summary': {
                'total_services': len(services_health),
                'healthy_services': len([s for s in services_health.values() 
                                       if s['status'] == HealthStatus.HEALTHY.value]),
                'degraded_services': len([s for s in services_health.values() 
                                        if s['status'] == HealthStatus.DEGRADED.value]),
                'unhealthy_services': len([s for s in services_health.values() 
                                         if s['status'] in [HealthStatus.UNHEALTHY.value, 
                                                          HealthStatus.CRITICAL.value, 
                                                          HealthStatus.DOWN.value]])
            },
            'timestamp': datetime.now().isoformat()
        }
    
    def _calculate_health_status(self, service_name: str) -> HealthStatus:
        """Calculate health status based on service statistics."""
        stats = self.stats[service_name]
        total_operations = stats['success_count'] + stats['failure_count']
        
        if total_operations == 0:
            return HealthStatus.UNKNOWN
        
        failure_rate = stats['failure_count'] / total_operations
        consecutive_failures = stats['consecutive_failures']
        
        # Critical status conditions
        if consecutive_failures >= self.thresholds['restart_threshold']:
            return HealthStatus.CRITICAL
        
        if failure_rate >= self.thresholds['critical_threshold']:
            return HealthStatus.CRITICAL
        
        # Unhealthy status conditions
        if consecutive_failures >= self.thresholds['consecutive_failures']:
            return HealthStatus.UNHEALTHY
        
        if failure_rate >= self.thresholds['failure_rate']:
            return HealthStatus.UNHEALTHY
        
        # Degraded status conditions
        if failure_rate >= self.thresholds['degradation_threshold']:
            return HealthStatus.DEGRADED
        
        # Healthy status
        return HealthStatus.HEALTHY
    
    def _calculate_degradation_level(self, service_name: str) -> int:
        """Calculate degradation level (0-100) based on service health."""
        stats = self.stats[service_name]
        total_operations = stats['success_count'] + stats['failure_count']
        
        if total_operations == 0:
            return 0
        
        failure_rate = stats['failure_count'] / total_operations
        consecutive_failures = stats['consecutive_failures']
        
        # Base degradation on failure rate
        degradation = min(100, int(failure_rate * 100))
        
        # Add penalty for consecutive failures
        consecutive_penalty = min(50, consecutive_failures * 10)
        degradation = min(100, degradation + consecutive_penalty)
        
        return degradation
    
    def _should_restart_service(self, service_name: str) -> bool:
        """Determine if service should be restarted."""
        stats = self.stats[service_name]
        
        # Check consecutive failures threshold
        if stats['consecutive_failures'] < self.thresholds['restart_threshold']:
            return False
        
        # Check restart rate limiting
        if stats['last_restart']:
            time_since_restart = (datetime.now() - stats['last_restart']).total_seconds()
            if time_since_restart < 3600:  # Within last hour
                if stats['restart_count'] >= self.thresholds['max_restarts_per_hour']:
                    self.logger.warning(
                        f"Service {service_name} restart rate limited: "
                        f"{stats['restart_count']} restarts in last hour"
                    )
                    return False
        
        return True
    
    def _should_degrade_service(self, service_name: str) -> bool:
        """Determine if service should be gracefully degraded."""
        stats = self.stats[service_name]
        total_operations = stats['success_count'] + stats['failure_count']
        
        if total_operations < 10:  # Need minimum operations
            return False
        
        failure_rate = stats['failure_count'] / total_operations
        return failure_rate >= self.thresholds['degradation_threshold']
    
    async def _attempt_service_restart(self, service_name: str) -> bool:
        """Attempt to restart a service."""
        if service_name not in self.restart_handlers:
            self.logger.warning(f"No restart handler registered for service: {service_name}")
            return False
        
        try:
            self.logger.info(f"Attempting to restart service: {service_name}")
            
            # Update restart statistics (no lock needed for simple updates)
            stats = self.stats[service_name]
            stats['restart_count'] += 1
            stats['last_restart'] = datetime.now()
            
            # Call restart handler
            restart_handler = self.restart_handlers[service_name]
            if asyncio.iscoroutinefunction(restart_handler):
                success = await restart_handler()
            else:
                success = restart_handler()
            
            if success:
                self.logger.info(f"Service restart successful: {service_name}")
                # Reset consecutive failures on successful restart
                self.stats[service_name]['consecutive_failures'] = 0
                return True
            else:
                self.logger.error(f"Service restart failed: {service_name}")
                return False
                
        except Exception as e:
            self.logger.error(f"Exception during service restart for {service_name}: {e}")
            return False
    
    async def _trigger_graceful_degradation(self, service_name: str) -> None:
        """Trigger graceful degradation for a service."""
        if service_name not in self.degradation_handlers:
            self.logger.warning(f"No degradation handler registered for service: {service_name}")
            return
        
        try:
            self.logger.info(f"Triggering graceful degradation for service: {service_name}")
            
            degradation_handler = self.degradation_handlers[service_name]
            if asyncio.iscoroutinefunction(degradation_handler):
                await degradation_handler()
            else:
                degradation_handler()
                
        except Exception as e:
            self.logger.error(f"Exception during graceful degradation for {service_name}: {e}")
    
    async def _safe_trigger_health_callbacks(self, service_name: str, new_status: HealthStatus) -> None:
        """Safely trigger health status change callbacks asynchronously.
        
        This method is designed to be called via asyncio.create_task() to avoid
        blocking the main execution flow.
        """
        callbacks = self.health_callbacks.get(service_name, [])
        
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(service_name, new_status)
                else:
                    callback(service_name, new_status)
            except Exception as e:
                self.logger.error(f"Exception in health callback for {service_name}: {e}")
    
    def _trigger_health_callbacks(self, service_name: str, new_status: HealthStatus) -> None:
        """Trigger health status change callbacks (synchronous version).
        
        This version creates tasks for async callbacks but doesn't await them.
        Used by the sync versions of record_success/record_failure.
        """
        callbacks = self.health_callbacks.get(service_name, [])
        
        for callback in callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    # Schedule async callback as a task
                    try:
                        asyncio.create_task(callback(service_name, new_status))
                    except RuntimeError:
                        # No event loop running, skip async callback
                        self.logger.warning(
                            f"Cannot trigger async callback for {service_name}: no event loop"
                        )
                else:
                    callback(service_name, new_status)
            except Exception as e:
                self.logger.error(f"Exception in health callback for {service_name}: {e}")
    
    def start_monitoring(self, interval: int = 60) -> None:
        """Start background health monitoring.
        
        NOTE: This method is now a no-op. Background monitoring is handled
        by the HealthCheckSystem which uses a single unified monitoring task.
        This prevents duplicate monitoring and potential race conditions.
        """
        # Background monitoring is now handled by HealthCheckSystem
        # to use a single unified monitoring task
        self.logger.info(
            "ServiceHealthMonitor.start_monitoring() called - "
            "monitoring is handled by HealthCheckSystem"
        )
    
    def stop_monitoring(self) -> None:
        """Stop background health monitoring."""
        self._monitoring_active = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            self._monitoring_task = None
        self.logger.info("Stopped background health monitoring")
    
    async def _background_monitoring(self, interval: int) -> None:
        """Background monitoring task.
        
        NOTE: This method is kept for backwards compatibility but is no longer
        used. Background monitoring is now handled by HealthCheckSystem which
        uses a single unified monitoring task.
        """
        self.logger.warning(
            "ServiceHealthMonitor._background_monitoring() is deprecated - "
            "use HealthCheckSystem for background monitoring"
        )
    
    def get_stats(self, service_name: str) -> Dict[str, Any]:
        """Get statistics for a specific service (backward compatibility)."""
        return self.get_service_health(service_name)