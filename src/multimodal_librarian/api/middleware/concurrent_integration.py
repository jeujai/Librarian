"""
Concurrent Request Handling Integration

This module integrates concurrent request handling into the FastAPI application,
ensuring graceful handling of concurrent requests during startup.

Key Features:
- Automatic middleware registration
- Configuration management
- Metrics endpoint
- Health check integration
"""

import logging
from typing import Dict, Any
from fastapi import FastAPI, APIRouter
from fastapi.responses import JSONResponse

from .concurrent_request_handler import (
    ConcurrentRequestHandler,
    get_concurrent_request_handler,
    set_concurrent_request_handler
)
from ...logging_config import get_logger

logger = get_logger("concurrent_integration")

# Router for concurrent request metrics
router = APIRouter(prefix="/api/concurrent", tags=["concurrent"])


def integrate_concurrent_request_handling(app: FastAPI) -> None:
    """
    Integrate concurrent request handling into the FastAPI application.
    
    This function:
    1. Adds the concurrent request handler middleware
    2. Registers metrics endpoints
    3. Configures health check integration
    
    Args:
        app: FastAPI application instance
    """
    try:
        # Create and register middleware
        handler = ConcurrentRequestHandler(app)
        app.add_middleware(ConcurrentRequestHandler)
        set_concurrent_request_handler(handler)
        
        # Register metrics router
        app.include_router(router)
        
        logger.info("Concurrent request handling integrated successfully")
        
    except Exception as e:
        logger.error(f"Failed to integrate concurrent request handling: {e}")
        # Don't fail application startup if integration fails
        logger.warning("Application will continue without concurrent request handling")


@router.get("/metrics")
async def get_concurrent_metrics() -> Dict[str, Any]:
    """
    Get concurrent request handling metrics.
    
    Returns:
        Metrics including:
        - Total requests processed
        - Current concurrent requests
        - Peak concurrent requests
        - Throttled requests
        - Success rate
        - Response time statistics
    """
    handler = get_concurrent_request_handler()
    
    if not handler:
        return {
            "status": "unavailable",
            "message": "Concurrent request handler not initialized"
        }
    
    metrics = handler.get_metrics()
    
    return {
        "status": "ok",
        "metrics": metrics,
        "health": {
            "concurrent_capacity": "healthy" if metrics["concurrent_requests"] < 100 else "high_load",
            "success_rate": "healthy" if metrics["success_rate"] > 95 else "degraded",
            "throttling": "active" if metrics["throttled_requests"] > 0 else "inactive"
        }
    }


@router.get("/status")
async def get_concurrent_status() -> Dict[str, Any]:
    """
    Get current concurrent request handling status.
    
    Returns:
        Current status including:
        - Active concurrent requests
        - System capacity
        - Throttling status
    """
    handler = get_concurrent_request_handler()
    
    if not handler:
        return {
            "status": "unavailable",
            "message": "Concurrent request handler not initialized"
        }
    
    metrics = handler.get_metrics()
    
    # Determine capacity status
    concurrent = metrics["concurrent_requests"]
    if concurrent < 50:
        capacity_status = "available"
        capacity_percent = (concurrent / 50) * 100
    elif concurrent < 100:
        capacity_status = "moderate"
        capacity_percent = (concurrent / 100) * 100
    else:
        capacity_status = "high"
        capacity_percent = min(100, (concurrent / 200) * 100)
    
    return {
        "status": "ok",
        "concurrent_requests": concurrent,
        "peak_concurrent_requests": metrics["peak_concurrent_requests"],
        "capacity_status": capacity_status,
        "capacity_percent": capacity_percent,
        "throttling_active": metrics["throttled_requests"] > 0,
        "success_rate": metrics["success_rate"],
        "avg_response_time_ms": metrics["avg_response_time_ms"]
    }


@router.get("/health")
async def concurrent_health_check() -> JSONResponse:
    """
    Health check for concurrent request handling.
    
    Returns:
        Health status with appropriate HTTP status code
    """
    handler = get_concurrent_request_handler()
    
    if not handler:
        return JSONResponse(
            content={
                "status": "unavailable",
                "message": "Concurrent request handler not initialized"
            },
            status_code=503
        )
    
    metrics = handler.get_metrics()
    
    # Determine health status
    is_healthy = True
    issues = []
    
    # Check success rate
    if metrics["success_rate"] < 90:
        is_healthy = False
        issues.append(f"Low success rate: {metrics['success_rate']:.1f}%")
    
    # Check if system is overloaded
    if metrics["concurrent_requests"] > 150:
        is_healthy = False
        issues.append(f"High concurrent load: {metrics['concurrent_requests']} requests")
    
    # Check throttling rate
    throttle_rate = (metrics["throttled_requests"] / max(metrics["total_requests"], 1)) * 100
    if throttle_rate > 20:
        is_healthy = False
        issues.append(f"High throttle rate: {throttle_rate:.1f}%")
    
    status_code = 200 if is_healthy else 503
    
    return JSONResponse(
        content={
            "status": "healthy" if is_healthy else "degraded",
            "concurrent_requests": metrics["concurrent_requests"],
            "success_rate": metrics["success_rate"],
            "issues": issues if issues else None
        },
        status_code=status_code
    )


@router.post("/reset-metrics")
async def reset_concurrent_metrics() -> Dict[str, str]:
    """
    Reset concurrent request metrics.
    
    This is useful for testing and monitoring purposes.
    
    Returns:
        Confirmation message
    """
    handler = get_concurrent_request_handler()
    
    if not handler:
        return {
            "status": "error",
            "message": "Concurrent request handler not initialized"
        }
    
    # Reset metrics by creating new instance
    handler._metrics = type(handler._metrics)()
    
    return {
        "status": "ok",
        "message": "Concurrent request metrics reset successfully"
    }
