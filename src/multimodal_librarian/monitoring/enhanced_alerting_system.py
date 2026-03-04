"""
Enhanced Alerting System - Comprehensive alerting with performance monitoring and escalation

This module extends the existing alerting service with:
- Performance-based alerting (response time, throughput, resource usage)
- Enhanced error rate monitoring with intelligent thresholds
- Multi-level escalation procedures with automatic escalation
- Integration with external notification systems
- Alert correlation and noise reduction
- Performance trend analysis for proactive alerting

Validates: Requirement 6.4 - Alerting system with performance alerts, error rate monitoring, and escalation procedures
"""

import asyncio
import json
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Set
from uuid import uuid4
import threading
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests

from .alerting_service import (
    get_alerting_service, AlertingService, AlertSeverity, AlertStatus, 
    AlertRule, Alert, NotificationChannel
)
from .comprehensive_metrics_collector import ComprehensiveMetricsCollector
from .error_monitoring_system import get_error_monitoring_system, ErrorMonitoringSystem
from ..config import get_settings
from ..logging_config import get_logger

logger = get_logger("enhanced_alerting_system")


class EscalationLevel(Enum):
    """Alert escalation levels."""
    LEVEL_1 = "level_1"  # Initial alert
    LEVEL_2 = "level_2"  # First escalation
    LEVEL_3 = "level_3"  # Second escalation
    LEVEL_4 = "level_4"  # Critical escalation


class AlertCategory(Enum):
    """Alert categories for better organization."""
    PERFORMANCE = "performance"
    ERROR_RATE = "error_rate"
    RESOURCE_USAGE = "resource_usage"
    AVAILABILITY = "availability"
    SECURITY = "security"
    BUSINESS_METRICS = "business_metrics"


@dataclass
class EscalationRule:
    """Escalation rule configuration."""
    rule_id: str
    name: str
    category: AlertCategory
    severity_threshold: AlertSeverity
    
    # Escalation timing
    level_1_duration_minutes: int = 15  # Time before first escalation
    level_2_duration_minutes: int = 30  # Time before second escalation
    level_3_duration_minutes: int = 60  # Time before critical escalation
    
    # Escalation targets
    level_1_channels: List[str] = field(default_factory=list)
    level_2_channels: List[str] = field(default_factory=list)
    level_3_channels: List[str] = field(default_factory=list)
    level_4_channels: List[str] = field(default_factory=list)
    
    # Escalation conditions
    auto_escalate: bool = True
    require_acknowledgment: bool = True
    max_escalation_level: EscalationLevel = EscalationLevel.LEVEL_4
    
    enabled: bool = True


@dataclass
class PerformanceThreshold:
    """Performance-based alert threshold."""
    metric_name: str
    threshold_value: float
    comparison: str  # "greater_than", "less_than", "equals"
    severity: AlertSeverity
    evaluation_window_minutes: int = 5
    consecutive_violations: int = 2  # Number of consecutive violations before alerting
    description: str = ""
    category: AlertCategory = AlertCategory.PERFORMANCE


@dataclass
class AlertCorrelation:
    """Alert correlation for noise reduction."""
    correlation_id: str
    related_alerts: List[str]  # Alert IDs
    root_cause_alert: Optional[str] = None
    correlation_reason: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    suppressed_alerts: List[str] = field(default_factory=list)


@dataclass
class EscalatedAlert:
    """Escalated alert with escalation history."""
    alert_id: str
    original_alert: Alert
    escalation_rule: EscalationRule
    current_level: EscalationLevel
    escalation_history: List[Dict[str, Any]] = field(default_factory=list)
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)


class EnhancedAlertingSystem:
    """
    Enhanced alerting system with performance monitoring and escalation procedures.
    
    Features:
    - Performance-based alerting with intelligent thresholds
    - Multi-level escalation with automatic progression
    - Alert correlation and noise reduction
    - Integration with external notification systems
    - Trend analysis for proactive alerting
    - Comprehensive alert management and reporting
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = get_logger("enhanced_alerting_system")
        
        # Core services
        self.alerting_service = get_alerting_service()
        self.error_monitoring = get_error_monitoring_system()
        self.metrics_collector = None  # Will be initialized if available
        
        # Thread-safe storage
        self._lock = threading.Lock()
        
        # Enhanced alerting state
        self._escalation_rules: Dict[str, EscalationRule] = {}
        self._performance_thresholds: Dict[str, PerformanceThreshold] = {}
        self._escalated_alerts: Dict[str, EscalatedAlert] = {}
        self._alert_correlations: Dict[str, AlertCorrelation] = {}
        
        # Performance tracking
        self._performance_history = defaultdict(lambda: deque(maxlen=1000))
        self._threshold_violations = defaultdict(int)
        
        # Notification channels
        self._external_channels: Dict[str, Dict[str, Any]] = {}
        
        # System state
        self._system_active = False
        self._escalation_task: Optional[asyncio.Task] = None
        self._performance_monitoring_task: Optional[asyncio.Task] = None
        
        # Initialize default configurations
        self._initialize_default_escalation_rules()
        self._initialize_performance_thresholds()
        self._initialize_external_channels()
        
        self.logger.info("Enhanced alerting system initialized")
    
    def _initialize_default_escalation_rules(self):
        """Initialize default escalation rules."""
        
        # Critical system performance escalation
        self.add_escalation_rule(EscalationRule(
            rule_id="critical_performance",
            name="Critical Performance Issues",
            category=AlertCategory.PERFORMANCE,
            severity_threshold=AlertSeverity.CRITICAL,
            level_1_duration_minutes=5,   # Escalate quickly for critical issues
            level_2_duration_minutes=15,
            level_3_duration_minutes=30,
            level_1_channels=["console", "email_ops"],
            level_2_channels=["console", "email_ops", "slack_alerts"],
            level_3_channels=["console", "email_ops", "slack_alerts", "pager_duty"],
            level_4_channels=["console", "email_ops", "slack_alerts", "pager_duty", "sms_emergency"],
            auto_escalate=True,
            require_acknowledgment=True
        ))
        
        # High error rate escalation
        self.add_escalation_rule(EscalationRule(
            rule_id="high_error_rate",
            name="High Error Rate",
            category=AlertCategory.ERROR_RATE,
            severity_threshold=AlertSeverity.HIGH,
            level_1_duration_minutes=10,
            level_2_duration_minutes=25,
            level_3_duration_minutes=45,
            level_1_channels=["console", "email_ops"],
            level_2_channels=["console", "email_ops", "slack_alerts"],
            level_3_channels=["console", "email_ops", "slack_alerts", "pager_duty"],
            auto_escalate=True,
            require_acknowledgment=False  # Auto-resolve when error rate drops
        ))
        
        # Resource usage escalation
        self.add_escalation_rule(EscalationRule(
            rule_id="resource_exhaustion",
            name="Resource Exhaustion",
            category=AlertCategory.RESOURCE_USAGE,
            severity_threshold=AlertSeverity.HIGH,
            level_1_duration_minutes=15,
            level_2_duration_minutes=30,
            level_3_duration_minutes=60,
            level_1_channels=["console", "email_ops"],
            level_2_channels=["console", "email_ops", "slack_alerts"],
            level_3_channels=["console", "email_ops", "slack_alerts", "pager_duty"],
            auto_escalate=True,
            require_acknowledgment=True
        ))
        
        # Availability escalation
        self.add_escalation_rule(EscalationRule(
            rule_id="service_availability",
            name="Service Availability Issues",
            category=AlertCategory.AVAILABILITY,
            severity_threshold=AlertSeverity.CRITICAL,
            level_1_duration_minutes=2,   # Very fast escalation for availability
            level_2_duration_minutes=5,
            level_3_duration_minutes=10,
            level_1_channels=["console", "email_ops", "slack_alerts"],
            level_2_channels=["console", "email_ops", "slack_alerts", "pager_duty"],
            level_3_channels=["console", "email_ops", "slack_alerts", "pager_duty", "sms_emergency"],
            level_4_channels=["console", "email_ops", "slack_alerts", "pager_duty", "sms_emergency", "phone_tree"],
            auto_escalate=True,
            require_acknowledgment=True,
            max_escalation_level=EscalationLevel.LEVEL_4
        ))
    
    def _initialize_performance_thresholds(self):
        """Initialize performance-based alert thresholds."""
        
        # Response time thresholds
        self.add_performance_threshold(PerformanceThreshold(
            metric_name="avg_response_time_ms",
            threshold_value=1000.0,  # 1 second
            comparison="greater_than",
            severity=AlertSeverity.MEDIUM,
            evaluation_window_minutes=5,
            consecutive_violations=3,
            description="Average response time is too high",
            category=AlertCategory.PERFORMANCE
        ))
        
        self.add_performance_threshold(PerformanceThreshold(
            metric_name="p95_response_time_ms",
            threshold_value=2000.0,  # 2 seconds
            comparison="greater_than",
            severity=AlertSeverity.HIGH,
            evaluation_window_minutes=3,
            consecutive_violations=2,
            description="95th percentile response time is critically high",
            category=AlertCategory.PERFORMANCE
        ))
        
        # Throughput thresholds
        self.add_performance_threshold(PerformanceThreshold(
            metric_name="requests_per_minute",
            threshold_value=10.0,
            comparison="less_than",
            severity=AlertSeverity.MEDIUM,
            evaluation_window_minutes=10,
            consecutive_violations=2,
            description="Request throughput is unusually low",
            category=AlertCategory.PERFORMANCE
        ))
        
        # Resource usage thresholds
        self.add_performance_threshold(PerformanceThreshold(
            metric_name="cpu_percent",
            threshold_value=85.0,
            comparison="greater_than",
            severity=AlertSeverity.HIGH,
            evaluation_window_minutes=5,
            consecutive_violations=3,
            description="CPU usage is critically high",
            category=AlertCategory.RESOURCE_USAGE
        ))
        
        self.add_performance_threshold(PerformanceThreshold(
            metric_name="memory_percent",
            threshold_value=90.0,
            comparison="greater_than",
            severity=AlertSeverity.CRITICAL,
            evaluation_window_minutes=3,
            consecutive_violations=2,
            description="Memory usage is critically high",
            category=AlertCategory.RESOURCE_USAGE
        ))
        
        self.add_performance_threshold(PerformanceThreshold(
            metric_name="disk_percent",
            threshold_value=95.0,
            comparison="greater_than",
            severity=AlertSeverity.CRITICAL,
            evaluation_window_minutes=1,
            consecutive_violations=1,
            description="Disk usage is critically high",
            category=AlertCategory.RESOURCE_USAGE
        ))
        
        # Cache performance thresholds
        self.add_performance_threshold(PerformanceThreshold(
            metric_name="cache_hit_rate_percent",
            threshold_value=50.0,
            comparison="less_than",
            severity=AlertSeverity.MEDIUM,
            evaluation_window_minutes=15,
            consecutive_violations=2,
            description="Cache hit rate is too low",
            category=AlertCategory.PERFORMANCE
        ))
        
        # Error rate thresholds
        self.add_performance_threshold(PerformanceThreshold(
            metric_name="error_rate_percent",
            threshold_value=5.0,
            comparison="greater_than",
            severity=AlertSeverity.HIGH,
            evaluation_window_minutes=5,
            consecutive_violations=2,
            description="Error rate is too high",
            category=AlertCategory.ERROR_RATE
        ))
        
        self.add_performance_threshold(PerformanceThreshold(
            metric_name="error_rate_percent",
            threshold_value=15.0,
            comparison="greater_than",
            severity=AlertSeverity.CRITICAL,
            evaluation_window_minutes=3,
            consecutive_violations=1,
            description="Error rate is critically high",
            category=AlertCategory.ERROR_RATE
        ))
    
    def _initialize_external_channels(self):
        """Initialize external notification channels."""
        
        # Email configuration
        self._external_channels["email_ops"] = {
            "type": "email",
            "enabled": False,  # Disabled by default - requires configuration
            "config": {
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "username": "",  # To be configured
                "password": "",  # To be configured
                "recipients": ["ops@multimodal-librarian.com"],
                "sender": "alerts@multimodal-librarian.com"
            }
        }
        
        # Slack configuration
        self._external_channels["slack_alerts"] = {
            "type": "slack",
            "enabled": False,  # Disabled by default - requires webhook URL
            "config": {
                "webhook_url": "",  # To be configured
                "channel": "#alerts",
                "username": "AlertBot",
                "icon_emoji": ":warning:"
            }
        }
        
        # PagerDuty configuration
        self._external_channels["pager_duty"] = {
            "type": "pagerduty",
            "enabled": False,  # Disabled by default - requires integration key
            "config": {
                "integration_key": "",  # To be configured
                "service_url": "https://events.pagerduty.com/v2/enqueue"
            }
        }
        
        # SMS configuration (placeholder)
        self._external_channels["sms_emergency"] = {
            "type": "sms",
            "enabled": False,  # Disabled by default - requires SMS service
            "config": {
                "service": "twilio",  # or "aws_sns"
                "account_sid": "",
                "auth_token": "",
                "from_number": "",
                "to_numbers": []
            }
        }
        
        # Phone tree (placeholder)
        self._external_channels["phone_tree"] = {
            "type": "phone",
            "enabled": False,  # Disabled by default - requires phone service
            "config": {
                "service": "twilio",
                "numbers": [],
                "message_template": "Critical alert: {alert_message}"
            }
        }
    
    def add_escalation_rule(self, rule: EscalationRule) -> bool:
        """Add or update an escalation rule."""
        try:
            with self._lock:
                self._escalation_rules[rule.rule_id] = rule
            
            self.logger.info(f"Added escalation rule: {rule.name} ({rule.rule_id})")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add escalation rule {rule.rule_id}: {e}")
            return False
    
    def add_performance_threshold(self, threshold: PerformanceThreshold) -> bool:
        """Add or update a performance threshold."""
        try:
            with self._lock:
                self._performance_thresholds[threshold.metric_name] = threshold
            
            self.logger.info(f"Added performance threshold: {threshold.metric_name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to add performance threshold {threshold.metric_name}: {e}")
            return False
    
    def configure_external_channel(self, channel_id: str, config: Dict[str, Any]) -> bool:
        """Configure an external notification channel."""
        try:
            if channel_id not in self._external_channels:
                self.logger.error(f"Unknown channel: {channel_id}")
                return False
            
            with self._lock:
                self._external_channels[channel_id]["config"].update(config)
                self._external_channels[channel_id]["enabled"] = True
            
            self.logger.info(f"Configured external channel: {channel_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to configure channel {channel_id}: {e}")
            return False
    
    async def start_enhanced_alerting(self):
        """Start the enhanced alerting system."""
        if self._system_active:
            self.logger.warning("Enhanced alerting system is already active")
            return
        
        self._system_active = True
        
        # Start escalation monitoring
        self._escalation_task = asyncio.create_task(self._escalation_loop())
        
        # Start performance monitoring if metrics collector is available
        try:
            from .comprehensive_metrics_collector import ComprehensiveMetricsCollector
            self.metrics_collector = ComprehensiveMetricsCollector()
            self._performance_monitoring_task = asyncio.create_task(self._performance_monitoring_loop())
            self.logger.info("Performance monitoring enabled")
        except Exception as e:
            self.logger.warning(f"Performance monitoring not available: {e}")
        
        # Start error monitoring integration
        try:
            await self.error_monitoring.start_monitoring()
            self.logger.info("Error monitoring integration enabled")
        except Exception as e:
            self.logger.warning(f"Error monitoring integration failed: {e}")
        
        self.logger.info("Enhanced alerting system started")
    
    async def stop_enhanced_alerting(self):
        """Stop the enhanced alerting system."""
        self._system_active = False
        
        # Stop escalation monitoring
        if self._escalation_task:
            self._escalation_task.cancel()
            try:
                await self._escalation_task
            except asyncio.CancelledError:
                pass
            self._escalation_task = None
        
        # Stop performance monitoring
        if self._performance_monitoring_task:
            self._performance_monitoring_task.cancel()
            try:
                await self._performance_monitoring_task
            except asyncio.CancelledError:
                pass
            self._performance_monitoring_task = None
        
        # Stop error monitoring
        try:
            await self.error_monitoring.stop_monitoring()
        except Exception as e:
            self.logger.warning(f"Error stopping error monitoring: {e}")
        
        self.logger.info("Enhanced alerting system stopped")
    
    async def _escalation_loop(self):
        """Main escalation monitoring loop."""
        while self._system_active:
            try:
                await self._process_escalations()
                await self._correlate_alerts()
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in escalation loop: {e}")
                await asyncio.sleep(30)
    
    async def _performance_monitoring_loop(self):
        """Performance monitoring and alerting loop."""
        while self._system_active:
            try:
                if self.metrics_collector:
                    await self._evaluate_performance_thresholds()
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in performance monitoring loop: {e}")
                await asyncio.sleep(60)
    
    async def _process_escalations(self):
        """Process alert escalations."""
        current_time = datetime.now()
        
        # Get active alerts from the base alerting service
        active_alerts = self.alerting_service.get_active_alerts()
        
        for alert in active_alerts:
            # Check if alert should be escalated
            escalation_rule = self._find_escalation_rule(alert)
            if not escalation_rule:
                continue
            
            # Check if alert is already being escalated
            escalated_alert = None
            with self._lock:
                for esc_alert in self._escalated_alerts.values():
                    if esc_alert.original_alert.alert_id == alert.alert_id:
                        escalated_alert = esc_alert
                        break
            
            if not escalated_alert:
                # Create new escalated alert
                escalated_alert = EscalatedAlert(
                    alert_id=str(uuid4()),
                    original_alert=alert,
                    escalation_rule=escalation_rule,
                    current_level=EscalationLevel.LEVEL_1
                )
                
                with self._lock:
                    self._escalated_alerts[escalated_alert.alert_id] = escalated_alert
                
                # Send initial notifications
                await self._send_escalation_notifications(escalated_alert, EscalationLevel.LEVEL_1)
                continue
            
            # Check if escalation is needed
            if escalated_alert.acknowledged and escalation_rule.require_acknowledgment:
                continue  # Don't escalate acknowledged alerts if required
            
            time_since_creation = (current_time - escalated_alert.created_at).total_seconds() / 60
            
            # Determine if escalation is needed
            should_escalate = False
            next_level = None
            
            if (escalated_alert.current_level == EscalationLevel.LEVEL_1 and 
                time_since_creation >= escalation_rule.level_1_duration_minutes):
                should_escalate = True
                next_level = EscalationLevel.LEVEL_2
            elif (escalated_alert.current_level == EscalationLevel.LEVEL_2 and 
                  time_since_creation >= escalation_rule.level_1_duration_minutes + escalation_rule.level_2_duration_minutes):
                should_escalate = True
                next_level = EscalationLevel.LEVEL_3
            elif (escalated_alert.current_level == EscalationLevel.LEVEL_3 and 
                  time_since_creation >= (escalation_rule.level_1_duration_minutes + 
                                        escalation_rule.level_2_duration_minutes + 
                                        escalation_rule.level_3_duration_minutes)):
                should_escalate = True
                next_level = EscalationLevel.LEVEL_4
            
            if should_escalate and next_level and escalation_rule.auto_escalate:
                if next_level.value <= escalation_rule.max_escalation_level.value:
                    await self._escalate_alert(escalated_alert, next_level)
    
    async def _evaluate_performance_thresholds(self):
        """Evaluate performance thresholds and trigger alerts."""
        if not self.metrics_collector:
            return
        
        # Get current metrics
        current_metrics = self.metrics_collector.get_real_time_metrics()
        
        for threshold_name, threshold in self._performance_thresholds.items():
            try:
                # Extract metric value from nested structure
                metric_value = self._extract_metric_value(current_metrics, threshold.metric_name)
                if metric_value is None:
                    continue
                
                # Store metric history
                self._performance_history[threshold.metric_name].append({
                    'timestamp': datetime.now(),
                    'value': metric_value
                })
                
                # Evaluate threshold
                violation = self._evaluate_threshold(metric_value, threshold)
                
                if violation:
                    self._threshold_violations[threshold.metric_name] += 1
                    
                    # Check if we have enough consecutive violations
                    if self._threshold_violations[threshold.metric_name] >= threshold.consecutive_violations:
                        await self._trigger_performance_alert(threshold, metric_value, current_metrics)
                        self._threshold_violations[threshold.metric_name] = 0  # Reset counter
                else:
                    # Reset violation counter on success
                    self._threshold_violations[threshold.metric_name] = 0
                    
            except Exception as e:
                self.logger.error(f"Error evaluating threshold {threshold_name}: {e}")
    
    def _extract_metric_value(self, metrics: Dict[str, Any], metric_name: str) -> Optional[float]:
        """Extract metric value from nested metrics structure."""
        try:
            # Handle nested metric paths
            if '.' in metric_name:
                parts = metric_name.split('.')
                value = metrics
                for part in parts:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        return None
                return float(value) if value is not None else None
            
            # Handle direct metric access
            if metric_name in metrics:
                return float(metrics[metric_name])
            
            # Handle common metric locations
            metric_locations = {
                'avg_response_time_ms': ['response_time_metrics', 'avg_response_time_ms'],
                'p95_response_time_ms': ['response_time_metrics', 'p95_response_time_ms'],
                'p99_response_time_ms': ['response_time_metrics', 'p99_response_time_ms'],
                'cpu_percent': ['resource_usage', 'cpu', 'percent'],
                'memory_percent': ['resource_usage', 'memory', 'percent'],
                'disk_percent': ['resource_usage', 'disk', 'percent'],
                'cache_hit_rate_percent': ['cache_metrics', 'hit_rate_percent'],
                'requests_per_minute': ['response_time_metrics', 'total_requests_5min'],
                'error_rate_percent': ['error_metrics', 'error_rate_percent']  # Would need to be added
            }
            
            if metric_name in metric_locations:
                path = metric_locations[metric_name]
                value = metrics
                for part in path:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        return None
                return float(value) if value is not None else None
            
            return None
            
        except (ValueError, TypeError, KeyError):
            return None
    
    def _evaluate_threshold(self, value: float, threshold: PerformanceThreshold) -> bool:
        """Evaluate if a threshold is violated."""
        if threshold.comparison == "greater_than":
            return value > threshold.threshold_value
        elif threshold.comparison == "less_than":
            return value < threshold.threshold_value
        elif threshold.comparison == "equals":
            return abs(value - threshold.threshold_value) < 0.001
        elif threshold.comparison == "greater_than_or_equal":
            return value >= threshold.threshold_value
        elif threshold.comparison == "less_than_or_equal":
            return value <= threshold.threshold_value
        else:
            return False
    
    async def _trigger_performance_alert(self, threshold: PerformanceThreshold, 
                                       current_value: float, metrics: Dict[str, Any]):
        """Trigger a performance-based alert."""
        alert_id = str(uuid4())
        
        message = (f"Performance threshold exceeded: {threshold.description}. "
                  f"Current value: {current_value:.2f}, Threshold: {threshold.threshold_value:.2f}")
        
        # Create alert through base alerting service
        alert = Alert(
            alert_id=alert_id,
            rule_id=f"performance_{threshold.metric_name}",
            rule_name=f"Performance Alert: {threshold.metric_name}",
            severity=threshold.severity,
            status=AlertStatus.ACTIVE,
            message=message,
            metric_value=current_value,
            threshold=threshold.threshold_value,
            triggered_at=datetime.now(),
            metadata={
                'category': threshold.category.value,
                'metric_name': threshold.metric_name,
                'evaluation_window_minutes': threshold.evaluation_window_minutes,
                'consecutive_violations': threshold.consecutive_violations,
                'full_metrics': metrics
            }
        )
        
        # Add to base alerting service
        self.alerting_service.active_alerts[alert_id] = alert
        self.alerting_service.alert_history.append(alert)
        
        self.logger.warning(f"Performance alert triggered: {message}")
    
    def _find_escalation_rule(self, alert: Alert) -> Optional[EscalationRule]:
        """Find the appropriate escalation rule for an alert."""
        # Determine alert category from metadata
        category = None
        if hasattr(alert, 'metadata') and alert.metadata:
            category_str = alert.metadata.get('category')
            if category_str:
                try:
                    category = AlertCategory(category_str)
                except ValueError:
                    pass
        
        # Find matching escalation rule
        with self._lock:
            for rule in self._escalation_rules.values():
                if not rule.enabled:
                    continue
                
                # Check severity threshold
                if alert.severity.value < rule.severity_threshold.value:
                    continue
                
                # Check category match
                if category and rule.category != category:
                    continue
                
                return rule
        
        return None
    
    async def _escalate_alert(self, escalated_alert: EscalatedAlert, next_level: EscalationLevel):
        """Escalate an alert to the next level."""
        escalated_alert.current_level = next_level
        
        # Record escalation in history
        escalation_entry = {
            'level': next_level.value,
            'escalated_at': datetime.now().isoformat(),
            'reason': 'Automatic escalation due to time threshold'
        }
        escalated_alert.escalation_history.append(escalation_entry)
        
        # Send escalation notifications
        await self._send_escalation_notifications(escalated_alert, next_level)
        
        self.logger.warning(
            f"Alert escalated to {next_level.value}: {escalated_alert.original_alert.rule_name}"
        )
    
    async def _send_escalation_notifications(self, escalated_alert: EscalatedAlert, 
                                           level: EscalationLevel):
        """Send notifications for an escalated alert."""
        rule = escalated_alert.escalation_rule
        
        # Get channels for this escalation level
        channels = []
        if level == EscalationLevel.LEVEL_1:
            channels = rule.level_1_channels
        elif level == EscalationLevel.LEVEL_2:
            channels = rule.level_2_channels
        elif level == EscalationLevel.LEVEL_3:
            channels = rule.level_3_channels
        elif level == EscalationLevel.LEVEL_4:
            channels = rule.level_4_channels
        
        # Send notifications through each channel
        for channel_id in channels:
            try:
                await self._send_external_notification(channel_id, escalated_alert, level)
            except Exception as e:
                self.logger.error(f"Failed to send notification via {channel_id}: {e}")
    
    async def _send_external_notification(self, channel_id: str, 
                                        escalated_alert: EscalatedAlert, 
                                        level: EscalationLevel):
        """Send notification through external channel."""
        if channel_id not in self._external_channels:
            self.logger.warning(f"Unknown notification channel: {channel_id}")
            return
        
        channel = self._external_channels[channel_id]
        if not channel["enabled"]:
            self.logger.debug(f"Channel {channel_id} is disabled")
            return
        
        alert = escalated_alert.original_alert
        
        # Prepare notification content
        subject = f"[{level.value.upper()}] {alert.rule_name}"
        message = f"""
ESCALATION LEVEL: {level.value.upper()}
Alert: {alert.rule_name}
Severity: {alert.severity.value.upper()}
Message: {alert.message}
Triggered: {alert.triggered_at}
Escalation Rule: {escalated_alert.escalation_rule.name}

Current Value: {alert.metric_value}
Threshold: {alert.threshold}

Alert ID: {alert.alert_id}
Escalated Alert ID: {escalated_alert.alert_id}
"""
        
        # Send through appropriate channel
        if channel["type"] == "email":
            await self._send_email_notification(channel["config"], subject, message)
        elif channel["type"] == "slack":
            await self._send_slack_notification(channel["config"], subject, message)
        elif channel["type"] == "pagerduty":
            await self._send_pagerduty_notification(channel["config"], alert, level)
        elif channel["type"] == "sms":
            await self._send_sms_notification(channel["config"], f"{subject}: {alert.message}")
        elif channel["type"] == "phone":
            await self._send_phone_notification(channel["config"], subject, message)
        else:
            self.logger.warning(f"Unknown channel type: {channel['type']}")
    
    async def _send_email_notification(self, config: Dict[str, Any], subject: str, message: str):
        """Send email notification."""
        try:
            if not config.get("username") or not config.get("password"):
                self.logger.warning("Email configuration incomplete")
                return
            
            msg = MIMEMultipart()
            msg['From'] = config.get("sender", config["username"])
            msg['To'] = ", ".join(config["recipients"])
            msg['Subject'] = subject
            
            msg.attach(MIMEText(message, 'plain'))
            
            # Send email (in a thread to avoid blocking)
            def send_email():
                try:
                    server = smtplib.SMTP(config["smtp_server"], config["smtp_port"])
                    server.starttls()
                    server.login(config["username"], config["password"])
                    server.send_message(msg)
                    server.quit()
                    self.logger.info(f"Email notification sent: {subject}")
                except Exception as e:
                    self.logger.error(f"Failed to send email: {e}")
            
            # Run in thread pool to avoid blocking
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                executor.submit(send_email)
                
        except Exception as e:
            self.logger.error(f"Email notification error: {e}")
    
    async def _send_slack_notification(self, config: Dict[str, Any], subject: str, message: str):
        """Send Slack notification."""
        try:
            if not config.get("webhook_url"):
                self.logger.warning("Slack webhook URL not configured")
                return
            
            payload = {
                "channel": config.get("channel", "#alerts"),
                "username": config.get("username", "AlertBot"),
                "icon_emoji": config.get("icon_emoji", ":warning:"),
                "text": f"*{subject}*\n```{message}```"
            }
            
            # Send webhook (in a thread to avoid blocking)
            def send_webhook():
                try:
                    response = requests.post(config["webhook_url"], json=payload, timeout=10)
                    if response.status_code == 200:
                        self.logger.info(f"Slack notification sent: {subject}")
                    else:
                        self.logger.error(f"Slack webhook failed: {response.status_code}")
                except Exception as e:
                    self.logger.error(f"Failed to send Slack notification: {e}")
            
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                executor.submit(send_webhook)
                
        except Exception as e:
            self.logger.error(f"Slack notification error: {e}")
    
    async def _send_pagerduty_notification(self, config: Dict[str, Any], alert: Alert, level: EscalationLevel):
        """Send PagerDuty notification."""
        try:
            if not config.get("integration_key"):
                self.logger.warning("PagerDuty integration key not configured")
                return
            
            payload = {
                "routing_key": config["integration_key"],
                "event_action": "trigger",
                "dedup_key": f"multimodal_librarian_{alert.alert_id}",
                "payload": {
                    "summary": f"[{level.value.upper()}] {alert.rule_name}",
                    "source": "multimodal-librarian",
                    "severity": "critical" if alert.severity == AlertSeverity.CRITICAL else "error",
                    "component": "alerting-system",
                    "group": "system-monitoring",
                    "class": alert.metadata.get('category', 'unknown') if alert.metadata else 'unknown',
                    "custom_details": {
                        "alert_id": alert.alert_id,
                        "metric_value": alert.metric_value,
                        "threshold": alert.threshold,
                        "triggered_at": alert.triggered_at.isoformat(),
                        "escalation_level": level.value
                    }
                }
            }
            
            def send_pagerduty():
                try:
                    response = requests.post(config["service_url"], json=payload, timeout=10)
                    if response.status_code == 202:
                        self.logger.info(f"PagerDuty notification sent: {alert.rule_name}")
                    else:
                        self.logger.error(f"PagerDuty API failed: {response.status_code}")
                except Exception as e:
                    self.logger.error(f"Failed to send PagerDuty notification: {e}")
            
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                executor.submit(send_pagerduty)
                
        except Exception as e:
            self.logger.error(f"PagerDuty notification error: {e}")
    
    async def _send_sms_notification(self, config: Dict[str, Any], message: str):
        """Send SMS notification (placeholder)."""
        # This would integrate with SMS services like Twilio or AWS SNS
        self.logger.info(f"SMS notification (placeholder): {message[:100]}...")
    
    async def _send_phone_notification(self, config: Dict[str, Any], subject: str, message: str):
        """Send phone notification (placeholder)."""
        # This would integrate with voice call services
        self.logger.info(f"Phone notification (placeholder): {subject}")
    
    async def _correlate_alerts(self):
        """Correlate related alerts to reduce noise."""
        active_alerts = self.alerting_service.get_active_alerts()
        
        # Simple correlation based on timing and categories
        correlation_window = timedelta(minutes=5)
        current_time = datetime.now()
        
        # Group alerts by category and time
        alert_groups = defaultdict(list)
        for alert in active_alerts:
            if hasattr(alert, 'metadata') and alert.metadata:
                category = alert.metadata.get('category', 'unknown')
                time_bucket = int(alert.triggered_at.timestamp() / 300) * 300  # 5-minute buckets
                alert_groups[f"{category}_{time_bucket}"].append(alert)
        
        # Create correlations for groups with multiple alerts
        for group_key, alerts in alert_groups.items():
            if len(alerts) > 1:
                correlation_id = str(uuid4())
                
                # Find the most severe alert as root cause
                root_cause = max(alerts, key=lambda a: a.severity.value)
                
                correlation = AlertCorrelation(
                    correlation_id=correlation_id,
                    related_alerts=[a.alert_id for a in alerts],
                    root_cause_alert=root_cause.alert_id,
                    correlation_reason=f"Multiple {group_key.split('_')[0]} alerts within 5 minutes",
                    suppressed_alerts=[a.alert_id for a in alerts if a.alert_id != root_cause.alert_id]
                )
                
                with self._lock:
                    self._alert_correlations[correlation_id] = correlation
                
                self.logger.info(f"Correlated {len(alerts)} alerts: {correlation_id}")
    
    def acknowledge_escalated_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        """Acknowledge an escalated alert."""
        with self._lock:
            if alert_id in self._escalated_alerts:
                escalated_alert = self._escalated_alerts[alert_id]
                escalated_alert.acknowledged = True
                escalated_alert.acknowledged_by = acknowledged_by
                escalated_alert.acknowledged_at = datetime.now()
                
                # Also acknowledge the original alert
                self.alerting_service.acknowledge_alert(
                    escalated_alert.original_alert.alert_id, 
                    acknowledged_by
                )
                
                self.logger.info(f"Escalated alert acknowledged: {alert_id} by {acknowledged_by}")
                return True
        
        return False
    
    def resolve_escalated_alert(self, alert_id: str, reason: str = "Manual resolution") -> bool:
        """Resolve an escalated alert."""
        with self._lock:
            if alert_id in self._escalated_alerts:
                escalated_alert = self._escalated_alerts[alert_id]
                escalated_alert.resolved = True
                escalated_alert.resolved_at = datetime.now()
                
                # Also resolve the original alert
                self.alerting_service.resolve_alert(
                    escalated_alert.original_alert.alert_id, 
                    reason
                )
                
                # Remove from active escalations
                del self._escalated_alerts[alert_id]
                
                self.logger.info(f"Escalated alert resolved: {alert_id} - {reason}")
                return True
        
        return False
    
    def get_escalation_status(self) -> Dict[str, Any]:
        """Get comprehensive escalation system status."""
        with self._lock:
            active_escalations = len(self._escalated_alerts)
            critical_escalations = len([
                a for a in self._escalated_alerts.values()
                if a.original_alert.severity == AlertSeverity.CRITICAL
            ])
            
            # Escalation level distribution
            level_distribution = defaultdict(int)
            for escalated_alert in self._escalated_alerts.values():
                level_distribution[escalated_alert.current_level.value] += 1
            
            # Channel status
            enabled_channels = len([
                ch for ch in self._external_channels.values()
                if ch["enabled"]
            ])
            
            return {
                'system_active': self._system_active,
                'active_escalations': active_escalations,
                'critical_escalations': critical_escalations,
                'escalation_rules': len(self._escalation_rules),
                'performance_thresholds': len(self._performance_thresholds),
                'external_channels': len(self._external_channels),
                'enabled_channels': enabled_channels,
                'alert_correlations': len(self._alert_correlations),
                'escalation_level_distribution': dict(level_distribution),
                'performance_monitoring_enabled': self.metrics_collector is not None,
                'error_monitoring_enabled': self.error_monitoring is not None
            }
    
    def export_escalation_report(self, filepath: Optional[str] = None) -> str:
        """Export comprehensive escalation report."""
        if not filepath:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filepath = f"enhanced_alerting_report_{timestamp}.json"
        
        with self._lock:
            report_data = {
                'export_timestamp': datetime.now().isoformat(),
                'system_status': self.get_escalation_status(),
                'escalation_rules': {
                    rule_id: {
                        'name': rule.name,
                        'category': rule.category.value,
                        'severity_threshold': rule.severity_threshold.value,
                        'level_1_duration_minutes': rule.level_1_duration_minutes,
                        'level_2_duration_minutes': rule.level_2_duration_minutes,
                        'level_3_duration_minutes': rule.level_3_duration_minutes,
                        'auto_escalate': rule.auto_escalate,
                        'enabled': rule.enabled
                    }
                    for rule_id, rule in self._escalation_rules.items()
                },
                'performance_thresholds': {
                    threshold.metric_name: {
                        'threshold_value': threshold.threshold_value,
                        'comparison': threshold.comparison,
                        'severity': threshold.severity.value,
                        'evaluation_window_minutes': threshold.evaluation_window_minutes,
                        'consecutive_violations': threshold.consecutive_violations,
                        'description': threshold.description,
                        'category': threshold.category.value
                    }
                    for threshold in self._performance_thresholds.values()
                },
                'active_escalations': [
                    {
                        'alert_id': esc_alert.alert_id,
                        'original_alert_id': esc_alert.original_alert.alert_id,
                        'rule_name': esc_alert.escalation_rule.name,
                        'current_level': esc_alert.current_level.value,
                        'created_at': esc_alert.created_at.isoformat(),
                        'acknowledged': esc_alert.acknowledged,
                        'escalation_history': esc_alert.escalation_history
                    }
                    for esc_alert in self._escalated_alerts.values()
                ],
                'alert_correlations': [
                    {
                        'correlation_id': corr.correlation_id,
                        'related_alerts': corr.related_alerts,
                        'root_cause_alert': corr.root_cause_alert,
                        'correlation_reason': corr.correlation_reason,
                        'created_at': corr.created_at.isoformat(),
                        'suppressed_alerts': corr.suppressed_alerts
                    }
                    for corr in self._alert_correlations.values()
                ]
            }
        
        try:
            import os
            if filepath and os.path.dirname(filepath):
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            with open(filepath, 'w') as f:
                json.dump(report_data, f, indent=2, default=str)
            
            self.logger.info(f"Enhanced alerting report exported to {filepath}")
            return filepath
            
        except Exception as e:
            self.logger.error(f"Failed to export escalation report: {e}")
            raise


# Global enhanced alerting system instance
_enhanced_alerting_system = None


def get_enhanced_alerting_system() -> EnhancedAlertingSystem:
    """Get the global enhanced alerting system instance."""
    global _enhanced_alerting_system
    if _enhanced_alerting_system is None:
        _enhanced_alerting_system = EnhancedAlertingSystem()
    return _enhanced_alerting_system


# Convenience functions
async def start_enhanced_alerting():
    """Start the enhanced alerting system."""
    system = get_enhanced_alerting_system()
    await system.start_enhanced_alerting()


async def stop_enhanced_alerting():
    """Stop the enhanced alerting system."""
    system = get_enhanced_alerting_system()
    await system.stop_enhanced_alerting()


def configure_notification_channel(channel_id: str, config: Dict[str, Any]) -> bool:
    """Configure an external notification channel."""
    system = get_enhanced_alerting_system()
    return system.configure_external_channel(channel_id, config)