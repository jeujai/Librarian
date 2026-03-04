"""
Rate Limiter and Request Queue for API Throttling.

This module implements a token bucket rate limiter and async request queue
for controlling the rate of outgoing API requests to external services
like YAGO and ConceptNet.

The token bucket algorithm allows for burst traffic while maintaining
an average rate limit over time.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Generic, List, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RateLimitTimeoutError(Exception):
    """Raised when a rate limit acquisition times out."""
    
    def __init__(self, message: str, wait_time: float):
        """
        Initialize the timeout error.
        
        Args:
            message: Error description
            wait_time: How long the request waited before timing out
        """
        super().__init__(message)
        self.wait_time = wait_time


class QueueFullError(Exception):
    """Raised when the request queue is at capacity."""
    
    def __init__(self, message: str, queue_depth: int, max_size: int):
        """
        Initialize the queue full error.
        
        Args:
            message: Error description
            queue_depth: Current queue depth
            max_size: Maximum queue size
        """
        super().__init__(message)
        self.queue_depth = queue_depth
        self.max_size = max_size


@dataclass
class RateLimiterStats:
    """Statistics for rate limiter monitoring."""
    
    tokens_available: float
    bucket_size: int
    rate_per_second: float
    total_requests: int
    total_waits: int
    total_timeouts: int
    average_wait_ms: float
    queue_depth: int


class RateLimiter:
    """
    Token bucket rate limiter for API request throttling.
    
    The token bucket algorithm works as follows:
    - The bucket has a maximum capacity (burst size)
    - Tokens are added at a constant rate (rate per second)
    - Each request consumes one token
    - If no tokens are available, requests wait until a token is available
    
    This allows for short bursts of traffic while maintaining an average
    rate limit over time.
    """
    
    def __init__(
        self,
        rate: float = 10.0,
        burst: int = 20,
        timeout: float = 30.0
    ):
        """
        Initialize the rate limiter.
        
        Args:
            rate: Maximum sustained request rate (requests/second)
            burst: Maximum tokens in bucket (allows short bursts)
            timeout: Default maximum time to wait for a token (seconds)
        """
        if rate <= 0:
            raise ValueError("Rate must be positive")
        if burst <= 0:
            raise ValueError("Burst size must be positive")
        if timeout < 0:
            raise ValueError("Timeout must be non-negative")
        
        self._rate = rate
        self._burst = burst
        self._default_timeout = timeout
        
        # Token bucket state
        self._tokens = float(burst)  # Start with full bucket
        self._last_refill = time.monotonic()
        
        # Statistics
        self._total_requests = 0
        self._total_waits = 0
        self._total_timeouts = 0
        self._total_wait_time_ms = 0.0
        
        # Synchronization
        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition(self._lock)
        
        # Queue depth tracking (for external queue integration)
        self._queue_depth = 0
        
        logger.info(
            f"RateLimiter initialized: rate={rate}/s, burst={burst}, timeout={timeout}s"
        )
    
    @property
    def rate(self) -> float:
        """Get the rate limit (requests per second)."""
        return self._rate
    
    @property
    def burst(self) -> int:
        """Get the burst size (maximum tokens)."""
        return self._burst
    
    def _refill_tokens(self) -> None:
        """
        Refill tokens based on elapsed time.
        
        This should be called while holding the lock.
        """
        now = time.monotonic()
        elapsed = now - self._last_refill
        
        # Add tokens based on elapsed time
        tokens_to_add = elapsed * self._rate
        self._tokens = min(self._tokens + tokens_to_add, float(self._burst))
        self._last_refill = now
    
    async def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire a token, waiting if necessary.
        
        Args:
            timeout: Override default timeout (seconds). Use 0 for no wait.
            
        Returns:
            True if token acquired successfully
            
        Raises:
            RateLimitTimeoutError: If timeout exceeded while waiting for token
        """
        effective_timeout = timeout if timeout is not None else self._default_timeout
        start_time = time.monotonic()
        
        async with self._lock:
            self._total_requests += 1
            self._refill_tokens()
            
            # Fast path: token available immediately
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            
            # Need to wait for a token
            self._total_waits += 1
            
            # Calculate how long we need to wait for one token
            tokens_needed = 1.0 - self._tokens
            wait_time = tokens_needed / self._rate
            
            # Check if we can wait that long
            if effective_timeout == 0:
                # No wait requested
                elapsed = time.monotonic() - start_time
                self._total_timeouts += 1
                raise RateLimitTimeoutError(
                    "No token available and timeout is 0",
                    wait_time=elapsed
                )
            
            if wait_time > effective_timeout:
                # Would exceed timeout
                elapsed = time.monotonic() - start_time
                self._total_timeouts += 1
                raise RateLimitTimeoutError(
                    f"Token wait time ({wait_time:.2f}s) exceeds timeout ({effective_timeout:.2f}s)",
                    wait_time=elapsed
                )
            
            # Wait for the token
            try:
                await asyncio.wait_for(
                    self._wait_for_token(),
                    timeout=effective_timeout
                )
            except asyncio.TimeoutError:
                elapsed = time.monotonic() - start_time
                self._total_timeouts += 1
                self._total_wait_time_ms += elapsed * 1000
                raise RateLimitTimeoutError(
                    f"Timeout waiting for rate limit token after {elapsed:.2f}s",
                    wait_time=elapsed
                )
            
            # Record wait time
            elapsed = time.monotonic() - start_time
            self._total_wait_time_ms += elapsed * 1000
            
            return True
    
    async def _wait_for_token(self) -> None:
        """
        Wait until a token is available.
        
        This should be called while holding the lock.
        """
        while self._tokens < 1.0:
            # Calculate time until next token
            tokens_needed = 1.0 - self._tokens
            wait_time = tokens_needed / self._rate
            
            # Release lock and wait
            await asyncio.sleep(wait_time)
            
            # Refill tokens after waiting
            self._refill_tokens()
    
    def get_stats(self) -> RateLimiterStats:
        """
        Get current rate limiter statistics.
        
        Returns:
            RateLimiterStats with current state and metrics
        """
        # Calculate average wait time
        avg_wait_ms = 0.0
        if self._total_waits > 0:
            avg_wait_ms = self._total_wait_time_ms / self._total_waits
        
        return RateLimiterStats(
            tokens_available=self._tokens,
            bucket_size=self._burst,
            rate_per_second=self._rate,
            total_requests=self._total_requests,
            total_waits=self._total_waits,
            total_timeouts=self._total_timeouts,
            average_wait_ms=avg_wait_ms,
            queue_depth=self._queue_depth
        )
    
    def _increment_queue_depth(self) -> None:
        """Increment queue depth counter."""
        self._queue_depth += 1
    
    def _decrement_queue_depth(self) -> None:
        """Decrement queue depth counter."""
        self._queue_depth = max(0, self._queue_depth - 1)
    
    def reset_stats(self) -> None:
        """Reset statistics counters."""
        self._total_requests = 0
        self._total_waits = 0
        self._total_timeouts = 0
        self._total_wait_time_ms = 0.0
        logger.debug("RateLimiter statistics reset")


@dataclass
class RequestQueueStats:
    """Statistics for request queue monitoring."""
    
    queue_depth: int
    max_queue_size: int
    total_submitted: int
    total_completed: int
    total_failed: int
    total_timeouts: int
    average_wait_time_ms: float
    is_draining: bool


@dataclass
class PendingRequest(Generic[T]):
    """A pending request in the queue."""
    
    request_fn: Callable[[], Awaitable[T]]
    future: asyncio.Future
    submitted_at: float
    timeout: Optional[float] = None


class RequestQueue:
    """
    Async request queue with rate limiting.
    
    This queue buffers outgoing requests and releases them at a controlled
    rate using the token bucket rate limiter. It provides:
    
    - Request buffering to smooth out bursts
    - Timeout support for individual requests
    - Graceful shutdown with drain capability
    - Queue depth and wait time metrics
    """
    
    def __init__(
        self,
        rate_limiter: RateLimiter,
        max_queue_size: int = 1000
    ):
        """
        Initialize the request queue.
        
        Args:
            rate_limiter: Rate limiter instance for throttling
            max_queue_size: Maximum number of pending requests
        """
        if max_queue_size <= 0:
            raise ValueError("Max queue size must be positive")
        
        self._rate_limiter = rate_limiter
        self._max_queue_size = max_queue_size
        
        # Queue state
        self._queue: List[PendingRequest] = []
        self._is_draining = False
        self._is_shutdown = False
        
        # Statistics
        self._total_submitted = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_timeouts = 0
        self._total_wait_time_ms = 0.0
        
        # Synchronization
        self._lock = asyncio.Lock()
        
        logger.info(
            f"RequestQueue initialized: max_size={max_queue_size}"
        )
    
    @property
    def queue_depth(self) -> int:
        """Get current queue depth."""
        return len(self._queue)
    
    @property
    def is_draining(self) -> bool:
        """Check if queue is in draining mode."""
        return self._is_draining
    
    async def submit(
        self,
        request_fn: Callable[[], Awaitable[T]],
        timeout: Optional[float] = None
    ) -> T:
        """
        Submit a request to the queue.
        
        The request will be executed after acquiring a rate limit token.
        
        Args:
            request_fn: Async function to execute
            timeout: Maximum wait time (seconds). If None, uses rate limiter default.
            
        Returns:
            Result of request_fn
            
        Raises:
            QueueFullError: If queue is at capacity
            RateLimitTimeoutError: If timeout exceeded while waiting
        """
        if self._is_shutdown:
            raise RuntimeError("RequestQueue has been shut down")
        
        async with self._lock:
            # Check queue capacity
            if len(self._queue) >= self._max_queue_size:
                raise QueueFullError(
                    f"Request queue is full ({len(self._queue)}/{self._max_queue_size})",
                    queue_depth=len(self._queue),
                    max_size=self._max_queue_size
                )
            
            self._total_submitted += 1
            self._rate_limiter._increment_queue_depth()
        
        start_time = time.monotonic()
        
        try:
            # Acquire rate limit token
            await self._rate_limiter.acquire(timeout=timeout)
            
            # Execute the request
            result = await request_fn()
            
            # Record success
            async with self._lock:
                self._total_completed += 1
                elapsed = time.monotonic() - start_time
                self._total_wait_time_ms += elapsed * 1000
            
            return result
            
        except RateLimitTimeoutError:
            async with self._lock:
                self._total_timeouts += 1
            raise
            
        except Exception:
            async with self._lock:
                self._total_failed += 1
            raise
            
        finally:
            self._rate_limiter._decrement_queue_depth()
    
    async def drain(self, timeout: float = 30.0) -> int:
        """
        Drain pending requests during shutdown.
        
        This method waits for pending requests to complete or cancels them
        after the timeout expires.
        
        Args:
            timeout: Maximum time to wait for drain (seconds)
            
        Returns:
            Number of requests that were drained (completed or cancelled)
        """
        async with self._lock:
            self._is_draining = True
            pending_count = len(self._queue)
        
        if pending_count == 0:
            logger.info("RequestQueue drain: no pending requests")
            async with self._lock:
                self._is_draining = False
                self._is_shutdown = True
            return 0
        
        logger.info(f"RequestQueue drain: waiting for {pending_count} pending requests")
        
        start_time = time.monotonic()
        drained = 0
        
        # Wait for pending requests to complete
        while True:
            async with self._lock:
                current_pending = len(self._queue)
                if current_pending == 0:
                    break
            
            elapsed = time.monotonic() - start_time
            if elapsed >= timeout:
                # Timeout reached, cancel remaining requests
                async with self._lock:
                    remaining = len(self._queue)
                    for pending in self._queue:
                        if not pending.future.done():
                            pending.future.cancel()
                    self._queue.clear()
                    drained += remaining
                
                logger.warning(
                    f"RequestQueue drain timeout: cancelled {remaining} remaining requests"
                )
                break
            
            # Wait a bit before checking again
            await asyncio.sleep(0.1)
        
        async with self._lock:
            self._is_draining = False
            self._is_shutdown = True
        
        logger.info(f"RequestQueue drain complete: {drained} requests drained")
        return drained
    
    def get_stats(self) -> RequestQueueStats:
        """
        Get current queue statistics.
        
        Returns:
            RequestQueueStats with current state and metrics
        """
        avg_wait_ms = 0.0
        if self._total_completed > 0:
            avg_wait_ms = self._total_wait_time_ms / self._total_completed
        
        return RequestQueueStats(
            queue_depth=len(self._queue),
            max_queue_size=self._max_queue_size,
            total_submitted=self._total_submitted,
            total_completed=self._total_completed,
            total_failed=self._total_failed,
            total_timeouts=self._total_timeouts,
            average_wait_time_ms=avg_wait_ms,
            is_draining=self._is_draining
        )
    
    def reset_stats(self) -> None:
        """Reset statistics counters."""
        self._total_submitted = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_timeouts = 0
        self._total_wait_time_ms = 0.0
        logger.debug("RequestQueue statistics reset")


# Factory functions for creating rate limiters with common configurations

def create_yago_rate_limiter(
    rate: float = 10.0,
    burst: int = 20,
    timeout: float = 30.0
) -> RateLimiter:
    """
    Create a rate limiter configured for YAGO local queries.
    
    Args:
        rate: Requests per second (default: 10)
        burst: Maximum burst size (default: 20)
        timeout: Default timeout in seconds (default: 30)
        
    Returns:
        Configured RateLimiter instance
    """
    return RateLimiter(rate=rate, burst=burst, timeout=timeout)


def create_conceptnet_rate_limiter(
    rate: float = 5.0,
    burst: int = 10,
    timeout: float = 30.0
) -> RateLimiter:
    """
    Create a rate limiter configured for ConceptNet API.
    
    Args:
        rate: Requests per second (default: 5)
        burst: Maximum burst size (default: 10)
        timeout: Default timeout in seconds (default: 30)
        
    Returns:
        Configured RateLimiter instance
    """
    return RateLimiter(rate=rate, burst=burst, timeout=timeout)
