"""
AI-Enhanced FastAPI application with analytics focus.

This version includes AI integration and analytics functionality
while avoiding heavy ML dependencies that cause deployment issues.
"""

import time
import os
import json
import asyncio
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, File, UploadFile, Form, Depends
from fastapi.responses import JSONResponse, HTMLResponse
import psycopg2
import boto3
from uuid import uuid4, UUID

# Import AI libraries
try:
    import openai
    import google.generativeai as genai
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

# Import document management (simplified)
from .models.documents import (
    DocumentUploadRequest, DocumentUploadResponse, Document, 
    DocumentListResponse, DocumentSearchRequest, DocumentStatus
)
from .services.upload_service import UploadService, UploadError, ValidationError
from .services.storage_service import StorageService

# Simple logging setup
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main_ai_enhanced_minimal")

CONFIG_AVAILABLE = False
settings = None

class AIManager:
    """Manages AI API connections and responses with Gemini 2.5 Flash multimodal support"""
    
    def __init__(self):
        self.openai_client = None
        self.openai_api_key = None
        self.gemini_model = None
        self.gemini_vision_model = None
        self.initialized = False
        
    async def initialize(self):
        """Initialize AI clients with API keys from AWS Secrets Manager"""
        try:
            # Get API keys from AWS Secrets Manager
            secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
            
            # Get API keys secret
            api_keys_response = secrets_client.get_secret_value(
                SecretId='multimodal-librarian/learning/api-keys'
            )
            api_keys = json.loads(api_keys_response['SecretString'])
            
            # Initialize OpenAI with proper client
            if api_keys.get('openai_api_key') and AI_AVAILABLE:
                try:
                    from openai import OpenAI
                    self.openai_client = OpenAI(api_key=api_keys['openai_api_key'])
                    self.openai_api_key = api_keys['openai_api_key']
                    if logger:
                        logger.info("OpenAI client initialized successfully")
                except Exception as e:
                    if logger:
                        logger.warning(f"Failed to initialize OpenAI client: {e}")
                    self.openai_client = None
                
            # Initialize Gemini 2.5 Flash (multimodal capabilities)
            if api_keys.get('gemini_api_key') and AI_AVAILABLE:
                try:
                    genai.configure(api_key=api_keys['gemini_api_key'])
                    self.gemini_model = genai.GenerativeModel('gemini-2.0-flash-exp')
                    self.gemini_vision_model = genai.GenerativeModel('gemini-2.0-flash-exp')  # Same model for vision
                    if logger:
                        logger.info("Gemini 2.5 Flash initialized successfully")
                except Exception as e:
                    if logger:
                        logger.warning(f"Failed to initialize Gemini: {e}")
                    self.gemini_model = None
                    self.gemini_vision_model = None
                
            self.initialized = True
            if logger:
                logger.info("AI Manager initialized successfully")
                
        except Exception as e:
            if logger:
                logger.error(f"Failed to initialize AI Manager: {e}")
            self.initialized = False
    
    async def generate_response(self, message: str, context: list = None, image_data: bytes = None, image_mime_type: str = None) -> Dict[str, Any]:
        """Generate AI response using available models with multimodal support"""
        if not self.initialized:
            await self.initialize()
            
        if not self.initialized:
            return {
                "text_content": self._fallback_response(message),
                "document_citations": [],
                "knowledge_insights": []
            }
        
        try:
            # Build context for AI
            context_text = ""
            if context:
                recent_context = context[-5:]  # Last 5 messages
                context_text = "\n".join([
                    f"{msg['type']}: {msg['content']}" 
                    for msg in recent_context
                ])
            
            # Create enhanced prompt
            system_prompt = """You are a knowledgeable AI assistant called The Librarian. 
            You help users with questions, provide detailed information, and maintain engaging conversations.
            You are running on AWS infrastructure and can discuss technical topics, general knowledge, 
            and help with research questions. You can also analyze images, documents, and other media.
            
            Be helpful, informative, and conversational."""
            
            # Handle multimodal input (image + text)
            if image_data and image_mime_type:
                response_text = await self._generate_multimodal_response(message, context_text, image_data, image_mime_type, system_prompt)
            else:
                # Handle text-only input
                full_prompt = f"{system_prompt}\n\nConversation context:\n{context_text}\n\nUser: {message}\n\nAssistant:"
                
                # Try Gemini 2.5 Flash first (faster, cheaper, and better)
                if self.gemini_model:
                    try:
                        response = self.gemini_model.generate_content(full_prompt)
                        response_text = response.text
                    except Exception as e:
                        if logger:
                            logger.warning(f"Gemini 2.5 Flash failed, trying OpenAI: {e}")
                        response_text = await self._try_openai_fallback(full_prompt)
                else:
                    response_text = await self._try_openai_fallback(full_prompt)
            
            return {
                "text_content": response_text,
                "document_citations": [],
                "knowledge_insights": []
            }
            
        except Exception as e:
            if logger:
                logger.error(f"AI response generation failed: {e}")
            return {
                "text_content": self._fallback_response(message),
                "document_citations": [],
                "knowledge_insights": []
            }
    
    async def _generate_multimodal_response(self, message: str, context_text: str, image_data: bytes, image_mime_type: str, system_prompt: str) -> str:
        """Generate response for multimodal input (text + image) using Gemini 2.5 Flash"""
        try:
            if self.gemini_vision_model:
                # Create image part for Gemini
                import PIL.Image
                import io
                
                # Convert bytes to PIL Image
                image = PIL.Image.open(io.BytesIO(image_data))
                
                # Create multimodal prompt
                multimodal_prompt = f"{system_prompt}\n\nConversation context:\n{context_text}\n\nUser message: {message}\n\nPlease analyze the provided image and respond to the user's message in context."
                
                # Generate content with both text and image
                response = self.gemini_vision_model.generate_content([multimodal_prompt, image])
                return response.text
            else:
                return f"I can see you've shared an image, but my multimodal capabilities are currently unavailable. However, I can help with your text message: {message}"
                
        except Exception as e:
            if logger:
                logger.error(f"Multimodal response generation failed: {e}")
            return f"I encountered an issue processing your image, but I can respond to your message: {message}. {self._fallback_response(message)}"
    
    async def _try_openai_fallback(self, full_prompt: str) -> str:
        """Try OpenAI as fallback when Gemini fails"""
        if self.openai_client and self.openai_api_key:
            try:
                response = self.openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "user", "content": full_prompt}
                    ],
                    max_tokens=500,
                    temperature=0.7
                )
                return response.choices[0].message.content
            except Exception as e:
                if logger:
                    logger.warning(f"OpenAI fallback failed: {e}")
        
        return self._fallback_response("your question")
    
    def _fallback_response(self, message: str) -> str:
        """Fallback response when AI is unavailable"""
        return f"I understand you're asking about '{message[:50]}...'. While my AI capabilities are currently limited, I'm working to provide you with the best response possible. This system is running on AWS with full infrastructure capabilities."

class EnhancedConnectionManager:
    """Enhanced connection manager with AI integration"""
    
    def __init__(self, ai_manager: AIManager):
        self.active_connections = {}
        self.conversation_history = {}
        self.ai_manager = ai_manager
    
    async def connect(self, websocket: WebSocket, connection_id: str):
        await websocket.accept()
        self.active_connections[connection_id] = websocket
        self.conversation_history[connection_id] = []
    
    def disconnect(self, connection_id: str):
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
        if connection_id in self.conversation_history:
            del self.conversation_history[connection_id]
    
    async def send_personal_message(self, message: dict, connection_id: str):
        if connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]
            try:
                await websocket.send_text(json.dumps(message))
            except:
                self.disconnect(connection_id)
    
    def add_to_history(self, connection_id: str, message: str, message_type: str):
        if connection_id in self.conversation_history:
            self.conversation_history[connection_id].append({
                'content': message,
                'type': message_type,
                'timestamp': time.time()
            })
            # Keep only last 20 messages for better context
            if len(self.conversation_history[connection_id]) > 20:
                self.conversation_history[connection_id] = self.conversation_history[connection_id][-20:]
    
    def get_history(self, connection_id: str):
        return self.conversation_history.get(connection_id, [])
    
    async def process_message(self, message: str, connection_id: str) -> Dict[str, Any]:
        """Process message with AI and return enhanced response"""
        history = self.get_history(connection_id)
        response = await self.ai_manager.generate_response(message, history)
        return response
    
    async def process_message_with_image(self, message: str, connection_id: str, image_data: bytes = None, image_mime_type: str = None) -> Dict[str, Any]:
        """Process message with optional image data and return enhanced AI response"""
        history = self.get_history(connection_id)
        response = await self.ai_manager.generate_response(message, history, image_data, image_mime_type)
        return response

