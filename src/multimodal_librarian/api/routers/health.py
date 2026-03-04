"""
Health Check API Router

This module provides health check endpoints optimized for AWS ECS and startup optimization.
It integrates with the minimal server and startup phase manager to provide accurate health status.

Key Features:
- ECS-optimized health checks
- Startup phase-aware health reporting
- Model loading status
- Request queuing status
- Progressive capability reporting
- Health check failure monitoring and alerting
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from ...logging_config import get_logger
from ...startup.minimal_server import get_minimal_server
from ...startup.phase_manager import StartupPhaseManager

router = APIRouter(prefix="/api/health", tags=["Health"])
logger = get_logger("health_api")

# Global reference to startup alerts service for health check monitoring
_startup_alerts_service = None

def set_startup_alerts_service(alerts_service):
    """Set the startup alerts service for health check monitoring."""
    global _startup_alerts_service
    _startup_alerts_service = alerts_service

def get_startup_alerts_service():
    """Get the startup alerts service for health check monitoring."""
    return _startup_alerts_service


@router.get("/minimal")
async def minimal_health_check():
    """
    Minimal health check for ECS - basic server readiness.
    
    This endpoint is optimized for AWS ECS health checks and returns quickly
    with basic server status information.
    
    Returns:
        Basic health status suitable for ECS health checks
    """
    start_time = time.time()
    success = False
    
    # Log that health check was called
    logger.info("=" * 80)
    logger.info("HEALTH CHECK CALLED: /api/health/minimal")
    logger.info("=" * 80)
    
    try:
        server = get_minimal_server()
        status = server.get_status()
        
        # Log detailed status
        logger.info(f"MinimalServer status: {status.status.value}")
        logger.info(f"MinimalServer health_check_ready: {status.health_check_ready}")
        logger.info(f"MinimalServer uptime: {status.uptime_seconds}s")
        
        # Determine health status
        is_healthy = status.health_check_ready and status.status.value != "error"
        success = is_healthy
        
        logger.info(f"Health check result: is_healthy={is_healthy}, will return {200 if is_healthy else 503}")
        
        response = {
            "status": "healthy" if is_healthy else "starting",
            "server_status": status.status.value,
            "uptime_seconds": status.uptime_seconds,
            "ready": status.health_check_ready,
            "timestamp": datetime.now().isoformat()
        }
        
        # Return appropriate HTTP status code
        status_code = 200 if is_healthy else 503
        return JSONResponse(content=response, status_code=status_code)
        
    except Exception as e:
        logger.error(f"Minimal health check failed: {e}")
        success = False
        return JSONResponse(
            content={
                "status": "error",
                "error": str(e),
                "ready": False,
                "timestamp": datetime.now().isoformat()
            },
            status_code=503
        )
    finally:
        # Record health check result for monitoring
        response_time_ms = (time.time() - start_time) * 1000
        alerts_service = get_startup_alerts_service()
        if alerts_service:
            try:
                await alerts_service.record_health_check_result(success, response_time_ms)
            except Exception as e:
                logger.warning(f"Failed to record health check result: {e}")


@router.get("/ready")
async def readiness_health_check():
    """
    Readiness health check - essential models loaded.
    
    This endpoint checks if essential models are loaded and the system
    is ready to handle user requests with basic functionality.
    
    Returns:
        Readiness status with capability information
    """
    start_time = time.time()
    success = False
    
    try:
        server = get_minimal_server()
        status = server.get_status()
        
        # Check if essential capabilities are ready
        essential_ready = (
            status.capabilities.get("basic_chat", False) or
            status.capabilities.get("simple_search", False) or
            status.uptime_seconds > 120  # Fallback after 2 minutes
        )
        success = essential_ready
        
        response = {
            "status": "ready" if essential_ready else "not_ready",
            "server_status": status.status.value,
            "essential_models_ready": essential_ready,
            "capabilities": status.capabilities,
            "model_statuses": {
                name: status for name, status in status.model_statuses.items()
                if status in ["loaded", "loading", "failed"]
            },
            "estimated_ready_times": status.estimated_ready_times,
            "uptime_seconds": status.uptime_seconds,
            "timestamp": datetime.now().isoformat()
        }
        
        status_code = 200 if essential_ready else 503
        return JSONResponse(content=response, status_code=status_code)
        
    except Exception as e:
        logger.error(f"Readiness health check failed: {e}")
        success = False
        return JSONResponse(
            content={
                "status": "error",
                "error": str(e),
                "ready": False,
                "timestamp": datetime.now().isoformat()
            },
            status_code=503
        )
    finally:
        # Record health check result for monitoring
        response_time_ms = (time.time() - start_time) * 1000
        alerts_service = get_startup_alerts_service()
        if alerts_service:
            try:
                await alerts_service.record_health_check_result(success, response_time_ms)
            except Exception as e:
                logger.warning(f"Failed to record health check result: {e}")


@router.get("/full")
async def full_health_check():
    """
    Full health check - all models loaded.
    
    This endpoint checks if all models are loaded and the system
    has full functionality available.
    
    Returns:
        Complete health status with all model information
    """
    try:
        server = get_minimal_server()
        status = server.get_status()
        
        # Check if all models are ready
        all_ready = status.status.value == "ready"
        loaded_models = [name for name, model_status in status.model_statuses.items() 
                        if model_status == "loaded"]
        
        response = {
            "status": "ready" if all_ready else "not_ready",
            "server_status": status.status.value,
            "all_models_ready": all_ready,
            "capabilities": status.capabilities,
            "model_statuses": status.model_statuses,
            "loaded_models": loaded_models,
            "loaded_models_count": len(loaded_models),
            "total_models_count": len(status.model_statuses),
            "queue_status": server.get_queue_status(),
            "uptime_seconds": status.uptime_seconds,
            "timestamp": datetime.now().isoformat()
        }
        
        status_code = 200 if all_ready else 503
        return JSONResponse(content=response, status_code=status_code)
        
    except Exception as e:
        logger.error(f"Full health check failed: {e}")
        return JSONResponse(
            content={
                "status": "error",
                "error": str(e),
                "ready": False,
                "timestamp": datetime.now().isoformat()
            },
            status_code=503
        )


@router.get("/startup")
async def startup_health_check():
    """
    Startup-specific health check with detailed phase information.
    
    This endpoint provides detailed information about the startup process,
    including phase transitions, model loading progress, and timing metrics.
    
    Returns:
        Detailed startup health information
    """
    try:
        server = get_minimal_server()
        status = server.get_status()
        
        # Calculate startup metrics
        startup_metrics = {
            "phase": "minimal" if status.uptime_seconds < 60 else 
                    "essential" if status.uptime_seconds < 180 else "full",
            "uptime_seconds": status.uptime_seconds,
            "target_minimal_time": 30,
            "target_essential_time": 120,
            "target_full_time": 300,
            "within_targets": {
                "minimal": status.uptime_seconds <= 30 or status.health_check_ready,
                "essential": status.uptime_seconds <= 120 or any(status.capabilities.values()),
                "full": status.uptime_seconds <= 300 or status.status.value == "ready"
            }
        }
        
        # Model loading progress
        model_progress = {
            "total_models": len(status.model_statuses),
            "loaded_models": len([s for s in status.model_statuses.values() if s == "loaded"]),
            "loading_models": len([s for s in status.model_statuses.values() if s == "loading"]),
            "failed_models": len([s for s in status.model_statuses.values() if s == "failed"]),
            "pending_models": len([s for s in status.model_statuses.values() if s == "pending"])
        }
        
        if model_progress["total_models"] > 0:
            model_progress["progress_percent"] = (
                model_progress["loaded_models"] / model_progress["total_models"]
            ) * 100
        else:
            model_progress["progress_percent"] = 0
        
        response = {
            "status": "healthy" if status.health_check_ready else "starting",
            "server_status": status.status.value,
            "startup_metrics": startup_metrics,
            "model_progress": model_progress,
            "capabilities": status.capabilities,
            "estimated_ready_times": status.estimated_ready_times,
            "queue_status": server.get_queue_status(),
            "detailed_model_statuses": status.model_statuses,
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Startup health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Startup health check failed: {str(e)}")


@router.get("/models")
async def model_status_check():
    """
    Model loading status endpoint.
    
    This endpoint provides detailed information about model loading progress,
    including individual model statuses and estimated completion times.
    
    Returns:
        Detailed model loading status information
    """
    try:
        server = get_minimal_server()
        status = server.get_status()
        
        # Organize models by priority/category
        model_categories = {
            "essential": ["text-embedding-small", "chat-model-base", "search-index"],
            "standard": ["chat-model-large", "document-processor"],
            "advanced": ["multimodal-model", "specialized-analyzers"]
        }
        
        categorized_status = {}
        for category, model_names in model_categories.items():
            categorized_status[category] = {
                "models": {},
                "loaded_count": 0,
                "total_count": len(model_names),
                "all_loaded": True
            }
            
            for model_name in model_names:
                model_status = status.model_statuses.get(model_name, "unknown")
                categorized_status[category]["models"][model_name] = model_status
                
                if model_status == "loaded":
                    categorized_status[category]["loaded_count"] += 1
                elif model_status != "loaded":
                    categorized_status[category]["all_loaded"] = False
        
        response = {
            "overall_status": status.status.value,
            "model_categories": categorized_status,
            "all_model_statuses": status.model_statuses,
            "capabilities": status.capabilities,
            "estimated_ready_times": status.estimated_ready_times,
            "uptime_seconds": status.uptime_seconds,
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Model status check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Model status check failed: {str(e)}")


@router.get("/capabilities")
async def capabilities_check():
    """
    Current capabilities endpoint.
    
    This endpoint reports what capabilities are currently available
    and what is still loading.
    
    Returns:
        Current capability status and availability
    """
    try:
        server = get_minimal_server()
        status = server.get_status()
        
        # Categorize capabilities
        available_capabilities = [cap for cap, available in status.capabilities.items() if available]
        loading_capabilities = list(status.estimated_ready_times.keys())
        
        response = {
            "server_status": status.status.value,
            "available_capabilities": available_capabilities,
            "loading_capabilities": loading_capabilities,
            "all_capabilities": status.capabilities,
            "estimated_ready_times": status.estimated_ready_times,
            "ready_for_requests": len(available_capabilities) > 3,  # Basic threshold
            "uptime_seconds": status.uptime_seconds,
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Capabilities check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Capabilities check failed: {str(e)}")


@router.get("/queue")
async def queue_status_check():
    """
    Request queue status endpoint.
    
    This endpoint provides information about the current request queue,
    including pending requests and processing statistics.
    
    Returns:
        Request queue status and statistics
    """
    try:
        server = get_minimal_server()
        queue_status = server.get_queue_status()
        server_status = server.get_status()
        
        response = {
            "server_status": server_status.status.value,
            "queue_enabled": True,
            "queue_status": queue_status,
            "capabilities": server_status.capabilities,
            "estimated_ready_times": server_status.estimated_ready_times,
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Queue status check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Queue status check failed: {str(e)}")


@router.get("/performance")
async def performance_health_check():
    """
    Performance-focused health check.
    
    This endpoint provides performance metrics and timing information
    for monitoring and optimization purposes.
    
    Returns:
        Performance metrics and health status
    """
    try:
        server = get_minimal_server()
        status = server.get_status()
        
        # Calculate performance metrics
        performance_metrics = {
            "startup_time_seconds": status.uptime_seconds,
            "health_check_response_time_ms": 1.0,  # This endpoint's response time
            "queue_processing_rate": (
                status.processed_requests / max(status.uptime_seconds, 1)
            ),
            "error_rate": (
                status.failed_requests / max(status.processed_requests + status.failed_requests, 1)
            ) * 100,
            "memory_efficient": status.uptime_seconds > 0,  # Basic check
            "within_startup_targets": {
                "minimal_phase": status.health_check_ready,
                "essential_phase": any(status.capabilities.values()),
                "response_time": True  # Always true for this simple check
            }
        }
        
        # Overall performance score (0-100)
        performance_score = 100
        if status.uptime_seconds > 60 and not status.health_check_ready:
            performance_score -= 30
        if status.uptime_seconds > 180 and not any(status.capabilities.values()):
            performance_score -= 40
        if performance_metrics["error_rate"] > 5:
            performance_score -= 20
        
        performance_score = max(0, performance_score)
        
        response = {
            "performance_score": performance_score,
            "performance_grade": (
                "excellent" if performance_score >= 90 else
                "good" if performance_score >= 70 else
                "acceptable" if performance_score >= 50 else
                "poor"
            ),
            "metrics": performance_metrics,
            "server_status": status.status.value,
            "capabilities": status.capabilities,
            "uptime_seconds": status.uptime_seconds,
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Performance health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Performance health check failed: {str(e)}")


@router.get("/simple")
async def simple_health_check():
    """
    Simple health check for load balancers.
    
    This is the most basic health check that returns immediately
    without waiting for any component initialization. This ensures
    ALB health checks pass even during startup.
    
    CRITICAL: This endpoint MUST NOT depend on:
    - Database connections (OpenSearch, Neptune, PostgreSQL)
    - Model loading
    - Any external service initialization
    
    Includes timing instrumentation to detect GIL contention during model loading.
    Logs warnings when response time exceeds 100ms threshold.
    Records latency metrics for monitoring and analysis.
    
    Returns:
        Simple OK status (always returns 200)
    """
    # Start timing instrumentation for GIL contention detection
    start_time = time.time()
    
    # CRITICAL: Do NOT call get_minimal_server() or any initialization code
    # This endpoint must respond immediately for ALB health checks
    # Do NOT add database checks, model checks, or any blocking operations
    response = {
        "status": "ok",
        "timestamp": datetime.now().isoformat()
    }
    
    # Calculate response time and check for GIL contention
    response_time_ms = (time.time() - start_time) * 1000
    
    # Add response time to the response for monitoring
    response["response_time_ms"] = round(response_time_ms, 2)
    
    # Log warning if response time exceeds threshold (indicates possible GIL contention)
    # Normal response time should be < 10ms, threshold set at 100ms
    if response_time_ms > 100:
        logger.warning(
            f"Health check slow: {response_time_ms:.1f}ms - possible GIL contention during model loading. "
            f"Consider using ProcessPoolExecutor for CPU-bound operations."
        )
    elif response_time_ms > 50:
        logger.info(f"Health check response time elevated: {response_time_ms:.1f}ms")
    
    # Record latency metrics for monitoring (non-blocking, fire-and-forget)
    try:
        from ...main import startup_metrics_collector
        if startup_metrics_collector:
            # Use create_task to avoid blocking the response
            import asyncio
            asyncio.create_task(
                startup_metrics_collector.record_health_check_latency(
                    response_time_ms=response_time_ms,
                    success=True,
                    endpoint="/health/simple"
                )
            )
    except Exception as e:
        # Don't let metric recording failures affect health check response
        logger.debug(f"Failed to record health check latency metric: {e}")
    
    return JSONResponse(
        content=response,
        status_code=200
    )


@router.get("/")
async def comprehensive_health_check():
    """
    Comprehensive health check endpoint.
    
    This endpoint provides a complete health report including all aspects
    of the system: startup status, model loading, capabilities, and performance.
    
    Returns:
        Complete system health report
    """
    try:
        server = get_minimal_server()
        status = server.get_status()
        
        # Gather comprehensive health information
        health_report = {
            "overall_status": "healthy" if status.health_check_ready else "starting",
            "server_status": status.status.value,
            "uptime_seconds": status.uptime_seconds,
            "startup_phase": (
                "minimal" if status.uptime_seconds < 60 else
                "essential" if status.uptime_seconds < 180 else
                "full"
            ),
            "health_checks": {
                "minimal": status.health_check_ready,
                "ready": any(status.capabilities.values()),
                "full": status.status.value == "ready"
            },
            "capabilities": status.capabilities,
            "model_statuses": status.model_statuses,
            "estimated_ready_times": status.estimated_ready_times,
            "queue_status": server.get_queue_status(),
            "performance": {
                "startup_time_seconds": status.uptime_seconds,
                "processed_requests": status.processed_requests,
                "failed_requests": status.failed_requests,
                "queue_size": len(server.request_queue)
            },
            "enrichment": await _get_enrichment_health_metrics(),
            "timestamp": datetime.now().isoformat()
        }
        
        return health_report
        
    except Exception as e:
        logger.error(f"Comprehensive health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


async def _get_enrichment_health_metrics() -> dict:
    """
    Get enrichment health metrics for the health check endpoint.
    
    Returns:
        Dictionary with enrichment queue depth and processing rate
    """
    try:
        from ...database.connection import get_database_connection
        
        db_pool = await get_database_connection()
        async with db_pool.acquire() as conn:
            # Get queue depth (pending + in-progress)
            queue_result = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) FILTER (WHERE state = 'pending') as pending_count,
                    COUNT(*) FILTER (WHERE state = 'enriching') as in_progress_count,
                    COUNT(*) FILTER (WHERE state = 'completed') as completed_count,
                    COUNT(*) FILTER (WHERE state = 'failed') as failed_count
                FROM enrichment_status
                """
            )
            
            # Get processing rate (completed in last hour)
            rate_result = await conn.fetchrow(
                """
                SELECT COUNT(*) as completed_last_hour
                FROM enrichment_status
                WHERE state = 'completed'
                AND completed_at > NOW() - INTERVAL '1 hour'
                """
            )
            
            pending = queue_result['pending_count'] if queue_result else 0
            in_progress = queue_result['in_progress_count'] if queue_result else 0
            completed = queue_result['completed_count'] if queue_result else 0
            failed = queue_result['failed_count'] if queue_result else 0
            completed_last_hour = rate_result['completed_last_hour'] if rate_result else 0
            
            return {
                "queue_depth": pending + in_progress,
                "pending_count": pending,
                "in_progress_count": in_progress,
                "completed_count": completed,
                "failed_count": failed,
                "processing_rate_per_hour": completed_last_hour,
                "status": "healthy" if failed == 0 or completed > failed else "degraded"
            }
            
    except Exception as e:
        logger.warning(f"Failed to get enrichment health metrics: {e}")
        return {
            "queue_depth": 0,
            "pending_count": 0,
            "in_progress_count": 0,
            "completed_count": 0,
            "failed_count": 0,
            "processing_rate_per_hour": 0,
            "status": "unknown",
            "error": str(e)
        }


