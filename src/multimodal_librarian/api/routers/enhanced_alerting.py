"""
Enhanced Alerting API Router - Performance alerts, error rate monitoring, and escalation management

This module provides REST API endpoints for managing the enhanced alerting system including:
- Performance threshold configuration and monitoring
- Error rate alert management
- Escalation rule configuration and status
- External notification channel management
- Alert correlation and noise reduction
- Comprehensive alerting analytics and reporting

Validates: Requirement 6.4 - Alerting system with performance alerts, error rate monitoring, and escalation procedures
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Body, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field

from ...monitoring.enhanced_alerting_system import (
    get_enhanced_alerting_system, EnhancedAlertingSystem,
    EscalationRule, PerformanceThreshold, AlertCategory, EscalationLevel, AlertSeverity
)
from ...monitoring.alerting_service import get_alerting_service, AlertingService

router = APIRouter(prefix="/api/enhanced-alerting", tags=["Enhanced Alerting"])


# Pydantic models for request/response
class EscalationRuleRequest(BaseModel):
    rule_id: str = Field(..., description="Unique identifier for the escalation rule")
    name: str = Field(..., description="Human-readable name for the rule")
    category: str = Field(..., description="Alert category (performance, error_rate, resource_usage, availability, security, business_metrics)")
    severity_threshold: str = Field(..., description="Minimum severity to trigger escalation (low, medium, high, critical)")
    level_1_duration_minutes: int = Field(15, description="Minutes before first escalation")
    level_2_duration_minutes: int = Field(30, description="Minutes before second escalation")
    level_3_duration_minutes: int = Field(60, description="Minutes before third escalation")
    level_1_channels: List[str] = Field(default_factory=list, description="Notification channels for level 1")
    level_2_channels: List[str] = Field(default_factory=list, description="Notification channels for level 2")
    level_3_channels: List[str] = Field(default_factory=list, description="Notification channels for level 3")
    level_4_channels: List[str] = Field(default_factory=list, description="Notification channels for level 4")
    auto_escalate: bool = Field(True, description="Whether to automatically escalate")
    require_acknowledgment: bool = Field(True, description="Whether acknowledgment prevents escalation")
    max_escalation_level: str = Field("level_4", description="Maximum escalation level")
    enabled: bool = Field(True, description="Whether the rule is enabled")


class PerformanceThresholdRequest(BaseModel):
    metric_name: str = Field(..., description="Name of the metric to monitor")
    threshold_value: float = Field(..., description="Threshold value for alerting")
    comparison: str = Field(..., description="Comparison operator (greater_than, less_than, equals)")
    severity: str = Field(..., description="Alert severity (low, medium, high, critical)")
    evaluation_window_minutes: int = Field(5, description="Evaluation window in minutes")
    consecutive_violations: int = Field(2, description="Number of consecutive violations before alerting")
    description: str = Field("", description="Human-readable description")
    category: str = Field("performance", description="Alert category")


class NotificationChannelConfig(BaseModel):
    channel_id: str = Field(..., description="Channel identifier")
    config: Dict[str, Any] = Field(..., description="Channel configuration")


# Service dependencies
def get_enhanced_alerting() -> EnhancedAlertingSystem:
    """Get enhanced alerting system instance."""
    return get_enhanced_alerting_system()


def get_base_alerting() -> AlertingService:
    """Get base alerting service instance."""
    return get_alerting_service()


# System Management Endpoints
@router.post("/start")
async def start_enhanced_alerting_system(
    background_tasks: BackgroundTasks,
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    Start the enhanced alerting system.
    
    Initializes performance monitoring, error rate tracking, and escalation procedures.
    """
    try:
        # Start in background to avoid blocking
        background_tasks.add_task(enhanced_alerting.start_enhanced_alerting)
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Enhanced alerting system startup initiated",
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start enhanced alerting: {str(e)}")


@router.post("/stop")
async def stop_enhanced_alerting_system(
    background_tasks: BackgroundTasks,
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    Stop the enhanced alerting system.
    
    Gracefully shuts down all monitoring and escalation processes.
    """
    try:
        # Stop in background to avoid blocking
        background_tasks.add_task(enhanced_alerting.stop_enhanced_alerting)
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Enhanced alerting system shutdown initiated",
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop enhanced alerting: {str(e)}")


@router.get("/status")
async def get_enhanced_alerting_status(
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    Get comprehensive enhanced alerting system status.
    
    Returns system status, active escalations, performance monitoring state,
    and configuration summary.
    """
    try:
        status = enhanced_alerting.get_escalation_status()
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "data": status,
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get system status: {str(e)}")


# Escalation Rule Management
@router.post("/escalation-rules")
async def create_escalation_rule(
    rule_request: EscalationRuleRequest,
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    Create or update an escalation rule.
    
    Escalation rules define how alerts are escalated through different levels
    based on severity, timing, and acknowledgment requirements.
    """
    try:
        # Convert request to EscalationRule object
        escalation_rule = EscalationRule(
            rule_id=rule_request.rule_id,
            name=rule_request.name,
            category=AlertCategory(rule_request.category),
            severity_threshold=AlertSeverity(rule_request.severity_threshold),
            level_1_duration_minutes=rule_request.level_1_duration_minutes,
            level_2_duration_minutes=rule_request.level_2_duration_minutes,
            level_3_duration_minutes=rule_request.level_3_duration_minutes,
            level_1_channels=rule_request.level_1_channels,
            level_2_channels=rule_request.level_2_channels,
            level_3_channels=rule_request.level_3_channels,
            level_4_channels=rule_request.level_4_channels,
            auto_escalate=rule_request.auto_escalate,
            require_acknowledgment=rule_request.require_acknowledgment,
            max_escalation_level=EscalationLevel(rule_request.max_escalation_level),
            enabled=rule_request.enabled
        )
        
        success = enhanced_alerting.add_escalation_rule(escalation_rule)
        
        if success:
            return JSONResponse(
                status_code=201,
                content={
                    "status": "success",
                    "message": f"Escalation rule '{rule_request.name}' created successfully",
                    "rule_id": rule_request.rule_id,
                    "timestamp": datetime.now().isoformat()
                }
            )
        else:
            raise HTTPException(status_code=400, detail="Failed to create escalation rule")
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request data: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create escalation rule: {str(e)}")


@router.get("/escalation-rules")
async def list_escalation_rules(
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    List all escalation rules.
    
    Returns all configured escalation rules with their current status and configuration.
    """
    try:
        with enhanced_alerting._lock:
            rules_data = []
            for rule_id, rule in enhanced_alerting._escalation_rules.items():
                rules_data.append({
                    "rule_id": rule.rule_id,
                    "name": rule.name,
                    "category": rule.category.value,
                    "severity_threshold": rule.severity_threshold.value,
                    "level_1_duration_minutes": rule.level_1_duration_minutes,
                    "level_2_duration_minutes": rule.level_2_duration_minutes,
                    "level_3_duration_minutes": rule.level_3_duration_minutes,
                    "level_1_channels": rule.level_1_channels,
                    "level_2_channels": rule.level_2_channels,
                    "level_3_channels": rule.level_3_channels,
                    "level_4_channels": rule.level_4_channels,
                    "auto_escalate": rule.auto_escalate,
                    "require_acknowledgment": rule.require_acknowledgment,
                    "max_escalation_level": rule.max_escalation_level.value,
                    "enabled": rule.enabled
                })
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "data": {
                    "escalation_rules": rules_data,
                    "total_rules": len(rules_data)
                },
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list escalation rules: {str(e)}")


@router.delete("/escalation-rules/{rule_id}")
async def delete_escalation_rule(
    rule_id: str,
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    Delete an escalation rule.
    
    Removes the specified escalation rule from the system.
    """
    try:
        with enhanced_alerting._lock:
            if rule_id in enhanced_alerting._escalation_rules:
                del enhanced_alerting._escalation_rules[rule_id]
                success = True
            else:
                success = False
        
        if success:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": f"Escalation rule '{rule_id}' deleted successfully",
                    "timestamp": datetime.now().isoformat()
                }
            )
        else:
            raise HTTPException(status_code=404, detail=f"Escalation rule '{rule_id}' not found")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete escalation rule: {str(e)}")


# Performance Threshold Management
@router.post("/performance-thresholds")
async def create_performance_threshold(
    threshold_request: PerformanceThresholdRequest,
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    Create or update a performance threshold.
    
    Performance thresholds define when to trigger alerts based on system metrics
    like response time, CPU usage, memory usage, etc.
    """
    try:
        # Convert request to PerformanceThreshold object
        threshold = PerformanceThreshold(
            metric_name=threshold_request.metric_name,
            threshold_value=threshold_request.threshold_value,
            comparison=threshold_request.comparison,
            severity=AlertSeverity(threshold_request.severity),
            evaluation_window_minutes=threshold_request.evaluation_window_minutes,
            consecutive_violations=threshold_request.consecutive_violations,
            description=threshold_request.description,
            category=AlertCategory(threshold_request.category)
        )
        
        success = enhanced_alerting.add_performance_threshold(threshold)
        
        if success:
            return JSONResponse(
                status_code=201,
                content={
                    "status": "success",
                    "message": f"Performance threshold for '{threshold_request.metric_name}' created successfully",
                    "metric_name": threshold_request.metric_name,
                    "timestamp": datetime.now().isoformat()
                }
            )
        else:
            raise HTTPException(status_code=400, detail="Failed to create performance threshold")
            
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid request data: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create performance threshold: {str(e)}")


@router.get("/performance-thresholds")
async def list_performance_thresholds(
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    List all performance thresholds.
    
    Returns all configured performance thresholds with their current status.
    """
    try:
        with enhanced_alerting._lock:
            thresholds_data = []
            for metric_name, threshold in enhanced_alerting._performance_thresholds.items():
                # Get current violation count
                violation_count = enhanced_alerting._threshold_violations.get(metric_name, 0)
                
                thresholds_data.append({
                    "metric_name": threshold.metric_name,
                    "threshold_value": threshold.threshold_value,
                    "comparison": threshold.comparison,
                    "severity": threshold.severity.value,
                    "evaluation_window_minutes": threshold.evaluation_window_minutes,
                    "consecutive_violations": threshold.consecutive_violations,
                    "description": threshold.description,
                    "category": threshold.category.value,
                    "current_violation_count": violation_count
                })
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "data": {
                    "performance_thresholds": thresholds_data,
                    "total_thresholds": len(thresholds_data)
                },
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list performance thresholds: {str(e)}")


@router.delete("/performance-thresholds/{metric_name}")
async def delete_performance_threshold(
    metric_name: str,
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    Delete a performance threshold.
    
    Removes the specified performance threshold from monitoring.
    """
    try:
        with enhanced_alerting._lock:
            if metric_name in enhanced_alerting._performance_thresholds:
                del enhanced_alerting._performance_thresholds[metric_name]
                # Also clear violation count
                if metric_name in enhanced_alerting._threshold_violations:
                    del enhanced_alerting._threshold_violations[metric_name]
                success = True
            else:
                success = False
        
        if success:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": f"Performance threshold for '{metric_name}' deleted successfully",
                    "timestamp": datetime.now().isoformat()
                }
            )
        else:
            raise HTTPException(status_code=404, detail=f"Performance threshold for '{metric_name}' not found")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete performance threshold: {str(e)}")


# Escalated Alert Management
@router.get("/escalated-alerts")
async def get_escalated_alerts(
    status: Optional[str] = Query(None, description="Filter by status (active, acknowledged, resolved)"),
    level: Optional[str] = Query(None, description="Filter by escalation level"),
    limit: int = Query(50, ge=1, le=500, description="Maximum number of alerts to return"),
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    Get escalated alerts with optional filtering.
    
    Returns escalated alerts with their current status, escalation history,
    and related information.
    """
    try:
        with enhanced_alerting._lock:
            escalated_alerts = list(enhanced_alerting._escalated_alerts.values())
        
        # Apply filters
        if status:
            if status == "active":
                escalated_alerts = [a for a in escalated_alerts if not a.acknowledged and not a.resolved]
            elif status == "acknowledged":
                escalated_alerts = [a for a in escalated_alerts if a.acknowledged and not a.resolved]
            elif status == "resolved":
                escalated_alerts = [a for a in escalated_alerts if a.resolved]
        
        if level:
            escalated_alerts = [a for a in escalated_alerts if a.current_level.value == level]
        
        # Sort by creation time (newest first) and limit
        escalated_alerts = sorted(escalated_alerts, key=lambda x: x.created_at, reverse=True)[:limit]
        
        # Convert to response format
        alerts_data = []
        for alert in escalated_alerts:
            alerts_data.append({
                "alert_id": alert.alert_id,
                "original_alert": {
                    "alert_id": alert.original_alert.alert_id,
                    "rule_name": alert.original_alert.rule_name,
                    "severity": alert.original_alert.severity.value,
                    "message": alert.original_alert.message,
                    "triggered_at": alert.original_alert.triggered_at.isoformat(),
                    "metric_value": alert.original_alert.metric_value,
                    "threshold": alert.original_alert.threshold
                },
                "escalation_rule": {
                    "rule_id": alert.escalation_rule.rule_id,
                    "name": alert.escalation_rule.name,
                    "category": alert.escalation_rule.category.value
                },
                "current_level": alert.current_level.value,
                "escalation_history": alert.escalation_history,
                "acknowledged": alert.acknowledged,
                "acknowledged_by": alert.acknowledged_by,
                "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                "resolved": alert.resolved,
                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
                "created_at": alert.created_at.isoformat()
            })
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "data": {
                    "escalated_alerts": alerts_data,
                    "total_alerts": len(alerts_data),
                    "filters_applied": {
                        "status": status,
                        "level": level,
                        "limit": limit
                    }
                },
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get escalated alerts: {str(e)}")


@router.post("/escalated-alerts/{alert_id}/acknowledge")
async def acknowledge_escalated_alert(
    alert_id: str,
    acknowledged_by: str = Body(..., embed=True),
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    Acknowledge an escalated alert.
    
    Acknowledging an alert may prevent further escalation depending on the
    escalation rule configuration.
    """
    try:
        success = enhanced_alerting.acknowledge_escalated_alert(alert_id, acknowledged_by)
        
        if success:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": f"Escalated alert acknowledged by {acknowledged_by}",
                    "alert_id": alert_id,
                    "acknowledged_by": acknowledged_by,
                    "timestamp": datetime.now().isoformat()
                }
            )
        else:
            raise HTTPException(status_code=404, detail=f"Escalated alert '{alert_id}' not found")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to acknowledge escalated alert: {str(e)}")


@router.post("/escalated-alerts/{alert_id}/resolve")
async def resolve_escalated_alert(
    alert_id: str,
    reason: str = Body(..., embed=True),
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    Resolve an escalated alert.
    
    Resolving an alert removes it from active escalations and stops further escalation.
    """
    try:
        success = enhanced_alerting.resolve_escalated_alert(alert_id, reason)
        
        if success:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": f"Escalated alert resolved: {reason}",
                    "alert_id": alert_id,
                    "resolution_reason": reason,
                    "timestamp": datetime.now().isoformat()
                }
            )
        else:
            raise HTTPException(status_code=404, detail=f"Escalated alert '{alert_id}' not found")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to resolve escalated alert: {str(e)}")


# Notification Channel Management
@router.post("/notification-channels/configure")
async def configure_notification_channel(
    channel_config: NotificationChannelConfig,
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    Configure an external notification channel.
    
    Configures channels like email, Slack, PagerDuty, SMS, etc. for alert notifications.
    """
    try:
        success = enhanced_alerting.configure_external_channel(
            channel_config.channel_id, 
            channel_config.config
        )
        
        if success:
            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": f"Notification channel '{channel_config.channel_id}' configured successfully",
                    "channel_id": channel_config.channel_id,
                    "timestamp": datetime.now().isoformat()
                }
            )
        else:
            raise HTTPException(status_code=400, detail=f"Failed to configure channel '{channel_config.channel_id}'")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to configure notification channel: {str(e)}")


@router.get("/notification-channels")
async def list_notification_channels(
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    List all notification channels.
    
    Returns all configured notification channels with their status and configuration
    (sensitive information is masked).
    """
    try:
        with enhanced_alerting._lock:
            channels_data = []
            for channel_id, channel in enhanced_alerting._external_channels.items():
                # Mask sensitive configuration data
                masked_config = {}
                for key, value in channel["config"].items():
                    if key in ["password", "auth_token", "integration_key", "webhook_url"]:
                        masked_config[key] = "***masked***" if value else ""
                    else:
                        masked_config[key] = value
                
                channels_data.append({
                    "channel_id": channel_id,
                    "type": channel["type"],
                    "enabled": channel["enabled"],
                    "config": masked_config
                })
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "data": {
                    "notification_channels": channels_data,
                    "total_channels": len(channels_data),
                    "enabled_channels": len([c for c in channels_data if c["enabled"]])
                },
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list notification channels: {str(e)}")


# Alert Correlation
@router.get("/alert-correlations")
async def get_alert_correlations(
    limit: int = Query(50, ge=1, le=200, description="Maximum number of correlations to return"),
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    Get alert correlations.
    
    Returns correlated alerts that have been grouped together to reduce noise.
    """
    try:
        with enhanced_alerting._lock:
            correlations = list(enhanced_alerting._alert_correlations.values())
        
        # Sort by creation time (newest first) and limit
        correlations = sorted(correlations, key=lambda x: x.created_at, reverse=True)[:limit]
        
        correlations_data = []
        for correlation in correlations:
            correlations_data.append({
                "correlation_id": correlation.correlation_id,
                "related_alerts": correlation.related_alerts,
                "root_cause_alert": correlation.root_cause_alert,
                "correlation_reason": correlation.correlation_reason,
                "created_at": correlation.created_at.isoformat(),
                "suppressed_alerts": correlation.suppressed_alerts,
                "total_related_alerts": len(correlation.related_alerts),
                "total_suppressed_alerts": len(correlation.suppressed_alerts)
            })
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "data": {
                    "alert_correlations": correlations_data,
                    "total_correlations": len(correlations_data)
                },
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get alert correlations: {str(e)}")


# Analytics and Reporting
@router.get("/analytics/escalation-trends")
async def get_escalation_trends(
    hours: int = Query(24, ge=1, le=168, description="Time period in hours"),
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    Get escalation trends and analytics.
    
    Returns escalation patterns, frequency, and trends over the specified time period.
    """
    try:
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with enhanced_alerting._lock:
            # Get all escalated alerts (including resolved ones)
            all_escalations = list(enhanced_alerting._escalated_alerts.values())
            
            # Filter by time period
            recent_escalations = [
                esc for esc in all_escalations 
                if esc.created_at >= cutoff_time
            ]
        
        # Calculate trends
        escalation_by_level = {}
        escalation_by_category = {}
        escalation_by_hour = {}
        
        for escalation in recent_escalations:
            # By level
            level = escalation.current_level.value
            escalation_by_level[level] = escalation_by_level.get(level, 0) + 1
            
            # By category
            category = escalation.escalation_rule.category.value
            escalation_by_category[category] = escalation_by_category.get(category, 0) + 1
            
            # By hour
            hour_key = escalation.created_at.strftime('%Y-%m-%d %H:00')
            escalation_by_hour[hour_key] = escalation_by_hour.get(hour_key, 0) + 1
        
        # Calculate resolution rates
        resolved_escalations = [esc for esc in recent_escalations if esc.resolved]
        acknowledged_escalations = [esc for esc in recent_escalations if esc.acknowledged]
        
        resolution_rate = (len(resolved_escalations) / len(recent_escalations) * 100) if recent_escalations else 0
        acknowledgment_rate = (len(acknowledged_escalations) / len(recent_escalations) * 100) if recent_escalations else 0
        
        # Average escalation time
        escalation_times = []
        for escalation in resolved_escalations:
            if escalation.resolved_at:
                duration = (escalation.resolved_at - escalation.created_at).total_seconds() / 60
                escalation_times.append(duration)
        
        avg_escalation_time = sum(escalation_times) / len(escalation_times) if escalation_times else 0
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "data": {
                    "time_period_hours": hours,
                    "total_escalations": len(recent_escalations),
                    "escalation_by_level": escalation_by_level,
                    "escalation_by_category": escalation_by_category,
                    "escalation_by_hour": escalation_by_hour,
                    "resolution_rate_percent": round(resolution_rate, 2),
                    "acknowledgment_rate_percent": round(acknowledgment_rate, 2),
                    "average_escalation_time_minutes": round(avg_escalation_time, 2),
                    "active_escalations": len([esc for esc in recent_escalations if not esc.resolved]),
                    "resolved_escalations": len(resolved_escalations)
                },
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get escalation trends: {str(e)}")


@router.get("/analytics/performance-metrics")
async def get_performance_metrics_analytics(
    hours: int = Query(24, ge=1, le=168, description="Time period in hours"),
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    Get performance metrics analytics.
    
    Returns performance threshold violations, trends, and system health metrics.
    """
    try:
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Get performance history
        performance_data = {}
        with enhanced_alerting._lock:
            for metric_name, history in enhanced_alerting._performance_history.items():
                recent_data = [
                    entry for entry in history 
                    if entry['timestamp'] >= cutoff_time
                ]
                
                if recent_data:
                    values = [entry['value'] for entry in recent_data]
                    performance_data[metric_name] = {
                        'data_points': len(recent_data),
                        'min_value': min(values),
                        'max_value': max(values),
                        'avg_value': sum(values) / len(values),
                        'current_value': recent_data[-1]['value'],
                        'threshold': enhanced_alerting._performance_thresholds[metric_name].threshold_value if metric_name in enhanced_alerting._performance_thresholds else None,
                        'current_violations': enhanced_alerting._threshold_violations.get(metric_name, 0)
                    }
        
        # Calculate overall system health score
        health_score = 100.0
        total_violations = sum(enhanced_alerting._threshold_violations.values())
        if total_violations > 0:
            health_score = max(0, 100 - (total_violations * 5))  # Reduce by 5 points per violation
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "data": {
                    "time_period_hours": hours,
                    "performance_metrics": performance_data,
                    "system_health_score": round(health_score, 2),
                    "total_threshold_violations": total_violations,
                    "monitored_metrics": len(performance_data),
                    "active_thresholds": len(enhanced_alerting._performance_thresholds)
                },
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get performance metrics analytics: {str(e)}")


@router.get("/export/report")
async def export_enhanced_alerting_report(
    format: str = Query("json", description="Export format (json)"),
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    Export comprehensive enhanced alerting report.
    
    Generates a detailed report including all configurations, active alerts,
    escalations, and analytics data.
    """
    try:
        if format.lower() != "json":
            raise HTTPException(status_code=400, detail="Only JSON format is currently supported")
        
        # Generate report
        filepath = enhanced_alerting.export_escalation_report()
        
        # Return file
        return FileResponse(
            path=filepath,
            filename=f"enhanced_alerting_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            media_type="application/json"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export report: {str(e)}")


# Health Check
@router.get("/health")
async def enhanced_alerting_health_check(
    enhanced_alerting: EnhancedAlertingSystem = Depends(get_enhanced_alerting)
):
    """
    Enhanced alerting system health check.
    
    Returns the current health status of the enhanced alerting system.
    """
    try:
        status = enhanced_alerting.get_escalation_status()
        
        # Determine overall health
        health_status = "healthy"
        if status["critical_escalations"] > 0:
            health_status = "critical"
        elif status["active_escalations"] > 10:
            health_status = "warning"
        elif not status["system_active"]:
            health_status = "inactive"
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "health": health_status,
                "system_active": status["system_active"],
                "active_escalations": status["active_escalations"],
                "critical_escalations": status["critical_escalations"],
                "performance_monitoring_enabled": status["performance_monitoring_enabled"],
                "error_monitoring_enabled": status["error_monitoring_enabled"],
                "enabled_channels": status["enabled_channels"],
                "timestamp": datetime.now().isoformat()
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")