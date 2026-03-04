"""
Cold Start Optimized Health Check Router

This module provides ultra-fast health check endpoints optimized for
cold start scenarios. These endpoints respond immediately without
waiting for full application initialization.
"""

import time
import asyncio
import os
from typing import Dict, Any, Optional
from fastapi import APIRouter, Response, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime

from ...startup.cold_start_optimizer import (
    get_cold_start_optimizer,
    is_cold_start_mode,
    get_startup_mode
)

router = APIRouter(prefix="/health", tags=["health", "cold-start"])


@router.get("/cold-start", include_in_schema=False)
async def cold_start_health_check():
    """
    Ultra-fast health check optimized for cold start scenarios.
    
    This endpoint:
    - Responds immediately (< 50ms)
    - Does not wait for services or models
    - Provides startup progress information
    - Works during all phases of startup
    """
    start_time = time.time()
    
    try:
        optimizer = get_cold_start_optimizer()
        
        # Basic health status
        health_status = {
            "status": "ok",
            "timestamp": datetime.now().isoformat(),
            "cold_start_mode": is_cold_start_mode(),
            "startup_mode": get_startup_mode(),
            "response_time_ms": 0  # Will be calculated at the end
        }
        
        # Add startup progress if in cold start mode
        if is_cold_start_mode():
            metrics = optimizer._get_startup_metrics()
            
            health_status.update({
                "startup_progress": {
                    "total_startup_time": metrics.get("total_startup_time", 0),
                    "health_check_ready": metrics.get("health_check_ready_time") is not None,
                    "essential_services_ready": metrics.get("essential_services_ready_time") is not None,
                    "models_loaded_count": metrics.get("models_loaded_count", 0),
                    "services_initialized_count": metrics.get("services_initialized_count", 0),
                    "background_tasks_active": metrics.get("background_tasks_active", 0)
                },
                "services": {
                    name: optimizer.is_service_ready(name)
                    for name in optimizer.critical_services
                },
                "phase": _determine_startup_phase(metrics)
            })
        
        # Calculate response time
        response_time = (time.time() - start_time) * 1000
        health_status["response_time_ms"] = round(response_time, 2)
        
        return JSONResponse(
            content=health_status,
            status_code=200,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "X-Health-Check-Type": "cold-start-optimized",
                "X-Response-Time-Ms": str(round(response_time, 2))
            }
        )
        
    except Exception as e:
        # Even if there's an error, return a basic health status
        response_time = (time.time() - start_time) * 1000
        
        return JSONResponse(
            content={
                "status": "ok",
                "timestamp": datetime.now().isoformat(),
                "cold_start_mode": is_cold_start_mode(),
                "startup_mode": get_startup_mode(),
                "response_time_ms": round(response_time, 2),
                "note": "Basic health check (optimizer unavailable)"
            },
            status_code=200,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "X-Health-Check-Type": "cold-start-basic",
                "X-Response-Time-Ms": str(round(response_time, 2))
            }
        )


@router.get("/startup-progress")
async def get_startup_progress():
    """
    Get detailed startup progress information.
    
    This endpoint provides comprehensive information about the
    startup process, including timing metrics and service status.
    """
    if not is_cold_start_mode():
        return {
            "cold_start_mode": False,
            "message": "Cold start optimization not enabled"
        }
    
    try:
        optimizer = get_cold_start_optimizer()
        metrics = optimizer._get_startup_metrics()
        
        # Get service statuses
        service_statuses = {}
        for service_name in optimizer.critical_services.union(optimizer.deferred_services):
            status = optimizer.get_service_status(service_name)
            service_statuses[service_name] = {
                "ready": optimizer.is_service_ready(service_name),
                "status": status.get("status") if status else "not_initialized",
                "initialized_at": status.get("initialized_at") if status else None
            }
        
        # Get model statuses
        model_statuses = {}
        for model_name in optimizer.essential_models.union(optimizer.deferred_models):
            model_statuses[model_name] = {
                "loaded": optimizer.is_model_loaded(model_name),
                "loaded_at": optimizer.metrics.models_loaded.get(model_name),
                "category": "essential" if model_name in optimizer.essential_models else "deferred"
            }
        
        return {
            "cold_start_mode": True,
            "startup_mode": get_startup_mode(),
            "phase": _determine_startup_phase(metrics),
            "metrics": metrics,
            "services": service_statuses,
            "models": model_statuses,
            "estimated_completion": _estimate_completion_time(metrics),
            "recommendations": _get_optimization_recommendations(metrics)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get startup progress: {str(e)}"
        )


@router.get("/readiness")
async def check_readiness():
    """
    Check if the application is ready to handle requests.
    
    This endpoint returns different readiness levels:
    - basic: Health checks work
    - functional: Core services available
    - full: All services and models loaded
    """
    if not is_cold_start_mode():
        return {
            "ready": True,
            "level": "full",
            "message": "Cold start optimization not enabled - assuming full readiness"
        }
    
    try:
        optimizer = get_cold_start_optimizer()
        metrics = optimizer._get_startup_metrics()
        
        # Determine readiness level
        readiness_level = "none"
        ready = False
        
        if metrics.get("health_check_ready_time") is not None:
            readiness_level = "basic"
            ready = True
            
            if metrics.get("essential_services_ready_time") is not None:
                readiness_level = "functional"
                
                if metrics.get("full_startup_complete_time") is not None:
                    readiness_level = "full"
        
        # Check critical services
        critical_services_ready = all(
            optimizer.is_service_ready(service)
            for service in optimizer.critical_services
        )
        
        return {
            "ready": ready and critical_services_ready,
            "level": readiness_level,
            "critical_services_ready": critical_services_ready,
            "essential_models_loaded": len([
                model for model in optimizer.essential_models
                if optimizer.is_model_loaded(model)
            ]),
            "total_essential_models": len(optimizer.essential_models),
            "startup_time": metrics.get("total_startup_time", 0),
            "phase": _determine_startup_phase(metrics)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to check readiness: {str(e)}"
        )


@router.get("/metrics")
async def get_cold_start_metrics():
    """
    Get detailed cold start performance metrics.
    
    This endpoint provides comprehensive timing and performance
    information for cold start optimization analysis.
    """
    if not is_cold_start_mode():
        return {
            "cold_start_mode": False,
            "message": "Cold start optimization not enabled"
        }
    
    try:
        optimizer = get_cold_start_optimizer()
        metrics = optimizer._get_startup_metrics()
        
        # Calculate additional metrics
        current_time = time.time()
        startup_start = optimizer.metrics.startup_start_time
        
        detailed_metrics = {
            "timing": {
                "startup_start_time": startup_start,
                "current_time": current_time,
                "total_elapsed": current_time - startup_start,
                "health_check_ready_time": metrics.get("health_check_ready_time"),
                "essential_services_ready_time": metrics.get("essential_services_ready_time"),
                "full_startup_complete_time": metrics.get("full_startup_complete_time")
            },
            "services": {
                "initialized_count": metrics.get("services_initialized_count", 0),
                "critical_services_count": len(optimizer.critical_services),
                "deferred_services_count": len(optimizer.deferred_services),
                "initialization_times": optimizer.metrics.services_initialized
            },
            "models": {
                "loaded_count": metrics.get("models_loaded_count", 0),
                "essential_models_count": len(optimizer.essential_models),
                "deferred_models_count": len(optimizer.deferred_models),
                "loading_times": optimizer.metrics.models_loaded
            },
            "background_tasks": {
                "active_count": metrics.get("background_tasks_active", 0),
                "total_started": len(optimizer._background_tasks)
            },
            "optimization_flags": {
                "cold_start_enabled": is_cold_start_mode(),
                "startup_mode": get_startup_mode(),
                "lazy_loading": os.getenv("LAZY_LOAD_MODELS", "true").lower() == "true",
                "parallel_init": os.getenv("PARALLEL_INIT", "true").lower() == "true"
            }
        }
        
        return detailed_metrics
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get cold start metrics: {str(e)}"
        )


def _determine_startup_phase(metrics: Dict[str, Any]) -> str:
    """Determine the current startup phase based on metrics."""
    if metrics.get("full_startup_complete_time") is not None:
        return "complete"
    elif metrics.get("essential_services_ready_time") is not None:
        return "functional"
    elif metrics.get("health_check_ready_time") is not None:
        return "basic"
    else:
        return "initializing"


def _estimate_completion_time(metrics: Dict[str, Any]) -> Optional[float]:
    """Estimate when startup will be complete."""
    startup_time = metrics.get("total_startup_time", 0)
    
    if metrics.get("full_startup_complete_time") is not None:
        return 0  # Already complete
    
    # Estimate based on current progress
    if metrics.get("essential_services_ready_time") is not None:
        # In functional phase, estimate 30-60 more seconds
        return max(0, 45 - startup_time)
    elif metrics.get("health_check_ready_time") is not None:
        # In basic phase, estimate 60-120 more seconds
        return max(0, 90 - startup_time)
    else:
        # Still initializing, estimate 120 seconds total
        return max(0, 120 - startup_time)


def _get_optimization_recommendations(metrics: Dict[str, Any]) -> List[str]:
    """Get recommendations for improving cold start performance."""
    recommendations = []
    
    startup_time = metrics.get("total_startup_time", 0)
    
    if startup_time > 60:
        recommendations.append("Consider enabling more aggressive lazy loading")
    
    if metrics.get("models_loaded_count", 0) == 0 and startup_time > 30:
        recommendations.append("Model loading may be slow - check network connectivity")
    
    if metrics.get("background_tasks_active", 0) > 5:
        recommendations.append("Many background tasks active - consider reducing parallelism")
    
    if not os.getenv("DOCKER_BUILDKIT"):
        recommendations.append("Enable Docker BuildKit for faster image builds")
    
    if not recommendations:
        recommendations.append("Cold start performance looks good!")
    
    return recommendations