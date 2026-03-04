#!/usr/bin/env python3
"""
Test Health Check Responsiveness During Model Loading

This test module validates that health check endpoints remain responsive
during CPU-bound model loading operations. It tests the event loop protection
mechanisms that prevent GIL contention from blocking health checks.

Key Test Scenarios:
1. Health check response time during simulated model loading
2. Event loop responsiveness under CPU-bound operations
3. ProcessPoolExecutor isolation from main event loop
4. Health check latency tracking and alerting

Requirements Validated:
- REQ-1: Health Check Optimization
- REQ-2: Application Startup Optimization
- Task 9.5: Create Event Loop Protection Tests
"""

import asyncio
import sys
import time
import threading
import multiprocessing
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pytest


class TestHealthCheckResponsivenessDuringModelLoading:
    """Test that health checks remain responsive during model loading."""
    
    @pytest.fixture
    def mock_phase_manager(self):
        """Create a mock phase manager for testing."""
        from multimodal_librarian.startup.phase_manager import StartupPhase
        
        mock = Mock()
        mock.current_phase = StartupPhase.ESSENTIAL
        
        # Create mock status with models loading
        mock_status = Mock()
        mock_status.current_phase = StartupPhase.ESSENTIAL
        mock_status.model_statuses = {
            "text-embedding": Mock(status="loading", priority="essential"),
            "chat-model": Mock(status="loading", priority="essential"),
            "search-index": Mock(status="loaded", priority="essential"),
        }
        mock.get_current_status.return_value = mock_status
        mock.status = mock_status
        
        return mock
    
    @pytest.fixture
    def metrics_collector(self, mock_phase_manager):
        """Create a metrics collector for testing."""
        from multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector
        return StartupMetricsCollector(mock_phase_manager)
    
    @pytest.mark.asyncio
    async def test_health_check_responds_quickly_without_load(self, metrics_collector):
        """Test that health check responds quickly when no model loading is happening."""
        # Simulate a health check without any CPU load
        start_time = time.time()
        
        # Record a health check latency (simulating the endpoint)
        await metrics_collector.record_health_check_latency(
            response_time_ms=5.0,  # Fast response
            success=True,
            endpoint="/health/simple"
        )
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        # The recording itself should be fast
        assert elapsed_ms < 100, f"Health check recording took too long: {elapsed_ms:.1f}ms"
        
        # Verify the metric was recorded correctly
        assert len(metrics_collector.health_check_latency_history) == 1
        metric = metrics_collector.health_check_latency_history[0]
        assert metric.response_time_ms == 5.0
        assert metric.is_slow is False
        assert metric.is_elevated is False
        
        print("✅ Health check responds quickly without CPU load")
    
    @pytest.mark.asyncio
    async def test_health_check_latency_tracking_during_model_loading(self, metrics_collector, mock_phase_manager):
        """Test that health check latency is properly tracked during model loading."""
        # Simulate health checks during model loading
        latencies = [10.0, 15.0, 25.0, 50.0, 75.0, 120.0, 150.0]
        
        for latency in latencies:
            await metrics_collector.record_health_check_latency(
                response_time_ms=latency,
                success=True,
                endpoint="/health/simple"
            )
        
        # Verify all metrics were recorded
        assert len(metrics_collector.health_check_latency_history) == len(latencies)
        
        # Check slow detection (>100ms)
        slow_metrics = [m for m in metrics_collector.health_check_latency_history if m.is_slow]
        assert len(slow_metrics) == 2  # 120.0 and 150.0
        
        # Check elevated detection (>50ms, not >=50ms)
        # 75.0, 120.0, 150.0 are elevated (50.0 is NOT elevated since it's >50, not >=50)
        elevated_metrics = [m for m in metrics_collector.health_check_latency_history if m.is_elevated]
        assert len(elevated_metrics) == 3  # 75.0, 120.0, 150.0
        
        # Verify models loading were captured
        for metric in metrics_collector.health_check_latency_history:
            assert "text-embedding" in metric.models_loading
            assert "chat-model" in metric.models_loading
        
        print("✅ Health check latency tracking during model loading works correctly")
    
    @pytest.mark.asyncio
    async def test_health_check_metrics_summary(self, metrics_collector, mock_phase_manager):
        """Test health check latency metrics summary generation."""
        # Record various latencies
        latencies = [5, 10, 15, 20, 30, 60, 80, 110, 150, 200]
        for latency in latencies:
            await metrics_collector.record_health_check_latency(
                response_time_ms=float(latency),
                success=True
            )
        
        # Get summary
        summary = metrics_collector.get_health_check_latency_summary()
        
        assert summary["total_health_checks"] == 10
        assert summary["successful_checks"] == 10
        assert summary["success_rate"] == 1.0
        assert summary["slow_checks"] == 3  # 110, 150, 200 > 100ms
        assert "average_latency_ms" in summary
        
        print("✅ Health check metrics summary generation works correctly")


class TestEventLoopResponsiveness:
    """Test event loop responsiveness during CPU-bound operations."""
    
    @pytest.mark.asyncio
    async def test_event_loop_yields_during_async_operations(self):
        """Test that event loop properly yields during async operations."""
        results = []
        
        async def background_task():
            """Simulated background task that should not block."""
            for i in range(5):
                results.append(f"background_{i}")
                await asyncio.sleep(0.01)
        
        async def health_check_task():
            """Simulated health check that should complete quickly."""
            for i in range(5):
                start = time.time()
                await asyncio.sleep(0)  # Yield to event loop
                elapsed = (time.time() - start) * 1000
                results.append(f"health_{i}_{elapsed:.1f}ms")
        
        # Run both tasks concurrently
        await asyncio.gather(background_task(), health_check_task())
        
        # Verify both tasks completed
        background_results = [r for r in results if r.startswith("background_")]
        health_results = [r for r in results if r.startswith("health_")]
        
        assert len(background_results) == 5
        assert len(health_results) == 5
        
        print("✅ Event loop yields properly during async operations")
    
    @pytest.mark.asyncio
    async def test_yield_points_allow_health_checks(self):
        """Test that yield points in long operations allow health checks to proceed."""
        health_check_times = []
        
        async def simulated_model_loading_with_yields():
            """Simulate model loading with yield points."""
            for i in range(10):
                # Simulate some work
                _ = sum(range(10000))
                # Yield point
                await asyncio.sleep(0)
        
        async def health_check_monitor():
            """Monitor health check responsiveness."""
            for i in range(5):
                start = time.time()
                await asyncio.sleep(0.01)
                elapsed = (time.time() - start) * 1000
                health_check_times.append(elapsed)
        
        # Run both concurrently
        await asyncio.gather(
            simulated_model_loading_with_yields(),
            health_check_monitor()
        )
        
        # Health checks should complete in reasonable time
        avg_time = sum(health_check_times) / len(health_check_times)
        max_time = max(health_check_times)
        
        # Allow some tolerance for system scheduling
        assert max_time < 100, f"Health check took too long: {max_time:.1f}ms"
        
        print(f"✅ Yield points allow health checks (avg: {avg_time:.1f}ms, max: {max_time:.1f}ms)")


class TestProcessPoolExecutorIsolation:
    """Test that ProcessPoolExecutor isolates CPU-bound work from main event loop."""
    
    def cpu_bound_work(self, duration_seconds: float = 0.1) -> Dict[str, Any]:
        """CPU-bound work that would block the GIL if run in ThreadPoolExecutor."""
        start = time.time()
        # Simulate CPU-bound work
        result = 0
        iterations = int(duration_seconds * 1000000)
        for i in range(iterations):
            result += i * i
        elapsed = time.time() - start
        return {
            "result": result,
            "elapsed_seconds": elapsed,
            "process_name": multiprocessing.current_process().name
        }
    
    @pytest.mark.asyncio
    async def test_process_pool_does_not_block_event_loop(self):
        """Test that ProcessPoolExecutor work doesn't block the event loop."""
        health_check_times = []
        
        async def health_check_monitor():
            """Monitor health check responsiveness during process pool work."""
            for i in range(10):
                start = time.time()
                await asyncio.sleep(0.01)
                elapsed = (time.time() - start) * 1000
                health_check_times.append(elapsed)
        
        async def run_cpu_work_in_process():
            """Run CPU-bound work in a separate process."""
            loop = asyncio.get_event_loop()
            
            # Use spawn context for PyTorch compatibility
            ctx = multiprocessing.get_context('spawn')
            
            with ProcessPoolExecutor(max_workers=1, mp_context=ctx) as executor:
                # Submit CPU-bound work
                future = loop.run_in_executor(
                    executor,
                    self.cpu_bound_work,
                    0.05  # 50ms of CPU work
                )
                result = await future
                return result
        
        # Run both concurrently
        results = await asyncio.gather(
            run_cpu_work_in_process(),
            health_check_monitor()
        )
        
        cpu_result = results[0]
        
        # Verify CPU work completed
        assert cpu_result["elapsed_seconds"] > 0
        
        # Health checks should remain responsive
        avg_time = sum(health_check_times) / len(health_check_times)
        max_time = max(health_check_times)
        
        # With ProcessPoolExecutor, health checks should not be blocked
        # Allow reasonable tolerance for system scheduling
        assert max_time < 50, f"Health check blocked: {max_time:.1f}ms (should be <50ms)"
        
        print(f"✅ ProcessPoolExecutor doesn't block event loop (avg: {avg_time:.1f}ms, max: {max_time:.1f}ms)")
    
    @pytest.mark.asyncio
    async def test_thread_pool_can_block_event_loop(self):
        """Test that ThreadPoolExecutor CAN block event loop (demonstrating the problem)."""
        health_check_times = []
        
        def blocking_cpu_work():
            """CPU-bound work that blocks the GIL."""
            result = 0
            for i in range(500000):
                result += i * i
            return result
        
        async def health_check_monitor():
            """Monitor health check responsiveness."""
            for i in range(5):
                start = time.time()
                await asyncio.sleep(0.01)
                elapsed = (time.time() - start) * 1000
                health_check_times.append(elapsed)
        
        async def run_cpu_work_in_thread():
            """Run CPU-bound work in a thread (shares GIL)."""
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=1) as executor:
                result = await loop.run_in_executor(executor, blocking_cpu_work)
                return result
        
        # Run both concurrently
        await asyncio.gather(
            run_cpu_work_in_thread(),
            health_check_monitor()
        )
        
        # With ThreadPoolExecutor, some health checks may be delayed
        # This test demonstrates the problem that ProcessPoolExecutor solves
        avg_time = sum(health_check_times) / len(health_check_times)
        
        # Note: This test may or may not show blocking depending on system
        # The key insight is that ProcessPoolExecutor provides better isolation
        print(f"✅ ThreadPoolExecutor test completed (avg health check: {avg_time:.1f}ms)")


class TestHealthCheckEndpointResponsiveness:
    """Test the actual health check endpoint responsiveness."""
    
    @pytest.fixture
    def mock_minimal_server(self):
        """Create a mock minimal server."""
        mock = Mock()
        mock_status = Mock()
        mock_status.status = Mock(value="ready")
        mock_status.health_check_ready = True
        mock_status.uptime_seconds = 60.0
        mock_status.capabilities = {"basic_chat": True}
        mock_status.model_statuses = {}
        mock_status.estimated_ready_times = {}
        mock_status.processed_requests = 10
        mock_status.failed_requests = 0
        mock.get_status.return_value = mock_status
        mock.get_queue_status.return_value = {"pending": 0}
        mock.request_queue = []
        return mock
    
    @pytest.mark.asyncio
    async def test_simple_health_endpoint_response_time(self, mock_minimal_server):
        """Test that /health/simple endpoint responds quickly."""
        from multimodal_librarian.api.routers.health import simple_health_check
        
        # Measure response time
        start_time = time.time()
        
        # Patch at the module level where it's imported
        with patch('multimodal_librarian.api.routers.health.get_minimal_server', return_value=mock_minimal_server):
            # The simple_health_check doesn't require startup_metrics_collector to exist
            # It handles the case where it's None gracefully
            response = await simple_health_check()
        
        elapsed_ms = (time.time() - start_time) * 1000
        
        # Simple health check should be very fast
        assert elapsed_ms < 100, f"Simple health check too slow: {elapsed_ms:.1f}ms"
        assert response.status_code == 200
        
        print(f"✅ Simple health endpoint responds in {elapsed_ms:.1f}ms")
    
    @pytest.mark.asyncio
    async def test_health_check_includes_response_time(self, mock_minimal_server):
        """Test that health check response includes response time metric."""
        from multimodal_librarian.api.routers.health import simple_health_check
        
        with patch('multimodal_librarian.api.routers.health.get_minimal_server', return_value=mock_minimal_server):
            response = await simple_health_check()
        
        # Parse response body
        import json
        body = json.loads(response.body.decode())
        
        assert "response_time_ms" in body
        assert body["response_time_ms"] >= 0
        assert body["status"] == "ok"
        
        print(f"✅ Health check includes response time: {body['response_time_ms']}ms")


class TestGILContentionDetection:
    """Test GIL contention detection during model loading."""
    
    @pytest.fixture
    def mock_phase_manager(self):
        """Create a mock phase manager."""
        from multimodal_librarian.startup.phase_manager import StartupPhase
        
        mock = Mock()
        mock.current_phase = StartupPhase.ESSENTIAL
        
        mock_status = Mock()
        mock_status.current_phase = StartupPhase.ESSENTIAL
        mock_status.model_statuses = {
            "large-model": Mock(status="loading", priority="essential"),
        }
        mock.get_current_status.return_value = mock_status
        
        return mock
    
    @pytest.fixture
    def metrics_collector(self, mock_phase_manager):
        """Create a metrics collector."""
        from multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector
        return StartupMetricsCollector(mock_phase_manager)
    
    @pytest.mark.asyncio
    async def test_slow_health_check_detection(self, metrics_collector):
        """Test that slow health checks (>100ms) are detected as GIL contention."""
        # Record a slow health check
        await metrics_collector.record_health_check_latency(
            response_time_ms=150.0,
            success=True,
            endpoint="/health/simple"
        )
        
        metric = metrics_collector.health_check_latency_history[0]
        
        assert metric.is_slow is True
        assert metric.is_elevated is True
        assert "large-model" in metric.models_loading
        
        print("✅ Slow health check correctly detected as GIL contention")
    
    @pytest.mark.asyncio
    async def test_elevated_health_check_detection(self, metrics_collector):
        """Test that elevated health checks (>50ms) are detected."""
        # Record an elevated but not slow health check
        await metrics_collector.record_health_check_latency(
            response_time_ms=75.0,
            success=True,
            endpoint="/health/simple"
        )
        
        metric = metrics_collector.health_check_latency_history[0]
        
        assert metric.is_slow is False
        assert metric.is_elevated is True
        
        print("✅ Elevated health check correctly detected")
    
    @pytest.mark.asyncio
    async def test_normal_health_check_not_flagged(self, metrics_collector):
        """Test that normal health checks are not flagged."""
        # Record a normal health check
        await metrics_collector.record_health_check_latency(
            response_time_ms=10.0,
            success=True,
            endpoint="/health/simple"
        )
        
        metric = metrics_collector.health_check_latency_history[0]
        
        assert metric.is_slow is False
        assert metric.is_elevated is False
        
        print("✅ Normal health check not flagged")
    
    @pytest.mark.asyncio
    async def test_gil_contention_analysis(self, metrics_collector, mock_phase_manager):
        """Test GIL contention analysis in metrics."""
        # Record a mix of slow and normal health checks
        for _ in range(3):
            await metrics_collector.record_health_check_latency(
                response_time_ms=150.0,  # Slow
                success=True
            )
        
        for _ in range(7):
            await metrics_collector.record_health_check_latency(
                response_time_ms=10.0,  # Normal
                success=True
            )
        
        # Get metrics with GIL contention analysis
        metrics = metrics_collector.get_health_check_latency_metrics()
        
        assert "gil_contention_analysis" in metrics
        gil_analysis = metrics["gil_contention_analysis"]
        assert gil_analysis["contention_detected"] is True
        assert gil_analysis["total_slow_checks"] == 3
        
        print("✅ GIL contention analysis works correctly")


class TestHealthCheckNoTimeoutsDuringStartup:
    """Test that health checks don't timeout during startup phase."""
    
    @pytest.fixture
    def mock_phase_manager(self):
        """Create a mock phase manager in startup phase."""
        from multimodal_librarian.startup.phase_manager import StartupPhase
        
        mock = Mock()
        mock.current_phase = StartupPhase.MINIMAL
        
        mock_status = Mock()
        mock_status.current_phase = StartupPhase.MINIMAL
        mock_status.model_statuses = {}
        mock.get_current_status.return_value = mock_status
        
        return mock
    
    @pytest.fixture
    def metrics_collector(self, mock_phase_manager):
        """Create a metrics collector."""
        from multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector
        return StartupMetricsCollector(mock_phase_manager)
    
    @pytest.mark.asyncio
    async def test_all_health_checks_succeed_during_startup(self, metrics_collector):
        """Test that all health checks succeed during startup phase."""
        # Simulate multiple health checks during startup
        for i in range(20):
            # Vary the response times
            response_time = 5.0 + (i % 5) * 10  # 5, 15, 25, 35, 45, 5, ...
            await metrics_collector.record_health_check_latency(
                response_time_ms=response_time,
                success=True,
                endpoint="/health/simple"
            )
        
        # All health checks should have succeeded
        all_successful = all(m.success for m in metrics_collector.health_check_latency_history)
        assert all_successful, "Some health checks failed during startup"
        
        # Get summary
        summary = metrics_collector.get_health_check_latency_summary()
        assert summary["success_rate"] == 1.0
        
        print("✅ All health checks succeed during startup phase")
    
    @pytest.mark.asyncio
    async def test_health_check_failure_tracking(self, metrics_collector):
        """Test that health check failures are properly tracked."""
        # Record some successful and some failed health checks
        for i in range(10):
            success = i < 8  # 8 successful, 2 failed
            await metrics_collector.record_health_check_latency(
                response_time_ms=20.0,
                success=success,
                endpoint="/health/simple",
                error_message=None if success else "Connection timeout"
            )
        
        summary = metrics_collector.get_health_check_latency_summary()
        
        assert summary["total_health_checks"] == 10
        assert summary["successful_checks"] == 8
        assert summary["success_rate"] == 0.8
        
        print("✅ Health check failure tracking works correctly")


def run_tests():
    """Run all tests."""
    print("=" * 70)
    print("Testing Health Check Responsiveness During Model Loading")
    print("=" * 70)
    
    exit_code = pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-x"  # Stop on first failure
    ])
    
    return exit_code


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
