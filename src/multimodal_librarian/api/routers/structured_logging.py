"""
API endpoints for structured logging service.

This module provides REST API endpoints for:
- Querying structured logs with correlation and filtering
- Managing log aggregation rules
- Configuring log retention policies
- Exporting logs in various formats
- Monitoring logging system health
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from fastapi import APIRouter, HTTPException, Query, Path, BackgroundTasks
from pydantic import BaseModel, Field
import json

from ...monitoring.structured_logging_service import (
    get_structured_logging_service,
    LogAggregationRule,
    LogRetentionPolicy,
    log_info_structured,
    log_error_structured
)
from ...logging_config import get_logger

router = APIRouter(prefix="/api/structured-logging", tags=["structured-logging"])
logger = get_logger("structured_logging_api")


# Pydantic models for API
class LogQuery(BaseModel):
    """Log query parameters."""
    query: Optional[str] = Field(None, description="Text search query")
    service: Optional[str] = Field(None, description="Filter by service name")
    operation: Optional[str] = Field(None, description="Filter by operation name")
    level: Optional[str] = Field(None, description="Filter by log level")
    user_id: Optional[str] = Field(None, description="Filter by user ID")
    correlation_id: Optional[str] = Field(None, description="Filter by correlation ID")
    trace_id: Optional[str] = Field(None, description="Filter by trace ID")
    hours: int = Field(24, description="Time window in hours", ge=1, le=168)
    limit: int = Field(1000, description="Maximum number of results", ge=1, le=10000)


class AggregationRuleRequest(BaseModel):
    """Request model for creating aggregation rules."""
    name: str = Field(..., description="Rule name")
    service_pattern: Optional[str] = Field(None, description="Service name pattern")
    operation_pattern: Optional[str] = Field(None, description="Operation name pattern")
    level_filter: Optional[List[str]] = Field(None, description="Log levels to include")
    tag_filters: Optional[Dict[str, str]] = Field(None, description="Tag filters")
    time_window_minutes: int = Field(60, description="Time window in minutes", ge=1)
    max_entries: int = Field(1000, description="Maximum entries to keep", ge=1)
    enabled: bool = Field(True, description="Whether rule is enabled")


class RetentionPolicyRequest(BaseModel):
    """Request model for creating retention policies."""
    name: str = Field(..., description="Policy name")
    retention_days: int = Field(30, description="Days to retain logs", ge=1)
    archive_after_days: int = Field(7, description="Days before archiving", ge=1)
    compression_enabled: bool = Field(True, description="Enable compression")
    archive_location: Optional[str] = Field(None, description="Archive directory path")
    cleanup_enabled: bool = Field(True, description="Enable automatic cleanup")


class LogExportRequest(BaseModel):
    """Request model for log export."""
    format: str = Field("json", description="Export format (json or txt)")
    hours: int = Field(24, description="Time window in hours", ge=1, le=168)
    correlation_id: Optional[str] = Field(None, description="Filter by correlation ID")
    trace_id: Optional[str] = Field(None, description="Filter by trace ID")
    filename: Optional[str] = Field(None, description="Custom filename")


@router.get("/logs", summary="Query structured logs")
async def query_logs(
    query: Optional[str] = Query(None, description="Text search query"),
    service: Optional[str] = Query(None, description="Filter by service name"),
    operation: Optional[str] = Query(None, description="Filter by operation name"),
    level: Optional[str] = Query(None, description="Filter by log level"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    correlation_id: Optional[str] = Query(None, description="Filter by correlation ID"),
    trace_id: Optional[str] = Query(None, description="Filter by trace ID"),
    hours: int = Query(24, description="Time window in hours", ge=1, le=168),
    limit: int = Query(1000, description="Maximum number of results", ge=1, le=10000)
) -> Dict[str, Any]:
    """
    Query structured logs with various filters and search options.
    
    Supports filtering by service, operation, level, user, correlation ID, trace ID,
    and full-text search across log messages and metadata.
    """
    
    try:
        structured_service = get_structured_logging_service()
        
        # Determine query type and execute
        if correlation_id:
            logs = structured_service.get_logs_by_correlation(correlation_id, limit)
            query_type = "correlation"
        elif trace_id:
            logs = structured_service.get_logs_by_trace(trace_id, limit)
            query_type = "trace"
        elif user_id:
            logs = structured_service.get_logs_by_user(user_id, hours, limit)
            query_type = "user"
        elif service:
            logs = structured_service.get_logs_by_service(service, hours, limit)
            query_type = "service"
        elif query:
            logs = structured_service.search_logs(query, service, level, hours, limit)
            query_type = "search"
        else:
            # Get recent logs with filters
            logs = structured_service.search_logs("", service, level, hours, limit)
            query_type = "recent"
        
        # Log the query
        log_info_structured(
            service="structured_logging_api",
            operation="query_logs",
            message=f"Logs queried: {query_type}",
            metadata={
                "query_type": query_type,
                "filters": {
                    "query": query,
                    "service": service,
                    "operation": operation,
                    "level": level,
                    "user_id": user_id,
                    "correlation_id": correlation_id,
                    "trace_id": trace_id
                },
                "time_window_hours": hours,
                "limit": limit,
                "results_count": len(logs)
            }
        )
        
        return {
            "query_type": query_type,
            "filters": {
                "query": query,
                "service": service,
                "operation": operation,
                "level": level,
                "user_id": user_id,
                "correlation_id": correlation_id,
                "trace_id": trace_id
            },
            "time_window_hours": hours,
            "limit": limit,
            "total_results": len(logs),
            "logs": logs
        }
        
    except Exception as e:
        log_error_structured(
            service="structured_logging_api",
            operation="query_logs",
            message=f"Failed to query logs: {str(e)}",
            error_type=type(e).__name__,
            stack_trace=str(e)
        )
        raise HTTPException(status_code=500, detail=f"Failed to query logs: {str(e)}")


@router.get("/logs/correlation/{correlation_id}", summary="Get logs by correlation ID")
async def get_logs_by_correlation(
    correlation_id: str = Path(..., description="Correlation ID"),
    limit: int = Query(1000, description="Maximum number of results", ge=1, le=10000)
) -> Dict[str, Any]:
    """Get all logs associated with a specific correlation ID."""
    
    try:
        structured_service = get_structured_logging_service()
        logs = structured_service.get_logs_by_correlation(correlation_id, limit)
        
        return {
            "correlation_id": correlation_id,
            "total_results": len(logs),
            "logs": logs
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get logs: {str(e)}")


@router.get("/logs/trace/{trace_id}", summary="Get logs by trace ID")
async def get_logs_by_trace(
    trace_id: str = Path(..., description="Trace ID"),
    limit: int = Query(1000, description="Maximum number of results", ge=1, le=10000)
) -> Dict[str, Any]:
    """Get all logs associated with a specific trace ID."""
    
    try:
        structured_service = get_structured_logging_service()
        logs = structured_service.get_logs_by_trace(trace_id, limit)
        
        return {
            "trace_id": trace_id,
            "total_results": len(logs),
            "logs": logs
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get logs: {str(e)}")


@router.get("/statistics", summary="Get log statistics")
async def get_log_statistics(
    hours: int = Query(24, description="Time window in hours", ge=1, le=168)
) -> Dict[str, Any]:
    """Get comprehensive statistics about structured logs."""
    
    try:
        structured_service = get_structured_logging_service()
        stats = structured_service.get_log_statistics(hours)
        
        return stats
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")


@router.get("/aggregation-rules", summary="List aggregation rules")
async def list_aggregation_rules() -> Dict[str, Any]:
    """List all configured log aggregation rules."""
    
    try:
        structured_service = get_structured_logging_service()
        
        with structured_service._lock:
            rules = {
                name: {
                    "name": rule.name,
                    "service_pattern": rule.service_pattern,
                    "operation_pattern": rule.operation_pattern,
                    "level_filter": list(rule.level_filter) if rule.level_filter else None,
                    "tag_filters": rule.tag_filters,
                    "time_window_minutes": rule.time_window_minutes,
                    "max_entries": rule.max_entries,
                    "enabled": rule.enabled
                }
                for name, rule in structured_service._aggregation_rules.items()
            }
        
        return {
            "total_rules": len(rules),
            "rules": rules
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list rules: {str(e)}")


@router.post("/aggregation-rules", summary="Create aggregation rule")
async def create_aggregation_rule(rule_request: AggregationRuleRequest) -> Dict[str, Any]:
    """Create a new log aggregation rule."""
    
    try:
        structured_service = get_structured_logging_service()
        
        # Convert request to rule object
        rule = LogAggregationRule(
            name=rule_request.name,
            service_pattern=rule_request.service_pattern,
            operation_pattern=rule_request.operation_pattern,
            level_filter=set(rule_request.level_filter) if rule_request.level_filter else None,
            tag_filters=rule_request.tag_filters,
            time_window_minutes=rule_request.time_window_minutes,
            max_entries=rule_request.max_entries,
            enabled=rule_request.enabled
        )
        
        structured_service.add_aggregation_rule(rule)
        
        log_info_structured(
            service="structured_logging_api",
            operation="create_aggregation_rule",
            message=f"Created aggregation rule: {rule.name}",
            metadata={"rule_name": rule.name, "enabled": rule.enabled}
        )
        
        return {
            "message": f"Aggregation rule '{rule.name}' created successfully",
            "rule": {
                "name": rule.name,
                "service_pattern": rule.service_pattern,
                "operation_pattern": rule.operation_pattern,
                "level_filter": list(rule.level_filter) if rule.level_filter else None,
                "tag_filters": rule.tag_filters,
                "time_window_minutes": rule.time_window_minutes,
                "max_entries": rule.max_entries,
                "enabled": rule.enabled
            }
        }
        
    except Exception as e:
        log_error_structured(
            service="structured_logging_api",
            operation="create_aggregation_rule",
            message=f"Failed to create aggregation rule: {str(e)}",
            error_type=type(e).__name__
        )
        raise HTTPException(status_code=500, detail=f"Failed to create rule: {str(e)}")


@router.delete("/aggregation-rules/{rule_name}", summary="Delete aggregation rule")
async def delete_aggregation_rule(rule_name: str = Path(..., description="Rule name")) -> Dict[str, Any]:
    """Delete a log aggregation rule."""
    
    try:
        structured_service = get_structured_logging_service()
        structured_service.remove_aggregation_rule(rule_name)
        
        log_info_structured(
            service="structured_logging_api",
            operation="delete_aggregation_rule",
            message=f"Deleted aggregation rule: {rule_name}",
            metadata={"rule_name": rule_name}
        )
        
        return {"message": f"Aggregation rule '{rule_name}' deleted successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete rule: {str(e)}")


@router.get("/aggregation-rules/{rule_name}/logs", summary="Get aggregated logs")
async def get_aggregated_logs(
    rule_name: str = Path(..., description="Rule name"),
    limit: int = Query(1000, description="Maximum number of results", ge=1, le=10000)
) -> Dict[str, Any]:
    """Get logs from a specific aggregation rule."""
    
    try:
        structured_service = get_structured_logging_service()
        logs = structured_service.get_aggregated_logs(rule_name, limit)
        
        return {
            "rule_name": rule_name,
            "total_results": len(logs),
            "logs": logs
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get aggregated logs: {str(e)}")


@router.get("/retention-policies", summary="List retention policies")
async def list_retention_policies() -> Dict[str, Any]:
    """List all configured log retention policies."""
    
    try:
        structured_service = get_structured_logging_service()
        
        with structured_service._lock:
            policies = {
                name: {
                    "name": policy.name,
                    "retention_days": policy.retention_days,
                    "archive_after_days": policy.archive_after_days,
                    "compression_enabled": policy.compression_enabled,
                    "archive_location": policy.archive_location,
                    "cleanup_enabled": policy.cleanup_enabled
                }
                for name, policy in structured_service._retention_policies.items()
            }
        
        return {
            "total_policies": len(policies),
            "policies": policies
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list policies: {str(e)}")


@router.post("/retention-policies", summary="Create retention policy")
async def create_retention_policy(policy_request: RetentionPolicyRequest) -> Dict[str, Any]:
    """Create a new log retention policy."""
    
    try:
        structured_service = get_structured_logging_service()
        
        # Convert request to policy object
        policy = LogRetentionPolicy(
            name=policy_request.name,
            retention_days=policy_request.retention_days,
            archive_after_days=policy_request.archive_after_days,
            compression_enabled=policy_request.compression_enabled,
            archive_location=policy_request.archive_location,
            cleanup_enabled=policy_request.cleanup_enabled
        )
        
        structured_service.add_retention_policy(policy)
        
        log_info_structured(
            service="structured_logging_api",
            operation="create_retention_policy",
            message=f"Created retention policy: {policy.name}",
            metadata={"policy_name": policy.name, "retention_days": policy.retention_days}
        )
        
        return {
            "message": f"Retention policy '{policy.name}' created successfully",
            "policy": {
                "name": policy.name,
                "retention_days": policy.retention_days,
                "archive_after_days": policy.archive_after_days,
                "compression_enabled": policy.compression_enabled,
                "archive_location": policy.archive_location,
                "cleanup_enabled": policy.cleanup_enabled
            }
        }
        
    except Exception as e:
        log_error_structured(
            service="structured_logging_api",
            operation="create_retention_policy",
            message=f"Failed to create retention policy: {str(e)}",
            error_type=type(e).__name__
        )
        raise HTTPException(status_code=500, detail=f"Failed to create policy: {str(e)}")


@router.post("/export", summary="Export structured logs")
async def export_logs(
    export_request: LogExportRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    """Export structured logs to file."""
    
    try:
        structured_service = get_structured_logging_service()
        
        # Export logs
        filepath = structured_service.export_structured_logs(
            filepath=export_request.filename,
            format=export_request.format,
            hours=export_request.hours,
            correlation_id=export_request.correlation_id,
            trace_id=export_request.trace_id
        )
        
        log_info_structured(
            service="structured_logging_api",
            operation="export_logs",
            message=f"Logs exported to: {filepath}",
            metadata={
                "filepath": filepath,
                "format": export_request.format,
                "hours": export_request.hours,
                "correlation_id": export_request.correlation_id,
                "trace_id": export_request.trace_id
            }
        )
        
        return {
            "message": "Logs exported successfully",
            "filepath": filepath,
            "format": export_request.format,
            "time_window_hours": export_request.hours
        }
        
    except Exception as e:
        log_error_structured(
            service="structured_logging_api",
            operation="export_logs",
            message=f"Failed to export logs: {str(e)}",
            error_type=type(e).__name__
        )
        raise HTTPException(status_code=500, detail=f"Failed to export logs: {str(e)}")


@router.get("/health", summary="Get logging system health")
async def get_logging_health() -> Dict[str, Any]:
    """Get health status of the structured logging system."""
    
    try:
        structured_service = get_structured_logging_service()
        
        # Get basic statistics
        stats = structured_service.get_log_statistics(hours=1)  # Last hour
        
        # Calculate health metrics
        health_status = "healthy"
        issues = []
        
        # Check processing performance
        if stats.get('processing_stats', {}).get('average_processing_time_ms', 0) > 100:
            health_status = "degraded"
            issues.append("High log processing latency")
        
        # Check error rate
        error_rate = stats.get('level_distribution', {}).get('ERROR', 0) / max(1, stats.get('total_logs', 1))
        if error_rate > 0.1:  # More than 10% errors
            health_status = "degraded"
            issues.append("High error rate in logs")
        
        # Check memory usage (approximate)
        total_logs = stats.get('total_logs', 0)
        if total_logs > 50000:  # High memory usage indicator
            health_status = "warning"
            issues.append("High log volume - consider archiving")
        
        return {
            "status": health_status,
            "timestamp": datetime.now().isoformat(),
            "issues": issues,
            "metrics": {
                "total_logs_last_hour": stats.get('total_logs', 0),
                "logs_per_hour": stats.get('logs_per_hour', 0),
                "error_rate_percent": round(error_rate * 100, 2),
                "processing_stats": stats.get('processing_stats', {}),
                "active_aggregation_rules": stats.get('aggregation_rules', 0),
                "retention_policies": stats.get('retention_policies', 0),
                "archived_logs": stats.get('archived_logs_count', 0)
            }
        }
        
    except Exception as e:
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "issues": ["Failed to get health status"]
        }


@router.post("/test", summary="Test structured logging")
async def test_structured_logging() -> Dict[str, Any]:
    """Test the structured logging system with sample entries."""
    
    try:
        structured_service = get_structured_logging_service()
        
        # Generate test correlation ID
        correlation_id = f"test_{int(datetime.now().timestamp())}"
        
        # Log test entries
        test_entries = [
            {
                "level": "INFO",
                "service": "test_service",
                "operation": "test_operation_1",
                "message": "Test info message",
                "metadata": {"test": True, "entry": 1}
            },
            {
                "level": "WARNING",
                "service": "test_service",
                "operation": "test_operation_2",
                "message": "Test warning message",
                "metadata": {"test": True, "entry": 2}
            },
            {
                "level": "ERROR",
                "service": "test_service",
                "operation": "test_operation_3",
                "message": "Test error message",
                "error_type": "TestError",
                "metadata": {"test": True, "entry": 3}
            }
        ]
        
        for entry in test_entries:
            structured_service.log_structured(
                correlation_id=correlation_id,
                **entry
            )
        
        # Retrieve test logs
        test_logs = structured_service.get_logs_by_correlation(correlation_id)
        
        return {
            "message": "Structured logging test completed",
            "correlation_id": correlation_id,
            "test_entries_created": len(test_entries),
            "test_entries_retrieved": len(test_logs),
            "test_logs": test_logs
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test failed: {str(e)}")