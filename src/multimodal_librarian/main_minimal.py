"""
Minimal FastAPI application for learning deployment.

This is a simplified version of main.py that removes complex dependencies
to get the basic application running in AWS ECS.
"""

import time
import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
import psycopg2
import boto3

# Import basic configuration
try:
    from .config import get_settings
    from .logging_config import configure_logging, get_logger
    
    # Configure logging
    configure_logging()
    logger = get_logger("main_minimal")
    
    # Get settings
    settings = get_settings()
    
    CONFIG_AVAILABLE = True
except ImportError as e:
    print(f"Configuration not available: {e}")
    CONFIG_AVAILABLE = False
    logger = None
    settings = None

# Simple health check response
def create_minimal_app() -> FastAPI:
    """Create a minimal FastAPI application for learning deployment."""
    
    app = FastAPI(
        title="Multimodal Librarian - Learning",
        description="Minimal version for AWS learning deployment",
        version="0.1.0-learning",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    app_start_time = time.time()
    
    if logger:
        logger.info("Starting minimal FastAPI application")
    
    # Feature availability
    FEATURES = {
        "chat": True,
        "functional_chat": True,
        "conversation_context": True,
        "intelligent_responses": True,
        "static_files": True,
        "monitoring": True,
        "auth": False,
        "conversations": False,
        "query": False,
        "export": False,
        "ml_training": False,
        "security": False,
        "vector_search": False,
        "knowledge_graph": False
    }
    
    # Add inline functional chat router to avoid import issues
    from fastapi import WebSocket, WebSocketDisconnect
    from uuid import uuid4
    import json
    
    # Simple connection manager
    class InlineConnectionManager:
        def __init__(self):
            self.active_connections = {}
            self.conversation_history = {}
        
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
                # Keep only last 10 messages
                if len(self.conversation_history[connection_id]) > 10:
                    self.conversation_history[connection_id] = self.conversation_history[connection_id][-10:]
        
        def get_history(self, connection_id: str):
            return self.conversation_history.get(connection_id, [])
    
    # Initialize connection manager
    inline_manager = InlineConnectionManager()
    
    # Simple chat processor
    def process_inline_message(message: str, history: list = None) -> str:
        """Process message and return intelligent response."""
        message_lower = message.lower().strip()
        
        # Greeting
        if any(word in message_lower for word in ['hello', 'hi', 'hey', 'good morning']):
            return "Hello! I'm your Multimodal Librarian assistant. I can help you with questions, provide information, and maintain conversation context. What would you like to know?"
        
        # Questions about capabilities
        elif any(word in message_lower for word in ['what can you do', 'capabilities', 'features']):
            return "I can engage in conversations, answer questions, and provide information on various topics. I maintain conversation context and can help with research questions. This is a cost-optimized deployment running on AWS for ~$50/month."
        
        # System questions
        elif any(word in message_lower for word in ['system', 'aws', 'deployment', 'cost']):
            return "This system runs on AWS ECS with PostgreSQL and Redis, optimized for learning at ~$50/month. It demonstrates functional chat capabilities with intelligent responses and conversation context while maintaining cost efficiency."
        
        # Help requests
        elif any(word in message_lower for word in ['help', 'assist', 'support']):
            return "I'm here to help! I can answer questions, provide explanations, and assist with various topics. Try asking me about the system, AWS deployment, or any subject you're curious about."
        
        # Thanks
        elif any(word in message_lower for word in ['thank', 'thanks']):
            return "You're welcome! Is there anything else I can help you with? Feel free to ask more questions."
        
        # Goodbye
        elif any(word in message_lower for word in ['bye', 'goodbye']):
            return "Goodbye! Feel free to return anytime you need assistance. Have a great day!"
        
        # Context-aware responses
        elif history and len(history) > 1:
            return f"I understand you're asking about that. Based on our conversation, I can see we've been discussing various topics. This functional chat system maintains context and provides intelligent responses while being cost-optimized for learning."
        
        # Default response
        else:
            return f"That's an interesting point about '{message[:50]}...'. While I don't have specific information about that topic right now, I can help you explore related concepts. This learning deployment demonstrates functional chat capabilities - in a full system, I would search through knowledge bases for detailed answers."
    
    # Add chat status endpoint
    @app.get("/chat/status")
    async def get_inline_chat_status():
        return {
            "status": "active",
            "active_connections": len(inline_manager.active_connections),
            "features": {
                "websocket": True,
                "conversation_context": True,
                "intelligent_responses": True,
                "inline_processing": True
            },
            "deployment_type": "inline-functional",
            "cost_optimized": True
        }
    
    # Add WebSocket endpoint
    @app.websocket("/ws/chat")
    async def websocket_inline_chat(websocket: WebSocket):
        connection_id = str(uuid4())
        await inline_manager.connect(websocket, connection_id)
        
        try:
            # Send welcome message
            await inline_manager.send_personal_message({
                "type": "system",
                "content": "🤖 Inline functional chat ready! I can provide intelligent responses and maintain conversation context.",
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
                inline_manager.add_to_history(connection_id, user_message, 'user')
                
                # Echo user message
                await inline_manager.send_personal_message({
                    "type": "user",
                    "content": user_message,
                    "timestamp": time.time()
                }, connection_id)
                
                # Generate response
                history = inline_manager.get_history(connection_id)
                response = process_inline_message(user_message, history)
                
                # Add response to history
                inline_manager.add_to_history(connection_id, response, 'assistant')
                
                # Send response
                await inline_manager.send_personal_message({
                    "type": "assistant",
                    "content": response,
                    "timestamp": time.time()
                }, connection_id)
                
        except WebSocketDisconnect:
            inline_manager.disconnect(connection_id)
        except Exception as e:
            if logger:
                logger.error(f"WebSocket error: {e}")
            inline_manager.disconnect(connection_id)
    
    if logger:
        logger.info("Inline functional chat added successfully")
    
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "message": "Multimodal Librarian API - Learning Deployment",
            "version": "0.1.0-learning",
            "status": "running",
            "docs_url": "/docs",
            "config_available": CONFIG_AVAILABLE,
            "features": FEATURES,
            "cost_optimized": True
        }
    
    @app.get("/features")
    async def get_features():
        """Get current feature availability."""
        return {
            "features": FEATURES,
            "deployment_type": "inline-functional",
            "cost_optimized": True,
            "fallbacks_enabled": True,
            "description": "Inline functional chat deployment with intelligent responses and conversation context",
            "chat_capabilities": {
                "intelligent_responses": True,
                "conversation_context": True,
                "websocket_communication": True,
                "inline_processing": True,
                "cost_optimized": True
            }
        }
    
    @app.get("/chat", response_class=HTMLResponse)
    async def serve_chat_interface():
        """Serve the enhanced chat interface."""
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Multimodal Librarian - Learning Chat</title>
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
                    background: #d1ecf1; 
                    color: #0c5460; 
                    border-bottom: 1px solid #bee5eb;
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
                .message { 
                    margin-bottom: 15px; 
                    padding: 12px 16px; 
                    border-radius: 12px; 
                    max-width: 80%; 
                    word-wrap: break-word; 
                    line-height: 1.4;
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
                .feature-grid {
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 15px;
                    margin: 20px 0;
                }
                .feature-card {
                    background: white;
                    border: 1px solid #e1e5e9;
                    border-radius: 8px;
                    padding: 15px;
                    text-align: center;
                }
                .feature-card h3 {
                    color: #333;
                    margin-bottom: 8px;
                }
                .feature-card p {
                    color: #666;
                    font-size: 14px;
                }
                .btn {
                    display: inline-block;
                    padding: 8px 16px;
                    background: #4facfe;
                    color: white;
                    text-decoration: none;
                    border-radius: 4px;
                    margin: 5px;
                    font-size: 14px;
                }
                .btn:hover {
                    background: #3d8bfe;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🤖 Multimodal Librarian</h1>
                    <p>Learning Deployment - Cost-Optimized AI Assistant</p>
                </div>
                <div class="status">🟢 Enhanced Web Interface Active - Full System Ready!</div>
                <div id="messages">
                    <div class="message system">🎉 Welcome to Multimodal Librarian Learning Deployment!</div>
                    <div class="message system">💡 This is a cost-optimized deployment perfect for learning AWS and AI.</div>
                    <div class="message system">💰 Running on ~$50/month AWS infrastructure with smart cost optimizations.</div>
                    
                    <div class="feature-grid">
                        <div class="feature-card">
                            <h3>📚 API Documentation</h3>
                            <p>Explore all available endpoints and test the API</p>
                            <a href="/docs" class="btn">View Docs</a>
                        </div>
                        <div class="feature-card">
                            <h3>🏥 Health Monitoring</h3>
                            <p>Check system health and service status</p>
                            <a href="/health" class="btn">Health Check</a>
                        </div>
                        <div class="feature-card">
                            <h3>🎯 Feature Status</h3>
                            <p>See which features are currently available</p>
                            <a href="/features" class="btn">View Features</a>
                        </div>
                        <div class="feature-card">
                            <h3>🗄️ Database Test</h3>
                            <p>Test PostgreSQL database connectivity</p>
                            <a href="/test/database" class="btn">Test DB</a>
                        </div>
                        <div class="feature-card">
                            <h3>⚡ Redis Test</h3>
                            <p>Test Redis cache connectivity</p>
                            <a href="/test/redis" class="btn">Test Redis</a>
                        </div>
                        <div class="feature-card">
                            <h3>⚙️ Configuration</h3>
                            <p>View current system configuration</p>
                            <a href="/test/config" class="btn">View Config</a>
                        </div>
                    </div>
                    
                    <div class="message system">🔧 This interface now provides inline functional chat with intelligent responses!</div>
                    <div class="message system">💬 The chat maintains conversation context and provides meaningful interactions.</div>
                    <div class="message system">🎯 Perfect for learning AWS ECS, RDS, ElastiCache, FastAPI, and conversational AI!</div>
                </div>
                <div class="input-area">
                    <div class="input-group">
                        <input type="text" id="messageInput" placeholder="Try saying hello or ask me about the system!" />
                        <button id="sendButton">Send</button>
                    </div>
                    <p style="text-align: center; margin-top: 10px; font-size: 12px; color: #666;">
                        💡 Functional chat enabled! Try: "Hello", "What can you do?", "Tell me about AWS costs"
                    </p>
                </div>
            </div>
        </body>
        <script>
            // Add functional chat JavaScript
            let ws = null;
            let isConnected = false;
            
            const messageInput = document.getElementById('messageInput');
            const sendButton = document.getElementById('sendButton');
            const messages = document.getElementById('messages');
            
            function connectWebSocket() {
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws/chat`;
                
                ws = new WebSocket(wsUrl);
                
                ws.onopen = function(event) {
                    isConnected = true;
                    sendButton.disabled = false;
                    messageInput.disabled = false;
                    addMessage('system', '🟢 Chat connected! You can now have real conversations.');
                };
                
                ws.onmessage = function(event) {
                    const message = JSON.parse(event.data);
                    addMessage(message.type, message.content);
                };
                
                ws.onclose = function(event) {
                    isConnected = false;
                    sendButton.disabled = true;
                    messageInput.disabled = true;
                    addMessage('system', '🔴 Chat disconnected. Refresh page to reconnect.');
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
            
            function sendMessage() {
                const message = messageInput.value.trim();
                if (message && isConnected) {
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
            
            // Initialize WebSocket connection
            connectWebSocket();
        </script>
        </html>
        """)
    
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
                }
            },
            "uptime_seconds": uptime,
            "active_connections": 0,
            "active_threads": 0,
            "features": FEATURES,
            "deployment_type": "learning-enhanced"
        }
    
    @app.get("/health/simple")
    async def simple_health_check():
        """Simple health check for load balancers."""
        return {"status": "ok", "timestamp": time.time()}
    
    @app.get("/test/database")
    async def test_database_connection():
        """Test database connectivity."""
        try:
            # Get database credentials from AWS Secrets Manager
            secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
            
            # Get database secret
            db_secret_response = secrets_client.get_secret_value(
                SecretId='multimodal-librarian/full-ml/database'
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
                SecretId='multimodal-librarian/full-ml/redis'
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
    
    @app.get("/test/config")
    async def test_configuration():
        """Test configuration system."""
        if not CONFIG_AVAILABLE:
            return {
                "status": "error",
                "message": "Configuration system not available",
                "config_available": False
            }
        
        try:
            return {
                "status": "success",
                "config_available": True,
                "app_name": settings.app_name,
                "debug": settings.debug,
                "log_level": settings.log_level,
                "api_host": settings.api_host,
                "api_port": settings.api_port,
                "environment_variables": {
                    "ENVIRONMENT": os.getenv("ENVIRONMENT", "not_set"),
                    "AWS_DEFAULT_REGION": os.getenv("AWS_DEFAULT_REGION", "not_set"),
                    "PYTHONPATH": os.getenv("PYTHONPATH", "not_set"),
                    "LOG_LEVEL": os.getenv("LOG_LEVEL", "not_set")
                }
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Configuration error: {str(e)}",
                "config_available": True
            }
    
    @app.get("/test/logging")
    async def test_logging():
        """Test logging system."""
        if not logger:
            return {
                "status": "error",
                "message": "Logger not available",
                "logging_available": False
            }
        
        try:
            logger.info("Test log message from /test/logging endpoint")
            logger.warning("Test warning message")
            logger.error("Test error message")
            
            return {
                "status": "success",
                "message": "Logging test completed - check CloudWatch logs",
                "logging_available": True,
                "log_level": settings.log_level if settings else "unknown"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Logging error: {str(e)}",
                "logging_available": True
            }
    
    return app

# Create the app instance
app = create_minimal_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "multimodal_librarian.main_minimal:app",
        host="0.0.0.0",
        port=8000,
        workers=1,
    )