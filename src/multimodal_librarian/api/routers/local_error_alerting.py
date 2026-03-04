"""
Local Error Tracking and Alerting API Router

This module provides REST API endpoints for managing error tracking and alerting
in local development environments. It exposes functionality for viewing errors,
managing alerts, and configuring local development monitoring.

Endpoints:
- GET /api/v1/local/errors - List recent errors
- GET /api/v1/local/errors/{error_id} - Get error details
- POST /api/v1/local/errors/{error_id}/resolve - Resolve an error
- GET /api/v1/local/alerts - List active alerts
- GET /api/v1/local/alerts/{alert_id} - Get alert details
- POST /api/v1/local/alerts/{alert_id}/acknowledge - Acknowledge an alert
- POST /api/v1/local/alerts/{alert_id}/resolve - Resolve an alert
- GET /api/v1/local/statistics - Get error and alert statistics
- GET /api/v1/local/dashboard - Get dashboard data
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field

from ...monitoring.local_error_tracking import (
    LocalErrorTracker,
    LocalErrorEvent,
    LocalErrorCategory,
    LocalErrorStats,
    get_local_error_tracker
)
from ...monitoring.local_alerting_system import (
    LocalAlertingSystem,
    LocalAlert,
    LocalAlertType,
    LocalAlertStats,
    get_local_alerting_system
)
from ...monitoring.error_logging_service import ErrorSeverity
from ...monitoring.alerting_service import AlertSeverity
from ...config.local_config import LocalDatabaseConfig
from ...logging_config import get_logger

logger = get_logger("local_error_alerting_api")

router = APIRouter(prefix="/api/v1/local", tags=["Local Development Monitoring"])


# Request/Response Models
class ErrorEventResponse(BaseModel):
    """Error event response model."""
    id: str
    timestamp: datetime
    category: str
    severity: str
    service: str
    operation: str
    message: str
    exception_type: str
    stack_trace: str
    context: Dict[str, Any]
    resolved: bool
    resolution_time: Optional[datetime] = None
    resolution_notes: str


class AlertResponse(BaseModel):
    """Alert response model."""
    id: str
    timestamp: datetime
    alert_type: str
    severity: str
    title: str
    message: str
    service: str
    context: Dict[str, Any]
    acknowledged: bool
    acknowledged_by: str
    acknowledged_at: Optional[datetime] = None
    resolved: bool
    resolved_at: Optional[datetime] = None
    resolution_notes: str
    notification_sent: bool


class ErrorStatsResponse(BaseModel):
    """Error statistics response model."""
    total_errors: int
    errors_by_category: Dict[str, int]
    errors_by_service: Dict[str, int]
    errors_by_hour: Dict[int, int]
    error_rate_per_minute: float
    critical_error_count: int
    unresolved_error_count: int
    recent_errors: List[ErrorEventResponse]


class AlertStatsResponse(BaseModel):
    """Alert statistics response model."""
    total_alerts: int
    alerts_by_type: Dict[str, int]
    alerts_by_severity: Dict[str, int]
    alerts_by_service: Dict[str, int]
    active_alerts: int
    acknowledged_alerts: int
    resolved_alerts: int
    recent_alerts: List[AlertResponse]


class DashboardResponse(BaseModel):
    """Dashboard data response model."""
    error_stats: ErrorStatsResponse
    alert_stats: AlertStatsResponse
    system_health: Dict[str, Any]
    recent_activity: List[Dict[str, Any]]


class ResolveRequest(BaseModel):
    """Request model for resolving errors/alerts."""
    resolution_notes: str = Field(default="", description="Notes about the resolution")


class AcknowledgeRequest(BaseModel):
    """Request model for acknowledging alerts."""
    acknowledged_by: str = Field(default="developer", description="Who acknowledged the alert")


# Dependency functions
def get_error_tracker() -> LocalErrorTracker:
    """Get the local error tracker instance."""
    return get_local_error_tracker()


def get_alerting_system() -> LocalAlertingSystem:
    """Get the local alerting system instance."""
    return get_local_alerting_system()


# Helper functions
def _convert_error_event(error: LocalErrorEvent) -> ErrorEventResponse:
    """Convert LocalErrorEvent to ErrorEventResponse."""
    return ErrorEventResponse(
        id=error.id,
        timestamp=error.timestamp,
        category=error.category.value,
        severity=error.severity.value,
        service=error.service,
        operation=error.operation,
        message=error.message,
        exception_type=error.exception_type,
        stack_trace=error.stack_trace,
        context=error.context,
        resolved=error.resolved,
        resolution_time=error.resolution_time,
        resolution_notes=error.resolution_notes
    )


def _convert_alert(alert: LocalAlert) -> AlertResponse:
    """Convert LocalAlert to AlertResponse."""
    return AlertResponse(
        id=alert.id,
        timestamp=alert.timestamp,
        alert_type=alert.alert_type.value,
        severity=alert.severity.value,
        title=alert.title,
        message=alert.message,
        service=alert.service,
        context=alert.context,
        acknowledged=alert.acknowledged,
        acknowledged_by=alert.acknowledged_by,
        acknowledged_at=alert.acknowledged_at,
        resolved=alert.resolved,
        resolved_at=alert.resolved_at,
        resolution_notes=alert.resolution_notes,
        notification_sent=alert.notification_sent
    )


def _convert_error_stats(stats: LocalErrorStats) -> ErrorStatsResponse:
    """Convert LocalErrorStats to ErrorStatsResponse."""
    return ErrorStatsResponse(
        total_errors=stats.total_errors,
        errors_by_category={cat.value: count for cat, count in stats.errors_by_category.items()},
        errors_by_service=dict(stats.errors_by_service),
        errors_by_hour=dict(stats.errors_by_hour),
        error_rate_per_minute=stats.error_rate_per_minute,
        critical_error_count=stats.critical_error_count,
        unresolved_error_count=stats.unresolved_error_count,
        recent_errors=[_convert_error_event(error) for error in stats.recent_errors]
    )


def _convert_alert_stats(stats: LocalAlertStats) -> AlertStatsResponse:
    """Convert LocalAlertStats to AlertStatsResponse."""
    return AlertStatsResponse(
        total_alerts=stats.total_alerts,
        alerts_by_type={alert_type.value: count for alert_type, count in stats.alerts_by_type.items()},
        alerts_by_severity={severity.value: count for severity, count in stats.alerts_by_severity.items()},
        alerts_by_service=dict(stats.alerts_by_service),
        active_alerts=stats.active_alerts,
        acknowledged_alerts=stats.acknowledged_alerts,
        resolved_alerts=stats.resolved_alerts,
        recent_alerts=[_convert_alert(alert) for alert in stats.recent_alerts]
    )


# Error Tracking Endpoints
@router.get("/errors", response_model=List[ErrorEventResponse])
async def list_errors(
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of errors to return"),
    category: Optional[str] = Query(None, description="Filter by error category"),
    service: Optional[str] = Query(None, description="Filter by service"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    resolved: Optional[bool] = Query(None, description="Filter by resolution status"),
    error_tracker: LocalErrorTracker = Depends(get_error_tracker)
):
    """
    List recent errors with optional filtering.
    
    Returns a list of error events, optionally filtered by category, service,
    severity, or resolution status.
    """
    try:
        # Get all errors from history
        all_errors = list(error_tracker._error_history)
        
        # Apply filters
        filtered_errors = all_errors
        
        if category:
            try:
                category_enum = LocalErrorCategory(category)
                filtered_errors = [e for e in filtered_errors if e.category == category_enum]
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid category: {category}")
        
        if service:
            filtered_errors = [e for e in filtered_errors if e.service == service]
        
        if severity:
            try:
                severity_enum = ErrorSeverity(severity)
                filtered_errors = [e for e in filtered_errors if e.severity == severity_enum]
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")
        
        if resolved is not None:
            filtered_errors = [e for e in filtered_errors if e.resolved == resolved]
        
        # Sort by timestamp (most recent first) and limit
        filtered_errors.sort(key=lambda x: x.timestamp, reverse=True)
        filtered_errors = filtered_errors[:limit]
        
        return [_convert_error_event(error) for error in filtered_errors]
        
    except Exception as e:
        logger.error(f"Failed to list errors: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve errors")


@router.get("/errors/{error_id}", response_model=ErrorEventResponse)
async def get_error_details(
    error_id: str,
    error_tracker: LocalErrorTracker = Depends(get_error_tracker)
):
    """
    Get detailed information about a specific error.
    
    Returns complete error details including stack trace and context.
    """
    try:
        error = error_tracker.get_error_details(error_id)
        if not error:
            raise HTTPException(status_code=404, detail="Error not found")
        
        return _convert_error_event(error)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get error details for {error_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve error details")


@router.post("/errors/{error_id}/resolve")
async def resolve_error(
    error_id: str,
    request: ResolveRequest,
    error_tracker: LocalErrorTracker = Depends(get_error_tracker)
):
    """
    Mark an error as resolved.
    
    This endpoint allows developers to mark errors as resolved with optional
    resolution notes for tracking purposes.
    """
    try:
        success = error_tracker.resolve_error(error_id, request.resolution_notes)
        if not success:
            raise HTTPException(status_code=404, detail="Error not found")
        
        return {"message": "Error resolved successfully", "error_id": error_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve error {error_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to resolve error")


# Alert Management Endpoints
@router.get("/alerts", response_model=List[AlertResponse])
async def list_alerts(
    limit: int = Query(50, ge=1, le=1000, description="Maximum number of alerts to return"),
    alert_type: Optional[str] = Query(None, description="Filter by alert type"),
    service: Optional[str] = Query(None, description="Filter by service"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    active_only: bool = Query(False, description="Show only active (unresolved) alerts"),
    alerting_system: LocalAlertingSystem = Depends(get_alerting_system)
):
    """
    List alerts with optional filtering.
    
    Returns a list of alerts, optionally filtered by type, service, severity,
    or active status.
    """
    try:
        if active_only:
            all_alerts = alerting_system.get_active_alerts()
        else:
            all_alerts = list(alerting_system._alert_history)
        
        # Apply filters
        filtered_alerts = all_alerts
        
        if alert_type:
            try:
                alert_type_enum = LocalAlertType(alert_type)
                filtered_alerts = [a for a in filtered_alerts if a.alert_type == alert_type_enum]
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid alert type: {alert_type}")
        
        if service:
            filtered_alerts = [a for a in filtered_alerts if a.service == service]
        
        if severity:
            try:
                severity_enum = AlertSeverity(severity)
                filtered_alerts = [a for a in filtered_alerts if a.severity == severity_enum]
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")
        
        # Sort by timestamp (most recent first) and limit
        filtered_alerts.sort(key=lambda x: x.timestamp, reverse=True)
        filtered_alerts = filtered_alerts[:limit]
        
        return [_convert_alert(alert) for alert in filtered_alerts]
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list alerts: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve alerts")


@router.get("/alerts/{alert_id}", response_model=AlertResponse)
async def get_alert_details(
    alert_id: str,
    alerting_system: LocalAlertingSystem = Depends(get_alerting_system)
):
    """
    Get detailed information about a specific alert.
    
    Returns complete alert details including context and resolution information.
    """
    try:
        alert = alerting_system.get_alert_details(alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        return _convert_alert(alert)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get alert details for {alert_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve alert details")


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    request: AcknowledgeRequest,
    alerting_system: LocalAlertingSystem = Depends(get_alerting_system)
):
    """
    Acknowledge an alert.
    
    This endpoint allows developers to acknowledge alerts to indicate they
    are aware of the issue and working on it.
    """
    try:
        success = await alerting_system.acknowledge_alert(alert_id, request.acknowledged_by)
        if not success:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        return {"message": "Alert acknowledged successfully", "alert_id": alert_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to acknowledge alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to acknowledge alert")


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    request: ResolveRequest,
    alerting_system: LocalAlertingSystem = Depends(get_alerting_system)
):
    """
    Resolve an alert.
    
    This endpoint allows developers to mark alerts as resolved with optional
    resolution notes for tracking purposes.
    """
    try:
        success = await alerting_system.resolve_alert(alert_id, request.resolution_notes)
        if not success:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        return {"message": "Alert resolved successfully", "alert_id": alert_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to resolve alert")


# Statistics and Dashboard Endpoints
@router.get("/statistics/errors", response_model=ErrorStatsResponse)
async def get_error_statistics(
    error_tracker: LocalErrorTracker = Depends(get_error_tracker)
):
    """
    Get error statistics for local development.
    
    Returns comprehensive error statistics including counts by category,
    service, and time period.
    """
    try:
        stats = error_tracker.get_error_statistics()
        return _convert_error_stats(stats)
        
    except Exception as e:
        logger.error(f"Failed to get error statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve error statistics")


@router.get("/statistics/alerts", response_model=AlertStatsResponse)
async def get_alert_statistics(
    alerting_system: LocalAlertingSystem = Depends(get_alerting_system)
):
    """
    Get alert statistics for local development.
    
    Returns comprehensive alert statistics including counts by type,
    severity, and resolution status.
    """
    try:
        stats = alerting_system.get_alert_statistics()
        return _convert_alert_stats(stats)
        
    except Exception as e:
        logger.error(f"Failed to get alert statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve alert statistics")


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard_data(
    error_tracker: LocalErrorTracker = Depends(get_error_tracker),
    alerting_system: LocalAlertingSystem = Depends(get_alerting_system)
):
    """
    Get comprehensive dashboard data for local development monitoring.
    
    Returns error statistics, alert statistics, system health information,
    and recent activity for display in a monitoring dashboard.
    """
    try:
        # Get error and alert statistics
        error_stats = error_tracker.get_error_statistics()
        alert_stats = alerting_system.get_alert_statistics()
        
        # Get system health information
        system_health = {
            "error_tracking_active": error_tracker._tracking_active,
            "alerting_active": alerting_system._alerting_active,
            "total_errors_24h": len([
                e for e in error_tracker._error_history
                if datetime.now() - e.timestamp <= timedelta(hours=24)
            ]),
            "total_alerts_24h": len([
                a for a in alerting_system._alert_history
                if datetime.now() - a.timestamp <= timedelta(hours=24)
            ]),
            "active_alerts": len(alerting_system._active_alerts),
            "critical_errors": error_stats.critical_error_count,
            "unresolved_errors": error_stats.unresolved_error_count
        }
        
        # Get recent activity (errors and alerts combined)
        recent_activity = []
        
        # Add recent errors
        for error in error_stats.recent_errors[-5:]:
            recent_activity.append({
                "type": "error",
                "timestamp": error.timestamp,
                "title": f"Error in {error.service}",
                "message": error.message,
                "severity": error.severity,
                "id": error.id
            })
        
        # Add recent alerts
        for alert in alert_stats.recent_alerts[-5:]:
            recent_activity.append({
                "type": "alert",
                "timestamp": alert.timestamp,
                "title": alert.title,
                "message": alert.message,
                "severity": alert.severity,
                "id": alert.id
            })
        
        # Sort by timestamp (most recent first)
        recent_activity.sort(key=lambda x: x["timestamp"], reverse=True)
        recent_activity = recent_activity[:10]
        
        return DashboardResponse(
            error_stats=_convert_error_stats(error_stats),
            alert_stats=_convert_alert_stats(alert_stats),
            system_health=system_health,
            recent_activity=recent_activity
        )
        
    except Exception as e:
        logger.error(f"Failed to get dashboard data: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve dashboard data")


# Health Check Endpoints
@router.get("/health")
async def health_check(
    error_tracker: LocalErrorTracker = Depends(get_error_tracker),
    alerting_system: LocalAlertingSystem = Depends(get_alerting_system)
):
    """
    Health check for local error tracking and alerting systems.
    
    Returns the status of error tracking and alerting systems.
    """
    try:
        return {
            "status": "healthy",
            "error_tracking_active": error_tracker._tracking_active,
            "alerting_active": alerting_system._alerting_active,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# Configuration Endpoints
@router.get("/config")
async def get_configuration():
    """
    Get current configuration for local error tracking and alerting.
    
    Returns configuration information for debugging and monitoring purposes.
    """
    try:
        config = LocalDatabaseConfig()
        
        return {
            "log_dir": config.log_dir,
            "debug": config.debug,
            "log_level": config.log_level,
            "enable_notifications": True,  # This would be determined by the system
            "tracking_enabled": True,
            "alerting_enabled": True
        }
        
    except Exception as e:
        logger.error(f"Failed to get configuration: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve configuration")