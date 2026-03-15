"""
AI-Powered Chat Router - WebSocket and REST endpoints for intelligent chat

This router provides both WebSocket real-time chat and REST API endpoints
for AI-powered conversations with document context support.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...config import get_settings
from ...services.ai_service_cached import AIProvider
from ...services.chat_service import get_chat_service
from ..dependencies import get_cached_ai_service_di, get_cached_rag_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["AI Chat"])

# Pydantic models for API requests/responses
class ChatMessageRequest(BaseModel):
    """Request model for chat messages."""
    content: str = Field(..., min_length=1, max_length=10000, description="Message content")
    context: Optional[str] = Field(None, description="Additional context for the message")
    user_id: Optional[str] = Field(None, description="User identifier")
    preferred_provider: Optional[str] = Field(None, description="Preferred AI provider")

class ChatMessageResponse(BaseModel):
    """Response model for chat messages."""
    id: str = Field(..., description="Message ID")
    content: str = Field(..., description="AI response content")
    type: str = Field(..., description="Message type")
    timestamp: str = Field(..., description="Response timestamp")
    sources: List[Any] = Field(default=[], description="Source documents with metadata")
    metadata: Dict[str, Any] = Field(default={}, description="Response metadata")

class ChatHistoryResponse(BaseModel):
    """Response model for chat history."""
    messages: List[Dict[str, Any]] = Field(..., description="Chat messages")
    total_count: int = Field(..., description="Total message count")
    user_id: str = Field(..., description="User identifier")

class ChatStatusResponse(BaseModel):
    """Response model for chat status."""
    status: str = Field(..., description="Chat service status")
    active_connections: int = Field(..., description="Number of active connections")
    active_users: int = Field(..., description="Number of active users")
    ai_providers: List[str] = Field(..., description="Available AI providers")
    features: Dict[str, bool] = Field(..., description="Available features")

# Initialize chat service (stateless, no external connections)
# Note: RAG service will be injected via dependency injection in endpoints
settings = get_settings()

# Global chat service - RAG will be injected on first WebSocket connection
_chat_service_instance = None

def _get_chat_service_with_rag(rag_service=None):
    """Get chat service with RAG injection."""
    global _chat_service_instance
    if _chat_service_instance is None:
        _chat_service_instance = get_chat_service(rag_service=rag_service)
    elif rag_service is not None:
        _chat_service_instance.set_rag_service(rag_service)
    return _chat_service_instance

@router.websocket("/ws")
async def websocket_chat_endpoint(
    websocket: WebSocket, 
    user_id: Optional[str] = Query(None),
    rag_service = Depends(get_cached_rag_service)
):
    """
    WebSocket endpoint for real-time AI-powered chat.
    
    Supports:
    - Real-time bidirectional communication
    - Conversation context and history
    - AI provider fallback
    - Document context integration via RAG
    """
    logger.info(f"WebSocket chat connection attempt for user: {user_id}, RAG available: {rag_service is not None}")
    
    # Get chat service with RAG injection
    chat_service = _get_chat_service_with_rag(rag_service)
    
    try:
        await chat_service.handle_websocket_connection(websocket, user_id)
    except WebSocketDisconnect:
        logger.info(f"WebSocket chat disconnected for user: {user_id}")
    except Exception as e:
        logger.error(f"WebSocket chat error for user {user_id}: {e}")

@router.post("/message", response_model=ChatMessageResponse)
async def send_chat_message(
    request: ChatMessageRequest,
    ai_service = Depends(get_cached_ai_service_di),
    rag_service = Depends(get_cached_rag_service)
):
    """
    Send a chat message and get AI response via REST API.
    
    This endpoint provides an alternative to WebSocket for applications
    that prefer REST API communication. When RAG service is available,
    it will include document sources in the response.
    """
    try:
        # Determine preferred provider
        preferred_provider = None
        if request.preferred_provider:
            try:
                preferred_provider = AIProvider(request.preferred_provider.lower())
            except ValueError:
                logger.warning(f"Invalid AI provider: {request.preferred_provider}")
        
        # Try to use RAG service for document-enhanced responses
        sources = []
        ai_response = None
        
        try:
            if rag_service is not None:
                # Use RAG for document-enhanced response
                rag_response = await rag_service.generate_response(
                    query=request.content,
                    user_id=request.user_id or "anonymous"
                )
                
                # Extract sources from RAG response
                if hasattr(rag_response, 'sources') and rag_response.sources:
                    sources = [
                        {
                            "document_id": source.document_id,
                            "title": source.document_title,
                            "relevance_score": source.relevance_score,
                            "location": f"Page {source.page_number}" if source.page_number else source.section_title,
                            "knowledge_source_type": getattr(source, 'knowledge_source_type', None),
                            "source_type": getattr(source, 'source_type', None),
                            "url": getattr(source, 'url', None),
                        }
                        for source in rag_response.sources
                    ]
                
                # Create AI response from RAG response
                from ...services.ai_service import AIResponse
                ai_response = AIResponse(
                    content=rag_response.response,
                    provider="rag",
                    model="rag_enhanced",
                    tokens_used=0,
                    processing_time_ms=rag_response.processing_time_ms,
                    confidence_score=rag_response.confidence_score
                )
                
                logger.info(f"Chat message processed with RAG - {len(sources)} sources found")
                
        except Exception as rag_error:
            logger.warning(f"RAG service error, falling back to direct AI: {rag_error}")
        
        # Fall back to direct AI if RAG not available or failed
        if ai_response is None:
            # Prepare messages for AI
            messages = [{"role": "user", "content": request.content}]
            
            # Generate AI response
            ai_response = await ai_service.generate_response(
                messages=messages,
                context=request.context,
                preferred_provider=preferred_provider
            )
        
        # Create response
        response = ChatMessageResponse(
            id=f"msg_{datetime.utcnow().timestamp()}",
            content=ai_response.content,
            type="assistant",
            timestamp=datetime.utcnow().isoformat(),
            sources=sources,
            metadata={
                "provider": ai_response.provider,
                "model": ai_response.model,
                "tokens_used": ai_response.tokens_used,
                "processing_time_ms": ai_response.processing_time_ms,
                "confidence_score": ai_response.confidence_score,
                "rag_enhanced": len(sources) > 0
            }
        )
        
        logger.info(f"Chat message processed successfully with {ai_response.provider}")
        return response
        
    except Exception as e:
        logger.error(f"Error processing chat message: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process chat message: {str(e)}"
        )

@router.get("/history/{user_id}", response_model=ChatHistoryResponse)
async def get_chat_history(
    user_id: str,
    limit: int = Query(50, ge=1, le=200, description="Number of messages to retrieve")
):
    """
    Get chat history for a specific user.
    
    Returns the most recent messages in chronological order.
    """
    try:
        messages = await chat_service.get_conversation_history(user_id, limit)
        
        return ChatHistoryResponse(
            messages=messages,
            total_count=len(messages),
            user_id=user_id
        )
        
    except Exception as e:
        logger.error(f"Error retrieving chat history for user {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve chat history: {str(e)}"
        )

@router.delete("/history/{user_id}")
async def clear_chat_history(user_id: str):
    """
    Clear chat history for a specific user.
    
    This permanently deletes all conversation history for the user.
    """
    try:
        success = await chat_service.clear_conversation_history(user_id)
        
        if success:
            return {"message": f"Chat history cleared for user {user_id}"}
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to clear chat history"
            )
            
    except Exception as e:
        logger.error(f"Error clearing chat history for user {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear chat history: {str(e)}"
        )

@router.get("/status", response_model=ChatStatusResponse)
async def get_chat_status():
    """
    Get current chat service status and capabilities.
    
    Returns information about active connections, available AI providers,
    and enabled features.
    """
    try:
        status = chat_service.get_chat_status()
        
        return ChatStatusResponse(
            status=status["status"],
            active_connections=status["active_connections"],
            active_users=status["active_users"],
            ai_providers=status["ai_providers"],
            features=status["features"]
        )
        
    except Exception as e:
        logger.error(f"Error getting chat status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get chat status: {str(e)}"
        )

@router.get("/providers")
async def get_ai_providers(
    ai_service = Depends(get_cached_ai_service_di)
):
    """
    Get information about available AI providers and their status.
    
    Returns detailed information about each configured AI provider
    including availability, models, and capabilities.
    """
    try:
        return {
            "available_providers": ai_service.get_available_providers(),
            "provider_status": ai_service.get_provider_status(),
            "primary_provider": getattr(ai_service, 'primary_provider', None),
            "fallback_providers": getattr(ai_service, 'fallback_providers', [])
        }
        
    except Exception as e:
        logger.error(f"Error getting AI providers: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get AI providers: {str(e)}"
        )

@router.post("/test")
async def test_ai_integration(
    ai_service = Depends(get_cached_ai_service_di)
):
    """
    Test AI integration with a simple message.
    
    This endpoint is useful for testing AI provider connectivity
    and basic functionality.
    """
    try:
        test_messages = [
            {"role": "user", "content": "Hello! Please respond with a brief greeting to confirm you're working."}
        ]
        
        response = await ai_service.generate_response(
            messages=test_messages,
            temperature=0.7
        )
        
        return {
            "status": "success",
            "message": "AI integration test successful",
            "response": response.content,
            "provider": response.provider,
            "model": response.model,
            "processing_time_ms": response.processing_time_ms,
            "tokens_used": response.tokens_used
        }
        
    except Exception as e:
        logger.error(f"AI integration test failed: {e}")
        return {
            "status": "error",
            "message": "AI integration test failed",
            "error": str(e)
        }

@router.get("/health")
async def chat_health_check(
    ai_service = Depends(get_cached_ai_service_di)
):
    """
    Health check endpoint for chat service.
    
    Returns basic health information about the chat service
    and its dependencies.
    """
    try:
        # Check AI service availability
        ai_providers = ai_service.get_available_providers()
        
        health_status = "healthy" if ai_providers else "degraded"
        
        return {
            "status": health_status,
            "timestamp": datetime.utcnow().isoformat(),
            "chat_service": {
                "active": True,
                "active_connections": 0,  # Would need connection manager to track
                "active_users": 0
            },
            "ai_service": {
                "available_providers": len(ai_providers),
                "providers": ai_providers
            },
            "features": {
                "websocket_chat": True,
                "rest_api": True,
                "conversation_history": True,
                "ai_integration": len(ai_providers) > 0,
                "multi_provider_fallback": len(ai_providers) > 1
            }
        }
        
    except Exception as e:
        logger.error(f"Chat health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }