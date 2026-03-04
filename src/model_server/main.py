"""
Model Server - FastAPI Application

Dedicated ML model inference service for embeddings and NLP tasks.
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.embeddings import router as embeddings_router
from .api.health import router as health_router
from .api.nlp import router as nlp_router
from .config import get_settings
from .models.embedding import initialize_embedding_model
from .models.nlp import initialize_nlp_model

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan context manager.
    
    Handles model loading on startup and cleanup on shutdown.
    """
    settings = get_settings()
    
    logger.info("=" * 60)
    logger.info("MODEL SERVER STARTING")
    logger.info("=" * 60)
    
    # Load models if preload is enabled
    if settings.preload_models:
        logger.info("Preloading models...")
        
        # Load embedding model
        logger.info(f"Loading embedding model: {settings.embedding_model}")
        try:
            embedding_model = initialize_embedding_model(
                model_name=settings.embedding_model,
                device=settings.embedding_device,
                cache_dir=settings.model_cache_dir
            )
            if embedding_model.is_loaded:
                logger.info(
                    f"✓ Embedding model loaded: {settings.embedding_model} "
                    f"(dimensions={embedding_model.dimensions}, "
                    f"time={embedding_model.load_time_seconds:.2f}s)"
                )
            else:
                logger.error(f"✗ Failed to load embedding model: {embedding_model.error}")
        except Exception as e:
            logger.error(f"✗ Error loading embedding model: {e}")
        
        # Load NLP model
        logger.info(f"Loading NLP model: {settings.nlp_model}")
        try:
            nlp_model = initialize_nlp_model(model_name=settings.nlp_model)
            if nlp_model.is_loaded:
                logger.info(
                    f"✓ NLP model loaded: {settings.nlp_model} "
                    f"(time={nlp_model.load_time_seconds:.2f}s)"
                )
            else:
                logger.error(f"✗ Failed to load NLP model: {nlp_model.error}")
        except Exception as e:
            logger.error(f"✗ Error loading NLP model: {e}")
    else:
        logger.info("Model preloading disabled, models will load on first request")
    
    logger.info("=" * 60)
    logger.info("MODEL SERVER READY")
    logger.info("=" * 60)
    
    yield
    
    # Cleanup on shutdown
    logger.info("=" * 60)
    logger.info("MODEL SERVER SHUTTING DOWN")
    logger.info("=" * 60)


# Create FastAPI application
app = FastAPI(
    title="Model Server",
    description="Dedicated ML model inference service for embeddings and NLP tasks",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router)
app.include_router(embeddings_router)
app.include_router(nlp_router)


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return {
        "service": "model-server",
        "version": "1.0.0",
        "description": "ML model inference service",
        "endpoints": {
            "health": "/health",
            "embeddings": "/embeddings",
            "nlp": "/nlp/process"
        }
    }


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "src.model_server.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=False
    )
