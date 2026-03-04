"""
API router for comprehensive metrics collection and reporting.

This module provides REST endpoints for accessing comprehensive system metrics
including response times, resource usage, user sessions, and performance analytics.
"""

from fastapi import APIRouter, HTTPException, Query, BackgroundTasks
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import asyncio

from ...monitoring.comprehensive_metrics_collector import ComprehensiveMetricsCollector
from ...logging_config import get_logger

# Global metrics collector instance
metrics_collector = ComprehensiveMetricsCollector()
logger = get_logger("comprehensive_metrics_api")

router = APIRouter(prefix="/api/metrics", tags=["comprehensive-metrics"])


@router.get("/real-time")
async def get_real_time_metrics() -> Dict[str, Any]:
    """
    Get real-time system metrics including response times, resource usage, and user activity.
    
    Returns comprehensive real-time metrics for system monitoring and alerting.
    """
    try:
        return metrics_collector.get_real_time_metrics()
    except Exception as e:
        logger.error(f"Error getting real-time metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get real-time metrics: {str(e)}")


@router.get("/trends")
async def get_performance_trends(
    hours: int = Query(24, ge=1, le=168, description="Number of hours to analyze (1-168)")
) -> Dict[str, Any]:
    """
    Get performance trends over the specified time period.
    
    Args:
        hours: Number of hours to analyze (1-168, default 24)
    
    Returns performance trends including hourly breakdowns and summary statistics.
    """
    try:
        return metrics_collector.get_performance_trends(hours)
    except Exception as e:
        logger.error(f"Error getting performance trends: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get performance trends: {str(e)}")


@router.get("/user-sessions")
async def get_user_session_analytics() -> Dict[str, Any]:
    """
    Get detailed user session analytics including engagement metrics and usage patterns.
    
    Returns comprehensive user session analytics for understanding user behavior.
    """
    try:
        return metrics_collector.get_user_session_analytics()
    except Exception as e:
        logger.error(f"Error getting user session analytics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get user session analytics: {str(e)}")


@router.post("/record/response-time")
async def record_response_time(
    endpoint: str,
    method: str,
    response_time_ms: float,
    status_code: int,
    user_id: Optional[str] = None,
    user_agent: Optional[str] = None,
    request_size_bytes: Optional[int] = None,
    response_size_bytes: Optional[int] = None
) -> Dict[str, str]:
    """
    Record a response time metric.
    
    Args:
        endpoint: API endpoint path
        method: HTTP method
        response_time_ms: Response time in milliseconds
        status_code: HTTP status code
        user_id: Optional user identifier
        user_agent: Optional user agent string
        request_size_bytes: Optional request size in bytes
        response_size_bytes: Optional response size in bytes
    
    Returns confirmation of metric recording.
    """
    try:
        metrics_collector.record_response_time(
            endpoint=endpoint,
            method=method,
            response_time_ms=response_time_ms,
            status_code=status_code,
            user_id=user_id,
            user_agent=user_agent,
            request_size_bytes=request_size_bytes,
            response_size_bytes=response_size_bytes
        )
        return {"status": "success", "message": "Response time metric recorded"}
    except Exception as e:
        logger.error(f"Error recording response time metric: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record response time metric: {str(e)}")


@router.post("/record/user-session")
async def record_user_session_activity(
    session_id: str,
    user_id: Optional[str] = None,
    endpoint: str = "",
    response_time_ms: float = 0,
    user_agent: Optional[str] = None,
    ip_address: Optional[str] = None
) -> Dict[str, str]:
    """
    Record user session activity.
    
    Args:
        session_id: Unique session identifier
        user_id: Optional user identifier
        endpoint: API endpoint accessed
        response_time_ms: Response time for this request
        user_agent: Optional user agent string
        ip_address: Optional client IP address
    
    Returns confirmation of session activity recording.
    """
    try:
        metrics_collector.record_user_session_activity(
            session_id=session_id,
            user_id=user_id,
            endpoint=endpoint,
            response_time_ms=response_time_ms,
            user_agent=user_agent,
            ip_address=ip_address
        )
        return {"status": "success", "message": "User session activity recorded"}
    except Exception as e:
        logger.error(f"Error recording user session activity: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record user session activity: {str(e)}")


@router.post("/record/search-performance")
async def record_search_performance(
    query_text: str,
    search_type: str,
    response_time_ms: float,
    results_count: int,
    cache_hit: bool,
    user_id: Optional[str] = None,
    query_complexity_score: Optional[float] = None
) -> Dict[str, str]:
    """
    Record search performance metrics.
    
    Args:
        query_text: Search query text (will be truncated for privacy)
        search_type: Type of search (vector, hybrid, simple)
        response_time_ms: Search response time in milliseconds
        results_count: Number of results returned
        cache_hit: Whether the search result was cached
        user_id: Optional user identifier
        query_complexity_score: Optional complexity score for the query
    
    Returns confirmation of search performance recording.
    """
    try:
        metrics_collector.record_search_performance(
            query_text=query_text,
            search_type=search_type,
            response_time_ms=response_time_ms,
            results_count=results_count,
            cache_hit=cache_hit,
            user_id=user_id,
            query_complexity_score=query_complexity_score
        )
        return {"status": "success", "message": "Search performance metric recorded"}
    except Exception as e:
        logger.error(f"Error recording search performance metric: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record search performance metric: {str(e)}")


