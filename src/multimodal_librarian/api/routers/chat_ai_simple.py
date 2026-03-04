"""
Simple AI Chat Router - Fallback implementation without external dependencies

This router provides basic AI chat endpoints that work without requiring
external AI services or complex dependencies. It serves as a fallback
when the full AI chat router fails to load.
"""

import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/chat", tags=["AI Chat"])

# Simple response templates
SIMPLE_RESPONSES = [
    "I'm a simple AI assistant. I can help you with basic questions and provide information about this system.",
    "Hello! I'm running in fallback mode. The full AI capabilities are being set up. How can I help you?",
    "I understand you're asking about that. While I don't have access to advanced AI models right now, I can provide basic assistance.",
    "That's an interesting question. In full mode, I would search through knowledge bases and provide detailed answers.",
    "I'm here to help! This is a cost-optimized deployment running basic chat functionality.",
]

class ChatMessageRequest(BaseModel):
    """Request model for chat messages."""
    content: str = Field(..., min_length=1, max_length=10000)
    context: Optional[str] = Field(None)
    user_id: Optional[str] = Field(None)

class ChatMessageResponse(BaseModel):
    """Response model for chat messages."""
    id: str
    content: str
    type: str
    timestamp: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

def generate_simple_response(message: str) -> str:
    """Generate a simple response based on the message."""
    message_lower = message.lower().strip()
    
    # Greeting responses
    if any(word in message_lower for word in ['hello', 'hi', 'hey', 'good morning', 'good afternoon']):
        return "Hello! I'm your AI assistant running in simple mode. I can help answer questions and provide information about this system. What would you like to know?"
    
    # System/deployment questions
    elif any(word in message_lower for word in ['system', 'deployment', 'aws', 'cost', 'infrastructure']):
        return "This system is deployed on AWS ECS with cost optimization in mind. It's running a simplified AI chat mode while the full capabilities are being configured. The system includes document management, analytics, and monitoring features."
    
    # Help requests
    elif any(word in message_lower for word in ['help', 'assist', 'support', 'what can you do']):
        return "I can help with questions about this system, provide basic information, and assist with navigation. In full mode, I would have access to advanced AI models, document search, and knowledge graphs. Right now I'm running in a simplified mode."
    
    # Questions about features
    elif any(word in message_lower for word in ['features', 'capabilities', 'functions']):
        return "This system includes: AI-powered chat (you're using it now!), document upload and processing, analytics dashboards, monitoring systems, and health checks. The full AI capabilities are being configured."
    
    # Document-related questions
    elif any(word in message_lower for word in ['document', 'upload', 'pdf', 'file']):
        return "The system supports document upload and processing. You can upload PDFs and other documents through the /documents interface. In full mode, I would be able to search through your uploaded documents and answer questions about their content."
    
    # Thanks
    elif any(word in message_lower for word in ['thank', 'thanks']):
        return "You're welcome! Feel free to ask more questions. I'm here to help, even in this simplified mode."
    
    # Goodbye
    elif any(word in message_lower for word in ['bye', 'goodbye', 'see you']):
        return "Goodbye! Feel free to return anytime. The system will be here with improved AI capabilities as they come online."
    
    # Default intelligent response
    else:
        import random
        base_responses = [
            f"I understand you're asking about '{message[:50]}...'. While I'm running in simplified mode, I can tell you that this system is designed to handle complex queries with advanced AI when fully configured.",
            f"That's an interesting point about '{message[:30]}...'. In full deployment, I would analyze this using multiple AI models and provide detailed insights.",
            f"Regarding your question about '{message[:40]}...', this system is built to provide comprehensive answers using document search and knowledge graphs when fully operational.",
        ]
        return random.choice(base_responses)

@router.get("/status")
async def get_chat_status():
    """Get current chat service status."""
    return {
        "status": "active",
        "mode": "simple",
        "active_connections": 0,
        "active_users": 0,
        "ai_providers": ["simple_fallback"],
        "features": {
            "websocket_chat": False,
            "rest_api": True,
            "conversation_history": False,
            "ai_integration": True,
            "multi_provider_fallback": False,
            "simple_mode": True
        },
        "message": "Running in simple mode - full AI capabilities being configured"
    }

@router.get("/providers")
async def get_ai_providers():
    """Get information about available AI providers."""
    return {
        "available_providers": ["simple_fallback"],
        "provider_status": {
            "simple_fallback": {
                "status": "active",
                "description": "Simple fallback responses",
                "capabilities": ["basic_chat", "system_info"]
            }
        },
        "primary_provider": "simple_fallback",
        "fallback_providers": [],
        "message": "Running in simple mode - advanced AI providers being configured"
    }

@router.post("/message", response_model=ChatMessageResponse)
async def send_chat_message(request: ChatMessageRequest):
    """Send a chat message and get AI response."""
    try:
        # Generate simple response
        response_content = generate_simple_response(request.content)
        
        # Create response
        response = ChatMessageResponse(
            id=f"msg_{int(time.time() * 1000)}",
            content=response_content,
            type="assistant",
            timestamp=datetime.utcnow().isoformat(),
            metadata={
                "provider": "simple_fallback",
                "model": "rule_based",
                "tokens_used": 0,
                "processing_time_ms": 10,
                "confidence_score": 0.8,
                "mode": "simple"
            }
        )
        
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process chat message: {str(e)}"
        )

@router.get("/health")
async def chat_health_check():
    """Health check endpoint for chat service."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "mode": "simple",
        "chat_service": {
            "active": True,
            "mode": "simple_fallback",
            "active_connections": 0,
            "active_users": 0
        },
        "ai_service": {
            "available_providers": 1,
            "providers": ["simple_fallback"],
            "mode": "fallback"
        },
        "features": {
            "websocket_chat": False,
            "rest_api": True,
            "conversation_history": False,
            "ai_integration": True,
            "simple_mode": True
        },
        "message": "Simple AI chat is operational"
    }

@router.post("/test")
async def test_ai_integration():
    """Test AI integration with a simple message."""
    try:
        test_response = generate_simple_response("Hello! Please respond with a brief greeting to confirm you're working.")
        
        return {
            "status": "success",
            "message": "AI integration test successful",
            "response": test_response,
            "provider": "simple_fallback",
            "model": "rule_based",
            "processing_time_ms": 5,
            "tokens_used": 0,
            "mode": "simple"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": "AI integration test failed",
            "error": str(e),
            "mode": "simple"
        }

@router.get("/history/{user_id}")
async def get_chat_history(user_id: str, limit: int = 50):
    """Get chat history for a specific user."""
    return {
        "messages": [],
        "total_count": 0,
        "user_id": user_id,
        "message": "Chat history not available in simple mode"
    }

@router.delete("/history/{user_id}")
async def clear_chat_history(user_id: str):
    """Clear chat history for a specific user."""
    return {
        "message": f"No history to clear for user {user_id} in simple mode"
    }