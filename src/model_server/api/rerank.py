"""Rerank API endpoint using cross-encoder model."""

import logging
import time
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..models.cross_encoder import get_cross_encoder_model

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/rerank", tags=["rerank"])


class RerankRequest(BaseModel):
    """Request model for reranking."""

    query: str = Field(
        ...,
        description="Query text for cross-attention scoring",
        min_length=1,
    )
    documents: List[str] = Field(
        default_factory=list,
        description="Document texts to score against the query",
        max_length=200,
    )


class RerankResponse(BaseModel):
    """Response model for reranking."""

    scores: List[float] = Field(
        ...,
        description=(
            "Sigmoid-normalized relevance scores [0, 1], "
            "same order as input documents"
        ),
    )
    model: str = Field(..., description="Cross-encoder model name used")
    count: int = Field(..., description="Number of scores returned")
    processing_time_ms: float = Field(
        ..., description="Processing time in milliseconds"
    )


@router.post("", response_model=RerankResponse)
async def rerank(request: RerankRequest) -> RerankResponse:
    """
    Score query-document pairs using the cross-encoder model.

    Returns a relevance score in [0, 1] for each document, in the same order
    as the input documents list.
    """
    start_time = time.time()

    model = get_cross_encoder_model()
    if model is None or not model.is_loaded:
        raise HTTPException(
            status_code=503,
            detail="Cross-encoder model not loaded",
        )

    try:
        scores = model.predict(
            query=request.query,
            documents=request.documents,
        )

        processing_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Reranked {len(scores)} documents "
            f"in {processing_time_ms:.2f}ms"
        )

        return RerankResponse(
            scores=scores,
            model=model.model_name,
            count=len(scores),
            processing_time_ms=processing_time_ms,
        )

    except Exception as e:
        logger.error(f"Error during reranking: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error during reranking: {str(e)}",
        )
