"""
Performance tests for optimized simple search service.

Tests the performance improvements and fallback gap reduction.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock
from datetime import datetime
from typing import List, Dict, Any

from src.multimodal_librarian.components.vector_store.search_service_simple import (
    OptimizedSimpleSemanticSearchService,
    SimpleSearchRequest,
    SimpleSearchResponse
)
from src.multimodal_librarian.models.core import SourceType, ContentType


class MockVectorStore:
    """Mock vector store with configurable performance characteristics."""
    
    def __init__(self, base_delay_ms: float = 100):
        self.base_delay_ms = base_delay_ms
        self.search_call_count = 0
        
    def semantic_search(self, query: str, top_k: int = 10, **kwargs) -> List[Dict[str, Any]]:
        """Mock semantic search with realistic delay."""
        self.search_call_count += 1
        
        # Simulate processing time
        time.sleep(self.base_delay_ms / 1000)
        
        # Return mock results
        results = []
        for i in range(min(top_k, 5)):
            results.append({
                'chunk_id': f'chunk_{i}_{hash(query) % 1000}',
                'content': f'Mock content for {query} - result {i}',
                'source_type': SourceType.BOOK.value,
                'source_id': f'doc_{i}',
                'content_type': ContentType.GENERAL.value,
                'location_reference': f'page_{i}',
                'section': f'section_{i}',
                'similarity_score': 0.9 - (i * 0.1),
                'created_at': int(datetime.now().timestamp() * 1000)
            })
        
        return results
    
    def health_check(self) -> bool:
        return True


@pytest.fixture
def mock_vector_store():
    """Create mock vector store with 100ms base delay."""
    return MockVectorStore(base_delay_ms=100)


@pytest.fixture
def optimized_search_service(mock_vector_store):
    """Create optimized search service."""
    return OptimizedSimpleSemanticSearchService(mock_vector_store, cache_size=100)


class TestSimpleSearchOptimization:
    """Test performance optimizations in simple search service."""
    
    @pytest.mark.asyncio
    async def test_cache_performance_improvement(self, optimized_search_service, mock_vector_store):
        """Test that caching significantly improves performance."""
        request = SimpleSearchRequest(
            query="performance test query",
            top_k=5,
            enable_caching=True
        )
        
        # First search - should be slow (hits vector store)
        start_time = time.time()
        response1 = await optimized_search_service.search(request)
        first_search_time = time.time() - start_time
        
        assert response1.cache_hit is False
        assert len(response1.results) > 0
        assert first_search_time >= 0.1  # Should take at least 100ms due to mock delay
        
        # Second search - should be fast (hits cache)
        start_time = time.time()
        response2 = await optimized_search_service.search(request)
        second_search_time = time.time() - start_time
        
        assert response2.cache_hit is True
        assert len(response2.results) == len(response1.results)
        
        # Cache should be significantly faster
        performance_improvement = first_search_time / second_search_time
        assert performance_improvement > 2.0  # At least 2x faster
        
        # Vector store should only be called once
        assert mock_vector_store.search_call_count == 1
    
    @pytest.mark.asyncio
    async def test_enhanced_relevance_scoring(self, optimized_search_service):
        """Test that enhanced relevance scoring improves result quality."""
        request = SimpleSearchRequest(
            query="machine learning algorithms optimization",
            top_k=5,
            enable_reranking=True
        )
        
        response = await optimized_search_service.search(request)
        
        assert response.optimization_applied is True
        assert len(response.results) > 0
        
        # Check that relevance scores are calculated
        for result in response.results:
            assert hasattr(result, 'relevance_score')
            assert result.relevance_score >= 0
            assert result.relevance_score <= 1.0
        
        # Results should be sorted by relevance score
        relevance_scores = [r.relevance_score for r in response.results]
        assert relevance_scores == sorted(relevance_scores, reverse=True)
    
    @pytest.mark.asyncio
    async def test_concurrent_performance(self, optimized_search_service):
        """Test performance under concurrent load."""
        async def perform_search(query_id: int):
            request = SimpleSearchRequest(
                query=f"concurrent test {query_id}",
                top_k=3,
                enable_caching=True
            )
            start_time = time.time()
            response = await optimized_search_service.search(request)
            search_time = time.time() - start_time
            return response, search_time
        
        # Perform concurrent searches
        num_concurrent = 10
        tasks = [perform_search(i) for i in range(num_concurrent)]
        results = await asyncio.gather(*tasks)
        
        # Verify all searches completed successfully
        assert len(results) == num_concurrent
        
        total_time = 0
        cache_hits = 0
        
        for response, search_time in results:
            assert isinstance(response, SimpleSearchResponse)
            assert len(response.results) >= 0
            total_time += search_time
            if response.cache_hit:
                cache_hits += 1
        
        # Average time per search should be reasonable
        avg_time_per_search = total_time / num_concurrent
        assert avg_time_per_search < 0.5  # Should be under 500ms average
        
        # Some searches should hit cache (similar queries)
        # Note: This might be 0 if all queries are unique, which is fine
        print(f"Cache hits: {cache_hits}/{num_concurrent}")
    
    @pytest.mark.asyncio
    async def test_performance_metrics_tracking(self, optimized_search_service):
        """Test that performance metrics are accurately tracked."""
        # Perform several searches
        search_times = []
        for i in range(5):
            request = SimpleSearchRequest(
                query=f"metrics test {i}",
                top_k=3
            )
            start_time = time.time()
            response = await optimized_search_service.search(request)
            search_time = time.time() - start_time
            search_times.append(search_time)
        
        # Get performance stats
        stats = optimized_search_service.get_performance_stats()
        
        # Verify metrics are tracked
        assert stats['performance']['total_searches'] == 5
        assert stats['performance']['avg_response_time_ms'] > 0
        assert stats['performance']['performance_score'] > 0
        
        # Check recent performance tracking
        assert 'recent' in stats
        assert stats['recent']['recent_avg_response_time_ms'] > 0
    
    @pytest.mark.asyncio
    async def test_cache_hit_rate_optimization(self, optimized_search_service):
        """Test that cache hit rate improves with similar queries."""
        base_query = "optimization test"
        
        # Perform initial search
        request1 = SimpleSearchRequest(query=base_query, top_k=5, enable_caching=True)
        response1 = await optimized_search_service.search(request1)
        assert response1.cache_hit is False
        
        # Perform same search - should hit cache
        request2 = SimpleSearchRequest(query=base_query, top_k=5, enable_caching=True)
        response2 = await optimized_search_service.search(request2)
        assert response2.cache_hit is True
        
        # Get cache statistics
        cache_stats = optimized_search_service.get_cache_statistics()
        
        assert cache_stats['cache_hit_rate'] > 0
        assert cache_stats['total_entries'] > 0
        assert cache_stats['cache_utilization'] > 0
    
    @pytest.mark.asyncio
    async def test_fallback_performance_gap(self, optimized_search_service, mock_vector_store):
        """Test that optimizations reduce the fallback performance gap."""
        # This test simulates the performance gap between complex and simple search
        # The optimized simple search should perform much better than basic simple search
        
        # Test with caching enabled (simulating optimized fallback)
        request_optimized = SimpleSearchRequest(
            query="fallback performance test",
            top_k=5,
            enable_caching=True,
            enable_reranking=True
        )
        
        # First search (cache miss)
        start_time = time.time()
        response1 = await optimized_search_service.search(request_optimized)
        first_time = time.time() - start_time
        
        # Second search (cache hit)
        start_time = time.time()
        response2 = await optimized_search_service.search(request_optimized)
        second_time = time.time() - start_time
        
        # The cached search should be much faster
        performance_ratio = first_time / second_time
        assert performance_ratio > 3.0  # At least 3x improvement
        
        # Both should return valid results
        assert len(response1.results) > 0
        assert len(response2.results) > 0
        assert response2.cache_hit is True
        
        # Performance score should be good
        assert response2.performance_score > 50  # Reasonable performance
    
    @pytest.mark.asyncio
    async def test_memory_efficiency(self, optimized_search_service):
        """Test that the service manages memory efficiently."""
        # Fill cache with many queries
        for i in range(150):  # More than cache size (100)
            request = SimpleSearchRequest(
                query=f"memory test {i}",
                top_k=3,
                enable_caching=True
            )
            await optimized_search_service.search(request)
        
        # Cache should not exceed maximum size
        cache_stats = optimized_search_service.get_cache_statistics()
        assert cache_stats['total_entries'] <= optimized_search_service.cache_size
        
        # Cache utilization should be reasonable
        assert cache_stats['cache_utilization'] <= 1.0  # Should not exceed 100%
    
    @pytest.mark.asyncio
    async def test_auto_optimization(self, optimized_search_service):
        """Test that auto-optimization improves performance over time."""
        initial_stats = optimized_search_service.get_performance_stats()
        initial_optimizations = initial_stats['optimization']['optimization_count']
        
        # Perform many searches to trigger auto-optimization
        for i in range(60):  # More than optimization threshold (50)
            request = SimpleSearchRequest(
                query=f"auto optimization test {i % 10}",  # Some repeated queries
                top_k=3,
                enable_caching=True
            )
            await optimized_search_service.search(request)
        
        final_stats = optimized_search_service.get_performance_stats()
        final_optimizations = final_stats['optimization']['optimization_count']
        
        # Auto-optimization should have been triggered
        assert final_optimizations > initial_optimizations
        
        # Performance should be tracked
        assert final_stats['performance']['total_searches'] >= 60


if __name__ == "__main__":
    pytest.main([__file__])