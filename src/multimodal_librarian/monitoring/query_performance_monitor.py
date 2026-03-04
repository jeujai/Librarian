"""
Query Performance Monitor for Local Development Conversion

This module provides comprehensive query performance monitoring for all database clients
in the local development environment. It tracks query execution times, identifies slow
queries, monitors resource usage, and provides optimization recommendations.

The monitor integrates with all database clients (PostgreSQL, Neo4j, Milvus) to provide
unified performance insights across the entire database stack.

Features:
- Real-time query performance tracking
- Slow query detection and analysis
- Resource usage monitoring during queries
- Performance trend analysis
- Optimization recommendations
- Integration with existing monitoring infrastructure
- Configurable thresholds and alerting

Example Usage:
    ```python
    from multimodal_librarian.monitoring.query_performance_monitor import QueryPerformanceMonitor
    
    # Initialize monitor
    monitor = QueryPerformanceMonitor()
    await monitor.start()
    
    # Monitor a query
    async with monitor.track_query("postgresql", "SELECT * FROM users") as tracker:
        result = await client.execute_query("SELECT * FROM users")
        tracker.set_result_count(len(result))
    
    # Get performance stats
    stats = await monitor.get_performance_stats()
    print(f"Average query time: {stats['avg_query_time']:.3f}s")
    
    await monitor.stop()
    ```

Integration with Database Clients:
    The monitor integrates with database clients through a decorator pattern,
    automatically tracking all query operations without modifying client code.
"""

import asyncio
import time
import logging
import psutil
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, AsyncContextManager
from dataclasses import dataclass, field
from contextlib import asynccontextmanager
from collections import defaultdict, deque
import statistics
import json
from enum import Enum

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Types of database queries."""
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    CREATE = "CREATE"
    DROP = "DROP"
    ALTER = "ALTER"
    VECTOR_SEARCH = "VECTOR_SEARCH"
    GRAPH_QUERY = "GRAPH_QUERY"
    UNKNOWN = "UNKNOWN"


class DatabaseType(Enum):
    """Types of databases being monitored."""
    POSTGRESQL = "postgresql"
    NEO4J = "neo4j"
    MILVUS = "milvus"


@dataclass
class QueryMetrics:
    """Metrics for a single query execution."""
    query_id: str
    database_type: DatabaseType
    query_type: QueryType
    query_text: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    result_count: Optional[int] = None
    error: Optional[str] = None
    
    # Resource usage during query
    cpu_usage_start: float = 0.0
    cpu_usage_end: float = 0.0
    memory_usage_start: float = 0.0
    memory_usage_end: float = 0.0
    
    # Query characteristics
    query_complexity: str = "simple"  # simple, medium, complex
    uses_index: Optional[bool] = None
    table_scans: int = 0
    
    # Metadata
    client_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PerformanceAlert:
    """Performance alert for query monitoring."""
    alert_id: str
    alert_type: str  # slow_query, high_cpu, memory_spike, error_rate
    severity: str  # low, medium, high, critical
    message: str
    timestamp: datetime
    database_type: DatabaseType
    query_metrics: Optional[QueryMetrics] = None
    threshold_value: Optional[float] = None
    actual_value: Optional[float] = None
    recommendations: List[str] = field(default_factory=list)


@dataclass
class PerformanceStats:
    """Aggregated performance statistics."""
    database_type: DatabaseType
    time_window: timedelta
    
    # Query counts
    total_queries: int = 0
    successful_queries: int = 0
    failed_queries: int = 0
    
    # Timing statistics
    avg_query_time_ms: float = 0.0
    median_query_time_ms: float = 0.0
    p95_query_time_ms: float = 0.0
    p99_query_time_ms: float = 0.0
    min_query_time_ms: float = 0.0
    max_query_time_ms: float = 0.0
    
    # Query type breakdown
    query_type_counts: Dict[QueryType, int] = field(default_factory=dict)
    query_type_avg_times: Dict[QueryType, float] = field(default_factory=dict)
    
    # Slow queries
    slow_query_count: int = 0
    slow_query_threshold_ms: float = 1000.0
    
    # Resource usage
    avg_cpu_usage: float = 0.0
    peak_cpu_usage: float = 0.0
    avg_memory_usage_mb: float = 0.0
    peak_memory_usage_mb: float = 0.0
    
    # Error statistics
    error_rate: float = 0.0
    common_errors: Dict[str, int] = field(default_factory=dict)


class QueryTracker:
    """Context manager for tracking individual query performance."""
    
    def __init__(self, monitor: 'QueryPerformanceMonitor', metrics: QueryMetrics):
        self.monitor = monitor
        self.metrics = metrics
        self._start_resources_captured = False
    
    async def __aenter__(self):
        """Start tracking query performance."""
        self.metrics.start_time = datetime.utcnow()
        
        # Capture initial resource usage
        try:
            process = psutil.Process()
            self.metrics.cpu_usage_start = process.cpu_percent()
            self.metrics.memory_usage_start = process.memory_info().rss / 1024 / 1024  # MB
            self._start_resources_captured = True
        except Exception as e:
            logger.warning(f"Failed to capture start resource usage: {e}")
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Finish tracking query performance."""
        self.metrics.end_time = datetime.utcnow()
        
        if self.metrics.start_time and self.metrics.end_time:
            duration = self.metrics.end_time - self.metrics.start_time
            self.metrics.duration_ms = duration.total_seconds() * 1000
        
        # Capture final resource usage
        if self._start_resources_captured:
            try:
                process = psutil.Process()
                self.metrics.cpu_usage_end = process.cpu_percent()
                self.metrics.memory_usage_end = process.memory_info().rss / 1024 / 1024  # MB
            except Exception as e:
                logger.warning(f"Failed to capture end resource usage: {e}")
        
        # Handle exceptions
        if exc_type is not None:
            self.metrics.error = str(exc_val) if exc_val else str(exc_type)
        
        # Record the metrics
        await self.monitor._record_query_metrics(self.metrics)
    
    def set_result_count(self, count: int) -> None:
        """Set the number of results returned by the query."""
        self.metrics.result_count = count
    
    def set_query_complexity(self, complexity: str) -> None:
        """Set the query complexity level."""
        self.metrics.query_complexity = complexity
    
    def set_uses_index(self, uses_index: bool) -> None:
        """Set whether the query uses an index."""
        self.metrics.uses_index = uses_index
    
    def set_table_scans(self, count: int) -> None:
        """Set the number of table scans performed."""
        self.metrics.table_scans = count
    
    def add_metadata(self, key: str, value: Any) -> None:
        """Add metadata to the query metrics."""
        self.metrics.metadata[key] = value


class QueryPerformanceMonitor:
    """
    Comprehensive query performance monitor for local development.
    
    This monitor tracks query performance across all database types in the
    local development environment, providing insights into query execution
    times, resource usage, and optimization opportunities.
    """
    
    def __init__(
        self,
        slow_query_threshold_ms: float = 1000.0,
        high_cpu_threshold: float = 80.0,
        high_memory_threshold_mb: float = 1000.0,
        max_metrics_history: int = 10000,
        stats_window_minutes: int = 60
    ):
        """
        Initialize the query performance monitor.
        
        Args:
            slow_query_threshold_ms: Threshold for slow query alerts (default: 1000ms)
            high_cpu_threshold: CPU usage threshold for alerts (default: 80%)
            high_memory_threshold_mb: Memory usage threshold for alerts (default: 1000MB)
            max_metrics_history: Maximum number of query metrics to keep (default: 10000)
            stats_window_minutes: Time window for statistics calculation (default: 60 minutes)
        """
        self.slow_query_threshold_ms = slow_query_threshold_ms
        self.high_cpu_threshold = high_cpu_threshold
        self.high_memory_threshold_mb = high_memory_threshold_mb
        self.max_metrics_history = max_metrics_history
        self.stats_window = timedelta(minutes=stats_window_minutes)
        
        # Query metrics storage
        self.query_metrics: deque[QueryMetrics] = deque(maxlen=max_metrics_history)
        self.metrics_by_database: Dict[DatabaseType, deque[QueryMetrics]] = {
            db_type: deque(maxlen=max_metrics_history) for db_type in DatabaseType
        }
        
        # Performance alerts
        self.alerts: deque[PerformanceAlert] = deque(maxlen=1000)
        self.alert_callbacks: List[Callable[[PerformanceAlert], None]] = []
        
        # Monitoring state
        self.is_monitoring = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self._query_counter = 0
        
        # Statistics cache
        self._stats_cache: Dict[DatabaseType, PerformanceStats] = {}
        self._stats_cache_time: Dict[DatabaseType, datetime] = {}
        self._stats_cache_ttl = timedelta(minutes=5)
        
        logger.info("Query performance monitor initialized")
    
    async def start(self) -> None:
        """Start the query performance monitor."""
        if self.is_monitoring:
            logger.warning("Query performance monitor is already running")
            return
        
        self.is_monitoring = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        logger.info("Query performance monitor started")
    
    async def stop(self) -> None:
        """Stop the query performance monitor."""
        if not self.is_monitoring:
            return
        
        self.is_monitoring = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
        
        logger.info("Query performance monitor stopped")
    
    @asynccontextmanager
    async def track_query(
        self,
        database_type: str,
        query_text: str,
        query_type: Optional[str] = None,
        client_id: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> AsyncContextManager[QueryTracker]:
        """
        Track performance of a database query.
        
        Args:
            database_type: Type of database (postgresql, neo4j, milvus)
            query_text: The query being executed
            query_type: Type of query (SELECT, INSERT, etc.)
            client_id: Optional client identifier
            user_id: Optional user identifier
            session_id: Optional session identifier
            
        Returns:
            QueryTracker context manager for tracking the query
            
        Example:
            ```python
            async with monitor.track_query("postgresql", "SELECT * FROM users") as tracker:
                result = await client.execute_query("SELECT * FROM users")
                tracker.set_result_count(len(result))
            ```
        """
        # Generate unique query ID
        self._query_counter += 1
        query_id = f"{database_type}_{self._query_counter}_{int(time.time())}"
        
        # Parse database type
        try:
            db_type = DatabaseType(database_type.lower())
        except ValueError:
            logger.warning(f"Unknown database type: {database_type}")
            db_type = DatabaseType.POSTGRESQL  # Default fallback
        
        # Parse query type
        parsed_query_type = self._parse_query_type(query_text, query_type)
        
        # Create metrics object
        metrics = QueryMetrics(
            query_id=query_id,
            database_type=db_type,
            query_type=parsed_query_type,
            query_text=query_text[:1000],  # Truncate long queries
            start_time=datetime.utcnow(),
            client_id=client_id,
            user_id=user_id,
            session_id=session_id
        )
        
        # Create and return tracker
        tracker = QueryTracker(self, metrics)
        async with tracker:
            yield tracker
    
    def _parse_query_type(self, query_text: str, query_type: Optional[str] = None) -> QueryType:
        """Parse query type from query text or provided type."""
        if query_type:
            try:
                return QueryType(query_type.upper())
            except ValueError:
                pass
        
        # Parse from query text
        query_upper = query_text.strip().upper()
        
        if query_upper.startswith('SELECT'):
            return QueryType.SELECT
        elif query_upper.startswith('INSERT'):
            return QueryType.INSERT
        elif query_upper.startswith('UPDATE'):
            return QueryType.UPDATE
        elif query_upper.startswith('DELETE'):
            return QueryType.DELETE
        elif query_upper.startswith('CREATE'):
            return QueryType.CREATE
        elif query_upper.startswith('DROP'):
            return QueryType.DROP
        elif query_upper.startswith('ALTER'):
            return QueryType.ALTER
        elif 'MATCH' in query_upper or 'RETURN' in query_upper:
            return QueryType.GRAPH_QUERY
        elif 'search' in query_upper.lower() or 'vector' in query_upper.lower():
            return QueryType.VECTOR_SEARCH
        else:
            return QueryType.UNKNOWN
    
    async def _record_query_metrics(self, metrics: QueryMetrics) -> None:
        """Record query metrics and check for alerts."""
        # Store metrics
        self.query_metrics.append(metrics)
        self.metrics_by_database[metrics.database_type].append(metrics)
        
        # Check for performance alerts
        await self._check_performance_alerts(metrics)
        
        # Invalidate stats cache for this database type
        if metrics.database_type in self._stats_cache:
            del self._stats_cache[metrics.database_type]
            del self._stats_cache_time[metrics.database_type]
        
        logger.debug(
            f"Recorded query metrics: {metrics.database_type.value} "
            f"{metrics.query_type.value} {metrics.duration_ms:.2f}ms"
        )
    
    async def _check_performance_alerts(self, metrics: QueryMetrics) -> None:
        """Check for performance alerts based on query metrics."""
        alerts = []
        
        # Check for slow queries
        if metrics.duration_ms and metrics.duration_ms > self.slow_query_threshold_ms:
            alert = PerformanceAlert(
                alert_id=f"slow_query_{metrics.query_id}",
                alert_type="slow_query",
                severity="high" if metrics.duration_ms > self.slow_query_threshold_ms * 2 else "medium",
                message=f"Slow query detected: {metrics.duration_ms:.2f}ms (threshold: {self.slow_query_threshold_ms}ms)",
                timestamp=datetime.utcnow(),
                database_type=metrics.database_type,
                query_metrics=metrics,
                threshold_value=self.slow_query_threshold_ms,
                actual_value=metrics.duration_ms,
                recommendations=self._get_slow_query_recommendations(metrics)
            )
            alerts.append(alert)
        
        # Check for high CPU usage
        cpu_usage = metrics.cpu_usage_end - metrics.cpu_usage_start
        if cpu_usage > self.high_cpu_threshold:
            alert = PerformanceAlert(
                alert_id=f"high_cpu_{metrics.query_id}",
                alert_type="high_cpu",
                severity="high" if cpu_usage > self.high_cpu_threshold * 1.5 else "medium",
                message=f"High CPU usage during query: {cpu_usage:.1f}% (threshold: {self.high_cpu_threshold}%)",
                timestamp=datetime.utcnow(),
                database_type=metrics.database_type,
                query_metrics=metrics,
                threshold_value=self.high_cpu_threshold,
                actual_value=cpu_usage,
                recommendations=self._get_cpu_usage_recommendations(metrics)
            )
            alerts.append(alert)
        
        # Check for high memory usage
        memory_usage = metrics.memory_usage_end - metrics.memory_usage_start
        if memory_usage > self.high_memory_threshold_mb:
            alert = PerformanceAlert(
                alert_id=f"memory_spike_{metrics.query_id}",
                alert_type="memory_spike",
                severity="high" if memory_usage > self.high_memory_threshold_mb * 2 else "medium",
                message=f"Memory spike during query: {memory_usage:.1f}MB (threshold: {self.high_memory_threshold_mb}MB)",
                timestamp=datetime.utcnow(),
                database_type=metrics.database_type,
                query_metrics=metrics,
                threshold_value=self.high_memory_threshold_mb,
                actual_value=memory_usage,
                recommendations=self._get_memory_usage_recommendations(metrics)
            )
            alerts.append(alert)
        
        # Check for query errors
        if metrics.error:
            alert = PerformanceAlert(
                alert_id=f"query_error_{metrics.query_id}",
                alert_type="query_error",
                severity="high",
                message=f"Query error: {metrics.error}",
                timestamp=datetime.utcnow(),
                database_type=metrics.database_type,
                query_metrics=metrics,
                recommendations=self._get_error_recommendations(metrics)
            )
            alerts.append(alert)
        
        # Store and notify about alerts
        for alert in alerts:
            self.alerts.append(alert)
            await self._notify_alert(alert)
    
    def _get_slow_query_recommendations(self, metrics: QueryMetrics) -> List[str]:
        """Get recommendations for slow queries."""
        recommendations = []
        
        if metrics.database_type == DatabaseType.POSTGRESQL:
            recommendations.extend([
                "Consider adding indexes on frequently queried columns",
                "Use EXPLAIN ANALYZE to identify bottlenecks",
                "Consider query optimization or rewriting",
                "Check if table statistics are up to date (ANALYZE)",
                "Consider connection pooling if not already enabled"
            ])
        elif metrics.database_type == DatabaseType.NEO4J:
            recommendations.extend([
                "Consider adding indexes on node properties used in WHERE clauses",
                "Use PROFILE to analyze query execution plan",
                "Consider using parameters instead of literal values",
                "Check if relationships have appropriate direction",
                "Consider breaking complex queries into simpler parts"
            ])
        elif metrics.database_type == DatabaseType.MILVUS:
            recommendations.extend([
                "Consider using appropriate index type (IVF_FLAT, HNSW, etc.)",
                "Adjust search parameters (nprobe, ef) for better performance",
                "Consider batch operations for multiple queries",
                "Check if collection is properly loaded into memory",
                "Consider using GPU acceleration if available"
            ])
        
        return recommendations
    
    def _get_cpu_usage_recommendations(self, metrics: QueryMetrics) -> List[str]:
        """Get recommendations for high CPU usage."""
        return [
            "Consider optimizing query complexity",
            "Check for missing indexes causing full table scans",
            "Consider using connection pooling to reduce overhead",
            "Monitor concurrent query load",
            "Consider scaling database resources if consistently high"
        ]
    
    def _get_memory_usage_recommendations(self, metrics: QueryMetrics) -> List[str]:
        """Get recommendations for high memory usage."""
        return [
            "Consider limiting result set size with LIMIT clauses",
            "Use streaming or pagination for large result sets",
            "Check for memory leaks in application code",
            "Consider increasing available memory if consistently high",
            "Monitor garbage collection if applicable"
        ]
    
    def _get_error_recommendations(self, metrics: QueryMetrics) -> List[str]:
        """Get recommendations for query errors."""
        recommendations = [
            "Check query syntax and parameters",
            "Verify database connection is stable",
            "Check database logs for more details",
            "Consider implementing retry logic for transient errors"
        ]
        
        if "timeout" in metrics.error.lower():
            recommendations.extend([
                "Consider increasing query timeout",
                "Optimize query performance to reduce execution time",
                "Check database server load"
            ])
        
        return recommendations
    
    async def _notify_alert(self, alert: PerformanceAlert) -> None:
        """Notify registered callbacks about performance alerts."""
        for callback in self.alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(alert)
                else:
                    callback(alert)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}")
    
    def add_alert_callback(self, callback: Callable[[PerformanceAlert], None]) -> None:
        """Add a callback for performance alerts."""
        self.alert_callbacks.append(callback)
    
    def remove_alert_callback(self, callback: Callable[[PerformanceAlert], None]) -> None:
        """Remove a callback for performance alerts."""
        if callback in self.alert_callbacks:
            self.alert_callbacks.remove(callback)
    
    async def get_performance_stats(
        self, 
        database_type: Optional[str] = None,
        force_refresh: bool = False
    ) -> Dict[str, PerformanceStats]:
        """
        Get performance statistics for database types.
        
        Args:
            database_type: Specific database type to get stats for (optional)
            force_refresh: Force refresh of cached statistics
            
        Returns:
            Dictionary of performance statistics by database type
        """
        stats = {}
        
        # Determine which database types to include
        if database_type:
            try:
                db_types = [DatabaseType(database_type.lower())]
            except ValueError:
                logger.warning(f"Unknown database type: {database_type}")
                return {}
        else:
            db_types = list(DatabaseType)
        
        # Get stats for each database type
        for db_type in db_types:
            # Check cache first
            if (not force_refresh and 
                db_type in self._stats_cache and 
                db_type in self._stats_cache_time and
                datetime.utcnow() - self._stats_cache_time[db_type] < self._stats_cache_ttl):
                stats[db_type.value] = self._stats_cache[db_type]
                continue
            
            # Calculate fresh statistics
            db_stats = await self._calculate_performance_stats(db_type)
            
            # Cache the results
            self._stats_cache[db_type] = db_stats
            self._stats_cache_time[db_type] = datetime.utcnow()
            
            stats[db_type.value] = db_stats
        
        return stats
    
    async def _calculate_performance_stats(self, database_type: DatabaseType) -> PerformanceStats:
        """Calculate performance statistics for a specific database type."""
        # Get metrics within the time window
        cutoff_time = datetime.utcnow() - self.stats_window
        recent_metrics = [
            m for m in self.metrics_by_database[database_type]
            if m.start_time >= cutoff_time
        ]
        
        if not recent_metrics:
            return PerformanceStats(
                database_type=database_type,
                time_window=self.stats_window
            )
        
        # Calculate basic counts
        total_queries = len(recent_metrics)
        successful_queries = len([m for m in recent_metrics if not m.error])
        failed_queries = total_queries - successful_queries
        
        # Calculate timing statistics
        durations = [m.duration_ms for m in recent_metrics if m.duration_ms is not None]
        
        if durations:
            avg_query_time_ms = statistics.mean(durations)
            median_query_time_ms = statistics.median(durations)
            min_query_time_ms = min(durations)
            max_query_time_ms = max(durations)
            
            # Calculate percentiles
            sorted_durations = sorted(durations)
            p95_index = int(0.95 * len(sorted_durations))
            p99_index = int(0.99 * len(sorted_durations))
            p95_query_time_ms = sorted_durations[p95_index] if p95_index < len(sorted_durations) else max_query_time_ms
            p99_query_time_ms = sorted_durations[p99_index] if p99_index < len(sorted_durations) else max_query_time_ms
        else:
            avg_query_time_ms = median_query_time_ms = min_query_time_ms = max_query_time_ms = 0.0
            p95_query_time_ms = p99_query_time_ms = 0.0
        
        # Calculate query type breakdown
        query_type_counts = defaultdict(int)
        query_type_durations = defaultdict(list)
        
        for metrics in recent_metrics:
            query_type_counts[metrics.query_type] += 1
            if metrics.duration_ms is not None:
                query_type_durations[metrics.query_type].append(metrics.duration_ms)
        
        query_type_avg_times = {}
        for query_type, durations in query_type_durations.items():
            if durations:
                query_type_avg_times[query_type] = statistics.mean(durations)
        
        # Calculate slow queries
        slow_query_count = len([
            m for m in recent_metrics 
            if m.duration_ms and m.duration_ms > self.slow_query_threshold_ms
        ])
        
        # Calculate resource usage
        cpu_usages = []
        memory_usages = []
        
        for metrics in recent_metrics:
            if metrics.cpu_usage_end > metrics.cpu_usage_start:
                cpu_usages.append(metrics.cpu_usage_end - metrics.cpu_usage_start)
            if metrics.memory_usage_end > metrics.memory_usage_start:
                memory_usages.append(metrics.memory_usage_end - metrics.memory_usage_start)
        
        avg_cpu_usage = statistics.mean(cpu_usages) if cpu_usages else 0.0
        peak_cpu_usage = max(cpu_usages) if cpu_usages else 0.0
        avg_memory_usage_mb = statistics.mean(memory_usages) if memory_usages else 0.0
        peak_memory_usage_mb = max(memory_usages) if memory_usages else 0.0
        
        # Calculate error statistics
        error_rate = failed_queries / total_queries if total_queries > 0 else 0.0
        common_errors = defaultdict(int)
        for metrics in recent_metrics:
            if metrics.error:
                # Simplify error message for grouping
                error_key = metrics.error.split(':')[0] if ':' in metrics.error else metrics.error
                common_errors[error_key] += 1
        
        return PerformanceStats(
            database_type=database_type,
            time_window=self.stats_window,
            total_queries=total_queries,
            successful_queries=successful_queries,
            failed_queries=failed_queries,
            avg_query_time_ms=avg_query_time_ms,
            median_query_time_ms=median_query_time_ms,
            p95_query_time_ms=p95_query_time_ms,
            p99_query_time_ms=p99_query_time_ms,
            min_query_time_ms=min_query_time_ms,
            max_query_time_ms=max_query_time_ms,
            query_type_counts=dict(query_type_counts),
            query_type_avg_times=query_type_avg_times,
            slow_query_count=slow_query_count,
            slow_query_threshold_ms=self.slow_query_threshold_ms,
            avg_cpu_usage=avg_cpu_usage,
            peak_cpu_usage=peak_cpu_usage,
            avg_memory_usage_mb=avg_memory_usage_mb,
            peak_memory_usage_mb=peak_memory_usage_mb,
            error_rate=error_rate,
            common_errors=dict(common_errors)
        )
    
    async def get_slow_queries(
        self, 
        database_type: Optional[str] = None,
        limit: int = 10
    ) -> List[QueryMetrics]:
        """
        Get the slowest queries within the monitoring window.
        
        Args:
            database_type: Filter by database type (optional)
            limit: Maximum number of queries to return
            
        Returns:
            List of slowest query metrics
        """
        # Get recent metrics
        cutoff_time = datetime.utcnow() - self.stats_window
        
        if database_type:
            try:
                db_type = DatabaseType(database_type.lower())
                recent_metrics = [
                    m for m in self.metrics_by_database[db_type]
                    if m.start_time >= cutoff_time and m.duration_ms is not None
                ]
            except ValueError:
                logger.warning(f"Unknown database type: {database_type}")
                return []
        else:
            recent_metrics = [
                m for m in self.query_metrics
                if m.start_time >= cutoff_time and m.duration_ms is not None
            ]
        
        # Sort by duration and return top N
        slow_queries = sorted(
            recent_metrics,
            key=lambda m: m.duration_ms or 0,
            reverse=True
        )[:limit]
        
        return slow_queries
    
    async def get_recent_alerts(
        self, 
        alert_type: Optional[str] = None,
        limit: int = 50
    ) -> List[PerformanceAlert]:
        """
        Get recent performance alerts.
        
        Args:
            alert_type: Filter by alert type (optional)
            limit: Maximum number of alerts to return
            
        Returns:
            List of recent performance alerts
        """
        alerts = list(self.alerts)
        
        if alert_type:
            alerts = [a for a in alerts if a.alert_type == alert_type]
        
        # Sort by timestamp (most recent first) and limit
        alerts.sort(key=lambda a: a.timestamp, reverse=True)
        return alerts[:limit]
    
    async def export_metrics(
        self, 
        filepath: str,
        database_type: Optional[str] = None,
        format: str = "json"
    ) -> bool:
        """
        Export query metrics to a file.
        
        Args:
            filepath: Path to export file
            database_type: Filter by database type (optional)
            format: Export format (json, csv)
            
        Returns:
            True if export was successful
        """
        try:
            # Get metrics to export
            if database_type:
                try:
                    db_type = DatabaseType(database_type.lower())
                    metrics_to_export = list(self.metrics_by_database[db_type])
                except ValueError:
                    logger.error(f"Unknown database type: {database_type}")
                    return False
            else:
                metrics_to_export = list(self.query_metrics)
            
            if format.lower() == "json":
                # Convert to JSON-serializable format
                export_data = []
                for metrics in metrics_to_export:
                    data = {
                        "query_id": metrics.query_id,
                        "database_type": metrics.database_type.value,
                        "query_type": metrics.query_type.value,
                        "query_text": metrics.query_text,
                        "start_time": metrics.start_time.isoformat(),
                        "end_time": metrics.end_time.isoformat() if metrics.end_time else None,
                        "duration_ms": metrics.duration_ms,
                        "result_count": metrics.result_count,
                        "error": metrics.error,
                        "cpu_usage_delta": metrics.cpu_usage_end - metrics.cpu_usage_start,
                        "memory_usage_delta_mb": metrics.memory_usage_end - metrics.memory_usage_start,
                        "query_complexity": metrics.query_complexity,
                        "uses_index": metrics.uses_index,
                        "table_scans": metrics.table_scans,
                        "metadata": metrics.metadata
                    }
                    export_data.append(data)
                
                with open(filepath, 'w') as f:
                    json.dump(export_data, f, indent=2)
            
            elif format.lower() == "csv":
                import csv
                
                with open(filepath, 'w', newline='') as f:
                    writer = csv.writer(f)
                    
                    # Write header
                    writer.writerow([
                        "query_id", "database_type", "query_type", "start_time",
                        "duration_ms", "result_count", "error", "cpu_usage_delta",
                        "memory_usage_delta_mb", "query_complexity", "uses_index",
                        "table_scans"
                    ])
                    
                    # Write data
                    for metrics in metrics_to_export:
                        writer.writerow([
                            metrics.query_id,
                            metrics.database_type.value,
                            metrics.query_type.value,
                            metrics.start_time.isoformat(),
                            metrics.duration_ms,
                            metrics.result_count,
                            metrics.error,
                            metrics.cpu_usage_end - metrics.cpu_usage_start,
                            metrics.memory_usage_end - metrics.memory_usage_start,
                            metrics.query_complexity,
                            metrics.uses_index,
                            metrics.table_scans
                        ])
            
            else:
                logger.error(f"Unsupported export format: {format}")
                return False
            
            logger.info(f"Exported {len(metrics_to_export)} metrics to {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export metrics: {e}")
            return False
    
    async def _monitoring_loop(self) -> None:
        """Background monitoring loop for periodic tasks."""
        while self.is_monitoring:
            try:
                # Cleanup old metrics beyond max history
                current_time = datetime.utcnow()
                cleanup_cutoff = current_time - timedelta(hours=24)  # Keep 24 hours of data
                
                # Clean up main metrics
                while (self.query_metrics and 
                       self.query_metrics[0].start_time < cleanup_cutoff):
                    self.query_metrics.popleft()
                
                # Clean up per-database metrics
                for db_type in DatabaseType:
                    metrics_deque = self.metrics_by_database[db_type]
                    while (metrics_deque and 
                           metrics_deque[0].start_time < cleanup_cutoff):
                        metrics_deque.popleft()
                
                # Clean up old alerts
                alert_cutoff = current_time - timedelta(hours=6)  # Keep 6 hours of alerts
                while (self.alerts and 
                       self.alerts[0].timestamp < alert_cutoff):
                    self.alerts.popleft()
                
                # Log monitoring status
                total_metrics = len(self.query_metrics)
                total_alerts = len(self.alerts)
                
                logger.debug(
                    f"Query monitor status: {total_metrics} metrics, "
                    f"{total_alerts} alerts"
                )
                
                # Sleep for monitoring interval
                await asyncio.sleep(300)  # 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get current monitoring status."""
        return {
            "is_monitoring": self.is_monitoring,
            "total_queries_tracked": len(self.query_metrics),
            "total_alerts": len(self.alerts),
            "queries_by_database": {
                db_type.value: len(metrics)
                for db_type, metrics in self.metrics_by_database.items()
            },
            "slow_query_threshold_ms": self.slow_query_threshold_ms,
            "high_cpu_threshold": self.high_cpu_threshold,
            "high_memory_threshold_mb": self.high_memory_threshold_mb,
            "stats_window_minutes": self.stats_window.total_seconds() / 60,
            "cache_status": {
                db_type.value: {
                    "cached": db_type in self._stats_cache,
                    "cache_time": self._stats_cache_time.get(db_type, datetime.min).isoformat()
                }
                for db_type in DatabaseType
            }
        }


# Global monitor instance for easy access
_global_monitor: Optional[QueryPerformanceMonitor] = None


def get_global_monitor() -> Optional[QueryPerformanceMonitor]:
    """Get the global query performance monitor instance."""
    return _global_monitor


def set_global_monitor(monitor: QueryPerformanceMonitor) -> None:
    """Set the global query performance monitor instance."""
    global _global_monitor
    _global_monitor = monitor


async def initialize_global_monitor(**kwargs) -> QueryPerformanceMonitor:
    """Initialize and start the global query performance monitor."""
    global _global_monitor
    
    if _global_monitor is not None:
        logger.warning("Global query performance monitor already initialized")
        return _global_monitor
    
    _global_monitor = QueryPerformanceMonitor(**kwargs)
    await _global_monitor.start()
    
    logger.info("Global query performance monitor initialized and started")
    return _global_monitor


async def shutdown_global_monitor() -> None:
    """Shutdown the global query performance monitor."""
    global _global_monitor
    
    if _global_monitor is not None:
        await _global_monitor.stop()
        _global_monitor = None
        logger.info("Global query performance monitor shutdown")