@router.get("/metrics/startup")
async def startup_metrics_check():
    """
    Startup metrics endpoint with phase completion time tracking.
    
    This endpoint provides detailed startup metrics including phase completion times,
    model loading performance, and efficiency scores.
    
    Returns:
        Detailed startup metrics and performance data
    """
    try:
        # Try to get metrics from the global startup metrics collector
        from ...main import performance_tracker, startup_metrics_collector
        
        if not startup_metrics_collector:
            return JSONResponse(
                content={
                    "status": "unavailable",
                    "message": "Startup metrics collection not initialized",
                    "timestamp": datetime.now().isoformat()
                },
                status_code=503
            )
        
        # Get startup session summary
        session_summary = startup_metrics_collector.get_startup_session_summary()
        
        # Get phase completion metrics
        phase_metrics = {}
        for phase in ["minimal", "essential", "full"]:
            from ...startup.phase_manager import StartupPhase
            phase_enum = getattr(StartupPhase, phase.upper())
            phase_metrics[phase] = startup_metrics_collector.get_phase_completion_metrics(phase_enum)
        
        # Get model loading metrics
        model_metrics = startup_metrics_collector.get_model_loading_metrics()
        
        # Get historical trends
        historical_trends = startup_metrics_collector.get_historical_trends(days=7)
        
        response = {
            "status": "available",
            "current_session": session_summary,
            "phase_completion_metrics": phase_metrics,
            "model_loading_metrics": model_metrics,
            "historical_trends": historical_trends,
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Startup metrics check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Startup metrics check failed: {str(e)}")


@router.get("/metrics/performance")
async def performance_metrics_check():
    """
    Performance metrics endpoint with resource utilization tracking.
    
    This endpoint provides detailed performance metrics including resource usage,
    bottleneck identification, and optimization recommendations.
    
    Returns:
        Detailed performance metrics and analysis
    """
    try:
        # Try to get metrics from the global performance tracker
        from ...main import performance_tracker
        
        if not performance_tracker:
            return JSONResponse(
                content={
                    "status": "unavailable",
                    "message": "Performance tracking not initialized",
                    "timestamp": datetime.now().isoformat()
                },
                status_code=503
            )
        
        # Get performance summary
        performance_summary = performance_tracker.get_performance_summary()
        
        # Get recent alerts
        recent_alerts = performance_tracker.get_recent_alerts(minutes=30)
        
        # Get identified bottlenecks
        bottlenecks = performance_tracker.get_bottlenecks()
        
        # Get optimization recommendations
        recommendations = performance_tracker.get_recommendations()
        
        response = {
            "status": "available",
            "performance_summary": performance_summary,
            "recent_alerts": [
                {
                    "type": alert.alert_type,
                    "severity": alert.severity,
                    "message": alert.message,
                    "timestamp": alert.timestamp.isoformat(),
                    "metric": alert.metric_name,
                    "threshold": alert.threshold_value,
                    "actual": alert.actual_value,
                    "recommendations": alert.recommendations
                }
                for alert in recent_alerts
            ],
            "bottlenecks": bottlenecks,
            "optimization_recommendations": recommendations,
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Performance metrics check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Performance metrics check failed: {str(e)}")


@router.get("/metrics/phase-completion")
async def phase_completion_metrics_check(
    phase: Optional[str] = Query(None, description="Specific phase to get metrics for (minimal, essential, full)")
):
    """
    Phase completion time metrics endpoint.
    
    This endpoint provides detailed metrics about startup phase completion times,
    including duration statistics, efficiency scores, and success rates.
    
    Args:
        phase: Optional specific phase to get metrics for
    
    Returns:
        Phase completion time metrics and analysis
    """
    try:
        from ...main import startup_metrics_collector
        from ...startup.phase_manager import StartupPhase
        
        if not startup_metrics_collector:
            return JSONResponse(
                content={
                    "status": "unavailable",
                    "message": "Startup metrics collection not initialized",
                    "timestamp": datetime.now().isoformat()
                },
                status_code=503
            )
        
        # Get metrics for specific phase or all phases
        if phase:
            if phase.upper() not in [p.name for p in StartupPhase]:
                raise HTTPException(status_code=400, detail=f"Invalid phase: {phase}")
            
            phase_enum = getattr(StartupPhase, phase.upper())
            metrics = startup_metrics_collector.get_phase_completion_metrics(phase_enum)
        else:
            metrics = startup_metrics_collector.get_phase_completion_metrics()
        
        response = {
            "status": "available",
            "phase_metrics": metrics,
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Phase completion metrics check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Phase completion metrics check failed: {str(e)}")


@router.get("/metrics/model-loading")
async def model_loading_metrics_check(
    model: Optional[str] = Query(None, description="Specific model to get metrics for")
):
    """
    Model loading performance metrics endpoint.
    
    This endpoint provides detailed metrics about model loading performance,
    including duration statistics, efficiency ratios, success rates, cache performance,
    resource utilization, and performance bottleneck analysis.
    
    Args:
        model: Optional specific model to get metrics for
    
    Returns:
        Model loading performance metrics and analysis
    """
    try:
        from ...main import startup_metrics_collector
        
        if not startup_metrics_collector:
            return JSONResponse(
                content={
                    "status": "unavailable",
                    "message": "Startup metrics collection not initialized",
                    "timestamp": datetime.now().isoformat()
                },
                status_code=503
            )
        
        # Get metrics for specific model or all models
        metrics = startup_metrics_collector.get_model_loading_metrics(model)
        
        response = {
            "status": "available",
            "model_metrics": metrics,
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Model loading metrics check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Model loading metrics check failed: {str(e)}")


@router.get("/metrics/model-loading/cache")
async def model_loading_cache_metrics():
    """
    Model loading cache performance metrics endpoint.
    
    This endpoint provides detailed metrics about model loading cache performance,
    including cache hit rates, cache effectiveness, and cache source analysis.
    
    Returns:
        Model loading cache performance metrics
    """
    try:
        from ...main import startup_metrics_collector
        
        if not startup_metrics_collector:
            return JSONResponse(
                content={
                    "status": "unavailable",
                    "message": "Startup metrics collection not initialized",
                    "timestamp": datetime.now().isoformat()
                },
                status_code=503
            )
        
        cache_metrics = startup_metrics_collector.get_cache_performance_metrics()
        
        response = {
            "status": "available",
            "cache_metrics": cache_metrics,
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Model loading cache metrics check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Model loading cache metrics check failed: {str(e)}")


@router.get("/metrics/model-loading/bottlenecks")
async def model_loading_bottlenecks():
    """
    Model loading performance bottlenecks endpoint.
    
    This endpoint identifies performance bottlenecks in model loading operations,
    including slow models, high memory usage, frequent failures, and low cache hit rates.
    
    Returns:
        Model loading performance bottlenecks and recommendations
    """
    try:
        from ...main import startup_metrics_collector
        
        if not startup_metrics_collector:
            return JSONResponse(
                content={
                    "status": "unavailable",
                    "message": "Startup metrics collection not initialized",
                    "timestamp": datetime.now().isoformat()
                },
                status_code=503
            )
        
        bottlenecks = startup_metrics_collector.get_model_loading_bottlenecks()
        
        response = {
            "status": "available",
            "bottlenecks": bottlenecks,
            "bottleneck_count": len(bottlenecks),
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Model loading bottlenecks check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Model loading bottlenecks check failed: {str(e)}")


@router.get("/metrics/model-loading/summary")
async def model_loading_performance_summary():
    """
    Model loading performance summary endpoint.
    
    This endpoint provides a comprehensive summary of model loading performance,
    including overall statistics, trends, best/worst performing models, and insights.
    
    Returns:
        Comprehensive model loading performance summary
    """
    try:
        from ...main import startup_metrics_collector
        
        if not startup_metrics_collector:
            return JSONResponse(
                content={
                    "status": "unavailable",
                    "message": "Startup metrics collection not initialized",
                    "timestamp": datetime.now().isoformat()
                },
                status_code=503
            )
        
        summary = startup_metrics_collector.get_model_loading_performance_summary()
        
        response = {
            "status": "available",
            "performance_summary": summary,
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Model loading performance summary check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Model loading performance summary check failed: {str(e)}")


@router.get("/metrics/health-check-latency")
async def health_check_latency_metrics(
    phase: Optional[str] = Query(None, description="Filter by startup phase (minimal, essential, full)"),
    minutes_back: Optional[int] = Query(None, description="Only include metrics from the last N minutes"),
    during_model_loading: bool = Query(False, description="Only include metrics when models were being loaded")
):
    """
    Health check latency metrics endpoint.
    
    This endpoint provides detailed metrics about health check response times during
    model loading, including GIL contention detection and correlation analysis.
    
    Tracks health check latency to detect event loop blocking during CPU-bound
    model loading operations. Response times > 100ms indicate possible GIL contention.
    
    Args:
        phase: Optional filter by startup phase
        minutes_back: Only include metrics from the last N minutes
        during_model_loading: Only include metrics when models were being loaded
    
    Returns:
        Health check latency metrics and GIL contention analysis
    """
    try:
        from ...main import startup_metrics_collector
        from ...startup.phase_manager import StartupPhase
        
        if not startup_metrics_collector:
            return JSONResponse(
                content={
                    "status": "unavailable",
                    "message": "Startup metrics collection not initialized",
                    "timestamp": datetime.now().isoformat()
                },
                status_code=503
            )
        
        # Parse phase parameter
        phase_enum = None
        if phase:
            if phase.upper() not in [p.name for p in StartupPhase]:
                raise HTTPException(status_code=400, detail=f"Invalid phase: {phase}")
            phase_enum = getattr(StartupPhase, phase.upper())
        
        # Get metrics with filters
        metrics = startup_metrics_collector.get_health_check_latency_metrics(
            phase=phase_enum,
            minutes_back=minutes_back,
            during_model_loading=during_model_loading
        )
        
        response = {
            "status": "available",
            "health_check_latency_metrics": metrics,
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check latency metrics check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check latency metrics check failed: {str(e)}")


@router.get("/metrics/health-check-latency/summary")
async def health_check_latency_summary():
    """
    Health check latency summary endpoint.
    
    This endpoint provides a comprehensive summary of health check latency during
    startup, including overall statistics, model loading impact analysis, and
    GIL contention summary.
    
    Returns:
        Comprehensive health check latency summary
    """
    try:
        from ...main import startup_metrics_collector
        
        if not startup_metrics_collector:
            return JSONResponse(
                content={
                    "status": "unavailable",
                    "message": "Startup metrics collection not initialized",
                    "timestamp": datetime.now().isoformat()
                },
                status_code=503
            )
        
        summary = startup_metrics_collector.get_health_check_latency_summary()
        
        response = {
            "status": "available",
            "health_check_latency_summary": summary,
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Health check latency summary check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check latency summary check failed: {str(e)}")


@router.get("/metrics/export")
async def export_startup_metrics(
    format: str = Query("json", description="Export format (json)")
):
    """
    Export startup metrics data.
    
    This endpoint exports comprehensive startup metrics data in the specified format
    for analysis, reporting, or integration with external monitoring systems.
    
    Args:
        format: Export format (currently only 'json' is supported)
    
    Returns:
        Exported metrics data
    """
    try:
        from ...main import performance_tracker, startup_metrics_collector
        
        if not startup_metrics_collector:
            return JSONResponse(
                content={
                    "status": "unavailable",
                    "message": "Startup metrics collection not initialized",
                    "timestamp": datetime.now().isoformat()
                },
                status_code=503
            )
        
        if format.lower() != "json":
            raise HTTPException(status_code=400, detail=f"Unsupported export format: {format}")
        
        # Export startup metrics
        startup_data = startup_metrics_collector.export_metrics(format)
        
        # Export performance data if available
        performance_data = None
        if performance_tracker:
            performance_data = performance_tracker.export_performance_data(format)
        
        # Combine data
        import json
        startup_json = json.loads(startup_data)
        
        export_data = {
            "export_timestamp": datetime.now().isoformat(),
            "export_format": format,
            "startup_metrics": startup_json,
            "performance_metrics": json.loads(performance_data) if performance_data else None
        }
        
        return export_data
        
    except Exception as e:
        logger.error(f"Metrics export failed: {e}")
        raise HTTPException(status_code=500, detail=f"Metrics export failed: {str(e)}")


@router.get("/alerts")
async def health_check_alerts():
    """
    Health check failure alerts endpoint.
    
    This endpoint provides information about health check failures and related alerts,
    including consecutive failure counts, alert status, and remediation recommendations.
    
    Returns:
        Health check failure monitoring status and alerts
    """
    try:
        alerts_service = get_startup_alerts_service()
        
        if not alerts_service:
            return JSONResponse(
                content={
                    "status": "unavailable",
                    "message": "Health check failure monitoring not initialized",
                    "timestamp": datetime.now().isoformat()
                },
                status_code=503
            )
        
        # Get health check failure status
        consecutive_failures = alerts_service._consecutive_health_failures
        last_check_time = alerts_service._last_health_check_time
        
        # Get active health check related alerts
        active_alerts = alerts_service.get_active_alerts()
        health_alerts = [
            alert for alert in active_alerts
            if alert.alert_type.value == "health_check_failure"
        ]
        
        # Get recent health check alerts from history
        recent_alerts = alerts_service.get_alert_history(hours=24)
        recent_health_alerts = [
            alert for alert in recent_alerts
            if alert.alert_type.value == "health_check_failure"
        ]
        
        # Calculate health check status
        current_time = datetime.now()
        time_since_last_check = None
        if last_check_time:
            time_since_last_check = (current_time - last_check_time).total_seconds()
        
        health_check_status = {
            "consecutive_failures": consecutive_failures,
            "last_check_time": last_check_time.isoformat() if last_check_time else None,
            "time_since_last_check_seconds": time_since_last_check,
            "failure_threshold": alerts_service.default_thresholds["health_check_failure_threshold"].threshold_value,
            "threshold_exceeded": consecutive_failures >= alerts_service.default_thresholds["health_check_failure_threshold"].threshold_value,
            "monitoring_active": alerts_service._is_monitoring
        }
        
        # Generate recommendations based on failure status
        recommendations = []
        if consecutive_failures > 0:
            recommendations.extend([
                "Check application logs for health check errors",
                "Verify server startup and initialization",
                "Review resource availability (CPU, memory)",
                "Check network connectivity and dependencies"
            ])
        
        if consecutive_failures >= 2:
            recommendations.extend([
                "Consider increasing health check timeout",
                "Review health check endpoint implementation",
                "Check for resource contention or bottlenecks"
            ])
        
        if consecutive_failures >= 3:
            recommendations.extend([
                "URGENT: Investigate immediate health check failures",
                "Consider emergency restart or rollback",
                "Contact on-call engineer if issue persists"
            ])
        
        response = {
            "status": "available",
            "health_check_status": health_check_status,
            "active_health_alerts": len(health_alerts),
            "recent_health_alerts_24h": len(recent_health_alerts),
            "active_alerts": [
                {
                    "alert_id": alert.alert_id,
                    "severity": alert.severity.value,
                    "title": alert.title,
                    "description": alert.description,
                    "timestamp": alert.timestamp.isoformat(),
                    "affected_resources": alert.affected_resources,
                    "remediation_steps": alert.remediation_steps
                }
                for alert in health_alerts
            ],
            "recommendations": recommendations,
            "alert_rules_enabled": any(
                rule.enabled for rule in alerts_service.alert_rules.values()
                if rule.alert_type.value == "health_check_failure"
            ),
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Health check alerts endpoint failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check alerts failed: {str(e)}")


@router.get("/alerts/summary")
async def health_check_alerts_summary():
    """
    Health check failure alerts summary endpoint.
    
    This endpoint provides a concise summary of health check failure monitoring status,
    including current failure count, alert status, and overall health trend.
    
    Returns:
        Concise health check failure monitoring summary
    """
    try:
        alerts_service = get_startup_alerts_service()
        
        if not alerts_service:
            return JSONResponse(
                content={
                    "status": "unavailable",
                    "message": "Health check failure monitoring not initialized",
                    "timestamp": datetime.now().isoformat()
                },
                status_code=503
            )
        
        # Get basic health check status
        consecutive_failures = alerts_service._consecutive_health_failures
        last_check_time = alerts_service._last_health_check_time
        threshold = alerts_service.default_thresholds["health_check_failure_threshold"].threshold_value
        
        # Calculate health score (0-100)
        health_score = 100
        if consecutive_failures > 0:
            health_score = max(0, 100 - (consecutive_failures * 25))
        
        # Determine health trend
        recent_alerts = alerts_service.get_alert_history(hours=6)
        health_alerts = [
            alert for alert in recent_alerts
            if alert.alert_type.value == "health_check_failure"
        ]
        
        if len(health_alerts) == 0:
            trend = "stable"
        elif len(health_alerts) >= 3:
            trend = "degrading"
        elif consecutive_failures == 0:
            trend = "improving"
        else:
            trend = "concerning"
        
        # Get active alerts count
        active_alerts = alerts_service.get_active_alerts()
        active_health_alerts = len([
            alert for alert in active_alerts
            if alert.alert_type.value == "health_check_failure"
        ])
        
        response = {
            "health_score": health_score,
            "health_grade": (
                "excellent" if health_score >= 90 else
                "good" if health_score >= 70 else
                "concerning" if health_score >= 50 else
                "critical"
            ),
            "consecutive_failures": consecutive_failures,
            "failure_threshold": threshold,
            "threshold_exceeded": consecutive_failures >= threshold,
            "active_alerts": active_health_alerts,
            "trend": trend,
            "last_check_time": last_check_time.isoformat() if last_check_time else None,
            "monitoring_active": alerts_service._is_monitoring,
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Health check alerts summary failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check alerts summary failed: {str(e)}")


@router.post("/alerts/test")
async def test_health_check_failure_alert():
    """
    Test health check failure alert endpoint.
    
    This endpoint allows testing the health check failure alerting system
    by simulating a health check failure and triggering the alert mechanism.
    
    Returns:
        Test result and alert trigger status
    """
    try:
        alerts_service = get_startup_alerts_service()
        
        if not alerts_service:
            return JSONResponse(
                content={
                    "status": "unavailable",
                    "message": "Health check failure monitoring not initialized",
                    "timestamp": datetime.now().isoformat()
                },
                status_code=503
            )
        
        # Record a test health check failure
        await alerts_service.record_health_check_result(False, 5000.0)  # 5 second timeout
        
        # Get current failure count
        consecutive_failures = alerts_service._consecutive_health_failures
        threshold = alerts_service.default_thresholds["health_check_failure_threshold"].threshold_value
        
        # Check if alert would be triggered
        alert_triggered = consecutive_failures >= threshold
        
        response = {
            "test_status": "completed",
            "test_failure_recorded": True,
            "consecutive_failures": consecutive_failures,
            "failure_threshold": threshold,
            "alert_triggered": alert_triggered,
            "message": (
                f"Test health check failure recorded. Consecutive failures: {consecutive_failures}. "
                f"Alert {'triggered' if alert_triggered else 'not triggered'} (threshold: {threshold})."
            ),
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Health check failure alert test failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failure alert test failed: {str(e)}")


@router.post("/alerts/reset")
async def reset_health_check_failures():
    """
    Reset health check failure counter endpoint.
    
    This endpoint allows resetting the consecutive health check failure counter,
    which can be useful for testing or after resolving health check issues.
    
    Returns:
        Reset operation status
    """
    try:
        alerts_service = get_startup_alerts_service()
        
        if not alerts_service:
            return JSONResponse(
                content={
                    "status": "unavailable",
                    "message": "Health check failure monitoring not initialized",
                    "timestamp": datetime.now().isoformat()
                },
                status_code=503
            )
        
        # Record a successful health check to reset the counter
        await alerts_service.record_health_check_result(True, 100.0)  # 100ms response time
        
        response = {
            "reset_status": "completed",
            "consecutive_failures": alerts_service._consecutive_health_failures,
            "message": "Health check failure counter has been reset to 0.",
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Health check failure reset failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failure reset failed: {str(e)}")



@router.get("/databases")
async def database_initialization_status():
    """
    Database initialization status endpoint.
    
    This endpoint provides information about the asynchronous database initialization process,
    including OpenSearch and Neptune connection status.
    
    This is separate from the /health/simple endpoint to ensure health checks
    don't depend on database connectivity.
    
    Returns:
        Database initialization status and details
    """
    try:
        from ...startup.async_database_init import get_async_db_init_manager
        
        manager = get_async_db_init_manager()
        status = manager.get_status()
        
        response = {
            "database_initialization": status,
            "opensearch_ready": manager.is_opensearch_ready(),
            "neptune_ready": manager.is_neptune_ready(),
            "any_database_ready": manager.is_any_database_ready(),
            "timestamp": datetime.now().isoformat()
        }
        
        return response
        
    except Exception as e:
        logger.error(f"Database status check failed: {e}")
        return JSONResponse(
            content={
                "status": "error",
                "error": str(e),
                "message": "Database initialization manager not available",
                "timestamp": datetime.now().isoformat()
            },
            status_code=500
        )


@router.get("/databases/local")
async def local_database_health_check():
    """
    Local development database health check endpoint.
    
    This endpoint provides a simplified view of local database health status.
    For comprehensive local health checks, use /api/health/local/ endpoints.
    
    This endpoint is only available when ML_ENVIRONMENT=local.
    
    Returns:
        Basic local database health status
    """
    import os

    # Only available in local development environment
    if os.getenv("ML_ENVIRONMENT", "local") != "local":
        return JSONResponse(
            content={
                "status": "unavailable",
                "message": "Local database health check only available in local development environment",
                "environment": os.getenv("ML_ENVIRONMENT", "unknown"),
                "comprehensive_endpoint": "/api/health/local/",
                "timestamp": datetime.now().isoformat()
            },
            status_code=404
        )
    
    try:
        # Import the comprehensive local health check
        from .health_local import (
            comprehensive_local_health_check,
            get_local_database_factory,
        )

        # Get database factory
        factory = await get_local_database_factory()
        
        # Run comprehensive check
        health_result = await comprehensive_local_health_check(factory)
        
        # Extract simplified status for backward compatibility
        if hasattr(health_result, 'body'):
            import json
            health_data = json.loads(health_result.body)
        else:
            health_data = health_result
        
        # Create simplified response
        simplified_status = {
            "environment": "local",
            "overall_status": health_data.get("overall_status", "unknown"),
            "databases": {},
            "summary": health_data.get("summary", {}),
            "comprehensive_endpoint": "/api/health/local/",
            "timestamp": datetime.now().isoformat()
        }
        
        # Extract service statuses
        services = health_data.get("services", {})
        for service_name, service_info in services.items():
            simplified_status["databases"][service_name] = {
                "status": service_info.get("status", "unknown"),
                "error": service_info.get("error")
            }
        
        # Add recommendations if any
        if health_data.get("recommendations"):
            simplified_status["recommendations"] = health_data["recommendations"][:3]  # Limit to 3
            simplified_status["recommendations"].append("Use /api/health/local/ for detailed diagnostics")
        
        # Return appropriate HTTP status code
        status_code = 200 if simplified_status["overall_status"] in ["healthy", "degraded"] else 503
        
        return JSONResponse(content=simplified_status, status_code=status_code)
        
    except Exception as e:
        logger.error(f"Local database health check failed: {e}")
        return JSONResponse(
            content={
                "environment": "local",
                "overall_status": "error",
                "error": str(e),
                "comprehensive_endpoint": "/api/health/local/",
                "timestamp": datetime.now().isoformat()
            },
            status_code=503
        )
