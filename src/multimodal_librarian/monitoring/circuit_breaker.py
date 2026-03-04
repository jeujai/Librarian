"""
Circuit Breaker Pattern Implementation.

This module provides a comprehensive circuit breaker pattern implementation for
preventing cascading failures and enabling automatic service isolation and recovery.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable, Union, List
from enum import Enum
from dataclasses import dataclass, field
import threading
import logging
from collections import deque

from ..config import get_settings
from ..logging_config import get_logger


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Circuit is open, calls are blocked
    HALF_OPEN = "half_open"  # Testing if service has recovered


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open."""
    pass


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    # Failure detection
    failure_threshold: int = 5          # Number of failures to open circuit
    failure_rate_threshold: float = 0.5  # Failure rate (0.0-1.0) to open circuit
    minimum_requests: int = 10          # Minimum requests before rate calculation
    
    # Timing
    timeout_seconds: int = 60           # Time to wait before half-open
    success_threshold: int = 3          # Successes needed to close from half-open
    
    # Monitoring
    rolling_window_size: int = 100      # Size of rolling window for metrics
    health_check_interval: int = 30     # Health check interval in seconds
    
    # Recovery testing
    recovery_timeout: int = 5           # Timeout for recovery tests
    max_recovery_attempts: int = 3      # Max recovery attempts per cycle


