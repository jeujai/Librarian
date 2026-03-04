"""
Multi-Level Cache API Router

This module provides REST API endpoints for managing and monitoring
the multi-level caching system including L1, L2, L3 caches, session
caching, and cache warming strategies.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Body, Depends
from pydantic import BaseModel, Field

from ...services.multi_level_cache_manager import get_multi_level_cache_manager
from ...services.session_cache_service import get_session_cache_service
from ...services.cache_warming_service import get_cache_warming_service, WarmingStrategy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cache", tags=["Multi-Level Cache"])


# Pydantic models for request/response
class CacheGetRequest(BaseModel):
    """Request model for cache get operation."""
    key: str = Field(..., description="Cache key to retrieve")


class CacheSetRequest(BaseModel):
    """Request model for cache set operation."""
    key: str = Field(..., description="Cache key to set")
    value: Any = Field(..., description="Value to cache")
    ttl: Optional[int] = Field(None, description="Time to live in seconds")


class CacheDeleteRequest(BaseModel):
    """Request model for cache delete operation."""
    key: str = Field(..., description="Cache key to delete")


class SessionCacheRequest(BaseModel):
    """Request model for session cache operations."""
    session_id: str = Field(..., description="Session identifier")
    key: str = Field(..., description="Cache key")
    value: Optional[Any] = Field(None, description="Value to cache (for set operations)")
    ttl: Optional[int] = Field(None, description="Time to live in seconds")


class CreateSessionRequest(BaseModel):
    """Request model for creating a new session."""
    user_id: Optional[str] = Field(None, description="User identifier")
    ip_address: Optional[str] = Field(None, description="Client IP address")
    user_agent: Optional[str] = Field(None, description="Client user agent")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional session metadata")


class WarmingPatternRequest(BaseModel):
    """Request model for cache warming pattern operations."""
    name: str = Field(..., description="Pattern name")
    strategy: WarmingStrategy = Field(..., description="Warming strategy")
    interval_minutes: int = Field(60, description="Interval between runs in minutes")
    max_queries: int = Field(100, description="Maximum queries per run")
    priority: int = Field(2, description="Pattern priority (1=high, 2=medium, 3=low)")
    enabled: bool = Field(True, description="Whether pattern is enabled")


class WarmQueriesRequest(BaseModel):
    """Request model for warming specific queries."""
    queries: List[str] = Field(..., description="List of queries to warm")


# Multi-Level Cache Management Endpoints

@router.get("/health")
async def get_cache_health():
    """Get comprehensive health status of all cache levels."""
    try:
        cache_manager = await get_multi_level_cache_manager()
        session_cache = await get_session_cache_service()
        warming_service = await get_cache_warming_service()
        
        health = {
            "multi_level_cache": await cache_manager.health_check(),
            "session_cache": await session_cache.health_check(),
            "cache_warming": await warming_service.health_check(),
            "timestamp": datetime.now().isoformat()
        }
        
        # Determine overall status
        statuses = [
            health["multi_level_cache"]["status"],
            health["session_cache"]["status"],
            health["cache_warming"]["status"]
        ]
        
        if "unhealthy" in statuses:
            overall_status = "unhealthy"
        elif "degraded" in statuses:
            overall_status = "degraded"
        elif "warning" in statuses:
            overall_status = "warning"
        else:
            overall_status = "healthy"
        
        health["overall_status"] = overall_status
        return health
        
    except Exception as e:
        logger.error(f"Cache health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get("/stats")
async def get_cache_stats():
    """Get comprehensive statistics for all cache levels."""
    try:
        cache_manager = await get_multi_level_cache_manager()
        session_cache = await get_session_cache_service()
        warming_service = await get_cache_warming_service()
        
        return {
            "multi_level_cache": await cache_manager.get_comprehensive_stats(),
            "session_cache": session_cache.get_comprehensive_stats(),
            "cache_warming": warming_service.get_all_patterns_stats(),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get cache stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.get("/get/{key}")
async def get_cache_value(key: str):
    """Get value from multi-level cache."""
    try:
        cache_manager = await get_multi_level_cache_manager()
        value = await cache_manager.get(key)
        
        return {
            "key": key,
            "value": value,
            "found": value is not None,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cache get failed for key {key}: {e}")
        raise HTTPException(status_code=500, detail=f"Cache get failed: {str(e)}")


@router.post("/set")
async def set_cache_value(request: CacheSetRequest):
    """Set value in multi-level cache."""
    try:
        cache_manager = await get_multi_level_cache_manager()
        success = await cache_manager.set(request.key, request.value, request.ttl)
        
        return {
            "key": request.key,
            "success": success,
            "ttl": request.ttl,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cache set failed for key {request.key}: {e}")
        raise HTTPException(status_code=500, detail=f"Cache set failed: {str(e)}")


@router.delete("/delete/{key}")
async def delete_cache_value(key: str):
    """Delete value from multi-level cache."""
    try:
        cache_manager = await get_multi_level_cache_manager()
        success = await cache_manager.delete(key)
        
        return {
            "key": key,
            "deleted": success,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cache delete failed for key {key}: {e}")
        raise HTTPException(status_code=500, detail=f"Cache delete failed: {str(e)}")


@router.delete("/clear")
async def clear_all_cache():
    """Clear all cache levels."""
    try:
        cache_manager = await get_multi_level_cache_manager()
        results = await cache_manager.clear_all()
        
        return {
            "cleared": results,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cache clear all failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cache clear failed: {str(e)}")


@router.post("/cleanup")
async def cleanup_expired_cache():
    """Clean up expired cache entries."""
    try:
        cache_manager = await get_multi_level_cache_manager()
        results = await cache_manager.cleanup_expired()
        
        return {
            "cleanup_results": results,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Cache cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cache cleanup failed: {str(e)}")


# Session Cache Endpoints

@router.post("/session/create")
async def create_session(request: CreateSessionRequest):
    """Create a new cache session."""
    try:
        session_cache = await get_session_cache_service()
        session_id = session_cache.create_session(
            user_id=request.user_id,
            ip_address=request.ip_address,
            user_agent=request.user_agent,
            metadata=request.metadata
        )
        
        return {
            "session_id": session_id,
            "created_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Session creation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Session creation failed: {str(e)}")


@router.get("/session/{session_id}")
async def get_session_info(session_id: str):
    """Get session information."""
    try:
        session_cache = await get_session_cache_service()
        session_info = session_cache.get_session(session_id)
        
        if not session_info:
            raise HTTPException(status_code=404, detail="Session not found or expired")
        
        return {
            "session_id": session_info.session_id,
            "user_id": session_info.user_id,
            "created_at": session_info.created_at.isoformat(),
            "last_activity": session_info.last_activity.isoformat(),
            "ip_address": session_info.ip_address,
            "user_agent": session_info.user_agent,
            "cache_entries": len(session_info.cache_keys),
            "metadata": session_info.metadata
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session info: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get session info: {str(e)}")


@router.get("/session/{session_id}/get/{key}")
async def get_session_cache_value(session_id: str, key: str):
    """Get value from session cache."""
    try:
        session_cache = await get_session_cache_service()
        value = await session_cache.get(session_id, key)
        
        return {
            "session_id": session_id,
            "key": key,
            "value": value,
            "found": value is not None,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Session cache get failed: {e}")
        raise HTTPException(status_code=500, detail=f"Session cache get failed: {str(e)}")


@router.post("/session/set")
async def set_session_cache_value(request: SessionCacheRequest):
    """Set value in session cache."""
    try:
        session_cache = await get_session_cache_service()
        success = await session_cache.set(
            request.session_id, 
            request.key, 
            request.value, 
            request.ttl
        )
        
        return {
            "session_id": request.session_id,
            "key": request.key,
            "success": success,
            "ttl": request.ttl,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Session cache set failed: {e}")
        raise HTTPException(status_code=500, detail=f"Session cache set failed: {str(e)}")


@router.delete("/session/{session_id}/delete/{key}")
async def delete_session_cache_value(session_id: str, key: str):
    """Delete value from session cache."""
    try:
        session_cache = await get_session_cache_service()
        success = await session_cache.delete(session_id, key)
        
        return {
            "session_id": session_id,
            "key": key,
            "deleted": success,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Session cache delete failed: {e}")
        raise HTTPException(status_code=500, detail=f"Session cache delete failed: {str(e)}")


@router.delete("/session/{session_id}/clear")
async def clear_session_cache(session_id: str):
    """Clear all cache entries for a session."""
    try:
        session_cache = await get_session_cache_service()
        cleared_count = await session_cache.clear_session(session_id)
        
        return {
            "session_id": session_id,
            "cleared_entries": cleared_count,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Session cache clear failed: {e}")
        raise HTTPException(status_code=500, detail=f"Session cache clear failed: {str(e)}")


@router.delete("/session/{session_id}")
async def destroy_session(session_id: str):
    """Destroy a session and clear all its cache entries."""
    try:
        session_cache = await get_session_cache_service()
        success = await session_cache.destroy_session(session_id)
        
        return {
            "session_id": session_id,
            "destroyed": success,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Session destruction failed: {e}")
        raise HTTPException(status_code=500, detail=f"Session destruction failed: {str(e)}")


@router.get("/sessions")
async def get_active_sessions():
    """Get list of active sessions."""
    try:
        session_cache = await get_session_cache_service()
        active_sessions = session_cache.get_active_sessions()
        session_counts = session_cache.get_session_count()
        
        return {
            "active_sessions": active_sessions,
            "session_counts": session_counts,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get active sessions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get sessions: {str(e)}")


@router.post("/sessions/cleanup")
async def cleanup_expired_sessions():
    """Clean up expired sessions."""
    try:
        session_cache = await get_session_cache_service()
        results = await session_cache.cleanup_expired_sessions()
        
        return {
            "cleanup_results": results,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Session cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Session cleanup failed: {str(e)}")


# Cache Warming Endpoints

@router.get("/warming/status")
async def get_warming_status():
    """Get cache warming service status."""
    try:
        warming_service = await get_cache_warming_service()
        return await warming_service.health_check()
        
    except Exception as e:
        logger.error(f"Failed to get warming status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get warming status: {str(e)}")


@router.get("/warming/patterns")
async def get_warming_patterns():
    """Get all cache warming patterns and their statistics."""
    try:
        warming_service = await get_cache_warming_service()
        return warming_service.get_all_patterns_stats()
        
    except Exception as e:
        logger.error(f"Failed to get warming patterns: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get patterns: {str(e)}")


@router.get("/warming/patterns/{pattern_name}")
async def get_warming_pattern(pattern_name: str):
    """Get specific warming pattern statistics."""
    try:
        warming_service = await get_cache_warming_service()
        pattern_stats = warming_service.get_pattern_stats(pattern_name)
        
        if not pattern_stats:
            raise HTTPException(status_code=404, detail="Warming pattern not found")
        
        return pattern_stats
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get warming pattern: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get pattern: {str(e)}")


@router.post("/warming/start")
async def start_cache_warming():
    """Start the cache warming scheduler."""
    try:
        warming_service = await get_cache_warming_service()
        await warming_service.start_warming()
        
        return {
            "message": "Cache warming started",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to start cache warming: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start warming: {str(e)}")


@router.post("/warming/stop")
async def stop_cache_warming():
    """Stop the cache warming scheduler."""
    try:
        warming_service = await get_cache_warming_service()
        await warming_service.stop_warming()
        
        return {
            "message": "Cache warming stopped",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to stop cache warming: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop warming: {str(e)}")


@router.post("/warming/patterns/{pattern_name}/run")
async def run_warming_pattern(pattern_name: str):
    """Run a specific warming pattern immediately."""
    try:
        warming_service = await get_cache_warming_service()
        result = await warming_service.warm_pattern_now(pattern_name)
        
        return {
            "pattern_name": pattern_name,
            "result": {
                "queries_attempted": result.queries_attempted,
                "queries_successful": result.queries_successful,
                "queries_failed": result.queries_failed,
                "success_rate": result.success_rate,
                "duration_seconds": result.duration_seconds,
                "errors": result.errors
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to run warming pattern: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to run pattern: {str(e)}")


@router.post("/warming/patterns/{pattern_name}/enable")
async def enable_warming_pattern(pattern_name: str):
    """Enable a warming pattern."""
    try:
        warming_service = await get_cache_warming_service()
        success = warming_service.enable_pattern(pattern_name)
        
        if not success:
            raise HTTPException(status_code=404, detail="Warming pattern not found")
        
        return {
            "pattern_name": pattern_name,
            "enabled": True,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enable warming pattern: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to enable pattern: {str(e)}")


@router.post("/warming/patterns/{pattern_name}/disable")
async def disable_warming_pattern(pattern_name: str):
    """Disable a warming pattern."""
    try:
        warming_service = await get_cache_warming_service()
        success = warming_service.disable_pattern(pattern_name)
        
        if not success:
            raise HTTPException(status_code=404, detail="Warming pattern not found")
        
        return {
            "pattern_name": pattern_name,
            "enabled": False,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disable warming pattern: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to disable pattern: {str(e)}")


@router.post("/warming/queries")
async def warm_specific_queries(request: WarmQueriesRequest):
    """Warm cache with specific queries."""
    try:
        warming_service = await get_cache_warming_service()
        result = await warming_service.warm_specific_queries(request.queries)
        
        return {
            "queries": request.queries,
            "result": {
                "queries_attempted": result.queries_attempted,
                "queries_successful": result.queries_successful,
                "queries_failed": result.queries_failed,
                "success_rate": result.success_rate,
                "duration_seconds": result.duration_seconds,
                "errors": result.errors
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to warm specific queries: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to warm queries: {str(e)}")


# Monitoring and Analytics Endpoints

@router.get("/analytics/performance")
async def get_cache_performance_analytics():
    """Get cache performance analytics."""
    try:
        cache_manager = await get_multi_level_cache_manager()
        session_cache = await get_session_cache_service()
        
        cache_stats = await cache_manager.get_comprehensive_stats()
        session_stats = session_cache.get_comprehensive_stats()
        
        return {
            "cache_performance": {
                "overall_hit_rate": cache_stats.get("overall", {}).get("hit_rate_percent", 0),
                "l1_hit_rate": cache_stats.get("l1_memory", {}).get("hit_rate_percent", 0),
                "l2_hit_rate": cache_stats.get("l2_redis", {}).get("hit_rate_percent", 0),
                "l3_hit_rate": cache_stats.get("l3_database", {}).get("hit_rate_percent", 0),
                "avg_access_time_ms": cache_stats.get("overall", {}).get("avg_access_time_ms", 0),
                "memory_usage_mb": cache_stats.get("l1_memory", {}).get("memory_mb", 0)
            },
            "session_performance": {
                "hit_rate": session_stats.get("cache", {}).get("hit_rate_percent", 0),
                "active_sessions": session_stats.get("sessions", {}).get("currently_active", 0),
                "total_cache_entries": session_stats.get("cache", {}).get("total_entries", 0)
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get performance analytics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get analytics: {str(e)}")


@router.get("/analytics/usage")
async def get_cache_usage_analytics():
    """Get cache usage analytics."""
    try:
        cache_manager = await get_multi_level_cache_manager()
        cache_stats = await cache_manager.get_comprehensive_stats()
        
        return {
            "cache_sizes": {
                "l1_entries": cache_stats.get("l1_memory", {}).get("size", 0),
                "l2_entries": cache_stats.get("l2_redis", {}).get("size", 0),
                "l3_entries": cache_stats.get("l3_database", {}).get("size", 0)
            },
            "operation_counts": {
                "total_hits": cache_stats.get("overall", {}).get("total_hits", 0),
                "total_misses": cache_stats.get("overall", {}).get("total_misses", 0),
                "total_sets": cache_stats.get("overall", {}).get("total_sets", 0),
                "total_deletes": cache_stats.get("overall", {}).get("total_deletes", 0)
            },
            "cache_distribution": {
                "l1_hit_percentage": cache_stats.get("l1_memory", {}).get("hit_rate_percent", 0),
                "l2_hit_percentage": cache_stats.get("l2_redis", {}).get("hit_rate_percent", 0),
                "l3_hit_percentage": cache_stats.get("l3_database", {}).get("hit_rate_percent", 0)
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get usage analytics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get analytics: {str(e)}")