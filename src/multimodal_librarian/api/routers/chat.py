"""
Chat router for WebSocket-based conversational interface with RAG integration.

This module handles real-time chat communication, file uploads through chat,
conversation management, and document-aware responses using RAG.

REFACTORED: Now uses FastAPI dependency injection pattern instead of module-level
singleton instantiation. This prevents blocking during application startup.
"""

import base64
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# Set up logger first
logger = logging.getLogger(__name__)

# Import existing components (fallback if RAG fails)
try:
    from ...components.conversation.conversation_manager import ConversationManager
    from ...components.export_engine.export_engine import ExportEngine
    from ...components.knowledge_graph.kg_query_engine import KnowledgeGraphQueryEngine
    from ...components.query_processor.query_processor import (
        QueryContext,
        UnifiedKnowledgeQueryProcessor,
    )
    from ...components.vector_store.search_service import SemanticSearchService
    from ...models.core import (
        ConversationThread,
        Message,
        MessageType,
        MultimediaResponse,
    )
    LEGACY_COMPONENTS_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Some components not available: {e}")
    # Define fallback types
    ConversationThread = dict
    MultimediaResponse = dict
    Message = dict
    MessageType = None
    LEGACY_COMPONENTS_AVAILABLE = False

from ...config import get_settings

# Import dependency injection providers - NO module-level service instantiation
from ..dependencies import (
    get_ai_service_optional,
    get_cached_rag_service,
    get_connection_manager_with_services,
    get_conversation_manager,
    get_processing_status_service_optional,
    get_search_service,
    get_vector_store,
)
from ..dependencies.services import ConnectionManager

# Import chat document handlers for WebSocket document operations
from .chat_document_handlers import (
    handle_chat_document_upload,
    handle_document_delete_request,
    handle_document_list_request,
    handle_document_retry_request,
    handle_document_stats_request,
    handle_related_docs_graph,
)

# Router setup
router = APIRouter()
settings = get_settings()

# NO MODULE-LEVEL INSTANTIATION - ConnectionManager is now provided via DI
# The following line has been REMOVED:
# manager = ConnectionManager()

# Initialize components with RAG integration - USING DEPENDENCY INJECTION
# Components are now initialized via FastAPI dependencies
conversation_manager = None
query_processor = None
export_engine = None
_components_initialized = False
_components_lock = None


async def _get_legacy_components(search_service=None):
    """
    Lazy initialization of legacy components using dependency injection.
    
    This function now uses FastAPI dependency injection for VectorStore
    instead of direct instantiation.
    
    Args:
        search_service: Optional search service (injected via DI)
    """
    global conversation_manager, query_processor, export_engine, _components_initialized, _components_lock
    
    if _components_initialized:
        return conversation_manager, query_processor, export_engine
    
    # Initialize async lock if needed (use asyncio.Lock to avoid blocking event loop)
    if _components_lock is None:
        import asyncio
        _components_lock = asyncio.Lock()
    
    async with _components_lock:
        # Double-check after acquiring lock
        if _components_initialized:
            return conversation_manager, query_processor, export_engine
        
        try:
            # Use dependency injection for SearchService if not provided
            if search_service is None:
                try:
                    search_service = await get_search_service()
                except Exception as e:
                    logger.warning(f"Could not get search service via DI: {e}")
                    search_service = None
            
            conversation_manager = await get_conversation_manager()
            
            if search_service:
                # Initialize knowledge graph components
                from ...components.knowledge_graph.kg_builder import (
                    KnowledgeGraphBuilder,
                )
                kg_builder = KnowledgeGraphBuilder()
                kg_query_engine = KnowledgeGraphQueryEngine(kg_builder)
                
                query_processor = UnifiedKnowledgeQueryProcessor(
                    search_service=search_service,
                    conversation_manager=conversation_manager,
                    kg_query_engine=kg_query_engine
                )
            else:
                query_processor = None
            
            if LEGACY_COMPONENTS_AVAILABLE:
                export_engine = ExportEngine()
            else:
                export_engine = None
            
            logger.info("Legacy components initialized successfully (lazy with DI)")
        except Exception as e:
            logger.warning(f"Could not initialize legacy components: {e}")
            # Use minimal implementations for development
            try:
                conversation_manager = await get_conversation_manager()
                export_engine = None  # Skip ExportEngine if not available
                logger.info("Minimal components initialized (lazy)")
            except Exception as e2:
                logger.warning(f"Could not initialize minimal components: {e2}")
                conversation_manager = None
                export_engine = None
        
        _components_initialized = True
        return conversation_manager, query_processor, export_engine


# Fallback service providers - lazy loaded
_fallback_service = None
_expectation_manager = None


def _get_fallback_service():
    """Lazy load fallback service."""
    global _fallback_service
    if _fallback_service is None:
        try:
            from ...services.fallback_service import get_fallback_service
            _fallback_service = get_fallback_service()
        except Exception as e:
            logger.warning(f"Could not load fallback service: {e}")
    return _fallback_service


def _get_expectation_manager():
    """Lazy load expectation manager."""
    global _expectation_manager
    if _expectation_manager is None:
        try:
            from ...services.expectation_manager import get_expectation_manager
            _expectation_manager = get_expectation_manager()
        except Exception as e:
            logger.warning(f"Could not load expectation manager: {e}")
    return _expectation_manager


async def _persist_message(thread_id: str, content: str, message_type: MessageType, citations: list = None):
    """Persist a message to ConversationManager's thread. Non-fatal on failure."""
    try:
        conv_manager = await get_conversation_manager()
        if conv_manager:
            # Build knowledge_references from citations for persistence
            knowledge_refs = []
            if citations:
                for c in citations:
                    if isinstance(c, dict):
                        knowledge_refs.append(c)
                    else:
                        knowledge_refs.append(str(c))
            conv_manager.process_message(
                thread_id, content, message_type=message_type,
                knowledge_references=knowledge_refs,
            )
    except Exception as e:
        logger.warning(f"Failed to persist {message_type.value} message to thread {thread_id}: {e}")


@router.websocket("/ws/chat")
async def websocket_endpoint(
    websocket: WebSocket,
    manager: ConnectionManager = Depends(get_connection_manager_with_services)
):
    """
    WebSocket endpoint for real-time chat communication.
    
    Uses dependency injection for ConnectionManager with services.
    This ensures no blocking initialization at module import time.
    
    Args:
        websocket: The WebSocket connection
        manager: ConnectionManager with RAG and AI services injected via DI
    """
    connection_id = str(uuid4())
    
    try:
        await manager.connect(websocket, connection_id)
        
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            await handle_websocket_message(message_data, connection_id, manager)
            
    except WebSocketDisconnect:
        manager.disconnect(connection_id)
        logger.info(f"Client {connection_id} disconnected")
    except Exception as e:
        logger.error(f"WebSocket error for {connection_id}: {e}")
        manager.disconnect(connection_id)


async def handle_websocket_message(message_data: dict, connection_id: str, manager: ConnectionManager):
    """Handle incoming WebSocket messages."""
    message_type = message_data.get('type')
    
    try:
        if message_type == 'start_conversation':
            await handle_start_conversation(connection_id, manager)
            
        elif message_type == 'resume_conversation':
            await handle_resume_conversation(message_data, connection_id, manager)
            
        elif message_type == 'chat_message':
            await handle_chat_message(message_data, connection_id, manager)
            
        elif message_type == 'files_uploaded':
            await handle_files_uploaded(message_data, connection_id, manager)
            
        elif message_type == 'export_conversation':
            await handle_export_conversation(message_data, connection_id, manager)
        
        # Handle heartbeat/keepalive messages silently
        elif message_type == 'heartbeat':
            await manager.send_personal_message({
                'type': 'heartbeat_response',
                'timestamp': datetime.now().isoformat()
            }, connection_id)
        
        # Handle session info request
        elif message_type == 'session_info':
            thread_id = manager.get_thread_id(connection_id)
            await manager.send_personal_message({
                'type': 'session_info',
                'data': {
                    'connection_id': connection_id,
                    'thread_id': thread_id,
                    'rag_available': manager.rag_available,
                    'ai_available': manager.ai_service is not None
                }
            }, connection_id)
        
        # Handle typing indicators (acknowledge but don't broadcast in single-user mode)
        elif message_type in ('typing_start', 'typing_stop'):
            # Silently acknowledge - could broadcast to other users in multi-user mode
            pass
        
        # Handle clear history request
        elif message_type == 'clear_history':
            manager.clear_conversation_history(connection_id)
            await manager.send_personal_message({
                'type': 'history_cleared',
                'timestamp': datetime.now().isoformat()
            }, connection_id)
        
        # Handle context setting
        elif message_type == 'set_context':
            # Store context for future use (could enhance RAG queries)
            context = message_data.get('context', {})
            await manager.send_personal_message({
                'type': 'context_set',
                'context': context,
                'timestamp': datetime.now().isoformat()
            }, connection_id)
        
        # Handle suggestion requests
        elif message_type == 'get_suggestions':
            # Return some default suggestions
            await manager.send_personal_message({
                'type': 'suggestions',
                'suggestions': [
                    "What documents do I have?",
                    "Summarize my uploaded files",
                    "Search for specific topics",
                    "Help me understand a concept"
                ]
            }, connection_id)
        
        # =================================================================
        # Chat Document Operations (Requirements: 1.1, 7.2, 8.3, 8.4)
        # =================================================================
        
        # Handle document upload via chat interface
        elif message_type == 'chat_document_upload':
            # Get document manager and processing status service
            from ...components.document_manager.document_manager import DocumentManager
            document_manager = DocumentManager()
            
            # Get processing status service (optional)
            processing_status_service = None
            try:
                processing_status_service = await get_processing_status_service_optional()
                if processing_status_service:
                    processing_status_service.set_connection_manager(manager)
            except Exception as e:
                logger.warning(f"Could not get processing status service: {e}")
            
            await handle_chat_document_upload(
                message_data=message_data,
                connection_id=connection_id,
                manager=manager,
                document_manager=document_manager,
                processing_status_service=processing_status_service
            )
        
        # Handle document list request
        elif message_type == 'document_list_request':
            from ...components.document_manager.document_manager import DocumentManager
            document_manager = DocumentManager()
            
            await handle_document_list_request(
                message_data=message_data,
                connection_id=connection_id,
                manager=manager,
                document_manager=document_manager
            )
        
        # Handle on-demand document stats request
        elif message_type == 'document_stats_request':
            await handle_document_stats_request(
                message_data=message_data,
                connection_id=connection_id,
                manager=manager,
            )

        # Handle document delete request
        elif message_type == 'document_delete_request':
            from ...components.document_manager.document_manager import DocumentManager
            document_manager = DocumentManager()
            
            await handle_document_delete_request(
                message_data=message_data,
                connection_id=connection_id,
                manager=manager,
                document_manager=document_manager
            )
        
        # Handle document retry request
        elif message_type == 'document_retry_request':
            from ...components.document_manager.document_manager import DocumentManager
            document_manager = DocumentManager()
            
            # Get processing status service (optional)
            processing_status_service = None
            try:
                processing_status_service = await get_processing_status_service_optional()
                if processing_status_service:
                    processing_status_service.set_connection_manager(manager)
            except Exception as e:
                logger.warning(f"Could not get processing status service: {e}")
            
            await handle_document_retry_request(
                message_data=message_data,
                connection_id=connection_id,
                manager=manager,
                document_manager=document_manager,
                processing_status_service=processing_status_service
            )

        # Handle related docs graph request
        elif message_type == 'related_docs_graph':
            await handle_related_docs_graph(
                message_data=message_data,
                connection_id=connection_id,
                manager=manager,
            )
            
        else:
            # Log unknown message types but don't send error to avoid spamming UI
            logger.warning(f"Unknown message type from {connection_id}: {message_type}")
            
    except Exception as e:
        logger.error(f"Error handling message {message_type}: {e}")
        await manager.send_personal_message({
            'type': 'error',
            'message': 'An error occurred processing your request'
        }, connection_id)


