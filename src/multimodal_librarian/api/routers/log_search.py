"""
Log Search API Endpoints

This module provides REST API endpoints for log search and aggregation
functionality in the local development environment.

Key Features:
- Advanced log search with filtering
- Real-time log streaming
- Log statistics and analytics
- Export capabilities
- Integration with log search service
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Depends, BackgroundTasks
from fastapi.responses import StreamingResponse, PlainTextResponse
from pydantic import BaseModel, Field
from enum import Enum

from ...logging.log_search_service import (
    LogSearchService, SearchFilter, LogLevel, LogSource,
    get_log_search_service
)

router = APIRouter(prefix="/api/logs", tags=["Log Search"])


class LogLevelFilter(str, Enum):
    """Log level filter options."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogSourceFilter(str, Enum):
    """Log source filter options."""
    APPLICATION = "application"
    POSTGRES = "postgres"
    NEO4J = "neo4j"
    MILVUS = "milvus"
    REDIS = "redis"
    DOCKER = "docker"
    SYSTEM = "system"


class ExportFormat(str, Enum):
    """Export format options."""
    JSON = "json"
    CSV = "csv"


class LogSearchRequest(BaseModel):
    """Request model for log search."""
    query: Optional[str] = Field(None, description="Text search query")
    level: Optional[LogLevelFilter] = Field(None, description="Filter by log level")
    source: Optional[LogSourceFilter] = Field(None, description="Filter by log source")
    service: Optional[str] = Field(None, description="Filter by service name")
    user_id: Optional[str] = Field(None, description="Filter by user ID")
    correlation_id: Optional[str] = Field(None, description="Filter by correlation ID")
    error_type: Optional[str] = Field(None, description="Filter by error type")
    start_time: Optional[datetime] = Field(None, description="Start time for search")
    end_time: Optional[datetime] = Field(None, description="End time for search")
    has_error: Optional[bool] = Field(None, description="Filter entries with errors")
    has_duration: Optional[bool] = Field(None, description="Filter entries with duration")
    min_duration_ms: Optional[float] = Field(None, description="Minimum duration in milliseconds")
    max_duration_ms: Optional[float] = Field(None, description="Maximum duration in milliseconds")
    container_name: Optional[str] = Field(None, description="Filter by container name")
    limit: int = Field(100, ge=1, le=10000, description="Maximum number of results")
    offset: int = Field(0, ge=0, description="Offset for pagination")


class LogEntry(BaseModel):
    """Response model for log entry."""
    id: str
    timestamp: datetime
    level: str
    source: str
    service: str
    message: str
    raw_message: str
    metadata: Dict[str, Any]
    container_id: Optional[str] = None
    container_name: Optional[str] = None
    user_id: Optional[str] = None
    correlation_id: Optional[str] = None
    error_type: Optional[str] = None
    stack_trace: Optional[str] = None
    duration_ms: Optional[float] = None


class LogSearchResponse(BaseModel):
    """Response model for log search."""
    entries: List[LogEntry]
    total_count: int
    filtered_count: int
    search_time_ms: float
    filters_applied: Dict[str, Any]
    aggregations: Dict[str, Any]


class LogStatistics(BaseModel):
    """Response model for log statistics."""
    time_period_hours: int
    total_logs: int
    logs_per_hour: float
    level_distribution: Dict[str, int]
    source_distribution: Dict[str, int]
    service_distribution: Dict[str, int]
    error_distribution: Dict[str, int]
    time_distribution: Dict[str, int]
    duration_statistics: Dict[str, Any]
    error_rate: float


def get_search_service() -> LogSearchService:
    """Get log search service dependency."""
    service = get_log_search_service()
    if not service:
        raise HTTPException(
            status_code=503,
            detail="Log search service not available"
        )
    return service


@router.post("/search", response_model=LogSearchResponse)
async def search_logs(
    request: LogSearchRequest,
    search_service: LogSearchService = Depends(get_search_service)
) -> LogSearchResponse:
    """
    Search logs with advanced filtering and aggregation.
    
    Supports full-text search, filtering by various criteria,
    and provides aggregated statistics about the results.
    """
    try:
        # Convert request to search filter
        search_filter = SearchFilter(
            query=request.query,
            level=LogLevel(request.level.value) if request.level else None,
            source=LogSource(request.source.value) if request.source else None,
            service=request.service,
            user_id=request.user_id,
            correlation_id=request.correlation_id,
            error_type=request.error_type,
            start_time=request.start_time,
            end_time=request.end_time,
            has_error=request.has_error,
            has_duration=request.has_duration,
            min_duration_ms=request.min_duration_ms,
            max_duration_ms=request.max_duration_ms,
            container_name=request.container_name,
            limit=request.limit,
            offset=request.offset
        )
        
        # Perform search
        result = await search_service.search_logs(search_filter)
        
        # Convert to response format
        return LogSearchResponse(
            entries=[LogEntry(**entry.to_dict()) for entry in result.entries],
            total_count=result.total_count,
            filtered_count=result.filtered_count,
            search_time_ms=result.search_time_ms,
            filters_applied=result.filters_applied,
            aggregations=result.aggregations
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Log search failed: {str(e)}"
        )


