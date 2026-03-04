"""
Tests for Circuit Breaker Pattern Implementation.

This module tests the circuit breaker functionality including:
- Failure threshold detection
- Automatic service isolation
- Recovery testing
- State transitions
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from src.multimodal_librarian.monitoring.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerManager,
    CircuitBreakerConfig,
    CircuitState,
    CircuitBreakerError,
    circuit_breaker,
    get_circuit_breaker_manager
)


class TestCircuitBreaker:
    """Test circuit breaker functionality."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return CircuitBreakerConfig(
            failure_threshold=3,
            failure_rate_threshold=0.5,
            minimum_requests=5,
            timeout_seconds=2,
            success_threshold=2,
            health_check_interval=1
        )
    
    @pytest.fixture
    def circuit_breaker(self, config):
        """Create test circuit breaker."""
        return CircuitBreaker("test_service", config)
    
    @pytest.fixture
    def mock_function(self):
        """Create mock function for testing."""
        return Mock(return_value="success")
    
    @pytest.fixture
    def mock_async_function(self):
        """Create mock async function for testing."""
        return AsyncMock(return_value="success")
    
    @pytest.fixture
    def failing_function(self):
        """Create function that always fails."""
        def fail():
            raise Exception("Service failure")
        return fail
    
    @pytest.fixture
    def failing_async_function(self):
        """Create async function that always fails."""
        async def fail():
            raise Exception("Async service failure")
        return fail
    
    def test_circuit_breaker_initialization(self, config):
        """Test circuit breaker initialization."""
        cb = CircuitBreaker("test", config)
        
        assert cb.name == "test"
        assert cb.state == CircuitState.CLOSED
        assert cb.config == config
        assert cb.metrics.total_requests == 0
    
    @pytest.mark.asyncio
    async def test_successful_call(self, circuit_breaker, mock_async_function):
        """Test successful function call."""
        result = await circuit_breaker.call(mock_async_function)
        
        assert result == "success"
        assert circuit_breaker.metrics.successful_requests == 1
        assert circuit_breaker.metrics.consecutive_successes == 1
        assert circuit_breaker.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_sync_function_call(self, circuit_breaker, mock_function):
        """Test calling synchronous function."""
        result = await circuit_breaker.call(mock_function)
        
        assert result == "success"
        assert circuit_breaker.metrics.successful_requests == 1
        assert circuit_breaker.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_failed_call(self, circuit_breaker, failing_async_function):
        """Test failed function call."""
        with pytest.raises(Exception, match="Async service failure"):
            await circuit_breaker.call(failing_async_function)
        
        assert circuit_breaker.metrics.failed_requests == 1
        assert circuit_breaker.metrics.consecutive_failures == 1
        assert circuit_breaker.state == CircuitState.CLOSED  # Not enough failures yet
    
    @pytest.mark.asyncio
    async def test_circuit_opens_on_consecutive_failures(self, circuit_breaker, failing_async_function):
        """Test circuit opens after consecutive failures."""
        # Trigger failures to reach threshold
        for i in range(circuit_breaker.config.failure_threshold):
            with pytest.raises(Exception):
                await circuit_breaker.call(failing_async_function)
        
        assert circuit_breaker.state == CircuitState.OPEN
        assert circuit_breaker.metrics.consecutive_failures == circuit_breaker.config.failure_threshold
    
    @pytest.mark.asyncio
    async def test_circuit_blocks_calls_when_open(self, circuit_breaker, failing_async_function, mock_async_function):
        """Test circuit blocks calls when open."""
        # Open the circuit
        for i in range(circuit_breaker.config.failure_threshold):
            with pytest.raises(Exception):
                await circuit_breaker.call(failing_async_function)
        
        assert circuit_breaker.state == CircuitState.OPEN
        
        # Now calls should be blocked
        with pytest.raises(CircuitBreakerError, match="Circuit breaker .* is OPEN"):
            await circuit_breaker.call(mock_async_function)
    
    @pytest.mark.asyncio
    async def test_circuit_transitions_to_half_open(self, circuit_breaker, failing_async_function, mock_async_function):
        """Test circuit transitions to half-open after timeout."""
        # Open the circuit
        for i in range(circuit_breaker.config.failure_threshold):
            with pytest.raises(Exception):
                await circuit_breaker.call(failing_async_function)
        
        assert circuit_breaker.state == CircuitState.OPEN
        
        # Wait for timeout
        await asyncio.sleep(circuit_breaker.config.timeout_seconds + 0.1)
        
        # Next call should transition to half-open
        result = await circuit_breaker.call(mock_async_function)
        assert result == "success"
        assert circuit_breaker.state == CircuitState.HALF_OPEN
    
    @pytest.mark.asyncio
    async def test_circuit_closes_from_half_open(self, circuit_breaker, failing_async_function, mock_async_function):
        """Test circuit closes from half-open after successful calls."""
        # Open the circuit
        for i in range(circuit_breaker.config.failure_threshold):
            with pytest.raises(Exception):
                await circuit_breaker.call(failing_async_function)
        
        # Wait for timeout and transition to half-open
        await asyncio.sleep(circuit_breaker.config.timeout_seconds + 0.1)
        await circuit_breaker.call(mock_async_function)
        assert circuit_breaker.state == CircuitState.HALF_OPEN
        
        # Make enough successful calls to close circuit
        for i in range(circuit_breaker.config.success_threshold - 1):
            await circuit_breaker.call(mock_async_function)
        
        assert circuit_breaker.state == CircuitState.CLOSED
    
    @pytest.mark.asyncio
    async def test_circuit_opens_on_failure_rate(self, circuit_breaker, failing_async_function, mock_async_function):
        """Test circuit opens based on failure rate."""
        # Make minimum requests with high failure rate
        for i in range(circuit_breaker.config.minimum_requests):
            try:
                if i < int(circuit_breaker.config.minimum_requests * circuit_breaker.config.failure_rate_threshold) + 1:
                    # Make failures
                    await circuit_breaker.call(failing_async_function)
                else:
                    # Make successes
                    await circuit_breaker.call(mock_async_function)
            except Exception:
                pass  # Expected failures
        
        # Circuit should be open due to failure rate
        assert circuit_breaker.state == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_manual_reset(self, circuit_breaker, failing_async_function):
        """Test manual circuit reset."""
        # Open the circuit
        for i in range(circuit_breaker.config.failure_threshold):
            with pytest.raises(Exception):
                await circuit_breaker.call(failing_async_function)
        
        assert circuit_breaker.state == CircuitState.OPEN
        
        # Reset manually
        circuit_breaker.reset()
        assert circuit_breaker.state == CircuitState.CLOSED
        assert circuit_breaker.metrics.consecutive_failures == 0
    
    def test_force_open(self, circuit_breaker):
        """Test forcing circuit open."""
        assert circuit_breaker.state == CircuitState.CLOSED
        
        circuit_breaker.force_open()
        assert circuit_breaker.state == CircuitState.OPEN
    
    @pytest.mark.asyncio
    async def test_recovery_function(self, config):
        """Test circuit breaker with recovery function."""
        recovery_mock = AsyncMock(return_value=True)
        cb = CircuitBreaker("test_recovery", config, recovery_function=recovery_mock)
        
        # Open the circuit
        failing_func = AsyncMock(side_effect=Exception("Failure"))
        for i in range(config.failure_threshold):
            with pytest.raises(Exception):
                await cb.call(failing_func)
        
        assert cb.state == CircuitState.OPEN
        
        # Wait longer for recovery testing to kick in
        await asyncio.sleep(config.health_check_interval + 1.0)
        
        # Recovery function should have been called
        recovery_mock.assert_called()
    
    def test_get_status(self, circuit_breaker, mock_function):
        """Test getting circuit breaker status."""
        status = circuit_breaker.get_status()
        
        assert status['name'] == 'test_service'
        assert status['state'] == CircuitState.CLOSED.value
        assert 'metrics' in status
        assert 'config' in status
        assert 'thresholds' in status
    
    def test_metrics_calculation(self, circuit_breaker, mock_function, failing_function):
        """Test metrics calculation."""
        # Make some successful calls
        for i in range(3):
            asyncio.run(circuit_breaker.call(mock_function))
        
        # Make some failed calls
        for i in range(2):
            with pytest.raises(Exception):
                asyncio.run(circuit_breaker.call(failing_function))
        
        metrics = circuit_breaker.get_metrics()
        assert metrics.total_requests == 5
        assert metrics.successful_requests == 3
        assert metrics.failed_requests == 2
        assert metrics.failure_rate == 0.4
        assert metrics.success_rate == 0.6


