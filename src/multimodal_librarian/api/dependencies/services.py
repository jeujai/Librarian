"""
FastAPI Dependencies for Service and Component Dependencies

This module provides FastAPI dependency injection for all service and component
dependencies, ensuring lazy initialization without blocking application startup.

This implements the DI pattern described in the dependency-injection-architecture spec,
replacing module-level singleton patterns with proper FastAPI dependencies.

================================================================================
DEPENDENCY INJECTION ARCHITECTURE
================================================================================

Key Principles:
---------------
1. NO IMPORT-TIME CONNECTIONS: Module imports must not establish database 
   connections or make network requests. All connections happen lazily.

2. LAZY INITIALIZATION: Services are created on first use via FastAPI's 
   Depends() mechanism, not at module import time.

3. GRACEFUL DEGRADATION: Optional dependencies (suffixed with _optional) 
   return None instead of raising exceptions, allowing endpoints to function
   with reduced capabilities.

4. SINGLETON CACHING: Service instances are cached at module level for 
   performance. One instance per application lifecycle.

5. PROPER CLEANUP: All connections are properly closed during application 
   shutdown via cleanup_all_dependencies().

Factory-Based Dependencies:
---------------------------
This module now supports both legacy direct client dependencies and new
factory-based dependencies that automatically select the appropriate
database implementation based on environment configuration.

**New Factory-Based Dependencies (Recommended):**
- get_database_factory() - Main factory for all database clients
- get_relational_client() - PostgreSQL (local or AWS RDS)
- get_vector_client() - Vector DB (Milvus local or OpenSearch AWS)  
- get_graph_client() - Graph DB (Neo4j local or Neptune AWS)
- get_rag_service() - RAG service using factory-based vector client
- get_cached_rag_service() - Cached RAG service with factory-based client
- get_vector_store() - VectorStore component with factory-based client

**Legacy Dependencies (Backward Compatibility):**
- get_opensearch_client() - Direct OpenSearch client (AWS only)
- get_rag_service_legacy() - RAG service with direct OpenSearch client
- get_cached_rag_service_legacy() - Cached RAG with direct OpenSearch client
- get_vector_store_legacy() - VectorStore with direct OpenSearch client

**Migration Path:**
1. New code should use factory-based dependencies for environment flexibility
2. Existing code continues to work with legacy dependencies
3. Gradually migrate endpoints from legacy to factory-based dependencies
4. Legacy dependencies will be deprecated in future versions

Usage Patterns:
---------------
1. Basic injection with factory-based client:
   ```python
   @router.post("/endpoint")
   async def my_endpoint(vector_client = Depends(get_vector_client)):
       # Works with both Milvus (local) and OpenSearch (AWS)
       return await vector_client.semantic_search(...)
   ```

2. Optional injection for graceful degradation:
   ```python
   @router.post("/endpoint")
   async def my_endpoint(service = Depends(get_ai_service_optional)):
       if service is None:
           return {"status": "service unavailable"}
       return await service.generate(...)
   ```

3. Environment-agnostic RAG service:
   ```python
   @router.post("/chat")
   async def chat_endpoint(rag_service = Depends(get_rag_service)):
       # Automatically uses Milvus (local) or OpenSearch (AWS)
       if rag_service is None:
           return {"error": "RAG service unavailable"}
       return await rag_service.query(...)
   ```

4. Legacy compatibility:
   ```python
   @router.post("/legacy-endpoint")
   async def legacy_endpoint(opensearch = Depends(get_opensearch_client)):
       # Direct OpenSearch client (AWS only)
       return await opensearch.search(...)
   ```

Testing:
--------
Use FastAPI's dependency_overrides for testing:
```python
app.dependency_overrides[get_vector_client] = lambda: mock_vector_client
app.dependency_overrides[get_database_factory] = lambda: mock_factory
```

See .kiro/steering/dependency-injection.md for complete documentation.

This module consolidates both service-level dependencies (OpenSearchClient, AIService,
RAGService) and component-level dependencies (VectorStore, SearchService, etc.) into
a single source of truth for dependency injection.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from fastapi import Depends, HTTPException, WebSocket
from fastapi.params import Depends as DependsParam

if TYPE_CHECKING:
    from ...clients.conceptnet_client import ConceptNetClient
    from ...clients.database_client_factory import DatabaseClientFactory
    from ...clients.model_server_client import ModelServerClient
    from ...clients.opensearch_client import OpenSearchClient
    from ...clients.protocols import (
        GraphStoreClient,
        RelationalStoreClient,
        VectorStoreClient,
    )
    from ...clients.searxng_client import SearXNGClient
    from ...components.conversation.conversation_manager import ConversationManager
    from ...components.export_engine.export_engine import ExportEngine
    from ...components.kg_retrieval.query_decomposer import QueryDecomposer
    from ...components.kg_retrieval.relevance_detector import RelevanceDetector
    from ...components.knowledge_graph.kg_query_engine import KnowledgeGraphQueryEngine
    from ...components.knowledge_graph.relation_type_registry import (
        RelationTypeRegistry,
    )
    from ...components.multimedia_generator.multimedia_generator import (
        MultimediaGenerator,
    )
    from ...components.query_processor.query_processor import (
        UnifiedKnowledgeQueryProcessor,
    )
    from ...components.vector_store.search_service import SemanticSearchService
    from ...components.vector_store.vector_store import VectorStore
    from ...components.yago import YagoLocalClient
    from ...logging.database_query_logger import DatabaseQueryLogger
    from ...services.active_jobs_dispatcher import ActiveJobsDispatcher
    from ...services.ai_service import AIService
    from ...services.ai_service_cached import CachedAIService
    from ...services.conversation_knowledge_service import ConversationKnowledgeService
    from ...services.enrichment_cache import EnrichmentCache
    from ...services.enrichment_service import EnrichmentService
    from ...services.kg_retrieval_service import KGRetrievalService
    from ...services.model_status_service import ModelStatusService
    from ...services.processing_status_service import ProcessingStatusService
    from ...services.rag_service import RAGService
    from ...services.rag_service_cached import CachedRAGService
    from ...services.source_prioritization_engine import SourcePrioritizationEngine

logger = logging.getLogger(__name__)

# =============================================================================
# Service-level cached instances
# =============================================================================
_opensearch_client: Optional["OpenSearchClient"] = None
_ai_service: Optional["AIService"] = None
_cached_ai_service: Optional["CachedAIService"] = None
_rag_service: Optional["RAGService"] = None
_cached_rag_service: Optional["CachedRAGService"] = None
_connection_manager: Optional["ConnectionManager"] = None
_query_logger: Optional["DatabaseQueryLogger"] = None

# =============================================================================
# Database Client Factory cached instances
# =============================================================================
_database_factory: Optional["DatabaseClientFactory"] = None
_relational_client: Optional["RelationalStoreClient"] = None
_vector_client: Optional["VectorStoreClient"] = None
_graph_client: Optional["GraphStoreClient"] = None

# =============================================================================
# Component-level cached instances (consolidated from database.py)
# =============================================================================
_vector_store_cache: Optional["VectorStore"] = None
_search_service_cache: Optional["SemanticSearchService"] = None
_conversation_manager_cache: Optional["ConversationManager"] = None
_query_processor_cache: Optional["UnifiedKnowledgeQueryProcessor"] = None
_multimedia_generator_cache: Optional["MultimediaGenerator"] = None
_export_engine_cache: Optional["ExportEngine"] = None

# =============================================================================
# Model Server Client cached instance
# =============================================================================
_model_server_client: Optional["ModelServerClient"] = None

# =============================================================================
# Model Status Service cached instance
# =============================================================================
_model_status_service: Optional["ModelStatusService"] = None

# =============================================================================
# Enrichment Service cached instances
# =============================================================================
_conceptnet_client: Optional["ConceptNetClient"] = None
_enrichment_cache: Optional["EnrichmentCache"] = None
_enrichment_service: Optional["EnrichmentService"] = None

# =============================================================================
# KG Retrieval Service cached instance
# =============================================================================
_kg_retrieval_service: Optional["KGRetrievalService"] = None

# =============================================================================
# QueryDecomposer cached instance
# =============================================================================
_query_decomposer: Optional["QueryDecomposer"] = None

# =============================================================================
# RelevanceDetector cached instance
# =============================================================================
_relevance_detector: Optional["RelevanceDetector"] = None

# =============================================================================
# NER_Extractor cached instance
# =============================================================================
_ner_extractor: Optional["NER_Extractor"] = None

# =============================================================================
# Source Prioritization Engine cached instance
# =============================================================================
_source_prioritization_engine: Optional["SourcePrioritizationEngine"] = None

# =============================================================================
# SearXNG Client cached instance
# =============================================================================
_searxng_client: Optional["SearXNGClient"] = None

# =============================================================================
# Processing Status Service cached instance
# =============================================================================
_processing_status_service: Optional["ProcessingStatusService"] = None

# =============================================================================
# Status Report Service cached instance
# =============================================================================
_status_report_service: Optional["StatusReportService"] = None

# =============================================================================
# Relation Type Registry cached instance
# =============================================================================
_relation_type_registry: Optional["RelationTypeRegistry"] = None

# =============================================================================
# Active Jobs Dispatcher cached instance
# =============================================================================
_active_jobs_dispatcher: Optional["ActiveJobsDispatcher"] = None

# =============================================================================
# Conversation Knowledge Service cached instance
# =============================================================================
_conversation_knowledge_service: Optional["ConversationKnowledgeService"] = None


# =============================================================================
# Cache Invalidation Utilities
# =============================================================================

def invalidate_rag_cache() -> dict:
    """Clear retrieval caches on RAG service singletons and KG retrieval service.

    Call this after any operation that modifies the knowledge base (document
    upload/delete, conversation-to-knowledge conversion, conversation deletion)
    so that subsequent queries do not serve stale cached results.

    Returns:
        Dict with counts of cleared entries per service.
    """
    cleared = {}
    if _rag_service is not None:
        cleared["rag_service"] = _rag_service.clear_retrieval_cache()
    if _cached_rag_service is not None:
        cleared["cached_rag_service"] = _cached_rag_service.clear_retrieval_cache()
    if _kg_retrieval_service is not None:
        cleared["kg_retrieval_service"] = _kg_retrieval_service.clear_cache()
    logger.info(f"RAG cache invalidation complete: {cleared}")
    return cleared


class ConnectionManager:
    """
    WebSocket connection manager for chat functionality.
    
    This class manages WebSocket connections and conversation state.
    It is instantiated lazily via dependency injection, not at module import time.
    """
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_threads: Dict[str, str] = {}  # connection_id -> thread_id
        self.conversation_history: Dict[str, List[Dict[str, str]]] = {}
        self._active_jobs_subscribers: Set[str] = set()  # connection IDs subscribed to active jobs updates
        
        # Services are injected separately, not in __init__
        self._rag_service: Optional["RAGService"] = None
        self._ai_service: Optional["AIService"] = None
        
        logger.info("ConnectionManager initialized (lazy, no service connections)")
    
    def set_services(
        self, 
        rag_service: Optional["RAGService"] = None, 
        ai_service: Optional["AIService"] = None
    ):
        """
        Set services after DI resolution.
        
        This allows services to be injected after the ConnectionManager
        is created, supporting the DI pattern.
        """
        self._rag_service = rag_service
        self._ai_service = ai_service
        logger.debug("ConnectionManager services updated")
    
    @property
    def rag_service(self) -> Optional["RAGService"]:
        """Get the RAG service if available."""
        return self._rag_service
    
    @property
    def ai_service(self) -> Optional["AIService"]:
        """Get the AI service if available."""
        return self._ai_service
    
    @property
    def rag_available(self) -> bool:
        """Check if RAG service is available."""
        return self._rag_service is not None
    
    async def connect(self, websocket: WebSocket, connection_id: str):
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        self.conversation_history[connection_id] = []
        logger.info(f"WebSocket connection established: {connection_id}")
    
    def disconnect(self, connection_id: str):
        """Remove a WebSocket connection."""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        if connection_id in self.user_threads:
            del self.user_threads[connection_id]
        if connection_id in self.conversation_history:
            del self.conversation_history[connection_id]
        self._active_jobs_subscribers.discard(connection_id)
        logger.info(f"WebSocket connection closed: {connection_id}")
    
    def subscribe_active_jobs(self, connection_id: str) -> None:
        """Register a connection to receive Active Jobs update messages."""
        self._active_jobs_subscribers.add(connection_id)
        logger.info(f"Connection {connection_id} subscribed to active jobs updates")

    def unsubscribe_active_jobs(self, connection_id: str) -> None:
        """Remove a connection from Active Jobs update delivery."""
        self._active_jobs_subscribers.discard(connection_id)
        logger.info(f"Connection {connection_id} unsubscribed from active jobs updates")

    def get_active_jobs_subscribers(self) -> Set[str]:
        """Return the current set of connection IDs subscribed to active jobs."""
        return set(self._active_jobs_subscribers)
    
    async def send_personal_message(self, message: dict, connection_id: str):
        """Send a message to a specific connection."""
        import json
        if connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending message to {connection_id}: {e}")
                self.disconnect(connection_id)
    
    def get_thread_id(self, connection_id: str) -> Optional[str]:
        """Get the thread ID for a connection."""
        return self.user_threads.get(connection_id)
    
    def set_thread_id(self, connection_id: str, thread_id: str):
        """Set the thread ID for a connection."""
        self.user_threads[connection_id] = thread_id
    
    def add_to_conversation_history(self, connection_id: str, role: str, content: str, citations: list = None):
        """Add message to conversation history for RAG context."""
        from datetime import datetime
        
        if connection_id not in self.conversation_history:
            self.conversation_history[connection_id] = []
        
        entry = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }
        if citations:
            entry["citations"] = citations
        
        self.conversation_history[connection_id].append(entry)
        
        # Keep only last 10 messages for context
        if len(self.conversation_history[connection_id]) > 10:
            self.conversation_history[connection_id] = self.conversation_history[connection_id][-10:]
    
    def get_conversation_context(self, connection_id: str) -> List[Dict[str, str]]:
        """Get conversation context for RAG processing."""
        return self.conversation_history.get(connection_id, [])
    
    def clear_conversation_history(self, connection_id: str):
        """Clear conversation history for a connection."""
        if connection_id in self.conversation_history:
            self.conversation_history[connection_id] = []
            logger.info(f"Conversation history cleared for {connection_id}")

    # Streaming support methods
    async def send_streaming_start(
        self,
        connection_id: str,
        citations: List[Dict[str, Any]]
    ) -> None:
        """Send streaming start notification with citations.
        
        This is sent before streaming content begins to provide
        source information upfront.
        """
        from datetime import datetime
        await self.send_personal_message({
            'type': 'streaming_start',
            'citations': citations,
            'timestamp': datetime.now().isoformat()
        }, connection_id)

    async def send_streaming_chunk(
        self,
        connection_id: str,
        content: str,
        chunk_index: int
    ) -> None:
        """Send a streaming response chunk.
        
        Args:
            connection_id: The WebSocket connection ID
            content: The partial content for this chunk
            chunk_index: The index of this chunk in the sequence
        """
        from datetime import datetime
        await self.send_personal_message({
            'type': 'response_chunk',
            'content': content,
            'chunk_index': chunk_index,
            'timestamp': datetime.now().isoformat()
        }, connection_id)

    async def send_streaming_complete(
        self,
        connection_id: str,
        metadata: Dict[str, Any]
    ) -> None:
        """Send streaming complete notification with metadata.
        
        Args:
            connection_id: The WebSocket connection ID
            metadata: Final response metadata (confidence, processing time, etc.)
        """
        from datetime import datetime
        await self.send_personal_message({
            'type': 'response_complete',
            'metadata': metadata,
            'timestamp': datetime.now().isoformat()
        }, connection_id)

    async def send_streaming_error(
        self,
        connection_id: str,
        error_message: str,
        recoverable: bool = True
    ) -> None:
        """Send streaming error notification.
        
        Args:
            connection_id: The WebSocket connection ID
            error_message: User-friendly error message
            recoverable: Whether the error is recoverable
        """
        from datetime import datetime
        await self.send_personal_message({
            'type': 'streaming_error',
            'error': error_message,
            'recoverable': recoverable,
            'timestamp': datetime.now().isoformat()
        }, connection_id)

    def is_connected(self, connection_id: str) -> bool:
        """Check if a connection is still active.
        
        Used to check if streaming should continue or be cancelled.
        """
        return connection_id in self.active_connections

    async def send_timeout_notification(
        self,
        connection_id: str,
        message: str = "Response is taking longer than expected. Please try again.",
        retry_after_seconds: Optional[float] = None
    ) -> None:
        """Send timeout notification to user.
        
        Args:
            connection_id: The WebSocket connection ID
            message: User-friendly timeout message
            retry_after_seconds: Optional suggested retry time
        """
        from datetime import datetime
        notification = {
            'type': 'timeout_notification',
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
        if retry_after_seconds is not None:
            notification['retry_after_seconds'] = retry_after_seconds
        await self.send_personal_message(notification, connection_id)


async def get_opensearch_client() -> "OpenSearchClient":
    """
    FastAPI dependency for OpenSearchClient.
    
    Lazily creates and caches the client on first use.
    Connection is established only when this dependency is resolved.
    
    IMPORTANT: The connect() call is run in a thread pool to avoid blocking
    the event loop. This is critical because SentenceTransformer model loading
    is a CPU-intensive synchronous operation that can take several seconds.
    Blocking the event loop would prevent health checks from being processed,
    causing ALB to mark the target as unhealthy.
    
    BACKWARD COMPATIBILITY: This dependency maintains the existing behavior
    for AWS environments. In the future, this may be updated to use the
    factory-based approach for consistency.
    
    Raises:
        HTTPException: If OpenSearch connection fails (503 Service Unavailable)
    
    Validates: Requirements 1.2, 1.3, 3.1
    """
    global _opensearch_client
    
    if _opensearch_client is None:
        # Import here to avoid import-time side effects
        import asyncio

        from ...clients.opensearch_client import OpenSearchClient
        
        try:
            logger.info("Initializing OpenSearchClient via DI (lazy)")
            _opensearch_client = OpenSearchClient()
            
            # Run the blocking connect() call in a thread pool to avoid
            # blocking the event loop. This is critical for health checks.
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _opensearch_client.connect)
            
            logger.info("OpenSearchClient connected successfully via DI")
        except Exception as e:
            logger.error(f"OpenSearch connection failed: {e}")
            raise HTTPException(
                status_code=503,
                detail="Vector search service unavailable. OpenSearch may still be initializing."
            )
    
    return _opensearch_client


async def get_opensearch_client_factory_based() -> "VectorStoreClient":
    """
    FastAPI dependency for OpenSearchClient using factory-based approach.
    
    This is the new factory-based approach that supports both local (Milvus)
    and AWS (OpenSearch) environments. Use this for new code that needs
    environment-agnostic vector database access.
    
    Returns:
        VectorStoreClient: Vector client for current environment
        
    Raises:
        HTTPException: If vector client creation fails (503 Service Unavailable)
        
    Validates: Requirements US-1, US-4, NFR-1
    """
    factory = await get_database_factory()
    return await factory.get_vector_client()


async def get_opensearch_client_optional() -> Optional["OpenSearchClient"]:
    """
    Optional OpenSearch client dependency - returns None if unavailable.
    
    Use this for endpoints that can function without vector search,
    enabling graceful degradation.
    
    Returns:
        OpenSearchClient instance or None if unavailable
    
    Validates: Requirements 3.5, 4.3
    """
    try:
        return await get_opensearch_client()
    except HTTPException:
        logger.warning("OpenSearch unavailable, returning None for graceful degradation")
        return None
    except Exception as e:
        logger.warning(f"OpenSearch client error, returning None: {e}")
        return None


# =============================================================================
# Model Server Client Dependencies
# =============================================================================

async def get_model_server_client() -> "ModelServerClient":
    """
    FastAPI dependency for ModelServerClient.
    
    Lazily creates and caches the model server client on first use.
    The client communicates with the dedicated model server container
    for embedding generation and NLP tasks.
    
    Returns:
        ModelServerClient instance
    
    Raises:
        HTTPException: If model server client initialization fails
    """
    global _model_server_client
    
    if _model_server_client is None:
        from ...clients.model_server_client import initialize_model_client
        
        try:
            logger.info("Initializing ModelServerClient via DI (lazy)")
            _model_server_client = await initialize_model_client()
            logger.info("ModelServerClient initialized successfully via DI")
        except Exception as e:
            logger.error(f"ModelServerClient initialization failed: {e}")
            raise HTTPException(
                status_code=503,
                detail="Model server client unavailable"
            )
    
    return _model_server_client


async def get_model_server_client_optional() -> Optional["ModelServerClient"]:
    """
    Optional model server client dependency - returns None if unavailable.
    
    Use this for endpoints that can function without the model server,
    enabling graceful degradation to local model loading.
    
    Returns:
        ModelServerClient instance or None if unavailable
    """
    try:
        return await get_model_server_client()
    except HTTPException:
        logger.warning("Model server unavailable, returning None for graceful degradation")
        return None
    except Exception as e:
        logger.warning(f"Model server client error, returning None: {e}")
        return None


# =============================================================================
# Model Status Service Dependencies
# =============================================================================

async def get_model_status_service() -> "ModelStatusService":
    """
    FastAPI dependency for ModelStatusService.
    
    Lazily creates and caches the model status service on first use.
    The service queries the model server for actual model availability
    and is the single source of truth for model status.
    
    Returns:
        ModelStatusService instance
        
    Raises:
        HTTPException: If model status service initialization fails
        
    Validates: Requirements 1.1, 1.2, 1.4
    """
    global _model_status_service
    
    if _model_status_service is None:
        from ...services.model_status_service import ModelStatusService
        
        try:
            logger.info("Initializing ModelStatusService via DI (lazy)")
            
            # Get the model server client (may be None if unavailable)
            model_client = None
            try:
                model_client = await get_model_server_client()
            except HTTPException:
                logger.warning("Model server client unavailable, ModelStatusService will report unavailable status")
            
            _model_status_service = ModelStatusService(model_client=model_client)
            
            # Do initial status fetch
            try:
                await _model_status_service.get_status(force_refresh=True)
                logger.info("ModelStatusService initial status fetch completed")
            except Exception as e:
                logger.warning(f"ModelStatusService initial status fetch failed: {e}")
            
            logger.info("ModelStatusService initialized successfully via DI")
        except Exception as e:
            logger.error(f"ModelStatusService initialization failed: {e}")
            raise HTTPException(
                status_code=503,
                detail="Model status service unavailable"
            )
    
    return _model_status_service


async def get_model_status_service_optional() -> Optional["ModelStatusService"]:
    """
    Optional model status service dependency - returns None if unavailable.
    
    Use this for endpoints that can function without model status information,
    enabling graceful degradation.
    
    Returns:
        ModelStatusService instance or None if unavailable
    """
    try:
        return await get_model_status_service()
    except HTTPException:
        logger.warning("Model status service unavailable, returning None for graceful degradation")
        return None
    except Exception as e:
        logger.warning(f"Model status service error, returning None: {e}")
        return None


# =============================================================================
# Enrichment Service Dependencies
# =============================================================================


# =============================================================================
# YAGO Local Client (YAGO Bulk Load Feature)
# =============================================================================

_yago_local_client: Optional["YagoLocalClient"] = None


async def get_yago_local_client() -> Optional["YagoLocalClient"]:
    """
    FastAPI dependency for YagoLocalClient.
    
    Lazily creates and caches the local YAGO client on first use.
    The client queries YAGO data stored in Neo4j from the bulk load.
    Returns None if YAGO data is not loaded, enabling graceful degradation.
    
    Returns:
        YagoLocalClient instance or None if YAGO data not loaded
        
    Validates: Requirement 10.4
    """
    global _yago_local_client
    
    if _yago_local_client is not None:
        return _yago_local_client
    
    # Import here to avoid import-time side effects
    from ...components.yago import YagoLocalClient
    
    try:
        # Get graph client for Neo4j connection
        from . import get_graph_client
        neo4j_client = await get_graph_client()
        
        logger.info("Initializing YagoLocalClient via DI (lazy)")
        _yago_local_client = YagoLocalClient(neo4j_client=neo4j_client)
        
        # Check if YAGO data is actually loaded
        if not await _yago_local_client.is_available():
            logger.warning("YAGO data not loaded in Neo4j, local client will return None")
            _yago_local_client = None
            return None
        
        logger.info("YagoLocalClient initialized successfully via DI")
        return _yago_local_client
        
    except HTTPException:
        logger.warning("Neo4j unavailable, YagoLocalClient returning None")
        return None
    except Exception as e:
        logger.warning(f"YagoLocalClient initialization failed: {e}, returning None")
        return None


async def get_conceptnet_client() -> "ConceptNetClient":
    """
    FastAPI dependency for ConceptNetClient.
    
    Lazily creates and caches the ConceptNet client on first use.
    The client provides async access to the ConceptNet REST API
    for retrieving commonsense knowledge relationships.
    
    Returns:
        ConceptNetClient instance
        
    Raises:
        HTTPException: If ConceptNetClient initialization fails (503 Service Unavailable)
        
    Validates: Requirements 3.1, 3.3, 3.6, 7.2
    """
    global _conceptnet_client
    
    if _conceptnet_client is None:
        # Import here to avoid import-time side effects
        from ...clients.conceptnet_client import ConceptNetClient
        
        try:
            logger.info("Initializing ConceptNetClient via DI (lazy)")
            _conceptnet_client = ConceptNetClient()
            logger.info("ConceptNetClient initialized successfully via DI")
        except Exception as e:
            logger.error(f"ConceptNetClient initialization failed: {e}")
            raise HTTPException(
                status_code=503,
                detail="ConceptNet client unavailable"
            )
    
    return _conceptnet_client


async def get_conceptnet_client_optional() -> Optional["ConceptNetClient"]:
    """
    Optional ConceptNet client dependency - returns None if unavailable.
    
    Use this for endpoints that can function without ConceptNet enrichment,
    enabling graceful degradation.
    
    Returns:
        ConceptNetClient instance or None if unavailable
    """
    try:
        return await get_conceptnet_client()
    except HTTPException:
        logger.warning("ConceptNet client unavailable, returning None for graceful degradation")
        return None
    except Exception as e:
        logger.warning(f"ConceptNet client error, returning None: {e}")
        return None


async def get_enrichment_cache() -> "EnrichmentCache":
    """
    FastAPI dependency for EnrichmentCache.
    
    Lazily creates and caches the enrichment cache on first use.
    The cache provides LRU caching with TTL for YAGO and ConceptNet
    API responses to minimize external API calls and respect rate limits.
    
    Returns:
        EnrichmentCache instance
        
    Raises:
        HTTPException: If EnrichmentCache initialization fails (503 Service Unavailable)
        
    Validates: Requirements 6.1, 6.2, 6.3, 6.4
    """
    global _enrichment_cache
    
    if _enrichment_cache is None:
        # Import here to avoid import-time side effects
        from ...services.enrichment_cache import EnrichmentCache
        
        try:
            logger.info("Initializing EnrichmentCache via DI (lazy)")
            _enrichment_cache = EnrichmentCache()
            logger.info("EnrichmentCache initialized successfully via DI")
        except Exception as e:
            logger.error(f"EnrichmentCache initialization failed: {e}")
            raise HTTPException(
                status_code=503,
                detail="Enrichment cache unavailable"
            )
    
    return _enrichment_cache


async def get_enrichment_cache_optional() -> Optional["EnrichmentCache"]:
    """
    Optional enrichment cache dependency - returns None if unavailable.
    
    Use this for endpoints that can function without caching.
    
    Returns:
        EnrichmentCache instance or None if unavailable
    """
    try:
        return await get_enrichment_cache()
    except HTTPException:
        logger.warning("Enrichment cache unavailable, returning None for graceful degradation")
        return None
    except Exception as e:
        logger.warning(f"Enrichment cache error, returning None: {e}")
        return None


async def get_enrichment_service(
    yago_client: Optional["YagoLocalClient"] = Depends(get_yago_local_client),
    conceptnet_client: Optional["ConceptNetClient"] = Depends(get_conceptnet_client_optional),
    cache: Optional["EnrichmentCache"] = Depends(get_enrichment_cache_optional)
) -> "EnrichmentService":
    """
    FastAPI dependency for EnrichmentService.
    
    Lazily creates and caches the enrichment service on first use.
    The service orchestrates YAGO and ConceptNet enrichment for concepts,
    managing caching, circuit breakers, and Neo4j persistence.
    
    Args:
        yago_client: Optional YAGO local client (injected)
        conceptnet_client: Optional ConceptNet client (injected)
        cache: Optional enrichment cache (injected)
    
    Returns:
        EnrichmentService instance
        
    Raises:
        HTTPException: If EnrichmentService initialization fails (503 Service Unavailable)
        
    Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5
    """
    global _enrichment_service
    
    if _enrichment_service is None:
        # Import here to avoid import-time side effects
        from ...services.enrichment_service import EnrichmentService
        from ...services.knowledge_graph_service import get_knowledge_graph_service
        
        try:
            logger.info("Initializing EnrichmentService via DI (lazy)")
            
            # Get knowledge graph service for Neo4j operations
            kg_service = None
            try:
                kg_service = get_knowledge_graph_service()
            except Exception as e:
                logger.warning(f"Knowledge graph service unavailable for enrichment: {e}")
            
            _enrichment_service = EnrichmentService(
                yago_client=yago_client,
                conceptnet_client=conceptnet_client,
                cache=cache,
                kg_service=kg_service
            )
            logger.info("EnrichmentService initialized successfully via DI")
        except Exception as e:
            logger.error(f"EnrichmentService initialization failed: {e}")
            raise HTTPException(
                status_code=503,
                detail="Enrichment service unavailable"
            )
    
    return _enrichment_service


async def get_enrichment_service_optional(
    yago_client: Optional["YagoLocalClient"] = Depends(get_yago_local_client),
    conceptnet_client: Optional["ConceptNetClient"] = Depends(get_conceptnet_client_optional),
    cache: Optional["EnrichmentCache"] = Depends(get_enrichment_cache_optional)
) -> Optional["EnrichmentService"]:
    """
    Optional enrichment service dependency - returns None if unavailable.
    
    Use this for endpoints that can function without enrichment capabilities,
    enabling graceful degradation.
    
    Args:
        yago_client: Optional YAGO local client (injected)
        conceptnet_client: Optional ConceptNet client (injected)
        cache: Optional enrichment cache (injected)
    
    Returns:
        EnrichmentService instance or None if unavailable
    """
    try:
        return await get_enrichment_service(yago_client, conceptnet_client, cache)
    except HTTPException:
        logger.warning("Enrichment service unavailable, returning None for graceful degradation")
        return None
    except Exception as e:
        logger.warning(f"Enrichment service error, returning None: {e}")
        return None


async def get_ai_service() -> "AIService":
    """
    FastAPI dependency for AIService.
    
    Lazily creates and caches the AI service on first use.
    No external connections are made until AI methods are called.
    
    Returns:
        AIService instance
    
    Validates: Requirements 2.1, 2.3
    """
    global _ai_service
    
    if _ai_service is None:
        # Import here to avoid import-time side effects
        from ...services.ai_service import AIService
        
        try:
            logger.info("Initializing AIService via DI (lazy)")
            _ai_service = AIService()
            logger.info("AIService initialized successfully via DI")
        except Exception as e:
            logger.error(f"AIService initialization failed: {e}")
            raise HTTPException(
                status_code=503,
                detail="AI service unavailable"
            )
    
    return _ai_service


async def get_ai_service_optional() -> Optional["AIService"]:
    """
    Optional AI service dependency - returns None if unavailable.
    
    Use this for endpoints that can function without AI capabilities.
    
    Returns:
        AIService instance or None if unavailable
    """
    try:
        return await get_ai_service()
    except HTTPException:
        logger.warning("AI service unavailable, returning None for graceful degradation")
        return None
    except Exception as e:
        logger.warning(f"AI service error, returning None: {e}")
        return None


async def get_cached_ai_service_di() -> "CachedAIService":
    """
    FastAPI dependency for CachedAIService.
    
    Lazily creates and caches the cached AI service on first use.
    This provides enhanced AI capabilities with caching for performance.
    
    Returns:
        CachedAIService instance
    
    Validates: Requirements 2.1, 2.3
    """
    global _cached_ai_service
    
    if _cached_ai_service is None:
        # Import here to avoid import-time side effects
        from ...services.ai_service_cached import CachedAIService
        
        try:
            logger.info("Initializing CachedAIService via DI (lazy)")
            _cached_ai_service = CachedAIService()
            logger.info("CachedAIService initialized successfully via DI")
        except Exception as e:
            logger.error(f"CachedAIService initialization failed: {e}")
            raise HTTPException(
                status_code=503,
                detail="Cached AI service unavailable"
            )
    
    return _cached_ai_service


async def get_cached_ai_service_optional() -> Optional["CachedAIService"]:
    """
    Optional cached AI service dependency - returns None if unavailable.
    
    Use this for endpoints that can function without cached AI capabilities.
    
    Returns:
        CachedAIService instance or None if unavailable
    """
    try:
        return await get_cached_ai_service_di()
    except HTTPException:
        logger.warning("Cached AI service unavailable, returning None for graceful degradation")
        return None
    except Exception as e:
        logger.warning(f"Cached AI service error, returning None: {e}")
        return None


# =============================================================================
# Database Client Factory Dependencies
# =============================================================================

async def get_database_factory() -> "DatabaseClientFactory":
    """
    FastAPI dependency for DatabaseClientFactory.
    
    Creates and caches a database client factory based on the current environment.
    The factory automatically detects whether to use local or AWS database clients.
    
    Returns:
        DatabaseClientFactory instance configured for current environment
        
    Raises:
        HTTPException: If factory creation fails (503 Service Unavailable)
        
    Validates: Requirements US-1, US-3, NFR-3
    """
    global _database_factory
    
    if _database_factory is None:
        # Import here to avoid import-time side effects
        from ...clients.database_client_factory import DatabaseClientFactory
        from ...config.config_factory import get_database_config
        
        try:
            logger.info("Initializing DatabaseClientFactory via DI (lazy)")
            
            # Get configuration based on environment detection
            config = get_database_config("auto")
            _database_factory = DatabaseClientFactory(config)
            
            logger.info(f"DatabaseClientFactory initialized for {config.database_type} environment")
            
        except Exception as e:
            logger.error(f"DatabaseClientFactory initialization failed: {e}")
            raise HTTPException(
                status_code=503,
                detail="Database factory service unavailable. Configuration may be invalid."
            )
    
    return _database_factory


async def get_database_factory_optional() -> Optional["DatabaseClientFactory"]:
    """
    Optional database factory dependency - returns None if unavailable.
    
    Use this for endpoints that can function without database access.
    
    Returns:
        DatabaseClientFactory instance or None if unavailable
    """
    try:
        return await get_database_factory()
    except HTTPException:
        logger.warning("Database factory unavailable, returning None for graceful degradation")
        return None
    except Exception as e:
        logger.warning(f"Database factory error, returning None: {e}")
        return None


async def get_relational_client(
    factory: "DatabaseClientFactory" = Depends(get_database_factory)
) -> "RelationalStoreClient":
    """
    FastAPI dependency for RelationalStoreClient.
    
    Returns a PostgreSQL client that works with both local and AWS environments.
    The actual implementation (LocalPostgreSQLClient or AWSPostgreSQLClient) 
    is determined by the factory based on configuration.
    
    Args:
        factory: Database client factory (injected)
        
    Returns:
        RelationalStoreClient: PostgreSQL client for current environment
        
    Raises:
        HTTPException: If client creation fails (503 Service Unavailable)
        
    Validates: Requirements US-1, US-4, NFR-1
    """
    global _relational_client
    
    if _relational_client is None:
        try:
            logger.info("Getting relational client from factory via DI")
            _relational_client = await factory.get_relational_client()
            logger.info("Relational client obtained successfully via DI")
        except Exception as e:
            logger.error(f"Failed to get relational client: {e}")
            raise HTTPException(
                status_code=503,
                detail="Relational database service unavailable"
            )
    
    return _relational_client


async def get_relational_client_optional(
    factory: Optional["DatabaseClientFactory"] = Depends(get_database_factory_optional)
) -> Optional["RelationalStoreClient"]:
    """
    Optional relational client dependency - returns None if unavailable.
    
    Use this for endpoints that can function without relational database access.
    
    Args:
        factory: Optional database client factory (injected)
        
    Returns:
        RelationalStoreClient instance or None if unavailable
    """
    if factory is None:
        return None
    
    try:
        return await factory.get_relational_client()
    except Exception as e:
        logger.warning(f"Relational client error, returning None: {e}")
        return None


async def get_vector_client(
    factory: "DatabaseClientFactory" = Depends(get_database_factory)
) -> "VectorStoreClient":
    """
    FastAPI dependency for VectorStoreClient.
    
    Returns a vector database client that works with both local and AWS environments.
    The actual implementation (MilvusClient or OpenSearchClient) is determined 
    by the factory based on configuration.
    
    Args:
        factory: Database client factory (injected)
        
    Returns:
        VectorStoreClient: Vector database client for current environment
        
    Raises:
        HTTPException: If client creation fails (503 Service Unavailable)
        
    Validates: Requirements US-1, US-4, NFR-1
    """
    global _vector_client
    
    if _vector_client is None:
        try:
            logger.info("Getting vector client from factory via DI")
            _vector_client = await factory.get_vector_client()
            logger.info("Vector client obtained successfully via DI")
        except Exception as e:
            logger.error(f"Failed to get vector client: {e}")
            raise HTTPException(
                status_code=503,
                detail="Vector database service unavailable"
            )
    
    return _vector_client


async def get_vector_client_optional(
    factory: Optional["DatabaseClientFactory"] = Depends(get_database_factory_optional)
) -> Optional["VectorStoreClient"]:
    """
    Optional vector client dependency - returns None if unavailable.
    
    Use this for endpoints that can function without vector database access.
    
    Args:
        factory: Optional database client factory (injected)
        
    Returns:
        VectorStoreClient instance or None if unavailable
    """
    # When called outside FastAPI DI, factory will be a Depends object, not a real factory
    if factory is None or isinstance(factory, DependsParam):
        try:
            factory = await get_database_factory_optional()
        except Exception:
            return None
        if factory is None:
            return None
    
    try:
        return await factory.get_vector_client()
    except Exception as e:
        logger.warning(f"Vector client error, returning None: {e}")
        return None


async def get_graph_client(
    factory: "DatabaseClientFactory" = Depends(get_database_factory)
) -> "GraphStoreClient":
    """
    FastAPI dependency for GraphStoreClient.
    
    Returns a graph database client that works with both local and AWS environments.
    The actual implementation (Neo4jClient or NeptuneClient) is determined 
    by the factory based on configuration.
    
    Args:
        factory: Database client factory (injected)
        
    Returns:
        GraphStoreClient: Graph database client for current environment
        
    Raises:
        HTTPException: If client creation fails (503 Service Unavailable)
        
    Validates: Requirements US-1, US-4, NFR-1
    """
    global _graph_client
    
    if _graph_client is None:
        try:
            logger.info("Getting graph client from factory via DI")
            _graph_client = await factory.get_graph_client()
            logger.info("Graph client obtained successfully via DI")
        except Exception as e:
            logger.error(f"Failed to get graph client: {e}")
            raise HTTPException(
                status_code=503,
                detail="Graph database service unavailable"
            )
    
    return _graph_client


async def get_graph_client_optional(
    factory: Optional["DatabaseClientFactory"] = Depends(get_database_factory_optional)
) -> Optional["GraphStoreClient"]:
    """
    Optional graph client dependency - returns None if unavailable.
    
    Use this for endpoints that can function without graph database access.
    Uses the same cached client as get_graph_client() to avoid connection issues.
    
    Args:
        factory: Optional database client factory (injected)
        
    Returns:
        GraphStoreClient instance or None if unavailable
    """
    global _graph_client
    
    if factory is None:
        return None
    
    try:
        # Use cached client if available
        if _graph_client is not None:
            # Check if connection is still valid and reconnect if needed
            if hasattr(_graph_client, '_is_connected') and not _graph_client._is_connected:
                logger.info("Graph client connection lost, reconnecting...")
                if hasattr(_graph_client, 'connect'):
                    await _graph_client.connect()
                    logger.info("Graph client reconnected successfully")
            return _graph_client
        
        # Create new client (factory.get_graph_client() is async)
        _graph_client = await factory.get_graph_client()
        logger.info("Graph client obtained successfully (optional)")
        
        return _graph_client
    except Exception as e:
        logger.warning(f"Graph client error, returning None: {e}")
        return None


# =============================================================================
# UMLS Client Dependencies
# =============================================================================
_umls_client: Optional[Any] = None


async def get_umls_client(
    graph_client: Optional["GraphStoreClient"] = Depends(
        get_graph_client_optional,
    ),
) -> Optional[Any]:
    """
    FastAPI dependency for UMLSClient.

    Lazily creates and caches the UMLS client on first use.
    The client queries UMLS data stored in Neo4j by UMLSLoader.
    Returns None if Neo4j is unavailable or UMLS data is not
    loaded, enabling graceful degradation.

    Returns:
        UMLSClient instance or None if unavailable
    """
    global _umls_client

    if _umls_client is not None:
        return _umls_client

    if graph_client is None:
        return None

    from ...components.knowledge_graph.umls_client import UMLSClient

    try:
        logger.info("Initializing UMLSClient via DI (lazy)")
        client = UMLSClient(neo4j_client=graph_client)
        await client.initialize()

        if not await client.is_available():
            logger.warning(
                "UMLS data not loaded in Neo4j, "
                "UMLSClient returning None"
            )
            return None

        _umls_client = client
        logger.info(
            "UMLSClient initialized successfully via DI"
        )
        return _umls_client

    except Exception as e:
        logger.warning(
            f"UMLSClient initialization failed: {e}, "
            "returning None"
        )
        return None


async def get_umls_client_optional() -> Optional[Any]:
    """
    Optional UMLS client dependency — returns None if unavailable.

    Convenience wrapper that catches all errors and returns None,
    suitable for endpoints that can function without UMLS data.
    """
    try:
        graph = await get_graph_client_optional()
        return await get_umls_client(graph)
    except Exception as e:
        logger.warning(
            f"UMLS client error, returning None: {e}"
        )
        return None


# =============================================================================
# KG Retrieval Service Dependencies
# =============================================================================

async def get_kg_retrieval_service(
    graph_client: Optional["GraphStoreClient"] = Depends(get_graph_client_optional),
    vector_client: Optional["VectorStoreClient"] = Depends(get_vector_client_optional),
    model_client: Optional["ModelServerClient"] = Depends(get_model_server_client_optional),
) -> "KGRetrievalService":
    """
    FastAPI dependency for KGRetrievalService.
    
    Lazily creates and caches the KG retrieval service on first use.
    The service orchestrates knowledge graph-guided retrieval using Neo4j
    for precise chunk retrieval and semantic re-ranking for relevance.
    
    This dependency implements lazy initialization to avoid blocking
    application startup (Requirement 7.3).
    
    Args:
        graph_client: Optional graph client for Neo4j operations (injected)
        vector_client: Optional vector client for chunk resolution (injected)
        model_client: Optional model client for embedding generation (injected)
    
    Returns:
        KGRetrievalService instance
        
    Raises:
        HTTPException: If KGRetrievalService initialization fails (503 Service Unavailable)
        
    Validates: Requirements 7.1, 7.3, 7.5
    """
    global _kg_retrieval_service
    
    # Resolve relevance detector here (not in signature) to avoid
    # forward-reference error — get_relevance_detector_optional is
    # defined later in this file.
    relevance_detector = await get_relevance_detector_optional()
    
    if _kg_retrieval_service is None:
        # Import here to avoid import-time side effects
        from ...services.kg_retrieval_service import KGRetrievalService
        
        try:
            logger.info("Initializing KGRetrievalService via DI (lazy)")
            
            _kg_retrieval_service = KGRetrievalService(
                neo4j_client=graph_client,
                vector_client=vector_client,
                model_client=model_client,
                relevance_detector=relevance_detector,
            )
            
            logger.info("KGRetrievalService initialized successfully via DI")
        except Exception as e:
            logger.error(f"KGRetrievalService initialization failed: {e}")
            raise HTTPException(
                status_code=503,
                detail="KG retrieval service unavailable"
            )
    else:
        # Always update clients to ensure fresh connections are used
        # This handles cases where connections were lost and re-established
        if graph_client is not None:
            _kg_retrieval_service.set_neo4j_client(graph_client)
        if vector_client is not None:
            _kg_retrieval_service.set_vector_client(vector_client)
        if model_client is not None:
            _kg_retrieval_service.set_model_client(model_client)
    
    return _kg_retrieval_service


async def get_kg_retrieval_service_optional(
    graph_client: Optional["GraphStoreClient"] = Depends(get_graph_client_optional),
    vector_client: Optional["VectorStoreClient"] = Depends(get_vector_client_optional),
    model_client: Optional["ModelServerClient"] = Depends(get_model_server_client_optional),
) -> Optional["KGRetrievalService"]:
    """
    Optional KG retrieval service dependency - returns None if unavailable.
    
    Use this for endpoints that can function without KG-guided retrieval,
    enabling graceful degradation to pure semantic search.
    
    This is the recommended dependency for RAGService integration, as it
    allows the RAG service to continue functioning with existing semantic
    search when KG retrieval is unavailable (Requirement 7.4).
    
    Args:
        graph_client: Optional graph client for Neo4j operations (injected)
        vector_client: Optional vector client for chunk resolution (injected)
        model_client: Optional model client for embedding generation (injected)
    
    Returns:
        KGRetrievalService instance or None if unavailable
        
    Validates: Requirements 7.1, 7.4
    """
    try:
        return await get_kg_retrieval_service(graph_client, vector_client, model_client)
    except HTTPException:
        logger.warning(
            "KG retrieval service unavailable, returning None for graceful degradation"
        )
        return None
    except Exception as e:
        logger.warning(f"KG retrieval service error, returning None: {e}")
        return None


# =============================================================================
# NER_Extractor Dependencies
# =============================================================================

async def get_ner_extractor(
    umls_client: Optional[Any] = Depends(get_umls_client_optional),
) -> Optional["NER_Extractor"]:
    """
    FastAPI dependency for NER_Extractor.

    Lazily creates and caches the NER_Extractor with:
    - en_core_web_sm for Layer 1 (Base)
    - en_core_sci_sm for Layer 2 (Scientific)
    - Optional UMLSClient for Layer 3 (Medical Precision)

    Each model loads independently — failure of one does not
    prevent the others from loading.

    Args:
        umls_client: Optional UMLS client for Layer 3 refinement (injected)

    Returns:
        NER_Extractor instance (may have None for failed models).

    Validates: Requirements 7.1, 6.1, 6.2, 6.6
    """
    global _ner_extractor

    if _ner_extractor is not None:
        return _ner_extractor

    from ...components.kg_retrieval.ner_extractor import NER_Extractor

    # Load en_core_web_sm (Layer 1) — independent
    spacy_web_nlp = None
    try:
        import spacy
        spacy_web_nlp = spacy.load("en_core_web_sm")
        logger.info("Layer 1: en_core_web_sm loaded for NER_Extractor")
    except Exception as web_err:
        logger.warning(
            "Layer 1: en_core_web_sm unavailable (%s), Layer 1 disabled",
            web_err,
        )

    # Load en_core_sci_sm (Layer 2) — independent
    spacy_sci_nlp = None
    try:
        import spacy
        spacy_sci_nlp = spacy.load("en_core_sci_sm")
        logger.info("Layer 2: en_core_sci_sm loaded for NER_Extractor")
    except Exception as sci_err:
        logger.warning(
            "Layer 2: en_core_sci_sm unavailable (%s), Layer 2 disabled",
            sci_err,
        )

    if spacy_web_nlp is None and spacy_sci_nlp is None:
        logger.error(
            "Both en_core_web_sm and en_core_sci_sm failed to load. "
            "Only UMLS Layer 3 available (if configured)."
        )

    _ner_extractor = NER_Extractor(
        spacy_web_nlp=spacy_web_nlp,
        spacy_sci_nlp=spacy_sci_nlp,
        umls_client=umls_client,
    )
    return _ner_extractor


# =============================================================================
# QueryDecomposer Dependencies
# =============================================================================

async def get_query_decomposer_optional(
    graph_client: Optional["GraphStoreClient"] = Depends(get_graph_client_optional),
    model_client: Optional["ModelServerClient"] = Depends(get_model_server_client_optional),
    ner_extractor: Optional["NER_Extractor"] = Depends(get_ner_extractor),
) -> Optional["QueryDecomposer"]:
    """
    Optional QueryDecomposer dependency - returns None if unavailable.

    Lazily creates and caches a QueryDecomposer instance using the graph client
    (Neo4j) for lexical matching and the model server client for semantic matching.
    Returns None if dependencies are unavailable, enabling graceful degradation
    to pure semantic search in the RAG pipeline.

    Args:
        graph_client: Optional graph client for Neo4j concept lookups (injected)
        model_client: Optional model server client for embedding generation (injected)
        ner_extractor: Optional NER_Extractor for entity-aware query tokenization (injected)

    Returns:
        QueryDecomposer instance or None if unavailable

    Validates: Requirements 2.4, 2.5, 8.1
    """
    global _query_decomposer

    if _query_decomposer is None:
        from ...components.kg_retrieval.query_decomposer import QueryDecomposer

        try:
            logger.info("Initializing QueryDecomposer via DI (lazy)")

            _query_decomposer = QueryDecomposer(
                neo4j_client=graph_client,
                model_server_client=model_client,
                ner_extractor=ner_extractor,
            )

            logger.info("QueryDecomposer initialized successfully via DI")
        except Exception as e:
            logger.warning(f"QueryDecomposer initialization failed: {e}")
            return None
    else:
        # Update clients to ensure fresh connections are used
        if graph_client is not None:
            _query_decomposer.set_neo4j_client(graph_client)
        if model_client is not None:
            _query_decomposer.set_model_server_client(model_client)

    return _query_decomposer


# =============================================================================
# RelevanceDetector Dependencies
# =============================================================================

async def get_relevance_detector(
    ner_extractor: Optional["NER_Extractor"] = Depends(get_ner_extractor),
) -> "RelevanceDetector":
    """
    FastAPI dependency for RelevanceDetector.

    Lazily creates and caches the RelevanceDetector on first use.
    Reads spread, variance, and specificity thresholds from application
    settings (environment-overridable via Pydantic config).

    Uses the NER_Extractor's ``spacy_web_nlp`` model for backward-compatible
    NER-based proper-noun extraction, and passes the full NER_Extractor
    for three-layer concurrent extraction in ``filter_chunks_by_proper_nouns``.

    Args:
        ner_extractor: Optional NER_Extractor with pre-loaded spaCy models
                      and optional UMLS client (injected via DI).

    Returns:
        RelevanceDetector instance

    Raises:
        HTTPException: If initialization fails (503 Service Unavailable)

    Validates: Requirements 6.1, 6.2, 6.3, 7.1
    """
    global _relevance_detector

    if _relevance_detector is None:
        from ...components.kg_retrieval.relevance_detector import RelevanceDetector
        from ...config.config import get_settings

        try:
            settings = get_settings()

            # Use NER_Extractor's web model for backward compatibility;
            # fall back to loading en_core_web_sm directly if NER_Extractor
            # is unavailable.
            spacy_nlp = None
            if ner_extractor is not None:
                spacy_nlp = ner_extractor.spacy_web_nlp
                if spacy_nlp is not None:
                    logger.info(
                        "RelevanceDetector using NER_Extractor's "
                        "en_core_web_sm model"
                    )
                else:
                    logger.warning(
                        "NER_Extractor has no en_core_web_sm model, "
                        "query term coverage signal may be limited"
                    )
            else:
                try:
                    import spacy
                    spacy_nlp = spacy.load("en_core_web_sm")
                    logger.info(
                        "spaCy en_core_web_sm loaded directly for "
                        "RelevanceDetector NER (NER_Extractor unavailable)"
                    )
                except Exception as spacy_err:
                    logger.warning(
                        "spaCy model unavailable, query term "
                        "coverage signal disabled: %s",
                        spacy_err,
                    )

            logger.info(
                "Initializing RelevanceDetector via DI (lazy)"
            )
            _relevance_detector = RelevanceDetector(
                spread_threshold=settings.relevance_spread_threshold,
                variance_threshold=settings.relevance_variance_threshold,
                specificity_threshold=settings.relevance_specificity_threshold,
                spacy_nlp=spacy_nlp,
                base_threshold_floor=settings.adaptive_threshold_floor,
                medical_threshold=settings.adaptive_medical_threshold,
                legal_threshold=settings.adaptive_legal_threshold,
                small_query_noun_limit=settings.adaptive_small_query_noun_limit,
                ner_extractor=ner_extractor,
            )
            logger.info(
                "RelevanceDetector initialized successfully via DI"
            )
        except Exception as e:
            logger.error(
                f"RelevanceDetector initialization failed: {e}"
            )
            raise HTTPException(
                status_code=503,
                detail="Relevance detector unavailable",
            )

    return _relevance_detector


async def get_relevance_detector_optional() -> Optional["RelevanceDetector"]:
    """
    Optional RelevanceDetector dependency — returns None if unavailable.

    Use this for endpoints and services that can function without
    relevance detection, enabling graceful degradation.

    Returns:
        RelevanceDetector instance or None if unavailable

    Validates: Requirements 6.1, 6.2, 6.3
    """
    try:
        return await get_relevance_detector()
    except HTTPException:
        logger.debug(
            "RelevanceDetector unavailable, returning None "
            "for graceful degradation"
        )
        return None
    except Exception as e:
        logger.warning(
            f"RelevanceDetector error, returning None: {e}"
        )
        return None


# =============================================================================
# Source Prioritization Engine Dependencies
# =============================================================================

async def get_source_prioritization_engine(
    vector_client: Optional["VectorStoreClient"] = Depends(get_vector_client_optional)
) -> "SourcePrioritizationEngine":
    """
    FastAPI dependency for SourcePrioritizationEngine.
    
    Lazily creates and caches the source prioritization engine on first use.
    The engine prioritizes Librarian documents over external sources in RAG retrieval.
    
    Args:
        vector_client: Vector client for document search (injected)
    
    Returns:
        SourcePrioritizationEngine instance
        
    Raises:
        HTTPException: If vector client is unavailable (503 Service Unavailable)
        
    Validates: Requirements 5.1, 5.5, 5.6
    """
    global _source_prioritization_engine
    
    if vector_client is None:
        raise HTTPException(
            status_code=503,
            detail="Source prioritization engine unavailable - vector client not connected"
        )
    
    if _source_prioritization_engine is None:
        # Import here to avoid import-time side effects
        from ...services.source_prioritization_engine import SourcePrioritizationEngine
        
        try:
            logger.info("Initializing SourcePrioritizationEngine via DI (lazy)")
            
            _source_prioritization_engine = SourcePrioritizationEngine(
                vector_client=vector_client,
                librarian_boost_factor=1.5,  # 50% boost for Librarian documents
                min_confidence_threshold=0.35
            )
            
            logger.info("SourcePrioritizationEngine initialized successfully via DI")
        except Exception as e:
            logger.error(f"SourcePrioritizationEngine initialization failed: {e}")
            raise HTTPException(
                status_code=503,
                detail="Source prioritization engine unavailable"
            )
    
    return _source_prioritization_engine


async def get_source_prioritization_engine_optional(
    vector_client: Optional["VectorStoreClient"] = Depends(get_vector_client_optional)
) -> Optional["SourcePrioritizationEngine"]:
    """
    Optional source prioritization engine dependency - returns None if unavailable.
    
    Use this for endpoints that can function without source prioritization,
    enabling graceful degradation to standard semantic search.
    
    This is the recommended dependency for RAGService integration, as it
    allows the RAG service to continue functioning with existing semantic
    search when source prioritization is unavailable.
    
    Args:
        vector_client: Optional vector client for document search (injected)
    
    Returns:
        SourcePrioritizationEngine instance or None if unavailable
        
    Validates: Requirements 5.1, 5.5, 5.6
    """
    try:
        return await get_source_prioritization_engine(vector_client)
    except HTTPException:
        logger.warning(
            "Source prioritization engine unavailable, returning None for graceful degradation"
        )
        return None
    except Exception as e:
        logger.warning(f"Source prioritization engine error, returning None: {e}")
        return None


# =============================================================================
# SearXNG Client Dependencies
# =============================================================================


async def get_searxng_client() -> "SearXNGClient":
    """
    FastAPI dependency for SearXNGClient.

    Lazily creates and caches the SearXNG client on first use.
    Raises HTTPException 503 when SearXNG is disabled via configuration.

    Returns:
        SearXNGClient instance

    Raises:
        HTTPException: If SearXNG is disabled (503 Service Unavailable)

    Validates: Requirements 5.4
    """
    global _searxng_client

    if _searxng_client is None:
        from ...clients.searxng_client import SearXNGClient
        from ...config.config import get_settings

        settings = get_settings()

        if not settings.searxng_enabled:
            raise HTTPException(
                status_code=503,
                detail="SearXNG web search is disabled",
            )

        try:
            logger.info("Initializing SearXNGClient via DI (lazy)")
            _searxng_client = SearXNGClient(
                host=settings.searxng_host,
                port=settings.searxng_port,
                timeout=settings.searxng_timeout,
            )
            logger.info("SearXNGClient initialized successfully via DI")
        except Exception as e:
            logger.error(f"SearXNGClient initialization failed: {e}")
            raise HTTPException(
                status_code=503,
                detail="SearXNG client unavailable",
            )

    return _searxng_client


async def get_searxng_client_optional() -> Optional["SearXNGClient"]:
    """
    Optional SearXNG client dependency - returns None if unavailable or disabled.

    Use this for endpoints that can function without web search,
    enabling graceful degradation.

    Returns:
        SearXNGClient instance or None if unavailable/disabled

    Validates: Requirements 5.5
    """
    try:
        return await get_searxng_client()
    except HTTPException:
        logger.debug(
            "SearXNG client unavailable or disabled, returning None for graceful degradation"
        )
        return None
    except Exception as e:
        logger.warning(f"SearXNG client error, returning None: {e}")
        return None


async def get_rag_service(
    vector_client: Optional["VectorStoreClient"] = Depends(get_vector_client_optional),
    ai_service: "AIService" = Depends(get_ai_service),
    kg_retrieval_service: Optional["KGRetrievalService"] = Depends(get_kg_retrieval_service_optional),
    source_prioritization_engine: Optional["SourcePrioritizationEngine"] = Depends(get_source_prioritization_engine_optional),
    query_decomposer: Optional["QueryDecomposer"] = Depends(get_query_decomposer_optional),
    searxng_client: Optional["SearXNGClient"] = Depends(get_searxng_client_optional),
    relevance_detector: Optional["RelevanceDetector"] = Depends(get_relevance_detector_optional)
) -> Optional["RAGService"]:
    """
    FastAPI dependency for RAGService using factory-based vector client.
    
    Returns None if vector client is unavailable, enabling graceful degradation.
    The RAG service requires both vector database and AI service to function fully.
    
    This version uses the factory-based vector client, which automatically
    selects the appropriate implementation (Milvus for local, OpenSearch for AWS)
    based on the current environment configuration.
    
    When KGRetrievalService is available, it is injected into RAGService to enable
    KG-guided retrieval using Neo4j source_chunks for precise chunk retrieval.
    If KGRetrievalService is unavailable, RAGService continues to function with
    existing semantic search (graceful degradation per Requirement 7.4).
    
    When SourcePrioritizationEngine is available, it is injected into RAGService
    to enable source prioritization that boosts Librarian documents over external
    sources (Requirements 5.1, 5.5, 5.6).
    
    When QueryDecomposer is available, it is injected into RAGService to replace
    the legacy KG_Query_Engine concept extraction path (Requirements 2.1-2.5).
    
    When SearXNGClient is available, it is injected into RAGService to enable
    supplementary web search when Librarian results are below the configured
    threshold (Requirements 5.3, 5.4, 5.5).
    
    When RelevanceDetector is available, it is injected into RAGService to enable
    detection of irrelevant results via score distribution and concept specificity
    analysis (Requirements 4.1, 4.2, 4.4).
    
    Args:
        vector_client: Optional vector client from factory (injected)
        ai_service: AI service (injected)
        kg_retrieval_service: Optional KG retrieval service for KG-guided retrieval (injected)
        source_prioritization_engine: Optional source prioritization engine (injected)
        query_decomposer: Optional QueryDecomposer for concept extraction (injected)
        searxng_client: Optional SearXNG client for web search (injected)
        relevance_detector: Optional RelevanceDetector for relevance analysis (injected)
    
    Returns:
        RAGService instance or None if vector client unavailable
    
    Validates: Requirements 2.1, 2.4, 3.5, 4.3, 5.1, 5.3, 5.4, 5.5, 5.6, 7.1, 7.2, US-1, US-4
    """
    global _rag_service
    
    if vector_client is None:
        logger.info("RAG service unavailable - vector client not connected")
        return None
    
    if _rag_service is None:
        # Import here to avoid import-time side effects
        from ...services.rag_service import RAGService
        
        try:
            features = []
            if kg_retrieval_service:
                features.append("KG-guided retrieval")
            if source_prioritization_engine:
                features.append("source prioritization")
            if query_decomposer:
                features.append("QueryDecomposer")
            if searxng_client:
                features.append("SearXNG web search")
            if relevance_detector:
                features.append("relevance detection")
            feature_status = f"with {', '.join(features)}" if features else "without optional features"
            
            logger.info(f"Initializing RAGService via DI (lazy) {feature_status}")
            
            # Use the factory-based vector client and optionally inject services
            _rag_service = RAGService(
                vector_client=vector_client,
                ai_service=ai_service,
                kg_retrieval_service=kg_retrieval_service,
                source_prioritization_engine=source_prioritization_engine,
                query_decomposer=query_decomposer,
                searxng_client=searxng_client,
                relevance_detector=relevance_detector
            )
            logger.info(f"RAGService initialized successfully via DI {feature_status}")
        except Exception as e:
            logger.error(f"RAGService initialization failed: {e}")
            return None
    else:
        # Update services if they become available after initial creation
        # This supports dynamic service injection
        if kg_retrieval_service is not None and not _rag_service.use_kg_retrieval:
            _rag_service.kg_retrieval_service = kg_retrieval_service
            _rag_service.use_kg_retrieval = True
            logger.info("RAGService updated with KG-guided retrieval service")
        
        if source_prioritization_engine is not None and not _rag_service.use_source_prioritization:
            _rag_service.source_prioritization_engine = source_prioritization_engine
            _rag_service.use_source_prioritization = True
            logger.info("RAGService updated with source prioritization engine")
        
        if query_decomposer is not None and _rag_service.query_decomposer is None:
            _rag_service.query_decomposer = query_decomposer
            _rag_service.query_processor.query_decomposer = query_decomposer
            logger.info("RAGService updated with QueryDecomposer")
        
        if searxng_client is not None and not _rag_service.searxng_enabled:
            _rag_service.searxng_client = searxng_client
            _rag_service.searxng_enabled = True
            logger.info("RAGService updated with SearXNG web search client")
        
        if relevance_detector is not None and _rag_service.relevance_detector is None:
            _rag_service.relevance_detector = relevance_detector
            logger.info("RAGService updated with RelevanceDetector")
    
    return _rag_service


async def get_rag_service_legacy(
    opensearch: Optional["OpenSearchClient"] = Depends(get_opensearch_client_optional),
    ai_service: "AIService" = Depends(get_ai_service),
    query_decomposer: Optional["QueryDecomposer"] = Depends(get_query_decomposer_optional)
) -> Optional["RAGService"]:
    """
    Legacy FastAPI dependency for RAGService using direct OpenSearch client.
    
    This is the original implementation that directly uses OpenSearchClient.
    It's maintained for backward compatibility with existing code.
    
    DEPRECATED: Use get_rag_service() for new code, which uses the factory-based
    approach and supports both local and AWS environments.
    
    Args:
        opensearch: Optional OpenSearch client (injected)
        ai_service: AI service (injected)
        query_decomposer: Optional QueryDecomposer for concept extraction (injected)
    
    Returns:
        RAGService instance or None if OpenSearch unavailable
    
    Validates: Requirements 2.1, 2.4, 3.5, 4.3
    """
    if opensearch is None:
        logger.info("RAG service unavailable - OpenSearch not connected")
        return None
    
    # Import here to avoid import-time side effects
    from ...services.rag_service import RAGService
    
    try:
        logger.info("Initializing RAGService via DI (lazy) with legacy OpenSearch client")
        # Use the legacy constructor with OpenSearch client
        rag_service = RAGService(
            opensearch_client=opensearch,
            ai_service=ai_service,
            query_decomposer=query_decomposer
        )
        logger.info("RAGService initialized successfully via DI with legacy client")
        return rag_service
    except Exception as e:
        logger.error(f"RAGService initialization failed: {e}")
        return None


async def get_cached_rag_service(
    vector_client: Optional["VectorStoreClient"] = Depends(get_vector_client_optional),
    ai_service: "AIService" = Depends(get_ai_service),
    kg_retrieval_service: Optional["KGRetrievalService"] = Depends(get_kg_retrieval_service_optional),
    query_decomposer: Optional["QueryDecomposer"] = Depends(get_query_decomposer_optional),
    searxng_client: Optional["SearXNGClient"] = Depends(get_searxng_client_optional),
    relevance_detector: Optional["RelevanceDetector"] = Depends(get_relevance_detector_optional)
) -> Optional["CachedRAGService"]:
    """
    FastAPI dependency for CachedRAGService using factory-based vector client.
    
    Returns the cached version of RAG service with performance optimizations.
    Returns None if vector client is unavailable.
    
    This version uses the factory-based vector client, which automatically
    selects the appropriate implementation (Milvus for local, OpenSearch for AWS)
    based on the current environment configuration.
    
    When KGRetrievalService is available, it is injected into CachedRAGService to enable
    KG-guided retrieval using Neo4j source_chunks for precise chunk retrieval.
    If KGRetrievalService is unavailable, CachedRAGService continues to function with
    existing semantic search (graceful degradation per Requirement 7.4).
    
    When QueryDecomposer is available, it is injected into CachedRAGService to replace
    the legacy KG_Query_Engine concept extraction path (Requirements 2.1-2.5).
    
    Args:
        vector_client: Optional vector client from factory (injected)
        ai_service: AI service (injected)
        kg_retrieval_service: Optional KG retrieval service for KG-guided retrieval (injected)
        query_decomposer: Optional QueryDecomposer for concept extraction (injected)
        relevance_detector: Optional RelevanceDetector for relevance detection (injected)
    
    Returns:
        CachedRAGService instance or None if vector client unavailable
    
    Validates: Requirements 2.1, 2.4, 3.5, 4.3, 7.1, 7.2, US-1, US-4
    """
    global _cached_rag_service
    
    if vector_client is None:
        logger.info("Cached RAG service unavailable - vector client not connected")
        return None
    
    if _cached_rag_service is None:
        # Import here to avoid import-time side effects
        from ...services.rag_service_cached import CachedRAGService
        
        try:
            features = []
            if kg_retrieval_service:
                features.append("KG-guided retrieval")
            if query_decomposer:
                features.append("QueryDecomposer")
            if searxng_client:
                features.append("SearXNG web search")
            if relevance_detector:
                features.append("relevance detection")
            feature_status = f"with {', '.join(features)}" if features else "without optional features"
            logger.info(f"Initializing CachedRAGService via DI (lazy) {feature_status}")
            
            # Use the factory-based vector client and optionally inject services
            _cached_rag_service = CachedRAGService(
                vector_client=vector_client,
                ai_service=ai_service,
                kg_retrieval_service=kg_retrieval_service,
                query_decomposer=query_decomposer,
                searxng_client=searxng_client,
                relevance_detector=relevance_detector
            )
            logger.info(f"CachedRAGService initialized successfully via DI {feature_status}")
        except Exception as e:
            logger.error(f"CachedRAGService initialization failed: {e}")
            return None
    else:
        # Update services if they become available after initial creation
        # This supports dynamic service injection (Requirement 7.2)
        if kg_retrieval_service is not None and not _cached_rag_service.use_kg_retrieval:
            _cached_rag_service.kg_retrieval_service = kg_retrieval_service
            _cached_rag_service.use_kg_retrieval = True
            logger.info("CachedRAGService updated with KG-guided retrieval service")
        
        if query_decomposer is not None and _cached_rag_service.query_decomposer is None:
            _cached_rag_service.query_decomposer = query_decomposer
            _cached_rag_service.query_processor.query_decomposer = query_decomposer
            logger.info("CachedRAGService updated with QueryDecomposer")
        
        if searxng_client is not None and not _cached_rag_service.searxng_enabled:
            _cached_rag_service.searxng_client = searxng_client
            _cached_rag_service.searxng_enabled = True
            logger.info("CachedRAGService updated with SearXNG web search client")
        
        if relevance_detector is not None and _cached_rag_service.relevance_detector is None:
            _cached_rag_service.relevance_detector = relevance_detector
            logger.info("CachedRAGService updated with RelevanceDetector")
    
    return _cached_rag_service


async def get_cached_rag_service_legacy(
    opensearch: Optional["OpenSearchClient"] = Depends(get_opensearch_client_optional),
    ai_service: "AIService" = Depends(get_ai_service),
    query_decomposer: Optional["QueryDecomposer"] = Depends(get_query_decomposer_optional)
) -> Optional["CachedRAGService"]:
    """
    Legacy FastAPI dependency for CachedRAGService using direct OpenSearch client.
    
    This is the original implementation that directly uses OpenSearchClient.
    It's maintained for backward compatibility with existing code.
    
    DEPRECATED: Use get_cached_rag_service() for new code, which uses the 
    factory-based approach and supports both local and AWS environments.
    
    Args:
        opensearch: Optional OpenSearch client (injected)
        ai_service: AI service (injected)
        query_decomposer: Optional QueryDecomposer for concept extraction (injected)
    
    Returns:
        CachedRAGService instance or None if OpenSearch unavailable
    
    Validates: Requirements 2.1, 2.4, 3.5, 4.3
    """
    if opensearch is None:
        logger.info("Cached RAG service unavailable - OpenSearch not connected")
        return None
    
    # Import here to avoid import-time side effects
    from ...services.rag_service_cached import CachedRAGService
    
    try:
        logger.info("Initializing CachedRAGService via DI (lazy) with legacy OpenSearch client")
        # Use the legacy constructor with OpenSearch client
        cached_rag_service = CachedRAGService(
            opensearch_client=opensearch,
            ai_service=ai_service,
            query_decomposer=query_decomposer
        )
        logger.info("CachedRAGService initialized successfully via DI with legacy client")
        return cached_rag_service
    except Exception as e:
        logger.error(f"CachedRAGService initialization failed: {e}")
        return None


async def get_connection_manager() -> "ConnectionManager":
    """
    FastAPI dependency for ConnectionManager.
    
    Provides a singleton ConnectionManager instance for WebSocket management.
    The manager is created without any service connections - services are
    injected separately when needed.
    
    Returns:
        ConnectionManager instance
    
    Validates: Requirements 2.2, 4.1, 4.2
    """
    global _connection_manager
    
    if _connection_manager is None:
        logger.info("Initializing ConnectionManager via DI (lazy)")
        _connection_manager = ConnectionManager()
        logger.info("ConnectionManager initialized successfully via DI")
    
    return _connection_manager


async def get_connection_manager_with_services(
    rag_service: Optional["RAGService"] = Depends(get_cached_rag_service),
    ai_service: Optional["AIService"] = Depends(get_ai_service_optional)
) -> "ConnectionManager":
    """
    FastAPI dependency for ConnectionManager with services injected.
    
    This variant injects RAG and AI services into the connection manager,
    useful for WebSocket endpoints that need full functionality.
    
    Args:
        rag_service: Optional RAG service (injected)
        ai_service: Optional AI service (injected)
    
    Returns:
        ConnectionManager instance with services configured
    
    Validates: Requirements 4.1, 4.2, 4.3, 4.4
    """
    logger.info(f"get_connection_manager_with_services called - RAG: {rag_service is not None}, AI: {ai_service is not None}")
    manager = await get_connection_manager()
    manager.set_services(rag_service=rag_service, ai_service=ai_service)
    logger.info(f"ConnectionManager services set - rag_available: {manager.rag_available}")
    return manager


async def get_database_query_logger() -> "DatabaseQueryLogger":
    """
    FastAPI dependency for DatabaseQueryLogger.
    
    Provides database query logging and analysis capabilities for local development.
    The logger is automatically started on first use and provides comprehensive
    query monitoring across all database types.
    
    Returns:
        DatabaseQueryLogger instance
        
    Raises:
        HTTPException: If query logger initialization fails (503 Service Unavailable)
        
    Validates: Requirements 7.2 (Database query logging and analysis)
    """
    global _query_logger
    
    if _query_logger is None:
        # Import here to avoid import-time side effects
        from ...logging.database_query_logger import get_database_query_logger
        
        try:
            logger.info("Initializing DatabaseQueryLogger via DI (lazy)")
            _query_logger = get_database_query_logger()
            
            # Start the query logger if not already active
            if not _query_logger.is_active:
                await _query_logger.start()
            
            logger.info("DatabaseQueryLogger initialized and started successfully via DI")
        except Exception as e:
            logger.error(f"DatabaseQueryLogger initialization failed: {e}")
            raise HTTPException(
                status_code=503,
                detail="Database query logging service unavailable"
            )
    
    return _query_logger


async def get_database_query_logger_optional() -> Optional["DatabaseQueryLogger"]:
    """
    Optional database query logger dependency - returns None if unavailable.
    
    Use this for endpoints that can function without query logging.
    
    Returns:
        DatabaseQueryLogger instance or None if unavailable
    """
    try:
        return await get_database_query_logger()
    except HTTPException:
        logger.warning("Database query logger unavailable, returning None for graceful degradation")
        return None
    except Exception as e:
        logger.warning(f"Database query logger error, returning None: {e}")
        return None


def clear_service_cache():
    """
    Clear all cached service instances.
    
    Useful for testing or forcing re-initialization.
    Should be called during application shutdown.
    
    Note: This now calls clear_all_caches() to ensure both service
    and component caches are cleared together.
    """
    clear_all_caches()


async def cleanup_services():
    """
    Async cleanup for services during application shutdown.
    
    This should be called from the FastAPI lifespan shutdown handler.
    
    Note: This now calls cleanup_all_dependencies() to ensure both service
    and component dependencies are cleaned up together.
    """
    await cleanup_all_dependencies()


# =============================================================================
# Component-level Dependencies (consolidated from database.py)
# =============================================================================

async def get_vector_store() -> "VectorStore":
    """
    FastAPI dependency for VectorStore using factory-based vector client.
    
    Initializes and connects to the appropriate vector database on first use.
    The actual implementation (Milvus for local, OpenSearch for AWS) is
    determined by the factory based on environment configuration.
    
    This is a higher-level abstraction over the vector client that provides
    vector storage and search capabilities for knowledge chunks.
    
    Returns:
        VectorStore instance
    
    Raises:
        HTTPException: If VectorStore initialization fails (503 Service Unavailable)
        
    Validates: Requirements US-1, US-4, NFR-1
    """
    global _vector_store_cache
    
    if _vector_store_cache is None:
        # Import here to avoid import-time side effects
        from ...components.vector_store.vector_store import VectorStore
        
        try:
            logger.info("Initializing VectorStore via DI (lazy)")
            
            # Get the factory-based vector client (Milvus for local, OpenSearch for AWS)
            factory = await get_database_factory()
            vector_client = await factory.get_vector_client()
            
            # Create VectorStore and inject the factory-resolved client
            # This avoids VectorStore.connect() which hardcodes OpenSearchClient
            _vector_store_cache = VectorStore()
            _vector_store_cache.opensearch_client = vector_client
            _vector_store_cache._connected = True
            
            logger.info("VectorStore initialized successfully via DI")
        except Exception as e:
            logger.error(f"Failed to initialize VectorStore: {e}")
            raise HTTPException(
                status_code=503,
                detail="Vector store service unavailable. Database may still be initializing."
            )
    
    return _vector_store_cache


async def get_vector_store_legacy() -> "VectorStore":
    """
    Legacy FastAPI dependency for VectorStore using direct OpenSearch client.
    
    This is the original implementation that directly uses OpenSearchClient.
    It's maintained for backward compatibility with existing code.
    
    DEPRECATED: Use get_vector_store() for new code, which uses the factory-based
    approach and supports both local and AWS environments.
    
    Returns:
        VectorStore instance
    
    Raises:
        HTTPException: If VectorStore initialization fails (503 Service Unavailable)
    """
    # Import here to avoid import-time side effects
    from ...components.vector_store.vector_store import VectorStore
    
    try:
        logger.info("Initializing VectorStore via DI (lazy) with legacy approach")
        vector_store = VectorStore()
        vector_store.connect()
        logger.info("VectorStore initialized successfully via DI with legacy approach")
        return vector_store
    except Exception as e:
        logger.error(f"Failed to initialize VectorStore: {e}")
        raise HTTPException(
            status_code=503,
            detail="Vector store service unavailable. Database may still be initializing."
        )


async def get_vector_store_optional() -> Optional["VectorStore"]:
    """
    Optional VectorStore dependency - returns None if unavailable.
    
    Use this for endpoints that can function without vector storage,
    enabling graceful degradation.
    
    Returns:
        VectorStore instance or None if unavailable
    """
    try:
        return await get_vector_store()
    except HTTPException:
        logger.warning("VectorStore unavailable, returning None for graceful degradation")
        return None
    except Exception as e:
        logger.warning(f"VectorStore error, returning None: {e}")
        return None


async def get_search_service(
    vector_store: Optional["VectorStore"] = None
) -> "SemanticSearchService":
    """
    FastAPI dependency for SemanticSearchService.
    
    Provides semantic search capabilities over the vector store.
    
    Args:
        vector_store: Optional VectorStore dependency (will be resolved if not provided)
    
    Returns:
        SemanticSearchService instance
        
    Raises:
        HTTPException: If initialization fails (503 Service Unavailable)
    """
    global _search_service_cache
    
    if _search_service_cache is None:
        # Import here to avoid import-time side effects
        from ...components.vector_store.search_service import SemanticSearchService
        
        try:
            logger.info("Initializing SemanticSearchService via DI (lazy)")
            
            # Get vector store if not provided
            if vector_store is None:
                vector_store = await get_vector_store()
            
            _search_service_cache = SemanticSearchService(vector_store)
            logger.info("SemanticSearchService initialized successfully via DI")
        except Exception as e:
            logger.error(f"Failed to initialize SemanticSearchService: {e}")
            raise HTTPException(
                status_code=503,
                detail="Search service unavailable"
            )
    
    return _search_service_cache


async def get_search_service_optional(
    vector_store: Optional["VectorStore"] = None
) -> Optional["SemanticSearchService"]:
    """
    Optional SemanticSearchService dependency - returns None if unavailable.
    
    Use this for endpoints that can function without search capabilities.
    
    Args:
        vector_store: Optional VectorStore dependency
    
    Returns:
        SemanticSearchService instance or None if unavailable
    """
    try:
        return await get_search_service(vector_store)
    except HTTPException:
        logger.warning("SearchService unavailable, returning None for graceful degradation")
        return None
    except Exception as e:
        logger.warning(f"SearchService error, returning None: {e}")
        return None


async def get_conversation_manager() -> "ConversationManager":
    """
    FastAPI dependency for ConversationManager.
    
    Provides conversation state management and context tracking.
    
    Returns:
        ConversationManager instance
        
    Raises:
        HTTPException: If initialization fails (503 Service Unavailable)
    """
    global _conversation_manager_cache
    
    if _conversation_manager_cache is None:
        # Import here to avoid import-time side effects
        from ...components.conversation.conversation_manager import ConversationManager
        
        try:
            logger.info("Initializing ConversationManager via DI (lazy)")
            _conversation_manager_cache = ConversationManager()
            logger.info("ConversationManager initialized successfully via DI")
        except Exception as e:
            logger.error(f"Failed to initialize ConversationManager: {e}")
            raise HTTPException(
                status_code=503,
                detail="Conversation service unavailable"
            )
    
    return _conversation_manager_cache


async def get_conversation_manager_optional() -> Optional["ConversationManager"]:
    """
    Optional ConversationManager dependency - returns None if unavailable.
    
    Returns:
        ConversationManager instance or None if unavailable
    """
    try:
        return await get_conversation_manager()
    except HTTPException:
        logger.warning("ConversationManager unavailable, returning None for graceful degradation")
        return None
    except Exception as e:
        logger.warning(f"ConversationManager error, returning None: {e}")
        return None


async def get_query_processor(
    search_service: Optional["SemanticSearchService"] = None,
    conversation_manager: Optional["ConversationManager"] = None
) -> "UnifiedKnowledgeQueryProcessor":
    """
    FastAPI dependency for UnifiedKnowledgeQueryProcessor.
    
    Provides unified query processing across vector search and knowledge graph.
    
    Args:
        search_service: Optional SemanticSearchService dependency
        conversation_manager: Optional ConversationManager dependency
    
    Returns:
        UnifiedKnowledgeQueryProcessor instance
        
    Raises:
        HTTPException: If initialization fails (503 Service Unavailable)
    """
    global _query_processor_cache
    
    if _query_processor_cache is None:
        # Import here to avoid import-time side effects
        from ...components.knowledge_graph.kg_builder import KnowledgeGraphBuilder
        from ...components.knowledge_graph.kg_query_engine import (
            KnowledgeGraphQueryEngine,
        )
        from ...components.query_processor.query_processor import (
            UnifiedKnowledgeQueryProcessor,
        )
        
        try:
            logger.info("Initializing UnifiedKnowledgeQueryProcessor via DI (lazy)")
            
            # Get dependencies if not provided
            if search_service is None:
                search_service = await get_search_service()
            if conversation_manager is None:
                conversation_manager = await get_conversation_manager()
            
            # Initialize knowledge graph components
            kg_builder = KnowledgeGraphBuilder()
            kg_query_engine = KnowledgeGraphQueryEngine(kg_builder)
            
            # Get QueryDecomposer (optional, graceful degradation)
            query_decomposer = await get_query_decomposer_optional()
            
            _query_processor_cache = UnifiedKnowledgeQueryProcessor(
                search_service=search_service,
                conversation_manager=conversation_manager,
                kg_query_engine=kg_query_engine,
                query_decomposer=query_decomposer
            )
            logger.info("UnifiedKnowledgeQueryProcessor initialized successfully via DI")
        except Exception as e:
            logger.error(f"Failed to initialize UnifiedKnowledgeQueryProcessor: {e}")
            raise HTTPException(
                status_code=503,
                detail="Query processing service unavailable"
            )
    
    return _query_processor_cache


async def get_query_processor_optional(
    search_service: Optional["SemanticSearchService"] = None,
    conversation_manager: Optional["ConversationManager"] = None
) -> Optional["UnifiedKnowledgeQueryProcessor"]:
    """
    Optional UnifiedKnowledgeQueryProcessor dependency - returns None if unavailable.
    
    Args:
        search_service: Optional SemanticSearchService dependency
        conversation_manager: Optional ConversationManager dependency
    
    Returns:
        UnifiedKnowledgeQueryProcessor instance or None if unavailable
    """
    try:
        return await get_query_processor(search_service, conversation_manager)
    except HTTPException:
        logger.warning("QueryProcessor unavailable, returning None for graceful degradation")
        return None
    except Exception as e:
        logger.warning(f"QueryProcessor error, returning None: {e}")
        return None


async def get_multimedia_generator() -> Optional["MultimediaGenerator"]:
    """
    FastAPI dependency for MultimediaGenerator.
    
    Provides multimedia content generation capabilities.
    Returns None if unavailable (graceful degradation by default).
    
    Returns:
        MultimediaGenerator instance or None if unavailable
    """
    global _multimedia_generator_cache
    
    if _multimedia_generator_cache is None:
        # Import here to avoid import-time side effects
        from ...components.multimedia_generator.multimedia_generator import (
            MultimediaGenerator,
        )
        
        try:
            logger.info("Initializing MultimediaGenerator via DI (lazy)")
            _multimedia_generator_cache = MultimediaGenerator()
            logger.info("MultimediaGenerator initialized successfully via DI")
        except Exception as e:
            logger.warning(f"MultimediaGenerator not available: {e}")
            return None
    
    return _multimedia_generator_cache


async def get_export_engine() -> Optional["ExportEngine"]:
    """
    FastAPI dependency for ExportEngine.
    
    Provides document export capabilities in various formats.
    Returns None if unavailable (graceful degradation by default).
    
    Returns:
        ExportEngine instance or None if unavailable
    """
    global _export_engine_cache
    
    if _export_engine_cache is None:
        # Import here to avoid import-time side effects
        from ...components.export_engine.export_engine import ExportEngine
        
        try:
            logger.info("Initializing ExportEngine via DI (lazy)")
            _export_engine_cache = ExportEngine()
            logger.info("ExportEngine initialized successfully via DI")
        except Exception as e:
            logger.warning(f"ExportEngine not available: {e}")
            return None
    
    return _export_engine_cache


# =============================================================================
# Unified Cache Management
# =============================================================================

def clear_dependency_cache():
    """
    Clear all cached component dependencies.
    
    This is an alias for clear_all_caches() for backward compatibility
    with code that imported from database.py.
    """
    clear_all_caches()


def clear_all_caches():
    """
    Clear all cached service and component instances.
    
    Useful for testing or forcing re-initialization.
    Should be called during application shutdown.
    """
    global _opensearch_client, _ai_service, _cached_ai_service, _rag_service
    global _cached_rag_service, _connection_manager, _query_logger
    global _vector_store_cache, _search_service_cache, _conversation_manager_cache
    global _query_processor_cache, _multimedia_generator_cache, _export_engine_cache
    global _database_factory, _relational_client, _vector_client, _graph_client
    global _local_alerting_system, _model_server_client, _model_status_service
    global _conceptnet_client, _enrichment_cache, _enrichment_service
    global _kg_retrieval_service
    global _yago_rate_limiter, _conceptnet_rate_limiter, _enrichment_status_service
    global _query_decomposer
    global _relation_type_registry
    global _searxng_client
    global _umls_client
    global _status_report_service
    global _active_jobs_dispatcher
    global _ner_extractor
    
    # Disconnect OpenSearch if connected
    if _opensearch_client is not None:
        try:
            _opensearch_client.disconnect()
        except Exception as e:
            logger.warning(f"Error disconnecting OpenSearch: {e}")
    
    # Disconnect VectorStore if connected
    if _vector_store_cache is not None:
        try:
            _vector_store_cache.disconnect()
        except Exception as e:
            logger.warning(f"Error disconnecting VectorStore: {e}")
    
    # Clear enrichment cache if it exists
    if _enrichment_cache is not None:
        try:
            _enrichment_cache.clear()
        except Exception as e:
            logger.warning(f"Error clearing enrichment cache: {e}")
    
    # Clear KG retrieval service cache if it exists
    if _kg_retrieval_service is not None:
        try:
            _kg_retrieval_service.clear_cache()
        except Exception as e:
            logger.warning(f"Error clearing KG retrieval service cache: {e}")
    
    # Clear service-level caches
    _opensearch_client = None
    _ai_service = None
    _cached_ai_service = None
    _rag_service = None
    _cached_rag_service = None
    _connection_manager = None
    _query_logger = None
    _model_server_client = None
    _model_status_service = None
    
    # Clear enrichment service caches
    _conceptnet_client = None
    _enrichment_cache = None
    _enrichment_service = None
    
    # Clear KG retrieval service cache
    _kg_retrieval_service = None
    
    # Clear QueryDecomposer cache
    _query_decomposer = None
    
    # Clear NER_Extractor cache
    _ner_extractor = None
    
    # Clear component-level caches
    _vector_store_cache = None
    _search_service_cache = None
    _conversation_manager_cache = None
    _query_processor_cache = None
    _multimedia_generator_cache = None
    _export_engine_cache = None
    
    # Clear factory-based caches
    _database_factory = None
    _relational_client = None
    _vector_client = None
    _graph_client = None
    
    # Clear local development caches
    _local_alerting_system = None
    
    # Clear rate limiter caches
    _yago_rate_limiter = None
    _conceptnet_rate_limiter = None
    
    # Clear enrichment status service cache
    _enrichment_status_service = None
    
    # Clear relation type registry cache
    _relation_type_registry = None

    # Clear SearXNG client cache
    _searxng_client = None

    # Clear UMLS client cache
    _umls_client = None

    # Clear StatusReportService cache
    _status_report_service = None

    # Clear ActiveJobsDispatcher cache
    _active_jobs_dispatcher = None

    logger.info("All dependency caches cleared")


async def cleanup_all_dependencies():
    """
    Async cleanup for all dependencies during application shutdown.
    
    This should be called from the FastAPI lifespan shutdown handler.
    Replaces both cleanup_services() and any component cleanup.
    """
    global _database_factory, _query_logger, _model_server_client, _model_status_service
    global _searxng_client, _yago_local_client
    global _umls_client
    
    logger.info("Cleaning up all dependencies...")
    
    # Cleanup UMLS client
    if _umls_client is not None:
        try:
            _umls_client = None
            logger.info("UMLS client cleaned up successfully")
        except Exception as e:
            logger.warning(f"Error cleaning up UMLS client: {e}")
    
    # Cleanup YAGO local client
    if _yago_local_client is not None:
        try:
            _yago_local_client = None
            logger.info("YAGO local client cleaned up successfully")
        except Exception as e:
            logger.warning(f"Error cleaning up YAGO local client: {e}")
    
    # Stop model status service background refresh if it exists
    if _model_status_service is not None:
        try:
            await _model_status_service.stop_background_refresh()
            logger.info("Model status service stopped successfully")
        except Exception as e:
            logger.warning(f"Error stopping model status service: {e}")
    
    # Close model server client if it exists
    if _model_server_client is not None:
        try:
            await _model_server_client.close()
            logger.info("Model server client closed successfully")
        except Exception as e:
            logger.warning(f"Error closing model server client: {e}")
    
    # Stop query logger if it exists
    if _query_logger is not None:
        try:
            await _query_logger.stop()
            logger.info("Database query logger stopped successfully")
        except Exception as e:
            logger.warning(f"Error stopping database query logger: {e}")
    
    # Close database factory if it exists
    if _database_factory is not None:
        try:
            await _database_factory.close()
            logger.info("Database factory closed successfully")
        except Exception as e:
            logger.warning(f"Error closing database factory: {e}")
    
    # Close SearXNG client if it exists
    if _searxng_client is not None:
        try:
            await _searxng_client.close()
            logger.info("SearXNG client closed successfully")
        except Exception as e:
            logger.warning(f"Error closing SearXNG client: {e}")

    # Clear all caches (this handles individual client disconnections)
    clear_all_caches()
    
    logger.info("All dependency cleanup complete")


# =============================================================================
# Migration and Environment Helpers
# =============================================================================

def get_environment_info() -> Dict[str, Any]:
    """
    Get information about the current environment and available dependencies.
    
    This helper function provides information about which database clients
    are available and what environment is detected. Useful for debugging
    and migration planning.
    
    Returns:
        Dictionary with environment information:
        - detected_environment: "local" | "aws" | "unknown"
        - available_clients: List of available client types
        - factory_initialized: Whether database factory is initialized
        - legacy_clients_available: Whether legacy clients are available
        
    Example:
        ```python
        info = get_environment_info()
        print(f"Environment: {info['detected_environment']}")
        print(f"Available clients: {info['available_clients']}")
        ```
    """
    try:
        from ...config.config_factory import detect_environment
        env_info = detect_environment()
        detected_env = env_info.detected_type
    except Exception:
        detected_env = "unknown"
    
    available_clients = []
    
    # Check if factory-based clients are available
    try:
        from ...clients.database_client_factory import DatabaseClientFactory
        from ...config.config_factory import get_database_config
        config = get_database_config("auto")
        
        if getattr(config, 'enable_relational_db', True):
            available_clients.append("relational")
        if getattr(config, 'enable_vector_search', True):
            available_clients.append("vector")
        if getattr(config, 'enable_graph_db', True):
            available_clients.append("graph")
    except Exception:
        pass
    
    # Check legacy clients
    legacy_available = True
    try:
        from ...clients.opensearch_client import OpenSearchClient
    except ImportError:
        legacy_available = False
    
    return {
        "detected_environment": detected_env,
        "available_clients": available_clients,
        "factory_initialized": _database_factory is not None,
        "legacy_clients_available": legacy_available,
        "cached_clients": {
            "factory_based": {
                "relational": _relational_client is not None,
                "vector": _vector_client is not None,
                "graph": _graph_client is not None,
            },
            "legacy": {
                "opensearch": _opensearch_client is not None,
            }
        }
    }


def is_factory_based_environment() -> bool:
    """
    Check if the current environment supports factory-based dependencies.
    
    Returns:
        True if factory-based dependencies are available and recommended
        
    Example:
        ```python
        if is_factory_based_environment():
            # Use factory-based dependencies
            vector_client = await get_vector_client()
        else:
            # Fall back to legacy dependencies
            opensearch = await get_opensearch_client()
        ```
    """
    try:
        from ...config.config_factory import detect_environment
        env_info = detect_environment()
        return env_info.confidence > 0.5
    except Exception:
        return False


async def migrate_to_factory_based() -> Dict[str, Any]:
    """
    Helper function to migrate from legacy to factory-based dependencies.
    
    This function initializes factory-based dependencies and provides
    a migration report. It's useful for testing migration scenarios.
    
    Returns:
        Dictionary with migration results:
        - success: Whether migration was successful
        - initialized_clients: List of successfully initialized clients
        - errors: List of any errors encountered
        - recommendations: List of recommended actions
        
    Example:
        ```python
        migration_result = await migrate_to_factory_based()
        if migration_result['success']:
            print("Migration successful!")
        else:
            print(f"Migration issues: {migration_result['errors']}")
        ```
    """
    results = {
        "success": True,
        "initialized_clients": [],
        "errors": [],
        "recommendations": []
    }
    
    try:
        # Initialize database factory
        factory = await get_database_factory()
        results["initialized_clients"].append("database_factory")
        
        # Try to initialize each client type
        client_types = [
            ("relational", get_relational_client_optional),
            ("vector", get_vector_client_optional),
            ("graph", get_graph_client_optional)
        ]
        
        for client_type, get_client_func in client_types:
            try:
                client = await get_client_func()
                if client is not None:
                    results["initialized_clients"].append(client_type)
                else:
                    results["recommendations"].append(
                        f"{client_type} client is disabled or unavailable"
                    )
            except Exception as e:
                results["errors"].append(f"Failed to initialize {client_type} client: {e}")
                results["success"] = False
        
        # Check if any legacy clients are still cached
        if _opensearch_client is not None:
            results["recommendations"].append(
                "Legacy OpenSearch client is still cached. "
                "Consider using get_vector_client() instead of get_opensearch_client()"
            )
        
    except Exception as e:
        results["success"] = False
        results["errors"].append(f"Failed to initialize database factory: {e}")
    
    return results


# =============================================================================
# Local Development Dependencies
# =============================================================================

# Local alerting system cache
_local_alerting_system: Optional["LocalAlertingSystem"] = None


async def get_local_alerting_system_optional() -> Optional["LocalAlertingSystem"]:
    """
    Optional local alerting system dependency - returns None if unavailable.
    
    This dependency provides access to the local development alerting system
    for performance monitoring and issue notification. It's only available
    in local development environments.
    
    Returns:
        LocalAlertingSystem instance or None if unavailable
    """
    global _local_alerting_system
    
    if _local_alerting_system is None:
        try:
            # Import here to avoid import-time side effects
            from ...config.local_config import LocalDatabaseConfig
            from ...monitoring.local_alerting_system import get_local_alerting_system

            # Check if we're in local development mode
            config = LocalDatabaseConfig()
            if config.database_type != "local":
                logger.debug("Local alerting system not available (not in local mode)")
                return None
            
            logger.info("Initializing local alerting system via DI (lazy)")
            _local_alerting_system = get_local_alerting_system(config)
            logger.info("Local alerting system initialized successfully via DI")
            
        except Exception as e:
            logger.warning(f"Local alerting system not available: {e}")
            return None
    
    return _local_alerting_system


async def get_local_alerting_system() -> "LocalAlertingSystem":
    """
    Required local alerting system dependency.
    
    Raises an exception if the local alerting system is not available.
    Use get_local_alerting_system_optional() for graceful degradation.
    
    Returns:
        LocalAlertingSystem instance
        
    Raises:
        RuntimeError: If local alerting system is not available
    """
    alerting_system = await get_local_alerting_system_optional()
    
    if alerting_system is None:
        raise RuntimeError(
            "Local alerting system is not available. "
            "This may be because the application is not running in local development mode "
            "or the alerting system failed to initialize."
        )
    
    return alerting_system



# =============================================================================
# Rate Limiter Dependencies
# =============================================================================

# Cached rate limiter instances
_yago_rate_limiter: Optional["RateLimiter"] = None
_conceptnet_rate_limiter: Optional["RateLimiter"] = None


async def get_yago_rate_limiter() -> "RateLimiter":
    """
    Get or create the YAGO rate limiter.
    
    Uses lazy initialization to create the rate limiter on first use.
    The rate limiter is configured from application settings.
    
    Returns:
        RateLimiter instance for YAGO queries
    """
    global _yago_rate_limiter
    
    if _yago_rate_limiter is None:
        from ...services.rate_limiter import create_yago_rate_limiter
        _yago_rate_limiter = create_yago_rate_limiter()
        logger.info("Created YAGO rate limiter")
    
    return _yago_rate_limiter


async def get_yago_rate_limiter_optional() -> Optional["RateLimiter"]:
    """
    Get the YAGO rate limiter if available.
    
    Returns None if the rate limiter cannot be created.
    Use this for graceful degradation.
    
    Returns:
        RateLimiter instance or None
    """
    try:
        return await get_yago_rate_limiter()
    except Exception as e:
        logger.warning(f"YAGO rate limiter not available: {e}")
        return None


async def get_conceptnet_rate_limiter() -> "RateLimiter":
    """
    Get or create the ConceptNet rate limiter.
    
    Uses lazy initialization to create the rate limiter on first use.
    The rate limiter is configured from application settings.
    
    Returns:
        RateLimiter instance for ConceptNet API
    """
    global _conceptnet_rate_limiter
    
    if _conceptnet_rate_limiter is None:
        from ...services.rate_limiter import create_conceptnet_rate_limiter
        _conceptnet_rate_limiter = create_conceptnet_rate_limiter()
        logger.info("Created ConceptNet rate limiter")
    
    return _conceptnet_rate_limiter


async def get_conceptnet_rate_limiter_optional() -> Optional["RateLimiter"]:
    """
    Get the ConceptNet rate limiter if available.
    
    Returns None if the rate limiter cannot be created.
    Use this for graceful degradation.
    
    Returns:
        RateLimiter instance or None
    """
    try:
        return await get_conceptnet_rate_limiter()
    except Exception as e:
        logger.warning(f"ConceptNet rate limiter not available: {e}")
        return None


def clear_rate_limiter_cache():
    """Clear cached rate limiter instances."""
    global _yago_rate_limiter, _conceptnet_rate_limiter
    _yago_rate_limiter = None
    _conceptnet_rate_limiter = None
    logger.debug("Cleared rate limiter cache")


# =============================================================================
# Enrichment Status Service Dependencies
# =============================================================================

# Cached enrichment status service instance
_enrichment_status_service: Optional["EnrichmentStatusService"] = None


async def get_enrichment_status_service() -> "EnrichmentStatusService":
    """
    Get or create the EnrichmentStatusService.
    
    Uses lazy initialization to create the service on first use.
    Requires a database connection.
    
    Returns:
        EnrichmentStatusService instance
    """
    global _enrichment_status_service
    
    if _enrichment_status_service is None:
        from ...database.connection import get_async_engine
        from ...services.enrichment_status_service import EnrichmentStatusService
        
        engine = await get_async_engine()
        _enrichment_status_service = EnrichmentStatusService(engine)
        logger.info("Created EnrichmentStatusService")
    
    return _enrichment_status_service


async def get_enrichment_status_service_optional() -> Optional["EnrichmentStatusService"]:
    """
    Get the EnrichmentStatusService if available.
    
    Returns None if the service cannot be created.
    Use this for graceful degradation.
    
    Returns:
        EnrichmentStatusService instance or None
    """
    try:
        return await get_enrichment_status_service()
    except Exception as e:
        logger.warning(f"EnrichmentStatusService not available: {e}")
        return None


def clear_enrichment_status_service_cache():
    """Clear cached EnrichmentStatusService instance."""
    global _enrichment_status_service
    _enrichment_status_service = None
    logger.debug("Cleared EnrichmentStatusService cache")


# =============================================================================
# Processing Status Service Dependencies
# =============================================================================


async def get_processing_status_service() -> "ProcessingStatusService":
    """
    FastAPI dependency for ProcessingStatusService.
    
    Lazily creates and caches the processing status service on first use.
    The service tracks document processing progress and sends WebSocket
    updates to clients.
    
    Returns:
        ProcessingStatusService instance
        
    Validates: Requirements 6.4
    """
    global _processing_status_service
    
    if _processing_status_service is None:
        from ...services.processing_status_service import ProcessingStatusService
        
        logger.info("Initializing ProcessingStatusService via DI (lazy)")
        _processing_status_service = ProcessingStatusService()
        logger.info("ProcessingStatusService initialized successfully via DI")
    
    return _processing_status_service


async def get_processing_status_service_optional() -> Optional["ProcessingStatusService"]:
    """
    Optional ProcessingStatusService dependency - returns None if unavailable.
    
    Use this for endpoints that can function without processing status tracking,
    enabling graceful degradation.
    
    Returns:
        ProcessingStatusService instance or None if unavailable
    """
    try:
        return await get_processing_status_service()
    except Exception as e:
        logger.warning(f"ProcessingStatusService not available: {e}")
        return None


async def get_processing_status_service_with_connection_manager(
    connection_manager: "ConnectionManager" = Depends(get_connection_manager)
) -> "ProcessingStatusService":
    """
    FastAPI dependency for ProcessingStatusService with ConnectionManager injected.
    
    This variant injects the ConnectionManager into the processing status service,
    enabling WebSocket message sending for status updates.
    
    Args:
        connection_manager: ConnectionManager instance (injected)
    
    Returns:
        ProcessingStatusService instance with ConnectionManager configured
        
    Validates: Requirements 6.4
    """
    service = await get_processing_status_service()
    service.set_connection_manager(connection_manager)
    return service


def clear_processing_status_service_cache():
    """Clear cached ProcessingStatusService instance."""
    global _processing_status_service
    _processing_status_service = None
    logger.debug("Cleared ProcessingStatusService cache")


# =============================================================================
# Status Report Service Dependencies
# =============================================================================


async def get_status_report_service(
    db_client: "RelationalStoreClient" = Depends(get_relational_client),
    processing_status_service: Optional["ProcessingStatusService"] = Depends(
        get_processing_status_service_optional
    ),
) -> "StatusReportService":
    """
    FastAPI dependency for StatusReportService.

    Lazily creates and caches the status report service on first use.
    The service aggregates processing job data from PostgreSQL and
    in-memory tracking to produce structured status reports.

    Args:
        db_client: RelationalStoreClient for PostgreSQL queries (injected)
        processing_status_service: Optional ProcessingStatusService for
            in-memory progress augmentation (injected)

    Returns:
        StatusReportService instance

    Raises:
        HTTPException: If service creation fails (503 Service Unavailable)

    Validates: Requirements 4.3
    """
    global _status_report_service

    if _status_report_service is None:
        try:
            from ...services.status_report_service import StatusReportService

            logger.info("Initializing StatusReportService via DI (lazy)")
            _status_report_service = StatusReportService(
                db_client=db_client,
                processing_status_service=processing_status_service,
            )
            logger.info("StatusReportService initialized successfully via DI")
        except Exception as e:
            logger.error(f"Failed to initialize StatusReportService: {e}")
            raise HTTPException(
                status_code=503,
                detail="Status report service unavailable",
            )

    return _status_report_service


async def get_status_report_service_optional(
    db_client: Optional["RelationalStoreClient"] = Depends(get_relational_client_optional),
    processing_status_service: Optional["ProcessingStatusService"] = Depends(
        get_processing_status_service_optional
    ),
) -> Optional["StatusReportService"]:
    """
    Optional StatusReportService dependency - returns None if unavailable.

    Use this for endpoints that can function without status report capabilities,
    enabling graceful degradation.

    Args:
        db_client: Optional RelationalStoreClient (injected)
        processing_status_service: Optional ProcessingStatusService (injected)

    Returns:
        StatusReportService instance or None if unavailable
    """
    if db_client is None:
        logger.warning("StatusReportService unavailable: no relational client")
        return None

    try:
        global _status_report_service

        if _status_report_service is None:
            from ...services.status_report_service import StatusReportService

            _status_report_service = StatusReportService(
                db_client=db_client,
                processing_status_service=processing_status_service,
            )

        return _status_report_service
    except Exception as e:
        logger.warning(f"StatusReportService not available: {e}")
        return None


def clear_status_report_service_cache():
    """Clear cached StatusReportService instance."""
    global _status_report_service
    _status_report_service = None
    logger.debug("Cleared StatusReportService cache")


# =============================================================================
# Relation Type Registry Dependencies
# =============================================================================


async def get_relation_type_registry(
    graph_client: Optional["GraphStoreClient"] = Depends(get_graph_client_optional),
) -> Optional["RelationTypeRegistry"]:
    """
    FastAPI dependency for RelationTypeRegistry.

    Lazily creates and caches the registry on first use.
    Queries Neo4j for distinct ConceptNet relation types during initialization.

    Args:
        graph_client: Optional graph database client (injected)

    Returns:
        RelationTypeRegistry instance, or None if graph client unavailable

    Validates: Requirements 5.1, 5.2, 5.6
    """
    global _relation_type_registry

    if _relation_type_registry is not None:
        return _relation_type_registry

    if graph_client is None:
        logger.warning(
            "Graph client unavailable, RelationTypeRegistry not created"
        )
        return None

    from ...components.knowledge_graph.relation_type_registry import (
        RelationTypeRegistry,
    )

    try:
        logger.info("Initializing RelationTypeRegistry via DI (lazy)")
        _relation_type_registry = RelationTypeRegistry(graph_client)
        await _relation_type_registry.initialize()
        logger.info("RelationTypeRegistry initialized successfully via DI")
    except Exception as e:
        logger.warning(f"RelationTypeRegistry initialization failed: {e}")
        return None

    return _relation_type_registry


async def get_relation_type_registry_optional(
    graph_client: Optional["GraphStoreClient"] = Depends(get_graph_client_optional),
) -> Optional["RelationTypeRegistry"]:
    """
    Optional RelationTypeRegistry dependency - returns None if unavailable.

    Use this for endpoints that can function without the registry.

    Returns:
        RelationTypeRegistry instance or None if unavailable
    """
    try:
        return await get_relation_type_registry(graph_client)
    except Exception as e:
        logger.warning(
            f"RelationTypeRegistry unavailable, returning None: {e}"
        )
        return None


# =============================================================================
# Conversation Knowledge Service Dependencies
# =============================================================================


async def get_conversation_knowledge_service(
    conversation_manager: "ConversationManager" = Depends(get_conversation_manager),
    vector_store: "VectorStore" = Depends(get_vector_store),
    model_client: "ModelServerClient" = Depends(get_model_server_client),
    graph_client=Depends(get_graph_client),
) -> "ConversationKnowledgeService":
    """
    FastAPI dependency for ConversationKnowledgeService.

    Lazily creates and caches the service on first use.
    Orchestrates the full conversation → knowledge pipeline
    (chunking → embedding → vector storage → KG extraction).

    Args:
        conversation_manager: ConversationManager dependency (injected)
        vector_store: VectorStore dependency (injected)
        model_client: ModelServerClient dependency (injected)
        graph_client: Graph database client dependency (injected)

    Returns:
        ConversationKnowledgeService instance

    Raises:
        HTTPException: If initialization fails (503 Service Unavailable)

    Validates: Requirements 7.5, 6.3, 6.4
    """
    global _conversation_knowledge_service

    if _conversation_knowledge_service is None:
        from ...services.conversation_knowledge_service import (
            ConversationKnowledgeService,
        )

        try:
            logger.info("Initializing ConversationKnowledgeService via DI (lazy)")

            # Construct ConceptNetValidator from graph_client (matching
            # KnowledgeGraphBuilder._get_conceptnet_validator pattern).
            # Wrapped in try/except — if construction fails, pass None.
            conceptnet_validator = None
            if graph_client is not None:
                try:
                    from ...components.knowledge_graph.conceptnet_validator import (
                        ConceptNetValidator,
                    )
                    conceptnet_validator = ConceptNetValidator(graph_client)
                except Exception as e:
                    logger.warning(f"ConceptNetValidator init failed, proceeding without: {e}")

            _conversation_knowledge_service = ConversationKnowledgeService(
                conversation_manager=conversation_manager,
                vector_store=vector_store,
                model_server_client=model_client,
                neo4j_client=graph_client,
                conceptnet_validator=conceptnet_validator,
            )
            logger.info("ConversationKnowledgeService initialized successfully via DI")
        except Exception as e:
            logger.error(f"Failed to initialize ConversationKnowledgeService: {e}")
            raise HTTPException(
                status_code=503,
                detail="Conversation knowledge service unavailable",
            )

    return _conversation_knowledge_service


async def get_conversation_knowledge_service_optional(
    conversation_manager: Optional["ConversationManager"] = Depends(
        get_conversation_manager_optional
    ),
    vector_store: Optional["VectorStore"] = Depends(get_vector_store_optional),
    model_client: Optional["ModelServerClient"] = Depends(
        get_model_server_client_optional
    ),
    graph_client=Depends(get_graph_client_optional),
) -> Optional["ConversationKnowledgeService"]:
    """
    Optional ConversationKnowledgeService dependency.

    Returns None instead of raising HTTPException 503 when
    initialization fails, enabling graceful degradation in
    endpoints that can function without knowledge extraction.

    Returns:
        ConversationKnowledgeService instance or None
    """
    if conversation_manager is None or vector_store is None:
        logger.warning(
            "ConversationKnowledgeService unavailable "
            "(missing conversation_manager or vector_store), "
            "returning None"
        )
        return None

    try:
        return await get_conversation_knowledge_service(
            conversation_manager=conversation_manager,
            vector_store=vector_store,
            model_client=model_client,
            graph_client=graph_client,
        )
    except HTTPException:
        logger.warning(
            "ConversationKnowledgeService unavailable, "
            "returning None for graceful degradation"
        )
        return None
    except Exception as e:
        logger.warning(
            f"ConversationKnowledgeService error, "
            f"returning None: {e}"
        )
        return None


# =============================================================================
# KG Query Engine Dependencies (KG Explorer)
# =============================================================================
_kg_query_engine: Optional["KnowledgeGraphQueryEngine"] = None


async def get_kg_query_engine(
    graph_client: "GraphStoreClient" = Depends(get_graph_client),
) -> "KnowledgeGraphQueryEngine":
    """
    FastAPI dependency for KnowledgeGraphQueryEngine.

    Lazily creates and caches the query engine on first use.
    The engine provides neighborhood queries and concept search
    for the KG Explorer frontend.

    Args:
        graph_client: Graph database client dependency (injected)

    Returns:
        KnowledgeGraphQueryEngine instance

    Raises:
        HTTPException: If initialization fails (503 Service Unavailable)

    Validates: Requirements 15.1
    """
    global _kg_query_engine

    if _kg_query_engine is None:
        from ...components.knowledge_graph.kg_query_engine import (
            KnowledgeGraphQueryEngine,
        )

        try:
            logger.info("Initializing KnowledgeGraphQueryEngine via DI (lazy)")
            _kg_query_engine = KnowledgeGraphQueryEngine()
            # Inject the Neo4j client directly so the engine skips its own
            # factory-based initialisation and reuses the DI-managed client.
            _kg_query_engine._neo4j_client = graph_client
            _kg_query_engine._neo4j_initialized = True
            logger.info("KnowledgeGraphQueryEngine initialized successfully via DI")
        except Exception as e:
            logger.error(f"Failed to initialize KnowledgeGraphQueryEngine: {e}")
            raise HTTPException(
                status_code=503,
                detail="Knowledge graph query engine unavailable",
            )

    return _kg_query_engine


async def get_kg_query_engine_optional(
    graph_client: Optional["GraphStoreClient"] = Depends(get_graph_client_optional),
) -> Optional["KnowledgeGraphQueryEngine"]:
    """
    Optional KG query engine dependency — returns None if unavailable.

    Use this for endpoints that can degrade gracefully when the graph
    database is not reachable.

    Returns:
        KnowledgeGraphQueryEngine instance or None if unavailable
    """
    if graph_client is None:
        return None

    try:
        return await get_kg_query_engine(graph_client)
    except HTTPException:
        logger.warning("KG query engine unavailable, returning None for graceful degradation")
        return None
    except Exception as e:
        logger.warning(f"KG query engine error, returning None: {e}")
        return None


# =============================================================================
# Active Jobs Dispatcher Dependencies
# =============================================================================


async def get_active_jobs_dispatcher(
    connection_manager: "ConnectionManager" = Depends(get_connection_manager),
    processing_status_service: Optional["ProcessingStatusService"] = Depends(
        get_processing_status_service_optional
    ),
    status_report_service: Optional["StatusReportService"] = Depends(
        get_status_report_service_optional
    ),
) -> "ActiveJobsDispatcher":
    """
    FastAPI dependency for ActiveJobsDispatcher.

    Lazily creates and caches the dispatcher singleton on first use.
    The dispatcher fans out real-time progress events to WebSocket
    connections subscribed to active-jobs updates.

    Args:
        connection_manager: ConnectionManager for broadcasting (injected)
        processing_status_service: Optional PSS for in-memory tracking (injected)
        status_report_service: Optional SRS for snapshot generation (injected)

    Returns:
        ActiveJobsDispatcher instance

    Validates: Requirements 2.1
    """
    global _active_jobs_dispatcher

    if _active_jobs_dispatcher is None:
        from ...services.active_jobs_dispatcher import ActiveJobsDispatcher

        logger.info("Initializing ActiveJobsDispatcher via DI (lazy)")
        _active_jobs_dispatcher = ActiveJobsDispatcher(
            connection_manager=connection_manager,
            processing_status_service=processing_status_service,
            status_report_service=status_report_service,
        )
        logger.info("ActiveJobsDispatcher initialized successfully via DI")

    return _active_jobs_dispatcher


async def get_active_jobs_dispatcher_optional(
    connection_manager: Optional["ConnectionManager"] = Depends(get_connection_manager),
    processing_status_service: Optional["ProcessingStatusService"] = Depends(
        get_processing_status_service_optional
    ),
    status_report_service: Optional["StatusReportService"] = Depends(
        get_status_report_service_optional
    ),
) -> Optional["ActiveJobsDispatcher"]:
    """
    Optional ActiveJobsDispatcher dependency — returns None if unavailable.

    Returns:
        ActiveJobsDispatcher instance or None if unavailable
    """
    if connection_manager is None:
        return None
    try:
        return await get_active_jobs_dispatcher(
            connection_manager=connection_manager,
            processing_status_service=processing_status_service,
            status_report_service=status_report_service,
        )
    except Exception as e:
        logger.warning(f"ActiveJobsDispatcher not available: {e}")
        return None


def clear_active_jobs_dispatcher_cache():
    """Clear cached ActiveJobsDispatcher instance."""
    global _active_jobs_dispatcher
    _active_jobs_dispatcher = None
    logger.debug("Cleared ActiveJobsDispatcher cache")
