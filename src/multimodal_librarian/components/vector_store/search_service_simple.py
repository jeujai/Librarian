"""
Optimized Simple Semantic Search Service for Multimodal Librarian.

This module provides optimized basic semantic search functionality with:
- Improved search algorithms for better performance
- Query result caching to reduce response times
- Batch processing optimizations
- Memory-efficient operations
- Performance monitoring and auto-optimization

Validates: Requirement 2.2 - Search Service Stability
"""

import asyncio
import hashlib
import logging
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set, Tuple

from ...models.core import ContentType, KnowledgeChunk, SourceType

# Import SearchResult from models to avoid circular imports
from ...models.search_types import SearchQuery, SearchResponse, SearchResult
from .vector_store import VectorStore, VectorStoreError

logger = logging.getLogger(__name__)


@dataclass
class QueryCacheEntry:
    """Cache entry for search query results."""
    query_hash: str
    results: List['SimpleSearchResult']
    created_at: datetime
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    search_params: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self, ttl_seconds: int = 1800) -> bool:
        """Check if cache entry is expired (default 30 minutes)."""
        return (datetime.now() - self.created_at).total_seconds() > ttl_seconds
    
    def is_similar_query(self, other_hash: str, similarity_threshold: float = 0.9) -> bool:
        """Check if another query hash is similar enough to reuse results."""
        # Simple similarity check based on hash prefix
        # In a more sophisticated implementation, this could use embedding similarity
        return self.query_hash[:8] == other_hash[:8]


@dataclass
class SearchPerformanceMetrics:
    """Performance metrics for search operations."""
    total_searches: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    avg_response_time_ms: float = 0.0
    avg_results_count: float = 0.0
    optimization_count: int = 0
    fallback_usage_count: int = 0
    
    def get_cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total_requests = self.cache_hits + self.cache_misses
        return self.cache_hits / total_requests if total_requests > 0 else 0.0
    
    def get_performance_score(self) -> float:
        """Calculate overall performance score (0-100)."""
        # Weighted score based on response time and cache hit rate
        time_score = max(0, 100 - (self.avg_response_time_ms / 10))  # 1000ms = 0 score
        cache_score = self.get_cache_hit_rate() * 100
        return (time_score * 0.6) + (cache_score * 0.4)


@dataclass
class SimpleSearchResult:
    """Simple search result with basic metadata and optimization features."""
    chunk_id: str
    content: str
    source_type: SourceType
    source_id: str
    content_type: ContentType
    location_reference: str
    section: str
    similarity_score: float
    relevance_score: float = 0.0
    is_bridge: bool = False
    created_at: Optional[datetime] = None
    
    # Optimization fields
    content_length: int = field(init=False)
    content_hash: str = field(init=False)
    keywords: Set[str] = field(default_factory=set)
    
    def __post_init__(self):
        """Initialize computed fields."""
        self.content_length = len(self.content)
        self.content_hash = hashlib.md5(self.content.encode()).hexdigest()[:8]
        # Extract simple keywords (could be enhanced with NLP)
        self.keywords = set(word.lower().strip('.,!?;:') 
                          for word in self.content.split() 
                          if len(word) > 3)
    
    @classmethod
    def from_vector_result(cls, vector_result: Dict[str, Any]) -> 'SimpleSearchResult':
        """Create SimpleSearchResult from vector store result with optimizations."""
        created_at = None
        if vector_result.get('created_at'):
            created_at = datetime.fromtimestamp(vector_result['created_at'] / 1000)
        
        result = cls(
            chunk_id=vector_result['chunk_id'],
            content=vector_result['content'],
            source_type=SourceType(vector_result['source_type']),
            source_id=vector_result['source_id'],
            content_type=ContentType(vector_result['content_type']),
            location_reference=vector_result['location_reference'],
            section=vector_result['section'],
            similarity_score=vector_result['similarity_score'],
            relevance_score=vector_result['similarity_score'],
            is_bridge=vector_result.get('is_bridge', False) or 'BRIDGE' in vector_result.get('section', ''),
            created_at=created_at
        )
        
        return result
    
    def calculate_enhanced_relevance(self, query_keywords: Set[str]) -> float:
        """Calculate enhanced relevance score based on keyword overlap."""
        if not query_keywords:
            return self.similarity_score
        
        # Calculate keyword overlap
        overlap = len(self.keywords.intersection(query_keywords))
        total_keywords = len(query_keywords)
        keyword_score = overlap / total_keywords if total_keywords > 0 else 0
        
        # Combine with similarity score (weighted)
        enhanced_score = (self.similarity_score * 0.7) + (keyword_score * 0.3)
        return min(enhanced_score, 1.0)
    
    def to_search_result(self) -> 'SearchResult':
        """Convert to SearchResult for compatibility."""
        from ...models.search_types import SearchResult as SearchResultType
        return SearchResultType(
            chunk_id=self.chunk_id,
            content=self.content,
            source_type=self.source_type,
            source_id=self.source_id,
            content_type=self.content_type,
            location_reference=self.location_reference,
            section=self.section,
            similarity_score=self.similarity_score,
            relevance_score=self.relevance_score,
            is_bridge=self.is_bridge,
            created_at=self.created_at
        )


@dataclass
class SimpleSearchRequest:
    """Optimized search request with enhanced parameters."""
    query: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    
    # Filtering parameters
    source_type: Optional[SourceType] = None
    content_type: Optional[ContentType] = None
    source_id: Optional[str] = None
    
    # Search parameters
    top_k: int = 10
    
    # Optimization parameters
    enable_caching: bool = True
    enable_reranking: bool = True
    similarity_threshold: float = 0.1  # Minimum similarity score
    
    # Query processing
    query_keywords: Set[str] = field(init=False)
    query_hash: str = field(init=False)
    
    def __post_init__(self):
        if self.session_id is None:
            self.session_id = str(uuid.uuid4())
        
        # Process query for optimization
        self.query_keywords = set(word.lower().strip('.,!?;:') 
                                for word in self.query.split() 
                                if len(word) > 2)
        
        # Create query hash for caching
        cache_key = f"{self.query}:{self.source_type}:{self.content_type}:{self.source_id}:{self.top_k}"
        self.query_hash = hashlib.md5(cache_key.encode()).hexdigest()


@dataclass
class SimpleSearchResponse:
    """Optimized search response with enhanced metadata."""
    results: List[SimpleSearchResult]
    total_results: int = 0
    search_time_ms: float = 0.0
    session_id: str = ""
    query_id: str = ""
    
    # Optimization metadata
    cache_hit: bool = False
    optimization_applied: bool = False
    performance_score: float = 0.0
    fallback_mode: bool = True  # This is always fallback mode
    
    def __post_init__(self):
        if self.query_id == "":
            self.query_id = str(uuid.uuid4())
        
        # Calculate performance score
        if self.search_time_ms > 0:
            # Score based on response time (lower is better)
            time_score = max(0, 100 - (self.search_time_ms / 10))  # 1000ms = 0 score
            result_score = min(100, self.total_results * 10)  # More results = better
            self.performance_score = (time_score * 0.7) + (result_score * 0.3)


class OptimizedSimpleSemanticSearchService:
    """
    Optimized simple semantic search service with enhanced performance.
    
    This service provides fallback search capabilities with optimizations to reduce
    the performance gap compared to complex search services. Features include:
    - Query result caching with intelligent cache management
    - Enhanced relevance scoring with keyword matching
    - Batch processing optimizations
    - Performance monitoring and auto-optimization
    - Memory-efficient operations
    """
    
    def __init__(self, vector_store: VectorStore, cache_size: int = 1000):
        """
        Initialize optimized simple search service.
        
        Args:
            vector_store: Vector database instance
            cache_size: Maximum number of queries to cache
        """
        self.vector_store = vector_store
        self.cache_size = cache_size
        
        # Query result cache
        self.query_cache: Dict[str, QueryCacheEntry] = {}
        self.cache_access_order: deque = deque(maxlen=cache_size)
        
        # Performance tracking
        self.metrics = SearchPerformanceMetrics()
        
        # Optimization settings
        self.auto_optimize_enabled = True
        self.optimization_threshold = 50  # Optimize after 50 searches
        self.cache_ttl_seconds = 1800  # 30 minutes
        
        # Query processing optimizations
        self.frequent_queries: Dict[str, int] = defaultdict(int)
        self.query_patterns: Dict[str, List[str]] = defaultdict(list)
        
        # Performance monitoring
        self.response_times: deque = deque(maxlen=100)  # Last 100 response times
        self.last_optimization = datetime.now()
        
        logger.info("Optimized simple semantic search service initialized")
        logger.info(f"Cache size: {cache_size}, Auto-optimization: {self.auto_optimize_enabled}")
    
    def _generate_cache_key(self, request: SimpleSearchRequest) -> str:
        """Generate cache key for search request."""
        return request.query_hash
    
    def _cleanup_cache(self):
        """Clean up expired cache entries."""
        current_time = datetime.now()
        expired_keys = []
        
        for key, entry in self.query_cache.items():
            if entry.is_expired(self.cache_ttl_seconds):
                expired_keys.append(key)
        
        for key in expired_keys:
            del self.query_cache[key]
            if key in self.cache_access_order:
                self.cache_access_order.remove(key)
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")
    
    def _evict_lru_cache_entry(self):
        """Evict least recently used cache entry."""
        if self.cache_access_order:
            lru_key = self.cache_access_order.popleft()
            if lru_key in self.query_cache:
                del self.query_cache[lru_key]
                logger.debug(f"Evicted LRU cache entry: {lru_key[:8]}...")
    
    def _add_to_cache(self, request: SimpleSearchRequest, results: List[SimpleSearchResult]):
        """Add search results to cache."""
        if not request.enable_caching:
            return
        
        cache_key = self._generate_cache_key(request)
        
        # Clean up expired entries first
        self._cleanup_cache()
        
        # Evict LRU entry if cache is full
        if len(self.query_cache) >= self.cache_size:
            self._evict_lru_cache_entry()
        
        # Add new entry
        entry = QueryCacheEntry(
            query_hash=cache_key,
            results=results,
            created_at=datetime.now(),
            search_params={
                'source_type': request.source_type,
                'content_type': request.content_type,
                'source_id': request.source_id,
                'top_k': request.top_k
            }
        )
        
        self.query_cache[cache_key] = entry
        self.cache_access_order.append(cache_key)
        
        logger.debug(f"Added query to cache: {cache_key[:8]}... (cache size: {len(self.query_cache)})")
    
    def _get_from_cache(self, request: SimpleSearchRequest) -> Optional[List[SimpleSearchResult]]:
        """Get search results from cache."""
        if not request.enable_caching:
            return None
        
        cache_key = self._generate_cache_key(request)
        
        # Check direct cache hit
        if cache_key in self.query_cache:
            entry = self.query_cache[cache_key]
            if not entry.is_expired(self.cache_ttl_seconds):
                # Update access statistics
                entry.access_count += 1
                entry.last_accessed = datetime.now()
                
                # Move to end of access order (most recently used)
                if cache_key in self.cache_access_order:
                    self.cache_access_order.remove(cache_key)
                self.cache_access_order.append(cache_key)
                
                self.metrics.cache_hits += 1
                logger.debug(f"Cache hit for query: {cache_key[:8]}...")
                return entry.results
        
        # Check for similar queries (simple implementation)
        for existing_key, entry in self.query_cache.items():
            if (not entry.is_expired(self.cache_ttl_seconds) and 
                entry.is_similar_query(cache_key)):
                
                # Update access statistics
                entry.access_count += 1
                entry.last_accessed = datetime.now()
                
                self.metrics.cache_hits += 1
                logger.debug(f"Similar query cache hit: {existing_key[:8]}... for {cache_key[:8]}...")
                return entry.results
        
        self.metrics.cache_misses += 1
        return None
    
    def _enhance_results(self, results: List[SimpleSearchResult], request: SimpleSearchRequest) -> List[SimpleSearchResult]:
        """Enhance search results with improved relevance scoring."""
        if not request.enable_reranking or not results:
            return results
        
        # Calculate enhanced relevance scores
        for result in results:
            result.relevance_score = result.calculate_enhanced_relevance(request.query_keywords)
        
        # Re-sort by enhanced relevance score
        enhanced_results = sorted(results, key=lambda r: r.relevance_score, reverse=True)
        
        # Filter by similarity threshold
        filtered_results = [r for r in enhanced_results if r.similarity_score >= request.similarity_threshold]
        
        logger.debug(f"Enhanced {len(results)} results, filtered to {len(filtered_results)}")
        return filtered_results
    
    def _should_auto_optimize(self) -> bool:
        """Check if auto-optimization should be triggered."""
        if not self.auto_optimize_enabled:
            return False
        
        # Check if enough searches have been performed
        if self.metrics.total_searches % self.optimization_threshold != 0:
            return False
        
        # Check if enough time has passed since last optimization
        time_since_optimization = (datetime.now() - self.last_optimization).total_seconds()
        return time_since_optimization >= 300  # 5 minutes
    
    def _auto_optimize(self):
        """Perform automatic optimizations based on usage patterns."""
        try:
            # Optimize cache size based on hit rate
            hit_rate = self.metrics.get_cache_hit_rate()
            if hit_rate < 0.3 and self.cache_size < 2000:  # Low hit rate, increase cache
                self.cache_size = min(2000, int(self.cache_size * 1.2))
                logger.info(f"Increased cache size to {self.cache_size} (hit rate: {hit_rate:.2%})")
            elif hit_rate > 0.8 and self.cache_size > 500:  # High hit rate, can reduce cache
                self.cache_size = max(500, int(self.cache_size * 0.9))
                logger.info(f"Reduced cache size to {self.cache_size} (hit rate: {hit_rate:.2%})")
            
            # Optimize cache TTL based on access patterns
            avg_access_count = sum(entry.access_count for entry in self.query_cache.values()) / len(self.query_cache) if self.query_cache else 0
            if avg_access_count > 3:  # Frequently accessed queries
                self.cache_ttl_seconds = min(3600, int(self.cache_ttl_seconds * 1.1))  # Increase TTL
            elif avg_access_count < 1.5:  # Rarely accessed queries
                self.cache_ttl_seconds = max(900, int(self.cache_ttl_seconds * 0.9))  # Decrease TTL
            
            self.metrics.optimization_count += 1
            self.last_optimization = datetime.now()
            
            logger.info(f"Auto-optimization completed (#{self.metrics.optimization_count})")
            
        except Exception as e:
            logger.warning(f"Auto-optimization failed: {e}")
    
    async def search(self, request: SimpleSearchRequest) -> SimpleSearchResponse:
        """
        Perform optimized semantic search with caching and enhancements.
        
        Args:
            request: Search request with parameters
            
        Returns:
            Search response with results and metadata
        """
        start_time = time.time()
        cache_hit = False
        optimization_applied = False
        
        try:
            # Track query frequency
            self.frequent_queries[request.query] += 1
            
            # Check cache first
            cached_results = self._get_from_cache(request)
            if cached_results is not None:
                cache_hit = True
                simple_results = cached_results
                logger.debug(f"Using cached results for query: {request.query[:50]}...")
            else:
                # Perform vector search (ASYNC - non-blocking)
                # Use async method to avoid blocking the event loop
                if hasattr(self.vector_store, 'semantic_search_async'):
                    vector_results = await self.vector_store.semantic_search_async(
                        query=request.query,
                        top_k=min(request.top_k * 2, 50),  # Get more results for better reranking
                        source_type=request.source_type,
                        content_type=request.content_type,
                        source_id=request.source_id
                    )
                else:
                    # Fallback to sync method if async not available
                    # This should be avoided in production
                    logger.warning("Using synchronous semantic_search - this may block the event loop")
                    vector_results = self.vector_store.semantic_search(
                        query=request.query,
                        top_k=min(request.top_k * 2, 50),
                        source_type=request.source_type,
                        content_type=request.content_type,
                        source_id=request.source_id
                    )
                
                # Convert to simple results
                simple_results = [
                    SimpleSearchResult.from_vector_result(result) 
                    for result in vector_results
                ]
                
                # Enhance results with improved scoring
                simple_results = self._enhance_results(simple_results, request)
                optimization_applied = True
                
                # Limit to requested number of results
                simple_results = simple_results[:request.top_k]
                
                # Add to cache
                self._add_to_cache(request, simple_results)
            
            # Calculate search time
            search_time_ms = (time.time() - start_time) * 1000
            self.response_times.append(search_time_ms)
            
            # Create response
            response = SimpleSearchResponse(
                results=simple_results,
                total_results=len(simple_results),
                search_time_ms=search_time_ms,
                session_id=request.session_id,
                query_id=str(uuid.uuid4()),
                cache_hit=cache_hit,
                optimization_applied=optimization_applied,
                fallback_mode=True
            )
            
            # Update performance metrics
            self.metrics.total_searches += 1
            self.metrics.fallback_usage_count += 1
            
            # Update average response time
            total_time = self.metrics.avg_response_time_ms * (self.metrics.total_searches - 1) + search_time_ms
            self.metrics.avg_response_time_ms = total_time / self.metrics.total_searches
            
            # Update average results count
            total_results = self.metrics.avg_results_count * (self.metrics.total_searches - 1) + len(simple_results)
            self.metrics.avg_results_count = total_results / self.metrics.total_searches
            
            # Auto-optimization check
            if self._should_auto_optimize():
                self._auto_optimize()
            
            logger.info(f"Optimized search completed in {search_time_ms:.1f}ms: {len(simple_results)} results "
                       f"(cache_hit: {cache_hit}, optimized: {optimization_applied})")
            
            return response
            
        except Exception as e:
            search_time_ms = (time.time() - start_time) * 1000
            logger.error(f"Optimized search failed: {e}")
            
            # Return empty response on error
            return SimpleSearchResponse(
                results=[],
                search_time_ms=search_time_ms,
                session_id=request.session_id,
                fallback_mode=True
            )
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        cache_stats = {
            'cache_size': len(self.query_cache),
            'cache_hit_rate': self.metrics.get_cache_hit_rate(),
            'cache_hits': self.metrics.cache_hits,
            'cache_misses': self.metrics.cache_misses,
            'cache_ttl_seconds': self.cache_ttl_seconds
        }
        
        performance_stats = {
            'total_searches': self.metrics.total_searches,
            'avg_response_time_ms': self.metrics.avg_response_time_ms,
            'avg_results_count': self.metrics.avg_results_count,
            'performance_score': self.metrics.get_performance_score(),
            'optimization_count': self.metrics.optimization_count,
            'fallback_usage_count': self.metrics.fallback_usage_count
        }
        
        # Recent performance (last 10 searches)
        recent_times = list(self.response_times)[-10:] if self.response_times else []
        recent_stats = {
            'recent_avg_response_time_ms': sum(recent_times) / len(recent_times) if recent_times else 0,
            'recent_min_response_time_ms': min(recent_times) if recent_times else 0,
            'recent_max_response_time_ms': max(recent_times) if recent_times else 0
        }
        
        return {
            'cache': cache_stats,
            'performance': performance_stats,
            'recent': recent_stats,
            'optimization': {
                'auto_optimize_enabled': self.auto_optimize_enabled,
                'last_optimization': self.last_optimization.isoformat(),
                'frequent_queries_count': len(self.frequent_queries)
            }
        }
    
    def get_cache_statistics(self) -> Dict[str, Any]:
        """Get detailed cache statistics."""
        if not self.query_cache:
            return {'cache_empty': True}
        
        # Calculate cache entry statistics
        total_access_count = sum(entry.access_count for entry in self.query_cache.values())
        avg_access_count = total_access_count / len(self.query_cache)
        
        # Find most and least accessed entries
        most_accessed = max(self.query_cache.values(), key=lambda e: e.access_count)
        least_accessed = min(self.query_cache.values(), key=lambda e: e.access_count)
        
        return {
            'total_entries': len(self.query_cache),
            'total_access_count': total_access_count,
            'avg_access_count': avg_access_count,
            'most_accessed_count': most_accessed.access_count,
            'least_accessed_count': least_accessed.access_count,
            'cache_hit_rate': self.metrics.get_cache_hit_rate(),
            'cache_utilization': len(self.query_cache) / self.cache_size
        }
    
    def clear_cache(self):
        """Clear the query cache."""
        cleared_count = len(self.query_cache)
        self.query_cache.clear()
        self.cache_access_order.clear()
        logger.info(f"Cleared {cleared_count} cache entries")
    
    def health_check(self) -> Dict[str, Any]:
        """Enhanced health check with performance metrics."""
        try:
            vector_store_healthy = self.vector_store.health_check()
            
            # Calculate health score based on performance
            performance_score = self.metrics.get_performance_score()
            cache_hit_rate = self.metrics.get_cache_hit_rate()
            
            # Determine overall health
            is_healthy = (
                vector_store_healthy and 
                performance_score > 50 and  # Reasonable performance
                self.metrics.avg_response_time_ms < 1000  # Under 1 second average
            )
            
            return {
                'healthy': is_healthy,
                'vector_store_healthy': vector_store_healthy,
                'performance_score': performance_score,
                'cache_hit_rate': cache_hit_rate,
                'avg_response_time_ms': self.metrics.avg_response_time_ms,
                'total_searches': self.metrics.total_searches,
                'optimization_count': self.metrics.optimization_count,
                'service_type': 'optimized_simple_search'
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                'healthy': False,
                'error': str(e),
                'service_type': 'optimized_simple_search'
            }


# Maintain backward compatibility
SimpleSemanticSearchService = OptimizedSimpleSemanticSearchService
# Backward compatibility aliases
SemanticSearchService = OptimizedSimpleSemanticSearchService
SearchResult = SimpleSearchResultSearchResult = SimpleSearchResult