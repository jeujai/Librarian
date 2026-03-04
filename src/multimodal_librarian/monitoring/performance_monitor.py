"""
Performance monitoring service for tracking system performance over time.

This module provides performance monitoring capabilities including:
- Response time tracking
- Throughput monitoring
- Resource utilization alerts
- Performance trend analysis
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from collections import deque
import threading

from ..config import get_settings
from ..logging_config import get_logger


@dataclass
class PerformanceAlert:
    """Performance alert data structure."""
    alert_type: str
    severity: str  # low, medium, high, critical
    message: str
    metric_name: str
    current_value: float
    threshold: float
    timestamp: datetime
    resolved: bool = False


@dataclass
class PerformanceThreshold:
    """Performance threshold configuration."""
    metric_name: str
    warning_threshold: float
    critical_threshold: float
    comparison: str  # 'greater_than', 'less_than'
    duration_seconds: int = 60  # How long threshold must be exceeded


class PerformanceMonitor:
    """Monitors system performance and generates alerts."""
    
    def __init__(self, metrics_collector=None):
        self.settings = get_settings()
        self.logger = get_logger("performance_monitor")
        self.metrics_collector = metrics_collector
        
        # Performance data storage
        self._performance_data = deque(maxlen=10080)  # 7 days at 1-minute intervals
        self._alerts = deque(maxlen=1000)  # Last 1000 alerts
        self._active_alerts = {}  # Currently active alerts
        
        # Performance thresholds
        self._thresholds = self._initialize_thresholds()
        
        # Alert callbacks
        self._alert_callbacks: List[Callable[[PerformanceAlert], None]] = []
        
        # Monitoring state
        self._monitoring_active = False
        self._lock = threading.Lock()
        
        # Start monitoring
        self._start_monitoring()
    
    def _initialize_thresholds(self) -> List[PerformanceThreshold]:
        """Initialize default performance thresholds."""
        return [
            # Response time thresholds
            PerformanceThreshold(
                metric_name="avg_response_time_ms",
                warning_threshold=1000,  # 1 second
                critical_threshold=5000,  # 5 seconds
                comparison="greater_than",
                duration_seconds=60
            ),
            PerformanceThreshold(
                metric_name="p95_response_time_ms",
                warning_threshold=2000,  # 2 seconds
                critical_threshold=10000,  # 10 seconds
                comparison="greater_than",
                duration_seconds=60
            ),
            
            # Error rate thresholds
            PerformanceThreshold(
                metric_name="error_rate_percent",
                warning_threshold=5.0,  # 5%
                critical_threshold=15.0,  # 15%
                comparison="greater_than",
                duration_seconds=300  # 5 minutes
            ),
            
            # System resource thresholds
            PerformanceThreshold(
                metric_name="cpu_percent",
                warning_threshold=80.0,
                critical_threshold=95.0,
                comparison="greater_than",
                duration_seconds=300
            ),
            PerformanceThreshold(
                metric_name="memory_percent",
                warning_threshold=85.0,
                critical_threshold=95.0,
                comparison="greater_than",
                duration_seconds=300
            ),
            PerformanceThreshold(
                metric_name="disk_percent",
                warning_threshold=85.0,
                critical_threshold=95.0,
                comparison="greater_than",
                duration_seconds=300
            ),
            
            # Request rate thresholds
            PerformanceThreshold(
                metric_name="requests_per_minute",
                warning_threshold=1000,
                critical_threshold=2000,
                comparison="greater_than",
                duration_seconds=60
            )
        ]
    
    def add_alert_callback(self, callback: Callable[[PerformanceAlert], None]) -> None:
        """Add a callback function to be called when alerts are generated."""
        self._alert_callbacks.append(callback)
    
    def record_performance_data(self, data: Dict[str, Any]) -> None:
        """Record performance data point."""
        with self._lock:
            timestamp = datetime.now()
            performance_point = {
                'timestamp': timestamp,
                **data
            }
            self._performance_data.append(performance_point)
            
            # Check thresholds
            self._check_thresholds(performance_point)
    
    def _check_thresholds(self, data_point: Dict[str, Any]) -> None:
        """Check if any performance thresholds are exceeded."""
        for threshold in self._thresholds:
            if threshold.metric_name not in data_point:
                continue
            
            current_value = data_point[threshold.metric_name]
            
            # Check if threshold is exceeded
            threshold_exceeded = False
            if threshold.comparison == "greater_than":
                threshold_exceeded = current_value > threshold.critical_threshold
                warning_exceeded = current_value > threshold.warning_threshold
            elif threshold.comparison == "less_than":
                threshold_exceeded = current_value < threshold.critical_threshold
                warning_exceeded = current_value < threshold.warning_threshold
            
            # Generate alerts
            if threshold_exceeded:
                self._generate_alert(
                    threshold, current_value, "critical", data_point['timestamp']
                )
            elif warning_exceeded:
                self._generate_alert(
                    threshold, current_value, "warning", data_point['timestamp']
                )
            else:
                # Check if we should resolve an existing alert
                self._resolve_alert(threshold.metric_name)
    
    def _generate_alert(self, threshold: PerformanceThreshold, current_value: float, 
                       severity: str, timestamp: datetime) -> None:
        """Generate a performance alert."""
        alert_key = f"{threshold.metric_name}_{severity}"
        
        # Check if alert is already active
        if alert_key in self._active_alerts:
            # Update existing alert
            self._active_alerts[alert_key].current_value = current_value
            self._active_alerts[alert_key].timestamp = timestamp
            return
        
        # Create new alert
        alert = PerformanceAlert(
            alert_type="performance_threshold",
            severity=severity,
            message=f"{threshold.metric_name} is {current_value:.2f}, exceeding {severity} threshold of {threshold.warning_threshold if severity == 'warning' else threshold.critical_threshold:.2f}",
            metric_name=threshold.metric_name,
            current_value=current_value,
            threshold=threshold.warning_threshold if severity == "warning" else threshold.critical_threshold,
            timestamp=timestamp
        )
        
        # Store alert
        self._active_alerts[alert_key] = alert
        self._alerts.append(alert)
        
        # Notify callbacks
        for callback in self._alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                self.logger.error(f"Error in alert callback: {e}")
        
        self.logger.warning(f"Performance alert: {alert.message}")
    
    def _resolve_alert(self, metric_name: str) -> None:
        """Resolve alerts for a specific metric."""
        resolved_alerts = []
        for alert_key in list(self._active_alerts.keys()):
            if self._active_alerts[alert_key].metric_name == metric_name:
                alert = self._active_alerts[alert_key]
                alert.resolved = True
                resolved_alerts.append(alert)
                del self._active_alerts[alert_key]
        
        for alert in resolved_alerts:
            self.logger.info(f"Performance alert resolved: {alert.metric_name}")
    
    def get_current_performance(self) -> Dict[str, Any]:
        """Get current performance metrics."""
        with self._lock:
            if not self._performance_data:
                return {"error": "No performance data available"}
            
            latest_data = self._performance_data[-1]
            
            # Calculate trends (last hour vs previous hour)
            now = datetime.now()
            one_hour_ago = now - timedelta(hours=1)
            two_hours_ago = now - timedelta(hours=2)
            
            recent_data = [
                point for point in self._performance_data
                if point['timestamp'] >= one_hour_ago
            ]
            
            previous_data = [
                point for point in self._performance_data
                if two_hours_ago <= point['timestamp'] < one_hour_ago
            ]
            
            trends = self._calculate_trends(recent_data, previous_data)
            
            return {
                'current_metrics': latest_data,
                'trends': trends,
                'active_alerts': len(self._active_alerts),
                'total_alerts_24h': len([
                    alert for alert in self._alerts
                    if (now - alert.timestamp).total_seconds() <= 86400
                ]),
                'monitoring_status': 'active' if self._monitoring_active else 'inactive'
            }
    
    def _calculate_trends(self, recent_data: List[Dict], previous_data: List[Dict]) -> Dict[str, Any]:
        """Calculate performance trends."""
        if not recent_data or not previous_data:
            return {}
        
        trends = {}
        
        # Metrics to track trends for
        trend_metrics = [
            'avg_response_time_ms', 'error_rate_percent', 'requests_per_minute',
            'cpu_percent', 'memory_percent', 'disk_percent'
        ]
        
        for metric in trend_metrics:
            recent_values = [point.get(metric, 0) for point in recent_data if metric in point]
            previous_values = [point.get(metric, 0) for point in previous_data if metric in point]
            
            if recent_values and previous_values:
                recent_avg = sum(recent_values) / len(recent_values)
                previous_avg = sum(previous_values) / len(previous_values)
                
                if previous_avg > 0:
                    change_percent = ((recent_avg - previous_avg) / previous_avg) * 100
                    trends[metric] = {
                        'current_avg': round(recent_avg, 2),
                        'previous_avg': round(previous_avg, 2),
                        'change_percent': round(change_percent, 2),
                        'trend': 'improving' if change_percent < -5 else 'degrading' if change_percent > 5 else 'stable'
                    }
        
        return trends
    
    def get_performance_history(self, hours: int = 24) -> Dict[str, Any]:
        """Get performance history for the specified time period."""
        with self._lock:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            historical_data = [
                point for point in self._performance_data
                if point['timestamp'] >= cutoff_time
            ]
            
            if not historical_data:
                return {"error": "No historical data available for the specified period"}
            
            # Group data by hour
            hourly_data = {}
            for point in historical_data:
                hour_key = point['timestamp'].strftime('%Y-%m-%d %H:00')
                if hour_key not in hourly_data:
                    hourly_data[hour_key] = []
                hourly_data[hour_key].append(point)
            
            # Calculate hourly averages
            hourly_averages = []
            for hour, points in sorted(hourly_data.items()):
                if not points:
                    continue
                
                avg_point = {'hour': hour}
                
                # Calculate averages for numeric metrics
                numeric_metrics = [
                    'avg_response_time_ms', 'error_rate_percent', 'requests_per_minute',
                    'cpu_percent', 'memory_percent', 'disk_percent'
                ]
                
                for metric in numeric_metrics:
                    values = [point.get(metric, 0) for point in points if metric in point]
                    if values:
                        avg_point[metric] = round(sum(values) / len(values), 2)
                
                hourly_averages.append(avg_point)
            
            return {
                'period_hours': hours,
                'data_points': len(historical_data),
                'hourly_averages': hourly_averages,
                'summary': self._calculate_period_summary(historical_data)
            }
    
    def _calculate_period_summary(self, data_points: List[Dict]) -> Dict[str, Any]:
        """Calculate summary statistics for a period."""
        if not data_points:
            return {}
        
        summary = {}
        
        # Metrics to summarize
        metrics = [
            'avg_response_time_ms', 'error_rate_percent', 'requests_per_minute',
            'cpu_percent', 'memory_percent', 'disk_percent'
        ]
        
        for metric in metrics:
            values = [point.get(metric, 0) for point in data_points if metric in point]
            if values:
                summary[metric] = {
                    'min': round(min(values), 2),
                    'max': round(max(values), 2),
                    'avg': round(sum(values) / len(values), 2),
                    'p95': round(sorted(values)[int(len(values) * 0.95)], 2) if len(values) > 1 else round(values[0], 2)
                }
        
        return summary
    
    def get_alerts(self, hours: int = 24, severity: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get alerts for the specified time period."""
        with self._lock:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            
            filtered_alerts = [
                alert for alert in self._alerts
                if alert.timestamp >= cutoff_time
            ]
            
            if severity:
                filtered_alerts = [
                    alert for alert in filtered_alerts
                    if alert.severity == severity
                ]
            
            return [
                {
                    'alert_type': alert.alert_type,
                    'severity': alert.severity,
                    'message': alert.message,
                    'metric_name': alert.metric_name,
                    'current_value': alert.current_value,
                    'threshold': alert.threshold,
                    'timestamp': alert.timestamp.isoformat(),
                    'resolved': alert.resolved
                }
                for alert in sorted(filtered_alerts, key=lambda x: x.timestamp, reverse=True)
            ]
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get currently active alerts."""
        with self._lock:
            return [
                {
                    'alert_type': alert.alert_type,
                    'severity': alert.severity,
                    'message': alert.message,
                    'metric_name': alert.metric_name,
                    'current_value': alert.current_value,
                    'threshold': alert.threshold,
                    'timestamp': alert.timestamp.isoformat(),
                    'duration_minutes': (datetime.now() - alert.timestamp).total_seconds() / 60
                }
                for alert in self._active_alerts.values()
            ]
    
    def update_threshold(self, metric_name: str, warning_threshold: Optional[float] = None,
                        critical_threshold: Optional[float] = None) -> bool:
        """Update performance threshold for a metric."""
        for threshold in self._thresholds:
            if threshold.metric_name == metric_name:
                if warning_threshold is not None:
                    threshold.warning_threshold = warning_threshold
                if critical_threshold is not None:
                    threshold.critical_threshold = critical_threshold
                
                self.logger.info(f"Updated thresholds for {metric_name}: warning={threshold.warning_threshold}, critical={threshold.critical_threshold}")
                return True
        
        return False
    
    def _start_monitoring(self) -> None:
        """Start the performance monitoring loop."""
        async def monitoring_loop():
            self._monitoring_active = True
            self.logger.info("Performance monitoring started")
            
            while self._monitoring_active:
                try:
                    # Collect current metrics if metrics collector is available
                    if self.metrics_collector:
                        current_metrics = self.metrics_collector.get_current_metrics()
                        
                        # Extract relevant performance data
                        performance_data = {}
                        
                        if 'request_metrics' in current_metrics:
                            req_metrics = current_metrics['request_metrics']
                            performance_data.update({
                                'avg_response_time_ms': req_metrics.get('avg_response_time_ms', 0),
                                'p95_response_time_ms': req_metrics.get('p95_response_time_ms', 0),
                                'error_rate_percent': req_metrics.get('error_rate_percent', 0),
                                'requests_per_minute': req_metrics.get('requests_per_minute', 0)
                            })
                        
                        # Add system metrics
                        try:
                            import psutil
                            performance_data.update({
                                'cpu_percent': psutil.cpu_percent(interval=1),
                                'memory_percent': psutil.virtual_memory().percent,
                                'disk_percent': psutil.disk_usage('/').percent
                            })
                        except Exception as e:
                            self.logger.warning(f"Could not collect system metrics: {e}")
                        
                        # Record the performance data
                        if performance_data:
                            self.record_performance_data(performance_data)
                    
                    # Sleep for 1 minute
                    await asyncio.sleep(60)
                    
                except Exception as e:
                    self.logger.error(f"Error in performance monitoring loop: {e}")
                    await asyncio.sleep(60)
        
        # Start monitoring in background
        asyncio.create_task(monitoring_loop())
    
    def stop_monitoring(self) -> None:
        """Stop performance monitoring."""
        self._monitoring_active = False
        self.logger.info("Performance monitoring stopped")
    
    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate a comprehensive performance report."""
        current_perf = self.get_current_performance()
        history_24h = self.get_performance_history(24)
        active_alerts = self.get_active_alerts()
        recent_alerts = self.get_alerts(24)
        
        # Calculate uptime and availability
        total_requests = 0
        error_requests = 0
        
        if self.metrics_collector:
            metrics = self.metrics_collector.get_current_metrics()
            if 'request_metrics' in metrics:
                total_requests = metrics['request_metrics'].get('total_requests', 0)
                error_rate = metrics['request_metrics'].get('error_rate_percent', 0)
                error_requests = int(total_requests * error_rate / 100)
        
        availability = ((total_requests - error_requests) / max(1, total_requests)) * 100
        
        return {
            'report_timestamp': datetime.now().isoformat(),
            'summary': {
                'overall_status': 'healthy' if not active_alerts else 'degraded',
                'availability_percent': round(availability, 2),
                'total_requests_24h': total_requests,
                'active_alerts': len(active_alerts),
                'alerts_24h': len(recent_alerts)
            },
            'current_performance': current_perf,
            'performance_history': history_24h,
            'active_alerts': active_alerts,
            'recent_alerts': recent_alerts[:10],  # Last 10 alerts
            'recommendations': self._generate_recommendations(current_perf, active_alerts)
        }
    
    def _generate_recommendations(self, current_perf: Dict[str, Any], 
                                active_alerts: List[Dict[str, Any]]) -> List[str]:
        """Generate performance improvement recommendations."""
        recommendations = []
        
        if not current_perf.get('current_metrics'):
            return recommendations
        
        current_metrics = current_perf['current_metrics']
        
        # Response time recommendations
        avg_response_time = current_metrics.get('avg_response_time_ms', 0)
        if avg_response_time > 2000:
            recommendations.append("Consider optimizing database queries and adding caching to improve response times")
        
        # Error rate recommendations
        error_rate = current_metrics.get('error_rate_percent', 0)
        if error_rate > 5:
            recommendations.append("High error rate detected. Review application logs and implement better error handling")
        
        # Resource usage recommendations
        cpu_percent = current_metrics.get('cpu_percent', 0)
        memory_percent = current_metrics.get('memory_percent', 0)
        
        if cpu_percent > 80:
            recommendations.append("High CPU usage detected. Consider scaling horizontally or optimizing CPU-intensive operations")
        
        if memory_percent > 85:
            recommendations.append("High memory usage detected. Review memory leaks and consider increasing available memory")
        
        # Alert-based recommendations
        for alert in active_alerts:
            if alert['metric_name'] == 'requests_per_minute' and alert['severity'] == 'critical':
                recommendations.append("High request volume detected. Consider implementing rate limiting and load balancing")
        
        return recommendations