"""
Log Aggregation System for Startup Analysis

This module implements comprehensive log aggregation and analysis capabilities
for startup logs, providing insights into performance patterns, error trends,
and optimization opportunities.

Key Features:
- Real-time log aggregation from multiple sources
- Statistical analysis of startup performance
- Error pattern detection and classification
- Performance trend analysis
- Automated insights and recommendations
- Export capabilities for external analysis tools
"""

import json
import logging
import os
import sqlite3
import threading
import time
from collections import defaultdict, Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass, asdict
from enum import Enum
import statistics
import uuid

from .startup_logger import StartupLogEntry, StartupLogger


class AggregationPeriod(Enum):
    """Time periods for log aggregation."""
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    WEEK = "week"


class AnalysisType(Enum):
    """Types of analysis that can be performed."""
    PERFORMANCE = "performance"
    ERROR_PATTERNS = "error_patterns"
    PHASE_TIMING = "phase_timing"
    MODEL_LOADING = "model_loading"
    RESOURCE_USAGE = "resource_usage"
    TRENDS = "trends"


@dataclass
class AggregatedMetric:
    """Aggregated metric data."""
    metric_name: str
    period: str
    timestamp: str
    count: int
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    avg_value: Optional[float] = None
    median_value: Optional[float] = None
    std_dev: Optional[float] = None
    percentile_95: Optional[float] = None
    percentile_99: Optional[float] = None
    metadata: Dict[str, Any] = None


@dataclass
class ErrorPattern:
    """Detected error pattern."""
    pattern_id: str
    error_type: str
    error_message_pattern: str
    occurrence_count: int
    first_seen: str
    last_seen: str
    affected_phases: List[str]
    frequency_per_hour: float
    severity: str
    suggested_actions: List[str]


@dataclass
class PerformanceInsight:
    """Performance analysis insight."""
    insight_id: str
    insight_type: str
    title: str
    description: str
    severity: str
    affected_components: List[str]
    metrics: Dict[str, float]
    recommendations: List[str]
    confidence_score: float


@dataclass
class StartupAnalysisReport:
    """Comprehensive startup analysis report."""
    report_id: str
    generated_at: str
    analysis_period: str
    total_startups: int
    successful_startups: int
    failed_startups: int
    avg_startup_time_ms: float
    median_startup_time_ms: float
    p95_startup_time_ms: float
    p99_startup_time_ms: float
    phase_performance: Dict[str, Dict[str, float]]
    model_loading_performance: Dict[str, Dict[str, float]]
    error_patterns: List[ErrorPattern]
    performance_insights: List[PerformanceInsight]
    trends: Dict[str, List[Dict[str, Any]]]
    recommendations: List[str]


