"""
Enhanced WebSocket main application for Multimodal Librarian.

This version includes the enhanced WebSocket router with robust connection management.
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

# Import the enhanced chat router
from .api.routers import chat_simple_enhanced

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Multimodal Librarian - Enhanced WebSocket",
    description="Enhanced WebSocket implementation with robust connection management",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include enhanced chat router
app.include_router(chat_simple_enhanced.router, tags=["Enhanced Chat"])

# Health check endpoints
@app.get("/health")
async def health_check():
    """Simple health check."""
    return {"status": "healthy", "service": "enhanced_websocket"}

@app.get("/health/simple")
async def simple_health():
    """Simple health check for ALB."""
    return {"status": "ok"}

# Root redirect
@app.get("/")
async def root():
    """Redirect to chat interface."""
    return RedirectResponse(url="/chat")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)