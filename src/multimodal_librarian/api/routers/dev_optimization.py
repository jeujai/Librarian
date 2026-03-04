"""
Development Optimization API Router

This router provides endpoints for managing and monitoring development-specific
optimizations in the local development environment.
"""

import time
import asyncio
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from datetime import datetime

from ...development import (
    get_development_optimizer,
    apply_development_optimizations,
    is_development_optimization_enabled,
    get_optimization_recommendations
)

router = APIRouter(prefix="/dev", tags=["development", "optimization"])


@router.get("/optimization/status")
async def get_optimization_status():
    """
    Get the current status of development optimizations.
    
    Returns information about which optimizations are enabled,
    applied, and their performance impact.
    """
    if not is_development_optimization_enabled():
        return {
            "enabled": False,
            "message": "Development optimization is disabled"
        }
    
    try:
        optimizer = get_development_optimizer()
        status = optimizer.get_optimization_status()
        
        return {
            "enabled": True,
            "timestamp": datetime.now().isoformat(),
            "status": status,
            "system_metrics": optimizer.get_system_performance_metrics()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get optimization status: {str(e)}"
        )


@router.post("/optimization/apply")
async def apply_optimizations(background_tasks: BackgroundTasks):
    """
    Apply all available development optimizations.
    
    This endpoint triggers the application of various development-specific
    optimizations including memory, cache, workflow, and debugging optimizations.
    """
    if not is_development_optimization_enabled():
        raise HTTPException(
            status_code=400,
            detail="Development optimization is disabled"
        )
    
    try:
        # Apply optimizations in background
        result = await apply_development_optimizations()
        
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "result": result,
            "message": f"Applied {len(result.get('applied', []))} optimizations"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to apply optimizations: {str(e)}"
        )


@router.get("/optimization/recommendations")
async def get_recommendations():
    """
    Get optimization recommendations for the current environment.
    
    Analyzes the current system state and provides recommendations
    for improving development performance.
    """
    try:
        recommendations = get_optimization_recommendations()
        optimizer = get_development_optimizer()
        system_metrics = optimizer.get_system_performance_metrics()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "recommendations": recommendations,
            "system_metrics": system_metrics,
            "optimization_enabled": is_development_optimization_enabled()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get recommendations: {str(e)}"
        )


@router.get("/performance/metrics")
async def get_performance_metrics():
    """
    Get current system performance metrics.
    
    Returns detailed information about memory, CPU, and disk usage
    to help assess the impact of development optimizations.
    """
    try:
        optimizer = get_development_optimizer()
        metrics = optimizer.get_system_performance_metrics()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics,
            "optimization_status": optimizer.get_optimization_status()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get performance metrics: {str(e)}"
        )


@router.post("/performance/monitor")
async def monitor_performance(duration: int = 60):
    """
    Monitor performance impact over a specified duration.
    
    Args:
        duration: Monitoring duration in seconds (default: 60)
    
    Returns performance metrics before and after the monitoring period
    to assess the impact of optimizations.
    """
    if duration < 10 or duration > 300:
        raise HTTPException(
            status_code=400,
            detail="Duration must be between 10 and 300 seconds"
        )
    
    try:
        optimizer = get_development_optimizer()
        impact = await optimizer.monitor_performance_impact(duration)
        
        return {
            "timestamp": datetime.now().isoformat(),
            "monitoring_duration": duration,
            "performance_impact": impact,
            "recommendations": get_optimization_recommendations()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to monitor performance: {str(e)}"
        )


@router.get("/environment/info")
async def get_environment_info():
    """
    Get information about the development environment.
    
    Returns details about the current environment configuration,
    optimization settings, and system capabilities.
    """
    import os
    import sys
    import platform
    
    try:
        env_info = {
            "python_version": sys.version,
            "platform": platform.platform(),
            "architecture": platform.architecture(),
            "processor": platform.processor(),
            "environment_variables": {
                "ML_ENVIRONMENT": os.getenv("ML_ENVIRONMENT"),
                "DATABASE_TYPE": os.getenv("DATABASE_TYPE"),
                "DEBUG": os.getenv("DEBUG"),
                "LOG_LEVEL": os.getenv("LOG_LEVEL"),
                "DEV_OPTIMIZATION_ENABLED": os.getenv("DEV_OPTIMIZATION_ENABLED"),
                "DEV_MEMORY_OPTIMIZATION": os.getenv("DEV_MEMORY_OPTIMIZATION"),
                "DEV_CACHE_OPTIMIZATION": os.getenv("DEV_CACHE_OPTIMIZATION"),
                "DEV_WORKFLOW_OPTIMIZATION": os.getenv("DEV_WORKFLOW_OPTIMIZATION"),
                "COLD_START_OPTIMIZATION": os.getenv("COLD_START_OPTIMIZATION"),
                "STARTUP_MODE": os.getenv("STARTUP_MODE")
            },
            "optimization_status": {
                "development_optimization": is_development_optimization_enabled(),
                "cold_start_optimization": os.getenv("COLD_START_OPTIMIZATION", "false").lower() == "true"
            }
        }
        
        return {
            "timestamp": datetime.now().isoformat(),
            "environment": env_info
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get environment info: {str(e)}"
        )


@router.post("/cache/clear")
async def clear_development_cache():
    """
    Clear development-specific caches.
    
    This endpoint clears various caches used during development
    to ensure fresh state for testing and debugging.
    """
    try:
        import shutil
        from pathlib import Path
        
        cleared_caches = []
        
        # Clear Python cache
        pycache_dirs = [
            Path("/app/src").rglob("__pycache__"),
            Path("/app").rglob("*.pyc"),
            Path("/tmp/pycache")
        ]
        
        for cache_pattern in pycache_dirs:
            for cache_path in cache_pattern:
                if cache_path.exists():
                    if cache_path.is_dir():
                        shutil.rmtree(cache_path, ignore_errors=True)
                    else:
                        cache_path.unlink(missing_ok=True)
                    cleared_caches.append(str(cache_path))
        
        # Clear pytest cache
        pytest_cache = Path("/app/.pytest_cache")
        if pytest_cache.exists():
            shutil.rmtree(pytest_cache, ignore_errors=True)
            cleared_caches.append(str(pytest_cache))
        
        # Clear model cache (if requested)
        model_cache = Path("/app/.cache")
        if model_cache.exists():
            # Only clear temporary model files, not downloaded models
            temp_files = list(model_cache.rglob("*.tmp"))
            for temp_file in temp_files:
                temp_file.unlink(missing_ok=True)
                cleared_caches.append(str(temp_file))
        
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "cleared_caches": cleared_caches,
            "message": f"Cleared {len(cleared_caches)} cache items"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear cache: {str(e)}"
        )


@router.get("/debug/info")
async def get_debug_info():
    """
    Get debugging information for development.
    
    Returns information useful for debugging development issues,
    including system state, optimization status, and performance metrics.
    """
    try:
        optimizer = get_development_optimizer()
        
        debug_info = {
            "timestamp": datetime.now().isoformat(),
            "optimization_status": optimizer.get_optimization_status(),
            "system_metrics": optimizer.get_system_performance_metrics(),
            "recommendations": get_optimization_recommendations(),
            "environment": {
                "optimization_enabled": is_development_optimization_enabled(),
                "python_optimize": os.getenv("PYTHONOPTIMIZE"),
                "python_dont_write_bytecode": os.getenv("PYTHONDONTWRITEBYTECODE"),
                "development_mode": os.getenv("DEVELOPMENT_MODE"),
                "debug_enabled": os.getenv("DEBUG")
            }
        }
        
        return debug_info
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get debug info: {str(e)}"
        )


@router.post("/optimization/reset")
async def reset_optimizations():
    """
    Reset all development optimizations to default state.
    
    This endpoint resets optimization settings and clears any
    cached optimization state.
    """
    if not is_development_optimization_enabled():
        raise HTTPException(
            status_code=400,
            detail="Development optimization is disabled"
        )
    
    try:
        optimizer = get_development_optimizer()
        await optimizer.cleanup()
        
        # Reset environment variables to defaults
        default_settings = {
            "DEV_MEMORY_OPTIMIZATION": "true",
            "DEV_CACHE_OPTIMIZATION": "true", 
            "DEV_WORKFLOW_OPTIMIZATION": "true",
            "DEV_DEBUG_OPTIMIZATION": "true",
            "DEV_IMPORT_OPTIMIZATION": "true",
            "DEV_TEST_OPTIMIZATION": "true"
        }
        
        for key, value in default_settings.items():
            os.environ[key] = value
        
        return {
            "success": True,
            "timestamp": datetime.now().isoformat(),
            "message": "Development optimizations reset to defaults",
            "default_settings": default_settings
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset optimizations: {str(e)}"
        )