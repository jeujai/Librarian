"""
RAG Chat API Router

This demonstrates how the RAG service would be integrated into the existing
API structure to provide document-aware chat endpoints.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from ...services.chat_service_with_rag import get_enhanced_chat_service
from ..dependencies import get_cached_ai_service_di, get_cached_rag_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rag", tags=["RAG Chat"])

# Request/Response Models

class ChatMessage(BaseModel):
    """Chat message model."""
    role: str = Field(..., description="Message role: user, assistant, or system")
    content: str = Field(..., description="Message content")
    timestamp: Optional[datetime] = None

class RAGChatRequest(BaseModel):
    """RAG chat request model."""
    query: str = Field(..., description="User query")
    user_id: str = Field(..., description="User identifier")
    conversation_context: Optional[List[ChatMessage]] = Field(default=[], description="Recent conversation messages")
    document_filter: Optional[List[str]] = Field(default=None, description="Optional document IDs to search within")
    use_fallback: bool = Field(default=True, description="Whether to fallback to general AI if no documents found")
    preferred_ai_provider: Optional[str] = Field(default=None, description="Preferred AI provider")

class DocumentSearchRequest(BaseModel):
    """Document search request model."""
    query: str = Field(..., description="Search query")
    user_id: str = Field(..., description="User identifier")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum results to return")
    similarity_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Minimum similarity score")

class CitationSource(BaseModel):
    """Citation source model with excerpt information."""
    document_id: str
    document_title: str
    page_number: Optional[int]
    chunk_id: str
    relevance_score: float
    excerpt: str
    section_title: Optional[str] = None
    content_truncated: bool = False
    excerpt_error: Optional[str] = None
    source_type: Optional[str] = None  # "librarian", "web_search", or "llm_fallback"
    url: Optional[str] = None  # URL for web search sources

class RAGChatResponse(BaseModel):
    """RAG chat response model."""
    response: str = Field(..., description="Generated response")
    sources: List[CitationSource] = Field(..., description="Citation sources")
    confidence_score: float = Field(..., description="Response confidence score")
    processing_time_ms: int = Field(..., description="Processing time in milliseconds")
    tokens_used: int = Field(..., description="AI tokens consumed")
    search_results_count: int = Field(..., description="Number of search results found")
    fallback_used: bool = Field(..., description="Whether fallback to general AI was used")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

class DocumentChunkResult(BaseModel):
    """Document chunk search result model."""
    chunk_id: str
    document_id: str
    document_title: str
    content_preview: str
    page_number: Optional[int]
    section_title: Optional[str]
    similarity_score: float

class DocumentSearchResponse(BaseModel):
    """Document search response model."""
    query: str
    results: List[DocumentChunkResult]
    total_found: int
    processing_time_ms: int

# API Endpoints

@router.post("/chat", response_model=RAGChatResponse)
async def rag_chat(
    request: RAGChatRequest,
    rag_service = Depends(get_cached_rag_service)
) -> RAGChatResponse:
    """
    Generate document-aware chat response using RAG.
    
    This endpoint demonstrates how the RAG service integrates with the API layer
    to provide document-aware responses with citations.
    """
    try:
        # Convert conversation context to the format expected by RAG service
        conversation_context = []
        if request.conversation_context:
            for msg in request.conversation_context:
                conversation_context.append({
                    "role": msg.role,
                    "content": msg.content
                })
        
        # Generate RAG response
        rag_response = await rag_service.generate_response(
            query=request.query,
            user_id=request.user_id,
            conversation_context=conversation_context,
            document_filter=request.document_filter,
            preferred_ai_provider=request.preferred_ai_provider
        )
        
        # Convert to API response format
        return RAGChatResponse(
            response=rag_response.response,
            sources=[
                CitationSource(
                    document_id=source.document_id,
                    document_title=source.document_title,
                    page_number=source.page_number,
                    chunk_id=source.chunk_id,
                    relevance_score=source.relevance_score,
                    excerpt=source.excerpt,
                    section_title=source.section_title,
                    content_truncated=getattr(source, 'content_truncated', False),
                    excerpt_error=getattr(source, 'excerpt_error', None),
                    source_type=getattr(source, 'source_type', None),
                    url=getattr(source, 'url', None),
                )
                for source in rag_response.sources
            ],
            confidence_score=rag_response.confidence_score,
            processing_time_ms=rag_response.processing_time_ms,
            tokens_used=rag_response.tokens_used,
            search_results_count=rag_response.search_results_count,
            fallback_used=rag_response.fallback_used,
            metadata=rag_response.metadata
        )
        
    except Exception as e:
        logger.error(f"RAG chat failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"RAG chat processing failed: {str(e)}"
        )

@router.post("/search", response_model=DocumentSearchResponse)
async def search_documents(
    request: DocumentSearchRequest,
    rag_service = Depends(get_cached_rag_service)
) -> DocumentSearchResponse:
    """
    Search documents using semantic similarity.
    
    This endpoint provides document search functionality that can be used
    by the frontend for document discovery and exploration.
    """
    try:
        import time
        start_time = time.time()
        
        # Search documents
        search_results = await rag_service.search_documents(
            query=request.query,
            user_id=request.user_id,
            limit=request.limit,
            similarity_threshold=request.similarity_threshold
        )
        
        processing_time = int((time.time() - start_time) * 1000)
        
        # Convert to API response format
        formatted_results = [
            DocumentChunkResult(
                chunk_id=result.chunk_id,
                document_id=result.document_id,
                document_title=result.document_title,
                content_preview=result.content[:200] + "..." if len(result.content) > 200 else result.content,
                page_number=result.page_number,
                section_title=result.section_title,
                similarity_score=result.similarity_score
            )
            for result in search_results
        ]
        
        return DocumentSearchResponse(
            query=request.query,
            results=formatted_results,
            total_found=len(formatted_results),
            processing_time_ms=processing_time
        )
        
    except Exception as e:
        logger.error(f"Document search failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Document search failed: {str(e)}"
        )

@router.get("/status")
async def get_rag_status(
    rag_service = Depends(get_cached_rag_service),
    ai_service = Depends(get_cached_ai_service_di)
) -> Dict[str, Any]:
    """
    Get RAG service status and configuration.
    
    This endpoint provides status information about the RAG service,
    including OpenSearch connectivity and AI provider availability.
    """
    try:
        rag_status = rag_service.get_service_status()
        ai_providers = ai_service.get_available_providers()
        ai_provider_status = ai_service.get_provider_status()
        
        return {
            "rag_service": rag_status,
            "ai_providers": ai_providers,
            "ai_provider_status": ai_provider_status,
            "integration_ready": (
                rag_status['status'] == 'active' and
                rag_status['opensearch_connected'] and
                len(ai_providers) > 0
            ),
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get RAG status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get RAG status: {str(e)}"
        )

# WebSocket endpoint for real-time RAG chat

@router.websocket("/ws/{user_id}")
async def websocket_rag_chat(
    websocket: WebSocket,
    user_id: str,
    enhanced_chat_service = Depends(get_enhanced_chat_service)
):
    """
    WebSocket endpoint for real-time RAG-enabled chat.
    
    This demonstrates how the enhanced chat service with RAG integration
    would be exposed via WebSocket for real-time communication.
    """
    try:
        await enhanced_chat_service.handle_websocket_connection(websocket, user_id)
    except WebSocketDisconnect:
        logger.info(f"RAG WebSocket disconnected for user: {user_id}")
    except Exception as e:
        logger.error(f"RAG WebSocket error for user {user_id}: {e}")

# Health check endpoint

@router.get("/health")
async def health_check(
    rag_service = Depends(get_cached_rag_service)
) -> Dict[str, Any]:
    """
    Health check endpoint for RAG functionality.
    
    This endpoint can be used by load balancers and monitoring systems
    to check if the RAG service is healthy and ready to serve requests.
    """
    try:
        if rag_service is None:
            return {
                "status": "unhealthy",
                "rag_service_active": False,
                "opensearch_connected": False,
                "timestamp": datetime.utcnow().isoformat(),
                "details": {"error": "RAG service unavailable - OpenSearch not connected"}
            }
        
        rag_status = rag_service.get_service_status()
        
        is_healthy = (
            rag_status['status'] == 'active' and
            rag_status['opensearch_connected']
        )
        
        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "rag_service_active": rag_status['status'] == 'active',
            "opensearch_connected": rag_status['opensearch_connected'],
            "timestamp": datetime.utcnow().isoformat(),
            "details": rag_status if not is_healthy else None
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }

# Example usage endpoints for testing

@router.post("/example/simple-query")
async def example_simple_query(
    query: str,
    user_id: str = "example_user",
    rag_service = Depends(get_cached_rag_service)
) -> Dict[str, Any]:
    """
    Example endpoint for testing simple RAG queries.
    
    This is a simplified endpoint for testing and demonstration purposes.
    """
    try:
        response = await rag_service.generate_response(
            query=query,
            user_id=user_id
        )
        
        return {
            "query": query,
            "response": response.response,
            "sources_count": len(response.sources),
            "confidence": response.confidence_score,
            "fallback_used": response.fallback_used,
            "processing_time_ms": response.processing_time_ms
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Example query failed: {str(e)}"
        )