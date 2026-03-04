#!/usr/bin/env python3
"""
Test Health Check Response Time Under Load

This test module validates that health check endpoints respond within 100ms
even under concurrent load conditions. This is critical for ensuring ALB/ECS
health checks don't timeout during high-traffic periods or model loading.

Key Test Scenarios:
1. Health check response time under concurrent requests
2. Health check response time during simulated CPU load
3. Health check response time with background model loading
4. Statistical validation of 100ms threshold compliance

Requirements Validated:
- REQ-1: Health Check Optimization
- Task 9.5: Verify health checks respond within 100ms under load

Success Criteria:
- 95% of health checks respond within 100ms under load
- Maximum response time does not exceed 200ms
- Average response time stays below 50ms
"""

import asyncio
import sys
import time
import statistics
import multiprocessing
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple
from unittest.mock import Mock, patch, AsyncMock
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pytest


class TestHealthCheck100msUnderLoad:
    """Test that health checks respond within 100ms under various load conditions."""
    
    RESPONSE_TIME_THRESHOLD_MS = 100  # Target: 100ms
    MAX_ACCEPTABLE_MS = 200  # Absolute maximum
    TARGET_PERCENTILE_95 = 100  # 95th percentile should be under 100ms
    
    @pytest.fixture
    def mock_minimal_server(self):
        """Create a mock minimal server for testing."""
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
    
    @pytest.fixture
    def mock_phase_manager(self):
        """Create a mock phase manager for testing."""
        from multimodal_librarian.startup.phase_manager import StartupPhase
        
        mock = Mock()
        mock.current_phase = StartupPhase.ESSENTIAL
        
        mock_status = Mock()
        mock_status.current_phase = StartupPhase.ESSENTIAL
        mock_status.model_statuses = {
            "text-embedding": Mock(status="loading", priority="essential"),
            "chat-model": Mock(status="loading", priority="essential"),
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
    async def test_concurrent_health_checks_respond_within_100ms(self, mock_minimal_server):
        """
        Test that concurrent health check requests all respond within 100ms.
        
        Validates: Task 9.5 - Verify health checks respond within 100ms under load
        """
        from multimodal_librarian.api.routers.health import simple_health_check
        
        num_concurrent_requests = 50
        response_times: List[float] = []
        
        async def make_health_check() -> float:
            """Make a single health check and return response time in ms."""
            start_time = time.time()
            with patch('multimodal_librarian.api.routers.health.get_minimal_server', 
                       return_value=mock_minimal_server):
                response = await simple_health_check()
            elapsed_ms = (time.time() - start_time) * 1000
            assert response.status_code == 200, f"Health check failed with status {response.status_code}"
            return elapsed_ms
        
        # Run concurrent health checks
        tasks = [make_health_check() for _ in range(num_concurrent_requests)]
        response_times = await asyncio.gather(*tasks)
        
        # Calculate statistics
        avg_time = statistics.mean(response_times)
        max_time = max(response_times)
        min_time = min(response_times)
        p95_time = sorted(response_times)[int(len(response_times) * 0.95)]
        
        # Validate results
        within_threshold = sum(1 for t in response_times if t <= self.RESPONSE_TIME_THRESHOLD_MS)
        within_threshold_pct = (within_threshold / len(response_times)) * 100
        
        print(f"\n📊 Concurrent Health Check Results ({num_concurrent_requests} requests):")
        print(f"   Average: {avg_time:.2f}ms")
        print(f"   Min: {min_time:.2f}ms")
        print(f"   Max: {max_time:.2f}ms")
        print(f"   95th percentile: {p95_time:.2f}ms")
        print(f"   Within 100ms: {within_threshold_pct:.1f}%")
        
        # Assertions
        assert within_threshold_pct >= 95, \
            f"Only {within_threshold_pct:.1f}% of health checks responded within 100ms (target: 95%)"
        assert p95_time <= self.TARGET_PERCENTILE_95, \
            f"95th percentile ({p95_time:.2f}ms) exceeds 100ms threshold"
        assert max_time <= self.MAX_ACCEPTABLE_MS, \
            f"Maximum response time ({max_time:.2f}ms) exceeds 200ms limit"
        
        print("✅ All concurrent health checks responded within 100ms threshold")

    
    @pytest.mark.asyncio
    async def test_health_checks_under_cpu_load_respond_within_100ms(self, mock_minimal_server):
        """
        Test that health checks respond within 100ms even during CPU-intensive operations.
        
        This simulates the scenario where model loading is consuming CPU resources
        but health checks should still respond quickly due to ProcessPoolExecutor isolation.
        
        Validates: Task 9.5 - Verify health checks respond within 100ms under load
        """
        from multimodal_librarian.api.routers.health import simple_health_check
        
        response_times: List[float] = []
        cpu_load_running = True
        
        def cpu_intensive_work():
            """Simulate CPU-intensive model loading work."""
            result = 0
            for i in range(1000000):
                result += i * i
            return result
        
        async def generate_cpu_load():
            """Generate continuous CPU load in background."""
            loop = asyncio.get_event_loop()
            ctx = multiprocessing.get_context('spawn')
            
            with ProcessPoolExecutor(max_workers=2, mp_context=ctx) as executor:
                while cpu_load_running:
                    # Submit CPU work to separate processes
                    await loop.run_in_executor(executor, cpu_intensive_work)
                    await asyncio.sleep(0.01)  # Small yield
        
        async def make_health_checks():
            """Make health checks while CPU load is running."""
            nonlocal cpu_load_running
            
            for _ in range(30):
                start_time = time.time()
                with patch('multimodal_librarian.api.routers.health.get_minimal_server',
                           return_value=mock_minimal_server):
                    response = await simple_health_check()
                elapsed_ms = (time.time() - start_time) * 1000
                response_times.append(elapsed_ms)
                assert response.status_code == 200
                await asyncio.sleep(0.05)  # 50ms between checks
            
            cpu_load_running = False
        
        # Run CPU load and health checks concurrently
        await asyncio.gather(
            generate_cpu_load(),
            make_health_checks(),
            return_exceptions=True
        )
        
        # Calculate statistics
        avg_time = statistics.mean(response_times)
        max_time = max(response_times)
        p95_time = sorted(response_times)[int(len(response_times) * 0.95)]
        
        print(f"\n📊 Health Checks Under CPU Load Results:")
        print(f"   Average: {avg_time:.2f}ms")
        print(f"   Max: {max_time:.2f}ms")
        print(f"   95th percentile: {p95_time:.2f}ms")
        
        # Assertions - health checks should still be fast despite CPU load
        assert p95_time <= self.RESPONSE_TIME_THRESHOLD_MS, \
            f"95th percentile ({p95_time:.2f}ms) exceeds 100ms under CPU load"
        assert max_time <= self.MAX_ACCEPTABLE_MS, \
            f"Max response time ({max_time:.2f}ms) exceeds 200ms under CPU load"
        
        print("✅ Health checks respond within 100ms even under CPU load")

    
    @pytest.mark.asyncio
    async def test_health_checks_during_simulated_model_loading(
        self, mock_minimal_server, mock_phase_manager, metrics_collector
    ):
        """
        Test health check response times during simulated model loading phases.
        
        This test simulates the startup scenario where models are being loaded
        in the background and validates that health checks remain responsive.
        
        Validates: Task 9.5 - Verify health checks respond within 100ms under load
        """
        from multimodal_librarian.api.routers.health import simple_health_check
        
        response_times: List[float] = []
        model_loading_active = True
        
        async def simulate_model_loading():
            """Simulate model loading with periodic yields."""
            nonlocal model_loading_active
            
            while model_loading_active:
                # Simulate some model loading work
                _ = sum(range(50000))
                # Yield to allow health checks
                await asyncio.sleep(0)
        
        async def make_health_checks_during_loading():
            """Make health checks while model loading is simulated."""
            nonlocal model_loading_active
            
            for i in range(40):
                start_time = time.time()
                with patch('multimodal_librarian.api.routers.health.get_minimal_server',
                           return_value=mock_minimal_server):
                    response = await simple_health_check()
                elapsed_ms = (time.time() - start_time) * 1000
                response_times.append(elapsed_ms)
                
                # Record in metrics collector
                await metrics_collector.record_health_check_latency(
                    response_time_ms=elapsed_ms,
                    success=response.status_code == 200,
                    endpoint="/health/simple"
                )
                
                await asyncio.sleep(0.025)  # 25ms between checks
            
            model_loading_active = False
        
        # Run model loading simulation and health checks concurrently
        await asyncio.gather(
            simulate_model_loading(),
            make_health_checks_during_loading(),
            return_exceptions=True
        )
        
        # Calculate statistics
        avg_time = statistics.mean(response_times)
        max_time = max(response_times)
        min_time = min(response_times)
        p95_time = sorted(response_times)[int(len(response_times) * 0.95)]
        std_dev = statistics.stdev(response_times) if len(response_times) > 1 else 0
        
        # Get metrics summary
        summary = metrics_collector.get_health_check_latency_summary()
        
        print(f"\n📊 Health Checks During Model Loading Results:")
        print(f"   Total checks: {len(response_times)}")
        print(f"   Average: {avg_time:.2f}ms")
        print(f"   Min: {min_time:.2f}ms")
        print(f"   Max: {max_time:.2f}ms")
        print(f"   Std Dev: {std_dev:.2f}ms")
        print(f"   95th percentile: {p95_time:.2f}ms")
        print(f"   Success rate: {summary['success_rate'] * 100:.1f}%")
        
        # Assertions
        assert p95_time <= self.RESPONSE_TIME_THRESHOLD_MS, \
            f"95th percentile ({p95_time:.2f}ms) exceeds 100ms during model loading"
        assert summary['success_rate'] == 1.0, \
            f"Some health checks failed during model loading"
        
        print("✅ Health checks respond within 100ms during model loading")

    
    @pytest.mark.asyncio
    async def test_sustained_load_health_check_response_times(self, mock_minimal_server):
        """
        Test health check response times under sustained load over time.
        
        This test runs health checks continuously for a period to ensure
        response times remain stable and within threshold.
        
        Validates: Task 9.5 - Verify health checks respond within 100ms under load
        """
        from multimodal_librarian.api.routers.health import simple_health_check
        
        response_times: List[float] = []
        test_duration_seconds = 2.0  # Run for 2 seconds
        start_test_time = time.time()
        
        while (time.time() - start_test_time) < test_duration_seconds:
            start_time = time.time()
            with patch('multimodal_librarian.api.routers.health.get_minimal_server',
                       return_value=mock_minimal_server):
                response = await simple_health_check()
            elapsed_ms = (time.time() - start_time) * 1000
            response_times.append(elapsed_ms)
            assert response.status_code == 200
            await asyncio.sleep(0.01)  # 10ms between checks
        
        # Calculate statistics
        avg_time = statistics.mean(response_times)
        max_time = max(response_times)
        p95_time = sorted(response_times)[int(len(response_times) * 0.95)]
        p99_time = sorted(response_times)[int(len(response_times) * 0.99)]
        
        # Check for degradation over time
        first_half = response_times[:len(response_times)//2]
        second_half = response_times[len(response_times)//2:]
        first_half_avg = statistics.mean(first_half)
        second_half_avg = statistics.mean(second_half)
        degradation_pct = ((second_half_avg - first_half_avg) / first_half_avg) * 100 if first_half_avg > 0 else 0
        
        print(f"\n📊 Sustained Load Health Check Results:")
        print(f"   Total checks: {len(response_times)}")
        print(f"   Duration: {test_duration_seconds}s")
        print(f"   Average: {avg_time:.2f}ms")
        print(f"   Max: {max_time:.2f}ms")
        print(f"   95th percentile: {p95_time:.2f}ms")
        print(f"   99th percentile: {p99_time:.2f}ms")
        print(f"   First half avg: {first_half_avg:.2f}ms")
        print(f"   Second half avg: {second_half_avg:.2f}ms")
        print(f"   Degradation: {degradation_pct:.1f}%")
        
        # Assertions - primary requirement is 100ms threshold
        assert p95_time <= self.RESPONSE_TIME_THRESHOLD_MS, \
            f"95th percentile ({p95_time:.2f}ms) exceeds 100ms under sustained load"
        
        # Secondary check: degradation should be reasonable
        # Note: Some variance is expected due to system scheduling
        # We only flag severe degradation (>100%) as a warning, not a failure
        if degradation_pct > 100:
            print(f"⚠️ Warning: Response time degraded by {degradation_pct:.1f}% over time")
        
        # The key assertion is that all response times stay under threshold
        all_within_threshold = all(t <= self.RESPONSE_TIME_THRESHOLD_MS for t in response_times)
        assert all_within_threshold, \
            f"Some health checks exceeded 100ms threshold (max: {max_time:.2f}ms)"
        
        print("✅ Health checks maintain <100ms response under sustained load")

    
    @pytest.mark.asyncio
    async def test_burst_load_health_check_response_times(self, mock_minimal_server):
        """
        Test health check response times under burst load conditions.
        
        This simulates sudden spikes in health check requests that might occur
        during scaling events or load balancer health check storms.
        
        Validates: Task 9.5 - Verify health checks respond within 100ms under load
        """
        from multimodal_librarian.api.routers.health import simple_health_check
        
        all_response_times: List[float] = []
        burst_results: List[Dict[str, Any]] = []
        
        async def make_burst_requests(burst_size: int) -> List[float]:
            """Make a burst of concurrent health check requests."""
            async def single_check() -> float:
                start_time = time.time()
                with patch('multimodal_librarian.api.routers.health.get_minimal_server',
                           return_value=mock_minimal_server):
                    response = await simple_health_check()
                elapsed_ms = (time.time() - start_time) * 1000
                assert response.status_code == 200
                return elapsed_ms
            
            tasks = [single_check() for _ in range(burst_size)]
            return await asyncio.gather(*tasks)
        
        # Simulate multiple bursts
        burst_sizes = [10, 25, 50, 100]
        
        for burst_size in burst_sizes:
            burst_times = await make_burst_requests(burst_size)
            all_response_times.extend(burst_times)
            
            burst_avg = statistics.mean(burst_times)
            burst_max = max(burst_times)
            burst_p95 = sorted(burst_times)[int(len(burst_times) * 0.95)]
            
            burst_results.append({
                "size": burst_size,
                "avg": burst_avg,
                "max": burst_max,
                "p95": burst_p95
            })
            
            # Small delay between bursts
            await asyncio.sleep(0.1)
        
        # Overall statistics
        overall_avg = statistics.mean(all_response_times)
        overall_max = max(all_response_times)
        overall_p95 = sorted(all_response_times)[int(len(all_response_times) * 0.95)]
        
        print(f"\n📊 Burst Load Health Check Results:")
        for result in burst_results:
            print(f"   Burst size {result['size']:3d}: avg={result['avg']:.2f}ms, "
                  f"max={result['max']:.2f}ms, p95={result['p95']:.2f}ms")
        print(f"   Overall: avg={overall_avg:.2f}ms, max={overall_max:.2f}ms, p95={overall_p95:.2f}ms")
        
        # Assertions
        assert overall_p95 <= self.RESPONSE_TIME_THRESHOLD_MS, \
            f"Overall 95th percentile ({overall_p95:.2f}ms) exceeds 100ms under burst load"
        
        # Verify each burst met the threshold
        for result in burst_results:
            assert result['p95'] <= self.RESPONSE_TIME_THRESHOLD_MS, \
                f"Burst size {result['size']} p95 ({result['p95']:.2f}ms) exceeds 100ms"
        
        print("✅ Health checks respond within 100ms under burst load conditions")

    
    @pytest.mark.asyncio
    async def test_health_check_latency_metrics_under_load(
        self, mock_minimal_server, mock_phase_manager, metrics_collector
    ):
        """
        Test that health check latency metrics are properly recorded under load.
        
        This validates that the metrics collection system accurately tracks
        response times and identifies slow checks during load conditions.
        
        Validates: Task 9.5 - Verify health checks respond within 100ms under load
        """
        from multimodal_librarian.api.routers.health import simple_health_check
        
        num_checks = 50
        
        for i in range(num_checks):
            start_time = time.time()
            with patch('multimodal_librarian.api.routers.health.get_minimal_server',
                       return_value=mock_minimal_server):
                response = await simple_health_check()
            elapsed_ms = (time.time() - start_time) * 1000
            
            # Record the latency
            await metrics_collector.record_health_check_latency(
                response_time_ms=elapsed_ms,
                success=response.status_code == 200,
                endpoint="/health/simple"
            )
        
        # Get metrics summary
        summary = metrics_collector.get_health_check_latency_summary()
        metrics = metrics_collector.get_health_check_latency_metrics()
        
        print(f"\n📊 Health Check Latency Metrics Under Load:")
        print(f"   Total checks: {summary['total_health_checks']}")
        print(f"   Successful: {summary['successful_checks']}")
        print(f"   Success rate: {summary['success_rate'] * 100:.1f}%")
        print(f"   Average latency: {summary['average_latency_ms']:.2f}ms")
        print(f"   Slow checks (>100ms): {summary['slow_checks']}")
        
        # Assertions
        assert summary['total_health_checks'] == num_checks, \
            f"Expected {num_checks} checks, got {summary['total_health_checks']}"
        assert summary['success_rate'] == 1.0, \
            f"Some health checks failed: {summary['success_rate'] * 100:.1f}%"
        assert summary['slow_checks'] == 0, \
            f"Found {summary['slow_checks']} slow health checks (>100ms)"
        assert summary['average_latency_ms'] < self.RESPONSE_TIME_THRESHOLD_MS, \
            f"Average latency ({summary['average_latency_ms']:.2f}ms) exceeds 100ms"
        
        print("✅ Health check latency metrics properly recorded under load")


class TestHealthCheck100msWithBackgroundTasks:
    """Test health checks with various background tasks running."""
    
    RESPONSE_TIME_THRESHOLD_MS = 100
    
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
    async def test_health_checks_with_io_bound_background_tasks(self, mock_minimal_server):
        """
        Test health checks respond within 100ms with I/O-bound background tasks.
        
        Validates: Task 9.5 - Verify health checks respond within 100ms under load
        """
        from multimodal_librarian.api.routers.health import simple_health_check
        
        response_times: List[float] = []
        background_running = True
        
        async def io_bound_background_task():
            """Simulate I/O-bound background work."""
            while background_running:
                await asyncio.sleep(0.01)  # Simulate I/O wait
        
        async def make_health_checks():
            """Make health checks while background tasks run."""
            nonlocal background_running
            
            for _ in range(30):
                start_time = time.time()
                with patch('multimodal_librarian.api.routers.health.get_minimal_server',
                           return_value=mock_minimal_server):
                    response = await simple_health_check()
                elapsed_ms = (time.time() - start_time) * 1000
                response_times.append(elapsed_ms)
                assert response.status_code == 200
                await asyncio.sleep(0.02)
            
            background_running = False
        
        # Run multiple I/O-bound tasks and health checks concurrently
        await asyncio.gather(
            io_bound_background_task(),
            io_bound_background_task(),
            io_bound_background_task(),
            make_health_checks(),
            return_exceptions=True
        )
        
        avg_time = statistics.mean(response_times)
        max_time = max(response_times)
        p95_time = sorted(response_times)[int(len(response_times) * 0.95)]
        
        print(f"\n📊 Health Checks with I/O Background Tasks:")
        print(f"   Average: {avg_time:.2f}ms")
        print(f"   Max: {max_time:.2f}ms")
        print(f"   95th percentile: {p95_time:.2f}ms")
        
        assert p95_time <= self.RESPONSE_TIME_THRESHOLD_MS, \
            f"95th percentile ({p95_time:.2f}ms) exceeds 100ms with I/O background tasks"
        
        print("✅ Health checks respond within 100ms with I/O background tasks")
    
    @pytest.mark.asyncio
    async def test_health_checks_with_mixed_workload(self, mock_minimal_server):
        """
        Test health checks respond within 100ms with mixed CPU and I/O workload.
        
        Validates: Task 9.5 - Verify health checks respond within 100ms under load
        """
        from multimodal_librarian.api.routers.health import simple_health_check
        
        response_times: List[float] = []
        workload_running = True
        
        async def mixed_workload():
            """Simulate mixed CPU and I/O workload."""
            while workload_running:
                # Some CPU work
                _ = sum(range(10000))
                # Some I/O wait
                await asyncio.sleep(0.005)
        
        async def make_health_checks():
            """Make health checks during mixed workload."""
            nonlocal workload_running
            
            for _ in range(40):
                start_time = time.time()
                with patch('multimodal_librarian.api.routers.health.get_minimal_server',
                           return_value=mock_minimal_server):
                    response = await simple_health_check()
                elapsed_ms = (time.time() - start_time) * 1000
                response_times.append(elapsed_ms)
                assert response.status_code == 200
                await asyncio.sleep(0.015)
            
            workload_running = False
        
        # Run mixed workload and health checks
        await asyncio.gather(
            mixed_workload(),
            mixed_workload(),
            make_health_checks(),
            return_exceptions=True
        )
        
        avg_time = statistics.mean(response_times)
        max_time = max(response_times)
        p95_time = sorted(response_times)[int(len(response_times) * 0.95)]
        
        print(f"\n📊 Health Checks with Mixed Workload:")
        print(f"   Average: {avg_time:.2f}ms")
        print(f"   Max: {max_time:.2f}ms")
        print(f"   95th percentile: {p95_time:.2f}ms")
        
        assert p95_time <= self.RESPONSE_TIME_THRESHOLD_MS, \
            f"95th percentile ({p95_time:.2f}ms) exceeds 100ms with mixed workload"
        
        print("✅ Health checks respond within 100ms with mixed workload")



class TestHealthCheck100msStatisticalValidation:
    """Statistical validation of health check response times under load."""
    
    RESPONSE_TIME_THRESHOLD_MS = 100
    
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
    async def test_statistical_confidence_health_check_times(self, mock_minimal_server):
        """
        Test with statistical confidence that health checks respond within 100ms.
        
        Uses a larger sample size to ensure statistical significance.
        
        Validates: Task 9.5 - Verify health checks respond within 100ms under load
        """
        from multimodal_librarian.api.routers.health import simple_health_check
        
        sample_size = 100
        response_times: List[float] = []
        
        for _ in range(sample_size):
            start_time = time.time()
            with patch('multimodal_librarian.api.routers.health.get_minimal_server',
                       return_value=mock_minimal_server):
                response = await simple_health_check()
            elapsed_ms = (time.time() - start_time) * 1000
            response_times.append(elapsed_ms)
            assert response.status_code == 200
        
        # Calculate comprehensive statistics
        avg_time = statistics.mean(response_times)
        median_time = statistics.median(response_times)
        std_dev = statistics.stdev(response_times)
        min_time = min(response_times)
        max_time = max(response_times)
        
        # Percentiles
        sorted_times = sorted(response_times)
        p50 = sorted_times[int(sample_size * 0.50)]
        p90 = sorted_times[int(sample_size * 0.90)]
        p95 = sorted_times[int(sample_size * 0.95)]
        p99 = sorted_times[int(sample_size * 0.99)]
        
        # Count within threshold
        within_threshold = sum(1 for t in response_times if t <= self.RESPONSE_TIME_THRESHOLD_MS)
        within_threshold_pct = (within_threshold / sample_size) * 100
        
        print(f"\n📊 Statistical Health Check Analysis (n={sample_size}):")
        print(f"   Mean: {avg_time:.2f}ms")
        print(f"   Median: {median_time:.2f}ms")
        print(f"   Std Dev: {std_dev:.2f}ms")
        print(f"   Min: {min_time:.2f}ms")
        print(f"   Max: {max_time:.2f}ms")
        print(f"   P50: {p50:.2f}ms")
        print(f"   P90: {p90:.2f}ms")
        print(f"   P95: {p95:.2f}ms")
        print(f"   P99: {p99:.2f}ms")
        print(f"   Within 100ms: {within_threshold_pct:.1f}%")
        
        # Assertions with statistical confidence
        assert within_threshold_pct >= 95, \
            f"Only {within_threshold_pct:.1f}% within 100ms (need 95%)"
        assert p95 <= self.RESPONSE_TIME_THRESHOLD_MS, \
            f"P95 ({p95:.2f}ms) exceeds 100ms threshold"
        assert avg_time < 50, \
            f"Average ({avg_time:.2f}ms) should be well under 100ms"
        
        print("✅ Statistical validation confirms health checks respond within 100ms")


def run_tests():
    """Run all tests."""
    print("=" * 70)
    print("Testing Health Check Response Time Under Load (100ms Threshold)")
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
