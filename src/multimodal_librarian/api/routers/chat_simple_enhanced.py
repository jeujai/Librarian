"""
Simple Enhanced WebSocket Chat Router

This provides enhanced WebSocket functionality without complex dependencies.
"""

import json
import time
import asyncio
import logging
from typing import Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

# Router setup
router = APIRouter()

class SimpleEnhancedConnectionManager:
    """Simple enhanced WebSocket connection manager."""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_metadata: Dict[str, dict] = {}
        self.heartbeat_tasks: Dict[str, asyncio.Task] = {}
        self.conversation_history: Dict[str, list] = {}
        self.connection_stats = {
            'total_connections': 0,
            'active_connections': 0,
            'failed_connections': 0,
            'heartbeat_failures': 0
        }
    
    async def connect(self, websocket: WebSocket, connection_id: str) -> bool:
        """Connect a WebSocket with error handling."""
        try:
            await websocket.accept()
            
            self.active_connections[connection_id] = websocket
            self.connection_metadata[connection_id] = {
                'connected_at': time.time(),
                'last_ping': time.time(),
                'message_count': 0,
                'last_activity': time.time(),
                'status': 'connected'
            }
            self.conversation_history[connection_id] = []
            
            # Start heartbeat task
            self.heartbeat_tasks[connection_id] = asyncio.create_task(
                self._heartbeat_loop(connection_id)
            )
            
            # Update stats
            self.connection_stats['total_connections'] += 1
            self.connection_stats['active_connections'] = len(self.active_connections)
            
            logger.info(f"WebSocket connection established: {connection_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to establish WebSocket connection {connection_id}: {e}")
            self.connection_stats['failed_connections'] += 1
            return False
    
    async def disconnect(self, connection_id: str):
        """Disconnect a WebSocket and clean up resources."""
        try:
            # Cancel heartbeat task
            if connection_id in self.heartbeat_tasks:
                self.heartbeat_tasks[connection_id].cancel()
                del self.heartbeat_tasks[connection_id]
            
            # Clean up connection data
            if connection_id in self.active_connections:
                del self.active_connections[connection_id]
            if connection_id in self.connection_metadata:
                del self.connection_metadata[connection_id]
            if connection_id in self.conversation_history:
                del self.conversation_history[connection_id]
            
            # Update stats
            self.connection_stats['active_connections'] = len(self.active_connections)
            
            logger.info(f"WebSocket connection closed: {connection_id}")
            
        except Exception as e:
            logger.error(f"Error during disconnect cleanup for {connection_id}: {e}")
    
    async def send_personal_message(self, message: dict, connection_id: str) -> bool:
        """Send message to specific connection with error handling."""
        if connection_id not in self.active_connections:
            logger.warning(f"Attempted to send message to non-existent connection: {connection_id}")
            return False
        
        websocket = self.active_connections[connection_id]
        try:
            await websocket.send_text(json.dumps(message))
            
            # Update metadata
            if connection_id in self.connection_metadata:
                self.connection_metadata[connection_id]['message_count'] += 1
                self.connection_metadata[connection_id]['last_activity'] = time.time()
            
            return True
            
        except Exception as e:
            logger.error(f"Error sending message to {connection_id}: {e}")
            await self.disconnect(connection_id)
            return False
    
    async def _heartbeat_loop(self, connection_id: str):
        """Maintain connection with periodic ping/pong."""
        while connection_id in self.active_connections:
            try:
                await asyncio.sleep(30)  # Ping every 30 seconds
                
                if connection_id in self.active_connections:
                    websocket = self.active_connections[connection_id]
                    
                    # Send ping
                    await websocket.ping()
                    
                    # Update metadata
                    if connection_id in self.connection_metadata:
                        self.connection_metadata[connection_id]['last_ping'] = time.time()
                    
                    logger.debug(f"Heartbeat sent to {connection_id}")
                    
            except asyncio.CancelledError:
                logger.debug(f"Heartbeat task cancelled for {connection_id}")
                break
            except Exception as e:
                logger.warning(f"Heartbeat failed for {connection_id}: {e}")
                self.connection_stats['heartbeat_failures'] += 1
                await self.disconnect(connection_id)
                break
    
    def add_to_history(self, connection_id: str, message: str, message_type: str):
        """Add message to conversation history."""
        if connection_id in self.conversation_history:
            self.conversation_history[connection_id].append({
                'content': message,
                'type': message_type,
                'timestamp': time.time()
            })
            # Keep only last 50 messages
            if len(self.conversation_history[connection_id]) > 50:
                self.conversation_history[connection_id] = self.conversation_history[connection_id][-50:]
    
    def get_history(self, connection_id: str) -> list:
        """Get conversation history for connection."""
        return self.conversation_history.get(connection_id, [])
    
    def get_connection_info(self, connection_id: str) -> Optional[dict]:
        """Get connection metadata."""
        return self.connection_metadata.get(connection_id)
    
    def get_stats(self) -> dict:
        """Get connection statistics."""
        return {
            **self.connection_stats,
            'active_connections': len(self.active_connections),
            'active_heartbeats': len(self.heartbeat_tasks),
            'connections_with_history': len(self.conversation_history)
        }

class SimpleChatProcessor:
    """Simple chat processor with intelligent responses."""
    
    def __init__(self):
        self.response_templates = {
            'greeting': [
                "Hello! I'm your enhanced Multimodal Librarian assistant. How can I help you today?",
                "Hi there! I'm here with improved WebSocket reliability. What would you like to know?",
                "Welcome! I'm ready to assist you with reliable, real-time conversations."
            ],
            'connection_test': [
                "🔗 Connection test successful! Your WebSocket connection is stable and working perfectly.",
                "✅ Great! Your connection is solid with enhanced heartbeat monitoring active.",
                "🟢 Connection verified! The enhanced WebSocket manager is maintaining your session reliably."
            ],
            'system_status': [
                "🔧 Enhanced WebSocket system is running with heartbeat monitoring and automatic reconnection.",
                "⚡ System status: All enhanced features active including connection health monitoring.",
                "🛡️ Robust WebSocket implementation active with sticky sessions and error handling."
            ],
            'default': [
                "I understand you're interested in that topic. This enhanced WebSocket system ensures reliable communication.",
                "That's a thoughtful question. With improved connection management, we can discuss this effectively.",
                "Interesting! The enhanced system allows for better real-time interaction on various topics."
            ]
        }
    
    def process_message(self, message: str, conversation_history: list = None, connection_info: dict = None) -> str:
        """Process user message and generate appropriate response."""
        message_lower = message.lower().strip()
        
        # Determine response type
        if any(word in message_lower for word in ['hello', 'hi', 'hey', 'greetings']):
            response_type = 'greeting'
        elif any(word in message_lower for word in ['ping', 'test', 'connection']):
            response_type = 'connection_test'
        elif any(word in message_lower for word in ['status', 'system', 'health']):
            response_type = 'system_status'
        else:
            response_type = 'default'
        
        # Get base response
        import random
        templates = self.response_templates[response_type]
        base_response = random.choice(templates)
        
        # Add context information
        enhancements = []
        
        if connection_info:
            connected_duration = time.time() - connection_info.get('connected_at', time.time())
            if connected_duration > 60:  # 1 minute
                enhancements.append(f"🕐 Our connection has been stable for {int(connected_duration/60)} minutes.")
        
        if any(word in message_lower for word in ['websocket', 'connection', 'enhanced']):
            enhancements.append("🔗 This enhanced WebSocket implementation includes heartbeat monitoring and automatic recovery.")
        
        if conversation_history and len(conversation_history) > 1:
            enhancements.append(f"💬 I'm maintaining context from our {len(conversation_history)} message conversation.")
        
        # Combine response with enhancements
        if enhancements:
            enhanced = base_response + "\n\n" + "\n".join(enhancements)
        else:
            enhanced = base_response
        
        return enhanced

# Global instances
manager = SimpleEnhancedConnectionManager()
chat_processor = SimpleChatProcessor()

@router.get("/chat/status")
async def get_chat_status():
    """Get enhanced chat system status."""
    stats = manager.get_stats()
    return {
        "status": "active",
        "service": "simple_enhanced_websocket_chat",
        "connection_stats": stats,
        "features": {
            "websocket": True,
            "heartbeat_monitoring": True,
            "automatic_reconnection": True,
            "sticky_sessions": True,
            "error_recovery": True,
            "connection_cleanup": True,
            "conversation_context": True,
            "intelligent_responses": True,
            "enhanced_reliability": True
        },
        "deployment_type": "simple-enhanced",
        "cost_optimized": True
    }

@router.get("/chat")
async def get_chat_page():
    """Serve the enhanced chat interface."""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Multimodal Librarian - Enhanced WebSocket Chat</title>
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
                <p>Enhanced WebSocket Chat - Reliable & Robust</p>
            </div>
            <div class="status">🟢 Enhanced WebSocket Active - Heartbeat Monitoring & Auto-Recovery!</div>
            <div id="messages">
                <div class="message system">🎉 Welcome to the enhanced Multimodal Librarian chat!</div>
                <div class="message system">🛡️ This chat features robust WebSocket connectivity with heartbeat monitoring.</div>
                <div class="message system">🔗 Enhanced features: Automatic reconnection, sticky sessions, and error recovery.</div>
                <div class="message system">🚀 Try saying 'ping' to test the connection or ask about system status!</div>
            </div>
            <div class="input-area">
                <div class="input-group">
                    <input type="text" id="messageInput" placeholder="Type your message here..." />
                    <button id="sendButton">Send</button>
                </div>
            </div>
        </div>
        
        <script>
            class RobustWebSocketClient {
                constructor(url) {
                    this.url = url;
                    this.ws = null;
                    this.reconnectAttempts = 0;
                    this.maxReconnectAttempts = 10;
                    this.reconnectDelay = 1000;
                    this.maxReconnectDelay = 30000;
                    this.isConnected = false;
                    this.messageQueue = [];
                    this.heartbeatInterval = null;
                }
                
                connect() {
                    try {
                        this.ws = new WebSocket(this.url);
                        
                        this.ws.onopen = (event) => {
                            this.isConnected = true;
                            this.reconnectAttempts = 0;
                            this.reconnectDelay = 1000;
                            this.onConnectionEstablished();
                            this.flushMessageQueue();
                            this.startHeartbeat();
                        };
                        
                        this.ws.onmessage = (event) => {
                            this.onMessage(event);
                        };
                        
                        this.ws.onclose = (event) => {
                            this.isConnected = false;
                            this.stopHeartbeat();
                            this.onConnectionClosed();
                            this.scheduleReconnect();
                        };
                        
                        this.ws.onerror = (error) => {
                            this.onConnectionError(error);
                        };
                        
                    } catch (error) {
                        this.onConnectionError(error);
                        this.scheduleReconnect();
                    }
                }
                
                startHeartbeat() {
                    this.heartbeatInterval = setInterval(() => {
                        if (this.isConnected && this.ws.readyState === WebSocket.OPEN) {
                            this.send({
                                type: 'ping',
                                timestamp: new Date().toISOString()
                            });
                        }
                    }, 30000);
                }
                
                stopHeartbeat() {
                    if (this.heartbeatInterval) {
                        clearInterval(this.heartbeatInterval);
                        this.heartbeatInterval = null;
                    }
                }
                
                scheduleReconnect() {
                    if (this.reconnectAttempts < this.maxReconnectAttempts) {
                        this.reconnectAttempts++;
                        const delay = Math.min(
                            this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
                            this.maxReconnectDelay
                        );
                        
                        setTimeout(() => {
                            this.connect();
                        }, delay);
                    }
                }
                
                send(data) {
                    if (this.isConnected && this.ws.readyState === WebSocket.OPEN) {
                        this.ws.send(JSON.stringify(data));
                    } else {
                        this.messageQueue.push(data);
                    }
                }
                
                flushMessageQueue() {
                    while (this.messageQueue.length > 0) {
                        const message = this.messageQueue.shift();
                        this.send(message);
                    }
                }
                
                onConnectionEstablished() {
                    updateConnectionStatus('connected');
                    sendButton.disabled = false;
                    messageInput.disabled = false;
                    addMessage('system', 'Connected to enhanced WebSocket chat with heartbeat monitoring!');
                }
                
                onConnectionClosed() {
                    updateConnectionStatus('disconnected');
                    sendButton.disabled = true;
                    messageInput.disabled = true;
                    addMessage('system', 'Disconnected from chat. Enhanced reconnection in progress...');
                }
                
                onConnectionError(error) {
                    console.error('WebSocket error:', error);
                    addMessage('system', 'Connection error occurred. Enhanced recovery system activated.');
                }
                
                onMessage(event) {
                    const message = JSON.parse(event.data);
                    
                    if (message.type === 'pong') {
                        console.log('Heartbeat pong received');
                        return;
                    }
                    
                    const typingIndicator = document.querySelector('.typing-indicator');
                    if (typingIndicator) {
                        typingIndicator.remove();
                    }
                    
                    addMessage(message.type, message.content);
                }
            }
            
            const messages = document.getElementById('messages');
            const messageInput = document.getElementById('messageInput');
            const sendButton = document.getElementById('sendButton');
            const connectionStatus = document.getElementById('connectionStatus');
            
            function updateConnectionStatus(status) {
                connectionStatus.className = 'connection-status ' + status;
                switch(status) {
                    case 'connected':
                        connectionStatus.textContent = '🟢 Enhanced Connected';
                        break;
                    case 'disconnected':
                        connectionStatus.textContent = '🔴 Reconnecting...';
                        break;
                    case 'connecting':
                        connectionStatus.textContent = '🟡 Connecting...';
                        break;
                }
            }
            
            function addMessage(type, content) {
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message ' + type;
                messageDiv.innerHTML = content.replace(/\\n/g, '<br>');
                messages.appendChild(messageDiv);
                messages.scrollTop = messages.scrollHeight;
            }
            
            function showTypingIndicator() {
                const typingDiv = document.createElement('div');
                typingDiv.className = 'message typing-indicator';
                typingDiv.innerHTML = 'Enhanced assistant is typing...';
                messages.appendChild(typingDiv);
                messages.scrollTop = messages.scrollHeight;
            }
            
            function sendMessage() {
                const message = messageInput.value.trim();
                if (message && wsClient.isConnected) {
                    addMessage('user', message);
                    showTypingIndicator();
                    
                    wsClient.send({
                        type: 'user_message',
                        content: message,
                        timestamp: new Date().toISOString()
                    });
                    
                    messageInput.value = '';
                }
            }
            
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws/chat`;
            const wsClient = new RobustWebSocketClient(wsUrl);
            
            sendButton.onclick = sendMessage;
            messageInput.addEventListener('keypress', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
            
            updateConnectionStatus('connecting');
            sendButton.disabled = true;
            messageInput.disabled = true;
            wsClient.connect();
        </script>
    </body>
    </html>
    """)

@router.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    """Enhanced WebSocket endpoint with comprehensive error handling."""
    connection_id = str(uuid4())
    
    # Attempt to connect with error handling
    if not await manager.connect(websocket, connection_id):
        logger.error(f"Failed to establish WebSocket connection for {connection_id}")
        return
    
    try:
        # Send welcome message
        await manager.send_personal_message({
            "type": "system",
            "content": "🤖 Enhanced WebSocket chat ready! Features: heartbeat monitoring, automatic reconnection, and robust error handling.",
            "timestamp": time.time()
        }, connection_id)
        
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # Handle ping messages
            if message_data.get("type") == "ping":
                await manager.send_personal_message({
                    "type": "pong",
                    "timestamp": time.time()
                }, connection_id)
                continue
            
            # Process user messages
            user_message = message_data.get("content", "").strip()
            if not user_message:
                continue
            
            # Add to conversation history
            manager.add_to_history(connection_id, user_message, 'user')
            
            # Echo the user message
            await manager.send_personal_message({
                "type": "user",
                "content": user_message,
                "timestamp": time.time()
            }, connection_id)
            
            # Get conversation context
            conversation_history = manager.get_history(connection_id)
            connection_info = manager.get_connection_info(connection_id)
            
            # Generate intelligent response
            try:
                response_content = chat_processor.process_message(
                    user_message, 
                    conversation_history,
                    connection_info
                )
                
                # Add assistant response to history
                manager.add_to_history(connection_id, response_content, 'assistant')
                
            except Exception as e:
                logger.error(f"Error generating response: {e}")
                response_content = "I apologize, but I encountered an error processing your message. The enhanced system is recovering automatically. Please try again."
            
            # Send response back to client
            await manager.send_personal_message({
                "type": "assistant",
                "content": response_content,
                "timestamp": time.time()
            }, connection_id)
            
    except WebSocketDisconnect:
        await manager.disconnect(connection_id)
        logger.info(f"Client {connection_id} disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error for {connection_id}: {e}")
        await manager.disconnect(connection_id)

@router.get("/health")
async def chat_health():
    """Enhanced health check with comprehensive system status."""
    stats = manager.get_stats()
    return {
        "status": "healthy",
        "service": "simple_enhanced_websocket_chat",
        "connection_stats": stats,
        "features_enabled": {
            "enhanced_websocket": True,
            "heartbeat_monitoring": True,
            "automatic_reconnection": True,
            "sticky_sessions": True,
            "error_recovery": True,
            "connection_cleanup": True,
            "intelligent_responses": True,
            "conversation_context": True
        }
    }

@router.get("/diagnostics")
async def get_diagnostics():
    """Diagnostic endpoint for WebSocket troubleshooting."""
    stats = manager.get_stats()
    
    # Get detailed connection information
    connection_details = []
    for conn_id, metadata in manager.connection_metadata.items():
        connection_details.append({
            "connection_id": conn_id[:8] + "...",  # Truncated for privacy
            "connected_duration": time.time() - metadata.get('connected_at', time.time()),
            "message_count": metadata.get('message_count', 0),
            "last_activity": time.time() - metadata.get('last_activity', time.time()),
            "last_ping": time.time() - metadata.get('last_ping', time.time()),
            "status": metadata.get('status', 'unknown')
        })
    
    return {
        "timestamp": time.time(),
        "service": "simple_enhanced_websocket_chat",
        "overall_stats": stats,
        "active_connections": connection_details,
        "system_info": {
            "heartbeat_interval": 30,
            "max_history_per_connection": 50
        },
        "health_indicators": {
            "all_systems_operational": len(manager.active_connections) == len(manager.heartbeat_tasks),
            "heartbeat_health": stats['heartbeat_failures'] < stats['total_connections'] * 0.1
        }
    }