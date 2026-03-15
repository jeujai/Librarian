"""
Cached RAG Service - Enhanced RAG service with comprehensive caching

This service extends the base RAG service with intelligent caching for search results,
context preparation, and AI responses to dramatically improve performance.
"""

import hashlib
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .ai_service_cached import CachedAIService
from .cache_service import CacheService, CacheType, get_cache_service
from .rag_service import CitationSource, DocumentChunk, RAGResponse, RAGService

if TYPE_CHECKING:
    from ..clients.opensearch_client import OpenSearchClient
    from ..clients.searxng_client import SearXNGClient
    from ..components.kg_retrieval.query_decomposer import QueryDecomposer
    from ..components.kg_retrieval.relevance_detector import RelevanceDetector
    from ..components.knowledge_graph.kg_builder import KnowledgeGraphBuilder
    from ..components.knowledge_graph.kg_query_engine import KnowledgeGraphQueryEngine
    from .ai_service import AIService
    from .kg_retrieval_service import KGRetrievalService

logger = logging.getLogger(__name__)

class CachedRAGService(RAGService):
    """
    Enhanced RAG service with comprehensive caching capabilities.
    
    Features:
    - Search result caching with query-based keys
    - Context preparation caching
    - Knowledge graph insights caching
    - Response caching for similar queries
    - Cache warming for common queries
    - Performance optimization through intelligent caching
    - Optional KG-guided retrieval via KGRetrievalService
    
    Requires dependency injection for all dependencies, enabling:
    - Testability through mock injection
    - Lazy initialization via FastAPI DI
    - Graceful degradation when services unavailable
    
    Usage:
        # DI pattern (required):
        cached_rag = CachedRAGService(
            opensearch_client=injected_client,
            ai_service=injected_ai_service,
            kg_retrieval_service=injected_kg_service  # Optional
        )
        
        # Via FastAPI DI (recommended):
        from api.dependencies import get_cached_rag_service
        async def endpoint(service = Depends(get_cached_rag_service)):
            ...
    """
    
    def __init__(
        self,
        vector_client: "OpenSearchClient" = None,
        ai_service: "AIService" = None,
        kg_builder: Optional["KnowledgeGraphBuilder"] = None,
        kg_query_engine: Optional["KnowledgeGraphQueryEngine"] = None,
        kg_retrieval_service: Optional["KGRetrievalService"] = None,
        cache_service: Optional[CacheService] = None,
        query_decomposer: Optional["QueryDecomposer"] = None,
        searxng_client: Optional["SearXNGClient"] = None,
        relevance_detector: Optional["RelevanceDetector"] = None,
        # Legacy parameter for backward compatibility
        opensearch_client: "OpenSearchClient" = None
    ):
        """
        Initialize cached RAG service with dependency injection.
        
        Args:
            vector_client: VectorStoreClient instance (Milvus or OpenSearch).
            ai_service: AIService instance (required).
            kg_builder: Optional KnowledgeGraphBuilder instance. If None, creates new instance.
            kg_query_engine: Optional KnowledgeGraphQueryEngine instance. If None, creates new instance.
            kg_retrieval_service: Optional KGRetrievalService for KG-guided retrieval.
                                  When provided, enables two-stage retrieval using Neo4j
                                  source_chunks for precise chunk retrieval.
            cache_service: Optional CacheService instance. If None, initializes lazily.
            query_decomposer: Optional QueryDecomposer for concept extraction.
                              Requirements: 2.1, 2.2, 2.3
            searxng_client: Optional SearXNGClient for supplementary web search.
                            When provided and enabled, web results supplement thin
                            Librarian results. Requirements: 5.3, 6.1, 6.2, 6.3
            relevance_detector: Optional RelevanceDetector for identifying irrelevant
                                results via score distribution and concept specificity
                                analysis. Requirements: 4.1, 4.2, 4.4
            opensearch_client: DEPRECATED - use vector_client instead. Kept for backward compatibility.
        """
        # Support both new vector_client and legacy opensearch_client parameter
        actual_client = vector_client or opensearch_client
        
        # Initialize base RAG service with injected dependencies
        super().__init__(
            vector_client=actual_client,
            ai_service=ai_service,
            kg_builder=kg_builder,
            kg_query_engine=kg_query_engine,
            kg_retrieval_service=kg_retrieval_service,
            query_decomposer=query_decomposer,
            searxng_client=searxng_client,
            relevance_detector=relevance_detector
        )
        
        # Cache service can be injected or initialized lazily
        self.cache_service: Optional[CacheService] = cache_service
        self._cache_initialized = cache_service is not None
        
        # Cache configuration
        self.search_cache_ttl = 3600      # 1 hour
        self.context_cache_ttl = 1800     # 30 minutes
        self.kg_insights_cache_ttl = 3600 # 1 hour
        self.response_cache_ttl = 1800    # 30 minutes
        
        # Feature flags
        self.enable_search_cache = True
        self.enable_context_cache = True
        self.enable_kg_cache = True
        self.enable_response_cache = True
        
        # Performance tracking
        self.cache_stats = {
            'search_hits': 0,
            'search_misses': 0,
            'context_hits': 0,
            'context_misses': 0,
            'kg_hits': 0,
            'kg_misses': 0,
            'response_hits': 0,
            'response_misses': 0
        }
        
        logger.info("Cached RAG service initialized")
    
    async def _ensure_cache_initialized(self):
        """Ensure cache service is initialized."""
        if not self._cache_initialized:
            try:
                self.cache_service = await get_cache_service()
                self._cache_initialized = True
                logger.info("Cache service connected for RAG operations")
            except Exception as e:
                logger.warning(f"Failed to initialize cache service: {e}")
                self.cache_service = None
    
    def _generate_search_cache_key(
        self, 
        query: str, 
        user_id: str, 
        document_filter: Optional[List[str]] = None,
        related_concepts: Optional[List[str]] = None
    ) -> str:
        """Generate cache key for search results."""
        cache_data = {
            'query': query.lower().strip(),
            'user_id': user_id,
            'document_filter': sorted(document_filter) if document_filter else None,
            'related_concepts': sorted(related_concepts) if related_concepts else None,
            'threshold': self.min_similarity_threshold,
            'max_results': self.max_search_results
        }
        
        content_hash = hashlib.sha256(
            json.dumps(cache_data, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:16]
        
        return f"search:{content_hash}"
    
    def _generate_context_cache_key(
        self, 
        chunks: List[DocumentChunk], 
        query: str
    ) -> str:
        """Generate cache key for context preparation."""
        # Create key based on chunk IDs and query
        chunk_ids = sorted([chunk.chunk_id for chunk in chunks])
        cache_data = {
            'chunk_ids': chunk_ids,
            'query': query.lower().strip(),
            'max_context_length': self.context_preparer.max_context_length
        }
        
        content_hash = hashlib.sha256(
            json.dumps(cache_data, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:16]
        
        return f"context:{content_hash}"
    
    def _generate_kg_insights_cache_key(self, query: str) -> str:
        """Generate cache key for knowledge graph insights."""
        content_hash = hashlib.sha256(
            query.lower().strip().encode()
        ).hexdigest()[:16]
        
        return f"kg_insights:{content_hash}"
    
    def _generate_response_cache_key(
        self,
        query: str,
        context: str,
        conversation_context: Optional[List[Dict[str, str]]],
        kg_metadata: Optional[Dict[str, Any]]
    ) -> str:
        """Generate cache key for RAG responses."""
        # Create simplified conversation context for caching
        simplified_context = []
        if conversation_context:
            # Only use last 3 messages for cache key
            for msg in conversation_context[-3:]:
                simplified_context.append({
                    'role': msg.get('role'),
                    'content': msg.get('content', '')[:200]  # Truncate content
                })
        
        cache_data = {
            'query': query.lower().strip(),
            'context_hash': hashlib.sha256(context.encode()).hexdigest()[:16],
            'conversation': simplified_context,
            'kg_reasoning_paths': kg_metadata.get('reasoning_paths', 0) if kg_metadata else 0,
            'kg_related_concepts': kg_metadata.get('related_concepts', 0) if kg_metadata else 0
        }
        
        content_hash = hashlib.sha256(
            json.dumps(cache_data, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()[:16]
        
        return f"rag_response:{content_hash}"
    
    async def _search_documents(
        self,
        query: str,
        user_id: str,
        document_filter: Optional[List[str]] = None,
        related_concepts: Optional[List[str]] = None,
        kg_metadata: Optional[Dict[str, Any]] = None
    ) -> List[DocumentChunk]:
        """Search for relevant document chunks with caching."""
        if not self.enable_search_cache:
            return await super()._search_documents(query, user_id, document_filter, related_concepts, kg_metadata)
        
        await self._ensure_cache_initialized()
        
        # Generate cache key
        cache_key = self._generate_search_cache_key(query, user_id, document_filter, related_concepts)
        
        # Try to get from cache
        if self.cache_service:
            try:
                cached_chunks = await self.cache_service.get(
                    CacheType.SEARCH_RESULT,
                    cache_key
                )
                
                if cached_chunks is not None:
                    self.cache_stats['search_hits'] += 1
                    logger.debug(f"Search cache hit for query: {query[:50]}...")
                    return cached_chunks
                    
            except Exception as e:
                logger.warning(f"Search cache get failed: {e}")
        
        # Cache miss - perform search
        self.cache_stats['search_misses'] += 1
        
        try:
            chunks = await super()._search_documents(query, user_id, document_filter, related_concepts, kg_metadata)
            
            # Cache the results
            if self.cache_service and chunks:
                try:
                    await self.cache_service.set(
                        CacheType.SEARCH_RESULT,
                        cache_key,
                        chunks,
                        ttl=self.search_cache_ttl
                    )
                    logger.debug(f"Cached search results for query: {query[:50]}...")
                    
                except Exception as e:
                    logger.warning(f"Search cache set failed: {e}")
            
            return chunks
            
        except Exception as e:
            logger.error(f"Document search failed: {e}")
            return []
    
    async def _prepare_context_cached(
        self, 
        chunks: List[DocumentChunk], 
        query: str
    ) -> tuple[str, List[CitationSource]]:
        """Prepare context with caching support."""
        if not self.enable_context_cache or not chunks:
            return self.context_preparer.prepare_context(chunks, query)
        
        await self._ensure_cache_initialized()
        
        # Generate cache key
        cache_key = self._generate_context_cache_key(chunks, query)
        
        # Try to get from cache
        if self.cache_service:
            try:
                cached_context = await self.cache_service.get(
                    CacheType.SEARCH_RESULT,
                    cache_key
                )
                
                if cached_context is not None:
                    self.cache_stats['context_hits'] += 1
                    logger.debug(f"Context cache hit for {len(chunks)} chunks")
                    return cached_context['context'], cached_context['citations']
                    
            except Exception as e:
                logger.warning(f"Context cache get failed: {e}")
        
        # Cache miss - prepare context
        self.cache_stats['context_misses'] += 1
        
        try:
            context, citations = self.context_preparer.prepare_context(chunks, query)
            
            # Cache the results
            if self.cache_service and context:
                try:
                    cached_data = {
                        'context': context,
                        'citations': citations
                    }
                    
                    await self.cache_service.set(
                        CacheType.SEARCH_RESULT,
                        cache_key,
                        cached_data,
                        ttl=self.context_cache_ttl
                    )
                    logger.debug(f"Cached context for {len(chunks)} chunks")
                    
                except Exception as e:
                    logger.warning(f"Context cache set failed: {e}")
            
            return context, citations
            
        except Exception as e:
            logger.error(f"Context preparation failed: {e}")
            return "", []
    
    async def get_knowledge_graph_insights(self, query: str) -> Dict[str, Any]:
        """Get knowledge graph insights with caching."""
        if not self.enable_kg_cache:
            return await super().get_knowledge_graph_insights(query)
        
        await self._ensure_cache_initialized()
        
        # Generate cache key
        cache_key = self._generate_kg_insights_cache_key(query)
        
        # Try to get from cache
        if self.cache_service:
            try:
                cached_insights = await self.cache_service.get(
                    CacheType.KNOWLEDGE_GRAPH,
                    cache_key
                )
                
                if cached_insights is not None:
                    self.cache_stats['kg_hits'] += 1
                    logger.debug(f"KG insights cache hit for query: {query[:50]}...")
                    
                    # Add cache metadata
                    cached_insights['cached'] = True
                    cached_insights['cache_hit_time'] = datetime.utcnow().isoformat()
                    
                    return cached_insights
                    
            except Exception as e:
                logger.warning(f"KG insights cache get failed: {e}")
        
        # Cache miss - generate insights
        self.cache_stats['kg_misses'] += 1
        
        try:
            insights = await super().get_knowledge_graph_insights(query)
            
            # Cache the results
            if self.cache_service and insights.get('status') == 'success':
                try:
                    # Add cache metadata
                    insights['cached'] = False
                    insights['cache_set_time'] = datetime.utcnow().isoformat()
                    
                    await self.cache_service.set(
                        CacheType.KNOWLEDGE_GRAPH,
                        cache_key,
                        insights,
                        ttl=self.kg_insights_cache_ttl
                    )
                    logger.debug(f"Cached KG insights for query: {query[:50]}...")
                    
                except Exception as e:
                    logger.warning(f"KG insights cache set failed: {e}")
            
            return insights
            
        except Exception as e:
            logger.error(f"KG insights generation failed: {e}")
            return {"status": "error", "error": str(e)}
    
    async def generate_response(
        self,
        query: str,
        user_id: str,
        conversation_context: Optional[List[Dict[str, str]]] = None,
        document_filter: Optional[List[str]] = None,
        preferred_ai_provider: Optional[str] = None
    ) -> RAGResponse:
        """Generate RAG response with comprehensive caching."""
        await self._ensure_cache_initialized()
        
        # Step 1: Process and enhance query with KG (cached)
        processed_query, related_concepts, kg_metadata = await self.query_processor.process_query(
            query, conversation_context
        )
        
        # Step 2: Search for relevant documents (cached)
        search_results = await self._search_documents(
            processed_query, user_id, document_filter, related_concepts, kg_metadata
        )
        
        # Step 3: Prepare context (cached)
        context, citations = await self._prepare_context_cached(search_results, query)
        
        # Step 4: Check for cached response
        if self.enable_response_cache and context and citations:
            cache_key = self._generate_response_cache_key(
                query, context, conversation_context, kg_metadata
            )
            
            if self.cache_service:
                try:
                    cached_response = await self.cache_service.get(
                        CacheType.AI_RESPONSE,
                        cache_key
                    )
                    
                    if cached_response is not None:
                        self.cache_stats['response_hits'] += 1
                        logger.debug(f"RAG response cache hit for query: {query[:50]}...")
                        
                        # Add cache metadata
                        cached_response.metadata = cached_response.metadata or {}
                        cached_response.metadata['cached'] = True
                        cached_response.metadata['cache_hit_time'] = datetime.utcnow().isoformat()
                        
                        return cached_response
                        
                except Exception as e:
                    logger.warning(f"RAG response cache get failed: {e}")
        
        # Cache miss - generate response using parent method
        self.cache_stats['response_misses'] += 1
        
        try:
            # Use the parent class method to generate response
            response = await super().generate_response(
                query, user_id, conversation_context, document_filter, preferred_ai_provider
            )
            
            # Cache the response if successful and not a fallback
            if (self.enable_response_cache and self.cache_service and 
                response and not response.fallback_used):
                
                try:
                    # Add cache metadata
                    response.metadata = response.metadata or {}
                    response.metadata['cached'] = False
                    response.metadata['cache_set_time'] = datetime.utcnow().isoformat()
                    
                    cache_key = self._generate_response_cache_key(
                        query, context, conversation_context, kg_metadata
                    )
                    
                    await self.cache_service.set(
                        CacheType.AI_RESPONSE,
                        cache_key,
                        response,
                        ttl=self.response_cache_ttl
                    )
                    logger.debug(f"Cached RAG response for query: {query[:50]}...")
                    
                except Exception as e:
                    logger.warning(f"RAG response cache set failed: {e}")
            
            return response
            
        except Exception as e:
            logger.error(f"RAG response generation failed: {e}")
            raise
    
    async def warm_cache(
        self,
        common_queries: List[str],
        user_id: str = "default_user"
    ) -> Dict[str, Any]:
        """
        Warm the RAG cache with common queries.
        
        Args:
            common_queries: List of common queries to pre-cache
            user_id: User ID for caching context
            
        Returns:
            Cache warming results
        """
        await self._ensure_cache_initialized()
        
        if not self.cache_service:
            return {"error": "Cache service not available"}
        
        results = {
            "queries_processed": 0,
            "search_results_cached": 0,
            "kg_insights_cached": 0,
            "responses_cached": 0,
            "errors": 0
        }
        
        for query in common_queries:
            try:
                # Pre-cache search results
                search_results = await self._search_documents(query, user_id)
                if search_results:
                    results["search_results_cached"] += 1
                
                # Pre-cache KG insights
                kg_insights = await self.get_knowledge_graph_insights(query)
                if kg_insights.get('status') == 'success':
                    results["kg_insights_cached"] += 1
                
                # Pre-cache full response
                response = await self.generate_response(query, user_id)
                if response and not response.fallback_used:
                    results["responses_cached"] += 1
                
                results["queries_processed"] += 1
                
            except Exception as e:
                logger.error(f"Cache warming failed for query '{query}': {e}")
                results["errors"] += 1
        
        logger.info(f"RAG cache warming completed: {results}")
        return results
    
    async def clear_rag_cache(self, cache_type: Optional[str] = None) -> Dict[str, int]:
        """
        Clear RAG-related cache entries.
        
        Args:
            cache_type: Type of cache to clear ('search', 'kg', 'response', or None for all)
            
        Returns:
            Dictionary with clearing results
        """
        await self._ensure_cache_initialized()
        
        if not self.cache_service:
            return {"error": "Cache service not available"}
        
        results = {"cleared": 0, "types": []}
        
        try:
            if cache_type is None or cache_type == "search":
                search_cleared = await self.cache_service.clear_by_type(CacheType.SEARCH_RESULT)
                results["cleared"] += search_cleared
                results["types"].append(f"search: {search_cleared}")
            
            if cache_type is None or cache_type == "kg":
                kg_cleared = await self.cache_service.clear_by_type(CacheType.KNOWLEDGE_GRAPH)
                results["cleared"] += kg_cleared
                results["types"].append(f"knowledge_graph: {kg_cleared}")
            
            if cache_type is None or cache_type == "response":
                response_cleared = await self.cache_service.clear_by_type(CacheType.AI_RESPONSE)
                results["cleared"] += response_cleared
                results["types"].append(f"ai_response: {response_cleared}")
            
            logger.info(f"Cleared {results['cleared']} RAG cache entries")
            
        except Exception as e:
            logger.error(f"RAG cache clearing failed: {e}")
            results["error"] = str(e)
        
        return results
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get RAG service cache statistics."""
        total_search = self.cache_stats['search_hits'] + self.cache_stats['search_misses']
        total_context = self.cache_stats['context_hits'] + self.cache_stats['context_misses']
        total_kg = self.cache_stats['kg_hits'] + self.cache_stats['kg_misses']
        total_response = self.cache_stats['response_hits'] + self.cache_stats['response_misses']
        
        return {
            "cache_enabled": {
                "search": self.enable_search_cache,
                "context": self.enable_context_cache,
                "knowledge_graph": self.enable_kg_cache,
                "response": self.enable_response_cache
            },
            "cache_initialized": self._cache_initialized,
            "search_cache": {
                "hits": self.cache_stats['search_hits'],
                "misses": self.cache_stats['search_misses'],
                "hit_rate": round(self.cache_stats['search_hits'] / max(1, total_search), 3),
                "ttl_seconds": self.search_cache_ttl
            },
            "context_cache": {
                "hits": self.cache_stats['context_hits'],
                "misses": self.cache_stats['context_misses'],
                "hit_rate": round(self.cache_stats['context_hits'] / max(1, total_context), 3),
                "ttl_seconds": self.context_cache_ttl
            },
            "knowledge_graph_cache": {
                "hits": self.cache_stats['kg_hits'],
                "misses": self.cache_stats['kg_misses'],
                "hit_rate": round(self.cache_stats['kg_hits'] / max(1, total_kg), 3),
                "ttl_seconds": self.kg_insights_cache_ttl
            },
            "response_cache": {
                "hits": self.cache_stats['response_hits'],
                "misses": self.cache_stats['response_misses'],
                "hit_rate": round(self.cache_stats['response_hits'] / max(1, total_response), 3),
                "ttl_seconds": self.response_cache_ttl
            },
            "overall_performance": {
                "total_requests": total_search + total_context + total_kg + total_response,
                "total_hits": (self.cache_stats['search_hits'] + self.cache_stats['context_hits'] + 
                              self.cache_stats['kg_hits'] + self.cache_stats['response_hits']),
                "overall_hit_rate": round(
                    (self.cache_stats['search_hits'] + self.cache_stats['context_hits'] + 
                     self.cache_stats['kg_hits'] + self.cache_stats['response_hits']) / 
                    max(1, total_search + total_context + total_kg + total_response), 3
                )
            }
        }
    
    async def get_enhanced_service_status(self) -> Dict[str, Any]:
        """Get enhanced RAG service status with cache information."""
        base_status = self.get_service_status()
        cache_stats = self.get_cache_stats()
        
        # Add cache health check
        cache_health = {"status": "disabled"}
        if self.cache_service:
            cache_health = await self.cache_service.health_check()
        
        # Get AI service cache stats
        ai_cache_stats = self.ai_service.get_cache_stats()
        
        return {
            **base_status,
            "cache_service": cache_health,
            "rag_cache_statistics": cache_stats,
            "ai_cache_statistics": ai_cache_stats,
            "enhanced_features": {
                "search_result_caching": self.enable_search_cache,
                "context_preparation_caching": self.enable_context_cache,
                "knowledge_graph_caching": self.enable_kg_cache,
                "response_caching": self.enable_response_cache,
                "cache_warming": True,
                "intelligent_cache_keys": True,
                "performance_optimization": True
            }
        }

# DEPRECATED: Module-level singleton pattern removed in favor of FastAPI DI
# Use api/dependencies/services.py get_cached_rag_service() instead
#
# Migration guide:
#   Old: from .rag_service_cached import get_cached_rag_service
#        service = get_cached_rag_service()
#
#   New: from ..api.dependencies import get_cached_rag_service
#        # In FastAPI endpoint:
#        async def endpoint(service = Depends(get_cached_rag_service)):
#            ...