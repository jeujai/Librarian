"""
Comprehensive metrics collection service for system integration and stability monitoring.

This module provides comprehensive metrics collection including:
- Response time tracking across all endpoints
- Resource usage monitoring (CPU, memory, disk, network)
- User session metrics and activity patterns
- Search performance and caching effectiveness
- Document processing metrics
- AI service usage patterns
- Real-time performance dashboards
"""

import asyncio
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from collections import defaultdict, deque
from dataclasses import dataclass, asdict
import json
import os
import psutil
import uuid

from ..config import get_settings
from ..logging_config import get_logger


@dataclass
class ResponseTimeMetric:
    """Response time metric data structure."""
    timestamp: datetime
    endpoint: str
    method: str
    response_time_ms: float
    status_code: int
    user_id: Optional[str] = None
    user_agent: Optional[str] = None
    request_size_bytes: Optional[int] = None
    response_size_bytes: Optional[int] = None


@dataclass
class ResourceUsageMetric:
    """Resource usage metric data structure."""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    memory_available_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_free_gb: float
    network_bytes_sent: int
    network_bytes_recv: int
    active_connections: int
    load_average: List[float]


@dataclass
class UserSessionMetric:
    """User session metric data structure."""
    session_id: str
    user_id: Optional[str]
    start_time: datetime
    last_activity: datetime
    total_requests: int
    total_response_time_ms: float
    endpoints_accessed: Set[str]
    user_agent: Optional[str]
    ip_address: Optional[str]
    is_active: bool = True


@dataclass
class SearchPerformanceMetric:
    """Search performance metric data structure."""
    timestamp: datetime
    query_text: str
    search_type: str  # vector, hybrid, simple
    response_time_ms: float
    results_count: int
    cache_hit: bool
    user_id: Optional[str] = None
    query_complexity_score: Optional[float] = None


@dataclass
class DocumentProcessingMetric:
    """Document processing metric data structure."""
    timestamp: datetime
    document_id: str
    document_size_mb: float
    processing_time_ms: float
    processing_stage: str  # upload, extract, chunk, embed, index
    success: bool
    error_message: Optional[str] = None


