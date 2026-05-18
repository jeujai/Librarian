"""
Provider Resilience - Provider-agnostic resilience primitives

This module provides provider-agnostic resilience building blocks used by
AI service implementations (Gemini, DeepSeek, and future providers) to
handle failure modes uniformly.

Includes:
- ``ErrorType``: canonical classification of failure modes
- ``USER_FRIENDLY_ERROR_MESSAGES``: user-facing copy keyed by ``ErrorType``
- ``classify_error`` / ``get_user_friendly_message``: exception-to-type helpers
- ``ProviderError``: structured error record with recoverability metadata
- ``CircuitState`` / ``CircuitBreakerConfig`` / ``CircuitBreaker``: circuit
  breaker primitive that prevents cascade failures by temporarily blocking
  calls to an upstream provider
- ``CircuitBreakerOpenError``: raised when the breaker is open
- ``ErrorRateConfig`` / ``ErrorRateTracker``: sliding-window tracker that
  auto-disables streaming when the failure rate exceeds a threshold

This module is a relocation of the equivalent primitives previously defined
at the top of ``services/ai_service.py`` (as ``GeminiErrorType``,
``GeminiError``, ``GeminiCircuitBreaker``, etc.). Behavior is preserved
bit-for-bit; only the type names are generalized.
"""

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Error Types and User-Friendly Messages
# =============================================================================

class ErrorType(Enum):
    """Types of errors that can occur with Gemini API."""
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    INVALID_RESPONSE = "invalid_response"
    NETWORK_ERROR = "network_error"
    AUTHENTICATION = "authentication"
    CONTENT_BLOCKED = "content_blocked"
    QUOTA_EXCEEDED = "quota_exceeded"
    MODEL_OVERLOADED = "model_overloaded"
    CIRCUIT_BREAKER = "circuit_breaker"
    UNKNOWN = "unknown"


# User-friendly error messages mapped to error types
USER_FRIENDLY_ERROR_MESSAGES: Dict[ErrorType, str] = {
    ErrorType.TIMEOUT: (
        "Response is taking longer than expected. Please try again with a shorter "
        "question or simpler request."
    ),
    ErrorType.RATE_LIMIT: (
        "Service is busy. Please wait a moment and try again."
    ),
    ErrorType.INVALID_RESPONSE: (
        "Unable to generate response. Please try rephrasing your question."
    ),
    ErrorType.NETWORK_ERROR: (
        "Connection issue. Please check your network and try again."
    ),
    ErrorType.AUTHENTICATION: (
        "Service configuration error. Please contact support."
    ),
    ErrorType.CONTENT_BLOCKED: (
        "I cannot respond to that request. Please try a different question."
    ),
    ErrorType.QUOTA_EXCEEDED: (
        "Service quota exceeded. Please try again later or contact support."
    ),
    ErrorType.MODEL_OVERLOADED: (
        "The AI service is currently overloaded. Please try again in a few moments."
    ),
    ErrorType.CIRCUIT_BREAKER: (
        "Service is temporarily unavailable. Please try again in a moment."
    ),
    ErrorType.UNKNOWN: (
        "An unexpected error occurred. Please try again."
    ),
}


def classify_error(error: Exception) -> ErrorType:
    """
    Classify an exception into a GeminiErrorType.
    
    Args:
        error: The exception to classify
        
    Returns:
        The classified error type
    """
    error_str = str(error).lower()
    error_type_name = type(error).__name__.lower()
    
    # Timeout errors
    if isinstance(error, asyncio.TimeoutError) or "timeout" in error_str:
        return ErrorType.TIMEOUT
    
    # Rate limit errors
    if "rate" in error_str and "limit" in error_str:
        return ErrorType.RATE_LIMIT
    if "429" in error_str or "too many requests" in error_str:
        return ErrorType.RATE_LIMIT
    
    # Quota errors
    if "quota" in error_str or "exceeded" in error_str:
        return ErrorType.QUOTA_EXCEEDED
    
    # Authentication errors
    if "auth" in error_str or "api key" in error_str or "401" in error_str:
        return ErrorType.AUTHENTICATION
    if "permission" in error_str or "403" in error_str:
        return ErrorType.AUTHENTICATION
    
    # Content blocked
    if "blocked" in error_str or "safety" in error_str or "harmful" in error_str:
        return ErrorType.CONTENT_BLOCKED
    
    # Model overloaded
    if "overloaded" in error_str or "503" in error_str or "unavailable" in error_str:
        return ErrorType.MODEL_OVERLOADED
    
    # Network errors
    if "connection" in error_str or "network" in error_str:
        return ErrorType.NETWORK_ERROR
    if "socket" in error_type_name or "connection" in error_type_name:
        return ErrorType.NETWORK_ERROR
    
    # Invalid response
    if "invalid" in error_str or "parse" in error_str or "decode" in error_str:
        return ErrorType.INVALID_RESPONSE
    
    return ErrorType.UNKNOWN


