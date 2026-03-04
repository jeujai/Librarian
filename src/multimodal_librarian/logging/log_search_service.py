"""
Log Search Service for Local Development

This module provides comprehensive log search and aggregation capabilities
specifically designed for local development environments. It integrates with
the existing logging infrastructure to provide powerful search, filtering,
and analysis capabilities.

Key Features:
- Full-text search across all log entries
- Advanced filtering by service, level, time range, user, etc.
- Real-time log streaming and monitoring
- Log pattern detection and analysis
- Export capabilities for external analysis
- Integration with Docker container logs
"""

import asyncio
import json
import logging
import os
import re
import sqlite3
import threading
import time
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple, Union
from dataclasses import dataclass, asdict
from enum import Enum
import docker
import aiofiles
import subprocess

logger = logging.getLogger(__name__)


class LogLevel(Enum):
    """Log levels for filtering."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogSource(Enum):
    """Sources of log data."""
    APPLICATION = "application"
    POSTGRES = "postgres"
    NEO4J = "neo4j"
    MILVUS = "milvus"
    REDIS = "redis"
    DOCKER = "docker"
    SYSTEM = "system"


@dataclass
class LogEntry:
    """Structured log entry for search and analysis."""
    id: str
    timestamp: datetime
    level: str
    source: LogSource
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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        data['source'] = self.source.value
        return data
    
    def matches_query(self, query: str) -> bool:
        """Check if log entry matches search query."""
        query_lower = query.lower()
        
        # Search in main fields
        if (query_lower in self.message.lower() or
            query_lower in self.raw_message.lower() or
            query_lower in self.service.lower()):
            return True
        
        # Search in metadata
        if any(query_lower in str(v).lower() for v in self.metadata.values()):
            return True
        
        # Search in error details
        if self.error_type and query_lower in self.error_type.lower():
            return True
        
        if self.stack_trace and query_lower in self.stack_trace.lower():
            return True
        
        return False


@dataclass
class SearchFilter:
    """Filter criteria for log search."""
    query: Optional[str] = None
    level: Optional[LogLevel] = None
    source: Optional[LogSource] = None
    service: Optional[str] = None
    user_id: Optional[str] = None
    correlation_id: Optional[str] = None
    error_type: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    has_error: Optional[bool] = None
    has_duration: Optional[bool] = None
    min_duration_ms: Optional[float] = None
    max_duration_ms: Optional[float] = None
    container_name: Optional[str] = None
    limit: int = 1000
    offset: int = 0


@dataclass
class SearchResult:
    """Result of log search operation."""
    entries: List[LogEntry]
    total_count: int
    filtered_count: int
    search_time_ms: float
    filters_applied: Dict[str, Any]
    aggregations: Dict[str, Any]


class LogSearchService:
    """
    Comprehensive log search service for local development environments.
    
    Provides advanced search, filtering, and analysis capabilities across
    all log sources including application logs, database logs, and container logs.
    """
    
    def __init__(self, db_path: Optional[str] = None, enable_docker_logs: bool = True):
        """Initialize the log search service."""
        self.db_path = db_path or os.path.join(os.getcwd(), "logs", "log_search.db")
        self.enable_docker_logs = enable_docker_logs
        
        # Ensure logs directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # Initialize database
        self._init_database()
        
        # Docker client for container log access
        self.docker_client = None
        if enable_docker_logs:
            try:
                self.docker_client = docker.from_env()
            except Exception as e:
                logger.warning(f"Docker client not available: {e}")
        
        # In-memory cache for recent logs
        self.log_cache: List[LogEntry] = []
        self.cache_lock = threading.Lock()
        self.cache_size_limit = 10000
        
        # Background processing
        self.processing_thread: Optional[threading.Thread] = None
        self.stop_processing = threading.Event()
        self.processing_interval = 5  # Process every 5 seconds
        
        # Log file watchers
        self.log_watchers: Dict[str, Any] = {}
        
        logger.info("LogSearchService initialized", extra={
            "db_path": self.db_path,
            "enable_docker_logs": enable_docker_logs,
            "cache_size_limit": self.cache_size_limit
        })
    
    def _init_database(self) -> None:
        """Initialize SQLite database for log storage and indexing."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create main logs table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS log_entries (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    source TEXT NOT NULL,
                    service TEXT NOT NULL,
                    message TEXT NOT NULL,
                    raw_message TEXT NOT NULL,
                    metadata TEXT,
                    container_id TEXT,
                    container_name TEXT,
                    user_id TEXT,
                    correlation_id TEXT,
                    error_type TEXT,
                    stack_trace TEXT,
                    duration_ms REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for efficient searching
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_timestamp ON log_entries(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_level ON log_entries(level)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_source ON log_entries(source)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_service ON log_entries(service)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_user_id ON log_entries(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_correlation_id ON log_entries(correlation_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_error_type ON log_entries(error_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_log_container_name ON log_entries(container_name)")
            
            # Full-text search index
            cursor.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS log_fts USING fts5(
                    id UNINDEXED,
                    message,
                    raw_message,
                    service,
                    error_type,
                    stack_trace,
                    content='log_entries',
                    content_rowid='rowid'
                )
            """)
            
            # Create triggers to maintain FTS index
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS log_fts_insert AFTER INSERT ON log_entries BEGIN
                    INSERT INTO log_fts(id, message, raw_message, service, error_type, stack_trace)
                    VALUES (new.id, new.message, new.raw_message, new.service, new.error_type, new.stack_trace);
                END
            """)
            
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS log_fts_delete AFTER DELETE ON log_entries BEGIN
                    DELETE FROM log_fts WHERE id = old.id;
                END
            """)
            
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS log_fts_update AFTER UPDATE ON log_entries BEGIN
                    DELETE FROM log_fts WHERE id = old.id;
                    INSERT INTO log_fts(id, message, raw_message, service, error_type, stack_trace)
                    VALUES (new.id, new.message, new.raw_message, new.service, new.error_type, new.stack_trace);
                END
            """)
            
            conn.commit()
    
    async def start_service(self) -> None:
        """Start the log search service and background processing."""
        if self.processing_thread and self.processing_thread.is_alive():
            logger.warning("Log search service already running")
            return
        
        self.stop_processing.clear()
        self.processing_thread = threading.Thread(
            target=self._background_processing_loop,
            name="LogSearchProcessor",
            daemon=True
        )
        self.processing_thread.start()
        
        # Start log file watchers
        await self._start_log_watchers()
        
        logger.info("Log search service started")
    
    async def initialize(self) -> None:
        """Initialize and start the log search service."""
        await self.start_service()
    
    async def get_container_logs(self, container_name: Optional[str] = None, 
                                lines: int = 100) -> List[LogEntry]:
        """Get logs from Docker containers."""
        if not self.docker_client:
            logger.warning("Docker client not available")
            return []
        
        logs = []
        try:
            if container_name:
                # Get logs from specific container
                try:
                    container = self.docker_client.containers.get(container_name)
                    container_logs = container.logs(tail=lines, timestamps=True).decode('utf-8')
                    self._parse_docker_logs(container, container_logs)
                except Exception as e:
                    logger.warning(f"Failed to get logs from container {container_name}: {e}")
            else:
                # Get logs from all containers
                containers = self.docker_client.containers.list()
                for container in containers:
                    try:
                        container_logs = container.logs(tail=lines//len(containers) if containers else lines, 
                                                      timestamps=True).decode('utf-8')
                        self._parse_docker_logs(container, container_logs)
                    except Exception as e:
                        logger.debug(f"Failed to get logs from container {container.name}: {e}")
            
            # Return recent logs from cache that match container filter
            with self.cache_lock:
                if container_name:
                    logs = [entry for entry in self.log_cache 
                           if entry.container_name == container_name]
                else:
                    logs = [entry for entry in self.log_cache 
                           if entry.source == LogSource.DOCKER]
                
                # Sort by timestamp and limit
                logs.sort(key=lambda x: x.timestamp, reverse=True)
                logs = logs[:lines]
        
        except Exception as e:
            logger.error(f"Failed to get container logs: {e}")
        
        return logs
    
    async def stop_service(self) -> None:
        """Stop the log search service and cleanup resources."""
        if self.processing_thread and self.processing_thread.is_alive():
            self.stop_processing.set()
            self.processing_thread.join(timeout=10)
        
        # Stop log watchers
        await self._stop_log_watchers()
        
        logger.info("Log search service stopped")
    
    def _background_processing_loop(self) -> None:
        """Background processing loop for log collection and indexing."""
        while not self.stop_processing.is_set():
            try:
                # Collect logs from various sources
                self._collect_docker_logs()
                self._collect_application_logs()
                self._process_log_cache()
                
                # Cleanup old logs
                self._cleanup_old_logs()
                
            except Exception as e:
                logger.error(f"Error in log search background processing: {str(e)}", exc_info=True)
            
            # Wait for next processing cycle
            self.stop_processing.wait(self.processing_interval)
    
    def _collect_docker_logs(self) -> None:
        """Collect logs from Docker containers."""
        if not self.docker_client:
            return
        
        try:
            # Get containers for the multimodal librarian project
            containers = self.docker_client.containers.list(
                filters={"network": "multimodal-librarian-local"}
            )
            
            for container in containers:
                try:
                    # Get recent logs (last 100 lines)
                    logs = container.logs(
                        tail=100,
                        since=datetime.now() - timedelta(minutes=5),
                        timestamps=True
                    ).decode('utf-8', errors='ignore')
                    
                    if logs.strip():
                        self._parse_docker_logs(container, logs)
                        
                except Exception as e:
                    logger.debug(f"Failed to collect logs from container {container.name}: {e}")
                    
        except Exception as e:
            logger.debug(f"Failed to collect Docker logs: {e}")
    
    def _parse_docker_logs(self, container, logs: str) -> None:
        """Parse Docker container logs and add to cache."""
        container_name = container.name
        container_id = container.id[:12]
        
        # Determine log source based on container name
        if "postgres" in container_name:
            source = LogSource.POSTGRES
        elif "neo4j" in container_name:
            source = LogSource.NEO4J
        elif "milvus" in container_name:
            source = LogSource.MILVUS
        elif "redis" in container_name:
            source = LogSource.REDIS
        else:
            source = LogSource.DOCKER
        
        for line in logs.strip().split('\n'):
            if not line.strip():
                continue
            
            try:
                # Parse timestamp and message from Docker log format
                # Format: 2024-01-01T12:00:00.000000000Z message
                parts = line.split(' ', 1)
                if len(parts) < 2:
                    continue
                
                timestamp_str, message = parts
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                
                # Parse log level from message
                level = self._extract_log_level(message)
                
                # Create log entry
                log_entry = LogEntry(
                    id=f"{container_id}_{int(timestamp.timestamp() * 1000000)}",
                    timestamp=timestamp,
                    level=level,
                    source=source,
                    service=container_name,
                    message=self._clean_message(message),
                    raw_message=message,
                    metadata=self._extract_metadata(message, source),
                    container_id=container_id,
                    container_name=container_name
                )
                
                # Add to cache
                with self.cache_lock:
                    self.log_cache.append(log_entry)
                    
                    # Limit cache size
                    if len(self.log_cache) > self.cache_size_limit:
                        self.log_cache = self.log_cache[-self.cache_size_limit:]
                        
            except Exception as e:
                logger.debug(f"Failed to parse Docker log line: {line[:100]}... Error: {e}")
    
    def _collect_application_logs(self) -> None:
        """Collect logs from application log files."""
        log_dirs = [
            "./logs",
            "./audit_logs",
            "/app/logs",
            "/app/audit_logs"
        ]
        
        for log_dir in log_dirs:
            if os.path.exists(log_dir):
                self._scan_log_directory(log_dir)
    
    def _scan_log_directory(self, log_dir: str) -> None:
        """Scan directory for log files and process new entries."""
        try:
            for log_file in Path(log_dir).glob("*.log"):
                if log_file.stat().st_mtime > time.time() - 300:  # Modified in last 5 minutes
                    self._process_log_file(log_file)
        except Exception as e:
            logger.debug(f"Failed to scan log directory {log_dir}: {e}")
    
    def _process_log_file(self, log_file: Path) -> None:
        """Process individual log file for new entries."""
        try:
            # Read last few lines of the file
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
                
            # Process recent lines (last 50)
            for line in lines[-50:]:
                if not line.strip():
                    continue
                
                try:
                    # Try to parse as JSON (structured log)
                    if line.strip().startswith('{'):
                        log_data = json.loads(line.strip())
                        log_entry = self._parse_structured_log(log_data, log_file.name)
                    else:
                        # Parse as plain text log
                        log_entry = self._parse_plain_log(line.strip(), log_file.name)
                    
                    if log_entry:
                        with self.cache_lock:
                            self.log_cache.append(log_entry)
                            
                except Exception as e:
                    logger.debug(f"Failed to parse log line from {log_file}: {e}")
                    
        except Exception as e:
            logger.debug(f"Failed to process log file {log_file}: {e}")
    
    def _parse_structured_log(self, log_data: Dict[str, Any], filename: str) -> Optional[LogEntry]:
        """Parse structured JSON log entry."""
        try:
            timestamp = datetime.fromisoformat(log_data.get('timestamp', datetime.now().isoformat()))
            
            return LogEntry(
                id=f"app_{int(timestamp.timestamp() * 1000000)}_{hash(str(log_data)) % 10000}",
                timestamp=timestamp,
                level=log_data.get('level', 'INFO'),
                source=LogSource.APPLICATION,
                service=log_data.get('logger', log_data.get('service', filename)),
                message=log_data.get('message', ''),
                raw_message=json.dumps(log_data),
                metadata=log_data,
                user_id=log_data.get('user_id'),
                correlation_id=log_data.get('correlation_id'),
                error_type=log_data.get('error_type'),
                stack_trace=log_data.get('stack_trace'),
                duration_ms=log_data.get('duration_ms')
            )
        except Exception as e:
            logger.debug(f"Failed to parse structured log: {e}")
            return None
    
    def _parse_plain_log(self, line: str, filename: str) -> Optional[LogEntry]:
        """Parse plain text log entry."""
        try:
            # Extract timestamp (various formats)
            timestamp_match = re.search(r'(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2})', line)
            if timestamp_match:
                timestamp = datetime.fromisoformat(timestamp_match.group(1).replace(' ', 'T'))
            else:
                timestamp = datetime.now()
            
            # Extract log level
            level = self._extract_log_level(line)
            
            return LogEntry(
                id=f"plain_{int(timestamp.timestamp() * 1000000)}_{hash(line) % 10000}",
                timestamp=timestamp,
                level=level,
                source=LogSource.APPLICATION,
                service=filename,
                message=self._clean_message(line),
                raw_message=line,
                metadata={}
            )
        except Exception as e:
            logger.debug(f"Failed to parse plain log: {e}")
            return None
    
    def _extract_log_level(self, message: str) -> str:
        """Extract log level from message."""
        message_upper = message.upper()
        
        for level in ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']:
            if level in message_upper:
                return level
        
        return 'INFO'
    
    def _clean_message(self, message: str) -> str:
        """Clean and normalize log message."""
        # Remove timestamp prefixes
        message = re.sub(r'^\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}[^\s]*\s*', '', message)
        
        # Remove log level prefixes
        message = re.sub(r'^(CRITICAL|ERROR|WARNING|INFO|DEBUG):\s*', '', message, flags=re.IGNORECASE)
        
        # Remove container/service prefixes
        message = re.sub(r'^\[[^\]]+\]\s*', '', message)
        
        return message.strip()
    
    def _extract_metadata(self, message: str, source: LogSource) -> Dict[str, Any]:
        """Extract metadata from log message based on source."""
        metadata = {}
        
        if source == LogSource.POSTGRES:
            # Extract SQL statements, user info, etc.
            if 'STATEMENT:' in message:
                statement_match = re.search(r'STATEMENT:\s*(.+)', message)
                if statement_match:
                    metadata['sql_statement'] = statement_match.group(1).strip()
            
            if 'user=' in message:
                user_match = re.search(r'user=(\w+)', message)
                if user_match:
                    metadata['db_user'] = user_match.group(1)
        
        elif source == LogSource.NEO4J:
            # Extract Cypher queries, transaction info, etc.
            if 'Query:' in message:
                query_match = re.search(r'Query:\s*(.+)', message)
                if query_match:
                    metadata['cypher_query'] = query_match.group(1).strip()
        
        elif source == LogSource.MILVUS:
            # Extract collection info, operations, etc.
            if 'collection' in message.lower():
                collection_match = re.search(r'collection[:\s]+(\w+)', message, re.IGNORECASE)
                if collection_match:
                    metadata['collection'] = collection_match.group(1)
        
        return metadata
    
    def _process_log_cache(self) -> None:
        """Process cached logs and store in database."""
        if not self.log_cache:
            return
        
        with self.cache_lock:
            logs_to_process = self.log_cache.copy()
            self.log_cache.clear()
        
        # Store in database
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for log_entry in logs_to_process:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO log_entries 
                        (id, timestamp, level, source, service, message, raw_message, 
                         metadata, container_id, container_name, user_id, correlation_id, 
                         error_type, stack_trace, duration_ms)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        log_entry.id,
                        log_entry.timestamp.isoformat(),
                        log_entry.level,
                        log_entry.source.value,
                        log_entry.service,
                        log_entry.message,
                        log_entry.raw_message,
                        json.dumps(log_entry.metadata) if log_entry.metadata else None,
                        log_entry.container_id,
                        log_entry.container_name,
                        log_entry.user_id,
                        log_entry.correlation_id,
                        log_entry.error_type,
                        log_entry.stack_trace,
                        log_entry.duration_ms
                    ))
                except Exception as e:
                    logger.debug(f"Failed to store log entry {log_entry.id}: {e}")
            
            conn.commit()
        
        logger.debug(f"Processed {len(logs_to_process)} log entries")
    
    def _cleanup_old_logs(self) -> None:
        """Clean up old log entries based on retention policy."""
        cutoff_date = datetime.now() - timedelta(days=7)  # Keep 7 days
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM log_entries 
                WHERE timestamp < ?
            """, (cutoff_date.isoformat(),))
            
            deleted_count = cursor.rowcount
            conn.commit()
            
            if deleted_count > 0:
                logger.debug(f"Cleaned up {deleted_count} old log entries")
    
    async def search_logs(self, search_filter: SearchFilter) -> SearchResult:
        """Search logs with advanced filtering and aggregation."""
        start_time = time.time()
        
        # Build SQL query
        query_parts = []
        params = []
        
        # Base query
        if search_filter.query:
            # Use FTS for text search
            query_parts.append("""
                SELECT l.* FROM log_entries l
                JOIN log_fts fts ON l.id = fts.id
                WHERE fts MATCH ?
            """)
            params.append(search_filter.query)
        else:
            query_parts.append("SELECT * FROM log_entries WHERE 1=1")
        
        # Add filters
        if search_filter.level:
            query_parts.append("AND level = ?")
            params.append(search_filter.level.value)
        
        if search_filter.source:
            query_parts.append("AND source = ?")
            params.append(search_filter.source.value)
        
        if search_filter.service:
            query_parts.append("AND service LIKE ?")
            params.append(f"%{search_filter.service}%")
        
        if search_filter.user_id:
            query_parts.append("AND user_id = ?")
            params.append(search_filter.user_id)
        
        if search_filter.correlation_id:
            query_parts.append("AND correlation_id = ?")
            params.append(search_filter.correlation_id)
        
        if search_filter.error_type:
            query_parts.append("AND error_type = ?")
            params.append(search_filter.error_type)
        
        if search_filter.start_time:
            query_parts.append("AND timestamp >= ?")
            params.append(search_filter.start_time.isoformat())
        
        if search_filter.end_time:
            query_parts.append("AND timestamp <= ?")
            params.append(search_filter.end_time.isoformat())
        
        if search_filter.has_error is not None:
            if search_filter.has_error:
                query_parts.append("AND (level IN ('ERROR', 'CRITICAL') OR error_type IS NOT NULL)")
            else:
                query_parts.append("AND level NOT IN ('ERROR', 'CRITICAL') AND error_type IS NULL")
        
        if search_filter.has_duration is not None:
            if search_filter.has_duration:
                query_parts.append("AND duration_ms IS NOT NULL")
            else:
                query_parts.append("AND duration_ms IS NULL")
        
        if search_filter.min_duration_ms is not None:
            query_parts.append("AND duration_ms >= ?")
            params.append(search_filter.min_duration_ms)
        
        if search_filter.max_duration_ms is not None:
            query_parts.append("AND duration_ms <= ?")
            params.append(search_filter.max_duration_ms)
        
        if search_filter.container_name:
            query_parts.append("AND container_name LIKE ?")
            params.append(f"%{search_filter.container_name}%")
        
        # Add ordering and pagination
        query_parts.append("ORDER BY timestamp DESC")
        query_parts.append("LIMIT ? OFFSET ?")
        params.extend([search_filter.limit, search_filter.offset])
        
        # Execute query
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get total count (without pagination)
            count_query = " ".join(query_parts[:-2]).replace("SELECT *", "SELECT COUNT(*)")
            cursor.execute(count_query, params[:-2])
            total_count = cursor.fetchone()[0]
            
            # Get filtered results
            full_query = " ".join(query_parts)
            cursor.execute(full_query, params)
            
            entries = []
            for row in cursor.fetchall():
                entry = LogEntry(
                    id=row[0],
                    timestamp=datetime.fromisoformat(row[1]),
                    level=row[2],
                    source=LogSource(row[3]),
                    service=row[4],
                    message=row[5],
                    raw_message=row[6],
                    metadata=json.loads(row[7]) if row[7] else {},
                    container_id=row[8],
                    container_name=row[9],
                    user_id=row[10],
                    correlation_id=row[11],
                    error_type=row[12],
                    stack_trace=row[13],
                    duration_ms=row[14]
                )
                entries.append(entry)
        
        # Calculate aggregations
        aggregations = await self._calculate_aggregations(entries)
        
        search_time_ms = (time.time() - start_time) * 1000
        
        return SearchResult(
            entries=entries,
            total_count=total_count,
            filtered_count=len(entries),
            search_time_ms=search_time_ms,
            filters_applied=asdict(search_filter),
            aggregations=aggregations
        )
    
    async def _calculate_aggregations(self, entries: List[LogEntry]) -> Dict[str, Any]:
        """Calculate aggregations for search results."""
        if not entries:
            return {}
        
        level_counts = Counter(entry.level for entry in entries)
        source_counts = Counter(entry.source.value for entry in entries)
        service_counts = Counter(entry.service for entry in entries)
        error_counts = Counter(entry.error_type for entry in entries if entry.error_type)
        
        # Time-based aggregations
        time_buckets = defaultdict(int)
        for entry in entries:
            hour_bucket = entry.timestamp.replace(minute=0, second=0, microsecond=0)
            time_buckets[hour_bucket.isoformat()] += 1
        
        # Duration statistics
        durations = [entry.duration_ms for entry in entries if entry.duration_ms is not None]
        duration_stats = {}
        if durations:
            duration_stats = {
                'count': len(durations),
                'min': min(durations),
                'max': max(durations),
                'avg': sum(durations) / len(durations),
                'median': sorted(durations)[len(durations) // 2]
            }
        
        return {
            'level_distribution': dict(level_counts),
            'source_distribution': dict(source_counts),
            'service_distribution': dict(service_counts),
            'error_distribution': dict(error_counts),
            'time_distribution': dict(time_buckets),
            'duration_statistics': duration_stats,
            'total_entries': len(entries),
            'error_rate': len([e for e in entries if e.level in ['ERROR', 'CRITICAL']]) / len(entries)
        }
    
    async def get_log_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """Get comprehensive log statistics for the specified time period."""
        start_time = datetime.now() - timedelta(hours=hours)
        
        search_filter = SearchFilter(
            start_time=start_time,
            limit=10000  # Get more entries for statistics
        )
        
        result = await self.search_logs(search_filter)
        
        return {
            'time_period_hours': hours,
            'total_logs': result.total_count,
            'logs_per_hour': result.total_count / max(1, hours),
            **result.aggregations
        }
    
    async def export_logs(self, search_filter: SearchFilter, format_type: str = "json") -> str:
        """Export search results in specified format."""
        result = await self.search_logs(search_filter)
        
        if format_type == "json":
            export_data = {
                'search_results': result.entries,
                'metadata': {
                    'total_count': result.total_count,
                    'filtered_count': result.filtered_count,
                    'search_time_ms': result.search_time_ms,
                    'filters_applied': result.filters_applied,
                    'aggregations': result.aggregations,
                    'exported_at': datetime.now().isoformat()
                }
            }
            return json.dumps(export_data, indent=2, default=str)
        
        elif format_type == "csv":
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow([
                'timestamp', 'level', 'source', 'service', 'message',
                'container_name', 'user_id', 'correlation_id', 'error_type', 'duration_ms'
            ])
            
            # Write data
            for entry in result.entries:
                writer.writerow([
                    entry.timestamp.isoformat(),
                    entry.level,
                    entry.source.value,
                    entry.service,
                    entry.message,
                    entry.container_name or '',
                    entry.user_id or '',
                    entry.correlation_id or '',
                    entry.error_type or '',
                    entry.duration_ms or ''
                ])
            
            return output.getvalue()
        
        else:
            raise ValueError(f"Unsupported export format: {format_type}")
    
    async def _start_log_watchers(self) -> None:
        """Start log file watchers for real-time monitoring."""
        # This would implement file system watchers for real-time log monitoring
        # For now, we rely on the background processing loop
        pass
    
    async def _stop_log_watchers(self) -> None:
        """Stop log file watchers."""
        # Cleanup any file watchers
        pass


# Global log search service instance
_log_search_service: Optional[LogSearchService] = None


def get_log_search_service() -> Optional[LogSearchService]:
    """Get the global log search service instance."""
    return _log_search_service


async def initialize_log_search_service(db_path: Optional[str] = None, 
                                      enable_docker_logs: bool = True) -> LogSearchService:
    """Initialize the global log search service."""
    global _log_search_service
    _log_search_service = LogSearchService(db_path, enable_docker_logs)
    await _log_search_service.start_service()
    return _log_search_service


async def cleanup_log_search_service() -> None:
    """Cleanup the global log search service."""
    global _log_search_service
    if _log_search_service:
        await _log_search_service.stop_service()
        _log_search_service = None