#!/usr/bin/env python3
"""
Test ProcessPoolExecutor Isolation from Main Event Loop

This test module validates that ProcessPoolExecutor properly isolates CPU-bound
model loading operations from the main asyncio event loop, ensuring health checks
remain responsive during model initialization.

Key Test Scenarios:
1. ProcessPoolExecutor runs work in separate process with separate GIL
2. Main event loop remains responsive during ProcessPoolExecutor work
3. Health check endpoints respond quickly during CPU-bound subprocess work
4. Comparison with ThreadPoolExecutor to demonstrate GIL blocking problem
5. Integration with ModelManager's ProcessPoolExecutor configuration

Requirements Validated:
- REQ-1: Health Check Optimization
- REQ-2: Application Startup Optimization
- Task 9.3: Test ProcessPoolExecutor isolation from main event loop

Success Criteria:
- ProcessPoolExecutor work runs in separate process (different PID)
- Health checks respond within 100ms during ProcessPoolExecutor work
- Event loop yields properly during subprocess execution
- ModelManager correctly uses ProcessPoolExecutor for model loading
"""

import asyncio
import sys
import time
import os
import multiprocessing
import statistics
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Tuple
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pytest


# Module-level functions for ProcessPoolExecutor (required for spawn context pickling)
def _cpu_bound_work_module_level(duration_seconds: float = 0.1) -> Dict[str, Any]:
    """
    CPU-bound work that would block the GIL if run in ThreadPoolExecutor.
    
    This function is defined at module level (not as a method) so it can be
    pickled and sent to ProcessPoolExecutor workers.
    """
    start = time.time()
    result = 0
    iterations = int(duration_seconds * 1000000)
    for i in range(iterations):
        result += i * i
    elapsed = time.time() - start
    return {
        "result": result,
        "elapsed_seconds": elapsed,
        "process_id": os.getpid(),
        "process_name": multiprocessing.current_process().name
    }


def _get_process_info() -> Dict[str, Any]:
    """Get information about the current process."""
    return {
        "pid": os.getpid(),
        "process_name": multiprocessing.current_process().name,
        "is_main_process": multiprocessing.current_process().name == "MainProcess"
    }


def _simulate_model_loading(model_name: str, load_time_seconds: float) -> Dict[str, Any]:
    """
    Simulate model loading in a subprocess.
    
    This mimics the actual model loading behavior where CPU-intensive
    operations would block the GIL in a ThreadPoolExecutor.
    """
    start = time.time()
    
    # Simulate CPU-intensive model loading
    result = 0
    iterations = int(load_time_seconds * 500000)
    for i in range(iterations):
        result += i * i
    
    elapsed = time.time() - start
    return {
        "model_name": model_name,
        "load_time_seconds": elapsed,
        "process_id": os.getpid(),
        "process_name": multiprocessing.current_process().name,
        "loaded_at": datetime.now().isoformat()
    }


class TestProcessPoolExecutorIsolation:
    """Test that ProcessPoolExecutor properly isolates work from main event loop."""
    
    @pytest.mark.asyncio
    async def test_process_pool_runs_in_separate_process(self):
        """
        Test that work submitted to ProcessPoolExecutor runs in a separate process.
        
        This is the fundamental requirement for GIL isolation - the subprocess
        must have a different PID than the main process.
        
        Validates: Task 9.3 - ProcessPoolExecutor isolation from main event loop
        """
        main_pid = os.getpid()
        
        # Use spawn context for PyTorch compatibility
        ctx = multiprocessing.get_context('spawn')
        
        with ProcessPoolExecutor(max_workers=1, mp_context=ctx) as executor:
            loop = asyncio.get_event_loop()
            
            # Submit work to get process info
            future = loop.run_in_executor(executor, _get_process_info)
            worker_info = await future
        
        # Verify work ran in a different process
        assert worker_info["pid"] != main_pid, \
            f"Worker PID ({worker_info['pid']}) should differ from main PID ({main_pid})"
        assert worker_info["is_main_process"] is False, \
            "Worker should not be the main process"
        
        print(f"✅ ProcessPoolExecutor runs in separate process (main: {main_pid}, worker: {worker_info['pid']})")
    
    @pytest.mark.asyncio
    async def test_event_loop_responsive_during_process_pool_work(self):
        """
        Test that the main event loop remains responsive during ProcessPoolExecutor work.
        
        This validates that CPU-bound work in the subprocess doesn't block
        the main event loop, allowing health checks to proceed.
        
        Validates: Task 9.3 - ProcessPoolExecutor isolation from main event loop
        """
        event_loop_response_times: List[float] = []
        
        async def monitor_event_loop_responsiveness():
            """Monitor how quickly the event loop responds to async operations."""
            for i in range(20):
                start = time.time()
                await asyncio.sleep(0.01)  # 10ms sleep
                elapsed_ms = (time.time() - start) * 1000
                event_loop_response_times.append(elapsed_ms)
        
        async def run_cpu_work_in_process():
            """Run CPU-bound work in ProcessPoolExecutor."""
            ctx = multiprocessing.get_context('spawn')
            loop = asyncio.get_event_loop()
            
            with ProcessPoolExecutor(max_workers=2, mp_context=ctx) as executor:
                # Submit multiple CPU-bound tasks
                futures = [
                    loop.run_in_executor(executor, _cpu_bound_work_module_level, 0.1)
                    for _ in range(3)
                ]
                results = await asyncio.gather(*futures)
                return results
        
        # Run both concurrently
        results = await asyncio.gather(
            run_cpu_work_in_process(),
            monitor_event_loop_responsiveness()
        )
        
        cpu_results = results[0]
        
        # Verify CPU work completed in subprocesses
        for result in cpu_results:
            assert result["process_id"] != os.getpid()
        
        # Verify event loop remained responsive
        avg_response = statistics.mean(event_loop_response_times)
        max_response = max(event_loop_response_times)
        
        # Event loop should respond within reasonable time (allowing for scheduling overhead)
        # 10ms sleep + some overhead should be < 50ms
        assert max_response < 50, \
            f"Event loop blocked: max response {max_response:.1f}ms (should be <50ms)"
        
        print(f"✅ Event loop responsive during ProcessPoolExecutor work "
              f"(avg: {avg_response:.1f}ms, max: {max_response:.1f}ms)")
    
    @pytest.mark.asyncio
    async def test_health_check_simulation_during_process_pool_work(self):
        """
        Test that simulated health checks respond quickly during ProcessPoolExecutor work.
        
        This simulates the actual health check scenario where the endpoint
        must respond within 100ms even during model loading.
        
        Validates: Task 9.3 - ProcessPoolExecutor isolation from main event loop
        """
        health_check_times: List[float] = []
        
        async def simulate_health_check():
            """Simulate a health check endpoint call."""
            start = time.time()
            # Simulate minimal health check work
            status = {"status": "ok", "timestamp": datetime.now().isoformat()}
            await asyncio.sleep(0)  # Yield to event loop
            elapsed_ms = (time.time() - start) * 1000
            return elapsed_ms, status
        
        async def run_health_checks():
            """Run multiple health checks during CPU work."""
            for _ in range(30):
                elapsed_ms, _ = await simulate_health_check()
                health_check_times.append(elapsed_ms)
                await asyncio.sleep(0.02)  # 20ms between checks
        
        async def run_model_loading_simulation():
            """Simulate model loading in ProcessPoolExecutor."""
            ctx = multiprocessing.get_context('spawn')
            loop = asyncio.get_event_loop()
            
            with ProcessPoolExecutor(max_workers=2, mp_context=ctx) as executor:
                # Simulate loading multiple models
                models = ["text-embedding", "chat-model", "search-index"]
                futures = [
                    loop.run_in_executor(
                        executor, 
                        _simulate_model_loading, 
                        model, 
                        0.2  # 200ms load time each
                    )
                    for model in models
                ]
                results = await asyncio.gather(*futures)
                return results
        
        # Run both concurrently
        results = await asyncio.gather(
            run_model_loading_simulation(),
            run_health_checks()
        )
        
        model_results = results[0]
        
        # Verify models loaded in subprocesses
        for result in model_results:
            assert result["process_id"] != os.getpid()
        
        # Verify health checks remained fast
        avg_time = statistics.mean(health_check_times)
        max_time = max(health_check_times)
        p95_time = sorted(health_check_times)[int(len(health_check_times) * 0.95)]
        
        # Health checks should be very fast (< 10ms typically)
        assert p95_time < 100, \
            f"Health check p95 ({p95_time:.1f}ms) exceeds 100ms threshold"
        
        print(f"✅ Health checks fast during ProcessPoolExecutor model loading "
              f"(avg: {avg_time:.1f}ms, max: {max_time:.1f}ms, p95: {p95_time:.1f}ms)")


