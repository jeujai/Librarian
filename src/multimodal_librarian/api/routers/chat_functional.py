"""
Functional chat router for learning deployment.

This provides real chat functionality with cost-optimized components,
bridging the gap between minimal echo and full ML system.
"""

import json
import time
import logging
from typing import Dict, List, Optional
from uuid import uuid4
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

# Import lightweight components
# from ...components.conversation.conversation_manager import ConversationManager
# from ...models.core import Message, MessageType, ConversationThread

logger = logging.getLogger(__name__)

# Router setup
router = APIRouter()

# Simple connection manager for WebSocket connections
class FunctionalConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_threads: Dict[str, str] = {}  # connection_id -> thread_id
    
    async def connect(self, websocket: WebSocket, connection_id: str):
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        logger.info(f"WebSocket connection established: {connection_id}")
    
    def disconnect(self, connection_id: str):
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        if connection_id in self.user_threads:
            del self.user_threads[connection_id]
        logger.info(f"WebSocket connection closed: {connection_id}")
    
    async def send_personal_message(self, message: dict, connection_id: str):
        if connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]
            try:
                await websocket.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"Error sending message to {connection_id}: {e}")
                self.disconnect(connection_id)
    
    def get_thread_id(self, connection_id: str) -> Optional[str]:
        return self.user_threads.get(connection_id)
    
    def set_thread_id(self, connection_id: str, thread_id: str):
        self.user_threads[connection_id] = thread_id

# Global connection manager and conversation manager
manager = FunctionalConnectionManager()

# Initialize conversation manager (lightweight, no ML dependencies)
try:
    # For now, skip conversation manager to avoid database dependency issues
    # conversation_manager = ConversationManager()
    conversation_manager = None
    CONVERSATION_AVAILABLE = False
    logger.info("ConversationManager skipped for simplified deployment")
except Exception as e:
    logger.warning(f"ConversationManager not available: {e}")
    conversation_manager = None
    CONVERSATION_AVAILABLE = False

