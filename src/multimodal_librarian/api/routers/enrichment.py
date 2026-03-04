"""
Enrichment Management API Router

This module provides REST API endpoints for managing the Knowledge Graph
External Enrichment feature, including cache statistics, circuit breaker
status, and document lookup by YAGO entity.

Requirements: 6.4, 5.3
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ...services.circuit_breaker import get_circuit_breaker_registry
from ...services.enrichment_cache import EnrichmentCache
from ..dependencies import (
    get_enrichment_cache_optional,
    get_enrichment_service_optional,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/enrichment", tags=["enrichment"])


# =============================================================================
# Response Models
# =============================================================================

class CacheStatsResponse(BaseModel):
    """Response model for cache statistics."""
    success: bool
    timestamp: str
    yago_size: int = Field(description="Number of YAGO entries in cache")
    conceptnet_size: int = Field(description="Number of ConceptNet entries in cache")
    total_size: int = Field(description="Total cache entries")
    yago_hits: int = Field(description="Total YAGO cache hits")
    yago_misses: int = Field(description="Total YAGO cache misses")
    yago_hit_rate: float = Field(description="YAGO cache hit rate (0-1)")
    conceptnet_hits: int = Field(description="Total ConceptNet cache hits")
    conceptnet_misses: int = Field(description="Total ConceptNet cache misses")
    conceptnet_hit_rate: float = Field(description="ConceptNet cache hit rate (0-1)")
    evictions: int = Field(description="Total LRU evictions")


class CacheClearResponse(BaseModel):
    """Response model for cache clear operation."""
    success: bool
    message: str
    timestamp: str


class CircuitBreakerStatusResponse(BaseModel):
    """Response model for circuit breaker status."""
    success: bool
    timestamp: str
    yago: dict = Field(description="YAGO circuit breaker status")
    conceptnet: dict = Field(description="ConceptNet circuit breaker status")


class DocumentLookupResponse(BaseModel):
    """Response model for document lookup by entity."""
    success: bool
    timestamp: str
    q_number: str = Field(description="YAGO Q-number queried")
    document_ids: List[str] = Field(description="List of document IDs containing this entity")
    document_count: int = Field(description="Number of documents found")


# =============================================================================
# Cache Management Endpoints
# =============================================================================

@router.get("/cache/stats", response_model=CacheStatsResponse)
async def get_cache_stats(
    cache: Optional[EnrichmentCache] = Depends(get_enrichment_cache_optional)
):
    """
    Get enrichment cache statistics.
    
    Returns detailed statistics about the YAGO and ConceptNet caches,
    including size, hit rates, and eviction counts.
    
    Requirements: 6.4
    """
    if cache is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Enrichment cache service unavailable"
        )
    
    try:
        stats = cache.get_stats()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "timestamp": datetime.utcnow().isoformat(),
                "yago_size": stats.yago_size,
                "conceptnet_size": stats.conceptnet_size,
                "total_size": stats.total_size,
                "yago_hits": stats.yago_hits,
                "yago_misses": stats.yago_misses,
                "yago_hit_rate": round(stats.yago_hit_rate, 4),
                "conceptnet_hits": stats.conceptnet_hits,
                "conceptnet_misses": stats.conceptnet_misses,
                "conceptnet_hit_rate": round(stats.conceptnet_hit_rate, 4),
                "evictions": stats.evictions
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to get enrichment cache stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve cache statistics: {str(e)}"
        )


@router.post("/cache/clear", response_model=CacheClearResponse)
async def clear_cache(
    cache: Optional[EnrichmentCache] = Depends(get_enrichment_cache_optional)
):
    """
    Clear the enrichment cache.
    
    Clears all cached YAGO and ConceptNet data and resets statistics.
    Use with caution as this will cause increased API calls until the cache
    is repopulated.
    
    Requirements: 6.4
    """
    if cache is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Enrichment cache service unavailable"
        )
    
    try:
        # Get stats before clearing for logging
        stats_before = cache.get_stats()
        entries_cleared = stats_before.total_size
        
        cache.clear()
        
        logger.info(
            f"Enrichment cache cleared: {entries_cleared} entries removed "
            f"(YAGO: {stats_before.yago_size}, "
            f"ConceptNet: {stats_before.conceptnet_size})"
        )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "message": f"Cache cleared successfully. {entries_cleared} entries removed.",
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to clear enrichment cache: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear cache: {str(e)}"
        )


# =============================================================================
# Circuit Breaker Endpoints
# =============================================================================

@router.get("/circuit-breaker/status", response_model=CircuitBreakerStatusResponse)
async def get_circuit_breaker_status():
    """
    Get circuit breaker status for external APIs.
    
    Returns the current state of circuit breakers for YAGO and ConceptNet
    APIs, including failure counts and recovery times.
    
    Requirements: 7.3
    """
    try:
        registry = get_circuit_breaker_registry()
        all_stats = registry.get_all_stats()
        
        # Get YAGO circuit breaker status
        yago_stats = all_stats.get("yago")
        yago_breaker = registry.get("yago")
        yago_status = {
            "state": yago_stats.state.value if yago_stats else "closed",
            "failures": yago_stats.failures if yago_stats else 0,
            "successes": yago_stats.successes if yago_stats else 0,
            "last_failure_time": yago_stats.last_failure_time if yago_stats else None,
            "last_state_change": yago_stats.last_state_change if yago_stats else None,
            "recovery_time": None
        }
        
        # Add recovery time if circuit is open
        if yago_breaker:
            recovery_time = yago_breaker.get_recovery_time()
            if recovery_time:
                yago_status["recovery_time"] = recovery_time.isoformat()
        
        # Get ConceptNet circuit breaker status
        conceptnet_stats = all_stats.get("conceptnet")
        conceptnet_breaker = registry.get("conceptnet")
        conceptnet_status = {
            "state": conceptnet_stats.state.value if conceptnet_stats else "closed",
            "failures": conceptnet_stats.failures if conceptnet_stats else 0,
            "successes": conceptnet_stats.successes if conceptnet_stats else 0,
            "last_failure_time": conceptnet_stats.last_failure_time if conceptnet_stats else None,
            "last_state_change": conceptnet_stats.last_state_change if conceptnet_stats else None,
            "recovery_time": None
        }
        
        # Add recovery time if circuit is open
        if conceptnet_breaker:
            recovery_time = conceptnet_breaker.get_recovery_time()
            if recovery_time:
                conceptnet_status["recovery_time"] = recovery_time.isoformat()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "timestamp": datetime.utcnow().isoformat(),
                "yago": yago_status,
                "conceptnet": conceptnet_status
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to get circuit breaker status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve circuit breaker status: {str(e)}"
        )


# =============================================================================
# Document Lookup Endpoints
# =============================================================================

@router.get("/documents/{q_number}", response_model=DocumentLookupResponse)
async def get_documents_by_entity(
    q_number: str,
    enrichment_service = Depends(get_enrichment_service_optional)
):
    """
    Find all documents containing concepts linked to a YAGO entity.
    
    Given a YAGO Q-number (e.g., "Q42" for Douglas Adams), returns all
    document IDs that contain concepts enriched with this entity.
    
    Args:
        q_number: YAGO Q-number (e.g., "Q42", "Q5", "Q515")
    
    Requirements: 5.3
    """
    # Validate Q-number format
    if not q_number.startswith("Q") or not q_number[1:].isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid Q-number format: {q_number}. Expected format: Q followed by digits (e.g., Q42)"
        )
    
    if enrichment_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Enrichment service unavailable"
        )
    
    try:
        document_ids = await enrichment_service.find_documents_by_entity(q_number)
        
        logger.info(
            f"Document lookup for {q_number}: found {len(document_ids)} documents"
        )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "timestamp": datetime.utcnow().isoformat(),
                "q_number": q_number,
                "document_ids": document_ids,
                "document_count": len(document_ids)
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to lookup documents for entity {q_number}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to lookup documents: {str(e)}"
        )
