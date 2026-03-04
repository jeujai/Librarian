"""
Enhanced Semantic Search Service for Multimodal Librarian.

This module provides semantic search functionality with fallback to simple search
to avoid circular import issues during startup.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import uuid

# Import SearchResult from models to avoid circular imports
from ...models.search_types import SearchResult, SearchQuery, SearchResponse
from ...models.core import SourceType, ContentType, KnowledgeChunk
from .vector_store import VectorStore, VectorStoreError
from .vector_store_optimized import OptimizedVectorStore

logger = logging.getLogger(__name__)

# Try to enable complex search functionality
try:
    from .search_service_complex import (
        EnhancedSemanticSearchService as ComplexSearchService,
        SearchRequest as ComplexSearchRequest,
        SearchResponse as ComplexSearchResponse,
        EnhancedSearchResult as ComplexSearchResult
    )
    COMPLEX_SEARCH_AVAILABLE = True
    logger.info("Complex search functionality enabled")
except ImportError as e:
    COMPLEX_SEARCH_AVAILABLE = False
    logger.warning(f"Complex search not available, using simple search: {e}")

# Import simple search as fallback
from .search_service_simple import (
    SimpleSemanticSearchService,
    SimpleSearchResult,
    SimpleSearchRequest,
    SimpleSearchResponse
)


@dataclass
class SearchRequest:
    """Unified search request that works with both simple and complex search."""
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
    
    # Context (only used by complex search)
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
    
    def to_simple_request(self) -> SimpleSearchRequest:
        """Convert to simple search request."""
        return SimpleSearchRequest(
            query=self.query,
            user_id=self.user_id,
            session_id=self.session_id,
            source_type=self.source_type,
            content_type=self.content_type,
            source_id=self.source_id,
            top_k=self.top_k
        )
    
    def to_complex_request(self):
        """Convert to complex search request if available."""
        if not COMPLEX_SEARCH_AVAILABLE:
            return None
        
        return ComplexSearchRequest(
            query=self.query,
            user_id=self.user_id,
            session_id=self.session_id,
            source_type=self.source_type,
            content_type=self.content_type,
            source_id=self.source_id,
            top_k=self.top_k,
            enable_hybrid_search=self.enable_hybrid_search,
            enable_query_understanding=self.enable_query_understanding,
            enable_reranking=self.enable_reranking,
            enable_analytics=self.enable_analytics,
            conversation_history=self.conversation_history,
            document_context=self.document_context,
            user_expertise=self.user_expertise
        )


class EnhancedSemanticSearchService:
    """
    Unified semantic search service that uses complex search when available,
    falls back to simple search to avoid circular import issues.
    """
    
    def __init__(self, vector_store: VectorStore, config=None, use_optimized_store: bool = True):
        """
        Initialize search service with fallback capability.
        
        Args:
            vector_store: Vector database instance
            config: Search configuration (only used by complex search)
            use_optimized_store: Whether to use optimized vector store operations
        """
        # Wrap vector store with optimized version if requested
        if use_optimized_store and not isinstance(vector_store, OptimizedVectorStore):
            try:
                # Create optimized wrapper
                optimized_store = OptimizedVectorStore(vector_store.collection_name)
                optimized_store.settings = vector_store.settings
                optimized_store._connected = vector_store._connected
                optimized_store.collection = vector_store.collection
                optimized_store.embedding_model = vector_store.embedding_model
                
                # Initialize optimizer if connected
                if optimized_store._connected:
                    optimized_store.connect()
                
                self.vector_store = optimized_store
                logger.info("Using optimized vector store for enhanced performance")
                
            except Exception as e:
                logger.warning(f"Failed to create optimized vector store, using original: {e}")
                self.vector_store = vector_store
        else:
            self.vector_store = vector_store
        
        self.config = config
        
        # Initialize the appropriate search service
        if COMPLEX_SEARCH_AVAILABLE:
            try:
                self.search_service = ComplexSearchService(vector_store, config)
                self.service_type = "complex"
                logger.info("Using complex search service")
            except Exception as e:
                logger.warning(f"Failed to initialize complex search, falling back to simple: {e}")
                self.search_service = SimpleSemanticSearchService(vector_store)
                self.service_type = "simple"
        else:
            self.search_service = SimpleSemanticSearchService(vector_store)
            self.service_type = "simple"
            logger.info("Using simple search service")
    
    async def search(self, request: SearchRequest):
        """
        Perform semantic search using the available service.
        
        Args:
            request: Unified search request
            
        Returns:
            Search response with results and metadata
        """
        try:
            if self.service_type == "complex":
                # Use complex search
                complex_request = request.to_complex_request()
                if complex_request:
                    return await self.search_service.search(complex_request)
            
            # Fall back to simple search
            simple_request = request.to_simple_request()
            simple_response = await self.search_service.search(simple_request)
            
            # Convert simple response to unified format
            return self._convert_simple_response(simple_response)
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            # Return empty response on error
            return SimpleSearchResponse(
                results=[],
                search_time_ms=0.0,
                session_id=request.session_id
            )
    
    def _convert_simple_response(self, simple_response: SimpleSearchResponse):
        """Convert simple response to unified format."""
        # For now, return the simple response as-is
        # In the future, we could convert to a more complex format
        return simple_response
    
    async def record_result_interaction(
        self,
        session_id: str,
        query: str,
        chunk_id: str,
        interaction_type: str,
        position: Optional[int] = None,
        rating: Optional[float] = None
    ) -> None:
        """Record user interaction with search results."""
        try:
            if self.service_type == "complex" and hasattr(self.search_service, 'record_result_interaction'):
                await self.search_service.record_result_interaction(
                    session_id, query, chunk_id, interaction_type, position, rating
                )
            else:
                logger.debug(f"Interaction recording not available in {self.service_type} mode")
        except Exception as e:
            logger.error(f"Failed to record interaction: {e}")
    
    async def get_search_analytics(self, hours: int = 24) -> Dict[str, Any]:
        """Get search analytics and performance metrics."""
        try:
            if self.service_type == "complex" and hasattr(self.search_service, 'get_search_analytics'):
                return await self.search_service.get_search_analytics(hours)
            else:
                # Return basic stats for simple service
                return {
                    'service_type': self.service_type,
                    'performance_stats': self.search_service.get_performance_stats(),
                    'message': 'Limited analytics available in simple mode'
                }
        except Exception as e:
            logger.error(f"Failed to get analytics: {e}")
            return {'error': str(e)}
    
    def health_check(self) -> bool:
        """Check if the search service is healthy."""
        try:
            return self.search_service.health_check()
        except Exception as e:
            logger.error(f"Search service health check failed: {e}")
            return False


# Backward compatibility
SemanticSearchService = EnhancedSemanticSearchService
SearchService = EnhancedSemanticSearchService  # Backward compatibility alias

# Conditional backward compatibility for SearchResult
if COMPLEX_SEARCH_AVAILABLE:
    try:
        from .search_service_complex import EnhancedSearchResult
        SearchResult = EnhancedSearchResult
    except ImportError:
        SearchResult = SimpleSearchResult
else:
    SearchResult = SimpleSearchResult