"""
Local Memory Monitoring API Router

This module provides REST API endpoints for local development memory monitoring:
- Memory status and metrics
- Memory usage history
- Memory optimization recommendations
- Container memory monitoring
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, List, Any, Optional
from datetime import datetime

from ...monitoring.local_memory_monitor import (
    get_local_memory_monitor,
    start_local_memory_monitoring,
    stop_local_memory_monitoring,
    get_memory_status
)
from ...logging_config import get_logger

logger = get_logger("local_memory_api")
router = APIRouter(prefix="/api/v1/memory", tags=["Local Memory Monitoring"])

@router.get("/status")
async def get_memory_monitoring_status() -> Dict[str, Any]:
    """
    Get current memory monitoring status and metrics.
    
    Returns:
        Dict containing current memory usage, alerts, and recommendations
    """
    try:
        status = get_memory_status()
        return {
            "success": True,
            "data": status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting memory status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get memory status: {str(e)}")

@router.post("/monitoring/start")
async def start_memory_monitoring() -> Dict[str, Any]:
    """
    Start local memory monitoring.
    
    Returns:
        Success confirmation with monitoring status
    """
    try:
        monitor = get_local_memory_monitor()
        
        if monitor.is_monitoring:
            return {
                "success": True,
                "message": "Memory monitoring is already active",
                "data": {"monitoring_active": True}
            }
        
        await start_local_memory_monitoring()
        
        return {
            "success": True,
            "message": "Memory monitoring started successfully",
            "data": {
                "monitoring_active": True,
                "check_interval_seconds": monitor.check_interval,
                "alert_threshold_percent": monitor.alert_threshold
            }
        }
        
    except Exception as e:
        logger.error(f"Error starting memory monitoring: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start memory monitoring: {str(e)}")

@router.post("/monitoring/stop")
async def stop_memory_monitoring() -> Dict[str, Any]:
    """
    Stop local memory monitoring.
    
    Returns:
        Success confirmation
    """
    try:
        await stop_local_memory_monitoring()
        
        return {
            "success": True,
            "message": "Memory monitoring stopped successfully",
            "data": {"monitoring_active": False}
        }
        
    except Exception as e:
        logger.error(f"Error stopping memory monitoring: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop memory monitoring: {str(e)}")

@router.get("/metrics/current")
async def get_current_memory_metrics() -> Dict[str, Any]:
    """
    Get current memory metrics for system and containers.
    
    Returns:
        Current memory usage metrics
    """
    try:
        monitor = get_local_memory_monitor()
        metrics = await monitor.collect_metrics()
        
        return {
            "success": True,
            "data": {
                "timestamp": metrics.timestamp.isoformat(),
                "system": {
                    "memory_mb": metrics.system_memory_mb,
                    "memory_percent": metrics.system_memory_percent,
                    "available_mb": metrics.available_memory_mb
                },
                "containers": {
                    name: {
                        "usage_mb": usage,
                        "limit_mb": metrics.container_memory_limits.get(name, 0),
                        "percent": metrics.container_memory_percent.get(name, 0)
                    }
                    for name, usage in metrics.container_memory_usage.items()
                },
                "total_container_memory_mb": metrics.total_container_memory_mb,
                "alerts": metrics.memory_alerts,
                "optimization_suggestions": metrics.optimization_suggestions
            }
        }
        
    except Exception as e:
        logger.error(f"Error collecting memory metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to collect memory metrics: {str(e)}")

@router.get("/history")
async def get_memory_history(
    minutes: int = Query(default=60, ge=1, le=1440, description="Number of minutes of history to retrieve")
) -> Dict[str, Any]:
    """
    Get memory usage history for the specified time period.
    
    Args:
        minutes: Number of minutes of history to retrieve (1-1440)
    
    Returns:
        Memory usage history data
    """
    try:
        monitor = get_local_memory_monitor()
        history = monitor.get_memory_history(minutes)
        
        return {
            "success": True,
            "data": {
                "history": history,
                "period_minutes": minutes,
                "sample_count": len(history),
                "monitoring_active": monitor.is_monitoring
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting memory history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get memory history: {str(e)}")

@router.get("/analysis/trends")
async def get_memory_trends() -> Dict[str, Any]:
    """
    Analyze memory usage trends over recent monitoring period.
    
    Returns:
        Memory trend analysis including system and container trends
    """
    try:
        monitor = get_local_memory_monitor()
        trends = monitor.analyze_memory_trends()
        
        return {
            "success": True,
            "data": trends
        }
        
    except Exception as e:
        logger.error(f"Error analyzing memory trends: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to analyze memory trends: {str(e)}")

@router.get("/containers")
async def get_container_memory_info() -> Dict[str, Any]:
    """
    Get detailed memory information for all monitored containers.
    
    Returns:
        Container memory usage details
    """
    try:
        monitor = get_local_memory_monitor()
        
        if not monitor.docker_available:
            return {
                "success": False,
                "message": "Docker is not available",
                "data": {"docker_available": False}
            }
        
        # Get current metrics to extract container info
        metrics = await monitor.collect_metrics()
        
        container_info = {}
        for container_name in metrics.container_memory_usage.keys():
            service_name = monitor._extract_service_name(container_name)
            container_info[service_name] = {
                "container_name": container_name,
                "memory_usage_mb": metrics.container_memory_usage[container_name],
                "memory_limit_mb": metrics.container_memory_limits.get(container_name, 0),
                "memory_percent": metrics.container_memory_percent.get(container_name, 0),
                "alert_threshold": monitor.service_thresholds.get(service_name, monitor.alert_threshold),
                "status": "healthy" if metrics.container_memory_percent.get(container_name, 0) < 80 else "warning"
            }
        
        return {
            "success": True,
            "data": {
                "containers": container_info,
                "total_containers": len(container_info),
                "total_memory_mb": metrics.total_container_memory_mb,
                "docker_available": monitor.docker_available
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting container memory info: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get container memory info: {str(e)}")

@router.get("/recommendations")
async def get_memory_recommendations() -> Dict[str, Any]:
    """
    Get memory optimization recommendations based on current usage patterns.
    
    Returns:
        Memory optimization recommendations
    """
    try:
        monitor = get_local_memory_monitor()
        
        if not monitor.metrics_history:
            return {
                "success": True,
                "data": {
                    "recommendations": ["Start memory monitoring to get optimization recommendations"],
                    "status": "no_data"
                }
            }
        
        # Get latest metrics for recommendations
        latest_metrics = monitor.metrics_history[-1]
        
        # Generate comprehensive recommendations
        recommendations = latest_metrics.optimization_suggestions.copy()
        
        # Add trend-based recommendations
        trends = monitor.analyze_memory_trends()
        if trends.get("status") == "analyzed":
            if trends.get("system_memory_trend") == "increasing":
                recommendations.append("System memory usage is trending upward - monitor closely")
            
            for container, trend in trends.get("container_memory_trends", {}).items():
                if trend == "increasing":
                    service_name = monitor._extract_service_name(container)
                    recommendations.append(f"{service_name}: Memory usage is increasing - investigate potential memory leaks")
        
        # Add Docker-specific recommendations
        if monitor.docker_available and latest_metrics.total_container_memory_mb > 0:
            system_memory_gb = latest_metrics.system_memory_mb / 1024
            container_memory_gb = latest_metrics.total_container_memory_mb / 1024
            
            if container_memory_gb > system_memory_gb * 0.8:
                recommendations.append("Container memory limits exceed 80% of system memory - consider reducing limits")
            elif container_memory_gb < system_memory_gb * 0.3:
                recommendations.append("Container memory limits are conservative - consider optimizing for better performance")
        
        return {
            "success": True,
            "data": {
                "recommendations": recommendations,
                "recommendation_count": len(recommendations),
                "based_on_samples": len(monitor.metrics_history),
                "monitoring_active": monitor.is_monitoring
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting memory recommendations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get memory recommendations: {str(e)}")

@router.get("/alerts")
async def get_memory_alerts() -> Dict[str, Any]:
    """
    Get current memory alerts and their severity.
    
    Returns:
        Current memory alerts
    """
    try:
        monitor = get_local_memory_monitor()
        
        if not monitor.metrics_history:
            return {
                "success": True,
                "data": {
                    "alerts": [],
                    "alert_count": 0,
                    "status": "no_data"
                }
            }
        
        # Get latest alerts
        latest_metrics = monitor.metrics_history[-1]
        alerts = latest_metrics.memory_alerts
        
        # Categorize alerts by severity
        critical_alerts = [alert for alert in alerts if "critical" in alert.lower()]
        warning_alerts = [alert for alert in alerts if "high" in alert.lower() and "critical" not in alert.lower()]
        info_alerts = [alert for alert in alerts if alert not in critical_alerts and alert not in warning_alerts]
        
        return {
            "success": True,
            "data": {
                "alerts": {
                    "critical": critical_alerts,
                    "warning": warning_alerts,
                    "info": info_alerts
                },
                "alert_count": len(alerts),
                "severity_summary": {
                    "critical": len(critical_alerts),
                    "warning": len(warning_alerts),
                    "info": len(info_alerts)
                },
                "timestamp": latest_metrics.timestamp.isoformat(),
                "monitoring_active": monitor.is_monitoring
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting memory alerts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get memory alerts: {str(e)}")

@router.get("/health")
async def get_memory_monitoring_health() -> Dict[str, Any]:
    """
    Get health status of the memory monitoring system.
    
    Returns:
        Health status of memory monitoring components
    """
    try:
        monitor = get_local_memory_monitor()
        
        # Check system memory availability
        try:
            import psutil
            memory = psutil.virtual_memory()
            system_healthy = memory.available > 100 * 1024 * 1024  # At least 100MB available
        except Exception:
            system_healthy = False
        
        # Check Docker availability
        docker_healthy = monitor.docker_available
        
        # Check monitoring status
        monitoring_healthy = monitor.is_monitoring
        
        # Overall health
        overall_healthy = system_healthy and (docker_healthy or not monitor.docker_available)
        
        return {
            "success": True,
            "data": {
                "overall_health": "healthy" if overall_healthy else "unhealthy",
                "components": {
                    "system_memory": "healthy" if system_healthy else "unhealthy",
                    "docker_monitoring": "healthy" if docker_healthy else "unavailable",
                    "monitoring_service": "active" if monitoring_healthy else "inactive"
                },
                "monitoring_active": monitoring_healthy,
                "docker_available": docker_healthy,
                "metrics_collected": len(monitor.metrics_history),
                "last_check": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Error checking memory monitoring health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check memory monitoring health: {str(e)}")