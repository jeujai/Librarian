"""
Cached Search Service for Multimodal Librarian.

This module provides search result caching functionality to improve performance
by caching frequent search results and reducing vector store operations.
"""

import logging
import hashlib
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import uuid

# Import search types and services
from ...models.search_types import SearchResult, SearchQuery, SearchResponse
from ...models.core import SourceType, ContentType
from .search_service import EnhancedSemanticSearchService, SearchRequest
from .search_service_simple import SimpleSemanticSearchService, SimpleSearchRequest, SimpleSearchResponse
from ...services.cache_service import get_cache_service, CacheType, CacheService

logger = logging.getLogger(__name__)


@dataclass
class CacheMetrics:
    """Cache performance metrics for search operations."""
    total_searches: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_hit_rate: float = 0.0
    avg_cache_response_time_ms: float = 0.0
    avg_search_response_time_ms: float = 0.0
    cache_size_entries: int = 0
    cache_memory_usage_mb: float = 0.0
    
    def update_hit_rate(self):
        """Update cache hit rate based on hits and misses."""
        total = self.cache_hits + self.cache_misses
        self.cache_hit_rate = (self.cache_hits / total * 100) if total > 0 else 0.0


@dataclass
class CachedSearchResult:
    """Search result with cache metadata."""
    results: List[SearchResult]
    total_results: int
    search_time_ms: float
    session_id: str
    query_id: str
    cached_at: datetime
    cache_key: str
    original_query: str
    
    @classmethod
    def from_simple_response(cls, response: SimpleSearchResponse, cache_key: str, original_query: str) -> 'CachedSearchResult':
        """Create from SimpleSearchResponse."""
        # Convert SimpleSearchResult to SearchResult
        search_results = [result.to_search_result() for result in response.results]
        
        return cls(
            results=search_results,
            total_results=response.total_results,
            search_time_ms=response.search_time_ms,
            session_id=response.session_id,
            query_id=response.query_id,
            cached_at=datetime.now(),
            cache_key=cache_key,
            original_query=original_query
        )
    
    def to_simple_response(self) -> SimpleSearchResponse:
        """Convert back to SimpleSearchResponse."""
        from .search_service_simple import SimpleSearchResult
        
        # Convert SearchResult back to SimpleSearchResult
        simple_results = []
        for result in self.results:
            simple_result = SimpleSearchResult(
                chunk_id=result.chunk_id,
                content=result.content,
                source_type=result.source_type,
                source_id=result.source_id,
                content_type=result.content_type,
                location_reference=result.location_reference,
                section=result.section,
                similarity_score=result.similarity_score,
                relevance_score=result.relevance_score,
                is_bridge=result.is_bridge,
                created_at=result.created_at
            )
            simple_results.append(simple_result)
        
        return SimpleSearchResponse(
            results=simple_results,
            total_results=self.total_results,
            search_time_ms=self.search_time_ms,
            session_id=self.session_id,
            query_id=self.query_id
        )


