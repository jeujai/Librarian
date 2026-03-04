"""
Local Performance Metrics API Router

This module provides REST API endpoints for accessing local development
performance metrics, including real-time monitoring, historical data,
and performance optimization recommendations.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...monitoring.local_performance_metrics import (
    LocalPerformanceMetricsCollector,
    LocalServiceMetrics,
    LocalDevelopmentSession
)
from ...clients.database_factory import DatabaseClientFactory
from ...config.local_config import LocalDatabaseConfig
from ..dependencies.services import get_database_factory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/performance/local", tags=["local-performance"])

# Global collector instance (will be initialized when needed)
_global_collector: Optional[LocalPerformanceMetricsCollector] = None


class PerformanceSummaryResponse(BaseModel):
    """Response model for performance summary."""
    session_id: str
    collection_duration_seconds: float
    performance_score: float
    service_status: Dict[str, Any]
    session_metrics: Dict[str, Any]
    query_performance: Dict[str, Any]
    recommendations: List[str]


class ServiceMetricsResponse(BaseModel):
    """Response model for service metrics."""
    service_name: str
    container_name: Optional[str]
    timestamp: datetime
    status: str
    response_time_ms: Optional[float]
    cpu_percent: Optional[float]
    memory_usage_mb: Optional[float]
    connection_count: int
    custom_metrics: Dict[str, Any]


class SessionResponse(BaseModel):
    """Response model for development session."""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime]
    duration_seconds: Optional[float]
    performance_score: float
    avg_response_time_ms: float
    total_queries: int
    total_errors: int
    peak_memory_usage_mb: float
    avg_cpu_usage_percent: float
    container_restarts: int


async def get_local_performance_collector(
    factory: DatabaseClientFactory = Depends(get_database_factory)
) -> LocalPerformanceMetricsCollector:
    """Get or create the local performance metrics collector."""
    global _global_collector
    
    if _global_collector is None or not _global_collector.is_collecting:
        try:
            from ...monitoring.local_performance_metrics import start_local_performance_monitoring
            
            # Get local config
            config = factory.config
            if not hasattr(config, 'database_type') or config.database_type != 'local':
                raise HTTPException(
                    status_code=400,
                    detail="Local performance metrics are only available in local development mode"
                )
            
            _global_collector = await start_local_performance_monitoring(
                database_factory=factory,
                config=config
            )
            
        except Exception as e:
            logger.error(f"Failed to initialize local performance collector: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to initialize performance monitoring: {str(e)}"
            )
    
    return _global_collector


@router.get("/summary", response_model=PerformanceSummaryResponse)
async def get_performance_summary(
    collector: LocalPerformanceMetricsCollector = Depends(get_local_performance_collector)
):
    """
    Get comprehensive performance summary for local development environment.
    
    Returns current performance metrics, service status, and optimization recommendations.
    """
    try:
        summary = collector.get_performance_summary()
        return PerformanceSummaryResponse(**summary)
    except Exception as e:
        logger.error(f"Error getting performance summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services/{service_name}/metrics")
async def get_service_metrics(
    service_name: str,
    hours_back: int = Query(1, ge=1, le=24, description="Hours of history to retrieve"),
    collector: LocalPerformanceMetricsCollector = Depends(get_local_performance_collector)
):
    """
    Get performance metrics for a specific service.
    
    Args:
        service_name: Name of the service (postgres, neo4j, milvus, redis)
        hours_back: Number of hours of historical data to retrieve
    """
    if service_name not in collector.monitored_services:
        raise HTTPException(
            status_code=404,
            detail=f"Service '{service_name}' not found. Available services: {list(collector.monitored_services.keys())}"
        )
    
    try:
        cutoff_time = datetime.now() - timedelta(hours=hours_back)
        service_metrics = collector.service_metrics_history.get(service_name, [])
        
        # Filter by time range
        filtered_metrics = [
            m for m in service_metrics
            if m.timestamp >= cutoff_time
        ]
        
        # Convert to response format
        response_metrics = [
            ServiceMetricsResponse(
                service_name=m.service_name,
                container_name=m.container_name,
                timestamp=m.timestamp,
                status=m.status,
                response_time_ms=m.response_time_ms,
                cpu_percent=m.cpu_percent,
                memory_usage_mb=m.memory_usage_mb,
                connection_count=m.connection_count,
                custom_metrics=m.custom_metrics
            )
            for m in filtered_metrics
        ]
        
        return {
            "service_name": service_name,
            "metrics_count": len(response_metrics),
            "time_range_hours": hours_back,
            "metrics": response_metrics
        }
        
    except Exception as e:
        logger.error(f"Error getting service metrics for {service_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services")
async def get_all_services_status(
    collector: LocalPerformanceMetricsCollector = Depends(get_local_performance_collector)
):
    """
    Get current status of all monitored services.
    
    Returns the latest metrics for each service including health status,
    response times, and resource usage.
    """
    try:
        current_time = datetime.now()
        services_status = {}
        
        for service_name in collector.monitored_services:
            recent_metrics = [
                m for m in collector.service_metrics_history.get(service_name, [])
                if (current_time - m.timestamp).total_seconds() < 60  # Last minute
            ]
            
            if recent_metrics:
                latest = recent_metrics[-1]
                services_status[service_name] = {
                    "status": latest.status,
                    "last_check": latest.timestamp.isoformat(),
                    "response_time_ms": latest.response_time_ms,
                    "container_name": latest.container_name,
                    "cpu_percent": latest.cpu_percent,
                    "memory_usage_mb": latest.memory_usage_mb,
                    "memory_limit_mb": latest.memory_limit_mb,
                    "connection_count": latest.connection_count,
                    "custom_metrics": latest.custom_metrics
                }
            else:
                services_status[service_name] = {
                    "status": "unknown",
                    "last_check": None,
                    "message": "No recent metrics available"
                }
        
        return {
            "timestamp": current_time.isoformat(),
            "services": services_status,
            "total_services": len(services_status),
            "healthy_services": sum(1 for s in services_status.values() if s.get("status") == "running")
        }
        
    except Exception as e:
        logger.error(f"Error getting services status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/current", response_model=SessionResponse)
async def get_current_session(
    collector: LocalPerformanceMetricsCollector = Depends(get_local_performance_collector)
):
    """
    Get metrics for the current development session.
    
    Returns comprehensive metrics for the ongoing development session including
    performance scores, resource usage, and development workflow metrics.
    """
    try:
        session = collector.current_session
        return SessionResponse(
            session_id=session.session_id,
            start_time=session.start_time,
            end_time=session.end_time,
            duration_seconds=session.duration_seconds,
            performance_score=session.performance_score,
            avg_response_time_ms=session.avg_response_time_ms,
            total_queries=session.total_queries,
            total_errors=session.total_errors,
            peak_memory_usage_mb=session.peak_memory_usage_mb,
            avg_cpu_usage_percent=session.avg_cpu_usage_percent,
            container_restarts=session.container_restarts
        )
    except Exception as e:
        logger.error(f"Error getting current session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions/history")
async def get_session_history(
    limit: int = Query(10, ge=1, le=100, description="Maximum number of sessions to retrieve"),
    collector: LocalPerformanceMetricsCollector = Depends(get_local_performance_collector)
):
    """
    Get historical development session data.
    
    Args:
        limit: Maximum number of historical sessions to retrieve
    """
    try:
        # Get recent sessions, sorted by start time (most recent first)
        recent_sessions = sorted(
            collector.historical_sessions,
            key=lambda s: s.start_time,
            reverse=True
        )[:limit]
        
        sessions_data = [
            {
                "session_id": session.session_id,
                "start_time": session.start_time.isoformat(),
                "end_time": session.end_time.isoformat() if session.end_time else None,
                "duration_seconds": session.duration_seconds,
                "performance_score": session.performance_score,
                "avg_response_time_ms": session.avg_response_time_ms,
                "total_queries": session.total_queries,
                "total_errors": session.total_errors,
                "peak_memory_usage_mb": session.peak_memory_usage_mb,
                "avg_cpu_usage_percent": session.avg_cpu_usage_percent,
                "container_restarts": session.container_restarts
            }
            for session in recent_sessions
        ]
        
        return {
            "sessions_count": len(sessions_data),
            "sessions": sessions_data
        }
        
    except Exception as e:
        logger.error(f"Error getting session history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recommendations")
async def get_performance_recommendations(
    collector: LocalPerformanceMetricsCollector = Depends(get_local_performance_collector)
):
    """
    Get performance optimization recommendations for local development.
    
    Returns actionable recommendations based on current performance metrics
    and historical patterns.
    """
    try:
        recommendations = collector._generate_recommendations()
        
        # Add additional context-aware recommendations
        summary = collector.get_performance_summary()
        
        additional_recommendations = []
        
        # Service-specific recommendations
        for service_name, service_status in summary['service_status'].items():
            if service_status.get('status') == 'error':
                additional_recommendations.append(f"Service {service_name} is experiencing errors - check container logs")
            elif service_status.get('avg_response_time_ms', 0) > 200:
                additional_recommendations.append(f"Service {service_name} has high response times - consider optimization")
        
        # Resource-based recommendations
        if summary['session_metrics']['peak_memory_usage_mb'] > 7000:
            additional_recommendations.append("Consider increasing Docker memory limits or optimizing memory usage")
        
        if summary['session_metrics']['avg_cpu_usage_percent'] > 85:
            additional_recommendations.append("High CPU usage detected - consider reducing concurrent operations or scaling resources")
        
        all_recommendations = recommendations + additional_recommendations
        
        return {
            "timestamp": datetime.now().isoformat(),
            "performance_score": summary['performance_score'],
            "recommendations_count": len(all_recommendations),
            "recommendations": all_recommendations,
            "priority_recommendations": [
                rec for rec in all_recommendations
                if any(keyword in rec.lower() for keyword in ['error', 'critical', 'high', 'urgent'])
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting recommendations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collection/start")
async def start_performance_collection(
    collector: LocalPerformanceMetricsCollector = Depends(get_local_performance_collector)
):
    """
    Start performance metrics collection.
    
    Begins collecting performance metrics for the local development environment.
    Collection will continue until explicitly stopped or the application shuts down.
    """
    try:
        if collector.is_collecting:
            return {
                "message": "Performance collection is already running",
                "session_id": collector.session_id,
                "started_at": collector.collection_start_time.isoformat()
            }
        
        await collector.start_collection()
        
        return {
            "message": "Performance collection started successfully",
            "session_id": collector.session_id,
            "started_at": collector.collection_start_time.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error starting performance collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/collection/stop")
async def stop_performance_collection(
    collector: LocalPerformanceMetricsCollector = Depends(get_local_performance_collector)
):
    """
    Stop performance metrics collection.
    
    Stops the current metrics collection session and finalizes the data.
    Historical data will be preserved.
    """
    try:
        if not collector.is_collecting:
            return {
                "message": "Performance collection is not currently running",
                "session_id": collector.session_id
            }
        
        await collector.stop_collection()
        
        return {
            "message": "Performance collection stopped successfully",
            "session_id": collector.session_id,
            "final_performance_score": collector.current_session.performance_score,
            "session_duration_seconds": collector.current_session.duration_seconds
        }
        
    except Exception as e:
        logger.error(f"Error stopping performance collection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export")
async def export_performance_data(
    format: str = Query("json", regex="^(json)$", description="Export format"),
    collector: LocalPerformanceMetricsCollector = Depends(get_local_performance_collector)
):
    """
    Export performance metrics data.
    
    Args:
        format: Export format (currently only 'json' is supported)
    """
    try:
        exported_data = collector.export_metrics(format=format)
        
        return {
            "export_timestamp": datetime.now().isoformat(),
            "format": format,
            "session_id": collector.session_id,
            "data": exported_data
        }
        
    except Exception as e:
        logger.error(f"Error exporting performance data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def get_performance_monitoring_health():
    """
    Get health status of the performance monitoring system.
    
    Returns information about the monitoring system's operational status.
    """
    global _global_collector
    
    try:
        if _global_collector is None:
            return {
                "status": "not_initialized",
                "message": "Performance monitoring not yet initialized",
                "timestamp": datetime.now().isoformat()
            }
        
        return {
            "status": "running" if _global_collector.is_collecting else "stopped",
            "session_id": _global_collector.session_id,
            "collection_start_time": _global_collector.collection_start_time.isoformat(),
            "monitored_services": list(_global_collector.monitored_services.keys()),
            "docker_available": _global_collector.docker_client is not None,
            "metrics_collected": len(_global_collector.current_session.service_metrics),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting performance monitoring health: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }