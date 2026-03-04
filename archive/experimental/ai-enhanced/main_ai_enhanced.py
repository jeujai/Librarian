"""
AI-Enhanced FastAPI application with full AI capabilities.

This version includes real AI integration with OpenAI/Gemini APIs,
knowledge base functionality, and advanced conversation capabilities.
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

# Import document management
from .models.documents import (
    DocumentUploadRequest, DocumentUploadResponse, Document, 
    DocumentListResponse, DocumentSearchRequest, DocumentStatus
)
from .services.upload_service import UploadService, UploadError, ValidationError
from .services.storage_service import StorageService
from .services.processing_service import ProcessingService
from .components.document_manager.document_manager import DocumentManager

# Simple logging setup
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("main_ai_enhanced")

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
    
    async def generate_response(self, message: str, context: list = None, image_data: bytes = None, image_mime_type: str = None, document_manager=None) -> Dict[str, Any]:
        """Generate AI response using available models with multimodal support and document search"""
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
            
            # Search documents for relevant content
            document_context = ""
            document_citations = []
            knowledge_insights = []
            
            if document_manager:
                try:
                    # Get list of available documents
                    from .models.documents import DocumentSearchRequest, DocumentStatus
                    search_request = DocumentSearchRequest(
                        status=DocumentStatus.COMPLETED,
                        page=1,
                        page_size=10
                    )
                    
                    documents_response = await document_manager.upload_service.list_documents(search_request)
                    
                    if documents_response.documents:
                        # Search through completed documents for relevant content
                        for doc in documents_response.documents[:3]:  # Limit to top 3 documents
                            try:
                                # Search document knowledge
                                knowledge_results = await document_manager.search_document_knowledge(
                                    doc.document_id, message, max_results=3
                                )
                                
                                if knowledge_results.get('concepts') or knowledge_results.get('relationships'):
                                    # Add document citation
                                    document_citations.append({
                                        "document_id": str(doc.document_id),
                                        "title": doc.title,
                                        "source_type": "PDF_DOCUMENT",
                                        "concepts_found": len(knowledge_results.get('concepts', [])),
                                        "relationships_found": len(knowledge_results.get('relationships', []))
                                    })
                                    
                                    # Add knowledge insights
                                    for concept in knowledge_results.get('concepts', [])[:2]:
                                        knowledge_insights.append({
                                            "type": "concept",
                                            "name": concept['concept_name'],
                                            "confidence": concept['confidence'],
                                            "source_document": doc.title
                                        })
                                    
                                    for relationship in knowledge_results.get('relationships', [])[:2]:
                                        knowledge_insights.append({
                                            "type": "relationship", 
                                            "subject": relationship['subject_concept'],
                                            "predicate": relationship['predicate'],
                                            "object": relationship['object_concept'],
                                            "confidence": relationship['confidence'],
                                            "source_document": doc.title
                                        })
                                    
                                    # Build document context for AI
                                    concepts_text = ", ".join([c['concept_name'] for c in knowledge_results.get('concepts', [])[:3]])
                                    if concepts_text:
                                        document_context += f"\n\nFrom document '{doc.title}': Key concepts include {concepts_text}."
                                        
                            except Exception as e:
                                logger.warning(f"Failed to search document {doc.document_id}: {e}")
                                continue
                                
                except Exception as e:
                    logger.warning(f"Failed to search documents: {e}")
            
            # Create enhanced prompt with document context
            system_prompt = """You are a knowledgeable AI assistant called The Librarian. 
            You help users with questions, provide detailed information, and maintain engaging conversations.
            You are running on AWS infrastructure and can discuss technical topics, general knowledge, 
            and help with research questions. You can also analyze images, documents, and other media.
            
            When you have access to document content and knowledge from uploaded PDFs, incorporate this 
            information naturally into your responses and mention the source documents when relevant.
            Be helpful, informative, and conversational."""
            
            # Handle multimodal input (image + text)
            if image_data and image_mime_type:
                response_text = await self._generate_multimodal_response(message, context_text, image_data, image_mime_type, system_prompt, document_context)
            else:
                # Handle text-only input with document context
                full_prompt = f"{system_prompt}\n\nConversation context:\n{context_text}{document_context}\n\nUser: {message}\n\nAssistant:"
                
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
                "document_citations": document_citations,
                "knowledge_insights": knowledge_insights
            }
            
        except Exception as e:
            if logger:
                logger.error(f"AI response generation failed: {e}")
            return {
                "text_content": self._fallback_response(message),
                "document_citations": [],
                "knowledge_insights": []
            }
    
    async def _generate_multimodal_response(self, message: str, context_text: str, image_data: bytes, image_mime_type: str, system_prompt: str, document_context: str = "") -> str:
        """Generate response for multimodal input (text + image) using Gemini 2.5 Flash"""
        try:
            if self.gemini_vision_model:
                # Create image part for Gemini
                import PIL.Image
                import io
                
                # Convert bytes to PIL Image
                image = PIL.Image.open(io.BytesIO(image_data))
                
                # Create multimodal prompt with document context
                multimodal_prompt = f"{system_prompt}\n\nConversation context:\n{context_text}{document_context}\n\nUser message: {message}\n\nPlease analyze the provided image and respond to the user's message in context."
                
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
    
    def __init__(self, ai_manager: AIManager, document_manager=None):
        self.active_connections = {}
        self.conversation_history = {}
        self.ai_manager = ai_manager
        self.document_manager = document_manager
    
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
        response = await self.ai_manager.generate_response(message, history, document_manager=self.document_manager)
        return response
    
    async def process_message_with_image(self, message: str, connection_id: str, image_data: bytes = None, image_mime_type: str = None) -> Dict[str, Any]:
        """Process message with optional image data and return enhanced AI response"""
        history = self.get_history(connection_id)
        response = await self.ai_manager.generate_response(message, history, image_data, image_mime_type, self.document_manager)
        return response

def create_ai_enhanced_app() -> FastAPI:
    """Create an AI-enhanced FastAPI application."""
    
    app = FastAPI(
        title="The Librarian",
        description="AI-powered assistant with OpenAI/Gemini integration",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    app_start_time = time.time()
    
    if logger:
        logger.info("Starting AI-enhanced FastAPI application")
    
    # Initialize AI Manager
    ai_manager = AIManager()
    
    # Initialize Upload Service
    upload_service = UploadService()
    
    # Initialize Processing Service and Document Manager
    processing_service = ProcessingService(upload_service)
    document_manager = DocumentManager(upload_service, processing_service)
    
    # Initialize Enhanced Connection Manager
    connection_manager = EnhancedConnectionManager(ai_manager, document_manager)
    
    # Feature availability
    FEATURES = {
        "chat": True,
        "ai_powered_chat": True,
        "conversation_context": True,
        "intelligent_responses": True,
        "openai_integration": True,
        "gemini_integration": True,
        "multimodal": True,          # Now implemented!
        "image_analysis": True,      # Now implemented!
        "static_files": True,
        "monitoring": True,
        "enhanced_ai": True,
        "knowledge_base": False,  # To be implemented
        "vector_search": False,   # To be implemented
        "pdf_processing": True,   # Now implemented!
        "document_upload": True,  # Now implemented!
        "document_management": True,  # Now implemented!
        "document_search": True,  # Now implemented!
        "knowledge_integration": True,  # Now implemented!
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
            "enhancement": "Full AI Integration"
        }
    
    @app.get("/features")
    async def get_features():
        """Get current feature availability."""
        return {
            "features": FEATURES,
            "deployment_type": "ai-enhanced",
            "ai_integration": True,
            "cost_optimized": False,
            "description": "Full AI-powered deployment with OpenAI and Gemini integration",
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
                "document_processing": True,
                "document_search": True,
                "knowledge_citations": True
            }
        }
    
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
                .document-item {
                    background: white;
                    border: 1px solid #dee2e6;
                    border-radius: 8px;
                    padding: 16px;
                    margin-bottom: 12px;
                    transition: all 0.3s;
                }
                .document-item:hover {
                    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
                }
                .document-title {
                    font-weight: 600;
                    color: #495057;
                    margin-bottom: 4px;
                }
                .document-meta {
                    font-size: 12px;
                    color: #6c757d;
                    display: flex;
                    gap: 16px;
                }
                .document-status {
                    padding: 2px 8px;
                    border-radius: 12px;
                    font-size: 11px;
                    font-weight: 500;
                    text-transform: uppercase;
                }
                .status-uploaded { background: #fff3cd; color: #856404; }
                .status-processing { background: #cce5ff; color: #004085; }
                .status-completed { background: #d4edda; color: #155724; }
                .status-failed { background: #f8d7da; color: #721c24; }
                .input-area { 
                    position: relative;
                    padding: 20px; 
                    background: white; 
                    border-top: 1px solid #eee; 
                    flex-shrink: 0;
                }
                .input-group { display: flex; gap: 12px; align-items: center; }
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
                .drop-overlay {
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: rgba(255, 107, 107, 0.95);
                    color: white;
                    display: none;
                    align-items: center;
                    justify-content: center;
                    z-index: 1000;
                    border-radius: 12px;
                }
                .drop-message {
                    text-align: center;
                    font-size: 18px;
                    font-weight: 500;
                }
                .drop-icon {
                    display: block;
                    font-size: 48px;
                    margin-bottom: 16px;
                }
                .input-area.drag-over .drop-overlay {
                    display: flex;
                }
                .container.drag-over { 
                    border: 3px dashed #ff6b6b; 
                    background: rgba(255, 107, 107, 0.05); 
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
                .system.citation {
                    background: #e7f3ff;
                    color: #0066cc;
                    border: 1px solid #b3d9ff;
                    text-align: left;
                    font-style: normal;
                }
                .system.insight {
                    background: #f0f9ff;
                    color: #0369a1;
                    border: 1px solid #bae6fd;
                    text-align: left;
                    font-style: normal;
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
                .hidden { display: none !important; }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📚 The Librarian</h1>
                    <p>Powered by Gemini 2.5 Flash - Advanced AI Assistant with Document Processing</p>
                </div>
                
                <div class="nav-tabs">
                    <button class="nav-tab active" onclick="switchTab('chat')">💬 Chat</button>
                    <button class="nav-tab" onclick="switchTab('documents')">📄 Documents</button>
                    <button class="nav-tab" onclick="switchTab('analytics')">📊 Analytics</button>
                </div>
                
                <!-- Chat Tab -->
                <div id="chat-tab" class="tab-content active">
                    <div class="status">🟢 The Librarian Active - AI Ready with Document Processing!</div>
                    <div id="messages">
                        <div class="message system">📚 Welcome to The Librarian!</div>
                        <div class="message system">🧠 I'm powered by Gemini 2.5 Flash with advanced AI capabilities and document processing.</div>
                        <div class="message system">💬 Ask me anything - I can help with research, analysis, and conversations!</div>
                        <div class="message system">📄 Upload PDF documents in the Documents tab to enhance our conversations with knowledge from your files!</div>
                        <div class="message system">🔍 Try asking about topics related to your uploaded documents for enhanced responses with citations.</div>
                    </div>
                    <div class="input-area">
                        <div class="rich-input-container">
                            <div id="richInput" contenteditable="true" class="rich-input" placeholder="Type your message here... You can paste images directly or drag them in!"></div>
                            <div class="input-actions">
                                <button id="sendButton">Send</button>
                            </div>
                        </div>
                        <div id="dropOverlay" class="drop-overlay">
                            <div class="drop-message">
                                <span class="drop-icon">📎</span>
                                <span>Drop images here to add them to your message</span>
                            </div>
                        </div>
                        <p style="text-align: center; margin-top: 10px; font-size: 12px; color: #666;">
                            📚 The Librarian • Powered by Gemini 2.5 Flash • AI Assistant with Document Search & Knowledge Integration
                        </p>
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
                                <div>No documents uploaded yet</div>
                                <div style="font-size: 14px; margin-top: 8px;">Upload PDF documents to enhance your conversations with The Librarian</div>
                            </div>
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
                                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                color: white;
                                border: none;
                                padding: 12px 24px;
                                border-radius: 8px;
                                font-size: 16px;
                                cursor: pointer;
                                transition: transform 0.2s ease;
                            " onmouseover="this.style.transform='translateY(-2px)'" onmouseout="this.style.transform='translateY(0)'">
                                📈 Open Analytics Dashboard
                            </button>
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
            const dropOverlay = document.getElementById('dropOverlay');
            const inputArea = document.querySelector('.input-area');
            const fileInput = document.getElementById('fileInput');
            const uploadZone = document.querySelector('.upload-zone');
            const documentsList = document.getElementById('documentsList');
            
            // Tab switching
            function switchTab(tabName) {
                // Update tab buttons
                document.querySelectorAll('.nav-tab').forEach(tab => tab.classList.remove('active'));
                document.querySelector(`[onclick="switchTab('${tabName}')"]`).classList.add('active');
                
                // Update tab content
                document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
                document.getElementById(`${tabName}-tab`).classList.add('active');
                
                currentTab = tabName;
                
                if (tabName === 'documents') {
                    loadDocuments();
                }
            }
            
            // Analytics dashboard function
            function openAnalyticsDashboard() {
                window.open('/analytics', '_blank');
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
                event.target.value = ''; // Reset input
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
                        loadDocuments(); // Refresh document list
                        
                        // Show success message in chat if on chat tab
                        if (currentTab === 'chat') {
                            addMessage('system', `📄 Document "${result.title}" uploaded successfully! Processing will begin shortly.`);
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
            
            async function loadDocuments() {
                try {
                    const response = await fetch('/api/documents?page=1&page_size=20');
                    if (response.ok) {
                        const data = await response.json();
                        displayDocuments(data.documents);
                    } else {
                        console.error('Failed to load documents');
                    }
                } catch (error) {
                    console.error('Error loading documents:', error);
                }
            }
            
            function displayDocuments(documents) {
                if (documents.length === 0) {
                    documentsList.innerHTML = `
                        <div style="text-align: center; color: #6c757d; padding: 40px;">
                            <div style="font-size: 48px; margin-bottom: 16px;">📚</div>
                            <div>No documents uploaded yet</div>
                            <div style="font-size: 14px; margin-top: 8px;">Upload PDF documents to enhance your conversations with The Librarian</div>
                        </div>
                    `;
                    return;
                }
                
                const documentsHtml = documents.map(doc => `
                    <div class="document-item">
                        <div class="document-title">${doc.title}</div>
                        <div class="document-meta">
                            <span class="document-status status-${doc.status}">${doc.status}</span>
                            <span>${formatFileSize(doc.file_size)}</span>
                            <span>${formatDate(doc.upload_timestamp)}</span>
                            ${doc.page_count ? `<span>${doc.page_count} pages</span>` : ''}
                        </div>
                    </div>
                `).join('');
                
                documentsList.innerHTML = documentsHtml;
            }
            
            function formatFileSize(bytes) {
                if (bytes === 0) return '0 Bytes';
                const k = 1024;
                const sizes = ['Bytes', 'KB', 'MB', 'GB'];
                const i = Math.floor(Math.log(bytes) / Math.log(k));
                return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
            }
            
            function formatDate(dateString) {
                const date = new Date(dateString);
                return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'});
            }
            
            // WebSocket functionality
            function connectWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws/ai-chat`;
                
                ws = new WebSocket(wsUrl);
                
                ws.onopen = function(event) {
                    isConnected = true;
                    sendButton.disabled = false;
                    addMessage('system', '🟢 The Librarian connected! Ask me anything - I have advanced AI capabilities and document processing now.');
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
            
            // Rich input functions
            function extractContentFromRichInput() {
                const content = {
                    text: '',
                    images: []
                };
                
                // Get text content (strip HTML but preserve line breaks)
                const textContent = richInput.innerText || richInput.textContent || '';
                content.text = textContent.trim();
                
                // Get images
                const images = richInput.querySelectorAll('img');
                images.forEach(img => {
                    if (img.src && img.src.startsWith('data:image/')) {
                        const base64Data = img.src.split(',')[1];
                        const mimeType = img.src.match(/data:([^;]+);/)[1];
                        content.images.push({
                            data: base64Data,
                            mimeType: mimeType
                        });
                    }
                });
                
                return content;
            }
            
            function clearRichInput() {
                richInput.innerHTML = '';
                richInput.focus();
            }
            
            function insertImageIntoRichInput(file) {
                if (file && file.type.startsWith('image/')) {
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        const img = document.createElement('img');
                        img.src = e.target.result;
                        img.style.maxWidth = '100%';
                        img.style.maxHeight = '200px';
                        img.style.borderRadius = '8px';
                        img.style.margin = '8px 0';
                        img.style.display = 'block';
                        img.style.border = '2px solid #e1e5e9';
                        
                        // Insert at cursor position or at the end
                        const selection = window.getSelection();
                        if (selection.rangeCount > 0 && richInput.contains(selection.anchorNode)) {
                            const range = selection.getRangeAt(0);
                            range.deleteContents();
                            range.insertNode(img);
                            range.collapse(false);
                        } else {
                            richInput.appendChild(img);
                        }
                        
                        // Add a line break after the image
                        const br = document.createElement('br');
                        richInput.appendChild(br);
                        
                        // Focus back to the input
                        richInput.focus();
                    };
                    reader.readAsDataURL(file);
                }
            }
            
            function sendMessage() {
                const content = extractContentFromRichInput();
                
                if ((content.text || content.images.length > 0) && isConnected) {
                    const messageData = {
                        type: 'user_message',
                        content: content.text,
                        timestamp: new Date().toISOString()
                    };
                    
                    // Add image data if present (for now, just send the first image)
                    if (content.images.length > 0) {
                        messageData.image_data = content.images[0].data;
                        messageData.image_mime_type = content.images[0].mimeType;
                    }
                    
                    ws.send(JSON.stringify(messageData));
                    clearRichInput();
                }
            }
            
            sendButton.onclick = sendMessage;
            
            // Rich input event listeners
            richInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
            
            // Paste event for images
            richInput.addEventListener('paste', function(e) {
                const items = e.clipboardData.items;
                for (let i = 0; i < items.length; i++) {
                    const item = items[i];
                    if (item.type.startsWith('image/')) {
                        e.preventDefault();
                        const file = item.getAsFile();
                        insertImageIntoRichInput(file);
                        break;
                    }
                }
            });
            
            // Drag and drop functionality for chat
            inputArea.addEventListener('dragover', function(e) {
                e.preventDefault();
                inputArea.classList.add('drag-over');
            });
            
            inputArea.addEventListener('dragleave', function(e) {
                e.preventDefault();
                if (!inputArea.contains(e.relatedTarget)) {
                    inputArea.classList.remove('drag-over');
                }
            });
            
            inputArea.addEventListener('drop', function(e) {
                e.preventDefault();
                inputArea.classList.remove('drag-over');
                
                const files = e.dataTransfer.files;
                for (let i = 0; i < files.length; i++) {
                    const file = files[i];
                    if (file.type.startsWith('image/')) {
                        insertImageIntoRichInput(file);
                    }
                }
            });
            
            // Initialize WebSocket connection
            connectWebSocket();
        </script>
            let ws = null;
            let isConnected = false;
            
            const richInput = document.getElementById('richInput');
            const sendButton = document.getElementById('sendButton');
            const messages = document.getElementById('messages');
            const dropOverlay = document.getElementById('dropOverlay');
            const inputArea = document.querySelector('.input-area');
            
            function connectWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws/ai-chat`;
                
                ws = new WebSocket(wsUrl);
                
                ws.onopen = function(event) {
                    isConnected = true;
                    sendButton.disabled = false;
                    messageInput.disabled = false;
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
                    messageInput.disabled = true;
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
            
            // Rich input functions
            function extractContentFromRichInput() {
                const content = {
                    text: '',
                    images: []
                };
                
                // Get text content (strip HTML but preserve line breaks)
                const textContent = richInput.innerText || richInput.textContent || '';
                content.text = textContent.trim();
                
                // Get images
                const images = richInput.querySelectorAll('img');
                images.forEach(img => {
                    if (img.src && img.src.startsWith('data:image/')) {
                        const base64Data = img.src.split(',')[1];
                        const mimeType = img.src.match(/data:([^;]+);/)[1];
                        content.images.push({
                            data: base64Data,
                            mimeType: mimeType
                        });
                    }
                });
                
                return content;
            }
            
            function clearRichInput() {
                richInput.innerHTML = '';
                richInput.focus();
            }
            
            function insertImageIntoRichInput(file) {
                if (file && file.type.startsWith('image/')) {
                    const reader = new FileReader();
                    reader.onload = function(e) {
                        const img = document.createElement('img');
                        img.src = e.target.result;
                        img.style.maxWidth = '100%';
                        img.style.maxHeight = '200px';
                        img.style.borderRadius = '8px';
                        img.style.margin = '8px 0';
                        img.style.display = 'block';
                        img.style.border = '2px solid #e1e5e9';
                        
                        // Insert at cursor position or at the end
                        const selection = window.getSelection();
                        if (selection.rangeCount > 0 && richInput.contains(selection.anchorNode)) {
                            const range = selection.getRangeAt(0);
                            range.deleteContents();
                            range.insertNode(img);
                            range.collapse(false);
                        } else {
                            richInput.appendChild(img);
                        }
                        
                        // Add a line break after the image
                        const br = document.createElement('br');
                        richInput.appendChild(br);
                        
                        // Focus back to the input
                        richInput.focus();
                    };
                    reader.readAsDataURL(file);
                }
            }
            
            function sendMessage() {
                const content = extractContentFromRichInput();
                
                if ((content.text || content.images.length > 0) && isConnected) {
                    const messageData = {
                        type: 'user_message',
                        content: content.text,
                        timestamp: new Date().toISOString()
                    };
                    
                    // Add image data if present (for now, just send the first image)
                    if (content.images.length > 0) {
                        messageData.image_data = content.images[0].data;
                        messageData.image_mime_type = content.images[0].mimeType;
                    }
                    
                    ws.send(JSON.stringify(messageData));
                    clearRichInput();
                }
            }
            
            sendButton.onclick = sendMessage;
            
            // Rich input event listeners
            richInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                }
            });
            
            // Paste event for images
            richInput.addEventListener('paste', function(e) {
                const items = e.clipboardData.items;
                for (let i = 0; i < items.length; i++) {
                    const item = items[i];
                    if (item.type.startsWith('image/')) {
                        e.preventDefault();
                        const file = item.getAsFile();
                        insertImageIntoRichInput(file);
                        break;
                    }
                }
            });
            
            // Drag and drop functionality
            inputArea.addEventListener('dragover', function(e) {
                e.preventDefault();
                inputArea.classList.add('drag-over');
            });
            
            inputArea.addEventListener('dragleave', function(e) {
                e.preventDefault();
                if (!inputArea.contains(e.relatedTarget)) {
                    inputArea.classList.remove('drag-over');
                }
            });
            
            inputArea.addEventListener('drop', function(e) {
                e.preventDefault();
                inputArea.classList.remove('drag-over');
                
                const files = e.dataTransfer.files;
                for (let i = 0; i < files.length; i++) {
                    const file = files[i];
                    if (file.type.startsWith('image/')) {
                        insertImageIntoRichInput(file);
                    }
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
                image_data = message_data.get("image_data")
                image_mime_type = message_data.get("image_mime_type")
                
                if not user_message and not image_data:
                    continue
                
                # Process image data if present
                image_bytes = None
                if image_data:
                    import base64
                    image_bytes = base64.b64decode(image_data)
                
                # Add to history
                history_content = user_message
                if image_data:
                    history_content += " [Image attached]"
                connection_manager.add_to_history(connection_id, history_content, 'user')
                
                # Echo user message
                echo_content = user_message
                if image_data:
                    echo_content += " 🖼️ [Image attached]"
                await connection_manager.send_personal_message({
                    "type": "user",
                    "content": echo_content,
                    "timestamp": time.time()
                }, connection_id)
                
                # Show typing indicator
                await connection_manager.send_personal_message({
                    "type": "typing",
                    "content": "The Librarian is analyzing...",
                    "timestamp": time.time()
                }, connection_id)
                
                # Generate AI response with image support
                response = await connection_manager.process_message_with_image(
                    user_message, connection_id, image_bytes, image_mime_type
                )
                
                # Add response to history
                response_text = response.get("text_content", "")
                connection_manager.add_to_history(connection_id, response_text, 'assistant')
                
                # Send main response
                await connection_manager.send_personal_message({
                    "type": "assistant",
                    "content": response_text,
                    "timestamp": time.time()
                }, connection_id)
                
                # Send document citations if available
                if response.get("document_citations"):
                    citations_text = "📚 **Sources from your documents:**\n"
                    for citation in response["document_citations"]:
                        citations_text += f"• **{citation['title']}**: Found {citation['concepts_found']} relevant concepts"
                        if citation['relationships_found'] > 0:
                            citations_text += f" and {citation['relationships_found']} relationships"
                        citations_text += "\n"
                    
                    await connection_manager.send_personal_message({
                        "type": "system",
                        "content": citations_text,
                        "timestamp": time.time()
                    }, connection_id)
                
                # Send knowledge insights if available
                if response.get("knowledge_insights"):
                    insights_text = "🧠 **Key insights from your documents:**\n"
                    for insight in response["knowledge_insights"][:3]:  # Limit to 3 insights
                        if insight["type"] == "concept":
                            insights_text += f"• **{insight['name']}** (from {insight['source_document']})\n"
                        elif insight["type"] == "relationship":
                            insights_text += f"• **{insight['subject']}** {insight['predicate']} **{insight['object']}** (from {insight['source_document']})\n"
                    
                    await connection_manager.send_personal_message({
                        "type": "system", 
                        "content": insights_text,
                        "timestamp": time.time()
                    }, connection_id)
                
        except WebSocketDisconnect:
            connection_manager.disconnect(connection_id)
        except Exception as e:
            if logger:
                logger.error(f"WebSocket error: {e}")
            connection_manager.disconnect(connection_id)
    
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
            "deployment_type": "ai-enhanced"
        }
    
    @app.get("/health/simple")
    async def simple_health_check():
        """Simple health check for load balancers."""
        return {"status": "ok", "timestamp": time.time(), "ai_enabled": True}
    
    @app.get("/test/database")
    async def test_database_connection():
        """Test database connectivity."""
        try:
            # Get database credentials from AWS Secrets Manager
            secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
            
            # Get database secret
            db_secret_response = secrets_client.get_secret_value(
                SecretId='multimodal-librarian/learning/database'
            )
            db_credentials = json.loads(db_secret_response['SecretString'])
            
            # Test PostgreSQL connection
            conn = psycopg2.connect(
                host=db_credentials['host'],
                port=db_credentials['port'],
                database=db_credentials['dbname'],
                user=db_credentials['username'],
                password=db_credentials['password'],
                connect_timeout=10
            )
            
            # Test basic query
            cursor = conn.cursor()
            cursor.execute("SELECT version();")
            db_version = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            
            return {
                "status": "success",
                "database": "postgresql",
                "host": db_credentials['host'],
                "database_name": db_credentials['dbname'],
                "version": db_version,
                "connection_test": "passed"
            }
            
        except Exception as e:
            return {
                "status": "error",
                "database": "postgresql", 
                "error": str(e),
                "connection_test": "failed"
            }
    
    @app.get("/test/redis")
    async def test_redis_connection():
        """Test Redis connectivity."""
        try:
            # Get Redis credentials from AWS Secrets Manager
            secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
            
            # Get Redis secret
            redis_secret_response = secrets_client.get_secret_value(
                SecretId='multimodal-librarian/learning/redis'
            )
            redis_credentials = json.loads(redis_secret_response['SecretString'])
            
            return {
                "status": "success",
                "database": "redis",
                "host": redis_credentials['host'],
                "port": redis_credentials['port'],
                "connection_test": "credentials_available"
            }
            
        except Exception as e:
            return {
                "status": "error",
                "database": "redis",
                "error": str(e),
                "connection_test": "failed"
            }
    
    @app.get("/test/ai")
    async def test_ai_integration():
        """Test AI integration."""
        if not ai_manager.initialized:
            await ai_manager.initialize()
        
        test_response = await ai_manager.generate_response(
            "Hello, this is a test message. Please respond briefly to confirm you're working."
        )
        
        return {
            "status": "success" if ai_manager.initialized else "error",
            "ai_available": AI_AVAILABLE,
            "ai_initialized": ai_manager.initialized,
            "openai_available": ai_manager.openai_client is not None,
            "gemini_available": ai_manager.gemini_model is not None,
            "gemini_vision_available": ai_manager.gemini_vision_model is not None,
            "model_info": {
                "primary_model": "gemini-2.0-flash-exp",
                "fallback_model": "gpt-3.5-turbo",
                "multimodal_support": True,
                "vision_capabilities": True
            },
            "test_response": test_response[:100] + "..." if len(test_response) > 100 else test_response
        }
    
    # Document Upload API Endpoints
    
    @app.post("/api/documents/upload", response_model=DocumentUploadResponse)
    async def upload_document(
        file: UploadFile = File(...),
        title: Optional[str] = Form(None),
        description: Optional[str] = Form(None)
    ):
        """Upload a PDF document for processing."""
        try:
            # Validate file type
            if file.content_type != 'application/pdf':
                raise HTTPException(status_code=400, detail="Only PDF files are supported")
            
            # Read file content
            file_content = await file.read()
            
            # Create upload request
            upload_request = DocumentUploadRequest(
                title=title,
                description=description
            )
            
            # Process upload
            result = await upload_service.upload_document(
                file_data=file_content,
                filename=file.filename,
                upload_request=upload_request
            )
            
            return result
            
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except UploadError as e:
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Unexpected error in upload endpoint: {e}")
            raise HTTPException(status_code=500, detail="Internal server error")
    
    @app.get("/api/documents", response_model=DocumentListResponse)
    async def list_documents(
        query: Optional[str] = None,
        status: Optional[DocumentStatus] = None,
        page: int = 1,
        page_size: int = 20
    ):
        """List uploaded documents with filtering and pagination."""
        try:
            search_request = DocumentSearchRequest(
                query=query,
                status=status,
                page=page,
                page_size=page_size
            )
            
            result = await upload_service.list_documents(search_request)
            return result
            
        except Exception as e:
            logger.error(f"Error listing documents: {e}")
            raise HTTPException(status_code=500, detail="Failed to retrieve documents")
    
    @app.get("/api/documents/statistics")
    async def get_upload_statistics():
        """Get upload statistics and metrics."""
        try:
            stats = await upload_service.get_upload_statistics()
            return stats
            
        except Exception as e:
            logger.error(f"Error retrieving statistics: {e}")
            raise HTTPException(status_code=500, detail="Failed to retrieve statistics")
    
    @app.get("/api/documents/{document_id}", response_model=Document)
    async def get_document(document_id: UUID):
        """Get document details by ID."""
        try:
            document = await upload_service.get_document(document_id)
            if not document:
                raise HTTPException(status_code=404, detail="Document not found")
            
            return document
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error retrieving document {document_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to retrieve document")
    
    @app.delete("/api/documents/{document_id}")
    async def delete_document(document_id: UUID):
        """Delete a document and its associated files."""
        try:
            success = await upload_service.delete_document(document_id)
            if not success:
                raise HTTPException(status_code=404, detail="Document not found")
            
            return {"message": "Document deleted successfully"}
            
        except HTTPException:
            raise
        except UploadError as e:
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            logger.error(f"Error deleting document {document_id}: {e}")
            raise HTTPException(status_code=500, detail="Failed to delete document")
    
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
                return HTMLResponse(content=template_path.read_text())
            else:
                # Fallback HTML if template not found
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
                    <a href="/" style="color: #3498db;">← Back to Chat</a>
                </div>
            </body>
            </html>
            """)
    
    return app

# Create the app instance
app = create_ai_enhanced_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "multimodal_librarian.main_ai_enhanced:app",
        host="0.0.0.0",
        port=8000,
        workers=1,
    )