class TestCircuitBreakerManager:
    """Test circuit breaker manager functionality."""
    
    @pytest.fixture
    def manager(self):
        """Create test circuit breaker manager."""
        return CircuitBreakerManager()
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return CircuitBreakerConfig(failure_threshold=2)
    
    def test_create_circuit_breaker(self, manager, config):
        """Test creating circuit breaker."""
        cb = manager.create_circuit_breaker("test", config)
        
        assert cb.name == "test"
        assert cb.config == config
        assert manager.get_circuit_breaker("test") == cb
    
    def test_duplicate_circuit_breaker_error(self, manager, config):
        """Test error when creating duplicate circuit breaker."""
        manager.create_circuit_breaker("test", config)
        
        with pytest.raises(ValueError, match="Circuit breaker 'test' already exists"):
            manager.create_circuit_breaker("test", config)
    
    def test_get_nonexistent_circuit_breaker(self, manager):
        """Test getting non-existent circuit breaker."""
        assert manager.get_circuit_breaker("nonexistent") is None
    
    @pytest.mark.asyncio
    async def test_remove_circuit_breaker(self, manager, config):
        """Test removing circuit breaker."""
        manager.create_circuit_breaker("test", config)
        assert manager.get_circuit_breaker("test") is not None
        
        removed = manager.remove_circuit_breaker("test")
        assert removed is True
        assert manager.get_circuit_breaker("test") is None
    
    def test_remove_nonexistent_circuit_breaker(self, manager):
        """Test removing non-existent circuit breaker."""
        removed = manager.remove_circuit_breaker("nonexistent")
        assert removed is False
    
    def test_get_all_status(self, manager, config):
        """Test getting status of all circuit breakers."""
        manager.create_circuit_breaker("test1", config)
        manager.create_circuit_breaker("test2", config)
        
        status = manager.get_all_status()
        assert len(status) == 2
        assert "test1" in status
        assert "test2" in status
    
    def test_get_summary(self, manager, config):
        """Test getting summary statistics."""
        # Create some circuit breakers
        cb1 = manager.create_circuit_breaker("test1", config)
        cb2 = manager.create_circuit_breaker("test2", config)
        
        # Force one open
        cb1.force_open()
        
        summary = manager.get_summary()
        assert summary['total_circuit_breakers'] == 2
        assert summary['closed_breakers'] == 1
        assert summary['open_breakers'] == 1
        assert summary['half_open_breakers'] == 0
        assert summary['health_percentage'] == 50.0
    
    @pytest.mark.asyncio
    async def test_shutdown_all(self, manager, config):
        """Test shutting down all circuit breakers."""
        manager.create_circuit_breaker("test1", config)
        manager.create_circuit_breaker("test2", config)
        
        await manager.shutdown_all()
        
        status = manager.get_all_status()
        assert len(status) == 0


