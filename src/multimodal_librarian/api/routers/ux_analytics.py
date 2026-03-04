"""
User Experience Analytics API Router

This router provides REST API endpoints for accessing user experience analytics
during application startup phases. It exposes insights, reports, and real-time
monitoring data for UX optimization.

Endpoints:
- GET /ux-analytics/summary - Get executive summary of UX metrics
- GET /ux-analytics/comprehensive - Get comprehensive analysis report
- GET /ux-analytics/real-time - Get real-time UX insights
- GET /ux-analytics/insights - Get actionable insights
- GET /ux-analytics/recommendations - Get improvement recommendations
- GET /ux-analytics/export - Export analytics report in various formats
- GET /ux-analytics/health - Get UX health status
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse

from ...services.ux_analytics_service import (
    UserExperienceAnalyticsService, get_ux_analytics_service, initialize_ux_analytics_service
)
from ...logging.ux_logger import get_ux_logger

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/ux-analytics", tags=["User Experience Analytics"])


def get_analytics_service() -> UserExperienceAnalyticsService:
    """Get or initialize the UX analytics service."""
    service = get_ux_analytics_service()
    if not service:
        ux_logger = get_ux_logger()
        service = initialize_ux_analytics_service(ux_logger)
    return service


@router.get("/summary")
async def get_ux_summary(
    analytics_service: UserExperienceAnalyticsService = Depends(get_analytics_service)
) -> Dict[str, Any]:
    """
    Get executive summary of user experience metrics.
    
    Returns high-level KPIs and health indicators for quick assessment
    of startup user experience performance.
    """
    try:
        logger.info("Generating UX summary")
        
        analysis = await analytics_service.generate_comprehensive_analysis()
        
        if "error" in analysis:
            raise HTTPException(status_code=500, detail=analysis["error"])
        
        # Extract summary information
        summary = analysis.get("summary", {})
        
        # Add timestamp
        summary["generated_at"] = datetime.now().isoformat()
        summary["data_freshness"] = analysis.get("data_freshness", {})
        
        return JSONResponse(content=summary)
        
    except Exception as e:
        logger.error(f"Failed to generate UX summary: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {str(e)}")


@router.get("/comprehensive")
async def get_comprehensive_analysis(
    analytics_service: UserExperienceAnalyticsService = Depends(get_analytics_service)
) -> Dict[str, Any]:
    """
    Get comprehensive user experience analysis report.
    
    Returns detailed analysis including user journeys, phase analysis,
    behavior patterns, fallback effectiveness, and actionable insights.
    """
    try:
        logger.info("Generating comprehensive UX analysis")
        
        analysis = await analytics_service.generate_comprehensive_analysis()
        
        if "error" in analysis:
            raise HTTPException(status_code=500, detail=analysis["error"])
        
        return JSONResponse(content=analysis)
        
    except Exception as e:
        logger.error(f"Failed to generate comprehensive analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate analysis: {str(e)}")


@router.get("/real-time")
async def get_real_time_insights(
    analytics_service: UserExperienceAnalyticsService = Depends(get_analytics_service)
) -> Dict[str, Any]:
    """
    Get real-time user experience insights.
    
    Returns current UX health indicators, active issues, and key metrics
    for real-time monitoring dashboards.
    """
    try:
        logger.debug("Getting real-time UX insights")
        
        insights = await analytics_service.get_real_time_insights()
        
        if "error" in insights:
            raise HTTPException(status_code=500, detail=insights["error"])
        
        return JSONResponse(content=insights)
        
    except Exception as e:
        logger.error(f"Failed to get real-time insights: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get insights: {str(e)}")


@router.get("/insights")
async def get_actionable_insights(
    analytics_service: UserExperienceAnalyticsService = Depends(get_analytics_service),
    severity: Optional[str] = Query(None, description="Filter by severity: info, warning, critical"),
    insight_type: Optional[str] = Query(None, description="Filter by type: performance, behavior, satisfaction, abandonment, fallback, recommendation")
) -> Dict[str, Any]:
    """
    Get actionable insights from user experience analysis.
    
    Returns specific insights with recommendations for improving
    the startup user experience.
    """
    try:
        logger.info(f"Getting actionable insights (severity: {severity}, type: {insight_type})")
        
        analysis = await analytics_service.generate_comprehensive_analysis()
        
        if "error" in analysis:
            raise HTTPException(status_code=500, detail=analysis["error"])
        
        insights = analysis.get("insights", [])
        
        # Apply filters
        if severity:
            insights = [i for i in insights if i.get("severity") == severity.lower()]
        
        if insight_type:
            insights = [i for i in insights if i.get("insight_type") == insight_type.lower()]
        
        return JSONResponse(content={
            "insights": insights,
            "total_insights": len(insights),
            "filters_applied": {
                "severity": severity,
                "insight_type": insight_type
            },
            "generated_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Failed to get actionable insights: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get insights: {str(e)}")


@router.get("/recommendations")
async def get_recommendations(
    analytics_service: UserExperienceAnalyticsService = Depends(get_analytics_service),
    category: Optional[str] = Query(None, description="Filter by category: Performance, User Retention, Capability Management, User Experience"),
    priority: Optional[str] = Query(None, description="Filter by priority: Critical, High, Medium, Low")
) -> Dict[str, Any]:
    """
    Get improvement recommendations based on UX analysis.
    
    Returns actionable recommendations for optimizing the startup
    user experience, with implementation guidance.
    """
    try:
        logger.info(f"Getting UX recommendations (category: {category}, priority: {priority})")
        
        analysis = await analytics_service.generate_comprehensive_analysis()
        
        if "error" in analysis:
            raise HTTPException(status_code=500, detail=analysis["error"])
        
        recommendations = analysis.get("recommendations", [])
        
        # Apply filters
        if category:
            recommendations = [r for r in recommendations if r.get("category") == category]
        
        if priority:
            recommendations = [r for r in recommendations if r.get("priority") == priority]
        
        return JSONResponse(content={
            "recommendations": recommendations,
            "total_recommendations": len(recommendations),
            "filters_applied": {
                "category": category,
                "priority": priority
            },
            "generated_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Failed to get recommendations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get recommendations: {str(e)}")


@router.get("/export")
async def export_analytics_report(
    format_type: str = Query("json", description="Export format: json, summary"),
    analytics_service: UserExperienceAnalyticsService = Depends(get_analytics_service)
):
    """
    Export comprehensive analytics report in various formats.
    
    Supports JSON format for programmatic access and summary format
    for human-readable reports.
    """
    try:
        logger.info(f"Exporting analytics report in {format_type} format")
        
        if format_type not in ["json", "summary"]:
            raise HTTPException(status_code=400, detail="Unsupported format. Use 'json' or 'summary'")
        
        report = await analytics_service.export_analytics_report(format_type)
        
        if format_type == "json":
            return JSONResponse(content={"report": report, "format": format_type})
        else:
            return PlainTextResponse(content=report, media_type="text/plain")
        
    except Exception as e:
        logger.error(f"Failed to export analytics report: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export report: {str(e)}")


@router.get("/health")
async def get_ux_health_status(
    analytics_service: UserExperienceAnalyticsService = Depends(get_analytics_service)
) -> Dict[str, Any]:
    """
    Get current user experience health status.
    
    Returns a simple health check for UX monitoring systems,
    including overall health score and critical issues.
    """
    try:
        logger.debug("Getting UX health status")
        
        real_time_insights = await analytics_service.get_real_time_insights()
        
        if "error" in real_time_insights:
            # Return degraded status if analytics are unavailable
            return JSONResponse(content={
                "status": "degraded",
                "health_score": 0,
                "message": "UX analytics unavailable",
                "timestamp": datetime.now().isoformat()
            })
        
        health_score = real_time_insights.get("health_score", 0)
        health_status = real_time_insights.get("health_status", "unknown")
        active_issues = real_time_insights.get("active_issues", [])
        
        # Determine overall status
        if health_score >= 80 and not active_issues:
            status = "healthy"
        elif health_score >= 60:
            status = "warning"
        else:
            status = "critical"
        
        return JSONResponse(content={
            "status": status,
            "health_score": health_score,
            "health_status": health_status,
            "active_issues": active_issues,
            "total_requests": real_time_insights.get("key_metrics", {}).get("total_requests", 0),
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Failed to get UX health status: {e}")
        return JSONResponse(content={
            "status": "error",
            "health_score": 0,
            "message": f"Health check failed: {str(e)}",
            "timestamp": datetime.now().isoformat()
        })


@router.get("/user-journeys")
async def get_user_journey_analysis(
    analytics_service: UserExperienceAnalyticsService = Depends(get_analytics_service),
    limit: int = Query(10, description="Maximum number of journeys to return")
) -> Dict[str, Any]:
    """
    Get user journey analysis.
    
    Returns detailed analysis of individual user journeys through
    the startup process, including pain points and success factors.
    """
    try:
        logger.info(f"Getting user journey analysis (limit: {limit})")
        
        analysis = await analytics_service.generate_comprehensive_analysis()
        
        if "error" in analysis:
            raise HTTPException(status_code=500, detail=analysis["error"])
        
        user_journeys = analysis.get("user_journeys", {})
        
        # Limit journey details if requested
        if "journey_details" in user_journeys and limit > 0:
            user_journeys["journey_details"] = user_journeys["journey_details"][:limit]
        
        return JSONResponse(content={
            "user_journeys": user_journeys,
            "generated_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Failed to get user journey analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get journey analysis: {str(e)}")


@router.get("/phase-analysis")
async def get_startup_phase_analysis(
    analytics_service: UserExperienceAnalyticsService = Depends(get_analytics_service),
    phase: Optional[str] = Query(None, description="Filter by startup phase: minimal, essential, full")
) -> Dict[str, Any]:
    """
    Get startup phase analysis.
    
    Returns detailed analysis of user experience during different
    startup phases, including performance metrics and recommendations.
    """
    try:
        logger.info(f"Getting startup phase analysis (phase: {phase})")
        
        analysis = await analytics_service.generate_comprehensive_analysis()
        
        if "error" in analysis:
            raise HTTPException(status_code=500, detail=analysis["error"])
        
        phase_analysis = analysis.get("phase_analysis", {})
        
        # Filter by specific phase if requested
        if phase and "phase_details" in phase_analysis:
            phase_details = phase_analysis["phase_details"]
            if phase in phase_details:
                phase_analysis["phase_details"] = {phase: phase_details[phase]}
            else:
                phase_analysis["phase_details"] = {}
                phase_analysis["message"] = f"No data available for phase: {phase}"
        
        return JSONResponse(content={
            "phase_analysis": phase_analysis,
            "generated_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Failed to get phase analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get phase analysis: {str(e)}")


@router.get("/behavior-patterns")
async def get_behavior_pattern_analysis(
    analytics_service: UserExperienceAnalyticsService = Depends(get_analytics_service)
) -> Dict[str, Any]:
    """
    Get user behavior pattern analysis.
    
    Returns analysis of user behavior patterns during startup,
    including patience, engagement, and satisfaction metrics.
    """
    try:
        logger.info("Getting behavior pattern analysis")
        
        analysis = await analytics_service.generate_comprehensive_analysis()
        
        if "error" in analysis:
            raise HTTPException(status_code=500, detail=analysis["error"])
        
        behavior_patterns = analysis.get("behavior_patterns", {})
        
        return JSONResponse(content={
            "behavior_patterns": behavior_patterns,
            "generated_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Failed to get behavior pattern analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get behavior analysis: {str(e)}")


@router.get("/fallback-effectiveness")
async def get_fallback_effectiveness_analysis(
    analytics_service: UserExperienceAnalyticsService = Depends(get_analytics_service)
) -> Dict[str, Any]:
    """
    Get fallback response effectiveness analysis.
    
    Returns detailed analysis of how well fallback responses are
    working, including acceptance rates and improvement opportunities.
    """
    try:
        logger.info("Getting fallback effectiveness analysis")
        
        analysis = await analytics_service.generate_comprehensive_analysis()
        
        if "error" in analysis:
            raise HTTPException(status_code=500, detail=analysis["error"])
        
        fallback_effectiveness = analysis.get("fallback_effectiveness", {})
        
        return JSONResponse(content={
            "fallback_effectiveness": fallback_effectiveness,
            "generated_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Failed to get fallback effectiveness analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get fallback analysis: {str(e)}")


@router.get("/abandonment-analysis")
async def get_abandonment_analysis(
    analytics_service: UserExperienceAnalyticsService = Depends(get_analytics_service)
) -> Dict[str, Any]:
    """
    Get user abandonment analysis.
    
    Returns detailed analysis of user abandonment patterns,
    including reasons, timing, and prevention recommendations.
    """
    try:
        logger.info("Getting abandonment analysis")
        
        analysis = await analytics_service.generate_comprehensive_analysis()
        
        if "error" in analysis:
            raise HTTPException(status_code=500, detail=analysis["error"])
        
        abandonment_analysis = analysis.get("abandonment_analysis", {})
        
        return JSONResponse(content={
            "abandonment_analysis": abandonment_analysis,
            "generated_at": datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error(f"Failed to get abandonment analysis: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get abandonment analysis: {str(e)}")


# Health check endpoint for the analytics service itself
@router.get("/service-health")
async def get_service_health() -> Dict[str, Any]:
    """
    Get health status of the UX analytics service itself.
    
    Returns information about the service availability and dependencies.
    """
    try:
        # Check if UX logger is available
        ux_logger = get_ux_logger()
        ux_logger_status = "available" if ux_logger else "unavailable"
        
        # Check if analytics service is available
        analytics_service = get_ux_analytics_service()
        analytics_service_status = "available" if analytics_service else "unavailable"
        
        # Overall service status
        if ux_logger and analytics_service:
            service_status = "healthy"
        elif analytics_service:
            service_status = "degraded"
        else:
            service_status = "unavailable"
        
        return JSONResponse(content={
            "service_status": service_status,
            "dependencies": {
                "ux_logger": ux_logger_status,
                "analytics_service": analytics_service_status
            },
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0"
        })
        
    except Exception as e:
        logger.error(f"Service health check failed: {e}")
        return JSONResponse(content={
            "service_status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        })