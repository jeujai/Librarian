"""
Performance tests for fallback detection system.

Tests the performance impact and efficiency of the fallback detection system
under various load conditions.
"""

import pytest
import asyncio
import time
import statistics
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from typing import List, Dict, Any

from src.multimodal_librarian.components.vector_store.fallback_manager import (
    FallbackManager, FallbackConfig
)
from src.multimodal_librarian.components.vector_store.search_service_enhanced import (
    SearchServiceWithFallback
)
from src.multimodal_librarian.components.vector_store.search_service import SearchRequest


class PerformanceTestService:
    """Service for performance testing with configurable behavior."""
    
    def __init__(self, name: str, base_latency_ms: float = 10.0, failure_rate: float = 0.0):
        self.name = name
        self.base_latency_ms = base_latency_ms
        self.failure_rate = failure_rate
        self.call_count = 0
        self.total_time = 0.0
        
    async def health_check(self) -> bool:
        """Performance-oriented health check."""
        start_time = time.time()
        
        # Simulate work
        await asyncio.sleep(self.base_latency_ms / 1000.0)
        
        self.call_count += 1
        self.total_time += (time.time() - start_time) * 1000
        
        # Simulate failures based on failure rate
        import random
        if random.random() < self.failure_rate:
            raise Exception(f"Simulated failure in {self.name}")
        
        return True
    
    async def search(self, request):
        """Performance-oriented search method."""
        start_time = time.time()
        
        # Simulate search work
        await asyncio.sleep(self.base_latency_ms / 1000.0)
        
        self.call_count += 1
        self.total_time += (time.time() - start_time) * 1000
        
        # Simulate failures
        import random
        if random.random() < self.failure_rate:
            raise Exception(f"Simulated search failure in {self.name}")
        
        from src.multimodal_librarian.components.vector_store.search_service_simple import SimpleSearchResponse
        return SimpleSearchResponse(
            results=[],
            search_time_ms=self.base_latency_ms,
            session_id=getattr(request, 'session_id', 'test')
        )
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        avg_latency = self.total_time / self.call_count if self.call_count > 0 else 0
        return {
            'call_count': self.call_count,
            'total_time_ms': self.total_time,
            'avg_latency_ms': avg_latency
        }


@pytest.fixture
def performance_config():
    """Create performance-oriented fallback configuration."""
    return FallbackConfig(
        health_check_interval_seconds=0.1,  # Very fast for performance testing
        health_check_timeout_seconds=1.0,
        max_response_time_ms=100.0,
        max_error_rate=0.05,
        consecutive_failures_threshold=2,
        consecutive_successes_threshold=2,
        enable_notifications=False,  # Disable for performance
        notification_cooldown_minutes=0
    )


@pytest.fixture
def mock_vector_store():
    """Create mock vector store for performance testing."""
    mock_store = Mock()
    mock_store.health_check.return_value = True
    mock_store.semantic_search.return_value = []
    return mock_store


class TestFallbackManagerPerformance:
    """Test fallback manager performance characteristics."""
    
    @pytest.mark.asyncio
    async def test_health_check_performance(self, performance_config):
        """Test health check performance with multiple services."""
        fallback_manager = FallbackManager(performance_config)
        
        # Create multiple services with different latencies
        services = []
        for i in range(10):
            service = PerformanceTestService(f"service_{i}", base_latency_ms=5.0)
            services.append(service)
            fallback_manager.register_service(f"service_{i}", service)
        
        # Measure health check performance
        start_time = time.time()
        
        # Perform health checks for all services
        tasks = []
        for i in range(10):
            task = fallback_manager._check_service_health(f"service_{i}")
            tasks.append(task)
        
        await asyncio.gather(*tasks)
        
        total_time = (time.time() - start_time) * 1000  # Convert to ms
        
        # Verify performance
        assert total_time < 100.0  # Should complete within 100ms
        
        # Verify all services were checked
        for service in services:
            assert service.call_count == 1
        
        print(f"Health check for 10 services completed in {total_time:.2f}ms")
    
    @pytest.mark.asyncio
    async def test_monitoring_loop_overhead(self, performance_config):
        """Test monitoring loop performance overhead."""
        fallback_manager = FallbackManager(performance_config)
        
        # Create services
        fast_service = PerformanceTestService("fast", base_latency_ms=1.0)
        slow_service = PerformanceTestService("slow", base_latency_ms=10.0)
        
        fallback_manager.register_service("fast", fast_service)
        fallback_manager.register_service("slow", slow_service)
        
        # Start monitoring
        await fallback_manager.start_monitoring()
        
        # Let it run for a short time
        start_time = time.time()
        await asyncio.sleep(1.0)  # 1 second
        runtime = time.time() - start_time
        
        # Stop monitoring
        await fallback_manager.stop_monitoring()
        
        # Calculate monitoring overhead
        expected_cycles = runtime / performance_config.health_check_interval_seconds
        actual_cycles = fast_service.call_count
        
        # Should be close to expected cycles (within 20% tolerance)
        assert abs(actual_cycles - expected_cycles) / expected_cycles < 0.2
        
        print(f"Monitoring ran {actual_cycles} cycles in {runtime:.2f}s (expected ~{expected_cycles:.1f})")
    
    @pytest.mark.asyncio
    async def test_fallback_detection_latency(self, performance_config):
        """Test latency of fallback detection."""
        fallback_manager = FallbackManager(performance_config)
        
        # Create services
        failing_service = PerformanceTestService("failing", failure_rate=1.0)  # Always fails
        healthy_service = PerformanceTestService("healthy")
        
        fallback_manager.register_service("failing", failing_service, is_primary=True)
        fallback_manager.register_service("healthy", healthy_service)
        
        # Track fallback events
        fallback_events = []
        fallback_manager.add_notification_callback(lambda event: fallback_events.append(event))
        
        # Start monitoring
        await fallback_manager.start_monitoring()
        
        # Wait for fallback detection
        start_time = time.time()
        while len(fallback_events) == 0 and (time.time() - start_time) < 5.0:
            await asyncio.sleep(0.01)
        
        detection_time = (time.time() - start_time) * 1000
        
        # Stop monitoring
        await fallback_manager.stop_monitoring()
        
        # Verify fallback was detected quickly
        assert len(fallback_events) > 0
        assert detection_time < 1000.0  # Should detect within 1 second
        
        print(f"Fallback detected in {detection_time:.2f}ms")
    
    @pytest.mark.asyncio
    async def test_concurrent_health_checks(self, performance_config):
        """Test performance with concurrent health checks."""
        fallback_manager = FallbackManager(performance_config)
        
        # Create many services
        num_services = 50
        services = []
        for i in range(num_services):
            service = PerformanceTestService(f"service_{i}", base_latency_ms=2.0)
            services.append(service)
            fallback_manager.register_service(f"service_{i}", service)
        
        # Measure concurrent health check performance
        start_time = time.time()
        
        # Create concurrent health check tasks
        tasks = []
        for i in range(num_services):
            task = fallback_manager._check_service_health(f"service_{i}")
            tasks.append(task)
        
        # Execute all health checks concurrently
        await asyncio.gather(*tasks)
        
        total_time = (time.time() - start_time) * 1000
        
        # Should complete much faster than sequential execution
        sequential_time_estimate = num_services * 2.0  # 2ms per service
        assert total_time < sequential_time_estimate * 0.5  # At least 50% faster
        
        print(f"Concurrent health checks for {num_services} services: {total_time:.2f}ms")
        print(f"Sequential estimate: {sequential_time_estimate:.2f}ms")
        print(f"Speedup: {sequential_time_estimate / total_time:.1f}x")


class TestSearchServicePerformance:
    """Test search service performance with fallback management."""
    
    @pytest.mark.asyncio
    async def test_search_performance_without_fallback(self, mock_vector_store, performance_config):
        """Test search performance when no fallback is needed."""
        service = SearchServiceWithFallback(mock_vector_store, fallback_config=performance_config)
        
        # Mock primary service for consistent performance
        with patch.object(service.primary_service, 'search', new_callable=AsyncMock) as mock_search:
            from src.multimodal_librarian.components.vector_store.search_service_simple import SimpleSearchResponse
            mock_search.return_value = SimpleSearchResponse(
                results=[], search_time_ms=10.0, session_id="perf-test"
            )
            
            # Perform multiple searches and measure performance
            num_searches = 100
            search_times = []
            
            for i in range(num_searches):
                request = SearchRequest(query=f"test query {i}", session_id=f"session-{i}")
                
                start_time = time.time()
                await service.search(request)
                search_time = (time.time() - start_time) * 1000
                
                search_times.append(search_time)
            
            # Analyze performance
            avg_time = statistics.mean(search_times)
            p95_time = statistics.quantiles(search_times, n=20)[18]  # 95th percentile
            
            # Performance should be good without fallback overhead
            assert avg_time < 50.0  # Average under 50ms
            assert p95_time < 100.0  # 95th percentile under 100ms
            
            print(f"Search performance without fallback:")
            print(f"  Average: {avg_time:.2f}ms")
            print(f"  95th percentile: {p95_time:.2f}ms")
            print(f"  Min: {min(search_times):.2f}ms")
            print(f"  Max: {max(search_times):.2f}ms")
    
    @pytest.mark.asyncio
    async def test_search_performance_with_fallback_switching(self, mock_vector_store, performance_config):
        """Test search performance during fallback switching."""
        service = SearchServiceWithFallback(mock_vector_store, fallback_config=performance_config)
        
        # Track search times during different phases
        primary_times = []
        fallback_times = []
        recovery_times = []
        
        # Phase 1: Normal operation with primary service
        with patch.object(service.primary_service, 'search', new_callable=AsyncMock) as mock_primary:
            from src.multimodal_librarian.components.vector_store.search_service_simple import SimpleSearchResponse
            mock_primary.return_value = SimpleSearchResponse(
                results=[], search_time_ms=10.0, session_id="perf-test"
            )
            
            for i in range(20):
                request = SearchRequest(query=f"primary query {i}")
                start_time = time.time()
                await service.search(request)
                primary_times.append((time.time() - start_time) * 1000)
        
        # Trigger fallback
        await service.manual_fallback("Performance test fallback")
        
        # Phase 2: Fallback operation
        with patch.object(service.fallback_service, 'search', new_callable=AsyncMock) as mock_fallback:
            mock_fallback.return_value = SimpleSearchResponse(
                results=[], search_time_ms=15.0, session_id="perf-test"
            )
            
            for i in range(20):
                request = SearchRequest(query=f"fallback query {i}")
                start_time = time.time()
                await service.search(request)
                fallback_times.append((time.time() - start_time) * 1000)
        
        # Trigger recovery
        await service.manual_recovery()
        
        # Phase 3: Recovery operation
        with patch.object(service.primary_service, 'search', new_callable=AsyncMock) as mock_primary_recovery:
            mock_primary_recovery.return_value = SimpleSearchResponse(
                results=[], search_time_ms=10.0, session_id="perf-test"
            )
            
            for i in range(20):
                request = SearchRequest(query=f"recovery query {i}")
                start_time = time.time()
                await service.search(request)
                recovery_times.append((time.time() - start_time) * 1000)
        
        # Analyze performance across phases
        primary_avg = statistics.mean(primary_times)
        fallback_avg = statistics.mean(fallback_times)
        recovery_avg = statistics.mean(recovery_times)
        
        print(f"Search performance across phases:")
        print(f"  Primary service: {primary_avg:.2f}ms average")
        print(f"  Fallback service: {fallback_avg:.2f}ms average")
        print(f"  Recovery service: {recovery_avg:.2f}ms average")
        
        # All phases should maintain reasonable performance
        assert primary_avg < 50.0
        assert fallback_avg < 100.0  # Fallback may be slightly slower
        assert recovery_avg < 50.0
    
    @pytest.mark.asyncio
    async def test_concurrent_search_performance(self, mock_vector_store, performance_config):
        """Test search performance under concurrent load."""
        service = SearchServiceWithFallback(mock_vector_store, fallback_config=performance_config)
        
        # Mock search method
        with patch.object(service.primary_service, 'search', new_callable=AsyncMock) as mock_search:
            from src.multimodal_librarian.components.vector_store.search_service_simple import SimpleSearchResponse
            
            async def mock_search_impl(*args, **kwargs):
                await asyncio.sleep(0.01)  # 10ms simulated work
                return SimpleSearchResponse(results=[], search_time_ms=10.0, session_id="concurrent-test")
            
            mock_search.side_effect = mock_search_impl
            
            # Perform concurrent searches
            num_concurrent = 50
            num_searches_per_task = 10
            
            async def search_task(task_id: int) -> List[float]:
                """Perform multiple searches and return timing data."""
                times = []
                for i in range(num_searches_per_task):
                    request = SearchRequest(query=f"concurrent query {task_id}-{i}")
                    start_time = time.time()
                    await service.search(request)
                    times.append((time.time() - start_time) * 1000)
                return times
            
            # Execute concurrent search tasks
            start_time = time.time()
            tasks = [search_task(i) for i in range(num_concurrent)]
            results = await asyncio.gather(*tasks)
            total_time = (time.time() - start_time) * 1000
            
            # Flatten results
            all_times = [time for task_times in results for time in task_times]
            
            # Analyze concurrent performance
            total_searches = num_concurrent * num_searches_per_task
            avg_time = statistics.mean(all_times)
            p95_time = statistics.quantiles(all_times, n=20)[18]
            throughput = total_searches / (total_time / 1000)  # searches per second
            
            print(f"Concurrent search performance:")
            print(f"  Total searches: {total_searches}")
            print(f"  Total time: {total_time:.2f}ms")
            print(f"  Average latency: {avg_time:.2f}ms")
            print(f"  95th percentile: {p95_time:.2f}ms")
            print(f"  Throughput: {throughput:.1f} searches/second")
            
            # Performance should scale well
            assert avg_time < 100.0  # Average latency under 100ms
            assert p95_time < 200.0  # 95th percentile under 200ms
            assert throughput > 100.0  # At least 100 searches/second
    
    @pytest.mark.asyncio
    async def test_fallback_overhead_measurement(self, mock_vector_store, performance_config):
        """Measure the overhead introduced by fallback management."""
        # Create service without fallback management
        from src.multimodal_librarian.components.vector_store.search_service import EnhancedSemanticSearchService
        simple_service = EnhancedSemanticSearchService(mock_vector_store)
        
        # Create service with fallback management
        enhanced_service = SearchServiceWithFallback(mock_vector_store, fallback_config=performance_config)
        
        # Mock search methods consistently
        from src.multimodal_librarian.components.vector_store.search_service_simple import SimpleSearchResponse
        mock_response = SimpleSearchResponse(results=[], search_time_ms=10.0, session_id="overhead-test")
        
        # Measure simple service performance
        simple_times = []
        with patch.object(simple_service, 'search', new_callable=AsyncMock) as mock_simple:
            mock_simple.return_value = mock_response
            
            for i in range(100):
                request = SearchRequest(query=f"simple query {i}")
                start_time = time.time()
                await simple_service.search(request)
                simple_times.append((time.time() - start_time) * 1000)
        
        # Measure enhanced service performance
        enhanced_times = []
        with patch.object(enhanced_service.primary_service, 'search', new_callable=AsyncMock) as mock_enhanced:
            mock_enhanced.return_value = mock_response
            
            for i in range(100):
                request = SearchRequest(query=f"enhanced query {i}")
                start_time = time.time()
                await enhanced_service.search(request)
                enhanced_times.append((time.time() - start_time) * 1000)
        
        # Calculate overhead
        simple_avg = statistics.mean(simple_times)
        enhanced_avg = statistics.mean(enhanced_times)
        overhead_ms = enhanced_avg - simple_avg
        overhead_percent = (overhead_ms / simple_avg) * 100
        
        print(f"Fallback management overhead:")
        print(f"  Simple service: {simple_avg:.2f}ms average")
        print(f"  Enhanced service: {enhanced_avg:.2f}ms average")
        print(f"  Overhead: {overhead_ms:.2f}ms ({overhead_percent:.1f}%)")
        
        # Overhead should be minimal
        assert overhead_percent < 50.0  # Less than 50% overhead
        assert overhead_ms < 10.0  # Less than 10ms absolute overhead


