"""
Real Model Loader - Model Server Client Integration

This module provides model loading functionality via the model server.
All ML models (embeddings, NLP) are loaded from the dedicated model server
to minimize app container startup time and decouple the app from models.

Key Features:
- Model server client integration for embeddings and NLP
- Non-blocking async interface
- Graceful handling when model server is unavailable
- No local ML model loading (models are in model-server container)
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Cache for model status (not actual models - those are in model server)
_model_status: Dict[str, Dict[str, Any]] = {}


async def _check_model_server_ready() -> bool:
    """Check if model server is ready."""
    try:
        from ..clients.model_server_client import get_model_client
        client = get_model_client()
        if client is None:
            return False
        return await client.is_ready()
    except Exception as e:
        logger.debug(f"Model server not ready: {e}")
        return False


async def _load_embedding_model_async(model_name: str) -> Dict[str, Any]:
    """
    Check embedding model availability via model server.
    
    Models are loaded in the model-server container, not locally.
    This function verifies the model server is ready to serve embeddings.
    """
    logger.info(f"Checking embedding model availability: {model_name}")
    start_time = datetime.now()
    
    try:
        # Check if model server is ready
        is_ready = await _check_model_server_ready()
        
        load_time = (datetime.now() - start_time).total_seconds()
        
        if is_ready:
            logger.info(f"Embedding model {model_name} available via model server")
            result = {
                "name": model_name,
                "type": "embedding",
                "loaded_at": datetime.now().isoformat(),
                "load_time_seconds": load_time,
                "status": "loaded",
                "model_object": None,  # Model is in model-server
                "capabilities": ["text_embedding", "semantic_search"],
                "note": "Model served by model-server container",
            }
        else:
            logger.warning(f"Model server not ready for {model_name}")
            result = {
                "name": model_name,
                "type": "embedding",
                "loaded_at": datetime.now().isoformat(),
                "load_time_seconds": load_time,
                "status": "pending",
                "model_object": None,
                "capabilities": [],
                "note": "Waiting for model-server to be ready",
            }
        
        _model_status[model_name] = result
        return result
        
    except Exception as e:
        logger.error(f"Failed to check embedding model {model_name}: {e}")
        return {
            "name": model_name,
            "type": "embedding",
            "loaded_at": datetime.now().isoformat(),
            "status": "failed",
            "error": str(e),
            "capabilities": [],
        }


async def _load_chat_model_async(model_name: str) -> Dict[str, Any]:
    """
    Check chat model availability.
    
    Chat models use external APIs (OpenAI, Anthropic), not local loading.
    """
    logger.info(f"Checking chat model: {model_name}")
    start_time = datetime.now()
    
    try:
        load_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"Chat model {model_name} ready (uses external API)")
        
        result = {
            "name": model_name,
            "type": "chat",
            "loaded_at": datetime.now().isoformat(),
            "load_time_seconds": load_time,
            "status": "loaded",
            "model_object": None,  # Uses external API
            "capabilities": ["chat", "text_generation"],
            "note": "Uses external API (OpenAI/Anthropic) for inference",
        }
        
        _model_status[model_name] = result
        return result
        
    except Exception as e:
        logger.error(f"Failed to initialize chat model {model_name}: {e}")
        return {
            "name": model_name,
            "type": "chat",
            "loaded_at": datetime.now().isoformat(),
            "status": "failed",
            "error": str(e),
            "capabilities": [],
        }


async def _load_document_processor_async(model_name: str) -> Dict[str, Any]:
    """
    Check document processor availability via model server.
    
    NLP models (spacy) are loaded in the model-server container.
    This function verifies the model server is ready to serve NLP tasks.
    """
    logger.info(f"Checking document processor: {model_name}")
    start_time = datetime.now()
    
    try:
        # Check if model server is ready
        is_ready = await _check_model_server_ready()
        
        load_time = (datetime.now() - start_time).total_seconds()
        
        if is_ready:
            logger.info(f"Document processor {model_name} available via model server")
            result = {
                "name": model_name,
                "type": "document_processor",
                "loaded_at": datetime.now().isoformat(),
                "load_time_seconds": load_time,
                "status": "loaded",
                "model_object": None,  # Model is in model-server
                "capabilities": ["text_processing", "entity_extraction", "tokenization"],
                "note": "NLP served by model-server container",
            }
        else:
            logger.warning(f"Model server not ready for {model_name}")
            result = {
                "name": model_name,
                "type": "document_processor",
                "loaded_at": datetime.now().isoformat(),
                "load_time_seconds": load_time,
                "status": "pending",
                "model_object": None,
                "capabilities": [],
                "note": "Waiting for model-server to be ready",
            }
        
        _model_status[model_name] = result
        return result
        
    except Exception as e:
        logger.error(f"Failed to check document processor {model_name}: {e}")
        return {
            "name": model_name,
            "type": "document_processor",
            "loaded_at": datetime.now().isoformat(),
            "status": "failed",
            "error": str(e),
            "capabilities": [],
        }


async def load_model_async(model_name: str, model_type: str = "unknown") -> Dict[str, Any]:
    """
    Check model availability asynchronously.
    
    Models are served by the model-server container. This function
    verifies availability without loading models locally.
    
    Args:
        model_name: Name of the model to check
        model_type: Type of the model (embedding, chat, document_processor, etc.)
    
    Returns:
        Dict containing model information and status
    """
    try:
        # Route to appropriate checker
        if model_type == "embedding" or model_name in ["text-embedding-small", "search-index"]:
            return await _load_embedding_model_async(model_name)
        elif model_type == "chat" or "chat" in model_name.lower():
            return await _load_chat_model_async(model_name)
        elif model_type == "document_processor" or "document" in model_name.lower():
            return await _load_document_processor_async(model_name)
        else:
            # Default: mark as ready (placeholder for advanced models)
            logger.info(f"Model {model_name} ({model_type}) marked as ready (placeholder)")
            result = {
                "name": model_name,
                "type": model_type,
                "loaded_at": datetime.now().isoformat(),
                "status": "loaded",
                "model_object": None,
                "capabilities": [],
                "note": "Placeholder - model not required locally",
            }
            _model_status[model_name] = result
            return result
            
    except Exception as e:
        logger.error(f"Async model check failed for {model_name}: {e}")
        return {
            "name": model_name,
            "type": model_type,
            "loaded_at": datetime.now().isoformat(),
            "status": "failed",
            "error": str(e),
            "capabilities": [],
        }


def get_loaded_model(model_name: str) -> Optional[Any]:
    """
    Get model status by name.
    
    Note: Actual models are in model-server, this returns status info only.
    """
    status = _model_status.get(model_name)
    if status and status.get("status") == "loaded":
        return status
    return None


def is_model_loaded(model_name: str) -> bool:
    """Check if a model is available (via model server)."""
    status = _model_status.get(model_name)
    return status is not None and status.get("status") == "loaded"


def cleanup_models() -> None:
    """Clean up model status cache."""
    _model_status.clear()
    logger.info("Model loader cleaned up")
