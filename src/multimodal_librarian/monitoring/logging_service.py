"""
Comprehensive logging service for the Multimodal Librarian system.

This module provides structured logging across all services with:
- Distributed tracing for requests
- Performance monitoring
- Business metrics tracking
- Error tracking and alerting
- Audit logging
"""

import asyncio
import time
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from contextlib import asynccontextmanager
import json
import threading
from collections import defaultdict, deque
import traceback

from ..config import get_settings
from ..logging_config import get_logger


@dataclass
class LogEntry:
    """Structured log entry."""
    timestamp: datetime
    level: str
    service: str
    operation: str
    message: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    duration_ms: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    stack_trace: Optional[str] = None


@dataclass
class PerformanceMetric:
    """Performance metric entry."""
    timestamp: datetime
    service: str
    operation: str
    duration_ms: float
    success: bool
    trace_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class BusinessMetric:
    """Business metric entry."""
    timestamp: datetime
    metric_name: str
    metric_value: Union[int, float]
    metric_type: str  # counter, gauge, histogram
    tags: Optional[Dict[str, str]] = None
    trace_id: Optional[str] = None


@dataclass
class TraceSpan:
    """Distributed tracing span."""
    trace_id: str
    span_id: str
    parent_span_id: Optional[str]
    service: str
    operation: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    tags: Optional[Dict[str, str]] = None
    logs: Optional[List[Dict[str, Any]]] = None
    error: bool = False


