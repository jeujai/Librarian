"""
Integration tests for cached search service functionality.

Tests the integration between search services and caching layer,
validating cache hit rates, performance improvements, and cache invalidation.
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from typing import List, Dict, Any

# Import the cached search service and dependencies
from src.multimodal_librarian.components.vector_store.search_service_cached import (
    CachedSearchService,
    CachedSimpleSearchService,
    CachedEnhancedSearchService,
    CachedSearchResult,
    CacheMetrics,
    create_cached_search_service
)
from src.multimodal_librarian.components.vector_store.search_service_simple import (
    SimpleSemanticSearchService,
    SimpleSearchRequest,
    SimpleSearchResponse,
    SimpleSearchResult
)
from src.multimodal_librarian.models.core import SourceType, ContentType
from src.multimodal_librarian.models.search_types import SearchResult
from src.multimodal_librarian.services.cache_service import CacheService, CacheType


class TestCachedSearchIntegration:
    """Test cached search service integration."""
    
    @pytest.fixture
    def mock_vector_store(self):
        """Create mock vector store."""
        mock_store = Mock()
        mock_store.health_check.return_value = True
        mock_store.semantic_search.return_value = [
            {
                'chunk_id': 'chunk_1',
                'content': 'Test content about machine learning',
                'source_type': SourceType.BOOK.value,
                'source_id': 'doc_1',
                'content_type': ContentType.GENERAL.value,
                'location_reference': 'page_1',
                'section': 'Introduction',
                'similarity_score': 0.95,
                'created_at': int(datetime.now().timestamp() * 1000)
            },
            {
                'chunk_id': 'chunk_2',
                'content': 'Advanced ML algorithms and techniques',
                'source_type': SourceType.BOOK.value,
                'source_id': 'doc_1',
                'content_type': ContentType.GENERAL.value,
                'location_reference': 'page_2',
                'section': 'Methods',
                'similarity_score': 0.87,
                'created_at': int(datetime.now().timestamp() * 1000)
            }
        ]
        return mock_store
    
    @pytest.fixture
    def mock_cache_service(self):
        """Create mock cache service."""
        mock_cache = AsyncMock(spec=CacheService)
        mock_cache.is_connected = True
        mock_cache.get.return_value = None  # Default to cache miss
        mock_cache.set.return_value = True
        mock_cache.delete.return_value = True
        mock_cache.exists.return_value = False
        mock_cache.clear_by_type.return_value = 5
        mock_cache.get_stats.return_value = Mock(
            total_entries=100,
            memory_usage_mb=10.5,
            hit_rate=0.75,
            avg_access_time_ms=2.3,
            entries_by_type={'search_result': 25}
        )
        return mock_cache
    
    @pytest.fixture
    def cache_config(self):
        """Cache configuration for testing."""
        return {
            'ttl': 1800,  # 30 minutes
            'enable': True,
            'threshold_ms': 50,
            'max_entries': 1000,
            'invalidation_hours': 12
        }
    
    @pytest.fixture
    def cached_search_service(self, mock_vector_store, cache_config):
        """Create cached search service for testing."""
        service = CachedSimpleSearchService(mock_vector_store, cache_config)
        return service
    
    @pytest.mark.asyncio
    async def test_cached_service_initialization(self, mock_vector_store, cache_config):
        """Test cached search service initialization."""
        service = CachedSimpleSearchService(mock_vector_store, cache_config)
        
        assert service.search_service is not None
        assert service.cache_ttl == 1800
        assert service.enable_cache is True
        assert service.cache_threshold_ms == 50
        assert service.max_cache_entries == 1000
        assert isinstance(service.metrics, CacheMetrics)
        assert service.metrics.total_searches == 0
        assert service.metrics.cache_hits == 0
        assert service.metrics.cache_misses == 0
    
    @pytest.mark.asyncio
    async def test_cache_key_generation(self, cached_search_service):
        """Test cache key generation for different requests."""
        # Test simple request
        request1 = SimpleSearchRequest(
            query="machine learning",
            top_k=10,
            source_type=SourceType.BOOK
        )
        
        request2 = SimpleSearchRequest(
            query="machine learning",
            top_k=10,
            source_type=SourceType.BOOK
        )
        
        request3 = SimpleSearchRequest(
            query="deep learning",
            top_k=10,
            source_type=SourceType.BOOK
        )
        
        key1 = cached_search_service._generate_cache_key(request1)
        key2 = cached_search_service._generate_cache_key(request2)
        key3 = cached_search_service._generate_cache_key(request3)
        
        # Same requests should generate same keys
        assert key1 == key2
        # Different requests should generate different keys
        assert key1 != key3
        # Keys should have proper format
        assert key1.startswith("search_result:")
        assert len(key1.split(":")[1]) == 16  # Hash length
    
    @pytest.mark.asyncio
    async def test_search_cache_miss(self, cached_search_service, mock_cache_service):
        """Test search operation with cache miss."""
        with patch('src.multimodal_librarian.components.vector_store.search_service_cached.get_cache_service', 
                   return_value=mock_cache_service):
            
            request = SimpleSearchRequest(query="machine learning", top_k=5)
            
            # Perform search
            response = await cached_search_service.search(request)
            
            # Verify response
            assert response is not None
            assert len(response.results) == 2
            assert response.results[0].content == "Test content about machine learning"
            assert response.results[1].content == "Advanced ML algorithms and techniques"
            
            # Verify metrics
            assert cached_search_service.metrics.total_searches == 1
            assert cached_search_service.metrics.cache_misses == 1
            assert cached_search_service.metrics.cache_hits == 0
            assert cached_search_service.metrics.cache_hit_rate == 0.0
            
            # Verify cache service was called
            mock_cache_service.get.assert_called_once()
            mock_cache_service.set.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_search_cache_hit(self, cached_search_service, mock_cache_service):
        """Test search operation with cache hit."""
        # Create cached result
        cached_result = CachedSearchResult(
            results=[
                SearchResult(
                    chunk_id='cached_chunk',
                    content='Cached content about AI',
                    source_type=SourceType.BOOK,
                    source_id='cached_doc',
                    content_type=ContentType.GENERAL,
                    location_reference='cached_page',
                    section='Cached Section',
                    similarity_score=0.92
                )
            ],
            total_results=1,
            search_time_ms=150.0,
            session_id='test_session',
            query_id='test_query',
            cached_at=datetime.now(),
            cache_key='test_key',
            original_query='artificial intelligence'
        )
        
        # Mock cache hit
        mock_cache_service.get.return_value = cached_result
        
        with patch('src.multimodal_librarian.components.vector_store.search_service_cached.get_cache_service', 
                   return_value=mock_cache_service):
            
            request = SimpleSearchRequest(query="artificial intelligence", top_k=5)
            
            # Perform search
            response = await cached_search_service.search(request)
            
            # Verify response from cache
            assert response is not None
            assert len(response.results) == 1
            assert response.results[0].content == "Cached content about AI"
            assert response.results[0].chunk_id == "cached_chunk"
            
            # Verify metrics
            assert cached_search_service.metrics.total_searches == 1
            assert cached_search_service.metrics.cache_hits == 1
            assert cached_search_service.metrics.cache_misses == 0
            assert cached_search_service.metrics.cache_hit_rate == 100.0
            
            # Verify cache service was called for get but not set
            mock_cache_service.get.assert_called_once()
            mock_cache_service.set.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_cache_performance_threshold(self, cached_search_service, mock_cache_service):
        """Test caching based on performance threshold."""
        # Set threshold to 100ms
        cached_search_service.cache_threshold_ms = 100
        
        with patch('src.multimodal_librarian.components.vector_store.search_service_cached.get_cache_service', 
                   return_value=mock_cache_service):
            
            # Mock slow search (should be cached)
            with patch.object(cached_search_service.search_service, 'search') as mock_search:
                slow_response = SimpleSearchResponse(
                    results=[SimpleSearchResult(
                        chunk_id='slow_chunk',
                        content='Slow search result',
                        source_type=SourceType.BOOK,
                        source_id='slow_doc',
                        content_type=ContentType.GENERAL,
                        location_reference='slow_page',
                        section='Slow Section',
                        similarity_score=0.88
                    )],
                    search_time_ms=150.0,  # Above threshold
                    session_id='slow_session'
                )
                
                # Add delay to simulate slow search
                async def slow_search_func(request):
                    await asyncio.sleep(0.15)  # 150ms delay
                    return slow_response
                
                mock_search.side_effect = slow_search_func
                
                request = SimpleSearchRequest(query="slow query", top_k=5)
                response = await cached_search_service.search(request)
                
                # Verify result was cached (set was called)
                mock_cache_service.set.assert_called_once()
                
                # Verify response
                assert response.search_time_ms >= 150.0
    
    @pytest.mark.asyncio
    async def test_cache_invalidation_specific_query(self, cached_search_service, mock_cache_service):
        """Test cache invalidation for specific query."""
        with patch('src.multimodal_librarian.components.vector_store.search_service_cached.get_cache_service', 
                   return_value=mock_cache_service):
            
            # Test specific query invalidation
            result = await cached_search_service.invalidate_cache("machine learning")
            
            assert result["invalidated"] == 1
            assert result["query"] == "machine learning"
            assert "cache_key" in result
            
            # Verify cache service delete was called
            mock_cache_service.delete.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cache_invalidation_all(self, cached_search_service, mock_cache_service):
        """Test cache invalidation for all queries."""
        with patch('src.multimodal_librarian.components.vector_store.search_service_cached.get_cache_service', 
                   return_value=mock_cache_service):
            
            # Test all queries invalidation
            result = await cached_search_service.invalidate_cache()
            
            assert result["invalidated"] == 5
            assert result["type"] == "all_search_results"
            
            # Verify cache service clear_by_type was called
            mock_cache_service.clear_by_type.assert_called_once_with(CacheType.SEARCH_RESULT)
    
    @pytest.mark.asyncio
    async def test_cache_stats_collection(self, cached_search_service, mock_cache_service):
        """Test cache statistics collection."""
        with patch('src.multimodal_librarian.components.vector_store.search_service_cached.get_cache_service', 
                   return_value=mock_cache_service):
            
            # Simulate some cache activity
            cached_search_service.metrics.total_searches = 10
            cached_search_service.metrics.cache_hits = 7
            cached_search_service.metrics.cache_misses = 3
            cached_search_service.metrics.update_hit_rate()
            
            stats = await cached_search_service.get_cache_stats()
            
            # Verify stats structure
            assert stats["cache_enabled"] is True
            assert stats["cache_service_available"] is True
            assert stats["metrics"]["total_searches"] == 10
            assert stats["metrics"]["cache_hits"] == 7
            assert stats["metrics"]["cache_misses"] == 3
            assert stats["metrics"]["cache_hit_rate"] == 70.0
            
            # Verify config
            assert stats["config"]["ttl_seconds"] == 1800
            assert stats["config"]["threshold_ms"] == 50
            
            # Verify cache service stats
            assert "cache_service" in stats
            assert stats["cache_service"]["total_entries"] == 100
            assert stats["cache_service"]["search_entries"] == 25
    
    @pytest.mark.asyncio
    async def test_cache_warming(self, cached_search_service, mock_cache_service):
        """Test cache warming functionality."""
        with patch('src.multimodal_librarian.components.vector_store.search_service_cached.get_cache_service', 
                   return_value=mock_cache_service):
            
            queries = [
                "machine learning",
                "deep learning",
                "artificial intelligence",
                "neural networks"
            ]
            
            # Mock some queries as already cached
            mock_cache_service.exists.side_effect = [False, True, False, False]
            
            result = await cached_search_service.warm_cache(queries, top_k=5)
            
            assert result["total_queries"] == 4
            assert result["cached"] == 3  # 3 new queries cached
            assert result["already_cached"] == 1  # 1 already cached
            assert result["failed"] == 0
            assert len(result["errors"]) == 0
    
    @pytest.mark.asyncio
    async def test_multiple_concurrent_searches(self, cached_search_service, mock_cache_service):
        """Test concurrent search operations with caching."""
        with patch('src.multimodal_librarian.components.vector_store.search_service_cached.get_cache_service', 
                   return_value=mock_cache_service):
            
            # Create multiple search requests
            requests = [
                SimpleSearchRequest(query=f"query {i}", top_k=5)
                for i in range(5)
            ]
            
            # Perform concurrent searches
            tasks = [cached_search_service.search(request) for request in requests]
            responses = await asyncio.gather(*tasks)
            
            # Verify all searches completed
            assert len(responses) == 5
            for response in responses:
                assert response is not None
                assert len(response.results) == 2
            
            # Verify metrics
            assert cached_search_service.metrics.total_searches == 5
            assert cached_search_service.metrics.cache_misses == 5
            assert cached_search_service.metrics.cache_hits == 0
    
    @pytest.mark.asyncio
    async def test_cache_service_unavailable(self, mock_vector_store, cache_config):
        """Test behavior when cache service is unavailable."""
        service = CachedSimpleSearchService(mock_vector_store, cache_config)
        
        # Mock cache service initialization failure
        with patch('src.multimodal_librarian.components.vector_store.search_service_cached.get_cache_service', 
                   side_effect=Exception("Cache unavailable")):
            
            request = SimpleSearchRequest(query="test query", top_k=5)
            response = await service.search(request)
            
            # Search should still work without cache
            assert response is not None
            assert len(response.results) == 2
            
            # Cache should be disabled
            assert service.enable_cache is False
            assert service.cache_service is None
    
    @pytest.mark.asyncio
    async def test_factory_function(self, mock_vector_store):
        """Test factory function for creating cached search services."""
        # Test simple service creation
        simple_service = create_cached_search_service(
            mock_vector_store, 
            service_type="simple",
            cache_config={'ttl': 900}
        )
        assert isinstance(simple_service, CachedSimpleSearchService)
        assert simple_service.cache_ttl == 900
        
        # Test enhanced service creation
        enhanced_service = create_cached_search_service(
            mock_vector_store,
            service_type="enhanced",
            cache_config={'ttl': 1200}
        )
        assert isinstance(enhanced_service, CachedEnhancedSearchService)
        assert enhanced_service.cache_ttl == 1200
    
    @pytest.mark.asyncio
    async def test_health_check(self, cached_search_service):
        """Test health check functionality."""
        # Mock healthy underlying service
        cached_search_service.search_service.health_check = Mock(return_value=True)
        
        assert cached_search_service.health_check() is True
        
        # Mock unhealthy underlying service
        cached_search_service.search_service.health_check = Mock(return_value=False)
        
        assert cached_search_service.health_check() is False
    
    @pytest.mark.asyncio
    async def test_cached_search_result_conversion(self):
        """Test CachedSearchResult conversion methods."""
        # Create original search result
        search_result = SearchResult(
            chunk_id='test_chunk',
            content='Test content',
            source_type=SourceType.BOOK,
            source_id='test_doc',
            content_type=ContentType.GENERAL,
            location_reference='test_page',
            section='Test Section',
            similarity_score=0.95
        )
        
        # Create simple response
        from src.multimodal_librarian.components.vector_store.search_service_simple import SimpleSearchResult
        simple_result = SimpleSearchResult(
            chunk_id='test_chunk',
            content='Test content',
            source_type=SourceType.BOOK,
            source_id='test_doc',
            content_type=ContentType.GENERAL,
            location_reference='test_page',
            section='Test Section',
            similarity_score=0.95
        )
        
        simple_response = SimpleSearchResponse(
            results=[simple_result],
            total_results=1,
            search_time_ms=100.0,
            session_id='test_session',
            query_id='test_query'
        )
        
        # Test conversion from simple response
        cached_result = CachedSearchResult.from_simple_response(
            simple_response, 'test_key', 'test query'
        )
        
        assert cached_result.total_results == 1
        assert cached_result.cache_key == 'test_key'
        assert cached_result.original_query == 'test query'
        assert len(cached_result.results) == 1
        
        # Test conversion back to simple response
        converted_response = cached_result.to_simple_response()
        
        assert converted_response.total_results == 1
        assert converted_response.session_id == 'test_session'
        assert len(converted_response.results) == 1
        assert converted_response.results[0].chunk_id == 'test_chunk'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])