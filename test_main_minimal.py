#!/usr/bin/env python3
"""
Minimal version of main app to test auth integration.
"""

import sys
import traceback
sys.path.insert(0, '.')

from fastapi import FastAPI
from src.multimodal_librarian.logging_config import configure_logging, get_logger

# Configure logging
configure_logging()
logger = get_logger(__name__)

app = FastAPI(title="Main App Test")

# Add Authentication API router
try:
    from src.multimodal_librarian.api.routers.auth import router as auth_router
    app.include_router(auth_router)
    logger.info("Authentication API router added successfully")
except ImportError as e:
    logger.error(f"Failed to import Authentication router: {e}")
    logger.error(f"Traceback: {traceback.format_exc()}")
except Exception as e:
    logger.error(f"Failed to add Authentication router: {e}")
    logger.error(f"Traceback: {traceback.format_exc()}")

@app.get("/")
async def root():
    return {"message": "Main App Test", "auth_enabled": True}

@app.get("/features")
async def get_features():
    return {"features": {"auth": True}}

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting main app test server...")
    uvicorn.run(app, host="0.0.0.0", port=8004, log_level="info")