class LogAggregator:
    """
    Comprehensive log aggregation system that collects, analyzes, and provides
    insights from startup logs for performance optimization and debugging.
    """
    
    def __init__(self, db_path: Optional[str] = None, retention_days: int = 30):
        """Initialize the log aggregator."""
        self.db_path = db_path or os.path.join(os.getcwd(), "logs", "startup_analysis.db")
        self.retention_days = retention_days
        
        # Ensure logs directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        # Initialize database
        self._init_database()
        
        # In-memory aggregation buffers
        self.log_buffer: List[StartupLogEntry] = []
        self.buffer_lock = threading.Lock()
        self.buffer_size_limit = 10000
        
        # Analysis cache
        self.analysis_cache: Dict[str, Any] = {}
        self.cache_ttl_seconds = 300  # 5 minutes
        self.cache_timestamps: Dict[str, datetime] = {}
        
        # Background processing
        self.processing_thread: Optional[threading.Thread] = None
        self.stop_processing = threading.Event()
        self.processing_interval = 60  # Process every minute
        
        # Logger for this component
        self.logger = logging.getLogger("log_aggregator")
        
        self.logger.info("LogAggregator initialized", extra={
            "db_path": self.db_path,
            "retention_days": retention_days,
            "buffer_size_limit": self.buffer_size_limit
        })
    
    def _init_database(self) -> None:
        """Initialize SQLite database for log storage and analysis."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create tables for log storage
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS startup_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    message TEXT NOT NULL,
                    duration_ms REAL,
                    metadata TEXT,
                    error_details TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create table for aggregated metrics
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS aggregated_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_name TEXT NOT NULL,
                    period TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    count INTEGER NOT NULL,
                    min_value REAL,
                    max_value REAL,
                    avg_value REAL,
                    median_value REAL,
                    std_dev REAL,
                    percentile_95 REAL,
                    percentile_99 REAL,
                    metadata TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create table for error patterns
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS error_patterns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern_id TEXT UNIQUE NOT NULL,
                    error_type TEXT NOT NULL,
                    error_message_pattern TEXT NOT NULL,
                    occurrence_count INTEGER NOT NULL,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    affected_phases TEXT NOT NULL,
                    frequency_per_hour REAL NOT NULL,
                    severity TEXT NOT NULL,
                    suggested_actions TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create table for performance insights
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS performance_insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    insight_id TEXT UNIQUE NOT NULL,
                    insight_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    affected_components TEXT NOT NULL,
                    metrics TEXT NOT NULL,
                    recommendations TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for better query performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_startup_logs_timestamp ON startup_logs(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_startup_logs_event_type ON startup_logs(event_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_startup_logs_phase ON startup_logs(phase)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_startup_logs_level ON startup_logs(level)")
            
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_aggregated_metrics_timestamp ON aggregated_metrics(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_aggregated_metrics_metric_name ON aggregated_metrics(metric_name)")
            
            conn.commit()
    
    def start_background_processing(self) -> None:
        """Start background processing thread for log aggregation."""
        if self.processing_thread and self.processing_thread.is_alive():
            return
        
        self.stop_processing.clear()
        self.processing_thread = threading.Thread(
            target=self._background_processing_loop,
            name="LogAggregatorProcessor",
            daemon=True
        )
        self.processing_thread.start()
        
        self.logger.info("Background processing started")
    
    def stop_background_processing(self) -> None:
        """Stop background processing thread."""
        if self.processing_thread and self.processing_thread.is_alive():
            self.stop_processing.set()
            self.processing_thread.join(timeout=10)
            
        self.logger.info("Background processing stopped")
    
    def _background_processing_loop(self) -> None:
        """Background processing loop for log aggregation and analysis."""
        while not self.stop_processing.is_set():
            try:
                # Process buffered logs
                self._process_log_buffer()
                
                # Perform periodic aggregation
                self._perform_periodic_aggregation()
                
                # Clean up old data
                self._cleanup_old_data()
                
                # Update analysis cache
                self._update_analysis_cache()
                
            except Exception as e:
                self.logger.error(f"Error in background processing: {str(e)}", exc_info=True)
            
            # Wait for next processing cycle
            self.stop_processing.wait(self.processing_interval)
    
    def add_log_entry(self, log_entry: StartupLogEntry) -> None:
        """Add a log entry to the aggregation buffer."""
        with self.buffer_lock:
            self.log_buffer.append(log_entry)
            
            # If buffer is full, process immediately
            if len(self.log_buffer) >= self.buffer_size_limit:
                self._process_log_buffer()
    
    def add_log_entries(self, log_entries: List[StartupLogEntry]) -> None:
        """Add multiple log entries to the aggregation buffer."""
        with self.buffer_lock:
            self.log_buffer.extend(log_entries)
            
            # If buffer is full, process immediately
            if len(self.log_buffer) >= self.buffer_size_limit:
                self._process_log_buffer()
    
    def _process_log_buffer(self) -> None:
        """Process all logs in the buffer and store them in the database."""
        if not self.log_buffer:
            return
        
        with self.buffer_lock:
            logs_to_process = self.log_buffer.copy()
            self.log_buffer.clear()
        
        # Store logs in database
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for log_entry in logs_to_process:
                cursor.execute("""
                    INSERT INTO startup_logs 
                    (timestamp, level, event_type, phase, message, duration_ms, metadata, error_details)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    log_entry.timestamp,
                    log_entry.level,
                    log_entry.event_type,
                    log_entry.phase,
                    log_entry.message,
                    log_entry.duration_ms,
                    json.dumps(log_entry.metadata) if log_entry.metadata else None,
                    json.dumps(log_entry.error_details) if log_entry.error_details else None
                ))
            
            conn.commit()
        
        self.logger.debug(f"Processed {len(logs_to_process)} log entries")
    
    def _perform_periodic_aggregation(self) -> None:
        """Perform periodic aggregation of metrics."""
        current_time = datetime.now()
        
        # Aggregate metrics for different time periods
        for period in AggregationPeriod:
            self._aggregate_metrics_for_period(period, current_time)
    
    def _aggregate_metrics_for_period(self, period: AggregationPeriod, current_time: datetime) -> None:
        """Aggregate metrics for a specific time period."""
        # Calculate time window based on period
        if period == AggregationPeriod.MINUTE:
            window_start = current_time.replace(second=0, microsecond=0) - timedelta(minutes=1)
            window_end = current_time.replace(second=0, microsecond=0)
        elif period == AggregationPeriod.HOUR:
            window_start = current_time.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
            window_end = current_time.replace(minute=0, second=0, microsecond=0)
        elif period == AggregationPeriod.DAY:
            window_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
            window_end = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        else:  # WEEK
            days_since_monday = current_time.weekday()
            window_start = (current_time.replace(hour=0, minute=0, second=0, microsecond=0) - 
                          timedelta(days=days_since_monday + 7))
            window_end = (current_time.replace(hour=0, minute=0, second=0, microsecond=0) - 
                        timedelta(days=days_since_monday))
        
        # Query logs for the time window
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Aggregate startup times
            cursor.execute("""
                SELECT duration_ms FROM startup_logs 
                WHERE event_type = 'phase_transition_complete' 
                AND phase = 'full' 
                AND timestamp >= ? AND timestamp < ?
                AND duration_ms IS NOT NULL
            """, (window_start.isoformat(), window_end.isoformat()))
            
            startup_times = [row[0] for row in cursor.fetchall()]
            
            if startup_times:
                self._store_aggregated_metric(
                    "startup_time_ms",
                    period.value,
                    window_end.isoformat(),
                    startup_times
                )
            
            # Aggregate model loading times by priority
            for priority in ["essential", "standard", "advanced"]:
                cursor.execute("""
                    SELECT duration_ms FROM startup_logs 
                    WHERE event_type = 'model_loading_complete' 
                    AND timestamp >= ? AND timestamp < ?
                    AND duration_ms IS NOT NULL
                    AND metadata LIKE ?
                """, (window_start.isoformat(), window_end.isoformat(), f'%"priority": "{priority}"%'))
                
                model_times = [row[0] for row in cursor.fetchall()]
                
                if model_times:
                    self._store_aggregated_metric(
                        f"model_loading_time_ms_{priority}",
                        period.value,
                        window_end.isoformat(),
                        model_times
                    )
            
            # Aggregate error counts by type
            cursor.execute("""
                SELECT event_type, COUNT(*) FROM startup_logs 
                WHERE level = 'ERROR' 
                AND timestamp >= ? AND timestamp < ?
                GROUP BY event_type
            """, (window_start.isoformat(), window_end.isoformat()))
            
            for event_type, count in cursor.fetchall():
                self._store_aggregated_metric(
                    f"error_count_{event_type}",
                    period.value,
                    window_end.isoformat(),
                    [count]
                )
    
    def _store_aggregated_metric(self, metric_name: str, period: str, timestamp: str, values: List[float]) -> None:
        """Store aggregated metric in the database."""
        if not values:
            return
        
        # Calculate statistics
        count = len(values)
        min_value = min(values)
        max_value = max(values)
        avg_value = statistics.mean(values)
        median_value = statistics.median(values)
        std_dev = statistics.stdev(values) if len(values) > 1 else 0.0
        
        # Calculate percentiles
        sorted_values = sorted(values)
        percentile_95 = sorted_values[int(0.95 * len(sorted_values))] if len(sorted_values) > 1 else sorted_values[0]
        percentile_99 = sorted_values[int(0.99 * len(sorted_values))] if len(sorted_values) > 1 else sorted_values[0]
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Check if metric already exists for this period
            cursor.execute("""
                SELECT id FROM aggregated_metrics 
                WHERE metric_name = ? AND period = ? AND timestamp = ?
            """, (metric_name, period, timestamp))
            
            if cursor.fetchone():
                # Update existing metric
                cursor.execute("""
                    UPDATE aggregated_metrics 
                    SET count = ?, min_value = ?, max_value = ?, avg_value = ?, 
                        median_value = ?, std_dev = ?, percentile_95 = ?, percentile_99 = ?
                    WHERE metric_name = ? AND period = ? AND timestamp = ?
                """, (count, min_value, max_value, avg_value, median_value, std_dev, 
                     percentile_95, percentile_99, metric_name, period, timestamp))
            else:
                # Insert new metric
                cursor.execute("""
                    INSERT INTO aggregated_metrics 
                    (metric_name, period, timestamp, count, min_value, max_value, avg_value, 
                     median_value, std_dev, percentile_95, percentile_99)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (metric_name, period, timestamp, count, min_value, max_value, avg_value,
                     median_value, std_dev, percentile_95, percentile_99))
            
            conn.commit()
    
    def _cleanup_old_data(self) -> None:
        """Clean up old data based on retention policy."""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Clean up old startup logs
            cursor.execute("""
                DELETE FROM startup_logs 
                WHERE created_at < ?
            """, (cutoff_date.isoformat(),))
            
            # Clean up old aggregated metrics
            cursor.execute("""
                DELETE FROM aggregated_metrics 
                WHERE created_at < ?
            """, (cutoff_date.isoformat(),))
            
            # Clean up old error patterns
            cursor.execute("""
                DELETE FROM error_patterns 
                WHERE created_at < ?
            """, (cutoff_date.isoformat(),))
            
            # Clean up old performance insights
            cursor.execute("""
                DELETE FROM performance_insights 
                WHERE created_at < ?
            """, (cutoff_date.isoformat(),))
            
            conn.commit()
            
            deleted_logs = cursor.rowcount
            if deleted_logs > 0:
                self.logger.info(f"Cleaned up {deleted_logs} old records")
    
    def _update_analysis_cache(self) -> None:
        """Update analysis cache with fresh insights."""
        current_time = datetime.now()
        
        # Check if cache needs updating
        cache_keys_to_update = []
        for key, timestamp in self.cache_timestamps.items():
            if (current_time - timestamp).total_seconds() > self.cache_ttl_seconds:
                cache_keys_to_update.append(key)
        
        # Update expired cache entries
        for key in cache_keys_to_update:
            if key == "error_patterns":
                self.analysis_cache[key] = self._analyze_error_patterns()
            elif key == "performance_insights":
                self.analysis_cache[key] = self._analyze_performance_insights()
            elif key == "trends":
                self.analysis_cache[key] = self._analyze_trends()
            
            self.cache_timestamps[key] = current_time
    
    def get_startup_analysis_report(self, period_hours: int = 24) -> StartupAnalysisReport:
        """Generate a comprehensive startup analysis report."""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=period_hours)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get startup statistics
            cursor.execute("""
                SELECT COUNT(*) as total_startups,
                       SUM(CASE WHEN level != 'ERROR' THEN 1 ELSE 0 END) as successful_startups,
                       SUM(CASE WHEN level = 'ERROR' THEN 1 ELSE 0 END) as failed_startups
                FROM startup_logs 
                WHERE event_type = 'phase_transition_complete' 
                AND phase = 'full'
                AND timestamp >= ? AND timestamp <= ?
            """, (start_time.isoformat(), end_time.isoformat()))
            
            startup_stats = cursor.fetchone()
            total_startups = startup_stats[0] if startup_stats[0] else 0
            successful_startups = startup_stats[1] if startup_stats[1] else 0
            failed_startups = startup_stats[2] if startup_stats[2] else 0
            
            # Get startup time statistics
            cursor.execute("""
                SELECT duration_ms FROM startup_logs 
                WHERE event_type = 'phase_transition_complete' 
                AND phase = 'full'
                AND timestamp >= ? AND timestamp <= ?
                AND duration_ms IS NOT NULL
            """, (start_time.isoformat(), end_time.isoformat()))
            
            startup_times = [row[0] for row in cursor.fetchall()]
            
            if startup_times:
                avg_startup_time = statistics.mean(startup_times)
                median_startup_time = statistics.median(startup_times)
                sorted_times = sorted(startup_times)
                p95_startup_time = sorted_times[int(0.95 * len(sorted_times))] if len(sorted_times) > 1 else sorted_times[0]
                p99_startup_time = sorted_times[int(0.99 * len(sorted_times))] if len(sorted_times) > 1 else sorted_times[0]
            else:
                avg_startup_time = median_startup_time = p95_startup_time = p99_startup_time = 0.0
        
        # Get phase performance
        phase_performance = self._analyze_phase_performance(start_time, end_time)
        
        # Get model loading performance
        model_loading_performance = self._analyze_model_loading_performance(start_time, end_time)
        
        # Get error patterns
        error_patterns = self._analyze_error_patterns(start_time, end_time)
        
        # Get performance insights
        performance_insights = self._analyze_performance_insights(start_time, end_time)
        
        # Get trends
        trends = self._analyze_trends(start_time, end_time)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            startup_times, phase_performance, model_loading_performance, 
            error_patterns, performance_insights
        )
        
        return StartupAnalysisReport(
            report_id=str(uuid.uuid4()),
            generated_at=end_time.isoformat(),
            analysis_period=f"{period_hours} hours",
            total_startups=total_startups,
            successful_startups=successful_startups,
            failed_startups=failed_startups,
            avg_startup_time_ms=avg_startup_time,
            median_startup_time_ms=median_startup_time,
            p95_startup_time_ms=p95_startup_time,
            p99_startup_time_ms=p99_startup_time,
            phase_performance=phase_performance,
            model_loading_performance=model_loading_performance,
            error_patterns=error_patterns,
            performance_insights=performance_insights,
            trends=trends,
            recommendations=recommendations
        )
    
    def _analyze_phase_performance(self, start_time: datetime, end_time: datetime) -> Dict[str, Dict[str, float]]:
        """Analyze phase transition performance."""
        phase_performance = {}
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for phase in ["minimal", "essential", "full"]:
                cursor.execute("""
                    SELECT duration_ms FROM startup_logs 
                    WHERE event_type = 'phase_transition_complete' 
                    AND phase = ?
                    AND timestamp >= ? AND timestamp <= ?
                    AND duration_ms IS NOT NULL
                """, (phase, start_time.isoformat(), end_time.isoformat()))
                
                durations = [row[0] for row in cursor.fetchall()]
                
                if durations:
                    phase_performance[phase] = {
                        "avg_duration_ms": statistics.mean(durations),
                        "median_duration_ms": statistics.median(durations),
                        "min_duration_ms": min(durations),
                        "max_duration_ms": max(durations),
                        "count": len(durations)
                    }
        
        return phase_performance
    
    def _analyze_model_loading_performance(self, start_time: datetime, end_time: datetime) -> Dict[str, Dict[str, float]]:
        """Analyze model loading performance."""
        model_performance = {}
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for priority in ["essential", "standard", "advanced"]:
                cursor.execute("""
                    SELECT duration_ms FROM startup_logs 
                    WHERE event_type = 'model_loading_complete' 
                    AND timestamp >= ? AND timestamp <= ?
                    AND duration_ms IS NOT NULL
                    AND metadata LIKE ?
                """, (start_time.isoformat(), end_time.isoformat(), f'%"priority": "{priority}"%'))
                
                durations = [row[0] for row in cursor.fetchall()]
                
                if durations:
                    model_performance[priority] = {
                        "avg_duration_ms": statistics.mean(durations),
                        "median_duration_ms": statistics.median(durations),
                        "min_duration_ms": min(durations),
                        "max_duration_ms": max(durations),
                        "count": len(durations)
                    }
        
        return model_performance
    
    def _analyze_error_patterns(self, start_time: Optional[datetime] = None, 
                               end_time: Optional[datetime] = None) -> List[ErrorPattern]:
        """Analyze error patterns and classify them."""
        if start_time is None:
            start_time = datetime.now() - timedelta(hours=24)
        if end_time is None:
            end_time = datetime.now()
        
        error_patterns = []
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get error logs
            cursor.execute("""
                SELECT event_type, message, phase, timestamp, error_details 
                FROM startup_logs 
                WHERE level = 'ERROR' 
                AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp
            """, (start_time.isoformat(), end_time.isoformat()))
            
            errors = cursor.fetchall()
            
            # Group errors by type and message pattern
            error_groups = defaultdict(list)
            for error in errors:
                event_type, message, phase, timestamp, error_details = error
                
                # Create a pattern key based on error type and simplified message
                pattern_key = f"{event_type}:{self._simplify_error_message(message)}"
                error_groups[pattern_key].append({
                    "event_type": event_type,
                    "message": message,
                    "phase": phase,
                    "timestamp": timestamp,
                    "error_details": error_details
                })
            
            # Analyze each error group
            for pattern_key, error_list in error_groups.items():
                if len(error_list) < 2:  # Skip single occurrences
                    continue
                
                event_type = error_list[0]["event_type"]
                message_pattern = self._simplify_error_message(error_list[0]["message"])
                
                timestamps = [datetime.fromisoformat(e["timestamp"]) for e in error_list]
                first_seen = min(timestamps)
                last_seen = max(timestamps)
                
                affected_phases = list(set(e["phase"] for e in error_list))
                
                # Calculate frequency
                time_span_hours = (last_seen - first_seen).total_seconds() / 3600
                frequency_per_hour = len(error_list) / max(time_span_hours, 1)
                
                # Determine severity
                severity = self._determine_error_severity(event_type, len(error_list), frequency_per_hour)
                
                # Generate suggested actions
                suggested_actions = self._generate_error_suggestions(event_type, message_pattern, affected_phases)
                
                error_patterns.append(ErrorPattern(
                    pattern_id=str(uuid.uuid4()),
                    error_type=event_type,
                    error_message_pattern=message_pattern,
                    occurrence_count=len(error_list),
                    first_seen=first_seen.isoformat(),
                    last_seen=last_seen.isoformat(),
                    affected_phases=affected_phases,
                    frequency_per_hour=frequency_per_hour,
                    severity=severity,
                    suggested_actions=suggested_actions
                ))
        
        return error_patterns
    
    def _analyze_performance_insights(self, start_time: Optional[datetime] = None,
                                    end_time: Optional[datetime] = None) -> List[PerformanceInsight]:
        """Analyze performance data and generate insights."""
        if start_time is None:
            start_time = datetime.now() - timedelta(hours=24)
        if end_time is None:
            end_time = datetime.now()
        
        insights = []
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Analyze startup time trends
            cursor.execute("""
                SELECT AVG(avg_value) as avg_startup_time,
                       MAX(max_value) as max_startup_time,
                       MIN(min_value) as min_startup_time
                FROM aggregated_metrics 
                WHERE metric_name = 'startup_time_ms' 
                AND period = 'hour'
                AND timestamp >= ? AND timestamp <= ?
            """, (start_time.isoformat(), end_time.isoformat()))
            
            startup_stats = cursor.fetchone()
            if startup_stats and startup_stats[0]:
                avg_startup_time, max_startup_time, min_startup_time = startup_stats
                
                # Check for slow startup times
                if avg_startup_time > 300000:  # 5 minutes
                    insights.append(PerformanceInsight(
                        insight_id=str(uuid.uuid4()),
                        insight_type="performance",
                        title="Slow Startup Times Detected",
                        description=f"Average startup time is {avg_startup_time/1000:.1f} seconds, which exceeds the recommended 5-minute threshold.",
                        severity="high",
                        affected_components=["startup_system"],
                        metrics={"avg_startup_time_ms": avg_startup_time, "max_startup_time_ms": max_startup_time},
                        recommendations=[
                            "Implement model caching to reduce loading times",
                            "Optimize model loading order by priority",
                            "Consider lazy loading for non-essential models",
                            "Review resource initialization bottlenecks"
                        ],
                        confidence_score=0.9
                    ))
                
                # Check for startup time variability
                if max_startup_time > min_startup_time * 2:
                    insights.append(PerformanceInsight(
                        insight_id=str(uuid.uuid4()),
                        insight_type="consistency",
                        title="High Startup Time Variability",
                        description=f"Startup times vary significantly (min: {min_startup_time/1000:.1f}s, max: {max_startup_time/1000:.1f}s).",
                        severity="medium",
                        affected_components=["startup_system"],
                        metrics={"min_startup_time_ms": min_startup_time, "max_startup_time_ms": max_startup_time},
                        recommendations=[
                            "Investigate environmental factors affecting startup",
                            "Implement consistent resource allocation",
                            "Add startup performance monitoring",
                            "Consider warm-up strategies"
                        ],
                        confidence_score=0.8
                    ))
        
        return insights
    
    def _analyze_trends(self, start_time: Optional[datetime] = None,
                       end_time: Optional[datetime] = None) -> Dict[str, List[Dict[str, Any]]]:
        """Analyze performance trends over time."""
        if start_time is None:
            start_time = datetime.now() - timedelta(days=7)
        if end_time is None:
            end_time = datetime.now()
        
        trends = {}
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Startup time trends
            cursor.execute("""
                SELECT timestamp, avg_value, count 
                FROM aggregated_metrics 
                WHERE metric_name = 'startup_time_ms' 
                AND period = 'hour'
                AND timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp
            """, (start_time.isoformat(), end_time.isoformat()))
            
            startup_trend = []
            for row in cursor.fetchall():
                startup_trend.append({
                    "timestamp": row[0],
                    "avg_startup_time_ms": row[1],
                    "startup_count": row[2]
                })
            
            trends["startup_times"] = startup_trend
            
            # Error rate trends
            cursor.execute("""
                SELECT timestamp, SUM(count) as total_errors
                FROM aggregated_metrics 
                WHERE metric_name LIKE 'error_count_%'
                AND period = 'hour'
                AND timestamp >= ? AND timestamp <= ?
                GROUP BY timestamp
                ORDER BY timestamp
            """, (start_time.isoformat(), end_time.isoformat()))
            
            error_trend = []
            for row in cursor.fetchall():
                error_trend.append({
                    "timestamp": row[0],
                    "error_count": row[1]
                })
            
            trends["error_rates"] = error_trend
        
        return trends
    
    def _generate_recommendations(self, startup_times: List[float], 
                                phase_performance: Dict[str, Dict[str, float]],
                                model_loading_performance: Dict[str, Dict[str, float]],
                                error_patterns: List[ErrorPattern],
                                performance_insights: List[PerformanceInsight]) -> List[str]:
        """Generate actionable recommendations based on analysis."""
        recommendations = []
        
        # Startup time recommendations
        if startup_times and statistics.mean(startup_times) > 300000:  # 5 minutes
            recommendations.append("Consider implementing model caching to reduce startup times")
            recommendations.append("Optimize model loading order by priority (essential first)")
        
        # Phase performance recommendations
        if "full" in phase_performance:
            full_phase_avg = phase_performance["full"]["avg_duration_ms"]
            if full_phase_avg > 180000:  # 3 minutes
                recommendations.append("Full phase transition is slow - review model loading efficiency")
        
        # Error pattern recommendations
        high_frequency_errors = [ep for ep in error_patterns if ep.frequency_per_hour > 1.0]
        if high_frequency_errors:
            recommendations.append("Address high-frequency error patterns to improve reliability")
        
        # Model loading recommendations
        for priority, perf in model_loading_performance.items():
            if perf["avg_duration_ms"] > 60000:  # 1 minute
                recommendations.append(f"Optimize {priority} priority model loading (currently {perf['avg_duration_ms']/1000:.1f}s avg)")
        
        # Performance insight recommendations
        high_severity_insights = [pi for pi in performance_insights if pi.severity == "high"]
        if high_severity_insights:
            recommendations.append("Address high-severity performance issues identified in analysis")
        
        return recommendations
    
    def _simplify_error_message(self, message: str) -> str:
        """Simplify error message to create patterns."""
        # Remove specific values, paths, and timestamps to create patterns
        import re
        
        # Remove file paths
        message = re.sub(r'/[^\s]+', '<path>', message)
        
        # Remove numbers that might be IDs, ports, etc.
        message = re.sub(r'\b\d+\b', '<number>', message)
        
        # Remove timestamps
        message = re.sub(r'\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}', '<timestamp>', message)
        
        # Remove UUIDs
        message = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '<uuid>', message)
        
        return message
    
    def _determine_error_severity(self, error_type: str, occurrence_count: int, frequency_per_hour: float) -> str:
        """Determine error severity based on type, count, and frequency."""
        if error_type in ["startup_error", "phase_transition_complete"] and frequency_per_hour > 2.0:
            return "critical"
        elif frequency_per_hour > 1.0 or occurrence_count > 10:
            return "high"
        elif frequency_per_hour > 0.5 or occurrence_count > 5:
            return "medium"
        else:
            return "low"
    
    def _generate_error_suggestions(self, error_type: str, message_pattern: str, affected_phases: List[str]) -> List[str]:
        """Generate suggested actions for error patterns."""
        suggestions = []
        
        if "model_loading" in error_type:
            suggestions.extend([
                "Check model file availability and permissions",
                "Verify sufficient memory for model loading",
                "Review model loading timeout settings",
                "Consider fallback models for failed loads"
            ])
        elif "resource_init" in error_type:
            suggestions.extend([
                "Verify network connectivity to external resources",
                "Check authentication credentials and permissions",
                "Review resource initialization timeout settings",
                "Implement retry logic with exponential backoff"
            ])
        elif "phase_transition" in error_type:
            suggestions.extend([
                "Review phase transition prerequisites",
                "Check for resource conflicts during transitions",
                "Verify phase timeout configurations",
                "Add detailed logging for transition failures"
            ])
        else:
            suggestions.extend([
                "Review error logs for detailed context",
                "Check system resources and dependencies",
                "Verify configuration settings",
                "Consider implementing error recovery mechanisms"
            ])
        
        return suggestions
    
    def export_analysis_data(self, format_type: str = "json", include_raw_logs: bool = False) -> str:
        """Export analysis data in the specified format."""
        # Get recent analysis report
        report = self.get_startup_analysis_report(period_hours=24)
        
        if format_type == "json":
            export_data = {
                "analysis_report": asdict(report),
                "export_timestamp": datetime.now().isoformat(),
                "export_format": "json"
            }
            
            if include_raw_logs:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT timestamp, level, event_type, phase, message, duration_ms, metadata, error_details
                        FROM startup_logs 
                        WHERE timestamp >= ?
                        ORDER BY timestamp DESC
                        LIMIT 1000
                    """, ((datetime.now() - timedelta(hours=24)).isoformat(),))
                    
                    raw_logs = []
                    for row in cursor.fetchall():
                        raw_logs.append({
                            "timestamp": row[0],
                            "level": row[1],
                            "event_type": row[2],
                            "phase": row[3],
                            "message": row[4],
                            "duration_ms": row[5],
                            "metadata": json.loads(row[6]) if row[6] else None,
                            "error_details": json.loads(row[7]) if row[7] else None
                        })
                    
                    export_data["raw_logs"] = raw_logs
            
            return json.dumps(export_data, indent=2, default=str)
        
        elif format_type == "csv":
            import csv
            import io
            
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write analysis summary
            writer.writerow(["Analysis Report Summary"])
            writer.writerow(["Generated At", report.generated_at])
            writer.writerow(["Analysis Period", report.analysis_period])
            writer.writerow(["Total Startups", report.total_startups])
            writer.writerow(["Successful Startups", report.successful_startups])
            writer.writerow(["Failed Startups", report.failed_startups])
            writer.writerow(["Avg Startup Time (ms)", report.avg_startup_time_ms])
            writer.writerow(["Median Startup Time (ms)", report.median_startup_time_ms])
            writer.writerow(["P95 Startup Time (ms)", report.p95_startup_time_ms])
            writer.writerow(["P99 Startup Time (ms)", report.p99_startup_time_ms])
            writer.writerow([])
            
            # Write error patterns
            writer.writerow(["Error Patterns"])
            writer.writerow(["Pattern ID", "Error Type", "Message Pattern", "Count", "Severity", "Frequency/Hour"])
            for pattern in report.error_patterns:
                writer.writerow([
                    pattern.pattern_id, pattern.error_type, pattern.error_message_pattern,
                    pattern.occurrence_count, pattern.severity, pattern.frequency_per_hour
                ])
            writer.writerow([])
            
            # Write performance insights
            writer.writerow(["Performance Insights"])
            writer.writerow(["Insight ID", "Type", "Title", "Severity", "Confidence"])
            for insight in report.performance_insights:
                writer.writerow([
                    insight.insight_id, insight.insight_type, insight.title,
                    insight.severity, insight.confidence_score
                ])
            
            return output.getvalue()
        
        else:
            raise ValueError(f"Unsupported export format: {format_type}")
    
    def get_real_time_metrics(self) -> Dict[str, Any]:
        """Get real-time metrics for monitoring dashboards."""
        current_time = datetime.now()
        last_hour = current_time - timedelta(hours=1)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Recent startup count
            cursor.execute("""
                SELECT COUNT(*) FROM startup_logs 
                WHERE event_type = 'phase_transition_complete' 
                AND phase = 'full'
                AND timestamp >= ?
            """, (last_hour.isoformat(),))
            recent_startups = cursor.fetchone()[0]
            
            # Recent error count
            cursor.execute("""
                SELECT COUNT(*) FROM startup_logs 
                WHERE level = 'ERROR' 
                AND timestamp >= ?
            """, (last_hour.isoformat(),))
            recent_errors = cursor.fetchone()[0]
            
            # Average startup time (last hour)
            cursor.execute("""
                SELECT AVG(duration_ms) FROM startup_logs 
                WHERE event_type = 'phase_transition_complete' 
                AND phase = 'full'
                AND timestamp >= ?
                AND duration_ms IS NOT NULL
            """, (last_hour.isoformat(),))
            avg_startup_time = cursor.fetchone()[0] or 0
            
            # Current buffer size
            buffer_size = len(self.log_buffer)
        
        return {
            "timestamp": current_time.isoformat(),
            "recent_startups_count": recent_startups,
            "recent_errors_count": recent_errors,
            "avg_startup_time_ms": avg_startup_time,
            "log_buffer_size": buffer_size,
            "processing_active": self.processing_thread and self.processing_thread.is_alive(),
            "cache_entries": len(self.analysis_cache)
        }


