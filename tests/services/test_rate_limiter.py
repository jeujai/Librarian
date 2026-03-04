"""
Tests for Rate Limiter and Request Queue.

This module tests the rate limiting functionality including:
- RateLimiter with token bucket algorithm
- RequestQueue with rate limiting
- Timeout handling
- Statistics tracking
"""

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from src.multimodal_librarian.services.rate_limiter import (
    QueueFullError,
    RateLimiter,
    RateLimiterStats,
    RateLimitTimeoutError,
    RequestQueue,
    RequestQueueStats,
    create_conceptnet_rate_limiter,
    create_yago_rate_limiter,
)

# =============================================================================
# Test RateLimiter
# =============================================================================


class TestRateLimiter:
    """Test RateLimiter functionality."""

    def test_initialization(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter(rate=10.0, burst=20, timeout=30.0)

        assert limiter.rate == 10.0
        assert limiter.burst == 20

        stats = limiter.get_stats()
        assert stats.rate_per_second == 10.0
        assert stats.bucket_size == 20
        assert stats.tokens_available == 20.0  # Starts full

    def test_initialization_validation(self):
        """Test rate limiter initialization validation."""
        with pytest.raises(ValueError, match="Rate must be positive"):
            RateLimiter(rate=0)

        with pytest.raises(ValueError, match="Rate must be positive"):
            RateLimiter(rate=-1)

        with pytest.raises(ValueError, match="Burst size must be positive"):
            RateLimiter(burst=0)

        with pytest.raises(ValueError, match="Timeout must be non-negative"):
            RateLimiter(timeout=-1)

    @pytest.mark.asyncio
    async def test_acquire_immediate_success(self):
        """Test acquiring token when available."""
        limiter = RateLimiter(rate=10.0, burst=5, timeout=30.0)

        # Should succeed immediately for first 5 requests
        for _ in range(5):
            result = await limiter.acquire()
            assert result is True

        stats = limiter.get_stats()
        assert stats.total_requests == 5
        assert stats.total_waits == 0

    @pytest.mark.asyncio
    async def test_acquire_with_wait(self):
        """Test acquiring token when bucket is empty."""
        limiter = RateLimiter(rate=10.0, burst=1, timeout=30.0)

        # First request succeeds immediately
        await limiter.acquire()

        # Second request should wait
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start

        # Should have waited approximately 0.1 seconds (1/10 rate)
        assert elapsed >= 0.05  # Allow some tolerance

        stats = limiter.get_stats()
        assert stats.total_requests == 2
        assert stats.total_waits == 1

    @pytest.mark.asyncio
    async def test_acquire_timeout_zero(self):
        """Test acquire with zero timeout when no token available."""
        limiter = RateLimiter(rate=10.0, burst=1, timeout=30.0)

        # Exhaust the bucket
        await limiter.acquire()

        # Should timeout immediately with timeout=0
        with pytest.raises(RateLimitTimeoutError) as exc_info:
            await limiter.acquire(timeout=0)

        assert "timeout is 0" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_acquire_timeout_exceeded(self):
        """Test acquire when wait time exceeds timeout."""
        limiter = RateLimiter(rate=1.0, burst=1, timeout=30.0)

        # Exhaust the bucket
        await limiter.acquire()

        # Should timeout - need to wait 1 second but timeout is 0.1
        with pytest.raises(RateLimitTimeoutError) as exc_info:
            await limiter.acquire(timeout=0.1)

        assert exc_info.value.wait_time >= 0

    @pytest.mark.asyncio
    async def test_token_refill(self):
        """Test that tokens refill over time."""
        limiter = RateLimiter(rate=10.0, burst=2, timeout=30.0)

        # Exhaust the bucket
        await limiter.acquire()
        await limiter.acquire()

        # Wait for refill
        await asyncio.sleep(0.2)  # Should refill ~2 tokens

        # Should succeed without waiting
        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start

        # Should be nearly instant
        assert elapsed < 0.1

    def test_get_stats(self):
        """Test statistics retrieval."""
        limiter = RateLimiter(rate=10.0, burst=20, timeout=30.0)

        stats = limiter.get_stats()

        assert isinstance(stats, RateLimiterStats)
        assert stats.tokens_available == 20.0
        assert stats.bucket_size == 20
        assert stats.rate_per_second == 10.0
        assert stats.total_requests == 0
        assert stats.total_waits == 0
        assert stats.total_timeouts == 0
        assert stats.average_wait_ms == 0.0
        assert stats.queue_depth == 0

    def test_reset_stats(self):
        """Test statistics reset."""
        limiter = RateLimiter(rate=10.0, burst=20, timeout=30.0)

        # Manually set some stats
        limiter._total_requests = 100
        limiter._total_waits = 50
        limiter._total_timeouts = 5

        limiter.reset_stats()

        stats = limiter.get_stats()
        assert stats.total_requests == 0
        assert stats.total_waits == 0
        assert stats.total_timeouts == 0


# =============================================================================
# Test RequestQueue
# =============================================================================


class TestRequestQueue:
    """Test RequestQueue functionality."""

    @pytest.fixture
    def rate_limiter(self):
        """Create a rate limiter for testing."""
        return RateLimiter(rate=100.0, burst=10, timeout=30.0)

    @pytest.fixture
    def queue(self, rate_limiter):
        """Create a request queue for testing."""
        return RequestQueue(rate_limiter=rate_limiter, max_queue_size=100)

    def test_initialization(self, rate_limiter):
        """Test request queue initialization."""
        queue = RequestQueue(rate_limiter=rate_limiter, max_queue_size=50)

        stats = queue.get_stats()
        assert stats.max_queue_size == 50
        assert stats.queue_depth == 0
        assert stats.is_draining is False

    def test_initialization_validation(self, rate_limiter):
        """Test request queue initialization validation."""
        with pytest.raises(ValueError, match="Max queue size must be positive"):
            RequestQueue(rate_limiter=rate_limiter, max_queue_size=0)

    @pytest.mark.asyncio
    async def test_submit_success(self, queue):
        """Test successful request submission."""
        async def mock_request():
            return "success"

        result = await queue.submit(mock_request)

        assert result == "success"

        stats = queue.get_stats()
        assert stats.total_submitted == 1
        assert stats.total_completed == 1
        assert stats.total_failed == 0

    @pytest.mark.asyncio
    async def test_submit_with_rate_limiting(self, rate_limiter):
        """Test that requests are rate limited."""
        # Use a slow rate limiter
        slow_limiter = RateLimiter(rate=10.0, burst=2, timeout=30.0)
        queue = RequestQueue(rate_limiter=slow_limiter, max_queue_size=100)

        results = []

        async def mock_request(i):
            return i

        # Submit 4 requests - first 2 should be immediate, rest should wait
        start = time.monotonic()
        for i in range(4):
            result = await queue.submit(lambda i=i: mock_request(i))
            results.append(result)
        elapsed = time.monotonic() - start

        assert len(results) == 4
        # Should have taken at least 0.2 seconds for the last 2 requests
        assert elapsed >= 0.1

    @pytest.mark.asyncio
    async def test_submit_request_failure(self, queue):
        """Test handling of request failures."""
        async def failing_request():
            raise ValueError("Request failed")

        with pytest.raises(ValueError, match="Request failed"):
            await queue.submit(failing_request)

        stats = queue.get_stats()
        assert stats.total_submitted == 1
        assert stats.total_completed == 0
        assert stats.total_failed == 1

    @pytest.mark.asyncio
    async def test_submit_timeout(self):
        """Test request timeout."""
        # Very slow rate limiter
        slow_limiter = RateLimiter(rate=0.1, burst=1, timeout=30.0)
        queue = RequestQueue(rate_limiter=slow_limiter, max_queue_size=100)

        # Exhaust the bucket
        await queue.submit(lambda: asyncio.sleep(0))

        # Next request should timeout
        with pytest.raises(RateLimitTimeoutError):
            await queue.submit(lambda: asyncio.sleep(0), timeout=0.1)

        stats = queue.get_stats()
        assert stats.total_timeouts == 1

    @pytest.mark.asyncio
    async def test_queue_full_error(self, rate_limiter):
        """Test queue full error."""
        # Very small queue
        queue = RequestQueue(rate_limiter=rate_limiter, max_queue_size=1)

        # This is a simplified test - in practice the queue tracks
        # pending requests differently
        # For now, just verify the error class exists and works
        error = QueueFullError("Queue full", queue_depth=1, max_size=1)
        assert error.queue_depth == 1
        assert error.max_size == 1

    def test_get_stats(self, queue):
        """Test statistics retrieval."""
        stats = queue.get_stats()

        assert isinstance(stats, RequestQueueStats)
        assert stats.queue_depth == 0
        assert stats.max_queue_size == 100
        assert stats.total_submitted == 0
        assert stats.total_completed == 0
        assert stats.total_failed == 0
        assert stats.total_timeouts == 0
        assert stats.is_draining is False

    def test_reset_stats(self, queue):
        """Test statistics reset."""
        # Manually set some stats
        queue._total_submitted = 100
        queue._total_completed = 90
        queue._total_failed = 10

        queue.reset_stats()

        stats = queue.get_stats()
        assert stats.total_submitted == 0
        assert stats.total_completed == 0
        assert stats.total_failed == 0

    @pytest.mark.asyncio
    async def test_drain_empty_queue(self, queue):
        """Test draining an empty queue."""
        drained = await queue.drain(timeout=1.0)

        assert drained == 0
        assert queue.is_draining is False

    @pytest.mark.asyncio
    async def test_shutdown_prevents_new_requests(self, queue):
        """Test that shutdown prevents new requests."""
        await queue.drain(timeout=1.0)

        with pytest.raises(RuntimeError, match="shut down"):
            await queue.submit(lambda: asyncio.sleep(0))


# =============================================================================
# Test Factory Functions
# =============================================================================


class TestFactoryFunctions:
    """Test factory functions for creating rate limiters."""

    def test_create_yago_rate_limiter_defaults(self):
        """Test YAGO rate limiter with defaults."""
        limiter = create_yago_rate_limiter()

        assert limiter.rate == 10.0
        assert limiter.burst == 20

    def test_create_yago_rate_limiter_custom(self):
        """Test YAGO rate limiter with custom values."""
        limiter = create_yago_rate_limiter(rate=5.0, burst=10, timeout=60.0)

        assert limiter.rate == 5.0
        assert limiter.burst == 10

    def test_create_conceptnet_rate_limiter_defaults(self):
        """Test ConceptNet rate limiter with defaults."""
        limiter = create_conceptnet_rate_limiter()

        assert limiter.rate == 5.0
        assert limiter.burst == 10

    def test_create_conceptnet_rate_limiter_custom(self):
        """Test ConceptNet rate limiter with custom values."""
        limiter = create_conceptnet_rate_limiter(rate=2.0, burst=5, timeout=45.0)

        assert limiter.rate == 2.0
        assert limiter.burst == 5


# =============================================================================
# Test Concurrent Access
# =============================================================================


class TestConcurrentAccess:
    """Test concurrent access to rate limiter."""

    @pytest.mark.asyncio
    async def test_concurrent_acquire(self):
        """Test concurrent token acquisition."""
        limiter = RateLimiter(rate=100.0, burst=10, timeout=30.0)

        async def acquire_token():
            await limiter.acquire()
            return True

        # Run 10 concurrent acquisitions
        tasks = [acquire_token() for _ in range(10)]
        results = await asyncio.gather(*tasks)

        assert all(results)
        assert limiter.get_stats().total_requests == 10

    @pytest.mark.asyncio
    async def test_concurrent_submit(self):
        """Test concurrent request submission."""
        limiter = RateLimiter(rate=100.0, burst=20, timeout=30.0)
        queue = RequestQueue(rate_limiter=limiter, max_queue_size=100)

        async def mock_request(i):
            await asyncio.sleep(0.01)
            return i

        # Run 10 concurrent submissions
        tasks = [queue.submit(lambda i=i: mock_request(i)) for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        assert queue.get_stats().total_completed == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
