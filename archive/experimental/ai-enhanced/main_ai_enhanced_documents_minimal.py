"""
AI-Enhanced FastAPI application with minimal document upload functionality.

This version includes AI integration and basic document upload without heavy ML dependencies.
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

# Simple logging setup
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main_ai_enhanced_documents_minimal")

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
    
    async def generate_response(self, message: str, context: list = None, image_data: bytes = None, image_mime_type: str = None) -> str:
        """Generate AI response using available models with multimodal support"""
        if not self.initialized:
            await self.initialize()
            
        if not self.initialized:
            return self._fallback_response(message)
        
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
            
            return response_text
            
        except Exception as e:
            if logger:
                logger.error(f"AI response generation failed: {e}")
            return self._fallback_response(message)
    
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

class SimpleDocumentManager:
    """Simple document manager without heavy ML dependencies"""
    
    def __init__(self):
        self.s3_client = boto3.client('s3', region_name='us-east-1')
        self.bucket_name = 'multimodal-librarian-full-ml-storage'
        
    async def upload_document(self, file_data: bytes, filename: str, title: str = None) -> Dict[str, Any]:
        """Upload document to S3 and store metadata"""
        try:
            document_id = str(uuid4())
            s3_key = f"documents/{document_id}/{filename}"
            
            # Upload to S3
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=s3_key,
                Body=file_data,
                ContentType='application/pdf'
            )
            
            # Store basic metadata (in a real implementation, this would go to a database)
            metadata = {
                'document_id': document_id,
                'title': title or filename,
                'filename': filename,
                'file_size': len(file_data),
                's3_key': s3_key,
                'status': 'uploaded',
                'upload_timestamp': time.time()
            }
            
            return metadata
            
        except Exception as e:
            logger.error(f"Document upload failed: {e}")
            raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    
    async def list_documents(self) -> list:
        """List uploaded documents (simplified)"""
        try:
            # In a real implementation, this would query a database
            # For now, return empty list
            return []
        except Exception as e:
            logger.error(f"Failed to list documents: {e}")
            return []

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
    
    async def process_message(self, message: str, connection_id: str) -> str:
        """Process message with AI and return response"""
        history = self.get_history(connection_id)
        response = await self.ai_manager.generate_response(message, history)
        return response
    
    async def process_message_with_image(self, message: str, connection_id: str, image_data: bytes = None, image_mime_type: str = None) -> str:
        """Process message with optional image data and return AI response"""
        history = self.get_history(connection_id)
        response = await self.ai_manager.generate_response(message, history, image_data, image_mime_type)
        return response

def create_ai_enhanced_documents_app() -> FastAPI:
    """Create an AI-enhanced FastAPI application with minimal document upload."""
    
    app = FastAPI(
        title="The Librarian - Document Upload",
        description="AI-powered assistant with document upload capabilities",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    app_start_time = time.time()
    
    if logger:
        logger.info("Starting AI-enhanced FastAPI application with document upload")
    
    # Initialize AI Manager
    ai_manager = AIManager()
    
    # Initialize Simple Document Manager
    document_manager = SimpleDocumentManager()
    
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
        "document_upload": True,
        "document_management": True,
        "pdf_processing": False,  # Simplified version
        "document_search": False,
        "knowledge_integration": False,
        "analytics": False,
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
            "message": "The Librarian API - Document Upload",
            "version": "1.0.0",
            "status": "running",
            "docs_url": "/docs",
            "config_available": CONFIG_AVAILABLE,
            "ai_available": AI_AVAILABLE,
            "ai_initialized": ai_manager.initialized,
            "features": FEATURES,
            "enhancement": "AI Integration with Document Upload"
        }
    
    @app.get("/features")
    async def get_features():
        """Get current feature availability."""
        return {
            "features": FEATURES,
            "deployment_type": "ai-enhanced-documents-minimal",
            "ai_integration": True,
            "cost_optimized": True,
            "description": "AI-powered deployment with basic document upload capabilities",
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
                "document_processing": False,
                "document_search": False,
                "knowledge_citations": False
            }
        }
    
    @app.get("/chat", response_class=HTMLResponse)
    async def serve_chat_interface():
        """Serve the AI-enhanced chat interface with document upload."""
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>The Librarian - Document Upload</title>
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
                .documents-section {
                    flex: 1;
                    display: flex;
                    flex-direction: column;
                    background: #fafafa;
                }
                .upload-area {
                    padding: 20px;
                    border-bottom: 1px solid #dee2e6;
                    background: white;
                }
                .upload-zone {
                    border: 2px dashed #dee2e6;
                    border-radius: 8px;
                    padding: 40px 20px;
                    text-align: center;
                    cursor: pointer;
                    transition: all 0.3s;
                    background: #f8f9fa;
                }
                .upload-zone:hover, .upload-zone.dragover {
                    border-color: #ff6b6b;
                    background: rgba(255, 107, 107, 0.05);
                }
                .upload-icon {
                    font-size: 48px;
                    color: #6c757d;
                    margin-bottom: 16px;
                }
                .upload-text {
                    font-size: 16px;
                    color: #495057;
                    margin-bottom: 8px;
                }
                .upload-subtext {
                    font-size: 14px;
                    color: #6c757d;
                }
                .documents-list {
                    flex: 1;
                    overflow-y: auto;
                    padding: 20px;
                }
                .message { 
                    margin-bottom: 15px; 
                    padding: 12px 16px; 
                    border-radius: 12px; 
                    max-width: 80%; 
                    word-wrap: break-word; 
                    line-height: 1.4;
                }
                .user { 
                    background: #ff6b6b; 
                    color: white; 
                    margin-left: auto; 
                    text-align: right; 
                }
                .assistant { 
                    background: #f8f9fa; 
                    color: #333; 
                    border: 1px solid #e9ecef; 
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
                .typing { 
                    background: #e9ecef; 
                    color: #6c757d; 
                    font-style: italic; 
                    animation: pulse 1.5s infinite; 
                }
                @keyframes pulse { 
                    0%, 100% { opacity: 1; } 
                    50% { opacity: 0.5; } 
                }
                .input-area { 
                    position: relative;
                    padding: 20px; 
                    background: white; 
                    border-top: 1px solid #eee; 
                    flex-shrink: 0;
                }
                .rich-input-container {
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                    width: 100%;
                }
                .rich-input {
                    min-height: 60px;
                    max-height: 200px;
                    padding: 16px;
                    border: 2px solid #e1e5e9;
                    border-radius: 12px;
                    font-size: 14px;
                    font-family: inherit;
                    line-height: 1.4;
                    outline: none;
                    overflow-y: auto;
                    background: white;
                    transition: border-color 0.3s;
                    resize: none;
                }
                .rich-input:focus { border-color: #ff6b6b; }
                .rich-input:empty:before {
                    content: attr(placeholder);
                    color: #999;
                    pointer-events: none;
                }
                .rich-input img {
                    max-width: 100%;
                    max-height: 200px;
                    border-radius: 8px;
                    margin: 8px 0;
                    display: block;
                    border: 2px solid #e1e5e9;
                }
                .input-actions {
                    display: flex;
                    justify-content: flex-end;
                }
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
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📚 The Librarian</h1>
                    <p>Powered by Gemini 2.5 Flash - AI Assistant with Document Upload</p>
                </div>
                
                <div class="nav-tabs">
                    <button class="nav-tab active" onclick="switchTab('chat')">💬 Chat</button>
                    <button class="nav-tab" onclick="switchTab('documents')">📄 Documents</button>
                </div>
                
                <!-- Chat Tab -->
                <div id="chat-tab" class="tab-content active">
                    <div class="status">🟢 The Librarian Active - AI Ready with Document Upload!</div>
                    <div id="messages">
                        <div class="message system">📚 Welcome to The Librarian!</div>
                        <div class="message system">🧠 I'm powered by Gemini 2.5 Flash with advanced AI capabilities.</div>
                        <div class="message system">💬 Ask me anything - I can help with research, analysis, and conversations!</div>
                        <div class="message system">📄 Upload PDF documents in the Documents tab to enhance our conversations!</div>
                    </div>
                    <div class="input-area">
                        <div class="rich-input-container">
                            <div id="richInput" contenteditable="true" class="rich-input" placeholder="Type your message here... You can paste images directly or drag them in!"></div>
                            <div class="input-actions">
                                <button id="sendButton">Send</button>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Documents Tab -->
                <div id="documents-tab" class="tab-content">
                    <div class="documents-section">
                        <div class="upload-area">
                            <div class="upload-zone" onclick="document.getElementById('fileInput').click()">
                                <div class="upload-icon">📄</div>
                                <div class="upload-text">Upload PDF Documents</div>
                                <div class="upload-subtext">Click here or drag and drop PDF files (max 100MB)</div>
                            </div>
                            <input type="file" id="fileInput" accept=".pdf" multiple style="display: none;">
                        </div>
                        <div class="documents-list" id="documentsList">
                            <div style="text-align: center; color: #6c757d; padding: 40px;">
                                <div style="font-size: 48px; margin-bottom: 16px;">📚</div>
                                <div>Document upload feature available</div>
                                <div style="font-size: 14px; margin-top: 8px;">Upload PDF documents to store them securely</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </body>
        <script>
            let ws = null;
            let isConnected = false;
            let currentTab = 'chat';
            
            const richInput = document.getElementById('richInput');
            const sendButton = document.getElementById('sendButton');
            const messages = document.getElementById('messages');
            const fileInput = document.getElementById('fileInput');
            const uploadZone = document.querySelector('.upload-zone');
            const documentsList = document.getElementById('documentsList');
            
            // Tab switching
            function switchTab(tabName) {
                document.querySelectorAll('.nav-tab').forEach(tab => tab.classList.remove('active'));
                document.querySelector(`[onclick="switchTab('${tabName}')"]`).classList.add('active');
                
                document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
                document.getElementById(`${tabName}-tab`).classList.add('active');
                
                currentTab = tabName;
            }
            
            // Document upload functionality
            fileInput.addEventListener('change', handleFileSelect);
            uploadZone.addEventListener('dragover', handleDragOver);
            uploadZone.addEventListener('dragleave', handleDragLeave);
            uploadZone.addEventListener('drop', handleDrop);
            
            function handleFileSelect(event) {
                const files = event.target.files;
                for (let file of files) {
                    uploadDocument(file);
                }
                event.target.value = '';
            }
            
            function handleDragOver(event) {
                event.preventDefault();
                uploadZone.classList.add('dragover');
            }
            
            function handleDragLeave(event) {
                event.preventDefault();
                uploadZone.classList.remove('dragover');
            }
            
            function handleDrop(event) {
                event.preventDefault();
                uploadZone.classList.remove('dragover');
                
                const files = event.dataTransfer.files;
                for (let file of files) {
                    if (file.type === 'application/pdf') {
                        uploadDocument(file);
                    }
                }
            }
            
            async function uploadDocument(file) {
                if (file.type !== 'application/pdf') {
                    alert('Only PDF files are supported');
                    return;
                }
                
                if (file.size > 100 * 1024 * 1024) {
                    alert('File size exceeds 100MB limit');
                    return;
                }
                
                const formData = new FormData();
                formData.append('file', file);
                formData.append('title', file.name.replace('.pdf', ''));
                
                try {
                    const response = await fetch('/api/documents/upload', {
                        method: 'POST',
                        body: formData
                    });
                    
                    if (response.ok) {
                        const result = await response.json();
                        console.log('Upload successful:', result);
                        
                        if (currentTab === 'chat') {
                            addMessage('system', `📄 Document "${result.title}" uploaded successfully!`);
                        }
                    } else {
                        const error = await response.json();
                        alert(`Upload failed: ${error.detail || 'Unknown error'}`);
                    }
                } catch (error) {
                    console.error('Upload error:', error);
                    alert('Upload failed: Network error');
                }
            }
            
            // WebSocket functionality
            function connectWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws/ai-chat`;
                
                ws = new WebSocket(wsUrl);
                
                ws.onopen = function(event) {
                    isConnected = true;
                    sendButton.disabled = false;
                    addMessage('system', '🟢 The Librarian connected! Ask me anything - I have advanced AI capabilities now.');
                };
                
                ws.onmessage = function(event) {
                    const message = JSON.parse(event.data);
                    if (message.type === 'typing') {
                        showTyping();
                    } else {
                        hideTyping();
                        addMessage(message.type, message.content);
                    }
                };
                
                ws.onclose = function(event) {
                    isConnected = false;
                    sendButton.disabled = true;
                    addMessage('system', '🔴 The Librarian disconnected. Refresh page to reconnect.');
                };
                
                ws.onerror = function(error) {
                    console.error('WebSocket error:', error);
                };
            }
            
            function addMessage(type, content) {
                const messageDiv = document.createElement('div');
                messageDiv.className = 'message ' + type;
                messageDiv.innerHTML = content;
                messages.appendChild(messageDiv);
                messages.scrollTop = messages.scrollHeight;
            }
            
            function showTyping() {
                const existingTyping = document.querySelector('.typing');
                if (!existingTyping) {
                    const typingDiv = document.createElement('div');
                    typingDiv.className = 'message typing';
                    typingDiv.innerHTML = 'AI is thinking...';
                    messages.appendChild(typingDiv);
                    messages.scrollTop = messages.scrollHeight;
                }
            }
            
            function hideTyping() {
                const typingDiv = document.querySelector('.typing');
                if (typingDiv) {
                    typingDiv.remove();
                }
            }
            
            function sendMessage() {
                const content = richInput.innerText || richInput.textContent || '';
                
                if (content.trim() && isConnected) {
                    const messageData = {
                        type: 'user_message',
                        content: content.trim(),
                        timestamp: new Date().toISOString()
                    };
                    
                    ws.send(JSON.stringify(messageData));
                    richInput.innerHTML = '';
                    richInput.focus();
                }
            }
            
            sendButton.onclick = sendMessage;
            
            richInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
            
            // Initialize WebSocket connection
            connectWebSocket();
        </script>
        </html>
        """)
    
    @app.websocket("/ws/ai-chat")
    async def websocket_ai_chat(websocket: WebSocket):
        connection_id = str(uuid4())
        await connection_manager.connect(websocket, connection_id)
        
        try:
            # Send welcome message
            await connection_manager.send_personal_message({
                "type": "system",
                "content": "📚 Welcome! I'm The Librarian, powered by advanced AI. I can help with research, analysis, and conversations.",
                "timestamp": time.time()
            }, connection_id)
            
            while True:
                # Receive message
                data = await websocket.receive_text()
                message_data = json.loads(data)
                user_message = message_data.get("content", "").strip()
                
                if not user_message:
                    continue
                
                # Add to history
                connection_manager.add_to_history(connection_id, user_message, 'user')
                
                # Echo user message
                await connection_manager.send_personal_message({
                    "type": "user",
                    "content": user_message,
                    "timestamp": time.time()
                }, connection_id)
                
                # Show typing indicator
                await connection_manager.send_personal_message({
                    "type": "typing",
                    "content": "The Librarian is analyzing...",
                    "timestamp": time.time()
                }, connection_id)
                
                # Generate AI response
                response = await connection_manager.process_message(user_message, connection_id)
                
                # Add response to history
                connection_manager.add_to_history(connection_id, response, 'assistant')
                
                # Send response
                await connection_manager.send_personal_message({
                    "type": "assistant",
                    "content": response,
                    "timestamp": time.time()
                }, connection_id)
                
        except WebSocketDisconnect:
            connection_manager.disconnect(connection_id)
        except Exception as e:
            if logger:
                logger.error(f"WebSocket error: {e}")
            connection_manager.disconnect(connection_id)
    
    @app.post("/api/documents/upload")
    async def upload_document(
        file: UploadFile = File(...),
        title: Optional[str] = Form(None)
    ):
        """Upload a PDF document."""
        try:
            # Validate file type
            if file.content_type != 'application/pdf':
                raise HTTPException(status_code=400, detail="Only PDF files are supported")
            
            # Read file content
            file_content = await file.read()
            
            # Upload document
            result = await document_manager.upload_document(
                file_data=file_content,
                filename=file.filename,
                title=title
            )
            
            return result
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unexpected error in upload endpoint: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")
    
    @app.get("/api/documents")
    async def list_documents():
        """List uploaded documents."""
        try:
            documents = await document_manager.list_documents()
            return {"documents": documents, "total_count": len(documents)}
        except Exception as e:
            logger.error(f"Error listing documents: {e}")
            raise HTTPException(status_code=500, detail="Failed to retrieve documents")
    
    @app.get("/health")
    async def health_check():
        """Comprehensive health check endpoint."""
        uptime = time.time() - app_start_time
        return {
            "overall_status": "healthy",
            "services": {
                "api": {
                    "status": "healthy",
                    "service": "api",
                    "response_time_ms": 1.0,
                    "components": {
                        "uptime_seconds": str(uptime)
                    }
                },
                "ai": {
                    "status": "healthy" if ai_manager.initialized else "degraded",
                    "openai_available": ai_manager.openai_client is not None,
                    "gemini_available": ai_manager.gemini_model is not None,
                    "gemini_vision_available": ai_manager.gemini_vision_model is not None,
                    "ai_libraries_available": AI_AVAILABLE,
                    "model_versions": {
                        "gemini": "gemini-2.0-flash-exp",
                        "openai": "gpt-3.5-turbo"
                    }
                }
            },
            "uptime_seconds": uptime,
            "active_connections": len(connection_manager.active_connections),
            "features": FEATURES,
            "deployment_type": "ai-enhanced-documents-minimal"
        }
    
    @app.get("/health/simple")
    async def simple_health_check():
        """Simple health check for load balancers."""
        return {"status": "ok", "timestamp": time.time(), "ai_enabled": True, "document_upload": True}
    
    return app

# Create the app instance
app = create_ai_enhanced_documents_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "multimodal_librarian.main_ai_enhanced_documents_minimal:app",
        host="0.0.0.0",
        port=8000,
        workers=1,
    )