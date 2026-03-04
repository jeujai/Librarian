"""
Database Optimization API Router

This module provides REST API endpoints for database optimization features including:
- Connection pool management and monitoring
- Query performance analysis
- Batch operation utilities
- Database optimization controls
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field

from ...database.database_optimizer import (
    get_database_optimizer,
    optimize_database,
    get_database_status,
    batch_insert_data,
    batch_update_data,
    batch_delete_data
)
from ...logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/database", tags=["database-optimization"])


# Request/Response Models
class BatchInsertRequest(BaseModel):
    """Request model for batch insert operations."""
    table_name: str = Field(..., description="Target table name")
    data: List[Dict[str, Any]] = Field(..., description="List of row data to insert")
    batch_size: Optional[int] = Field(1000, description="Number of rows per batch")
    on_conflict: str = Field("ignore", description="Conflict resolution strategy")


class BatchUpdateRequest(BaseModel):
    """Request model for batch update operations."""
    table_name: str = Field(..., description="Target table name")
    updates: List[Dict[str, Any]] = Field(..., description="List of update data")
    key_column: str = Field("id", description="Column to use for WHERE clause")
    batch_size: Optional[int] = Field(1000, description="Number of rows per batch")


class BatchDeleteRequest(BaseModel):
    """Request model for batch delete operations."""
    table_name: str = Field(..., description="Target table name")
    conditions: List[Dict[str, Any]] = Field(..., description="List of delete conditions")
    batch_size: Optional[int] = Field(1000, description="Number of rows per batch")


class OptimizationResponse(BaseModel):
    """Response model for optimization operations."""
    status: str
    timestamp: str
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class BatchOperationResponse(BaseModel):
    """Response model for batch operations."""
    status: str
    rows_affected: int
    batches_processed: int
    execution_time_seconds: float
    rows_per_second: float
    errors: List[str] = []


# Health and Status Endpoints
@router.get("/health", response_model=OptimizationResponse)
async def get_database_health():
    """
    Get database optimization health status.
    
    Returns comprehensive status including:
    - Connection pool metrics
    - Query performance statistics
    - Optimization recommendations
    """
    try:
        status = get_database_status()
        
        return OptimizationResponse(
            status="success",
            timestamp=datetime.now().isoformat(),
            message="Database optimization status retrieved successfully",
            data=status
        )
    except Exception as e:
        logger.error(f"Error getting database health: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status", response_model=OptimizationResponse)
async def get_optimization_status():
    """
    Get detailed database optimization status.
    
    Provides detailed information about:
    - Connection pool utilization
    - Query performance metrics
    - Batch processing capabilities
    - Current optimization settings
    """
    try:
        optimizer = get_database_optimizer()
        status = optimizer.get_optimization_status()
        
        return OptimizationResponse(
            status="success",
            timestamp=datetime.now().isoformat(),
            message="Optimization status retrieved successfully",
            data=status
        )
    except Exception as e:
        logger.error(f"Error getting optimization status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Connection Pool Management
@router.get("/connection-pool/metrics", response_model=OptimizationResponse)
async def get_connection_pool_metrics():
    """
    Get connection pool performance metrics.
    
    Returns:
    - Pool size and utilization
    - Connection checkout statistics
    - Performance metrics
    - Health status
    """
    try:
        optimizer = get_database_optimizer()
        metrics = optimizer.connection_pool.get_pool_metrics()
        health = optimizer.connection_pool.health_check()
        
        return OptimizationResponse(
            status="success",
            timestamp=datetime.now().isoformat(),
            message="Connection pool metrics retrieved successfully",
            data={
                "metrics": {
                    "pool_size": metrics.pool_size,
                    "checked_out": metrics.checked_out,
                    "checked_in": metrics.checked_in,
                    "overflow": metrics.overflow,
                    "utilization": metrics.checked_out / max(1, metrics.pool_size),
                    "average_checkout_time": metrics.average_checkout_time,
                    "total_connections": metrics.total_connections,
                    "peak_connections": metrics.peak_connections,
                    "connection_requests": metrics.connection_requests,
                    "connection_timeouts": metrics.connection_timeouts
                },
                "health": health
            }
        )
    except Exception as e:
        logger.error(f"Error getting connection pool metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connection-pool/optimize", response_model=OptimizationResponse)
async def optimize_connection_pool():
    """
    Optimize connection pool settings.
    
    Analyzes current usage patterns and provides optimization recommendations.
    May automatically adjust pool settings if auto-optimization is enabled.
    """
    try:
        optimizer = get_database_optimizer()
        result = optimizer.connection_pool.optimize_pool_settings()
        
        return OptimizationResponse(
            status="success",
            timestamp=datetime.now().isoformat(),
            message="Connection pool optimization completed",
            data=result
        )
    except Exception as e:
        logger.error(f"Error optimizing connection pool: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Query Performance Analysis
@router.get("/queries/performance", response_model=OptimizationResponse)
async def get_query_performance():
    """
    Get query performance analysis.
    
    Returns:
    - Slow query statistics
    - Frequent query analysis
    - Performance recommendations
    - Error statistics
    """
    try:
        optimizer = get_database_optimizer()
        analysis = optimizer.query_optimizer.analyze_query_performance()
        
        return OptimizationResponse(
            status="success",
            timestamp=datetime.now().isoformat(),
            message="Query performance analysis completed",
            data=analysis
        )
    except Exception as e:
        logger.error(f"Error analyzing query performance: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queries/slow", response_model=OptimizationResponse)
async def get_slow_queries(threshold_ms: Optional[float] = None):
    """
    Get slow queries above threshold.
    
    Args:
        threshold_ms: Minimum execution time in milliseconds (default: 1000ms)
    
    Returns:
        List of queries exceeding the threshold with performance metrics
    """
    try:
        optimizer = get_database_optimizer()
        slow_queries = optimizer.query_optimizer.get_slow_queries(threshold_ms)
        
        return OptimizationResponse(
            status="success",
            timestamp=datetime.now().isoformat(),
            message=f"Found {len(slow_queries)} slow queries",
            data={
                "threshold_ms": threshold_ms or 1000,
                "slow_queries": [
                    {
                        "query": q.query_text,
                        "average_time_ms": round(q.average_time_ms, 2),
                        "execution_count": q.execution_count,
                        "total_time_ms": round(q.total_time_ms, 2),
                        "min_time_ms": round(q.min_time_ms, 2),
                        "max_time_ms": round(q.max_time_ms, 2),
                        "error_count": q.error_count,
                        "last_executed": q.last_executed.isoformat()
                    }
                    for q in slow_queries
                ]
            }
        )
    except Exception as e:
        logger.error(f"Error getting slow queries: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/queries/frequent", response_model=OptimizationResponse)
async def get_frequent_queries(min_executions: int = 10):
    """
    Get frequently executed queries.
    
    Args:
        min_executions: Minimum number of executions to be considered frequent
    
    Returns:
        List of frequently executed queries with performance metrics
    """
    try:
        optimizer = get_database_optimizer()
        frequent_queries = optimizer.query_optimizer.get_frequent_queries(min_executions)
        
        return OptimizationResponse(
            status="success",
            timestamp=datetime.now().isoformat(),
            message=f"Found {len(frequent_queries)} frequent queries",
            data={
                "min_executions": min_executions,
                "frequent_queries": [
                    {
                        "query": q.query_text,
                        "execution_count": q.execution_count,
                        "average_time_ms": round(q.average_time_ms, 2),
                        "total_time_ms": round(q.total_time_ms, 2),
                        "error_count": q.error_count,
                        "last_executed": q.last_executed.isoformat()
                    }
                    for q in frequent_queries
                ]
            }
        )
    except Exception as e:
        logger.error(f"Error getting frequent queries: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/queries/suggest-optimizations", response_model=OptimizationResponse)
async def suggest_query_optimizations(query: str):
    """
    Get optimization suggestions for a specific query.
    
    Args:
        query: SQL query to analyze
    
    Returns:
        List of optimization suggestions with priorities and impact descriptions
    """
    try:
        optimizer = get_database_optimizer()
        suggestions = optimizer.query_optimizer.suggest_optimizations(query)
        
        return OptimizationResponse(
            status="success",
            timestamp=datetime.now().isoformat(),
            message=f"Generated {len(suggestions)} optimization suggestions",
            data={
                "query": query,
                "suggestions": suggestions
            }
        )
    except Exception as e:
        logger.error(f"Error suggesting query optimizations: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Batch Operations
@router.post("/batch/insert", response_model=BatchOperationResponse)
async def batch_insert(request: BatchInsertRequest, background_tasks: BackgroundTasks):
    """
    Perform batch insert operation.
    
    Efficiently inserts multiple rows with:
    - Configurable batch sizes
    - Conflict resolution strategies
    - Performance monitoring
    - Error handling
    """
    try:
        result = batch_insert_data(
            table_name=request.table_name,
            data=request.data,
            batch_size=request.batch_size,
            on_conflict=request.on_conflict
        )
        
        return BatchOperationResponse(
            status=result["status"],
            rows_affected=result["rows_inserted"],
            batches_processed=result["batches_processed"],
            execution_time_seconds=result["execution_time_seconds"],
            rows_per_second=result["rows_per_second"],
            errors=result.get("errors", [])
        )
    except Exception as e:
        logger.error(f"Error in batch insert: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch/update", response_model=BatchOperationResponse)
async def batch_update(request: BatchUpdateRequest, background_tasks: BackgroundTasks):
    """
    Perform batch update operation.
    
    Efficiently updates multiple rows with:
    - Configurable batch sizes
    - Flexible key column selection
    - Performance monitoring
    - Error handling
    """
    try:
        result = batch_update_data(
            table_name=request.table_name,
            updates=request.updates,
            key_column=request.key_column,
            batch_size=request.batch_size
        )
        
        return BatchOperationResponse(
            status=result["status"],
            rows_affected=result["rows_updated"],
            batches_processed=result["batches_processed"],
            execution_time_seconds=result["execution_time_seconds"],
            rows_per_second=result["rows_per_second"],
            errors=result.get("errors", [])
        )
    except Exception as e:
        logger.error(f"Error in batch update: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch/delete", response_model=BatchOperationResponse)
async def batch_delete(request: BatchDeleteRequest, background_tasks: BackgroundTasks):
    """
    Perform batch delete operation.
    
    Efficiently deletes multiple rows with:
    - Configurable batch sizes
    - Flexible condition matching
    - Performance monitoring
    - Error handling
    """
    try:
        result = batch_delete_data(
            table_name=request.table_name,
            conditions=request.conditions,
            batch_size=request.batch_size
        )
        
        return BatchOperationResponse(
            status=result["status"],
            rows_affected=result["rows_deleted"],
            batches_processed=result["batches_processed"],
            execution_time_seconds=result["execution_time_seconds"],
            rows_per_second=result["rows_per_second"],
            errors=result.get("errors", [])
        )
    except Exception as e:
        logger.error(f"Error in batch delete: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Optimization Controls
@router.post("/optimize", response_model=OptimizationResponse)
async def run_database_optimization(background_tasks: BackgroundTasks):
    """
    Run comprehensive database optimization.
    
    Performs:
    - Connection pool optimization
    - Query performance analysis
    - Index recommendations
    - General performance tuning
    """
    try:
        result = optimize_database()
        
        return OptimizationResponse(
            status="success",
            timestamp=datetime.now().isoformat(),
            message="Database optimization completed",
            data=result
        )
    except Exception as e:
        logger.error(f"Error running database optimization: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monitoring/start", response_model=OptimizationResponse)
async def start_monitoring():
    """
    Start database performance monitoring.
    
    Enables continuous monitoring of:
    - Connection pool performance
    - Query execution metrics
    - Automatic optimization triggers
    """
    try:
        optimizer = get_database_optimizer()
        result = optimizer.start_monitoring()
        
        return OptimizationResponse(
            status="success",
            timestamp=datetime.now().isoformat(),
            message="Database monitoring started",
            data=result
        )
    except Exception as e:
        logger.error(f"Error starting monitoring: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/monitoring/stop", response_model=OptimizationResponse)
async def stop_monitoring():
    """
    Stop database performance monitoring.
    
    Disables continuous monitoring and cleanup monitoring resources.
    """
    try:
        optimizer = get_database_optimizer()
        result = optimizer.stop_monitoring()
        
        return OptimizationResponse(
            status="success",
            timestamp=datetime.now().isoformat(),
            message="Database monitoring stopped",
            data=result
        )
    except Exception as e:
        logger.error(f"Error stopping monitoring: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Utility Endpoints
@router.get("/tables/stats", response_model=OptimizationResponse)
async def get_table_statistics():
    """
    Get database table statistics.
    
    Returns information about:
    - Table sizes
    - Row counts
    - Index usage
    - Storage statistics
    """
    try:
        optimizer = get_database_optimizer()
        
        with optimizer.connection_pool.get_session() as session:
            # Get table statistics (PostgreSQL specific)
            stats_query = """
                SELECT 
                    schemaname,
                    tablename,
                    attname,
                    n_distinct,
                    correlation
                FROM pg_stats 
                WHERE schemaname = 'public'
                ORDER BY tablename, attname
            """
            
            result = session.execute(text(stats_query))
            stats = [dict(row._mapping) for row in result]
            
            # Get table sizes
            size_query = """
                SELECT 
                    tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
                FROM pg_tables 
                WHERE schemaname = 'public'
                ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
            """
            
            size_result = session.execute(text(size_query))
            sizes = [dict(row._mapping) for row in size_result]
        
        return OptimizationResponse(
            status="success",
            timestamp=datetime.now().isoformat(),
            message="Table statistics retrieved successfully",
            data={
                "column_statistics": stats,
                "table_sizes": sizes
            }
        )
    except Exception as e:
        logger.error(f"Error getting table statistics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/indexes/usage", response_model=OptimizationResponse)
async def get_index_usage():
    """
    Get database index usage statistics.
    
    Returns information about:
    - Index usage frequency
    - Unused indexes
    - Index efficiency
    - Recommendations for index optimization
    """
    try:
        optimizer = get_database_optimizer()
        
        with optimizer.connection_pool.get_session() as session:
            # Get index usage statistics (PostgreSQL specific)
            index_query = """
                SELECT 
                    schemaname,
                    tablename,
                    indexname,
                    idx_tup_read,
                    idx_tup_fetch,
                    idx_scan
                FROM pg_stat_user_indexes
                ORDER BY idx_scan DESC
            """
            
            result = session.execute(text(index_query))
            index_stats = [dict(row._mapping) for row in result]
            
            # Find unused indexes
            unused_indexes = [idx for idx in index_stats if idx['idx_scan'] == 0]
            
        return OptimizationResponse(
            status="success",
            timestamp=datetime.now().isoformat(),
            message="Index usage statistics retrieved successfully",
            data={
                "index_usage": index_stats,
                "unused_indexes": unused_indexes,
                "recommendations": [
                    f"Consider dropping unused index: {idx['indexname']}"
                    for idx in unused_indexes[:5]  # Top 5 recommendations
                ]
            }
        )
    except Exception as e:
        logger.error(f"Error getting index usage: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))