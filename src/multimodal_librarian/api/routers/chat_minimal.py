"""
Minimal chat router for learning deployment.

This is a simplified version that provides basic chat functionality
without complex dependencies.
"""

import json
import time
from typing import Dict
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

# Router setup
router = APIRouter()

# Simple connection manager for WebSocket connections
class SimpleConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, connection_id: str):
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        print(f"WebSocket connection established: {connection_id}")
    
    def disconnect(self, connection_id: str):
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        print(f"WebSocket connection closed: {connection_id}")
    
    async def send_personal_message(self, message: dict, connection_id: str):
        if connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]
            await websocket.send_text(json.dumps(message))
    
    async def broadcast(self, message: dict):
        for connection_id, websocket in self.active_connections.items():
            try:
                await websocket.send_text(json.dumps(message))
            except:
                # Connection might be closed
                pass

# Global connection manager
manager = SimpleConnectionManager()

@router.get("/chat/status")
async def get_chat_status():
    """Get chat system status."""
    return {
        "status": "active",
        "active_connections": len(manager.active_connections),
        "features": {
            "websocket": True,
            "file_upload": False,
            "multimedia": False,
            "knowledge_graph": False
        }
    }

@router.get("/chat")
async def get_chat_page():
    """Serve the chat interface."""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Multimodal Librarian - Learning Chat</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            #messages { border: 1px solid #ccc; height: 400px; overflow-y: scroll; padding: 10px; margin-bottom: 10px; }
            #messageInput { width: 70%; padding: 10px; }
            #sendButton { padding: 10px 20px; }
            .message { margin-bottom: 10px; }
            .user { color: blue; }
            .assistant { color: green; }
            .system { color: gray; font-style: italic; }
        </style>
    </head>
    <body>
        <h1>Multimodal Librarian - Learning Chat</h1>
        <div id="messages"></div>
        <input type="text" id="messageInput" placeholder="Type your message here..." />
        <button id="sendButton">Send</button>
        
        <script>
            const ws = new WebSocket("ws://multimodal-librarian-full-ml-249704554.us-east-1.elb.amazonaws.com/ws/chat");
            const messages = document.getElementById('messages');
            const messageInput = document.getElementById('messageInput');
            const sendButton = document.getElementById('sendButton');
            
            ws.onmessage = function(event) {
                const message = JSON.parse(event.data);
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message ' + message.type;
                messageDiv.innerHTML = '<strong>' + message.type + ':</strong> ' + message.content;
                messages.appendChild(messageDiv);
                messages.scrollTop = messages.scrollHeight;
            };
            
            function sendMessage() {
                const message = messageInput.value;
                if (message) {
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
                if (e.key === 'Enter') {
                    sendMessage();
                }
            });
            
            ws.onopen = function(event) {
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message system';
                messageDiv.innerHTML = '<strong>System:</strong> Connected to chat';
                messages.appendChild(messageDiv);
            };
            
            ws.onclose = function(event) {
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message system';
                messageDiv.innerHTML = '<strong>System:</strong> Disconnected from chat';
                messages.appendChild(messageDiv);
            };
        </script>
    </body>
    </html>
    """)

@router.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for chat communication."""
    connection_id = str(uuid4())
    await manager.connect(websocket, connection_id)
    
    try:
        # Send welcome message
        await manager.send_personal_message({
            "type": "system",
            "content": "Welcome to Multimodal Librarian Learning Chat!",
            "timestamp": time.time()
        }, connection_id)
        
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # Echo the user message
            await manager.send_personal_message({
                "type": "user",
                "content": message_data.get("content", ""),
                "timestamp": time.time()
            }, connection_id)
            
            # Send a simple response
            response_content = f"Echo: {message_data.get('content', '')}"
            await manager.send_personal_message({
                "type": "assistant",
                "content": response_content,
                "timestamp": time.time()
            }, connection_id)
            
    except WebSocketDisconnect:
        manager.disconnect(connection_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(connection_id)