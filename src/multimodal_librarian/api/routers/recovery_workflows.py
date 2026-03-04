"""
Recovery Workflows API Router

Provides REST API endpoints for managing and monitoring recovery workflows:
- Recovery workflow management
- Recovery attempt monitoring
- Recovery notifications
- Recovery statistics and metrics
"""

from fastapi import APIRouter, HTTPException, Query, Path, Body
from fastapi.responses import JSONResponse
from typing import Dict, List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field

from ...monitoring.recovery_workflow_manager import (
    get_recovery_workflow_manager,
    RecoveryPriority,
    RecoveryStatus
)
from ...monitoring.recovery_notification_service import (
    get_recovery_notification_service,
    RecoveryNotificationType,
    RecoveryNotificationPriority
)
from ...monitoring.recovery_integration import get_recovery_integration_service
from ...logging_config import get_logger

logger = get_logger("recovery_workflows_api")

router = APIRouter(prefix="/recovery", tags=["Recovery Workflows"])


# Pydantic models for request/response
class TriggerRecoveryRequest(BaseModel):
    """Request model for triggering recovery."""
    service_name: str = Field(..., description="Name of the service to recover")
    reason: str = Field(..., description="Reason for triggering recovery")
    priority: Optional[str] = Field("medium", description="Recovery priority (low, medium, high, critical)")


class AcknowledgeNotificationRequest(BaseModel):
    """Request model for acknowledging notifications."""
    acknowledged_by: str = Field(..., description="Name or ID of person acknowledging")


class RecoveryAttemptResponse(BaseModel):
    """Response model for recovery attempts."""
    attempt_id: str
    workflow_id: str
    service_name: str
    status: str
    start_time: str
    end_time: Optional[str]
    duration_seconds: Optional[float]
    actions_executed: int
    validation_results: int
    error_messages: List[str]
    trigger_reason: str
    priority: str


class RecoveryNotificationResponse(BaseModel):
    """Response model for recovery notifications."""
    notification_id: str
    type: str
    priority: str
    service_name: str
    workflow_id: str
    attempt_id: str
    title: str
    message: str
    timestamp: str
    acknowledged: bool
    acknowledged_by: Optional[str]
    escalation_level: int
    channels_sent: List[str]


# Recovery workflow management endpoints
@router.post("/trigger", response_model=Dict[str, Any])
async def trigger_recovery(request: TriggerRecoveryRequest):
    """
    Manually trigger recovery workflows for a service.
    
    This endpoint allows manual triggering of recovery workflows when automatic
    triggers haven't activated or when immediate recovery is needed.
    """
    try:
        # Validate priority
        priority_mapping = {
            "low": RecoveryPriority.LOW,
            "medium": RecoveryPriority.MEDIUM,
            "high": RecoveryPriority.HIGH,
            "critical": RecoveryPriority.CRITICAL
        }
        
        priority = priority_mapping.get(request.priority.lower(), RecoveryPriority.MEDIUM)
        
        # Get recovery workflow manager
        recovery_manager = get_recovery_workflow_manager()
        
        # Trigger recovery
        attempt_ids = await recovery_manager.trigger_recovery(
            service_name=request.service_name,
            trigger_reason=f"Manual trigger: {request.reason}",
            priority=priority
        )
        
        if attempt_ids:
            logger.info(f"Manually triggered recovery for {request.service_name}: {len(attempt_ids)} attempts")
            
            return {
                "success": True,
                "message": f"Recovery triggered for {request.service_name}",
                "attempt_ids": attempt_ids,
                "service_name": request.service_name,
                "priority": request.priority,
                "trigger_reason": request.reason
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"No recovery workflows available for service: {request.service_name}"
            )
            
    except Exception as e:
        logger.error(f"Failed to trigger recovery: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger recovery: {str(e)}")


@router.get("/attempts/active", response_model=List[Dict[str, Any]])
async def get_active_recovery_attempts():
    """
    Get all currently active recovery attempts.
    
    Returns information about recovery workflows that are currently in progress.
    """
    try:
        recovery_manager = get_recovery_workflow_manager()
        active_attempts = recovery_manager.get_active_attempts()
        
        return active_attempts
        
    except Exception as e:
        logger.error(f"Failed to get active recovery attempts: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get active attempts: {str(e)}")


@router.get("/attempts/history", response_model=List[Dict[str, Any]])
async def get_recovery_history(
    hours: int = Query(24, description="Number of hours to look back", ge=1, le=168),
    service_name: Optional[str] = Query(None, description="Filter by service name")
):
    """
    Get recovery attempt history.
    
    Returns historical information about recovery attempts, optionally filtered
    by service name and time period.
    """
    try:
        recovery_manager = get_recovery_workflow_manager()
        history = recovery_manager.get_recovery_history(hours=hours, service_name=service_name)
        
        return history
        
    except Exception as e:
        logger.error(f"Failed to get recovery history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get recovery history: {str(e)}")