async def handle_start_conversation(connection_id: str, manager: ConnectionManager):
    """Start a new conversation thread with RAG capabilities."""
    try:
        # Lazy load components
        conv_manager, _, _ = await _get_legacy_components()
        
        # Create new conversation thread
        if conv_manager:
            thread = conv_manager.start_conversation(user_id=connection_id)
            manager.set_thread_id(connection_id, thread.thread_id)
            thread_id = thread.thread_id
        else:
            # Simple thread ID generation if conversation manager not available
            thread_id = str(uuid4())
            manager.set_thread_id(connection_id, thread_id)
        
        # Get RAG service status
        rag_status = {}
        if manager.rag_service:
            try:
                rag_status = manager.rag_service.get_service_status()
            except Exception as e:
                logger.warning(f"Could not get RAG status: {e}")
                rag_status = {"status": "unavailable", "error": str(e)}
        
        await manager.send_personal_message({
            'type': 'conversation_started',
            'thread_id': thread_id,
            'timestamp': datetime.now().isoformat(),
            'features': {
                'rag_enabled': manager.rag_available,
                'document_aware_responses': manager.rag_available,
                'citation_support': manager.rag_available,
                'fallback_ai': True,
                'conversation_memory': True
            },
            'rag_status': rag_status,
            'welcome_message': "🤖 Welcome to Multimodal Librarian! I can help you with questions and provide document-aware responses when you upload documents. Ask me anything!"
        }, connection_id)
        
    except Exception as e:
        logger.error(f"Error starting conversation: {e}")
        await manager.send_personal_message({
            'type': 'error',
            'message': 'Failed to start conversation'
        }, connection_id)


async def handle_resume_conversation(message_data: dict, connection_id: str, manager: ConnectionManager):
    """Resume an existing conversation thread after WebSocket reconnection."""
    thread_id = message_data.get('thread_id')
    if not thread_id:
        # No thread to resume — fall back to starting a new one
        await handle_start_conversation(connection_id, manager)
        return

    try:
        # Re-associate this connection with the existing thread
        manager.set_thread_id(connection_id, thread_id)

        # Ensure the ConversationManager has the thread loaded
        conv_manager, _, _ = await _get_legacy_components()
        if conv_manager:
            conversation = conv_manager.get_conversation(thread_id)
            if conversation is None:
                logger.warning(f"Thread {thread_id} not found during resume, starting new conversation")
                await handle_start_conversation(connection_id, manager)
                return

        logger.info(f"Resumed conversation {thread_id} for connection {connection_id}")

        await manager.send_personal_message({
            'type': 'conversation_resumed',
            'thread_id': thread_id,
            'timestamp': datetime.now().isoformat(),
            'features': {
                'rag_enabled': manager.rag_available,
                'document_aware_responses': manager.rag_available,
                'citation_support': manager.rag_available,
                'fallback_ai': True,
                'conversation_memory': True
            }
        }, connection_id)

    except Exception as e:
        logger.error(f"Error resuming conversation {thread_id}: {e}")
        # Fall back to starting a new conversation
        await handle_start_conversation(connection_id, manager)


async def handle_chat_message(message_data: dict, connection_id: str, manager: ConnectionManager):
    """Handle chat message from user with RAG integration and streaming support."""
    thread_id = manager.get_thread_id(connection_id)
    if not thread_id:
        await manager.send_personal_message({
            'type': 'error',
            'message': 'No active conversation. Please refresh the page.'
        }, connection_id)
        return
    
    request_id = str(uuid4())  # Generate request ID for tracking
    
    # Check if streaming is requested (default to True for better UX)
    use_streaming = message_data.get('streaming', True)
    
    try:
        user_message = message_data.get('message', '').strip()
        if not user_message:
            return
        
        # Add user message to conversation history
        manager.add_to_conversation_history(connection_id, "user", user_message)
        
        # Persist user message to ConversationManager thread for convert-to-knowledge
        thread_id_for_persist = manager.get_thread_id(connection_id)
        if thread_id_for_persist:
            await _persist_message(thread_id_for_persist, user_message, MessageType.USER)
        
        # Send processing indicator
        await manager.send_personal_message({
            'type': 'processing',
            'message': 'Processing your message...'
        }, connection_id)
        
        # Try RAG-powered response first
        if manager.rag_available and manager.rag_service:
            try:
                # Get conversation context for RAG
                conversation_context = manager.get_conversation_context(connection_id)
                
                # Check if RAG service supports streaming
                if use_streaming and hasattr(manager.rag_service, 'generate_response_stream'):
                    # Use streaming response
                    await handle_streaming_rag_response(
                        user_message=user_message,
                        connection_id=connection_id,
                        manager=manager,
                        conversation_context=conversation_context,
                        request_id=request_id
                    )
                else:
                    # Use non-streaming response
                    await handle_non_streaming_rag_response(
                        user_message=user_message,
                        connection_id=connection_id,
                        manager=manager,
                        conversation_context=conversation_context,
                        request_id=request_id
                    )
                
            except Exception as rag_error:
                logger.error(f"RAG processing failed: {rag_error}")
                # Fall back to legacy processing
                await handle_chat_message_fallback(user_message, connection_id, manager)
        else:
            # RAG not available, use fallback
            await handle_chat_message_fallback(user_message, connection_id, manager)
        
        # Send processing complete
        await manager.send_personal_message({
            'type': 'processing_complete'
        }, connection_id)
        
    except Exception as e:
        logger.error(f"Error processing chat message: {e}")
        await manager.send_personal_message({
            'type': 'error',
            'message': 'Failed to process your message. Please try again.'
        }, connection_id)