class LoggingService:
    """Comprehensive logging service with distributed tracing."""
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = get_logger("logging_service")
        
        # Thread-safe storage
        self._lock = threading.Lock()
        
        # Log storage
        self._log_entries = deque(maxlen=50000)  # Last 50k log entries
        self._performance_metrics = deque(maxlen=20000)  # Last 20k performance metrics
        self._business_metrics = deque(maxlen=10000)  # Last 10k business metrics
        
        # Distributed tracing
        self._active_traces = {}  # trace_id -> TraceSpan
        self._completed_traces = deque(maxlen=5000)  # Last 5k completed traces
        
        # Error tracking
        self._error_counts = defaultdict(int)
        self._error_patterns = defaultdict(list)
        
        # Performance tracking
        self._operation_stats = defaultdict(lambda: {
            'count': 0,
            'total_duration': 0,
            'min_duration': float('inf'),
            'max_duration': 0,
            'error_count': 0
        })
        
        # Business metrics aggregation
        self._business_metric_aggregates = defaultdict(lambda: {
            'count': 0,
            'sum': 0,
            'min': float('inf'),
            'max': 0,
            'last_value': 0
        })
        
        # Start background processing
        self._start_background_processing()
    
    def create_trace(self, service: str, operation: str, 
                    parent_trace_id: Optional[str] = None,
                    parent_span_id: Optional[str] = None) -> str:
        """Create a new distributed trace."""
        trace_id = str(uuid.uuid4())
        span_id = str(uuid.uuid4())
        
        span = TraceSpan(
            trace_id=trace_id,
            span_id=span_id,
            parent_span_id=parent_span_id,
            service=service,
            operation=operation,
            start_time=datetime.now(),
            tags={},
            logs=[]
        )
        
        with self._lock:
            self._active_traces[trace_id] = span
        
        self.logger.info(f"Started trace {trace_id} for {service}.{operation}")
        return trace_id
    
    def finish_trace(self, trace_id: str, error: bool = False, 
                    error_message: Optional[str] = None) -> None:
        """Finish a distributed trace."""
        with self._lock:
            if trace_id not in self._active_traces:
                self.logger.warning(f"Attempted to finish unknown trace: {trace_id}")
                return
            
            span = self._active_traces[trace_id]
            span.end_time = datetime.now()
            span.duration_ms = (span.end_time - span.start_time).total_seconds() * 1000
            span.error = error
            
            if error and error_message:
                span.logs.append({
                    'timestamp': datetime.now().isoformat(),
                    'level': 'ERROR',
                    'message': error_message
                })
            
            # Move to completed traces
            self._completed_traces.append(span)
            del self._active_traces[trace_id]
            
            # Update operation statistics
            operation_key = f"{span.service}.{span.operation}"
            stats = self._operation_stats[operation_key]
            stats['count'] += 1
            stats['total_duration'] += span.duration_ms
            stats['min_duration'] = min(stats['min_duration'], span.duration_ms)
            stats['max_duration'] = max(stats['max_duration'], span.duration_ms)
            if error:
                stats['error_count'] += 1
        
        self.logger.info(f"Finished trace {trace_id} in {span.duration_ms:.2f}ms (error: {error})")
    
    @asynccontextmanager
    async def trace_operation(self, service: str, operation: str,
                             parent_trace_id: Optional[str] = None,
                             parent_span_id: Optional[str] = None):
        """Context manager for tracing operations."""
        trace_id = self.create_trace(service, operation, parent_trace_id, parent_span_id)
        
        try:
            yield trace_id
            self.finish_trace(trace_id, error=False)
        except Exception as e:
            self.finish_trace(trace_id, error=True, error_message=str(e))
            raise
    
    def log_structured(self, level: str, service: str, operation: str, message: str,
                      trace_id: Optional[str] = None, span_id: Optional[str] = None,
                      user_id: Optional[str] = None, session_id: Optional[str] = None,
                      duration_ms: Optional[float] = None, metadata: Optional[Dict[str, Any]] = None,
                      error: Optional[Exception] = None) -> None:
        """Log a structured log entry."""
        
        error_str = None
        stack_trace = None
        if error:
            error_str = str(error)
            stack_trace = traceback.format_exc()
            
            # Track error patterns
            error_key = f"{service}.{operation}.{type(error).__name__}"
            with self._lock:
                self._error_counts[error_key] += 1
                self._error_patterns[error_key].append({
                    'timestamp': datetime.now(),
                    'message': error_str,
                    'trace_id': trace_id
                })
                # Keep only last 100 errors per pattern
                if len(self._error_patterns[error_key]) > 100:
                    self._error_patterns[error_key] = self._error_patterns[error_key][-100:]
        
        log_entry = LogEntry(
            timestamp=datetime.now(),
            level=level.upper(),
            service=service,
            operation=operation,
            message=message,
            trace_id=trace_id,
            span_id=span_id,
            user_id=user_id,
            session_id=session_id,
            duration_ms=duration_ms,
            metadata=metadata,
            error=error_str,
            stack_trace=stack_trace
        )
        
        with self._lock:
            self._log_entries.append(log_entry)
        
        # Also log to standard logger
        log_data = {
            'service': service,
            'operation': operation,
            'trace_id': trace_id,
            'user_id': user_id,
            'duration_ms': duration_ms,
            'metadata': metadata
        }
        
        if level.upper() == 'ERROR':
            self.logger.error(message, extra=log_data, exc_info=error)
        elif level.upper() == 'WARNING':
            self.logger.warning(message, extra=log_data)
        elif level.upper() == 'INFO':
            self.logger.info(message, extra=log_data)
        elif level.upper() == 'DEBUG':
            self.logger.debug(message, extra=log_data)
    
    def log_performance(self, service: str, operation: str, duration_ms: float,
                       success: bool = True, trace_id: Optional[str] = None,
                       metadata: Optional[Dict[str, Any]] = None) -> None:
        """Log a performance metric."""
        
        metric = PerformanceMetric(
            timestamp=datetime.now(),
            service=service,
            operation=operation,
            duration_ms=duration_ms,
            success=success,
            trace_id=trace_id,
            metadata=metadata
        )
        
        with self._lock:
            self._performance_metrics.append(metric)
        
        # Log structured entry
        self.log_structured(
            level='INFO',
            service=service,
            operation=operation,
            message=f"Performance: {operation} completed in {duration_ms:.2f}ms (success: {success})",
            trace_id=trace_id,
            duration_ms=duration_ms,
            metadata=metadata
        )
    
    def log_business_metric(self, metric_name: str, metric_value: Union[int, float],
                           metric_type: str = 'counter', tags: Optional[Dict[str, str]] = None,
                           trace_id: Optional[str] = None) -> None:
        """Log a business metric."""
        
        metric = BusinessMetric(
            timestamp=datetime.now(),
            metric_name=metric_name,
            metric_value=metric_value,
            metric_type=metric_type,
            tags=tags,
            trace_id=trace_id
        )
        
        with self._lock:
            self._business_metrics.append(metric)
            
            # Update aggregates
            agg = self._business_metric_aggregates[metric_name]
            agg['count'] += 1
            agg['last_value'] = metric_value
            
            if metric_type in ['counter', 'gauge']:
                agg['sum'] += metric_value
                agg['min'] = min(agg['min'], metric_value)
                agg['max'] = max(agg['max'], metric_value)
        
        # Log structured entry
        self.log_structured(
            level='INFO',
            service='business_metrics',
            operation='metric_recorded',
            message=f"Business metric: {metric_name} = {metric_value} ({metric_type})",
            trace_id=trace_id,
            metadata={'metric_name': metric_name, 'metric_value': metric_value, 'metric_type': metric_type, 'tags': tags}
        )
    
    def get_logs(self, service: Optional[str] = None, operation: Optional[str] = None,
                level: Optional[str] = None, trace_id: Optional[str] = None,
                user_id: Optional[str] = None, hours: int = 24,
                limit: int = 1000) -> List[Dict[str, Any]]:
        """Get filtered log entries."""
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with self._lock:
            filtered_logs = []
            
            for log_entry in reversed(self._log_entries):
                if log_entry.timestamp < cutoff_time:
                    break
                
                # Apply filters
                if service and log_entry.service != service:
                    continue
                if operation and log_entry.operation != operation:
                    continue
                if level and log_entry.level != level.upper():
                    continue
                if trace_id and log_entry.trace_id != trace_id:
                    continue
                if user_id and log_entry.user_id != user_id:
                    continue
                
                filtered_logs.append(asdict(log_entry))
                
                if len(filtered_logs) >= limit:
                    break
            
            return filtered_logs
    
    def get_performance_metrics(self, service: Optional[str] = None,
                               operation: Optional[str] = None,
                               hours: int = 24) -> Dict[str, Any]:
        """Get performance metrics summary."""
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with self._lock:
            filtered_metrics = [
                metric for metric in self._performance_metrics
                if metric.timestamp >= cutoff_time and
                (not service or metric.service == service) and
                (not operation or metric.operation == operation)
            ]
            
            if not filtered_metrics:
                return {'error': 'No performance metrics found for the specified criteria'}
            
            # Calculate statistics
            durations = [m.duration_ms for m in filtered_metrics]
            success_count = sum(1 for m in filtered_metrics if m.success)
            
            return {
                'total_operations': len(filtered_metrics),
                'success_rate': (success_count / len(filtered_metrics)) * 100,
                'performance': {
                    'avg_duration_ms': sum(durations) / len(durations),
                    'min_duration_ms': min(durations),
                    'max_duration_ms': max(durations),
                    'p95_duration_ms': sorted(durations)[int(len(durations) * 0.95)] if len(durations) > 1 else durations[0],
                    'p99_duration_ms': sorted(durations)[int(len(durations) * 0.99)] if len(durations) > 1 else durations[0]
                },
                'time_period_hours': hours,
                'service_filter': service,
                'operation_filter': operation
            }
    
    def get_business_metrics(self, metric_name: Optional[str] = None,
                            hours: int = 24) -> Dict[str, Any]:
        """Get business metrics summary."""
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with self._lock:
            filtered_metrics = [
                metric for metric in self._business_metrics
                if metric.timestamp >= cutoff_time and
                (not metric_name or metric.metric_name == metric_name)
            ]
            
            if not filtered_metrics:
                return {'error': 'No business metrics found for the specified criteria'}
            
            # Group by metric name
            metrics_by_name = defaultdict(list)
            for metric in filtered_metrics:
                metrics_by_name[metric.metric_name].append(metric)
            
            summary = {}
            for name, metrics in metrics_by_name.items():
                values = [m.metric_value for m in metrics]
                summary[name] = {
                    'count': len(metrics),
                    'latest_value': metrics[-1].metric_value,
                    'sum': sum(values),
                    'avg': sum(values) / len(values),
                    'min': min(values),
                    'max': max(values),
                    'metric_type': metrics[-1].metric_type
                }
            
            return {
                'metrics': summary,
                'time_period_hours': hours,
                'metric_filter': metric_name
            }
    
    def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get error summary and patterns."""
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with self._lock:
            # Get recent errors
            recent_errors = []
            for pattern_key, errors in self._error_patterns.items():
                recent_pattern_errors = [
                    error for error in errors
                    if error['timestamp'] >= cutoff_time
                ]
                if recent_pattern_errors:
                    recent_errors.extend([
                        {
                            'pattern': pattern_key,
                            'count': len(recent_pattern_errors),
                            'latest_error': recent_pattern_errors[-1]
                        }
                    ])
            
            # Sort by error count
            recent_errors.sort(key=lambda x: x['count'], reverse=True)
            
            # Get total error counts
            total_errors = sum(len(errors) for errors in self._error_patterns.values())
            recent_error_count = sum(error['count'] for error in recent_errors)
            
            return {
                'total_error_patterns': len(self._error_patterns),
                'total_errors_all_time': total_errors,
                'recent_errors_count': recent_error_count,
                'time_period_hours': hours,
                'top_error_patterns': recent_errors[:10],
                'error_rate_per_hour': recent_error_count / max(1, hours)
            }
    
    def get_trace_summary(self, trace_id: Optional[str] = None,
                         hours: int = 24) -> Dict[str, Any]:
        """Get distributed tracing summary."""
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        with self._lock:
            if trace_id:
                # Get specific trace
                for trace in self._completed_traces:
                    if trace.trace_id == trace_id:
                        return {
                            'trace': asdict(trace),
                            'logs': self.get_logs(trace_id=trace_id, hours=hours, limit=100)
                        }
                
                # Check active traces
                if trace_id in self._active_traces:
                    trace = self._active_traces[trace_id]
                    return {
                        'trace': asdict(trace),
                        'status': 'active',
                        'logs': self.get_logs(trace_id=trace_id, hours=hours, limit=100)
                    }
                
                return {'error': f'Trace {trace_id} not found'}
            
            else:
                # Get trace summary
                recent_traces = [
                    trace for trace in self._completed_traces
                    if trace.start_time >= cutoff_time
                ]
                
                if not recent_traces:
                    return {'error': 'No traces found for the specified time period'}
                
                # Calculate statistics
                durations = [t.duration_ms for t in recent_traces if t.duration_ms]
                error_count = sum(1 for t in recent_traces if t.error)
                
                # Group by service and operation
                service_stats = defaultdict(lambda: {'count': 0, 'errors': 0, 'total_duration': 0})
                for trace in recent_traces:
                    key = f"{trace.service}.{trace.operation}"
                    service_stats[key]['count'] += 1
                    if trace.error:
                        service_stats[key]['errors'] += 1
                    if trace.duration_ms:
                        service_stats[key]['total_duration'] += trace.duration_ms
                
                return {
                    'total_traces': len(recent_traces),
                    'active_traces': len(self._active_traces),
                    'error_rate': (error_count / len(recent_traces)) * 100,
                    'avg_duration_ms': sum(durations) / len(durations) if durations else 0,
                    'service_breakdown': dict(service_stats),
                    'time_period_hours': hours
                }
    
    def get_operation_stats(self, hours: int = 24) -> Dict[str, Any]:
        """Get operation performance statistics."""
        
        with self._lock:
            stats_summary = {}
            
            for operation, stats in self._operation_stats.items():
                if stats['count'] > 0:
                    avg_duration = stats['total_duration'] / stats['count']
                    error_rate = (stats['error_count'] / stats['count']) * 100
                    
                    stats_summary[operation] = {
                        'total_calls': stats['count'],
                        'avg_duration_ms': round(avg_duration, 2),
                        'min_duration_ms': round(stats['min_duration'], 2),
                        'max_duration_ms': round(stats['max_duration'], 2),
                        'error_count': stats['error_count'],
                        'error_rate_percent': round(error_rate, 2)
                    }
            
            # Sort by call count
            sorted_stats = dict(sorted(stats_summary.items(), key=lambda x: x[1]['total_calls'], reverse=True))
            
            return {
                'operations': sorted_stats,
                'total_operations': len(sorted_stats),
                'summary_note': 'Statistics are cumulative since service start'
            }
    
    def export_logs(self, filepath: Optional[str] = None, hours: int = 24) -> str:
        """Export logs to JSON file."""
        
        if not filepath:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filepath = f"logs_export_{timestamp}.json"
        
        export_data = {
            'export_timestamp': datetime.now().isoformat(),
            'time_period_hours': hours,
            'logs': self.get_logs(hours=hours, limit=10000),
            'performance_metrics': self.get_performance_metrics(hours=hours),
            'business_metrics': self.get_business_metrics(hours=hours),
            'error_summary': self.get_error_summary(hours=hours),
            'trace_summary': self.get_trace_summary(hours=hours),
            'operation_stats': self.get_operation_stats(hours=hours)
        }
        
        try:
            import os
            if filepath and os.path.dirname(filepath):
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            self.logger.info(f"Logs exported to {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"Failed to export logs: {e}")
            raise
    
    def _start_background_processing(self) -> None:
        """Start background processing for log aggregation and cleanup."""
        
        def background_processor():
            while True:
                try:
                    # Clean up old data every hour
                    self._cleanup_old_data()
                    
                    # Log system health every 5 minutes
                    self._log_system_health()
                    
                    # Sleep for 5 minutes
                    time.sleep(300)
                    
                except Exception as e:
                    self.logger.error(f"Error in background log processing: {e}")
                    time.sleep(300)  # Continue after error
        
        # Start background thread
        thread = threading.Thread(target=background_processor, daemon=True)
        thread.start()
        self.logger.info("Background log processing started")
    
    def _cleanup_old_data(self) -> None:
        """Clean up old log data to prevent memory issues."""
        
        cutoff_time = datetime.now() - timedelta(days=7)  # Keep 7 days
        
        with self._lock:
            # Clean up error patterns
            for pattern_key in list(self._error_patterns.keys()):
                self._error_patterns[pattern_key] = [
                    error for error in self._error_patterns[pattern_key]
                    if error['timestamp'] >= cutoff_time
                ]
                
                # Remove empty patterns
                if not self._error_patterns[pattern_key]:
                    del self._error_patterns[pattern_key]
                    if pattern_key in self._error_counts:
                        del self._error_counts[pattern_key]
        
        self.logger.debug("Completed log data cleanup")
    
    def _log_system_health(self) -> None:
        """Log system health metrics."""
        
        with self._lock:
            log_count = len(self._log_entries)
            performance_count = len(self._performance_metrics)
            business_count = len(self._business_metrics)
            active_traces = len(self._active_traces)
            completed_traces = len(self._completed_traces)
            error_patterns = len(self._error_patterns)
        
        self.log_structured(
            level='INFO',
            service='logging_service',
            operation='system_health',
            message='Logging service health check',
            metadata={
                'log_entries': log_count,
                'performance_metrics': performance_count,
                'business_metrics': business_count,
                'active_traces': active_traces,
                'completed_traces': completed_traces,
                'error_patterns': error_patterns
            }
        )


# Global logging service instance
_logging_service = None


def get_logging_service() -> LoggingService:
    """Get the global logging service instance."""
    global _logging_service
    if _logging_service is None:
        _logging_service = LoggingService()
    return _logging_service


# Convenience functions for common logging operations
def log_info(service: str, operation: str, message: str, **kwargs):
    """Log an info message."""
    get_logging_service().log_structured('INFO', service, operation, message, **kwargs)


def log_warning(service: str, operation: str, message: str, **kwargs):
    """Log a warning message."""
    get_logging_service().log_structured('WARNING', service, operation, message, **kwargs)


def log_error(service: str, operation: str, message: str, error: Optional[Exception] = None, **kwargs):
    """Log an error message."""
    get_logging_service().log_structured('ERROR', service, operation, message, error=error, **kwargs)


def log_performance(service: str, operation: str, duration_ms: float, success: bool = True, **kwargs):
    """Log a performance metric."""
    get_logging_service().log_performance(service, operation, duration_ms, success, **kwargs)


def log_business_metric(metric_name: str, metric_value: Union[int, float], 
                       metric_type: str = 'counter', **kwargs):
    """Log a business metric."""
    get_logging_service().log_business_metric(metric_name, metric_value, metric_type, **kwargs)


def create_trace(service: str, operation: str, **kwargs) -> str:
    """Create a new distributed trace."""
    return get_logging_service().create_trace(service, operation, **kwargs)


def finish_trace(trace_id: str, error: bool = False, error_message: Optional[str] = None):
    """Finish a distributed trace."""
    get_logging_service().finish_trace(trace_id, error, error_message)


def trace_operation(service: str, operation: str, **kwargs):
    """Context manager for tracing operations."""
    return get_logging_service().trace_operation(service, operation, **kwargs)