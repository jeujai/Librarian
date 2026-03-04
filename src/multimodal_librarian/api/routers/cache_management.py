"""
Cache Management API Router

This module provides REST API endpoints for cache management, monitoring,
and optimization operations.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, status, Query
from fastapi.responses import JSONResponse

from ...services.cache_service import get_cache_service_sync, CacheService, CacheType
from ..dependencies import get_cached_ai_service_di, get_cached_rag_service
from ...services.conversation_cache_service import get_conversation_cache_service

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/cache", tags=["cache"])

async def get_cache_service() -> CacheService:
    """Dependency to get cache service."""
    return get_cache_service_sync()

@router.get("/health")
async def cache_health_check(
    cache_service: CacheService = Depends(get_cache_service),
    ai_service = Depends(get_cached_ai_service_di),
    rag_service = Depends(get_cached_rag_service)
):
    """
    Get cache service health status.
    
    Returns comprehensive health information for all caching components.
    """
    try:
        # Get health from all cache-related services
        cache_health = await cache_service.health_check()
        
        ai_status = await ai_service.get_enhanced_status()
        
        rag_status = {}
        if rag_service is not None:
            rag_status = await rag_service.get_enhanced_service_status()
        
        conversation_service = get_conversation_cache_service()
        conversation_health = await conversation_service.health_check()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "healthy" if cache_health["status"] == "healthy" else "degraded",
                "timestamp": datetime.utcnow().isoformat(),
                "components": {
                    "cache_service": cache_health,
                    "ai_service_cache": ai_status.get("cache_statistics", {}),
                    "rag_service_cache": rag_status.get("rag_cache_statistics", {}) if rag_status else {},
                    "conversation_cache": conversation_health
                },
                "overall_performance": {
                    "redis_connected": cache_health.get("connected", False),
                    "memory_usage_mb": cache_health.get("memory_usage_mb", 0),
                    "total_entries": cache_health.get("total_entries", 0),
                    "hit_rate": cache_health.get("hit_rate", 0.0)
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Cache health check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )

@router.get("/stats")
async def get_cache_statistics(
    cache_service: CacheService = Depends(get_cache_service),
    ai_service = Depends(get_cached_ai_service_di),
    rag_service = Depends(get_cached_rag_service)
):
    """
    Get comprehensive cache statistics.
    
    Returns detailed statistics for all cache types and performance metrics.
    """
    try:
        # Get stats from cache service
        cache_stats = await cache_service.get_stats()
        
        # Get stats from AI service
        ai_cache_stats = ai_service.get_cache_stats()
        
        # Get stats from RAG service
        rag_cache_stats = {}
        if rag_service is not None:
            rag_cache_stats = rag_service.get_cache_stats()
        
        # Get stats from conversation service
        conversation_service = get_conversation_cache_service()
        conversation_stats = conversation_service.get_cache_stats()
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "timestamp": datetime.utcnow().isoformat(),
                "cache_service": {
                    "total_entries": cache_stats.total_entries,
                    "total_size_bytes": cache_stats.total_size_bytes,
                    "memory_usage_mb": cache_stats.memory_usage_mb,
                    "hit_rate": cache_stats.hit_rate,
                    "miss_rate": cache_stats.miss_rate,
                    "avg_access_time_ms": cache_stats.avg_access_time_ms,
                    "entries_by_type": cache_stats.entries_by_type
                },
                "ai_service_cache": ai_cache_stats,
                "rag_service_cache": rag_cache_stats,
                "conversation_cache": conversation_stats,
                "performance_summary": {
                    "total_cache_entries": cache_stats.total_entries,
                    "overall_hit_rate": cache_stats.hit_rate,
                    "memory_efficiency": round(
                        cache_stats.total_entries / max(1, cache_stats.memory_usage_mb), 2
                    ),
                    "response_time_ms": cache_stats.avg_access_time_ms
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to get cache statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve cache statistics"
        )

@router.post("/clear")
async def clear_cache(
    cache_type: Optional[str] = Query(None, description="Type of cache to clear (embedding, search_result, conversation, ai_response, database_query, analytics, knowledge_graph, or 'all')"),
    cache_service: CacheService = Depends(get_cache_service)
):
    """
    Clear cache entries by type or all entries.
    
    - **cache_type**: Specific cache type to clear, or 'all' for everything
    """
    try:
        if cache_type == "all" or cache_type is None:
            # Clear all cache
            success = await cache_service.clear_all()
            if success:
                return JSONResponse(
                    status_code=status.HTTP_200_OK,
                    content={
                        "success": True,
                        "message": "All cache entries cleared successfully",
                        "timestamp": datetime.utcnow().isoformat()
                    }
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to clear all cache entries"
                )
        
        # Clear specific cache type
        try:
            cache_type_enum = CacheType(cache_type)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid cache type: {cache_type}. Valid types: {[ct.value for ct in CacheType]}"
            )
        
        cleared_count = await cache_service.clear_by_type(cache_type_enum)
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "message": f"Cleared {cleared_count} entries of type {cache_type}",
                "cache_type": cache_type,
                "entries_cleared": cleared_count,
                "timestamp": datetime.utcnow().isoformat()
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cache clearing failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear cache: {str(e)}"
        )

@router.post("/warm")
async def warm_cache(
    cache_types: List[str] = Query(["embedding", "ai_response"], description="Types of cache to warm"),
    cache_service: CacheService = Depends(get_cache_service),
    ai_service = Depends(get_cached_ai_service_di),
    rag_service = Depends(get_cached_rag_service)
):
    """
    Warm cache with common data.
    
    Pre-loads frequently used data into cache for improved performance.
    
    - **cache_types**: List of cache types to warm
    """
    try:
        results = {
            "success": True,
            "timestamp": datetime.utcnow().isoformat(),
            "warming_results": {}
        }
        
        # Warm AI service cache
        if "embedding" in cache_types or "ai_response" in cache_types:
            # Common texts for embedding cache warming
            common_texts = [
                "What is this document about?",
                "Can you summarize this content?",
                "What are the main topics discussed?",
                "How does this relate to my other documents?",
                "What are the key insights from this text?",
                "Explain this concept in simple terms",
                "What questions does this document answer?",
                "What are the important details here?"
            ]
            
            if "embedding" in cache_types:
                embedding_results = await ai_service.warm_embedding_cache(common_texts)
                results["warming_results"]["embeddings"] = embedding_results
        
        # Warm RAG service cache
        if "search_result" in cache_types or "knowledge_graph" in cache_types:
            if rag_service is not None:
                # Common queries for RAG cache warming
                common_queries = [
                    "What is the main topic of my documents?",
                    "Summarize the key points",
                    "What are the most important insights?",
                    "How are these concepts related?",
                    "What questions can you answer from my documents?"
                ]
                
                rag_results = await rag_service.warm_cache(common_queries)
                results["warming_results"]["rag"] = rag_results
            else:
                results["warming_results"]["rag"] = {"status": "skipped", "reason": "RAG service unavailable"}
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=results
        )
        
    except Exception as e:
        logger.error(f"Cache warming failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to warm cache: {str(e)}"
        )

@router.get("/performance")
async def get_cache_performance_metrics(
    cache_service: CacheService = Depends(get_cache_service),
    ai_service = Depends(get_cached_ai_service_di),
    rag_service = Depends(get_cached_rag_service)
):
    """
    Get detailed cache performance metrics and optimization recommendations.
    
    Returns performance analysis and suggestions for cache optimization.
    """
    try:
        # Get current statistics
        cache_stats = await cache_service.get_stats()
        
        # Get service-specific stats
        ai_stats = ai_service.get_cache_stats()
        
        rag_stats = {}
        if rag_service is not None:
            rag_stats = rag_service.get_cache_stats()
        
        conversation_service = get_conversation_cache_service()
        conv_stats = conversation_service.get_cache_stats()
        
        # Calculate performance metrics
        overall_hit_rate = cache_stats.hit_rate
        memory_efficiency = cache_stats.total_entries / max(1, cache_stats.memory_usage_mb)
        response_time = cache_stats.avg_access_time_ms
        
        # Generate recommendations
        recommendations = []
        
        if overall_hit_rate < 0.5:
            recommendations.append({
                "type": "hit_rate",
                "severity": "high",
                "message": "Low cache hit rate detected",
                "suggestion": "Consider increasing cache TTL or warming cache with common queries",
                "current_value": overall_hit_rate,
                "target_value": 0.7
            })
        
        if response_time > 10:
            recommendations.append({
                "type": "response_time",
                "severity": "medium",
                "message": "High cache response time",
                "suggestion": "Check Redis connection and consider optimizing cache keys",
                "current_value": response_time,
                "target_value": 5.0
            })
        
        if cache_stats.memory_usage_mb > 400:
            recommendations.append({
                "type": "memory_usage",
                "severity": "medium",
                "message": "High memory usage",
                "suggestion": "Consider reducing TTL or implementing more aggressive eviction",
                "current_value": cache_stats.memory_usage_mb,
                "target_value": 300
            })
        
        # Calculate cost savings estimate
        total_cache_hits = (
            ai_stats["performance"]["total_cache_hits"] +
            (rag_stats.get("overall_performance", {}).get("total_hits", 0) if rag_stats else 0) +
            conv_stats["performance"]["total_hits"]
        )
        
        # Rough estimate: each cache hit saves ~$0.001 in API costs
        estimated_cost_savings = total_cache_hits * 0.001
        
        # Build service performance section
        service_performance = {
            "ai_service": {
                "embedding_hit_rate": ai_stats["embedding_cache"]["hit_rate"],
                "response_hit_rate": ai_stats["response_cache"]["hit_rate"],
                "total_requests": ai_stats["performance"]["total_requests"]
            },
            "conversation_service": {
                "summary_hit_rate": conv_stats["summary_cache"]["hit_rate"],
                "context_hit_rate": conv_stats["context_cache"]["hit_rate"],
                "overall_hit_rate": conv_stats["performance"]["overall_hit_rate"]
            }
        }
        
        if rag_stats:
            service_performance["rag_service"] = {
                "search_hit_rate": rag_stats.get("search_cache", {}).get("hit_rate", 0),
                "response_hit_rate": rag_stats.get("response_cache", {}).get("hit_rate", 0),
                "overall_hit_rate": rag_stats.get("overall_performance", {}).get("overall_hit_rate", 0)
            }
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "timestamp": datetime.utcnow().isoformat(),
                "performance_metrics": {
                    "overall_hit_rate": overall_hit_rate,
                    "memory_efficiency_entries_per_mb": round(memory_efficiency, 2),
                    "avg_response_time_ms": response_time,
                    "total_entries": cache_stats.total_entries,
                    "memory_usage_mb": cache_stats.memory_usage_mb
                },
                "service_performance": service_performance,
                "cost_optimization": {
                    "total_cache_hits": total_cache_hits,
                    "estimated_cost_savings_usd": round(estimated_cost_savings, 2),
                    "api_calls_avoided": total_cache_hits
                },
                "recommendations": recommendations,
                "health_score": _calculate_health_score(
                    overall_hit_rate, response_time, cache_stats.memory_usage_mb
                )
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to get performance metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve performance metrics"
        )

def _calculate_health_score(hit_rate: float, response_time: float, memory_usage: float) -> Dict[str, Any]:
    """Calculate overall cache health score."""
    score = 100
    
    # Hit rate scoring (40% weight)
    if hit_rate >= 0.8:
        hit_rate_score = 40
    elif hit_rate >= 0.6:
        hit_rate_score = 30
    elif hit_rate >= 0.4:
        hit_rate_score = 20
    else:
        hit_rate_score = 10
    
    # Response time scoring (30% weight)
    if response_time <= 2:
        response_time_score = 30
    elif response_time <= 5:
        response_time_score = 25
    elif response_time <= 10:
        response_time_score = 15
    else:
        response_time_score = 5
    
    # Memory usage scoring (30% weight)
    if memory_usage <= 200:
        memory_score = 30
    elif memory_usage <= 300:
        memory_score = 25
    elif memory_usage <= 400:
        memory_score = 15
    else:
        memory_score = 5
    
    total_score = hit_rate_score + response_time_score + memory_score
    
    if total_score >= 90:
        health_status = "excellent"
    elif total_score >= 75:
        health_status = "good"
    elif total_score >= 60:
        health_status = "fair"
    else:
        health_status = "poor"
    
    return {
        "score": total_score,
        "status": health_status,
        "components": {
            "hit_rate_score": hit_rate_score,
            "response_time_score": response_time_score,
            "memory_score": memory_score
        }
    }

@router.post("/optimize")
async def optimize_cache_performance(
    cache_service: CacheService = Depends(get_cache_service),
    ai_service = Depends(get_cached_ai_service_di)
):
    """
    Perform cache optimization operations.
    
    Analyzes current performance and applies optimization strategies.
    """
    try:
        optimization_results = {
            "success": True,
            "timestamp": datetime.utcnow().isoformat(),
            "optimizations_applied": []
        }
        
        # Get current stats
        cache_stats = await cache_service.get_stats()
        
        # Optimization 1: Clear expired entries (Redis handles this automatically)
        # But we can provide recommendations
        
        # Optimization 2: Warm cache with common queries if hit rate is low
        if cache_stats.hit_rate < 0.5:
            try:
                # Warm AI cache
                common_texts = [
                    "What is this about?",
                    "Summarize this content",
                    "What are the main points?"
                ]
                
                warming_result = await ai_service.warm_embedding_cache(common_texts)
                optimization_results["optimizations_applied"].append({
                    "type": "cache_warming",
                    "description": "Warmed embedding cache with common queries",
                    "result": warming_result
                })
                
            except Exception as e:
                logger.warning(f"Cache warming optimization failed: {e}")
        
        # Optimization 3: Memory usage recommendations
        if cache_stats.memory_usage_mb > 400:
            optimization_results["optimizations_applied"].append({
                "type": "memory_recommendation",
                "description": "High memory usage detected",
                "recommendation": "Consider reducing TTL values or implementing more aggressive eviction policies",
                "current_memory_mb": cache_stats.memory_usage_mb,
                "target_memory_mb": 300
            })
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=optimization_results
        )
        
    except Exception as e:
        logger.error(f"Cache optimization failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to optimize cache: {str(e)}"
        )

@router.get("/config")
async def get_cache_configuration(
    cache_service: CacheService = Depends(get_cache_service)
):
    """
    Get current cache configuration settings.
    
    Returns all cache configuration parameters and feature flags.
    """
    try:
        config = cache_service.config
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "timestamp": datetime.utcnow().isoformat(),
                "redis_config": {
                    "host": config.redis_host,
                    "port": config.redis_port,
                    "db": config.redis_db,
                    "ssl_enabled": config.redis_ssl
                },
                "ttl_settings": {
                    "embedding_ttl_seconds": config.embedding_ttl,
                    "search_result_ttl_seconds": config.search_result_ttl,
                    "conversation_ttl_seconds": config.conversation_ttl,
                    "ai_response_ttl_seconds": config.ai_response_ttl,
                    "database_query_ttl_seconds": config.database_query_ttl,
                    "analytics_ttl_seconds": config.analytics_ttl,
                    "knowledge_graph_ttl_seconds": config.knowledge_graph_ttl
                },
                "performance_settings": {
                    "max_memory_mb": config.max_memory_mb,
                    "max_entries_per_type": config.max_entries_per_type,
                    "compression_enabled": config.compression_enabled,
                    "compression_threshold_bytes": config.compression_threshold,
                    "batch_size": config.batch_size
                },
                "feature_flags": {
                    "embedding_cache_enabled": config.enable_embedding_cache,
                    "search_cache_enabled": config.enable_search_cache,
                    "conversation_cache_enabled": config.enable_conversation_cache,
                    "ai_response_cache_enabled": config.enable_ai_response_cache,
                    "database_cache_enabled": config.enable_database_cache,
                    "analytics_cache_enabled": config.enable_analytics_cache,
                    "knowledge_graph_cache_enabled": config.enable_knowledge_graph_cache
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to get cache configuration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve cache configuration"
        )