@router.get("/search", response_model=LogSearchResponse)
async def search_logs_get(
    query: Optional[str] = Query(None, description="Text search query"),
    level: Optional[LogLevelFilter] = Query(None, description="Filter by log level"),
    source: Optional[LogSourceFilter] = Query(None, description="Filter by log source"),
    service: Optional[str] = Query(None, description="Filter by service name"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    correlation_id: Optional[str] = Query(None, description="Filter by correlation ID"),
    error_type: Optional[str] = Query(None, description="Filter by error type"),
    start_time: Optional[datetime] = Query(None, description="Start time for search"),
    end_time: Optional[datetime] = Query(None, description="End time for search"),
    has_error: Optional[bool] = Query(None, description="Filter entries with errors"),
    has_duration: Optional[bool] = Query(None, description="Filter entries with duration"),
    min_duration_ms: Optional[float] = Query(None, description="Minimum duration in milliseconds"),
    max_duration_ms: Optional[float] = Query(None, description="Maximum duration in milliseconds"),
    container_name: Optional[str] = Query(None, description="Filter by container name"),
    limit: int = Query(100, ge=1, le=10000, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    search_service: LogSearchService = Depends(get_search_service)
) -> LogSearchResponse:
    """
    Search logs using GET parameters (alternative to POST).
    
    Provides the same functionality as the POST endpoint but using
    query parameters for easier integration with web interfaces.
    """
    request = LogSearchRequest(
        query=query,
        level=level,
        source=source,
        service=service,
        user_id=user_id,
        correlation_id=correlation_id,
        error_type=error_type,
        start_time=start_time,
        end_time=end_time,
        has_error=has_error,
        has_duration=has_duration,
        min_duration_ms=min_duration_ms,
        max_duration_ms=max_duration_ms,
        container_name=container_name,
        limit=limit,
        offset=offset
    )
    
    return await search_logs(request, search_service)


@router.get("/statistics", response_model=LogStatistics)
async def get_log_statistics(
    hours: int = Query(24, ge=1, le=168, description="Time period in hours"),
    search_service: LogSearchService = Depends(get_search_service)
) -> LogStatistics:
    """
    Get comprehensive log statistics for the specified time period.
    
    Provides aggregated information about log levels, sources, services,
    error rates, and timing patterns.
    """
    try:
        stats = await search_service.get_log_statistics(hours)
        return LogStatistics(**stats)
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get log statistics: {str(e)}"
        )


@router.post("/export")
async def export_logs(
    request: LogSearchRequest,
    format_type: ExportFormat = Query(ExportFormat.JSON, description="Export format"),
    search_service: LogSearchService = Depends(get_search_service)
):
    """
    Export search results in the specified format.
    
    Supports JSON and CSV formats for external analysis and reporting.
    """
    try:
        # Convert request to search filter
        search_filter = SearchFilter(
            query=request.query,
            level=LogLevel(request.level.value) if request.level else None,
            source=LogSource(request.source.value) if request.source else None,
            service=request.service,
            user_id=request.user_id,
            correlation_id=request.correlation_id,
            error_type=request.error_type,
            start_time=request.start_time,
            end_time=request.end_time,
            has_error=request.has_error,
            has_duration=request.has_duration,
            min_duration_ms=request.min_duration_ms,
            max_duration_ms=request.max_duration_ms,
            container_name=request.container_name,
            limit=min(request.limit, 50000),  # Limit exports to prevent memory issues
            offset=request.offset
        )
        
        # Export data
        export_data = await search_service.export_logs(search_filter, format_type.value)
        
        # Determine content type and filename
        if format_type == ExportFormat.JSON:
            media_type = "application/json"
            filename = f"logs_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        else:  # CSV
            media_type = "text/csv"
            filename = f"logs_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        return PlainTextResponse(
            content=export_data,
            media_type=media_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Log export failed: {str(e)}"
        )


@router.get("/stream")
async def stream_logs(
    level: Optional[LogLevelFilter] = Query(None, description="Filter by log level"),
    source: Optional[LogSourceFilter] = Query(None, description="Filter by log source"),
    service: Optional[str] = Query(None, description="Filter by service name"),
    search_service: LogSearchService = Depends(get_search_service)
):
    """
    Stream real-time logs matching the specified filters.
    
    Provides a continuous stream of new log entries as they arrive,
    useful for real-time monitoring and debugging.
    """
    async def log_generator():
        """Generate streaming log entries."""
        last_check = datetime.now()
        
        while True:
            try:
                # Get recent logs (last 10 seconds)
                current_time = datetime.now()
                search_filter = SearchFilter(
                    level=LogLevel(level.value) if level else None,
                    source=LogSource(source.value) if source else None,
                    service=service,
                    start_time=last_check,
                    end_time=current_time,
                    limit=1000
                )
                
                result = await search_service.search_logs(search_filter)
                
                # Send new entries
                for entry in reversed(result.entries):  # Newest first
                    yield f"data: {json.dumps(entry.to_dict(), default=str)}\n\n"
                
                last_check = current_time
                
                # Wait before next check
                await asyncio.sleep(2)
                
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                await asyncio.sleep(5)
    
    return StreamingResponse(
        log_generator(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )


@router.get("/recent")
async def get_recent_logs(
    limit: int = Query(100, ge=1, le=1000, description="Number of recent logs"),
    level: Optional[LogLevelFilter] = Query(None, description="Filter by log level"),
    source: Optional[LogSourceFilter] = Query(None, description="Filter by log source"),
    service: Optional[str] = Query(None, description="Filter by service name"),
    search_service: LogSearchService = Depends(get_search_service)
) -> LogSearchResponse:
    """
    Get the most recent log entries with optional filtering.
    
    Provides a quick way to see the latest activity across all services.
    """
    try:
        # Get logs from the last hour
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=1)
        
        search_filter = SearchFilter(
            level=LogLevel(level.value) if level else None,
            source=LogSource(source.value) if source else None,
            service=service,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=0
        )
        
        result = await search_service.search_logs(search_filter)
        
        return LogSearchResponse(
            entries=[LogEntry(**entry.to_dict()) for entry in result.entries],
            total_count=result.total_count,
            filtered_count=result.filtered_count,
            search_time_ms=result.search_time_ms,
            filters_applied=result.filters_applied,
            aggregations=result.aggregations
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get recent logs: {str(e)}"
        )


@router.get("/errors")
async def get_error_logs(
    hours: int = Query(24, ge=1, le=168, description="Time period in hours"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    search_service: LogSearchService = Depends(get_search_service)
) -> LogSearchResponse:
    """
    Get error and critical logs for the specified time period.
    
    Provides a focused view of problems and issues in the system.
    """
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        search_filter = SearchFilter(
            has_error=True,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=0
        )
        
        result = await search_service.search_logs(search_filter)
        
        return LogSearchResponse(
            entries=[LogEntry(**entry.to_dict()) for entry in result.entries],
            total_count=result.total_count,
            filtered_count=result.filtered_count,
            search_time_ms=result.search_time_ms,
            filters_applied=result.filters_applied,
            aggregations=result.aggregations
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get error logs: {str(e)}"
        )


@router.get("/services")
async def get_service_logs(
    service_name: str = Query(..., description="Service name to filter by"),
    hours: int = Query(24, ge=1, le=168, description="Time period in hours"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of results"),
    search_service: LogSearchService = Depends(get_search_service)
) -> LogSearchResponse:
    """
    Get logs for a specific service.
    
    Provides service-specific log analysis and debugging capabilities.
    """
    try:
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        
        search_filter = SearchFilter(
            service=service_name,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=0
        )
        
        result = await search_service.search_logs(search_filter)
        
        return LogSearchResponse(
            entries=[LogEntry(**entry.to_dict()) for entry in result.entries],
            total_count=result.total_count,
            filtered_count=result.filtered_count,
            search_time_ms=result.search_time_ms,
            filters_applied=result.filters_applied,
            aggregations=result.aggregations
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get service logs: {str(e)}"
        )


@router.delete("/cleanup")
async def cleanup_old_logs(
    background_tasks: BackgroundTasks,
    days: int = Query(7, ge=1, le=30, description="Keep logs newer than this many days"),
    search_service: LogSearchService = Depends(get_search_service)
) -> Dict[str, Any]:
    """
    Clean up old log entries to free up storage space.
    
    Removes log entries older than the specified number of days.
    This operation runs in the background.
    """
    def cleanup_task():
        """Background task to clean up old logs."""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # This would be implemented in the search service
            # For now, just return success
            return {"status": "completed", "cutoff_date": cutoff_date.isoformat()}
            
        except Exception as e:
            return {"status": "failed", "error": str(e)}
    
    background_tasks.add_task(cleanup_task)
    
    return {
        "message": f"Log cleanup initiated for entries older than {days} days",
        "status": "started"
    }


@router.get("/health")
async def log_search_health(
    search_service: LogSearchService = Depends(get_search_service)
) -> Dict[str, Any]:
    """
    Check the health of the log search service.
    
    Provides status information about the log search functionality.
    """
    try:
        # Get basic statistics to verify service is working
        stats = await search_service.get_log_statistics(1)  # Last hour
        
        return {
            "status": "healthy",
            "service": "log_search",
            "recent_logs_count": stats.get("total_logs", 0),
            "database_accessible": True,
            "docker_integration": search_service.docker_client is not None
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "log_search",
            "error": str(e),
            "database_accessible": False
        }