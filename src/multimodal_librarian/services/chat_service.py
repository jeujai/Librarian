"""
Chat Service - Real-time chat with AI integration and conversation management

This service handles WebSocket connections, conversation history, and integrates
with the AI service for intelligent responses.
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
from sqlalchemy import delete, desc, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.connection import get_async_session
from ..database.models import ChatMessage
from .ai_service_cached import get_cached_ai_service

logger = logging.getLogger(__name__)

@dataclass
class ChatSession:
    """Chat session data."""
    connection_id: str
    user_id: str
    websocket: WebSocket
    created_at: datetime
    last_activity: datetime
    message_count: int = 0
    context_window: List[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.context_window is None:
            self.context_window = []

@dataclass
class ChatMessageData:
    """Chat message data structure."""
    id: str
    content: str
    message_type: str  # 'user', 'assistant', 'system'
    timestamp: datetime
    user_id: str
    connection_id: str
    sources: List[str] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.sources is None:
            self.sources = []
        if self.metadata is None:
            self.metadata = {}

class ConversationManager:
    """Enhanced conversation history and context management with summarization."""
    
    def __init__(self, max_context_messages: int = 20, max_context_tokens: int = 4000):
        self.max_context_messages = max_context_messages
        self.max_context_tokens = max_context_tokens
        self.conversation_summaries = {}  # user_id -> summary
        self.context_strategies = {
            'recent': self._get_recent_context,
            'important': self._get_important_context,
            'summarized': self._get_summarized_context
        }
    
    async def add_message(self, session: ChatSession, message: ChatMessageData) -> None:
        """Add message to conversation history with enhanced context management."""
        # Add to session context
        session.context_window.append({
            "role": "user" if message.message_type == "user" else "assistant",
            "content": message.content,
            "timestamp": message.timestamp.isoformat(),
            "sources": message.sources,
            "importance_score": self._calculate_importance_score(message.content)
        })
        
        # Manage context window size with intelligent trimming
        await self._manage_context_window(session)
        
        # Store in database
        try:
            async with get_async_session() as db:
                chat_message = ChatMessage(
                    id=message.id,
                    user_id=message.user_id,
                    content=message.content,
                    message_type=message.message_type,
                    timestamp=message.timestamp,
                    sources=message.sources,
                    metadata=message.metadata
                )
                db.add(chat_message)
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to store message in database: {e}")
        
        # Update conversation summary if needed
        await self._update_conversation_summary(session.user_id, session.context_window)
    
    async def _manage_context_window(self, session: ChatSession):
        """Intelligently manage context window size."""
        if len(session.context_window) <= self.max_context_messages:
            return
        
        # Calculate token usage (rough estimate)
        total_tokens = sum(len(msg["content"].split()) * 1.3 for msg in session.context_window)
        
        if total_tokens > self.max_context_tokens or len(session.context_window) > self.max_context_messages:
            # Use intelligent trimming strategy
            session.context_window = await self._trim_context_intelligently(
                session.context_window, 
                session.user_id
            )
    
    async def _trim_context_intelligently(self, context_window: List[Dict], user_id: str) -> List[Dict]:
        """Trim context window intelligently, preserving important messages."""
        if len(context_window) <= self.max_context_messages // 2:
            return context_window
        
        # Sort messages by importance score
        sorted_messages = sorted(
            enumerate(context_window), 
            key=lambda x: x[1].get('importance_score', 0.5), 
            reverse=True
        )
        
        # Keep the most recent messages and highest importance messages
        recent_count = self.max_context_messages // 3
        important_count = self.max_context_messages // 3
        
        # Always keep recent messages
        recent_messages = context_window[-recent_count:]
        
        # Keep important messages (excluding recent ones to avoid duplicates)
        important_indices = [idx for idx, _ in sorted_messages[:important_count] 
                           if idx < len(context_window) - recent_count]
        important_messages = [context_window[idx] for idx in sorted(important_indices)]
        
        # Combine and sort by timestamp
        combined_messages = important_messages + recent_messages
        combined_messages.sort(key=lambda x: x['timestamp'])
        
        # Generate summary of trimmed content if significant content was removed
        if len(context_window) - len(combined_messages) > 5:
            await self._update_conversation_summary(user_id, context_window[:len(context_window) - len(combined_messages)])
        
        return combined_messages
    
    def _calculate_importance_score(self, content: str) -> float:
        """Calculate importance score for a message."""
        score = 0.5  # Base score
        
        # Increase score for questions
        if '?' in content:
            score += 0.2
        
        # Increase score for longer messages (more detailed)
        if len(content) > 100:
            score += 0.1
        
        # Increase score for messages with specific keywords
        important_keywords = ['error', 'problem', 'help', 'explain', 'how', 'why', 'what', 'document', 'upload']
        keyword_count = sum(1 for keyword in important_keywords if keyword.lower() in content.lower())
        score += min(keyword_count * 0.1, 0.3)
        
        # Decrease score for very short messages
        if len(content) < 20:
            score -= 0.1
        
        return max(0.1, min(1.0, score))  # Clamp between 0.1 and 1.0
    
    async def _update_conversation_summary(self, user_id: str, context_messages: List[Dict]):
        """Update conversation summary for long-term context."""
        if len(context_messages) < 5:
            return
        
        try:
            # Create a summary of the conversation
            conversation_text = "\n".join([
                f"{msg['role']}: {msg['content']}" for msg in context_messages[-10:]
            ])
            
            # Use AI service to generate summary
            ai_service = get_ai_service()
            summary_prompt = [
                {
                    "role": "user", 
                    "content": f"Please provide a concise summary of this conversation, focusing on key topics and important information:\n\n{conversation_text}"
                }
            ]
            
            summary_response = await ai_service.generate_response(
                messages=summary_prompt,
                temperature=0.3,
                max_tokens=200
            )
            
            # Store summary
            self.conversation_summaries[user_id] = {
                "summary": summary_response.content,
                "updated_at": datetime.utcnow(),
                "message_count": len(context_messages)
            }
            
            logger.info(f"Updated conversation summary for user {user_id}")
            
        except Exception as e:
            logger.error(f"Failed to update conversation summary: {e}")
    
    def get_context_for_ai(self, session: ChatSession, strategy: str = 'recent') -> List[Dict[str, str]]:
        """Get conversation context formatted for AI with different strategies."""
        if strategy not in self.context_strategies:
            strategy = 'recent'
        
        return self.context_strategies[strategy](session)
    
    def _get_recent_context(self, session: ChatSession) -> List[Dict[str, str]]:
        """Get recent messages context."""
        context = []
        
        # Add conversation summary if available
        if session.user_id in self.conversation_summaries:
            summary_data = self.conversation_summaries[session.user_id]
            context.append({
                "role": "system",
                "content": f"Previous conversation summary: {summary_data['summary']}"
            })
        
        # Get recent messages from context window
        for msg in session.context_window[-10:]:  # Last 10 messages
            context.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        return context
    
    def _get_important_context(self, session: ChatSession) -> List[Dict[str, str]]:
        """Get important messages context."""
        context = []
        
        # Add conversation summary
        if session.user_id in self.conversation_summaries:
            summary_data = self.conversation_summaries[session.user_id]
            context.append({
                "role": "system",
                "content": f"Conversation summary: {summary_data['summary']}"
            })
        
        # Get high-importance messages
        important_messages = [
            msg for msg in session.context_window 
            if msg.get('importance_score', 0.5) > 0.7
        ][-8:]  # Last 8 important messages
        
        for msg in important_messages:
            context.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        # Always include the most recent message
        if session.context_window and session.context_window[-1] not in important_messages:
            last_msg = session.context_window[-1]
            context.append({
                "role": last_msg["role"],
                "content": last_msg["content"]
            })
        
        return context
    
    def _get_summarized_context(self, session: ChatSession) -> List[Dict[str, str]]:
        """Get summarized context for very long conversations."""
        context = []
        
        # Add comprehensive conversation summary
        if session.user_id in self.conversation_summaries:
            summary_data = self.conversation_summaries[session.user_id]
            context.append({
                "role": "system",
                "content": f"Conversation context: {summary_data['summary']}"
            })
        
        # Add only the most recent 3-5 messages
        recent_messages = session.context_window[-5:]
        for msg in recent_messages:
            context.append({
                "role": msg["role"],
                "content": msg["content"]
            })
        
        return context
    
    async def get_conversation_history(
        self, 
        user_id: str, 
        limit: int = 50
    ) -> List[ChatMessageData]:
        """Get conversation history for user."""
        try:
            async with get_async_session() as db:
                result = await db.execute(
                    select(ChatMessage)
                    .where(ChatMessage.user_id == user_id)
                    .order_by(desc(ChatMessage.timestamp))
                    .limit(limit)
                )
                messages = result.scalars().all()
                
                return [
                    ChatMessageData(
                        id=msg.id,
                        content=msg.content,
                        message_type=msg.message_type,
                        timestamp=msg.timestamp,
                        user_id=msg.user_id,
                        connection_id="",  # Not stored in DB
                        sources=msg.sources or [],
                        metadata=msg.metadata or {}
                    )
                    for msg in reversed(messages)  # Reverse to get chronological order
                ]
        except Exception as e:
            logger.error(f"Failed to get conversation history: {e}")
            return []
    
    def get_context_for_ai(self, session: ChatSession) -> List[Dict[str, str]]:
        """Get conversation context formatted for AI."""
        return self._get_recent_context(session)
    
    async def clear_conversation_history(self, user_id: str) -> bool:
        """Clear conversation history for user."""
        try:
            async with get_async_session() as db:
                await db.execute(
                    delete(ChatMessage).where(ChatMessage.user_id == user_id)
                )
                await db.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to clear conversation history: {e}")
            return False

class ConnectionManager:
    """Enhanced WebSocket connection manager with advanced session handling."""
    
    def __init__(self, rag_service=None):
        self.active_connections: Dict[str, ChatSession] = {}
        self.user_sessions: Dict[str, List[str]] = {}  # user_id -> [connection_ids]
        self.conversation_manager = ConversationManager()
        self.ai_service = get_cached_ai_service()
        self._rag_service = rag_service  # RAG service injected via DI
        self.settings = get_settings()
        self.message_handlers = {}
        self.session_stats = {}
        
        # Initialize message handlers
        self._setup_message_handlers()
    
    def set_rag_service(self, rag_service):
        """Set RAG service after initialization (for DI pattern)."""
        self._rag_service = rag_service
        if rag_service:
            logger.info("RAG service set for WebSocket chat")
    
    @property
    def rag_service(self):
        """Get RAG service if available."""
        return self._rag_service
    
    @property
    def rag_available(self) -> bool:
        """Check if RAG service is available."""
        return self._rag_service is not None
    
    def _setup_message_handlers(self):
        """Setup message type handlers for different message types."""
        self.message_handlers = {
            'user_message': self._handle_user_message,
            'typing_start': self._handle_typing_start,
            'typing_stop': self._handle_typing_stop,
            'session_info': self._handle_session_info_request,
            'clear_history': self._handle_clear_history,
            'set_context': self._handle_set_context,
            'get_suggestions': self._handle_get_suggestions,
            'heartbeat': self._handle_heartbeat
        }
    
    async def connect(self, websocket: WebSocket, user_id: str = None) -> str:
        """Accept WebSocket connection and create enhanced session."""
        await websocket.accept()
        
        connection_id = str(uuid4())
        if not user_id:
            user_id = f"anonymous_{connection_id[:8]}"
        
        session = ChatSession(
            connection_id=connection_id,
            user_id=user_id,
            websocket=websocket,
            created_at=datetime.utcnow(),
            last_activity=datetime.utcnow()
        )
        
        self.active_connections[connection_id] = session
        
        # Track user sessions for multi-connection support
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = []
        self.user_sessions[user_id].append(connection_id)
        
        # Initialize session stats
        self.session_stats[connection_id] = {
            'messages_sent': 0,
            'messages_received': 0,
            'total_tokens': 0,
            'avg_response_time': 0,
            'last_activity': datetime.utcnow()
        }
        
        logger.info(f"Enhanced WebSocket connected: {connection_id} for user {user_id}")
        
        # Send enhanced welcome message with session info
        await self.send_message(connection_id, {
            "type": "session_started",
            "connection_id": connection_id,
            "user_id": user_id,
            "features": {
                "typing_indicators": True,
                "message_routing": True,
                "context_management": True,
                "multi_session": True,
                "conversation_memory": True
            },
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return connection_id
    
    def disconnect(self, connection_id: str) -> None:
        """Disconnect WebSocket and clean up enhanced session."""
        if connection_id not in self.active_connections:
            return
            
        session = self.active_connections[connection_id]
        user_id = session.user_id
        
        # Remove from user sessions
        if user_id in self.user_sessions:
            if connection_id in self.user_sessions[user_id]:
                self.user_sessions[user_id].remove(connection_id)
            if not self.user_sessions[user_id]:
                del self.user_sessions[user_id]
        
        # Clean up session stats
        if connection_id in self.session_stats:
            del self.session_stats[connection_id]
        
        # Remove connection
        del self.active_connections[connection_id]
        
        logger.info(f"Enhanced WebSocket disconnected: {connection_id} for user {user_id}")
        
        # Notify other sessions of the same user about disconnection
        asyncio.create_task(self._notify_user_sessions(user_id, {
            "type": "session_disconnected",
            "connection_id": connection_id,
            "timestamp": datetime.utcnow().isoformat()
        }, exclude_connection=connection_id))
    
    async def send_message(self, connection_id: str, message: Dict[str, Any]) -> bool:
        """Send message to specific connection with enhanced error handling."""
        if connection_id not in self.active_connections:
            return False
        
        session = self.active_connections[connection_id]
        try:
            await session.websocket.send_text(json.dumps(message))
            session.last_activity = datetime.utcnow()
            
            # Update session stats
            if connection_id in self.session_stats:
                self.session_stats[connection_id]['messages_sent'] += 1
                self.session_stats[connection_id]['last_activity'] = datetime.utcnow()
            
            return True
        except Exception as e:
            logger.error(f"Failed to send message to {connection_id}: {e}")
            self.disconnect(connection_id)
            return False
    
    async def _notify_user_sessions(
        self, 
        user_id: str, 
        message: Dict[str, Any], 
        exclude_connection: str = None
    ) -> int:
        """Notify all sessions for a user, optionally excluding one connection."""
        if user_id not in self.user_sessions:
            return 0
        
        sent_count = 0
        connections_to_remove = []
        
        for connection_id in self.user_sessions[user_id]:
            if connection_id == exclude_connection:
                continue
                
            success = await self.send_message(connection_id, message)
            if success:
                sent_count += 1
            else:
                connections_to_remove.append(connection_id)
        
        # Clean up failed connections
        for connection_id in connections_to_remove:
            self.disconnect(connection_id)
        
        return sent_count
    
    async def broadcast_to_user(self, user_id: str, message: Dict[str, Any]) -> int:
        """Broadcast message to all connections for a user."""
        return await self._notify_user_sessions(user_id, message)
    
    async def handle_message(self, connection_id: str, message_data: Dict[str, Any]) -> bool:
        """Enhanced message handling with routing to specific handlers."""
        if connection_id not in self.active_connections:
            return False
        
        message_type = message_data.get('type', 'user_message')
        
        # Update session activity
        session = self.active_connections[connection_id]
        session.last_activity = datetime.utcnow()
        
        # Route to appropriate handler
        if message_type in self.message_handlers:
            try:
                await self.message_handlers[message_type](connection_id, message_data)
                return True
            except Exception as e:
                logger.error(f"Error handling message type {message_type}: {e}")
                await self.send_message(connection_id, {
                    "type": "error",
                    "content": f"Error processing {message_type}: {str(e)}",
                    "timestamp": datetime.utcnow().isoformat()
                })
                return False
        else:
            logger.warning(f"Unknown message type: {message_type}")
            await self.send_message(connection_id, {
                "type": "error",
                "content": f"Unknown message type: {message_type}",
                "timestamp": datetime.utcnow().isoformat()
            })
            return False
    
    async def _handle_user_message(self, connection_id: str, message_data: Dict[str, Any]):
        """Handle user chat messages."""
        content = message_data.get('content', '').strip()
        if not content:
            return
        
        # Process the message (existing logic)
        response = await self.process_user_message(
            connection_id=connection_id,
            message_content=content,
            context=message_data.get('context')
        )
        
        if response:
            await self.send_message(connection_id, response)
    
    async def _handle_typing_start(self, connection_id: str, message_data: Dict[str, Any]):
        """Handle typing start indicator."""
        session = self.active_connections[connection_id]
        
        # Broadcast typing indicator to other sessions of the same user
        await self._notify_user_sessions(session.user_id, {
            "type": "typing_indicator",
            "connection_id": connection_id,
            "status": "typing",
            "timestamp": datetime.utcnow().isoformat()
        }, exclude_connection=connection_id)
    
    async def _handle_typing_stop(self, connection_id: str, message_data: Dict[str, Any]):
        """Handle typing stop indicator."""
        session = self.active_connections[connection_id]
        
        # Broadcast typing stop to other sessions of the same user
        await self._notify_user_sessions(session.user_id, {
            "type": "typing_indicator",
            "connection_id": connection_id,
            "status": "stopped",
            "timestamp": datetime.utcnow().isoformat()
        }, exclude_connection=connection_id)
    
    async def _handle_session_info_request(self, connection_id: str, message_data: Dict[str, Any]):
        """Handle session information requests."""
        session_info = await self.get_session_info(connection_id)
        if session_info:
            # Add enhanced session statistics
            stats = self.session_stats.get(connection_id, {})
            session_info.update({
                "statistics": stats,
                "user_sessions": len(self.user_sessions.get(session_info["user_id"], [])),
                "conversation_length": len(self.active_connections[connection_id].context_window)
            })
            
            await self.send_message(connection_id, {
                "type": "session_info",
                "data": session_info,
                "timestamp": datetime.utcnow().isoformat()
            })
    
    async def _handle_clear_history(self, connection_id: str, message_data: Dict[str, Any]):
        """Handle conversation history clearing."""
        session = self.active_connections[connection_id]
        success = await self.conversation_manager.clear_conversation_history(session.user_id)
        
        # Clear session context
        session.context_window = []
        session.message_count = 0
        
        await self.send_message(connection_id, {
            "type": "history_cleared",
            "success": success,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Notify other sessions of the same user
        await self._notify_user_sessions(session.user_id, {
            "type": "history_cleared_notification",
            "by_connection": connection_id,
            "timestamp": datetime.utcnow().isoformat()
        }, exclude_connection=connection_id)
    
    async def _handle_set_context(self, connection_id: str, message_data: Dict[str, Any]):
        """Handle context setting for conversation."""
        context = message_data.get('context', '')
        session = self.active_connections[connection_id]
        
        # Store context in session metadata
        if not hasattr(session, 'custom_context'):
            session.custom_context = {}
        session.custom_context['user_context'] = context
        
        await self.send_message(connection_id, {
            "type": "context_set",
            "context": context,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def _handle_get_suggestions(self, connection_id: str, message_data: Dict[str, Any]):
        """Handle conversation suggestions request."""
        session = self.active_connections[connection_id]
        
        # Generate suggestions based on conversation history
        suggestions = self._generate_conversation_suggestions(session)
        
        await self.send_message(connection_id, {
            "type": "suggestions",
            "suggestions": suggestions,
            "timestamp": datetime.utcnow().isoformat()
        })
    
    async def _handle_heartbeat(self, connection_id: str, message_data: Dict[str, Any]):
        """Handle heartbeat/ping messages."""
        await self.send_message(connection_id, {
            "type": "heartbeat_response",
            "timestamp": datetime.utcnow().isoformat()
        })
    
    def _generate_conversation_suggestions(self, session: ChatSession) -> List[str]:
        """Generate conversation suggestions based on context."""
        suggestions = [
            "What can you help me with?",
            "Tell me about this system",
            "How does the AI integration work?",
            "What features are available?"
        ]
        
        # Add context-aware suggestions based on conversation history
        if len(session.context_window) > 0:
            last_messages = session.context_window[-3:]
            if any("document" in msg.get("content", "").lower() for msg in last_messages):
                suggestions.extend([
                    "How do I upload documents?",
                    "What document formats are supported?",
                    "Can you search through my documents?"
                ])
            elif any("ai" in msg.get("content", "").lower() for msg in last_messages):
                suggestions.extend([
                    "Which AI models do you use?",
                    "How accurate are your responses?",
                    "Can you explain how you work?"
                ])
        
        return suggestions[:6]  # Limit to 6 suggestions
    
    async def process_user_message(
        self, 
        connection_id: str, 
        message_content: str,
        context: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Process user message and generate AI response with RAG support."""
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
            
            # Try RAG-enhanced response first
            sources = []
            ai_response = None
            rag_used = False
            
            if self.rag_service is not None:
                try:
                    # Get conversation context for RAG
                    conversation_context = []
                    for msg in session.context_window[-5:]:  # Last 5 messages
                        conversation_context.append({
                            "role": msg.message_type,
                            "content": msg.content
                        })
                    
                    # Use RAG for document-enhanced response
                    rag_response = await self.rag_service.generate_response(
                        query=message_content,
                        user_id=session.user_id,
                        conversation_context=conversation_context
                    )
                    
                    # Extract sources from RAG response
                    if hasattr(rag_response, 'sources') and rag_response.sources:
                        sources = [
                            {
                                "document_id": source.document_id,
                                "title": source.document_title,
                                "relevance_score": source.relevance_score,
                                "location": f"Page {source.page_number}" if source.page_number else source.section_title
                            }
                            for source in rag_response.sources
                        ]
                    
                    # Create AI response from RAG response
                    from .ai_service import AIResponse
                    ai_response = AIResponse(
                        content=rag_response.response,
                        provider="rag",
                        model="rag_enhanced",
                        tokens_used=getattr(rag_response, 'tokens_used', 0),
                        processing_time_ms=rag_response.processing_time_ms,
                        confidence_score=rag_response.confidence_score
                    )
                    rag_used = True
                    logger.info(f"WebSocket chat processed with RAG - {len(sources)} sources found")
                    
                except Exception as rag_error:
                    logger.warning(f"RAG service error in WebSocket chat, falling back to direct AI: {rag_error}")
            
            # Fall back to direct AI if RAG not available or failed
            if ai_response is None:
                # Get conversation context for AI
                conversation_context = self.conversation_manager.get_context_for_ai(session)
                
                # Generate AI response
                ai_response = await self.ai_service.generate_response(
                    messages=conversation_context,
                    context=context,
                    temperature=0.7,
                    max_tokens=2048
                )
            
            # Create assistant message
            assistant_message = ChatMessageData(
                id=str(uuid4()),
                content=ai_response.content,
                message_type="assistant",
                timestamp=datetime.utcnow(),
                user_id=session.user_id,
                connection_id=connection_id,
                sources=sources,
                metadata={
                    "provider": ai_response.provider,
                    "model": ai_response.model,
                    "tokens_used": ai_response.tokens_used,
                    "processing_time_ms": ai_response.processing_time_ms,
                    "confidence_score": ai_response.confidence_score,
                    "rag_enhanced": rag_used
                }
            )
            
            # Add assistant response to conversation history
            await self.conversation_manager.add_message(session, assistant_message)
            
            return {
                "type": "assistant",
                "content": ai_response.content,
                "message_id": assistant_message.id,
                "timestamp": assistant_message.timestamp.isoformat(),
                "metadata": assistant_message.metadata,
                "sources": sources
            }
            
        except Exception as e:
            logger.error(f"Error processing message for {connection_id}: {e}")
            
            # Send error message
            error_message = {
                "type": "error",
                "content": "I'm sorry, I encountered an error processing your message. Please try again.",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
            
            return error_message
    
    async def get_session_info(self, connection_id: str) -> Optional[Dict[str, Any]]:
        """Get session information."""
        if connection_id not in self.active_connections:
            return None
        
        session = self.active_connections[connection_id]
        return {
            "connection_id": connection_id,
            "user_id": session.user_id,
            "created_at": session.created_at.isoformat(),
            "last_activity": session.last_activity.isoformat(),
            "message_count": session.message_count,
            "context_messages": len(session.context_window)
        }
    
    def get_active_connections_count(self) -> int:
        """Get number of active connections."""
        return len(self.active_connections)
    
    def get_active_users_count(self) -> int:
        """Get number of unique active users."""
        return len(set(session.user_id for session in self.active_connections.values()))
    
    async def cleanup_inactive_sessions(self, timeout_minutes: int = 30) -> int:
        """Clean up inactive sessions."""
        cutoff_time = datetime.utcnow() - timedelta(minutes=timeout_minutes)
        connections_to_remove = []
        
        for connection_id, session in self.active_connections.items():
            if session.last_activity < cutoff_time:
                connections_to_remove.append(connection_id)
        
        for connection_id in connections_to_remove:
            try:
                session = self.active_connections[connection_id]
                await session.websocket.close()
            except:
                pass  # Connection might already be closed
            self.disconnect(connection_id)
        
        return len(connections_to_remove)

class ChatService:
    """Main chat service for handling WebSocket chat functionality."""
    
    def __init__(self, rag_service=None):
        self.connection_manager = ConnectionManager(rag_service=rag_service)
        self.settings = get_settings()
    
    def set_rag_service(self, rag_service):
        """Set RAG service for document-aware responses."""
        self.connection_manager.set_rag_service(rag_service)
    
    async def handle_websocket_connection(self, websocket: WebSocket, user_id: str = None):
        """Handle enhanced WebSocket connection for chat."""
        connection_id = await self.connection_manager.connect(websocket, user_id)
        
        try:
            # Send enhanced welcome message
            await self.connection_manager.send_message(connection_id, {
                "type": "system",
                "content": "🤖 Welcome to Enhanced Multimodal Librarian! I'm your AI assistant with advanced conversation capabilities including context management, typing indicators, and multi-session support.",
                "timestamp": datetime.utcnow().isoformat(),
                "features": {
                    "enhanced_context": True,
                    "conversation_summarization": True,
                    "typing_indicators": True,
                    "message_routing": True,
                    "multi_session_support": True,
                    "intelligent_suggestions": True
                }
            })
            
            # Main message loop with enhanced handling
            while True:
                try:
                    # Receive message from client
                    data = await websocket.receive_text()
                    message_data = json.loads(data)
                    
                    # Use enhanced message handling
                    await self.connection_manager.handle_message(connection_id, message_data)
                    
                except json.JSONDecodeError:
                    await self.connection_manager.send_message(connection_id, {
                        "type": "error",
                        "content": "Invalid message format. Please send valid JSON.",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                except Exception as e:
                    logger.error(f"Error in enhanced message loop for {connection_id}: {e}")
                    await self.connection_manager.send_message(connection_id, {
                        "type": "error",
                        "content": "An error occurred processing your message.",
                        "timestamp": datetime.utcnow().isoformat()
                    })
        
        except WebSocketDisconnect:
            logger.info(f"Enhanced WebSocket disconnected normally: {connection_id}")
        except Exception as e:
            logger.error(f"Enhanced WebSocket error for {connection_id}: {e}")
        finally:
            self.connection_manager.disconnect(connection_id)
    
    async def get_conversation_history(self, user_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get conversation history for user."""
        messages = await self.connection_manager.conversation_manager.get_conversation_history(
            user_id, limit
        )
        
        return [
            {
                "id": msg.id,
                "content": msg.content,
                "type": msg.message_type,
                "timestamp": msg.timestamp.isoformat(),
                "sources": msg.sources,
                "metadata": msg.metadata
            }
            for msg in messages
        ]
    
    async def clear_conversation_history(self, user_id: str) -> bool:
        """Clear conversation history for user."""
        return await self.connection_manager.conversation_manager.clear_conversation_history(user_id)
    
    def get_chat_status(self) -> Dict[str, Any]:
        """Get enhanced chat service status."""
        ai_service = get_cached_ai_service()
        
        return {
            "status": "active",
            "active_connections": self.connection_manager.get_active_connections_count(),
            "active_users": self.connection_manager.get_active_users_count(),
            "ai_providers": ai_service.get_available_providers(),
            "ai_provider_status": ai_service.get_provider_status(),
            "features": {
                "websocket": True,
                "conversation_context": True,
                "ai_integration": True,
                "persistent_history": True,
                "multi_provider_fallback": True,
                # Enhanced Task 2 features
                "enhanced_context_management": True,
                "conversation_summarization": True,
                "intelligent_context_trimming": True,
                "typing_indicators": True,
                "message_routing": True,
                "multi_session_support": True,
                "session_statistics": True,
                "conversation_suggestions": True,
                "importance_scoring": True,
                "context_strategies": True
            },
            "context_strategies": ["recent", "important", "summarized"],
            "message_types": list(self.connection_manager.message_handlers.keys()),
            "conversation_summaries": len(self.connection_manager.conversation_manager.conversation_summaries)
        }

# Global chat service instance
_chat_service = None

def get_chat_service(rag_service=None) -> ChatService:
    """Get global chat service instance with optional RAG service."""
    global _chat_service
    if _chat_service is None:
        _chat_service = ChatService(rag_service=rag_service)
    elif rag_service is not None and not _chat_service.connection_manager.rag_available:
        # Update RAG service if it becomes available later
        _chat_service.set_rag_service(rag_service)
    return _chat_service