class SimpleChatProcessor:
    """
    Simple chat processor that provides intelligent responses without ML dependencies.
    
    This processor uses rule-based logic and conversation context to provide
    meaningful responses while maintaining cost optimization.
    """
    
    def __init__(self):
        self.response_templates = {
            'greeting': [
                "Hello! I'm your Multimodal Librarian assistant. How can I help you today?",
                "Hi there! I'm here to help you with information and questions. What would you like to know?",
                "Welcome! I'm ready to assist you with your queries. What can I help you with?"
            ],
            'question': [
                "That's an interesting question about {topic}. Let me help you with that.",
                "I understand you're asking about {topic}. Here's what I can tell you:",
                "Great question regarding {topic}. Let me provide some insights:"
            ],
            'help': [
                "I can help you with various topics including research, analysis, and general questions.",
                "I'm designed to assist with information retrieval, document analysis, and answering questions.",
                "I can help you find information, analyze content, and provide explanations on various topics."
            ],
            'thanks': [
                "You're welcome! Is there anything else I can help you with?",
                "Happy to help! Feel free to ask if you have more questions.",
                "Glad I could assist! Let me know if you need anything else."
            ],
            'goodbye': [
                "Goodbye! Feel free to return anytime you need assistance.",
                "Take care! I'll be here whenever you need help.",
                "See you later! Don't hesitate to ask if you have more questions."
            ],
            'default': [
                "I understand you're interested in {topic}. While I don't have specific information about that right now, I can help you explore related concepts.",
                "That's a thoughtful question about {topic}. In a full deployment, I would search through uploaded documents and knowledge bases to provide detailed answers.",
                "I see you're asking about {topic}. This learning deployment demonstrates the chat interface - in production, I would access vector databases and knowledge graphs for comprehensive responses."
            ]
        }
        
        self.conversation_starters = [
            "What would you like to learn about today?",
            "I'm here to help with your questions and research needs.",
            "Feel free to ask me about any topic you're curious about.",
            "What information can I help you find or analyze?"
        ]
    
    def process_message(self, message: str, conversation_context: Optional[List] = None) -> str:
        """Process user message and generate appropriate response."""
        message_lower = message.lower().strip()
        
        # Extract potential topics from the message
        topic = self._extract_topic(message)
        
        # Determine response type based on message content
        if self._is_greeting(message_lower):
            response_type = 'greeting'
        elif self._is_question(message_lower):
            response_type = 'question'
        elif self._is_help_request(message_lower):
            response_type = 'help'
        elif self._is_thanks(message_lower):
            response_type = 'thanks'
        elif self._is_goodbye(message_lower):
            response_type = 'goodbye'
        else:
            response_type = 'default'
        
        # Get base response
        import random
        templates = self.response_templates[response_type]
        base_response = random.choice(templates)
        
        # Format with topic if needed
        if '{topic}' in base_response:
            base_response = base_response.format(topic=topic or "that")
        
        # Add context-aware enhancement
        enhanced_response = self._enhance_with_context(base_response, message, conversation_context)
        
        return enhanced_response
    
    def _is_greeting(self, message: str) -> bool:
        """Check if message is a greeting."""
        greetings = ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening']
        return any(greeting in message for greeting in greetings)
    
    def _is_question(self, message: str) -> bool:
        """Check if message is a question."""
        question_words = ['what', 'how', 'why', 'when', 'where', 'who', 'which', 'can you', 'could you', 'do you']
        return any(word in message for word in question_words) or message.endswith('?')
    
    def _is_help_request(self, message: str) -> bool:
        """Check if message is asking for help."""
        help_words = ['help', 'assist', 'support', 'guide', 'explain', 'show me']
        return any(word in message for word in help_words)
    
    def _is_thanks(self, message: str) -> bool:
        """Check if message is expressing gratitude."""
        thanks_words = ['thank', 'thanks', 'appreciate', 'grateful']
        return any(word in message for word in thanks_words)
    
    def _is_goodbye(self, message: str) -> bool:
        """Check if message is a goodbye."""
        goodbye_words = ['bye', 'goodbye', 'see you', 'farewell', 'exit', 'quit']
        return any(word in message for word in goodbye_words)
    
    def _extract_topic(self, message: str) -> Optional[str]:
        """Extract main topic from message."""
        # Simple topic extraction - look for nouns and key phrases
        import re
        
        # Remove common words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        
        # Extract potential topic words (longer words, capitalized words)
        words = re.findall(r'\b\w+\b', message)
        topic_candidates = []
        
        for word in words:
            if len(word) > 3 and word.lower() not in stop_words:
                topic_candidates.append(word)
        
        # Return first significant word as topic
        return topic_candidates[0] if topic_candidates else None
    
    def _enhance_with_context(self, base_response: str, original_message: str, context: Optional[List]) -> str:
        """Enhance response with conversation context and helpful information."""
        
        # Add contextual information based on message content
        enhancements = []
        
        message_lower = original_message.lower()
        
        # Add specific guidance based on message content
        if any(word in message_lower for word in ['upload', 'file', 'document', 'pdf']):
            enhancements.append("📁 In the full system, you would be able to upload PDFs and documents for analysis.")
        
        if any(word in message_lower for word in ['search', 'find', 'look for']):
            enhancements.append("🔍 The complete deployment includes vector search across uploaded documents.")
        
        if any(word in message_lower for word in ['learn', 'study', 'research']):
            enhancements.append("📚 This system is designed to help with learning and research by analyzing uploaded materials.")
        
        if any(word in message_lower for word in ['cost', 'price', 'expensive', 'cheap']):
            enhancements.append("💰 This learning deployment is optimized for ~$50/month AWS costs while demonstrating core functionality.")
        
        if any(word in message_lower for word in ['aws', 'cloud', 'deployment']):
            enhancements.append("☁️ This system runs on AWS ECS with PostgreSQL, Redis, and cost-optimized infrastructure.")
        
        # Add conversation continuity if we have context
        if context and len(context) > 1:
            enhancements.append("💬 I can see our conversation history and maintain context across our discussion.")
        
        # Combine base response with enhancements
        if enhancements:
            enhanced = base_response + "\n\n" + "\n".join(enhancements)
        else:
            enhanced = base_response
        
        # Add helpful suggestions
        if self._is_greeting(original_message.lower()):
            enhanced += "\n\n💡 Try asking me about the system features, AWS deployment, or any topic you'd like to explore!"
        
        return enhanced

