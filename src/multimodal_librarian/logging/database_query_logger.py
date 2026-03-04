"""
Database Query Logging and Analysis for Local Development

This module provides comprehensive query logging and analysis for all database clients
in the local development environment. It captures query execution details, performance
metrics, and provides analysis capabilities for optimization.

Features:
- Query execution logging with detailed metrics
- Performance analysis and slow query detection
- Query pattern analysis and optimization recommendations
- Integration with existing monitoring infrastructure
- Configurable logging levels and retention policies
- Real-time query analysis and alerting

Example Usage:
    ```python
    from multimodal_librarian.logging.database_query_logger import DatabaseQueryLogger
    
    # Initialize logger
    query_logger = DatabaseQueryLogger()
    await query_logger.start()
    
    # Log a query
    await query_logger.log_query(
        database_type="postgresql",
        query="SELECT * FROM users WHERE active = $1",
        parameters={"$1": True},
        execution_time_ms=45.2,
        result_count=150
    )
    
    # Get analysis
    analysis = await query_logger.get_query_analysis()
    print(f"Slow queries: {len(analysis['slow_queries'])}")
    
    await query_logger.stop()
    ```
"""

import asyncio
import json
import logging
import time
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict, deque
import statistics
import re

from ..config import get_settings
from ..logging_config import get_logger
from ..monitoring.structured_logging_service import (
    get_structured_logging_service,
    log_info_structured,
    log_warning_structured,
    log_error_structured
)

logger = get_logger(__name__)


class QueryLogLevel(Enum):
    """Query logging levels."""
    NONE = "none"
    ERROR = "error"
    SLOW = "slow"
    ALL = "all"
    DEBUG = "debug"


class DatabaseType(Enum):
    """Database types for query logging."""
    POSTGRESQL = "postgresql"
    NEO4J = "neo4j"
    MILVUS = "milvus"


class QueryType(Enum):
    """Types of database queries."""
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    CREATE = "CREATE"
    DROP = "DROP"
    ALTER = "ALTER"
    CYPHER_READ = "CYPHER_READ"
    CYPHER_WRITE = "CYPHER_WRITE"
    VECTOR_SEARCH = "VECTOR_SEARCH"
    VECTOR_INSERT = "VECTOR_INSERT"
    COLLECTION_OP = "COLLECTION_OP"
    UNKNOWN = "UNKNOWN"


@dataclass
class QueryLogEntry:
    """Individual query log entry with comprehensive details."""
    # Basic query information
    query_id: str
    timestamp: datetime
    database_type: DatabaseType
    query_type: QueryType
    query_text: str
    query_hash: str
    
    # Execution details
    execution_time_ms: float
    result_count: Optional[int] = None
    affected_rows: Optional[int] = None
    error_message: Optional[str] = None
    
    # Query parameters and context
    parameters: Dict[str, Any] = field(default_factory=dict)
    client_info: Dict[str, str] = field(default_factory=dict)
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    
    # Performance metrics
    cpu_usage_percent: Optional[float] = None
    memory_usage_mb: Optional[float] = None
    disk_io_mb: Optional[float] = None
    network_io_mb: Optional[float] = None
    
    # Query analysis
    is_slow_query: bool = False
    uses_index: Optional[bool] = None
    table_scans: int = 0
    complexity_score: float = 0.0
    optimization_suggestions: List[str] = field(default_factory=list)
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: Set[str] = field(default_factory=set)


@dataclass
class QueryPattern:
    """Pattern analysis for similar queries."""
    pattern_hash: str
    pattern_template: str
    query_count: int
    total_execution_time_ms: float
    avg_execution_time_ms: float
    min_execution_time_ms: float
    max_execution_time_ms: float
    error_count: int
    last_seen: datetime
    databases: Set[DatabaseType] = field(default_factory=set)
    optimization_opportunities: List[str] = field(default_factory=list)


@dataclass
class QueryAnalysisReport:
    """Comprehensive query analysis report."""
    analysis_period: timedelta
    total_queries: int
    queries_by_database: Dict[DatabaseType, int]
    queries_by_type: Dict[QueryType, int]
    
    # Performance metrics
    avg_execution_time_ms: float
    median_execution_time_ms: float
    p95_execution_time_ms: float
    p99_execution_time_ms: float
    
    # Slow queries
    slow_queries: List[QueryLogEntry]
    slow_query_threshold_ms: float
    slow_query_count: int
    slow_query_percentage: float
    
    # Error analysis
    error_queries: List[QueryLogEntry]
    error_count: int
    error_rate: float
    common_errors: Dict[str, int]
    
    # Pattern analysis
    query_patterns: List[QueryPattern]
    most_frequent_patterns: List[QueryPattern]
    slowest_patterns: List[QueryPattern]
    
    # Optimization recommendations
    optimization_recommendations: List[str]
    performance_insights: List[str]
    
    # Resource usage
    avg_cpu_usage: float
    peak_cpu_usage: float
    avg_memory_usage_mb: float
    peak_memory_usage_mb: float