@router.get("/statistics", response_model=Dict[str, Any])
async def get_recovery_statistics():
    """
    Get comprehensive recovery statistics.
    
    Returns statistics about recovery workflows including success rates,
    average durations, and workflow performance metrics.
    """
    try:
        recovery_manager = get_recovery_workflow_manager()
        statistics = recovery_manager.get_recovery_statistics()
        
        return statistics
        
    except Exception as e:
        logger.error(f"Failed to get recovery statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get recovery statistics: {str(e)}")


@router.get("/workflows", response_model=List[Dict[str, Any]])
async def get_recovery_workflows():
    """
    Get information about all registered recovery workflows.
    
    Returns details about available recovery workflows including their
    configurations, actions, and statistics.
    """
    try:
        recovery_manager = get_recovery_workflow_manager()
        
        workflows = []
        for workflow_id in recovery_manager._workflows.keys():
            workflow_details = recovery_manager.get_workflow_details(workflow_id)
            if workflow_details:
                workflows.append(workflow_details)
        
        return workflows
        
    except Exception as e:
        logger.error(f"Failed to get recovery workflows: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get recovery workflows: {str(e)}")


@router.get("/workflows/{workflow_id}", response_model=Dict[str, Any])
async def get_workflow_details(workflow_id: str = Path(..., description="Workflow ID")):
    """
    Get detailed information about a specific recovery workflow.
    
    Returns comprehensive details about a workflow including its configuration,
    actions, prerequisites, and performance statistics.
    """
    try:
        recovery_manager = get_recovery_workflow_manager()
        workflow_details = recovery_manager.get_workflow_details(workflow_id)
        
        if not workflow_details:
            raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
        
        return workflow_details
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workflow details: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get workflow details: {str(e)}")


# Recovery notification endpoints
@router.get("/notifications/active", response_model=List[Dict[str, Any]])
async def get_active_notifications(
    service_name: Optional[str] = Query(None, description="Filter by service name"),
    priority: Optional[str] = Query(None, description="Filter by priority (low, medium, high, critical, urgent)")
):
    """
    Get active recovery notifications that require acknowledgment.
    
    Returns notifications that are currently active and waiting for acknowledgment,
    optionally filtered by service name and priority level.
    """
    try:
        notification_service = get_recovery_notification_service()
        
        # Parse priority filter
        priority_filter = None
        if priority:
            priority_mapping = {
                "low": RecoveryNotificationPriority.LOW,
                "medium": RecoveryNotificationPriority.MEDIUM,
                "high": RecoveryNotificationPriority.HIGH,
                "critical": RecoveryNotificationPriority.CRITICAL,
                "urgent": RecoveryNotificationPriority.URGENT
            }
            priority_enum = priority_mapping.get(priority.lower())
            if priority_enum:
                priority_filter = [priority_enum]
        
        notifications = notification_service.get_active_notifications(
            service_name=service_name,
            priority_filter=priority_filter
        )
        
        return notifications
        
    except Exception as e:
        logger.error(f"Failed to get active notifications: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get active notifications: {str(e)}")


@router.get("/notifications/history", response_model=List[Dict[str, Any]])
async def get_notification_history(
    hours: int = Query(24, description="Number of hours to look back", ge=1, le=168),
    service_name: Optional[str] = Query(None, description="Filter by service name")
):
    """
    Get recovery notification history.
    
    Returns historical information about recovery notifications including
    acknowledgment status and delivery information.
    """
    try:
        notification_service = get_recovery_notification_service()
        history = notification_service.get_notification_history(hours=hours, service_name=service_name)
        
        return history
        
    except Exception as e:
        logger.error(f"Failed to get notification history: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get notification history: {str(e)}")


@router.post("/notifications/{notification_id}/acknowledge", response_model=Dict[str, Any])
async def acknowledge_notification(
    notification_id: str = Path(..., description="Notification ID"),
    request: AcknowledgeNotificationRequest = Body(...)
):
    """
    Acknowledge a recovery notification.
    
    Marks a recovery notification as acknowledged, which stops escalation
    and indicates that the notification has been seen and handled.
    """
    try:
        notification_service = get_recovery_notification_service()
        
        success = await notification_service.acknowledge_notification(
            notification_id=notification_id,
            acknowledged_by=request.acknowledged_by
        )
        
        if success:
            return {
                "success": True,
                "message": "Notification acknowledged successfully",
                "notification_id": notification_id,
                "acknowledged_by": request.acknowledged_by,
                "acknowledged_at": datetime.now().isoformat()
            }
        else:
            raise HTTPException(status_code=404, detail=f"Notification not found: {notification_id}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to acknowledge notification: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to acknowledge notification: {str(e)}")


@router.get("/notifications/statistics", response_model=Dict[str, Any])
async def get_notification_statistics():
    """
    Get recovery notification statistics.
    
    Returns comprehensive statistics about recovery notifications including
    delivery rates, acknowledgment rates, and escalation information.
    """
    try:
        notification_service = get_recovery_notification_service()
        statistics = notification_service.get_notification_statistics()
        
        return statistics
        
    except Exception as e:
        logger.error(f"Failed to get notification statistics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get notification statistics: {str(e)}")


# Integration and monitoring endpoints
@router.get("/integration/status", response_model=Dict[str, Any])
async def get_integration_status():
    """
    Get recovery integration status.
    
    Returns information about the recovery integration service including
    active triggers, cooldowns, and health monitoring integration.
    """
    try:
        integration_service = get_recovery_integration_service()
        status = integration_service.get_integration_status()
        
        return status
        
    except Exception as e:
        logger.error(f"Failed to get integration status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get integration status: {str(e)}")


@router.get("/metrics", response_model=Dict[str, Any])
async def get_recovery_metrics():
    """
    Get comprehensive recovery metrics.
    
    Returns combined metrics from recovery workflows, notifications,
    and integration services for monitoring and analysis.
    """
    try:
        integration_service = get_recovery_integration_service()
        metrics = integration_service.get_recovery_metrics()
        
        return metrics
        
    except Exception as e:
        logger.error(f"Failed to get recovery metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get recovery metrics: {str(e)}")


@router.post("/validate/{service_name}", response_model=Dict[str, Any])
async def validate_service_recovery(
    service_name: str = Path(..., description="Service name to validate"),
    attempt_id: str = Query(..., description="Recovery attempt ID")
):
    """
    Validate that service recovery was successful.
    
    Runs health checks and validation to confirm that a service has
    successfully recovered from a failure condition.
    """
    try:
        integration_service = get_recovery_integration_service()
        
        validation_result = await integration_service.validate_recovery_success(
            service_name=service_name,
            attempt_id=attempt_id
        )
        
        return {
            "success": validation_result,
            "service_name": service_name,
            "attempt_id": attempt_id,
            "validation_time": datetime.now().isoformat(),
            "message": f"Service {service_name} recovery {'validated successfully' if validation_result else 'validation failed'}"
        }
        
    except Exception as e:
        logger.error(f"Failed to validate service recovery: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to validate service recovery: {str(e)}")


# Health and status endpoints
@router.get("/health", response_model=Dict[str, Any])
async def get_recovery_system_health():
    """
    Get recovery system health status.
    
    Returns health information about all recovery system components
    including workflow manager, notification service, and integration.
    """
    try:
        recovery_manager = get_recovery_workflow_manager()
        notification_service = get_recovery_notification_service()
        integration_service = get_recovery_integration_service()
        
        # Get component status
        active_attempts = len(recovery_manager.get_active_attempts())
        active_notifications = len(notification_service.get_active_notifications())
        integration_status = integration_service.get_integration_status()
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "components": {
                "recovery_workflow_manager": {
                    "status": "active",
                    "active_attempts": active_attempts,
                    "registered_workflows": len(recovery_manager._workflows)
                },
                "recovery_notification_service": {
                    "status": "active",
                    "active_notifications": active_notifications,
                    "notification_rules": len(notification_service._notification_rules)
                },
                "recovery_integration_service": {
                    "status": "active" if integration_status["integration_active"] else "inactive",
                    "registered_triggers": integration_status["registered_triggers"],
                    "active_cooldowns": integration_status["active_cooldowns"]
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get recovery system health: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get recovery system health: {str(e)}")


# Utility endpoints
@router.post("/cleanup", response_model=Dict[str, Any])
async def cleanup_old_data(
    days: int = Query(30, description="Number of days of data to keep", ge=1, le=365)
):
    """
    Clean up old recovery data.
    
    Removes old recovery attempts, notifications, and related data
    to prevent storage bloat while preserving recent information.
    """
    try:
        notification_service = get_recovery_notification_service()
        
        # Clean up old notifications
        cleaned_notifications = notification_service.cleanup_old_notifications(days=days)
        
        return {
            "success": True,
            "message": f"Cleanup completed successfully",
            "cleaned_notifications": cleaned_notifications,
            "retention_days": days,
            "cleanup_time": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to cleanup old data: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cleanup old data: {str(e)}")


# Note: Error handlers are typically added at the app level, not router level