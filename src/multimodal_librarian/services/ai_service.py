"""
AI Service - Gemini-only AI provider

This module provides a unified interface for the Gemini AI provider
with error handling, response formatting, performance profiling, and streaming support.

Includes:
- User-friendly error messages for all error types
- Circuit breaker pattern for API resilience
- Error rate tracking with automatic streaming disable
"""

import asyncio
import logging
import statistics
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

import google.generativeai as genai

from ..config import get_settings

logger = logging.getLogger(__name__)


# =============================================================================
# Error Types and User-Friendly Messages
# =============================================================================

class GeminiErrorType(Enum):
    """Types of errors that can occur with Gemini API."""
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    INVALID_RESPONSE = "invalid_response"
    NETWORK_ERROR = "network_error"
    AUTHENTICATION = "authentication"
    CONTENT_BLOCKED = "content_blocked"
    QUOTA_EXCEEDED = "quota_exceeded"
    MODEL_OVERLOADED = "model_overloaded"
    UNKNOWN = "unknown"


# User-friendly error messages mapped to error types
USER_FRIENDLY_ERROR_MESSAGES: Dict[GeminiErrorType, str] = {
    GeminiErrorType.TIMEOUT: (
        "Response is taking longer than expected. Please try again with a shorter "
        "question or simpler request."
    ),
    GeminiErrorType.RATE_LIMIT: (
        "Service is busy. Please wait a moment and try again."
    ),
    GeminiErrorType.INVALID_RESPONSE: (
        "Unable to generate response. Please try rephrasing your question."
    ),
    GeminiErrorType.NETWORK_ERROR: (
        "Connection issue. Please check your network and try again."
    ),
    GeminiErrorType.AUTHENTICATION: (
        "Service configuration error. Please contact support."
    ),
    GeminiErrorType.CONTENT_BLOCKED: (
        "I cannot respond to that request. Please try a different question."
    ),
    GeminiErrorType.QUOTA_EXCEEDED: (
        "Service quota exceeded. Please try again later or contact support."
    ),
    GeminiErrorType.MODEL_OVERLOADED: (
        "The AI service is currently overloaded. Please try again in a few moments."
    ),
    GeminiErrorType.UNKNOWN: (
        "An unexpected error occurred. Please try again."
    ),
}


def classify_error(error: Exception) -> GeminiErrorType:
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
        return GeminiErrorType.TIMEOUT
    
    # Rate limit errors
    if "rate" in error_str and "limit" in error_str:
        return GeminiErrorType.RATE_LIMIT
    if "429" in error_str or "too many requests" in error_str:
        return GeminiErrorType.RATE_LIMIT
    
    # Quota errors
    if "quota" in error_str or "exceeded" in error_str:
        return GeminiErrorType.QUOTA_EXCEEDED
    
    # Authentication errors
    if "auth" in error_str or "api key" in error_str or "401" in error_str:
        return GeminiErrorType.AUTHENTICATION
    if "permission" in error_str or "403" in error_str:
        return GeminiErrorType.AUTHENTICATION
    
    # Content blocked
    if "blocked" in error_str or "safety" in error_str or "harmful" in error_str:
        return GeminiErrorType.CONTENT_BLOCKED
    
    # Model overloaded
    if "overloaded" in error_str or "503" in error_str or "unavailable" in error_str:
        return GeminiErrorType.MODEL_OVERLOADED
    
    # Network errors
    if "connection" in error_str or "network" in error_str:
        return GeminiErrorType.NETWORK_ERROR
    if "socket" in error_type_name or "connection" in error_type_name:
        return GeminiErrorType.NETWORK_ERROR
    
    # Invalid response
    if "invalid" in error_str or "parse" in error_str or "decode" in error_str:
        return GeminiErrorType.INVALID_RESPONSE
    
    return GeminiErrorType.UNKNOWN


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
class GeminiError:
    """Structured error information for Gemini API errors."""
    error_type: GeminiErrorType
    user_message: str
    technical_message: str
    recoverable: bool
    retry_after_seconds: Optional[float] = None
    
    @classmethod
    def from_exception(cls, error: Exception) -> "GeminiError":
        """Create a GeminiError from an exception."""
        error_type = classify_error(error)
        user_message = USER_FRIENDLY_ERROR_MESSAGES[error_type]
        
        # Determine if error is recoverable
        recoverable = error_type in {
            GeminiErrorType.TIMEOUT,
            GeminiErrorType.RATE_LIMIT,
            GeminiErrorType.NETWORK_ERROR,
            GeminiErrorType.MODEL_OVERLOADED,
        }
        
        # Suggest retry time for rate limits
        retry_after = None
        if error_type == GeminiErrorType.RATE_LIMIT:
            retry_after = 60.0  # Default 60 seconds for rate limits
        elif error_type == GeminiErrorType.MODEL_OVERLOADED:
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

class GeminiCircuitState(Enum):
    """Circuit breaker states for Gemini API."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Blocking requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class GeminiCircuitBreakerConfig:
    """Configuration for Gemini circuit breaker."""
    failure_threshold: int = 5  # Failures before opening
    reset_timeout_seconds: float = 60.0  # Time before half-open
    half_open_max_calls: int = 3  # Calls allowed in half-open state


class GeminiCircuitBreaker:
    """
    Circuit breaker for Gemini API calls.
    
    Prevents cascade failures by temporarily blocking requests
    when the API is experiencing issues.
    
    States:
    - CLOSED: Normal operation, requests allowed
    - OPEN: Blocking requests after too many failures
    - HALF_OPEN: Testing recovery with limited requests
    """
    
    def __init__(self, config: Optional[GeminiCircuitBreakerConfig] = None):
        self.config = config or GeminiCircuitBreakerConfig()
        self._state = GeminiCircuitState.CLOSED
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
    def state(self) -> GeminiCircuitState:
        """Get current circuit state."""
        return self._state
    
    @property
    def is_open(self) -> bool:
        """Check if circuit is open (blocking calls)."""
        return self._state == GeminiCircuitState.OPEN
    
    async def _check_state_transition(self) -> None:
        """Check if state should transition based on time."""
        if self._state == GeminiCircuitState.OPEN and self._last_failure_time is not None:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.config.reset_timeout_seconds:
                self._state = GeminiCircuitState.HALF_OPEN
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
            
            if self._state == GeminiCircuitState.CLOSED:
                return True
            
            if self._state == GeminiCircuitState.HALF_OPEN:
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
            
            if self._state == GeminiCircuitState.HALF_OPEN:
                # Successful call in half-open state closes the circuit
                self._state = GeminiCircuitState.CLOSED
                self._failure_count = 0
                self._last_state_change = time.time()
                logger.info("GeminiCircuitBreaker: HALF_OPEN -> CLOSED (recovered)")
    
    async def record_failure(self) -> None:
        """Record a failed API call."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            
            if self._state == GeminiCircuitState.HALF_OPEN:
                # Failure in half-open state reopens the circuit
                self._state = GeminiCircuitState.OPEN
                self._last_state_change = time.time()
                logger.warning("GeminiCircuitBreaker: HALF_OPEN -> OPEN (failure during recovery)")
                return
            
            if self._state == GeminiCircuitState.CLOSED:
                if self._failure_count >= self.config.failure_threshold:
                    self._state = GeminiCircuitState.OPEN
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
            self._state = GeminiCircuitState.CLOSED
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


# Performance Metrics Dataclasses

@dataclass
class APICallMetrics:
    """Metrics for a single API call."""
    call_id: str
    start_time: float
    end_time: float
    duration_ms: int
    prompt_chars: int
    prompt_tokens_estimate: int
    response_chars: int
    response_tokens: int
    success: bool
    error: Optional[str] = None
    request_prep_time_ms: int = 0
    api_call_time_ms: int = 0
    response_processing_time_ms: int = 0


@dataclass
class PerformanceStats:
    """Aggregated performance statistics."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    timeout_count: int = 0
    avg_duration_ms: float = 0.0
    p50_duration_ms: float = 0.0
    p95_duration_ms: float = 0.0
    p99_duration_ms: float = 0.0
    avg_prompt_tokens: float = 0.0
    avg_response_tokens: float = 0.0


@dataclass
class StreamingChunk:
    """A chunk of streaming response."""
    content: str
    is_final: bool
    cumulative_tokens: int
    chunk_index: int
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


class AIProvider(str, Enum):
    """Supported AI providers."""
    GEMINI = "gemini"


@dataclass
class AIResponse:
    """Standardized AI response format."""
    content: str
    provider: str
    model: str
    tokens_used: int
    processing_time_ms: int
    confidence_score: float = 1.0
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class GeminiProvider:
    """Google Gemini AI provider with performance profiling and streaming support."""

    # Configuration constants
    DEFAULT_TIMEOUT_SECONDS = 25.0
    DEFAULT_MAX_CONTEXT_CHARS = 6000
    DEFAULT_MAX_HISTORY_MESSAGES = 3
    SLOW_CALL_THRESHOLD_SECONDS = 10.0
    METRICS_HISTORY_SIZE = 100

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash",
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS
    ):
        self.api_key = api_key
        self.model = model
        self.provider_name = "gemini"
        self._configured = False
        self._client = None
        self.embedding_model = "models/text-embedding-004"
        
        # Performance configuration
        self.timeout_seconds = timeout_seconds
        self.max_context_chars = max_context_chars
        
        # Metrics tracking
        self._metrics_history: deque[APICallMetrics] = deque(maxlen=self.METRICS_HISTORY_SIZE)
        self._total_calls = 0
        self._successful_calls = 0
        self._failed_calls = 0
        self._timeout_count = 0

    def _ensure_configured(self):
        """Lazily configure the Gemini client (called in thread pool)."""
        if not self._configured:
            genai.configure(api_key=self.api_key)
            self._client = genai.GenerativeModel(self.model)
            self._configured = True

    @property
    def client(self):
        """Get the client, ensuring it's configured."""
        self._ensure_configured()
        return self._client

    def _truncate_context(self, context: str) -> str:
        """Truncate context to max_context_chars."""
        if len(context) <= self.max_context_chars:
            return context
        # Truncate and add indicator
        truncated = context[:self.max_context_chars - 50]
        return truncated + "\n\n[Context truncated for length...]"

    def _limit_conversation_history(
        self,
        messages: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """Limit conversation history to most recent messages."""
        # Keep system messages and last N user/assistant messages
        system_messages = [m for m in messages if m.get("role") == "system"]
        other_messages = [m for m in messages if m.get("role") != "system"]
        
        # Take only the last DEFAULT_MAX_HISTORY_MESSAGES
        limited_others = other_messages[-self.DEFAULT_MAX_HISTORY_MESSAGES:]
        
        return system_messages + limited_others

    def _record_metrics(self, metrics: APICallMetrics) -> None:
        """Record API call metrics and log warnings for slow calls."""
        self._metrics_history.append(metrics)
        self._total_calls += 1
        
        if metrics.success:
            self._successful_calls += 1
        else:
            self._failed_calls += 1
            if metrics.error and "timeout" in metrics.error.lower():
                self._timeout_count += 1
        
        # Log detailed metrics
        logger.info(
            f"Gemini API call metrics: call_id={metrics.call_id}, "
            f"duration_ms={metrics.duration_ms}, "
            f"prompt_chars={metrics.prompt_chars}, "
            f"prompt_tokens_est={metrics.prompt_tokens_estimate}, "
            f"success={metrics.success}"
        )
        
        # Log warning for slow calls
        if metrics.duration_ms > self.SLOW_CALL_THRESHOLD_SECONDS * 1000:
            logger.warning(
                f"Slow Gemini API call detected: call_id={metrics.call_id}, "
                f"duration_ms={metrics.duration_ms}, "
                f"request_prep_ms={metrics.request_prep_time_ms}, "
                f"api_call_ms={metrics.api_call_time_ms}, "
                f"response_processing_ms={metrics.response_processing_time_ms}, "
                f"prompt_chars={metrics.prompt_chars}"
            )

    def get_performance_stats(self) -> PerformanceStats:
        """Get aggregated performance statistics."""
        if not self._metrics_history:
            return PerformanceStats()
        
        durations = [m.duration_ms for m in self._metrics_history if m.success]
        prompt_tokens = [m.prompt_tokens_estimate for m in self._metrics_history]
        response_tokens = [m.response_tokens for m in self._metrics_history if m.success]
        
        stats = PerformanceStats(
            total_calls=self._total_calls,
            successful_calls=self._successful_calls,
            failed_calls=self._failed_calls,
            timeout_count=self._timeout_count
        )
        
        if durations:
            sorted_durations = sorted(durations)
            stats.avg_duration_ms = statistics.mean(durations)
            stats.p50_duration_ms = statistics.median(durations)
            stats.p95_duration_ms = sorted_durations[int(len(sorted_durations) * 0.95)] if len(sorted_durations) >= 20 else max(durations)
            stats.p99_duration_ms = sorted_durations[int(len(sorted_durations) * 0.99)] if len(sorted_durations) >= 100 else max(durations)
        
        if prompt_tokens:
            stats.avg_prompt_tokens = statistics.mean(prompt_tokens)
        
        if response_tokens:
            stats.avg_response_tokens = statistics.mean(response_tokens)
        
        return stats

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        context: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024  # Reduced default for chat responses
    ) -> AIResponse:
        """Generate response using Gemini with performance profiling."""
        call_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        request_prep_start = start_time
        
        metrics = APICallMetrics(
            call_id=call_id,
            start_time=start_time,
            end_time=0,
            duration_ms=0,
            prompt_chars=0,
            prompt_tokens_estimate=0,
            response_chars=0,
            response_tokens=0,
            success=False
        )

        try:
            # Limit conversation history
            limited_messages = self._limit_conversation_history(messages)
            
            # Truncate context if needed
            truncated_context = self._truncate_context(context) if context else None
            
            # Build prompt from messages and context
            prompt = self._build_prompt(limited_messages, truncated_context)
            
            # Record prompt metrics
            metrics.prompt_chars = len(prompt)
            metrics.prompt_tokens_estimate = self._estimate_tokens_from_chars(len(prompt))
            
            request_prep_end = time.time()
            metrics.request_prep_time_ms = int((request_prep_end - request_prep_start) * 1000)
            
            logger.info(
                f"Gemini API call starting: call_id={call_id}, "
                f"prompt_chars={metrics.prompt_chars}, "
                f"prompt_tokens_est={metrics.prompt_tokens_estimate}"
            )

            # Configure generation with optimized parameters
            generation_config = genai.types.GenerationConfig(
                temperature=temperature,
                top_p=0.8,
                top_k=40,
                max_output_tokens=max_tokens
            )

            # Ensure client is configured (run in thread pool to avoid blocking)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._ensure_configured)

            api_call_start = time.time()
            
            # Generate response with timeout
            try:
                response = await asyncio.wait_for(
                    self._client.generate_content_async(
                        prompt,
                        generation_config=generation_config
                    ),
                    timeout=self.timeout_seconds
                )
            except asyncio.TimeoutError:
                metrics.error = f"Timeout after {self.timeout_seconds}s"
                metrics.end_time = time.time()
                metrics.duration_ms = int((metrics.end_time - start_time) * 1000)
                metrics.api_call_time_ms = int((time.time() - api_call_start) * 1000)
                self._record_metrics(metrics)
                
                # Return graceful error response instead of raising
                return AIResponse(
                    content="I apologize, but the response is taking longer than expected. Please try again with a shorter question or simpler request.",
                    provider="gemini",
                    model=self.model,
                    tokens_used=0,
                    processing_time_ms=metrics.duration_ms,
                    confidence_score=0.0,
                    metadata={
                        "finish_reason": "timeout",
                        "error": metrics.error,
                        "call_id": call_id
                    }
                )
            
            api_call_end = time.time()
            metrics.api_call_time_ms = int((api_call_end - api_call_start) * 1000)
            
            response_processing_start = time.time()
            
            response_text = response.text
            metrics.response_chars = len(response_text)
            metrics.response_tokens = self._estimate_tokens_from_chars(len(response_text))
            
            response_processing_end = time.time()
            metrics.response_processing_time_ms = int((response_processing_end - response_processing_start) * 1000)
            
            metrics.end_time = time.time()
            metrics.duration_ms = int((metrics.end_time - start_time) * 1000)
            metrics.success = True
            
            self._record_metrics(metrics)

            return AIResponse(
                content=response_text,
                provider="gemini",
                model=self.model,
                tokens_used=self._estimate_tokens(prompt, response_text),
                processing_time_ms=metrics.duration_ms,
                metadata={
                    "finish_reason": "completed",
                    "safety_ratings": getattr(response, 'safety_ratings', []),
                    "call_id": call_id,
                    "request_prep_ms": metrics.request_prep_time_ms,
                    "api_call_ms": metrics.api_call_time_ms,
                    "response_processing_ms": metrics.response_processing_time_ms
                }
            )

        except Exception as e:
            metrics.end_time = time.time()
            metrics.duration_ms = int((metrics.end_time - start_time) * 1000)
            metrics.error = str(e)
            self._record_metrics(metrics)
            
            logger.error(f"Gemini API error: call_id={call_id}, error={e}")
            raise

    def _estimate_tokens_from_chars(self, char_count: int) -> int:
        """Estimate token count from character count (rough approximation)."""
        # Roughly 4 characters per token for English text
        return int(char_count / 4)

    async def generate_response_stream(
        self,
        messages: List[Dict[str, str]],
        context: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> AsyncGenerator[StreamingChunk, None]:
        """Generate streaming response using Gemini API.
        
        Yields StreamingChunk objects as content arrives from the API.
        """
        call_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        
        try:
            # Limit conversation history
            limited_messages = self._limit_conversation_history(messages)
            
            # Truncate context if needed
            truncated_context = self._truncate_context(context) if context else None
            
            # Build prompt from messages and context
            prompt = self._build_prompt(limited_messages, truncated_context)
            
            prompt_chars = len(prompt)
            prompt_tokens_est = self._estimate_tokens_from_chars(prompt_chars)
            
            logger.info(
                f"Gemini streaming call starting: call_id={call_id}, "
                f"prompt_chars={prompt_chars}, "
                f"prompt_tokens_est={prompt_tokens_est}"
            )

            # Configure generation with optimized parameters
            generation_config = genai.types.GenerationConfig(
                temperature=temperature,
                top_p=0.8,
                top_k=40,
                max_output_tokens=max_tokens
            )

            # Ensure client is configured
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._ensure_configured)

            # Generate streaming response
            chunk_index = 0
            cumulative_content = ""
            cumulative_tokens = 0
            
            try:
                response = await asyncio.wait_for(
                    self._client.generate_content_async(
                        prompt,
                        generation_config=generation_config,
                        stream=True
                    ),
                    timeout=self.timeout_seconds
                )
                
                async for chunk in response:
                    if hasattr(chunk, 'text') and chunk.text:
                        chunk_content = chunk.text
                        cumulative_content += chunk_content
                        cumulative_tokens = self._estimate_tokens_from_chars(
                            len(cumulative_content)
                        )
                        
                        yield StreamingChunk(
                            content=chunk_content,
                            is_final=False,
                            cumulative_tokens=cumulative_tokens,
                            chunk_index=chunk_index
                        )
                        chunk_index += 1
                
                # Yield final chunk
                duration_ms = int((time.time() - start_time) * 1000)
                yield StreamingChunk(
                    content="",
                    is_final=True,
                    cumulative_tokens=cumulative_tokens,
                    chunk_index=chunk_index
                )
                
                logger.info(
                    f"Gemini streaming completed: call_id={call_id}, "
                    f"duration_ms={duration_ms}, "
                    f"chunks={chunk_index}, "
                    f"total_tokens={cumulative_tokens}"
                )
                
            except asyncio.TimeoutError:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.warning(
                    f"Gemini streaming timeout: call_id={call_id}, "
                    f"duration_ms={duration_ms}"
                )
                yield StreamingChunk(
                    content="",
                    is_final=True,
                    cumulative_tokens=cumulative_tokens,
                    chunk_index=chunk_index,
                    error=f"Timeout after {self.timeout_seconds}s"
                )
                
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"Gemini streaming error: call_id={call_id}, "
                f"duration_ms={duration_ms}, error={e}"
            )
            yield StreamingChunk(
                content="",
                is_final=True,
                cumulative_tokens=0,
                chunk_index=0,
                error=str(e)
            )

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using Gemini."""
        try:
            embeddings = []
            for text in texts:
                result = genai.embed_content(
                    model=self.embedding_model,
                    content=text,
                    task_type="retrieval_document"
                )
                embeddings.append(result['embedding'])
            return embeddings
        except Exception as e:
            logger.error(f"Gemini embedding error: {e}")
            raise

    def is_available(self) -> bool:
        """Check if Gemini is available."""
        try:
            genai.list_models()
            return True
        except Exception:
            return False

    def _build_prompt(
        self,
        messages: List[Dict[str, str]],
        context: Optional[str] = None
    ) -> str:
        """Build prompt from messages and context."""
        prompt_parts = []

        # Add system context if provided
        if context:
            prompt_parts.append(f"Context:\n{context}\n")

        # Add conversation history
        for message in messages:
            role = message.get("role", "user")
            content = message.get("content", "")

            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")

        return "\n\n".join(prompt_parts)

    def _estimate_tokens(self, prompt: str, response: str) -> int:
        """Estimate token usage (rough approximation)."""
        return int(len((prompt + response).split()) * 1.3)


class AIService:
    """
    Main AI service using Gemini with performance tracking, circuit breaker,
    and error rate-based streaming control.
    
    Features:
    - User-friendly error messages for all error types
    - Circuit breaker pattern for API resilience
    - Error rate tracking with automatic streaming disable
    - Graceful degradation on failures
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.provider: Optional[GeminiProvider] = None
        self.providers: Dict[AIProvider, GeminiProvider] = {}
        self.primary_provider: Optional[AIProvider] = None
        
        # Circuit breaker for API resilience
        self._circuit_breaker = GeminiCircuitBreaker()
        
        # Error rate tracker for streaming control
        self._error_rate_tracker = ErrorRateTracker()
        
        self._initialize_provider()

    def _initialize_provider(self) -> None:
        """Initialize Gemini provider.

        IMPORTANT: This method does NOT call is_available() to avoid blocking
        the event loop with synchronous API calls. Provider is registered
        based on API key availability only.
        """
        gemini_key = getattr(self.settings, 'gemini_api_key', None)
        if gemini_key:
            try:
                self.provider = GeminiProvider(gemini_key)
                self.providers[AIProvider.GEMINI] = self.provider
                self.primary_provider = AIProvider.GEMINI
                logger.info("Gemini provider registered (API key present)")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini provider: {e}")

        if not self.provider:
            logger.error("Gemini provider not available! Please configure GEMINI_API_KEY.")

    def _create_error_response(
        self,
        error: Exception,
        call_id: str = "",
        processing_time_ms: int = 0
    ) -> AIResponse:
        """
        Create a user-friendly error response instead of raising an exception.
        
        Args:
            error: The exception that occurred
            call_id: Optional call ID for tracking
            processing_time_ms: Processing time before error
            
        Returns:
            AIResponse with user-friendly error message
        """
        gemini_error = GeminiError.from_exception(error)
        
        return AIResponse(
            content=gemini_error.user_message,
            provider="gemini",
            model=self.provider.model if self.provider else "unknown",
            tokens_used=0,
            processing_time_ms=processing_time_ms,
            confidence_score=0.0,
            metadata={
                "finish_reason": "error",
                "error_type": gemini_error.error_type.value,
                "error": gemini_error.technical_message,
                "recoverable": gemini_error.recoverable,
                "retry_after_seconds": gemini_error.retry_after_seconds,
                "call_id": call_id
            }
        )

    async def generate_response(
        self,
        messages: List[Dict[str, str]],
        context: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,  # Reduced default for chat
        preferred_provider: Optional[AIProvider] = None
    ) -> AIResponse:
        """
        Generate AI response using Gemini with circuit breaker protection.
        
        Returns a graceful error response instead of raising exceptions.
        """
        if not self.provider:
            return AIResponse(
                content=USER_FRIENDLY_ERROR_MESSAGES[GeminiErrorType.AUTHENTICATION],
                provider="gemini",
                model="unknown",
                tokens_used=0,
                processing_time_ms=0,
                confidence_score=0.0,
                metadata={
                    "finish_reason": "error",
                    "error_type": GeminiErrorType.AUTHENTICATION.value,
                    "error": "Gemini provider not configured. Set GEMINI_API_KEY.",
                    "recoverable": False
                }
            )

        start_time = time.time()
        call_id = str(uuid.uuid4())[:8]
        
        try:
            # Check circuit breaker
            if not await self._circuit_breaker.allow_request():
                logger.warning(f"Circuit breaker open, blocking request: call_id={call_id}")
                await self._error_rate_tracker.record_call(success=False)
                return AIResponse(
                    content="Service is temporarily unavailable due to high error rate. Please try again in a moment.",
                    provider="gemini",
                    model=self.provider.model,
                    tokens_used=0,
                    processing_time_ms=0,
                    confidence_score=0.0,
                    metadata={
                        "finish_reason": "circuit_breaker_open",
                        "error_type": "circuit_breaker",
                        "circuit_breaker_stats": self._circuit_breaker.get_stats(),
                        "call_id": call_id
                    }
                )
            
            logger.info(f"Generating response with Gemini: call_id={call_id}")
            response = await self.provider.generate_response(
                messages=messages,
                context=context,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            # Check if response indicates an error (e.g., timeout)
            if response.metadata and response.metadata.get("finish_reason") == "timeout":
                await self._circuit_breaker.record_failure()
                await self._error_rate_tracker.record_call(success=False)
            else:
                await self._circuit_breaker.record_success()
                await self._error_rate_tracker.record_call(success=True)
            
            logger.info(f"Successfully generated response with Gemini: call_id={call_id}")
            return response

        except CircuitBreakerOpenError as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.warning(f"Circuit breaker blocked request: call_id={call_id}")
            await self._error_rate_tracker.record_call(success=False)
            return self._create_error_response(e, call_id, processing_time_ms)
            
        except Exception as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Gemini provider failed: call_id={call_id}, error={e}")
            
            # Record failure for circuit breaker and error rate
            await self._circuit_breaker.record_failure()
            await self._error_rate_tracker.record_call(success=False)
            
            # Return user-friendly error response instead of raising
            return self._create_error_response(e, call_id, processing_time_ms)

    @property
    def streaming_enabled(self) -> bool:
        """Check if streaming is currently enabled based on error rate."""
        return self._error_rate_tracker.streaming_enabled

    async def generate_response_stream(
        self,
        messages: List[Dict[str, str]],
        context: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024
    ) -> AsyncGenerator[AIResponse, None]:
        """
        Generate streaming AI response using Gemini.
        
        Yields AIResponse objects with partial content as chunks arrive.
        Automatically falls back to non-streaming if error rate is too high.
        """
        if not self.provider:
            yield AIResponse(
                content=USER_FRIENDLY_ERROR_MESSAGES[GeminiErrorType.AUTHENTICATION],
                provider="gemini",
                model="unknown",
                tokens_used=0,
                processing_time_ms=0,
                metadata={
                    "is_final": True,
                    "error_type": GeminiErrorType.AUTHENTICATION.value,
                    "error": "Gemini provider not configured"
                }
            )
            return

        call_id = str(uuid.uuid4())[:8]
        
        # Check if streaming is disabled due to high error rate
        if not self._error_rate_tracker.streaming_enabled:
            logger.info(
                f"Streaming disabled due to high error rate, using non-streaming: "
                f"call_id={call_id}"
            )
            # Fall back to non-streaming response
            response = await self.generate_response(
                messages=messages,
                context=context,
                temperature=temperature,
                max_tokens=max_tokens
            )
            yield AIResponse(
                content=response.content,
                provider=response.provider,
                model=response.model,
                tokens_used=response.tokens_used,
                processing_time_ms=response.processing_time_ms,
                metadata={
                    "is_final": True,
                    "chunk_index": 0,
                    "streaming_fallback": True,
                    "error": response.metadata.get("error") if response.metadata else None
                }
            )
            return
        
        # Check circuit breaker
        if not await self._circuit_breaker.allow_request():
            logger.warning(f"Circuit breaker open, blocking streaming request: call_id={call_id}")
            await self._error_rate_tracker.record_call(success=False)
            yield AIResponse(
                content="Service is temporarily unavailable. Please try again in a moment.",
                provider="gemini",
                model=self.provider.model,
                tokens_used=0,
                processing_time_ms=0,
                metadata={
                    "is_final": True,
                    "error_type": "circuit_breaker",
                    "circuit_breaker_stats": self._circuit_breaker.get_stats()
                }
            )
            return

        try:
            logger.info(f"Starting streaming response with Gemini: call_id={call_id}")
            had_error = False
            
            async for chunk in self.provider.generate_response_stream(
                messages=messages,
                context=context,
                temperature=temperature,
                max_tokens=max_tokens
            ):
                # Check for errors in chunk
                if chunk.error:
                    had_error = True
                    # Convert error to user-friendly message
                    error_type = classify_error(Exception(chunk.error))
                    user_message = USER_FRIENDLY_ERROR_MESSAGES[error_type]
                    
                    yield AIResponse(
                        content=user_message,
                        provider="gemini",
                        model=self.provider.model,
                        tokens_used=chunk.cumulative_tokens,
                        processing_time_ms=0,
                        metadata={
                            "is_final": True,
                            "chunk_index": chunk.chunk_index,
                            "error": chunk.error,
                            "error_type": error_type.value,
                            "user_message": user_message
                        }
                    )
                else:
                    # Convert StreamingChunk to AIResponse
                    yield AIResponse(
                        content=chunk.content,
                        provider="gemini",
                        model=self.provider.model,
                        tokens_used=chunk.cumulative_tokens,
                        processing_time_ms=0,
                        metadata={
                            "is_final": chunk.is_final,
                            "chunk_index": chunk.chunk_index,
                            "error": None
                        }
                    )
            
            # Record success/failure for circuit breaker and error rate
            if had_error:
                await self._circuit_breaker.record_failure()
                await self._error_rate_tracker.record_call(success=False)
            else:
                await self._circuit_breaker.record_success()
                await self._error_rate_tracker.record_call(success=True)
            
            logger.info(f"Completed streaming response with Gemini: call_id={call_id}")
            
        except Exception as e:
            logger.error(f"Gemini streaming failed: call_id={call_id}, error={e}")
            
            # Record failure
            await self._circuit_breaker.record_failure()
            await self._error_rate_tracker.record_call(success=False)
            
            # Yield user-friendly error chunk
            error_type = classify_error(e)
            user_message = USER_FRIENDLY_ERROR_MESSAGES[error_type]
            
            yield AIResponse(
                content=user_message,
                provider="gemini",
                model=self.provider.model if self.provider else "unknown",
                tokens_used=0,
                processing_time_ms=0,
                metadata={
                    "is_final": True,
                    "error": str(e),
                    "error_type": error_type.value,
                    "user_message": user_message
                }
            )

    async def generate_embeddings(
        self,
        texts: List[str],
        preferred_provider: Optional[AIProvider] = None
    ) -> List[List[float]]:
        """Generate embeddings using Gemini."""
        if not self.provider:
            raise Exception("Gemini provider not configured. Set GEMINI_API_KEY.")

        try:
            logger.info("Generating embeddings with Gemini")
            embeddings = await self.provider.generate_embeddings(texts)
            logger.info("Successfully generated embeddings with Gemini")
            return embeddings

        except Exception as e:
            logger.error(f"Gemini embedding failed: {e}")
            raise Exception(f"Embedding generation failed: {e}")

    def get_available_providers(self) -> List[str]:
        """Get list of available providers."""
        if self.provider:
            return ["gemini"]
        return []

    def get_provider_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of the Gemini provider."""
        if not self.provider:
            return {}

        return {
            "gemini": {
                "available": True,
                "model": self.provider.model,
                "is_primary": True,
                "supports_embeddings": True,
                "circuit_breaker_state": self._circuit_breaker.state.value,
                "streaming_enabled": self._error_rate_tracker.streaming_enabled
            }
        }

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics from the Gemini provider.
        
        Returns aggregated metrics including:
        - total_calls: Total number of API calls
        - successful_calls: Number of successful calls
        - failed_calls: Number of failed calls
        - timeout_count: Number of timeouts
        - avg_duration_ms: Average call duration
        - p50_duration_ms: Median call duration
        - p95_duration_ms: 95th percentile duration
        - p99_duration_ms: 99th percentile duration
        - avg_prompt_tokens: Average prompt token count
        - avg_response_tokens: Average response token count
        - circuit_breaker: Circuit breaker statistics
        - error_rate: Error rate statistics
        """
        if not self.provider:
            return {"error": "No provider configured"}
        
        stats = self.provider.get_performance_stats()
        return {
            "provider": "gemini",
            "model": self.provider.model,
            "total_calls": stats.total_calls,
            "successful_calls": stats.successful_calls,
            "failed_calls": stats.failed_calls,
            "timeout_count": stats.timeout_count,
            "avg_duration_ms": round(stats.avg_duration_ms, 2),
            "p50_duration_ms": round(stats.p50_duration_ms, 2),
            "p95_duration_ms": round(stats.p95_duration_ms, 2),
            "p99_duration_ms": round(stats.p99_duration_ms, 2),
            "avg_prompt_tokens": round(stats.avg_prompt_tokens, 2),
            "avg_response_tokens": round(stats.avg_response_tokens, 2),
            "success_rate": round(stats.successful_calls / stats.total_calls * 100, 2) if stats.total_calls > 0 else 0.0,
            "circuit_breaker": self._circuit_breaker.get_stats(),
            "error_rate": self._error_rate_tracker.get_stats()
        }

    def get_circuit_breaker_stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        return self._circuit_breaker.get_stats()

    def get_error_rate_stats(self) -> Dict[str, Any]:
        """Get error rate statistics."""
        return self._error_rate_tracker.get_stats()

    async def reset_circuit_breaker(self) -> None:
        """Reset the circuit breaker to closed state."""
        await self._circuit_breaker.reset()


# DEPRECATED: Module-level singleton pattern removed in favor of FastAPI DI
# Use api/dependencies/services.py get_ai_service() instead
