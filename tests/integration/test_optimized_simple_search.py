"""
Integration tests for optimized simple search service.

Tests the performance optimizations including caching, enhanced relevance scoring,
and fallback-specific optimizations.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, MagicMock
from datetime import datetime, timedelta
from typing import List, Dict, Any

from src.multimodal_librarian.components.vector_store.search_service_simple import (
    OptimizedSimpleSemanticSearchService,
    SimpleSearchRequest,
    SimpleSearchResponse,
    SimpleSearchResult,
    QueryCacheEntry,
    SearchPerformanceMetrics
)
from src.multimodal_librarian.models.core import SourceType, ContentType


class MockVectorStore:
    """Mock vector store for testing."""
    
    def __init__(self, response_delay_ms: float = 50):
        self.response_delay_ms = response_delay_ms
        self.search_call_count = 0
        self.last_query = None
        
    def semantic_search(self, query: str, top_k: int = 10, **kwargs) -> List[Dict[str, Any]]:
        """Mock semantic search with configurable delay."""
        self.search_call_count += 1
        self.last_query = query
        
        # Simulate processing time
        time.sleep(self.response_delay_ms / 1000)
        
        # Return mock results
        results = []
        for i in range(min(top_k, 5)):  # Return up to 5 results
            results.append({
                'chunk_id': f'chunk_{i}_{hash(query) % 1000}',
                'content': f'Mock content for {query} - result {i}',
                'source_type': SourceType.BOOK.value,  # Use correct enum value
                'source_id': f'doc_{i}',
                'content_type': ContentType.GENERAL.value,  # Use correct enum value
                'location_reference': f'page_{i}',
                'section': f'section_{i}',
                'similarity_score': 0.9 - (i * 0.1),  # Decreasing similarity
                'created_at': int(datetime.now().timestamp() * 1000)
            })
        
        return results
    
    def health_check(self) -> bool:
        """Mock health check."""
        return True


@pytest.fixture
def mock_vector_store():
    """Create mock vector store."""
    return MockVectorStore()


@pytest.fixture
def optimized_search_service(mock_vector_store):
    """Create optimized search service with mock vector store."""
    return OptimizedSimpleSemanticSearchService(mock_vector_store, cache_size=100)


class TestOptimizedSimpleSearchService:
    """Test optimized simple search service functionality."""
    
    @pytest.mark.asyncio
    async def test_basic_search_functionality(self, optimized_search_service):
        """Test basic search functionality works."""
        request = SimpleSearchRequest(
            query="test query",
            top_k=3
        )
        
        response = await optimized_search_service.search(request)
        
        assert isinstance(response, SimpleSearchResponse)
        assert len(response.results) <= 3
        assert response.total_results == len(response.results)
        assert response.search_time_ms > 0
        assert response.fallback_mode is True
        assert response.session_id == request.session_id
    
    @pytest.mark.asyncio
    async def test_caching_functionality(self, optimized_search_service, mock_vector_store):
        """Test that caching reduces vector store calls."""
        request = SimpleSearchRequest(
            query="cached query test",
            top_k=5,
            enable_caching=True
        )
        
        # First search - should hit vector store
        response1 = await optimized_search_service.search(request)
        first_call_count = mock_vector_store.search_call_count
        
        assert response1.cache_hit is False
        assert len(response1.results) > 0
        
        # Second search with same query - should hit cache
        response2 = await optimized_search_service.search(request)
        second_call_count = mock_vector_store.search_call_count
        
        assert response2.cache_hit is True
        assert second_call_count == first_call_count  # No additional vector store call
        assert len(response2.results) == len(response1.results)
        assert response2.search_time_ms < response1.search_time_ms  # Cache should be faster
    
    @pytest.mark.asyncio
    async def test_cache_disabled(self, optimized_search_service, mock_vector_store):
        """Test search with caching disabled."""
        request = SimpleSearchRequest(
            query="no cache query",
            top_k=3,
            enable_caching=False
        )
        
        # First search
        response1 = await optimized_search_service.search(request)
        first_call_count = mock_vector_store.search_call_count
        
        # Second search - should hit vector store again
        response2 = await optimized_search_service.search(request)
        second_call_count = mock_vector_store.search_call_count
        
        assert response1.cache_hit is False
        assert response2.cache_hit is False
        assert second_call_count > first_call_count  # Additional vector store call
    
    @pytest.mark.asyncio
    async def test_enhanced_relevance_scoring(self, optimized_search_service):
        """Test enhanced relevance scoring with keyword matching."""
        request = SimpleSearchRequest(
            query="machine learning algorithms",
            top_k=5,
            enable_reranking=True
        )
        
        response = await optimized_search_service.search(request)
        
        assert response.optimization_applied is True
        assert len(response.results) > 0
        
        # Check that results have enhanced relevance scores
        for result in response.results:
            assert hasattr(result, 'relevance_score')
            assert result.relevance_score >= 0
            assert result.relevance_score <= 1.0
    
    @pytest.mark.asyncio
    async def test_similarity_threshold_filtering(self, optimized_search_service):
        """Test filtering by similarity threshold."""
        request = SimpleSearchRequest(
            query="threshold test",
            top_k=10,
            similarity_threshold=0.8,  # High threshold
            enable_reranking=True
        )
        
        response = await optimized_search_service.search(request)
        
        # All results should meet the similarity threshold
        for result in response.results:
            assert result.similarity_score >= request.similarity_threshold
    
    @pytest.mark.asyncio
    async def test_performance_metrics_tracking(self, optimized_search_service):
        """Test that performance metrics are tracked correctly."""
        initial_stats = optimized_search_service.get_performance_stats()
        initial_searches = initial_stats['performance']['total_searches']
        
        # Perform several searches
        for i in range(3):
            request = SimpleSearchRequest(
                query=f"metrics test {i}",
                top_k=3
            )
            await optimized_search_service.search(request)
        
        final_stats = optimized_search_service.get_performance_stats()
        
        assert final_stats['performance']['total_searches'] == initial_searches + 3
        assert final_stats['performance']['avg_response_time_ms'] > 0
        assert final_stats['performance']['fallback_usage_count'] > 0
    
    @pytest.mark.asyncio
    async def test_cache_statistics(self, optimized_search_service):
        """Test cache statistics reporting."""
        # Perform searches to populate cache
        for i in range(5):
            request = SimpleSearchRequest(
                query=f"cache stats test {i}",
                top_k=3,
                enable_caching=True
            )
            await optimized_search_service.search(request)
        
        cache_stats = optimized_search_service.get_cache_statistics()
        
        assert 'total_entries' in cache_stats
        assert 'cache_hit_rate' in cache_stats
        assert 'cache_utilization' in cache_stats
        assert cache_stats['total_entries'] > 0
    
    @pytest.mark.asyncio
    async def test_cache_cleanup(self, optimized_search_service):
        """Test cache cleanup functionality."""
        # Add entries to cache
        for i in range(10):
            request = SimpleSearchRequest(
                query=f"cleanup test {i}",
                top_k=3,
                enable_caching=True
            )
            await optimized_search_service.search(request)
        
        initial_cache_size = len(optimized_search_service.query_cache)
        assert initial_cache_size > 0
        
        # Clear cache
        optimized_search_service.clear_cache()
        
        final_cache_size = len(optimized_search_service.query_cache)
        assert final_cache_size == 0
    
    @pytest.mark.asyncio
    async def test_health_check_enhanced(self, optimized_search_service):
        """Test enhanced health check functionality."""
        # Perform some searches to generate metrics
        for i in range(3):
            request = SimpleSearchRequest(
                query=f"health test {i}",
                top_k=3
            )
            await optimized_search_service.search(request)
        
        health_status = optimized_search_service.health_check()
        
        assert isinstance(health_status, dict)
        assert 'healthy' in health_status
        assert 'performance_score' in health_status
        assert 'cache_hit_rate' in health_status
        assert 'service_type' in health_status
        assert health_status['service_type'] == 'optimized_simple_search'
    
    @pytest.mark.asyncio
    async def test_concurrent_search_performance(self, optimized_search_service):
        """Test performance under concurrent load."""
        async def perform_search(query_id: int):
            request = SimpleSearchRequest(
                query=f"concurrent test {query_id}",
                top_k=3
            )
            return await optimized_search_service.search(request)
        
        # Perform concurrent searches
        start_time = time.time()
        tasks = [perform_search(i) for i in range(10)]
        responses = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        # Verify all searches completed successfully
        assert len(responses) == 10
        for response in responses:
            assert isinstance(response, SimpleSearchResponse)
            assert len(response.results) >= 0
        
        # Check that concurrent performance is reasonable
        avg_time_per_search = total_time / 10
        assert avg_time_per_search < 1.0  # Should be under 1 second per search
    
    @pytest.mark.asyncio
    async def test_error_handling(self, optimized_search_service):
        """Test error handling in search operations."""
        # Mock vector store to raise exception
        optimized_search_service.vector_store.semantic_search = Mock(
            side_effect=Exception("Mock vector store error")
        )
        
        request = SimpleSearchRequest(
            query="error test",
            top_k=3
        )
        
        response = await optimized_search_service.search(request)
        
        # Should return empty response without crashing
        assert isinstance(response, SimpleSearchResponse)
        assert len(response.results) == 0
        assert response.search_time_ms > 0
        assert response.fallback_mode is True
    
    def test_query_cache_entry_expiration(self):
        """Test query cache entry expiration logic."""
        entry = QueryCacheEntry(
            query_hash="test_hash",
            results=[],
            created_at=datetime.now()
        )
        
        # Should not be expired immediately
        assert not entry.is_expired(ttl_seconds=3600)
        
        # Mock old creation time
        entry.created_at = datetime.now() - timedelta(seconds=7200)  # 2 hours ago
        
        # Should be expired with 1 hour TTL
        assert entry.is_expired(ttl_seconds=3600)
    
    def test_search_performance_metrics(self):
        """Test search performance metrics calculations."""
        metrics = SearchPerformanceMetrics()
        
        # Test initial state
        assert metrics.get_cache_hit_rate() == 0.0
        assert metrics.get_performance_score() >= 0.0  # Can be > 0 due to time score calculation
        
        # Add some metrics
        metrics.cache_hits = 7
        metrics.cache_misses = 3
        metrics.avg_response_time_ms = 200
        
        # Test calculations
        assert metrics.get_cache_hit_rate() == 0.7  # 70%
        assert metrics.get_performance_score() > 0


if __name__ == "__main__":
    pytest.main([__file__])