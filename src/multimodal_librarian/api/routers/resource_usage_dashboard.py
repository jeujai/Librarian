"""
Resource Usage Dashboard API Router

This module provides REST API endpoints for resource usage dashboards in local development:
- Real-time resource monitoring dashboards
- System and container resource metrics
- Resource optimization recommendations
- Performance trend analysis
- Resource efficiency scoring
- Interactive dashboard data

Validates: Requirements NFR-1 (Performance), NFR-3 (Usability), TR-5 (Development Tools)
"""

from fastapi import APIRouter, HTTPException, Query, Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from ...monitoring.resource_usage_dashboard import (
    get_resource_usage_dashboard_service,
    start_resource_monitoring,
    stop_resource_monitoring
)
from ...logging_config import get_logger

logger = get_logger("resource_dashboard_api")
router = APIRouter(prefix="/api/v1/resource-dashboard", tags=["Resource Usage Dashboard"])

@router.get("/status")
async def get_dashboard_service_status() -> Dict[str, Any]:
    """
    Get resource usage dashboard service status.
    
    Returns:
        Service status, features, and statistics
    """
    try:
        service = get_resource_usage_dashboard_service()
        status = service.get_service_status()
        
        return {
            "success": True,
            "data": status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting dashboard service status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get service status: {str(e)}")

@router.post("/monitoring/start")
async def start_resource_dashboard_monitoring() -> Dict[str, Any]:
    """
    Start resource usage monitoring for dashboards.
    
    Returns:
        Success confirmation with monitoring status
    """
    try:
        service = get_resource_usage_dashboard_service()
        
        if service.monitoring_active:
            return {
                "success": True,
                "message": "Resource monitoring is already active",
                "data": {"monitoring_active": True}
            }
        
        await start_resource_monitoring()
        
        return {
            "success": True,
            "message": "Resource monitoring started successfully",
            "data": {
                "monitoring_active": True,
                "collection_interval_seconds": service.collection_interval,
                "docker_available": service.docker_available
            }
        }
        
    except Exception as e:
        logger.error(f"Error starting resource monitoring: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start resource monitoring: {str(e)}")

@router.post("/monitoring/stop")
async def stop_resource_dashboard_monitoring() -> Dict[str, Any]:
    """
    Stop resource usage monitoring.
    
    Returns:
        Success confirmation
    """
    try:
        await stop_resource_monitoring()
        
        return {
            "success": True,
            "message": "Resource monitoring stopped successfully",
            "data": {"monitoring_active": False}
        }
        
    except Exception as e:
        logger.error(f"Error stopping resource monitoring: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop resource monitoring: {str(e)}")

@router.get("/dashboards")
async def get_available_dashboards() -> Dict[str, Any]:
    """
    Get list of available resource usage dashboards.
    
    Returns:
        List of available dashboards with metadata
    """
    try:
        service = get_resource_usage_dashboard_service()
        dashboards = service.get_available_dashboards()
        
        return {
            "success": True,
            "data": {
                "dashboards": dashboards,
                "total_dashboards": len(dashboards)
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting available dashboards: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get available dashboards: {str(e)}")

@router.get("/dashboards/{dashboard_id}")
async def get_dashboard_data(
    dashboard_id: str = Path(..., description="Dashboard ID"),
    force_refresh: bool = Query(default=False, description="Force refresh of chart data")
) -> Dict[str, Any]:
    """
    Get complete dashboard data including all charts.
    
    Args:
        dashboard_id: ID of the dashboard to retrieve
        force_refresh: Whether to force refresh of chart data
    
    Returns:
        Complete dashboard data with chart data
    """
    try:
        service = get_resource_usage_dashboard_service()
        dashboard_data = await service.get_dashboard_data(dashboard_id, force_refresh)
        
        if dashboard_data is None:
            raise HTTPException(status_code=404, detail=f"Dashboard '{dashboard_id}' not found")
        
        return {
            "success": True,
            "data": dashboard_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting dashboard data for {dashboard_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get dashboard data: {str(e)}")

@router.get("/alerts")
async def get_resource_alerts() -> Dict[str, Any]:
    """
    Get current resource alerts.
    
    Returns:
        Current resource alerts with severity levels
    """
    try:
        service = get_resource_usage_dashboard_service()
        
        # Get alerts from the service
        alerts_data = []
        for alert in service.active_alerts:
            alerts_data.append(alert.to_dict())
        
        # Categorize alerts by severity
        critical_alerts = [alert for alert in alerts_data if alert["severity"] == "critical"]
        warning_alerts = [alert for alert in alerts_data if alert["severity"] == "warning"]
        info_alerts = [alert for alert in alerts_data if alert["severity"] == "info"]
        
        return {
            "success": True,
            "data": {
                "alerts": {
                    "critical": critical_alerts,
                    "warning": warning_alerts,
                    "info": info_alerts
                },
                "summary": {
                    "total_alerts": len(alerts_data),
                    "critical_count": len(critical_alerts),
                    "warning_count": len(warning_alerts),
                    "info_count": len(info_alerts)
                },
                "monitoring_active": service.monitoring_active
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting resource alerts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get resource alerts: {str(e)}")

@router.get("/optimization")
async def get_optimization_recommendations() -> Dict[str, Any]:
    """
    Get resource optimization recommendations.
    
    Returns:
        Resource optimization recommendations with priorities
    """
    try:
        service = get_resource_usage_dashboard_service()
        
        # Get recommendations from the service
        recommendations_data = []
        for recommendation in service.optimization_recommendations:
            recommendations_data.append(recommendation.to_dict())
        
        # Categorize by priority
        high_priority = [rec for rec in recommendations_data if rec["priority"] == "high"]
        medium_priority = [rec for rec in recommendations_data if rec["priority"] == "medium"]
        low_priority = [rec for rec in recommendations_data if rec["priority"] == "low"]
        
        return {
            "success": True,
            "data": {
                "recommendations": {
                    "high_priority": high_priority,
                    "medium_priority": medium_priority,
                    "low_priority": low_priority
                },
                "summary": {
                    "total_recommendations": len(recommendations_data),
                    "high_priority_count": len(high_priority),
                    "medium_priority_count": len(medium_priority),
                    "low_priority_count": len(low_priority)
                },
                "monitoring_active": service.monitoring_active
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting optimization recommendations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get optimization recommendations: {str(e)}")

@router.get("/metrics/system")
async def get_system_resource_metrics() -> Dict[str, Any]:
    """
    Get current system resource metrics.
    
    Returns:
        Current system CPU, memory, disk, and network metrics
    """
    try:
        service = get_resource_usage_dashboard_service()
        
        if not service.resource_history:
            return {
                "success": True,
                "data": {
                    "status": "no_data",
                    "message": "No resource data available. Start monitoring to collect metrics."
                }
            }
        
        # Get latest system metrics
        latest_metrics = service.resource_history[-1]
        
        return {
            "success": True,
            "data": {
                "timestamp": latest_metrics["timestamp"].isoformat(),
                "cpu": {
                    "percent": latest_metrics["cpu_percent"],
                    "status": "critical" if latest_metrics["cpu_percent"] > service.thresholds["cpu_critical"] 
                             else "warning" if latest_metrics["cpu_percent"] > service.thresholds["cpu_warning"] 
                             else "healthy"
                },
                "memory": {
                    "percent": latest_metrics["memory_percent"],
                    "used_gb": latest_metrics["memory_used_gb"],
                    "available_gb": latest_metrics["memory_available_gb"],
                    "status": "critical" if latest_metrics["memory_percent"] > service.thresholds["memory_critical"] 
                             else "warning" if latest_metrics["memory_percent"] > service.thresholds["memory_warning"] 
                             else "healthy"
                },
                "disk": {
                    "percent": latest_metrics["disk_percent"],
                    "used_gb": latest_metrics["disk_used_gb"],
                    "free_gb": latest_metrics["disk_free_gb"],
                    "status": "critical" if latest_metrics["disk_percent"] > service.thresholds["disk_critical"] 
                             else "warning" if latest_metrics["disk_percent"] > service.thresholds["disk_warning"] 
                             else "healthy"
                },
                "network": {
                    "bytes_sent": latest_metrics["network_bytes_sent"],
                    "bytes_recv": latest_metrics["network_bytes_recv"]
                },
                "monitoring_active": service.monitoring_active
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting system resource metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get system resource metrics: {str(e)}")

@router.get("/metrics/containers")
async def get_container_resource_metrics() -> Dict[str, Any]:
    """
    Get current container resource metrics.
    
    Returns:
        Current container CPU and memory metrics for all monitored containers
    """
    try:
        service = get_resource_usage_dashboard_service()
        
        if not service.docker_available:
            return {
                "success": False,
                "message": "Docker is not available",
                "data": {"docker_available": False}
            }
        
        container_metrics = {}
        total_memory_usage = 0
        total_memory_limit = 0
        
        for container_name, metrics_history in service.container_history.items():
            if not metrics_history:
                continue
            
            latest_metrics = metrics_history[-1]
            service_name = container_name.replace("multimodal-librarian-", "").replace("-1", "")
            
            container_metrics[service_name] = {
                "container_name": container_name,
                "cpu_percent": latest_metrics["cpu_percent"],
                "memory_usage_mb": latest_metrics["memory_usage_mb"],
                "memory_limit_mb": latest_metrics["memory_limit_mb"],
                "memory_percent": latest_metrics["memory_percent"],
                "status": latest_metrics["status"],
                "timestamp": latest_metrics["timestamp"].isoformat(),
                "health_status": "critical" if latest_metrics["memory_percent"] > service.thresholds["container_memory_critical"] 
                               else "warning" if latest_metrics["memory_percent"] > service.thresholds["container_memory_warning"] 
                               else "healthy"
            }
            
            total_memory_usage += latest_metrics["memory_usage_mb"]
            total_memory_limit += latest_metrics["memory_limit_mb"]
        
        return {
            "success": True,
            "data": {
                "containers": container_metrics,
                "summary": {
                    "total_containers": len(container_metrics),
                    "total_memory_usage_mb": total_memory_usage,
                    "total_memory_limit_mb": total_memory_limit,
                    "total_memory_percent": (total_memory_usage / total_memory_limit * 100) if total_memory_limit > 0 else 0
                },
                "docker_available": service.docker_available,
                "monitoring_active": service.monitoring_active
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting container resource metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get container resource metrics: {str(e)}")

@router.get("/trends")
async def get_resource_trends(
    hours: int = Query(default=24, ge=1, le=168, description="Number of hours of trend data to retrieve")
) -> Dict[str, Any]:
    """
    Get resource usage trends over the specified time period.
    
    Args:
        hours: Number of hours of trend data to retrieve (1-168)
    
    Returns:
        Resource usage trend data
    """
    try:
        service = get_resource_usage_dashboard_service()
        
        if not service.resource_history:
            return {
                "success": True,
                "data": {
                    "status": "no_data",
                    "message": "No trend data available. Start monitoring to collect historical data."
                }
            }
        
        # Calculate how many samples to include based on collection interval
        samples_per_hour = 3600 / service.collection_interval  # samples per hour
        max_samples = int(hours * samples_per_hour)
        
        # Get recent data
        trend_data = list(service.resource_history)[-max_samples:]
        
        # Format trend data
        trends = []
        for metrics in trend_data:
            trends.append({
                "timestamp": metrics["timestamp"].isoformat(),
                "cpu_percent": metrics["cpu_percent"],
                "memory_percent": metrics["memory_percent"],
                "disk_percent": metrics["disk_percent"],
                "memory_used_gb": metrics["memory_used_gb"],
                "disk_used_gb": metrics["disk_used_gb"]
            })
        
        # Calculate trend statistics
        if len(trend_data) > 1:
            cpu_values = [m["cpu_percent"] for m in trend_data]
            memory_values = [m["memory_percent"] for m in trend_data]
            
            import statistics
            trend_stats = {
                "cpu": {
                    "avg": statistics.mean(cpu_values),
                    "min": min(cpu_values),
                    "max": max(cpu_values),
                    "current": cpu_values[-1]
                },
                "memory": {
                    "avg": statistics.mean(memory_values),
                    "min": min(memory_values),
                    "max": max(memory_values),
                    "current": memory_values[-1]
                }
            }
        else:
            trend_stats = {"status": "insufficient_data"}
        
        return {
            "success": True,
            "data": {
                "trends": trends,
                "statistics": trend_stats,
                "period_hours": hours,
                "sample_count": len(trends),
                "collection_interval_seconds": service.collection_interval,
                "monitoring_active": service.monitoring_active
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting resource trends: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get resource trends: {str(e)}")

@router.get("/efficiency")
async def get_resource_efficiency_analysis() -> Dict[str, Any]:
    """
    Get resource efficiency analysis and scoring.
    
    Returns:
        Resource efficiency scores and analysis
    """
    try:
        service = get_resource_usage_dashboard_service()
        
        if len(service.resource_history) < 10:
            return {
                "success": True,
                "data": {
                    "status": "insufficient_data",
                    "message": "Need at least 10 samples for efficiency analysis"
                }
            }
        
        # Get recent metrics for analysis
        recent_metrics = list(service.resource_history)[-60:]  # Last hour
        
        import statistics
        
        # Calculate efficiency metrics
        cpu_values = [m["cpu_percent"] for m in recent_metrics]
        memory_values = [m["memory_percent"] for m in recent_metrics]
        
        avg_cpu = statistics.mean(cpu_values)
        avg_memory = statistics.mean(memory_values)
        
        # Calculate efficiency scores (optimal ranges: CPU 20-70%, Memory 40-80%)
        cpu_efficiency = 100 if 20 <= avg_cpu <= 70 else max(0, 100 - abs(avg_cpu - 45) * 2)
        memory_efficiency = 100 if 40 <= avg_memory <= 80 else max(0, 100 - abs(avg_memory - 60) * 2)
        
        overall_efficiency = (cpu_efficiency + memory_efficiency) / 2
        
        # Determine efficiency grade
        if overall_efficiency >= 90:
            grade = "A"
            status = "Excellent"
        elif overall_efficiency >= 80:
            grade = "B"
            status = "Good"
        elif overall_efficiency >= 70:
            grade = "C"
            status = "Fair"
        elif overall_efficiency >= 60:
            grade = "D"
            status = "Poor"
        else:
            grade = "F"
            status = "Very Poor"
        
        # Generate efficiency recommendations
        recommendations = []
        if avg_cpu < 20:
            recommendations.append("CPU is underutilized - consider running additional services or reducing resources")
        elif avg_cpu > 70:
            recommendations.append("CPU usage is high - consider optimizing applications or adding resources")
        
        if avg_memory < 40:
            recommendations.append("Memory is underutilized - consider reducing memory allocations")
        elif avg_memory > 80:
            recommendations.append("Memory usage is high - consider adding memory or optimizing applications")
        
        return {
            "success": True,
            "data": {
                "efficiency_score": {
                    "overall": round(overall_efficiency, 1),
                    "cpu": round(cpu_efficiency, 1),
                    "memory": round(memory_efficiency, 1),
                    "grade": grade,
                    "status": status
                },
                "current_usage": {
                    "cpu_percent": avg_cpu,
                    "memory_percent": avg_memory
                },
                "optimal_ranges": {
                    "cpu": "20-70%",
                    "memory": "40-80%"
                },
                "recommendations": recommendations,
                "analysis_period_minutes": len(recent_metrics) * (service.collection_interval / 60),
                "monitoring_active": service.monitoring_active
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting resource efficiency analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get resource efficiency analysis: {str(e)}")

@router.get("/health")
async def get_resource_dashboard_health() -> Dict[str, Any]:
    """
    Get health status of the resource dashboard system.
    
    Returns:
        Health status of all dashboard components
    """
    try:
        service = get_resource_usage_dashboard_service()
        
        # Check component health
        system_healthy = len(service.resource_history) > 0
        docker_healthy = service.docker_available
        monitoring_healthy = service.monitoring_active
        
        # Check for critical alerts
        critical_alerts = [alert for alert in service.active_alerts if alert.severity == "critical"]
        alerts_healthy = len(critical_alerts) == 0
        
        # Overall health
        overall_healthy = system_healthy and monitoring_healthy and alerts_healthy
        
        return {
            "success": True,
            "data": {
                "overall_health": "healthy" if overall_healthy else "unhealthy",
                "components": {
                    "system_monitoring": "healthy" if system_healthy else "unhealthy",
                    "docker_monitoring": "healthy" if docker_healthy else "unavailable",
                    "monitoring_service": "active" if monitoring_healthy else "inactive",
                    "alerts_status": "healthy" if alerts_healthy else "critical_alerts_present"
                },
                "statistics": {
                    "monitoring_active": monitoring_healthy,
                    "docker_available": docker_healthy,
                    "resource_samples": len(service.resource_history),
                    "active_alerts": len(service.active_alerts),
                    "critical_alerts": len(critical_alerts),
                    "optimization_recommendations": len(service.optimization_recommendations),
                    "monitored_containers": len(service.container_history)
                },
                "last_check": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"Error checking resource dashboard health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to check resource dashboard health: {str(e)}")

@router.post("/thresholds")
async def update_resource_thresholds(thresholds: Dict[str, float]) -> Dict[str, Any]:
    """
    Update resource monitoring thresholds.
    
    Args:
        thresholds: Dictionary of threshold values to update
    
    Returns:
        Success confirmation with updated thresholds
    """
    try:
        service = get_resource_usage_dashboard_service()
        
        # Validate threshold values
        valid_thresholds = {
            "cpu_warning", "cpu_critical",
            "memory_warning", "memory_critical", 
            "disk_warning", "disk_critical",
            "container_memory_warning", "container_memory_critical",
            "container_cpu_warning", "container_cpu_critical"
        }
        
        updated_thresholds = {}
        for key, value in thresholds.items():
            if key not in valid_thresholds:
                raise HTTPException(status_code=400, detail=f"Invalid threshold key: {key}")
            
            if not isinstance(value, (int, float)) or value < 0 or value > 100:
                raise HTTPException(status_code=400, detail=f"Invalid threshold value for {key}: {value}")
            
            service.thresholds[key] = float(value)
            updated_thresholds[key] = float(value)
        
        return {
            "success": True,
            "message": f"Updated {len(updated_thresholds)} threshold(s)",
            "data": {
                "updated_thresholds": updated_thresholds,
                "current_thresholds": service.thresholds
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating resource thresholds: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update resource thresholds: {str(e)}")