@router.post("/record/document-processing")
async def record_document_processing(
    document_id: str,
    document_size_mb: float,
    processing_time_ms: float,
    processing_stage: str,
    success: bool,
    error_message: Optional[str] = None
) -> Dict[str, str]:
    """
    Record document processing metrics.
    
    Args:
        document_id: Unique document identifier
        document_size_mb: Document size in megabytes
        processing_time_ms: Processing time in milliseconds
        processing_stage: Processing stage (upload, extract, chunk, embed, index)
        success: Whether the processing was successful
        error_message: Optional error message if processing failed
    
    Returns confirmation of document processing recording.
    """
    try:
        metrics_collector.record_document_processing(
            document_id=document_id,
            document_size_mb=document_size_mb,
            processing_time_ms=processing_time_ms,
            processing_stage=processing_stage,
            success=success,
            error_message=error_message
        )
        return {"status": "success", "message": "Document processing metric recorded"}
    except Exception as e:
        logger.error(f"Error recording document processing metric: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record document processing metric: {str(e)}")


@router.post("/record/cache-event")
async def record_cache_event(
    event_type: str,
    size_bytes: int = 0
) -> Dict[str, str]:
    """
    Record cache-related events.
    
    Args:
        event_type: Type of cache event (hit, miss, eviction, size_update)
        size_bytes: Size in bytes (for size_update events)
    
    Returns confirmation of cache event recording.
    """
    try:
        metrics_collector.record_cache_event(event_type, size_bytes)
        return {"status": "success", "message": "Cache event recorded"}
    except Exception as e:
        logger.error(f"Error recording cache event: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record cache event: {str(e)}")


@router.get("/export")
async def export_comprehensive_report(
    background_tasks: BackgroundTasks,
    filepath: Optional[str] = Query(None, description="Optional custom filepath for export")
) -> Dict[str, str]:
    """
    Export comprehensive metrics report to JSON file.
    
    Args:
        filepath: Optional custom filepath for the export file
    
    Returns information about the exported report.
    """
    try:
        def export_task():
            return metrics_collector.export_comprehensive_report(filepath)
        
        # Run export in background
        background_tasks.add_task(export_task)
        
        return {
            "status": "success",
            "message": "Comprehensive metrics report export started",
            "note": "Export is running in background, check logs for completion"
        }
    except Exception as e:
        logger.error(f"Error starting metrics export: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start metrics export: {str(e)}")


@router.get("/health")
async def get_metrics_health() -> Dict[str, Any]:
    """
    Get health status of the metrics collection system.
    
    Returns health information about the metrics collector.
    """
    try:
        real_time = metrics_collector.get_real_time_metrics()
        
        return {
            "status": "healthy",
            "collection_active": metrics_collector._collection_active,
            "uptime_hours": real_time.get("system_uptime_hours", 0),
            "total_metrics_collected": {
                "response_times": len(metrics_collector._response_times),
                "resource_usage": len(metrics_collector._resource_usage),
                "user_sessions": len(metrics_collector._user_sessions),
                "search_performance": len(metrics_collector._search_performance),
                "document_processing": len(metrics_collector._document_processing)
            },
            "current_activity": {
                "concurrent_requests": metrics_collector._concurrent_requests,
                "active_users": len(metrics_collector._active_users),
                "peak_concurrent_requests": metrics_collector._peak_concurrent_requests
            }
        }
    except Exception as e:
        logger.error(f"Error getting metrics health: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }


@router.post("/request-start")
async def record_request_start() -> Dict[str, str]:
    """
    Record the start of a request for concurrent tracking.
    
    Returns confirmation of request start recording.
    """
    try:
        metrics_collector.record_request_start()
        return {"status": "success", "message": "Request start recorded"}
    except Exception as e:
        logger.error(f"Error recording request start: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record request start: {str(e)}")


@router.post("/request-end")
async def record_request_end() -> Dict[str, str]:
    """
    Record the end of a request for concurrent tracking.
    
    Returns confirmation of request end recording.
    """
    try:
        metrics_collector.record_request_end()
        return {"status": "success", "message": "Request end recorded"}
    except Exception as e:
        logger.error(f"Error recording request end: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record request end: {str(e)}")


# Middleware integration functions
def get_metrics_collector() -> ComprehensiveMetricsCollector:
    """Get the global metrics collector instance."""
    return metrics_collector


async def record_api_request(endpoint: str, method: str, response_time_ms: float,
                           status_code: int, user_id: Optional[str] = None,
                           user_agent: Optional[str] = None,
                           request_size: Optional[int] = None,
                           response_size: Optional[int] = None) -> None:
    """
    Convenience function for recording API requests from middleware.
    
    Args:
        endpoint: API endpoint path
        method: HTTP method
        response_time_ms: Response time in milliseconds
        status_code: HTTP status code
        user_id: Optional user identifier
        user_agent: Optional user agent string
        request_size: Optional request size in bytes
        response_size: Optional response size in bytes
    """
    try:
        metrics_collector.record_response_time(
            endpoint=endpoint,
            method=method,
            response_time_ms=response_time_ms,
            status_code=status_code,
            user_id=user_id,
            user_agent=user_agent,
            request_size_bytes=request_size,
            response_size_bytes=response_size
        )
    except Exception as e:
        logger.error(f"Error recording API request metric: {e}")