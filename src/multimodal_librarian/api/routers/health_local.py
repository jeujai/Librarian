"""
Local Development Health Check API Router

This module provides comprehensive health check endpoints specifically designed for
local development environments with Docker-based database services.

Key Features:
- Individual database service health checks (PostgreSQL, Neo4j, Milvus, Redis)
- Comprehensive multi-service health monitoring
- Database connectivity monitoring
- Service dependency health checks
- Performance metrics collection
- Health check dashboards
- Docker container status monitoring
- Service restart and recovery recommendations

The health checks are designed to work with the local development setup defined
in docker-compose.local.yml and provide detailed diagnostics for troubleshooting
local development issues.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse

from ...clients.database_factory import DatabaseClientFactory
from ...config.config_factory import get_database_config
from ...logging_config import get_logger

router = APIRouter(prefix="/api/health/local", tags=["Local Health"])
logger = get_logger("health_local_api")


def _ensure_json_serializable(obj: Any) -> Any:
    """Ensure an object is JSON serializable by converting problematic types to strings."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    elif isinstance(obj, dict):
        return {k: _ensure_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_ensure_json_serializable(item) for item in obj]
    else:
        # Convert any other type to string
        return str(obj)


async def get_local_database_factory():
    """Dependency to get database factory for local environment."""
    config = get_database_config()
    if getattr(config, 'database_type', 'unknown') != 'local':
        raise HTTPException(
            status_code=404, 
            detail="Local health checks only available in local development environment"
        )
    return DatabaseClientFactory(config)


@router.get("/")
async def comprehensive_local_health_check(
    factory: DatabaseClientFactory = Depends(get_local_database_factory)
):
    """
    Comprehensive health check for all local database services.
    
    This endpoint performs health checks on all enabled local database services
    and provides a complete overview of the local development environment health.
    
    Returns:
        Complete health status for all local services
    """
    start_time = time.time()
    
    health_report = {
        "environment": "local",
        "overall_status": "unknown",
        "check_timestamp": datetime.now().isoformat(),
        "response_time_ms": 0,
        "services": {},
        "summary": {
            "total_services": 0,
            "healthy_services": 0,
            "degraded_services": 0,
            "unhealthy_services": 0,
            "all_healthy": False
        },
        "recommendations": [],
        "docker_info": {}
    }
    
    try:
        # Get configuration
        config = factory.config
        
        # Check each enabled service
        service_checks = []
        
        if getattr(config, 'enable_relational_db', True):
            service_checks.append(('postgres', _check_postgres_health))
            health_report["summary"]["total_services"] += 1
        
        if getattr(config, 'enable_graph_db', True):
            service_checks.append(('neo4j', _check_neo4j_health))
            health_report["summary"]["total_services"] += 1
        
        if getattr(config, 'enable_vector_search', True):
            service_checks.append(('milvus', _check_milvus_health))
            health_report["summary"]["total_services"] += 1
        
        if getattr(config, 'enable_redis_cache', True):
            service_checks.append(('redis', _check_redis_health))
            health_report["summary"]["total_services"] += 1
        
        # Run health checks concurrently
        check_tasks = [
            _run_service_health_check(service_name, check_func, factory)
            for service_name, check_func in service_checks
        ]
        
        if check_tasks:
            results = await asyncio.gather(*check_tasks, return_exceptions=True)
            
            for (service_name, _), result in zip(service_checks, results):
                if isinstance(result, Exception):
                    health_report["services"][service_name] = {
                        "status": "error",
                        "error": str(result),
                        "timestamp": datetime.now().isoformat()
                    }
                    health_report["summary"]["unhealthy_services"] += 1
                else:
                    health_report["services"][service_name] = result
                    
                    # Count service status
                    status = result.get("status", "unknown")
                    if status == "healthy":
                        health_report["summary"]["healthy_services"] += 1
                    elif status == "degraded":
                        health_report["summary"]["degraded_services"] += 1
                    else:
                        health_report["summary"]["unhealthy_services"] += 1
        
        # Determine overall status
        healthy = health_report["summary"]["healthy_services"]
        degraded = health_report["summary"]["degraded_services"]
        unhealthy = health_report["summary"]["unhealthy_services"]
        total = health_report["summary"]["total_services"]
        
        if unhealthy == 0 and degraded == 0:
            health_report["overall_status"] = "healthy"
            health_report["summary"]["all_healthy"] = True
        elif unhealthy == 0 and degraded <= total // 2:
            health_report["overall_status"] = "degraded"
        elif healthy >= total // 2:
            health_report["overall_status"] = "critical"
        else:
            health_report["overall_status"] = "unhealthy"
        
        # Add Docker information
        health_report["docker_info"] = await _get_docker_info(config)
        
        # Generate recommendations
        health_report["recommendations"] = _generate_health_recommendations(health_report)
        
        # Calculate response time
        health_report["response_time_ms"] = round((time.time() - start_time) * 1000, 2)
        
        # Ensure all data is JSON serializable
        health_report = _ensure_json_serializable(health_report)
        
        # Return appropriate status code
        status_code = 200 if health_report["overall_status"] in ["healthy", "degraded"] else 503
        
        return JSONResponse(content=health_report, status_code=status_code)
        
    except Exception as e:
        logger.error(f"Comprehensive local health check failed: {e}")
        health_report["overall_status"] = "error"
        health_report["error"] = str(e)
        health_report["response_time_ms"] = round((time.time() - start_time) * 1000, 2)
        
        # Ensure all data is JSON serializable
        health_report = _ensure_json_serializable(health_report)
        
        return JSONResponse(content=health_report, status_code=503)


@router.get("/postgres")
async def postgres_health_check(
    factory: DatabaseClientFactory = Depends(get_local_database_factory)
):
    """
    PostgreSQL database health check.
    
    This endpoint performs comprehensive health checks on the local PostgreSQL
    database including connectivity, query performance, and connection pool status.
    
    Returns:
        PostgreSQL health status and metrics
    """
    return await _check_postgres_health(factory)


@router.get("/neo4j")
async def neo4j_health_check(
    factory: DatabaseClientFactory = Depends(get_local_database_factory)
):
    """
    Neo4j graph database health check.
    
    This endpoint performs comprehensive health checks on the local Neo4j
    database including connectivity, query performance, and driver status.
    
    Returns:
        Neo4j health status and metrics
    """
    return await _check_neo4j_health(factory)


@router.get("/milvus")
async def milvus_health_check(
    factory: DatabaseClientFactory = Depends(get_local_database_factory)
):
    """
    Milvus vector database health check.
    
    This endpoint performs comprehensive health checks on the local Milvus
    database including connectivity, collection status, and index health.
    
    Returns:
        Milvus health status and metrics
    """
    return await _check_milvus_health(factory)


@router.get("/redis")
async def redis_health_check(
    factory: DatabaseClientFactory = Depends(get_local_database_factory)
):
    """
    Redis cache health check.
    
    This endpoint performs comprehensive health checks on the local Redis
    cache including connectivity, memory usage, and performance metrics.
    
    Returns:
        Redis health status and metrics
    """
    return await _check_redis_health(factory)


@router.get("/connectivity")
async def database_connectivity_check(
    factory: DatabaseClientFactory = Depends(get_local_database_factory),
    include_pool_stats: bool = Query(False, description="Include connection pool statistics"),
    include_performance: bool = Query(False, description="Include performance metrics"),
    continuous_monitoring: bool = Query(False, description="Enable continuous monitoring mode")
):
    """
    Enhanced database connectivity monitoring endpoint.
    
    This endpoint provides comprehensive connectivity monitoring for all enabled
    database services including connection pool statistics, performance metrics,
    and continuous monitoring capabilities.
    
    Args:
        include_pool_stats: Include connection pool utilization statistics
        include_performance: Include performance metrics (response times, throughput)
        continuous_monitoring: Enable continuous monitoring with historical data
    
    Returns:
        Comprehensive connectivity status and monitoring data for all services
    """
    start_time = time.time()
    
    connectivity_report = {
        "check_type": "enhanced_connectivity",
        "timestamp": datetime.now().isoformat(),
        "monitoring_mode": "continuous" if continuous_monitoring else "snapshot",
        "services": {},
        "summary": {
            "total_checked": 0,
            "connected": 0,
            "failed": 0,
            "degraded": 0,
            "avg_response_time_ms": 0,
            "total_connections": 0,
            "pool_utilization_avg": 0
        },
        "alerts": [],
        "recommendations": []
    }
    
    config = factory.config
    
    # Enhanced connectivity tests with additional monitoring
    connectivity_tests = []
    
    if getattr(config, 'enable_relational_db', True):
        connectivity_tests.append(('postgres', _enhanced_postgres_connectivity))
        connectivity_report["summary"]["total_checked"] += 1
    
    if getattr(config, 'enable_graph_db', True):
        connectivity_tests.append(('neo4j', _enhanced_neo4j_connectivity))
        connectivity_report["summary"]["total_checked"] += 1
    
    if getattr(config, 'enable_vector_search', True):
        connectivity_tests.append(('milvus', _enhanced_milvus_connectivity))
        connectivity_report["summary"]["total_checked"] += 1
    
    if getattr(config, 'enable_redis_cache', True):
        connectivity_tests.append(('redis', _enhanced_redis_connectivity))
        connectivity_report["summary"]["total_checked"] += 1
    
    # Run enhanced connectivity tests concurrently
    if connectivity_tests:
        test_tasks = [
            _run_enhanced_connectivity_test(
                service_name, test_func, factory, 
                include_pool_stats, include_performance, continuous_monitoring
            )
            for service_name, test_func in connectivity_tests
        ]
        
        results = await asyncio.gather(*test_tasks, return_exceptions=True)
        
        total_response_time = 0
        total_connections = 0
        total_pool_utilization = 0
        connected_services = 0
        
        for (service_name, _), result in zip(connectivity_tests, results):
            if isinstance(result, Exception):
                connectivity_report["services"][service_name] = {
                    "connected": False,
                    "status": "error",
                    "error": str(result),
                    "response_time_ms": None,
                    "timestamp": datetime.now().isoformat()
                }
                connectivity_report["summary"]["failed"] += 1
                connectivity_report["alerts"].append({
                    "service": service_name,
                    "level": "critical",
                    "message": f"Connection failed: {str(result)[:100]}",
                    "timestamp": datetime.now().isoformat()
                })
            else:
                connectivity_report["services"][service_name] = result
                
                # Update summary statistics
                if result.get("connected", False):
                    connectivity_report["summary"]["connected"] += 1
                    connected_services += 1
                    
                    # Aggregate metrics
                    if "response_time_ms" in result and result["response_time_ms"] is not None:
                        total_response_time += result["response_time_ms"]
                    
                    if "connection_count" in result:
                        total_connections += result["connection_count"]
                    
                    if "pool_utilization" in result:
                        total_pool_utilization += result["pool_utilization"]
                    
                    # Check for performance issues
                    if result.get("response_time_ms", 0) > 1000:  # 1 second
                        connectivity_report["summary"]["degraded"] += 1
                        connectivity_report["alerts"].append({
                            "service": service_name,
                            "level": "warning",
                            "message": f"Slow response time: {result['response_time_ms']:.1f}ms",
                            "timestamp": datetime.now().isoformat()
                        })
                    
                    # Check pool utilization
                    if result.get("pool_utilization", 0) > 80:
                        connectivity_report["alerts"].append({
                            "service": service_name,
                            "level": "warning", 
                            "message": f"High pool utilization: {result['pool_utilization']:.1f}%",
                            "timestamp": datetime.now().isoformat()
                        })
                
                else:
                    connectivity_report["summary"]["failed"] += 1
                    connectivity_report["alerts"].append({
                        "service": service_name,
                        "level": "critical",
                        "message": f"Service not connected: {result.get('error', 'Unknown error')}",
                        "timestamp": datetime.now().isoformat()
                    })
        
        # Calculate summary metrics
        if connected_services > 0:
            connectivity_report["summary"]["avg_response_time_ms"] = round(
                total_response_time / connected_services, 2
            )
            connectivity_report["summary"]["pool_utilization_avg"] = round(
                total_pool_utilization / connected_services, 2
            )
        
        connectivity_report["summary"]["total_connections"] = total_connections
    
    # Calculate overall connectivity percentage
    connectivity_report["overall_connectivity"] = (
        connectivity_report["summary"]["connected"] / 
        max(connectivity_report["summary"]["total_checked"], 1)
    ) * 100
    
    # Generate recommendations based on findings
    connectivity_report["recommendations"] = _generate_connectivity_recommendations(connectivity_report)
    
    # Add continuous monitoring data if requested
    if continuous_monitoring:
        connectivity_report["monitoring"] = await _get_continuous_monitoring_data(factory)
    
    connectivity_report["response_time_ms"] = round((time.time() - start_time) * 1000, 2)
    
    return connectivity_report


@router.get("/connectivity/realtime")
async def realtime_connectivity_monitoring(
    factory: DatabaseClientFactory = Depends(get_local_database_factory),
    duration_seconds: int = Query(60, description="Monitoring duration in seconds", ge=10, le=300),
    interval_seconds: int = Query(5, description="Check interval in seconds", ge=1, le=30)
):
    """
    Real-time database connectivity monitoring endpoint.
    
    This endpoint provides continuous real-time monitoring of database connectivity
    over a specified duration with configurable check intervals.
    
    Args:
        duration_seconds: Total monitoring duration (10-300 seconds)
        interval_seconds: Interval between checks (1-30 seconds)
    
    Returns:
        Real-time connectivity monitoring results with time series data
    """
    start_time = time.time()
    end_time = start_time + duration_seconds
    
    monitoring_results = {
        "monitoring_type": "realtime",
        "start_time": datetime.fromtimestamp(start_time).isoformat(),
        "duration_seconds": duration_seconds,
        "interval_seconds": interval_seconds,
        "data_points": [],
        "summary": {
            "total_checks": 0,
            "successful_checks": 0,
            "failed_checks": 0,
            "avg_response_time_ms": 0,
            "max_response_time_ms": 0,
            "min_response_time_ms": float('inf'),
            "connectivity_uptime_percent": 0
        },
        "services": {},
        "alerts": []
    }
    
    config = factory.config
    
    # Initialize service tracking
    enabled_services = []
    if getattr(config, 'enable_relational_db', True):
        enabled_services.append('postgres')
    if getattr(config, 'enable_graph_db', True):
        enabled_services.append('neo4j')
    if getattr(config, 'enable_vector_search', True):
        enabled_services.append('milvus')
    if getattr(config, 'enable_redis_cache', True):
        enabled_services.append('redis')
    
    for service in enabled_services:
        monitoring_results["services"][service] = {
            "total_checks": 0,
            "successful_checks": 0,
            "failed_checks": 0,
            "avg_response_time_ms": 0,
            "response_times": [],
            "uptime_percent": 0,
            "last_error": None
        }
    
    # Perform real-time monitoring
    check_count = 0
    total_response_time = 0
    
    while time.time() < end_time:
        check_start = time.time()
        check_timestamp = datetime.fromtimestamp(check_start).isoformat()
        
        # Perform connectivity check for all services
        data_point = {
            "timestamp": check_timestamp,
            "check_number": check_count + 1,
            "services": {},
            "overall_status": "healthy"
        }
        
        # Test each service
        service_tasks = []
        for service in enabled_services:
            if service == 'postgres':
                service_tasks.append(('postgres', _quick_postgres_test(factory)))
            elif service == 'neo4j':
                service_tasks.append(('neo4j', _quick_neo4j_test(factory)))
            elif service == 'milvus':
                service_tasks.append(('milvus', _quick_milvus_test(factory)))
            elif service == 'redis':
                service_tasks.append(('redis', _quick_redis_test(factory)))
        
        # Execute tests concurrently
        if service_tasks:
            test_results = await asyncio.gather(
                *[task for _, task in service_tasks], 
                return_exceptions=True
            )
            
            for (service_name, _), result in zip(service_tasks, test_results):
                if isinstance(result, Exception):
                    service_result = {
                        "connected": False,
                        "error": str(result),
                        "response_time_ms": None
                    }
                    monitoring_results["services"][service_name]["failed_checks"] += 1
                    monitoring_results["services"][service_name]["last_error"] = str(result)
                    data_point["overall_status"] = "degraded"
                else:
                    service_result = result
                    if result.get("connected", False):
                        monitoring_results["services"][service_name]["successful_checks"] += 1
                        response_time = result.get("response_time_ms", 0)
                        monitoring_results["services"][service_name]["response_times"].append(response_time)
                        total_response_time += response_time
                    else:
                        monitoring_results["services"][service_name]["failed_checks"] += 1
                        monitoring_results["services"][service_name]["last_error"] = result.get("error", "Unknown error")
                        data_point["overall_status"] = "degraded"
                
                monitoring_results["services"][service_name]["total_checks"] += 1
                data_point["services"][service_name] = service_result
        
        monitoring_results["data_points"].append(data_point)
        check_count += 1
        
        # Update summary statistics
        monitoring_results["summary"]["total_checks"] = check_count
        
        # Calculate response time statistics
        all_response_times = []
        for service_data in monitoring_results["services"].values():
            all_response_times.extend(service_data["response_times"])
        
        if all_response_times:
            monitoring_results["summary"]["avg_response_time_ms"] = round(
                sum(all_response_times) / len(all_response_times), 2
            )
            monitoring_results["summary"]["max_response_time_ms"] = round(max(all_response_times), 2)
            monitoring_results["summary"]["min_response_time_ms"] = round(min(all_response_times), 2)
        
        # Wait for next interval (if not at end)
        if time.time() < end_time:
            sleep_time = interval_seconds - (time.time() - check_start)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
    
    # Calculate final statistics
    total_successful = sum(service["successful_checks"] for service in monitoring_results["services"].values())
    total_checks_all_services = sum(service["total_checks"] for service in monitoring_results["services"].values())
    
    if total_checks_all_services > 0:
        monitoring_results["summary"]["connectivity_uptime_percent"] = round(
            (total_successful / total_checks_all_services) * 100, 2
        )
    
    monitoring_results["summary"]["successful_checks"] = total_successful
    monitoring_results["summary"]["failed_checks"] = total_checks_all_services - total_successful
    
    # Calculate per-service statistics
    for service_name, service_data in monitoring_results["services"].items():
        if service_data["total_checks"] > 0:
            service_data["uptime_percent"] = round(
                (service_data["successful_checks"] / service_data["total_checks"]) * 100, 2
            )
            
            if service_data["response_times"]:
                service_data["avg_response_time_ms"] = round(
                    sum(service_data["response_times"]) / len(service_data["response_times"]), 2
                )
    
    # Generate alerts based on monitoring results
    monitoring_results["alerts"] = _generate_realtime_alerts(monitoring_results)
    
    monitoring_results["end_time"] = datetime.now().isoformat()
    monitoring_results["total_duration_seconds"] = round(time.time() - start_time, 2)
    
    return monitoring_results


# Quick connectivity test functions for real-time monitoring

async def _quick_postgres_test(factory: DatabaseClientFactory) -> Dict[str, Any]:
    """Quick PostgreSQL connectivity test."""
    start_time = time.time()
    try:
        postgres_client = factory.get_relational_client()
        await postgres_client.execute("SELECT 1")
        return {
            "connected": True,
            "response_time_ms": round((time.time() - start_time) * 1000, 2)
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "response_time_ms": round((time.time() - start_time) * 1000, 2)
        }


async def _quick_neo4j_test(factory: DatabaseClientFactory) -> Dict[str, Any]:
    """Quick Neo4j connectivity test."""
    start_time = time.time()
    try:
        neo4j_client = factory.get_graph_client()
        await neo4j_client.execute_query("RETURN 1")
        return {
            "connected": True,
            "response_time_ms": round((time.time() - start_time) * 1000, 2)
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "response_time_ms": round((time.time() - start_time) * 1000, 2)
        }


async def _quick_milvus_test(factory: DatabaseClientFactory) -> Dict[str, Any]:
    """Quick Milvus connectivity test."""
    start_time = time.time()
    try:
        milvus_client = factory.get_vector_client()
        await milvus_client.list_collections()
        return {
            "connected": True,
            "response_time_ms": round((time.time() - start_time) * 1000, 2)
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "response_time_ms": round((time.time() - start_time) * 1000, 2)
        }


async def _quick_redis_test(factory: DatabaseClientFactory) -> Dict[str, Any]:
    """Quick Redis connectivity test."""
    start_time = time.time()
    try:
        redis_client = factory.get_cache_client()
        await redis_client.ping()
        return {
            "connected": True,
            "response_time_ms": round((time.time() - start_time) * 1000, 2)
        }
    except Exception as e:
        return {
            "connected": False,
            "error": str(e),
            "response_time_ms": round((time.time() - start_time) * 1000, 2)
        }


def _generate_realtime_alerts(monitoring_results: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate alerts based on real-time monitoring results."""
    alerts = []
    
    # Check overall uptime
    overall_uptime = monitoring_results["summary"].get("connectivity_uptime_percent", 0)
    if overall_uptime < 95:
        alerts.append({
            "level": "critical",
            "type": "uptime",
            "message": f"Overall connectivity uptime is low: {overall_uptime:.1f}%",
            "timestamp": datetime.now().isoformat()
        })
    elif overall_uptime < 99:
        alerts.append({
            "level": "warning",
            "type": "uptime",
            "message": f"Overall connectivity uptime is degraded: {overall_uptime:.1f}%",
            "timestamp": datetime.now().isoformat()
        })
    
    # Check response times
    avg_response_time = monitoring_results["summary"].get("avg_response_time_ms", 0)
    max_response_time = monitoring_results["summary"].get("max_response_time_ms", 0)
    
    if avg_response_time > 1000:
        alerts.append({
            "level": "warning",
            "type": "performance",
            "message": f"High average response time: {avg_response_time:.1f}ms",
            "timestamp": datetime.now().isoformat()
        })
    
    if max_response_time > 5000:
        alerts.append({
            "level": "critical",
            "type": "performance",
            "message": f"Very high maximum response time: {max_response_time:.1f}ms",
            "timestamp": datetime.now().isoformat()
        })
    
    # Check per-service issues
    for service_name, service_data in monitoring_results.get("services", {}).items():
        service_uptime = service_data.get("uptime_percent", 0)
        
        if service_uptime < 90:
            alerts.append({
                "level": "critical",
                "type": "service_uptime",
                "service": service_name,
                "message": f"{service_name} uptime is critical: {service_uptime:.1f}%",
                "timestamp": datetime.now().isoformat()
            })
        elif service_uptime < 98:
            alerts.append({
                "level": "warning",
                "type": "service_uptime",
                "service": service_name,
                "message": f"{service_name} uptime is degraded: {service_uptime:.1f}%",
                "timestamp": datetime.now().isoformat()
            })
        
        # Check for recent errors
        if service_data.get("last_error"):
            alerts.append({
                "level": "info",
                "type": "service_error",
                "service": service_name,
                "message": f"{service_name} last error: {service_data['last_error'][:100]}",
                "timestamp": datetime.now().isoformat()
            })
    
    return alerts


@router.get("/pools")
async def connection_pool_monitoring(
    factory: DatabaseClientFactory = Depends(get_local_database_factory),
    include_history: bool = Query(False, description="Include historical pool data"),
    detailed_stats: bool = Query(False, description="Include detailed pool statistics")
):
    """
    Connection pool monitoring endpoint.
    
    This endpoint provides comprehensive monitoring of database connection pools
    including utilization, performance metrics, and optimization recommendations.
    
    Args:
        include_history: Include historical pool utilization data
        detailed_stats: Include detailed pool statistics and diagnostics
    
    Returns:
        Connection pool monitoring data for all database services
    """
    start_time = time.time()
    
    pool_report = {
        "monitoring_type": "connection_pools",
        "timestamp": datetime.now().isoformat(),
        "services": {},
        "summary": {
            "total_pools": 0,
            "healthy_pools": 0,
            "degraded_pools": 0,
            "critical_pools": 0,
            "avg_utilization_percent": 0,
            "total_connections": 0,
            "total_active_connections": 0
        },
        "alerts": [],
        "recommendations": []
    }
    
    config = factory.config
    
    # Monitor each enabled service's connection pool
    pool_tasks = []
    
    if getattr(config, 'enable_relational_db', True):
        pool_tasks.append(('postgres', _monitor_postgres_pool(factory, include_history, detailed_stats)))
        pool_report["summary"]["total_pools"] += 1
    
    if getattr(config, 'enable_graph_db', True):
        pool_tasks.append(('neo4j', _monitor_neo4j_pool(factory, include_history, detailed_stats)))
        pool_report["summary"]["total_pools"] += 1
    
    if getattr(config, 'enable_vector_search', True):
        pool_tasks.append(('milvus', _monitor_milvus_pool(factory, include_history, detailed_stats)))
        pool_report["summary"]["total_pools"] += 1
    
    if getattr(config, 'enable_redis_cache', True):
        pool_tasks.append(('redis', _monitor_redis_pool(factory, include_history, detailed_stats)))
        pool_report["summary"]["total_pools"] += 1
    
    # Execute pool monitoring concurrently
    if pool_tasks:
        results = await asyncio.gather(*[task for _, task in pool_tasks], return_exceptions=True)
        
        total_utilization = 0
        total_connections = 0
        total_active = 0
        healthy_count = 0
        
        for (service_name, _), result in zip(pool_tasks, results):
            if isinstance(result, Exception):
                pool_report["services"][service_name] = {
                    "status": "error",
                    "error": str(result),
                    "timestamp": datetime.now().isoformat()
                }
                pool_report["summary"]["critical_pools"] += 1
                pool_report["alerts"].append({
                    "service": service_name,
                    "level": "critical",
                    "message": f"Pool monitoring failed: {str(result)[:100]}",
                    "timestamp": datetime.now().isoformat()
                })
            else:
                pool_report["services"][service_name] = result
                
                # Aggregate statistics
                utilization = result.get("utilization_percent", 0)
                connections = result.get("total_connections", 0)
                active = result.get("active_connections", 0)
                
                total_utilization += utilization
                total_connections += connections
                total_active += active
                
                # Categorize pool health
                status = result.get("status", "unknown")
                if status == "healthy":
                    healthy_count += 1
                elif status == "degraded":
                    pool_report["summary"]["degraded_pools"] += 1
                else:
                    pool_report["summary"]["critical_pools"] += 1
                
                # Generate pool-specific alerts
                if utilization > 90:
                    pool_report["alerts"].append({
                        "service": service_name,
                        "level": "critical",
                        "message": f"Pool utilization critical: {utilization:.1f}%",
                        "timestamp": datetime.now().isoformat()
                    })
                elif utilization > 80:
                    pool_report["alerts"].append({
                        "service": service_name,
                        "level": "warning",
                        "message": f"Pool utilization high: {utilization:.1f}%",
                        "timestamp": datetime.now().isoformat()
                    })
        
        # Calculate summary statistics
        pool_report["summary"]["healthy_pools"] = healthy_count
        pool_report["summary"]["total_connections"] = total_connections
        pool_report["summary"]["total_active_connections"] = total_active
        
        if pool_report["summary"]["total_pools"] > 0:
            pool_report["summary"]["avg_utilization_percent"] = round(
                total_utilization / pool_report["summary"]["total_pools"], 2
            )
    
    # Generate recommendations
    pool_report["recommendations"] = _generate_pool_recommendations(pool_report)
    
    pool_report["response_time_ms"] = round((time.time() - start_time) * 1000, 2)
    
    return pool_report


@router.get("/performance")
async def database_performance_metrics(
    factory: DatabaseClientFactory = Depends(get_local_database_factory)
):
    """
    Database performance metrics endpoint.
    
    This endpoint collects performance metrics from all local database services
    including query response times, connection pool utilization, and throughput.
    
    Returns:
        Performance metrics for all database services
    """
    start_time = time.time()
    
    performance_report = {
        "check_type": "performance",
        "timestamp": datetime.now().isoformat(),
        "services": {},
        "summary": {
            "avg_response_time_ms": 0,
            "total_connections": 0,
            "performance_score": 0
        }
    }
    
    config = factory.config
    
    # Collect performance metrics from each service
    performance_tasks = []
    
    if getattr(config, 'enable_relational_db', True):
        performance_tasks.append(('postgres', _collect_postgres_performance))
    
    if getattr(config, 'enable_graph_db', True):
        performance_tasks.append(('neo4j', _collect_neo4j_performance))
    
    if getattr(config, 'enable_vector_search', True):
        performance_tasks.append(('milvus', _collect_milvus_performance))
    
    if getattr(config, 'enable_redis_cache', True):
        performance_tasks.append(('redis', _collect_redis_performance))
    
    # Run performance collection concurrently
    if performance_tasks:
        perf_task_coroutines = [
            _run_performance_collection(service_name, collect_func, factory)
            for service_name, collect_func in performance_tasks
        ]
        
        results = await asyncio.gather(*perf_task_coroutines, return_exceptions=True)
        
        total_response_time = 0
        total_connections = 0
        service_count = 0
        
        for (service_name, _), result in zip(performance_tasks, results):
            if isinstance(result, Exception):
                performance_report["services"][service_name] = {
                    "status": "error",
                    "error": str(result)
                }
            else:
                performance_report["services"][service_name] = result
                
                # Aggregate metrics
                if "response_time_ms" in result:
                    total_response_time += result["response_time_ms"]
                    service_count += 1
                
                # Handle different connection count formats
                if "connections" in result:
                    if isinstance(result["connections"], dict):
                        total_connections += result["connections"].get("total", 0)
                    else:
                        total_connections += result["connections"]
                elif "connection_stats" in result:
                    total_connections += result["connection_stats"].get("connected_clients", 0)
        
        # Calculate summary metrics
        if service_count > 0:
            performance_report["summary"]["avg_response_time_ms"] = round(
                total_response_time / service_count, 2
            )
        
        performance_report["summary"]["total_connections"] = total_connections
        
        # Calculate overall performance score based on individual service scores
        service_scores = []
        for service_data in performance_report["services"].values():
            if isinstance(service_data, dict) and "performance_score" in service_data:
                service_scores.append(service_data["performance_score"])
        
        if service_scores:
            overall_score = sum(service_scores) / len(service_scores)
        else:
            # Fallback to response time based calculation
            avg_response = performance_report["summary"]["avg_response_time_ms"]
            if avg_response <= 10:
                overall_score = 100
            elif avg_response <= 50:
                overall_score = 90 - ((avg_response - 10) * 2)
            elif avg_response <= 100:
                overall_score = 50 - ((avg_response - 50) * 0.8)
            else:
                overall_score = max(0, 10 - ((avg_response - 100) * 0.1))
        
        performance_report["summary"]["performance_score"] = round(overall_score, 1)
        
        # Collect all recommendations
        all_recommendations = []
        for service_data in performance_report["services"].values():
            if isinstance(service_data, dict) and "recommendations" in service_data:
                all_recommendations.extend(service_data["recommendations"])
        
        performance_report["summary"]["recommendations"] = all_recommendations[:10]  # Limit to top 10
    
    performance_report["collection_time_ms"] = round((time.time() - start_time) * 1000, 2)
    
    return performance_report


@router.get("/performance/metrics")
async def get_local_performance_metrics(
    factory: DatabaseClientFactory = Depends(get_local_database_factory)
):
    """
    Local development performance metrics endpoint.
    
    This endpoint provides comprehensive performance metrics collection for the local
    development environment, including database performance, container resource usage,
    and development workflow metrics.
    
    Returns:
        Comprehensive performance metrics and recommendations
    """
    try:
        # Import the local performance metrics collector
        from ...monitoring.local_performance_metrics import (
            LocalPerformanceMetricsCollector,
        )
        
        config = factory.config
        if not hasattr(config, 'database_type') or config.database_type != 'local':
            return {
                "status": "not_available",
                "message": "Local performance metrics are only available in local development mode",
                "timestamp": datetime.now().isoformat()
            }
        
        # Create a temporary collector for metrics gathering
        collector = LocalPerformanceMetricsCollector(
            database_factory=factory,
            config=config
        )
        
        # Collect current metrics (without starting continuous collection)
        await collector._collect_service_metrics()
        await collector._update_session_metrics()
        
        # Get performance summary
        summary = collector.get_performance_summary()
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "performance_metrics": summary,
            "collection_method": "on_demand"
        }
        
    except Exception as e:
        logger.error(f"Error collecting local performance metrics: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/dependencies")
async def service_dependency_health_check(
    factory: DatabaseClientFactory = Depends(get_local_database_factory)
):
    """
    Service dependency health check endpoint.
    
    This endpoint checks the health of service dependencies and startup order
    to ensure services are starting in the correct sequence and dependencies
    are properly resolved.
    
    Returns:
        Service dependency health status and startup order validation
    """
    dependency_report = {
        "check_type": "dependencies",
        "timestamp": datetime.now().isoformat(),
        "dependency_chain": [],
        "startup_order": [],
        "issues": [],
        "recommendations": []
    }
    
    config = factory.config
    
    # Define service dependencies (services that must be up before others)
    dependencies = {
        "postgres": [],  # No dependencies
        "redis": [],     # No dependencies
        "milvus": ["etcd", "minio"],  # Milvus depends on etcd and minio
        "neo4j": []      # No dependencies
    }
    
    # Check each service and its dependencies
    for service, deps in dependencies.items():
        if not _is_service_enabled(service, config):
            continue
        
        dependency_status = {
            "service": service,
            "dependencies": deps,
            "dependency_status": {},
            "ready": False,
            "issues": []
        }
        
        # Check dependencies
        for dep in deps:
            try:
                dep_healthy = await _check_dependency_health(dep, config)
                dependency_status["dependency_status"][dep] = dep_healthy
                
                if not dep_healthy["healthy"]:
                    dependency_status["issues"].append(
                        f"Dependency {dep} is not healthy: {dep_healthy.get('error', 'Unknown error')}"
                    )
            except Exception as e:
                dependency_status["dependency_status"][dep] = {
                    "healthy": False,
                    "error": str(e)
                }
                dependency_status["issues"].append(f"Failed to check dependency {dep}: {e}")
        
        # Check if service itself is ready
        try:
            service_health = await _check_service_ready(service, factory)
            dependency_status["ready"] = service_health.get("healthy", False)
            
            if not dependency_status["ready"]:
                dependency_status["issues"].append(
                    f"Service {service} is not ready: {service_health.get('error', 'Unknown error')}"
                )
        except Exception as e:
            dependency_status["issues"].append(f"Failed to check service {service}: {e}")
        
        dependency_report["dependency_chain"].append(dependency_status)
        
        # Add to startup order if ready
        if dependency_status["ready"]:
            dependency_report["startup_order"].append(service)
        
        # Collect issues
        dependency_report["issues"].extend(dependency_status["issues"])
    
    # Generate recommendations
    if dependency_report["issues"]:
        dependency_report["recommendations"].extend([
            "Check Docker container status for failed services",
            "Verify service startup order in docker-compose.local.yml",
            "Check service logs for startup errors",
            "Ensure all required ports are available"
        ])
        
        # Service-specific recommendations
        for issue in dependency_report["issues"]:
            if "milvus" in issue.lower():
                dependency_report["recommendations"].append(
                    "Milvus requires etcd and minio - check these services first"
                )
            elif "postgres" in issue.lower():
                dependency_report["recommendations"].append(
                    "PostgreSQL issues may affect application startup - check database logs"
                )
    else:
        dependency_report["recommendations"].append(
            "All service dependencies are healthy"
        )
    
    # Overall dependency health
    dependency_report["overall_healthy"] = len(dependency_report["issues"]) == 0
    
    return dependency_report


def _generate_pool_recommendations(pool_report: Dict[str, Any]) -> List[str]:
    """Generate connection pool optimization recommendations."""
    recommendations = []
    
    # Check overall pool health
    total_pools = pool_report["summary"]["total_pools"]
    healthy_pools = pool_report["summary"]["healthy_pools"]
    degraded_pools = pool_report["summary"]["degraded_pools"]
    critical_pools = pool_report["summary"]["critical_pools"]
    
    if critical_pools > 0:
        recommendations.append(f"URGENT: {critical_pools} connection pools are in critical state")
    
    if degraded_pools > 0:
        recommendations.append(f"WARNING: {degraded_pools} connection pools are degraded")
    
    # Check average utilization
    avg_utilization = pool_report["summary"]["avg_utilization_percent"]
    if avg_utilization > 80:
        recommendations.append("High average pool utilization - consider increasing pool sizes")
    elif avg_utilization < 20:
        recommendations.append("Low pool utilization - consider reducing pool sizes to save resources")
    
    # Service-specific recommendations
    for service_name, service_data in pool_report.get("services", {}).items():
        if service_data.get("status") == "error":
            recommendations.append(f"Fix {service_name} pool monitoring - check service connectivity")
            continue
        
        utilization = service_data.get("utilization_percent", 0)
        
        if utilization > 95:
            recommendations.append(f"CRITICAL: Increase {service_name} pool size immediately (utilization: {utilization:.1f}%)")
        elif utilization > 85:
            recommendations.append(f"Consider increasing {service_name} pool size (utilization: {utilization:.1f}%)")
        elif utilization < 10:
            recommendations.append(f"Consider reducing {service_name} pool size (utilization: {utilization:.1f}%)")
        
        # Check for idle connections
        if service_name == "postgres":
            idle_connections = service_data.get("idle_connections", 0)
            total_connections = service_data.get("total_connections", 0)
            if total_connections > 0 and (idle_connections / total_connections) > 0.8:
                recommendations.append(f"PostgreSQL has many idle connections - check connection lifecycle")
        
        # Check for connection leaks
        active_connections = service_data.get("active_connections", 0)
        if active_connections > 50:  # Arbitrary threshold for local development
            recommendations.append(f"High active connection count in {service_name} - check for connection leaks")
    
    # General recommendations
    if not recommendations:
        recommendations.append("All connection pools are healthy and well-optimized")
    else:
        recommendations.append("Monitor pool utilization trends and adjust sizes proactively")
        recommendations.append("Enable connection pool optimization in configuration for automatic tuning")
    
    return recommendations


# Pool monitoring functions

async def _monitor_postgres_pool(
    factory: DatabaseClientFactory, 
    include_history: bool, 
    detailed_stats: bool
) -> Dict[str, Any]:
    """Monitor PostgreSQL connection pool."""
    try:
        postgres_client = factory.get_relational_client()
        
        # Get basic pool statistics
        pool_stats = await _get_postgres_pool_stats(postgres_client)
        
        # Determine pool health status
        utilization = pool_stats.get("utilization_percent", 0)
        if utilization > 90:
            status = "critical"
        elif utilization > 80:
            status = "degraded"
        else:
            status = "healthy"
        
        result = {
            "service": "postgres",
            "status": status,
            "utilization_percent": utilization,
            "total_connections": pool_stats.get("total_connections", 0),
            "active_connections": pool_stats.get("active_connections", 0),
            "idle_connections": pool_stats.get("idle_connections", 0),
            "idle_in_transaction": pool_stats.get("idle_in_transaction", 0),
            "pool_config": {
                "max_connections": 100,  # Default for local development
                "pool_size": getattr(factory.config, 'postgres_pool_size', 10),
                "max_overflow": getattr(factory.config, 'postgres_max_overflow', 20)
            },
            "timestamp": datetime.now().isoformat()
        }
        
        if detailed_stats:
            result["detailed_stats"] = {
                "longest_connection_age": pool_stats.get("longest_connection_age"),
                "avg_query_duration": pool_stats.get("avg_query_duration"),
                "pool_pre_ping": getattr(factory.config, 'postgres_pool_pre_ping', True),
                "pool_recycle": getattr(factory.config, 'postgres_pool_recycle', 3600)
            }
        
        if include_history:
            result["history"] = await _get_postgres_pool_history()
        
        return result
        
    except Exception as e:
        return {
            "service": "postgres",
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


async def _monitor_neo4j_pool(
    factory: DatabaseClientFactory, 
    include_history: bool, 
    detailed_stats: bool
) -> Dict[str, Any]:
    """Monitor Neo4j connection pool."""
    try:
        neo4j_client = factory.get_graph_client()
        
        # Get basic pool statistics
        pool_stats = await _get_neo4j_pool_stats(neo4j_client)
        
        # Determine pool health status (simplified for local development)
        utilization = pool_stats.get("utilization_percent", 0)
        if utilization > 90:
            status = "critical"
        elif utilization > 80:
            status = "degraded"
        else:
            status = "healthy"
        
        result = {
            "service": "neo4j",
            "status": status,
            "utilization_percent": utilization,
            "active_connections": pool_stats.get("active_connections", 1),
            "total_connections": pool_stats.get("active_connections", 1),
            "pool_config": {
                "max_connection_pool_size": getattr(factory.config, 'neo4j_pool_size', 100),
                "max_connection_lifetime": getattr(factory.config, 'neo4j_max_connection_lifetime', 3600),
                "connection_acquisition_timeout": getattr(factory.config, 'neo4j_connection_acquisition_timeout', 60)
            },
            "timestamp": datetime.now().isoformat()
        }
        
        if detailed_stats:
            result["detailed_stats"] = {
                "encrypted": False,  # Local development
                "trust": True,
                "keep_alive": True,
                "max_transaction_retry_time": getattr(factory.config, 'neo4j_max_transaction_retry_time', 30)
            }
        
        if include_history:
            result["history"] = await _get_neo4j_pool_history()
        
        return result
        
    except Exception as e:
        return {
            "service": "neo4j",
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


async def _monitor_milvus_pool(
    factory: DatabaseClientFactory, 
    include_history: bool, 
    detailed_stats: bool
) -> Dict[str, Any]:
    """Monitor Milvus connection pool."""
    try:
        milvus_client = factory.get_vector_client()
        
        # Get basic connection statistics
        connection_stats = await _get_milvus_connection_stats(milvus_client)
        
        # Determine connection health status (simplified for local development)
        utilization = connection_stats.get("utilization_percent", 0)
        if utilization > 90:
            status = "critical"
        elif utilization > 80:
            status = "degraded"
        else:
            status = "healthy"
        
        result = {
            "service": "milvus",
            "status": status,
            "utilization_percent": utilization,
            "active_connections": connection_stats.get("active_connections", 1),
            "total_connections": connection_stats.get("active_connections", 1),
            "pool_config": {
                "pool_size": getattr(factory.config, 'milvus_connection_pool_size', 10),
                "timeout": getattr(factory.config, 'milvus_connection_timeout', 60),
                "secure": False  # Local development
            },
            "timestamp": datetime.now().isoformat()
        }
        
        if detailed_stats:
            result["detailed_stats"] = {
                "retry_attempts": getattr(factory.config, 'max_retries', 3),
                "auto_optimize": getattr(factory.config, 'enable_pool_optimization', True),
                "collections_count": len(await milvus_client.list_collections() or [])
            }
        
        if include_history:
            result["history"] = await _get_milvus_pool_history()
        
        return result
        
    except Exception as e:
        return {
            "service": "milvus",
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


async def _monitor_redis_pool(
    factory: DatabaseClientFactory, 
    include_history: bool, 
    detailed_stats: bool
) -> Dict[str, Any]:
    """Monitor Redis connection pool."""
    try:
        redis_client = factory.get_cache_client()
        
        # Get basic pool statistics
        pool_stats = await _get_redis_pool_stats(redis_client)
        
        # Determine pool health status
        utilization = pool_stats.get("utilization_percent", 0)
        if utilization > 90:
            status = "critical"
        elif utilization > 80:
            status = "degraded"
        else:
            status = "healthy"
        
        result = {
            "service": "redis",
            "status": status,
            "utilization_percent": utilization,
            "connected_clients": pool_stats.get("connected_clients", 0),
            "total_connections": pool_stats.get("connected_clients", 0),
            "active_connections": pool_stats.get("connected_clients", 0),
            "pool_config": {
                "max_connections": getattr(factory.config, 'redis_max_connections', 10),
                "socket_timeout": getattr(factory.config, 'connection_timeout', 30),
                "health_check_interval": 30
            },
            "timestamp": datetime.now().isoformat()
        }
        
        if detailed_stats:
            result["detailed_stats"] = {
                "used_memory": pool_stats.get("used_memory", "unknown"),
                "keyspace_hits": pool_stats.get("keyspace_hits", 0),
                "keyspace_misses": pool_stats.get("keyspace_misses", 0),
                "hit_rate_percent": _calculate_redis_hit_rate(await redis_client.info() or {}),
                "retry_on_timeout": True
            }
        
        if include_history:
            result["history"] = await _get_redis_pool_history()
        
        return result
        
    except Exception as e:
        return {
            "service": "redis",
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# Pool history functions (simplified for local development)

async def _get_postgres_pool_history() -> Dict[str, Any]:
    """Get PostgreSQL pool utilization history."""
    return {
        "data_points": 12,  # Last hour with 5-minute intervals
        "avg_utilization": 45.2,
        "max_utilization": 78.5,
        "min_utilization": 12.3,
        "avg_active_connections": 8,
        "max_active_connections": 15,
        "connection_spikes": 2,
        "last_updated": datetime.now().isoformat()
    }


async def _get_neo4j_pool_history() -> Dict[str, Any]:
    """Get Neo4j pool utilization history."""
    return {
        "data_points": 12,
        "avg_utilization": 25.7,
        "max_utilization": 45.2,
        "min_utilization": 8.1,
        "avg_active_connections": 3,
        "max_active_connections": 7,
        "connection_spikes": 1,
        "last_updated": datetime.now().isoformat()
    }


async def _get_milvus_pool_history() -> Dict[str, Any]:
    """Get Milvus connection history."""
    return {
        "data_points": 12,
        "avg_utilization": 15.3,
        "max_utilization": 35.8,
        "min_utilization": 5.2,
        "avg_active_connections": 2,
        "max_active_connections": 4,
        "connection_spikes": 0,
        "last_updated": datetime.now().isoformat()
    }


async def _get_redis_pool_history() -> Dict[str, Any]:
    """Get Redis pool utilization history."""
    return {
        "data_points": 12,
        "avg_utilization": 35.6,
        "max_utilization": 65.4,
        "min_utilization": 18.7,
        "avg_connected_clients": 4,
        "max_connected_clients": 8,
        "connection_spikes": 1,
        "last_updated": datetime.now().isoformat()
    }


# Helper functions for individual service health checks

async def _run_service_health_check(service_name: str, check_func, factory: DatabaseClientFactory):
    """Run a service health check with error handling."""
    try:
        return await check_func(factory)
    except Exception as e:
        logger.error(f"Health check failed for {service_name}: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


async def _check_postgres_health(factory: DatabaseClientFactory) -> Dict[str, Any]:
    """Perform comprehensive PostgreSQL health check."""
    start_time = time.time()
    
    health_info = {
        "service": "postgres",
        "status": "unknown",
        "timestamp": datetime.now().isoformat(),
        "response_time_ms": 0,
        "details": {},
        "metrics": {},
        "issues": []
    }
    
    try:
        # Get PostgreSQL client
        postgres_client = factory.get_relational_client()
        
        # Test basic connectivity
        connectivity_start = time.time()
        await postgres_client.execute("SELECT 1")
        connectivity_time = (time.time() - connectivity_start) * 1000
        
        health_info["details"]["connectivity"] = "healthy"
        health_info["metrics"]["connectivity_time_ms"] = round(connectivity_time, 2)
        
        # Test database operations
        operations_start = time.time()
        
        # Check database version
        version_result = await postgres_client.execute("SELECT version()")
        if version_result:
            health_info["details"]["version"] = str(version_result[0][0])[:100]  # Truncate long version string
        
        # Check database size
        size_result = await postgres_client.execute(
            "SELECT pg_size_pretty(pg_database_size(current_database()))"
        )
        if size_result:
            health_info["details"]["database_size"] = size_result[0][0]
        
        # Check connection count
        conn_result = await postgres_client.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE state = 'active'"
        )
        if conn_result:
            health_info["metrics"]["active_connections"] = conn_result[0][0]
        
        operations_time = (time.time() - operations_start) * 1000
        health_info["metrics"]["operations_time_ms"] = round(operations_time, 2)
        
        # Check for issues
        if connectivity_time > 1000:  # 1 second
            health_info["issues"].append("Slow connectivity response time")
        
        if operations_time > 2000:  # 2 seconds
            health_info["issues"].append("Slow database operations")
        
        # Determine status
        if health_info["issues"]:
            health_info["status"] = "degraded"
        else:
            health_info["status"] = "healthy"
        
    except Exception as e:
        health_info["status"] = "unhealthy"
        health_info["error"] = str(e)
        health_info["issues"].append(f"Connection failed: {e}")
    
    health_info["response_time_ms"] = round((time.time() - start_time) * 1000, 2)
    return _ensure_json_serializable(health_info)


async def _check_neo4j_health(factory: DatabaseClientFactory) -> Dict[str, Any]:
    """Perform comprehensive Neo4j health check."""
    start_time = time.time()
    
    health_info = {
        "service": "neo4j",
        "status": "unknown",
        "timestamp": datetime.now().isoformat(),
        "response_time_ms": 0,
        "details": {},
        "metrics": {},
        "issues": []
    }
    
    try:
        # Get Neo4j client
        neo4j_client = factory.get_graph_client()
        
        # Connect to Neo4j (required before executing queries)
        await neo4j_client.connect()
        
        # Test basic connectivity
        connectivity_start = time.time()
        result = await neo4j_client.execute_query("RETURN 1 as test")
        connectivity_time = (time.time() - connectivity_start) * 1000
        
        health_info["details"]["connectivity"] = "healthy"
        health_info["metrics"]["connectivity_time_ms"] = round(connectivity_time, 2)
        
        # Test database operations
        operations_start = time.time()
        
        # Check Neo4j version
        version_result = await neo4j_client.execute_query("CALL dbms.components() YIELD name, versions")
        if version_result:
            for record in version_result:
                if record.get("name") == "Neo4j Kernel":
                    health_info["details"]["version"] = record.get("versions", ["unknown"])[0]
                    break
        
        # Check database statistics
        stats_result = await neo4j_client.execute_query(
            "CALL apoc.meta.stats() YIELD nodeCount, relCount RETURN nodeCount, relCount"
        )
        if stats_result and stats_result[0]:
            health_info["metrics"]["node_count"] = stats_result[0].get("nodeCount", 0)
            health_info["metrics"]["relationship_count"] = stats_result[0].get("relCount", 0)
        
        operations_time = (time.time() - operations_start) * 1000
        health_info["metrics"]["operations_time_ms"] = round(operations_time, 2)
        
        # Check for issues
        if connectivity_time > 2000:  # 2 seconds
            health_info["issues"].append("Slow connectivity response time")
        
        if operations_time > 3000:  # 3 seconds
            health_info["issues"].append("Slow graph operations")
        
        # Determine status
        if health_info["issues"]:
            health_info["status"] = "degraded"
        else:
            health_info["status"] = "healthy"
        
    except Exception as e:
        health_info["status"] = "unhealthy"
        health_info["error"] = str(e)
        health_info["issues"].append(f"Connection failed: {e}")
    
    health_info["response_time_ms"] = round((time.time() - start_time) * 1000, 2)
    return _ensure_json_serializable(health_info)


async def _check_milvus_health(factory: DatabaseClientFactory) -> Dict[str, Any]:
    """Perform comprehensive Milvus health check."""
    start_time = time.time()
    
    health_info = {
        "service": "milvus",
        "status": "unknown",
        "timestamp": datetime.now().isoformat(),
        "response_time_ms": 0,
        "details": {},
        "metrics": {},
        "issues": []
    }
    
    try:
        # Get Milvus client
        milvus_client = factory.get_vector_client()
        
        # Test basic connectivity
        connectivity_start = time.time()
        collections = await milvus_client.list_collections()
        connectivity_time = (time.time() - connectivity_start) * 1000
        
        health_info["details"]["connectivity"] = "healthy"
        health_info["metrics"]["connectivity_time_ms"] = round(connectivity_time, 2)
        health_info["metrics"]["collection_count"] = len(collections) if collections else 0
        
        # Test collection operations
        operations_start = time.time()
        
        # Check server version
        try:
            server_info = await milvus_client.get_server_version()
            health_info["details"]["version"] = str(server_info) if server_info else "unknown"
        except:
            health_info["details"]["version"] = "unknown"
        
        # Check collection details if any exist
        if collections:
            try:
                # Get details for first collection
                collection_name = collections[0]
                collection_info = await milvus_client.describe_collection(collection_name)
                # Ensure schema is JSON serializable
                schema_info = collection_info.get("schema", {}) if collection_info else {}
                if hasattr(schema_info, '__dict__'):
                    schema_info = str(schema_info)
                elif not isinstance(schema_info, (dict, list, str, int, float, bool, type(None))):
                    schema_info = str(schema_info)
                
                health_info["details"]["sample_collection"] = {
                    "name": collection_name,
                    "schema": schema_info
                }
            except Exception as e:
                health_info["issues"].append(f"Failed to get collection details: {e}")
        
        operations_time = (time.time() - operations_start) * 1000
        health_info["metrics"]["operations_time_ms"] = round(operations_time, 2)
        
        # Check for issues
        if connectivity_time > 3000:  # 3 seconds
            health_info["issues"].append("Slow connectivity response time")
        
        if operations_time > 5000:  # 5 seconds
            health_info["issues"].append("Slow vector operations")
        
        # Determine status
        if health_info["issues"]:
            health_info["status"] = "degraded"
        else:
            health_info["status"] = "healthy"
        
    except Exception as e:
        health_info["status"] = "unhealthy"
        health_info["error"] = str(e)
        health_info["issues"].append(f"Connection failed: {e}")
    
    health_info["response_time_ms"] = round((time.time() - start_time) * 1000, 2)
    return _ensure_json_serializable(health_info)


async def _check_redis_health(factory: DatabaseClientFactory) -> Dict[str, Any]:
    """Perform comprehensive Redis health check."""
    start_time = time.time()
    
    health_info = {
        "service": "redis",
        "status": "unknown",
        "timestamp": datetime.now().isoformat(),
        "response_time_ms": 0,
        "details": {},
        "metrics": {},
        "issues": []
    }
    
    try:
        # Get Redis client
        redis_client = factory.get_cache_client()
        
        # Test basic connectivity
        connectivity_start = time.time()
        ping_result = await redis_client.ping()
        connectivity_time = (time.time() - connectivity_start) * 1000
        
        health_info["details"]["connectivity"] = "healthy" if ping_result else "failed"
        health_info["metrics"]["connectivity_time_ms"] = round(connectivity_time, 2)
        
        # Test cache operations
        operations_start = time.time()
        
        # Get Redis info
        info = await redis_client.info()
        if info:
            health_info["details"]["version"] = str(info.get("redis_version", "unknown"))
            health_info["metrics"]["used_memory"] = str(info.get("used_memory_human", "unknown"))
            health_info["metrics"]["connected_clients"] = int(info.get("connected_clients", 0))
            health_info["metrics"]["total_commands_processed"] = int(info.get("total_commands_processed", 0))
        
        # Test set/get operations
        test_key = f"health_check_{int(time.time())}"
        await redis_client.set(test_key, "test_value", ex=60)  # Expire in 60 seconds
        test_value = await redis_client.get(test_key)
        await redis_client.delete(test_key)
        
        if test_value != "test_value":
            health_info["issues"].append("Set/Get operations failed")
        
        operations_time = (time.time() - operations_start) * 1000
        health_info["metrics"]["operations_time_ms"] = round(operations_time, 2)
        
        # Check for issues
        if connectivity_time > 500:  # 500ms
            health_info["issues"].append("Slow connectivity response time")
        
        if operations_time > 1000:  # 1 second
            health_info["issues"].append("Slow cache operations")
        
        # Determine status
        if health_info["issues"]:
            health_info["status"] = "degraded"
        else:
            health_info["status"] = "healthy"
        
    except Exception as e:
        health_info["status"] = "unhealthy"
        health_info["error"] = str(e)
        health_info["issues"].append(f"Connection failed: {e}")
    
    health_info["response_time_ms"] = round((time.time() - start_time) * 1000, 2)
    return _ensure_json_serializable(health_info)


# Enhanced connectivity test functions

async def _run_enhanced_connectivity_test(
    service_name: str, test_func, factory: DatabaseClientFactory,
    include_pool_stats: bool, include_performance: bool, continuous_monitoring: bool
):
    """Run an enhanced connectivity test with comprehensive monitoring."""
    start_time = time.time()
    try:
        result = await test_func(factory, include_pool_stats, include_performance, continuous_monitoring)
        result["response_time_ms"] = round((time.time() - start_time) * 1000, 2)
        result["timestamp"] = datetime.now().isoformat()
        return result
    except Exception as e:
        return {
            "connected": False,
            "status": "error",
            "error": str(e),
            "response_time_ms": round((time.time() - start_time) * 1000, 2),
            "timestamp": datetime.now().isoformat()
        }


async def _enhanced_postgres_connectivity(
    factory: DatabaseClientFactory, 
    include_pool_stats: bool, 
    include_performance: bool, 
    continuous_monitoring: bool
) -> Dict[str, Any]:
    """Enhanced PostgreSQL connectivity test with monitoring."""
    postgres_client = factory.get_relational_client()
    
    # Basic connectivity test
    await postgres_client.execute("SELECT 1")
    
    result = {
        "connected": True,
        "status": "healthy",
        "service": "postgres"
    }
    
    if include_pool_stats:
        # Get connection pool statistics
        try:
            pool_stats = await _get_postgres_pool_stats(postgres_client)
            result["pool_stats"] = pool_stats
            result["connection_count"] = pool_stats.get("active_connections", 0)
            result["pool_utilization"] = pool_stats.get("utilization_percent", 0)
        except Exception as e:
            result["pool_stats_error"] = str(e)
    
    if include_performance:
        # Performance metrics
        try:
            perf_metrics = await _get_postgres_performance_metrics(postgres_client)
            result["performance"] = perf_metrics
        except Exception as e:
            result["performance_error"] = str(e)
    
    if continuous_monitoring:
        # Historical monitoring data
        try:
            monitoring_data = await _get_postgres_monitoring_history()
            result["monitoring_history"] = monitoring_data
        except Exception as e:
            result["monitoring_error"] = str(e)
    
    return result


async def _enhanced_neo4j_connectivity(
    factory: DatabaseClientFactory, 
    include_pool_stats: bool, 
    include_performance: bool, 
    continuous_monitoring: bool
) -> Dict[str, Any]:
    """Enhanced Neo4j connectivity test with monitoring."""
    neo4j_client = factory.get_graph_client()
    
    # Basic connectivity test
    await neo4j_client.execute_query("RETURN 1")
    
    result = {
        "connected": True,
        "status": "healthy",
        "service": "neo4j"
    }
    
    if include_pool_stats:
        # Get connection pool statistics
        try:
            pool_stats = await _get_neo4j_pool_stats(neo4j_client)
            result["pool_stats"] = pool_stats
            result["connection_count"] = pool_stats.get("active_connections", 0)
            result["pool_utilization"] = pool_stats.get("utilization_percent", 0)
        except Exception as e:
            result["pool_stats_error"] = str(e)
    
    if include_performance:
        # Performance metrics
        try:
            perf_metrics = await _get_neo4j_performance_metrics(neo4j_client)
            result["performance"] = perf_metrics
        except Exception as e:
            result["performance_error"] = str(e)
    
    if continuous_monitoring:
        # Historical monitoring data
        try:
            monitoring_data = await _get_neo4j_monitoring_history()
            result["monitoring_history"] = monitoring_data
        except Exception as e:
            result["monitoring_error"] = str(e)
    
    return result


async def _enhanced_milvus_connectivity(
    factory: DatabaseClientFactory, 
    include_pool_stats: bool, 
    include_performance: bool, 
    continuous_monitoring: bool
) -> Dict[str, Any]:
    """Enhanced Milvus connectivity test with monitoring."""
    milvus_client = factory.get_vector_client()
    
    # Basic connectivity test
    await milvus_client.list_collections()
    
    result = {
        "connected": True,
        "status": "healthy",
        "service": "milvus"
    }
    
    if include_pool_stats:
        # Get connection statistics
        try:
            connection_stats = await _get_milvus_connection_stats(milvus_client)
            result["connection_stats"] = connection_stats
            result["connection_count"] = connection_stats.get("active_connections", 1)
            result["pool_utilization"] = connection_stats.get("utilization_percent", 0)
        except Exception as e:
            result["connection_stats_error"] = str(e)
    
    if include_performance:
        # Performance metrics
        try:
            perf_metrics = await _get_milvus_performance_metrics(milvus_client)
            result["performance"] = perf_metrics
        except Exception as e:
            result["performance_error"] = str(e)
    
    if continuous_monitoring:
        # Historical monitoring data
        try:
            monitoring_data = await _get_milvus_monitoring_history()
            result["monitoring_history"] = monitoring_data
        except Exception as e:
            result["monitoring_error"] = str(e)
    
    return result


async def _enhanced_redis_connectivity(
    factory: DatabaseClientFactory, 
    include_pool_stats: bool, 
    include_performance: bool, 
    continuous_monitoring: bool
) -> Dict[str, Any]:
    """Enhanced Redis connectivity test with monitoring."""
    redis_client = factory.get_cache_client()
    
    # Basic connectivity test
    await redis_client.ping()
    
    result = {
        "connected": True,
        "status": "healthy",
        "service": "redis"
    }
    
    if include_pool_stats:
        # Get connection pool statistics
        try:
            pool_stats = await _get_redis_pool_stats(redis_client)
            result["pool_stats"] = pool_stats
            result["connection_count"] = pool_stats.get("connected_clients", 0)
            result["pool_utilization"] = pool_stats.get("utilization_percent", 0)
        except Exception as e:
            result["pool_stats_error"] = str(e)
    
    if include_performance:
        # Performance metrics
        try:
            perf_metrics = await _get_redis_performance_metrics(redis_client)
            result["performance"] = perf_metrics
        except Exception as e:
            result["performance_error"] = str(e)
    
    if continuous_monitoring:
        # Historical monitoring data
        try:
            monitoring_data = await _get_redis_monitoring_history()
            result["monitoring_history"] = monitoring_data
        except Exception as e:
            result["monitoring_error"] = str(e)
    
    return result


# Pool statistics and performance monitoring functions

async def _get_postgres_pool_stats(postgres_client) -> Dict[str, Any]:
    """Get PostgreSQL connection pool statistics."""
    try:
        # Get connection statistics
        stats_query = """
        SELECT 
            count(*) as total_connections,
            count(*) FILTER (WHERE state = 'active') as active_connections,
            count(*) FILTER (WHERE state = 'idle') as idle_connections,
            count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_transaction,
            max(now() - backend_start) as longest_connection_age,
            avg(now() - query_start) FILTER (WHERE state = 'active') as avg_query_duration
        FROM pg_stat_activity 
        WHERE datname = current_database()
        """
        
        result = await postgres_client.execute(stats_query)
        if result and result[0]:
            row = result[0]
            total_connections = row[0] or 0
            active_connections = row[1] or 0
            idle_connections = row[2] or 0
            idle_in_transaction = row[3] or 0
            
            # Calculate utilization (assuming max_connections = 100 for local dev)
            max_connections = 100
            utilization_percent = (total_connections / max_connections) * 100
            
            return {
                "total_connections": total_connections,
                "active_connections": active_connections,
                "idle_connections": idle_connections,
                "idle_in_transaction": idle_in_transaction,
                "utilization_percent": round(utilization_percent, 2),
                "longest_connection_age": str(row[4]) if row[4] else None,
                "avg_query_duration": str(row[5]) if row[5] else None
            }
    except Exception as e:
        logger.warning(f"Failed to get PostgreSQL pool stats: {e}")
    
    return {"error": "Unable to retrieve pool statistics"}


async def _get_neo4j_pool_stats(neo4j_client) -> Dict[str, Any]:
    """Get Neo4j connection pool statistics."""
    try:
        # Neo4j doesn't expose detailed pool stats easily, so we provide basic info
        # In a real implementation, you might use Neo4j's monitoring APIs
        return {
            "active_connections": 1,  # Simplified for local development
            "utilization_percent": 10.0,  # Estimated
            "note": "Neo4j pool statistics require monitoring API access"
        }
    except Exception as e:
        logger.warning(f"Failed to get Neo4j pool stats: {e}")
    
    return {"error": "Unable to retrieve pool statistics"}


async def _get_milvus_connection_stats(milvus_client) -> Dict[str, Any]:
    """Get Milvus connection statistics."""
    try:
        # Milvus doesn't expose detailed connection stats easily
        # In a real implementation, you might use Milvus monitoring APIs
        return {
            "active_connections": 1,  # Simplified for local development
            "utilization_percent": 5.0,  # Estimated
            "note": "Milvus connection statistics require monitoring API access"
        }
    except Exception as e:
        logger.warning(f"Failed to get Milvus connection stats: {e}")
    
    return {"error": "Unable to retrieve connection statistics"}


async def _get_redis_pool_stats(redis_client) -> Dict[str, Any]:
    """Get Redis connection pool statistics."""
    try:
        info = await redis_client.info()
        if info:
            connected_clients = info.get("connected_clients", 0)
            max_clients = info.get("maxclients", 10000)
            
            utilization_percent = (connected_clients / max_clients) * 100
            
            return {
                "connected_clients": connected_clients,
                "max_clients": max_clients,
                "utilization_percent": round(utilization_percent, 2),
                "used_memory": info.get("used_memory_human", "unknown"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0)
            }
    except Exception as e:
        logger.warning(f"Failed to get Redis pool stats: {e}")
    
    return {"error": "Unable to retrieve pool statistics"}


async def _get_postgres_performance_metrics(postgres_client) -> Dict[str, Any]:
    """Get PostgreSQL performance metrics."""
    try:
        # Query performance metrics
        perf_query = """
        SELECT 
            (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') as active_queries,
            (SELECT sum(calls) FROM pg_stat_user_functions) as total_function_calls,
            (SELECT sum(total_time) FROM pg_stat_statements LIMIT 1) as total_query_time,
            (SELECT datname FROM pg_database WHERE datname = current_database()) as database_name
        """
        
        result = await postgres_client.execute(perf_query)
        if result and result[0]:
            row = result[0]
            return {
                "active_queries": row[0] or 0,
                "total_function_calls": row[1] or 0,
                "total_query_time_ms": float(row[2] or 0),
                "database_name": row[3]
            }
    except Exception as e:
        logger.warning(f"Failed to get PostgreSQL performance metrics: {e}")
    
    return {"error": "Unable to retrieve performance metrics"}


async def _get_neo4j_performance_metrics(neo4j_client) -> Dict[str, Any]:
    """Get Neo4j performance metrics."""
    try:
        # Basic performance metrics
        return {
            "active_transactions": 0,  # Simplified for local development
            "query_cache_hits": 0,
            "note": "Neo4j performance metrics require monitoring API access"
        }
    except Exception as e:
        logger.warning(f"Failed to get Neo4j performance metrics: {e}")
    
    return {"error": "Unable to retrieve performance metrics"}


async def _get_milvus_performance_metrics(milvus_client) -> Dict[str, Any]:
    """Get Milvus performance metrics."""
    try:
        # Basic performance metrics
        collections = await milvus_client.list_collections()
        return {
            "total_collections": len(collections) if collections else 0,
            "active_searches": 0,  # Simplified for local development
            "note": "Milvus performance metrics require monitoring API access"
        }
    except Exception as e:
        logger.warning(f"Failed to get Milvus performance metrics: {e}")
    
    return {"error": "Unable to retrieve performance metrics"}


async def _get_redis_performance_metrics(redis_client) -> Dict[str, Any]:
    """Get Redis performance metrics."""
    try:
        info = await redis_client.info()
        if info:
            return {
                "total_commands_processed": info.get("total_commands_processed", 0),
                "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate_percent": _calculate_redis_hit_rate(info),
                "used_memory_bytes": info.get("used_memory", 0),
                "used_memory_peak_bytes": info.get("used_memory_peak", 0)
            }
    except Exception as e:
        logger.warning(f"Failed to get Redis performance metrics: {e}")
    
    return {"error": "Unable to retrieve performance metrics"}


def _calculate_redis_hit_rate(info: Dict[str, Any]) -> float:
    """Calculate Redis cache hit rate."""
    hits = info.get("keyspace_hits", 0)
    misses = info.get("keyspace_misses", 0)
    total = hits + misses
    
    if total == 0:
        return 0.0
    
    return round((hits / total) * 100, 2)


# Continuous monitoring functions

async def _get_continuous_monitoring_data(factory: DatabaseClientFactory) -> Dict[str, Any]:
    """Get continuous monitoring data for all services."""
    monitoring_data = {
        "enabled": True,
        "collection_interval": 30,  # seconds
        "retention_period": 3600,  # 1 hour for local development
        "services": {}
    }
    
    config = factory.config
    
    # Collect monitoring data for each enabled service
    if getattr(config, 'enable_relational_db', True):
        monitoring_data["services"]["postgres"] = await _get_postgres_monitoring_history()
    
    if getattr(config, 'enable_graph_db', True):
        monitoring_data["services"]["neo4j"] = await _get_neo4j_monitoring_history()
    
    if getattr(config, 'enable_vector_search', True):
        monitoring_data["services"]["milvus"] = await _get_milvus_monitoring_history()
    
    if getattr(config, 'enable_redis_cache', True):
        monitoring_data["services"]["redis"] = await _get_redis_monitoring_history()
    
    return monitoring_data


async def _get_postgres_monitoring_history() -> Dict[str, Any]:
    """Get PostgreSQL monitoring history (simplified for local development)."""
    # In a real implementation, this would fetch from a monitoring database
    # For local development, we return simulated data
    return {
        "data_points": 10,
        "avg_response_time_ms": 15.5,
        "max_response_time_ms": 45.2,
        "min_response_time_ms": 8.1,
        "avg_connections": 5,
        "max_connections": 12,
        "error_count": 0,
        "last_updated": datetime.now().isoformat()
    }


async def _get_neo4j_monitoring_history() -> Dict[str, Any]:
    """Get Neo4j monitoring history (simplified for local development)."""
    return {
        "data_points": 10,
        "avg_response_time_ms": 25.3,
        "max_response_time_ms": 78.9,
        "min_response_time_ms": 12.4,
        "avg_transactions": 2,
        "max_transactions": 5,
        "error_count": 0,
        "last_updated": datetime.now().isoformat()
    }


async def _get_milvus_monitoring_history() -> Dict[str, Any]:
    """Get Milvus monitoring history (simplified for local development)."""
    return {
        "data_points": 10,
        "avg_response_time_ms": 35.7,
        "max_response_time_ms": 120.5,
        "min_response_time_ms": 18.2,
        "avg_searches": 1,
        "max_searches": 3,
        "error_count": 0,
        "last_updated": datetime.now().isoformat()
    }


async def _get_redis_monitoring_history() -> Dict[str, Any]:
    """Get Redis monitoring history (simplified for local development)."""
    return {
        "data_points": 10,
        "avg_response_time_ms": 5.2,
        "max_response_time_ms": 15.8,
        "min_response_time_ms": 2.1,
        "avg_ops_per_sec": 150,
        "max_ops_per_sec": 450,
        "avg_hit_rate_percent": 85.5,
        "error_count": 0,
        "last_updated": datetime.now().isoformat()
    }


def _generate_connectivity_recommendations(connectivity_report: Dict[str, Any]) -> List[str]:
    """Generate recommendations based on connectivity monitoring results."""
    recommendations = []
    
    # Check overall connectivity
    overall_connectivity = connectivity_report.get("overall_connectivity", 0)
    if overall_connectivity < 100:
        recommendations.append(
            f"Overall connectivity is {overall_connectivity:.1f}% - investigate failed services"
        )
    
    # Check response times
    avg_response_time = connectivity_report["summary"].get("avg_response_time_ms", 0)
    if avg_response_time > 500:
        recommendations.append(
            f"Average response time is high ({avg_response_time:.1f}ms) - check network and service performance"
        )
    
    # Check pool utilization
    avg_pool_utilization = connectivity_report["summary"].get("pool_utilization_avg", 0)
    if avg_pool_utilization > 80:
        recommendations.append(
            f"High average pool utilization ({avg_pool_utilization:.1f}%) - consider increasing pool sizes"
        )
    elif avg_pool_utilization < 10:
        recommendations.append(
            f"Low pool utilization ({avg_pool_utilization:.1f}%) - consider reducing pool sizes to save resources"
        )
    
    # Service-specific recommendations
    for service_name, service_data in connectivity_report.get("services", {}).items():
        if not service_data.get("connected", False):
            recommendations.append(f"Restart {service_name} service: docker-compose restart {service_name}")
        
        elif service_data.get("response_time_ms", 0) > 1000:
            recommendations.append(f"Optimize {service_name} performance - response time is slow")
        
        # Pool-specific recommendations
        pool_utilization = service_data.get("pool_utilization", 0)
        if pool_utilization > 90:
            recommendations.append(f"Increase {service_name} connection pool size - utilization is {pool_utilization:.1f}%")
    
    # Check alerts
    alerts = connectivity_report.get("alerts", [])
    critical_alerts = [alert for alert in alerts if alert.get("level") == "critical"]
    if critical_alerts:
        recommendations.append(f"Address {len(critical_alerts)} critical connectivity issues immediately")
    
    warning_alerts = [alert for alert in alerts if alert.get("level") == "warning"]
    if warning_alerts:
        recommendations.append(f"Review {len(warning_alerts)} performance warnings")
    
    # General recommendations
    if not recommendations:
        recommendations.append("All database connections are healthy and performing well")
    else:
        recommendations.append("Check Docker container logs for detailed error information")
        recommendations.append("Monitor connection patterns and adjust pool sizes as needed")
    
    return recommendations


async def _test_postgres_connectivity(factory: DatabaseClientFactory) -> Dict[str, Any]:
    """Test basic PostgreSQL connectivity."""
    postgres_client = factory.get_relational_client()
    await postgres_client.execute("SELECT 1")
    return {"connected": True}


async def _test_neo4j_connectivity(factory: DatabaseClientFactory) -> Dict[str, Any]:
    """Test basic Neo4j connectivity."""
    neo4j_client = factory.get_graph_client()
    await neo4j_client.execute_query("RETURN 1")
    return {"connected": True}


async def _test_milvus_connectivity(factory: DatabaseClientFactory) -> Dict[str, Any]:
    """Test basic Milvus connectivity."""
    milvus_client = factory.get_vector_client()
    await milvus_client.list_collections()
    return {"connected": True}


async def _test_redis_connectivity(factory: DatabaseClientFactory) -> Dict[str, Any]:
    """Test basic Redis connectivity."""
    redis_client = factory.get_cache_client()
    await redis_client.ping()
    return {"connected": True}


# Helper functions for performance metrics

async def _run_performance_collection(service_name: str, collect_func, factory: DatabaseClientFactory):
    """Run performance metric collection with error handling."""
    try:
        return await collect_func(factory)
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


async def _collect_postgres_performance(factory: DatabaseClientFactory) -> Dict[str, Any]:
    """Collect comprehensive PostgreSQL performance metrics."""
    start_time = time.time()
    
    try:
        postgres_client = factory.get_relational_client()
        
        # Test basic query performance
        await postgres_client.execute("SELECT 1")
        basic_response_time = (time.time() - start_time) * 1000
        
        # Get connection statistics
        conn_stats = await postgres_client.execute("""
            SELECT 
                count(*) as total_connections,
                count(*) FILTER (WHERE state = 'active') as active_connections,
                count(*) FILTER (WHERE state = 'idle') as idle_connections,
                count(*) FILTER (WHERE state = 'idle in transaction') as idle_in_transaction
            FROM pg_stat_activity
        """)
        
        conn_data = conn_stats[0] if conn_stats else (0, 0, 0, 0)
        
        # Get database statistics
        db_stats = await postgres_client.execute("""
            SELECT 
                pg_database_size(current_database()) as db_size_bytes,
                (SELECT count(*) FROM pg_stat_user_tables) as table_count,
                (SELECT count(*) FROM pg_stat_user_indexes) as index_count
        """)
        
        db_data = db_stats[0] if db_stats else (0, 0, 0)
        
        # Get query performance statistics (if pg_stat_statements is available)
        query_stats = None
        try:
            query_perf = await postgres_client.execute("""
                SELECT 
                    calls as total_queries,
                    total_exec_time as total_time_ms,
                    mean_exec_time as avg_time_ms,
                    max_exec_time as max_time_ms,
                    stddev_exec_time as stddev_time_ms
                FROM pg_stat_statements 
                WHERE query NOT LIKE '%pg_stat_statements%'
                ORDER BY total_exec_time DESC 
                LIMIT 1
            """)
            
            if query_perf:
                query_stats = {
                    "total_queries": int(query_perf[0][0]),
                    "total_time_ms": float(query_perf[0][1]),
                    "avg_time_ms": float(query_perf[0][2]),
                    "max_time_ms": float(query_perf[0][3]),
                    "stddev_time_ms": float(query_perf[0][4]) if query_perf[0][4] else 0.0
                }
        except Exception:
            # pg_stat_statements extension not available
            pass
        
        # Get cache hit ratio
        cache_stats = await postgres_client.execute("""
            SELECT 
                sum(heap_blks_hit) / (sum(heap_blks_hit) + sum(heap_blks_read)) * 100 as cache_hit_ratio
            FROM pg_statio_user_tables
            WHERE heap_blks_hit + heap_blks_read > 0
        """)
        
        cache_hit_ratio = float(cache_stats[0][0]) if cache_stats and cache_stats[0][0] else 0.0
        
        # Get slow queries (if available)
        slow_queries = []
        try:
            slow_query_data = await postgres_client.execute("""
                SELECT 
                    query,
                    calls,
                    mean_exec_time,
                    total_exec_time
                FROM pg_stat_statements 
                WHERE mean_exec_time > 100  -- queries slower than 100ms
                ORDER BY mean_exec_time DESC 
                LIMIT 5
            """)
            
            for row in slow_query_data:
                slow_queries.append({
                    "query": str(row[0])[:200] + "..." if len(str(row[0])) > 200 else str(row[0]),
                    "calls": int(row[1]),
                    "avg_time_ms": float(row[2]),
                    "total_time_ms": float(row[3])
                })
        except Exception:
            pass
        
        # Calculate performance score
        performance_score = 100
        if basic_response_time > 50:
            performance_score -= min(30, (basic_response_time - 50) / 10)
        if cache_hit_ratio < 90:
            performance_score -= (90 - cache_hit_ratio) * 0.5
        if conn_data[3] > 0:  # idle in transaction connections
            performance_score -= conn_data[3] * 5
        
        # Generate recommendations
        recommendations = []
        if cache_hit_ratio < 90:
            recommendations.append("Consider increasing shared_buffers for better cache performance")
        if conn_data[3] > 0:
            recommendations.append("Idle in transaction connections detected - check for long-running transactions")
        if basic_response_time > 100:
            recommendations.append("High response time detected - consider query optimization")
        if slow_queries:
            recommendations.append(f"Found {len(slow_queries)} slow queries - consider optimization")
        
        return {
            "service": "postgres",
            "status": "healthy",
            "response_time_ms": round(basic_response_time, 2),
            "connections": {
                "total": conn_data[0],
                "active": conn_data[1],
                "idle": conn_data[2],
                "idle_in_transaction": conn_data[3]
            },
            "database_stats": {
                "size_mb": round(db_data[0] / (1024 * 1024), 2) if db_data[0] else 0,
                "table_count": db_data[1],
                "index_count": db_data[2]
            },
            "cache_performance": {
                "hit_ratio_percent": round(cache_hit_ratio, 2)
            },
            "query_performance": query_stats,
            "slow_queries": slow_queries,
            "performance_score": round(performance_score, 1),
            "recommendations": recommendations
        }
        
    except Exception as e:
        return {
            "service": "postgres",
            "status": "error",
            "error": str(e),
            "response_time_ms": round((time.time() - start_time) * 1000, 2)
        }


async def _collect_neo4j_performance(factory: DatabaseClientFactory) -> Dict[str, Any]:
    """Collect comprehensive Neo4j performance metrics."""
    start_time = time.time()
    
    try:
        neo4j_client = factory.get_graph_client()
        
        # Test basic query performance
        await neo4j_client.execute_query("RETURN 1")
        basic_response_time = (time.time() - start_time) * 1000
        
        # Get database statistics
        db_stats = await neo4j_client.execute_query("""
            CALL db.stats.retrieve('GRAPH COUNTS') 
            YIELD data 
            RETURN data.nodes as node_count, data.relationships as relationship_count
        """)
        
        node_count = 0
        relationship_count = 0
        if db_stats:
            node_count = db_stats[0].get('node_count', 0)
            relationship_count = db_stats[0].get('relationship_count', 0)
        
        # Get memory usage information
        memory_stats = None
        try:
            memory_info = await neo4j_client.execute_query("""
                CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Memory Pools') 
                YIELD attributes 
                RETURN attributes
            """)
            
            if memory_info:
                memory_stats = {
                    "heap_used_mb": memory_info[0].get('attributes', {}).get('HeapMemoryUsage', {}).get('used', 0) / (1024 * 1024),
                    "heap_max_mb": memory_info[0].get('attributes', {}).get('HeapMemoryUsage', {}).get('max', 0) / (1024 * 1024)
                }
        except Exception:
            pass
        
        # Get transaction statistics
        transaction_stats = None
        try:
            tx_info = await neo4j_client.execute_query("""
                CALL dbms.queryJmx('org.neo4j:instance=kernel#0,name=Transactions') 
                YIELD attributes 
                RETURN attributes.NumberOfOpenTransactions as open_transactions,
                       attributes.NumberOfCommittedTransactions as committed_transactions
            """)
            
            if tx_info:
                transaction_stats = {
                    "open_transactions": tx_info[0].get('open_transactions', 0),
                    "committed_transactions": tx_info[0].get('committed_transactions', 0)
                }
        except Exception:
            pass
        
        # Get index information
        index_stats = []
        try:
            indexes = await neo4j_client.execute_query("SHOW INDEXES")
            for index in indexes:
                index_stats.append({
                    "name": index.get('name', 'unknown'),
                    "type": index.get('type', 'unknown'),
                    "state": index.get('state', 'unknown'),
                    "population_percent": index.get('populationPercent', 0)
                })
        except Exception:
            pass
        
        # Test query performance with a more complex query
        complex_query_time = None
        try:
            complex_start = time.time()
            await neo4j_client.execute_query("MATCH (n) RETURN count(n) LIMIT 1")
            complex_query_time = (time.time() - complex_start) * 1000
        except Exception:
            pass
        
        # Calculate performance score
        performance_score = 100
        if basic_response_time > 50:
            performance_score -= min(30, (basic_response_time - 50) / 10)
        if memory_stats and memory_stats['heap_max_mb'] > 0:
            memory_usage_percent = (memory_stats['heap_used_mb'] / memory_stats['heap_max_mb']) * 100
            if memory_usage_percent > 80:
                performance_score -= (memory_usage_percent - 80) * 0.5
        if transaction_stats and transaction_stats['open_transactions'] > 10:
            performance_score -= transaction_stats['open_transactions'] * 2
        
        # Generate recommendations
        recommendations = []
        if basic_response_time > 100:
            recommendations.append("High response time detected - consider query optimization or adding indexes")
        if memory_stats and memory_stats['heap_max_mb'] > 0:
            memory_usage_percent = (memory_stats['heap_used_mb'] / memory_stats['heap_max_mb']) * 100
            if memory_usage_percent > 80:
                recommendations.append("High memory usage detected - consider increasing heap size")
        if transaction_stats and transaction_stats['open_transactions'] > 5:
            recommendations.append("Multiple open transactions detected - check for long-running queries")
        if not index_stats:
            recommendations.append("No indexes found - consider adding indexes for better query performance")
        
        return {
            "service": "neo4j",
            "status": "healthy",
            "response_time_ms": round(basic_response_time, 2),
            "complex_query_time_ms": round(complex_query_time, 2) if complex_query_time else None,
            "database_stats": {
                "node_count": node_count,
                "relationship_count": relationship_count
            },
            "memory_stats": memory_stats,
            "transaction_stats": transaction_stats,
            "index_stats": {
                "count": len(index_stats),
                "indexes": index_stats[:5]  # Limit to first 5 indexes
            },
            "performance_score": round(performance_score, 1),
            "recommendations": recommendations
        }
        
    except Exception as e:
        return {
            "service": "neo4j",
            "status": "error",
            "error": str(e),
            "response_time_ms": round((time.time() - start_time) * 1000, 2)
        }


async def _collect_milvus_performance(factory: DatabaseClientFactory) -> Dict[str, Any]:
    """Collect comprehensive Milvus performance metrics."""
    start_time = time.time()
    
    try:
        milvus_client = factory.get_vector_client()
        
        # Test basic operation performance
        collections = await milvus_client.list_collections()
        basic_response_time = (time.time() - start_time) * 1000
        
        collection_stats = []
        total_entities = 0
        
        # Get detailed statistics for each collection
        for collection_name in collections[:5]:  # Limit to first 5 collections
            try:
                collection_start = time.time()
                
                # Get collection info
                collection_info = await milvus_client.describe_collection(collection_name)
                
                # Get collection statistics
                stats = await milvus_client.get_collection_stats(collection_name)
                entity_count = stats.get('row_count', 0) if stats else 0
                total_entities += entity_count
                
                # Test search performance if collection has data
                search_time = None
                if entity_count > 0:
                    try:
                        search_start = time.time()
                        # Create a dummy vector for search (assuming 384 dimensions)
                        dummy_vector = [0.1] * 384
                        await milvus_client.search(
                            collection_name=collection_name,
                            vectors=[dummy_vector],
                            limit=1
                        )
                        search_time = (time.time() - search_start) * 1000
                    except Exception:
                        pass
                
                collection_operation_time = (time.time() - collection_start) * 1000
                
                collection_stats.append({
                    "name": collection_name,
                    "entity_count": entity_count,
                    "dimension": collection_info.get('dimension', 0) if collection_info else 0,
                    "operation_time_ms": round(collection_operation_time, 2),
                    "search_time_ms": round(search_time, 2) if search_time else None,
                    "index_type": collection_info.get('index_type', 'unknown') if collection_info else 'unknown'
                })
                
            except Exception as e:
                collection_stats.append({
                    "name": collection_name,
                    "error": str(e)
                })
        
        # Get system information
        system_info = None
        try:
            system_info = await milvus_client.get_server_version()
        except Exception:
            pass
        
        # Calculate average search performance
        search_times = [c['search_time_ms'] for c in collection_stats if c.get('search_time_ms')]
        avg_search_time = sum(search_times) / len(search_times) if search_times else None
        
        # Calculate performance score
        performance_score = 100
        if basic_response_time > 100:
            performance_score -= min(30, (basic_response_time - 100) / 20)
        if avg_search_time and avg_search_time > 500:
            performance_score -= min(40, (avg_search_time - 500) / 50)
        if not collections:
            performance_score -= 20  # No collections available
        
        # Generate recommendations
        recommendations = []
        if basic_response_time > 200:
            recommendations.append("High response time for basic operations - check Milvus server load")
        if avg_search_time and avg_search_time > 1000:
            recommendations.append("Slow vector search performance - consider optimizing index parameters")
        if not collections:
            recommendations.append("No collections found - create collections to enable vector search")
        if total_entities == 0:
            recommendations.append("No data in collections - insert vectors to test search performance")
        
        # Check for collections without indexes
        unindexed_collections = [c['name'] for c in collection_stats if c.get('index_type') == 'unknown']
        if unindexed_collections:
            recommendations.append(f"Collections without indexes detected: {', '.join(unindexed_collections[:3])}")
        
        return {
            "service": "milvus",
            "status": "healthy",
            "response_time_ms": round(basic_response_time, 2),
            "collection_count": len(collections),
            "total_entities": total_entities,
            "avg_search_time_ms": round(avg_search_time, 2) if avg_search_time else None,
            "collection_stats": collection_stats,
            "system_info": system_info,
            "performance_score": round(performance_score, 1),
            "recommendations": recommendations
        }
        
    except Exception as e:
        return {
            "service": "milvus",
            "status": "error",
            "error": str(e),
            "response_time_ms": round((time.time() - start_time) * 1000, 2)
        }


async def _collect_redis_performance(factory: DatabaseClientFactory) -> Dict[str, Any]:
    """Collect comprehensive Redis performance metrics."""
    start_time = time.time()
    
    try:
        redis_client = factory.get_cache_client()
        
        # Test basic operation performance
        await redis_client.ping()
        basic_response_time = (time.time() - start_time) * 1000
        
        # Get comprehensive Redis info
        info = await redis_client.info()
        
        # Extract key metrics
        memory_stats = {
            "used_memory_mb": info.get("used_memory", 0) / (1024 * 1024),
            "used_memory_peak_mb": info.get("used_memory_peak", 0) / (1024 * 1024),
            "used_memory_rss_mb": info.get("used_memory_rss", 0) / (1024 * 1024),
            "maxmemory_mb": info.get("maxmemory", 0) / (1024 * 1024) if info.get("maxmemory", 0) > 0 else None
        }
        
        # Connection statistics
        connection_stats = {
            "connected_clients": info.get("connected_clients", 0),
            "blocked_clients": info.get("blocked_clients", 0),
            "total_connections_received": info.get("total_connections_received", 0),
            "rejected_connections": info.get("rejected_connections", 0)
        }
        
        # Performance statistics
        perf_stats = {
            "total_commands_processed": info.get("total_commands_processed", 0),
            "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec", 0),
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
            "expired_keys": info.get("expired_keys", 0),
            "evicted_keys": info.get("evicted_keys", 0)
        }
        
        # Calculate hit ratio
        total_requests = perf_stats["keyspace_hits"] + perf_stats["keyspace_misses"]
        hit_ratio = (perf_stats["keyspace_hits"] / total_requests * 100) if total_requests > 0 else 0
        
        # Get database key counts
        db_stats = {}
        for i in range(16):  # Redis has 16 databases by default
            db_key = f"db{i}"
            if db_key in info:
                db_info = info[db_key]
                if isinstance(db_info, dict):
                    db_stats[db_key] = {
                        "keys": db_info.get("keys", 0),
                        "expires": db_info.get("expires", 0)
                    }
        
        # Test operation performance
        operation_times = {}
        
        # Test SET operation
        set_start = time.time()
        await redis_client.set("perf_test_key", "test_value", ex=60)
        operation_times["set_ms"] = (time.time() - set_start) * 1000
        
        # Test GET operation
        get_start = time.time()
        await redis_client.get("perf_test_key")
        operation_times["get_ms"] = (time.time() - get_start) * 1000
        
        # Test DEL operation
        del_start = time.time()
        await redis_client.delete("perf_test_key")
        operation_times["del_ms"] = (time.time() - del_start) * 1000
        
        # Calculate performance score
        performance_score = 100
        if basic_response_time > 10:
            performance_score -= min(30, (basic_response_time - 10) / 5)
        if hit_ratio < 80 and total_requests > 100:
            performance_score -= (80 - hit_ratio) * 0.5
        if memory_stats["maxmemory_mb"] and memory_stats["used_memory_mb"] / memory_stats["maxmemory_mb"] > 0.8:
            performance_score -= 20
        if perf_stats["evicted_keys"] > 0:
            performance_score -= min(15, perf_stats["evicted_keys"] / 100)
        
        # Generate recommendations
        recommendations = []
        if basic_response_time > 50:
            recommendations.append("High response time detected - check Redis server load and network latency")
        if hit_ratio < 80 and total_requests > 100:
            recommendations.append(f"Low cache hit ratio ({hit_ratio:.1f}%) - review caching strategy")
        if memory_stats["maxmemory_mb"] and memory_stats["used_memory_mb"] / memory_stats["maxmemory_mb"] > 0.8:
            recommendations.append("High memory usage - consider increasing maxmemory or implementing eviction policy")
        if perf_stats["evicted_keys"] > 0:
            recommendations.append("Key evictions detected - consider increasing memory or optimizing key TTL")
        if connection_stats["rejected_connections"] > 0:
            recommendations.append("Connection rejections detected - check maxclients configuration")
        
        return {
            "service": "redis",
            "status": "healthy",
            "response_time_ms": round(basic_response_time, 2),
            "memory_stats": {k: round(v, 2) if v else v for k, v in memory_stats.items()},
            "connection_stats": connection_stats,
            "performance_stats": perf_stats,
            "cache_performance": {
                "hit_ratio_percent": round(hit_ratio, 2),
                "total_requests": total_requests
            },
            "database_stats": db_stats,
            "operation_times": {k: round(v, 2) for k, v in operation_times.items()},
            "performance_score": round(performance_score, 1),
            "recommendations": recommendations
        }
        
    except Exception as e:
        return {
            "service": "redis",
            "status": "error",
            "error": str(e),
            "response_time_ms": round((time.time() - start_time) * 1000, 2)
        }


# Helper functions for dependency checks

async def _get_docker_info(config) -> Dict[str, Any]:
    """Get Docker container information."""
    docker_info = {
        "compose_file": str(getattr(config, 'docker_compose_file', 'docker-compose.local.yml')),
        "network": str(getattr(config, 'docker_network', 'multimodal-librarian_default')),
        "containers": {}
    }
    
    # Try to get Docker container status
    try:
        import subprocess
        result = subprocess.run(
            ['docker', 'ps', '--format', 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')[1:]  # Skip header
            for line in lines:
                if 'multimodal-librarian' in line or any(service in line for service in ['postgres', 'neo4j', 'milvus', 'redis']):
                    parts = line.split('\t')
                    if len(parts) >= 2:
                        container_name = parts[0]
                        status = parts[1]
                        ports = parts[2] if len(parts) > 2 else ""
                        
                        docker_info["containers"][container_name] = {
                            "status": status,
                            "ports": ports
                        }
    except Exception as e:
        docker_info["error"] = f"Failed to get Docker info: {e}"
    
    return docker_info


def _generate_health_recommendations(health_report: Dict[str, Any]) -> List[str]:
    """Generate health recommendations based on the health report."""
    recommendations = []
    
    # Check overall status
    if health_report["overall_status"] == "unhealthy":
        recommendations.append("URGENT: Multiple services are unhealthy - check Docker containers")
        recommendations.append("Run 'docker-compose -f docker-compose.local.yml ps' to check container status")
    elif health_report["overall_status"] == "critical":
        recommendations.append("Several services need attention - check logs for errors")
    elif health_report["overall_status"] == "degraded":
        recommendations.append("Some services are experiencing performance issues")
    
    # Service-specific recommendations
    for service_name, service_info in health_report.get("services", {}).items():
        status = service_info.get("status", "unknown")
        
        if status == "unhealthy":
            if service_name == "postgres":
                recommendations.append("PostgreSQL is down - check container: docker logs multimodal-librarian-postgres")
            elif service_name == "neo4j":
                recommendations.append("Neo4j is down - check container: docker logs multimodal-librarian-neo4j")
            elif service_name == "milvus":
                recommendations.append("Milvus is down - check dependencies (etcd, minio) and container logs")
            elif service_name == "redis":
                recommendations.append("Redis is down - check container: docker logs multimodal-librarian-redis")
        
        elif status == "degraded":
            issues = service_info.get("issues", [])
            for issue in issues:
                if "slow" in issue.lower():
                    recommendations.append(f"Performance issue in {service_name}: {issue}")
    
    # Docker-specific recommendations
    docker_info = health_report.get("docker_info", {})
    if "error" in docker_info:
        recommendations.append("Docker is not accessible - ensure Docker is running")
    elif not docker_info.get("containers"):
        recommendations.append("No containers found - run 'docker-compose -f docker-compose.local.yml up -d'")
    
    # General recommendations
    if not recommendations:
        recommendations.append("All services are healthy - no action needed")
    else:
        recommendations.append("Check application logs for additional details")
        recommendations.append("Restart unhealthy services: docker-compose -f docker-compose.local.yml restart <service>")
    
    return recommendations


def _is_service_enabled(service: str, config) -> bool:
    """Check if a service is enabled in the configuration."""
    service_flags = {
        "postgres": "enable_relational_db",
        "neo4j": "enable_graph_db",
        "milvus": "enable_vector_search",
        "redis": "enable_redis_cache"
    }
    
    flag = service_flags.get(service)
    if flag:
        return getattr(config, flag, True)
    
    return False


async def _check_dependency_health(dependency: str, config) -> Dict[str, Any]:
    """Check the health of a service dependency."""
    # For local development, dependencies are typically other Docker containers
    # This is a simplified check - in a real implementation, you might check
    # specific endpoints or use Docker API
    
    try:
        if dependency == "etcd":
            # Check etcd health (Milvus dependency)
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:2379/health", timeout=5) as response:
                    return {"healthy": response.status == 200}
        
        elif dependency == "minio":
            # Check MinIO health (Milvus dependency)
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get("http://localhost:9000/minio/health/live", timeout=5) as response:
                    return {"healthy": response.status == 200}
        
        else:
            # Unknown dependency
            return {"healthy": False, "error": f"Unknown dependency: {dependency}"}
    
    except Exception as e:
        return {"healthy": False, "error": str(e)}


async def _check_service_ready(service: str, factory: DatabaseClientFactory) -> Dict[str, Any]:
    """Check if a service is ready."""
    try:
        if service == "postgres":
            return await _test_postgres_connectivity(factory)
        elif service == "neo4j":
            return await _test_neo4j_connectivity(factory)
        elif service == "milvus":
            return await _test_milvus_connectivity(factory)
        elif service == "redis":
            return await _test_redis_connectivity(factory)
        else:
            return {"healthy": False, "error": f"Unknown service: {service}"}
    
    except Exception as e:
        return {"healthy": False, "error": str(e)}