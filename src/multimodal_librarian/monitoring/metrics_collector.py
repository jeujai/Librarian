"""
Metrics collection service for monitoring system performance.

This module collects and aggregates performance metrics including:
- API response times
- Request counts and rates
- Error rates and types
- Resource usage over time
- ML API usage statistics
"""

import time
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict, deque
import threading
import json
import os

from ..config import get_settings
from ..logging_config import get_logger


class MetricsCollector:
    """Collects and aggregates system performance metrics."""
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = get_logger("metrics_collector")
        
        # Thread-safe metrics storage
        self._lock = threading.Lock()
        
        # Request metrics
        self._request_times = deque(maxlen=10000)  # Last 10k requests
        self._request_counts = defaultdict(int)
        self._error_counts = defaultdict(int)
        self._endpoint_metrics = defaultdict(lambda: {
            'count': 0,
            'total_time': 0,
            'errors': 0,
            'last_request': None
        })
        
        # ML API metrics
        self._ml_metrics = {
            'chunk_requests': 0,
            'batch_requests': 0,
            'stream_requests': 0,
            'feedback_requests': 0,
            'total_chunks_served': 0,
            'avg_batch_size': 0,
            'stream_duration_total': 0
        }
        
        # Conversation metrics
        self._conversation_metrics = {
            'active_conversations': 0,
            'total_messages': 0,
            'websocket_connections': 0,
            'avg_message_length': 0,
            'multimedia_messages': 0
        }
        
        # System metrics history
        self._system_metrics_history = deque(maxlen=1440)  # 24 hours at 1-minute intervals
        
        # Start background metrics collection
        self._start_background_collection()
    
    def record_request(self, endpoint: str, method: str, response_time: float, 
                      status_code: int, user_id: Optional[str] = None) -> None:
        """Record a request metric."""
        with self._lock:
            timestamp = datetime.now()
            
            # Record request time
            self._request_times.append({
                'timestamp': timestamp,
                'response_time': response_time,
                'endpoint': endpoint,
                'method': method,
                'status_code': status_code,
                'user_id': user_id
            })
            
            # Update endpoint metrics
            endpoint_key = f"{method} {endpoint}"
            self._endpoint_metrics[endpoint_key]['count'] += 1
            self._endpoint_metrics[endpoint_key]['total_time'] += response_time
            self._endpoint_metrics[endpoint_key]['last_request'] = timestamp
            
            if status_code >= 400:
                self._endpoint_metrics[endpoint_key]['errors'] += 1
                self._error_counts[status_code] += 1
            
            # Update request counts by minute
            minute_key = timestamp.strftime('%Y-%m-%d %H:%M')
            self._request_counts[minute_key] += 1
    
    def record_ml_request(self, request_type: str, **kwargs) -> None:
        """Record ML API request metrics."""
        with self._lock:
            if request_type == 'chunk_stream':
                self._ml_metrics['chunk_requests'] += 1
                self._ml_metrics['total_chunks_served'] += kwargs.get('chunks_count', 0)
            
            elif request_type == 'training_batch':
                self._ml_metrics['batch_requests'] += 1
                batch_size = kwargs.get('batch_size', 0)
                current_avg = self._ml_metrics['avg_batch_size']
                total_batches = self._ml_metrics['batch_requests']
                self._ml_metrics['avg_batch_size'] = (
                    (current_avg * (total_batches - 1) + batch_size) / total_batches
                )
            
            elif request_type == 'stream_start':
                self._ml_metrics['stream_requests'] += 1
            
            elif request_type == 'stream_end':
                duration = kwargs.get('duration', 0)
                self._ml_metrics['stream_duration_total'] += duration
            
            elif request_type == 'feedback':
                self._ml_metrics['feedback_requests'] += 1
    
    def record_conversation_event(self, event_type: str, **kwargs) -> None:
        """Record conversation-related metrics."""
        with self._lock:
            if event_type == 'message_sent':
                self._conversation_metrics['total_messages'] += 1
                message_length = kwargs.get('message_length', 0)
                total_messages = self._conversation_metrics['total_messages']
                current_avg = self._conversation_metrics['avg_message_length']
                self._conversation_metrics['avg_message_length'] = (
                    (current_avg * (total_messages - 1) + message_length) / total_messages
                )
                
                if kwargs.get('has_multimedia', False):
                    self._conversation_metrics['multimedia_messages'] += 1
            
            elif event_type == 'websocket_connect':
                self._conversation_metrics['websocket_connections'] += 1
            
            elif event_type == 'websocket_disconnect':
                self._conversation_metrics['websocket_connections'] = max(
                    0, self._conversation_metrics['websocket_connections'] - 1
                )
            
            elif event_type == 'conversation_start':
                self._conversation_metrics['active_conversations'] += 1
            
            elif event_type == 'conversation_end':
                self._conversation_metrics['active_conversations'] = max(
                    0, self._conversation_metrics['active_conversations'] - 1
                )
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current system metrics."""
        with self._lock:
            now = datetime.now()
            
            # Calculate recent metrics (last 5 minutes)
            recent_requests = [
                req for req in self._request_times
                if (now - req['timestamp']).total_seconds() <= 300
            ]
            
            # Response time metrics
            if recent_requests:
                response_times = [req['response_time'] for req in recent_requests]
                avg_response_time = sum(response_times) / len(response_times)
                p95_response_time = sorted(response_times)[int(len(response_times) * 0.95)]
                p99_response_time = sorted(response_times)[int(len(response_times) * 0.99)]
            else:
                avg_response_time = p95_response_time = p99_response_time = 0
            
            # Request rate (requests per minute)
            requests_per_minute = len(recent_requests) / 5  # 5-minute window
            
            # Error rate
            recent_errors = [req for req in recent_requests if req['status_code'] >= 400]
            error_rate = (len(recent_errors) / len(recent_requests) * 100) if recent_requests else 0
            
            # Top endpoints by request count
            endpoint_stats = []
            for endpoint, stats in self._endpoint_metrics.items():
                if stats['count'] > 0:
                    endpoint_stats.append({
                        'endpoint': endpoint,
                        'count': stats['count'],
                        'avg_response_time': stats['total_time'] / stats['count'],
                        'error_rate': (stats['errors'] / stats['count'] * 100),
                        'last_request': stats['last_request'].isoformat() if stats['last_request'] else None
                    })
            
            endpoint_stats.sort(key=lambda x: x['count'], reverse=True)
            
            return {
                'timestamp': now.isoformat(),
                'request_metrics': {
                    'total_requests': len(self._request_times),
                    'requests_per_minute': round(requests_per_minute, 2),
                    'avg_response_time_ms': round(avg_response_time * 1000, 2),
                    'p95_response_time_ms': round(p95_response_time * 1000, 2),
                    'p99_response_time_ms': round(p99_response_time * 1000, 2),
                    'error_rate_percent': round(error_rate, 2),
                    'recent_requests_5min': len(recent_requests)
                },
                'ml_metrics': dict(self._ml_metrics),
                'conversation_metrics': dict(self._conversation_metrics),
                'top_endpoints': endpoint_stats[:10],
                'error_breakdown': dict(self._error_counts)
            }
    
    def get_historical_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """Get historical metrics for the specified time period."""
        with self._lock:
            now = datetime.now()
            cutoff_time = now - timedelta(hours=hours)
            
            # Filter historical data
            historical_requests = [
                req for req in self._request_times
                if req['timestamp'] >= cutoff_time
            ]
            
            # Group by hour
            hourly_metrics = defaultdict(lambda: {
                'requests': 0,
                'errors': 0,
                'total_response_time': 0,
                'hour': None
            })
            
            for req in historical_requests:
                hour_key = req['timestamp'].strftime('%Y-%m-%d %H:00')
                hourly_metrics[hour_key]['requests'] += 1
                hourly_metrics[hour_key]['total_response_time'] += req['response_time']
                hourly_metrics[hour_key]['hour'] = hour_key
                
                if req['status_code'] >= 400:
                    hourly_metrics[hour_key]['errors'] += 1
            
            # Convert to list and calculate averages
            hourly_data = []
            for hour_data in hourly_metrics.values():
                if hour_data['requests'] > 0:
                    hourly_data.append({
                        'hour': hour_data['hour'],
                        'requests': hour_data['requests'],
                        'errors': hour_data['errors'],
                        'error_rate': (hour_data['errors'] / hour_data['requests'] * 100),
                        'avg_response_time_ms': (hour_data['total_response_time'] / hour_data['requests'] * 1000)
                    })
            
            hourly_data.sort(key=lambda x: x['hour'])
            
            return {
                'period_hours': hours,
                'total_requests': len(historical_requests),
                'hourly_breakdown': hourly_data,
                'system_metrics_history': list(self._system_metrics_history)[-hours*60:]  # Last N hours
            }
    
    def export_metrics(self, filepath: Optional[str] = None) -> str:
        """Export current metrics to JSON file."""
        metrics = {
            'export_timestamp': datetime.now().isoformat(),
            'current_metrics': self.get_current_metrics(),
            'historical_metrics': self.get_historical_metrics(24)
        }
        
        if not filepath:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filepath = f"metrics_export_{timestamp}.json"
        
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w') as f:
                json.dump(metrics, f, indent=2, default=str)
            
            self.logger.info(f"Metrics exported to {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"Failed to export metrics: {e}")
            raise
    
    def reset_metrics(self) -> None:
        """Reset all metrics (use with caution)."""
        with self._lock:
            self._request_times.clear()
            self._request_counts.clear()
            self._error_counts.clear()
            self._endpoint_metrics.clear()
            
            # Reset ML metrics
            for key in self._ml_metrics:
                self._ml_metrics[key] = 0
            
            # Reset conversation metrics
            for key in self._conversation_metrics:
                self._conversation_metrics[key] = 0
            
            self._system_metrics_history.clear()
            
            self.logger.info("All metrics have been reset")
    
    def _start_background_collection(self) -> None:
        """Start background thread for periodic metrics collection."""
        def collect_system_metrics():
            while True:
                try:
                    import psutil
                    
                    # Collect system metrics
                    cpu_percent = psutil.cpu_percent(interval=1)
                    memory = psutil.virtual_memory()
                    disk = psutil.disk_usage('/')
                    
                    system_metric = {
                        'timestamp': datetime.now().isoformat(),
                        'cpu_percent': cpu_percent,
                        'memory_percent': memory.percent,
                        'disk_percent': disk.percent,
                        'memory_available_gb': memory.available / 1024**3,
                        'disk_free_gb': disk.free / 1024**3
                    }
                    
                    with self._lock:
                        self._system_metrics_history.append(system_metric)
                    
                    # Sleep for 1 minute
                    time.sleep(60)
                    
                except Exception as e:
                    self.logger.error(f"Error collecting system metrics: {e}")
                    time.sleep(60)  # Continue after error
        
        # Start background thread
        thread = threading.Thread(target=collect_system_metrics, daemon=True)
        thread.start()
        self.logger.info("Background metrics collection started")
    
    def get_ml_api_usage_report(self) -> Dict[str, Any]:
        """Get detailed ML API usage report."""
        with self._lock:
            total_requests = (
                self._ml_metrics['chunk_requests'] +
                self._ml_metrics['batch_requests'] +
                self._ml_metrics['stream_requests'] +
                self._ml_metrics['feedback_requests']
            )
            
            avg_stream_duration = 0
            if self._ml_metrics['stream_requests'] > 0:
                avg_stream_duration = (
                    self._ml_metrics['stream_duration_total'] / 
                    self._ml_metrics['stream_requests']
                )
            
            return {
                'total_ml_requests': total_requests,
                'breakdown': {
                    'chunk_requests': self._ml_metrics['chunk_requests'],
                    'batch_requests': self._ml_metrics['batch_requests'],
                    'stream_requests': self._ml_metrics['stream_requests'],
                    'feedback_requests': self._ml_metrics['feedback_requests']
                },
                'performance': {
                    'total_chunks_served': self._ml_metrics['total_chunks_served'],
                    'avg_batch_size': round(self._ml_metrics['avg_batch_size'], 2),
                    'avg_stream_duration_seconds': round(avg_stream_duration, 2)
                },
                'efficiency_metrics': {
                    'chunks_per_request': (
                        self._ml_metrics['total_chunks_served'] / 
                        max(1, self._ml_metrics['chunk_requests'])
                    ),
                    'feedback_rate': (
                        self._ml_metrics['feedback_requests'] / 
                        max(1, total_requests) * 100
                    )
                }
            }
    
    def get_conversation_usage_report(self) -> Dict[str, Any]:
        """Get detailed conversation usage report."""
        with self._lock:
            multimedia_rate = 0
            if self._conversation_metrics['total_messages'] > 0:
                multimedia_rate = (
                    self._conversation_metrics['multimedia_messages'] / 
                    self._conversation_metrics['total_messages'] * 100
                )
            
            return {
                'active_conversations': self._conversation_metrics['active_conversations'],
                'websocket_connections': self._conversation_metrics['websocket_connections'],
                'message_statistics': {
                    'total_messages': self._conversation_metrics['total_messages'],
                    'avg_message_length': round(self._conversation_metrics['avg_message_length'], 2),
                    'multimedia_messages': self._conversation_metrics['multimedia_messages'],
                    'multimedia_rate_percent': round(multimedia_rate, 2)
                },
                'engagement_metrics': {
                    'messages_per_conversation': (
                        self._conversation_metrics['total_messages'] / 
                        max(1, self._conversation_metrics['active_conversations'])
                    ),
                    'avg_concurrent_connections': self._conversation_metrics['websocket_connections']
                }
            }