def classify_http_status(status_code: int, body_excerpt: str = "") -> ErrorType:
    """
    Classify an HTTP status code into an ``ErrorType``.

    This is a pure mapping from HTTP status codes to the canonical
    ``ErrorType`` values used by provider resilience primitives. It is
    intended for cases where a provider call failed with a non-2xx HTTP
    response and we want to translate the raw status into our resilience
    taxonomy (so retry/backoff policies apply uniformly across providers).

    Mapping rules:
    - 401, 403                -> ``ErrorType.AUTHENTICATION``
    - 429                     -> ``ErrorType.RATE_LIMIT``
    - 500 <= status < 600     -> ``ErrorType.MODEL_OVERLOADED``
    - 400 <= status < 500     -> ``ErrorType.INVALID_RESPONSE``
      (any other 4xx not matched above)
    - anything else           -> ``ErrorType.UNKNOWN``
      (e.g. 2xx, 3xx, values < 400, values >= 600)

    Args:
        status_code: The HTTP status code returned by the provider.
        body_excerpt: Optional excerpt of the response body. Reserved for
            future heuristics (e.g. inspecting provider-specific error
            payloads). Currently unused in the classification logic.

    Returns:
        The classified ``ErrorType``. Pure function: no I/O, no logging,
        no exceptions raised.
    """
    # body_excerpt is intentionally unused for now; accepted for forward
    # compatibility so callers can pass it without changing their signature
    # when future heuristics are added.
    del body_excerpt

    if status_code == 401 or status_code == 403:
        return ErrorType.AUTHENTICATION
    if status_code == 429:
        return ErrorType.RATE_LIMIT
    if 500 <= status_code < 600:
        return ErrorType.MODEL_OVERLOADED
    if 400 <= status_code < 500:
        return ErrorType.INVALID_RESPONSE
    return ErrorType.UNKNOWN


def get_user_friendly_message(error: Exception) -> str:
    """
    Get a user-friendly error message for an exception.
    
    Args:
        error: The exception to get a message for
        
    Returns:
        A user-friendly error message string
    """
    error_type = classify_error(error)
    return USER_FRIENDLY_ERROR_MESSAGES[error_type]


@dataclass
class ProviderError:
    """Structured error information for Gemini API errors."""
    error_type: ErrorType
    user_message: str
    technical_message: str
    recoverable: bool
    retry_after_seconds: Optional[float] = None
    
    @classmethod
    def from_exception(cls, error: Exception) -> "ProviderError":
        """Create a GeminiError from an exception."""
        error_type = classify_error(error)
        user_message = USER_FRIENDLY_ERROR_MESSAGES[error_type]
        
        # Determine if error is recoverable
        recoverable = error_type in {
            ErrorType.TIMEOUT,
            ErrorType.RATE_LIMIT,
            ErrorType.NETWORK_ERROR,
            ErrorType.MODEL_OVERLOADED,
        }
        
        # Suggest retry time for rate limits
        retry_after = None
        if error_type == ErrorType.RATE_LIMIT:
            retry_after = 60.0  # Default 60 seconds for rate limits
        elif error_type == ErrorType.MODEL_OVERLOADED:
            retry_after = 30.0  # Default 30 seconds for overload
        
        return cls(
            error_type=error_type,
            user_message=user_message,
            technical_message=str(error),
            recoverable=recoverable,
            retry_after_seconds=retry_after
        )


# =============================================================================
# Circuit Breaker for Gemini API
# =============================================================================

class CircuitState(Enum):
    """Circuit breaker states for Gemini API."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for Gemini circuit breaker."""
    failure_threshold: int = 5  # Failures before opening
    reset_timeout_seconds: float = 60.0  # Time before half-open
    half_open_max_calls: int = 3  # Calls allowed in half-open state


