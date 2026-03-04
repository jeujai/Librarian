"""
Query Analysis API Router

This module provides REST API endpoints for database query analysis and monitoring.
It exposes the functionality of the DatabaseQueryLogger through HTTP endpoints
for real-time monitoring and analysis of database query performance.

Features:
- Real-time query performance statistics
- Slow query analysis and recommendations
- Query pattern analysis
- Error analysis and troubleshooting
- Performance trend monitoring
- Export capabilities for analysis reports

Example Usage:
    GET /api/query-analysis/stats - Get overall query statistics
    GET /api/query-analysis/slow-queries - Get slow query analysis
    GET /api/query-analysis/patterns - Get query pattern analysis
    POST /api/query-analysis/export - Export analysis report
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from fastapi import APIRouter, HTTPException, Query, BackgroundTasks, Depends
from pydantic import BaseModel, Field

from ...logging.database_query_logger import (
    get_database_query_logger,
    DatabaseQueryLogger,
    QueryAnalysisReport,
    QueryLogEntry,
    QueryPattern,
    QueryLogLevel
)
from ...logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/query-analysis", tags=["Query Analysis"])


# Pydantic models for API responses

class QueryStatsResponse(BaseModel):
    """Response model for query statistics."""
    total_queries: int
    queries_by_database: Dict[str, int]
    queries_by_type: Dict[str, int]
    avg_execution_time_ms: float
    median_execution_time_ms: float
    p95_execution_time_ms: float
    p99_execution_time_ms: float
    slow_query_count: int
    slow_query_percentage: float
    error_count: int
    error_rate: float
    analysis_period_hours: float


class SlowQueryInfo(BaseModel):
    """Information about a slow query."""
    query_id: str
    database_type: str
    query_type: str
    execution_time_ms: float
    query_text: str = Field(..., max_length=500)  # Truncated for API response
    timestamp: datetime
    optimization_suggestions: List[str]
    complexity_score: float
    result_count: Optional[int] = None
    error_message: Optional[str] = None


class QueryPatternInfo(BaseModel):
    """Information about a query pattern."""
    pattern_hash: str
    pattern_template: str = Field(..., max_length=500)  # Truncated for API response
    query_count: int
    avg_execution_time_ms: float
    min_execution_time_ms: float
    max_execution_time_ms: float
    error_count: int
    last_seen: datetime
    databases: List[str]
    optimization_opportunities: List[str]


class ErrorAnalysisResponse(BaseModel):
    """Response model for error analysis."""
    total_errors: int
    error_rate: float
    common_errors: Dict[str, int]
    recent_errors: List[SlowQueryInfo]


class PerformanceInsight(BaseModel):
    """Performance insight or recommendation."""
    category: str
    severity: str  # low, medium, high, critical
    title: str
    description: str
    recommendation: str
    affected_queries: int
    potential_impact: str


class QueryAnalysisResponse(BaseModel):
    """Complete query analysis response."""
    summary: QueryStatsResponse
    slow_queries: List[SlowQueryInfo]
    query_patterns: List[QueryPatternInfo]
    error_analysis: ErrorAnalysisResponse
    performance_insights: List[PerformanceInsight]
    optimization_recommendations: List[str]
    resource_usage: Dict[str, float]


class ExportRequest(BaseModel):
    """Request model for exporting analysis reports."""
    database_type: Optional[str] = None
    time_window_hours: Optional[int] = Field(None, ge=1, le=168)  # Max 1 week
    include_query_details: bool = True
    include_patterns: bool = True
    format: str = Field("json", pattern="^(json|csv)$")


class LoggingConfigRequest(BaseModel):
    """Request model for updating logging configuration."""
    log_level: str = Field(..., pattern="^(none|error|slow|all|debug)$")
    slow_query_threshold_ms: Optional[float] = Field(None, ge=0)
    enable_pattern_analysis: Optional[bool] = None
    enable_optimization_suggestions: Optional[bool] = None


# Dependency to get query logger
async def get_query_logger() -> DatabaseQueryLogger:
    """Get the database query logger instance."""
    return get_database_query_logger()


@router.get("/stats", response_model=QueryStatsResponse)
async def get_query_statistics(
    database_type: Optional[str] = Query(None, description="Filter by database type"),
    time_window_hours: int = Query(24, ge=1, le=168, description="Analysis time window in hours"),
    query_logger: DatabaseQueryLogger = Depends(get_query_logger)
):
    """
    Get comprehensive query performance statistics.
    
    Returns aggregated statistics for database queries including execution times,
    error rates, and performance metrics over the specified time window.
    """
    try:
        analysis = await query_logger.get_query_analysis(
            database_type=database_type,
            time_window_hours=time_window_hours
        )
        
        return QueryStatsResponse(
            total_queries=analysis.total_queries,
            queries_by_database={k.value if hasattr(k, 'value') else str(k): v 
                               for k, v in analysis.queries_by_database.items()},
            queries_by_type={k.value if hasattr(k, 'value') else str(k): v 
                           for k, v in analysis.queries_by_type.items()},
            avg_execution_time_ms=analysis.avg_execution_time_ms,
            median_execution_time_ms=analysis.median_execution_time_ms,
            p95_execution_time_ms=analysis.p95_execution_time_ms,
            p99_execution_time_ms=analysis.p99_execution_time_ms,
            slow_query_count=analysis.slow_query_count,
            slow_query_percentage=analysis.slow_query_percentage,
            error_count=analysis.error_count,
            error_rate=analysis.error_rate,
            analysis_period_hours=analysis.analysis_period.total_seconds() / 3600
        )
        
    except Exception as e:
        logger.error(f"Error getting query statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve query statistics")


@router.get("/slow-queries", response_model=List[SlowQueryInfo])
async def get_slow_queries(
    database_type: Optional[str] = Query(None, description="Filter by database type"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of queries to return"),
    time_window_hours: int = Query(24, ge=1, le=168, description="Analysis time window in hours"),
    query_logger: DatabaseQueryLogger = Depends(get_query_logger)
):
    """
    Get slow query analysis with optimization recommendations.
    
    Returns the slowest queries within the specified time window along with
    performance metrics and optimization suggestions.
    """
    try:
        analysis = await query_logger.get_query_analysis(
            database_type=database_type,
            time_window_hours=time_window_hours
        )
        
        slow_queries = []
        for query in analysis.slow_queries[:limit]:
            slow_queries.append(SlowQueryInfo(
                query_id=query.query_id,
                database_type=query.database_type.value,
                query_type=query.query_type.value,
                execution_time_ms=query.execution_time_ms,
                query_text=query.query_text[:500],  # Truncate for API
                timestamp=query.timestamp,
                optimization_suggestions=query.optimization_suggestions,
                complexity_score=query.complexity_score,
                result_count=query.result_count,
                error_message=query.error_message
            ))
        
        return slow_queries
        
    except Exception as e:
        logger.error(f"Error getting slow queries: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve slow queries")


@router.get("/patterns", response_model=List[QueryPatternInfo])
async def get_query_patterns(
    database_type: Optional[str] = Query(None, description="Filter by database type"),
    sort_by: str = Query("frequency", pattern="^(frequency|performance|errors)$", 
                        description="Sort patterns by frequency, performance, or errors"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of patterns to return"),
    query_logger: DatabaseQueryLogger = Depends(get_query_logger)
):
    """
    Get query pattern analysis for optimization opportunities.
    
    Returns identified query patterns with execution statistics and optimization
    opportunities. Patterns help identify frequently executed queries that could
    benefit from optimization.
    """
    try:
        analysis = await query_logger.get_query_analysis(database_type=database_type)
        
        # Sort patterns based on request
        if sort_by == "frequency":
            patterns = analysis.most_frequent_patterns
        elif sort_by == "performance":
            patterns = analysis.slowest_patterns
        else:  # errors
            patterns = sorted(analysis.query_patterns, 
                            key=lambda p: p.error_count, reverse=True)
        
        pattern_info = []
        for pattern in patterns[:limit]:
            pattern_info.append(QueryPatternInfo(
                pattern_hash=pattern.pattern_hash,
                pattern_template=pattern.pattern_template[:500],  # Truncate for API
                query_count=pattern.query_count,
                avg_execution_time_ms=pattern.avg_execution_time_ms,
                min_execution_time_ms=pattern.min_execution_time_ms,
                max_execution_time_ms=pattern.max_execution_time_ms,
                error_count=pattern.error_count,
                last_seen=pattern.last_seen,
                databases=[db.value for db in pattern.databases],
                optimization_opportunities=pattern.optimization_opportunities
            ))
        
        return pattern_info
        
    except Exception as e:
        logger.error(f"Error getting query patterns: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve query patterns")


@router.get("/errors", response_model=ErrorAnalysisResponse)
async def get_error_analysis(
    database_type: Optional[str] = Query(None, description="Filter by database type"),
    time_window_hours: int = Query(24, ge=1, le=168, description="Analysis time window in hours"),
    query_logger: DatabaseQueryLogger = Depends(get_query_logger)
):
    """
    Get database query error analysis.
    
    Returns analysis of query errors including common error types, error rates,
    and recent error examples for troubleshooting.
    """
    try:
        analysis = await query_logger.get_query_analysis(
            database_type=database_type,
            time_window_hours=time_window_hours
        )
        
        recent_errors = []
        for query in analysis.error_queries[:10]:  # Limit to 10 recent errors
            recent_errors.append(SlowQueryInfo(
                query_id=query.query_id,
                database_type=query.database_type.value,
                query_type=query.query_type.value,
                execution_time_ms=query.execution_time_ms,
                query_text=query.query_text[:500],  # Truncate for API
                timestamp=query.timestamp,
                optimization_suggestions=query.optimization_suggestions,
                complexity_score=query.complexity_score,
                result_count=query.result_count,
                error_message=query.error_message
            ))
        
        return ErrorAnalysisResponse(
            total_errors=analysis.error_count,
            error_rate=analysis.error_rate,
            common_errors=analysis.common_errors,
            recent_errors=recent_errors
        )
        
    except Exception as e:
        logger.error(f"Error getting error analysis: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve error analysis")


@router.get("/analysis", response_model=QueryAnalysisResponse)
async def get_comprehensive_analysis(
    database_type: Optional[str] = Query(None, description="Filter by database type"),
    time_window_hours: int = Query(24, ge=1, le=168, description="Analysis time window in hours"),
    query_logger: DatabaseQueryLogger = Depends(get_query_logger)
):
    """
    Get comprehensive query analysis report.
    
    Returns a complete analysis including statistics, slow queries, patterns,
    errors, and performance insights in a single response.
    """
    try:
        analysis = await query_logger.get_query_analysis(
            database_type=database_type,
            time_window_hours=time_window_hours
        )
        
        # Build summary
        summary = QueryStatsResponse(
            total_queries=analysis.total_queries,
            queries_by_database={k.value if hasattr(k, 'value') else str(k): v 
                               for k, v in analysis.queries_by_database.items()},
            queries_by_type={k.value if hasattr(k, 'value') else str(k): v 
                           for k, v in analysis.queries_by_type.items()},
            avg_execution_time_ms=analysis.avg_execution_time_ms,
            median_execution_time_ms=analysis.median_execution_time_ms,
            p95_execution_time_ms=analysis.p95_execution_time_ms,
            p99_execution_time_ms=analysis.p99_execution_time_ms,
            slow_query_count=analysis.slow_query_count,
            slow_query_percentage=analysis.slow_query_percentage,
            error_count=analysis.error_count,
            error_rate=analysis.error_rate,
            analysis_period_hours=analysis.analysis_period.total_seconds() / 3600
        )
        
        # Build slow queries list
        slow_queries = []
        for query in analysis.slow_queries[:10]:
            slow_queries.append(SlowQueryInfo(
                query_id=query.query_id,
                database_type=query.database_type.value,
                query_type=query.query_type.value,
                execution_time_ms=query.execution_time_ms,
                query_text=query.query_text[:500],
                timestamp=query.timestamp,
                optimization_suggestions=query.optimization_suggestions,
                complexity_score=query.complexity_score,
                result_count=query.result_count,
                error_message=query.error_message
            ))
        
        # Build patterns list
        query_patterns = []
        for pattern in analysis.most_frequent_patterns[:10]:
            query_patterns.append(QueryPatternInfo(
                pattern_hash=pattern.pattern_hash,
                pattern_template=pattern.pattern_template[:500],
                query_count=pattern.query_count,
                avg_execution_time_ms=pattern.avg_execution_time_ms,
                min_execution_time_ms=pattern.min_execution_time_ms,
                max_execution_time_ms=pattern.max_execution_time_ms,
                error_count=pattern.error_count,
                last_seen=pattern.last_seen,
                databases=[db.value for db in pattern.databases],
                optimization_opportunities=pattern.optimization_opportunities
            ))
        
        # Build error analysis
        recent_errors = []
        for query in analysis.error_queries[:5]:
            recent_errors.append(SlowQueryInfo(
                query_id=query.query_id,
                database_type=query.database_type.value,
                query_type=query.query_type.value,
                execution_time_ms=query.execution_time_ms,
                query_text=query.query_text[:500],
                timestamp=query.timestamp,
                optimization_suggestions=query.optimization_suggestions,
                complexity_score=query.complexity_score,
                result_count=query.result_count,
                error_message=query.error_message
            ))
        
        error_analysis = ErrorAnalysisResponse(
            total_errors=analysis.error_count,
            error_rate=analysis.error_rate,
            common_errors=analysis.common_errors,
            recent_errors=recent_errors
        )
        
        # Generate performance insights
        performance_insights = []
        
        # Slow query insights
        if analysis.slow_query_percentage > 15:
            performance_insights.append(PerformanceInsight(
                category="performance",
                severity="high",
                title="High Slow Query Rate",
                description=f"{analysis.slow_query_percentage:.1f}% of queries are slow",
                recommendation="Review and optimize slow queries, consider adding indexes",
                affected_queries=analysis.slow_query_count,
                potential_impact="Significant performance improvement possible"
            ))
        elif analysis.slow_query_percentage > 5:
            performance_insights.append(PerformanceInsight(
                category="performance",
                severity="medium",
                title="Moderate Slow Query Rate",
                description=f"{analysis.slow_query_percentage:.1f}% of queries are slow",
                recommendation="Monitor slow queries and optimize when possible",
                affected_queries=analysis.slow_query_count,
                potential_impact="Moderate performance improvement possible"
            ))
        
        # Error rate insights
        if analysis.error_rate > 5:
            performance_insights.append(PerformanceInsight(
                category="reliability",
                severity="high",
                title="High Error Rate",
                description=f"{analysis.error_rate:.1f}% of queries are failing",
                recommendation="Investigate and fix query errors",
                affected_queries=analysis.error_count,
                potential_impact="Improved application reliability"
            ))
        
        # Pattern insights
        if analysis.most_frequent_patterns:
            top_pattern = analysis.most_frequent_patterns[0]
            if top_pattern.avg_execution_time_ms > 500:
                performance_insights.append(PerformanceInsight(
                    category="optimization",
                    severity="medium",
                    title="Frequent Slow Pattern",
                    description=f"Most frequent query pattern is slow ({top_pattern.avg_execution_time_ms:.1f}ms avg)",
                    recommendation="Optimize the most frequently executed query pattern",
                    affected_queries=top_pattern.query_count,
                    potential_impact="High impact due to frequency"
                ))
        
        # Resource usage
        resource_usage = {
            "avg_cpu_usage": analysis.avg_cpu_usage,
            "peak_cpu_usage": analysis.peak_cpu_usage,
            "avg_memory_usage_mb": analysis.avg_memory_usage_mb,
            "peak_memory_usage_mb": analysis.peak_memory_usage_mb
        }
        
        return QueryAnalysisResponse(
            summary=summary,
            slow_queries=slow_queries,
            query_patterns=query_patterns,
            error_analysis=error_analysis,
            performance_insights=performance_insights,
            optimization_recommendations=analysis.optimization_recommendations,
            resource_usage=resource_usage
        )
        
    except Exception as e:
        logger.error(f"Error getting comprehensive analysis: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve comprehensive analysis")


@router.post("/export")
async def export_analysis_report(
    request: ExportRequest,
    background_tasks: BackgroundTasks,
    query_logger: DatabaseQueryLogger = Depends(get_query_logger)
):
    """
    Export query analysis report to file.
    
    Generates a comprehensive analysis report and exports it to the specified format.
    The export is processed in the background and the file path is returned.
    """
    try:
        # Generate timestamp for filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"query_analysis_report_{timestamp}.{request.format}"
        filepath = f"./logs/reports/{filename}"
        
        # Schedule background export
        background_tasks.add_task(
            _export_report_background,
            query_logger,
            filepath,
            request.database_type,
            request.time_window_hours
        )
        
        return {
            "message": "Export started",
            "filename": filename,
            "filepath": filepath,
            "format": request.format,
            "estimated_completion": "1-2 minutes"
        }
        
    except Exception as e:
        logger.error(f"Error starting export: {e}")
        raise HTTPException(status_code=500, detail="Failed to start export")


@router.get("/config")
async def get_logging_config(
    query_logger: DatabaseQueryLogger = Depends(get_query_logger)
):
    """
    Get current query logging configuration.
    
    Returns the current configuration settings for query logging including
    log levels, thresholds, and feature flags.
    """
    try:
        return {
            "log_level": query_logger.log_level.value,
            "slow_query_threshold_ms": query_logger.slow_query_threshold_ms,
            "max_log_entries": query_logger.max_log_entries,
            "analysis_window_hours": query_logger.analysis_window.total_seconds() / 3600,
            "enable_pattern_analysis": query_logger.enable_pattern_analysis,
            "enable_optimization_suggestions": query_logger.enable_optimization_suggestions,
            "is_active": query_logger.is_active,
            "total_queries_logged": len(query_logger.query_logs),
            "patterns_identified": len(query_logger.query_patterns)
        }
        
    except Exception as e:
        logger.error(f"Error getting logging config: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve logging configuration")


@router.put("/config")
async def update_logging_config(
    request: LoggingConfigRequest,
    query_logger: DatabaseQueryLogger = Depends(get_query_logger)
):
    """
    Update query logging configuration.
    
    Updates the configuration settings for query logging. Changes take effect
    immediately for new queries.
    """
    try:
        # Update log level
        from ...logging.database_query_logger import QueryLogLevel
        query_logger.log_level = QueryLogLevel(request.log_level.upper())
        
        # Update threshold if provided
        if request.slow_query_threshold_ms is not None:
            query_logger.slow_query_threshold_ms = request.slow_query_threshold_ms
        
        # Update feature flags if provided
        if request.enable_pattern_analysis is not None:
            query_logger.enable_pattern_analysis = request.enable_pattern_analysis
        
        if request.enable_optimization_suggestions is not None:
            query_logger.enable_optimization_suggestions = request.enable_optimization_suggestions
        
        logger.info(f"Query logging configuration updated: {request.dict()}")
        
        return {
            "message": "Configuration updated successfully",
            "new_config": {
                "log_level": query_logger.log_level.value,
                "slow_query_threshold_ms": query_logger.slow_query_threshold_ms,
                "enable_pattern_analysis": query_logger.enable_pattern_analysis,
                "enable_optimization_suggestions": query_logger.enable_optimization_suggestions
            }
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid configuration value: {e}")
    except Exception as e:
        logger.error(f"Error updating logging config: {e}")
        raise HTTPException(status_code=500, detail="Failed to update logging configuration")


@router.post("/clear-logs")
async def clear_query_logs(
    confirm: bool = Query(False, description="Confirmation flag to clear logs"),
    query_logger: DatabaseQueryLogger = Depends(get_query_logger)
):
    """
    Clear all stored query logs.
    
    Removes all stored query logs and patterns. This action cannot be undone.
    Requires explicit confirmation.
    """
    if not confirm:
        raise HTTPException(
            status_code=400, 
            detail="Confirmation required. Set confirm=true to clear logs."
        )
    
    try:
        # Clear logs
        logs_cleared = len(query_logger.query_logs)
        patterns_cleared = len(query_logger.query_patterns)
        
        query_logger.query_logs.clear()
        for db_logs in query_logger.query_logs_by_database.values():
            db_logs.clear()
        
        # Clear patterns
        async with query_logger.pattern_analysis_lock:
            query_logger.query_patterns.clear()
        
        logger.warning(f"Query logs cleared: {logs_cleared} logs, {patterns_cleared} patterns")
        
        return {
            "message": "Query logs cleared successfully",
            "logs_cleared": logs_cleared,
            "patterns_cleared": patterns_cleared
        }
        
    except Exception as e:
        logger.error(f"Error clearing query logs: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear query logs")


async def _export_report_background(
    query_logger: DatabaseQueryLogger,
    filepath: str,
    database_type: Optional[str],
    time_window_hours: Optional[int]
):
    """Background task to export analysis report."""
    try:
        await query_logger.export_analysis_report(filepath)
        logger.info(f"Query analysis report exported to {filepath}")
    except Exception as e:
        logger.error(f"Error exporting report to {filepath}: {e}")


# Health check endpoint
@router.get("/health")
async def query_analysis_health(
    query_logger: DatabaseQueryLogger = Depends(get_query_logger)
):
    """
    Health check for query analysis service.
    
    Returns the health status of the query logging and analysis service.
    """
    try:
        return {
            "status": "healthy" if query_logger.is_active else "inactive",
            "is_active": query_logger.is_active,
            "total_queries_logged": len(query_logger.query_logs),
            "patterns_identified": len(query_logger.query_patterns),
            "log_level": query_logger.log_level.value,
            "slow_query_threshold_ms": query_logger.slow_query_threshold_ms
        }
        
    except Exception as e:
        logger.error(f"Error in query analysis health check: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }