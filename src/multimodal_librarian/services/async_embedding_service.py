"""
Async Embedding Service - Non-blocking embedding generation.

This module provides async wrappers around embedding operations.
Uses the model server for embeddings (separate container).

The model server approach keeps ML models in a separate container,
so app restarts don't require reloading models.
"""

import asyncio
import logging
from typing import List, Optional

import numpy as np

from ..clients.model_server_client import (
    ModelServerClient,
    ModelServerUnavailable,
    get_model_client,
    initialize_model_client,
)

logger = logging.getLogger(__name__)


async def ensure_model_loaded() -> None:
    """
    Ensure embedding capability is available (async, non-blocking).
    
    Initializes the model server client if not already done.
    """
    try:
        client = get_model_client()
        if client is None:
            await initialize_model_client()
            client = get_model_client()
        
        if client and client.enabled:
            # Check if model server is ready
            if await client.is_ready():
                logger.info("Model server is ready - using remote embeddings")
                return
            else:
                logger.info("Model server not ready yet, will retry on first request")
                return
    except Exception as e:
        logger.warning(f"Model server initialization failed: {e}")
        raise ModelServerUnavailable(f"Model server not available: {e}")


async def generate_embedding_async(text: str) -> np.ndarray:
    """
    Generate embedding for text asynchronously (non-blocking).
    
    Uses model server for embedding generation.
    
    Args:
        text: Text to generate embedding for
        
    Returns:
        Embedding vector as numpy array
        
    Raises:
        ModelServerUnavailable: If model server is not available
    """
    client = get_model_client()
    if client is None:
        await initialize_model_client()
        client = get_model_client()
    
    if not client or not client.enabled:
        raise ModelServerUnavailable("Model server is not enabled")
    
    embeddings = await client.generate_embeddings([text])
    if embeddings:
        return np.array(embeddings[0])
    
    raise ModelServerUnavailable("Failed to generate embedding from model server")


async def generate_embeddings_batch_async(texts: List[str]) -> List[np.ndarray]:
    """
    Generate embeddings for multiple texts asynchronously (non-blocking).
    
    Uses model server for embedding generation.
    
    Args:
        texts: List of texts to generate embeddings for
        
    Returns:
        List of embedding vectors
        
    Raises:
        ModelServerUnavailable: If model server is not available
    """
    if not texts:
        return []
    
    client = get_model_client()
    if client is None:
        await initialize_model_client()
        client = get_model_client()
    
    if not client or not client.enabled:
        raise ModelServerUnavailable("Model server is not enabled")
    
    embeddings = await client.generate_embeddings(texts)
    if embeddings:
        return [np.array(e) for e in embeddings]
    
    raise ModelServerUnavailable("Failed to generate embeddings from model server")


def cleanup_executor() -> None:
    """Clean up resources on shutdown (no-op, kept for compatibility)."""
    logger.info("Embedding service cleanup complete")


def get_model_status() -> dict:
    """Get the status of the embedding service."""
    client = get_model_client()
    
    return {
        "using_model_server": True,
        "model_server_enabled": client.enabled if client else False,
        "model_server_healthy": client._healthy if client else False,
        "model_name": "all-MiniLM-L6-v2"
    }


async def reset_to_model_server() -> bool:
    """
    Check if model server is available.
    
    Returns:
        True if model server is available
    """
    try:
        client = get_model_client()
        if client and client.enabled and await client.is_ready():
            logger.info("Model server is available")
            return True
    except Exception as e:
        logger.warning(f"Model server not available: {e}")
    
    return False
