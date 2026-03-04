"""
Enhanced Chat Service with RAG Integration

This demonstrates how the existing chat service would be modified to integrate
with the new RAG service for document-aware responses.
"""

import asyncio
import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect

# Import existing chat service components
from .chat_service import (
    ChatMessageData,
    ChatService,
    ChatSession,
    ConnectionManager,
    ConversationManager,
)

# Import RAG service class for type hints - actual instances come from DI
from .rag_service_cached import CachedRAGService

logger = logging.getLogger(__name__)

class EnhancedConnectionManager(ConnectionManager):
    """Enhanced connection manager with RAG integration."""
    
    def __init__(self, rag_service: CachedRAGService = None):
        super().__init__()
        # RAG service is now injected, not fetched from global singleton
        self.rag_service = rag_service
        
        # Add RAG-specific message handlers
        self.message_handlers.update({
            'document_query': self._handle_document_query,
            'search_documents': self._handle_search_documents,
            'get_document_context': self._handle_get_document_context
        })
    
    async def _handle_user_message(self, connection_id: str, message_data: Dict[str, Any]):
        """Enhanced user message handler with RAG integration."""
        content = message_data.get('content', '').strip()
        if not content:
            return
        
        # Check if this should be a document-aware response
        use_rag = message_data.get('use_documents', True)  # Default to using documents
        document_filter = message_data.get('document_filter')  # Optional document filtering
        
        if use_rag:
            # Process with RAG for document-aware response
            response = await self.process_user_message_with_rag(
                connection_id=connection_id,
                message_content=content,
                document_filter=document_filter,
                context=message_data.get('context')
            )
        else:
            # Process with standard AI response
            response = await self.process_user_message(
                connection_id=connection_id,
                message_content=content,
                context=message_data.get('context')
            )
        
        if response:
            await self.send_message(connection_id, response)
    
    async def _handle_document_query(self, connection_id: str, message_data: Dict[str, Any]):
        """Handle explicit document queries."""
        query = message_data.get('query', '').strip()
        document_ids = message_data.get('document_ids', [])
        
        if not query:
            await self.send_message(connection_id, {
                "type": "error",
                "content": "Query cannot be empty",
                "timestamp": datetime.utcnow().isoformat()
            })
            return
        
        session = self.active_connections[connection_id]
        
        try:
            # Get conversation context
            conversation_context = self.conversation_manager.get_context_for_ai(session)
            
            # Generate RAG response
            rag_response = await self.rag_service.generate_response(
                query=query,
                user_id=session.user_id,
                conversation_context=conversation_context,
                document_filter=document_ids if document_ids else None
            )
            
            # Send enhanced response with document information
            await self.send_message(connection_id, {
                "type": "document_response",
                "content": rag_response.response,
                "sources": [
                    {
                        "document_id": source.document_id,
                        "document_title": source.document_title,
                        "page_number": source.page_number,
                        "relevance_score": source.relevance_score,
                        "excerpt": source.excerpt,
                        "url": source.url,
                        "source_type": source.source_type,
                    }
                    for source in rag_response.sources
                ],
                "confidence_score": rag_response.confidence_score,
                "processing_time_ms": rag_response.processing_time_ms,
                "fallback_used": rag_response.fallback_used,
                "timestamp": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Document query failed: {e}")
            await self.send_message(connection_id, {
                "type": "error",
                "content": "Failed to process document query. Please try again.",
                "timestamp": datetime.utcnow().isoformat()
            })
    
    async def _handle_search_documents(self, connection_id: str, message_data: Dict[str, Any]):
        """Handle document search requests."""
        query = message_data.get('query', '').strip()
        limit = message_data.get('limit', 10)
        
        if not query:
            await self.send_message(connection_id, {
                "type": "error",
                "content": "Search query cannot be empty",
                "timestamp": datetime.utcnow().isoformat()
            })
            return
        
        session = self.active_connections[connection_id]
        
        try:
            # Search documents
            search_results = await self.rag_service.search_documents(
                query=query,
                user_id=session.user_id,
                limit=limit
            )
            
            # Format results for client
            formatted_results = [
                {
                    "chunk_id": result.chunk_id,
                    "document_id": result.document_id,
                    "document_title": result.document_title,
                    "content_preview": result.content[:200] + "..." if len(result.content) > 200 else result.content,
                    "page_number": result.page_number,
                    "section_title": result.section_title,
                    "similarity_score": result.similarity_score
                }
                for result in search_results
            ]
            
            await self.send_message(connection_id, {
                "type": "search_results",
                "query": query,
                "results": formatted_results,
                "total_found": len(formatted_results),
                "timestamp": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Document search failed: {e}")
            await self.send_message(connection_id, {
                "type": "error",
                "content": "Document search failed. Please try again.",
                "timestamp": datetime.utcnow().isoformat()
            })
    
    async def _handle_get_document_context(self, connection_id: str, message_data: Dict[str, Any]):
        """Handle requests for document context information."""
        session = self.active_connections[connection_id]
        
        try:
            # Get RAG service status for this user
            rag_status = self.rag_service.get_service_status()
            
            await self.send_message(connection_id, {
                "type": "document_context",
                "rag_available": rag_status['status'] == 'active',
                "opensearch_connected": rag_status['opensearch_connected'],
                "features": rag_status['features'],
                "user_id": session.user_id,
                "timestamp": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            logger.error(f"Failed to get document context: {e}")
            await self.send_message(connection_id, {
                "type": "error",
                "content": "Failed to get document context information.",
                "timestamp": datetime.utcnow().isoformat()
            })
    
    async def process_user_message_with_rag(
        self, 
        connection_id: str, 
        message_content: str,
        document_filter: Optional[List[str]] = None,
        context: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Process user message with RAG for document-aware responses."""
        if connection_id not in self.active_connections:
            return None
        
        session = self.active_connections[connection_id]
        
        try:
            # Create user message
            user_message = ChatMessageData(
                id=str(uuid4()),
                content=message_content,
                message_type="user",
                timestamp=datetime.utcnow(),
                user_id=session.user_id,
                connection_id=connection_id
            )
            
            # Add to conversation history
            await self.conversation_manager.add_message(session, user_message)
            session.message_count += 1
            
            # Get conversation context for RAG
            conversation_context = self.conversation_manager.get_context_for_ai(session)
            
            # Generate RAG response
            rag_response = await self.rag_service.generate_response(
                query=message_content,
                user_id=session.user_id,
                conversation_context=conversation_context,
                document_filter=document_filter
            )
            
            # Create assistant message with RAG metadata
            assistant_message = ChatMessageData(
                id=str(uuid4()),
                content=rag_response.response,
                message_type="assistant",
                timestamp=datetime.utcnow(),
                user_id=session.user_id,
                connection_id=connection_id,
                sources=[source.document_id for source in rag_response.sources],
                metadata={
                    "rag_used": True,
                    "confidence_score": rag_response.confidence_score,
                    "processing_time_ms": rag_response.processing_time_ms,
                    "search_results_count": rag_response.search_results_count,
                    "fallback_used": rag_response.fallback_used,
                    "tokens_used": rag_response.tokens_used,
                    **rag_response.metadata
                }
            )
            
            # Add assistant response to conversation history
            await self.conversation_manager.add_message(session, assistant_message)
            
            # Format response with citations
            response_data = {
                "type": "assistant",
                "content": rag_response.response,
                "message_id": assistant_message.id,
                "timestamp": assistant_message.timestamp.isoformat(),
                "sources": [
                    {
                        "document_id": source.document_id,
                        "document_title": source.document_title,
                        "page_number": source.page_number,
                        "relevance_score": source.relevance_score,
                        "excerpt": source.excerpt,
                        "section_title": source.section_title,
                        "url": source.url,
                        "source_type": source.source_type,
                    }
                    for source in rag_response.sources
                ],
                "metadata": {
                    "rag_enabled": True,
                    "confidence_score": rag_response.confidence_score,
                    "processing_time_ms": rag_response.processing_time_ms,
                    "fallback_used": rag_response.fallback_used,
                    "search_results": rag_response.search_results_count
                }
            }
            
            return response_data
            
        except Exception as e:
            logger.error(f"Error processing RAG message for {connection_id}: {e}")
            
            # Fallback to standard AI response
            logger.info(f"Falling back to standard AI response for {connection_id}")
            return await self.process_user_message(connection_id, message_content, context)

class EnhancedChatService(ChatService):
    """Enhanced chat service with RAG integration."""
    
    def __init__(self, rag_service: CachedRAGService = None):
        super().__init__()
        # RAG service is now injected, not fetched from global singleton
        self.rag_service = rag_service
        # Replace connection manager with enhanced version that uses injected RAG service
        self.connection_manager = EnhancedConnectionManager(rag_service=rag_service)
    
    async def handle_websocket_connection(self, websocket: WebSocket, user_id: str = None):
        """Handle WebSocket connection with RAG capabilities."""
        connection_id = await self.connection_manager.connect(websocket, user_id)
        
        try:
            # Send enhanced welcome message with RAG information
            rag_status = self.rag_service.get_service_status()
            
            await self.connection_manager.send_message(connection_id, {
                "type": "system",
                "content": "🤖 Welcome to Multimodal Librarian with Document Intelligence! I can now answer questions using your uploaded documents and provide citations.",
                "timestamp": datetime.utcnow().isoformat(),
                "features": {
                    "enhanced_context": True,
                    "conversation_summarization": True,
                    "typing_indicators": True,
                    "message_routing": True,
                    "multi_session_support": True,
                    "intelligent_suggestions": True,
                    # RAG-specific features
                    "document_aware_responses": True,
                    "citation_support": True,
                    "document_search": True,
                    "context_ranking": True,
                    "fallback_responses": True
                },
                "rag_status": {
                    "available": rag_status['status'] == 'active',
                    "opensearch_connected": rag_status['opensearch_connected'],
                    "document_search_enabled": True
                }
            })
            
            # Main message loop (same as parent class)
            while True:
                try:
                    data = await websocket.receive_text()
                    message_data = json.loads(data)
                    await self.connection_manager.handle_message(connection_id, message_data)
                    
                except json.JSONDecodeError:
                    await self.connection_manager.send_message(connection_id, {
                        "type": "error",
                        "content": "Invalid message format. Please send valid JSON.",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                except Exception as e:
                    logger.error(f"Error in enhanced RAG message loop for {connection_id}: {e}")
                    await self.connection_manager.send_message(connection_id, {
                        "type": "error",
                        "content": "An error occurred processing your message.",
                        "timestamp": datetime.utcnow().isoformat()
                    })
        
        except WebSocketDisconnect:
            logger.info(f"Enhanced RAG WebSocket disconnected normally: {connection_id}")
        except Exception as e:
            logger.error(f"Enhanced RAG WebSocket error for {connection_id}: {e}")
        finally:
            self.connection_manager.disconnect(connection_id)
    
    def get_chat_status(self) -> Dict[str, Any]:
        """Get enhanced chat service status with RAG information."""
        base_status = super().get_chat_status()
        rag_status = self.rag_service.get_service_status()
        
        # Enhance status with RAG information
        base_status["features"].update({
            "document_aware_responses": True,
            "citation_support": True,
            "document_search": True,
            "context_ranking": True,
            "query_enhancement": True,
            "confidence_scoring": True
        })
        
        base_status["rag_integration"] = {
            "status": rag_status['status'],
            "opensearch_connected": rag_status['opensearch_connected'],
            "configuration": rag_status['configuration'],
            "features": rag_status['features']
        }
        
        base_status["message_types"].extend([
            "document_query",
            "search_documents", 
            "get_document_context"
        ])
        
        return base_status

# DEPRECATED: Module-level singleton pattern removed in favor of FastAPI DI
# Use api/dependencies/services.py get_cached_rag_service() to get RAG service
# and inject it into EnhancedChatService
#
# Migration guide:
#   Old: from .chat_service_with_rag import get_enhanced_chat_service
#        service = get_enhanced_chat_service()
#
#   New: from ..api.dependencies import get_cached_rag_service
#        # In FastAPI endpoint:
#        async def endpoint(rag_service = Depends(get_cached_rag_service)):
#            chat_service = EnhancedChatService(rag_service=rag_service)
#            ...