"""
ML API monitoring service for tracking machine learning endpoint usage.

This module provides specialized monitoring for ML training APIs including:
- Training request tracking
- Chunk streaming monitoring
- Feedback loop analysis
- Model performance metrics
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from collections import defaultdict, deque
from dataclasses import dataclass
import threading
import json

from ..config import get_settings
from ..logging_config import get_logger


@dataclass
class MLTrainingSession:
    """ML training session data."""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime]
    request_type: str  # batch, stream, feedback
    total_chunks: int
    total_sequences: int
    avg_chunk_size: float
    reward_signals: List[float]
    client_info: Dict[str, Any]
    performance_metrics: Dict[str, float]


@dataclass
class StreamingSession:
    """Streaming session tracking."""
    session_id: str
    start_time: datetime
    end_time: Optional[datetime]
    chunks_streamed: int
    bytes_transferred: int
    client_disconnects: int
    avg_chunk_rate: float  # chunks per second
    filters_applied: Dict[str, Any]


class MLMonitor:
    """Monitors ML API usage and performance."""
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = get_logger("ml_monitor")
        
        # Thread-safe storage
        self._lock = threading.Lock()
        
        # Training sessions
        self._training_sessions = deque(maxlen=10000)  # Last 10k sessions
        self._active_sessions: Dict[str, MLTrainingSession] = {}
        
        # Streaming sessions
        self._streaming_sessions = deque(maxlen=5000)  # Last 5k streaming sessions
        self._active_streams: Dict[str, StreamingSession] = {}
        
        # Request metrics
        self._request_counts = defaultdict(int)
        self._error_counts = defaultdict(int)
        self._response_times = deque(maxlen=10000)
        
        # Chunk and sequence metrics
        self._chunk_metrics = {
            'total_chunks_served': 0,
            'total_sequences_generated': 0,
            'avg_chunk_complexity': 0.0,
            'chunk_types_distribution': defaultdict(int),
            'source_types_distribution': defaultdict(int)
        }
        
        # Feedback metrics
        self._feedback_metrics = {
            'total_feedback_received': 0,
            'avg_feedback_score': 0.0,
            'feedback_by_interaction_type': defaultdict(int),
            'feedback_trends': deque(maxlen=1440)  # 24 hours at 1-minute intervals
        }
        
        # Client tracking
        self._client_metrics: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            'total_requests': 0,
            'total_chunks_requested': 0,
            'avg_session_duration': 0.0,
            'last_request': None,
            'preferred_formats': defaultdict(int),
            'error_rate': 0.0
        })
        
        # Performance tracking
        self._performance_history = deque(maxlen=1440)  # 24 hours
        
        # Start background monitoring
        self._start_background_monitoring()
    
    def start_training_session(self, session_id: str, request_type: str, 
                             client_info: Dict[str, Any]) -> None:
        """Start tracking a new ML training session."""
        with self._lock:
            session = MLTrainingSession(
                session_id=session_id,
                start_time=datetime.now(),
                end_time=None,
                request_type=request_type,
                total_chunks=0,
                total_sequences=0,
                avg_chunk_size=0.0,
                reward_signals=[],
                client_info=client_info,
                performance_metrics={}
            )
            
            self._active_sessions[session_id] = session
            self._request_counts[request_type] += 1
            
            # Update client metrics
            client_id = client_info.get('client_id', 'unknown')
            self._client_metrics[client_id]['total_requests'] += 1
            self._client_metrics[client_id]['last_request'] = datetime.now()
    
    def end_training_session(self, session_id: str, chunks_served: int = 0, 
                           sequences_generated: int = 0, error: Optional[str] = None) -> None:
        """End a training session and record metrics."""
        with self._lock:
            if session_id not in self._active_sessions:
                self.logger.warning(f"Attempted to end unknown session: {session_id}")
                return
            
            session = self._active_sessions[session_id]
            session.end_time = datetime.now()
            session.total_chunks = chunks_served
            session.total_sequences = sequences_generated
            
            # Calculate session duration
            duration = (session.end_time - session.start_time).total_seconds()
            
            # Update performance metrics
            session.performance_metrics = {
                'duration_seconds': duration,
                'chunks_per_second': chunks_served / max(1, duration),
                'sequences_per_second': sequences_generated / max(1, duration)
            }
            
            # Update global metrics
            self._chunk_metrics['total_chunks_served'] += chunks_served
            self._chunk_metrics['total_sequences_generated'] += sequences_generated
            
            # Update client metrics
            client_id = session.client_info.get('client_id', 'unknown')
            client_metrics = self._client_metrics[client_id]
            client_metrics['total_chunks_requested'] += chunks_served
            
            # Update average session duration
            current_avg = client_metrics['avg_session_duration']
            total_requests = client_metrics['total_requests']
            client_metrics['avg_session_duration'] = (
                (current_avg * (total_requests - 1) + duration) / total_requests
            )
            
            # Handle errors
            if error:
                self._error_counts[session.request_type] += 1
                client_metrics['error_rate'] = (
                    self._error_counts[session.request_type] / 
                    max(1, self._request_counts[session.request_type]) * 100
                )
            
            # Move to completed sessions
            self._training_sessions.append(session)
            del self._active_sessions[session_id]
    
    def start_streaming_session(self, session_id: str, client_info: Dict[str, Any],
                              filters: Dict[str, Any]) -> None:
        """Start tracking a streaming session."""
        with self._lock:
            stream = StreamingSession(
                session_id=session_id,
                start_time=datetime.now(),
                end_time=None,
                chunks_streamed=0,
                bytes_transferred=0,
                client_disconnects=0,
                avg_chunk_rate=0.0,
                filters_applied=filters
            )
            
            self._active_streams[session_id] = stream
            self._request_counts['stream'] += 1
    
    def update_streaming_session(self, session_id: str, chunks_added: int = 0,
                               bytes_added: int = 0, disconnected: bool = False) -> None:
        """Update streaming session metrics."""
        with self._lock:
            if session_id not in self._active_streams:
                return
            
            stream = self._active_streams[session_id]
            stream.chunks_streamed += chunks_added
            stream.bytes_transferred += bytes_added
            
            if disconnected:
                stream.client_disconnects += 1
            
            # Calculate streaming rate
            duration = (datetime.now() - stream.start_time).total_seconds()
            if duration > 0:
                stream.avg_chunk_rate = stream.chunks_streamed / duration
    
    def end_streaming_session(self, session_id: str) -> None:
        """End a streaming session."""
        with self._lock:
            if session_id not in self._active_streams:
                return
            
            stream = self._active_streams[session_id]
            stream.end_time = datetime.now()
            
            # Move to completed streams
            self._streaming_sessions.append(stream)
            del self._active_streams[session_id]
    
    def record_feedback(self, chunk_id: str, interaction_type: str, 
                       feedback_score: float, client_id: str) -> None:
        """Record user feedback for ML training."""
        with self._lock:
            self._feedback_metrics['total_feedback_received'] += 1
            self._feedback_metrics['feedback_by_interaction_type'][interaction_type] += 1
            
            # Update average feedback score
            total_feedback = self._feedback_metrics['total_feedback_received']
            current_avg = self._feedback_metrics['avg_feedback_score']
            self._feedback_metrics['avg_feedback_score'] = (
                (current_avg * (total_feedback - 1) + feedback_score) / total_feedback
            )
            
            # Record feedback trend
            self._feedback_metrics['feedback_trends'].append({
                'timestamp': datetime.now(),
                'score': feedback_score,
                'interaction_type': interaction_type,
                'client_id': client_id
            })
    
    def record_chunk_metadata(self, chunk_data: Dict[str, Any]) -> None:
        """Record metadata about served chunks."""
        with self._lock:
            content_type = chunk_data.get('content_type', 'unknown')
            source_type = chunk_data.get('source_type', 'unknown')
            complexity = chunk_data.get('complexity_score', 0.0)
            
            self._chunk_metrics['chunk_types_distribution'][content_type] += 1
            self._chunk_metrics['source_types_distribution'][source_type] += 1
            
            # Update average complexity
            total_chunks = self._chunk_metrics['total_chunks_served']
            if total_chunks > 0:
                current_avg = self._chunk_metrics['avg_chunk_complexity']
                self._chunk_metrics['avg_chunk_complexity'] = (
                    (current_avg * (total_chunks - 1) + complexity) / total_chunks
                )
    
    def record_response_time(self, endpoint: str, response_time: float) -> None:
        """Record ML API response time."""
        with self._lock:
            self._response_times.append({
                'timestamp': datetime.now(),
                'endpoint': endpoint,
                'response_time': response_time
            })
    
    def get_current_ml_metrics(self) -> Dict[str, Any]:
        """Get current ML API metrics."""
        with self._lock:
            now = datetime.now()
            
            # Calculate recent metrics (last 5 minutes)
            recent_responses = [
                resp for resp in self._response_times
                if (now - resp['timestamp']).total_seconds() <= 300
            ]
            
            # Response time statistics
            if recent_responses:
                response_times = [resp['response_time'] for resp in recent_responses]
                avg_response_time = sum(response_times) / len(response_times)
                p95_response_time = sorted(response_times)[int(len(response_times) * 0.95)]
            else:
                avg_response_time = p95_response_time = 0
            
            # Active session counts
            active_training = len(self._active_sessions)
            active_streaming = len(self._active_streams)
            
            # Request rate (last 5 minutes)
            total_requests = sum(self._request_counts.values())
            recent_request_rate = len(recent_responses) / 5  # per minute
            
            # Error rate
            total_errors = sum(self._error_counts.values())
            error_rate = (total_errors / max(1, total_requests)) * 100
            
            return {
                'timestamp': now.isoformat(),
                'active_sessions': {
                    'training_sessions': active_training,
                    'streaming_sessions': active_streaming,
                    'total_active': active_training + active_streaming
                },
                'request_metrics': {
                    'total_requests': total_requests,
                    'requests_per_minute': round(recent_request_rate, 2),
                    'avg_response_time_ms': round(avg_response_time * 1000, 2),
                    'p95_response_time_ms': round(p95_response_time * 1000, 2),
                    'error_rate_percent': round(error_rate, 2)
                },
                'chunk_metrics': dict(self._chunk_metrics),
                'feedback_metrics': dict(self._feedback_metrics),
                'request_breakdown': dict(self._request_counts),
                'error_breakdown': dict(self._error_counts)
            }
    
    def get_client_analytics(self, client_id: Optional[str] = None) -> Dict[str, Any]:
        """Get client usage analytics."""
        with self._lock:
            if client_id:
                if client_id not in self._client_metrics:
                    return {"error": f"Client {client_id} not found"}
                
                return {
                    'client_id': client_id,
                    'metrics': dict(self._client_metrics[client_id])
                }
            else:
                # Return all client metrics
                return {
                    'total_clients': len(self._client_metrics),
                    'clients': {
                        client_id: dict(metrics)
                        for client_id, metrics in self._client_metrics.items()
                    }
                }
    
    def get_streaming_analytics(self) -> Dict[str, Any]:
        """Get streaming session analytics."""
        with self._lock:
            completed_streams = list(self._streaming_sessions)
            active_streams = list(self._active_streams.values())
            
            if not completed_streams and not active_streams:
                return {"message": "No streaming data available"}
            
            # Calculate streaming statistics
            total_streams = len(completed_streams) + len(active_streams)
            total_chunks_streamed = sum(s.chunks_streamed for s in completed_streams + active_streams)
            total_bytes_transferred = sum(s.bytes_transferred for s in completed_streams + active_streams)
            
            # Average session duration (completed sessions only)
            if completed_streams:
                durations = [
                    (s.end_time - s.start_time).total_seconds()
                    for s in completed_streams if s.end_time
                ]
                avg_duration = sum(durations) / len(durations) if durations else 0
            else:
                avg_duration = 0
            
            # Average streaming rate
            if completed_streams:
                rates = [s.avg_chunk_rate for s in completed_streams if s.avg_chunk_rate > 0]
                avg_rate = sum(rates) / len(rates) if rates else 0
            else:
                avg_rate = 0
            
            return {
                'total_streaming_sessions': total_streams,
                'active_streaming_sessions': len(active_streams),
                'completed_streaming_sessions': len(completed_streams),
                'total_chunks_streamed': total_chunks_streamed,
                'total_bytes_transferred': total_bytes_transferred,
                'avg_session_duration_seconds': round(avg_duration, 2),
                'avg_streaming_rate_chunks_per_second': round(avg_rate, 2),
                'active_streams': [
                    {
                        'session_id': s.session_id,
                        'start_time': s.start_time.isoformat(),
                        'chunks_streamed': s.chunks_streamed,
                        'current_rate': s.avg_chunk_rate,
                        'filters': s.filters_applied
                    }
                    for s in active_streams
                ]
            }
    
    def get_training_analytics(self) -> Dict[str, Any]:
        """Get training session analytics."""
        with self._lock:
            completed_sessions = list(self._training_sessions)
            active_sessions = list(self._active_sessions.values())
            
            if not completed_sessions and not active_sessions:
                return {"message": "No training data available"}
            
            # Session type breakdown
            session_types = defaultdict(int)
            for session in completed_sessions + active_sessions:
                session_types[session.request_type] += 1
            
            # Performance metrics (completed sessions only)
            if completed_sessions:
                durations = [
                    s.performance_metrics.get('duration_seconds', 0)
                    for s in completed_sessions
                ]
                chunk_rates = [
                    s.performance_metrics.get('chunks_per_second', 0)
                    for s in completed_sessions
                ]
                
                avg_duration = sum(durations) / len(durations) if durations else 0
                avg_chunk_rate = sum(chunk_rates) / len(chunk_rates) if chunk_rates else 0
            else:
                avg_duration = avg_chunk_rate = 0
            
            return {
                'total_training_sessions': len(completed_sessions) + len(active_sessions),
                'active_training_sessions': len(active_sessions),
                'completed_training_sessions': len(completed_sessions),
                'session_type_breakdown': dict(session_types),
                'performance_metrics': {
                    'avg_session_duration_seconds': round(avg_duration, 2),
                    'avg_chunks_per_second': round(avg_chunk_rate, 2)
                },
                'active_sessions': [
                    {
                        'session_id': s.session_id,
                        'request_type': s.request_type,
                        'start_time': s.start_time.isoformat(),
                        'chunks_served': s.total_chunks,
                        'client_info': s.client_info
                    }
                    for s in active_sessions
                ]
            }
    
    def get_feedback_analytics(self) -> Dict[str, Any]:
        """Get feedback analytics."""
        with self._lock:
            feedback_metrics = dict(self._feedback_metrics)
            
            # Recent feedback trends (last 24 hours)
            now = datetime.now()
            recent_feedback = [
                fb for fb in self._feedback_metrics['feedback_trends']
                if (now - fb['timestamp']).total_seconds() <= 86400
            ]
            
            # Calculate hourly feedback averages
            hourly_feedback = defaultdict(list)
            for fb in recent_feedback:
                hour_key = fb['timestamp'].strftime('%Y-%m-%d %H:00')
                hourly_feedback[hour_key].append(fb['score'])
            
            hourly_averages = [
                {
                    'hour': hour,
                    'avg_score': sum(scores) / len(scores),
                    'feedback_count': len(scores)
                }
                for hour, scores in sorted(hourly_feedback.items())
            ]
            
            # Interaction type analysis
            interaction_breakdown = dict(feedback_metrics['feedback_by_interaction_type'])
            
            return {
                'total_feedback_received': feedback_metrics['total_feedback_received'],
                'avg_feedback_score': round(feedback_metrics['avg_feedback_score'], 3),
                'feedback_by_interaction_type': interaction_breakdown,
                'recent_feedback_24h': len(recent_feedback),
                'hourly_feedback_trends': hourly_averages,
                'feedback_distribution': self._calculate_feedback_distribution(recent_feedback)
            }
    
    def _calculate_feedback_distribution(self, feedback_data: List[Dict]) -> Dict[str, int]:
        """Calculate feedback score distribution."""
        distribution = {
            'very_negative': 0,  # -1.0 to -0.6
            'negative': 0,       # -0.6 to -0.2
            'neutral': 0,        # -0.2 to 0.2
            'positive': 0,       # 0.2 to 0.6
            'very_positive': 0   # 0.6 to 1.0
        }
        
        for fb in feedback_data:
            score = fb['score']
            if score <= -0.6:
                distribution['very_negative'] += 1
            elif score <= -0.2:
                distribution['negative'] += 1
            elif score <= 0.2:
                distribution['neutral'] += 1
            elif score <= 0.6:
                distribution['positive'] += 1
            else:
                distribution['very_positive'] += 1
        
        return distribution
    
    def generate_ml_usage_report(self) -> Dict[str, Any]:
        """Generate comprehensive ML usage report."""
        current_metrics = self.get_current_ml_metrics()
        client_analytics = self.get_client_analytics()
        streaming_analytics = self.get_streaming_analytics()
        training_analytics = self.get_training_analytics()
        feedback_analytics = self.get_feedback_analytics()
        
        return {
            'report_timestamp': datetime.now().isoformat(),
            'summary': {
                'total_ml_requests': current_metrics['request_metrics']['total_requests'],
                'active_sessions': current_metrics['active_sessions']['total_active'],
                'total_chunks_served': current_metrics['chunk_metrics']['total_chunks_served'],
                'avg_feedback_score': feedback_analytics['avg_feedback_score'],
                'error_rate_percent': current_metrics['request_metrics']['error_rate_percent']
            },
            'current_metrics': current_metrics,
            'client_analytics': client_analytics,
            'streaming_analytics': streaming_analytics,
            'training_analytics': training_analytics,
            'feedback_analytics': feedback_analytics,
            'recommendations': self._generate_ml_recommendations(current_metrics)
        }
    
    def _generate_ml_recommendations(self, metrics: Dict[str, Any]) -> List[str]:
        """Generate ML API optimization recommendations."""
        recommendations = []
        
        # Response time recommendations
        avg_response_time = metrics['request_metrics']['avg_response_time_ms']
        if avg_response_time > 5000:  # 5 seconds
            recommendations.append("ML API response times are high. Consider optimizing chunk generation and caching frequent requests")
        
        # Error rate recommendations
        error_rate = metrics['request_metrics']['error_rate_percent']
        if error_rate > 10:
            recommendations.append("High ML API error rate detected. Review error logs and implement better error handling")
        
        # Feedback recommendations
        if 'feedback_metrics' in metrics:
            avg_feedback = metrics['feedback_metrics']['avg_feedback_score']
            if avg_feedback < 0.2:
                recommendations.append("Low average feedback score indicates poor chunk quality. Review chunk generation algorithms")
        
        # Usage pattern recommendations
        active_sessions = metrics['active_sessions']['total_active']
        if active_sessions > 100:
            recommendations.append("High number of active ML sessions. Consider implementing session pooling and resource limits")
        
        return recommendations
    
    def _start_background_monitoring(self) -> None:
        """Start background monitoring for ML metrics."""
        def collect_ml_performance():
            while True:
                try:
                    current_metrics = self.get_current_ml_metrics()
                    
                    # Store performance snapshot
                    performance_snapshot = {
                        'timestamp': datetime.now(),
                        'active_sessions': current_metrics['active_sessions']['total_active'],
                        'requests_per_minute': current_metrics['request_metrics']['requests_per_minute'],
                        'avg_response_time_ms': current_metrics['request_metrics']['avg_response_time_ms'],
                        'error_rate_percent': current_metrics['request_metrics']['error_rate_percent']
                    }
                    
                    with self._lock:
                        self._performance_history.append(performance_snapshot)
                    
                    time.sleep(60)  # Collect every minute
                    
                except Exception as e:
                    self.logger.error(f"Error in ML performance monitoring: {e}")
                    time.sleep(60)
        
        # Start background thread
        thread = threading.Thread(target=collect_ml_performance, daemon=True)
        thread.start()
        self.logger.info("ML monitoring background collection started")