class DatabaseQueryLogger:
    """
    Comprehensive database query logger and analyzer.
    
    This class provides detailed logging and analysis of database queries across
    all database types in the local development environment. It captures execution
    metrics, identifies performance issues, and provides optimization recommendations.
    """
    
    def __init__(
        self,
        log_level: QueryLogLevel = QueryLogLevel.SLOW,
        slow_query_threshold_ms: float = 1000.0,
        max_log_entries: int = 50000,
        analysis_window_hours: int = 24,
        enable_pattern_analysis: bool = True,
        enable_optimization_suggestions: bool = True
    ):
        """
        Initialize the database query logger.
        
        Args:
            log_level: Level of query logging (NONE, ERROR, SLOW, ALL, DEBUG)
            slow_query_threshold_ms: Threshold for slow query detection
            max_log_entries: Maximum number of log entries to keep in memory
            analysis_window_hours: Time window for query analysis
            enable_pattern_analysis: Enable query pattern analysis
            enable_optimization_suggestions: Enable optimization suggestions
        """
        self.log_level = log_level
        self.slow_query_threshold_ms = slow_query_threshold_ms
        self.max_log_entries = max_log_entries
        self.analysis_window = timedelta(hours=analysis_window_hours)
        self.enable_pattern_analysis = enable_pattern_analysis
        self.enable_optimization_suggestions = enable_optimization_suggestions
        
        # Query storage
        self.query_logs: deque[QueryLogEntry] = deque(maxlen=max_log_entries)
        self.query_logs_by_database: Dict[DatabaseType, deque[QueryLogEntry]] = {
            db_type: deque(maxlen=max_log_entries // len(DatabaseType))
            for db_type in DatabaseType
        }
        
        # Pattern analysis
        self.query_patterns: Dict[str, QueryPattern] = {}
        self.pattern_analysis_lock = asyncio.Lock()
        
        # Logging infrastructure
        self.settings = get_settings()
        self.structured_logging = get_structured_logging_service()
        
        # State management
        self.is_active = False
        self._analysis_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        
        # Statistics
        self._query_counter = 0
        self._last_analysis_time = datetime.utcnow()
        
        logger.info(f"Database query logger initialized with level: {log_level.value}")
    
    async def start(self) -> None:
        """Start the database query logger."""
        if self.is_active:
            logger.warning("Database query logger is already active")
            return
        
        self.is_active = True
        
        # Start background tasks
        self._analysis_task = asyncio.create_task(self._periodic_analysis())
        self._cleanup_task = asyncio.create_task(self._periodic_cleanup())
        
        logger.info("Database query logger started")
        
        # Log startup
        log_info_structured(
            service="database_query_logger",
            operation="start",
            message="Database query logger started",
            metadata={
                "log_level": self.log_level.value,
                "slow_query_threshold_ms": self.slow_query_threshold_ms,
                "max_log_entries": self.max_log_entries,
                "analysis_window_hours": self.analysis_window.total_seconds() / 3600
            },
            tags={"category": "query_logging", "action": "start"}
        )
    
    async def stop(self) -> None:
        """Stop the database query logger."""
        if not self.is_active:
            return
        
        self.is_active = False
        
        # Cancel background tasks
        if self._analysis_task:
            self._analysis_task.cancel()
            try:
                await self._analysis_task
            except asyncio.CancelledError:
                pass
        
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Database query logger stopped")
        
        # Log shutdown with final statistics
        log_info_structured(
            service="database_query_logger",
            operation="stop",
            message="Database query logger stopped",
            metadata={
                "total_queries_logged": len(self.query_logs),
                "patterns_identified": len(self.query_patterns),
                "uptime_hours": (datetime.utcnow() - self._last_analysis_time).total_seconds() / 3600
            },
            tags={"category": "query_logging", "action": "stop"}
        )
    
    async def log_query(
        self,
        database_type: str,
        query: str,
        execution_time_ms: float,
        parameters: Optional[Dict[str, Any]] = None,
        result_count: Optional[int] = None,
        affected_rows: Optional[int] = None,
        error_message: Optional[str] = None,
        client_info: Optional[Dict[str, str]] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Log a database query with comprehensive details.
        
        Args:
            database_type: Type of database (postgresql, neo4j, milvus)
            query: The executed query
            execution_time_ms: Query execution time in milliseconds
            parameters: Query parameters
            result_count: Number of results returned
            affected_rows: Number of rows affected (for write operations)
            error_message: Error message if query failed
            client_info: Client connection information
            session_id: Session identifier
            user_id: User identifier
            **kwargs: Additional metadata
            
        Returns:
            Query ID for the logged query
        """
        # Check if we should log this query
        if not self._should_log_query(execution_time_ms, error_message):
            return ""
        
        try:
            # Parse database type
            try:
                db_type = DatabaseType(database_type.lower())
            except ValueError:
                logger.warning(f"Unknown database type: {database_type}")
                db_type = DatabaseType.POSTGRESQL  # Default fallback
            
            # Generate query ID and hash
            self._query_counter += 1
            query_id = f"{db_type.value}_{self._query_counter}_{int(time.time())}"
            query_hash = self._generate_query_hash(query)
            
            # Parse query type
            query_type = self._parse_query_type(query, db_type)
            
            # Analyze query performance
            is_slow_query = execution_time_ms > self.slow_query_threshold_ms
            
            # Create log entry
            log_entry = QueryLogEntry(
                query_id=query_id,
                timestamp=datetime.utcnow(),
                database_type=db_type,
                query_type=query_type,
                query_text=query[:2000],  # Truncate very long queries
                query_hash=query_hash,
                execution_time_ms=execution_time_ms,
                result_count=result_count,
                affected_rows=affected_rows,
                error_message=error_message,
                parameters=parameters or {},
                client_info=client_info or {},
                session_id=session_id,
                user_id=user_id,
                is_slow_query=is_slow_query,
                metadata=kwargs
            )
            
            # Add performance analysis
            if self.enable_optimization_suggestions:
                log_entry.optimization_suggestions = self._generate_optimization_suggestions(log_entry)
                log_entry.complexity_score = self._calculate_complexity_score(log_entry)
            
            # Store the log entry
            self.query_logs.append(log_entry)
            self.query_logs_by_database[db_type].append(log_entry)
            
            # Update pattern analysis
            if self.enable_pattern_analysis:
                await self._update_pattern_analysis(log_entry)
            
            # Log to structured logging service
            await self._log_to_structured_service(log_entry)
            
            # Log slow queries and errors with higher priority
            if is_slow_query:
                log_warning_structured(
                    service="database_query_logger",
                    operation="slow_query_detected",
                    message=f"Slow query detected: {execution_time_ms:.2f}ms",
                    metadata={
                        "query_id": query_id,
                        "database_type": db_type.value,
                        "query_type": query_type.value,
                        "execution_time_ms": execution_time_ms,
                        "threshold_ms": self.slow_query_threshold_ms,
                        "query_hash": query_hash,
                        "optimization_suggestions": log_entry.optimization_suggestions
                    },
                    tags={"category": "slow_query", "database": db_type.value}
                )
            
            if error_message:
                log_error_structured(
                    service="database_query_logger",
                    operation="query_error_detected",
                    message=f"Query error: {error_message}",
                    metadata={
                        "query_id": query_id,
                        "database_type": db_type.value,
                        "query_type": query_type.value,
                        "error_message": error_message,
                        "query_hash": query_hash
                    },
                    tags={"category": "query_error", "database": db_type.value}
                )
            
            return query_id
            
        except Exception as e:
            logger.error(f"Error logging query: {e}")
            return ""
    
    def _should_log_query(self, execution_time_ms: float, error_message: Optional[str]) -> bool:
        """Determine if a query should be logged based on current log level."""
        if self.log_level == QueryLogLevel.NONE:
            return False
        elif self.log_level == QueryLogLevel.ERROR:
            return error_message is not None
        elif self.log_level == QueryLogLevel.SLOW:
            return error_message is not None or execution_time_ms > self.slow_query_threshold_ms
        elif self.log_level in (QueryLogLevel.ALL, QueryLogLevel.DEBUG):
            return True
        
        return False
    
    def _generate_query_hash(self, query: str) -> str:
        """Generate a hash for query pattern analysis."""
        # Normalize query for pattern matching
        normalized = self._normalize_query_for_pattern(query)
        return hashlib.md5(normalized.encode()).hexdigest()[:16]
    
    def _normalize_query_for_pattern(self, query: str) -> str:
        """Normalize query text for pattern analysis."""
        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', query.strip())
        
        # Replace parameter placeholders with generic markers
        normalized = re.sub(r'\$\d+', '$PARAM', normalized)  # PostgreSQL parameters
        normalized = re.sub(r':\w+', ':PARAM', normalized)   # Named parameters
        normalized = re.sub(r'\?', '?PARAM', normalized)     # Question mark parameters
        
        # Replace string literals with generic markers
        normalized = re.sub(r"'[^']*'", "'STRING'", normalized)
        normalized = re.sub(r'"[^"]*"', '"STRING"', normalized)
        
        # Replace numeric literals with generic markers
        normalized = re.sub(r'\b\d+\b', 'NUMBER', normalized)
        normalized = re.sub(r'\b\d+\.\d+\b', 'DECIMAL', normalized)
        
        return normalized.upper()
    
    def _parse_query_type(self, query: str, database_type: DatabaseType) -> QueryType:
        """Parse the type of query from the query text."""
        query_upper = query.strip().upper()
        
        if database_type == DatabaseType.POSTGRESQL:
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
        
        elif database_type == DatabaseType.NEO4J:
            if any(keyword in query_upper for keyword in ['MATCH', 'RETURN', 'WHERE']):
                return QueryType.CYPHER_READ
            elif any(keyword in query_upper for keyword in ['CREATE', 'MERGE', 'SET', 'DELETE', 'REMOVE']):
                return QueryType.CYPHER_WRITE
        
        elif database_type == DatabaseType.MILVUS:
            if 'search' in query.lower():
                return QueryType.VECTOR_SEARCH
            elif 'insert' in query.lower():
                return QueryType.VECTOR_INSERT
            elif any(keyword in query.lower() for keyword in ['create_collection', 'drop_collection', 'load_collection']):
                return QueryType.COLLECTION_OP
        
        return QueryType.UNKNOWN
    
    def _calculate_complexity_score(self, log_entry: QueryLogEntry) -> float:
        """Calculate a complexity score for the query."""
        score = 0.0
        query = log_entry.query_text.upper()
        
        # Base complexity factors
        if 'JOIN' in query:
            score += query.count('JOIN') * 2.0
        if 'SUBQUERY' in query or '(' in query:
            score += query.count('(') * 1.5
        if 'ORDER BY' in query:
            score += 1.0
        if 'GROUP BY' in query:
            score += 1.5
        if 'HAVING' in query:
            score += 1.0
        
        # Neo4j specific complexity
        if log_entry.database_type == DatabaseType.NEO4J:
            if 'MATCH' in query:
                score += query.count('MATCH') * 1.0
            if 'OPTIONAL MATCH' in query:
                score += query.count('OPTIONAL MATCH') * 1.5
            if 'WITH' in query:
                score += query.count('WITH') * 1.0
        
        # Milvus specific complexity
        elif log_entry.database_type == DatabaseType.MILVUS:
            if log_entry.result_count and log_entry.result_count > 1000:
                score += 2.0
        
        # Execution time factor
        if log_entry.execution_time_ms > 100:
            score += log_entry.execution_time_ms / 1000.0
        
        return min(score, 10.0)  # Cap at 10.0
    
    def _generate_optimization_suggestions(self, log_entry: QueryLogEntry) -> List[str]:
        """Generate optimization suggestions for a query."""
        suggestions = []
        query = log_entry.query_text.upper()
        
        # General suggestions
        if log_entry.execution_time_ms > self.slow_query_threshold_ms:
            suggestions.append("Consider optimizing this slow query")
        
        # PostgreSQL specific suggestions
        if log_entry.database_type == DatabaseType.POSTGRESQL:
            if 'SELECT *' in query:
                suggestions.append("Avoid SELECT * - specify only needed columns")
            if 'ORDER BY' in query and 'LIMIT' not in query:
                suggestions.append("Consider adding LIMIT when using ORDER BY")
            if log_entry.result_count and log_entry.result_count > 10000:
                suggestions.append("Large result set - consider pagination")
            if 'WHERE' not in query and 'SELECT' in query:
                suggestions.append("Consider adding WHERE clause to filter results")
        
        # Neo4j specific suggestions
        elif log_entry.database_type == DatabaseType.NEO4J:
            if 'MATCH' in query and 'WHERE' not in query:
                suggestions.append("Consider adding WHERE clause to filter nodes")
            if query.count('MATCH') > 3:
                suggestions.append("Complex query - consider breaking into simpler parts")
            if 'OPTIONAL MATCH' in query:
                suggestions.append("OPTIONAL MATCH can be expensive - ensure it's necessary")
        
        # Milvus specific suggestions
        elif log_entry.database_type == DatabaseType.MILVUS:
            if log_entry.execution_time_ms > 500:
                suggestions.append("Consider adjusting search parameters for better performance")
            if log_entry.result_count and log_entry.result_count > 1000:
                suggestions.append("Large vector search result - consider reducing top_k")
        
        return suggestions
    
    async def _update_pattern_analysis(self, log_entry: QueryLogEntry) -> None:
        """Update query pattern analysis with new log entry."""
        async with self.pattern_analysis_lock:
            pattern_hash = log_entry.query_hash
            
            if pattern_hash in self.query_patterns:
                # Update existing pattern
                pattern = self.query_patterns[pattern_hash]
                pattern.query_count += 1
                pattern.total_execution_time_ms += log_entry.execution_time_ms
                pattern.avg_execution_time_ms = pattern.total_execution_time_ms / pattern.query_count
                pattern.min_execution_time_ms = min(pattern.min_execution_time_ms, log_entry.execution_time_ms)
                pattern.max_execution_time_ms = max(pattern.max_execution_time_ms, log_entry.execution_time_ms)
                pattern.last_seen = log_entry.timestamp
                pattern.databases.add(log_entry.database_type)
                
                if log_entry.error_message:
                    pattern.error_count += 1
            else:
                # Create new pattern
                pattern_template = self._normalize_query_for_pattern(log_entry.query_text)
                
                self.query_patterns[pattern_hash] = QueryPattern(
                    pattern_hash=pattern_hash,
                    pattern_template=pattern_template,
                    query_count=1,
                    total_execution_time_ms=log_entry.execution_time_ms,
                    avg_execution_time_ms=log_entry.execution_time_ms,
                    min_execution_time_ms=log_entry.execution_time_ms,
                    max_execution_time_ms=log_entry.execution_time_ms,
                    error_count=1 if log_entry.error_message else 0,
                    last_seen=log_entry.timestamp,
                    databases={log_entry.database_type}
                )
    
    async def _log_to_structured_service(self, log_entry: QueryLogEntry) -> None:
        """Log query entry to structured logging service."""
        try:
            # Prepare metadata
            metadata = {
                "query_id": log_entry.query_id,
                "database_type": log_entry.database_type.value,
                "query_type": log_entry.query_type.value,
                "query_hash": log_entry.query_hash,
                "execution_time_ms": log_entry.execution_time_ms,
                "result_count": log_entry.result_count,
                "affected_rows": log_entry.affected_rows,
                "is_slow_query": log_entry.is_slow_query,
                "complexity_score": log_entry.complexity_score,
                "client_info": log_entry.client_info,
                "session_id": log_entry.session_id,
                "user_id": log_entry.user_id
            }
            
            # Add parameters if present (but sanitize sensitive data)
            if log_entry.parameters:
                sanitized_params = self._sanitize_parameters(log_entry.parameters)
                metadata["parameters"] = sanitized_params
            
            # Add optimization suggestions
            if log_entry.optimization_suggestions:
                metadata["optimization_suggestions"] = log_entry.optimization_suggestions
            
            # Add error information
            if log_entry.error_message:
                metadata["error_message"] = log_entry.error_message
            
            # Add custom metadata
            if log_entry.metadata:
                metadata.update(log_entry.metadata)
            
            # Prepare tags
            tags = {
                "category": "database_query",
                "database": log_entry.database_type.value,
                "query_type": log_entry.query_type.value
            }
            
            if log_entry.is_slow_query:
                tags["slow_query"] = "true"
            if log_entry.error_message:
                tags["has_error"] = "true"
            
            # Add custom tags
            tags.update(log_entry.tags)
            
            # Log to structured service
            log_level = "ERROR" if log_entry.error_message else "WARNING" if log_entry.is_slow_query else "INFO"
            
            self.structured_logging.log_structured(
                level=log_level,
                service="database_query_logger",
                operation="query_execution",
                message=f"Query executed: {log_entry.query_type.value} on {log_entry.database_type.value}",
                correlation_id=log_entry.query_id,
                metadata=metadata,
                tags=tags
            )
            
        except Exception as e:
            logger.error(f"Error logging to structured service: {e}")
    
    def _sanitize_parameters(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize query parameters to remove sensitive information."""
        sanitized = {}
        
        sensitive_keys = {'password', 'token', 'secret', 'key', 'auth', 'credential'}
        
        for key, value in parameters.items():
            key_lower = key.lower()
            
            # Check if key contains sensitive information
            if any(sensitive_word in key_lower for sensitive_word in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif isinstance(value, str) and len(value) > 100:
                # Truncate very long string values
                sanitized[key] = value[:100] + "..."
            else:
                sanitized[key] = value
        
        return sanitized
    
    async def get_query_analysis(
        self,
        database_type: Optional[str] = None,
        time_window_hours: Optional[int] = None
    ) -> QueryAnalysisReport:
        """
        Generate comprehensive query analysis report.
        
        Args:
            database_type: Filter by specific database type
            time_window_hours: Analysis time window (default: configured window)
            
        Returns:
            Comprehensive query analysis report
        """
        # Determine analysis window
        analysis_window = (
            timedelta(hours=time_window_hours) if time_window_hours
            else self.analysis_window
        )
        cutoff_time = datetime.utcnow() - analysis_window
        
        # Filter queries by time window and database type
        filtered_queries = []
        for query in self.query_logs:
            if query.timestamp >= cutoff_time:
                if not database_type or query.database_type.value == database_type.lower():
                    filtered_queries.append(query)
        
        if not filtered_queries:
            return QueryAnalysisReport(
                analysis_period=analysis_window,
                total_queries=0,
                queries_by_database={},
                queries_by_type={},
                avg_execution_time_ms=0.0,
                median_execution_time_ms=0.0,
                p95_execution_time_ms=0.0,
                p99_execution_time_ms=0.0,
                slow_queries=[],
                slow_query_threshold_ms=self.slow_query_threshold_ms,
                slow_query_count=0,
                slow_query_percentage=0.0,
                error_queries=[],
                error_count=0,
                error_rate=0.0,
                common_errors={},
                query_patterns=[],
                most_frequent_patterns=[],
                slowest_patterns=[],
                optimization_recommendations=[],
                performance_insights=[],
                avg_cpu_usage=0.0,
                peak_cpu_usage=0.0,
                avg_memory_usage_mb=0.0,
                peak_memory_usage_mb=0.0
            )
        
        # Calculate basic statistics
        total_queries = len(filtered_queries)
        execution_times = [q.execution_time_ms for q in filtered_queries]
        
        # Database and query type breakdown
        queries_by_database = defaultdict(int)
        queries_by_type = defaultdict(int)
        
        for query in filtered_queries:
            queries_by_database[query.database_type] += 1
            queries_by_type[query.query_type] += 1
        
        # Performance statistics
        avg_execution_time_ms = statistics.mean(execution_times)
        median_execution_time_ms = statistics.median(execution_times)
        
        sorted_times = sorted(execution_times)
        p95_index = int(0.95 * len(sorted_times))
        p99_index = int(0.99 * len(sorted_times))
        p95_execution_time_ms = sorted_times[p95_index] if p95_index < len(sorted_times) else sorted_times[-1]
        p99_execution_time_ms = sorted_times[p99_index] if p99_index < len(sorted_times) else sorted_times[-1]
        
        # Slow queries analysis
        slow_queries = [q for q in filtered_queries if q.is_slow_query]
        slow_query_count = len(slow_queries)
        slow_query_percentage = (slow_query_count / total_queries) * 100 if total_queries > 0 else 0
        
        # Error analysis
        error_queries = [q for q in filtered_queries if q.error_message]
        error_count = len(error_queries)
        error_rate = (error_count / total_queries) * 100 if total_queries > 0 else 0
        
        common_errors = defaultdict(int)
        for query in error_queries:
            if query.error_message:
                # Simplify error message for grouping
                error_key = query.error_message.split(':')[0] if ':' in query.error_message else query.error_message
                common_errors[error_key] += 1
        
        # Pattern analysis
        relevant_patterns = []
        if self.enable_pattern_analysis:
            for pattern in self.query_patterns.values():
                if pattern.last_seen >= cutoff_time:
                    relevant_patterns.append(pattern)
        
        # Sort patterns by frequency and performance
        most_frequent_patterns = sorted(relevant_patterns, key=lambda p: p.query_count, reverse=True)[:10]
        slowest_patterns = sorted(relevant_patterns, key=lambda p: p.avg_execution_time_ms, reverse=True)[:10]
        
        # Resource usage analysis
        cpu_usages = [q.cpu_usage_percent for q in filtered_queries if q.cpu_usage_percent is not None]
        memory_usages = [q.memory_usage_mb for q in filtered_queries if q.memory_usage_mb is not None]
        
        avg_cpu_usage = statistics.mean(cpu_usages) if cpu_usages else 0.0
        peak_cpu_usage = max(cpu_usages) if cpu_usages else 0.0
        avg_memory_usage_mb = statistics.mean(memory_usages) if memory_usages else 0.0
        peak_memory_usage_mb = max(memory_usages) if memory_usages else 0.0
        
        # Generate optimization recommendations
        optimization_recommendations = self._generate_analysis_recommendations(
            filtered_queries, slow_queries, error_queries, relevant_patterns
        )
        
        # Generate performance insights
        performance_insights = self._generate_performance_insights(
            filtered_queries, avg_execution_time_ms, slow_query_percentage, error_rate
        )
        
        return QueryAnalysisReport(
            analysis_period=analysis_window,
            total_queries=total_queries,
            queries_by_database=dict(queries_by_database),
            queries_by_type=dict(queries_by_type),
            avg_execution_time_ms=avg_execution_time_ms,
            median_execution_time_ms=median_execution_time_ms,
            p95_execution_time_ms=p95_execution_time_ms,
            p99_execution_time_ms=p99_execution_time_ms,
            slow_queries=slow_queries[:20],  # Limit to top 20 slow queries
            slow_query_threshold_ms=self.slow_query_threshold_ms,
            slow_query_count=slow_query_count,
            slow_query_percentage=slow_query_percentage,
            error_queries=error_queries[:20],  # Limit to top 20 error queries
            error_count=error_count,
            error_rate=error_rate,
            common_errors=dict(common_errors),
            query_patterns=relevant_patterns,
            most_frequent_patterns=most_frequent_patterns,
            slowest_patterns=slowest_patterns,
            optimization_recommendations=optimization_recommendations,
            performance_insights=performance_insights,
            avg_cpu_usage=avg_cpu_usage,
            peak_cpu_usage=peak_cpu_usage,
            avg_memory_usage_mb=avg_memory_usage_mb,
            peak_memory_usage_mb=peak_memory_usage_mb
        )
    
    def _generate_analysis_recommendations(
        self,
        all_queries: List[QueryLogEntry],
        slow_queries: List[QueryLogEntry],
        error_queries: List[QueryLogEntry],
        patterns: List[QueryPattern]
    ) -> List[str]:
        """Generate optimization recommendations based on query analysis."""
        recommendations = []
        
        # Slow query recommendations
        if slow_queries:
            slow_percentage = (len(slow_queries) / len(all_queries)) * 100
            if slow_percentage > 10:
                recommendations.append(f"High percentage of slow queries ({slow_percentage:.1f}%) - review query optimization")
            
            # Database-specific recommendations
            slow_by_db = defaultdict(int)
            for query in slow_queries:
                slow_by_db[query.database_type] += 1
            
            for db_type, count in slow_by_db.items():
                if count > 5:
                    if db_type == DatabaseType.POSTGRESQL:
                        recommendations.append("Consider adding indexes for PostgreSQL slow queries")
                    elif db_type == DatabaseType.NEO4J:
                        recommendations.append("Consider optimizing Cypher queries and adding node indexes")
                    elif db_type == DatabaseType.MILVUS:
                        recommendations.append("Consider optimizing vector search parameters and index configuration")
        
        # Error recommendations
        if error_queries:
            error_percentage = (len(error_queries) / len(all_queries)) * 100
            if error_percentage > 5:
                recommendations.append(f"High error rate ({error_percentage:.1f}%) - investigate query failures")
        
        # Pattern-based recommendations
        if patterns:
            frequent_slow_patterns = [p for p in patterns if p.query_count > 10 and p.avg_execution_time_ms > 500]
            if frequent_slow_patterns:
                recommendations.append("Frequently executed slow query patterns detected - prioritize optimization")
        
        return recommendations
    
    def _generate_performance_insights(
        self,
        queries: List[QueryLogEntry],
        avg_time: float,
        slow_percentage: float,
        error_rate: float
    ) -> List[str]:
        """Generate performance insights from query analysis."""
        insights = []
        
        # Performance insights
        if avg_time < 100:
            insights.append("Overall query performance is good (avg < 100ms)")
        elif avg_time < 500:
            insights.append("Query performance is acceptable (avg < 500ms)")
        else:
            insights.append("Query performance needs attention (avg > 500ms)")
        
        # Slow query insights
        if slow_percentage < 5:
            insights.append("Low percentage of slow queries - good performance")
        elif slow_percentage < 15:
            insights.append("Moderate percentage of slow queries - room for improvement")
        else:
            insights.append("High percentage of slow queries - optimization needed")
        
        # Error rate insights
        if error_rate < 1:
            insights.append("Low error rate - queries are generally successful")
        elif error_rate < 5:
            insights.append("Moderate error rate - some queries failing")
        else:
            insights.append("High error rate - investigate query failures")
        
        # Query distribution insights
        db_distribution = defaultdict(int)
        for query in queries:
            db_distribution[query.database_type] += 1
        
        if len(db_distribution) > 1:
            most_used_db = max(db_distribution.items(), key=lambda x: x[1])
            insights.append(f"Most queries target {most_used_db[0].value} ({most_used_db[1]} queries)")
        
        return insights
    
    async def _periodic_analysis(self) -> None:
        """Perform periodic query analysis and reporting."""
        while self.is_active:
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                if not self.is_active:
                    break
                
                # Generate analysis report
                analysis = await self.get_query_analysis()
                
                # Log analysis summary
                log_info_structured(
                    service="database_query_logger",
                    operation="periodic_analysis",
                    message="Periodic query analysis completed",
                    metadata={
                        "total_queries": analysis.total_queries,
                        "avg_execution_time_ms": analysis.avg_execution_time_ms,
                        "slow_query_count": analysis.slow_query_count,
                        "slow_query_percentage": analysis.slow_query_percentage,
                        "error_count": analysis.error_count,
                        "error_rate": analysis.error_rate,
                        "patterns_identified": len(analysis.query_patterns)
                    },
                    tags={"category": "query_analysis", "type": "periodic"}
                )
                
                # Log recommendations if any
                if analysis.optimization_recommendations:
                    log_warning_structured(
                        service="database_query_logger",
                        operation="optimization_recommendations",
                        message="Query optimization recommendations available",
                        metadata={
                            "recommendations": analysis.optimization_recommendations,
                            "performance_insights": analysis.performance_insights
                        },
                        tags={"category": "optimization", "type": "recommendations"}
                    )
                
            except Exception as e:
                logger.error(f"Error in periodic analysis: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes before retrying
    
    async def _periodic_cleanup(self) -> None:
        """Perform periodic cleanup of old data."""
        while self.is_active:
            try:
                await asyncio.sleep(86400)  # Run daily
                
                if not self.is_active:
                    break
                
                # Clean up old patterns
                cutoff_time = datetime.utcnow() - timedelta(days=7)
                patterns_to_remove = []
                
                async with self.pattern_analysis_lock:
                    for pattern_hash, pattern in self.query_patterns.items():
                        if pattern.last_seen < cutoff_time:
                            patterns_to_remove.append(pattern_hash)
                    
                    for pattern_hash in patterns_to_remove:
                        del self.query_patterns[pattern_hash]
                
                logger.info(f"Cleaned up {len(patterns_to_remove)} old query patterns")
                
            except Exception as e:
                logger.error(f"Error in periodic cleanup: {e}")
                await asyncio.sleep(3600)  # Wait 1 hour before retrying
    
    async def export_analysis_report(self, filepath: str) -> str:
        """Export query analysis report to JSON file."""
        try:
            analysis = await self.get_query_analysis()
            
            # Convert to serializable format
            report_data = {
                "generated_at": datetime.utcnow().isoformat(),
                "analysis_period_hours": analysis.analysis_period.total_seconds() / 3600,
                "summary": {
                    "total_queries": analysis.total_queries,
                    "avg_execution_time_ms": analysis.avg_execution_time_ms,
                    "median_execution_time_ms": analysis.median_execution_time_ms,
                    "p95_execution_time_ms": analysis.p95_execution_time_ms,
                    "p99_execution_time_ms": analysis.p99_execution_time_ms,
                    "slow_query_count": analysis.slow_query_count,
                    "slow_query_percentage": analysis.slow_query_percentage,
                    "error_count": analysis.error_count,
                    "error_rate": analysis.error_rate
                },
                "queries_by_database": {k.value: v for k, v in analysis.queries_by_database.items()},
                "queries_by_type": {k.value: v for k, v in analysis.queries_by_type.items()},
                "slow_queries": [asdict(q) for q in analysis.slow_queries[:10]],
                "error_queries": [asdict(q) for q in analysis.error_queries[:10]],
                "common_errors": analysis.common_errors,
                "optimization_recommendations": analysis.optimization_recommendations,
                "performance_insights": analysis.performance_insights,
                "resource_usage": {
                    "avg_cpu_usage": analysis.avg_cpu_usage,
                    "peak_cpu_usage": analysis.peak_cpu_usage,
                    "avg_memory_usage_mb": analysis.avg_memory_usage_mb,
                    "peak_memory_usage_mb": analysis.peak_memory_usage_mb
                }
            }
            
            # Write to file
            with open(filepath, 'w') as f:
                json.dump(report_data, f, indent=2, default=str)
            
            logger.info(f"Query analysis report exported to {filepath}")
            return filepath
            
        except Exception as e:
            logger.error(f"Error exporting analysis report: {e}")
            raise


# Global instance for easy access
_global_query_logger: Optional[DatabaseQueryLogger] = None


def get_database_query_logger() -> DatabaseQueryLogger:
    """Get the global database query logger instance."""
    global _global_query_logger
    
    if _global_query_logger is None:
        settings = get_settings()
        
        # Configure based on settings
        log_level = QueryLogLevel.ALL if getattr(settings, 'enable_query_logging', False) else QueryLogLevel.SLOW
        slow_threshold = getattr(settings, 'slow_query_threshold_ms', 1000.0)
        
        _global_query_logger = DatabaseQueryLogger(
            log_level=log_level,
            slow_query_threshold_ms=slow_threshold
        )
    
    return _global_query_logger


async def start_query_logging() -> None:
    """Start the global query logging service."""
    logger_instance = get_database_query_logger()
    await logger_instance.start()


async def stop_query_logging() -> None:
    """Stop the global query logging service."""
    global _global_query_logger
    if _global_query_logger:
        await _global_query_logger.stop()