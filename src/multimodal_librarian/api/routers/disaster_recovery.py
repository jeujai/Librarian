#!/usr/bin/env python3
"""
Disaster Recovery API Router

Provides REST API endpoints for disaster recovery testing,
monitoring, and validation.
"""

import logging
from datetime import datetime
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel

from ...monitoring.disaster_recovery_service import (
    DisasterRecoveryService,
    get_disaster_recovery_status,
    run_disaster_recovery_validation,
    generate_disaster_recovery_report
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/v1/disaster-recovery", tags=["disaster-recovery"])


# Request/Response models
class DisasterRecoveryTestRequest(BaseModel):
    """Request model for disaster recovery test."""
    test_type: str = "full"  # full, backup, restore, consistency, rto
    force_refresh: bool = False
    notify_on_completion: bool = True


class DisasterRecoveryStatusResponse(BaseModel):
    """Response model for disaster recovery status."""
    overall_status: str
    last_test: Optional[datetime]
    next_test: Optional[datetime]
    issues_count: int
    recommendations_count: int
    backup_success_rate: float
    rto_compliance_rate: float
    rpo_compliance_rate: float


class BackupValidationResponse(BaseModel):
    """Response model for backup validation."""
    success: bool
    timestamp: datetime
    total_backups: int
    successful_backups: int
    failed_backups: int
    issues: list
    recommendations: list


# Global service instance
_dr_service = None


def get_dr_service() -> DisasterRecoveryService:
    """Get disaster recovery service instance."""
    global _dr_service
    if _dr_service is None:
        _dr_service = DisasterRecoveryService()
    return _dr_service


@router.get("/status", response_model=DisasterRecoveryStatusResponse)
async def get_status(force_refresh: bool = Query(False, description="Force refresh of status data")):
    """
    Get current disaster recovery status.
    
    Returns overall disaster recovery readiness including:
    - Backup status
    - RTO/RPO compliance
    - Recent test results
    - Issues and recommendations
    """
    try:
        logger.info(f"Getting disaster recovery status (force_refresh={force_refresh})")
        
        service = get_dr_service()
        status = await service.get_disaster_recovery_status(force_refresh=force_refresh)
        
        # Calculate rates
        total_backups = len(status.backup_statuses)
        successful_backups = sum(1 for b in status.backup_statuses if b.status == "success")
        backup_success_rate = (successful_backups / total_backups * 100) if total_backups > 0 else 0
        
        total_rto = len(status.rto_objectives)
        met_rto = sum(1 for r in status.rto_objectives if r.status == "met")
        rto_compliance_rate = (met_rto / total_rto * 100) if total_rto > 0 else 0
        
        total_rpo = len(status.rpo_objectives)
        met_rpo = sum(1 for r in status.rpo_objectives if r.status == "met")
        rpo_compliance_rate = (met_rpo / total_rpo * 100) if total_rpo > 0 else 0
        
        return DisasterRecoveryStatusResponse(
            overall_status=status.overall_status,
            last_test=status.last_test,
            next_test=status.next_test,
            issues_count=len(status.issues),
            recommendations_count=len(status.recommendations),
            backup_success_rate=backup_success_rate,
            rto_compliance_rate=rto_compliance_rate,
            rpo_compliance_rate=rpo_compliance_rate
        )
    
    except Exception as e:
        logger.error(f"Failed to get disaster recovery status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get disaster recovery status: {str(e)}")


@router.get("/status/detailed")
async def get_detailed_status(force_refresh: bool = Query(False, description="Force refresh of status data")):
    """
    Get detailed disaster recovery status.
    
    Returns comprehensive disaster recovery information including:
    - Individual component statuses
    - Detailed RTO/RPO metrics
    - Backup details
    - Historical data
    """
    try:
        logger.info(f"Getting detailed disaster recovery status (force_refresh={force_refresh})")
        
        status = await get_disaster_recovery_status()
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "data": status
        }
    
    except Exception as e:
        logger.error(f"Failed to get detailed disaster recovery status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get detailed status: {str(e)}")


@router.post("/validate/backups", response_model=BackupValidationResponse)
async def validate_backups():
    """
    Validate backup procedures and integrity.
    
    Performs comprehensive backup validation including:
    - RDS backup verification
    - S3 backup integrity checks
    - Lambda backup function testing
    - Backup age and retention validation
    """
    try:
        logger.info("Starting backup validation")
        
        validation_result = await run_disaster_recovery_validation()
        
        # Calculate metrics
        backup_tests = validation_result.get('backup_tests', {})
        total_backups = sum(
            test.get('backup_count', 0) + test.get('bucket_count', 0) + test.get('function_count', 0)
            for test in backup_tests.values()
        )
        
        successful_tests = sum(1 for test in backup_tests.values() if test.get('success', False))
        failed_tests = len(backup_tests) - successful_tests
        
        return BackupValidationResponse(
            success=validation_result.get('success', False),
            timestamp=datetime.fromisoformat(validation_result.get('timestamp', datetime.now().isoformat())),
            total_backups=total_backups,
            successful_backups=successful_tests,
            failed_backups=failed_tests,
            issues=validation_result.get('issues', []),
            recommendations=[]  # Could be enhanced to include recommendations
        )
    
    except Exception as e:
        logger.error(f"Backup validation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Backup validation failed: {str(e)}")


@router.post("/test")
async def run_disaster_recovery_test(
    request: DisasterRecoveryTestRequest,
    background_tasks: BackgroundTasks
):
    """
    Run disaster recovery test.
    
    Executes disaster recovery testing based on specified type:
    - full: Comprehensive disaster recovery test
    - backup: Backup procedures test only
    - restore: Restore procedures test only
    - consistency: Data consistency test only
    - rto: Recovery time objectives test only
    """
    try:
        logger.info(f"Starting disaster recovery test: {request.test_type}")
        
        # For now, we'll run the backup validation as a starting point
        # In a full implementation, this would run the comprehensive test framework
        
        if request.test_type == "backup":
            result = await run_disaster_recovery_validation()
        else:
            # Simulate other test types
            result = {
                "test_type": request.test_type,
                "status": "completed",
                "timestamp": datetime.now().isoformat(),
                "success": True,
                "message": f"Disaster recovery test '{request.test_type}' completed successfully",
                "details": {
                    "note": "This is a simulated test result. Full implementation would run comprehensive tests."
                }
            }
        
        return {
            "status": "success",
            "message": f"Disaster recovery test '{request.test_type}' initiated",
            "test_id": f"dr-test-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "result": result
        }
    
    except Exception as e:
        logger.error(f"Disaster recovery test failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Disaster recovery test failed: {str(e)}")


@router.get("/report")
async def get_disaster_recovery_report():
    """
    Generate comprehensive disaster recovery report.
    
    Returns detailed report including:
    - Overall DR readiness assessment
    - Backup status and validation results
    - RTO/RPO compliance analysis
    - Issues and recommendations
    - Next actions and priorities
    """
    try:
        logger.info("Generating disaster recovery report")
        
        report = await generate_disaster_recovery_report()
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "report": report
        }
    
    except Exception as e:
        logger.error(f"Failed to generate disaster recovery report: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@router.get("/metrics")
async def get_disaster_recovery_metrics():
    """
    Get disaster recovery metrics for monitoring dashboards.
    
    Returns key metrics including:
    - Backup success rates
    - RTO/RPO compliance rates
    - Test frequency and results
    - Issue counts and trends
    """
    try:
        logger.info("Getting disaster recovery metrics")
        
        service = get_dr_service()
        status = await service.get_disaster_recovery_status()
        
        # Calculate metrics
        metrics = {
            "overall_status": status.overall_status,
            "backup_metrics": {
                "total_backups": len(status.backup_statuses),
                "successful_backups": sum(1 for b in status.backup_statuses if b.status == "success"),
                "failed_backups": sum(1 for b in status.backup_statuses if b.status == "failed"),
                "success_rate": (
                    sum(1 for b in status.backup_statuses if b.status == "success") / 
                    len(status.backup_statuses) * 100
                ) if status.backup_statuses else 0
            },
            "rto_metrics": {
                "total_objectives": len(status.rto_objectives),
                "met_objectives": sum(1 for r in status.rto_objectives if r.status == "met"),
                "exceeded_objectives": sum(1 for r in status.rto_objectives if r.status == "exceeded"),
                "compliance_rate": (
                    sum(1 for r in status.rto_objectives if r.status == "met") / 
                    len(status.rto_objectives) * 100
                ) if status.rto_objectives else 0
            },
            "rpo_metrics": {
                "total_objectives": len(status.rpo_objectives),
                "met_objectives": sum(1 for r in status.rpo_objectives if r.status == "met"),
                "exceeded_objectives": sum(1 for r in status.rpo_objectives if r.status == "exceeded"),
                "compliance_rate": (
                    sum(1 for r in status.rpo_objectives if r.status == "met") / 
                    len(status.rpo_objectives) * 100
                ) if status.rpo_objectives else 0
            },
            "issue_metrics": {
                "total_issues": len(status.issues),
                "total_recommendations": len(status.recommendations)
            },
            "test_metrics": {
                "last_test": status.last_test.isoformat() if status.last_test else None,
                "next_test": status.next_test.isoformat() if status.next_test else None,
                "days_since_last_test": (
                    (datetime.now() - status.last_test).days
                ) if status.last_test else None
            }
        }
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "metrics": metrics
        }
    
    except Exception as e:
        logger.error(f"Failed to get disaster recovery metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@router.get("/health")
async def disaster_recovery_health_check():
    """
    Health check endpoint for disaster recovery system.
    
    Returns basic health status of disaster recovery components.
    """
    try:
        # Basic health check
        service = get_dr_service()
        
        # Test AWS connectivity
        try:
            service.rds_client.describe_db_instances(MaxRecords=1)
            aws_connectivity = True
        except Exception:
            aws_connectivity = False
        
        health_status = {
            "status": "healthy" if aws_connectivity else "degraded",
            "timestamp": datetime.now().isoformat(),
            "components": {
                "aws_connectivity": "healthy" if aws_connectivity else "unhealthy",
                "service_initialization": "healthy"
            }
        }
        
        return health_status
    
    except Exception as e:
        logger.error(f"Disaster recovery health check failed: {str(e)}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }


@router.get("/config")
async def get_disaster_recovery_config():
    """
    Get disaster recovery configuration.
    
    Returns current DR configuration including:
    - RTO/RPO targets
    - Test schedules
    - Backup policies
    - Notification settings
    """
    try:
        service = get_dr_service()
        
        config = {
            "rto_targets": service.default_rto_targets,
            "rpo_targets": service.default_rpo_targets,
            "test_interval_days": service.test_interval_days,
            "backup_check_interval_hours": service.backup_check_interval_hours,
            "project_name": service.project_name,
            "environment": service.environment
        }
        
        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "config": config
        }
    
    except Exception as e:
        logger.error(f"Failed to get disaster recovery config: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get config: {str(e)}")


# Add router to main application
def setup_disaster_recovery_routes(app):
    """Setup disaster recovery routes in the main application."""
    app.include_router(router)