class TestThreadPoolVsProcessPoolComparison:
    """Compare ThreadPoolExecutor and ProcessPoolExecutor behavior for GIL blocking."""
    
    @pytest.mark.asyncio
    async def test_thread_pool_shares_gil_with_event_loop(self):
        """
        Test that ThreadPoolExecutor shares GIL with the main event loop.
        
        This demonstrates the problem that ProcessPoolExecutor solves:
        CPU-bound work in ThreadPoolExecutor can delay event loop operations.
        
        Validates: Task 9.3 - Understanding why ProcessPoolExecutor is needed
        """
        event_loop_times: List[float] = []
        
        def cpu_bound_in_thread():
            """CPU-bound work that holds the GIL."""
            result = 0
            for i in range(1000000):
                result += i * i
            return result
        
        async def monitor_event_loop():
            """Monitor event loop responsiveness."""
            for _ in range(10):
                start = time.time()
                await asyncio.sleep(0.01)
                elapsed_ms = (time.time() - start) * 1000
                event_loop_times.append(elapsed_ms)
        
        async def run_in_thread_pool():
            """Run CPU work in ThreadPoolExecutor."""
            loop = asyncio.get_event_loop()
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    loop.run_in_executor(executor, cpu_bound_in_thread)
                    for _ in range(4)
                ]
                await asyncio.gather(*futures)
        
        # Run both concurrently
        await asyncio.gather(
            run_in_thread_pool(),
            monitor_event_loop()
        )
        
        avg_time = statistics.mean(event_loop_times)
        max_time = max(event_loop_times)
        
        # ThreadPoolExecutor may show some GIL contention
        # This test documents the behavior rather than asserting specific values
        print(f"📊 ThreadPoolExecutor event loop times: avg={avg_time:.1f}ms, max={max_time:.1f}ms")
        print("   (Note: ThreadPoolExecutor shares GIL, may show some delays)")
    
    @pytest.mark.asyncio
    async def test_process_pool_isolates_gil_from_event_loop(self):
        """
        Test that ProcessPoolExecutor isolates GIL from the main event loop.
        
        This demonstrates the solution: CPU-bound work in ProcessPoolExecutor
        doesn't affect event loop responsiveness.
        
        Validates: Task 9.3 - ProcessPoolExecutor isolation from main event loop
        """
        event_loop_times: List[float] = []
        
        async def monitor_event_loop():
            """Monitor event loop responsiveness."""
            for _ in range(10):
                start = time.time()
                await asyncio.sleep(0.01)
                elapsed_ms = (time.time() - start) * 1000
                event_loop_times.append(elapsed_ms)
        
        async def run_in_process_pool():
            """Run CPU work in ProcessPoolExecutor."""
            ctx = multiprocessing.get_context('spawn')
            loop = asyncio.get_event_loop()
            
            with ProcessPoolExecutor(max_workers=2, mp_context=ctx) as executor:
                futures = [
                    loop.run_in_executor(executor, _cpu_bound_work_module_level, 0.1)
                    for _ in range(4)
                ]
                await asyncio.gather(*futures)
        
        # Run both concurrently
        await asyncio.gather(
            run_in_process_pool(),
            monitor_event_loop()
        )
        
        avg_time = statistics.mean(event_loop_times)
        max_time = max(event_loop_times)
        
        # ProcessPoolExecutor should show minimal impact on event loop
        assert max_time < 50, \
            f"ProcessPoolExecutor should not block event loop: max={max_time:.1f}ms"
        
        print(f"✅ ProcessPoolExecutor isolates GIL: avg={avg_time:.1f}ms, max={max_time:.1f}ms")


class TestModelManagerProcessPoolIntegration:
    """Test ModelManager's integration with ProcessPoolExecutor."""
    
    def test_model_manager_creates_process_pool(self):
        """
        Test that ModelManager creates a ProcessPoolExecutor for model loading.
        
        Validates: Task 9.3 - ModelManager uses ProcessPoolExecutor
        """
        from multimodal_librarian.models.model_manager import ModelManager
        
        manager = ModelManager(max_concurrent_loads=2)
        
        try:
            # Verify process pool was created
            assert hasattr(manager, 'process_pool'), \
                "ModelManager should have process_pool attribute"
            assert manager.process_pool is not None, \
                "ModelManager process_pool should not be None"
            
            # Check if using ProcessPoolExecutor or fallback ThreadPoolExecutor
            if manager._use_process_pool:
                assert isinstance(manager.process_pool, ProcessPoolExecutor), \
                    "ModelManager should use ProcessPoolExecutor when available"
                print("✅ ModelManager uses ProcessPoolExecutor")
            else:
                assert isinstance(manager.process_pool, ThreadPoolExecutor), \
                    "ModelManager should fallback to ThreadPoolExecutor"
                print("⚠️ ModelManager fell back to ThreadPoolExecutor")
        finally:
            # Cleanup
            if hasattr(manager, 'process_pool') and manager.process_pool:
                manager.process_pool.shutdown(wait=True)
            if hasattr(manager, 'thread_pool') and manager.thread_pool:
                manager.thread_pool.shutdown(wait=True)
    
    def test_model_manager_uses_spawn_context(self):
        """
        Test that ModelManager uses 'spawn' multiprocessing context.
        
        The 'spawn' context is required for PyTorch compatibility.
        
        Validates: Task 9.3 - Correct multiprocessing context
        """
        import inspect
        from multimodal_librarian.models.model_manager import ModelManager
        
        # Check the source code for spawn context usage
        source = inspect.getsource(ModelManager.__init__)
        
        # Verify spawn context is used
        assert "spawn" in source.lower(), \
            "ModelManager should use 'spawn' multiprocessing context"
        
        print("✅ ModelManager uses 'spawn' multiprocessing context")
    
    @pytest.mark.asyncio
    async def test_model_manager_load_does_not_block_event_loop(self):
        """
        Test that ModelManager's model loading doesn't block the event loop.
        
        Validates: Task 9.3 - ProcessPoolExecutor isolation from main event loop
        """
        from multimodal_librarian.models.model_manager import ModelManager, ModelConfig, ModelPriority
        
        event_loop_times: List[float] = []
        
        async def monitor_event_loop():
            """Monitor event loop responsiveness during model loading."""
            for _ in range(15):
                start = time.time()
                await asyncio.sleep(0.02)  # 20ms sleep
                elapsed_ms = (time.time() - start) * 1000
                event_loop_times.append(elapsed_ms)
        
        async def load_model_with_manager():
            """Load a model using ModelManager."""
            manager = ModelManager(max_concurrent_loads=1)
            
            try:
                # Register a test model
                config = ModelConfig(
                    name="test-model",
                    priority=ModelPriority.ESSENTIAL,
                    estimated_load_time_seconds=0.1,  # 100ms simulated load
                    estimated_memory_mb=100.0,
                    required_for_capabilities=["test"],
                    model_type="test"
                )
                manager.register_model(config)
                
                # Load the model using force_load_model (the actual API method)
                success = await manager.force_load_model("test-model")
                return success
            finally:
                # Cleanup
                if hasattr(manager, 'process_pool') and manager.process_pool:
                    manager.process_pool.shutdown(wait=True)
                if hasattr(manager, 'thread_pool') and manager.thread_pool:
                    manager.thread_pool.shutdown(wait=True)
        
        # Run both concurrently
        results = await asyncio.gather(
            load_model_with_manager(),
            monitor_event_loop()
        )
        
        load_success = results[0]
        
        # Verify model loaded
        assert load_success, "Model should load successfully"
        
        # Verify event loop remained responsive
        avg_time = statistics.mean(event_loop_times)
        max_time = max(event_loop_times)
        
        # Event loop should respond within reasonable time
        assert max_time < 100, \
            f"Event loop blocked during model loading: max={max_time:.1f}ms"
        
        print(f"✅ ModelManager load doesn't block event loop "
              f"(avg: {avg_time:.1f}ms, max: {max_time:.1f}ms)")


