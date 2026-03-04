"""
Performance Alerting API Router

This module provides REST API endpoints for managing and monitoring the
performance alerting system in local development environments.

Features:
- Get alerting system status
- Configure alert thresholds
- View active alerts
- Manage alert rules
- Performance metrics dashboard integration
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field

from ..dependencies.services import get_local_alerting_system_optional
from ...monitoring.local_performance_alerting import (
    LocalPerformanceAlerting,
    PerformanceAlertType,
    PerformanceThreshold,
    PerformanceAlertRule,
    get_local_performance_alerting
)
from ...monitoring.performance_alerting_integration import (
    PerformanceAlertingIntegration,
    get_performance_alerting_integration
)
from ...monitoring.alerting_service import AlertSeverity
from ...config.local_config import LocalDatabaseConfig
from ...logging_config import get_logger

logger = get_logger("performance_alerting_api")

router = APIRouter(prefix="/performance-alerting", tags=["Performance Alerting"])


# Pydantic models for API
class AlertThresholdModel(BaseModel):
    """Model for alert threshold configuration."""
    metric_name: str = Field(..., description="Name of the metric to monitor")
    threshold_value: float = Field(..., description="Threshold value for alerting")
    comparison: str = Field("greater_than", description="Comparison operator")
    window_minutes: int = Field(5, description="Time window for evaluation")
    min_samples: int = Field(3, description="Minimum samples required")
    severity: str = Field("medium", description="Alert severity level")
    cooldown_minutes: int = Field(10, description="Cooldown period between alerts")
    auto_resolve: bool = Field(True, description="Whether to auto-resolve alerts")


class AlertRuleModel(BaseModel):
    """Model for alert rule configuration."""
    alert_type: str = Field(..., description="Type of performance alert")
    service_pattern: str = Field(..., description="Service name pattern (regex)")
    thresholds: List[AlertThresholdModel] = Field(..., description="Alert thresholds")
    enabled: bool = Field(True, description="Whether the rule is enabled")
    description: str = Field("", description="Rule description")
    remediation_steps: List[str] = Field(default_factory=list, description="Remediation steps")


class AlertingStatusModel(BaseModel):
    """Model for alerting system status."""
    integration_active: bool = Field(..., description="Whether integration is active")
    alerting_system_active: bool = Field(..., description="Whether alerting system is active")
    components_initialized: Dict[str, bool] = Field(..., description="Component initialization status")
    custom_thresholds_count: int = Field(..., description="Number of custom thresholds")
    alert_rules_count: int = Field(0, description="Number of alert rules")
    timestamp: str = Field(..., description="Status timestamp")


class CustomThresholdRequest(BaseModel):
    """Model for custom threshold configuration request."""
    alert_type: str = Field(..., description="Performance alert type")
    metric_name: str = Field(..., description="Metric name to monitor")
    threshold_value: float = Field(..., description="Threshold value")
    comparison: str = Field("greater_than", description="Comparison operator")
    severity: str = Field("medium", description="Alert severity")


@router.get("/status", response_model=AlertingStatusModel)
async def get_alerting_status():
    """
    Get the current status of the performance alerting system.
    
    Returns information about the alerting system state, component
    initialization status, and configuration.
    """
    try:
        integration = get_performance_alerting_integration()
        status = integration.get_alerting_status()
        
        return AlertingStatusModel(**status)
        
    except Exception as e:
        logger.error(f"Failed to get alerting status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get alerting status: {str(e)}"
        )


@router.get("/rules", response_model=Dict[str, AlertRuleModel])
async def get_alert_rules():
    """
    Get all configured alert rules.
    
    Returns a dictionary of alert rules keyed by alert type.
    """
    try:
        alerting = get_local_performance_alerting()
        rules = alerting.get_alert_rules()
        
        # Convert to API models
        api_rules = {}
        for alert_type, rule in rules.items():
            api_thresholds = [
                AlertThresholdModel(
                    metric_name=t.metric_name,
                    threshold_value=t.threshold_value,
                    comparison=t.comparison,
                    window_minutes=t.window_minutes,
                    min_samples=t.min_samples,
                    severity=t.severity.value.lower(),
                    cooldown_minutes=t.cooldown_minutes,
                    auto_resolve=t.auto_resolve
                )
                for t in rule.thresholds
            ]
            
            api_rules[alert_type.value] = AlertRuleModel(
                alert_type=alert_type.value,
                service_pattern=rule.service_pattern,
                thresholds=api_thresholds,
                enabled=rule.enabled,
                description=rule.description,
                remediation_steps=rule.remediation_steps
            )
        
        return api_rules
        
    except Exception as e:
        logger.error(f"Failed to get alert rules: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get alert rules: {str(e)}"
        )


@router.put("/rules/{alert_type}/enable")
async def enable_alert_rule(alert_type: str):
    """
    Enable a specific alert rule.
    
    Args:
        alert_type: The type of alert rule to enable
    """
    try:
        # Validate alert type
        try:
            perf_alert_type = PerformanceAlertType(alert_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid alert type: {alert_type}"
            )
        
        alerting = get_local_performance_alerting()
        alerting.enable_alert_rule(perf_alert_type)
        
        return {"message": f"Alert rule {alert_type} enabled successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enable alert rule {alert_type}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to enable alert rule: {str(e)}"
        )


@router.put("/rules/{alert_type}/disable")
async def disable_alert_rule(alert_type: str):
    """
    Disable a specific alert rule.
    
    Args:
        alert_type: The type of alert rule to disable
    """
    try:
        # Validate alert type
        try:
            perf_alert_type = PerformanceAlertType(alert_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid alert type: {alert_type}"
            )
        
        alerting = get_local_performance_alerting()
        alerting.disable_alert_rule(perf_alert_type)
        
        return {"message": f"Alert rule {alert_type} disabled successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disable alert rule {alert_type}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to disable alert rule: {str(e)}"
        )


@router.post("/thresholds/custom")
async def configure_custom_threshold(request: CustomThresholdRequest):
    """
    Configure a custom performance threshold.
    
    Args:
        request: Custom threshold configuration
    """
    try:
        # Validate alert type
        try:
            perf_alert_type = PerformanceAlertType(request.alert_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid alert type: {request.alert_type}"
            )
        
        # Validate severity
        valid_severities = ["low", "medium", "high", "critical"]
        if request.severity.lower() not in valid_severities:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid severity: {request.severity}. Must be one of {valid_severities}"
            )
        
        # Validate comparison
        valid_comparisons = ["greater_than", "less_than", "equals"]
        if request.comparison not in valid_comparisons:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid comparison: {request.comparison}. Must be one of {valid_comparisons}"
            )
        
        integration = get_performance_alerting_integration()
        integration.configure_custom_threshold(
            alert_type=perf_alert_type,
            metric_name=request.metric_name,
            threshold_value=request.threshold_value,
            comparison=request.comparison,
            severity=request.severity
        )
        
        return {
            "message": "Custom threshold configured successfully",
            "alert_type": request.alert_type,
            "metric_name": request.metric_name,
            "threshold_value": request.threshold_value
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to configure custom threshold: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to configure custom threshold: {str(e)}"
        )


@router.post("/restart")
async def restart_alerting():
    """
    Restart the performance alerting system.
    
    This can be useful after configuration changes or to recover
    from errors in the alerting system.
    """
    try:
        integration = get_performance_alerting_integration()
        await integration.restart_alerting()
        
        return {"message": "Performance alerting system restarted successfully"}
        
    except Exception as e:
        logger.error(f"Failed to restart alerting system: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to restart alerting system: {str(e)}"
        )


@router.get("/metrics/summary")
async def get_performance_metrics_summary():
    """
    Get a summary of current performance metrics.
    
    Returns key performance indicators that are being monitored
    for alerting purposes.
    """
    try:
        alerting = get_local_performance_alerting()
        
        # Get performance history for key metrics
        metrics_summary = {}
        
        if alerting._performance_history:
            for metric_name, values in alerting._performance_history.items():
                if values:
                    metrics_summary[metric_name] = {
                        "current_value": values[-1] if values else None,
                        "average": sum(values) / len(values) if values else None,
                        "min_value": min(values) if values else None,
                        "max_value": max(values) if values else None,
                        "sample_count": len(values),
                        "last_updated": datetime.now().isoformat()
                    }
        
        return {
            "metrics": metrics_summary,
            "timestamp": datetime.now().isoformat(),
            "monitoring_active": alerting._alerting_active
        }
        
    except Exception as e:
        logger.error(f"Failed to get performance metrics summary: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get performance metrics summary: {str(e)}"
        )


@router.get("/alerts/active")
async def get_active_alerts(
    alerting_system = Depends(get_local_alerting_system_optional)
):
    """
    Get currently active performance alerts.
    
    Returns a list of active alerts from the local alerting system.
    """
    try:
        if not alerting_system:
            return {
                "active_alerts": [],
                "message": "Local alerting system not available",
                "timestamp": datetime.now().isoformat()
            }
        
        active_alerts = alerting_system.get_active_alerts()
        
        # Convert alerts to API format
        api_alerts = []
        for alert in active_alerts:
            api_alerts.append({
                "id": alert.id,
                "timestamp": alert.timestamp.isoformat(),
                "alert_type": alert.alert_type.value,
                "severity": alert.severity.value,
                "title": alert.title,
                "message": alert.message,
                "service": alert.service,
                "context": alert.context,
                "acknowledged": alert.acknowledged,
                "acknowledged_by": alert.acknowledged_by,
                "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None
            })
        
        return {
            "active_alerts": api_alerts,
            "count": len(api_alerts),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get active alerts: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get active alerts: {str(e)}"
        )


@router.put("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    acknowledged_by: str = Query("developer", description="Who is acknowledging the alert"),
    alerting_system = Depends(get_local_alerting_system_optional)
):
    """
    Acknowledge a specific alert.
    
    Args:
        alert_id: ID of the alert to acknowledge
        acknowledged_by: Name of the person acknowledging the alert
    """
    try:
        if not alerting_system:
            raise HTTPException(
                status_code=503,
                detail="Local alerting system not available"
            )
        
        success = await alerting_system.acknowledge_alert(alert_id, acknowledged_by)
        
        if success:
            return {
                "message": f"Alert {alert_id} acknowledged successfully",
                "acknowledged_by": acknowledged_by,
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Alert {alert_id} not found"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to acknowledge alert {alert_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to acknowledge alert: {str(e)}"
        )


@router.put("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    resolution_notes: str = Query("", description="Notes about the resolution"),
    alerting_system = Depends(get_local_alerting_system_optional)
):
    """
    Resolve a specific alert.
    
    Args:
        alert_id: ID of the alert to resolve
        resolution_notes: Notes about how the alert was resolved
    """
    try:
        if not alerting_system:
            raise HTTPException(
                status_code=503,
                detail="Local alerting system not available"
            )
        
        success = await alerting_system.resolve_alert(alert_id, resolution_notes)
        
        if success:
            return {
                "message": f"Alert {alert_id} resolved successfully",
                "resolution_notes": resolution_notes,
                "timestamp": datetime.now().isoformat()
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Alert {alert_id} not found"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resolve alert {alert_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resolve alert: {str(e)}"
        )


@router.get("/health")
async def get_alerting_health():
    """
    Get health status of the performance alerting system.
    
    Returns basic health information for monitoring purposes.
    """
    try:
        integration = get_performance_alerting_integration()
        status = integration.get_alerting_status()
        
        # Determine overall health
        health_status = "healthy"
        if not status["integration_active"]:
            health_status = "inactive"
        elif not status["alerting_system_active"]:
            health_status = "degraded"
        elif not any(status["components_initialized"].values()):
            health_status = "degraded"
        
        return {
            "status": health_status,
            "integration_active": status["integration_active"],
            "alerting_active": status["alerting_system_active"],
            "components_healthy": sum(status["components_initialized"].values()),
            "total_components": len(status["components_initialized"]),
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to get alerting health: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }