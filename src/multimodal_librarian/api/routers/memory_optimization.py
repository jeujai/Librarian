"""
Memory optimization API endpoints.

This module provides REST API endpoints for:
- Memory usage monitoring
- Memory leak detection
- Garbage collection optimization
- Memory profiling and analysis
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, List, Optional, Any
from datetime import datetime
import asyncio

from ...monitoring.memory_optimizer import MemoryOptimizer
from ...logging_config import get_logger

# Initialize router and logger
router = APIRouter(prefix="/api/memory", tags=["memory-optimization"])
logger = get_logger("memory_optimization_api")

# Global memory optimizer instance
memory_optimizer = None


def get_memory_optimizer() -> MemoryOptimizer:
    """Get or create memory optimizer instance."""
    global memory_optimizer
    if memory_optimizer is None:
        memory_optimizer = MemoryOptimizer()
    return memory_optimizer


@router.get("/status")
async def get_memory_status() -> Dict[str, Any]:
    """
    Get current memory status and statistics.
    
    Returns comprehensive memory usage information including:
    - System and process memory usage
    - Garbage collection statistics
    - Memory trends and leak detection
    - Top memory consumers
    """
    try:
        optimizer = get_memory_optimizer()
        status = optimizer.get_memory_status()
        
        return {
            "success": True,
            "data": status,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting memory status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get memory status: {str(e)}")


@router.post("/optimize")
async def optimize_memory(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    Perform comprehensive memory optimization.
    
    Executes various memory optimization techniques including:
    - Garbage collection optimization
    - Memory cache clearing
    - Weak reference cleanup
    """
    try:
        optimizer = get_memory_optimizer()
        
        # Run optimization in background to avoid blocking
        def run_optimization():
            return optimizer.optimize_memory()
        
        # Execute optimization
        optimization_results = await asyncio.get_event_loop().run_in_executor(
            None, run_optimization
        )
        
        return {
            "success": True,
            "data": optimization_results,
            "message": "Memory optimization completed successfully"
        }
        
    except Exception as e:
        logger.error(f"Error during memory optimization: {e}")
        raise HTTPException(status_code=500, detail=f"Memory optimization failed: {str(e)}")


@router.get("/report")
async def get_memory_report() -> Dict[str, Any]:
    """
    Generate comprehensive memory usage report.
    
    Returns detailed memory analysis including:
    - Current memory status
    - Historical usage data
    - Memory optimization recommendations
    - Health score assessment
    """
    try:
        optimizer = get_memory_optimizer()
        report = optimizer.get_memory_report()
        
        return {
            "success": True,
            "data": report,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error generating memory report: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate memory report: {str(e)}")


@router.get("/leaks")
async def get_memory_leaks(hours: int = 24) -> Dict[str, Any]:
    """
    Get detected memory leaks within the specified time period.
    
    Args:
        hours: Number of hours to look back for leak detection (default: 24)
    
    Returns:
        List of detected memory leaks with severity and details
    """
    try:
        if hours < 1 or hours > 168:  # Max 1 week
            raise HTTPException(status_code=400, detail="Hours must be between 1 and 168")
        
        optimizer = get_memory_optimizer()
        leaks = optimizer.leak_detector.get_detected_leaks(hours)
        
        # Categorize leaks by severity
        leak_summary = {
            'critical': [leak for leak in leaks if leak['severity'] == 'critical'],
            'high': [leak for leak in leaks if leak['severity'] == 'high'],
            'medium': [leak for leak in leaks if leak['severity'] == 'medium'],
            'low': [leak for leak in leaks if leak['severity'] == 'low']
        }
        
        return {
            "success": True,
            "data": {
                "time_period_hours": hours,
                "total_leaks": len(leaks),
                "leaks_by_severity": {
                    severity: len(leak_list) 
                    for severity, leak_list in leak_summary.items()
                },
                "detected_leaks": leaks,
                "leak_summary": leak_summary
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting memory leaks: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get memory leaks: {str(e)}")


@router.get("/gc/stats")
async def get_gc_statistics() -> Dict[str, Any]:
    """
    Get garbage collection statistics and performance metrics.
    
    Returns:
        Detailed GC statistics including generation counts,
        collection performance, and tuning parameters
    """
    try:
        optimizer = get_memory_optimizer()
        gc_stats = optimizer.gc_optimizer.get_gc_statistics()
        
        return {
            "success": True,
            "data": gc_stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting GC statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get GC statistics: {str(e)}")


@router.post("/gc/optimize")
async def optimize_garbage_collection() -> Dict[str, Any]:
    """
    Perform garbage collection optimization.
    
    Executes optimized garbage collection for all generations
    and returns performance metrics.
    """
    try:
        optimizer = get_memory_optimizer()
        
        # Run GC optimization in executor to avoid blocking
        def run_gc_optimization():
            return optimizer.gc_optimizer.optimize_garbage_collection()
        
        optimizations = await asyncio.get_event_loop().run_in_executor(
            None, run_gc_optimization
        )
        
        # Calculate summary statistics
        total_objects_collected = sum(opt.objects_collected for opt in optimizations)
        total_memory_freed = sum(opt.memory_freed_mb for opt in optimizations)
        total_time_taken = sum(opt.time_taken_ms for opt in optimizations)
        
        return {
            "success": True,
            "data": {
                "optimizations": [
                    {
                        "generation": opt.generation,
                        "objects_collected": opt.objects_collected,
                        "memory_freed_mb": opt.memory_freed_mb,
                        "time_taken_ms": opt.time_taken_ms,
                        "optimization_applied": opt.optimization_applied
                    }
                    for opt in optimizations
                ],
                "summary": {
                    "total_objects_collected": total_objects_collected,
                    "total_memory_freed_mb": round(total_memory_freed, 2),
                    "total_time_taken_ms": round(total_time_taken, 2),
                    "generations_optimized": len(optimizations)
                }
            },
            "message": f"GC optimization completed: {total_objects_collected} objects collected, {total_memory_freed:.2f} MB freed"
        }
        
    except Exception as e:
        logger.error(f"Error during GC optimization: {e}")
        raise HTTPException(status_code=500, detail=f"GC optimization failed: {str(e)}")


@router.put("/gc/tune")
async def tune_gc_thresholds(
    generation_0: Optional[int] = None,
    generation_1: Optional[int] = None,
    generation_2: Optional[int] = None
) -> Dict[str, Any]:
    """
    Tune garbage collection thresholds for better performance.
    
    Args:
        generation_0: Threshold for generation 0 (default: 700)
        generation_1: Threshold for generation 1 (default: 10)
        generation_2: Threshold for generation 2 (default: 10)
    
    Returns:
        Success status and updated threshold values
    """
    try:
        # Validate threshold values
        if generation_0 is not None and (generation_0 < 100 or generation_0 > 10000):
            raise HTTPException(status_code=400, detail="Generation 0 threshold must be between 100 and 10000")
        
        if generation_1 is not None and (generation_1 < 1 or generation_1 > 100):
            raise HTTPException(status_code=400, detail="Generation 1 threshold must be between 1 and 100")
        
        if generation_2 is not None and (generation_2 < 1 or generation_2 > 100):
            raise HTTPException(status_code=400, detail="Generation 2 threshold must be between 1 and 100")
        
        optimizer = get_memory_optimizer()
        success = optimizer.gc_optimizer.tune_gc_thresholds(generation_0, generation_1, generation_2)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update GC thresholds")
        
        # Get updated statistics
        updated_stats = optimizer.gc_optimizer.get_gc_statistics()
        
        return {
            "success": True,
            "data": {
                "updated_thresholds": updated_stats.get('tuning_parameters', {}),
                "current_state": updated_stats.get('current_state', {})
            },
            "message": "GC thresholds updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error tuning GC thresholds: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to tune GC thresholds: {str(e)}")


@router.get("/profiling/top-consumers")
async def get_top_memory_consumers(limit: int = 10) -> Dict[str, Any]:
    """
    Get top memory consuming objects from profiling data.
    
    Args:
        limit: Maximum number of top consumers to return (default: 10)
    
    Returns:
        List of top memory consuming objects with file and line information
    """
    try:
        if limit < 1 or limit > 100:
            raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")
        
        optimizer = get_memory_optimizer()
        top_consumers = optimizer.profiler.get_top_memory_consumers(limit)
        
        return {
            "success": True,
            "data": {
                "limit": limit,
                "top_consumers": top_consumers,
                "total_consumers": len(top_consumers)
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting top memory consumers: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get top memory consumers: {str(e)}")


@router.get("/profiling/snapshot-comparison")
async def compare_memory_snapshots(
    snapshot1_idx: int = -2,
    snapshot2_idx: int = -1
) -> Dict[str, Any]:
    """
    Compare two memory snapshots to detect changes.
    
    Args:
        snapshot1_idx: Index of first snapshot (default: -2, second to last)
        snapshot2_idx: Index of second snapshot (default: -1, last)
    
    Returns:
        Comparison results showing memory changes between snapshots
    """
    try:
        optimizer = get_memory_optimizer()
        comparison = optimizer.profiler.compare_snapshots(snapshot1_idx, snapshot2_idx)
        
        if 'error' in comparison:
            raise HTTPException(status_code=400, detail=comparison['error'])
        
        return {
            "success": True,
            "data": comparison,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error comparing memory snapshots: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to compare memory snapshots: {str(e)}")


@router.get("/health")
async def get_memory_health() -> Dict[str, Any]:
    """
    Get memory health status and score.
    
    Returns:
        Memory health assessment with score and recommendations
    """
    try:
        optimizer = get_memory_optimizer()
        memory_status = optimizer.get_memory_status()
        health_score = optimizer._calculate_memory_health_score(memory_status)
        
        return {
            "success": True,
            "data": {
                "health_score": health_score,
                "memory_summary": {
                    "system_usage_percent": memory_status.get('system_memory', {}).get('usage_percent', 0),
                    "process_usage_mb": memory_status.get('process_memory', {}).get('used_mb', 0),
                    "detected_leaks": len(memory_status.get('detected_leaks', [])),
                    "monitoring_active": memory_status.get('monitoring_status') == 'active'
                }
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting memory health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get memory health: {str(e)}")


@router.post("/monitoring/start")
async def start_memory_monitoring() -> Dict[str, Any]:
    """
    Start memory monitoring if not already active.
    
    Returns:
        Success status and monitoring information
    """
    try:
        optimizer = get_memory_optimizer()
        
        if optimizer._monitoring_active:
            return {
                "success": True,
                "message": "Memory monitoring is already active",
                "data": {"monitoring_active": True}
            }
        
        # Restart monitoring
        optimizer._start_monitoring()
        
        return {
            "success": True,
            "message": "Memory monitoring started successfully",
            "data": {"monitoring_active": True}
        }
        
    except Exception as e:
        logger.error(f"Error starting memory monitoring: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start memory monitoring: {str(e)}")


@router.post("/monitoring/stop")
async def stop_memory_monitoring() -> Dict[str, Any]:
    """
    Stop memory monitoring.
    
    Returns:
        Success status and monitoring information
    """
    try:
        optimizer = get_memory_optimizer()
        optimizer.stop_monitoring()
        
        return {
            "success": True,
            "message": "Memory monitoring stopped successfully",
            "data": {"monitoring_active": False}
        }
        
    except Exception as e:
        logger.error(f"Error stopping memory monitoring: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop memory monitoring: {str(e)}")


@router.get("/recommendations")
async def get_memory_recommendations() -> Dict[str, Any]:
    """
    Get memory optimization recommendations based on current usage patterns.
    
    Returns:
        List of actionable recommendations for memory optimization
    """
    try:
        optimizer = get_memory_optimizer()
        memory_status = optimizer.get_memory_status()
        recommendations = optimizer._generate_memory_recommendations(memory_status)
        
        # Categorize recommendations by severity
        recommendations_by_severity = {
            'critical': [rec for rec in recommendations if rec.get('severity') == 'critical'],
            'high': [rec for rec in recommendations if rec.get('severity') == 'high'],
            'medium': [rec for rec in recommendations if rec.get('severity') == 'medium'],
            'low': [rec for rec in recommendations if rec.get('severity') == 'low']
        }
        
        return {
            "success": True,
            "data": {
                "total_recommendations": len(recommendations),
                "recommendations_by_severity": {
                    severity: len(rec_list) 
                    for severity, rec_list in recommendations_by_severity.items()
                },
                "recommendations": recommendations,
                "categorized_recommendations": recommendations_by_severity
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting memory recommendations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get memory recommendations: {str(e)}")