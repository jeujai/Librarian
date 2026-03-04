#!/usr/bin/env python3
"""
Simple test server for authentication endpoints.
"""

import sys
import os
sys.path.insert(0, '.')

from fastapi import FastAPI
from src.multimodal_librarian.api.routers.auth import router as auth_router
from src.multimodal_librarian.logging_config import configure_logging, get_logger

# Configure logging
configure_logging()
logger = get_logger(__name__)

# Create simple FastAPI app
app = FastAPI(title="Auth Test Server")

# Add authentication router
app.include_router(auth_router)

@app.get("/")
async def root():
    return {"message": "Auth Test Server", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting auth test server...")
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")