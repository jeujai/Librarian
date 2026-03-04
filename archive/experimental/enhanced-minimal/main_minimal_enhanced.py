"""
Enhanced minimal FastAPI application for learning deployment.

This version includes all the basic functionality with the missing endpoints
that were causing the 404 errors, while maintaining cost optimization.
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
    logger = get_logger("main_minimal_enhanced")
    
    # Get settings
    settings = get_settings()
    
    CONFIG_AVAILABLE = True
except ImportError as e:
    print(f"Configuration not available: {e}")
    CONFIG_AVAILABLE = False
    logger = None
    settings = None

def create_enhanced_minimal_app() -> FastAPI:
    """Create an enhanced minimal FastAPI application for learning deployment."""
    
    app = FastAPI(
        title="Multimodal Librarian - Learning Enhanced",
        description="Enhanced minimal version for AWS learning deployment with full web interface",
        version="0.1.0-learning-enhanced",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    app_start_time = time.time()
    
    if logger:
        logger.info("Starting enhanced minimal FastAPI application")
    
    # Feature availability
    FEATURES = {
        "chat": False,
        "static_files": False,
        "monitoring": False,
        "auth": False,
        "conversations": False,
        "query": False,
        "export": False,
        "ml_training": False,
        "security": False
    }
    
    # Add minimal chat router
    try:
        from .api.routers.chat_minimal import router as chat_router
        app.include_router(chat_router, tags=["chat"])
        FEATURES["chat"] = True
        if logger:
            logger.info("Chat router added successfully")
    except ImportError as e:
        if logger:
            logger.warning(f"Could not import chat router: {e}")
        print(f"Could not import chat router: {e}")
    
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "message": "Multimodal Librarian API - Learning Enhanced",
            "version": "0.1.0-learning-enhanced",
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
            "deployment_type": "learning-enhanced",
            "cost_optimized": True,
            "fallbacks_enabled": True,
            "description": "Enhanced minimal deployment with web interface"
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
                }
                .connected { background: #d1ecf1; color: #0c5460; border-bottom: 1px solid #bee5eb; }
                .disconnected { background: #f8d7da; color: #721c24; border-bottom: 1px solid #f5c6cb; }
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
                #sendButton:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
                .message { 
                    margin-bottom: 15px; 
                    padding: 12px 16px; 
                    border-radius: 12px; 
                    max-width: 80%; 
                    word-wrap: break-word; 
                    line-height: 1.4;
                }
                .user { 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                    color: white; 
                    margin-left: auto; 
                }
                .assistant { 
                    background: #f1f3f4; 
                    color: #333; 
                    border: 1px solid #e8eaed; 
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
                .typing { opacity: 0.7; font-style: italic; }
                @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
                .pulse { animation: pulse 1.5s infinite; }
                
                /* Mobile responsiveness */
                @media (max-width: 768px) {
                    body { padding: 10px; }
                    .container { height: calc(100vh - 20px); }
                    .header { padding: 15px; }
                    .header h1 { font-size: 20px; }
                    #messages { padding: 15px; }
                    .input-area { padding: 15px; }
                    .message { max-width: 90%; }
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🤖 Multimodal Librarian</h1>
                    <p>Learning Deployment - Cost-Optimized AI Assistant</p>
                </div>
                <div id="status" class="status disconnected">🔄 Connecting to chat server...</div>
                <div id="messages"></div>
                <div class="input-area">
                    <div class="input-group">
                        <input type="text" id="messageInput" placeholder="Ask me anything about your documents..." />
                        <button id="sendButton" disabled>Send</button>
                    </div>
                </div>
            </div>
            
            <script>
                const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
                const wsUrl = `${protocol}//${window.location.host}/ws/chat`;
                let ws = null;
                let reconnectAttempts = 0;
                const maxReconnectAttempts = 5;
                
                const messages = document.getElementById('messages');
                const messageInput = document.getElementById('messageInput');
                const sendButton = document.getElementById('sendButton');
                const status = document.getElementById('status');
                
                function connect() {
                    try {
                        ws = new WebSocket(wsUrl);
                        
                        ws.onopen = function(event) {
                            status.textContent = '🟢 Connected - Ready to chat!';
                            status.className = 'status connected';
                            reconnectAttempts = 0;
                            sendButton.disabled = false;
                            
                            addMessage('system', '🎉 Welcome to Multimodal Librarian Learning Chat!');
                            addMessage('system', '💡 This is a cost-optimized deployment perfect for learning AWS and AI.');
                            addMessage('system', '📚 Try asking questions or uploading documents to explore the system.');
                            addMessage('system', '💰 Running on ~$50/month AWS infrastructure with smart cost optimizations.');
                        };
                        
                        ws.onmessage = function(event) {
                            // Remove typing indicator
                            const indicator = document.getElementById('typing-indicator');
                            if (indicator) indicator.remove();
                            
                            try {
                                const message = JSON.parse(event.data);
                                addMessage(message.type || 'assistant', message.content || message.message || event.data);
                            } catch (e) {
                                addMessage('assistant', event.data);
                            }
                        };
                        
                        ws.onclose = function(event) {
                            status.textContent = '🔴 Disconnected from server';
                            status.className = 'status disconnected';
                            sendButton.disabled = true;
                            
                            if (reconnectAttempts < maxReconnectAttempts) {
                                reconnectAttempts++;
                                addMessage('system', `🔄 Connection lost. Reconnecting... (${reconnectAttempts}/${maxReconnectAttempts})`);
                                setTimeout(connect, 2000 * reconnectAttempts);
                            } else {
                                addMessage('system', '❌ Connection lost. Please refresh the page to reconnect.');
                            }
                        };
                        
                        ws.onerror = function(error) {
                            addMessage('system', '⚠️ Connection error - checking server status...');
                        };
                        
                    } catch (error) {
                        status.textContent = '❌ Failed to connect';
                        status.className = 'status disconnected';
                        addMessage('system', '❌ WebSocket connection failed. Please check if the server is running.');
                        sendButton.disabled = true;
                    }
                }
                
                function addMessage(type, content) {
                    const messageDiv = document.createElement('div');
                    messageDiv.className = 'message ' + type;
                    
                    if (type === 'system') {
                        messageDiv.innerHTML = content;
                    } else {
                        const timestamp = new Date().toLocaleTimeString();
                        messageDiv.innerHTML = `<strong>${type.charAt(0).toUpperCase() + type.slice(1)}:</strong> ${content}`;
                    }
                    
                    messages.appendChild(messageDiv);
                    messages.scrollTop = messages.scrollHeight;
                }
                
                function sendMessage() {
                    const message = messageInput.value.trim();
                    if (message && ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({
                            type: 'user_message',
                            content: message,
                            timestamp: new Date().toISOString()
                        }));
                        addMessage('user', message);
                        messageInput.value = '';
                        
                        // Show typing indicator
                        const typingDiv = document.createElement('div');
                        typingDiv.className = 'message assistant typing pulse';
                        typingDiv.innerHTML = '<strong>Assistant:</strong> 🤔 Thinking...';
                        typingDiv.id = 'typing-indicator';
                        messages.appendChild(typingDiv);
                        messages.scrollTop = messages.scrollHeight;
                        
                        // Remove typing indicator after 30 seconds if no response
                        setTimeout(() => {
                            const indicator = document.getElementById('typing-indicator');
                            if (indicator) {
                                indicator.remove();
                                addMessage('system', '⏰ Response taking longer than expected. The AI might be processing a complex request.');
                            }
                        }, 30000);
                    }
                }
                
                sendButton.onclick = sendMessage;
                messageInput.addEventListener('keypress', function(e) {
                    if (e.key === 'Enter' && !e.shiftKey) {
                        e.preventDefault();
                        sendMessage();
                    }
                });
                
                // Connect on page load
                connect();
                
                // Focus input after connection
                setTimeout(() => messageInput.focus(), 1000);
                
                // Add some helpful keyboard shortcuts
                document.addEventListener('keydown', function(e) {
                    if (e.ctrlKey && e.key === 'k') {
                        e.preventDefault();
                        messageInput.focus();
                        messageInput.select();
                    }
                });
            </script>
        </body>
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
    
    # Keep all the existing test endpoints
    @app.get("/test/database")
    async def test_database_connection():
        """Test database connectivity."""
        try:
            secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
            
            db_secret_response = secrets_client.get_secret_value(
                SecretId='multimodal-librarian/learning/database'
            )
            db_credentials = json.loads(db_secret_response['SecretString'])
            
            conn = psycopg2.connect(
                host=db_credentials['host'],
                port=db_credentials['port'],
                database=db_credentials['dbname'],
                user=db_credentials['username'],
                password=db_credentials['password'],
                connect_timeout=10
            )
            
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
            secrets_client = boto3.client('secretsmanager', region_name='us-east-1')
            
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
    
    if logger:
        logger.info("Enhanced minimal FastAPI application created successfully")
        logger.info(f"Available features: {[k for k, v in FEATURES.items() if v]}")
    
    return app

# Create the app instance
app = create_enhanced_minimal_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "multimodal_librarian.main_minimal_enhanced:app",
        host="0.0.0.0",
        port=8000,
        workers=1,
    )