class TestProcessPoolExecutorEdgeCases:
    """Test edge cases and error handling for ProcessPoolExecutor isolation."""
    
    @pytest.mark.asyncio
    async def test_multiple_concurrent_process_pool_tasks(self):
        """
        Test that multiple concurrent ProcessPoolExecutor tasks don't block event loop.
        
        Validates: Task 9.3 - ProcessPoolExecutor isolation under load
        """
        event_loop_times: List[float] = []
        
        async def monitor_event_loop():
            """Monitor event loop during heavy subprocess load."""
            for _ in range(20):
                start = time.time()
                await asyncio.sleep(0.01)
                elapsed_ms = (time.time() - start) * 1000
                event_loop_times.append(elapsed_ms)
        
        async def run_many_subprocess_tasks():
            """Run many tasks in ProcessPoolExecutor."""
            ctx = multiprocessing.get_context('spawn')
            loop = asyncio.get_event_loop()
            
            with ProcessPoolExecutor(max_workers=4, mp_context=ctx) as executor:
                # Submit many tasks
                futures = [
                    loop.run_in_executor(executor, _cpu_bound_work_module_level, 0.05)
                    for _ in range(10)
                ]
                results = await asyncio.gather(*futures)
                return results
        
        # Run both concurrently
        results = await asyncio.gather(
            run_many_subprocess_tasks(),
            monitor_event_loop()
        )
        
        subprocess_results = results[0]
        
        # Verify all tasks completed in subprocesses
        main_pid = os.getpid()
        for result in subprocess_results:
            assert result["process_id"] != main_pid
        
        # Verify event loop remained responsive
        avg_time = statistics.mean(event_loop_times)
        max_time = max(event_loop_times)
        
        assert max_time < 50, \
            f"Event loop blocked with many subprocess tasks: max={max_time:.1f}ms"
        
        print(f"✅ Event loop responsive with {len(subprocess_results)} concurrent subprocess tasks "
              f"(avg: {avg_time:.1f}ms, max: {max_time:.1f}ms)")
    
    @pytest.mark.asyncio
    async def test_process_pool_cleanup_doesnt_block(self):
        """
        Test that ProcessPoolExecutor cleanup doesn't block the event loop.
        
        Validates: Task 9.3 - Clean shutdown of ProcessPoolExecutor
        """
        event_loop_times: List[float] = []
        cleanup_complete = False
        
        async def monitor_during_cleanup():
            """Monitor event loop during pool cleanup."""
            while not cleanup_complete:
                start = time.time()
                await asyncio.sleep(0.01)
                elapsed_ms = (time.time() - start) * 1000
                event_loop_times.append(elapsed_ms)
        
        async def create_and_cleanup_pool():
            """Create pool, do work, and cleanup."""
            nonlocal cleanup_complete
            
            ctx = multiprocessing.get_context('spawn')
            loop = asyncio.get_event_loop()
            
            pool = ProcessPoolExecutor(max_workers=2, mp_context=ctx)
            
            try:
                # Do some work
                future = loop.run_in_executor(pool, _cpu_bound_work_module_level, 0.05)
                await future
            finally:
                # Cleanup
                pool.shutdown(wait=True)
                cleanup_complete = True
        
        # Run both concurrently
        await asyncio.gather(
            create_and_cleanup_pool(),
            monitor_during_cleanup()
        )
        
        # Verify event loop remained responsive during cleanup
        if event_loop_times:
            avg_time = statistics.mean(event_loop_times)
            max_time = max(event_loop_times)
            
            assert max_time < 100, \
                f"Event loop blocked during pool cleanup: max={max_time:.1f}ms"
            
            print(f"✅ ProcessPoolExecutor cleanup doesn't block event loop "
                  f"(avg: {avg_time:.1f}ms, max: {max_time:.1f}ms)")
        else:
            print("✅ ProcessPoolExecutor cleanup completed quickly")


class TestHealthCheckEndpointWithProcessPool:
    """Test actual health check endpoint behavior with ProcessPoolExecutor work."""
    
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
    
    @pytest.mark.asyncio
    async def test_health_endpoint_responds_during_subprocess_work(self, mock_minimal_server):
        """
        Test that health check endpoint responds quickly during subprocess work.
        
        Validates: Task 9.3 - Health checks respond during ProcessPoolExecutor work
        """
        from multimodal_librarian.api.routers.health import simple_health_check
        
        health_check_times: List[float] = []
        
        async def make_health_checks():
            """Make health check requests during subprocess work."""
            for _ in range(20):
                start = time.time()
                with patch('multimodal_librarian.api.routers.health.get_minimal_server',
                           return_value=mock_minimal_server):
                    response = await simple_health_check()
                elapsed_ms = (time.time() - start) * 1000
                health_check_times.append(elapsed_ms)
                assert response.status_code == 200
                await asyncio.sleep(0.02)
        
        async def run_subprocess_work():
            """Run CPU work in ProcessPoolExecutor."""
            ctx = multiprocessing.get_context('spawn')
            loop = asyncio.get_event_loop()
            
            with ProcessPoolExecutor(max_workers=2, mp_context=ctx) as executor:
                futures = [
                    loop.run_in_executor(executor, _simulate_model_loading, f"model-{i}", 0.15)
                    for i in range(4)
                ]
                await asyncio.gather(*futures)
        
        # Run both concurrently
        await asyncio.gather(
            run_subprocess_work(),
            make_health_checks()
        )
        
        # Verify health checks remained fast
        avg_time = statistics.mean(health_check_times)
        max_time = max(health_check_times)
        p95_time = sorted(health_check_times)[int(len(health_check_times) * 0.95)]
        
        assert p95_time < 100, \
            f"Health check p95 ({p95_time:.1f}ms) exceeds 100ms during subprocess work"
        
        print(f"✅ Health endpoint responds during subprocess work "
              f"(avg: {avg_time:.1f}ms, max: {max_time:.1f}ms, p95: {p95_time:.1f}ms)")


def run_tests():
    """Run all tests."""
    print("=" * 70)
    print("Testing ProcessPoolExecutor Isolation from Main Event Loop")
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
