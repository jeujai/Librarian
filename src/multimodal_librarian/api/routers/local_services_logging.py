"""
API endpoints for local services logging management and monitoring.

This module provides REST API endpoints for:
- Monitoring local services logs and health
- Managing local services logging configuration
- Viewing service metrics and performance data
- Controlling logging integration
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, Field

from ...logging_config import get_logger
from ...logging.local_services_integration import (
    get_local_services_integration,
    get_local_services_status,
    restart_local_services_monitoring
)
from ...logging.local_services_logger import get_local_services_logger
from ...config.local_logging_config import (
    get_local_logging_config,
    get_service_logging_config,
    update_service_logging_config,
    export_logging_config_to_file
)
from ...monitoring.structured_logging_service import (
    log_info_structured,
    log_error_structured,
    log_warning_structured
)


# Pydantic models for API requests/responses
class ServiceLogQuery(BaseModel):
    """Query parameters for service logs."""
    service_name: Optional[str] = Field(None, description="Filter by service name")
    log_level: Optional[str] = Field(None, description="Filter by log level")
    hours: int = Field(24, description="Time window in hours", ge=1, le=168)
    limit: int = Field(1000, description="Maximum number of logs to return", ge=1, le=10000)
    search: Optional[str] = Field(None, description="Text search in log messages")


class ServiceConfigUpdate(BaseModel):
    """Update request for service logging configuration."""
    log_level: Optional[str] = Field(None, description="New log level")
    enable_metrics_extraction: Optional[bool] = Field(None, description="Enable metrics extraction")
    enable_error_detection: Optional[bool] = Field(None, description="Enable error detection")
    enable_performance_monitoring: Optional[bool] = Field(None, description="Enable performance monitoring")
    log_retention_days: Optional[int] = Field(None, description="Log retention in days", ge=1, le=365)


class ServiceHealthResponse(BaseModel):
    """Response model for service health status."""
    service_name: str
    is_healthy: bool
    cpu_usage_percent: float
    memory_usage_mb: float
    uptime_seconds: float
    restart_count: int
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None


class LoggingStatusResponse(BaseModel):
    """Response model for logging status."""
    integration_active: bool
    monitoring_active: bool
    health_monitoring_enabled: bool
    performance_metrics_enabled: bool
    error_alerting_enabled: bool
    monitored_services: List[str]
    total_logs_processed: int
    logs_per_second: float
    parsing_errors: int


router = APIRouter(prefix="/api/local-services-logging", tags=["local-services-logging"])
logger = get_logger("local_services_logging_api")


@router.get("/status", summary="Get local services logging status")
async def get_logging_status() -> LoggingStatusResponse:
    """
    Get the current status of local services logging integration.
    
    Returns comprehensive status information including:
    - Integration and monitoring status
    - Configuration settings
    - Processing statistics
    - Monitored services list
    """
    try:
        status = get_local_services_status()
        service_metrics = status.get('service_metrics', {})
        processing_stats = service_metrics.get('processing_stats', {})
        config = status.get('configuration', {})
        
        return LoggingStatusResponse(
            integration_active=status.get('integration_active', False),
            monitoring_active=service_metrics.get('monitoring_active', False),
            health_monitoring_enabled=config.get('enable_health_monitoring', False),
            performance_metrics_enabled=config.get('enable_performance_metrics', False),
            error_alerting_enabled=config.get('enable_error_alerting', False),
            monitored_services=status.get('monitored_services', []),
            total_logs_processed=processing_stats.get('logs_processed', 0),
            logs_per_second=processing_stats.get('logs_per_second', 0.0),
            parsing_errors=processing_stats.get('parsing_errors', 0)
        )
    
    except Exception as e:
        logger.error(f"Error getting logging status: {e}")
        log_error_structured(
            service="local_services_logging_api",
            operation="get_status_error",
            message=f"Failed to get logging status: {str(e)}",
            error_type=type(e).__name__,
            stack_trace=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to get logging status: {str(e)}")


@router.get("/logs", summary="Query local services logs")
async def query_service_logs(
    service_name: Optional[str] = Query(None, description="Filter by service name"),
    log_level: Optional[str] = Query(None, description="Filter by log level (DEBUG, INFO, WARNING, ERROR)"),
    hours: int = Query(24, description="Time window in hours", ge=1, le=168),
    limit: int = Query(1000, description="Maximum number of logs to return", ge=1, le=10000),
    search: Optional[str] = Query(None, description="Text search in log messages")
) -> Dict[str, Any]:
    """
    Query local services logs with filtering and search capabilities.
    
    Supports filtering by:
    - Service name (postgres, neo4j, milvus, redis, etc.)
    - Log level (DEBUG, INFO, WARNING, ERROR)
    - Time window (last N hours)
    - Text search in log messages
    """
    try:
        local_services_logger = get_local_services_logger()
        
        # Get logs with basic filtering
        logs = local_services_logger.get_service_logs(
            service_name=service_name,
            hours=hours,
            limit=limit
        )
        
        # Apply additional filters
        filtered_logs = []
        for log_entry in logs:
            # Log level filter
            if log_level and log_entry.get('log_level', '').upper() != log_level.upper():
                continue
            
            # Text search filter
            if search:
                search_lower = search.lower()
                message = log_entry.get('message', '').lower()
                parsed_data = str(log_entry.get('parsed_data', {})).lower()
                
                if search_lower not in message and search_lower not in parsed_data:
                    continue
            
            filtered_logs.append(log_entry)
        
        # Log the query
        log_info_structured(
            service="local_services_logging_api",
            operation="query_logs",
            message=f"Queried service logs: {len(filtered_logs)} results",
            metadata={
                'service_name': service_name,
                'log_level': log_level,
                'hours': hours,
                'limit': limit,
                'search': search,
                'results_count': len(filtered_logs)
            }
        )
        
        return {
            "query": {
                "service_name": service_name,
                "log_level": log_level,
                "hours": hours,
                "limit": limit,
                "search": search
            },
            "results": {
                "total_count": len(filtered_logs),
                "logs": filtered_logs[:limit]  # Ensure we don't exceed limit
            },
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error querying service logs: {e}")
        log_error_structured(
            service="local_services_logging_api",
            operation="query_logs_error",
            message=f"Failed to query service logs: {str(e)}",
            error_type=type(e).__name__,
            stack_trace=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to query logs: {str(e)}")


@router.get("/logs/{service_name}", summary="Get logs for specific service")
async def get_service_logs(
    service_name: str = Path(..., description="Service name (postgres, neo4j, milvus, redis, etc.)"),
    hours: int = Query(24, description="Time window in hours", ge=1, le=168),
    limit: int = Query(1000, description="Maximum number of logs to return", ge=1, le=10000)
) -> Dict[str, Any]:
    """
    Get logs for a specific service.
    
    Returns logs from the specified service within the given time window.
    """
    try:
        local_services_logger = get_local_services_logger()
        
        # Validate service name
        config = get_local_logging_config()
        if service_name not in config.service_configs:
            raise HTTPException(
                status_code=404, 
                detail=f"Service '{service_name}' not found. Available services: {list(config.service_configs.keys())}"
            )
        
        # Get logs for the service
        logs = local_services_logger.get_service_logs(
            service_name=service_name,
            hours=hours,
            limit=limit
        )
        
        # Calculate statistics
        log_levels = {}
        error_count = 0
        metrics_count = 0
        
        for log_entry in logs:
            level = log_entry.get('log_level', 'UNKNOWN')
            log_levels[level] = log_levels.get(level, 0) + 1
            
            if log_entry.get('error_info'):
                error_count += 1
            
            if log_entry.get('metrics'):
                metrics_count += 1
        
        return {
            "service_name": service_name,
            "time_window_hours": hours,
            "statistics": {
                "total_logs": len(logs),
                "log_levels": log_levels,
                "error_count": error_count,
                "logs_with_metrics": metrics_count
            },
            "logs": logs,
            "timestamp": datetime.now().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting logs for service {service_name}: {e}")
        log_error_structured(
            service="local_services_logging_api",
            operation="get_service_logs_error",
            message=f"Failed to get logs for service {service_name}: {str(e)}",
            metadata={'service_name': service_name},
            error_type=type(e).__name__,
            stack_trace=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to get service logs: {str(e)}")


@router.get("/metrics", summary="Get local services metrics")
async def get_services_metrics() -> Dict[str, Any]:
    """
    Get comprehensive metrics for all local services.
    
    Returns processing statistics, service-specific metrics, and health information.
    """
    try:
        local_services_logger = get_local_services_logger()
        metrics = local_services_logger.get_service_metrics()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics
        }
    
    except Exception as e:
        logger.error(f"Error getting services metrics: {e}")
        log_error_structured(
            service="local_services_logging_api",
            operation="get_metrics_error",
            message=f"Failed to get services metrics: {str(e)}",
            error_type=type(e).__name__,
            stack_trace=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@router.get("/health", summary="Get services health status")
async def get_services_health() -> Dict[str, Any]:
    """
    Get health status for all monitored local services.
    
    Returns health information including CPU usage, memory usage, uptime, and error status.
    """
    try:
        status = get_local_services_status()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_status": {
                "integration_active": status.get('integration_active', False),
                "monitoring_active": status.get('service_metrics', {}).get('monitoring_active', False),
                "monitored_services_count": len(status.get('monitored_services', []))
            },
            "services": status.get('monitored_services', []),
            "service_metrics": status.get('service_metrics', {}),
            "configuration": status.get('configuration', {})
        }
    
    except Exception as e:
        logger.error(f"Error getting services health: {e}")
        log_error_structured(
            service="local_services_logging_api",
            operation="get_health_error",
            message=f"Failed to get services health: {str(e)}",
            error_type=type(e).__name__,
            stack_trace=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to get health status: {str(e)}")


@router.get("/config", summary="Get logging configuration")
async def get_logging_config() -> Dict[str, Any]:
    """
    Get the current local services logging configuration.
    
    Returns all configuration settings including service-specific configurations.
    """
    try:
        config = get_local_logging_config()
        
        # Convert to serializable format
        config_dict = {
            "enable_local_logging": config.enable_local_logging,
            "log_output_directory": config.log_output_directory,
            "global_log_level": config.global_log_level.value,
            "global_log_format": config.global_log_format.value,
            "enable_health_monitoring": config.enable_health_monitoring,
            "health_check_interval_seconds": config.health_check_interval_seconds,
            "enable_performance_metrics": config.enable_performance_metrics,
            "metrics_collection_interval_seconds": config.metrics_collection_interval_seconds,
            "log_buffer_size": config.log_buffer_size,
            "log_processing_batch_size": config.log_processing_batch_size,
            "default_retention_days": config.default_retention_days,
            "enable_log_compression": config.enable_log_compression,
            "enable_log_archival": config.enable_log_archival,
            "archive_directory": config.archive_directory,
            "enable_error_alerting": config.enable_error_alerting,
            "error_alert_threshold": config.error_alert_threshold,
            "service_configs": {
                name: {
                    "service_name": svc_config.service_name,
                    "container_name": svc_config.container_name,
                    "log_level": svc_config.log_level.value,
                    "log_format": svc_config.log_format.value,
                    "enable_metrics_extraction": svc_config.enable_metrics_extraction,
                    "enable_error_detection": svc_config.enable_error_detection,
                    "enable_performance_monitoring": svc_config.enable_performance_monitoring,
                    "max_log_size_mb": svc_config.max_log_size_mb,
                    "log_retention_days": svc_config.log_retention_days,
                    "enable_log_rotation": svc_config.enable_log_rotation
                }
                for name, svc_config in config.service_configs.items()
            }
        }
        
        return {
            "timestamp": datetime.now().isoformat(),
            "configuration": config_dict
        }
    
    except Exception as e:
        logger.error(f"Error getting logging configuration: {e}")
        log_error_structured(
            service="local_services_logging_api",
            operation="get_config_error",
            message=f"Failed to get logging configuration: {str(e)}",
            error_type=type(e).__name__,
            stack_trace=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to get configuration: {str(e)}")


@router.put("/config/{service_name}", summary="Update service logging configuration")
async def update_service_config(
    service_name: str = Path(..., description="Service name to update"),
    config_update: ServiceConfigUpdate = ...
) -> Dict[str, Any]:
    """
    Update logging configuration for a specific service.
    
    Allows updating log level, metrics extraction, error detection, and other settings.
    """
    try:
        # Validate service name
        config = get_local_logging_config()
        if service_name not in config.service_configs:
            raise HTTPException(
                status_code=404,
                detail=f"Service '{service_name}' not found. Available services: {list(config.service_configs.keys())}"
            )
        
        # Prepare updates
        updates = {}
        if config_update.log_level is not None:
            updates['log_level'] = config_update.log_level
        if config_update.enable_metrics_extraction is not None:
            updates['enable_metrics_extraction'] = config_update.enable_metrics_extraction
        if config_update.enable_error_detection is not None:
            updates['enable_error_detection'] = config_update.enable_error_detection
        if config_update.enable_performance_monitoring is not None:
            updates['enable_performance_monitoring'] = config_update.enable_performance_monitoring
        if config_update.log_retention_days is not None:
            updates['log_retention_days'] = config_update.log_retention_days
        
        # Apply updates
        update_service_logging_config(service_name, updates)
        
        # Get updated configuration
        updated_config = get_service_logging_config(service_name)
        
        # Log the update
        log_info_structured(
            service="local_services_logging_api",
            operation="update_service_config",
            message=f"Updated logging configuration for service: {service_name}",
            metadata={
                'service_name': service_name,
                'updates': updates
            }
        )
        
        return {
            "service_name": service_name,
            "updates_applied": updates,
            "updated_config": {
                "log_level": updated_config.log_level.value if updated_config else None,
                "enable_metrics_extraction": updated_config.enable_metrics_extraction if updated_config else None,
                "enable_error_detection": updated_config.enable_error_detection if updated_config else None,
                "enable_performance_monitoring": updated_config.enable_performance_monitoring if updated_config else None,
                "log_retention_days": updated_config.log_retention_days if updated_config else None
            },
            "timestamp": datetime.now().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating service configuration for {service_name}: {e}")
        log_error_structured(
            service="local_services_logging_api",
            operation="update_service_config_error",
            message=f"Failed to update service configuration for {service_name}: {str(e)}",
            metadata={'service_name': service_name},
            error_type=type(e).__name__,
            stack_trace=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to update configuration: {str(e)}")


@router.post("/restart", summary="Restart local services monitoring")
async def restart_monitoring() -> Dict[str, Any]:
    """
    Restart the local services monitoring system.
    
    This will stop and restart all monitoring tasks, which can help resolve issues
    with log collection or processing.
    """
    try:
        log_info_structured(
            service="local_services_logging_api",
            operation="restart_monitoring_request",
            message="Restart monitoring requested via API"
        )
        
        # Restart monitoring
        await restart_local_services_monitoring()
        
        # Get updated status
        status = get_local_services_status()
        
        log_info_structured(
            service="local_services_logging_api",
            operation="restart_monitoring_complete",
            message="Successfully restarted local services monitoring"
        )
        
        return {
            "message": "Local services monitoring restarted successfully",
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error restarting monitoring: {e}")
        log_error_structured(
            service="local_services_logging_api",
            operation="restart_monitoring_error",
            message=f"Failed to restart monitoring: {str(e)}",
            error_type=type(e).__name__,
            stack_trace=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to restart monitoring: {str(e)}")


@router.get("/export", summary="Export logging configuration")
async def export_config(
    format: str = Query("json", description="Export format (json)")
) -> Dict[str, Any]:
    """
    Export the current logging configuration to a file.
    
    Returns the path to the exported configuration file.
    """
    try:
        if format.lower() != "json":
            raise HTTPException(status_code=400, detail="Only JSON format is currently supported")
        
        # Export configuration
        filepath = export_logging_config_to_file()
        
        log_info_structured(
            service="local_services_logging_api",
            operation="export_config",
            message=f"Exported logging configuration to: {filepath}",
            metadata={'filepath': filepath, 'format': format}
        )
        
        return {
            "message": "Configuration exported successfully",
            "filepath": filepath,
            "format": format,
            "timestamp": datetime.now().isoformat()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting configuration: {e}")
        log_error_structured(
            service="local_services_logging_api",
            operation="export_config_error",
            message=f"Failed to export configuration: {str(e)}",
            error_type=type(e).__name__,
            stack_trace=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to export configuration: {str(e)}")


@router.get("/statistics", summary="Get logging statistics")
async def get_logging_statistics(
    hours: int = Query(24, description="Time window in hours", ge=1, le=168)
) -> Dict[str, Any]:
    """
    Get comprehensive logging statistics for the specified time window.
    
    Returns statistics including log counts by service, error rates, and performance metrics.
    """
    try:
        local_services_logger = get_local_services_logger()
        
        # Get all logs for the time window
        all_logs = local_services_logger.get_service_logs(hours=hours, limit=50000)
        
        # Calculate statistics
        stats = {
            "time_window_hours": hours,
            "total_logs": len(all_logs),
            "logs_by_service": {},
            "logs_by_level": {},
            "error_statistics": {},
            "metrics_statistics": {},
            "timeline": {}
        }
        
        # Process logs
        for log_entry in all_logs:
            service_name = log_entry.get('service_name', 'unknown')
            log_level = log_entry.get('log_level', 'UNKNOWN')
            timestamp = log_entry.get('timestamp', '')
            
            # Count by service
            stats["logs_by_service"][service_name] = stats["logs_by_service"].get(service_name, 0) + 1
            
            # Count by level
            stats["logs_by_level"][log_level] = stats["logs_by_level"].get(log_level, 0) + 1
            
            # Error statistics
            if log_entry.get('error_info'):
                if service_name not in stats["error_statistics"]:
                    stats["error_statistics"][service_name] = 0
                stats["error_statistics"][service_name] += 1
            
            # Metrics statistics
            if log_entry.get('metrics'):
                if service_name not in stats["metrics_statistics"]:
                    stats["metrics_statistics"][service_name] = 0
                stats["metrics_statistics"][service_name] += 1
            
            # Timeline (hourly buckets)
            if timestamp:
                try:
                    log_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    hour_bucket = log_time.strftime('%Y-%m-%d %H:00')
                    stats["timeline"][hour_bucket] = stats["timeline"].get(hour_bucket, 0) + 1
                except Exception:
                    pass
        
        # Calculate rates
        if hours > 0:
            stats["logs_per_hour"] = len(all_logs) / hours
            stats["errors_per_hour"] = sum(stats["error_statistics"].values()) / hours
        
        return {
            "timestamp": datetime.now().isoformat(),
            "statistics": stats
        }
    
    except Exception as e:
        logger.error(f"Error getting logging statistics: {e}")
        log_error_structured(
            service="local_services_logging_api",
            operation="get_statistics_error",
            message=f"Failed to get logging statistics: {str(e)}",
            error_type=type(e).__name__,
            stack_trace=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")