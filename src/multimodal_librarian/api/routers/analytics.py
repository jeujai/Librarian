"""
Analytics API Router

This module provides REST API endpoints for document and usage analytics,
including statistics, content insights, similarity analysis, and usage patterns.
"""

import logging
from typing import Dict, Any
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import JSONResponse

from ...services.analytics_service import get_analytics_service, AnalyticsService

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/documents/statistics")
async def get_document_statistics(
    user_id: str = "default_user",
    analytics_service: AnalyticsService = Depends(get_analytics_service)
) -> Dict[str, Any]:
    """
    Get comprehensive document processing statistics.
    
    - **user_id**: User identifier for filtering documents
    
    Returns detailed statistics about document uploads, processing, and distribution.
    """
    try:
        # Add timeout protection at the API level
        import asyncio
        
        statistics = await asyncio.wait_for(
            analytics_service.get_document_statistics(user_id),
            timeout=10.0  # 10 second timeout
        )
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "data": statistics,
                "message": "Document statistics retrieved successfully"
            }
        )
        
    except asyncio.TimeoutError:
        logger.error(f"Timeout retrieving document statistics for user {user_id}")
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail="Request timeout while retrieving document statistics"
        )
    except Exception as e:
        logger.error(f"Error retrieving document statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve document statistics"
        )


@router.get("/content/insights")
async def get_content_insights(
    user_id: str = "default_user",
    analytics_service: AnalyticsService = Depends(get_analytics_service)
) -> Dict[str, Any]:
    """
    Get content summaries and key insights from documents.
    
    - **user_id**: User identifier for filtering documents
    
    Returns content analysis including keywords, categories, and quality metrics.
    """
    try:
        insights = await analytics_service.get_content_insights(user_id)
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "data": insights,
                "message": "Content insights retrieved successfully"
            }
        )
        
    except Exception as e:
        logger.error(f"Error retrieving content insights: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve content insights"
        )


@router.get("/similarity/analysis")
async def get_similarity_analysis(
    user_id: str = "default_user",
    analytics_service: AnalyticsService = Depends(get_analytics_service)
) -> Dict[str, Any]:
    """
    Get document similarity analysis and content clusters.
    
    - **user_id**: User identifier for filtering documents
    
    Returns similarity analysis including related documents and content groupings.
    """
    try:
        analysis = await analytics_service.get_similarity_analysis(user_id)
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "data": analysis,
                "message": "Similarity analysis retrieved successfully"
            }
        )
        
    except Exception as e:
        logger.error(f"Error retrieving similarity analysis: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve similarity analysis"
        )


@router.get("/usage/patterns")
async def get_usage_analytics(
    user_id: str = "default_user",
    analytics_service: AnalyticsService = Depends(get_analytics_service)
) -> Dict[str, Any]:
    """
    Get usage analytics for chat and document interactions.
    
    - **user_id**: User identifier for filtering usage data
    
    Returns usage patterns including activity metrics and engagement data.
    """
    try:
        analytics = await analytics_service.get_usage_analytics(user_id)
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "data": analytics,
                "message": "Usage analytics retrieved successfully"
            }
        )
        
    except Exception as e:
        logger.error(f"Error retrieving usage analytics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve usage analytics"
        )


@router.get("/dashboard/summary")
async def get_analytics_dashboard(
    user_id: str = "default_user",
    analytics_service: AnalyticsService = Depends(get_analytics_service)
) -> Dict[str, Any]:
    """
    Get comprehensive analytics dashboard data.
    
    - **user_id**: User identifier for filtering data
    
    Returns combined analytics data for dashboard display.
    """
    try:
        # Get all analytics data
        statistics = await analytics_service.get_document_statistics(user_id)
        insights = await analytics_service.get_content_insights(user_id)
        similarity = await analytics_service.get_similarity_analysis(user_id)
        usage = await analytics_service.get_usage_analytics(user_id)
        
        # Combine into dashboard summary
        dashboard_data = {
            "overview": {
                "total_documents": statistics["overview"]["total_documents"],
                "total_size_mb": statistics["overview"]["total_size_mb"],
                "recent_uploads": statistics["overview"]["recent_uploads_30d"],
                "chat_sessions": usage["usage_overview"]["total_chat_sessions"],
                "content_categories": len(insights["document_categories"]),
                "similar_pairs": similarity["similarity_overview"]["similar_pairs_found"]
            },
            "quick_stats": {
                "documents": statistics["overview"],
                "content_quality": insights["quality_metrics"],
                "user_engagement": usage["user_engagement"],
                "top_categories": insights["document_categories"]
            },
            "charts_data": {
                "upload_timeline": statistics["upload_timeline"],
                "file_types": statistics["file_type_distribution"],
                "daily_activity": usage["daily_activity"],
                "feature_usage": usage["feature_usage_percentage"]
            },
            "insights": {
                "top_keywords": insights["top_keywords"],
                "content_clusters": similarity["content_clusters"],
                "similar_documents": similarity["similar_documents"][:5]  # Top 5
            },
            "generated_at": datetime.utcnow().isoformat()
        }
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "success": True,
                "data": dashboard_data,
                "message": "Analytics dashboard data retrieved successfully"
            }
        )
        
    except Exception as e:
        logger.error(f"Error retrieving analytics dashboard: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve analytics dashboard data"
        )


@router.get("/health")
async def analytics_health():
    """
    Health check for analytics service.
    
    Returns analytics service health status and capabilities.
    """
    try:
        # Simple health check without external dependencies
        import time
        start_time = time.time()
        
        # Test basic service functionality
        from ...services.analytics_service import get_analytics_service
        service = get_analytics_service()
        
        # Quick validation that service is initialized
        if service is None:
            raise Exception("Analytics service not initialized")
        
        response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "healthy",
                "service": "analytics",
                "version": "1.0.0",
                "timestamp": datetime.utcnow().isoformat(),
                "response_time_ms": round(response_time, 2),
                "capabilities": {
                    "document_statistics": True,
                    "content_insights": True,
                    "similarity_analysis": True,
                    "usage_analytics": True,
                    "dashboard_summary": True
                },
                "features": {
                    "real_time_analytics": True,
                    "content_clustering": True,
                    "similarity_detection": True,
                    "usage_tracking": True,
                    "keyword_extraction": True,
                    "timeout_protection": True
                }
            }
        )
        
    except Exception as e:
        logger.error(f"Analytics health check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "service": "analytics",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )