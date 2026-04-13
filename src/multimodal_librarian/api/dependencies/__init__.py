"""
FastAPI Dependencies Module

Provides dependency injection for all service and component dependencies.

================================================================================
DEPENDENCY INJECTION QUICK REFERENCE
================================================================================

Import dependencies from this module:
    from multimodal_librarian.api.dependencies import get_ai_service, get_rag_service

Available Dependencies:
-----------------------
Service-Level:
  - get_opensearch_client()          - OpenSearch vector database client
  - get_opensearch_client_optional() - Returns None if unavailable
  - get_ai_service()                 - AI/LLM service
  - get_ai_service_optional()        - Returns None if unavailable
  - get_cached_ai_service_di()       - Cached AI service with optimizations
  - get_rag_service()                - RAG service (requires OpenSearch + AI)
  - get_cached_rag_service()         - Cached RAG service

Component-Level:
  - get_vector_store()               - Vector storage for knowledge chunks
  - get_search_service()             - Semantic search over vector store
  - get_conversation_manager()       - Conversation state management
  - get_query_processor()            - Unified query processing

WebSocket:
  - get_connection_manager()         - WebSocket connection manager
  - get_connection_manager_with_services() - Manager with RAG/AI injected

Cleanup:
  - clear_all_caches()               - Clear all cached instances
  - cleanup_all_dependencies()       - Async cleanup for shutdown

Usage Example:
--------------
    from fastapi import Depends
    from multimodal_librarian.api.dependencies import get_ai_service
    
    @router.post("/generate")
    async def generate(prompt: str, ai = Depends(get_ai_service)):
        return await ai.generate(prompt)

For complete documentation, see:
  - .kiro/steering/dependency-injection.md
  - .kiro/specs/dependency-injection-architecture/design.md
"""

# Import all dependencies from the consolidated services module
from .services import (  # ==========================================================================; OpenSearch/Vector Database Dependencies; Search Service Dependencies; AI Service Dependencies; RAG Service Dependencies; Model Status Service Dependencies; Enrichment Service Dependencies; KG Retrieval Service Dependencies; Conversation/Query Dependencies; WebSocket Connection Management; Multimedia/Export Dependencies; Cache/Cleanup Utilities
    ConnectionManager,
    cleanup_all_dependencies,
    cleanup_services,
    clear_active_jobs_dispatcher_cache,
    clear_all_caches,
    clear_dependency_cache,
    clear_processing_status_service_cache,
    clear_service_cache,
    clear_status_report_service_cache,
    get_active_jobs_dispatcher,
    get_active_jobs_dispatcher_optional,
    get_ai_service,
    get_ai_service_optional,
    get_cached_ai_service_di,
    get_cached_ai_service_optional,
    get_cached_rag_service,
    get_conceptnet_client,
    get_conceptnet_client_optional,
    get_connection_manager,
    get_connection_manager_with_services,
    get_conversation_knowledge_service,
    get_conversation_knowledge_service_optional,
    get_conversation_manager,
    get_conversation_manager_optional,
    get_enrichment_cache,
    get_enrichment_cache_optional,
    get_enrichment_service,
    get_enrichment_service_optional,
    get_export_engine,
    get_kg_query_engine,
    get_kg_query_engine_optional,
    get_kg_retrieval_service,
    get_kg_retrieval_service_optional,
    get_model_server_client,
    get_model_server_client_optional,
    get_model_status_service,
    get_model_status_service_optional,
    get_multimedia_generator,
    get_opensearch_client,
    get_opensearch_client_optional,
    get_processing_status_service,
    get_processing_status_service_optional,
    get_processing_status_service_with_connection_manager,
    get_query_decomposer_optional,
    get_query_processor,
    get_query_processor_optional,
    get_rag_service,
    get_relation_type_registry,
    get_relation_type_registry_optional,
    get_relevance_detector,
    get_relevance_detector_optional,
    get_search_service,
    get_search_service_optional,
    get_searxng_client,
    get_searxng_client_optional,
    get_status_report_service,
    get_status_report_service_optional,
    get_umls_client,
    get_umls_client_optional,
    get_vector_store,
    get_vector_store_optional,
    get_yago_local_client,
)

__all__ = [
    # OpenSearch/Vector Database Dependencies
    "get_opensearch_client",
    "get_opensearch_client_optional",
    "get_vector_store",
    "get_vector_store_optional",
    # Search Service Dependencies
    "get_search_service",
    "get_search_service_optional",
    # SearXNG Client Dependencies
    "get_searxng_client",
    "get_searxng_client_optional",
    # AI Service Dependencies
    "get_ai_service",
    "get_ai_service_optional",
    "get_cached_ai_service_di",
    "get_cached_ai_service_optional",
    # RAG Service Dependencies
    "get_rag_service",
    "get_cached_rag_service",
    # Model Status Service Dependencies
    "get_model_status_service",
    "get_model_status_service_optional",
    # Model Server Client Dependencies
    "get_model_server_client",
    "get_model_server_client_optional",
    # Processing Status Service Dependencies
    "get_processing_status_service",
    "get_processing_status_service_optional",
    "get_processing_status_service_with_connection_manager",
    "clear_processing_status_service_cache",
    # Status Report Service Dependencies
    "get_status_report_service",
    "get_status_report_service_optional",
    "clear_status_report_service_cache",
    # Active Jobs Dispatcher Dependencies
    "get_active_jobs_dispatcher",
    "get_active_jobs_dispatcher_optional",
    "clear_active_jobs_dispatcher_cache",
    # Enrichment Service Dependencies
    "get_yago_local_client",
    "get_umls_client",
    "get_umls_client_optional",
    "get_conceptnet_client",
    "get_conceptnet_client_optional",
    "get_enrichment_cache",
    "get_enrichment_cache_optional",
    "get_enrichment_service",
    "get_enrichment_service_optional",
    # KG Retrieval Service Dependencies
    "get_kg_retrieval_service",
    "get_kg_retrieval_service_optional",
    # KG Query Engine Dependencies (KG Explorer)
    "get_kg_query_engine",
    "get_kg_query_engine_optional",
    # Conversation Knowledge Service Dependencies
    "get_conversation_knowledge_service",
    "get_conversation_knowledge_service_optional",
    # Conversation/Query Dependencies
    "get_conversation_manager",
    "get_conversation_manager_optional",
    "get_query_processor",
    "get_query_processor_optional",
    # QueryDecomposer Dependencies
    "get_query_decomposer_optional",
    # RelevanceDetector Dependencies
    "get_relevance_detector",
    "get_relevance_detector_optional",
    # Relation Type Registry Dependencies
    "get_relation_type_registry",
    "get_relation_type_registry_optional",
    # WebSocket Connection Management
    "get_connection_manager",
    "get_connection_manager_with_services",
    "ConnectionManager",
    # Multimedia/Export Dependencies
    "get_multimedia_generator",
    "get_export_engine",
    # Cache/Cleanup Utilities
    "clear_service_cache",
    "clear_dependency_cache",
    "clear_all_caches",
    "cleanup_services",
    "cleanup_all_dependencies",
]
