"""Embedding API endpoints."""

import logging
import time
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..models.embedding import get_embedding_model

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/embeddings", tags=["embeddings"])


class EmbeddingRequest(BaseModel):
    """Request model for embedding generation."""
    
    texts: List[str] = Field(
        ...,
        description="List of texts to generate embeddings for",
        min_length=1,
        max_length=1000
    )
    model: Optional[str] = Field(
        default=None,
        description="Model to use (currently ignored, uses configured model)"
    )
    normalize: bool = Field(
        default=True,
        description="Whether to normalize embeddings"
    )


class EmbeddingResponse(BaseModel):
    """Response model for embedding generation."""
    
    embeddings: List[List[float]] = Field(
        ...,
        description="List of embedding vectors"
    )
    model: str = Field(
        ...,
        description="Model used for generation"
    )
    dimensions: int = Field(
        ...,
        description="Embedding dimensions"
    )
    count: int = Field(
        ...,
        description="Number of embeddings generated"
    )
    processing_time_ms: float = Field(
        ...,
        description="Processing time in milliseconds"
    )


@router.post("", response_model=EmbeddingResponse)
async def generate_embeddings(request: EmbeddingRequest) -> EmbeddingResponse:
    """
    Generate embeddings for a list of texts.
    
    This endpoint accepts a list of texts and returns their embedding vectors
    using the configured sentence-transformers model.
    """
    start_time = time.time()
    
    model = get_embedding_model()
    if model is None or not model.is_loaded:
        raise HTTPException(
            status_code=503,
            detail="Embedding model not loaded"
        )
    
    try:
        embeddings = model.encode(
            texts=request.texts,
            normalize=request.normalize
        )
        
        processing_time_ms = (time.time() - start_time) * 1000
        
        logger.info(
            f"Generated {len(embeddings)} embeddings in {processing_time_ms:.2f}ms"
        )
        
        return EmbeddingResponse(
            embeddings=embeddings,
            model=model.model_name,
            dimensions=model.dimensions,
            count=len(embeddings),
            processing_time_ms=processing_time_ms
        )
        
    except Exception as e:
        logger.error(f"Error generating embeddings: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating embeddings: {str(e)}"
        )


@router.get("/info")
async def get_embedding_info():
    """Get information about the embedding model."""
    model = get_embedding_model()
    if model is None:
        return {"status": "not_initialized"}
    
    return model.get_status()