def create_ai_enhanced_app() -> FastAPI:
    """Create an AI-enhanced FastAPI application with analytics focus."""
    
    app = FastAPI(
        title="The Librarian",
        description="AI-powered assistant with analytics and OpenAI/Gemini integration",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    app_start_time = time.time()
    
    if logger:
        logger.info("Starting AI-enhanced FastAPI application (minimal)")
    
    # Initialize AI Manager
    ai_manager = AIManager()
    
    # Initialize Upload Service
    upload_service = UploadService()
    
    # Initialize Enhanced Connection Manager
    connection_manager = EnhancedConnectionManager(ai_manager)
    
    # Feature availability
    FEATURES = {
        "chat": True,
        "ai_powered_chat": True,
        "conversation_context": True,
        "intelligent_responses": True,
        "openai_integration": True,
        "gemini_integration": True,
        "multimodal": True,
        "image_analysis": True,
        "static_files": True,
        "monitoring": True,
        "enhanced_ai": True,
        "knowledge_base": False,
        "vector_search": False,
        "pdf_processing": True,
        "document_upload": True,
        "document_management": True,
        "document_search": False,  # Simplified for minimal version
        "knowledge_integration": False,  # Simplified for minimal version
        "analytics": False,       # Will be set to True if router loads successfully
        "auth": False,
        "conversations": False,
        "query": False,
        "export": False,
        "ml_training": False,
        "security": False
    }
    
    @app.on_event("startup")
    async def startup_event():
        """Initialize AI on startup"""
        await ai_manager.initialize()
    
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "message": "The Librarian API",
            "version": "1.0.0",
            "status": "running",
            "docs_url": "/docs",
            "config_available": CONFIG_AVAILABLE,
            "ai_available": AI_AVAILABLE,
            "ai_initialized": ai_manager.initialized,
            "features": FEATURES,
            "enhancement": "AI Integration with Analytics Focus"
        }
    
    @app.get("/features")
    async def get_features():
        """Get current feature availability."""
        return {
            "features": FEATURES,
            "deployment_type": "ai-enhanced-minimal",
            "ai_integration": True,
            "cost_optimized": True,
            "description": "AI-powered deployment with analytics focus and reduced dependencies",
            "chat_capabilities": {
                "ai_powered_responses": True,
                "conversation_context": True,
                "websocket_communication": True,
                "openai_integration": ai_manager.openai_client is not None,
                "gemini_integration": ai_manager.gemini_model is not None,
                "multimodal_support": ai_manager.gemini_vision_model is not None,
                "intelligent_responses": True,
                "enhanced_context": True,
                "image_analysis": True,
                "document_processing": False,  # Simplified
                "document_search": False,     # Simplified
                "knowledge_citations": False  # Simplified
            }
        }
    
    @app.get("/health/simple")
    async def health_check():
        """Simple health check endpoint."""
        return {
            "status": "healthy",
            "timestamp": time.time(),
            "uptime": time.time() - app_start_time,
            "ai_initialized": ai_manager.initialized
        }
    
    # Analytics API Router
    try:
        from .api.routers.analytics import router as analytics_router
        app.include_router(analytics_router, tags=["analytics"])
        FEATURES["analytics"] = True
        
        if logger:
            logger.info("Analytics router added successfully")
            
    except ImportError as e:
        if logger:
            logger.warning(f"Could not import analytics router: {e}")
        FEATURES["analytics"] = False
    
    # Analytics Dashboard Route
    @app.get("/analytics", response_class=HTMLResponse)
    async def serve_analytics_dashboard():
        """Serve the analytics dashboard interface."""
        try:
            from pathlib import Path
            template_path = Path(__file__).parent / "templates" / "analytics_dashboard.html"
            
            if template_path.exists():
                with open(template_path, 'r') as f:
                    return HTMLResponse(content=f.read())
            else:
                return HTMLResponse(content="""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Analytics Dashboard - The Librarian</title>
                    <meta name="viewport" content="width=device-width, initial-scale=1.0">
                </head>
                <body>
                    <div style="text-align: center; padding: 50px;">
                        <h1>📊 Analytics Dashboard</h1>
                        <p>Analytics dashboard template not found.</p>
                        <p>Please ensure the analytics_dashboard.html template is available.</p>
                        <br>
                        <a href="/" style="color: #3498db;">← Back to Chat</a>
                    </div>
                </body>
                </html>
                """)
                
        except Exception as e:
            if logger:
                logger.error(f"Error serving analytics dashboard: {e}")
            
            return HTMLResponse(content=f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>Analytics Dashboard Error</title>
            </head>
            <body>
                <div style="text-align: center; padding: 50px;">
                    <h1>❌ Error Loading Analytics Dashboard</h1>
                    <p>Failed to load analytics dashboard: {str(e)}</p>
                    <br>
                    <a href="/" style="color: #3498db;">← Back to Chat</a>
                </div>
            </body>
            </html>
            """)
    
    # Basic chat interface
    @app.get("/chat", response_class=HTMLResponse)
    async def serve_chat_interface():
        """Serve the AI-enhanced chat interface."""
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>The Librarian</title>
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
                    background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%); 
                    color: white; 
                    padding: 20px; 
                    text-align: center; 
                    flex-shrink: 0;
                }
                .header h1 { font-size: 24px; font-weight: 600; margin-bottom: 5px; }
                .header p { opacity: 0.9; font-size: 14px; }
                .nav-tabs {
                    display: flex;
                    background: #f8f9fa;
                    border-bottom: 1px solid #dee2e6;
                    flex-shrink: 0;
                }
                .nav-tab {
                    flex: 1;
                    padding: 12px 20px;
                    background: none;
                    border: none;
                    cursor: pointer;
                    font-size: 14px;
                    font-weight: 500;
                    color: #6c757d;
                    transition: all 0.3s;
                }
                .nav-tab.active {
                    background: white;
                    color: #ff6b6b;
                    border-bottom: 2px solid #ff6b6b;
                }
                .nav-tab:hover {
                    background: #e9ecef;
                }
                .tab-content {
                    flex: 1;
                    display: none;
                    flex-direction: column;
                }
                .tab-content.active {
                    display: flex;
                }
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
                #messageInput:focus { border-color: #ff6b6b; }
                #sendButton { 
                    padding: 12px 24px; 
                    background: linear-gradient(135deg, #ff6b6b 0%, #ee5a24 100%); 
                    color: white; 
                    border: none; 
                    border-radius: 25px; 
                    cursor: pointer; 
                    font-size: 14px; 
                    font-weight: 500; 
                    transition: transform 0.2s; 
                }
                #sendButton:hover { transform: translateY(-1px); }
                .message { 
                    margin-bottom: 16px; 
                    padding: 12px 16px; 
                    border-radius: 12px; 
                    max-width: 80%; 
                    word-wrap: break-word; 
                }
                .user-message { 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    color: white; 
                    margin-left: auto; 
                }
                .ai-message { 
                    background: #f8f9fa; 
                    color: #333; 
                    border: 1px solid #e9ecef; 
                }
                .analytics-section {
                    flex: 1;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    background: #fafafa;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🤖 The Librarian</h1>
                    <p>AI-powered assistant with analytics capabilities</p>
                </div>
                
                <div class="nav-tabs">
                    <button class="nav-tab active" onclick="switchTab('chat')">💬 Chat</button>
                    <button class="nav-tab" onclick="switchTab('analytics')">📊 Analytics</button>
                </div>
                
                <!-- Chat Tab -->
                <div id="chat-tab" class="tab-content active">
                    <div class="status" id="status">🟢 Connected to AI-enhanced system</div>
                    <div id="messages"></div>
                    <div class="input-area">
                        <div class="input-group">
                            <input type="text" id="messageInput" placeholder="Ask me anything..." onkeypress="handleKeyPress(event)">
                            <button id="sendButton" onclick="sendMessage()">Send</button>
                        </div>
                    </div>
                </div>
                
                <!-- Analytics Tab -->
                <div id="analytics-tab" class="tab-content">
                    <div class="analytics-section">
                        <div style="text-align: center; padding: 40px;">
                            <div style="font-size: 48px; margin-bottom: 16px;">📊</div>
                            <div style="font-size: 24px; margin-bottom: 16px;">Analytics Dashboard</div>
                            <div style="color: #6c757d; margin-bottom: 24px;">View insights about your document usage and interactions</div>
                            <button onclick="openAnalyticsDashboard()" style="
                                padding: 12px 24px;
                                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                color: white;
                                border: none;
                                border-radius: 25px;
                                cursor: pointer;
                                font-size: 14px;
                                font-weight: 500;
                                transition: transform 0.2s ease;
                            " onmouseover="this.style.transform='translateY(-2px)'" onmouseout="this.style.transform='translateY(0)'">
                                📈 Open Analytics Dashboard
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            
            <script>
            let ws = null;
            let connectionId = Math.random().toString(36).substring(7);
            
            function switchTab(tabName) {
                // Hide all tabs
                document.querySelectorAll('.tab-content').forEach(tab => {
                    tab.classList.remove('active');
                });
                document.querySelectorAll('.nav-tab').forEach(tab => {
                    tab.classList.remove('active');
                });
                
                // Show selected tab
                document.getElementById(tabName + '-tab').classList.add('active');
                event.target.classList.add('active');
            }
            
            // Analytics dashboard function
            function openAnalyticsDashboard() {
                window.open('/analytics', '_blank');
            }
            
            function connectWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws/${connectionId}`;
                
                ws = new WebSocket(wsUrl);
                
                ws.onopen = function(event) {
                    document.getElementById('status').innerHTML = '🟢 Connected to AI-enhanced system';
                    document.getElementById('status').style.background = '#d4edda';
                    document.getElementById('status').style.color = '#155724';
                };
                
                ws.onmessage = function(event) {
                    const data = JSON.parse(event.data);
                    displayMessage(data.message, 'ai');
                };
                
                ws.onclose = function(event) {
                    document.getElementById('status').innerHTML = '🔴 Disconnected - Reconnecting...';
                    document.getElementById('status').style.background = '#f8d7da';
                    document.getElementById('status').style.color = '#721c24';
                    setTimeout(connectWebSocket, 3000);
                };
                
                ws.onerror = function(error) {
                    console.error('WebSocket error:', error);
                };
            }
            
            function sendMessage() {
                const input = document.getElementById('messageInput');
                const message = input.value.trim();
                
                if (message && ws && ws.readyState === WebSocket.OPEN) {
                    displayMessage(message, 'user');
                    ws.send(JSON.stringify({message: message}));
                    input.value = '';
                }
            }
            
            function displayMessage(message, sender) {
                const messagesDiv = document.getElementById('messages');
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${sender}-message`;
                messageDiv.textContent = message;
                messagesDiv.appendChild(messageDiv);
                messagesDiv.scrollTop = messagesDiv.scrollHeight;
            }
            
            function handleKeyPress(event) {
                if (event.key === 'Enter') {
                    sendMessage();
                }
            }
            
            // Initialize WebSocket connection
            connectWebSocket();
            </script>
        </body>
        </html>
        """)
    
    # WebSocket endpoint for chat
    @app.websocket("/ws/{connection_id}")
    async def websocket_endpoint(websocket: WebSocket, connection_id: str):
        await connection_manager.connect(websocket, connection_id)
        try:
            while True:
                data = await websocket.receive_text()
                message_data = json.loads(data)
                user_message = message_data.get('message', '')
                
                # Add user message to history
                connection_manager.add_to_history(connection_id, user_message, 'user')
                
                # Process with AI
                ai_response = await connection_manager.process_message(user_message, connection_id)
                
                # Add AI response to history
                connection_manager.add_to_history(connection_id, ai_response['text_content'], 'assistant')
                
                # Send response back
                await connection_manager.send_personal_message({
                    "message": ai_response['text_content'],
                    "type": "ai_response"
                }, connection_id)
                
        except WebSocketDisconnect:
            connection_manager.disconnect(connection_id)
    
    return app

# Create the app instance
app = create_ai_enhanced_app()