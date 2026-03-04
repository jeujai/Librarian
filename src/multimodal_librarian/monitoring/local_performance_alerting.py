"""
Local Development Performance Alerting

This module provides performance alerting specifically designed for local development
environments. It monitors performance metrics and sends alerts when thresholds are
exceeded, helping developers identify and resolve performance issues quickly.

Features:
- Database performance alerting (query times, connection issues)
- Resource usage alerting (memory, CPU, disk)
- Container performance monitoring
- Development workflow performance alerts
- Integration with existing alerting infrastructure
- Configurable thresholds for different alert types
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
import statistics
import logging

from .local_alerting_system import (
    LocalAlertingSystem,
    LocalAlert,
    LocalAlertType,
    get_local_alerting_system,
    send_local_alert
)
from .alerting_service import AlertSeverity
from .performance_tracker import PerformanceTracker, PerformanceAlert
from .local_performance_metrics import LocalPerformanceMetricsCollector, LocalServiceMetrics
from .query_performance_monitor import QueryPerformanceMonitor
from ..config.local_config import LocalDatabaseConfig
from ..logging_config import get_logger

logger = get_logger("local_performance_alerting")


class PerformanceAlertType(Enum):
    """Performance-specific alert types for local development."""
    SLOW_DATABASE_QUERY = "slow_database_query"
    HIGH_QUERY_ERROR_RATE = "high_query_error_rate"
    DATABASE_CONNECTION_POOL_EXHAUSTED = "database_connection_pool_exhausted"
    CONTAINER_MEMORY_LIMIT_EXCEEDED = "container_memory_limit_exceeded"
    CONTAINER_CPU_THROTTLING = "container_cpu_throttling"
    DISK_IO_BOTTLENECK = "disk_io_bottleneck"
    NETWORK_LATENCY_HIGH = "network_latency_high"
    SERVICE_RESPONSE_TIME_DEGRADED = "service_response_time_degraded"
    DEVELOPMENT_WORKFLOW_SLOW = "development_workflow_slow"
    CACHE_HIT_RATE_LOW = "cache_hit_rate_low"
    STARTUP_TIME_EXCESSIVE = "startup_time_excessive"


@dataclass
class PerformanceThreshold:
    """Performance threshold configuration."""
    metric_name: str
    threshold_value: float
    comparison: str  # "greater_than", "less_than", "equals"
    window_minutes: int = 5
    min_samples: int = 3
    severity: AlertSeverity = AlertSeverity.MEDIUM
    cooldown_minutes: int = 10
    auto_resolve: bool = True


@dataclass
class PerformanceAlertRule:
    """Performance alert rule configuration."""
    alert_type: PerformanceAlertType
    service_pattern: str  # regex pattern for service names
    thresholds: List[PerformanceThreshold]
    enabled: bool = True
    description: str = ""
    remediation_steps: List[str] = field(default_factory=list)


class LocalPerformanceAlerting:
    """
    Performance alerting system for local development environments.
    
    This class monitors performance metrics from various sources and generates
    alerts when performance thresholds are exceeded. It integrates with the
    existing alerting infrastructure while providing local development specific
    performance monitoring.
    """
    
    def __init__(self, config: Optional[LocalDatabaseConfig] = None):
        self.config = config or LocalDatabaseConfig()
        self.logger = get_logger("local_performance_alerting")
        
        # Alerting infrastructure
        self._alerting_system = get_local_alerting_system(config)
        self._performance_tracker: Optional[PerformanceTracker] = None
        self._metrics_collector: Optional[LocalPerformanceMetricsCollector] = None
        self._query_monitor: Optional[QueryPerformanceMonitor] = None
        
        # Alert state
        self._alerting_active = False
        self._alerting_task: Optional[asyncio.Task] = None
        self._active_performance_alerts: Dict[str, datetime] = {}
        
        # Performance data storage
        self._performance_history: Dict[str, List[float]] = {}
        self._service_metrics_history: Dict[str, List[LocalServiceMetrics]] = {}
        self._last_alert_times: Dict[str, datetime] = {}
        
        # Alert rules configuration
        self._alert_rules = self._initialize_alert_rules()
        
        # Callbacks for performance events
        self._alert_callbacks: List[Callable[[PerformanceAlert], None]] = []
        
        self.logger.info("Local performance alerting system initialized")
    
    def _initialize_alert_rules(self) -> Dict[PerformanceAlertType, PerformanceAlertRule]:
        """Initialize default performance alert rules."""
        rules = {}
        
        # Database query performance
        rules[PerformanceAlertType.SLOW_DATABASE_QUERY] = PerformanceAlertRule(
            alert_type=PerformanceAlertType.SLOW_DATABASE_QUERY,
            service_pattern=r"(postgres|neo4j|milvus|redis)",
            thresholds=[
                PerformanceThreshold(
                    metric_name="query_response_time_ms",
                    threshold_value=5000.0,  # 5 seconds
                    comparison="greater_than",
                    window_minutes=5,
                    min_samples=3,
                    severity=AlertSeverity.MEDIUM,
                    cooldown_minutes=10
                )
            ],
            description="Database queries are taking longer than expected",
            remediation_steps=[
                "Check database connection pool settings",
                "Review query execution plans",
                "Consider adding database indexes",
                "Monitor database resource usage"
            ]
        )
        
        # High query error rate
        rules[PerformanceAlertType.HIGH_QUERY_ERROR_RATE] = PerformanceAlertRule(
            alert_type=PerformanceAlertType.HIGH_QUERY_ERROR_RATE,
            service_pattern=r"(postgres|neo4j|milvus|redis)",
            thresholds=[
                PerformanceThreshold(
                    metric_name="error_rate_percent",
                    threshold_value=10.0,  # 10% error rate
                    comparison="greater_than",
                    window_minutes=5,
                    min_samples=5,
                    severity=AlertSeverity.HIGH,
                    cooldown_minutes=15
                )
            ],
            description="High rate of database query errors detected",
            remediation_steps=[
                "Check database connectivity",
                "Review recent query changes",
                "Check database logs for errors",
                "Verify database schema integrity"
            ]
        )
        
        # Container memory limits
        rules[PerformanceAlertType.CONTAINER_MEMORY_LIMIT_EXCEEDED] = PerformanceAlertRule(
            alert_type=PerformanceAlertType.CONTAINER_MEMORY_LIMIT_EXCEEDED,
            service_pattern=r".*",  # All services
            thresholds=[
                PerformanceThreshold(
                    metric_name="memory_usage_percent",
                    threshold_value=90.0,  # 90% of container limit
                    comparison="greater_than",
                    window_minutes=3,
                    min_samples=2,
                    severity=AlertSeverity.HIGH,
                    cooldown_minutes=20
                )
            ],
            description="Container is approaching memory limits",
            remediation_steps=[
                "Increase container memory limits",
                "Check for memory leaks in application",
                "Review memory usage patterns",
                "Consider optimizing data structures"
            ]
        )
        
        # CPU throttling
        rules[PerformanceAlertType.CONTAINER_CPU_THROTTLING] = PerformanceAlertRule(
            alert_type=PerformanceAlertType.CONTAINER_CPU_THROTTLING,
            service_pattern=r".*",
            thresholds=[
                PerformanceThreshold(
                    metric_name="cpu_throttling_percent",
                    threshold_value=50.0,  # 50% of time throttled
                    comparison="greater_than",
                    window_minutes=5,
                    min_samples=3,
                    severity=AlertSeverity.MEDIUM,
                    cooldown_minutes=15
                )
            ],
            description="Container CPU is being throttled",
            remediation_steps=[
                "Increase container CPU limits",
                "Optimize CPU-intensive operations",
                "Review concurrent processing",
                "Consider load balancing"
            ]
        )
        
        # Service response time degradation
        rules[PerformanceAlertType.SERVICE_RESPONSE_TIME_DEGRADED] = PerformanceAlertRule(
            alert_type=PerformanceAlertType.SERVICE_RESPONSE_TIME_DEGRADED,
            service_pattern=r".*",
            thresholds=[
                PerformanceThreshold(
                    metric_name="avg_response_time_ms",
                    threshold_value=2000.0,  # 2 seconds
                    comparison="greater_than",
                    window_minutes=10,
                    min_samples=5,
                    severity=AlertSeverity.MEDIUM,
                    cooldown_minutes=20
                )
            ],
            description="Service response times have degraded",
            remediation_steps=[
                "Check service health and logs",
                "Review recent deployments",
                "Monitor resource usage",
                "Check network connectivity"
            ]
        )
        
        # Cache hit rate
        rules[PerformanceAlertType.CACHE_HIT_RATE_LOW] = PerformanceAlertRule(
            alert_type=PerformanceAlertType.CACHE_HIT_RATE_LOW,
            service_pattern=r"(redis|cache)",
            thresholds=[
                PerformanceThreshold(
                    metric_name="cache_hit_rate_percent",
                    threshold_value=70.0,  # 70% hit rate
                    comparison="less_than",
                    window_minutes=15,
                    min_samples=10,
                    severity=AlertSeverity.MEDIUM,
                    cooldown_minutes=30
                )
            ],
            description="Cache hit rate is lower than expected",
            remediation_steps=[
                "Review cache configuration",
                "Check cache key patterns",
                "Monitor cache memory usage",
                "Consider cache warming strategies"
            ]
        )
        
        # Startup time excessive
        rules[PerformanceAlertType.STARTUP_TIME_EXCESSIVE] = PerformanceAlertRule(
            alert_type=PerformanceAlertType.STARTUP_TIME_EXCESSIVE,
            service_pattern=r".*",
            thresholds=[
                PerformanceThreshold(
                    metric_name="startup_time_seconds",
                    threshold_value=120.0,  # 2 minutes (requirement: < 2 minutes)
                    comparison="greater_than",
                    window_minutes=1,
                    min_samples=1,
                    severity=AlertSeverity.HIGH,
                    cooldown_minutes=30
                )
            ],
            description="Service startup time exceeds requirements",
            remediation_steps=[
                "Check container resource allocation",
                "Review initialization processes",
                "Optimize database connections",
                "Consider parallel initialization"
            ]
        )
        
        return rules
    
    async def start_alerting(
        self,
        performance_tracker: Optional[PerformanceTracker] = None,
        metrics_collector: Optional[LocalPerformanceMetricsCollector] = None,
        query_monitor: Optional[QueryPerformanceMonitor] = None
    ) -> None:
        """Start performance alerting system."""
        if self._alerting_active:
            self.logger.warning("Performance alerting is already active")
            return
        
        # Store references to monitoring components
        self._performance_tracker = performance_tracker
        self._metrics_collector = metrics_collector
        self._query_monitor = query_monitor
        
        # Register callbacks with monitoring components
        if self._performance_tracker:
            self._performance_tracker.register_alert_callback(self._handle_performance_alert)
        
        if self._query_monitor:
            self._query_monitor.add_alert_callback(self._handle_query_alert)
        
        # Start alerting loop
        self._alerting_active = True
        self._alerting_task = asyncio.create_task(self._alerting_loop())
        
        self.logger.info("Performance alerting system started")
    
    async def stop_alerting(self) -> None:
        """Stop performance alerting system."""
        self._alerting_active = False
        
        if self._alerting_task:
            self._alerting_task.cancel()
            try:
                await self._alerting_task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Performance alerting system stopped")
    
    async def _alerting_loop(self) -> None:
        """Main alerting loop for performance monitoring."""
        while self._alerting_active:
            try:
                # Check performance metrics against thresholds
                await self._check_performance_thresholds()
                
                # Check service-specific metrics
                await self._check_service_metrics()
                
                # Check development workflow performance
                await self._check_development_workflow_performance()
                
                # Clean up old alert state
                await self._cleanup_old_alerts()
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                self.logger.error(f"Error in performance alerting loop: {e}")
                await asyncio.sleep(60)  # Continue despite errors
    
    async def _check_performance_thresholds(self) -> None:
        """Check performance metrics against configured thresholds."""
        if not self._performance_tracker:
            return
        
        try:
            # Get recent performance metrics
            recent_metrics = self._performance_tracker.get_performance_summary()
            
            for alert_type, rule in self._alert_rules.items():
                if not rule.enabled:
                    continue
                
                # Check each threshold in the rule
                for threshold in rule.thresholds:
                    await self._evaluate_threshold(alert_type, rule, threshold, recent_metrics)
                    
        except Exception as e:
            self.logger.warning(f"Failed to check performance thresholds: {e}")
    
    async def _evaluate_threshold(
        self,
        alert_type: PerformanceAlertType,
        rule: PerformanceAlertRule,
        threshold: PerformanceThreshold,
        metrics: Dict[str, Any]
    ) -> None:
        """Evaluate a specific threshold against current metrics."""
        try:
            metric_name = threshold.metric_name
            
            # Get metric value from current metrics
            metric_value = self._extract_metric_value(metrics, metric_name)
            if metric_value is None:
                return
            
            # Store metric in history
            if metric_name not in self._performance_history:
                self._performance_history[metric_name] = []
            
            self._performance_history[metric_name].append(metric_value)
            
            # Keep only recent history (based on window)
            cutoff_time = datetime.now() - timedelta(minutes=threshold.window_minutes)
            # For simplicity, keep last N samples based on window
            max_samples = threshold.window_minutes * 2  # Assuming 30-second intervals
            self._performance_history[metric_name] = self._performance_history[metric_name][-max_samples:]
            
            # Check if we have enough samples
            if len(self._performance_history[metric_name]) < threshold.min_samples:
                return
            
            # Evaluate threshold
            recent_values = self._performance_history[metric_name][-threshold.min_samples:]
            avg_value = statistics.mean(recent_values)
            
            threshold_exceeded = False
            if threshold.comparison == "greater_than":
                threshold_exceeded = avg_value > threshold.threshold_value
            elif threshold.comparison == "less_than":
                threshold_exceeded = avg_value < threshold.threshold_value
            elif threshold.comparison == "equals":
                threshold_exceeded = abs(avg_value - threshold.threshold_value) < 0.01
            
            if threshold_exceeded:
                await self._send_performance_alert(
                    alert_type=alert_type,
                    rule=rule,
                    threshold=threshold,
                    current_value=avg_value,
                    metric_name=metric_name
                )
                
        except Exception as e:
            self.logger.warning(f"Failed to evaluate threshold for {alert_type}: {e}")
    
    def _extract_metric_value(self, metrics: Dict[str, Any], metric_name: str) -> Optional[float]:
        """Extract metric value from metrics dictionary."""
        try:
            # Handle nested metric names with dot notation
            keys = metric_name.split('.')
            value = metrics
            
            for key in keys:
                if isinstance(value, dict) and key in value:
                    value = value[key]
                else:
                    return None
            
            # Convert to float if possible
            if isinstance(value, (int, float)):
                return float(value)
            
            return None
            
        except Exception:
            return None
    
    async def _check_service_metrics(self) -> None:
        """Check service-specific performance metrics."""
        if not self._metrics_collector:
            return
        
        try:
            # Get current service metrics
            service_metrics = await self._metrics_collector.get_current_service_metrics()
            
            for service_name, metrics in service_metrics.items():
                # Store metrics in history
                if service_name not in self._service_metrics_history:
                    self._service_metrics_history[service_name] = []
                
                self._service_metrics_history[service_name].append(metrics)
                
                # Keep only recent history (last hour)
                cutoff_time = datetime.now() - timedelta(hours=1)
                self._service_metrics_history[service_name] = [
                    m for m in self._service_metrics_history[service_name]
                    if m.timestamp >= cutoff_time
                ]
                
                # Check service-specific thresholds
                await self._check_service_specific_thresholds(service_name, metrics)
                
        except Exception as e:
            self.logger.warning(f"Failed to check service metrics: {e}")
    
    async def _check_service_specific_thresholds(
        self,
        service_name: str,
        metrics: LocalServiceMetrics
    ) -> None:
        """Check service-specific performance thresholds."""
        try:
            # Check memory usage
            if metrics.memory_usage_mb and metrics.memory_limit_mb:
                memory_percent = (metrics.memory_usage_mb / metrics.memory_limit_mb) * 100
                
                if memory_percent > 90:
                    await self._send_service_alert(
                        service_name=service_name,
                        alert_type=PerformanceAlertType.CONTAINER_MEMORY_LIMIT_EXCEEDED,
                        title=f"High Memory Usage - {service_name}",
                        message=f"Memory usage is at {memory_percent:.1f}% ({metrics.memory_usage_mb:.1f}MB / {metrics.memory_limit_mb:.1f}MB)",
                        severity=AlertSeverity.HIGH,
                        context={
                            "memory_usage_mb": metrics.memory_usage_mb,
                            "memory_limit_mb": metrics.memory_limit_mb,
                            "memory_percent": memory_percent
                        }
                    )
            
            # Check response time
            if metrics.response_time_ms and metrics.response_time_ms > 2000:
                await self._send_service_alert(
                    service_name=service_name,
                    alert_type=PerformanceAlertType.SERVICE_RESPONSE_TIME_DEGRADED,
                    title=f"Slow Response Time - {service_name}",
                    message=f"Average response time is {metrics.response_time_ms:.1f}ms",
                    severity=AlertSeverity.MEDIUM,
                    context={
                        "response_time_ms": metrics.response_time_ms,
                        "query_count": metrics.query_count
                    }
                )
            
            # Check error rate
            if metrics.query_count > 0:
                error_rate = (metrics.error_count / metrics.query_count) * 100
                
                if error_rate > 10:
                    await self._send_service_alert(
                        service_name=service_name,
                        alert_type=PerformanceAlertType.HIGH_QUERY_ERROR_RATE,
                        title=f"High Error Rate - {service_name}",
                        message=f"Error rate is {error_rate:.1f}% ({metrics.error_count}/{metrics.query_count} queries)",
                        severity=AlertSeverity.HIGH,
                        context={
                            "error_count": metrics.error_count,
                            "query_count": metrics.query_count,
                            "error_rate_percent": error_rate
                        }
                    )
                    
        except Exception as e:
            self.logger.warning(f"Failed to check service thresholds for {service_name}: {e}")
    
    async def _check_development_workflow_performance(self) -> None:
        """Check development workflow performance metrics."""
        try:
            # Check startup times from startup metrics
            if hasattr(self, '_startup_metrics'):
                startup_time = getattr(self._startup_metrics, 'total_startup_time', None)
                
                if startup_time and startup_time > 120:  # 2 minutes requirement
                    await self._send_workflow_alert(
                        alert_type=PerformanceAlertType.STARTUP_TIME_EXCESSIVE,
                        title="Slow Startup Time",
                        message=f"Application startup took {startup_time:.1f} seconds (requirement: < 120s)",
                        severity=AlertSeverity.HIGH,
                        context={"startup_time_seconds": startup_time}
                    )
            
            # Check hot reload performance
            # This would integrate with hot reload monitoring if available
            
        except Exception as e:
            self.logger.warning(f"Failed to check development workflow performance: {e}")
    
    async def _send_performance_alert(
        self,
        alert_type: PerformanceAlertType,
        rule: PerformanceAlertRule,
        threshold: PerformanceThreshold,
        current_value: float,
        metric_name: str
    ) -> None:
        """Send a performance alert."""
        try:
            # Check cooldown
            alert_key = f"{alert_type.value}_{metric_name}"
            now = datetime.now()
            
            if alert_key in self._last_alert_times:
                time_since_last = now - self._last_alert_times[alert_key]
                if time_since_last < timedelta(minutes=threshold.cooldown_minutes):
                    return
            
            self._last_alert_times[alert_key] = now
            
            # Convert to local alert type
            local_alert_type = self._map_to_local_alert_type(alert_type)
            
            title = f"Performance Alert: {alert_type.value.replace('_', ' ').title()}"
            message = f"{rule.description}. Current value: {current_value:.2f}, Threshold: {threshold.threshold_value:.2f}"
            
            await send_local_alert(
                alert_type=local_alert_type,
                title=title,
                message=message,
                severity=threshold.severity,
                service="performance_monitoring",
                context={
                    "alert_type": alert_type.value,
                    "metric_name": metric_name,
                    "current_value": current_value,
                    "threshold_value": threshold.threshold_value,
                    "comparison": threshold.comparison,
                    "remediation_steps": rule.remediation_steps
                }
            )
            
        except Exception as e:
            self.logger.error(f"Failed to send performance alert: {e}")
    
    async def _send_service_alert(
        self,
        service_name: str,
        alert_type: PerformanceAlertType,
        title: str,
        message: str,
        severity: AlertSeverity,
        context: Dict[str, Any]
    ) -> None:
        """Send a service-specific alert."""
        try:
            # Check cooldown
            alert_key = f"{alert_type.value}_{service_name}"
            now = datetime.now()
            
            if alert_key in self._last_alert_times:
                time_since_last = now - self._last_alert_times[alert_key]
                if time_since_last < timedelta(minutes=10):  # Default cooldown
                    return
            
            self._last_alert_times[alert_key] = now
            
            local_alert_type = self._map_to_local_alert_type(alert_type)
            
            await send_local_alert(
                alert_type=local_alert_type,
                title=title,
                message=message,
                severity=severity,
                service=service_name,
                context=context
            )
            
        except Exception as e:
            self.logger.error(f"Failed to send service alert: {e}")
    
    async def _send_workflow_alert(
        self,
        alert_type: PerformanceAlertType,
        title: str,
        message: str,
        severity: AlertSeverity,
        context: Dict[str, Any]
    ) -> None:
        """Send a development workflow alert."""
        try:
            local_alert_type = self._map_to_local_alert_type(alert_type)
            
            await send_local_alert(
                alert_type=local_alert_type,
                title=title,
                message=message,
                severity=severity,
                service="development_workflow",
                context=context
            )
            
        except Exception as e:
            self.logger.error(f"Failed to send workflow alert: {e}")
    
    def _map_to_local_alert_type(self, perf_alert_type: PerformanceAlertType) -> LocalAlertType:
        """Map performance alert type to local alert type."""
        mapping = {
            PerformanceAlertType.SLOW_DATABASE_QUERY: LocalAlertType.DATABASE_DOWN,
            PerformanceAlertType.HIGH_QUERY_ERROR_RATE: LocalAlertType.DATABASE_DOWN,
            PerformanceAlertType.DATABASE_CONNECTION_POOL_EXHAUSTED: LocalAlertType.DATABASE_DOWN,
            PerformanceAlertType.CONTAINER_MEMORY_LIMIT_EXCEEDED: LocalAlertType.HIGH_MEMORY_USAGE,
            PerformanceAlertType.CONTAINER_CPU_THROTTLING: LocalAlertType.HIGH_CPU_USAGE,
            PerformanceAlertType.SERVICE_RESPONSE_TIME_DEGRADED: LocalAlertType.DEVELOPMENT_SERVER_DOWN,
            PerformanceAlertType.STARTUP_TIME_EXCESSIVE: LocalAlertType.DEVELOPMENT_SERVER_DOWN,
        }
        
        return mapping.get(perf_alert_type, LocalAlertType.RESOURCE_LIMIT_EXCEEDED)
    
    async def _handle_performance_alert(self, alert: PerformanceAlert) -> None:
        """Handle alerts from the performance tracker."""
        try:
            # Convert performance tracker alert to local alert
            local_alert_type = LocalAlertType.RESOURCE_LIMIT_EXCEEDED
            
            if "memory" in alert.alert_type.lower():
                local_alert_type = LocalAlertType.HIGH_MEMORY_USAGE
            elif "cpu" in alert.alert_type.lower():
                local_alert_type = LocalAlertType.HIGH_CPU_USAGE
            
            await send_local_alert(
                alert_type=local_alert_type,
                title=f"Performance Alert: {alert.alert_type}",
                message=alert.message,
                severity=AlertSeverity(alert.severity),
                service="performance_tracker",
                context={
                    "original_alert_type": alert.alert_type,
                    "metric_name": alert.metric_name,
                    "threshold_value": alert.threshold_value,
                    "actual_value": alert.actual_value,
                    "recommendations": alert.recommendations
                }
            )
            
        except Exception as e:
            self.logger.error(f"Failed to handle performance alert: {e}")
    
    async def _handle_query_alert(self, alert) -> None:
        """Handle alerts from the query performance monitor."""
        try:
            # Map query alert types to local alert types
            alert_type_mapping = {
                "slow_query": LocalAlertType.DATABASE_DOWN,
                "high_cpu": LocalAlertType.HIGH_CPU_USAGE,
                "memory_spike": LocalAlertType.HIGH_MEMORY_USAGE,
                "query_error": LocalAlertType.DATABASE_DOWN
            }
            
            local_alert_type = alert_type_mapping.get(
                alert.alert_type, 
                LocalAlertType.RESOURCE_LIMIT_EXCEEDED
            )
            
            await send_local_alert(
                alert_type=local_alert_type,
                title=f"Query Performance Alert: {alert.alert_type}",
                message=alert.message,
                severity=AlertSeverity(alert.severity),
                service="query_monitor",
                context={
                    "query_id": alert.query_id,
                    "database_type": alert.database_type,
                    "alert_type": alert.alert_type,
                    "timestamp": alert.timestamp.isoformat()
                }
            )
            
        except Exception as e:
            self.logger.error(f"Failed to handle query alert: {e}")
    
    async def _cleanup_old_alerts(self) -> None:
        """Clean up old alert state to prevent memory issues."""
        try:
            cutoff_time = datetime.now() - timedelta(hours=1)
            
            # Clean up last alert times
            old_keys = [
                key for key, timestamp in self._last_alert_times.items()
                if timestamp < cutoff_time
            ]
            
            for key in old_keys:
                del self._last_alert_times[key]
            
            # Clean up performance history (keep last 100 samples per metric)
            for metric_name in self._performance_history:
                self._performance_history[metric_name] = self._performance_history[metric_name][-100:]
            
        except Exception as e:
            self.logger.warning(f"Failed to cleanup old alerts: {e}")
    
    def add_alert_callback(self, callback: Callable[[PerformanceAlert], None]) -> None:
        """Add callback for performance alerts."""
        self._alert_callbacks.append(callback)
    
    def remove_alert_callback(self, callback: Callable[[PerformanceAlert], None]) -> None:
        """Remove callback for performance alerts."""
        if callback in self._alert_callbacks:
            self._alert_callbacks.remove(callback)
    
    def get_alert_rules(self) -> Dict[PerformanceAlertType, PerformanceAlertRule]:
        """Get current alert rules configuration."""
        return self._alert_rules.copy()
    
    def update_alert_rule(self, alert_type: PerformanceAlertType, rule: PerformanceAlertRule) -> None:
        """Update an alert rule configuration."""
        self._alert_rules[alert_type] = rule
        self.logger.info(f"Updated alert rule for {alert_type.value}")
    
    def enable_alert_rule(self, alert_type: PerformanceAlertType) -> None:
        """Enable an alert rule."""
        if alert_type in self._alert_rules:
            self._alert_rules[alert_type].enabled = True
            self.logger.info(f"Enabled alert rule for {alert_type.value}")
    
    def disable_alert_rule(self, alert_type: PerformanceAlertType) -> None:
        """Disable an alert rule."""
        if alert_type in self._alert_rules:
            self._alert_rules[alert_type].enabled = False
            self.logger.info(f"Disabled alert rule for {alert_type.value}")


# Global instance
_local_performance_alerting: Optional[LocalPerformanceAlerting] = None


def get_local_performance_alerting(config: Optional[LocalDatabaseConfig] = None) -> LocalPerformanceAlerting:
    """Get the global local performance alerting instance."""
    global _local_performance_alerting
    if _local_performance_alerting is None:
        _local_performance_alerting = LocalPerformanceAlerting(config)
    return _local_performance_alerting


async def start_local_performance_alerting(
    config: Optional[LocalDatabaseConfig] = None,
    performance_tracker: Optional[PerformanceTracker] = None,
    metrics_collector: Optional[LocalPerformanceMetricsCollector] = None,
    query_monitor: Optional[QueryPerformanceMonitor] = None
) -> None:
    """Start local performance alerting system."""
    alerting = get_local_performance_alerting(config)
    await alerting.start_alerting(performance_tracker, metrics_collector, query_monitor)


async def stop_local_performance_alerting() -> None:
    """Stop local performance alerting system."""
    if _local_performance_alerting:
        await _local_performance_alerting.stop_alerting()