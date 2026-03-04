"""
Vector Store Components for Multimodal Librarian.

This package provides comprehensive vector database functionality including:
- Vector storage and retrieval with Milvus
- Advanced semantic search with hybrid capabilities
- Query understanding and intent classification
- Search analytics and performance monitoring
- Result re-ranking and optimization
"""

from .vector_store import VectorStore, VectorStoreError
from .search_service import (
    EnhancedSemanticSearchService, SearchRequest
)
from .search_service_simple import (
    SimpleSemanticSearchService, SimpleSearchResult
)
from .hybrid_search import (
    HybridSearchEngine, HybridSearchConfig, HybridSearchResult,
    QueryExpander, CrossEncoderReranker, SearchFacets
)
from .query_understanding import (
    QueryUnderstandingEngine, UnderstoodQuery, QueryContext,
    QueryIntent, QueryComplexity, QueryEntity, QueryRelation,
    EntityExtractor, IntentClassifier, ComplexityAnalyzer
)
from .search_analytics import (
    SearchAnalyticsCollector, SearchMetricsCalculator, SearchPerformanceMonitor,
    SearchAnalyticsDashboard, SearchEvent, SearchMetrics, PerformanceAlert,
    SearchEventType
)

__all__ = [
    # Core vector store
    'VectorStore', 'VectorStoreError',
    
    # Enhanced search service
    'EnhancedSemanticSearchService', 'SearchRequest',
    
    # Simple search service
    'SimpleSemanticSearchService', 'SimpleSearchResult',
    
    # Hybrid search
    'HybridSearchEngine', 'HybridSearchConfig', 'HybridSearchResult',
    'QueryExpander', 'CrossEncoderReranker', 'SearchFacets',
    
    # Query understanding
    'QueryUnderstandingEngine', 'UnderstoodQuery', 'QueryContext',
    'QueryIntent', 'QueryComplexity', 'QueryEntity', 'QueryRelation',
    'EntityExtractor', 'IntentClassifier', 'ComplexityAnalyzer',
    
    # Search analytics
    'SearchAnalyticsCollector', 'SearchMetricsCalculator', 'SearchPerformanceMonitor',
    'SearchAnalyticsDashboard', 'SearchEvent', 'SearchMetrics', 'PerformanceAlert',
    'SearchEventType'
]