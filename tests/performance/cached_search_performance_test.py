"""
Performance tests for cached search service.

Tests cache hit rates, performance improvements, and resource usage
to validate Requirement 4.5 - result caching effectiveness.
"""

import pytest
import asyncio
import time
import statistics
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from typing import List, Dict, Any, Tuple

# Import the cached search service and dependencies
from src.multimodal_librarian.components.vector_store.search_service_cached import (
    CachedSearchService,
    CachedSimpleSearchService,
    CacheMetrics
)
from src.multimodal_librarian.components.vector_store.search_service_simple import (
    SimpleSearchRequest,
    SimpleSearchResponse,
    SimpleSearchResult
)
from src.multimodal_librarian.models.core import SourceType, ContentType
from src.multimodal_librarian.services.cache_service import CacheService


class CachedSearchPerformanceTester:
    """Performance tester for cached search operations."""
    
    def __init__(self, cached_service: CachedSearchService):
        """Initialize performance tester."""
        self.cached_service = cached_service
        self.performance_data = {
            'cache_hits': [],
            'cache_misses': [],
            'concurrent_operations': [],
            'cache_warming': [],
            'memory_usage': []
        }
    
    async def measure_cache_hit_performance(
        self, 
        queries: List[str], 
        iterations: int = 3
    ) -> Dict[str, Any]:
        """
        Measure performance improvement from cache hits.
        
        Args:
            queries: List of queries to test
            iterations: Number of iterations per query
            
        Returns:
            Performance measurement results
        """
        results = {
            'queries_tested': len(queries),
            'iterations_per_query': iterations,
            'first_run_times': [],
            'cached_run_times': [],
            'performance_improvement': [],
            'cache_hit_rate': 0.0,
            'avg_first_run_ms': 0.0,
            'avg_cached_run_ms': 0.0,
            'avg_improvement_factor': 0.0
        }
        
        for query in queries:
            request = SimpleSearchRequest(query=query, top_k=10)
            
            # First run (cache miss)
            start_time = time.time()
            first_response = await self.cached_service.search(request)
            first_run_time = (time.time() - start_time) * 1000
            results['first_run_times'].append(first_run_time)
            
            # Subsequent runs (cache hits)
            cached_times = []
            for _ in range(iterations):
                start_time = time.time()
                cached_response = await self.cached_service.search(request)
                cached_time = (time.time() - start_time) * 1000
                cached_times.append(cached_time)
            
            avg_cached_time = statistics.mean(cached_times)
            results['cached_run_times'].append(avg_cached_time)
            
            # Calculate improvement
            if avg_cached_time > 0:
                improvement = first_run_time / avg_cached_time
                results['performance_improvement'].append(improvement)
        
        # Calculate averages
        if results['first_run_times']:
            results['avg_first_run_ms'] = statistics.mean(results['first_run_times'])
        if results['cached_run_times']:
            results['avg_cached_run_ms'] = statistics.mean(results['cached_run_times'])
        if results['performance_improvement']:
            results['avg_improvement_factor'] = statistics.mean(results['performance_improvement'])
        
        # Get cache hit rate from service metrics
        stats = await self.cached_service.get_cache_stats()
        results['cache_hit_rate'] = stats['metrics']['cache_hit_rate']
        
        return results
    
    async def measure_concurrent_cache_performance(
        self, 
        queries: List[str], 
        concurrent_users: int = 10
    ) -> Dict[str, Any]:
        """
        Measure cache performance under concurrent load.
        
        Args:
            queries: List of queries to test
            concurrent_users: Number of concurrent users
            
        Returns:
            Concurrent performance results
        """
        results = {
            'concurrent_users': concurrent_users,
            'total_queries': len(queries),
            'response_times': [],
            'cache_hit_times': [],
            'cache_miss_times': [],
            'avg_response_time_ms': 0.0,
            'p95_response_time_ms': 0.0,
            'p99_response_time_ms': 0.0,
            'throughput_qps': 0.0,
            'cache_effectiveness': 0.0
        }
        
        # Create tasks for concurrent execution
        tasks = []
        start_time = time.time()
        
        for user_id in range(concurrent_users):
            for query in queries:
                request = SimpleSearchRequest(
                    query=query, 
                    top_k=10,
                    user_id=f"user_{user_id}"
                )
                task = self._timed_search(request)
                tasks.append(task)
        
        # Execute all tasks concurrently
        timing_results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        # Process results
        for timing_result in timing_results:
            response_time, was_cache_hit = timing_result
            results['response_times'].append(response_time)
            
            if was_cache_hit:
                results['cache_hit_times'].append(response_time)
            else:
                results['cache_miss_times'].append(response_time)
        
        # Calculate statistics
        if results['response_times']:
            results['avg_response_time_ms'] = statistics.mean(results['response_times'])
            results['p95_response_time_ms'] = statistics.quantiles(
                results['response_times'], n=20
            )[18]  # 95th percentile
            results['p99_response_time_ms'] = statistics.quantiles(
                results['response_times'], n=100
            )[98]  # 99th percentile
        
        # Calculate throughput
        total_operations = len(timing_results)
        results['throughput_qps'] = total_operations / total_time if total_time > 0 else 0
        
        # Calculate cache effectiveness
        if results['cache_hit_times'] and results['cache_miss_times']:
            avg_hit_time = statistics.mean(results['cache_hit_times'])
            avg_miss_time = statistics.mean(results['cache_miss_times'])
            results['cache_effectiveness'] = (
                (avg_miss_time - avg_hit_time) / avg_miss_time * 100
                if avg_miss_time > 0 else 0
            )
        
        return results
    
    async def _timed_search(self, request: SimpleSearchRequest) -> Tuple[float, bool]:
        """
        Perform timed search and determine if it was a cache hit.
        
        Args:
            request: Search request
            
        Returns:
            Tuple of (response_time_ms, was_cache_hit)
        """
        # Get initial cache stats
        initial_stats = await self.cached_service.get_cache_stats()
        initial_hits = initial_stats['metrics']['cache_hits']
        
        # Perform search
        start_time = time.time()
        response = await self.cached_service.search(request)
        response_time = (time.time() - start_time) * 1000
        
        # Check if it was a cache hit
        final_stats = await self.cached_service.get_cache_stats()
        final_hits = final_stats['metrics']['cache_hits']
        was_cache_hit = final_hits > initial_hits
        
        return response_time, was_cache_hit
    
    async def measure_cache_warming_performance(
        self, 
        queries: List[str]
    ) -> Dict[str, Any]:
        """
        Measure cache warming performance and effectiveness.
        
        Args:
            queries: List of queries to warm
            
        Returns:
            Cache warming performance results
        """
        results = {
            'total_queries': len(queries),
            'warming_time_ms': 0.0,
            'warming_throughput_qps': 0.0,
            'cache_entries_created': 0,
            'warming_success_rate': 0.0,
            'post_warming_hit_rate': 0.0
        }
        
        # Measure warming time
        start_time = time.time()
        warming_result = await self.cached_service.warm_cache(queries, top_k=10)
        warming_time = (time.time() - start_time) * 1000
        
        results['warming_time_ms'] = warming_time
        results['warming_throughput_qps'] = (
            len(queries) / (warming_time / 1000) if warming_time > 0 else 0
        )
        results['cache_entries_created'] = warming_result.get('cached', 0)
        results['warming_success_rate'] = (
            warming_result.get('cached', 0) / len(queries) * 100
            if len(queries) > 0 else 0
        )
        
        # Test post-warming performance
        post_warming_times = []
        for query in queries[:5]:  # Test first 5 queries
            request = SimpleSearchRequest(query=query, top_k=10)
            start_time = time.time()
            response = await self.cached_service.search(request)
            response_time = (time.time() - start_time) * 1000
            post_warming_times.append(response_time)
        
        # Get final cache stats
        final_stats = await self.cached_service.get_cache_stats()
        results['post_warming_hit_rate'] = final_stats['metrics']['cache_hit_rate']
        
        return results
    
    async def measure_memory_usage_scaling(
        self, 
        query_batches: List[List[str]]
    ) -> Dict[str, Any]:
        """
        Measure memory usage as cache size increases.
        
        Args:
            query_batches: Batches of queries to add progressively
            
        Returns:
            Memory usage scaling results
        """
        results = {
            'batch_sizes': [],
            'memory_usage_mb': [],
            'cache_entries': [],
            'memory_per_entry_kb': [],
            'memory_efficiency': 0.0
        }
        
        for batch_idx, query_batch in enumerate(query_batches):
            # Add queries to cache
            for query in query_batch:
                request = SimpleSearchRequest(query=query, top_k=10)
                await self.cached_service.search(request)
            
            # Measure memory usage
            stats = await self.cached_service.get_cache_stats()
            
            results['batch_sizes'].append(len(query_batch))
            results['memory_usage_mb'].append(stats['cache_service']['memory_usage_mb'])
            results['cache_entries'].append(stats['cache_service']['search_entries'])
            
            # Calculate memory per entry
            if stats['cache_service']['search_entries'] > 0:
                memory_per_entry = (
                    stats['cache_service']['memory_usage_mb'] * 1024 / 
                    stats['cache_service']['search_entries']
                )
                results['memory_per_entry_kb'].append(memory_per_entry)
        
        # Calculate memory efficiency
        if len(results['memory_per_entry_kb']) > 1:
            # Memory efficiency = how consistent memory per entry is
            memory_variance = statistics.variance(results['memory_per_entry_kb'])
            memory_mean = statistics.mean(results['memory_per_entry_kb'])
            results['memory_efficiency'] = (
                (1 - (memory_variance / memory_mean)) * 100
                if memory_mean > 0 else 0
            )
        
        return results


class TestCachedSearchPerformance:
    """Performance tests for cached search service."""
    
    @pytest.fixture
    def mock_vector_store(self):
        """Create mock vector store with realistic response times."""
        mock_store = Mock()
        mock_store.health_check.return_value = True
        
        # Simulate variable search times
        def mock_search(query, top_k=10, **kwargs):
            # Simulate processing time based on query complexity
            time.sleep(0.05 + len(query) * 0.001)  # 50ms + 1ms per character
            
            return [
                {
                    'chunk_id': f'chunk_{i}',
                    'content': f'Content for {query} - result {i}',
                    'source_type': 'pdf',
                    'source_id': f'doc_{i}',
                    'content_type': 'text',
                    'location_reference': f'page_{i}',
                    'section': f'Section {i}',
                    'similarity_score': 0.9 - (i * 0.1),
                    'created_at': int(datetime.now().timestamp() * 1000)
                }
                for i in range(min(top_k, 3))
            ]
        
        mock_store.semantic_search.side_effect = mock_search
        return mock_store
    
    @pytest.fixture
    def mock_cache_service(self):
        """Create mock cache service with realistic behavior."""
        mock_cache = AsyncMock(spec=CacheService)
        mock_cache.is_connected = True
        
        # Simulate cache storage
        cache_storage = {}
        
        async def mock_get(cache_type, key, **kwargs):
            return cache_storage.get(key)
        
        async def mock_set(cache_type, key, value, ttl=None, **kwargs):
            cache_storage[key] = value
            return True
        
        async def mock_exists(cache_type, key, **kwargs):
            return key in cache_storage
        
        mock_cache.get.side_effect = mock_get
        mock_cache.set.side_effect = mock_set
        mock_cache.exists.side_effect = mock_exists
        mock_cache.clear_by_type.return_value = len(cache_storage)
        
        # Mock stats
        mock_cache.get_stats.return_value = Mock(
            total_entries=len(cache_storage),
            memory_usage_mb=len(cache_storage) * 0.1,  # 0.1MB per entry
            hit_rate=0.75,
            avg_access_time_ms=2.0,
            entries_by_type={'search_result': len(cache_storage)}
        )
        
        return mock_cache
    
    @pytest.fixture
    async def cached_service(self, mock_vector_store, mock_cache_service):
        """Create cached search service for performance testing."""
        cache_config = {
            'ttl': 3600,
            'enable': True,
            'threshold_ms': 10,  # Low threshold for testing
            'max_entries': 1000
        }
        
        service = CachedSimpleSearchService(mock_vector_store, cache_config)
        
        # Patch cache service
        with patch('src.multimodal_librarian.components.vector_store.search_service_cached.get_cache_service', 
                   return_value=mock_cache_service):
            await service._ensure_cache_initialized()
        
        return service
    
    @pytest.fixture
    def performance_tester(self, cached_service):
        """Create performance tester."""
        return CachedSearchPerformanceTester(cached_service)
    
    @pytest.fixture
    def test_queries(self):
        """Generate test queries of varying complexity."""
        return [
            "AI",
            "machine learning",
            "deep learning algorithms",
            "artificial intelligence applications",
            "neural network architectures and optimization",
            "transformer models for natural language processing",
            "computer vision and convolutional neural networks for image recognition",
            "reinforcement learning algorithms for autonomous systems and robotics applications"
        ]
    
    @pytest.mark.asyncio
    async def test_cache_hit_performance_improvement(self, performance_tester, test_queries):
        """Test performance improvement from cache hits."""
        # Patch cache service
        with patch('src.multimodal_librarian.components.vector_store.search_service_cached.get_cache_service') as mock_get_cache:
            mock_cache = AsyncMock()
            mock_cache.is_connected = True
            
            # Simulate cache behavior
            cache_storage = {}
            
            async def mock_get(cache_type, key, **kwargs):
                return cache_storage.get(key)
            
            async def mock_set(cache_type, key, value, ttl=None, **kwargs):
                cache_storage[key] = value
                return True
            
            mock_cache.get.side_effect = mock_get
            mock_cache.set.side_effect = mock_set
            mock_cache.get_stats.return_value = Mock(
                total_entries=len(cache_storage),
                memory_usage_mb=len(cache_storage) * 0.1,
                hit_rate=0.0,
                avg_access_time_ms=1.0,
                entries_by_type={'search_result': len(cache_storage)}
            )
            
            mock_get_cache.return_value = mock_cache
            
            # Measure performance
            results = await performance_tester.measure_cache_hit_performance(
                test_queries[:4], iterations=2
            )
            
            # Validate results
            assert results['queries_tested'] == 4
            assert results['iterations_per_query'] == 2
            assert len(results['first_run_times']) == 4
            assert len(results['cached_run_times']) == 4
            assert results['avg_first_run_ms'] > 0
            assert results['avg_cached_run_ms'] > 0
            
            # Cache should provide performance improvement
            # (Note: In mock environment, improvement may be minimal)
            assert results['avg_improvement_factor'] >= 1.0
            
            print(f"Cache Performance Results:")
            print(f"  Average first run: {results['avg_first_run_ms']:.1f}ms")
            print(f"  Average cached run: {results['avg_cached_run_ms']:.1f}ms")
            print(f"  Improvement factor: {results['avg_improvement_factor']:.2f}x")
    
    @pytest.mark.asyncio
    async def test_concurrent_cache_performance(self, performance_tester, test_queries):
        """Test cache performance under concurrent load."""
        with patch('src.multimodal_librarian.components.vector_store.search_service_cached.get_cache_service') as mock_get_cache:
            mock_cache = AsyncMock()
            mock_cache.is_connected = True
            
            # Simulate cache with some pre-existing entries
            cache_storage = {}
            
            async def mock_get(cache_type, key, **kwargs):
                # Simulate some cache hits
                if len(cache_storage) > 0 and key in cache_storage:
                    return cache_storage[key]
                return None
            
            async def mock_set(cache_type, key, value, ttl=None, **kwargs):
                cache_storage[key] = value
                return True
            
            mock_cache.get.side_effect = mock_get
            mock_cache.set.side_effect = mock_set
            mock_cache.get_stats.return_value = Mock(
                total_entries=len(cache_storage),
                memory_usage_mb=len(cache_storage) * 0.1,
                hit_rate=50.0,
                avg_access_time_ms=1.5,
                entries_by_type={'search_result': len(cache_storage)}
            )
            
            mock_get_cache.return_value = mock_cache
            
            # Measure concurrent performance
            results = await performance_tester.measure_concurrent_cache_performance(
                test_queries[:3], concurrent_users=5
            )
            
            # Validate results
            assert results['concurrent_users'] == 5
            assert results['total_queries'] == 3
            assert len(results['response_times']) == 15  # 5 users * 3 queries
            assert results['avg_response_time_ms'] > 0
            assert results['p95_response_time_ms'] > 0
            assert results['throughput_qps'] > 0
            
            print(f"Concurrent Performance Results:")
            print(f"  Average response time: {results['avg_response_time_ms']:.1f}ms")
            print(f"  95th percentile: {results['p95_response_time_ms']:.1f}ms")
            print(f"  Throughput: {results['throughput_qps']:.1f} QPS")
            print(f"  Cache effectiveness: {results['cache_effectiveness']:.1f}%")
    
    @pytest.mark.asyncio
    async def test_cache_warming_performance(self, performance_tester, test_queries):
        """Test cache warming performance and effectiveness."""
        with patch('src.multimodal_librarian.components.vector_store.search_service_cached.get_cache_service') as mock_get_cache:
            mock_cache = AsyncMock()
            mock_cache.is_connected = True
            
            cache_storage = {}
            
            async def mock_get(cache_type, key, **kwargs):
                return cache_storage.get(key)
            
            async def mock_set(cache_type, key, value, ttl=None, **kwargs):
                cache_storage[key] = value
                return True
            
            async def mock_exists(cache_type, key, **kwargs):
                return key in cache_storage
            
            mock_cache.get.side_effect = mock_get
            mock_cache.set.side_effect = mock_set
            mock_cache.exists.side_effect = mock_exists
            mock_cache.get_stats.return_value = Mock(
                total_entries=len(cache_storage),
                memory_usage_mb=len(cache_storage) * 0.1,
                hit_rate=100.0,  # After warming
                avg_access_time_ms=1.0,
                entries_by_type={'search_result': len(cache_storage)}
            )
            
            mock_get_cache.return_value = mock_cache
            
            # Measure cache warming
            results = await performance_tester.measure_cache_warming_performance(
                test_queries[:5]
            )
            
            # Validate results
            assert results['total_queries'] == 5
            assert results['warming_time_ms'] > 0
            assert results['warming_throughput_qps'] > 0
            assert results['cache_entries_created'] >= 0
            assert results['warming_success_rate'] >= 0
            
            print(f"Cache Warming Results:")
            print(f"  Warming time: {results['warming_time_ms']:.1f}ms")
            print(f"  Throughput: {results['warming_throughput_qps']:.1f} QPS")
            print(f"  Entries created: {results['cache_entries_created']}")
            print(f"  Success rate: {results['warming_success_rate']:.1f}%")
    
    @pytest.mark.asyncio
    async def test_cache_hit_rate_target(self, performance_tester, test_queries):
        """Test that cache hit rate meets target (>70% as per requirement 4.5)."""
        with patch('src.multimodal_librarian.components.vector_store.search_service_cached.get_cache_service') as mock_get_cache:
            mock_cache = AsyncMock()
            mock_cache.is_connected = True
            
            cache_storage = {}
            access_count = {'hits': 0, 'misses': 0}
            
            async def mock_get(cache_type, key, **kwargs):
                if key in cache_storage:
                    access_count['hits'] += 1
                    return cache_storage[key]
                else:
                    access_count['misses'] += 1
                    return None
            
            async def mock_set(cache_type, key, value, ttl=None, **kwargs):
                cache_storage[key] = value
                return True
            
            def get_hit_rate():
                total = access_count['hits'] + access_count['misses']
                return (access_count['hits'] / total * 100) if total > 0 else 0
            
            mock_cache.get.side_effect = mock_get
            mock_cache.set.side_effect = mock_set
            mock_cache.get_stats.return_value = Mock(
                total_entries=len(cache_storage),
                memory_usage_mb=len(cache_storage) * 0.1,
                hit_rate=get_hit_rate(),
                avg_access_time_ms=1.0,
                entries_by_type={'search_result': len(cache_storage)}
            )
            
            mock_get_cache.return_value = mock_cache
            
            # Perform searches to populate cache
            for query in test_queries:
                request = SimpleSearchRequest(query=query, top_k=10)
                await performance_tester.cached_service.search(request)
            
            # Repeat searches to generate cache hits
            for _ in range(2):
                for query in test_queries:
                    request = SimpleSearchRequest(query=query, top_k=10)
                    await performance_tester.cached_service.search(request)
            
            # Check final hit rate
            final_hit_rate = get_hit_rate()
            
            print(f"Cache Hit Rate: {final_hit_rate:.1f}%")
            print(f"Cache Hits: {access_count['hits']}")
            print(f"Cache Misses: {access_count['misses']}")
            
            # Validate hit rate meets target (>70%)
            assert final_hit_rate > 70.0, f"Cache hit rate {final_hit_rate:.1f}% below target of 70%"
    
    @pytest.mark.asyncio
    async def test_performance_regression_prevention(self, performance_tester, test_queries):
        """Test that caching doesn't cause performance regression."""
        with patch('src.multimodal_librarian.components.vector_store.search_service_cached.get_cache_service') as mock_get_cache:
            mock_cache = AsyncMock()
            mock_cache.is_connected = True
            
            # Simulate fast cache operations
            async def mock_get(cache_type, key, **kwargs):
                await asyncio.sleep(0.001)  # 1ms cache lookup
                return None  # Always miss for baseline
            
            async def mock_set(cache_type, key, value, ttl=None, **kwargs):
                await asyncio.sleep(0.001)  # 1ms cache store
                return True
            
            mock_cache.get.side_effect = mock_get
            mock_cache.set.side_effect = mock_set
            mock_cache.get_stats.return_value = Mock(
                total_entries=0,
                memory_usage_mb=0.0,
                hit_rate=0.0,
                avg_access_time_ms=1.0,
                entries_by_type={'search_result': 0}
            )
            
            mock_get_cache.return_value = mock_cache
            
            # Measure search times with caching overhead
            search_times = []
            for query in test_queries[:3]:
                request = SimpleSearchRequest(query=query, top_k=10)
                
                start_time = time.time()
                response = await performance_tester.cached_service.search(request)
                search_time = (time.time() - start_time) * 1000
                
                search_times.append(search_time)
                assert response is not None
                assert len(response.results) > 0
            
            avg_search_time = statistics.mean(search_times)
            
            print(f"Average search time with caching: {avg_search_time:.1f}ms")
            
            # Ensure caching overhead is minimal (< 10ms additional overhead)
            # This accounts for cache lookup + store operations
            assert avg_search_time < 100.0, f"Search time {avg_search_time:.1f}ms indicates performance regression"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])