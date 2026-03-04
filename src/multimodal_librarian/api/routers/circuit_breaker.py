"""
Circuit Breaker API Router.

This module provides REST API endpoints for monitoring and managing
circuit breakers in the system.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Any, List, Optional
from datetime import datetime
import logging

from ...monitoring.circuit_breaker import (
    get_circuit_breaker_manager,
    CircuitBreakerManager,
    CircuitBreakerConfig,
    CircuitState
)
from ...monitoring.service_health_monitor_enhanced import get_enhanced_service_health_monitor
from ...logging_config import get_logger

logger = get_logger("circuit_breaker_api")

router = APIRouter(prefix="/api/circuit-breaker", tags=["circuit-breaker"])


def get_circuit_breaker_manager_dependency() -> CircuitBreakerManager:
    """Dependency to get circuit breaker manager."""
    return get_circuit_breaker_manager()


@router.get("/status", response_model=Dict[str, Any])
async def get_circuit_breaker_status(
    manager: CircuitBreakerManager = Depends(get_circuit_breaker_manager_dependency)
):
    """
    Get status of all circuit breakers.
    
    Returns comprehensive status information for all registered circuit breakers
    including their current state, metrics, and configuration.
    """
    try:
        status = manager.get_all_status()
        summary = manager.get_summary()
        
        return {
            "summary": summary,
            "circuit_breakers": status,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get circuit breaker status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status/{circuit_breaker_name}", response_model=Dict[str, Any])
async def get_circuit_breaker_status_by_name(
    circuit_breaker_name: str,
    manager: CircuitBreakerManager = Depends(get_circuit_breaker_manager_dependency)
):
    """
    Get status of a specific circuit breaker.
    
    Args:
        circuit_breaker_name: Name of the circuit breaker
        
    Returns:
        Detailed status information for the specified circuit breaker
    """
    try:
        circuit_breaker = manager.get_circuit_breaker(circuit_breaker_name)
        
        if circuit_breaker is None:
            raise HTTPException(
                status_code=404, 
                detail=f"Circuit breaker '{circuit_breaker_name}' not found"
            )
        
        status = circuit_breaker.get_status()
        
        return {
            "circuit_breaker": status,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get circuit breaker status for '{circuit_breaker_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary", response_model=Dict[str, Any])
async def get_circuit_breaker_summary(
    manager: CircuitBreakerManager = Depends(get_circuit_breaker_manager_dependency)
):
    """
    Get summary statistics for all circuit breakers.
    
    Returns high-level summary including counts by state and overall health percentage.
    """
    try:
        summary = manager.get_summary()
        
        return {
            "summary": summary,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get circuit breaker summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset/{circuit_breaker_name}")
async def reset_circuit_breaker(
    circuit_breaker_name: str,
    manager: CircuitBreakerManager = Depends(get_circuit_breaker_manager_dependency)
):
    """
    Manually reset a circuit breaker to CLOSED state.
    
    Args:
        circuit_breaker_name: Name of the circuit breaker to reset
        
    Returns:
        Success message and new status
    """
    try:
        circuit_breaker = manager.get_circuit_breaker(circuit_breaker_name)
        
        if circuit_breaker is None:
            raise HTTPException(
                status_code=404, 
                detail=f"Circuit breaker '{circuit_breaker_name}' not found"
            )
        
        old_state = circuit_breaker.get_state()
        circuit_breaker.reset()
        new_state = circuit_breaker.get_state()
        
        logger.info(f"Circuit breaker '{circuit_breaker_name}' reset from {old_state.value} to {new_state.value}")
        
        return {
            "message": f"Circuit breaker '{circuit_breaker_name}' reset successfully",
            "old_state": old_state.value,
            "new_state": new_state.value,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reset circuit breaker '{circuit_breaker_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/force-open/{circuit_breaker_name}")
async def force_open_circuit_breaker(
    circuit_breaker_name: str,
    manager: CircuitBreakerManager = Depends(get_circuit_breaker_manager_dependency)
):
    """
    Manually force a circuit breaker to OPEN state.
    
    Args:
        circuit_breaker_name: Name of the circuit breaker to force open
        
    Returns:
        Success message and new status
    """
    try:
        circuit_breaker = manager.get_circuit_breaker(circuit_breaker_name)
        
        if circuit_breaker is None:
            raise HTTPException(
                status_code=404, 
                detail=f"Circuit breaker '{circuit_breaker_name}' not found"
            )
        
        old_state = circuit_breaker.get_state()
        circuit_breaker.force_open()
        new_state = circuit_breaker.get_state()
        
        logger.warning(f"Circuit breaker '{circuit_breaker_name}' forced from {old_state.value} to {new_state.value}")
        
        return {
            "message": f"Circuit breaker '{circuit_breaker_name}' forced open successfully",
            "old_state": old_state.value,
            "new_state": new_state.value,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to force open circuit breaker '{circuit_breaker_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=Dict[str, Any])
async def get_circuit_breaker_health():
    """
    Get overall health status of circuit breaker system.
    
    Returns health information including service isolation status
    and circuit breaker statistics.
    """
    try:
        # Get circuit breaker manager status
        manager = get_circuit_breaker_manager()
        summary = manager.get_summary()
        
        # Get enhanced service health monitor status
        enhanced_monitor = get_enhanced_service_health_monitor()
        circuit_stats = enhanced_monitor.get_circuit_breaker_statistics()
        
        # Calculate overall health
        total_breakers = summary.get('total_circuit_breakers', 0)
        healthy_breakers = summary.get('closed_breakers', 0)
        health_percentage = summary.get('health_percentage', 100.0)
        
        overall_status = "healthy"
        if health_percentage < 50:
            overall_status = "critical"
        elif health_percentage < 80:
            overall_status = "degraded"
        
        return {
            "overall_status": overall_status,
            "health_percentage": health_percentage,
            "circuit_breaker_summary": summary,
            "circuit_breaker_statistics": circuit_stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get circuit breaker health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services", response_model=Dict[str, Any])
async def get_services_with_circuit_breakers():
    """
    Get information about services with circuit breaker protection.
    
    Returns detailed information about all services that have
    circuit breaker protection enabled.
    """
    try:
        enhanced_monitor = get_enhanced_service_health_monitor()
        services_health = enhanced_monitor.get_all_services_health_with_circuit_breakers()
        
        return {
            "services": services_health,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get services with circuit breakers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services/{service_name}", response_model=Dict[str, Any])
async def get_service_circuit_breaker_status(service_name: str):
    """
    Get circuit breaker status for a specific service.
    
    Args:
        service_name: Name of the service
        
    Returns:
        Detailed circuit breaker and health information for the service
    """
    try:
        enhanced_monitor = get_enhanced_service_health_monitor()
        service_health = enhanced_monitor.get_service_health_with_circuit_breaker(service_name)
        
        if not service_health:
            raise HTTPException(
                status_code=404, 
                detail=f"Service '{service_name}' not found"
            )
        
        return {
            "service_name": service_name,
            "health_info": service_health,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get service circuit breaker status for '{service_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/services/{service_name}/recover")
async def force_service_recovery(service_name: str):
    """
    Force recovery of an isolated service.
    
    Args:
        service_name: Name of the service to recover
        
    Returns:
        Success message and recovery status
    """
    try:
        enhanced_monitor = get_enhanced_service_health_monitor()
        
        # Check if service exists
        service_health = enhanced_monitor.get_service_health_with_circuit_breaker(service_name)
        if not service_health:
            raise HTTPException(
                status_code=404, 
                detail=f"Service '{service_name}' not found"
            )
        
        # Attempt recovery
        recovery_successful = await enhanced_monitor.force_service_recovery(service_name)
        
        if recovery_successful:
            logger.info(f"Service '{service_name}' recovery forced successfully")
            return {
                "message": f"Service '{service_name}' recovery forced successfully",
                "recovery_successful": True,
                "timestamp": datetime.now().isoformat()
            }
        else:
            logger.warning(f"Failed to force recovery of service '{service_name}'")
            return {
                "message": f"Failed to force recovery of service '{service_name}'",
                "recovery_successful": False,
                "timestamp": datetime.now().isoformat()
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to force recovery of service '{service_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics", response_model=Dict[str, Any])
async def get_circuit_breaker_metrics(
    hours: int = Query(default=24, ge=1, le=168, description="Hours of metrics to retrieve")
):
    """
    Get circuit breaker metrics and statistics.
    
    Args:
        hours: Number of hours of metrics to retrieve (1-168)
        
    Returns:
        Comprehensive metrics including failure rates, state transitions,
        and recovery statistics
    """
    try:
        manager = get_circuit_breaker_manager()
        enhanced_monitor = get_enhanced_service_health_monitor()
        
        # Get all circuit breaker status
        all_status = manager.get_all_status()
        
        # Get circuit breaker statistics
        circuit_stats = enhanced_monitor.get_circuit_breaker_statistics()
        
        # Aggregate metrics
        total_requests = 0
        total_failures = 0
        total_state_changes = 0
        
        for cb_name, cb_status in all_status.items():
            metrics = cb_status.get('metrics', {})
            total_requests += metrics.get('total_requests', 0)
            total_failures += metrics.get('failed_requests', 0)
            total_state_changes += metrics.get('state_changes', 0)
        
        overall_failure_rate = (total_failures / max(1, total_requests)) * 100
        
        return {
            "time_period_hours": hours,
            "overall_metrics": {
                "total_requests": total_requests,
                "total_failures": total_failures,
                "overall_failure_rate_percent": overall_failure_rate,
                "total_state_changes": total_state_changes
            },
            "circuit_breaker_details": all_status,
            "circuit_breaker_statistics": circuit_stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get circuit breaker metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test/{circuit_breaker_name}")
async def test_circuit_breaker(
    circuit_breaker_name: str,
    manager: CircuitBreakerManager = Depends(get_circuit_breaker_manager_dependency)
):
    """
    Test a circuit breaker by triggering a recovery test.
    
    Args:
        circuit_breaker_name: Name of the circuit breaker to test
        
    Returns:
        Test result and current status
    """
    try:
        circuit_breaker = manager.get_circuit_breaker(circuit_breaker_name)
        
        if circuit_breaker is None:
            raise HTTPException(
                status_code=404, 
                detail=f"Circuit breaker '{circuit_breaker_name}' not found"
            )
        
        # Get current status
        current_status = circuit_breaker.get_status()
        
        # If circuit breaker has a recovery function, test it
        test_result = None
        if circuit_breaker.recovery_function:
            try:
                if asyncio.iscoroutinefunction(circuit_breaker.recovery_function):
                    await circuit_breaker.recovery_function()
                else:
                    circuit_breaker.recovery_function()
                test_result = "success"
            except Exception as e:
                test_result = f"failed: {str(e)}"
        else:
            test_result = "no_recovery_function"
        
        logger.info(f"Circuit breaker '{circuit_breaker_name}' test result: {test_result}")
        
        return {
            "circuit_breaker_name": circuit_breaker_name,
            "test_result": test_result,
            "current_status": current_status,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to test circuit breaker '{circuit_breaker_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))