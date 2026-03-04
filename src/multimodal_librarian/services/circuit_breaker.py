"""
Circuit Breaker for External API Resilience.

This module implements the circuit breaker pattern to prevent cascade failures
when external APIs (YAGO, ConceptNet) are experiencing issues.
"""

import logging
import threading
import time
from datetime import datetime
from typing import Dict, Optional

from ..models.enrichment import CircuitBreakerStats, CircuitState

logger = logging.getLogger(__name__)


class CircuitBreaker:
    """
    Circuit breaker for external API resilience.
    
    States:
    - CLOSED: Normal operation, requests allowed
    - OPEN: Blocking requests after too many failures
    - HALF_OPEN: Testing recovery with limited requests
    
    Transitions:
    - CLOSED -> OPEN: After failure_threshold failures within failure_window
    - OPEN -> HALF_OPEN: After recovery_timeout seconds
    - HALF_OPEN -> CLOSED: After a successful request
    - HALF_OPEN -> OPEN: After a failed request
    """
    
    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        failure_window: int = 60,  # seconds
        recovery_timeout: int = 300  # 5 minutes
    ):
        """
        Initialize the circuit breaker.
        
        Args:
            name: Name of this circuit breaker (for logging)
            failure_threshold: Number of failures to trigger OPEN state
            failure_window: Time window in seconds for counting failures
            recovery_timeout: Time in seconds before attempting recovery
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.failure_window = failure_window
        self.recovery_timeout = recovery_timeout
        
        # State tracking
        self._state = CircuitState.CLOSED
        self._failures: list = []  # List of failure timestamps
        self._successes = 0
        self._last_failure_time: Optional[float] = None
        self._last_state_change: Optional[float] = None
        self._opened_at: Optional[float] = None
        
        # Thread safety
        self._lock = threading.RLock()
        
        logger.info(
            f"CircuitBreaker '{name}' initialized: "
            f"threshold={failure_threshold}, window={failure_window}s, recovery={recovery_timeout}s"
        )
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        with self._lock:
            self._check_state_transition()
            return self._state
    
    def record_success(self) -> None:
        """
        Record a successful API call.
        
        In HALF_OPEN state, this closes the circuit.
        """
        with self._lock:
            self._successes += 1
            
            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.CLOSED)
                logger.info(f"CircuitBreaker '{self.name}' recovered: HALF_OPEN -> CLOSED")
    
    def record_failure(self) -> None:
        """
        Record a failed API call.
        
        May trigger transition to OPEN state if threshold exceeded.
        """
        current_time = time.time()
        
        with self._lock:
            self._last_failure_time = current_time
            
            # In HALF_OPEN state, any failure reopens the circuit
            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
                logger.warning(f"CircuitBreaker '{self.name}' reopened: HALF_OPEN -> OPEN")
                return
            
            # Add failure timestamp
            self._failures.append(current_time)
            
            # Remove failures outside the window
            cutoff = current_time - self.failure_window
            self._failures = [t for t in self._failures if t > cutoff]
            
            # Check if threshold exceeded
            if len(self._failures) >= self.failure_threshold:
                self._transition_to(CircuitState.OPEN)
                logger.warning(
                    f"CircuitBreaker '{self.name}' opened: "
                    f"{len(self._failures)} failures in {self.failure_window}s"
                )
    
    def is_open(self) -> bool:
        """
        Check if circuit is open (blocking calls).
        
        Returns:
            True if circuit is OPEN, False otherwise
        """
        return self.state == CircuitState.OPEN
    
    def allow_request(self) -> bool:
        """
        Check if a request should be allowed.
        
        Returns:
            True if request is allowed, False if blocked
        """
        with self._lock:
            self._check_state_transition()
            
            if self._state == CircuitState.CLOSED:
                return True
            
            if self._state == CircuitState.HALF_OPEN:
                # Allow one test request in HALF_OPEN
                return True
            
            # OPEN state - block requests
            return False
    
    def get_recovery_time(self) -> Optional[datetime]:
        """
        Get the time when circuit will attempt recovery.
        
        Returns:
            datetime when recovery will be attempted, or None if not OPEN
        """
        with self._lock:
            if self._state != CircuitState.OPEN or self._opened_at is None:
                return None
            
            recovery_timestamp = self._opened_at + self.recovery_timeout
            return datetime.fromtimestamp(recovery_timestamp)
    
    def get_stats(self) -> CircuitBreakerStats:
        """
        Get circuit breaker statistics.
        
        Returns:
            CircuitBreakerStats with current state
        """
        with self._lock:
            return CircuitBreakerStats(
                state=self._state,
                failures=len(self._failures),
                successes=self._successes,
                last_failure_time=self._last_failure_time,
                last_state_change=self._last_state_change
            )
    
    def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failures = []
            self._successes = 0
            self._last_failure_time = None
            self._last_state_change = time.time()
            self._opened_at = None
            
        logger.info(f"CircuitBreaker '{self.name}' reset to CLOSED")
    
    def _check_state_transition(self) -> None:
        """Check if state should transition based on time."""
        if self._state == CircuitState.OPEN and self._opened_at is not None:
            elapsed = time.time() - self._opened_at
            if elapsed >= self.recovery_timeout:
                self._transition_to(CircuitState.HALF_OPEN)
                logger.info(
                    f"CircuitBreaker '{self.name}' testing recovery: OPEN -> HALF_OPEN"
                )
    
    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state."""
        self._state = new_state
        self._last_state_change = time.time()
        
        if new_state == CircuitState.OPEN:
            self._opened_at = time.time()
        elif new_state == CircuitState.CLOSED:
            self._failures = []
            self._opened_at = None


class CircuitBreakerRegistry:
    """
    Registry for managing multiple circuit breakers.
    
    Provides named circuit breakers for different APIs.
    """
    
    def __init__(self):
        """Initialize the registry."""
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = threading.RLock()
    
    def get(
        self,
        name: str,
        failure_threshold: int = 5,
        failure_window: int = 60,
        recovery_timeout: int = 300
    ) -> CircuitBreaker:
        """
        Get or create a circuit breaker by name.
        
        Args:
            name: Name of the circuit breaker
            failure_threshold: Failures to trigger OPEN
            failure_window: Time window for counting failures
            recovery_timeout: Time before recovery attempt
            
        Returns:
            CircuitBreaker instance
        """
        with self._lock:
            if name not in self._breakers:
                self._breakers[name] = CircuitBreaker(
                    name=name,
                    failure_threshold=failure_threshold,
                    failure_window=failure_window,
                    recovery_timeout=recovery_timeout
                )
            return self._breakers[name]
    
    def get_all_stats(self) -> Dict[str, CircuitBreakerStats]:
        """
        Get statistics for all circuit breakers.
        
        Returns:
            Dict mapping names to CircuitBreakerStats
        """
        with self._lock:
            return {
                name: breaker.get_stats()
                for name, breaker in self._breakers.items()
            }
    
    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        with self._lock:
            for breaker in self._breakers.values():
                breaker.reset()


# Global registry instance
_circuit_breaker_registry: Optional[CircuitBreakerRegistry] = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """
    Get or create the global circuit breaker registry.
    
    Returns:
        CircuitBreakerRegistry singleton instance
    """
    global _circuit_breaker_registry
    
    if _circuit_breaker_registry is None:
        _circuit_breaker_registry = CircuitBreakerRegistry()
    
    return _circuit_breaker_registry


def get_circuit_breaker(name: str) -> CircuitBreaker:
    """
    Get a circuit breaker by name from the global registry.
    
    Args:
        name: Name of the circuit breaker (e.g., "yago", "conceptnet")
        
    Returns:
        CircuitBreaker instance
    """
    return get_circuit_breaker_registry().get(name)