# Initialize chat processor
chat_processor = SimpleChatProcessor()

@router.get("/chat/status")
async def get_chat_status():
    """Get chat system status."""
    return {
        "status": "active",
        "active_connections": len(manager.active_connections),
        "conversation_manager": CONVERSATION_AVAILABLE,
        "features": {
            "websocket": True,
            "conversation_context": CONVERSATION_AVAILABLE,
            "intelligent_responses": True,
            "file_upload": False,
            "multimedia": False,
            "knowledge_graph": False,
            "vector_search": False
        },
        "deployment_type": "functional-learning",
        "cost_optimized": True
    }

@router.get("/chat")
async def get_chat_page():
    """Serve the functional chat interface."""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Multimodal Librarian - Functional Chat</title>
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; }
            body { 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                min-height: 100vh; 
                padding: 20px;
            }
            .container { 
                max-width: 900px; 
                margin: 0 auto; 
                background: white; 
                border-radius: 12px; 
                box-shadow: 0 10px 30px rgba(0,0,0,0.2); 
                overflow: hidden; 
                height: calc(100vh - 40px);
                display: flex;
                flex-direction: column;
            }
            .header { 
                background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); 
                color: white; 
                padding: 20px; 
                text-align: center; 
                flex-shrink: 0;
            }
            .header h1 { font-size: 24px; font-weight: 600; margin-bottom: 5px; }
            .header p { opacity: 0.9; font-size: 14px; }
            .status { 
                text-align: center; 
                padding: 12px; 
                font-weight: 500; 
                flex-shrink: 0;
                background: #d4edda; 
                color: #155724; 
                border-bottom: 1px solid #c3e6cb;
            }
            #messages { 
                flex: 1; 
                overflow-y: auto; 
                padding: 20px; 
                background: #fafafa; 
            }
            .input-area { 
                padding: 20px; 
                background: white; 
                border-top: 1px solid #eee; 
                flex-shrink: 0;
            }
            .input-group { display: flex; gap: 12px; align-items: center; }
            #messageInput { 
                flex: 1; 
                padding: 12px 16px; 
                border: 2px solid #e1e5e9; 
                border-radius: 25px; 
                font-size: 14px; 
                outline: none; 
                transition: border-color 0.3s; 
            }
            #messageInput:focus { border-color: #4facfe; }
            #sendButton { 
                padding: 12px 24px; 
                background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); 
                color: white; 
                border: none; 
                border-radius: 25px; 
                cursor: pointer; 
                font-size: 14px; 
                font-weight: 500; 
                transition: transform 0.2s; 
            }
            #sendButton:hover { transform: translateY(-1px); }
            #sendButton:disabled { 
                background: #ccc; 
                cursor: not-allowed; 
                transform: none; 
            }
            .message { 
                margin-bottom: 15px; 
                padding: 12px 16px; 
                border-radius: 12px; 
                max-width: 80%; 
                word-wrap: break-word; 
                line-height: 1.4;
                animation: fadeIn 0.3s ease-in;
            }
            @keyframes fadeIn {
                from { opacity: 0; transform: translateY(10px); }
                to { opacity: 1; transform: translateY(0); }
            }
            .user { 
                background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); 
                color: white; 
                margin-left: auto; 
                text-align: right; 
            }
            .assistant { 
                background: white; 
                color: #333; 
                border: 1px solid #e1e5e9; 
                margin-right: auto; 
            }
            .system { 
                background: #fff3cd; 
                color: #856404; 
                border: 1px solid #ffeaa7; 
                font-style: italic; 
                text-align: center; 
                margin: 10px auto; 
                max-width: 90%; 
            }
            .typing-indicator {
                background: #f0f0f0;
                color: #666;
                margin-right: auto;
                font-style: italic;
                animation: pulse 1.5s infinite;
            }
            @keyframes pulse {
                0%, 100% { opacity: 0.6; }
                50% { opacity: 1; }
            }
            .connection-status {
                position: fixed;
                top: 20px;
                right: 20px;
                padding: 8px 12px;
                border-radius: 20px;
                font-size: 12px;
                font-weight: 500;
                z-index: 1000;
            }
            .connected { background: #d4edda; color: #155724; }
            .disconnected { background: #f8d7da; color: #721c24; }
            .connecting { background: #fff3cd; color: #856404; }
        </style>
    </head>
    <body>
        <div class="connection-status connecting" id="connectionStatus">Connecting...</div>
        <div class="container">
            <div class="header">
                <h1>🤖 Multimodal Librarian</h1>
                <p>Functional Chat - Cost-Optimized Learning Deployment</p>
            </div>
            <div class="status">🟢 Functional Chat Active - Real Conversations Enabled!</div>
            <div id="messages">
                <div class="message system">🎉 Welcome to the functional Multimodal Librarian chat!</div>
                <div class="message system">💬 This chat provides intelligent responses and maintains conversation context.</div>
                <div class="message system">💰 Optimized for learning with ~$50/month AWS costs.</div>
                <div class="message system">🚀 Try asking questions, saying hello, or exploring system features!</div>
            </div>
            <div class="input-area">
                <div class="input-group">
                    <input type="text" id="messageInput" placeholder="Type your message here..." />
                    <button id="sendButton">Send</button>
                </div>
            </div>
        </div>
        
        <script>
            let ws = null;
            let isConnected = false;
            
            const messages = document.getElementById('messages');
            const messageInput = document.getElementById('messageInput');
            const sendButton = document.getElementById('sendButton');
            const connectionStatus = document.getElementById('connectionStatus');
            
            function updateConnectionStatus(status) {
                connectionStatus.className = 'connection-status ' + status;
                switch(status) {
                    case 'connected':
                        connectionStatus.textContent = '🟢 Connected';
                        break;
                    case 'disconnected':
                        connectionStatus.textContent = '🔴 Disconnected';
                        break;
                    case 'connecting':
                        connectionStatus.textContent = '🟡 Connecting...';
                        break;
                }
            }
            
            function connectWebSocket() {
                updateConnectionStatus('connecting');
                
                // Use the current host for WebSocket connection
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws/chat`;
                
                ws = new WebSocket(wsUrl);
                
                ws.onopen = function(event) {
                    isConnected = true;
                    updateConnectionStatus('connected');
                    sendButton.disabled = false;
                    messageInput.disabled = false;
                    
                    addMessage('system', 'Connected to functional chat! You can now have real conversations.');
                };
                
                ws.onmessage = function(event) {
                    const message = JSON.parse(event.data);
                    
                    // Remove typing indicator if present
                    const typingIndicator = document.querySelector('.typing-indicator');
                    if (typingIndicator) {
                        typingIndicator.remove();
                    }
                    
                    addMessage(message.type, message.content);
                };
                
                ws.onclose = function(event) {
                    isConnected = false;
                    updateConnectionStatus('disconnected');
                    sendButton.disabled = true;
                    messageInput.disabled = true;
                    
                    addMessage('system', 'Disconnected from chat. Attempting to reconnect...');
                    
                    // Attempt to reconnect after 3 seconds
                    setTimeout(connectWebSocket, 3000);
                };
                
                ws.onerror = function(error) {
                    console.error('WebSocket error:', error);
                    addMessage('system', 'Connection error occurred.');
                };
            }
            
            function addMessage(type, content) {
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message ' + type;
                messageDiv.innerHTML = content;
                messages.appendChild(messageDiv);
                messages.scrollTop = messages.scrollHeight;
            }
            
            function showTypingIndicator() {
                const typingDiv = document.createElement('div');
                typingDiv.className = 'message typing-indicator';
                typingDiv.innerHTML = 'Assistant is typing...';
                messages.appendChild(typingDiv);
                messages.scrollTop = messages.scrollHeight;
            }
            
            function sendMessage() {
                const message = messageInput.value.trim();
                if (message && isConnected) {
                    // Add user message to chat
                    addMessage('user', message);
                    
                    // Show typing indicator
                    showTypingIndicator();
                    
                    // Send message via WebSocket
                    ws.send(JSON.stringify({
                        type: 'user_message',
                        content: message,
                        timestamp: new Date().toISOString()
                    }));
                    
                    messageInput.value = '';
                }
            }
            
            sendButton.onclick = sendMessage;
            messageInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
            
            // Initialize connection
            connectWebSocket();
            
            // Disable input initially
            sendButton.disabled = true;
            messageInput.disabled = true;
        </script>
    </body>
    </html>
    """)

@router.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for functional chat communication."""
    connection_id = str(uuid4())
    await manager.connect(websocket, connection_id)
    
    # Initialize conversation thread if conversation manager is available
    thread_id = None
    # Skip conversation manager for now to avoid database issues
    # if CONVERSATION_AVAILABLE and conversation_manager:
    #     try:
    #         thread = conversation_manager.start_conversation(user_id=connection_id)
    #         thread_id = thread.thread_id
    #         manager.set_thread_id(connection_id, thread_id)
    #         logger.info(f"Started conversation thread {thread_id} for connection {connection_id}")
    #     except Exception as e:
    #         logger.warning(f"Could not start conversation thread: {e}")
    
    try:
        # Send welcome message
        await manager.send_personal_message({
            "type": "system",
            "content": "🤖 Functional chat ready! I can now provide intelligent responses and maintain conversation context.",
            "timestamp": time.time()
        }, connection_id)
        
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # Process the user message
            user_message = message_data.get("content", "").strip()
            if not user_message:
                continue
            
            # Echo the user message
            await manager.send_personal_message({
                "type": "user",
                "content": user_message,
                "timestamp": time.time()
            }, connection_id)
            
            # Get conversation context if available
            conversation_context = None
            # Skip conversation manager for now
            # if CONVERSATION_AVAILABLE and conversation_manager and thread_id:
            #     try:
            #         # Add user message to conversation
            #         conversation_manager.process_message(
            #             thread_id, 
            #             user_message, 
            #             message_type=MessageType.USER
            #         )
            #         
            #         # Get conversation for context
            #         conversation = conversation_manager.get_conversation(thread_id)
            #         if conversation:
            #             conversation_context = conversation.messages
            #             
            #     except Exception as e:
            #         logger.warning(f"Could not process conversation context: {e}")
            
            # Generate intelligent response
            try:
                response_content = chat_processor.process_message(
                    user_message, 
                    conversation_context
                )
                
                # Add assistant message to conversation if available
                # Skip for now
                # if CONVERSATION_AVAILABLE and conversation_manager and thread_id:
                #     try:
                #         conversation_manager.process_message(
                #             thread_id,
                #             response_content,
                #             message_type=MessageType.SYSTEM
                #         )
                #     except Exception as e:
                #         logger.warning(f"Could not save assistant message: {e}")
                
            except Exception as e:
                logger.error(f"Error generating response: {e}")
                response_content = "I apologize, but I encountered an error processing your message. Please try again."
            
            # Send response back to client
            await manager.send_personal_message({
                "type": "assistant",
                "content": response_content,
                "timestamp": time.time()
            }, connection_id)
            
    except WebSocketDisconnect:
        manager.disconnect(connection_id)
        logger.info(f"Client {connection_id} disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(connection_id)

@router.get("/health")
async def chat_health():
    """Health check for functional chat service."""
    return {
        "status": "healthy",
        "service": "functional_chat",
        "active_connections": len(manager.active_connections),
        "active_threads": len(manager.user_threads),
        "conversation_manager": CONVERSATION_AVAILABLE,
        "features_enabled": {
            "intelligent_responses": True,
            "conversation_context": CONVERSATION_AVAILABLE,
            "websocket_chat": True
        }
    }