async def handle_streaming_rag_response(
    user_message: str,
    connection_id: str,
    manager: ConnectionManager,
    conversation_context: List[Dict[str, str]],
    request_id: str
):
    """Handle streaming RAG response with progressive content delivery."""
    start_time = datetime.now()
    cumulative_content = ""
    chunk_count = 0
    citations = []
    
    try:
        # Generate streaming RAG response
        async for chunk in manager.rag_service.generate_response_stream(
            query=user_message,
            user_id=connection_id,
            conversation_context=conversation_context
        ):
            # Check if connection is still active
            if not manager.is_connected(connection_id):
                logger.info(f"Connection {connection_id} disconnected, cancelling stream")
                return
            
            # Handle first chunk with citations
            if chunk_count == 0 and chunk.citations:
                citations = []
                for source in chunk.citations:
                    citations.append({
                        'document_id': getattr(source, 'document_id', ''),
                        'document_title': getattr(source, 'document_title', ''),
                        'page_number': getattr(source, 'page_number', None),
                        'relevance_score': round(getattr(source, 'relevance_score', 0), 3),
                        'excerpt': getattr(source, 'excerpt', ''),
                        'section_title': getattr(source, 'section_title', ''),
                        'chunk_id': getattr(source, 'chunk_id', ''),
                        'content_truncated': getattr(source, 'content_truncated', False),
                        'excerpt_error': getattr(source, 'excerpt_error', None),
                        'url': getattr(source, 'url', None),
                        'source_type': getattr(source, 'source_type', None),
                        'knowledge_source_type': getattr(source, 'knowledge_source_type', None),
                    })
                await manager.send_streaming_start(connection_id, citations)
            
            # Send content chunk
            if chunk.content:
                cumulative_content += chunk.content
                await manager.send_streaming_chunk(
                    connection_id=connection_id,
                    content=chunk.content,
                    chunk_index=chunk_count
                )
                chunk_count += 1
            
            # Handle final chunk with metadata
            if chunk.is_final:
                processing_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                
                # Add assistant response to conversation history (with citations)
                manager.add_to_conversation_history(connection_id, "assistant", cumulative_content, citations=citations)
                
                # Persist assistant response to ConversationManager thread
                stream_thread_id = manager.get_thread_id(connection_id)
                if stream_thread_id:
                    await _persist_message(stream_thread_id, cumulative_content, MessageType.SYSTEM, citations=citations)
                
                # Check for timeout or error in metadata
                chunk_metadata = chunk.metadata if chunk.metadata else {}
                error_type = chunk_metadata.get('error_type')
                
                # Send timeout notification if applicable
                if error_type == 'timeout':
                    await manager.send_personal_message({
                        'type': 'timeout_notification',
                        'message': 'Response generation timed out. The partial response has been delivered.',
                        'timestamp': datetime.now().isoformat()
                    }, connection_id)
                
                metadata = {
                    'rag_enabled': True,
                    'streaming': True,
                    'confidence_score': round(getattr(chunk, 'confidence_score', 0.8), 3),
                    'processing_time_ms': processing_time_ms,
                    'search_results_count': getattr(chunk, 'search_results_count', 0),
                    'fallback_used': getattr(chunk, 'fallback_used', False),
                    'tokens_used': getattr(chunk, 'tokens_used', 0),
                    'request_id': request_id,
                    'chunk_count': chunk_count,
                    'kg_retrieval_used': chunk_metadata.get('kg_retrieval_used', False),
                    'timeout_occurred': error_type == 'timeout'
                }
                
                await manager.send_streaming_complete(connection_id, metadata)
                
                logger.info(
                    f"Streaming RAG response completed for {connection_id}: "
                    f"{chunk_count} chunks, {processing_time_ms}ms (request_id: {request_id})"
                )
                return
        
    except Exception as e:
        logger.error(f"Streaming RAG error: {e}")
        
        # Send error and try non-streaming fallback
        await manager.send_streaming_error(
            connection_id=connection_id,
            error_message="Streaming interrupted. Attempting fallback...",
            recoverable=True
        )
        
        # Try non-streaming fallback
        try:
            await handle_non_streaming_rag_response(
                user_message=user_message,
                connection_id=connection_id,
                manager=manager,
                conversation_context=conversation_context,
                request_id=request_id
            )
        except Exception as fallback_error:
            logger.error(f"Non-streaming fallback also failed: {fallback_error}")
            await manager.send_personal_message({
                'type': 'error',
                'message': 'Unable to generate response. Please try again.'
            }, connection_id)


async def handle_non_streaming_rag_response(
    user_message: str,
    connection_id: str,
    manager: ConnectionManager,
    conversation_context: List[Dict[str, str]],
    request_id: str
):
    """Handle non-streaming RAG response (original implementation)."""
    # Generate RAG response
    rag_response = await manager.rag_service.generate_response(
        query=user_message,
        user_id=connection_id,
        conversation_context=conversation_context
    )
    
    # Format citations for display
    citations = []
    for source in rag_response.sources:
        citations.append({
            'document_id': source.document_id,
            'document_title': source.document_title,
            'page_number': source.page_number,
            'relevance_score': round(source.relevance_score, 3),
            'excerpt': source.excerpt,
            'section_title': source.section_title,
            'chunk_id': source.chunk_id,
            'content_truncated': getattr(source, 'content_truncated', False),
            'excerpt_error': getattr(source, 'excerpt_error', None),
            'url': getattr(source, 'url', None),
            'source_type': getattr(source, 'source_type', None),
            'knowledge_source_type': getattr(source, 'knowledge_source_type', None),
        })
    
    # Add assistant response to conversation history (with citations)
    manager.add_to_conversation_history(connection_id, "assistant", rag_response.response, citations=citations)
    
    # Persist assistant response to ConversationManager thread
    non_stream_thread_id = manager.get_thread_id(connection_id)
    if non_stream_thread_id:
        await _persist_message(non_stream_thread_id, rag_response.response, MessageType.SYSTEM, citations=citations)
    
    # Build response metadata
    response_metadata = {
        'rag_enabled': True,
        'streaming': False,
        'confidence_score': round(rag_response.confidence_score, 3),
        'processing_time_ms': rag_response.processing_time_ms,
        'search_results_count': rag_response.search_results_count,
        'fallback_used': rag_response.fallback_used,
        'ai_provider': rag_response.metadata.get('ai_provider', 'unknown'),
        'tokens_used': rag_response.tokens_used,
        'request_id': request_id,
        'kg_retrieval_used': rag_response.metadata.get('kg_retrieval_used', False)
    }

    # Apply relevance detection display formatting (Req 5.1, 5.2, 5.3)
    relevance_info = rag_response.metadata.get('relevance_detection')
    if relevance_info is not None:
        if not relevance_info.get('is_relevant', True):
            response_metadata['confidence_label'] = 'low confidence'
        if rag_response.confidence_score < 0.3:
            response_metadata['relevance_disclaimer'] = 'Results may not be relevant to your query'

    # Send RAG response back to client
    await manager.send_personal_message({
        'type': 'response',
        'response': {
            'text_content': rag_response.response,
            'visualizations': [],
            'knowledge_citations': citations
        },
        'metadata': response_metadata,
        'timestamp': datetime.now().isoformat()
    }, connection_id)
    
    # Track fallback usage if RAG used fallback internally
    if rag_response.fallback_used:
        fallback_service = _get_fallback_service()
        if fallback_service:
            try:
                from ...logging.ux_logger import log_fallback_response_usage

                # Generate fallback response for tracking purposes
                fallback_response = fallback_service.generate_fallback_response(user_message)
                await log_fallback_response_usage(
                    request_id=request_id,
                    fallback_response=fallback_response,
                    user_acceptance=True,
                    user_feedback="rag_internal_fallback"
                )
            except Exception as track_error:
                logger.debug(f"Failed to track RAG internal fallback: {track_error}")
    
    logger.info(
        f"Non-streaming RAG response sent for {connection_id}: "
        f"{rag_response.search_results_count} sources, "
        f"confidence {rag_response.confidence_score:.3f} (request_id: {request_id})"
    )


async def handle_chat_message_fallback(user_message: str, connection_id: str, manager: ConnectionManager):
    """Fallback chat message handling when RAG is not available."""
    request_id = str(uuid4())  # Generate request ID for tracking
    
    try:
        # Get fallback services lazily
        fallback_service = _get_fallback_service()
        expectation_manager = _get_expectation_manager()
        
        # Use the new fallback service for context-aware responses
        if fallback_service and expectation_manager:
            # Generate context-aware fallback response
            contextual_response = expectation_manager.create_contextual_response(
                user_message=user_message
            )
            
            # Generate fallback response for detailed tracking
            fallback_response = fallback_service.generate_fallback_response(user_message)
            
            # Track fallback response usage
            try:
                from ...logging.ux_logger import log_fallback_response_usage
                await log_fallback_response_usage(
                    request_id=request_id,
                    fallback_response=fallback_response,
                    user_acceptance=None,  # Could be enhanced with user feedback
                    user_feedback=None
                )
            except Exception as track_error:
                logger.debug(f"Failed to track fallback usage: {track_error}")
            
            # Add to conversation history
            response_text = contextual_response["response"]
            manager.add_to_conversation_history(connection_id, "assistant", response_text)
            
            # Persist assistant response to ConversationManager thread
            fallback_thread_id = manager.get_thread_id(connection_id)
            if fallback_thread_id:
                await _persist_message(fallback_thread_id, response_text, MessageType.SYSTEM)
            
            # Send enhanced response back to client
            await manager.send_personal_message({
                'type': 'response',
                'response': {
                    'text_content': response_text,
                    'visualizations': [],
                    'knowledge_citations': []
                },
                'metadata': {
                    'rag_enabled': False,
                    'fallback_mode': True,
                    'context_aware': True,
                    'processing_time_ms': 0,
                    'fallback_quality': fallback_response.response_quality.value,
                    'request_id': request_id
                },
                'quality_indicator': contextual_response.get("quality_indicator", {}),
                'system_status': contextual_response.get("system_status", {}),
                'capabilities': contextual_response.get("capabilities", {}),
                'user_guidance': contextual_response.get("user_guidance", {}),
                'timestamp': datetime.now().isoformat()
            }, connection_id)
            
            logger.info(f"Context-aware fallback response sent for {connection_id} (request_id: {request_id})")
            return
        
        # Lazy load components for legacy fallback
        conv_manager, query_proc, _ = await _get_legacy_components()
        
        # Legacy fallback if new services not available
        # Create message object for legacy system
        message = Message(
            message_id=str(uuid4()),
            content=user_message,
            multimedia_content=[],
            timestamp=datetime.now(),
            message_type='USER',
            knowledge_references=[]
        )
        
        # Try legacy query processor if available
        if query_proc and conv_manager:
            try:
                thread_id = manager.get_thread_id(connection_id)
                context = conv_manager.process_message(thread_id, message)
                
                query_context = QueryContext(
                    conversation_thread=context.conversation_thread if hasattr(context, 'conversation_thread') else None,
                    user_id=connection_id
                )
                
                search_result = query_proc.process_query(
                    query=user_message,
                    context=query_context
                )
                
                # Convert search result to response format
                response_text = f"Found {search_result.total_results} relevant results:\n\n"
                
                # Add content from top chunks
                for i, chunk in enumerate(search_result.chunks[:3]):  # Show top 3 results
                    response_text += f"{i+1}. {chunk.content[:200]}...\n\n"
                
                citations = [citation.__dict__ for citation in search_result.citations]
                
            except Exception as legacy_error:
                logger.warning(f"Legacy query processor failed: {legacy_error}")
                response_text = await generate_simple_ai_response(user_message, request_id, manager)
                citations = []
        else:
            # Simple AI response using AI service directly
            response_text = await generate_simple_ai_response(user_message, request_id, manager)
            citations = []
        
        # Add to conversation history
        manager.add_to_conversation_history(connection_id, "assistant", response_text)
        
        # Persist assistant response to ConversationManager thread
        legacy_thread_id = manager.get_thread_id(connection_id)
        if legacy_thread_id:
            await _persist_message(legacy_thread_id, response_text, MessageType.SYSTEM)
        
        # Send response back to client
        await manager.send_personal_message({
            'type': 'response',
            'response': {
                'text_content': response_text,
                'visualizations': [],
                'knowledge_citations': citations
            },
            'metadata': {
                'rag_enabled': False,
                'fallback_mode': True,
                'context_aware': False,
                'processing_time_ms': 0,
                'request_id': request_id
            },
            'timestamp': datetime.now().isoformat()
        }, connection_id)
        
    except Exception as e:
        logger.error(f"Fallback processing failed: {e}")
        # Ultimate fallback - simple response with context awareness
        expectation_manager = _get_expectation_manager()
        if expectation_manager:
            try:
                simple_contextual = expectation_manager.create_contextual_response(
                    user_message=user_message,
                    base_response=f"I received your message: '{user_message[:50]}...'\n\nI'm currently experiencing some technical difficulties with document processing, but the chat system is working. Please try again or contact support if the issue persists."
                )
                
                # Track emergency fallback usage
                fallback_service = _get_fallback_service()
                if fallback_service:
                    try:
                        from ...logging.ux_logger import log_fallback_response_usage
                        emergency_fallback = fallback_service.generate_fallback_response(user_message)
                        await log_fallback_response_usage(
                            request_id=request_id,
                            fallback_response=emergency_fallback,
                            user_acceptance=None,
                            user_feedback="emergency_fallback_used"
                        )
                    except Exception as track_error:
                        logger.debug(f"Failed to track emergency fallback: {track_error}")
                
                await manager.send_personal_message({
                    'type': 'response',
                    'response': {
                        'text_content': simple_contextual["response"],
                        'visualizations': [],
                        'knowledge_citations': []
                    },
                    'metadata': {
                        'rag_enabled': False,
                        'emergency_fallback': True,
                        'context_aware': True,
                        'request_id': request_id
                    },
                    'quality_indicator': simple_contextual.get("quality_indicator", {}),
                    'system_status': simple_contextual.get("system_status", {}),
                    'timestamp': datetime.now().isoformat()
                }, connection_id)
                return
            except Exception as ctx_error:
                logger.error(f"Context-aware emergency fallback failed: {ctx_error}")
        
        # Final emergency fallback
        simple_response = f"I received your message: '{user_message[:50]}...'\n\nI'm currently experiencing some technical difficulties with document processing, but the chat system is working. Please try again or contact support if the issue persists."
        
        await manager.send_personal_message({
            'type': 'response',
            'response': {
                'text_content': simple_response,
                'visualizations': [],
                'knowledge_citations': []
            },
            'metadata': {
                'rag_enabled': False,
                'emergency_fallback': True,
                'context_aware': False,
                'request_id': request_id
            },
            'timestamp': datetime.now().isoformat()
        }, connection_id)


async def generate_simple_ai_response(user_message: str, request_id: str, manager: ConnectionManager) -> str:
    """Generate a simple AI response when RAG is not available."""
    if request_id is None:
        request_id = str(uuid4())
    
    try:
        # Try to use the fallback service first
        fallback_service = _get_fallback_service()
        if fallback_service:
            try:
                fallback_response = fallback_service.generate_fallback_response(user_message)
                
                # Track fallback usage
                try:
                    from ...logging.ux_logger import log_fallback_response_usage
                    await log_fallback_response_usage(
                        request_id=request_id,
                        fallback_response=fallback_response,
                        user_acceptance=None,
                        user_feedback="simple_ai_fallback"
                    )
                except Exception as track_error:
                    logger.debug(f"Failed to track fallback usage: {track_error}")
                
                return fallback_response.response_text
            except Exception as fallback_error:
                logger.warning(f"Fallback service failed: {fallback_error}")
        
        # Try AI service directly
        if manager.ai_service:
            # Use AI service directly for simple response
            response = await manager.ai_service.generate_response(
                messages=[
                    {"role": "system", "content": "You are a helpful AI assistant. The user's document library is not currently available, so provide general assistance."},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.7,
                max_tokens=1024
            )
            return response.content
        else:
            # No AI service available - use basic template response
            return f"I received your message: '{user_message[:50]}...'\n\nThe AI service is currently unavailable. This is a basic chat interface that's working correctly, but advanced AI features are not accessible right now."
    
    except Exception as e:
        logger.error(f"Simple AI response generation failed: {e}")
        return f"I received your message about '{user_message[:50]}...'\n\nI'm experiencing technical difficulties but the chat interface is working. Please try again later or contact support."


async def handle_files_uploaded(message_data: dict, connection_id: str, manager: ConnectionManager):
    """Handle notification of uploaded files."""
    thread_id = manager.get_thread_id(connection_id)
    if not thread_id:
        return
    
    try:
        files = message_data.get('files', [])
        
        # Send acknowledgment
        await manager.send_personal_message({
            'type': 'files_processed',
            'message': f'Successfully processed {len(files)} file(s). You can now ask questions about the uploaded content.',
            'files': files
        }, connection_id)
        
    except Exception as e:
        logger.error(f"Error handling uploaded files: {e}")


async def handle_export_conversation(message_data: dict, connection_id: str, manager: ConnectionManager):
    """Handle conversation export request."""
    thread_id = manager.get_thread_id(connection_id)
    if not thread_id:
        return
    
    try:
        export_format = message_data.get('format', 'txt')
        
        # Lazy load components
        _, _, exp_engine = await _get_legacy_components()
        
        # Build export content from ConnectionManager's conversation history
        # (the RAG chat flow stores messages here, not in ConversationManager)
        history = manager.get_conversation_context(connection_id)

        # Fallback: for reactivated conversations the in-memory history
        # is empty because no new messages were sent via WebSocket.
        # Load from the database instead.
        if not history and thread_id:
            try:
                from ..dependencies.services import get_conversation_manager
                conv_mgr = await get_conversation_manager()
                conversation = conv_mgr.get_conversation(thread_id)
                if conversation and conversation.messages:
                    history = []
                    for msg in conversation.messages:
                        # Map DB message_type to WebSocket role names
                        role = msg.message_type.value
                        if role.lower() in ("system", "assistant"):
                            role = "assistant"
                        else:
                            role = "user"
                        entry = {
                            "role": role,
                            "content": msg.content,
                            "timestamp": msg.timestamp.isoformat(),
                        }
                        if msg.knowledge_references:
                            citations = [
                                ref for ref in msg.knowledge_references
                                if isinstance(ref, dict)
                            ]
                            if citations:
                                entry["citations"] = citations
                        history.append(entry)
            except Exception as e:
                logger.warning(
                    f"Failed to load conversation from DB for export: {e}"
                )

        if not history:
            await manager.send_personal_message({
                'type': 'error',
                'message': 'No conversation to export'
            }, connection_id)
            return
        
        content_parts = []
        content_parts.append("# Conversation Export")
        content_parts.append(f"**Thread ID:** {thread_id}")
        content_parts.append(f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        content_parts.append("")
        
        for msg in history:
            sender = "User" if msg.get("role") == "user" else "Assistant"
            timestamp = msg.get("timestamp", "")
            if timestamp:
                try:
                    ts = datetime.fromisoformat(timestamp).strftime('%H:%M:%S')
                except (ValueError, TypeError):
                    ts = timestamp
                content_parts.append(f"## {sender} ({ts})")
            else:
                content_parts.append(f"## {sender}")
            
            msg_content = msg.get("content", "")
            
            # Replace inline [Source N] references with clickable links
            citations = msg.get("citations", [])
            if citations and msg.get("role") == "assistant":
                import re

                # First expand multi-source patterns: [Source 1, Source 3] -> [Source 1] [Source 3]
                def _expand_multi(m):
                    inner = m.group(1)
                    parts = [p.strip() for p in inner.split(',')]
                    return ' '.join(f'[{p}]' for p in parts)
                msg_content = re.sub(r'\[(Source \d+(?:\s*,\s*Source \d+)+)\]', _expand_multi, msg_content)
                
                # Now replace individual [Source N] with markdown links
                def _replace_source_ref(match):
                    idx = int(match.group(1)) - 1
                    if 0 <= idx < len(citations):
                        url = citations[idx].get("url", "")
                        if url:
                            return f"[Source {idx+1}]({url})"
                    return match.group(0)
                msg_content = re.sub(r'\[Source (\d+)\]', _replace_source_ref, msg_content)
            
            content_parts.append(msg_content)
            
            # Add citations for assistant messages
            citations = msg.get("citations", [])
            if citations and msg.get("role") == "assistant":
                content_parts.append("")
                content_parts.append("**Sources:**")
                for i, cite in enumerate(citations, 1):
                    title = cite.get("document_title", "Unknown")
                    url = cite.get("url", "")
                    relevance = cite.get("relevance_score", 0)
                    if url:
                        content_parts.append(f"  {i}. [{title}]({url}) - {int(relevance * 100)}% relevant")
                    else:
                        page = cite.get("page_number", "")
                        page_str = f" (p.{page})" if page else ""
                        content_parts.append(f"  {i}. {title}{page_str} - {int(relevance * 100)}% relevant")
            
            content_parts.append("")
        
        export_content = MultimediaResponse(
            text_content="\n".join(content_parts),
            visualizations=[],
            audio_content=None,
            video_content=None,
            knowledge_citations=[],
            export_metadata=None
        )
        
        # Generate export file
        if exp_engine:
            export_data = exp_engine.export_to_format(export_content, export_format)
            
            # Send base64-encoded file data for client-side download
            await manager.send_personal_message({
                'type': 'export_ready',
                'message': f'Conversation exported to {export_format.upper()} format',
                'format': export_format,
                'size': len(export_data),
                'data': base64.b64encode(export_data).decode('utf-8')
            }, connection_id)
        else:
            await manager.send_personal_message({
                'type': 'error',
                'message': 'Export functionality is not available'
            }, connection_id)
        
    except Exception as e:
        logger.error(f"Error exporting conversation: {e}")
        await manager.send_personal_message({
            'type': 'error',
            'message': 'Failed to export conversation'
        }, connection_id)


def create_export_content(thread: ConversationThread) -> MultimediaResponse:
    """Create export content from conversation thread."""
    content_parts = []
    content_parts.append(f"# Conversation Export")
    content_parts.append(f"**Started:** {thread.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    content_parts.append(f"**Thread ID:** {thread.thread_id}")
    content_parts.append("")
    
    for message in thread.messages:
        sender = "User" if message.message_type == 'USER' else "Assistant"
        timestamp = message.timestamp.strftime('%H:%M:%S')
        content_parts.append(f"## {sender} ({timestamp})")
        content_parts.append(message.content)
        content_parts.append("")
    
    return MultimediaResponse(
        text_content="\n".join(content_parts),
        visualizations=[],
        audio_content=None,
        video_content=None,
        knowledge_citations=[],
        export_metadata=None
    )


@router.post("/api/v1/upload")
async def upload_file(file: UploadFile = File(...)):
    """Handle file upload through chat interface."""
    try:
        # Validate file
        if file.size > 100 * 1024 * 1024:  # 100MB limit
            raise HTTPException(status_code=413, detail="File too large")
        
        # Read file content
        content = await file.read()
        
        # Process file based on type
        # This would integrate with the PDF processor and other components
        # For now, just acknowledge the upload
        
        return {
            "message": "File uploaded successfully",
            "filename": file.filename,
            "size": len(content),
            "content_type": file.content_type
        }
        
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")


@router.get("/chat", response_class=HTMLResponse)
async def serve_chat_interface():
    """Serve the main chat interface."""
    import os

    # Try multiple paths to find the static index.html
    possible_paths = [
        os.path.join(os.path.dirname(__file__), "..", "..", "static", "index.html"),
        "src/multimodal_librarian/static/index.html",
        "multimodal_librarian/static/index.html",
        "/app/src/multimodal_librarian/static/index.html",  # Docker path
    ]
    
    for path in possible_paths:
        try:
            with open(path, "r") as f:
                return HTMLResponse(content=f.read())
        except FileNotFoundError:
            continue
    
    raise HTTPException(status_code=404, detail="Chat interface not found")



@router.get("/health")
async def chat_health(
    manager: ConnectionManager = Depends(get_connection_manager_with_services)
):
    """
    Health check for chat service with RAG integration.
    
    Uses dependency injection for ConnectionManager.
    """
    rag_status = {}
    if manager.rag_service:
        try:
            rag_status = manager.rag_service.get_service_status()
        except Exception as e:
            rag_status = {"status": "error", "error": str(e)}
    
    # Get fallback services status
    fallback_service = _get_fallback_service()
    expectation_manager = _get_expectation_manager()
    
    return {
        "status": "healthy",
        "service": "chat",
        "active_connections": len(manager.active_connections),
        "active_threads": len(manager.user_threads),
        "features": {
            "rag_integration": manager.rag_available,
            "document_aware_responses": manager.rag_available,
            "citation_support": manager.rag_available,
            "conversation_memory": True,
            "fallback_ai": True,
            "context_aware_fallbacks": fallback_service is not None,
            "expectation_management": expectation_manager is not None
        },
        "rag_status": rag_status,
        "di_pattern": "enabled"  # Indicates DI is being used
    }


@router.get("/api/chat/capabilities")
async def get_chat_capabilities(
    manager: ConnectionManager = Depends(get_connection_manager_with_services)
):
    """
    Get current chat capabilities and system status.
    
    Uses dependency injection for ConnectionManager.
    """
    try:
        expectation_manager = _get_expectation_manager()
        
        if expectation_manager:
            context = expectation_manager.get_expectation_context()
            
            return {
                "status": "success",
                "current_mode": context.current_mode.value,
                "quality_indicator": {
                    "symbol": context.quality_indicator.symbol,
                    "level": context.quality_indicator.level.value,
                    "description": context.quality_indicator.description,
                    "user_message": context.quality_indicator.user_message,
                    "color_code": context.quality_indicator.color_code
                },
                "capabilities": {
                    "available": context.available_capabilities,
                    "loading": context.loading_capabilities,
                    "estimated_times": context.estimated_times
                },
                "progress": {
                    "percentage": context.progress_percentage,
                    "upgrade_message": context.upgrade_message
                },
                "user_guidance": {
                    "limitations": context.limitations,
                    "alternatives": context.alternatives
                },
                "rag_available": manager.rag_available,
                "timestamp": datetime.now().isoformat()
            }
        else:
            # Fallback response if expectation manager not available
            return {
                "status": "limited",
                "current_mode": "startup",
                "quality_indicator": {
                    "symbol": "⚡",
                    "level": "basic",
                    "description": "Basic mode",
                    "user_message": "System starting up",
                    "color_code": "#FFA500"
                },
                "capabilities": {
                    "available": ["simple_text"],
                    "loading": ["basic_chat", "document_analysis"],
                    "estimated_times": {"full_capabilities": 120}
                },
                "progress": {
                    "percentage": 10.0,
                    "upgrade_message": "System loading - please wait"
                },
                "user_guidance": {
                    "limitations": ["Advanced AI not ready"],
                    "alternatives": ["Ask simple questions"]
                },
                "rag_available": manager.rag_available,
                "timestamp": datetime.now().isoformat()
            }
    
    except Exception as e:
        logger.error(f"Error getting chat capabilities: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/api/chat/progress")
async def get_chat_progress(
    manager: ConnectionManager = Depends(get_connection_manager_with_services)
):
    """
    Get real-time progress update for chat capabilities.
    
    Uses dependency injection for ConnectionManager.
    """
    try:
        expectation_manager = _get_expectation_manager()
        
        if expectation_manager:
            progress_update = expectation_manager.get_progress_update()
            return {
                "status": "success",
                "rag_available": manager.rag_available,
                **progress_update
            }
        else:
            return {
                "status": "limited",
                "progress_percentage": 10.0,
                "current_phase": "startup",
                "quality_indicator": {"symbol": "⚡", "description": "Starting up"},
                "status_message": "System loading - please wait",
                "capabilities_ready": 1,
                "capabilities_loading": 5,
                "estimated_completion": 120,
                "rag_available": manager.rag_available,
                "timestamp": datetime.now().isoformat()
            }
    
    except Exception as e:
        logger.error(f"Error getting chat progress: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
