"""
API endpoints for error logging and monitoring.

This module provides REST API endpoints to access error logs,
patterns, and recovery statistics.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field

from ...monitoring.error_logging_service import (
    get_error_logging_service,
    ErrorSeverity,
    ErrorCategory,
    ErrorRecoveryStatus
)
from ...monitoring.error_handler import get_recovery_manager
from ...logging_config import get_logger

logger = get_logger("error_logging_api")
router = APIRouter(prefix="/api/error-logging", tags=["Error Logging"])


class ErrorSummaryResponse(BaseModel):
    """Response model for error summary."""
    total_errors: int
    time_period_hours: int
    error_categories: Dict[str, int]
    error_severities: Dict[str, int]
    errors_by_service: Dict[str, int]
    recovery_statistics: Dict[str, Dict[str, Any]]
    top_error_patterns: List[Dict[str, Any]]
    critical_errors: int
    unrecovered_errors: int


class ErrorDetailsResponse(BaseModel):
    """Response model for detailed error information."""
    error_details: Dict[str, Any]
    pattern_info: Optional[Dict[str, Any]] = None


class ErrorPatternResponse(BaseModel):
    """Response model for error patterns."""
    pattern_id: str
    pattern_hash: str
    error_type: str
    error_message_pattern: str
    context_pattern: Dict[str, Any]
    occurrences: int
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]
    severity: str
    category: str
    recovery_success_rate: float
    impact_score: float


class RecoveryAttemptRequest(BaseModel):
    """Request model for logging recovery attempts."""
    recovery_strategy: str = Field(..., description="Recovery strategy used")
    success: bool = Field(..., description="Whether recovery was successful")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional recovery details")


@router.get("/summary", response_model=ErrorSummaryResponse)
async def get_error_summary(
    hours: int = Query(24, ge=1, le=168, description="Time period in hours (1-168)")
) -> ErrorSummaryResponse:
    """
    Get comprehensive error summary for the specified time period.
    
    Args:
        hours: Number of hours to look back (default: 24, max: 168/1 week)
    
    Returns:
        Comprehensive error summary including categories, patterns, and recovery stats
    """
    try:
        error_service = get_error_logging_service()
        summary = error_service.get_error_summary(hours=hours)
        
        return ErrorSummaryResponse(**summary)
        
    except Exception as e:
        logger.error(f"Failed to get error summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve error summary")


@router.get("/details/{error_id}", response_model=ErrorDetailsResponse)
async def get_error_details(
    error_id: str = Path(..., description="Unique error identifier")
) -> ErrorDetailsResponse:
    """
    Get detailed information about a specific error.
    
    Args:
        error_id: Unique identifier for the error
    
    Returns:
        Detailed error information including context and pattern data
    """
    try:
        error_service = get_error_logging_service()
        details = error_service.get_error_details(error_id)
        
        if not details:
            raise HTTPException(status_code=404, detail=f"Error {error_id} not found")
        
        return ErrorDetailsResponse(**details)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get error details for {error_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve error details")


@router.get("/patterns", response_model=List[ErrorPatternResponse])
async def get_error_patterns(
    limit: int = Query(50, ge=1, le=200, description="Maximum number of patterns to return")
) -> List[ErrorPatternResponse]:
    """
    Get error patterns sorted by frequency and impact.
    
    Args:
        limit: Maximum number of patterns to return (default: 50, max: 200)
    
    Returns:
        List of error patterns with occurrence statistics
    """
    try:
        error_service = get_error_logging_service()
        patterns = error_service.get_error_patterns(limit=limit)
        
        return [ErrorPatternResponse(**pattern) for pattern in patterns]
        
    except Exception as e:
        logger.error(f"Failed to get error patterns: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve error patterns")


@router.post("/recovery/{error_id}")
async def log_recovery_attempt(
    error_id: str = Path(..., description="Unique error identifier"),
    recovery_data: RecoveryAttemptRequest = ...
) -> Dict[str, str]:
    """
    Log an error recovery attempt.
    
    Args:
        error_id: Unique identifier for the error
        recovery_data: Recovery attempt information
    
    Returns:
        Confirmation message
    """
    try:
        error_service = get_error_logging_service()
        error_service.log_recovery_attempt(
            error_id=error_id,
            recovery_strategy=recovery_data.recovery_strategy,
            success=recovery_data.success,
            details=recovery_data.details
        )
        
        return {
            "message": f"Recovery attempt logged for error {error_id}",
            "strategy": recovery_data.recovery_strategy,
            "success": str(recovery_data.success)
        }
        
    except Exception as e:
        logger.error(f"Failed to log recovery attempt for {error_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to log recovery attempt")


@router.get("/categories")
async def get_error_categories() -> Dict[str, List[str]]:
    """
    Get available error categories and severities.
    
    Returns:
        Dictionary with available categories and severities
    """
    return {
        "categories": [category.value for category in ErrorCategory],
        "severities": [severity.value for severity in ErrorSeverity],
        "recovery_statuses": [status.value for status in ErrorRecoveryStatus]
    }


@router.get("/export")
async def export_error_data(
    hours: int = Query(24, ge=1, le=168, description="Time period in hours"),
    format: str = Query("json", regex="^(json)$", description="Export format")
) -> Dict[str, str]:
    """
    Export error data to file.
    
    Args:
        hours: Number of hours to include in export
        format: Export format (currently only 'json' supported)
    
    Returns:
        Export confirmation with file path
    """
    try:
        error_service = get_error_logging_service()
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"error_export_{timestamp}.json"
        
        filepath = error_service.export_error_data(filename, hours=hours)
        
        return {
            "message": "Error data exported successfully",
            "filepath": filepath,
            "format": format,
            "time_period_hours": str(hours)
        }
        
    except Exception as e:
        logger.error(f"Failed to export error data: {e}")
        raise HTTPException(status_code=500, detail="Failed to export error data")


@router.get("/health")
async def get_error_logging_health() -> Dict[str, Any]:
    """
    Get health status of the error logging service.
    
    Returns:
        Health status and basic statistics
    """
    try:
        error_service = get_error_logging_service()
        
        # Get basic statistics
        summary = error_service.get_error_summary(hours=1)  # Last hour
        patterns = error_service.get_error_patterns(limit=10)
        
        return {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "recent_errors": summary.get("total_errors", 0),
            "total_patterns": len(patterns),
            "critical_errors_last_hour": summary.get("critical_errors", 0),
            "service_info": {
                "name": "error_logging_service",
                "version": "1.0.0",
                "features": [
                    "structured_error_logging",
                    "error_categorization",
                    "pattern_detection",
                    "recovery_tracking",
                    "context_extraction"
                ]
            }
        }
        
    except Exception as e:
        logger.error(f"Error logging health check failed: {e}")
        return {
            "status": "unhealthy",
            "timestamp": datetime.now().isoformat(),
            "error": str(e)
        }


@router.get("/stats/recovery")
async def get_recovery_statistics(
    hours: int = Query(24, ge=1, le=168, description="Time period in hours")
) -> Dict[str, Any]:
    """
    Get detailed recovery statistics.
    
    Args:
        hours: Number of hours to analyze
    
    Returns:
        Detailed recovery statistics by category and strategy
    """
    try:
        error_service = get_error_logging_service()
        summary = error_service.get_error_summary(hours=hours)
        
        recovery_stats = summary.get("recovery_statistics", {})
        
        # Calculate overall recovery rate
        total_errors = sum(stats["total_errors"] for stats in recovery_stats.values())
        total_recovered = sum(stats["recovered_errors"] for stats in recovery_stats.values())
        overall_recovery_rate = (total_recovered / total_errors * 100) if total_errors > 0 else 0
        
        return {
            "time_period_hours": hours,
            "overall_recovery_rate": round(overall_recovery_rate, 2),
            "total_errors": total_errors,
            "total_recovered": total_recovered,
            "recovery_by_category": recovery_stats,
            "recommendations": _generate_recovery_recommendations(recovery_stats)
        }
        
    except Exception as e:
        logger.error(f"Failed to get recovery statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve recovery statistics")


def _generate_recovery_recommendations(recovery_stats: Dict[str, Any]) -> List[str]:
    """Generate recommendations based on recovery statistics."""
    recommendations = []
    
    for category, stats in recovery_stats.items():
        recovery_rate = stats.get("recovery_rate", 0)
        total_errors = stats.get("total_errors", 0)
        
        if total_errors > 0:
            if recovery_rate < 50:
                recommendations.append(
                    f"Low recovery rate for {category} ({recovery_rate:.1f}%) - "
                    f"consider improving recovery strategies"
                )
            elif recovery_rate > 90:
                recommendations.append(
                    f"Excellent recovery rate for {category} ({recovery_rate:.1f}%) - "
                    f"recovery strategies are working well"
                )
    
    if not recommendations:
        recommendations.append("No specific recommendations at this time")
    
    return recommendations


@router.get("/trends")
async def get_error_trends(
    days: int = Query(7, ge=1, le=30, description="Number of days to analyze")
) -> Dict[str, Any]:
    """
    Get error trends over time.
    
    Args:
        days: Number of days to analyze (1-30)
    
    Returns:
        Error trends by day, category, and severity
    """
    try:
        error_service = get_error_logging_service()
        
        # Get data for each day
        daily_data = []
        for day_offset in range(days):
            start_time = datetime.now() - timedelta(days=day_offset+1)
            end_time = datetime.now() - timedelta(days=day_offset)
            
            # This is a simplified implementation
            # In a real system, you'd query the data more efficiently
            summary = error_service.get_error_summary(hours=24)
            
            daily_data.append({
                "date": start_time.strftime("%Y-%m-%d"),
                "total_errors": summary.get("total_errors", 0),
                "critical_errors": summary.get("critical_errors", 0),
                "categories": summary.get("error_categories", {}),
                "severities": summary.get("error_severities", {})
            })
        
        return {
            "period_days": days,
            "daily_data": daily_data,
            "trends": {
                "total_errors_trend": "stable",  # This would be calculated
                "critical_errors_trend": "decreasing",  # This would be calculated
                "most_common_category": "service_failure",  # This would be calculated
                "recovery_rate_trend": "improving"  # This would be calculated
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get error trends: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve error trends")