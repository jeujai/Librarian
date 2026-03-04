"""
Query processing API endpoints.

This module handles unified knowledge query processing across all sources,
including books and conversation knowledge with multimedia response generation.
"""

import logging
import time
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

# Import dependency injection for VectorStore
from ...api.dependencies.database import get_search_service, get_vector_store
from ...components.conversation.conversation_manager import ConversationManager
from ...components.knowledge_graph.kg_query_engine import KnowledgeGraphQueryEngine
from ...components.multimedia_generator.multimedia_generator import MultimediaGenerator
from ...components.query_processor.query_processor import (
    QueryContext,
    UnifiedKnowledgeQueryProcessor,
)
from ...components.vector_store.search_service import SemanticSearchService
from ...config import get_settings
from ...models.core import KnowledgeCitation, MultimediaResponse, SourceType
from ..middleware import get_request_id, get_user_id
from ..models import (
    APIResponse,
    ChatMessageRequest,
    ChatMessageResponse,
    ErrorResponse,
    QueryRequest,
    QueryResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/query")
settings = get_settings()

# Initialize components - USING DEPENDENCY INJECTION
# Components are now initialized via FastAPI dependencies
query_processor = None
search_service = None
multimedia_generator = None
_components_initialized = False
_components_lock = None

async def _get_query_components():
    """
    Lazy initialization of query components using dependency injection.
    
    This function now uses FastAPI dependency injection for VectorStore
    instead of direct instantiation.
    """
    global query_processor, search_service, multimedia_generator, _components_initialized, _components_lock
    
    if _components_initialized:
        return query_processor, search_service, multimedia_generator
    
    # Initialize async lock if needed (use asyncio.Lock to avoid blocking event loop)
    if _components_lock is None:
        import asyncio
        _components_lock = asyncio.Lock()
    
    async with _components_lock:
        # Double-check after acquiring lock
        if _components_initialized:
            return query_processor, search_service, multimedia_generator
        
        try:
            # Use dependency injection for VectorStore and SearchService
            search_service = await get_search_service()
            conversation_manager = ConversationManager()
            
            # Initialize knowledge graph components
            from ...components.knowledge_graph.kg_builder import KnowledgeGraphBuilder
            kg_builder = KnowledgeGraphBuilder()
            kg_query_engine = KnowledgeGraphQueryEngine(kg_builder)
            
            multimedia_generator = MultimediaGenerator()
            
            query_processor = UnifiedKnowledgeQueryProcessor(
                search_service=search_service,
                conversation_manager=conversation_manager,
                kg_query_engine=kg_query_engine
            )
            
            logger.info("Query processing components initialized successfully (lazy with DI)")
            
        except Exception as e:
            logger.warning(f"Could not initialize all query components: {e}")
            # Use mock implementations for development
            query_processor = None
            search_service = None
            multimedia_generator = None
        
        _components_initialized = True
        return query_processor, search_service, multimedia_generator


@router.post("/search", response_model=QueryResponse)
async def search_knowledge_base(
    request: QueryRequest,
    user_id: Optional[str] = Depends(get_user_id),
    request_id: Optional[str] = Depends(get_request_id)
):
    """
    Search across all knowledge sources including books and conversations.
    
    This endpoint provides unified search across the entire knowledge base,
    treating book content and conversation knowledge with equal priority.
    """
    start_time = time.time()
    
    try:
        # Lazy load components
        query_processor, _, multimedia_generator = _get_query_components()
        
        if not query_processor:
            raise HTTPException(
                status_code=503, 
                detail="Query processing service not available"
            )
        
        # Create query context
        context = QueryContext(
            user_id=user_id or "anonymous",
            conversation_thread=None,  # Will be set if thread_id provided
            include_multimedia=request.include_multimedia,
            max_results=request.max_results,
            source_type_filters=request.source_types,
            content_type_filters=request.content_types
        )
        
        # Get conversation context if thread_id provided
        if request.thread_id:
            conversation = conversation_manager.get_conversation_thread(request.thread_id)
            if conversation:
                context.conversation_thread = conversation
            else:
                logger.warning(f"Conversation thread {request.thread_id} not found")
        
        # Process query
        search_result = query_processor.process_query(
            query=request.query,
            context=context
        )
        
        # Generate multimedia response if requested
        multimedia_response = None
        if request.include_multimedia and multimedia_generator:
            try:
                multimedia_response = multimedia_generator.generate_multimedia_response(
                    query=request.query,
                    search_results=search_result.chunks,
                    context=context
                )
            except Exception as e:
                logger.warning(f"Failed to generate multimedia response: {e}")
        
        # Format response
        results = {
            "text_content": search_result.response_text,
            "chunks": [chunk.to_dict() for chunk in search_result.chunks],
            "knowledge_citations": [citation.to_dict() for citation in search_result.citations],
            "reasoning_paths": getattr(search_result, 'reasoning_paths', []),
            "multimedia_content": multimedia_response.to_dict() if multimedia_response else None
        }
        
        processing_time = time.time() - start_time
        
        logger.info(
            f"Processed query '{request.query[:50]}...' in {processing_time:.3f}s, "
            f"found {search_result.total_results} results"
        )
        
        return QueryResponse(
            message="Query processed successfully",
            results=results,
            total_results=search_result.total_results,
            processing_time=processing_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Error processing query: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Query processing failed: {str(e)}"
        )


@router.post("/conversational", response_model=ChatMessageResponse)
async def conversational_query(
    request: ChatMessageRequest,
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    Process a conversational query with full context and multimedia support.
    
    This endpoint maintains conversation context and provides responses
    that build upon previous exchanges in the conversation thread.
    """
    try:
        # Lazy load components
        query_processor, _, multimedia_generator = _get_query_components()
        
        if not query_processor:
            raise HTTPException(
                status_code=503,
                detail="Conversational query service not available"
            )
        
        # Get or create conversation thread
        thread_id = request.thread_id
        if not thread_id:
            # Lazy load conversation_manager
            from ...components.conversation.conversation_manager import (
                ConversationManager,
            )
            conversation_manager = ConversationManager()
            
            # Create new conversation
            thread = conversation_manager.start_conversation(
                user_id=user_id or "anonymous"
            )
            thread_id = thread.thread_id
        else:
            # Lazy load conversation_manager
            from ...components.conversation.conversation_manager import (
                ConversationManager,
            )
            conversation_manager = ConversationManager()
            
            # Get existing conversation
            thread = conversation_manager.get_conversation_thread(thread_id)
            if not thread:
                raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Process message through conversation manager
        from ...models.core import Message, MessageType
        message = Message(
            message_id=str(uuid4()),
            content=request.message,
            message_type=MessageType.USER
        )
        
        context = conversation_manager.process_message(thread_id, message)
        
        # Create query context for processing
        query_context = QueryContext(
            user_id=user_id or "anonymous",
            conversation_thread=context.thread,
            include_multimedia=request.include_multimedia
        )
        
        # Process query with full context
        search_result = query_processor.process_query(
            query=request.message,
            context=query_context
        )
        
        # Generate multimedia response if requested
        multimedia_response = None
        if request.include_multimedia and multimedia_generator:
            try:
                multimedia_response = multimedia_generator.generate_multimedia_response(
                    query=request.message,
                    search_results=search_result.chunks,
                    context=query_context
                )
            except Exception as e:
                logger.warning(f"Failed to generate multimedia response: {e}")
        
        # Create system response message
        response_content = search_result.response_text
        if multimedia_response:
            response_content += f"\n\n[Generated {len(multimedia_response.visualizations)} visualizations]"
        
        system_message = Message(
            message_id=str(uuid4()),
            content=response_content,
            message_type=MessageType.SYSTEM,
            knowledge_references=[chunk.id for chunk in search_result.chunks]
        )
        
        # Add system response to conversation
        thread.add_message(system_message)
        
        # Format response
        response_data = {
            "text_content": response_content,
            "visualizations": multimedia_response.visualizations if multimedia_response else [],
            "knowledge_citations": [citation.to_dict() for citation in search_result.citations],
            "reasoning_explanation": getattr(search_result, 'reasoning_explanation', ''),
            "context_used": len(context.recent_messages)
        }
        
        logger.info(f"Processed conversational query in thread {thread_id}")
        
        return ChatMessageResponse(
            message="Conversational query processed successfully",
            response=response_data,
            thread_id=thread_id,
            message_id=system_message.message_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing conversational query: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Conversational query processing failed: {str(e)}"
        )


@router.get("/suggestions", response_model=Dict[str, List[str]])
async def get_query_suggestions(
    partial_query: str = "",
    limit: int = 5,
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    Get query suggestions based on partial input and user history.
    
    This endpoint provides intelligent query suggestions to help users
    formulate better queries based on available knowledge.
    """
    try:
        suggestions = {
            "completions": [],
            "related_topics": [],
            "popular_queries": []
        }
        
        if not partial_query:
            # Return popular/recent queries
            suggestions["popular_queries"] = [
                "What are the main concepts in machine learning?",
                "How does natural language processing work?",
                "Explain the principles of software architecture",
                "What are the latest developments in AI?",
                "How to implement a REST API?"
            ][:limit]
        else:
            # Generate completions based on partial query
            partial_lower = partial_query.lower()
            
            # Simple completion suggestions (in production, use ML-based suggestions)
            common_completions = [
                f"{partial_query} examples",
                f"{partial_query} best practices",
                f"{partial_query} implementation",
                f"{partial_query} comparison",
                f"{partial_query} tutorial"
            ]
            
            suggestions["completions"] = common_completions[:limit]
            
            # Related topics (simplified)
            if "machine learning" in partial_lower:
                suggestions["related_topics"] = [
                    "deep learning", "neural networks", "supervised learning",
                    "unsupervised learning", "reinforcement learning"
                ][:limit]
            elif "programming" in partial_lower:
                suggestions["related_topics"] = [
                    "algorithms", "data structures", "software design",
                    "code optimization", "debugging"
                ][:limit]
            elif "api" in partial_lower:
                suggestions["related_topics"] = [
                    "REST", "GraphQL", "authentication", "rate limiting",
                    "documentation"
                ][:limit]
        
        return suggestions
        
    except Exception as e:
        logger.error(f"Error generating query suggestions: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to generate query suggestions"
        )


@router.get("/knowledge-stats", response_model=Dict[str, Any])
async def get_knowledge_base_statistics():
    """
    Get statistics about the knowledge base content.
    
    This endpoint provides insights into the available knowledge sources,
    content types, and overall knowledge base health.
    """
    try:
        # Lazy load components
        _, search_service, _ = _get_query_components()
        
        stats = {
            "total_chunks": 0,
            "source_breakdown": {
                "books": 0,
                "conversations": 0
            },
            "content_type_breakdown": {
                "technical": 0,
                "academic": 0,
                "general": 0,
                "legal": 0,
                "medical": 0,
                "narrative": 0
            },
            "recent_additions": 0,
            "knowledge_graph_nodes": 0,
            "knowledge_graph_relationships": 0
        }
        
        # Get statistics from vector store
        if search_service:
            try:
                vector_stats = search_service.get_collection_stats()
                stats["total_chunks"] = vector_stats.get("total_vectors", 0)
                
                # Get source breakdown
                source_stats = search_service.get_source_breakdown()
                stats["source_breakdown"] = source_stats
                
                # Get content type breakdown
                content_stats = search_service.get_content_type_breakdown()
                stats["content_type_breakdown"] = content_stats
                
            except Exception as e:
                logger.warning(f"Could not get vector store stats: {e}")
        
        # Get knowledge graph statistics
        if True:  # kg_query_engine check removed - lazy load if needed
            try:
                from ...components.knowledge_graph.kg_builder import (
                    KnowledgeGraphBuilder,
                )
                from ...components.knowledge_graph.kg_query_engine import (
                    KnowledgeGraphQueryEngine,
                )
                kg_builder = KnowledgeGraphBuilder()
                kg_query_engine = KnowledgeGraphQueryEngine(kg_builder)
                
                kg_stats = kg_query_engine.get_graph_statistics()
                stats["knowledge_graph_nodes"] = kg_stats.get("total_nodes", 0)
                stats["knowledge_graph_relationships"] = kg_stats.get("total_relationships", 0)
            except Exception as e:
                logger.warning(f"Could not get knowledge graph stats: {e}")
        
        # Get conversation statistics
        if True:  # conversation_manager check removed - lazy load if needed
            try:
                from ...components.conversation.conversation_manager import (
                    ConversationManager,
                )
                conversation_manager = ConversationManager()
                
                conv_stats = conversation_manager.get_conversation_statistics()
                stats["conversation_stats"] = conv_stats
            except Exception as e:
                logger.warning(f"Could not get conversation stats: {e}")
        
        return stats
        
    except Exception as e:
        logger.error(f"Error getting knowledge base statistics: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve knowledge base statistics"
        )


@router.post("/feedback", response_model=APIResponse)
async def submit_query_feedback(
    query_id: str,
    feedback_score: float,
    feedback_text: Optional[str] = None,
    user_id: Optional[str] = Depends(get_user_id)
):
    """
    Submit feedback for a query result to improve future responses.
    
    This endpoint allows users to provide feedback on query results,
    which is used to improve the quality of future responses.
    """
    try:
        # Validate feedback score
        if not -1.0 <= feedback_score <= 1.0:
            raise HTTPException(
                status_code=400,
                detail="Feedback score must be between -1.0 and 1.0"
            )
        
        # Store feedback (simplified implementation)
        feedback_data = {
            "query_id": query_id,
            "user_id": user_id or "anonymous",
            "feedback_score": feedback_score,
            "feedback_text": feedback_text,
            "timestamp": time.time()
        }
        
        # In production, store in database and use for ML training
        logger.info(f"Received feedback for query {query_id}: score={feedback_score}")
        
        return APIResponse(
            message="Feedback submitted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting query feedback: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to submit feedback"
        )


@router.get("/health", response_model=Dict[str, Any])
async def query_service_health():
    """Health check for query processing service."""
    # Lazy load components for health check
    query_processor, search_service, multimedia_generator = _get_query_components()
    
    health_status = {
        "status": "healthy",
        "service": "query_processor",
        "components": {}
    }
    
    # Check query processor
    if query_processor:
        health_status["components"]["query_processor"] = "healthy"
    else:
        health_status["components"]["query_processor"] = "unavailable"
        health_status["status"] = "degraded"
    
    # Check search service
    if search_service:
        try:
            # Test search service
            health_status["components"]["search_service"] = "healthy"
        except Exception:
            health_status["components"]["search_service"] = "unhealthy"
            health_status["status"] = "degraded"
    else:
        health_status["components"]["search_service"] = "unavailable"
        health_status["status"] = "degraded"
    
    # Check multimedia generator
    if multimedia_generator:
        health_status["components"]["multimedia_generator"] = "healthy"
    else:
        health_status["components"]["multimedia_generator"] = "unavailable"
    
    return health_status