class TestCircuitBreakerDecorator:
    """Test circuit breaker decorator functionality."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return CircuitBreakerConfig(failure_threshold=2, timeout_seconds=1)
    
    def test_sync_function_decorator(self, config):
        """Test decorator on synchronous function."""
        call_count = 0
        
        @circuit_breaker("sync_test", config)
        def test_function():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("Failure")
            return "success"
        
        # First two calls should fail and open circuit
        with pytest.raises(Exception):
            test_function()
        with pytest.raises(Exception):
            test_function()
        
        # Third call should be blocked by circuit breaker
        with pytest.raises(CircuitBreakerError):
            test_function()
    
    @pytest.mark.asyncio
    async def test_async_function_decorator(self, config):
        """Test decorator on asynchronous function."""
        call_count = 0
        
        @circuit_breaker("async_test", config)
        async def test_function():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise Exception("Async failure")
            return "success"
        
        # First two calls should fail and open circuit
        with pytest.raises(Exception):
            await test_function()
        with pytest.raises(Exception):
            await test_function()
        
        # Third call should be blocked by circuit breaker
        with pytest.raises(CircuitBreakerError):
            await test_function()
    
    def test_global_manager_access(self):
        """Test accessing global circuit breaker manager."""
        manager = get_circuit_breaker_manager()
        assert isinstance(manager, CircuitBreakerManager)
        
        # Should return same instance
        manager2 = get_circuit_breaker_manager()
        assert manager is manager2


class TestCircuitBreakerIntegration:
    """Integration tests for circuit breaker pattern."""
    
    @pytest.mark.asyncio
    async def test_service_isolation_and_recovery(self):
        """Test complete service isolation and recovery cycle."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            timeout_seconds=1,
            success_threshold=2,
            health_check_interval=0.5
        )
        
        # Mock service that can be controlled
        service_healthy = False
        call_count = 0
        
        async def mock_service():
            nonlocal call_count
            call_count += 1
            if not service_healthy:
                raise Exception("Service unavailable")
            return f"success_{call_count}"
        
        async def recovery_test():
            return service_healthy
        
        cb = CircuitBreaker("integration_test", config, recovery_test)
        
        # Phase 1: Service fails and circuit opens
        for i in range(config.failure_threshold):
            with pytest.raises(Exception):
                await cb.call(mock_service)
        
        assert cb.state == CircuitState.OPEN
        
        # Phase 2: Calls are blocked
        with pytest.raises(CircuitBreakerError):
            await cb.call(mock_service)
        
        # Phase 3: Service recovers
        service_healthy = True
        
        # Wait for recovery testing
        await asyncio.sleep(config.health_check_interval + 0.5)
        
        # Phase 4: Circuit should transition to half-open and then closed
        result1 = await cb.call(mock_service)
        assert cb.state == CircuitState.HALF_OPEN
        
        result2 = await cb.call(mock_service)
        assert cb.state == CircuitState.CLOSED
        
        # Phase 5: Normal operation resumes
        result3 = await cb.call(mock_service)
        assert result3.startswith("success_")
        assert cb.state == CircuitState.CLOSED
        
        await cb.shutdown()
    
    @pytest.mark.asyncio
    async def test_multiple_circuit_breakers(self):
        """Test multiple circuit breakers working independently."""
        manager = CircuitBreakerManager()
        
        config = CircuitBreakerConfig(failure_threshold=2)
        
        cb1 = manager.create_circuit_breaker("service1", config)
        cb2 = manager.create_circuit_breaker("service2", config)
        
        async def failing_service():
            raise Exception("Service failure")
        
        async def working_service():
            return "success"
        
        # Fail service1 circuit breaker
        for i in range(config.failure_threshold):
            with pytest.raises(Exception):
                await cb1.call(failing_service)
        
        assert cb1.state == CircuitState.OPEN
        assert cb2.state == CircuitState.CLOSED
        
        # Service2 should still work
        result = await cb2.call(working_service)
        assert result == "success"
        assert cb2.state == CircuitState.CLOSED
        
        # Service1 should be blocked
        with pytest.raises(CircuitBreakerError):
            await cb1.call(working_service)
        
        await manager.shutdown_all()
    
    @pytest.mark.asyncio
    async def test_failure_rate_threshold(self):
        """Test circuit opening based on failure rate."""
        config = CircuitBreakerConfig(
            failure_threshold=10,  # High threshold
            failure_rate_threshold=0.6,  # 60% failure rate
            minimum_requests=10
        )
        
        cb = CircuitBreaker("rate_test", config)
        
        # Make 10 requests with 70% failure rate (7 failures, 3 successes)
        for i in range(10):
            try:
                if i < 7:  # First 7 are failures
                    await cb.call(lambda: (_ for _ in ()).throw(Exception("Failure")))
                else:  # Last 3 are successes
                    await cb.call(lambda: "success")
            except Exception:
                pass  # Expected failures
        
        # Circuit should be open due to failure rate (70% > 60%)
        assert cb.state == CircuitState.OPEN
        
        await cb.shutdown()


if __name__ == "__main__":
    pytest.main([__file__])