# Global log aggregator instance
_log_aggregator: Optional[LogAggregator] = None


def get_log_aggregator() -> Optional[LogAggregator]:
    """Get the global log aggregator instance."""
    return _log_aggregator


def initialize_log_aggregator(db_path: Optional[str] = None, retention_days: int = 30) -> LogAggregator:
    """Initialize the global log aggregator."""
    global _log_aggregator
    _log_aggregator = LogAggregator(db_path, retention_days)
    _log_aggregator.start_background_processing()
    return _log_aggregator


def add_log_entry(log_entry: StartupLogEntry) -> None:
    """Convenience function to add log entry to aggregator."""
    if _log_aggregator:
        _log_aggregator.add_log_entry(log_entry)


def add_log_entries(log_entries: List[StartupLogEntry]) -> None:
    """Convenience function to add multiple log entries to aggregator."""
    if _log_aggregator:
        _log_aggregator.add_log_entries(log_entries)


def get_startup_analysis_report(period_hours: int = 24) -> Optional[StartupAnalysisReport]:
    """Convenience function to get startup analysis report."""
    if _log_aggregator:
        return _log_aggregator.get_startup_analysis_report(period_hours)
    return None


def export_analysis_data(format_type: str = "json", include_raw_logs: bool = False) -> Optional[str]:
    """Convenience function to export analysis data."""
    if _log_aggregator:
        return _log_aggregator.export_analysis_data(format_type, include_raw_logs)
    return None


def get_real_time_metrics() -> Optional[Dict[str, Any]]:
    """Convenience function to get real-time metrics."""
    if _log_aggregator:
        return _log_aggregator.get_real_time_metrics()
    return None