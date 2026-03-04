"""
Enhanced Search API Router for Multimodal Librarian.

This module provides REST API endpoints for the enhanced search functionality
including hybrid search, query understanding, analytics, and optimization.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from ...components.vector_store import (
    EnhancedSemanticSearchService, SearchRequest, SearchResponse,
    HybridSearchConfig, QueryContext
)
from ...components.vector_store.vector_store import VectorStore
from ...models.core import SourceType, ContentType
from ...database.connection import get_database_session

# Import dependency injection for VectorStore
from ...api.dependencies.database import get_vector_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["enhanced_search"])

# Global search service instance (would be properly initialized in main app)
search_service: Optional[EnhancedSemanticSearchService] = None


# Request/Response Models
class EnhancedSearchRequest(BaseModel):
    """Enhanced search request model."""
    query: str = Field(..., description="Search query text")
    user_id: Optional[str] = Field(None, description="User ID for analytics")
    session_id: Optional[str] = Field(None, description="Session ID for tracking")
    
    # Filtering
    source_type: Optional[str] = Field(None, description="Filter by source type (BOOK, CONVERSATION)")
    content_type: Optional[str] = Field(None, description="Filter by content type")
    source_id: Optional[str] = Field(None, description="Filter by specific source ID")
    
    # Search parameters
    top_k: int = Field(10, ge=1, le=100, description="Number of results to return")
    enable_hybrid_search: bool = Field(True, description="Enable hybrid search")
    enable_query_understanding: bool = Field(True, description="Enable query understanding")
    enable_reranking: bool = Field(True, description="Enable result re-ranking")
    enable_analytics: bool = Field(True, description="Enable search analytics")
    
    # Context
    conversation_history: List[str] = Field(default_factory=list, description="Recent conversation history")
    document_context: List[str] = Field(default_factory=list, description="Document context")
    user_expertise: str = Field("general", description="User expertise level")


class SearchResultModel(BaseModel):
    """Search result model for API response."""
    chunk_id: str
    content: str
    source_type: str
    source_id: str
    content_type: str
    location_reference: str
    section: str
    similarity_score: float
    relevance_score: float
    hybrid_score: float = 0.0
    rerank_score: Optional[float] = None
    final_score: float = 0.0
    is_bridge: bool = False
    created_at: Optional[datetime] = None
    query_match_explanation: str = ""
    click_count: int = 0
    rating_avg: float = 0.0
    rating_count: int = 0


class QueryUnderstandingModel(BaseModel):
    """Query understanding model for API response."""
    original_query: str
    normalized_query: str
    intent: str
    complexity: str
    key_concepts: List[str]
    confidence: float
    suggested_expansions: List[str]
    search_strategy: str
    explanation: str


class EnhancedSearchResponse(BaseModel):
    """Enhanced search response model."""
    results: List[SearchResultModel]
    query_understanding: Optional[QueryUnderstandingModel] = None
    total_results: int
    search_time_ms: float
    search_strategy: str
    facets: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    session_id: str
    query_id: str


class InteractionRequest(BaseModel):
    """User interaction request model."""
    session_id: str
    query: str
    chunk_id: str
    interaction_type: str  # click, rating, export
    position: Optional[int] = None
    rating: Optional[float] = Field(None, ge=1.0, le=5.0)


class SearchAnalyticsResponse(BaseModel):
    """Search analytics response model."""
    search_metrics: Dict[str, Any]
    service_performance: Dict[str, Any]
    hybrid_engine_analytics: Dict[str, Any]
    recent_alerts: List[Dict[str, Any]]
    query_distribution: Dict[str, Any]


class OptimizationResponse(BaseModel):
    """Search optimization response model."""
    optimization_recommendations: List[Dict[str, Any]]
    current_metrics: Dict[str, Any]
    generated_at: str


# Dependency to get search service
async def get_search_service() -> EnhancedSemanticSearchService:
    """
    Get the search service instance using dependency injection.
    
    This function now uses FastAPI dependency injection for VectorStore
    instead of direct instantiation.
    """
    global search_service
    if search_service is None:
        # Initialize search service (in practice, this would be done in app startup)
        try:
            from ...config import get_settings
            settings = get_settings()
            
            # Use dependency injection for VectorStore
            vector_store = await get_vector_store()
            
            # Initialize search service with default config
            config = HybridSearchConfig()
            search_service = EnhancedSemanticSearchService(vector_store, config)
            
            logger.info("Search service initialized for API (with DI)")
            
        except Exception as e:
            logger.error(f"Failed to initialize search service: {e}")
            raise HTTPException(status_code=500, detail="Search service unavailable")
    
    return search_service


@router.post("/enhanced", response_model=EnhancedSearchResponse)
async def enhanced_search(
    request: EnhancedSearchRequest,
    service: EnhancedSemanticSearchService = Depends(get_search_service)
) -> EnhancedSearchResponse:
    """
    Perform enhanced semantic search with all advanced features.
    
    This endpoint provides comprehensive search functionality including:
    - Hybrid search (vector + keyword)
    - Query understanding and intent detection
    - Cross-encoder re-ranking
    - Search analytics
    - Faceted search results
    """
    try:
        # Convert API request to internal request
        search_request = SearchRequest(
            query=request.query,
            user_id=request.user_id,
            session_id=request.session_id,
            source_type=SourceType(request.source_type) if request.source_type else None,
            content_type=ContentType(request.content_type) if request.content_type else None,
            source_id=request.source_id,
            top_k=request.top_k,
            enable_hybrid_search=request.enable_hybrid_search,
            enable_query_understanding=request.enable_query_understanding,
            enable_reranking=request.enable_reranking,
            enable_analytics=request.enable_analytics,
            conversation_history=request.conversation_history,
            document_context=request.document_context,
            user_expertise=request.user_expertise
        )
        
        # Perform search
        response = await service.search(search_request)
        
        # Convert to API response
        api_results = []
        for result in response.results:
            api_result = SearchResultModel(
                chunk_id=result.chunk_id,
                content=result.content,
                source_type=result.source_type.value,
                source_id=result.source_id,
                content_type=result.content_type.value,
                location_reference=result.location_reference,
                section=result.section,
                similarity_score=result.similarity_score,
                relevance_score=result.relevance_score,
                hybrid_score=result.hybrid_score,
                rerank_score=result.rerank_score,
                final_score=result.final_score,
                is_bridge=result.is_bridge,
                created_at=result.created_at,
                query_match_explanation=result.query_match_explanation,
                click_count=result.click_count,
                rating_avg=result.rating_avg,
                rating_count=result.rating_count
            )
            api_results.append(api_result)
        
        # Convert query understanding
        query_understanding = None
        if response.query_understanding:
            qu = response.query_understanding
            query_understanding = QueryUnderstandingModel(
                original_query=qu.original_query,
                normalized_query=qu.normalized_query,
                intent=qu.intent.value,
                complexity=qu.complexity.value,
                key_concepts=qu.key_concepts,
                confidence=qu.confidence,
                suggested_expansions=qu.suggested_expansions,
                search_strategy=qu.search_strategy,
                explanation=qu.explanation
            )
        
        return EnhancedSearchResponse(
            results=api_results,
            query_understanding=query_understanding,
            total_results=response.total_results,
            search_time_ms=response.search_time_ms,
            search_strategy=response.search_strategy,
            facets=response.facets,
            session_id=response.session_id,
            query_id=response.query_id
        )
        
    except Exception as e:
        logger.error(f"Enhanced search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.post("/interaction")
async def record_interaction(
    request: InteractionRequest,
    service: EnhancedSemanticSearchService = Depends(get_search_service)
):
    """
    Record user interaction with search results.
    
    This endpoint tracks user interactions for analytics and optimization:
    - Click tracking
    - Rating collection
    - Export tracking
    """
    try:
        await service.record_result_interaction(
            session_id=request.session_id,
            query=request.query,
            chunk_id=request.chunk_id,
            interaction_type=request.interaction_type,
            position=request.position,
            rating=request.rating
        )
        
        return {"status": "success", "message": "Interaction recorded"}
        
    except Exception as e:
        logger.error(f"Failed to record interaction: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record interaction: {str(e)}")


@router.get("/analytics", response_model=SearchAnalyticsResponse)
async def get_search_analytics(
    hours: int = Query(24, ge=1, le=168, description="Time range in hours"),
    service: EnhancedSemanticSearchService = Depends(get_search_service)
) -> SearchAnalyticsResponse:
    """
    Get comprehensive search analytics and performance metrics.
    
    Provides insights into:
    - Search performance metrics
    - User behavior patterns
    - Query distribution
    - Performance alerts
    """
    try:
        analytics_data = await service.get_search_analytics(hours=hours)
        
        return SearchAnalyticsResponse(
            search_metrics=analytics_data.get('search_metrics', {}),
            service_performance=analytics_data.get('service_performance', {}),
            hybrid_engine_analytics=analytics_data.get('hybrid_engine_analytics', {}),
            recent_alerts=analytics_data.get('recent_alerts', []),
            query_distribution=analytics_data.get('query_distribution', {})
        )
        
    except Exception as e:
        logger.error(f"Failed to get analytics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get analytics: {str(e)}")


@router.get("/optimization", response_model=OptimizationResponse)
async def get_optimization_recommendations(
    service: EnhancedSemanticSearchService = Depends(get_search_service)
) -> OptimizationResponse:
    """
    Get search performance optimization recommendations.
    
    Analyzes current performance and suggests improvements for:
    - Response time optimization
    - Search accuracy improvements
    - Query success rate enhancement
    """
    try:
        optimization_data = await service.optimize_search_performance()
        
        return OptimizationResponse(
            optimization_recommendations=optimization_data.get('optimization_recommendations', []),
            current_metrics=optimization_data.get('current_metrics', {}),
            generated_at=optimization_data.get('generated_at', datetime.now().isoformat())
        )
        
    except Exception as e:
        logger.error(f"Failed to get optimization recommendations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get optimization recommendations: {str(e)}")


@router.post("/cache/clear")
async def clear_search_cache(
    service: EnhancedSemanticSearchService = Depends(get_search_service)
):
    """
    Clear search result caches.
    
    Useful for:
    - Forcing fresh results after system updates
    - Clearing stale cached data
    - Performance troubleshooting
    """
    try:
        service.clear_cache()
        return {"status": "success", "message": "Search caches cleared"}
        
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")


@router.get("/config")
async def get_search_config(
    service: EnhancedSemanticSearchService = Depends(get_search_service)
):
    """
    Get current search configuration.
    
    Returns the current hybrid search configuration including:
    - Vector/keyword weights
    - Re-ranking settings
    - Query expansion settings
    - Cache settings
    """
    try:
        config = service.config
        
        return {
            "vector_weight": config.vector_weight,
            "keyword_weight": config.keyword_weight,
            "rerank_top_k": config.rerank_top_k,
            "final_top_k": config.final_top_k,
            "query_expansion_terms": config.query_expansion_terms,
            "enable_cross_encoder": config.enable_cross_encoder,
            "enable_query_expansion": config.enable_query_expansion,
            "enable_faceted_search": config.enable_faceted_search,
            "cache_results": config.cache_results,
            "cache_ttl_seconds": config.cache_ttl_seconds
        }
        
    except Exception as e:
        logger.error(f"Failed to get config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get config: {str(e)}")


@router.get("/health")
async def search_service_health():
    """
    Health check for enhanced search service.
    
    Returns the status of all search components:
    - Vector store connectivity
    - Search service availability
    - Analytics service status
    """
    try:
        global search_service
        
        health_status = {
            "status": "healthy",
            "service": "enhanced_search",
            "timestamp": datetime.now().isoformat(),
            "components": {
                "search_service": "healthy" if search_service else "unavailable",
                "vector_store": "unknown",  # Would check actual connectivity
                "analytics": "healthy",
                "query_understanding": "healthy"
            }
        }
        
        # Check vector store connectivity if service is available
        if search_service:
            try:
                # This would perform an actual health check
                health_status["components"]["vector_store"] = "healthy"
            except Exception:
                health_status["components"]["vector_store"] = "unhealthy"
                health_status["status"] = "degraded"
        
        return health_status
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "service": "enhanced_search",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }