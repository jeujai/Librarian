"""
Error Monitoring System - Real-time error tracking and alerting

This module provides comprehensive error monitoring capabilities including:
- Real-time error tracking and rate monitoring
- Configurable alert thresholds for different error types
- Integration with existing error logging and alerting services
- Error trend analysis and pattern detection
- Automatic escalation based on error severity and frequency
"""

import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from uuid import uuid4
import threading
import json

from .error_logging_service import (
    get_error_logging_service, 
    ErrorSeverity, 
    ErrorCategory,
    ErrorLoggingService
)
from .alerting_service import (
    get_alerting_service,
    AlertSeverity,
    AlertRule,
    AlertingService
)
from ..logging_config import get_logger

logger = get_logger("error_monitoring_system")


class ErrorRateThreshold(Enum):
    """Error rate threshold levels."""
    LOW = "low"           # 1% error rate
    MEDIUM = "medium"     # 5% error rate  
    HIGH = "high"         # 10% error rate
    CRITICAL = "critical" # 20% error rate


@dataclass
class ErrorMetrics:
    """Error metrics for a specific time window."""
    timestamp: datetime
    total_operations: int = 0
    total_errors: int = 0
    error_rate: float = 0.0
    errors_by_category: Dict[str, int] = field(default_factory=dict)
    errors_by_severity: Dict[str, int] = field(default_factory=dict)
    errors_by_service: Dict[str, int] = field(default_factory=dict)
    top_error_types: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ErrorThresholdConfig:
    """Configuration for error monitoring thresholds."""
    service: str
    operation: Optional[str] = None
    category: Optional[ErrorCategory] = None
    
    # Rate thresholds (errors per minute)
    warning_rate: float = 5.0      # 5 errors per minute
    critical_rate: float = 20.0    # 20 errors per minute
    
    # Percentage thresholds (error rate %)
    warning_percentage: float = 5.0   # 5% error rate
    critical_percentage: float = 15.0 # 15% error rate
    
    # Time windows for evaluation
    evaluation_window_minutes: int = 5
    cooldown_minutes: int = 15
    
    # Escalation settings
    escalate_after_minutes: int = 30
    max_consecutive_alerts: int = 3
    
    enabled: bool = True


@dataclass
class ErrorAlert:
    """Error monitoring alert."""
    alert_id: str
    threshold_config: ErrorThresholdConfig
    triggered_at: datetime
    current_rate: float
    current_percentage: float
    threshold_exceeded: str  # 'rate' or 'percentage'
    severity: AlertSeverity
    message: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    escalated: bool = False
    consecutive_count: int = 1


class ErrorMonitoringSystem:
    """
    Comprehensive error monitoring system with real-time tracking and alerting.
    
    Features:
    - Real-time error rate monitoring
    - Configurable thresholds per service/operation
    - Automatic alert generation and escalation
    - Error trend analysis and pattern detection
    - Integration with existing logging and alerting infrastructure
    """
    
    def __init__(self):
        self.error_logging_service = get_error_logging_service()
        self.alerting_service = get_alerting_service()
        self.logger = get_logger("error_monitoring_system")
        
        # Thread-safe storage
        self._lock = threading.Lock()
        
        # Error tracking
        self._error_counts = defaultdict(lambda: deque(maxlen=1000))  # service -> error timestamps
        self._operation_counts = defaultdict(lambda: deque(maxlen=1000))  # service.operation -> timestamps
        self._success_counts = defaultdict(lambda: deque(maxlen=1000))  # service -> success timestamps
        
        # Metrics storage (last 24 hours)
        self._metrics_history = deque(maxlen=288)  # 5-minute intervals for 24 hours
        
        # Threshold configurations
        self._threshold_configs: Dict[str, ErrorThresholdConfig] = {}
        
        # Active alerts
        self._active_alerts: Dict[str, ErrorAlert] = {}
        self._alert_history: List[ErrorAlert] = []
        
        # Monitoring state
        self._monitoring_active = False
        self._monitoring_task: Optional[asyncio.Task] = None
        self._last_metrics_calculation = datetime.now()
        
        # Initialize default thresholds
        self._initialize_default_thresholds()
        
        # Register with error logging service for real-time updates
        self._register_error_callbacks()
        
        self.logger.info("Error monitoring system initialized")
    
    def _initialize_default_thresholds(self):
        """Initialize default error monitoring thresholds."""
        
        # API service thresholds
        self.add_threshold_config(ErrorThresholdConfig(
            service="api",
            warning_rate=10.0,      # 10 errors per minute
            critical_rate=30.0,     # 30 errors per minute
            warning_percentage=3.0,  # 3% error rate
            critical_percentage=10.0, # 10% error rate
            evaluation_window_minutes=5,
            cooldown_minutes=10
        ))
        
        # Database service thresholds
        self.add_threshold_config(ErrorThresholdConfig(
            service="database",
            warning_rate=5.0,       # 5 errors per minute
            critical_rate=15.0,     # 15 errors per minute
            warning_percentage=2.0,  # 2% error rate
            critical_percentage=8.0, # 8% error rate
            evaluation_window_minutes=3,
            cooldown_minutes=15
        ))
        
        # Search service thresholds
        self.add_threshold_config(ErrorThresholdConfig(
            service="search",
            warning_rate=8.0,       # 8 errors per minute
            critical_rate=25.0,     # 25 errors per minute
            warning_percentage=5.0,  # 5% error rate
            critical_percentage=15.0, # 15% error rate
            evaluation_window_minutes=5,
            cooldown_minutes=10
        ))
        
        # AI service thresholds
        self.add_threshold_config(ErrorThresholdConfig(
            service="ai_service",
            warning_rate=3.0,       # 3 errors per minute
            critical_rate=10.0,     # 10 errors per minute
            warning_percentage=8.0,  # 8% error rate (AI services can be flaky)
            critical_percentage=20.0, # 20% error rate
            evaluation_window_minutes=10,
            cooldown_minutes=20
        ))
        
        # Vector store thresholds
        self.add_threshold_config(ErrorThresholdConfig(
            service="vector_store",
            warning_rate=5.0,       # 5 errors per minute
            critical_rate=20.0,     # 20 errors per minute
            warning_percentage=3.0,  # 3% error rate
            critical_percentage=12.0, # 12% error rate
            evaluation_window_minutes=5,
            cooldown_minutes=15
        ))
        
        # Global fallback threshold
        self.add_threshold_config(ErrorThresholdConfig(
            service="*",  # Wildcard for any service not specifically configured
            warning_rate=15.0,      # 15 errors per minute
            critical_rate=50.0,     # 50 errors per minute
            warning_percentage=10.0, # 10% error rate
            critical_percentage=25.0, # 25% error rate
            evaluation_window_minutes=5,
            cooldown_minutes=15
        ))
    
    def _register_error_callbacks(self):
        """Register callbacks with error logging service for real-time updates."""
        # This would be enhanced if the error logging service supported callbacks
        # For now, we'll poll the error logging service periodically
        pass
    
    def add_threshold_config(self, config: ErrorThresholdConfig) -> bool:
        """Add or update an error threshold configuration."""
        try:
            config_key = self._get_config_key(config.service, config.operation, config.category)
            
            with self._lock:
                self._threshold_configs[config_key] = config
            
            self.logger.info(f"Added error threshold config: {config_key}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add threshold config: {e}")
            return False
    
    def remove_threshold_config(self, service: str, operation: Optional[str] = None, 
                              category: Optional[ErrorCategory] = None) -> bool:
        """Remove an error threshold configuration."""
        try:
            config_key = self._get_config_key(service, operation, category)
            
            with self._lock:
                if config_key in self._threshold_configs:
                    del self._threshold_configs[config_key]
                    self.logger.info(f"Removed error threshold config: {config_key}")
                    return True
            
            return False
            
        except Exception as e:
            self.logger.error(f"Failed to remove threshold config: {e}")
            return False
    
    def _get_config_key(self, service: str, operation: Optional[str] = None, 
                       category: Optional[ErrorCategory] = None) -> str:
        """Generate configuration key."""
        parts = [service]
        if operation:
            parts.append(operation)
        if category:
            parts.append(category.value)
        return ":".join(parts)
    
    def record_operation(self, service: str, operation: str, success: bool, 
                        error_category: Optional[ErrorCategory] = None,
                        error_severity: Optional[ErrorSeverity] = None):
        """Record an operation result for monitoring."""
        timestamp = datetime.now()
        
        with self._lock:
            if success:
                self._success_counts[service].append(timestamp)
                self._success_counts[f"{service}.{operation}"].append(timestamp)
            else:
                self._error_counts[service].append(timestamp)
                self._error_counts[f"{service}.{operation}"].append(timestamp)
                
                # Record additional error metadata
                if error_category or error_severity:
                    error_key = f"{service}:{error_category.value if error_category else 'unknown'}"
                    self._error_counts[error_key].append(timestamp)
    
    def get_error_rate(self, service: str, operation: Optional[str] = None, 
                      window_minutes: int = 5) -> Dict[str, Any]:
        """Get current error rate for a service/operation."""
        cutoff_time = datetime.now() - timedelta(minutes=window_minutes)
        
        key = f"{service}.{operation}" if operation else service
        
        with self._lock:
            # Count errors in time window
            error_timestamps = self._error_counts[key]
            success_timestamps = self._success_counts[key]
            
            recent_errors = len([t for t in error_timestamps if t >= cutoff_time])
            recent_successes = len([t for t in success_timestamps if t >= cutoff_time])
            
            total_operations = recent_errors + recent_successes
            error_rate_percentage = (recent_errors / total_operations * 100) if total_operations > 0 else 0
            errors_per_minute = recent_errors / window_minutes if window_minutes > 0 else 0
            
            return {
                'service': service,
                'operation': operation,
                'window_minutes': window_minutes,
                'total_operations': total_operations,
                'total_errors': recent_errors,
                'total_successes': recent_successes,
                'error_rate_percentage': error_rate_percentage,
                'errors_per_minute': errors_per_minute,
                'timestamp': datetime.now()
            }
    
    def get_system_error_metrics(self, window_minutes: int = 5) -> ErrorMetrics:
        """Get comprehensive system error metrics."""
        cutoff_time = datetime.now() - timedelta(minutes=window_minutes)
        
        with self._lock:
            total_errors = 0
            total_operations = 0
            errors_by_service = defaultdict(int)
            
            # Aggregate across all services
            for key, error_timestamps in self._error_counts.items():
                if '.' not in key and ':' not in key:  # Service-level key
                    service_errors = len([t for t in error_timestamps if t >= cutoff_time])
                    service_successes = len([t for t in self._success_counts[key] if t >= cutoff_time])
                    
                    total_errors += service_errors
                    total_operations += service_errors + service_successes
                    errors_by_service[key] = service_errors
            
            error_rate = (total_errors / total_operations * 100) if total_operations > 0 else 0
            
            # Get error summary from error logging service
            error_summary = self.error_logging_service.get_error_summary(hours=window_minutes/60)
            
            return ErrorMetrics(
                timestamp=datetime.now(),
                total_operations=total_operations,
                total_errors=total_errors,
                error_rate=error_rate,
                errors_by_category=error_summary.get('error_categories', {}),
                errors_by_severity=error_summary.get('error_severities', {}),
                errors_by_service=dict(errors_by_service),
                top_error_types=error_summary.get('top_error_patterns', [])[:5]
            )
    
    async def start_monitoring(self):
        """Start the error monitoring system."""
        if self._monitoring_active:
            self.logger.warning("Error monitoring is already active")
            return
        
        self._monitoring_active = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        
        # Register alert rules with alerting service
        self._register_alert_rules()
        
        self.logger.info("Error monitoring system started")
    
    async def stop_monitoring(self):
        """Stop the error monitoring system."""
        self._monitoring_active = False
        
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
            self._monitoring_task = None
        
        self.logger.info("Error monitoring system stopped")
    
    def _register_alert_rules(self):
        """Register error monitoring alert rules with the alerting service."""
        
        # High error rate alert
        self.alerting_service.add_alert_rule(AlertRule(
            rule_id="error_monitoring_high_rate",
            name="High System Error Rate",
            description="System-wide error rate is above acceptable threshold",
            metric_name="system_error_rate",
            condition="greater_than",
            threshold=10.0,  # 10% error rate
            severity=AlertSeverity.HIGH,
            evaluation_window=300,  # 5 minutes
            cooldown_period=900,    # 15 minutes
            tags={"category": "error_monitoring", "type": "error_rate"}
        ))
        
        # Critical error rate alert
        self.alerting_service.add_alert_rule(AlertRule(
            rule_id="error_monitoring_critical_rate",
            name="Critical System Error Rate",
            description="System-wide error rate is critically high",
            metric_name="system_error_rate",
            condition="greater_than",
            threshold=25.0,  # 25% error rate
            severity=AlertSeverity.CRITICAL,
            evaluation_window=180,  # 3 minutes
            cooldown_period=600,    # 10 minutes
            tags={"category": "error_monitoring", "type": "error_rate"}
        ))
        
        # Error spike alert
        self.alerting_service.add_alert_rule(AlertRule(
            rule_id="error_monitoring_spike",
            name="Error Rate Spike",
            description="Sudden spike in error rate detected",
            metric_name="errors_per_minute",
            condition="greater_than",
            threshold=50.0,  # 50 errors per minute
            severity=AlertSeverity.HIGH,
            evaluation_window=120,  # 2 minutes
            cooldown_period=600,    # 10 minutes
            tags={"category": "error_monitoring", "type": "error_spike"}
        ))
    
    async def _monitoring_loop(self):
        """Main monitoring loop."""
        while self._monitoring_active:
            try:
                # Calculate current metrics
                metrics = self.get_system_error_metrics(window_minutes=5)
                
                # Store metrics history
                with self._lock:
                    self._metrics_history.append(metrics)
                
                # Record metrics with alerting service
                self.alerting_service.record_metric("system_error_rate", metrics.error_rate)
                self.alerting_service.record_metric("errors_per_minute", metrics.total_errors / 5.0)
                self.alerting_service.record_metric("total_operations", metrics.total_operations)
                
                # Evaluate thresholds
                await self._evaluate_thresholds(metrics)
                
                # Evaluate alerting rules
                await self.alerting_service.evaluate_alerts()
                
                # Update last calculation time
                self._last_metrics_calculation = datetime.now()
                
                # Wait before next evaluation (30 seconds)
                await asyncio.sleep(30)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(30)  # Continue monitoring despite errors
    
    async def _evaluate_thresholds(self, system_metrics: ErrorMetrics):
        """Evaluate error thresholds and generate alerts."""
        current_time = datetime.now()
        
        # Evaluate service-specific thresholds
        for service in system_metrics.errors_by_service.keys():
            await self._evaluate_service_threshold(service, current_time)
        
        # Evaluate global thresholds
        await self._evaluate_global_threshold(system_metrics, current_time)
    
    async def _evaluate_service_threshold(self, service: str, current_time: datetime):
        """Evaluate threshold for a specific service."""
        # Find applicable threshold config
        config = self._find_threshold_config(service)
        if not config or not config.enabled:
            return
        
        # Get service error rate
        error_rate_data = self.get_error_rate(service, window_minutes=config.evaluation_window_minutes)
        
        # Check if thresholds are exceeded
        rate_exceeded = error_rate_data['errors_per_minute'] > config.warning_rate
        percentage_exceeded = error_rate_data['error_rate_percentage'] > config.warning_percentage
        
        critical_rate_exceeded = error_rate_data['errors_per_minute'] > config.critical_rate
        critical_percentage_exceeded = error_rate_data['error_rate_percentage'] > config.critical_percentage
        
        if critical_rate_exceeded or critical_percentage_exceeded:
            await self._trigger_error_alert(
                config, error_rate_data, AlertSeverity.CRITICAL, 
                "critical_rate" if critical_rate_exceeded else "critical_percentage"
            )
        elif rate_exceeded or percentage_exceeded:
            await self._trigger_error_alert(
                config, error_rate_data, AlertSeverity.HIGH,
                "warning_rate" if rate_exceeded else "warning_percentage"
            )
    
    async def _evaluate_global_threshold(self, metrics: ErrorMetrics, current_time: datetime):
        """Evaluate global system thresholds."""
        # Check for global error rate spikes
        if metrics.error_rate > 20.0:  # 20% global error rate
            await self._trigger_global_alert(
                metrics, AlertSeverity.CRITICAL,
                f"Critical system-wide error rate: {metrics.error_rate:.1f}%"
            )
        elif metrics.error_rate > 10.0:  # 10% global error rate
            await self._trigger_global_alert(
                metrics, AlertSeverity.HIGH,
                f"High system-wide error rate: {metrics.error_rate:.1f}%"
            )
        
        # Check for error volume spikes
        errors_per_minute = metrics.total_errors / 5.0  # 5-minute window
        if errors_per_minute > 100:  # 100 errors per minute
            await self._trigger_global_alert(
                metrics, AlertSeverity.CRITICAL,
                f"Critical error volume: {errors_per_minute:.1f} errors/minute"
            )
        elif errors_per_minute > 50:  # 50 errors per minute
            await self._trigger_global_alert(
                metrics, AlertSeverity.HIGH,
                f"High error volume: {errors_per_minute:.1f} errors/minute"
            )
    
    def _find_threshold_config(self, service: str, operation: Optional[str] = None, 
                             category: Optional[ErrorCategory] = None) -> Optional[ErrorThresholdConfig]:
        """Find the most specific threshold configuration for the given parameters."""
        with self._lock:
            # Try exact match first
            exact_key = self._get_config_key(service, operation, category)
            if exact_key in self._threshold_configs:
                return self._threshold_configs[exact_key]
            
            # Try service + operation
            if operation:
                service_op_key = self._get_config_key(service, operation)
                if service_op_key in self._threshold_configs:
                    return self._threshold_configs[service_op_key]
            
            # Try service only
            service_key = self._get_config_key(service)
            if service_key in self._threshold_configs:
                return self._threshold_configs[service_key]
            
            # Try wildcard
            if "*" in self._threshold_configs:
                return self._threshold_configs["*"]
            
            return None
    
    async def _trigger_error_alert(self, config: ErrorThresholdConfig, 
                                 error_rate_data: Dict[str, Any],
                                 severity: AlertSeverity, threshold_type: str):
        """Trigger an error monitoring alert."""
        alert_id = str(uuid4())
        
        # Check for existing active alert
        existing_alert_key = f"{config.service}:{threshold_type}"
        existing_alert = None
        
        with self._lock:
            for alert in self._active_alerts.values():
                if (alert.threshold_config.service == config.service and 
                    alert.threshold_exceeded == threshold_type):
                    existing_alert = alert
                    break
        
        if existing_alert:
            # Update existing alert
            existing_alert.consecutive_count += 1
            existing_alert.current_rate = error_rate_data['errors_per_minute']
            existing_alert.current_percentage = error_rate_data['error_rate_percentage']
            
            # Check for escalation
            if (existing_alert.consecutive_count >= config.max_consecutive_alerts and 
                not existing_alert.escalated):
                existing_alert.escalated = True
                existing_alert.severity = AlertSeverity.CRITICAL
                self.logger.critical(f"Error alert escalated: {existing_alert.message}")
            
            return
        
        # Create new alert
        message = (f"Error threshold exceeded for {config.service}: "
                  f"{error_rate_data['errors_per_minute']:.1f} errors/min, "
                  f"{error_rate_data['error_rate_percentage']:.1f}% error rate")
        
        alert = ErrorAlert(
            alert_id=alert_id,
            threshold_config=config,
            triggered_at=datetime.now(),
            current_rate=error_rate_data['errors_per_minute'],
            current_percentage=error_rate_data['error_rate_percentage'],
            threshold_exceeded=threshold_type,
            severity=severity,
            message=message,
            metadata={
                'service': config.service,
                'operation': config.operation,
                'total_operations': error_rate_data['total_operations'],
                'window_minutes': config.evaluation_window_minutes
            }
        )
        
        with self._lock:
            self._active_alerts[alert_id] = alert
            self._alert_history.append(alert)
        
        self.logger.warning(f"Error monitoring alert triggered: {message}")
        
        # Send notification through alerting service
        self.alerting_service.record_metric(
            f"error_alert_{config.service}", 
            error_rate_data['error_rate_percentage']
        )
    
    async def _trigger_global_alert(self, metrics: ErrorMetrics, 
                                  severity: AlertSeverity, message: str):
        """Trigger a global system error alert."""
        alert_id = str(uuid4())
        
        # Check for existing global alert
        existing_alert = None
        with self._lock:
            for alert in self._active_alerts.values():
                if alert.threshold_config.service == "system" and alert.severity == severity:
                    existing_alert = alert
                    break
        
        if existing_alert:
            existing_alert.consecutive_count += 1
            existing_alert.current_rate = metrics.total_errors / 5.0
            existing_alert.current_percentage = metrics.error_rate
            return
        
        # Create global threshold config for this alert
        global_config = ErrorThresholdConfig(
            service="system",
            warning_rate=50.0,
            critical_rate=100.0,
            warning_percentage=10.0,
            critical_percentage=20.0
        )
        
        alert = ErrorAlert(
            alert_id=alert_id,
            threshold_config=global_config,
            triggered_at=datetime.now(),
            current_rate=metrics.total_errors / 5.0,
            current_percentage=metrics.error_rate,
            threshold_exceeded="global",
            severity=severity,
            message=message,
            metadata={
                'total_operations': metrics.total_operations,
                'errors_by_service': metrics.errors_by_service,
                'errors_by_category': metrics.errors_by_category
            }
        )
        
        with self._lock:
            self._active_alerts[alert_id] = alert
            self._alert_history.append(alert)
        
        self.logger.error(f"Global error alert triggered: {message}")
    
    def get_active_alerts(self) -> List[ErrorAlert]:
        """Get all active error monitoring alerts."""
        with self._lock:
            return list(self._active_alerts.values())
    
    def get_alert_history(self, limit: int = 50) -> List[ErrorAlert]:
        """Get error alert history."""
        with self._lock:
            return sorted(self._alert_history, key=lambda x: x.triggered_at, reverse=True)[:limit]
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an error monitoring alert."""
        with self._lock:
            if alert_id in self._active_alerts:
                alert = self._active_alerts[alert_id]
                alert.metadata['acknowledged'] = True
                alert.metadata['acknowledged_at'] = datetime.now()
                self.logger.info(f"Error alert acknowledged: {alert.message}")
                return True
        return False
    
    def resolve_alert(self, alert_id: str, reason: str = "Manual resolution") -> bool:
        """Resolve an error monitoring alert."""
        with self._lock:
            if alert_id in self._active_alerts:
                alert = self._active_alerts.pop(alert_id)
                alert.metadata['resolved'] = True
                alert.metadata['resolved_at'] = datetime.now()
                alert.metadata['resolution_reason'] = reason
                self.logger.info(f"Error alert resolved: {alert.message} - {reason}")
                return True
        return False
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get comprehensive monitoring system status."""
        with self._lock:
            active_alerts = len(self._active_alerts)
            critical_alerts = len([a for a in self._active_alerts.values() 
                                 if a.severity == AlertSeverity.CRITICAL])
            
            # Get recent metrics
            recent_metrics = list(self._metrics_history)[-12:]  # Last hour (5-min intervals)
            
            avg_error_rate = 0
            if recent_metrics:
                avg_error_rate = sum(m.error_rate for m in recent_metrics) / len(recent_metrics)
            
            return {
                'monitoring_active': self._monitoring_active,
                'last_evaluation': self._last_metrics_calculation,
                'threshold_configs': len(self._threshold_configs),
                'active_alerts': active_alerts,
                'critical_alerts': critical_alerts,
                'total_alert_history': len(self._alert_history),
                'current_system_metrics': self.get_system_error_metrics(),
                'average_error_rate_1h': avg_error_rate,
                'services_monitored': len(set(config.service for config in self._threshold_configs.values())),
                'metrics_history_size': len(self._metrics_history)
            }
    
    def export_monitoring_data(self, filepath: Optional[str] = None) -> str:
        """Export error monitoring data to JSON file."""
        if not filepath:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filepath = f"error_monitoring_export_{timestamp}.json"
        
        with self._lock:
            export_data = {
                'export_timestamp': datetime.now().isoformat(),
                'monitoring_status': self.get_monitoring_status(),
                'threshold_configs': {
                    key: {
                        'service': config.service,
                        'operation': config.operation,
                        'category': config.category.value if config.category else None,
                        'warning_rate': config.warning_rate,
                        'critical_rate': config.critical_rate,
                        'warning_percentage': config.warning_percentage,
                        'critical_percentage': config.critical_percentage,
                        'evaluation_window_minutes': config.evaluation_window_minutes,
                        'enabled': config.enabled
                    }
                    for key, config in self._threshold_configs.items()
                },
                'active_alerts': [
                    {
                        'alert_id': alert.alert_id,
                        'service': alert.threshold_config.service,
                        'triggered_at': alert.triggered_at.isoformat(),
                        'severity': alert.severity.value,
                        'message': alert.message,
                        'current_rate': alert.current_rate,
                        'current_percentage': alert.current_percentage,
                        'consecutive_count': alert.consecutive_count,
                        'escalated': alert.escalated
                    }
                    for alert in self._active_alerts.values()
                ],
                'metrics_history': [
                    {
                        'timestamp': metrics.timestamp.isoformat(),
                        'total_operations': metrics.total_operations,
                        'total_errors': metrics.total_errors,
                        'error_rate': metrics.error_rate,
                        'errors_by_service': metrics.errors_by_service
                    }
                    for metrics in list(self._metrics_history)[-24:]  # Last 2 hours
                ]
            }
        
        try:
            import os
            if filepath and os.path.dirname(filepath):
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            with open(filepath, 'w') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            self.logger.info(f"Error monitoring data exported to {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"Failed to export monitoring data: {e}")
            raise


# Global error monitoring system instance
_error_monitoring_system = None


def get_error_monitoring_system() -> ErrorMonitoringSystem:
    """Get the global error monitoring system instance."""
    global _error_monitoring_system
    if _error_monitoring_system is None:
        _error_monitoring_system = ErrorMonitoringSystem()
    return _error_monitoring_system


# Convenience functions
async def start_error_monitoring():
    """Start the global error monitoring system."""
    monitoring_system = get_error_monitoring_system()
    await monitoring_system.start_monitoring()


async def stop_error_monitoring():
    """Stop the global error monitoring system."""
    monitoring_system = get_error_monitoring_system()
    await monitoring_system.stop_monitoring()


def record_operation_result(service: str, operation: str, success: bool, **kwargs):
    """Record an operation result for error monitoring."""
    monitoring_system = get_error_monitoring_system()
    monitoring_system.record_operation(service, operation, success, **kwargs)


def get_current_error_rate(service: str, operation: Optional[str] = None) -> Dict[str, Any]:
    """Get current error rate for a service/operation."""
    monitoring_system = get_error_monitoring_system()
    return monitoring_system.get_error_rate(service, operation)