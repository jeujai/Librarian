"""Health check API endpoints."""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Response

from ..models.embedding import get_embedding_model
from ..models.nlp import get_nlp_model

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Comprehensive health check with model status.
    
    Returns detailed information about all loaded models and their status.
    """
    embedding_model = get_embedding_model()
    nlp_model = get_nlp_model()
    
    models_status = {}
    all_ready = True
    
    # Check embedding model
    if embedding_model:
        models_status["embedding"] = embedding_model.get_status()
        if not embedding_model.is_loaded:
            all_ready = False
    else:
        models_status["embedding"] = {"status": "not_initialized"}
        all_ready = False
    
    # Check NLP model
    if nlp_model:
        models_status["nlp"] = nlp_model.get_status()
        if not nlp_model.is_loaded:
            all_ready = False
    else:
        models_status["nlp"] = {"status": "not_initialized"}
        all_ready = False
    
    return {
        "status": "healthy" if all_ready else "degraded",
        "ready": all_ready,
        "models": models_status
    }


@router.get("/health/ready")
async def readiness_check(response: Response) -> Dict[str, Any]:
    """
    Readiness probe for Kubernetes/Docker health checks.
    
    Returns 200 if all models are loaded and ready to serve requests.
    Returns 503 if models are still loading.
    """
    embedding_model = get_embedding_model()
    nlp_model = get_nlp_model()
    
    embedding_ready = embedding_model is not None and embedding_model.is_loaded
    nlp_ready = nlp_model is not None and nlp_model.is_loaded
    
    all_ready = embedding_ready and nlp_ready
    
    if not all_ready:
        response.status_code = 503
    
    return {
        "ready": all_ready,
        "embedding": embedding_ready,
        "nlp": nlp_ready
    }


@router.get("/health/live")
async def liveness_check() -> Dict[str, str]:
    """
    Liveness probe for Kubernetes/Docker health checks.
    
    Always returns 200 if the server is running.
    This indicates the process is alive, not necessarily ready.
    """
    return {"status": "alive"}
