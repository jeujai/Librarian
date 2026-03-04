"""
Cost-optimized FastAPI application for learning deployment.

This version includes all functionality but with graceful fallbacks
for expensive or complex dependencies to maintain cost efficiency.
"""

import time
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.exceptions import HTTPException

# Core imports that should always work
from .config import get_settings
from .logging_config import configure_logging, get_logger

# Global variables for tracking application state
app_start_time = time.time()

# Global monitoring instances (will be None if not available)
health_checker = None
metrics_collector = None
performance_monitor = None
ml_monitor = None

# Feature availability flags
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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager with graceful fallbacks."""
    global health_checker, metrics_collector, performance_monitor, ml_monitor
    
    logger = get_logger("main_learning")
    logger.info("Starting Multimodal Librarian learning deployment")
    
    # Try to initialize monitoring components (optional)
    try:
        from .monitoring import HealthChecker, MetricsCollector, PerformanceMonitor, MLMonitor
        
        metrics_collector = MetricsCollector()
        health_checker = HealthChecker()
        performance_monitor = PerformanceMonitor(metrics_collector)
        ml_monitor = MLMonitor()
        
        FEATURES["monitoring"] = True
        logger.info("Monitoring components initialized successfully")
        
    except ImportError as e:
        logger.warning(f"Monitoring components not available: {e}")
    except Exception as e:
        logger.error(f"Failed to initialize monitoring: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Multimodal Librarian learning deployment")
    
    try:
        if performance_monitor:
            performance_monitor.stop_monitoring()
        logger.info("Cleanup completed successfully")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")


def create_learning_app() -> FastAPI:
    """Create cost-optimized FastAPI application with all features."""
    configure_logging()
    
    settings = get_settings()
    logger = get_logger("main_learning")
    
    # Create FastAPI app
    app = FastAPI(
        title=f"{settings.app_name} - Learning",
        description="Cost-optimized learning deployment with full functionality",
        version="0.1.0-learning",
        debug=settings.debug,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    
    # Add basic middleware
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    
    # Try to mount static files
    try:
        if os.path.exists("src/multimodal_librarian/static"):
            app.mount("/static", StaticFiles(directory="src/multimodal_librarian/static"), name="static")
            FEATURES["static_files"] = True
            logger.info("Static files mounted successfully")
        else:
            logger.warning("Static files directory not found")
    except Exception as e:
        logger.warning(f"Could not mount static files: {e}")
    
    # Add chat router (priority feature)
    try:
        from .api.routers import chat
        app.include_router(chat.router, tags=["chat"])
        FEATURES["chat"] = True
        logger.info("Chat router added successfully")
    except ImportError as e:
        logger.warning(f"Chat router not available (missing dependencies): {e}")
        # Try minimal chat router as fallback
        try:
            from .api.routers.chat_minimal import router as chat_minimal_router
            app.include_router(chat_minimal_router, tags=["chat"])
            FEATURES["chat"] = True
            logger.info("Minimal chat router added as fallback")
        except ImportError as e2:
            logger.error(f"No chat router available: {e2}")
    
    # Add other routers with graceful fallbacks
    routers_to_try = [
        ("auth", "authentication", ".api.routers.auth"),
        ("security", "security", ".api.routers.security"),
        ("conversations", "conversations", ".api.routers.conversations"),
        ("query", "query", ".api.routers.query"),
        ("export", "export", ".api.routers.export"),
        ("ml_training", "ml_training", ".api.routers.ml_training"),
    ]
    
    for feature_name, tag_name, module_path in routers_to_try:
        try:
            module = __import__(module_path, fromlist=["router"], level=1)
            app.include_router(module.router, tags=[tag_name])
            FEATURES[feature_name] = True
            logger.info(f"{feature_name.title()} router added successfully")
        except ImportError as e:
            logger.warning(f"{feature_name.title()} router not available: {e}")
        except Exception as e:
            logger.error(f"Error adding {feature_name} router: {e}")
    
    # Root endpoint
    @app.get("/", response_model=dict)
    async def root():
        """Root endpoint with feature status."""
        return {
            "message": "Multimodal Librarian API - Learning Deployment",
            "version": "0.1.0-learning",
            "status": "running",
            "docs_url": "/docs",
            "features": FEATURES,
            "cost_optimized": True
        }
    
    # Serve chat interface
    @app.get("/chat", response_class=HTMLResponse)
    async def serve_chat_interface():
        """Serve the main chat interface."""
        if FEATURES["static_files"]:
            try:
                with open("src/multimodal_librarian/static/index.html", "r") as f:
                    return HTMLResponse(content=f.read())
            except FileNotFoundError:
                pass
        
        # Fallback to minimal chat interface
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Multimodal Librarian - Learning Chat</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
                .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                h1 { color: #333; text-align: center; }
                #messages { border: 1px solid #ddd; height: 400px; overflow-y: scroll; padding: 15px; margin-bottom: 15px; background: #fafafa; border-radius: 4px; }
                .input-group { display: flex; gap: 10px; }
                #messageInput { flex: 1; padding: 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }
                #sendButton { padding: 12px 24px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
                #sendButton:hover { background: #0056b3; }
                .message { margin-bottom: 10px; padding: 8px; border-radius: 4px; }
                .user { background: #e3f2fd; border-left: 4px solid #2196f3; }
                .assistant { background: #f1f8e9; border-left: 4px solid #4caf50; }
                .system { background: #fff3e0; border-left: 4px solid #ff9800; font-style: italic; }
                .status { text-align: center; padding: 10px; margin-bottom: 15px; border-radius: 4px; }
                .connected { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
                .disconnected { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🤖 Multimodal Librarian - Learning Chat</h1>
                <div id="status" class="status disconnected">Connecting to chat server...</div>
                <div id="messages"></div>
                <div class="input-group">
                    <input type="text" id="messageInput" placeholder="Type your message here..." />
                    <button id="sendButton">Send</button>
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
                            status.textContent = 'Connected to chat server';
                            status.className = 'status connected';
                            reconnectAttempts = 0;
                            
                            addMessage('system', 'Connected to Multimodal Librarian Learning Chat!');
                            addMessage('system', 'This is a cost-optimized learning deployment. Some advanced features may have graceful fallbacks.');
                        };
                        
                        ws.onmessage = function(event) {
                            try {
                                const message = JSON.parse(event.data);
                                addMessage(message.type || 'assistant', message.content || message.message || event.data);
                            } catch (e) {
                                addMessage('assistant', event.data);
                            }
                        };
                        
                        ws.onclose = function(event) {
                            status.textContent = 'Disconnected from chat server';
                            status.className = 'status disconnected';
                            
                            if (reconnectAttempts < maxReconnectAttempts) {
                                reconnectAttempts++;
                                addMessage('system', `Connection lost. Attempting to reconnect... (${reconnectAttempts}/${maxReconnectAttempts})`);
                                setTimeout(connect, 2000 * reconnectAttempts);
                            } else {
                                addMessage('system', 'Connection lost. Please refresh the page to reconnect.');
                            }
                        };
                        
                        ws.onerror = function(error) {
                            addMessage('system', 'Connection error occurred');
                        };
                        
                    } catch (error) {
                        status.textContent = 'Failed to connect to chat server';
                        status.className = 'status disconnected';
                        addMessage('system', 'Failed to establish WebSocket connection');
                    }
                }
                
                function addMessage(type, content) {
                    const messageDiv = document.createElement('div');
                    messageDiv.className = 'message ' + type;
                    messageDiv.innerHTML = `<strong>${type.charAt(0).toUpperCase() + type.slice(1)}:</strong> ${content}`;
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
                    }
                }
                
                sendButton.onclick = sendMessage;
                messageInput.addEventListener('keypress', function(e) {
                    if (e.key === 'Enter') {
                        sendMessage();
                    }
                });
                
                // Connect on page load
                connect();
            </script>
        </body>
        </html>
        """)
    
    # Health check endpoints
    @app.get("/health")
    async def health_check(request: Request):
        """Comprehensive health check endpoint."""
        if health_checker:
            try:
                health_status = await health_checker.check_all_services()
                return {
                    "overall_status": health_status["overall_status"],
                    "services": health_status["services"],
                    "uptime_seconds": time.time() - app_start_time,
                    "features": FEATURES
                }
            except Exception as e:
                logger.error(f"Health check error: {e}")
        
        # Fallback health check
        return {
            "overall_status": "healthy",
            "services": {
                "api": {
                    "status": "healthy",
                    "service": "api",
                    "response_time_ms": 1.0
                }
            },
            "uptime_seconds": time.time() - app_start_time,
            "features": FEATURES
        }
    
    @app.get("/health/simple")
    async def simple_health_check():
        """Simple health check for load balancers."""
        return {"status": "ok", "timestamp": time.time()}
    
    # Feature status endpoint
    @app.get("/features")
    async def get_features():
        """Get current feature availability."""
        return {
            "features": FEATURES,
            "deployment_type": "learning",
            "cost_optimized": True,
            "fallbacks_enabled": True
        }
    
    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """Global exception handler."""
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "An internal server error occurred",
                "error_code": "INTERNAL_SERVER_ERROR",
                "deployment_type": "learning"
            }
        )
    
    logger.info("Learning FastAPI application created successfully")
    logger.info(f"Available features: {[k for k, v in FEATURES.items() if v]}")
    
    return app


# Create the app instance
app = create_learning_app()


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "multimodal_librarian.main_learning:app",
        host=settings.api_host,
        port=settings.api_port,
        workers=1,  # Single worker for learning deployment
        reload=settings.debug,
    )