class CircuitBreaker:
    """
    Circuit breaker for Gemini API calls.
    
    Prevents cascade failures by temporarily blocking requests
    when the API is experiencing issues.
    
    States:
    - CLOSED: Normal operation, requests allowed
    - OPEN: Blocking requests after too many failures
    - HALF_OPEN: Testing recovery with limited requests
    """
    
    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._last_state_change: Optional[float] = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
        
        logger.info(
            f"GeminiCircuitBreaker initialized: "
            f"threshold={self.config.failure_threshold}, "
            f"reset_timeout={self.config.reset_timeout_seconds}s"
        )
    
    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state
    
    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking calls)."""
        return self._state == CircuitState.OPEN
    
    async def _check_state_transition(self) -> None:
        """Check if state should transition based on time."""
        if self._state == CircuitState.OPEN and self._last_failure_time is not None:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.config.reset_timeout_seconds:
                self._state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                self._last_state_change = time.time()
                logger.info("GeminiCircuitBreaker: OPEN -> HALF_OPEN (testing recovery)")
    
    async def allow_request(self) -> bool:
        """
        Check if a request should be allowed.
        
        Returns:
            True if request is allowed, False if blocked
        """
        async with self._lock:
            await self._check_state_transition()
            
            if self._state == CircuitState.CLOSED:
                return True
            
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.config.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False
            
            # OPEN state - block requests
            return False
    
    async def record_success(self) -> None:
        """Record a successful API call."""
        async with self._lock:
            self._success_count += 1
            
            if self._state == CircuitState.HALF_OPEN:
                # Successful call in half-open state closes the circuit
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._last_state_change = time.time()
                logger.info("GeminiCircuitBreaker: HALF_OPEN -> CLOSED (recovered)")
    
    async def record_failure(self) -> None:
        """Record a failed API call."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == CircuitState.HALF_OPEN:
                # Failure in half-open state reopens the circuit
                self._state = CircuitState.OPEN
                self._last_state_change = time.time()
                logger.warning("GeminiCircuitBreaker: HALF_OPEN -> OPEN (failure during recovery)")
                return
            
            if self._state == CircuitState.CLOSED:
                if self._failure_count >= self.config.failure_threshold:
                    self._state = CircuitState.OPEN
                    self._last_state_change = time.time()
                    logger.warning(
                        f"GeminiCircuitBreaker: CLOSED -> OPEN "
                        f"({self._failure_count} failures)"
                    )
    
    async def call(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute function with circuit breaker protection.
        
        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result of func
            
        Raises:
            CircuitBreakerOpenError: If circuit is open
            Exception: If func raises an exception
        """
        if not await self.allow_request():
            raise CircuitBreakerOpenError(
                "Gemini API circuit breaker is open. Please try again later."
            )
        
        try:
            result = await func(*args, **kwargs)
            await self.record_success()
            return result
        except Exception as e:
            await self.record_failure()
            raise
    
    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return {
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "last_failure_time": self._last_failure_time,
            "last_state_change": self._last_state_change,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "reset_timeout_seconds": self.config.reset_timeout_seconds,
                "half_open_max_calls": self.config.half_open_max_calls
            }
        }
    
    async def reset(self) -> None:
        """Reset circuit breaker to initial state."""
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
            self._last_state_change = time.time()
            self._half_open_calls = 0
            logger.info("GeminiCircuitBreaker reset to CLOSED")


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and blocking requests."""
    pass


# =============================================================================
# Error Rate Tracker for Streaming Disable
# =============================================================================

@dataclass
class ErrorRateConfig:
    """Configuration for error rate tracking."""
    window_size_seconds: float = 300.0  # 5 minute sliding window
    disable_threshold: float = 0.5  # 50% error rate to disable streaming
    enable_threshold: float = 0.3  # 30% error rate to re-enable streaming
    min_samples: int = 10  # Minimum samples before making decisions


class ErrorRateTracker:
    """
    Tracks error rate over a sliding window.
    
    Used to automatically disable streaming when error rate is too high.
    """
    
    def __init__(self, config: Optional[ErrorRateConfig] = None):
        self.config = config or ErrorRateConfig()
        self._calls: deque = deque()  # (timestamp, success: bool)
        self._streaming_enabled = True
        self._lock = asyncio.Lock()
        
        logger.info(
            f"ErrorRateTracker initialized: "
            f"window={self.config.window_size_seconds}s, "
            f"disable_threshold={self.config.disable_threshold}"
        )
    
    async def record_call(self, success: bool) -> None:
        """Record a call result."""
        async with self._lock:
            current_time = time.time()
            self._calls.append((current_time, success))
            
            # Remove old entries outside the window
            cutoff = current_time - self.config.window_size_seconds
            while self._calls and self._calls[0][0] < cutoff:
                self._calls.popleft()
            
            # Check if we should toggle streaming
            await self._check_streaming_state()
    
    async def _check_streaming_state(self) -> None:
        """Check if streaming should be enabled or disabled."""
        if len(self._calls) < self.config.min_samples:
            return  # Not enough data
        
        error_rate = self.get_error_rate()
        
        if self._streaming_enabled and error_rate >= self.config.disable_threshold:
            self._streaming_enabled = False
            logger.warning(
                f"Streaming disabled due to high error rate: {error_rate:.2%}"
            )
        elif not self._streaming_enabled and error_rate <= self.config.enable_threshold:
            self._streaming_enabled = True
            logger.info(
                f"Streaming re-enabled, error rate dropped to: {error_rate:.2%}"
            )
    
    def get_error_rate(self) -> float:
        """Get current error rate."""
        if not self._calls:
            return 0.0
        
        failures = sum(1 for _, success in self._calls if not success)
        return failures / len(self._calls)
    
    @property
    def streaming_enabled(self) -> bool:
        """Check if streaming is currently enabled."""
        return self._streaming_enabled
    
    def get_stats(self) -> Dict[str, Any]:
        """Get error rate statistics."""
        return {
            "streaming_enabled": self._streaming_enabled,
            "error_rate": self.get_error_rate(),
            "total_calls": len(self._calls),
            "window_size_seconds": self.config.window_size_seconds,
            "disable_threshold": self.config.disable_threshold,
            "enable_threshold": self.config.enable_threshold
        }
