"""API routers for model server endpoints."""

from .embeddings import router as embeddings_router
from .health import router as health_router
from .nlp import router as nlp_router

__all__ = ["embeddings_router", "nlp_router", "health_router"]
