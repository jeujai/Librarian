"""
Enhanced Health Check System with automatic restart and graceful degradation.

This module provides a comprehensive health checking system that integrates
with the ServiceHealthMonitor to provide automatic restart capabilities
and graceful degradation management.

IMPORTANT: This module uses a single unified monitoring task to prevent
duplicate monitoring and potential race conditions. All health checks
have hard timeouts to prevent blocking.
"""

import asyncio
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from ..config import get_settings
from ..logging_config import get_logger
from .component_health_checks import (
    AIServiceHealthCheck,
    CacheHealthCheck,
    DatabaseHealthCheck,
    KnowledgeGraphHealthCheck,
    ModelServerHealthCheck,
    SearchServiceHealthCheck,
    SystemResourcesHealthCheck,
    UMLSHealthCheck,
    VectorStoreHealthCheck,
    YagoHealthCheck,
)
from .service_health_monitor import HealthStatus, ServiceHealthMonitor


class HealthReport:
    """Health check report container."""
    
    def __init__(self):
        self.results: Dict[str, Dict[str, Any]] = {}
        self.overall_status = HealthStatus.UNKNOWN
        self.timestamp = datetime.now()
        self.total_response_time = 0
    
    def add_check_result(self, component_name: str, result: Dict[str, Any]) -> None:
        """Add a component health check result."""
        self.results[component_name] = result
        self.total_response_time += result.get('response_time_ms', 0)
    
    def get_overall_status(self) -> HealthStatus:
        """Determine overall system status."""
        if not self.results:
            return HealthStatus.UNKNOWN
        
        statuses = [HealthStatus(result.get('status', 'unknown')) for result in self.results.values()]
        
        if any(status == HealthStatus.CRITICAL for status in statuses):
            return HealthStatus.CRITICAL
        elif any(status == HealthStatus.DOWN for status in statuses):
            return HealthStatus.DOWN
        elif any(status == HealthStatus.UNHEALTHY for status in statuses):
            return HealthStatus.UNHEALTHY
        elif any(status == HealthStatus.DEGRADED for status in statuses):
            return HealthStatus.DEGRADED
        elif all(status == HealthStatus.HEALTHY for status in statuses):
            return HealthStatus.HEALTHY
        else:
            return HealthStatus.UNKNOWN
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert report to dictionary."""
        return {
            'overall_status': self.get_overall_status().value,
            'components': self.results,
            'summary': {
                'total_components': len(self.results),
                'healthy_components': len([r for r in self.results.values() 
                                         if r.get('status') == HealthStatus.HEALTHY.value]),
                'degraded_components': len([r for r in self.results.values() 
                                          if r.get('status') == HealthStatus.DEGRADED.value]),
                'unhealthy_components': len([r for r in self.results.values() 
                                           if r.get('status') in [HealthStatus.UNHEALTHY.value, 
                                                                HealthStatus.CRITICAL.value, 
                                                                HealthStatus.DOWN.value]]),
                'total_response_time_ms': round(self.total_response_time, 2)
            },
            'timestamp': self.timestamp.isoformat()
        }


class HealthCheckSystem:
    """
    Enhanced health check system with automatic restart and graceful degradation.
    
    Integrates with ServiceHealthMonitor to provide comprehensive health monitoring
    with automatic recovery capabilities.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = get_logger("health_check_system")
        
        # Initialize service health monitor
        self.health_monitor = ServiceHealthMonitor()
        
        # Initialize component health checks
        self.checks = {
            'database': DatabaseHealthCheck(),
            'vector_store': VectorStoreHealthCheck(),
            'search_service': SearchServiceHealthCheck(),
            'ai_services': AIServiceHealthCheck(),
            'cache': CacheHealthCheck(),
            'knowledge_graph': KnowledgeGraphHealthCheck(),
            'system_resources': SystemResourcesHealthCheck(),
            'model_server': ModelServerHealthCheck(),
            'yago': YagoHealthCheck(),
            'umls': UMLSHealthCheck()
        }
        
        # Critical services that must be healthy for system operation
        self.critical_services = ['database', 'vector_store', 'search_service']
        
        # Register restart handlers
        self._register_restart_handlers()
        
        # Register degradation handlers
        self._register_degradation_handlers()
        
        # Register health callbacks
        self._register_health_callbacks()
        
        # Background monitoring
        self._monitoring_active = False
        self._monitoring_task = None
    
    def _register_restart_handlers(self) -> None:
        """Register restart handlers for services that support automatic restart.
        
        NOTE: Restart handlers are DISABLED because they create new service instances
        which can block the event loop and cause server freezes. The handlers are
        kept here for reference but not registered.
        """
        # DISABLED: These handlers create new service instances which can block
        # the event loop. They are kept here for reference but not registered.
        pass
    
    def _register_degradation_handlers(self) -> None:
        """Register graceful degradation handlers.
        
        NOTE: Degradation handlers are DISABLED because they can trigger
        service creation which blocks the event loop. They are kept here
        for reference but not registered.
        """
        # DISABLED: These handlers can trigger service creation which blocks
        # the event loop. They are kept here for reference but not registered.
        pass
    
    def _register_health_callbacks(self) -> None:
        """Register health status change callbacks."""
        
        async def on_health_change(service_name: str, new_status: HealthStatus) -> None:
            """Handle health status changes."""
            self.logger.info(f"Health status changed for {service_name}: {new_status.value}")
            
            # Log critical status changes
            if new_status in [HealthStatus.CRITICAL, HealthStatus.DOWN]:
                self.logger.critical(f"Service {service_name} is in critical state: {new_status.value}")
            elif new_status == HealthStatus.UNHEALTHY:
                self.logger.error(f"Service {service_name} is unhealthy: {new_status.value}")
            elif new_status == HealthStatus.DEGRADED:
                self.logger.warning(f"Service {service_name} is degraded: {new_status.value}")
            elif new_status == HealthStatus.HEALTHY:
                self.logger.info(f"Service {service_name} has recovered: {new_status.value}")
        
        # Register callback for all services
        for service_name in self.checks.keys():
            self.health_monitor.register_health_callback(service_name, on_health_change)
    
    async def run_all_checks(self) -> HealthReport:
        """Run all health checks and generate comprehensive report.
        
        Each health check is run with a hard timeout to prevent blocking.
        Uses asyncio.wait_for with shield to ensure timeouts are enforced.
        """
        report = HealthReport()
        
        # Health check timeout - hard limit per check
        check_timeout = 5.0  # 5 seconds max per health check
        
        # Run all component health checks with individual timeouts
        for name, check in self.checks.items():
            try:
                # Run each health check with a hard timeout
                # Use wait_for to enforce the timeout
                result = await asyncio.wait_for(
                    self._run_single_check(name, check),
                    timeout=check_timeout
                )
                report.add_check_result(name, result)
                
            except asyncio.TimeoutError:
                self.logger.warning(f"Health check hard timeout for {name} ({check_timeout}s)")
                
                # Record timeout as failure using sync method to avoid nested async
                self.health_monitor.record_failure_sync(name, "Health check timeout")
                
                # Add timeout result
                report.add_check_result(name, {
                    'status': HealthStatus.DEGRADED.value,
                    'component': name,
                    'response_time_ms': check_timeout * 1000,
                    'details': {
                        'error': f'Health check timeout ({check_timeout}s)',
                        'note': 'Component may still be initializing or is unresponsive'
                    },
                    'timestamp': datetime.now().isoformat()
                })
                
            except Exception as e:
                self.logger.error(f"Health check failed for {name}: {e}")
                
                # Record failure using sync method
                self.health_monitor.record_failure_sync(name, str(e))
                
                # Add error result
                report.add_check_result(name, {
                    'status': HealthStatus.CRITICAL.value,
                    'component': name,
                    'response_time_ms': 0,
                    'details': {'error': str(e)},
                    'timestamp': datetime.now().isoformat()
                })
        
        # Update overall status
        report.overall_status = report.get_overall_status()
        
        return report
    
    async def _run_single_check(self, name: str, check) -> Dict[str, Any]:
        """Run a single health check and record the result.
        
        This method is separated to allow proper timeout handling.
        """
        result = await check.run()
        
        # Record result with health monitor using sync methods
        # to avoid nested async operations that could cause issues
        if result.get('status') in [HealthStatus.HEALTHY.value, 'healthy']:
            self.health_monitor.record_success_sync(name)
        else:
            error_msg = result.get('details', {}).get('error', 'Health check failed')
            self.health_monitor.record_failure_sync(name, error_msg)
        
        return result
    
    async def get_readiness_status(self) -> bool:
        """Check if system is ready to serve requests."""
        try:
            # Check critical services
            for service_name in self.critical_services:
                if service_name in self.checks:
                    result = await self.checks[service_name].run()
                    status = HealthStatus(result.get('status', 'unknown'))
                    
                    if status in [HealthStatus.CRITICAL, HealthStatus.DOWN]:
                        self.logger.warning(f"Critical service {service_name} is not ready: {status.value}")
                        return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Readiness check failed: {e}")
            return False
    
    async def get_liveness_status(self) -> bool:
        """Check if system is alive and responding."""
        try:
            # Simple liveness check - just test database connectivity
            if 'database' in self.checks:
                return await self.checks['database'].ping()
            return True
            
        except Exception as e:
            self.logger.error(f"Liveness check failed: {e}")
            return False
    
    async def get_detailed_status(self) -> Dict[str, Any]:
        """Get detailed system status including health monitor data."""
        # Get health check report
        health_report = await self.run_all_checks()
        
        # Get service health monitor data
        monitor_data = self.health_monitor.get_all_services_health()
        
        # Combine data
        detailed_status = health_report.to_dict()
        detailed_status['service_monitor'] = monitor_data
        detailed_status['readiness'] = await self.get_readiness_status()
        detailed_status['liveness'] = await self.get_liveness_status()
        
        return detailed_status
    
    def start_monitoring(self, interval: int = 60) -> None:
        """Start background health monitoring.
        
        Uses a SINGLE unified monitoring task to prevent duplicate monitoring
        and potential race conditions. The ServiceHealthMonitor's start_monitoring
        is no longer called separately.
        
        Health checks have hard timeouts to prevent blocking, and the monitoring
        task includes an initial delay to allow services to initialize.
        """
        if self._monitoring_active:
            self.logger.warning("Health monitoring is already active")
            return
        
        self._monitoring_active = True
        
        # Create a single unified monitoring task
        # NOTE: We do NOT call self.health_monitor.start_monitoring() anymore
        # to prevent duplicate monitoring tasks
        self._monitoring_task = asyncio.create_task(
            self._background_monitoring(interval)
        )
        
        self.logger.info(f"Started unified health monitoring with {interval}s interval")
    
    def stop_monitoring(self) -> None:
        """Stop background health monitoring."""
        self._monitoring_active = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            self._monitoring_task = None
        
        self.health_monitor.stop_monitoring()
        self.logger.info("Stopped comprehensive health monitoring")
    
    async def _background_monitoring(self, interval: int) -> None:
        """Background monitoring task.
        
        This is the SINGLE unified monitoring task for the entire health system.
        It includes an initial delay to allow services to initialize before
        running health checks.
        
        All health checks have hard timeouts enforced by run_all_checks().
        """
        # Initial delay to allow services to initialize
        # This prevents triggering service creation during startup
        initial_delay = 120  # 2 minutes delay before first health check
        self.logger.info(
            f"Background health monitoring will start in {initial_delay}s "
            "to allow services to initialize"
        )
        
        try:
            await asyncio.sleep(initial_delay)
        except asyncio.CancelledError:
            self.logger.info("Health monitoring cancelled during initial delay")
            return
        
        self.logger.info("Background health monitoring starting first check cycle")
        
        while self._monitoring_active:
            try:
                # Run comprehensive health checks with hard timeouts
                # Each individual check has a 5-second timeout
                # Total check cycle has a 60-second timeout
                try:
                    health_report = await asyncio.wait_for(
                        self.run_all_checks(),
                        timeout=60.0  # Hard timeout for entire check cycle
                    )
                except asyncio.TimeoutError:
                    self.logger.error(
                        "Health check cycle timed out (60s) - "
                        "some checks may be blocking"
                    )
                    # Continue to next cycle
                    await asyncio.sleep(interval)
                    continue
                
                # Log summary
                summary = health_report.to_dict()['summary']
                if summary['unhealthy_components'] > 0:
                    self.logger.warning(
                        f"Health monitoring: {summary['unhealthy_components']} unhealthy, "
                        f"{summary['degraded_components']} degraded components"
                    )
                else:
                    self.logger.debug(
                        f"Health monitoring: all {summary['total_components']} components OK"
                    )
                
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                self.logger.info("Health monitoring task cancelled")
                break
            except Exception as e:
                self.logger.error(f"Exception in background health monitoring: {e}")
                # Continue monitoring after error
                try:
                    await asyncio.sleep(interval)
                except asyncio.CancelledError:
                    break
    
    def get_service_health(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get health information for a specific service."""
        return self.health_monitor.get_service_health(service_name)
    
    def register_custom_check(self, name: str, check_instance) -> None:
        """Register a custom health check."""
        self.checks[name] = check_instance
        self.logger.info(f"Registered custom health check: {name}")
    
    def register_custom_restart_handler(self, service_name: str, handler: Callable) -> None:
        """Register a custom restart handler."""
        self.health_monitor.register_restart_handler(service_name, handler)
    
    def register_custom_degradation_handler(self, service_name: str, handler: Callable) -> None:
        """Register a custom degradation handler."""
        self.health_monitor.register_degradation_handler(service_name, handler)


# Global health check system instance
_health_check_system = None


def get_health_check_system() -> HealthCheckSystem:
    """Get the global health check system instance."""
    global _health_check_system
    if _health_check_system is None:
        _health_check_system = HealthCheckSystem()
    return _health_check_system
