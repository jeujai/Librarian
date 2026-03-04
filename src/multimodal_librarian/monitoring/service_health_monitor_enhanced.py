"""
Enhanced Service Health Monitor with Circuit Breaker Integration.

This module extends the existing service health monitor with circuit breaker
pattern integration for automatic service isolation and recovery.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from collections import defaultdict
from enum import Enum
import threading
import logging

from .service_health_monitor import ServiceHealthMonitor, HealthStatus
from .circuit_breaker import (
    CircuitBreaker, 
    CircuitBreakerManager, 
    CircuitBreakerConfig, 
    CircuitState,
    get_circuit_breaker_manager
)
from ..config import get_settings
from ..logging_config import get_logger


class EnhancedServiceHealthMonitor(ServiceHealthMonitor):
    """
    Enhanced service health monitor with circuit breaker integration.
    
    Extends the base service health monitor with circuit breaker pattern
    for automatic service isolation and recovery testing.
    """
    
    def __init__(self):
        """Initialize enhanced service health monitor."""
        super().__init__()
        
        # Circuit breaker integration
        self.circuit_breaker_manager = get_circuit_breaker_manager()
        self.service_circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # Circuit breaker configurations per service
        self.circuit_breaker_configs: Dict[str, CircuitBreakerConfig] = {}
        
        # Service isolation tracking
        self.isolated_services: Dict[str, datetime] = {}
        
        self.logger = get_logger("enhanced_service_health_monitor")
        self.logger.info("Enhanced service health monitor with circuit breakers initialized")
    
    def register_service_with_circuit_breaker(
        self,
        service_name: str,
        service_instance: Any,
        circuit_config: Optional[CircuitBreakerConfig] = None,
        recovery_function: Optional[Callable] = None
    ) -> None:
        """
        Register a service with circuit breaker protection.
        
        Args:
            service_name: Name of the service
            service_instance: Service instance
            circuit_config: Circuit breaker configuration
            recovery_function: Optional recovery test function
        """
        # Use default config if none provided
        if circuit_config is None:
            circuit_config = CircuitBreakerConfig(
                failure_threshold=self.thresholds['consecutive_failures'],
                failure_rate_threshold=self.thresholds['failure_rate'],
                timeout_seconds=self.thresholds['recovery_time'],
                success_threshold=3,
                health_check_interval=30
            )
        
        # Store configuration
        self.circuit_breaker_configs[service_name] = circuit_config
        
        # Create circuit breaker
        circuit_breaker = self.circuit_breaker_manager.create_circuit_breaker(
            f"service_{service_name}",
            circuit_config,
            recovery_function
        )
        
        self.service_circuit_breakers[service_name] = circuit_breaker
        
        # Register restart handler for circuit breaker integration
        if hasattr(service_instance, 'restart'):
            self.register_restart_handler(service_name, service_instance.restart)
        
        self.logger.info(f"Registered service '{service_name}' with circuit breaker protection")
    
    def record_success(self, service_name: str) -> None:
        """Record successful service operation with circuit breaker integration."""
        # Call parent method
        super().record_success(service_name)
        
        # Update circuit breaker if exists
        if service_name in self.service_circuit_breakers:
            # Circuit breaker success is recorded through the call method
            pass
        
        # Remove from isolated services if present
        if service_name in self.isolated_services:
            del self.isolated_services[service_name]
            self.logger.info(f"Service '{service_name}' recovered from isolation")
    
    def record_failure(self, service_name: str, error: Optional[str] = None) -> None:
        """Record failed service operation with circuit breaker integration."""
        # Call parent method
        super().record_failure(service_name, error)
        
        # Update circuit breaker if exists
        if service_name in self.service_circuit_breakers:
            # Circuit breaker failure is recorded through the call method
            pass
        
        # Check if service should be isolated
        if self._should_isolate_service(service_name):
            self._isolate_service(service_name)
    
    async def call_service_with_protection(
        self,
        service_name: str,
        service_method: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Call service method with circuit breaker protection.
        
        Args:
            service_name: Name of the service
            service_method: Service method to call
            *args: Method arguments
            **kwargs: Method keyword arguments
            
        Returns:
            Method result
            
        Raises:
            CircuitBreakerError: If service is isolated
            Exception: If service method fails
        """
        if service_name not in self.service_circuit_breakers:
            # No circuit breaker, call directly
            try:
                if asyncio.iscoroutinefunction(service_method):
                    result = await service_method(*args, **kwargs)
                else:
                    result = service_method(*args, **kwargs)
                
                self.record_success(service_name)
                return result
                
            except Exception as e:
                self.record_failure(service_name, str(e))
                raise
        
        # Use circuit breaker protection
        circuit_breaker = self.service_circuit_breakers[service_name]
        
        try:
            result = await circuit_breaker.call(service_method, *args, **kwargs)
            self.record_success(service_name)
            return result
            
        except Exception as e:
            self.record_failure(service_name, str(e))
            raise
    
    def _should_isolate_service(self, service_name: str) -> bool:
        """Determine if service should be isolated."""
        # Check if circuit breaker is open
        if service_name in self.service_circuit_breakers:
            circuit_breaker = self.service_circuit_breakers[service_name]
            if circuit_breaker.get_state() == CircuitState.OPEN:
                return True
        
        # Use parent logic as fallback
        return self.should_fallback(service_name)
    
    def _isolate_service(self, service_name: str) -> None:
        """Isolate a service due to failures."""
        if service_name not in self.isolated_services:
            self.isolated_services[service_name] = datetime.now()
            self.logger.warning(f"Service '{service_name}' has been isolated due to failures")
            
            # Trigger degradation handler if available
            if service_name in self.degradation_handlers:
                asyncio.create_task(self._trigger_graceful_degradation(service_name))
    
    def is_service_isolated(self, service_name: str) -> bool:
        """Check if service is currently isolated."""
        # Check circuit breaker state
        if service_name in self.service_circuit_breakers:
            circuit_breaker = self.service_circuit_breakers[service_name]
            return circuit_breaker.get_state() == CircuitState.OPEN
        
        # Check manual isolation
        return service_name in self.isolated_services
    
    def get_service_health_with_circuit_breaker(self, service_name: str) -> Dict[str, Any]:
        """Get comprehensive health information including circuit breaker status."""
        # Get base health information
        health_info = self.get_service_health(service_name)
        
        # Add circuit breaker information
        if service_name in self.service_circuit_breakers:
            circuit_breaker = self.service_circuit_breakers[service_name]
            circuit_status = circuit_breaker.get_status()
            
            health_info['circuit_breaker'] = {
                'state': circuit_status['state'],
                'metrics': circuit_status['metrics'],
                'time_in_current_state': circuit_status['time_in_current_state_seconds'],
                'thresholds': circuit_status['thresholds']
            }
        
        # Add isolation information
        health_info['isolated'] = self.is_service_isolated(service_name)
        if service_name in self.isolated_services:
            health_info['isolation_time'] = self.isolated_services[service_name].isoformat()
        
        return health_info
    
    def get_all_services_health_with_circuit_breakers(self) -> Dict[str, Any]:
        """Get health information for all services including circuit breaker status."""
        # Get base health information
        health_info = self.get_all_services_health()
        
        # Add circuit breaker summary
        circuit_breaker_summary = self.circuit_breaker_manager.get_summary()
        health_info['circuit_breaker_summary'] = circuit_breaker_summary
        
        # Add detailed circuit breaker status for each service
        for service_name in self.stats.keys():
            if service_name in health_info['services']:
                service_health = self.get_service_health_with_circuit_breaker(service_name)
                health_info['services'][service_name] = service_health
        
        # Add isolation summary
        health_info['isolation_summary'] = {
            'isolated_services': len(self.isolated_services),
            'isolated_service_names': list(self.isolated_services.keys())
        }
        
        return health_info
    
    async def test_service_recovery(self, service_name: str) -> bool:
        """
        Test if an isolated service has recovered.
        
        Args:
            service_name: Name of the service to test
            
        Returns:
            True if service has recovered
        """
        if not self.is_service_isolated(service_name):
            return True  # Not isolated, considered recovered
        
        # If circuit breaker exists, let it handle recovery testing
        if service_name in self.service_circuit_breakers:
            circuit_breaker = self.service_circuit_breakers[service_name]
            
            # Check if circuit breaker has transitioned from open
            if circuit_breaker.get_state() != CircuitState.OPEN:
                return True
            
            # Circuit breaker handles its own recovery testing
            return False
        
        # Manual recovery testing for services without circuit breakers
        try:
            # Try to perform a basic health check
            if service_name in self.restart_handlers:
                # If we have a restart handler, the service might be recoverable
                return True
            
            return False
            
        except Exception as e:
            self.logger.debug(f"Recovery test failed for service '{service_name}': {e}")
            return False
    
    async def force_service_recovery(self, service_name: str) -> bool:
        """
        Force recovery of an isolated service.
        
        Args:
            service_name: Name of the service to recover
            
        Returns:
            True if recovery was successful
        """
        if not self.is_service_isolated(service_name):
            self.logger.info(f"Service '{service_name}' is not isolated")
            return True
        
        try:
            # Reset circuit breaker if exists
            if service_name in self.service_circuit_breakers:
                circuit_breaker = self.service_circuit_breakers[service_name]
                circuit_breaker.reset()
                self.logger.info(f"Reset circuit breaker for service '{service_name}'")
            
            # Remove from isolated services
            if service_name in self.isolated_services:
                del self.isolated_services[service_name]
            
            # Reset health statistics
            if service_name in self.stats:
                self.stats[service_name]['consecutive_failures'] = 0
                self.stats[service_name]['status'] = HealthStatus.UNKNOWN
            
            self.logger.info(f"Forced recovery of service '{service_name}'")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to force recovery of service '{service_name}': {e}")
            return False
    
    def get_circuit_breaker_statistics(self) -> Dict[str, Any]:
        """Get comprehensive circuit breaker statistics."""
        stats = {
            'total_circuit_breakers': len(self.service_circuit_breakers),
            'circuit_breaker_states': {},
            'isolated_services': len(self.isolated_services),
            'service_details': {}
        }
        
        # Collect state information
        state_counts = defaultdict(int)
        for service_name, circuit_breaker in self.service_circuit_breakers.items():
            state = circuit_breaker.get_state()
            state_counts[state.value] += 1
            
            stats['service_details'][service_name] = {
                'circuit_state': state.value,
                'isolated': self.is_service_isolated(service_name),
                'metrics': circuit_breaker.get_metrics().to_dict()
            }
        
        stats['circuit_breaker_states'] = dict(state_counts)
        
        return stats
    
    async def shutdown_enhanced_monitoring(self) -> None:
        """Shutdown enhanced monitoring and cleanup resources."""
        # Stop base monitoring
        self.stop_monitoring()
        
        # Shutdown all circuit breakers
        for circuit_breaker in self.service_circuit_breakers.values():
            await circuit_breaker.shutdown()
        
        self.service_circuit_breakers.clear()
        self.isolated_services.clear()
        
        self.logger.info("Enhanced service health monitoring shutdown complete")


# Factory function for creating enhanced service health monitor
def create_enhanced_service_health_monitor() -> EnhancedServiceHealthMonitor:
    """Create and configure enhanced service health monitor."""
    return EnhancedServiceHealthMonitor()


# Global instance
_enhanced_monitor = None


def get_enhanced_service_health_monitor() -> EnhancedServiceHealthMonitor:
    """Get global enhanced service health monitor instance."""
    global _enhanced_monitor
    if _enhanced_monitor is None:
        _enhanced_monitor = create_enhanced_service_health_monitor()
    return _enhanced_monitor