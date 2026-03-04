"""
Health Check API endpoints.

This module provides REST API endpoints for system health monitoring,
including component health checks, service monitoring, and system status.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional, List
import asyncio
from datetime import datetime

from ...monitoring.health_check_system import get_health_check_system
from ...monitoring.service_health_monitor import HealthStatus
from ...logging_config import get_logger

router = APIRouter(prefix="/api/health", tags=["Health Checks"])
logger = get_logger("health_api")


@router.get("/", summary="Overall System Health")
async def get_system_health() -> Dict[str, Any]:
    """
    Get overall system health status.
    
    Returns a comprehensive health report including all components
    and their current status.
    """
    try:
        health_system = get_health_check_system()
        health_report = await health_system.run_all_checks()
        
        return {
            "success": True,
            "data": health_report.to_dict(),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"System health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get("/detailed", summary="Detailed System Health")
async def get_detailed_health() -> Dict[str, Any]:
    """
    Get detailed system health status including service monitor data.
    
    Returns comprehensive health information including:
    - Component health checks
    - Service health monitor statistics
    - Readiness and liveness status
    """
    try:
        health_system = get_health_check_system()
        detailed_status = await health_system.get_detailed_status()
        
        return {
            "success": True,
            "data": detailed_status,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Detailed health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Detailed health check failed: {str(e)}")


@router.get("/readiness", summary="Readiness Probe")
async def get_readiness() -> Dict[str, Any]:
    """
    Kubernetes-style readiness probe.
    
    Returns whether the system is ready to serve requests.
    Critical services must be healthy for readiness to pass.
    """
    try:
        health_system = get_health_check_system()
        is_ready = await health_system.get_readiness_status()
        
        status_code = 200 if is_ready else 503
        
        return {
            "ready": is_ready,
            "status": "ready" if is_ready else "not_ready",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {
            "ready": False,
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/liveness", summary="Liveness Probe")
async def get_liveness() -> Dict[str, Any]:
    """
    Kubernetes-style liveness probe.
    
    Returns whether the system is alive and responding.
    This is a basic connectivity test.
    """
    try:
        health_system = get_health_check_system()
        is_alive = await health_system.get_liveness_status()
        
        return {
            "alive": is_alive,
            "status": "alive" if is_alive else "dead",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Liveness check failed: {e}")
        return {
            "alive": False,
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/component/{component_name}", summary="Component Health")
async def get_component_health(component_name: str) -> Dict[str, Any]:
    """
    Get health status for a specific component.
    
    Args:
        component_name: Name of the component to check
        
    Returns:
        Health status and details for the specified component
    """
    try:
        health_system = get_health_check_system()
        
        # Check if component exists
        if component_name not in health_system.checks:
            available_components = list(health_system.checks.keys())
            raise HTTPException(
                status_code=404, 
                detail=f"Component '{component_name}' not found. Available: {available_components}"
            )
        
        # Run health check for specific component
        check = health_system.checks[component_name]
        result = await check.run()
        
        return {
            "success": True,
            "component": component_name,
            "data": result,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Component health check failed for {component_name}: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Component health check failed: {str(e)}"
        )


@router.get("/service/{service_name}", summary="Service Health Monitor")
async def get_service_health(service_name: str) -> Dict[str, Any]:
    """
    Get service health monitor data for a specific service.
    
    Args:
        service_name: Name of the service to check
        
    Returns:
        Service health monitor statistics and status
    """
    try:
        health_system = get_health_check_system()
        service_health = health_system.get_service_health(service_name)
        
        if service_health is None:
            raise HTTPException(
                status_code=404, 
                detail=f"Service '{service_name}' not found in health monitor"
            )
        
        return {
            "success": True,
            "service": service_name,
            "data": service_health,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Service health check failed for {service_name}: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Service health check failed: {str(e)}"
        )


@router.get("/services", summary="All Services Health Monitor")
async def get_all_services_health() -> Dict[str, Any]:
    """
    Get health monitor data for all services.
    
    Returns:
        Complete service health monitor report
    """
    try:
        health_system = get_health_check_system()
        all_services_health = health_system.health_monitor.get_all_services_health()
        
        return {
            "success": True,
            "data": all_services_health,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"All services health check failed: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Services health check failed: {str(e)}"
        )


@router.get("/components", summary="Available Components")
async def get_available_components() -> Dict[str, Any]:
    """
    Get list of available health check components.
    
    Returns:
        List of available components and their descriptions
    """
    try:
        health_system = get_health_check_system()
        
        components = []
        for name, check in health_system.checks.items():
            components.append({
                "name": name,
                "component_name": check.component_name,
                "class_name": check.__class__.__name__
            })
        
        return {
            "success": True,
            "data": {
                "components": components,
                "total_count": len(components)
            },
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get available components: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to get components: {str(e)}"
        )


@router.post("/monitoring/start", summary="Start Health Monitoring")
async def start_health_monitoring(
    interval: int = Query(60, description="Monitoring interval in seconds", ge=10, le=3600)
) -> Dict[str, Any]:
    """
    Start background health monitoring.
    
    Args:
        interval: Monitoring interval in seconds (10-3600)
        
    Returns:
        Confirmation of monitoring start
    """
    try:
        health_system = get_health_check_system()
        health_system.start_monitoring(interval)
        
        return {
            "success": True,
            "message": f"Health monitoring started with {interval}s interval",
            "interval_seconds": interval,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to start health monitoring: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to start monitoring: {str(e)}"
        )


@router.post("/monitoring/stop", summary="Stop Health Monitoring")
async def stop_health_monitoring() -> Dict[str, Any]:
    """
    Stop background health monitoring.
    
    Returns:
        Confirmation of monitoring stop
    """
    try:
        health_system = get_health_check_system()
        health_system.stop_monitoring()
        
        return {
            "success": True,
            "message": "Health monitoring stopped",
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to stop health monitoring: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to stop monitoring: {str(e)}"
        )


@router.get("/status/summary", summary="Health Status Summary")
async def get_health_summary() -> Dict[str, Any]:
    """
    Get a concise health status summary.
    
    Returns:
        Brief summary of system health suitable for dashboards
    """
    try:
        health_system = get_health_check_system()
        health_report = await health_system.run_all_checks()
        
        # Get service monitor summary
        monitor_data = health_system.health_monitor.get_all_services_health()
        
        summary = {
            "overall_status": health_report.get_overall_status().value,
            "components": {
                "total": len(health_report.results),
                "healthy": len([r for r in health_report.results.values() 
                              if r.get('status') == HealthStatus.HEALTHY.value]),
                "degraded": len([r for r in health_report.results.values() 
                               if r.get('status') == HealthStatus.DEGRADED.value]),
                "unhealthy": len([r for r in health_report.results.values() 
                                if r.get('status') in [HealthStatus.UNHEALTHY.value, 
                                                     HealthStatus.CRITICAL.value, 
                                                     HealthStatus.DOWN.value]])
            },
            "services": monitor_data.get('summary', {}),
            "readiness": await health_system.get_readiness_status(),
            "liveness": await health_system.get_liveness_status()
        }
        
        return {
            "success": True,
            "data": summary,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Health summary failed: {e}")
        raise HTTPException(
            status_code=500, 
            detail=f"Health summary failed: {str(e)}"
        )


@router.get("/simple", summary="Simple Health Check")
async def get_simple_health() -> Dict[str, Any]:
    """
    Simple health check endpoint for basic connectivity testing.
    
    This is a lightweight endpoint that performs minimal checks
    and is suitable for load balancer health checks.
    
    Returns:
        Basic health status
    """
    try:
        health_system = get_health_check_system()
        is_alive = await health_system.get_liveness_status()
        
        return {
            "status": "healthy" if is_alive else "unhealthy",
            "alive": is_alive,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Simple health check failed: {e}")
        return {
            "status": "unhealthy",
            "alive": False,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/startup", summary="System Startup Status")
async def get_startup_status() -> Dict[str, Any]:
    """
    Get overall system startup status.
    
    This endpoint checks if all critical components have started successfully
    and the system is ready for operation.
    
    Returns:
        System startup status and component initialization details
    """
    try:
        health_system = get_health_check_system()
        
        # Check critical startup components
        startup_components = ['database', 'vector_store', 'search_service']
        startup_results = {}
        overall_startup_success = True
        
        for component_name in startup_components:
            if component_name in health_system.checks:
                try:
                    result = await health_system.checks[component_name].run()
                    startup_results[component_name] = {
                        "status": result.get('status', 'unknown'),
                        "initialized": result.get('status') in ['healthy', 'degraded'],
                        "response_time_ms": result.get('response_time_ms', 0),
                        "details": result.get('details', {})
                    }
                    
                    if result.get('status') in ['critical', 'down', 'unhealthy']:
                        overall_startup_success = False
                        
                except Exception as e:
                    startup_results[component_name] = {
                        "status": "error",
                        "initialized": False,
                        "error": str(e)
                    }
                    overall_startup_success = False
            else:
                startup_results[component_name] = {
                    "status": "not_available",
                    "initialized": False,
                    "error": "Component check not available"
                }
                overall_startup_success = False
        
        return {
            "success": True,
            "startup_complete": overall_startup_success,
            "status": "ready" if overall_startup_success else "initializing",
            "components": startup_results,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Startup status check failed: {e}")
        return {
            "success": False,
            "startup_complete": False,
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/search", summary="Search Service Availability")
async def get_search_service_status() -> Dict[str, Any]:
    """
    Get search service availability and performance status.
    
    This endpoint specifically checks the search service health,
    including fallback status and performance metrics.
    
    Returns:
        Search service status and performance information
    """
    try:
        health_system = get_health_check_system()
        
        # Check search service component
        if 'search_service' not in health_system.checks:
            return {
                "success": False,
                "available": False,
                "status": "not_configured",
                "error": "Search service health check not configured",
                "timestamp": datetime.now().isoformat()
            }
        
        # Run search service health check
        result = await health_system.checks['search_service'].run()
        
        # Get service health monitor data
        service_health = health_system.get_service_health('search_service')
        
        return {
            "success": True,
            "available": result.get('status') in ['healthy', 'degraded'],
            "status": result.get('status', 'unknown'),
            "response_time_ms": result.get('response_time_ms', 0),
            "fallback_active": result.get('details', {}).get('fallback_active', False),
            "service_monitor": service_health,
            "details": result.get('details', {}),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Search service status check failed: {e}")
        return {
            "success": False,
            "available": False,
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/vector-store", summary="Vector Database Connectivity")
async def get_vector_store_status() -> Dict[str, Any]:
    """
    Get vector database connectivity and performance status.
    
    This endpoint checks the vector store connection, indexing status,
    and query performance.
    
    Returns:
        Vector store connectivity and performance information
    """
    try:
        health_system = get_health_check_system()
        
        # Check vector store component
        if 'vector_store' not in health_system.checks:
            return {
                "success": False,
                "connected": False,
                "status": "not_configured",
                "error": "Vector store health check not configured",
                "timestamp": datetime.now().isoformat()
            }
        
        # Run vector store health check
        result = await health_system.checks['vector_store'].run()
        
        # Get service health monitor data
        service_health = health_system.get_service_health('vector_store')
        
        return {
            "success": True,
            "connected": result.get('status') in ['healthy', 'degraded'],
            "status": result.get('status', 'unknown'),
            "response_time_ms": result.get('response_time_ms', 0),
            "index_status": result.get('details', {}).get('index_status', 'unknown'),
            "document_count": result.get('details', {}).get('document_count', 0),
            "service_monitor": service_health,
            "details": result.get('details', {}),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Vector store status check failed: {e}")
        return {
            "success": False,
            "connected": False,
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/ai-services", summary="AI Service Responsiveness")
async def get_ai_services_status() -> Dict[str, Any]:
    """
    Get AI services responsiveness and availability status.
    
    This endpoint checks AI service connectivity, response times,
    and token usage statistics.
    
    Returns:
        AI services status and performance information
    """
    try:
        health_system = get_health_check_system()
        
        # Check AI services component
        if 'ai_services' not in health_system.checks:
            return {
                "success": False,
                "responsive": False,
                "status": "not_configured",
                "error": "AI services health check not configured",
                "timestamp": datetime.now().isoformat()
            }
        
        # Run AI services health check
        result = await health_system.checks['ai_services'].run()
        
        # Get service health monitor data
        service_health = health_system.get_service_health('ai_services')
        
        return {
            "success": True,
            "responsive": result.get('status') in ['healthy', 'degraded'],
            "status": result.get('status', 'unknown'),
            "response_time_ms": result.get('response_time_ms', 0),
            "providers_available": result.get('details', {}).get('providers_available', []),
            "token_usage": result.get('details', {}).get('token_usage', {}),
            "service_monitor": service_health,
            "details": result.get('details', {}),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"AI services status check failed: {e}")
        return {
            "success": False,
            "responsive": False,
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/performance", summary="Performance Metrics Summary")
async def get_performance_status() -> Dict[str, Any]:
    """
    Get performance metrics summary for all system components.
    
    This endpoint provides a comprehensive view of system performance
    including response times, resource usage, and throughput metrics.
    
    Returns:
        Performance metrics summary and system resource status
    """
    try:
        health_system = get_health_check_system()
        
        # Get comprehensive health report
        health_report = await health_system.run_all_checks()
        
        # Extract performance metrics
        performance_summary = {
            "overall_response_time_ms": health_report.total_response_time,
            "components_performance": {},
            "system_resources": {}
        }
        
        # Process component performance
        for component_name, result in health_report.results.items():
            performance_summary["components_performance"][component_name] = {
                "response_time_ms": result.get('response_time_ms', 0),
                "status": result.get('status', 'unknown'),
                "performance_grade": "good" if result.get('response_time_ms', 0) < 100 else 
                                   "acceptable" if result.get('response_time_ms', 0) < 500 else "slow"
            }
        
        # Get system resources if available
        if 'system_resources' in health_system.checks:
            try:
                system_result = await health_system.checks['system_resources'].run()
                performance_summary["system_resources"] = system_result.get('details', {})
            except Exception as e:
                logger.warning(f"Failed to get system resources: {e}")
                performance_summary["system_resources"] = {"error": str(e)}
        
        # Calculate performance score
        avg_response_time = health_report.total_response_time / len(health_report.results) if health_report.results else 0
        performance_score = max(0, min(100, 100 - (avg_response_time / 10)))  # Score based on response time
        
        return {
            "success": True,
            "performance_score": round(performance_score, 2),
            "overall_status": health_report.get_overall_status().value,
            "metrics": performance_summary,
            "summary": health_report.to_dict()['summary'],
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Performance status check failed: {e}")
        return {
            "success": False,
            "performance_score": 0,
            "overall_status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/ping", summary="Simple Ping")
async def ping() -> Dict[str, Any]:
    """
    Simple ping endpoint for basic connectivity testing.
    
    Returns:
        Basic pong response with timestamp
    """
    return {
        "status": "ok",
        "message": "pong",
        "timestamp": datetime.now().isoformat()
    }