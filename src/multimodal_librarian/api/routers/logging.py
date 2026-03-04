"""
Logging API router for accessing and managing comprehensive logging data.

This router provides endpoints for:
- Viewing structured logs
- Performance metrics
- Business metrics
- Error tracking
- Distributed tracing
- Log export functionality
"""

from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional, List, Dict, Any
from datetime import datetime

from ...monitoring.logging_service import get_logging_service
from ...logging_config import get_logger
from ..models import SuccessResponse

router = APIRouter(prefix="/api/logging", tags=["logging"])
logger = get_logger("logging_api")


@router.get("/health")
async def get_logging_health():
    """Get logging service health status."""
    try:
        logging_service = get_logging_service()
        
        # Get basic stats
        logs = logging_service.get_logs(hours=1, limit=10)
        performance = logging_service.get_performance_metrics(hours=1)
        errors = logging_service.get_error_summary(hours=1)
        traces = logging_service.get_trace_summary(hours=1)
        
        return {
            "status": "healthy",
            "service": "logging_service",
            "components": {
                "structured_logging": "ok",
                "performance_tracking": "ok",
                "error_tracking": "ok",
                "distributed_tracing": "ok",
                "business_metrics": "ok"
            },
            "recent_activity": {
                "logs_last_hour": len(logs),
                "performance_metrics_available": "performance" in performance and performance.get("total_operations", 0) > 0,
                "errors_last_hour": errors.get("recent_errors_count", 0),
                "traces_last_hour": traces.get("total_traces", 0) if "error" not in traces else 0
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get logging health: {e}")
        raise HTTPException(status_code=500, detail=f"Logging health check failed: {str(e)}")


@router.get("/logs")
async def get_logs(
    service: Optional[str] = Query(None, description="Filter by service name"),
    operation: Optional[str] = Query(None, description="Filter by operation name"),
    level: Optional[str] = Query(None, description="Filter by log level (INFO, WARNING, ERROR, DEBUG)"),
    trace_id: Optional[str] = Query(None, description="Filter by trace ID"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    hours: int = Query(24, description="Time period in hours", ge=1, le=168),
    limit: int = Query(100, description="Maximum number of logs to return", ge=1, le=10000)
):
    """Get filtered structured logs."""
    try:
        logging_service = get_logging_service()
        
        logs = logging_service.get_logs(
            service=service,
            operation=operation,
            level=level,
            trace_id=trace_id,
            user_id=user_id,
            hours=hours,
            limit=limit
        )
        
        return {
            "logs": logs,
            "filters": {
                "service": service,
                "operation": operation,
                "level": level,
                "trace_id": trace_id,
                "user_id": user_id,
                "hours": hours,
                "limit": limit
            },
            "total_returned": len(logs),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get logs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve logs: {str(e)}")


@router.get("/performance")
async def get_performance_metrics(
    service: Optional[str] = Query(None, description="Filter by service name"),
    operation: Optional[str] = Query(None, description="Filter by operation name"),
    hours: int = Query(24, description="Time period in hours", ge=1, le=168)
):
    """Get performance metrics summary."""
    try:
        logging_service = get_logging_service()
        
        metrics = logging_service.get_performance_metrics(
            service=service,
            operation=operation,
            hours=hours
        )
        
        return {
            "performance_metrics": metrics,
            "filters": {
                "service": service,
                "operation": operation,
                "hours": hours
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get performance metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve performance metrics: {str(e)}")


@router.get("/business-metrics")
async def get_business_metrics(
    metric_name: Optional[str] = Query(None, description="Filter by metric name"),
    hours: int = Query(24, description="Time period in hours", ge=1, le=168)
):
    """Get business metrics summary."""
    try:
        logging_service = get_logging_service()
        
        metrics = logging_service.get_business_metrics(
            metric_name=metric_name,
            hours=hours
        )
        
        return {
            "business_metrics": metrics,
            "filters": {
                "metric_name": metric_name,
                "hours": hours
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get business metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve business metrics: {str(e)}")


@router.get("/errors")
async def get_error_summary(
    hours: int = Query(24, description="Time period in hours", ge=1, le=168)
):
    """Get error summary and patterns."""
    try:
        logging_service = get_logging_service()
        
        error_summary = logging_service.get_error_summary(hours=hours)
        
        return {
            "error_summary": error_summary,
            "filters": {
                "hours": hours
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get error summary: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve error summary: {str(e)}")


@router.get("/traces")
async def get_trace_summary(
    trace_id: Optional[str] = Query(None, description="Specific trace ID to retrieve"),
    hours: int = Query(24, description="Time period in hours", ge=1, le=168)
):
    """Get distributed tracing summary or specific trace details."""
    try:
        logging_service = get_logging_service()
        
        trace_data = logging_service.get_trace_summary(
            trace_id=trace_id,
            hours=hours
        )
        
        return {
            "trace_data": trace_data,
            "filters": {
                "trace_id": trace_id,
                "hours": hours
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get trace summary: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve trace data: {str(e)}")


@router.get("/operations")
async def get_operation_stats():
    """Get operation performance statistics."""
    try:
        logging_service = get_logging_service()
        
        stats = logging_service.get_operation_stats()
        
        return {
            "operation_stats": stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get operation stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve operation statistics: {str(e)}")


@router.post("/export")
async def export_logs(
    hours: int = Query(24, description="Time period in hours to export", ge=1, le=168),
    format: str = Query("json", description="Export format (currently only json supported)")
):
    """Export logs to file."""
    try:
        if format != "json":
            raise HTTPException(status_code=400, detail="Only JSON format is currently supported")
        
        logging_service = get_logging_service()
        
        # Generate export
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filepath = f"logs_export_{timestamp}.json"
        
        exported_filepath = logging_service.export_logs(filepath=filepath, hours=hours)
        
        return SuccessResponse(
            message=f"Logs exported successfully for {hours} hours",
            details={
                "filepath": exported_filepath,
                "format": format,
                "hours": hours,
                "export_timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to export logs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export logs: {str(e)}")


@router.post("/trace/start")
async def start_trace(
    service: str = Query(..., description="Service name"),
    operation: str = Query(..., description="Operation name"),
    parent_trace_id: Optional[str] = Query(None, description="Parent trace ID"),
    parent_span_id: Optional[str] = Query(None, description="Parent span ID")
):
    """Start a new distributed trace."""
    try:
        logging_service = get_logging_service()
        
        trace_id = logging_service.create_trace(
            service=service,
            operation=operation,
            parent_trace_id=parent_trace_id,
            parent_span_id=parent_span_id
        )
        
        return SuccessResponse(
            message="Trace started successfully",
            details={
                "trace_id": trace_id,
                "service": service,
                "operation": operation,
                "parent_trace_id": parent_trace_id,
                "parent_span_id": parent_span_id,
                "start_timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to start trace: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start trace: {str(e)}")


@router.post("/trace/{trace_id}/finish")
async def finish_trace(
    trace_id: str,
    error: bool = Query(False, description="Whether the trace ended with an error"),
    error_message: Optional[str] = Query(None, description="Error message if error occurred")
):
    """Finish a distributed trace."""
    try:
        logging_service = get_logging_service()
        
        logging_service.finish_trace(
            trace_id=trace_id,
            error=error,
            error_message=error_message
        )
        
        return SuccessResponse(
            message="Trace finished successfully",
            details={
                "trace_id": trace_id,
                "error": error,
                "error_message": error_message,
                "finish_timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to finish trace: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to finish trace: {str(e)}")


@router.post("/log")
async def log_structured_entry(
    level: str = Query(..., description="Log level (INFO, WARNING, ERROR, DEBUG)"),
    service: str = Query(..., description="Service name"),
    operation: str = Query(..., description="Operation name"),
    message: str = Query(..., description="Log message"),
    trace_id: Optional[str] = Query(None, description="Trace ID"),
    span_id: Optional[str] = Query(None, description="Span ID"),
    user_id: Optional[str] = Query(None, description="User ID"),
    session_id: Optional[str] = Query(None, description="Session ID"),
    duration_ms: Optional[float] = Query(None, description="Operation duration in milliseconds"),
    metadata: Optional[Dict[str, Any]] = None
):
    """Log a structured entry."""
    try:
        if level.upper() not in ['INFO', 'WARNING', 'ERROR', 'DEBUG']:
            raise HTTPException(status_code=400, detail="Invalid log level")
        
        logging_service = get_logging_service()
        
        logging_service.log_structured(
            level=level,
            service=service,
            operation=operation,
            message=message,
            trace_id=trace_id,
            span_id=span_id,
            user_id=user_id,
            session_id=session_id,
            duration_ms=duration_ms,
            metadata=metadata
        )
        
        return SuccessResponse(
            message="Log entry recorded successfully",
            details={
                "level": level.upper(),
                "service": service,
                "operation": operation,
                "message": message,
                "trace_id": trace_id,
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to log structured entry: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to log entry: {str(e)}")


@router.post("/business-metric")
async def log_business_metric_endpoint(
    metric_name: str = Query(..., description="Metric name"),
    metric_value: float = Query(..., description="Metric value"),
    metric_type: str = Query("counter", description="Metric type (counter, gauge, histogram)"),
    tags: Optional[Dict[str, str]] = None,
    trace_id: Optional[str] = Query(None, description="Trace ID")
):
    """Log a business metric."""
    try:
        if metric_type not in ['counter', 'gauge', 'histogram']:
            raise HTTPException(status_code=400, detail="Invalid metric type")
        
        logging_service = get_logging_service()
        
        logging_service.log_business_metric(
            metric_name=metric_name,
            metric_value=metric_value,
            metric_type=metric_type,
            tags=tags,
            trace_id=trace_id
        )
        
        return SuccessResponse(
            message="Business metric recorded successfully",
            details={
                "metric_name": metric_name,
                "metric_value": metric_value,
                "metric_type": metric_type,
                "tags": tags,
                "trace_id": trace_id,
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to log business metric: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to log business metric: {str(e)}")


@router.get("/dashboard")
async def get_logging_dashboard():
    """Get comprehensive logging dashboard data."""
    try:
        logging_service = get_logging_service()
        
        # Get data for dashboard
        recent_logs = logging_service.get_logs(hours=1, limit=50)
        performance_1h = logging_service.get_performance_metrics(hours=1)
        performance_24h = logging_service.get_performance_metrics(hours=24)
        business_metrics = logging_service.get_business_metrics(hours=24)
        error_summary = logging_service.get_error_summary(hours=24)
        trace_summary = logging_service.get_trace_summary(hours=24)
        operation_stats = logging_service.get_operation_stats()
        
        return {
            "dashboard_data": {
                "recent_logs": recent_logs,
                "performance": {
                    "last_hour": performance_1h,
                    "last_24_hours": performance_24h
                },
                "business_metrics": business_metrics,
                "error_summary": error_summary,
                "trace_summary": trace_summary,
                "operation_stats": operation_stats
            },
            "summary": {
                "total_recent_logs": len(recent_logs),
                "performance_available": "error" not in performance_24h,
                "business_metrics_available": "error" not in business_metrics,
                "errors_24h": error_summary.get("recent_errors_count", 0),
                "traces_24h": trace_summary.get("total_traces", 0) if "error" not in trace_summary else 0,
                "operations_tracked": operation_stats.get("total_operations", 0)
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get logging dashboard: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard data: {str(e)}")