@pytest.mark.asyncio
async def test_stress_test_fallback_system(mock_vector_store, performance_config):
    """Stress test the fallback system under high load."""
    service = SearchServiceWithFallback(mock_vector_store, fallback_config=performance_config)
    
    # Start monitoring
    await service.start()
    
    try:
        # Create high load scenario
        num_concurrent_users = 20
        searches_per_user = 50
        failure_injection_rate = 0.1  # 10% of searches fail
        
        async def user_simulation(user_id: int) -> Dict[str, Any]:
            """Simulate a user performing multiple searches."""
            user_stats = {
                'successful_searches': 0,
                'failed_searches': 0,
                'total_time_ms': 0.0,
                'search_times': []
            }
            
            for i in range(searches_per_user):
                request = SearchRequest(query=f"user {user_id} query {i}")
                
                # Inject failures randomly
                import random
                should_fail = random.random() < failure_injection_rate
                
                with patch.object(service.primary_service, 'search', new_callable=AsyncMock) as mock_search:
                    if should_fail:
                        mock_search.side_effect = Exception("Injected failure")
                    else:
                        from src.multimodal_librarian.components.vector_store.search_service_simple import SimpleSearchResponse
                        mock_search.return_value = SimpleSearchResponse(
                            results=[], search_time_ms=10.0, session_id=f"user-{user_id}"
                        )
                    
                    start_time = time.time()
                    try:
                        await service.search(request)
                        search_time = (time.time() - start_time) * 1000
                        user_stats['successful_searches'] += 1
                        user_stats['search_times'].append(search_time)
                    except Exception:
                        user_stats['failed_searches'] += 1
                    
                    user_stats['total_time_ms'] += (time.time() - start_time) * 1000
                
                # Small delay between searches
                await asyncio.sleep(0.01)
            
            return user_stats
        
        # Run stress test
        start_time = time.time()
        user_tasks = [user_simulation(i) for i in range(num_concurrent_users)]
        user_results = await asyncio.gather(*user_tasks)
        total_test_time = (time.time() - start_time) * 1000
        
        # Aggregate results
        total_searches = sum(stats['successful_searches'] + stats['failed_searches'] for stats in user_results)
        total_successful = sum(stats['successful_searches'] for stats in user_results)
        total_failed = sum(stats['failed_searches'] for stats in user_results)
        
        all_search_times = []
        for stats in user_results:
            all_search_times.extend(stats['search_times'])
        
        success_rate = (total_successful / total_searches) * 100
        avg_search_time = statistics.mean(all_search_times) if all_search_times else 0
        throughput = total_searches / (total_test_time / 1000)
        
        print(f"Stress test results:")
        print(f"  Total searches: {total_searches}")
        print(f"  Successful: {total_successful}")
        print(f"  Failed: {total_failed}")
        print(f"  Success rate: {success_rate:.1f}%")
        print(f"  Average search time: {avg_search_time:.2f}ms")
        print(f"  Throughput: {throughput:.1f} searches/second")
        print(f"  Test duration: {total_test_time:.2f}ms")
        
        # Get final service statistics
        final_stats = service.get_performance_stats()
        fallback_stats = service.fallback_manager.get_fallback_statistics()
        
        print(f"Service statistics:")
        print(f"  Service switches: {final_stats['service_switches']}")
        print(f"  Fallback activations: {final_stats['fallback_activations']}")
        print(f"  Primary searches: {final_stats['primary_searches']}")
        print(f"  Fallback searches: {final_stats['fallback_searches']}")
        
        # System should maintain reasonable performance under stress
        assert success_rate > 80.0  # At least 80% success rate
        assert avg_search_time < 200.0  # Average under 200ms
        assert throughput > 50.0  # At least 50 searches/second
    
    finally:
        # Stop monitoring
        await service.stop()


if __name__ == "__main__":
    # Run performance tests
    pytest.main([__file__, "-v", "-s"])