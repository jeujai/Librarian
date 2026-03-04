"""
Enhanced structured logging service with comprehensive log aggregation and correlation.

This service extends the existing logging infrastructure to provide:
- Consistent structured log formatting across all services
- Enhanced correlation ID tracking
- Log aggregation and centralized collection
- Advanced log filtering and search capabilities
- Log retention and archival policies
"""

import asyncio
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union, Set
from dataclasses import dataclass, asdict, field
from contextlib import asynccontextmanager
from collections import defaultdict, deque
import threading
import hashlib
import gzip
import os
from pathlib import Path

from ..config import get_settings
from ..logging_config import get_logger
from .logging_service import get_logging_service, LogEntry


@dataclass
class StructuredLogEntry:
    """Enhanced structured log entry with correlation and context."""
    timestamp: datetime
    level: str
    service: str
    operation: str
    message: str
    correlation_id: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    duration_ms: Optional[float] = None
    status_code: Optional[int] = None
    error_code: Optional[str] = None
    error_type: Optional[str] = None
    stack_trace: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: Dict[str, str] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_json(self) -> str:
        """Convert log entry to JSON string."""
        data = asdict(self)
        # Convert datetime to ISO string
        data['timestamp'] = self.timestamp.isoformat()
        return json.dumps(data, default=str)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert log entry to dictionary."""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        return data


@dataclass
class LogAggregationRule:
    """Rule for log aggregation and filtering."""
    name: str
    service_pattern: Optional[str] = None
    operation_pattern: Optional[str] = None
    level_filter: Optional[Set[str]] = None
    tag_filters: Optional[Dict[str, str]] = None
    time_window_minutes: int = 60
    max_entries: int = 1000
    enabled: bool = True


@dataclass
class LogRetentionPolicy:
    """Log retention and archival policy."""
    name: str
    retention_days: int
    archive_after_days: int
    compression_enabled: bool = True
    archive_location: Optional[str] = None
    cleanup_enabled: bool = True


class StructuredLoggingService:
    """Enhanced structured logging service with aggregation and correlation."""
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = get_logger("structured_logging")
        self.base_logging_service = get_logging_service()
        
        # Thread-safe storage
        self._lock = threading.Lock()
        
        # Enhanced log storage with correlation
        self._structured_logs = deque(maxlen=100000)  # Last 100k structured logs
        self._correlation_index = defaultdict(list)  # correlation_id -> log entries
        self._trace_index = defaultdict(list)  # trace_id -> log entries
        self._user_index = defaultdict(list)  # user_id -> log entries
        self._service_index = defaultdict(list)  # service -> log entries
        
        # Log aggregation
        self._aggregation_rules = {}
        self._aggregated_logs = defaultdict(lambda: deque(maxlen=10000))
        
        # Log retention
        self._retention_policies = {}
        self._archived_logs_count = 0
        
        # Performance tracking
        self._log_processing_stats = {
            'total_logs_processed': 0,
            'logs_per_second': 0,
            'average_processing_time_ms': 0,
            'last_processing_time': datetime.now()
        }
        
        # Initialize default configurations
        self._setup_default_aggregation_rules()
        self._setup_default_retention_policies()
        
        # Start background processing
        self._start_background_processing()
    
    def _setup_default_aggregation_rules(self):
        """Setup default log aggregation rules."""
        
        # API request aggregation
        self.add_aggregation_rule(LogAggregationRule(
            name="api_requests",
            service_pattern="api",
            time_window_minutes=15,
            max_entries=5000
        ))
        
        # Error aggregation
        self.add_aggregation_rule(LogAggregationRule(
            name="errors",
            level_filter={"ERROR", "CRITICAL"},
            time_window_minutes=60,
            max_entries=2000
        ))
        
        # Performance aggregation
        self.add_aggregation_rule(LogAggregationRule(
            name="performance",
            operation_pattern="*performance*",
            time_window_minutes=30,
            max_entries=3000
        ))
        
        # User activity aggregation
        self.add_aggregation_rule(LogAggregationRule(
            name="user_activity",
            tag_filters={"category": "user_action"},
            time_window_minutes=120,
            max_entries=10000
        ))
    
    def _setup_default_retention_policies(self):
        """Setup default log retention policies."""
        
        # Standard logs - 30 days retention, archive after 7 days
        self.add_retention_policy(LogRetentionPolicy(
            name="standard",
            retention_days=30,
            archive_after_days=7,
            compression_enabled=True,
            archive_location="logs/archive"
        ))
        
        # Error logs - 90 days retention, archive after 14 days
        self.add_retention_policy(LogRetentionPolicy(
            name="errors",
            retention_days=90,
            archive_after_days=14,
            compression_enabled=True,
            archive_location="logs/archive/errors"
        ))
        
        # Audit logs - 365 days retention, archive after 30 days
        self.add_retention_policy(LogRetentionPolicy(
            name="audit",
            retention_days=365,
            archive_after_days=30,
            compression_enabled=True,
            archive_location="logs/archive/audit"
        ))
    
    def log_structured(self, level: str, service: str, operation: str, message: str,
                      correlation_id: Optional[str] = None, trace_id: Optional[str] = None,
                      span_id: Optional[str] = None, parent_span_id: Optional[str] = None,
                      user_id: Optional[str] = None, session_id: Optional[str] = None,
                      request_id: Optional[str] = None, duration_ms: Optional[float] = None,
                      status_code: Optional[int] = None, error_code: Optional[str] = None,
                      error_type: Optional[str] = None, stack_trace: Optional[str] = None,
                      metadata: Optional[Dict[str, Any]] = None,
                      tags: Optional[Dict[str, str]] = None,
                      context: Optional[Dict[str, Any]] = None) -> str:
        """Log a structured entry with enhanced correlation and context."""
        
        start_time = time.time()
        
        # Generate correlation ID if not provided
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        
        # Create structured log entry
        log_entry = StructuredLogEntry(
            timestamp=datetime.now(),
            level=level.upper(),
            service=service,
            operation=operation,
            message=message,
            correlation_id=correlation_id,
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            user_id=user_id,
            session_id=session_id,
            request_id=request_id,
            duration_ms=duration_ms,
            status_code=status_code,
            error_code=error_code,
            error_type=error_type,
            stack_trace=stack_trace,
            metadata=metadata or {},
            tags=tags or {},
            context=context or {}
        )
        
        # Store in structured storage with indexing
        with self._lock:
            self._structured_logs.append(log_entry)
            
            # Update indexes
            self._correlation_index[correlation_id].append(log_entry)
            if trace_id:
                self._trace_index[trace_id].append(log_entry)
            if user_id:
                self._user_index[user_id].append(log_entry)
            self._service_index[service].append(log_entry)
            
            # Apply aggregation rules
            self._apply_aggregation_rules(log_entry)
            
            # Update processing stats
            self._log_processing_stats['total_logs_processed'] += 1
            processing_time_ms = (time.time() - start_time) * 1000
            self._update_processing_stats(processing_time_ms)
        
        # Also log to base logging service for compatibility
        self.base_logging_service.log_structured(
            level=level,
            service=service,
            operation=operation,
            message=message,
            trace_id=trace_id,
            span_id=span_id,
            user_id=user_id,
            session_id=session_id,
            duration_ms=duration_ms,
            metadata={
                **(metadata or {}),
                'correlation_id': correlation_id,
                'request_id': request_id,
                'status_code': status_code,
                'error_code': error_code,
                'error_type': error_type,
                'tags': tags,
                'context': context
            }
        )
        
        return correlation_id
    
    def _apply_aggregation_rules(self, log_entry: StructuredLogEntry):
        """Apply aggregation rules to log entry."""
        
        for rule_name, rule in self._aggregation_rules.items():
            if not rule.enabled:
                continue
            
            # Check if log entry matches rule
            if self._matches_aggregation_rule(log_entry, rule):
                # Add to aggregated logs
                aggregated_logs = self._aggregated_logs[rule_name]
                aggregated_logs.append(log_entry)
                
                # Trim if exceeds max entries
                if len(aggregated_logs) > rule.max_entries:
                    # Remove oldest entries outside time window
                    cutoff_time = datetime.now() - timedelta(minutes=rule.time_window_minutes)
                    while aggregated_logs and aggregated_logs[0].timestamp < cutoff_time:
                        aggregated_logs.popleft()
    
    def _matches_aggregation_rule(self, log_entry: StructuredLogEntry, rule: LogAggregationRule) -> bool:
        """Check if log entry matches aggregation rule."""
        
        # Service pattern matching
        if rule.service_pattern and not self._matches_pattern(log_entry.service, rule.service_pattern):
            return False
        
        # Operation pattern matching
        if rule.operation_pattern and not self._matches_pattern(log_entry.operation, rule.operation_pattern):
            return False
        
        # Level filtering
        if rule.level_filter and log_entry.level not in rule.level_filter:
            return False
        
        # Tag filtering
        if rule.tag_filters:
            for tag_key, tag_value in rule.tag_filters.items():
                if tag_key not in log_entry.tags or log_entry.tags[tag_key] != tag_value:
                    return False
        
        return True
    
    def _matches_pattern(self, text: str, pattern: str) -> bool:
        """Simple pattern matching with wildcards."""
        if pattern == "*":
            return True
        if "*" not in pattern:
            return text == pattern
        
        # Simple wildcard matching
        import re
        regex_pattern = pattern.replace("*", ".*")
        return bool(re.match(regex_pattern, text, re.IGNORECASE))
    
    def _update_processing_stats(self, processing_time_ms: float):
        """Update log processing statistics."""
        
        stats = self._log_processing_stats
        
        # Update average processing time (exponential moving average)
        alpha = 0.1  # Smoothing factor
        stats['average_processing_time_ms'] = (
            alpha * processing_time_ms + 
            (1 - alpha) * stats['average_processing_time_ms']
        )
        
        # Calculate logs per second
        now = datetime.now()
        time_diff = (now - stats['last_processing_time']).total_seconds()
        if time_diff > 0:
            stats['logs_per_second'] = 1.0 / time_diff
        stats['last_processing_time'] = now
    
    def get_logs_by_correlation(self, correlation_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get all logs for a specific correlation ID."""
        
        with self._lock:
            logs = self._correlation_index.get(correlation_id, [])
            # Sort by timestamp and limit
            sorted_logs = sorted(logs, key=lambda x: x.timestamp)[-limit:]
            return [log.to_dict() for log in sorted_logs]
    
    def get_logs_by_trace(self, trace_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get all logs for a specific trace ID."""
        
        with self._lock:
            logs = self._trace_index.get(trace_id, [])
            sorted_logs = sorted(logs, key=lambda x: x.timestamp)[-limit:]
            return [log.to_dict() for log in sorted_logs]
    
    def get_logs_by_user(self, user_id: str, hours: int = 24, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get logs for a specific user within time window."""
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with self._lock:
            logs = self._user_index.get(user_id, [])
            filtered_logs = [
                log for log in logs 
                if log.timestamp >= cutoff_time
            ]
            sorted_logs = sorted(filtered_logs, key=lambda x: x.timestamp)[-limit:]
            return [log.to_dict() for log in sorted_logs]
    
    def get_logs_by_service(self, service: str, hours: int = 24, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get logs for a specific service within time window."""
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with self._lock:
            logs = self._service_index.get(service, [])
            filtered_logs = [
                log for log in logs 
                if log.timestamp >= cutoff_time
            ]
            sorted_logs = sorted(filtered_logs, key=lambda x: x.timestamp)[-limit:]
            return [log.to_dict() for log in sorted_logs]
    
    def search_logs(self, query: str, service: Optional[str] = None, 
                   level: Optional[str] = None, hours: int = 24, 
                   limit: int = 1000) -> List[Dict[str, Any]]:
        """Search logs with text query and filters."""
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        query_lower = query.lower()
        
        with self._lock:
            matching_logs = []
            
            for log_entry in reversed(self._structured_logs):
                if log_entry.timestamp < cutoff_time:
                    break
                
                # Apply filters
                if service and log_entry.service != service:
                    continue
                if level and log_entry.level != level.upper():
                    continue
                
                # Text search in message, operation, and metadata
                if (query_lower in log_entry.message.lower() or
                    query_lower in log_entry.operation.lower() or
                    any(query_lower in str(v).lower() for v in log_entry.metadata.values())):
                    
                    matching_logs.append(log_entry.to_dict())
                    
                    if len(matching_logs) >= limit:
                        break
            
            return matching_logs
    
    def get_aggregated_logs(self, rule_name: str, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get logs from specific aggregation rule."""
        
        with self._lock:
            if rule_name not in self._aggregated_logs:
                return []
            
            logs = list(self._aggregated_logs[rule_name])[-limit:]
            return [log.to_dict() for log in logs]
    
    def get_log_statistics(self, hours: int = 24) -> Dict[str, Any]:
        """Get comprehensive log statistics."""
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with self._lock:
            # Filter recent logs
            recent_logs = [
                log for log in self._structured_logs
                if log.timestamp >= cutoff_time
            ]
            
            if not recent_logs:
                return {'error': 'No logs found for the specified time period'}
            
            # Calculate statistics
            level_counts = defaultdict(int)
            service_counts = defaultdict(int)
            operation_counts = defaultdict(int)
            error_counts = defaultdict(int)
            user_counts = defaultdict(int)
            
            total_duration = 0
            duration_count = 0
            
            for log in recent_logs:
                level_counts[log.level] += 1
                service_counts[log.service] += 1
                operation_counts[log.operation] += 1
                
                if log.user_id:
                    user_counts[log.user_id] += 1
                
                if log.level in ['ERROR', 'CRITICAL']:
                    error_key = f"{log.service}.{log.operation}"
                    if log.error_type:
                        error_key += f".{log.error_type}"
                    error_counts[error_key] += 1
                
                if log.duration_ms:
                    total_duration += log.duration_ms
                    duration_count += 1
            
            return {
                'time_period_hours': hours,
                'total_logs': len(recent_logs),
                'logs_per_hour': len(recent_logs) / max(1, hours),
                'level_distribution': dict(level_counts),
                'service_distribution': dict(service_counts),
                'top_operations': dict(sorted(operation_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
                'top_errors': dict(sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
                'active_users': len(user_counts),
                'average_duration_ms': total_duration / max(1, duration_count),
                'processing_stats': self._log_processing_stats.copy(),
                'aggregation_rules': len(self._aggregation_rules),
                'retention_policies': len(self._retention_policies),
                'archived_logs_count': self._archived_logs_count
            }
    
    def add_aggregation_rule(self, rule: LogAggregationRule):
        """Add a new log aggregation rule."""
        with self._lock:
            self._aggregation_rules[rule.name] = rule
        self.logger.info(f"Added aggregation rule: {rule.name}")
    
    def remove_aggregation_rule(self, rule_name: str):
        """Remove a log aggregation rule."""
        with self._lock:
            if rule_name in self._aggregation_rules:
                del self._aggregation_rules[rule_name]
                if rule_name in self._aggregated_logs:
                    del self._aggregated_logs[rule_name]
        self.logger.info(f"Removed aggregation rule: {rule_name}")
    
    def add_retention_policy(self, policy: LogRetentionPolicy):
        """Add a new log retention policy."""
        with self._lock:
            self._retention_policies[policy.name] = policy
        self.logger.info(f"Added retention policy: {policy.name}")
    
    def export_structured_logs(self, filepath: Optional[str] = None, 
                              format: str = "json", hours: int = 24,
                              correlation_id: Optional[str] = None,
                              trace_id: Optional[str] = None) -> str:
        """Export structured logs to file."""
        
        if not filepath:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            extension = "json" if format == "json" else "txt"
            filepath = f"structured_logs_export_{timestamp}.{extension}"
        
        # Get logs to export
        if correlation_id:
            logs = self.get_logs_by_correlation(correlation_id)
        elif trace_id:
            logs = self.get_logs_by_trace(trace_id)
        else:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            with self._lock:
                logs = [
                    log.to_dict() for log in self._structured_logs
                    if log.timestamp >= cutoff_time
                ]
        
        export_data = {
            'export_timestamp': datetime.now().isoformat(),
            'export_format': format,
            'time_period_hours': hours,
            'correlation_id_filter': correlation_id,
            'trace_id_filter': trace_id,
            'total_logs': len(logs),
            'logs': logs,
            'statistics': self.get_log_statistics(hours=hours)
        }
        
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
            
            if format == "json":
                with open(filepath, 'w') as f:
                    json.dump(export_data, f, indent=2, default=str)
            else:
                # Plain text format
                with open(filepath, 'w') as f:
                    f.write(f"Structured Logs Export - {export_data['export_timestamp']}\n")
                    f.write("=" * 60 + "\n\n")
                    
                    for log in logs:
                        f.write(f"[{log['timestamp']}] {log['level']} {log['service']}.{log['operation']}\n")
                        f.write(f"Correlation: {log['correlation_id']}\n")
                        if log.get('trace_id'):
                            f.write(f"Trace: {log['trace_id']}\n")
                        if log.get('user_id'):
                            f.write(f"User: {log['user_id']}\n")
                        f.write(f"Message: {log['message']}\n")
                        if log.get('metadata'):
                            f.write(f"Metadata: {json.dumps(log['metadata'], default=str)}\n")
                        f.write("-" * 40 + "\n\n")
            
            self.logger.info(f"Structured logs exported to {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"Failed to export structured logs: {e}")
            raise
    
    def _start_background_processing(self):
        """Start background processing for log management."""
        
        def background_processor():
            while True:
                try:
                    # Clean up old indexes every 30 minutes
                    self._cleanup_old_indexes()
                    
                    # Apply retention policies every hour
                    self._apply_retention_policies()
                    
                    # Log system health every 10 minutes
                    self._log_system_health()
                    
                    # Sleep for 10 minutes
                    time.sleep(600)
                    
                except Exception as e:
                    self.logger.error(f"Error in structured logging background processing: {e}")
                    time.sleep(600)  # Continue after error
        
        # Start background thread
        thread = threading.Thread(target=background_processor, daemon=True)
        thread.start()
        self.logger.info("Structured logging background processing started")
    
    def _cleanup_old_indexes(self):
        """Clean up old entries from indexes to prevent memory issues."""
        
        cutoff_time = datetime.now() - timedelta(days=7)  # Keep 7 days in indexes
        
        with self._lock:
            # Clean correlation index
            for correlation_id in list(self._correlation_index.keys()):
                self._correlation_index[correlation_id] = [
                    log for log in self._correlation_index[correlation_id]
                    if log.timestamp >= cutoff_time
                ]
                if not self._correlation_index[correlation_id]:
                    del self._correlation_index[correlation_id]
            
            # Clean other indexes similarly
            for index in [self._trace_index, self._user_index, self._service_index]:
                for key in list(index.keys()):
                    index[key] = [
                        log for log in index[key]
                        if log.timestamp >= cutoff_time
                    ]
                    if not index[key]:
                        del index[key]
        
        self.logger.debug("Completed structured logging index cleanup")
    
    def _apply_retention_policies(self):
        """Apply log retention and archival policies."""
        
        for policy_name, policy in self._retention_policies.items():
            try:
                if not policy.cleanup_enabled:
                    continue
                
                archive_cutoff = datetime.now() - timedelta(days=policy.archive_after_days)
                retention_cutoff = datetime.now() - timedelta(days=policy.retention_days)
                
                # Archive old logs
                if policy.archive_location:
                    self._archive_logs(policy, archive_cutoff)
                
                # Clean up very old logs
                self._cleanup_old_logs(retention_cutoff)
                
            except Exception as e:
                self.logger.error(f"Error applying retention policy {policy_name}: {e}")
    
    def _archive_logs(self, policy: LogRetentionPolicy, cutoff_time: datetime):
        """Archive logs according to retention policy."""
        
        try:
            # Create archive directory
            archive_path = Path(policy.archive_location or "logs/archive")
            archive_path.mkdir(parents=True, exist_ok=True)
            
            # Find logs to archive
            with self._lock:
                logs_to_archive = [
                    log for log in self._structured_logs
                    if log.timestamp < cutoff_time
                ]
            
            if not logs_to_archive:
                return
            
            # Create archive file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            archive_filename = f"structured_logs_archive_{timestamp}.json"
            
            if policy.compression_enabled:
                archive_filename += ".gz"
            
            archive_filepath = archive_path / archive_filename
            
            # Prepare archive data
            archive_data = {
                'archive_timestamp': datetime.now().isoformat(),
                'policy_name': policy.name,
                'total_logs': len(logs_to_archive),
                'logs': [log.to_dict() for log in logs_to_archive]
            }
            
            # Write archive file
            if policy.compression_enabled:
                with gzip.open(archive_filepath, 'wt') as f:
                    json.dump(archive_data, f, default=str)
            else:
                with open(archive_filepath, 'w') as f:
                    json.dump(archive_data, f, indent=2, default=str)
            
            self._archived_logs_count += len(logs_to_archive)
            self.logger.info(f"Archived {len(logs_to_archive)} logs to {archive_filepath}")
            
        except Exception as e:
            self.logger.error(f"Failed to archive logs: {e}")
    
    def _cleanup_old_logs(self, cutoff_time: datetime):
        """Remove very old logs from memory."""
        
        with self._lock:
            # Remove old logs from main storage
            original_count = len(self._structured_logs)
            self._structured_logs = deque(
                (log for log in self._structured_logs if log.timestamp >= cutoff_time),
                maxlen=self._structured_logs.maxlen
            )
            removed_count = original_count - len(self._structured_logs)
            
            if removed_count > 0:
                self.logger.info(f"Cleaned up {removed_count} old structured logs")
    
    def _log_system_health(self):
        """Log structured logging system health."""
        
        with self._lock:
            log_count = len(self._structured_logs)
            correlation_count = len(self._correlation_index)
            trace_count = len(self._trace_index)
            user_count = len(self._user_index)
            service_count = len(self._service_index)
            aggregation_count = sum(len(logs) for logs in self._aggregated_logs.values())
        
        self.log_structured(
            level='INFO',
            service='structured_logging',
            operation='system_health',
            message='Structured logging system health check',
            metadata={
                'structured_logs': log_count,
                'correlation_indexes': correlation_count,
                'trace_indexes': trace_count,
                'user_indexes': user_count,
                'service_indexes': service_count,
                'aggregated_logs': aggregation_count,
                'processing_stats': self._log_processing_stats.copy(),
                'archived_logs': self._archived_logs_count
            },
            tags={'category': 'system_health', 'component': 'structured_logging'}
        )


# Global structured logging service instance
_structured_logging_service = None


def get_structured_logging_service() -> StructuredLoggingService:
    """Get the global structured logging service instance."""
    global _structured_logging_service
    if _structured_logging_service is None:
        _structured_logging_service = StructuredLoggingService()
    return _structured_logging_service


# Convenience functions for structured logging
def log_structured(level: str, service: str, operation: str, message: str, **kwargs) -> str:
    """Log a structured entry with correlation."""
    return get_structured_logging_service().log_structured(level, service, operation, message, **kwargs)


def log_info_structured(service: str, operation: str, message: str, **kwargs) -> str:
    """Log a structured info message."""
    return log_structured('INFO', service, operation, message, **kwargs)


def log_warning_structured(service: str, operation: str, message: str, **kwargs) -> str:
    """Log a structured warning message."""
    return log_structured('WARNING', service, operation, message, **kwargs)


def log_error_structured(service: str, operation: str, message: str, **kwargs) -> str:
    """Log a structured error message."""
    return log_structured('ERROR', service, operation, message, **kwargs)


@asynccontextmanager
async def structured_trace_operation(service: str, operation: str, 
                                   correlation_id: Optional[str] = None,
                                   user_id: Optional[str] = None,
                                   metadata: Optional[Dict[str, Any]] = None):
    """Context manager for structured operation tracing."""
    
    structured_service = get_structured_logging_service()
    start_time = time.time()
    
    # Generate correlation ID if not provided
    if not correlation_id:
        correlation_id = str(uuid.uuid4())
    
    # Log operation start
    structured_service.log_structured(
        level='INFO',
        service=service,
        operation=f"{operation}_start",
        message=f"Started operation: {operation}",
        correlation_id=correlation_id,
        user_id=user_id,
        metadata=metadata,
        tags={'operation_phase': 'start'}
    )
    
    try:
        yield correlation_id
        
        # Log successful completion
        duration_ms = (time.time() - start_time) * 1000
        structured_service.log_structured(
            level='INFO',
            service=service,
            operation=f"{operation}_complete",
            message=f"Completed operation: {operation}",
            correlation_id=correlation_id,
            user_id=user_id,
            duration_ms=duration_ms,
            metadata={**(metadata or {}), 'success': True},
            tags={'operation_phase': 'complete', 'status': 'success'}
        )
        
    except Exception as e:
        # Log error completion
        duration_ms = (time.time() - start_time) * 1000
        structured_service.log_structured(
            level='ERROR',
            service=service,
            operation=f"{operation}_error",
            message=f"Operation failed: {operation}",
            correlation_id=correlation_id,
            user_id=user_id,
            duration_ms=duration_ms,
            error_type=type(e).__name__,
            stack_trace=str(e),
            metadata={**(metadata or {}), 'success': False, 'error': str(e)},
            tags={'operation_phase': 'error', 'status': 'failed'}
        )
        raise