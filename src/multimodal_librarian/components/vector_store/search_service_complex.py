"""
Enhanced Semantic Search Service for Multimodal Librarian.

This module provides advanced semantic search functionality with hybrid search,
query understanding, result re-ranking, analytics, and comprehensive search optimization.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import re
import asyncio
import uuid

# Import SearchResult from models to avoid circular imports
from ...models.search_types import SearchResult, SearchQuery, SearchResponse
from ...models.core import SourceType, ContentType, KnowledgeChunk
from .vector_store import VectorStore, VectorStoreError
from .hybrid_search import HybridSearchEngine, HybridSearchConfig, HybridSearchResult
from .query_understanding import QueryUnderstandingEngine, UnderstoodQuery, QueryContext
from .search_analytics import SearchAnalyticsCollector, SearchMetricsCalculator, SearchPerformanceMonitor

logger = logging.getLogger(__name__)


@dataclass
class EnhancedSearchResult:
    """Enhanced search result with comprehensive metadata and scoring."""
    chunk_id: str
    content: str
    source_type: SourceType
    source_id: str
    content_type: ContentType
    location_reference: str
    section: str
    
    # Scoring information
    similarity_score: float
    relevance_score: float
    hybrid_score: float = 0.0
    rerank_score: Optional[float] = None
    final_score: float = 0.0
    
    # Metadata
    is_bridge: bool = False
    created_at: Optional[datetime] = None
    query_match_explanation: str = ""
    
    # Analytics
    click_count: int = 0
    rating_avg: float = 0.0
    rating_count: int = 0
    
    @classmethod
    def from_hybrid_result(cls, hybrid_result: HybridSearchResult) -> 'EnhancedSearchResult':
        """Create EnhancedSearchResult from HybridSearchResult."""
        sr = hybrid_result.search_result
        return cls(
            chunk_id=sr.chunk_id,
            content=sr.content,
            source_type=sr.source_type,
            source_id=sr.source_id,
            content_type=sr.content_type,
            location_reference=sr.location_reference,
            section=sr.section,
            similarity_score=sr.similarity_score,
            relevance_score=sr.relevance_score,
            hybrid_score=hybrid_result.hybrid_score,
            rerank_score=hybrid_result.rerank_score,
            final_score=hybrid_result.final_score,
            is_bridge=sr.is_bridge,
            created_at=sr.created_at,
            query_match_explanation=hybrid_result.explanation
        )
    
    @classmethod
    def from_vector_result(cls, vector_result: Dict[str, Any]) -> 'EnhancedSearchResult':
        """Create EnhancedSearchResult from vector store result."""
        created_at = None
        if vector_result.get('created_at'):
            created_at = datetime.fromtimestamp(vector_result['created_at'] / 1000)
        
        return cls(
            chunk_id=vector_result['chunk_id'],
            content=vector_result['content'],
            source_type=SourceType(vector_result['source_type']),
            source_id=vector_result['source_id'],
            content_type=ContentType(vector_result['content_type']),
            location_reference=vector_result['location_reference'],
            section=vector_result['section'],
            similarity_score=vector_result['similarity_score'],
            relevance_score=vector_result['similarity_score'],
            final_score=vector_result['similarity_score'],
            is_bridge=vector_result.get('is_bridge', False) or 'BRIDGE' in vector_result.get('section', ''),
            created_at=created_at
        )


@dataclass
class SearchRequest:
    """Comprehensive search request with all parameters."""
    query: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    
    # Filtering parameters
    source_type: Optional[SourceType] = None
    content_type: Optional[ContentType] = None
    source_id: Optional[str] = None
    
    # Search parameters
    top_k: int = 10
    enable_hybrid_search: bool = True
    enable_query_understanding: bool = True
    enable_reranking: bool = True
    enable_analytics: bool = True
    
    # Context
    conversation_history: List[str] = None
    document_context: List[str] = None
    user_expertise: str = "general"
    
    def __post_init__(self):
        if self.conversation_history is None:
            self.conversation_history = []
        if self.document_context is None:
            self.document_context = []
        if self.session_id is None:
            self.session_id = str(uuid.uuid4())


@dataclass
class SearchResponse:
    """Comprehensive search response with results and metadata."""
    results: List[EnhancedSearchResult]
    query_understanding: Optional[UnderstoodQuery] = None
    
    # Search metadata
    total_results: int = 0
    search_time_ms: float = 0.0
    search_strategy: str = "hybrid"
    
    # Facets and filters
    facets: Dict[str, Dict[str, int]] = None
    
    # Analytics
    session_id: str = ""
    query_id: str = ""
    
    def __post_init__(self):
        if self.facets is None:
            self.facets = {}
        if self.query_id == "":
            self.query_id = str(uuid.uuid4())


class EnhancedSemanticSearchService:
    """
    Enhanced semantic search service with comprehensive search capabilities.
    
    Features:
    - Hybrid search (vector + keyword)
    - Advanced query understanding
    - Cross-encoder re-ranking
    - Search analytics and monitoring
    - Performance optimization
    - Faceted search
    - Query expansion
    """
    
    def __init__(self, vector_store: VectorStore, config: Optional[HybridSearchConfig] = None):
        """
        Initialize enhanced search service.
        
        Args:
            vector_store: Vector database instance
            config: Hybrid search configuration
        """
        self.vector_store = vector_store
        self.config = config or HybridSearchConfig()
        
        # Initialize components
        self.hybrid_engine = HybridSearchEngine(vector_store, self.config)
        self.query_understanding = QueryUnderstandingEngine()
        
        # Analytics components
        self.analytics_collector = SearchAnalyticsCollector()
        self.metrics_calculator = SearchMetricsCalculator(self.analytics_collector)
        self.performance_monitor = SearchPerformanceMonitor(
            self.analytics_collector, 
            self.metrics_calculator
        )
        
        # Performance tracking
        self.search_cache = {}
        self.performance_stats = {
            'total_searches': 0,
            'cache_hits': 0,
            'avg_response_time': 0.0
        }
        
        logger.info("Enhanced semantic search service initialized")
    
    async def search(self, request: SearchRequest) -> SearchResponse:
        """
        Perform comprehensive semantic search.
        
        Args:
            request: Search request with all parameters
            
        Returns:
            Complete search response with results and metadata
        """
        start_time = datetime.now()
        
        try:
            # Record query submission
            query_event_id = None
            if request.enable_analytics:
                query_event_id = await self.analytics_collector.record_query_submitted(
                    query=request.query,
                    user_id=request.user_id,
                    session_id=request.session_id
                )
            
            # Check cache first
            cache_key = self._generate_cache_key(request)
            if cache_key in self.search_cache:
                cached_response = self.search_cache[cache_key]
                if (datetime.now() - cached_response['timestamp']).seconds < 300:  # 5 min cache
                    self.performance_stats['cache_hits'] += 1
                    logger.debug(f"Returning cached results for query: {request.query}")
                    return cached_response['response']
            
            # Query understanding
            query_understanding = None
            if request.enable_query_understanding:
                context = QueryContext(
                    conversation_history=request.conversation_history,
                    document_context=request.document_context,
                    user_expertise=request.user_expertise
                )
                query_understanding = await self.query_understanding.understand_query(
                    request.query, context
                )
                
                # Update analytics with understanding
                if request.enable_analytics and query_event_id:
                    await self.analytics_collector.record_event(
                        await self.analytics_collector.record_query_submitted(
                            query=request.query,
                            user_id=request.user_id,
                            session_id=request.session_id,
                            query_intent=query_understanding.intent.value,
                            query_complexity=query_understanding.complexity.value,
                            search_strategy=query_understanding.search_strategy
                        )
                    )
            
            # Perform search based on strategy
            search_strategy = "hybrid"
            if query_understanding:
                search_strategy = query_understanding.search_strategy
            
            if search_strategy == "knowledge_graph":
                # Use knowledge graph search (would integrate with KG component)
                results, facets = await self._knowledge_graph_search(request, query_understanding)
            elif search_strategy == "keyword":
                # Use keyword-focused search
                results, facets = await self._keyword_focused_search(request, query_understanding)
            elif search_strategy == "vector":
                # Use vector-only search
                results, facets = await self._vector_only_search(request, query_understanding)
            else:
                # Use hybrid search (default)
                results, facets = await self.hybrid_engine.search(
                    query=request.query,
                    top_k=request.top_k,
                    source_type=request.source_type,
                    content_type=request.content_type,
                    source_id=request.source_id,
                    enable_reranking=request.enable_reranking,
                    enable_expansion=True
                )
            
            # Convert to enhanced results
            enhanced_results = [
                EnhancedSearchResult.from_hybrid_result(result) 
                for result in results
            ]
            
            # Enrich results with analytics data
            enhanced_results = await self._enrich_results_with_analytics(enhanced_results)
            
            # Calculate search time
            search_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            # Create response
            response = SearchResponse(
                results=enhanced_results,
                query_understanding=query_understanding,
                total_results=len(enhanced_results),
                search_time_ms=search_time_ms,
                search_strategy=search_strategy,
                facets=self._convert_facets(facets) if facets else {},
                session_id=request.session_id,
                query_id=str(uuid.uuid4())
            )
            
            # Record results returned
            if request.enable_analytics and query_event_id:
                await self.analytics_collector.record_results_returned(
                    event_id=query_event_id,
                    results_count=len(enhanced_results),
                    response_time_ms=search_time_ms
                )
            
            # Cache response
            self.search_cache[cache_key] = {
                'response': response,
                'timestamp': datetime.now()
            }
            
            # Update performance stats
            self.performance_stats['total_searches'] += 1
            self.performance_stats['avg_response_time'] = (
                (self.performance_stats['avg_response_time'] * (self.performance_stats['total_searches'] - 1) + 
                 search_time_ms) / self.performance_stats['total_searches']
            )
            
            logger.info(f"Search completed in {search_time_ms:.1f}ms: {len(enhanced_results)} results for '{request.query}'")
            return response
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            # Return empty response on error
            return SearchResponse(
                results=[],
                search_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
                session_id=request.session_id
            )
    
    async def record_result_interaction(
        self,
        session_id: str,
        query: str,
        chunk_id: str,
        interaction_type: str,
        position: Optional[int] = None,
        rating: Optional[float] = None
    ) -> None:
        """
        Record user interaction with search results.
        
        Args:
            session_id: User session ID
            query: Original query
            chunk_id: ID of interacted result
            interaction_type: Type of interaction (click, rating, etc.)
            position: Position of result in list
            rating: User rating if applicable
        """
        try:
            if interaction_type == "click" and position is not None:
                await self.analytics_collector.record_result_clicked(
                    session_id=session_id,
                    query=query,
                    chunk_id=chunk_id,
                    position=position
                )
            elif interaction_type == "rating" and rating is not None:
                await self.analytics_collector.record_result_rating(
                    session_id=session_id,
                    query=query,
                    chunk_id=chunk_id,
                    rating=rating
                )
            
            logger.debug(f"Recorded {interaction_type} interaction for chunk {chunk_id}")
            
        except Exception as e:
            logger.error(f"Failed to record interaction: {e}")
    
    async def get_search_analytics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Get search analytics and performance metrics.
        
        Args:
            hours: Time range for analytics
            
        Returns:
            Analytics data
        """
        try:
            # Calculate metrics
            metrics = self.metrics_calculator.calculate_metrics(
                start_time=datetime.now() - timedelta(hours=hours)
            )
            
            # Check for performance alerts
            alerts = await self.performance_monitor.check_performance()
            
            # Combine with service performance stats
            analytics_data = {
                'search_metrics': {
                    'total_queries': metrics.total_queries,
                    'unique_users': metrics.unique_users,
                    'avg_response_time_ms': metrics.avg_response_time_ms,
                    'click_through_rate': metrics.click_through_rate,
                    'success_rate': metrics.query_success_rate,
                    'avg_rating': metrics.avg_rating
                },
                'service_performance': self.performance_stats,
                'hybrid_engine_analytics': self.hybrid_engine.get_search_analytics(),
                'recent_alerts': [
                    {
                        'type': alert.alert_type,
                        'severity': alert.severity,
                        'message': alert.message,
                        'timestamp': alert.timestamp.isoformat()
                    }
                    for alert in alerts
                ],
                'query_distribution': {
                    'by_intent': metrics.intent_distribution,
                    'by_complexity': metrics.complexity_distribution,
                    'by_strategy': metrics.strategy_performance
                }
            }
            
            return analytics_data
            
        except Exception as e:
            logger.error(f"Failed to get analytics: {e}")
            return {}
    
    async def optimize_search_performance(self) -> Dict[str, Any]:
        """
        Analyze performance and suggest optimizations.
        
        Returns:
            Optimization recommendations
        """
        try:
            # Get current metrics
            metrics = self.metrics_calculator.calculate_metrics()
            
            recommendations = []
            
            # Response time optimization
            if metrics.avg_response_time_ms > 3000:
                recommendations.append({
                    'type': 'performance',
                    'issue': 'High response time',
                    'current_value': metrics.avg_response_time_ms,
                    'recommendations': [
                        'Increase vector database cache size',
                        'Optimize embedding model',
                        'Implement result pre-computation for common queries'
                    ]
                })
            
            # Accuracy optimization
            if metrics.click_through_rate < 0.15:
                recommendations.append({
                    'type': 'accuracy',
                    'issue': 'Low click-through rate',
                    'current_value': metrics.click_through_rate,
                    'recommendations': [
                        'Improve query understanding',
                        'Enhance result re-ranking',
                        'Optimize hybrid search weights'
                    ]
                })
            
            # Success rate optimization
            if metrics.query_success_rate < 0.8:
                recommendations.append({
                    'type': 'effectiveness',
                    'issue': 'Low query success rate',
                    'current_value': metrics.query_success_rate,
                    'recommendations': [
                        'Expand knowledge base coverage',
                        'Improve query expansion',
                        'Enhance fallback strategies'
                    ]
                })
            
            return {
                'optimization_recommendations': recommendations,
                'current_metrics': {
                    'response_time_ms': metrics.avg_response_time_ms,
                    'click_through_rate': metrics.click_through_rate,
                    'success_rate': metrics.query_success_rate,
                    'total_queries': metrics.total_queries
                },
                'generated_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to generate optimization recommendations: {e}")
            return {'optimization_recommendations': [], 'error': str(e)}
    
    async def _knowledge_graph_search(
        self, 
        request: SearchRequest, 
        understanding: Optional[UnderstoodQuery]
    ) -> Tuple[List[HybridSearchResult], Any]:
        """Perform knowledge graph-based search."""
        # Placeholder - would integrate with knowledge graph component
        # For now, fall back to hybrid search
        return await self.hybrid_engine.search(
            query=request.query,
            top_k=request.top_k,
            source_type=request.source_type,
            content_type=request.content_type,
            source_id=request.source_id
        )
    
    async def _keyword_focused_search(
        self, 
        request: SearchRequest, 
        understanding: Optional[UnderstoodQuery]
    ) -> Tuple[List[HybridSearchResult], Any]:
        """Perform keyword-focused search."""
        # Adjust hybrid search to favor keyword matching
        config = HybridSearchConfig(
            vector_weight=0.3,
            keyword_weight=0.7,
            enable_cross_encoder=False
        )
        temp_engine = HybridSearchEngine(self.vector_store, config)
        return await temp_engine.search(
            query=request.query,
            top_k=request.top_k,
            source_type=request.source_type,
            content_type=request.content_type,
            source_id=request.source_id
        )
    
    async def _vector_only_search(
        self, 
        request: SearchRequest, 
        understanding: Optional[UnderstoodQuery]
    ) -> Tuple[List[HybridSearchResult], Any]:
        """Perform vector-only search."""
        # Adjust hybrid search to use only vector similarity
        config = HybridSearchConfig(
            vector_weight=1.0,
            keyword_weight=0.0,
            enable_cross_encoder=True
        )
        temp_engine = HybridSearchEngine(self.vector_store, config)
        return await temp_engine.search(
            query=request.query,
            top_k=request.top_k,
            source_type=request.source_type,
            content_type=request.content_type,
            source_id=request.source_id
        )
    
    async def _enrich_results_with_analytics(
        self, 
        results: List[EnhancedSearchResult]
    ) -> List[EnhancedSearchResult]:
        """Enrich results with analytics data like click counts and ratings."""
        # This would query analytics data for each result
        # For now, return results as-is
        return results
    
    def _convert_facets(self, facets) -> Dict[str, Dict[str, int]]:
        """Convert facets to dictionary format."""
        if hasattr(facets, 'source_types'):
            return {
                'source_types': facets.source_types,
                'content_types': facets.content_types,
                'sources': facets.sources,
                'sections': facets.sections,
                'date_ranges': facets.date_ranges
            }
        return {}
    
    def _generate_cache_key(self, request: SearchRequest) -> str:
        """Generate cache key for search request."""
        key_parts = [
            request.query.lower(),
            str(request.source_type.value if request.source_type else ""),
            str(request.content_type.value if request.content_type else ""),
            str(request.source_id or ""),
            str(request.top_k)
        ]
        return "|".join(key_parts)
    
    def clear_cache(self):
        """Clear search cache."""
        self.search_cache.clear()
        self.hybrid_engine.clear_cache()
        logger.info("Search caches cleared")


# Backward compatibility
SemanticSearchService = EnhancedSemanticSearchService
SearchResult = EnhancedSearchResult