class ComprehensiveMetricsCollector:
    """
    Comprehensive metrics collector for system integration and stability monitoring.
    
    Collects detailed metrics across all system components including response times,
    resource usage, user sessions, search performance, and document processing.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = get_logger("comprehensive_metrics")
        
        # Thread-safe storage
        self._lock = threading.Lock()
        
        # Metrics storage with configurable retention
        self._response_times = deque(maxlen=50000)  # Last 50k requests
        self._resource_usage = deque(maxlen=2880)   # 48 hours at 1-minute intervals
        self._user_sessions: Dict[str, UserSessionMetric] = {}
        self._search_performance = deque(maxlen=10000)  # Last 10k searches
        self._document_processing = deque(maxlen=5000)  # Last 5k document operations
        
        # Real-time tracking
        self._active_users: Set[str] = set()
        self._concurrent_requests = 0
        self._peak_concurrent_requests = 0
        self._system_start_time = datetime.now()
        
        # Performance aggregations
        self._hourly_aggregates = defaultdict(lambda: {
            'requests': 0,
            'total_response_time': 0,
            'errors': 0,
            'unique_users': set(),
            'search_queries': 0,
            'documents_processed': 0
        })
        
        # Caching metrics
        self._cache_metrics = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'size_bytes': 0,
            'hit_rate_history': deque(maxlen=1440)  # 24 hours
        }
        
        # Network and connection metrics
        self._network_baseline = self._get_network_baseline()
        
        # Start background collection
        self._collection_active = True
        self._start_background_collection()
    
    def record_response_time(self, endpoint: str, method: str, response_time_ms: float,
                           status_code: int, user_id: Optional[str] = None,
                           user_agent: Optional[str] = None,
                           request_size_bytes: Optional[int] = None,
                           response_size_bytes: Optional[int] = None) -> None:
        """Record a response time metric."""
        with self._lock:
            timestamp = datetime.now()
            
            metric = ResponseTimeMetric(
                timestamp=timestamp,
                endpoint=endpoint,
                method=method,
                response_time_ms=response_time_ms,
                status_code=status_code,
                user_id=user_id,
                user_agent=user_agent,
                request_size_bytes=request_size_bytes,
                response_size_bytes=response_size_bytes
            )
            
            self._response_times.append(metric)
            
            # Update hourly aggregates
            hour_key = timestamp.strftime('%Y-%m-%d %H')
            self._hourly_aggregates[hour_key]['requests'] += 1
            self._hourly_aggregates[hour_key]['total_response_time'] += response_time_ms
            
            if status_code >= 400:
                self._hourly_aggregates[hour_key]['errors'] += 1
            
            if user_id:
                self._hourly_aggregates[hour_key]['unique_users'].add(user_id)
                self._active_users.add(user_id)
            
            # Track concurrent requests
            self._concurrent_requests += 1
            if self._concurrent_requests > self._peak_concurrent_requests:
                self._peak_concurrent_requests = self._concurrent_requests
    
    def record_request_start(self) -> None:
        """Record the start of a request for concurrent tracking."""
        with self._lock:
            self._concurrent_requests += 1
            if self._concurrent_requests > self._peak_concurrent_requests:
                self._peak_concurrent_requests = self._concurrent_requests
    
    def record_request_end(self) -> None:
        """Record the end of a request for concurrent tracking."""
        with self._lock:
            self._concurrent_requests = max(0, self._concurrent_requests - 1)
    
    def record_user_session_activity(self, session_id: str, user_id: Optional[str] = None,
                                   endpoint: str = "", response_time_ms: float = 0,
                                   user_agent: Optional[str] = None,
                                   ip_address: Optional[str] = None) -> None:
        """Record user session activity."""
        with self._lock:
            now = datetime.now()
            
            if session_id not in self._user_sessions:
                self._user_sessions[session_id] = UserSessionMetric(
                    session_id=session_id,
                    user_id=user_id,
                    start_time=now,
                    last_activity=now,
                    total_requests=0,
                    total_response_time_ms=0,
                    endpoints_accessed=set(),
                    user_agent=user_agent,
                    ip_address=ip_address
                )
            
            session = self._user_sessions[session_id]
            session.last_activity = now
            session.total_requests += 1
            session.total_response_time_ms += response_time_ms
            
            if endpoint:
                session.endpoints_accessed.add(endpoint)
            
            # Mark session as active if activity within last 30 minutes
            session.is_active = (now - session.last_activity).total_seconds() <= 1800
    
    def record_search_performance(self, query_text: str, search_type: str,
                                response_time_ms: float, results_count: int,
                                cache_hit: bool, user_id: Optional[str] = None,
                                query_complexity_score: Optional[float] = None) -> None:
        """Record search performance metrics."""
        with self._lock:
            timestamp = datetime.now()
            
            metric = SearchPerformanceMetric(
                timestamp=timestamp,
                query_text=query_text[:100],  # Truncate for privacy
                search_type=search_type,
                response_time_ms=response_time_ms,
                results_count=results_count,
                cache_hit=cache_hit,
                user_id=user_id,
                query_complexity_score=query_complexity_score
            )
            
            self._search_performance.append(metric)
            
            # Update cache metrics
            if cache_hit:
                self._cache_metrics['hits'] += 1
            else:
                self._cache_metrics['misses'] += 1
            
            # Update hourly aggregates
            hour_key = timestamp.strftime('%Y-%m-%d %H')
            self._hourly_aggregates[hour_key]['search_queries'] += 1
    
    def record_document_processing(self, document_id: str, document_size_mb: float,
                                 processing_time_ms: float, processing_stage: str,
                                 success: bool, error_message: Optional[str] = None) -> None:
        """Record document processing metrics."""
        with self._lock:
            timestamp = datetime.now()
            
            metric = DocumentProcessingMetric(
                timestamp=timestamp,
                document_id=document_id,
                document_size_mb=document_size_mb,
                processing_time_ms=processing_time_ms,
                processing_stage=processing_stage,
                success=success,
                error_message=error_message
            )
            
            self._document_processing.append(metric)
            
            # Update hourly aggregates
            hour_key = timestamp.strftime('%Y-%m-%d %H')
            if success:
                self._hourly_aggregates[hour_key]['documents_processed'] += 1
    
    def record_cache_event(self, event_type: str, size_bytes: int = 0) -> None:
        """Record cache-related events."""
        with self._lock:
            if event_type == 'hit':
                self._cache_metrics['hits'] += 1
            elif event_type == 'miss':
                self._cache_metrics['misses'] += 1
            elif event_type == 'eviction':
                self._cache_metrics['evictions'] += 1
            elif event_type == 'size_update':
                self._cache_metrics['size_bytes'] = size_bytes
    
    def get_real_time_metrics(self) -> Dict[str, Any]:
        """Get real-time system metrics."""
        with self._lock:
            now = datetime.now()
            uptime_seconds = (now - self._system_start_time).total_seconds()
            
            # Recent performance (last 5 minutes)
            recent_cutoff = now - timedelta(minutes=5)
            recent_responses = [
                r for r in self._response_times
                if r.timestamp >= recent_cutoff
            ]
            
            # Calculate response time statistics
            if recent_responses:
                response_times = [r.response_time_ms for r in recent_responses]
                avg_response_time = sum(response_times) / len(response_times)
                p50_response_time = sorted(response_times)[len(response_times) // 2]
                p95_response_time = sorted(response_times)[int(len(response_times) * 0.95)]
                p99_response_time = sorted(response_times)[int(len(response_times) * 0.99)]
            else:
                avg_response_time = p50_response_time = p95_response_time = p99_response_time = 0
            
            # Active sessions
            active_sessions = [
                s for s in self._user_sessions.values()
                if s.is_active and (now - s.last_activity).total_seconds() <= 1800
            ]
            
            # Cache hit rate
            total_cache_requests = self._cache_metrics['hits'] + self._cache_metrics['misses']
            cache_hit_rate = (
                (self._cache_metrics['hits'] / total_cache_requests * 100)
                if total_cache_requests > 0 else 0
            )
            
            # Recent search performance
            recent_searches = [
                s for s in self._search_performance
                if s.timestamp >= recent_cutoff
            ]
            
            search_stats = {}
            if recent_searches:
                search_times = [s.response_time_ms for s in recent_searches]
                search_stats = {
                    'total_searches': len(recent_searches),
                    'avg_search_time_ms': sum(search_times) / len(search_times),
                    'cache_hit_rate': len([s for s in recent_searches if s.cache_hit]) / len(recent_searches) * 100
                }
            
            return {
                'timestamp': now.isoformat(),
                'system_uptime_hours': round(uptime_seconds / 3600, 2),
                'response_time_metrics': {
                    'avg_response_time_ms': round(avg_response_time, 2),
                    'p50_response_time_ms': round(p50_response_time, 2),
                    'p95_response_time_ms': round(p95_response_time, 2),
                    'p99_response_time_ms': round(p99_response_time, 2),
                    'total_requests_5min': len(recent_responses)
                },
                'resource_usage': self._get_current_resource_usage(),
                'user_session_metrics': {
                    'active_sessions': len(active_sessions),
                    'total_sessions': len(self._user_sessions),
                    'concurrent_requests': self._concurrent_requests,
                    'peak_concurrent_requests': self._peak_concurrent_requests,
                    'unique_users_active': len(self._active_users)
                },
                'search_performance': search_stats,
                'cache_metrics': {
                    'hit_rate_percent': round(cache_hit_rate, 2),
                    'total_hits': self._cache_metrics['hits'],
                    'total_misses': self._cache_metrics['misses'],
                    'cache_size_mb': round(self._cache_metrics['size_bytes'] / 1024 / 1024, 2)
                }
            }
    
    def get_performance_trends(self, hours: int = 24) -> Dict[str, Any]:
        """Get performance trends over the specified time period."""
        with self._lock:
            now = datetime.now()
            cutoff_time = now - timedelta(hours=hours)
            
            # Filter data by time period
            recent_responses = [
                r for r in self._response_times
                if r.timestamp >= cutoff_time
            ]
            
            recent_searches = [
                s for s in self._search_performance
                if s.timestamp >= cutoff_time
            ]
            
            recent_processing = [
                p for p in self._document_processing
                if p.timestamp >= cutoff_time
            ]
            
            # Group by hour for trends
            hourly_trends = defaultdict(lambda: {
                'hour': '',
                'requests': 0,
                'avg_response_time': 0,
                'errors': 0,
                'searches': 0,
                'documents_processed': 0,
                'unique_users': set()
            })
            
            # Process response time data
            for response in recent_responses:
                hour_key = response.timestamp.strftime('%Y-%m-%d %H:00')
                hourly_trends[hour_key]['hour'] = hour_key
                hourly_trends[hour_key]['requests'] += 1
                hourly_trends[hour_key]['avg_response_time'] += response.response_time_ms
                
                if response.status_code >= 400:
                    hourly_trends[hour_key]['errors'] += 1
                
                if response.user_id:
                    hourly_trends[hour_key]['unique_users'].add(response.user_id)
            
            # Process search data
            for search in recent_searches:
                hour_key = search.timestamp.strftime('%Y-%m-%d %H:00')
                hourly_trends[hour_key]['searches'] += 1
            
            # Process document processing data
            for doc in recent_processing:
                if doc.success:
                    hour_key = doc.timestamp.strftime('%Y-%m-%d %H:00')
                    hourly_trends[hour_key]['documents_processed'] += 1
            
            # Calculate averages and convert to list
            trend_data = []
            for hour_data in sorted(hourly_trends.values(), key=lambda x: x['hour']):
                if hour_data['requests'] > 0:
                    hour_data['avg_response_time'] /= hour_data['requests']
                    hour_data['error_rate'] = (hour_data['errors'] / hour_data['requests']) * 100
                    hour_data['unique_users'] = len(hour_data['unique_users'])
                    trend_data.append(hour_data)
            
            return {
                'period_hours': hours,
                'hourly_trends': trend_data,
                'summary': {
                    'total_requests': len(recent_responses),
                    'total_searches': len(recent_searches),
                    'total_documents_processed': len([p for p in recent_processing if p.success]),
                    'avg_response_time_ms': (
                        sum(r.response_time_ms for r in recent_responses) / len(recent_responses)
                        if recent_responses else 0
                    ),
                    'error_rate_percent': (
                        len([r for r in recent_responses if r.status_code >= 400]) / len(recent_responses) * 100
                        if recent_responses else 0
                    )
                }
            }
    
    def get_user_session_analytics(self) -> Dict[str, Any]:
        """Get detailed user session analytics."""
        with self._lock:
            now = datetime.now()
            
            # Active sessions (activity within last 30 minutes)
            active_sessions = [
                s for s in self._user_sessions.values()
                if (now - s.last_activity).total_seconds() <= 1800
            ]
            
            # Session duration analysis
            session_durations = []
            for session in self._user_sessions.values():
                if not session.is_active:
                    duration = (session.last_activity - session.start_time).total_seconds()
                    session_durations.append(duration)
            
            # Calculate session statistics
            if session_durations:
                avg_session_duration = sum(session_durations) / len(session_durations)
                median_session_duration = sorted(session_durations)[len(session_durations) // 2]
            else:
                avg_session_duration = median_session_duration = 0
            
            # User engagement metrics
            total_requests = sum(s.total_requests for s in self._user_sessions.values())
            avg_requests_per_session = (
                total_requests / len(self._user_sessions)
                if self._user_sessions else 0
            )
            
            # Most active endpoints
            endpoint_usage = defaultdict(int)
            for session in self._user_sessions.values():
                for endpoint in session.endpoints_accessed:
                    endpoint_usage[endpoint] += 1
            
            top_endpoints = sorted(
                endpoint_usage.items(),
                key=lambda x: x[1],
                reverse=True
            )[:10]
            
            return {
                'active_sessions': len(active_sessions),
                'total_sessions': len(self._user_sessions),
                'session_analytics': {
                    'avg_session_duration_minutes': round(avg_session_duration / 60, 2),
                    'median_session_duration_minutes': round(median_session_duration / 60, 2),
                    'avg_requests_per_session': round(avg_requests_per_session, 2),
                    'total_requests': total_requests
                },
                'user_engagement': {
                    'unique_users': len(set(s.user_id for s in self._user_sessions.values() if s.user_id)),
                    'returning_users': len([
                        s for s in self._user_sessions.values()
                        if s.total_requests > 1
                    ]),
                    'top_endpoints': [{'endpoint': ep, 'usage_count': count} for ep, count in top_endpoints]
                }
            }
    
    def _get_current_resource_usage(self) -> Dict[str, Any]:
        """Get current system resource usage."""
        try:
            # CPU metrics
            cpu_percent = psutil.cpu_percent(interval=0.1)
            cpu_count = psutil.cpu_count()
            load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else [0, 0, 0]
            
            # Memory metrics
            memory = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            # Disk metrics
            disk = psutil.disk_usage('/')
            
            # Network metrics
            network = psutil.net_io_counters()
            network_delta = {
                'bytes_sent_delta': network.bytes_sent - self._network_baseline.get('bytes_sent', 0),
                'bytes_recv_delta': network.bytes_recv - self._network_baseline.get('bytes_recv', 0)
            }
            
            # Process metrics
            process = psutil.Process()
            process_memory = process.memory_info()
            
            return {
                'cpu': {
                    'percent': round(cpu_percent, 2),
                    'count': cpu_count,
                    'load_average': [round(l, 2) for l in load_avg]
                },
                'memory': {
                    'total_gb': round(memory.total / 1024**3, 2),
                    'used_gb': round(memory.used / 1024**3, 2),
                    'available_gb': round(memory.available / 1024**3, 2),
                    'percent': round(memory.percent, 2),
                    'swap_percent': round(swap.percent, 2)
                },
                'disk': {
                    'total_gb': round(disk.total / 1024**3, 2),
                    'used_gb': round(disk.used / 1024**3, 2),
                    'free_gb': round(disk.free / 1024**3, 2),
                    'percent': round(disk.percent, 2)
                },
                'network': {
                    'bytes_sent': network.bytes_sent,
                    'bytes_recv': network.bytes_recv,
                    'bytes_sent_delta': network_delta['bytes_sent_delta'],
                    'bytes_recv_delta': network_delta['bytes_recv_delta']
                },
                'process': {
                    'memory_rss_mb': round(process_memory.rss / 1024**2, 2),
                    'memory_vms_mb': round(process_memory.vms / 1024**2, 2),
                    'open_files': len(process.open_files()),
                    'connections': len(process.connections())
                }
            }
            
        except Exception as e:
            self.logger.error(f"Error collecting resource usage: {e}")
            return {'error': str(e)}
    
    def _get_network_baseline(self) -> Dict[str, int]:
        """Get network baseline for delta calculations."""
        try:
            network = psutil.net_io_counters()
            return {
                'bytes_sent': network.bytes_sent,
                'bytes_recv': network.bytes_recv
            }
        except Exception:
            return {'bytes_sent': 0, 'bytes_recv': 0}
    
    def _start_background_collection(self) -> None:
        """Start background resource collection."""
        def collect_resources():
            while self._collection_active:
                try:
                    resource_usage = self._get_current_resource_usage()
                    
                    if 'error' not in resource_usage:
                        with self._lock:
                            metric = ResourceUsageMetric(
                                timestamp=datetime.now(),
                                cpu_percent=resource_usage['cpu']['percent'],
                                memory_percent=resource_usage['memory']['percent'],
                                memory_used_gb=resource_usage['memory']['used_gb'],
                                memory_available_gb=resource_usage['memory']['available_gb'],
                                disk_percent=resource_usage['disk']['percent'],
                                disk_used_gb=resource_usage['disk']['used_gb'],
                                disk_free_gb=resource_usage['disk']['free_gb'],
                                network_bytes_sent=resource_usage['network']['bytes_sent'],
                                network_bytes_recv=resource_usage['network']['bytes_recv'],
                                active_connections=resource_usage['process']['connections'],
                                load_average=resource_usage['cpu']['load_average']
                            )
                            self._resource_usage.append(metric)
                    
                    # Clean up old sessions (inactive for more than 24 hours)
                    cutoff_time = datetime.now() - timedelta(hours=24)
                    with self._lock:
                        inactive_sessions = [
                            session_id for session_id, session in self._user_sessions.items()
                            if session.last_activity < cutoff_time
                        ]
                        for session_id in inactive_sessions:
                            del self._user_sessions[session_id]
                    
                    time.sleep(60)  # Collect every minute
                    
                except Exception as e:
                    self.logger.error(f"Error in background resource collection: {e}")
                    time.sleep(60)
        
        thread = threading.Thread(target=collect_resources, daemon=True)
        thread.start()
        self.logger.info("Background resource collection started")
    
    def export_comprehensive_report(self, filepath: Optional[str] = None) -> str:
        """Export comprehensive metrics report."""
        timestamp = datetime.now()
        
        report = {
            'export_timestamp': timestamp.isoformat(),
            'system_info': {
                'uptime_hours': (timestamp - self._system_start_time).total_seconds() / 3600,
                'python_version': os.sys.version,
                'platform': os.name
            },
            'real_time_metrics': self.get_real_time_metrics(),
            'performance_trends_24h': self.get_performance_trends(24),
            'user_session_analytics': self.get_user_session_analytics(),
            'detailed_metrics': {
                'total_response_records': len(self._response_times),
                'total_search_records': len(self._search_performance),
                'total_document_processing_records': len(self._document_processing),
                'total_resource_usage_records': len(self._resource_usage)
            }
        }
        
        if not filepath:
            timestamp_str = timestamp.strftime('%Y%m%d_%H%M%S')
            filepath = f"comprehensive_metrics_report_{timestamp_str}.json"
        
        try:
            # Ensure directory exists
            if filepath and '/' in filepath:
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            
            self.logger.info(f"Comprehensive metrics report exported to {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"Failed to export comprehensive report: {e}")
            raise
    
    def stop_collection(self) -> None:
        """Stop background collection."""
        self._collection_active = False
        self.logger.info("Comprehensive metrics collection stopped")