@dataclass
class CircuitBreakerMetrics:
    """Metrics for circuit breaker."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    state_changes: int = 0
    time_in_open_state: float = 0.0
    time_in_half_open_state: float = 0.0
    
    @property
    def failure_rate(self) -> float:
        """Calculate current failure rate."""
        if self.total_requests == 0:
            return 0.0
        return self.failed_requests / self.total_requests
    
    @property
    def success_rate(self) -> float:
        """Calculate current success rate."""
        return 1.0 - self.failure_rate
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            'total_requests': self.total_requests,
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'consecutive_failures': self.consecutive_failures,
            'consecutive_successes': self.consecutive_successes,
            'failure_rate': self.failure_rate,
            'success_rate': self.success_rate,
            'last_failure_time': self.last_failure_time.isoformat() if self.last_failure_time else None,
            'last_success_time': self.last_success_time.isoformat() if self.last_success_time else None,
            'state_changes': self.state_changes,
            'time_in_open_state': self.time_in_open_state,
            'time_in_half_open_state': self.time_in_half_open_state
        }


class CircuitBreaker:
    """
    Circuit breaker implementation for preventing cascading failures.
    
    Implements the circuit breaker pattern with three states:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Circuit is open, requests are blocked
    - HALF_OPEN: Testing if service has recovered
    """
    
    def __init__(
        self, 
        name: str, 
        config: Optional[CircuitBreakerConfig] = None,
        recovery_function: Optional[Callable] = None
    ):
        """
        Initialize circuit breaker.
        
        Args:
            name: Name of the circuit breaker
            config: Configuration for the circuit breaker
            recovery_function: Optional function to test service recovery
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.recovery_function = recovery_function
        
        # State management
        self.state = CircuitState.CLOSED
        self.state_changed_time = datetime.now()
        
        # Metrics
        self.metrics = CircuitBreakerMetrics()
        
        # Rolling window for recent requests
        self.recent_requests = deque(maxlen=self.config.rolling_window_size)
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Recovery testing
        self._recovery_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        
        # Logging
        self.logger = get_logger(f"circuit_breaker.{name}")
        
        self.logger.info(f"Circuit breaker '{name}' initialized")
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            CircuitBreakerError: If circuit is open
        """
        # Check if circuit is open
        if self.state == CircuitState.OPEN:
            if not self._should_attempt_reset():
                raise CircuitBreakerError(
                    f"Circuit breaker '{self.name}' is OPEN. "
                    f"Service is temporarily unavailable."
                )
            else:
                # Transition to half-open for testing
                await self._transition_to_half_open()
        
        # Execute the function
        start_time = time.time()
        try:
            # Execute function (async or sync)
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Record success
            execution_time = time.time() - start_time
            await self._record_success(execution_time)
            
            return result
            
        except Exception as e:
            # Record failure
            execution_time = time.time() - start_time
            await self._record_failure(e, execution_time)
            raise
    
    async def _record_success(self, execution_time: float) -> None:
        """Record successful operation."""
        with self._lock:
            self.metrics.total_requests += 1
            self.metrics.successful_requests += 1
            self.metrics.consecutive_successes += 1
            self.metrics.consecutive_failures = 0
            self.metrics.last_success_time = datetime.now()
            
            # Add to rolling window
            self.recent_requests.append({
                'success': True,
                'timestamp': datetime.now(),
                'execution_time': execution_time
            })
        
        # Check if we should close the circuit from half-open
        if (self.state == CircuitState.HALF_OPEN and 
            self.metrics.consecutive_successes >= self.config.success_threshold):
            await self._transition_to_closed()
        
        self.logger.debug(f"Success recorded for circuit '{self.name}'")
    
    async def _record_failure(self, error: Exception, execution_time: float) -> None:
        """Record failed operation."""
        with self._lock:
            self.metrics.total_requests += 1
            self.metrics.failed_requests += 1
            self.metrics.consecutive_failures += 1
            self.metrics.consecutive_successes = 0
            self.metrics.last_failure_time = datetime.now()
            
            # Add to rolling window
            self.recent_requests.append({
                'success': False,
                'timestamp': datetime.now(),
                'execution_time': execution_time,
                'error': str(error)
            })
        
        # Check if we should open the circuit
        if self._should_open_circuit():
            await self._transition_to_open()
        
        self.logger.warning(f"Failure recorded for circuit '{self.name}': {error}")
    
    def _should_open_circuit(self) -> bool:
        """Determine if circuit should be opened."""
        # Check consecutive failures
        if self.metrics.consecutive_failures >= self.config.failure_threshold:
            return True
        
        # Check failure rate (only if we have minimum requests)
        if (self.metrics.total_requests >= self.config.minimum_requests and
            self.metrics.failure_rate >= self.config.failure_rate_threshold):
            return True
        
        return False
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.state != CircuitState.OPEN:
            return False
        
        time_since_open = (datetime.now() - self.state_changed_time).total_seconds()
        return time_since_open >= self.config.timeout_seconds
    
    async def _transition_to_open(self) -> None:
        """Transition circuit to OPEN state."""
        if self.state == CircuitState.OPEN:
            return
        
        old_state = self.state
        self.state = CircuitState.OPEN
        self.state_changed_time = datetime.now()
        self.metrics.state_changes += 1
        
        self.logger.warning(
            f"Circuit breaker '{self.name}' transitioned from {old_state.value} to OPEN. "
            f"Consecutive failures: {self.metrics.consecutive_failures}, "
            f"Failure rate: {self.metrics.failure_rate:.2%}"
        )
        
        # Start recovery testing if recovery function is available
        if self.recovery_function:
            await self._start_recovery_testing()
    
    async def _transition_to_half_open(self) -> None:
        """Transition circuit to HALF_OPEN state."""
        if self.state == CircuitState.HALF_OPEN:
            return
        
        old_state = self.state
        
        # Update time in open state
        if old_state == CircuitState.OPEN:
            time_in_open = (datetime.now() - self.state_changed_time).total_seconds()
            self.metrics.time_in_open_state += time_in_open
        
        self.state = CircuitState.HALF_OPEN
        self.state_changed_time = datetime.now()
        self.metrics.state_changes += 1
        self.metrics.consecutive_successes = 0  # Reset for testing
        
        self.logger.info(
            f"Circuit breaker '{self.name}' transitioned from {old_state.value} to HALF_OPEN. "
            f"Testing service recovery..."
        )
    
    async def _transition_to_closed(self) -> None:
        """Transition circuit to CLOSED state."""
        if self.state == CircuitState.CLOSED:
            return
        
        old_state = self.state
        
        # Update time in half-open state
        if old_state == CircuitState.HALF_OPEN:
            time_in_half_open = (datetime.now() - self.state_changed_time).total_seconds()
            self.metrics.time_in_half_open_state += time_in_half_open
        
        self.state = CircuitState.CLOSED
        self.state_changed_time = datetime.now()
        self.metrics.state_changes += 1
        
        # Stop recovery testing
        await self._stop_recovery_testing()
        
        self.logger.info(
            f"Circuit breaker '{self.name}' transitioned from {old_state.value} to CLOSED. "
            f"Service has recovered. Consecutive successes: {self.metrics.consecutive_successes}"
        )
    
    async def _start_recovery_testing(self) -> None:
        """Start background recovery testing."""
        if self._recovery_task and not self._recovery_task.done():
            return  # Already running
        
        self._shutdown_event.clear()
        self._recovery_task = asyncio.create_task(self._recovery_testing_loop())
        self.logger.info(f"Started recovery testing for circuit '{self.name}'")
    
    async def _stop_recovery_testing(self) -> None:
        """Stop background recovery testing."""
        self._shutdown_event.set()
        
        if self._recovery_task:
            try:
                await asyncio.wait_for(self._recovery_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._recovery_task.cancel()
                self.logger.warning(f"Recovery testing task cancelled for circuit '{self.name}'")
        
        self.logger.info(f"Stopped recovery testing for circuit '{self.name}'")
    
    async def _recovery_testing_loop(self) -> None:
        """Background recovery testing loop."""
        self.logger.info(f"Recovery testing loop started for circuit '{self.name}'")
        
        while not self._shutdown_event.is_set() and self.state == CircuitState.OPEN:
            try:
                # Wait for health check interval
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.config.health_check_interval
                )
                
            except asyncio.TimeoutError:
                # Perform recovery test
                if self._should_attempt_reset():
                    recovery_successful = await self._test_service_recovery()
                    
                    if recovery_successful:
                        self.logger.info(f"Recovery test successful for circuit '{self.name}'")
                        await self._transition_to_half_open()
                        break
                    else:
                        self.logger.debug(f"Recovery test failed for circuit '{self.name}'")
        
        self.logger.info(f"Recovery testing loop stopped for circuit '{self.name}'")
    
    async def _test_service_recovery(self) -> bool:
        """Test if service has recovered."""
        if not self.recovery_function:
            return False
        
        try:
            # Execute recovery test with timeout
            if asyncio.iscoroutinefunction(self.recovery_function):
                await asyncio.wait_for(
                    self.recovery_function(),
                    timeout=self.config.recovery_timeout
                )
            else:
                self.recovery_function()
            
            return True
            
        except Exception as e:
            self.logger.debug(f"Recovery test failed for circuit '{self.name}': {e}")
            return False
    
    def get_state(self) -> CircuitState:
        """Get current circuit state."""
        return self.state
    
    def get_metrics(self) -> CircuitBreakerMetrics:
        """Get current metrics."""
        with self._lock:
            return self.metrics
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive status information."""
        with self._lock:
            time_in_current_state = (datetime.now() - self.state_changed_time).total_seconds()
            
            # Calculate recent failure rate (last 10 requests)
            recent_failures = sum(
                1 for req in list(self.recent_requests)[-10:] 
                if not req['success']
            )
            recent_failure_rate = recent_failures / min(10, len(self.recent_requests)) if self.recent_requests else 0.0
            
            return {
                'name': self.name,
                'state': self.state.value,
                'time_in_current_state_seconds': time_in_current_state,
                'state_changed_time': self.state_changed_time.isoformat(),
                'metrics': self.metrics.to_dict(),
                'recent_failure_rate': recent_failure_rate,
                'config': {
                    'failure_threshold': self.config.failure_threshold,
                    'failure_rate_threshold': self.config.failure_rate_threshold,
                    'timeout_seconds': self.config.timeout_seconds,
                    'success_threshold': self.config.success_threshold
                },
                'thresholds': {
                    'should_open': self._should_open_circuit(),
                    'can_attempt_reset': self._should_attempt_reset()
                }
            }
    
    def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state."""
        with self._lock:
            old_state = self.state
            self.state = CircuitState.CLOSED
            self.state_changed_time = datetime.now()
            self.metrics.state_changes += 1
            
            # Reset failure counters
            self.metrics.consecutive_failures = 0
            self.metrics.consecutive_successes = 0
        
        # Stop recovery testing (handle no event loop case)
        try:
            asyncio.create_task(self._stop_recovery_testing())
        except RuntimeError:
            # No event loop running, set shutdown event directly
            self._shutdown_event.set()
        
        self.logger.info(f"Circuit breaker '{self.name}' manually reset from {old_state.value} to CLOSED")
    
    def force_open(self) -> None:
        """Manually force circuit breaker to OPEN state."""
        with self._lock:
            old_state = self.state
            self.state = CircuitState.OPEN
            self.state_changed_time = datetime.now()
            self.metrics.state_changes += 1
        
        # Start recovery testing if available (handle no event loop case)
        if self.recovery_function:
            try:
                asyncio.create_task(self._start_recovery_testing())
            except RuntimeError:
                # No event loop running, skip recovery testing
                pass
        
        self.logger.warning(f"Circuit breaker '{self.name}' manually forced from {old_state.value} to OPEN")
    
    async def shutdown(self) -> None:
        """Shutdown circuit breaker and cleanup resources."""
        await self._stop_recovery_testing()
        self.logger.info(f"Circuit breaker '{self.name}' shutdown complete")


class CircuitBreakerManager:
    """
    Manager for multiple circuit breakers.
    
    Provides centralized management and monitoring of circuit breakers
    across the application.
    """
    
    def __init__(self):
        """Initialize circuit breaker manager."""
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.Lock()
        self.logger = get_logger("circuit_breaker_manager")
        
        self.logger.info("Circuit breaker manager initialized")
    
    def create_circuit_breaker(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        recovery_function: Optional[Callable] = None
    ) -> CircuitBreaker:
        """
        Create and register a new circuit breaker.
        
        Args:
            name: Unique name for the circuit breaker
            config: Configuration for the circuit breaker
            recovery_function: Optional recovery test function
            
        Returns:
            Created circuit breaker instance
        """
        with self._lock:
            if name in self.circuit_breakers:
                raise ValueError(f"Circuit breaker '{name}' already exists")
            
            circuit_breaker = CircuitBreaker(name, config, recovery_function)
            self.circuit_breakers[name] = circuit_breaker
            
            self.logger.info(f"Created circuit breaker '{name}'")
            return circuit_breaker
    
    def get_circuit_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """Get circuit breaker by name."""
        return self.circuit_breakers.get(name)
    
    def remove_circuit_breaker(self, name: str) -> bool:
        """
        Remove and shutdown circuit breaker.
        
        Args:
            name: Name of circuit breaker to remove
            
        Returns:
            True if removed, False if not found
        """
        with self._lock:
            circuit_breaker = self.circuit_breakers.pop(name, None)
            
            if circuit_breaker:
                # Handle shutdown (may not have event loop)
                try:
                    asyncio.create_task(circuit_breaker.shutdown())
                except RuntimeError:
                    # No event loop running, set shutdown event directly
                    circuit_breaker._shutdown_event.set()
                
                self.logger.info(f"Removed circuit breaker '{name}'")
                return True
            
            return False
    
    def get_all_status(self) -> Dict[str, Any]:
        """Get status of all circuit breakers."""
        with self._lock:
            return {
                name: cb.get_status() 
                for name, cb in self.circuit_breakers.items()
            }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary statistics for all circuit breakers."""
        with self._lock:
            total_breakers = len(self.circuit_breakers)
            open_breakers = sum(
                1 for cb in self.circuit_breakers.values() 
                if cb.get_state() == CircuitState.OPEN
            )
            half_open_breakers = sum(
                1 for cb in self.circuit_breakers.values() 
                if cb.get_state() == CircuitState.HALF_OPEN
            )
            closed_breakers = total_breakers - open_breakers - half_open_breakers
            
            return {
                'total_circuit_breakers': total_breakers,
                'closed_breakers': closed_breakers,
                'open_breakers': open_breakers,
                'half_open_breakers': half_open_breakers,
                'health_percentage': (closed_breakers / max(1, total_breakers)) * 100
            }
    
    async def shutdown_all(self) -> None:
        """Shutdown all circuit breakers."""
        with self._lock:
            circuit_breakers = list(self.circuit_breakers.values())
            self.circuit_breakers.clear()
        
        # Shutdown all circuit breakers
        for cb in circuit_breakers:
            await cb.shutdown()
        
        self.logger.info("All circuit breakers shutdown")


# Global circuit breaker manager instance
_circuit_breaker_manager = CircuitBreakerManager()


def get_circuit_breaker_manager() -> CircuitBreakerManager:
    """Get the global circuit breaker manager instance."""
    return _circuit_breaker_manager


def circuit_breaker(
    name: str,
    config: Optional[CircuitBreakerConfig] = None,
    recovery_function: Optional[Callable] = None
):
    """
    Decorator for applying circuit breaker pattern to functions.
    
    Args:
        name: Name for the circuit breaker
        config: Circuit breaker configuration
        recovery_function: Optional recovery test function
    """
    def decorator(func):
        # Get or create circuit breaker
        manager = get_circuit_breaker_manager()
        cb = manager.get_circuit_breaker(name)
        
        if cb is None:
            cb = manager.create_circuit_breaker(name, config, recovery_function)
        
        async def async_wrapper(*args, **kwargs):
            return await cb.call(func, *args, **kwargs)
        
        def sync_wrapper(*args, **kwargs):
            return asyncio.run(cb.call(func, *args, **kwargs))
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator