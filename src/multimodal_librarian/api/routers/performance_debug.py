"""
Performance Debugging API Router

Provides REST API endpoints for performance debugging and monitoring
in the local development environment.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional
import logging

from ...development.performance_debugger import get_performance_debugger, PerformanceDebugger
from ...config.local_config import LocalDatabaseConfig


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/debug/performance", tags=["performance-debug"])


def get_debugger() -> PerformanceDebugger:
    """Dependency to get performance debugger instance."""
    config = LocalDatabaseConfig()
    return get_performance_debugger(config)


@router.post("/monitoring/start")
async def start_monitoring(
    interval_seconds: int = Query(5, ge=1, le=60, description="Monitoring interval in seconds"),
    debugger: PerformanceDebugger = Depends(get_debugger)
) -> Dict[str, Any]:
    """
    Start performance monitoring.
    
    Args:
        interval_seconds: Monitoring interval in seconds (1-60)
        
    Returns:
        Status of monitoring start operation
    """
    try:
        result = await debugger.start_monitoring(interval_seconds)
        return result
    except Exception as e:
        logger.error(f"Error starting performance monitoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monitoring/stop")
async def stop_monitoring(
    debugger: PerformanceDebugger = Depends(get_debugger)
) -> Dict[str, Any]:
    """
    Stop performance monitoring.
    
    Returns:
        Status of monitoring stop operation with collected data summary
    """
    try:
        result = await debugger.stop_monitoring()
        return result
    except Exception as e:
        logger.error(f"Error stopping performance monitoring: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_performance_summary(
    last_minutes: int = Query(10, ge=1, le=60, description="Time range in minutes"),
    debugger: PerformanceDebugger = Depends(get_debugger)
) -> Dict[str, Any]:
    """
    Get performance summary for the specified time range.
    
    Args:
        last_minutes: Time range in minutes (1-60)
        
    Returns:
        Comprehensive performance summary including metrics, bottlenecks, and recommendations
    """
    try:
        summary = debugger.get_performance_summary(last_minutes)
        return summary
    except Exception as e:
        logger.error(f"Error getting performance summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics")
async def get_metrics(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of metrics to return"),
    metric_name: Optional[str] = Query(None, description="Filter by metric name"),
    debugger: PerformanceDebugger = Depends(get_debugger)
) -> Dict[str, Any]:
    """
    Get collected performance metrics.
    
    Args:
        limit: Maximum number of metrics to return
        metric_name: Optional filter by metric name
        
    Returns:
        List of performance metrics
    """
    try:
        metrics = debugger.metrics
        
        # Filter by metric name if specified
        if metric_name:
            metrics = [m for m in metrics if metric_name.lower() in m.name.lower()]
        
        # Apply limit
        metrics = metrics[-limit:]
        
        return {
            "metrics": [
                {
                    "name": m.name,
                    "value": m.value,
                    "unit": m.unit,
                    "timestamp": m.timestamp.isoformat(),
                    "context": m.context
                }
                for m in metrics
            ],
            "total_count": len(debugger.metrics),
            "filtered_count": len(metrics)
        }
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queries")
async def get_query_performance(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of queries to return"),
    database: Optional[str] = Query(None, description="Filter by database type"),
    debugger: PerformanceDebugger = Depends(get_debugger)
) -> Dict[str, Any]:
    """
    Get database query performance data.
    
    Args:
        limit: Maximum number of queries to return
        database: Optional filter by database type (postgresql, neo4j, milvus)
        
    Returns:
        List of query performance data
    """
    try:
        queries = debugger.query_data
        
        # Filter by database if specified
        if database:
            queries = [q for q in queries if q.database.lower() == database.lower()]
        
        # Apply limit
        queries = queries[-limit:]
        
        return {
            "queries": [
                {
                    "query_type": q.query_type,
                    "database": q.database,
                    "execution_time_ms": q.execution_time * 1000,
                    "rows_affected": q.rows_affected,
                    "timestamp": q.timestamp.isoformat(),
                    "parameters": q.parameters
                }
                for q in queries
            ],
            "total_count": len(debugger.query_data),
            "filtered_count": len(queries)
        }
    except Exception as e:
        logger.error(f"Error getting query performance data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resources")
async def get_resource_usage(
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of snapshots to return"),
    debugger: PerformanceDebugger = Depends(get_debugger)
) -> Dict[str, Any]:
    """
    Get system resource usage snapshots.
    
    Args:
        limit: Maximum number of snapshots to return
        
    Returns:
        List of resource usage snapshots
    """
    try:
        snapshots = debugger.resource_snapshots[-limit:]
        
        return {
            "snapshots": [
                {
                    "timestamp": s.timestamp.isoformat(),
                    "cpu_percent": s.cpu_percent,
                    "memory_percent": s.memory_percent,
                    "memory_used_mb": s.memory_used_mb,
                    "disk_io_read_mb": s.disk_io_read_mb,
                    "disk_io_write_mb": s.disk_io_write_mb,
                    "network_sent_mb": s.network_sent_mb,
                    "network_recv_mb": s.network_recv_mb,
                    "docker_containers": s.docker_containers
                }
                for s in snapshots
            ],
            "total_count": len(debugger.resource_snapshots),
            "returned_count": len(snapshots)
        }
    except Exception as e:
        logger.error(f"Error getting resource usage data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/measure")
async def measure_operation(
    operation_name: str,
    context: Optional[Dict[str, Any]] = None,
    debugger: PerformanceDebugger = Depends(get_debugger)
) -> Dict[str, Any]:
    """
    Start measuring a custom operation.
    
    This endpoint returns a measurement context that should be used
    with the /measure/stop endpoint to complete the measurement.
    
    Args:
        operation_name: Name of the operation to measure
        context: Optional context data for the measurement
        
    Returns:
        Measurement context information
    """
    try:
        # For API usage, we'll store the start time and return a token
        import time
        import uuid
        
        measurement_id = str(uuid.uuid4())
        start_time = time.time()
        
        # Store measurement context (in a real implementation, you'd use a proper cache)
        if not hasattr(debugger, '_active_measurements'):
            debugger._active_measurements = {}
        
        debugger._active_measurements[measurement_id] = {
            "operation_name": operation_name,
            "start_time": start_time,
            "context": context or {}
        }
        
        return {
            "measurement_id": measurement_id,
            "operation_name": operation_name,
            "started_at": start_time,
            "message": "Measurement started. Use /measure/stop to complete."
        }
    except Exception as e:
        logger.error(f"Error starting measurement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/measure/stop")
async def stop_measurement(
    measurement_id: str,
    debugger: PerformanceDebugger = Depends(get_debugger)
) -> Dict[str, Any]:
    """
    Stop measuring an operation and record the results.
    
    Args:
        measurement_id: ID returned from /measure endpoint
        
    Returns:
        Measurement results
    """
    try:
        import time
        
        if not hasattr(debugger, '_active_measurements'):
            raise HTTPException(status_code=404, detail="No active measurements found")
        
        if measurement_id not in debugger._active_measurements:
            raise HTTPException(status_code=404, detail="Measurement ID not found")
        
        measurement = debugger._active_measurements.pop(measurement_id)
        end_time = time.time()
        execution_time = end_time - measurement["start_time"]
        
        # Record the metric
        from ...development.performance_debugger import PerformanceMetric
        from datetime import datetime
        
        metric = PerformanceMetric(
            name=f"{measurement['operation_name']}_execution_time",
            value=execution_time * 1000,  # Convert to milliseconds
            unit="ms",
            timestamp=datetime.now(),
            context=measurement["context"]
        )
        
        debugger.metrics.append(metric)
        
        return {
            "measurement_id": measurement_id,
            "operation_name": measurement["operation_name"],
            "execution_time_ms": execution_time * 1000,
            "context": measurement["context"],
            "message": "Measurement completed and recorded"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error stopping measurement: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export")
async def export_metrics(
    filepath: str = Query(..., description="File path to export metrics"),
    format: str = Query("json", description="Export format (json)"),
    debugger: PerformanceDebugger = Depends(get_debugger)
) -> Dict[str, Any]:
    """
    Export collected performance data to file.
    
    Args:
        filepath: File path to export data
        format: Export format (currently only 'json' supported)
        
    Returns:
        Export operation status
    """
    try:
        result = debugger.export_metrics(filepath, format)
        return result
    except Exception as e:
        logger.error(f"Error exporting metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear")
async def clear_data(
    debugger: PerformanceDebugger = Depends(get_debugger)
) -> Dict[str, Any]:
    """
    Clear all collected performance data.
    
    Returns:
        Status of clear operation with counts of cleared data
    """
    try:
        result = debugger.clear_data()
        return result
    except Exception as e:
        logger.error(f"Error clearing data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_monitoring_status(
    debugger: PerformanceDebugger = Depends(get_debugger)
) -> Dict[str, Any]:
    """
    Get current monitoring status and data counts.
    
    Returns:
        Current monitoring status and collected data statistics
    """
    try:
        return {
            "monitoring_active": debugger.monitoring_active,
            "metrics_collected": len(debugger.metrics),
            "queries_analyzed": len(debugger.query_data),
            "resource_snapshots": len(debugger.resource_snapshots),
            "active_measurements": len(getattr(debugger, '_active_measurements', {}))
        }
    except Exception as e:
        logger.error(f"Error getting monitoring status: {e}")
        raise HTTPException(status_code=500, detail=str(e))