class CachedSearchService:
    """
    Search service with result caching capabilities.
    
    This service wraps existing search services and adds intelligent caching
    to improve performance for frequent queries.
    """
    
    def __init__(self, search_service, cache_config: Optional[Dict[str, Any]] = None):
        """
        Initialize cached search service.
        
        Args:
            search_service: Underlying search service (Simple or Enhanced)
            cache_config: Cache configuration options
        """
        self.search_service = search_service
        self.cache_service: Optional[CacheService] = None
        self._cache_initialized = False
        
        # Cache configuration
        self.cache_config = cache_config or {}
        self.cache_ttl = self.cache_config.get('ttl', 3600)  # 1 hour default
        self.enable_cache = self.cache_config.get('enable', True)
        self.cache_threshold_ms = self.cache_config.get('threshold_ms', 100)  # Cache queries taking > 100ms
        self.max_cache_entries = self.cache_config.get('max_entries', 10000)
        self.cache_invalidation_hours = self.cache_config.get('invalidation_hours', 24)
        
        # Performance metrics
        self.metrics = CacheMetrics()
        
        logger.info(f"Cached search service initialized with TTL: {self.cache_ttl}s")
    
    async def _ensure_cache_initialized(self):
        """Ensure cache service is initialized."""
        if not self._cache_initialized and self.enable_cache:
            try:
                self.cache_service = await get_cache_service()
                self._cache_initialized = True
                logger.info("Cache service connected for search operations")
            except Exception as e:
                logger.warning(f"Failed to initialize cache service: {e}")
                self.cache_service = None
                self.enable_cache = False
    
    def _generate_cache_key(self, request) -> str:
        """
        Generate cache key for search request.
        
        Args:
            request: Search request (SimpleSearchRequest or SearchRequest)
            
        Returns:
            Cache key string
        """
        # Extract key components based on request type
        if hasattr(request, 'to_simple_request'):
            # Enhanced SearchRequest
            key_data = {
                'query': request.query,
                'top_k': request.top_k,
                'source_type': request.source_type.value if request.source_type else None,
                'content_type': request.content_type.value if request.content_type else None,
                'source_id': request.source_id,
                'enable_hybrid_search': request.enable_hybrid_search,
                'enable_query_understanding': request.enable_query_understanding,
                'enable_reranking': request.enable_reranking,
                'user_expertise': request.user_expertise
            }
        else:
            # SimpleSearchRequest
            key_data = {
                'query': request.query,
                'top_k': request.top_k,
                'source_type': request.source_type.value if request.source_type else None,
                'content_type': request.content_type.value if request.content_type else None,
                'source_id': request.source_id
            }
        
        # Create deterministic key
        key_json = json.dumps(key_data, sort_keys=True)
        key_hash = hashlib.sha256(key_json.encode()).hexdigest()[:16]
        
        return f"search_result:{key_hash}"
    
    async def search(self, request) -> Any:
        """
        Perform cached search operation.
        
        Args:
            request: Search request (SimpleSearchRequest or SearchRequest)
            
        Returns:
            Search response with results
        """
        await self._ensure_cache_initialized()
        
        start_time = datetime.now()
        cache_key = self._generate_cache_key(request)
        
        # Try to get from cache first
        if self.enable_cache and self.cache_service:
            try:
                cached_result = await self.cache_service.get(
                    CacheType.SEARCH_RESULT,
                    cache_key
                )
                
                if cached_result:
                    # Cache hit
                    self.metrics.cache_hits += 1
                    self.metrics.total_searches += 1
                    
                    cache_response_time = (datetime.now() - start_time).total_seconds() * 1000
                    self.metrics.avg_cache_response_time_ms = (
                        (self.metrics.avg_cache_response_time_ms * (self.metrics.cache_hits - 1) + 
                         cache_response_time) / self.metrics.cache_hits
                    )
                    
                    self.metrics.update_hit_rate()
                    
                    logger.debug(f"Cache hit for search query: '{request.query}' ({cache_response_time:.1f}ms)")
                    
                    # Return cached result converted to appropriate format
                    if isinstance(cached_result, CachedSearchResult):
                        return cached_result.to_simple_response()
                    else:
                        return cached_result
                        
            except Exception as e:
                logger.warning(f"Cache retrieval failed: {e}")
        
        # Cache miss - perform actual search
        try:
            search_start = datetime.now()
            
            # Perform search using underlying service
            if hasattr(self.search_service, 'search'):
                response = await self.search_service.search(request)
            else:
                # Fallback for synchronous services
                response = self.search_service.search(request)
            
            search_time = (datetime.now() - search_start).total_seconds() * 1000
            
            # Update metrics
            self.metrics.cache_misses += 1
            self.metrics.total_searches += 1
            self.metrics.avg_search_response_time_ms = (
                (self.metrics.avg_search_response_time_ms * (self.metrics.cache_misses - 1) + 
                 search_time) / self.metrics.cache_misses
            )
            self.metrics.update_hit_rate()
            
            # Cache the result if it took longer than threshold
            if (self.enable_cache and self.cache_service and 
                search_time >= self.cache_threshold_ms and response):
                
                try:
                    # Create cached result
                    cached_result = CachedSearchResult.from_simple_response(
                        response, cache_key, request.query
                    )
                    
                    # Store in cache
                    await self.cache_service.set(
                        CacheType.SEARCH_RESULT,
                        cache_key,
                        cached_result,
                        ttl=self.cache_ttl
                    )
                    
                    logger.debug(f"Cached search result for query: '{request.query}' (search: {search_time:.1f}ms)")
                    
                except Exception as e:
                    logger.warning(f"Failed to cache search result: {e}")
            
            logger.info(f"Search completed: '{request.query}' ({search_time:.1f}ms, {len(response.results) if response else 0} results)")
            return response
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            # Return empty response on error
            if hasattr(request, 'session_id'):
                from .search_service_simple import SimpleSearchResponse
                return SimpleSearchResponse(
                    results=[],
                    search_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                    session_id=request.session_id
                )
            else:
                raise
    
    async def invalidate_cache(self, query: Optional[str] = None) -> Dict[str, Any]:
        """
        Invalidate cached search results.
        
        Args:
            query: Specific query to invalidate (None for all)
            
        Returns:
            Invalidation results
        """
        await self._ensure_cache_initialized()
        
        if not self.cache_service:
            return {"error": "Cache service not available"}
        
        try:
            if query:
                # Invalidate specific query
                # Create a dummy request to generate cache key
                from .search_service_simple import SimpleSearchRequest
                dummy_request = SimpleSearchRequest(query=query)
                cache_key = self._generate_cache_key(dummy_request)
                
                deleted = await self.cache_service.delete(CacheType.SEARCH_RESULT, cache_key)
                return {
                    "invalidated": 1 if deleted else 0,
                    "query": query,
                    "cache_key": cache_key
                }
            else:
                # Invalidate all search results
                cleared = await self.cache_service.clear_by_type(CacheType.SEARCH_RESULT)
                return {
                    "invalidated": cleared,
                    "type": "all_search_results"
                }
                
        except Exception as e:
            logger.error(f"Cache invalidation failed: {e}")
            return {"error": str(e)}
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache performance statistics.
        
        Returns:
            Cache statistics and metrics
        """
        await self._ensure_cache_initialized()
        
        stats = {
            "cache_enabled": self.enable_cache,
            "cache_service_available": self.cache_service is not None,
            "metrics": asdict(self.metrics),
            "config": {
                "ttl_seconds": self.cache_ttl,
                "threshold_ms": self.cache_threshold_ms,
                "max_entries": self.max_cache_entries,
                "invalidation_hours": self.cache_invalidation_hours
            }
        }
        
        # Get cache service stats if available
        if self.cache_service:
            try:
                cache_service_stats = await self.cache_service.get_stats()
                stats["cache_service"] = {
                    "total_entries": cache_service_stats.total_entries,
                    "memory_usage_mb": cache_service_stats.memory_usage_mb,
                    "hit_rate": cache_service_stats.hit_rate,
                    "avg_access_time_ms": cache_service_stats.avg_access_time_ms,
                    "search_entries": cache_service_stats.entries_by_type.get('search_result', 0)
                }
                
                # Update our metrics with cache service data
                self.metrics.cache_size_entries = cache_service_stats.entries_by_type.get('search_result', 0)
                self.metrics.cache_memory_usage_mb = cache_service_stats.memory_usage_mb
                
            except Exception as e:
                logger.warning(f"Failed to get cache service stats: {e}")
                stats["cache_service"] = {"error": str(e)}
        
        return stats
    
    async def warm_cache(self, queries: List[str], **search_params) -> Dict[str, Any]:
        """
        Warm cache with common queries.
        
        Args:
            queries: List of queries to pre-cache
            **search_params: Additional search parameters
            
        Returns:
            Cache warming results
        """
        await self._ensure_cache_initialized()
        
        if not self.enable_cache or not self.cache_service:
            return {"error": "Cache not available"}
        
        results = {
            "total_queries": len(queries),
            "cached": 0,
            "failed": 0,
            "already_cached": 0,
            "errors": []
        }
        
        for query in queries:
            try:
                # Create search request
                from .search_service_simple import SimpleSearchRequest
                request = SimpleSearchRequest(query=query, **search_params)
                cache_key = self._generate_cache_key(request)
                
                # Check if already cached
                if await self.cache_service.exists(CacheType.SEARCH_RESULT, cache_key):
                    results["already_cached"] += 1
                    continue
                
                # Perform search and cache result
                response = await self.search(request)
                if response and response.results:
                    results["cached"] += 1
                    logger.debug(f"Cache warmed for query: '{query}'")
                else:
                    results["failed"] += 1
                    
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Query '{query}': {str(e)}")
                logger.warning(f"Cache warming failed for query '{query}': {e}")
        
        logger.info(f"Cache warming completed: {results['cached']} cached, {results['failed']} failed")
        return results
    
    def health_check(self) -> bool:
        """Check if the cached search service is healthy."""
        try:
            # Check underlying search service
            if hasattr(self.search_service, 'health_check'):
                search_healthy = self.search_service.health_check()
            else:
                search_healthy = True  # Assume healthy if no health check method
            
            return search_healthy
            
        except Exception as e:
            logger.error(f"Cached search service health check failed: {e}")
            return False


class CachedSimpleSearchService(CachedSearchService):
    """Cached wrapper for SimpleSemanticSearchService."""
    
    def __init__(self, vector_store, cache_config: Optional[Dict[str, Any]] = None):
        """Initialize with SimpleSemanticSearchService."""
        search_service = SimpleSemanticSearchService(vector_store)
        super().__init__(search_service, cache_config)
        logger.info("Cached simple search service initialized")


class CachedEnhancedSearchService(CachedSearchService):
    """Cached wrapper for EnhancedSemanticSearchService."""
    
    def __init__(self, vector_store, config=None, cache_config: Optional[Dict[str, Any]] = None):
        """Initialize with EnhancedSemanticSearchService."""
        search_service = EnhancedSemanticSearchService(vector_store, config)
        super().__init__(search_service, cache_config)
        logger.info("Cached enhanced search service initialized")


# Factory function for creating cached search services
def create_cached_search_service(
    vector_store, 
    service_type: str = "simple",
    search_config=None,
    cache_config: Optional[Dict[str, Any]] = None
) -> CachedSearchService:
    """
    Create cached search service of specified type.
    
    Args:
        vector_store: Vector store instance
        service_type: "simple" or "enhanced"
        search_config: Configuration for search service
        cache_config: Configuration for caching
        
    Returns:
        Cached search service instance
    """
    if service_type == "enhanced":
        return CachedEnhancedSearchService(vector_store, search_config, cache_config)
    else:
        return CachedSimpleSearchService(vector_store, cache_config)