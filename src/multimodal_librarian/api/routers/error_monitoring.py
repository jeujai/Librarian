"""
Error Monitoring API Router

Provides REST API endpoints for the error monitoring system including:
- Real-time error metrics and rates
- Alert management and configuration
- Threshold configuration
- Monitoring system status and control
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from ...monitoring.error_monitoring_system import (
    get_error_monitoring_system,
    ErrorThresholdConfig,
    ErrorRateThreshold,
    start_error_monitoring,
    stop_error_monitoring,
    record_operation_result,
    get_current_error_rate
)
from ...monitoring.error_logging_service import ErrorCategory, ErrorSeverity
from ...monitoring.alerting_service import AlertSeverity
from ...logging_config import get_logger

logger = get_logger("error_monitoring_api")

router = APIRouter(prefix="/error-monitoring", tags=["Error Monitoring"])


# Pydantic models for API
class ErrorRateResponse(BaseModel):
    """Error rate response model."""
    service: str
    operation: Optional[str] = None
    window_minutes: int
    total_operations: int
    total_errors: int
    total_successes: int
    error_rate_percentage: float
    errors_per_minute: float
    timestamp: datetime


class ErrorMetricsResponse(BaseModel):
    """System error metrics response model."""
    timestamp: datetime
    total_operations: int
    total_errors: int
    error_rate: float
    errors_by_category: Dict[str, int]
    errors_by_severity: Dict[str, int]
    errors_by_service: Dict[str, int]
    top_error_types: List[Dict[str, Any]]


class ThresholdConfigRequest(BaseModel):
    """Threshold configuration request model."""
    service: str
    operation: Optional[str] = None
    category: Optional[str] = None
    warning_rate: float = Field(default=5.0, ge=0.1, le=1000.0)
    critical_rate: float = Field(default=20.0, ge=0.1, le=1000.0)
    warning_percentage: float = Field(default=5.0, ge=0.1, le=100.0)
    critical_percentage: float = Field(default=15.0, ge=0.1, le=100.0)
    evaluation_window_minutes: int = Field(default=5, ge=1, le=60)
    cooldown_minutes: int = Field(default=15, ge=1, le=120)
    escalate_after_minutes: int = Field(default=30, ge=5, le=240)
    max_consecutive_alerts: int = Field(default=3, ge=1, le=10)
    enabled: bool = True


class ThresholdConfigResponse(BaseModel):
    """Threshold configuration response model."""
    service: str
    operation: Optional[str] = None
    category: Optional[str] = None
    warning_rate: float
    critical_rate: float
    warning_percentage: float
    critical_percentage: float
    evaluation_window_minutes: int
    cooldown_minutes: int
    escalate_after_minutes: int
    max_consecutive_alerts: int
    enabled: bool


class ErrorAlertResponse(BaseModel):
    """Error alert response model."""
    alert_id: str
    service: str
    operation: Optional[str] = None
    triggered_at: datetime
    current_rate: float
    current_percentage: float
    threshold_exceeded: str
    severity: str
    message: str
    consecutive_count: int
    escalated: bool
    acknowledged: bool = False
    resolved: bool = False


class MonitoringStatusResponse(BaseModel):
    """Monitoring system status response model."""
    monitoring_active: bool
    last_evaluation: datetime
    threshold_configs: int
    active_alerts: int
    critical_alerts: int
    total_alert_history: int
    current_system_metrics: ErrorMetricsResponse
    average_error_rate_1h: float
    services_monitored: int
    metrics_history_size: int


class OperationRecordRequest(BaseModel):
    """Operation record request model."""
    service: str
    operation: str
    success: bool
    error_category: Optional[str] = None
    error_severity: Optional[str] = None


# API Endpoints

@router.get("/status", response_model=MonitoringStatusResponse)
async def get_monitoring_status():
    """Get comprehensive error monitoring system status."""
    try:
        monitoring_system = get_error_monitoring_system()
        status = monitoring_system.get_monitoring_status()
        
        return MonitoringStatusResponse(
            monitoring_active=status['monitoring_active'],
            last_evaluation=status['last_evaluation'],
            threshold_configs=status['threshold_configs'],
            active_alerts=status['active_alerts'],
            critical_alerts=status['critical_alerts'],
            total_alert_history=status['total_alert_history'],
            current_system_metrics=ErrorMetricsResponse(**status['current_system_metrics'].__dict__),
            average_error_rate_1h=status['average_error_rate_1h'],
            services_monitored=status['services_monitored'],
            metrics_history_size=status['metrics_history_size']
        )
        
    except Exception as e:
        logger.error(f"Failed to get monitoring status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get monitoring status: {str(e)}")


@router.post("/start")
async def start_monitoring():
    """Start the error monitoring system."""
    try:
        await start_error_monitoring()
        return {"message": "Error monitoring started successfully", "status": "active"}
        
    except Exception as e:
        logger.error(f"Failed to start error monitoring: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start monitoring: {str(e)}")


@router.post("/stop")
async def stop_monitoring():
    """Stop the error monitoring system."""
    try:
        await stop_error_monitoring()
        return {"message": "Error monitoring stopped successfully", "status": "inactive"}
        
    except Exception as e:
        logger.error(f"Failed to stop error monitoring: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to stop monitoring: {str(e)}")


@router.get("/metrics", response_model=ErrorMetricsResponse)
async def get_system_metrics(
    window_minutes: int = Query(default=5, ge=1, le=60, description="Time window in minutes")
):
    """Get comprehensive system error metrics."""
    try:
        monitoring_system = get_error_monitoring_system()
        metrics = monitoring_system.get_system_error_metrics(window_minutes=window_minutes)
        
        return ErrorMetricsResponse(**metrics.__dict__)
        
    except Exception as e:
        logger.error(f"Failed to get system metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@router.get("/error-rate", response_model=ErrorRateResponse)
async def get_error_rate(
    service: str = Query(..., description="Service name"),
    operation: Optional[str] = Query(None, description="Operation name"),
    window_minutes: int = Query(default=5, ge=1, le=60, description="Time window in minutes")
):
    """Get error rate for a specific service/operation."""
    try:
        error_rate_data = get_current_error_rate(service, operation)
        
        # Update window if different from default
        if window_minutes != 5:
            monitoring_system = get_error_monitoring_system()
            error_rate_data = monitoring_system.get_error_rate(service, operation, window_minutes)
        
        return ErrorRateResponse(**error_rate_data)
        
    except Exception as e:
        logger.error(f"Failed to get error rate for {service}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get error rate: {str(e)}")


@router.post("/record-operation")
async def record_operation(request: OperationRecordRequest):
    """Record an operation result for monitoring."""
    try:
        error_category = None
        error_severity = None
        
        if request.error_category:
            try:
                error_category = ErrorCategory(request.error_category)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid error category: {request.error_category}")
        
        if request.error_severity:
            try:
                error_severity = ErrorSeverity(request.error_severity)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid error severity: {request.error_severity}")
        
        record_operation_result(
            service=request.service,
            operation=request.operation,
            success=request.success,
            error_category=error_category,
            error_severity=error_severity
        )
        
        return {
            "message": "Operation recorded successfully",
            "service": request.service,
            "operation": request.operation,
            "success": request.success
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to record operation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record operation: {str(e)}")


@router.get("/thresholds", response_model=List[ThresholdConfigResponse])
async def get_threshold_configs():
    """Get all error threshold configurations."""
    try:
        monitoring_system = get_error_monitoring_system()
        
        configs = []
        with monitoring_system._lock:
            for config in monitoring_system._threshold_configs.values():
                configs.append(ThresholdConfigResponse(
                    service=config.service,
                    operation=config.operation,
                    category=config.category.value if config.category else None,
                    warning_rate=config.warning_rate,
                    critical_rate=config.critical_rate,
                    warning_percentage=config.warning_percentage,
                    critical_percentage=config.critical_percentage,
                    evaluation_window_minutes=config.evaluation_window_minutes,
                    cooldown_minutes=config.cooldown_minutes,
                    escalate_after_minutes=config.escalate_after_minutes,
                    max_consecutive_alerts=config.max_consecutive_alerts,
                    enabled=config.enabled
                ))
        
        return configs
        
    except Exception as e:
        logger.error(f"Failed to get threshold configs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get threshold configs: {str(e)}")


@router.post("/thresholds", response_model=ThresholdConfigResponse)
async def add_threshold_config(request: ThresholdConfigRequest):
    """Add or update an error threshold configuration."""
    try:
        # Validate category if provided
        category = None
        if request.category:
            try:
                category = ErrorCategory(request.category)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid error category: {request.category}")
        
        # Validate threshold values
        if request.warning_rate >= request.critical_rate:
            raise HTTPException(status_code=400, detail="Warning rate must be less than critical rate")
        
        if request.warning_percentage >= request.critical_percentage:
            raise HTTPException(status_code=400, detail="Warning percentage must be less than critical percentage")
        
        # Create threshold config
        config = ErrorThresholdConfig(
            service=request.service,
            operation=request.operation,
            category=category,
            warning_rate=request.warning_rate,
            critical_rate=request.critical_rate,
            warning_percentage=request.warning_percentage,
            critical_percentage=request.critical_percentage,
            evaluation_window_minutes=request.evaluation_window_minutes,
            cooldown_minutes=request.cooldown_minutes,
            escalate_after_minutes=request.escalate_after_minutes,
            max_consecutive_alerts=request.max_consecutive_alerts,
            enabled=request.enabled
        )
        
        monitoring_system = get_error_monitoring_system()
        success = monitoring_system.add_threshold_config(config)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to add threshold configuration")
        
        return ThresholdConfigResponse(
            service=config.service,
            operation=config.operation,
            category=config.category.value if config.category else None,
            warning_rate=config.warning_rate,
            critical_rate=config.critical_rate,
            warning_percentage=config.warning_percentage,
            critical_percentage=config.critical_percentage,
            evaluation_window_minutes=config.evaluation_window_minutes,
            cooldown_minutes=config.cooldown_minutes,
            escalate_after_minutes=config.escalate_after_minutes,
            max_consecutive_alerts=config.max_consecutive_alerts,
            enabled=config.enabled
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to add threshold config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to add threshold config: {str(e)}")


@router.delete("/thresholds/{service}")
async def remove_threshold_config(
    service: str,
    operation: Optional[str] = Query(None, description="Operation name"),
    category: Optional[str] = Query(None, description="Error category")
):
    """Remove an error threshold configuration."""
    try:
        error_category = None
        if category:
            try:
                error_category = ErrorCategory(category)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid error category: {category}")
        
        monitoring_system = get_error_monitoring_system()
        success = monitoring_system.remove_threshold_config(service, operation, error_category)
        
        if not success:
            raise HTTPException(status_code=404, detail="Threshold configuration not found")
        
        return {
            "message": "Threshold configuration removed successfully",
            "service": service,
            "operation": operation,
            "category": category
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to remove threshold config: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to remove threshold config: {str(e)}")


@router.get("/alerts", response_model=List[ErrorAlertResponse])
async def get_active_alerts():
    """Get all active error monitoring alerts."""
    try:
        monitoring_system = get_error_monitoring_system()
        alerts = monitoring_system.get_active_alerts()
        
        response_alerts = []
        for alert in alerts:
            response_alerts.append(ErrorAlertResponse(
                alert_id=alert.alert_id,
                service=alert.threshold_config.service,
                operation=alert.threshold_config.operation,
                triggered_at=alert.triggered_at,
                current_rate=alert.current_rate,
                current_percentage=alert.current_percentage,
                threshold_exceeded=alert.threshold_exceeded,
                severity=alert.severity.value,
                message=alert.message,
                consecutive_count=alert.consecutive_count,
                escalated=alert.escalated,
                acknowledged=alert.metadata.get('acknowledged', False),
                resolved=alert.metadata.get('resolved', False)
            ))
        
        return response_alerts
        
    except Exception as e:
        logger.error(f"Failed to get active alerts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get active alerts: {str(e)}")


@router.get("/alerts/history", response_model=List[ErrorAlertResponse])
async def get_alert_history(
    limit: int = Query(default=50, ge=1, le=500, description="Maximum number of alerts to return")
):
    """Get error alert history."""
    try:
        monitoring_system = get_error_monitoring_system()
        alerts = monitoring_system.get_alert_history(limit=limit)
        
        response_alerts = []
        for alert in alerts:
            response_alerts.append(ErrorAlertResponse(
                alert_id=alert.alert_id,
                service=alert.threshold_config.service,
                operation=alert.threshold_config.operation,
                triggered_at=alert.triggered_at,
                current_rate=alert.current_rate,
                current_percentage=alert.current_percentage,
                threshold_exceeded=alert.threshold_exceeded,
                severity=alert.severity.value,
                message=alert.message,
                consecutive_count=alert.consecutive_count,
                escalated=alert.escalated,
                acknowledged=alert.metadata.get('acknowledged', False),
                resolved=alert.metadata.get('resolved', False)
            ))
        
        return response_alerts
        
    except Exception as e:
        logger.error(f"Failed to get alert history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get alert history: {str(e)}")


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    """Acknowledge an error monitoring alert."""
    try:
        monitoring_system = get_error_monitoring_system()
        success = monitoring_system.acknowledge_alert(alert_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        return {
            "message": "Alert acknowledged successfully",
            "alert_id": alert_id,
            "acknowledged_at": datetime.now()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to acknowledge alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to acknowledge alert: {str(e)}")


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    reason: str = Body(default="Manual resolution", description="Resolution reason")
):
    """Resolve an error monitoring alert."""
    try:
        monitoring_system = get_error_monitoring_system()
        success = monitoring_system.resolve_alert(alert_id, reason)
        
        if not success:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        return {
            "message": "Alert resolved successfully",
            "alert_id": alert_id,
            "resolved_at": datetime.now(),
            "reason": reason
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve alert {alert_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to resolve alert: {str(e)}")


@router.get("/export")
async def export_monitoring_data(
    format: str = Query(default="json", regex="^(json)$", description="Export format")
):
    """Export error monitoring data."""
    try:
        monitoring_system = get_error_monitoring_system()
        
        if format == "json":
            filepath = monitoring_system.export_monitoring_data()
            
            # Read the exported file content
            with open(filepath, 'r') as f:
                data = f.read()
            
            return {
                "message": "Monitoring data exported successfully",
                "format": format,
                "filepath": filepath,
                "data": data
            }
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported export format: {format}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to export monitoring data: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export data: {str(e)}")


@router.get("/health")
async def health_check():
    """Health check endpoint for error monitoring system."""
    try:
        monitoring_system = get_error_monitoring_system()
        status = monitoring_system.get_monitoring_status()
        
        return {
            "status": "healthy",
            "service": "error_monitoring",
            "monitoring_active": status['monitoring_active'],
            "last_evaluation": status['last_evaluation'],
            "active_alerts": status['active_alerts'],
            "timestamp": datetime.now()
        }
        
    except Exception as e:
        logger.error(f"Error monitoring health check failed: {e}")
        return {
            "status": "unhealthy",
            "service": "error_monitoring",
            "error": str(e),
            "timestamp": datetime.now()
        }