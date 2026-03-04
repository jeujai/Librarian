"""
Alerting Service - Comprehensive alerting and notification system

This service provides intelligent alerting capabilities for system health,
performance issues, cost monitoring, and user activity metrics.
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from uuid import uuid4

logger = logging.getLogger(__name__)

class AlertSeverity(Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class AlertStatus(Enum):
    """Alert status."""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"

@dataclass
class AlertRule:
    """Alert rule configuration."""
    rule_id: str
    name: str
    description: str
    metric_name: str
    condition: str  # e.g., "greater_than", "less_than", "equals"
    threshold: float
    severity: AlertSeverity
    evaluation_window: int  # seconds
    cooldown_period: int  # seconds
    enabled: bool = True
    tags: Dict[str, str] = None
    
    def __post_init__(self):
        if self.tags is None:
            self.tags = {}

@dataclass
class Alert:
    """Alert instance."""
    alert_id: str
    rule_id: str
    rule_name: str
    severity: AlertSeverity
    status: AlertStatus
    message: str
    metric_value: float
    threshold: float
    triggered_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

@dataclass
class NotificationChannel:
    """Notification channel configuration."""
    channel_id: str
    name: str
    type: str  # email, slack, webhook, sms
    config: Dict[str, Any]
    enabled: bool = True
    severity_filter: List[AlertSeverity] = None
    
    def __post_init__(self):
        if self.severity_filter is None:
            self.severity_filter = list(AlertSeverity)

class AlertingService:
    """
    Comprehensive alerting service for system monitoring.
    
    Provides intelligent alerting with configurable rules, notification channels,
    and alert management capabilities.
    """
    
    def __init__(self):
        self.alert_rules: Dict[str, AlertRule] = {}
        self.active_alerts: Dict[str, Alert] = {}
        self.alert_history: List[Alert] = []
        self.notification_channels: Dict[str, NotificationChannel] = {}
        self.metrics_cache: Dict[str, List[Dict[str, Any]]] = {}
        self.last_evaluation: Dict[str, datetime] = {}
        
        # Initialize default alert rules
        self._initialize_default_rules()
        
        # Initialize default notification channels
        self._initialize_default_channels()
        
        logger.info("Alerting service initialized")
    
    def _initialize_default_rules(self):
        """Initialize default alert rules for common scenarios."""
        
        # System health alerts
        self.add_alert_rule(AlertRule(
            rule_id="high_error_rate",
            name="High Error Rate",
            description="Error rate exceeds acceptable threshold",
            metric_name="error_rate",
            condition="greater_than",
            threshold=0.05,  # 5%
            severity=AlertSeverity.HIGH,
            evaluation_window=300,  # 5 minutes
            cooldown_period=900,    # 15 minutes
            tags={"category": "system_health", "component": "api"}
        ))
        
        self.add_alert_rule(AlertRule(
            rule_id="high_response_time",
            name="High Response Time",
            description="Average response time is too high",
            metric_name="avg_response_time",
            condition="greater_than",
            threshold=2000,  # 2 seconds
            severity=AlertSeverity.MEDIUM,
            evaluation_window=300,
            cooldown_period=600,
            tags={"category": "performance", "component": "api"}
        ))
        
        self.add_alert_rule(AlertRule(
            rule_id="low_disk_space",
            name="Low Disk Space",
            description="Available disk space is running low",
            metric_name="disk_usage_percent",
            condition="greater_than",
            threshold=85.0,  # 85%
            severity=AlertSeverity.HIGH,
            evaluation_window=60,
            cooldown_period=1800,
            tags={"category": "infrastructure", "component": "storage"}
        ))
        
        # Cost monitoring alerts
        self.add_alert_rule(AlertRule(
            rule_id="high_ai_costs",
            name="High AI API Costs",
            description="AI API costs are exceeding budget",
            metric_name="daily_ai_cost",
            condition="greater_than",
            threshold=50.0,  # $50 per day
            severity=AlertSeverity.MEDIUM,
            evaluation_window=3600,  # 1 hour
            cooldown_period=3600,
            tags={"category": "cost", "component": "ai_api"}
        ))
        
        # User activity alerts
        self.add_alert_rule(AlertRule(
            rule_id="low_user_activity",
            name="Low User Activity",
            description="User activity has dropped significantly",
            metric_name="active_users_hourly",
            condition="less_than",
            threshold=1.0,
            severity=AlertSeverity.LOW,
            evaluation_window=3600,
            cooldown_period=7200,
            tags={"category": "user_activity", "component": "engagement"}
        ))
        
        # Security alerts
        self.add_alert_rule(AlertRule(
            rule_id="failed_auth_attempts",
            name="High Failed Authentication Attempts",
            description="Unusual number of failed authentication attempts",
            metric_name="failed_auth_rate",
            condition="greater_than",
            threshold=10.0,  # 10 failures per minute
            severity=AlertSeverity.HIGH,
            evaluation_window=60,
            cooldown_period=300,
            tags={"category": "security", "component": "authentication"}
        ))
    
    def _initialize_default_channels(self):
        """Initialize default notification channels."""
        
        # Console logging channel (always available)
        self.add_notification_channel(NotificationChannel(
            channel_id="console",
            name="Console Logging",
            type="console",
            config={},
            severity_filter=[AlertSeverity.MEDIUM, AlertSeverity.HIGH, AlertSeverity.CRITICAL]
        ))
        
        # Email channel (placeholder - would need SMTP configuration)
        self.add_notification_channel(NotificationChannel(
            channel_id="email_admin",
            name="Admin Email",
            type="email",
            config={
                "smtp_server": "localhost",
                "smtp_port": 587,
                "username": "alerts@multimodal-librarian.com",
                "recipients": ["admin@multimodal-librarian.com"]
            },
            enabled=False,  # Disabled by default
            severity_filter=[AlertSeverity.HIGH, AlertSeverity.CRITICAL]
        ))
        
        # Webhook channel (for integration with external systems)
        self.add_notification_channel(NotificationChannel(
            channel_id="webhook_monitoring",
            name="Monitoring Webhook",
            type="webhook",
            config={
                "url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
                "method": "POST",
                "headers": {"Content-Type": "application/json"}
            },
            enabled=False,  # Disabled by default
            severity_filter=[AlertSeverity.HIGH, AlertSeverity.CRITICAL]
        ))
    
    def add_alert_rule(self, rule: AlertRule) -> bool:
        """Add or update an alert rule."""
        try:
            self.alert_rules[rule.rule_id] = rule
            logger.info(f"Added alert rule: {rule.name} ({rule.rule_id})")
            return True
        except Exception as e:
            logger.error(f"Failed to add alert rule {rule.rule_id}: {e}")
            return False
    
    def remove_alert_rule(self, rule_id: str) -> bool:
        """Remove an alert rule."""
        try:
            if rule_id in self.alert_rules:
                rule = self.alert_rules.pop(rule_id)
                logger.info(f"Removed alert rule: {rule.name} ({rule_id})")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to remove alert rule {rule_id}: {e}")
            return False
    
    def add_notification_channel(self, channel: NotificationChannel) -> bool:
        """Add or update a notification channel."""
        try:
            self.notification_channels[channel.channel_id] = channel
            logger.info(f"Added notification channel: {channel.name} ({channel.channel_id})")
            return True
        except Exception as e:
            logger.error(f"Failed to add notification channel {channel.channel_id}: {e}")
            return False
    
    def remove_notification_channel(self, channel_id: str) -> bool:
        """Remove a notification channel."""
        try:
            if channel_id in self.notification_channels:
                channel = self.notification_channels.pop(channel_id)
                logger.info(f"Removed notification channel: {channel.name} ({channel_id})")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to remove notification channel {channel_id}: {e}")
            return False
    
    def record_metric(self, metric_name: str, value: float, timestamp: Optional[datetime] = None, metadata: Optional[Dict[str, Any]] = None):
        """Record a metric value for alert evaluation."""
        if timestamp is None:
            timestamp = datetime.now()
        
        if metadata is None:
            metadata = {}
        
        if metric_name not in self.metrics_cache:
            self.metrics_cache[metric_name] = []
        
        metric_entry = {
            "value": value,
            "timestamp": timestamp,
            "metadata": metadata
        }
        
        self.metrics_cache[metric_name].append(metric_entry)
        
        # Keep only recent metrics (last 24 hours)
        cutoff_time = datetime.now() - timedelta(hours=24)
        self.metrics_cache[metric_name] = [
            entry for entry in self.metrics_cache[metric_name]
            if entry["timestamp"] > cutoff_time
        ]
    
    async def evaluate_alerts(self):
        """Evaluate all alert rules against current metrics."""
        current_time = datetime.now()
        
        for rule_id, rule in self.alert_rules.items():
            if not rule.enabled:
                continue
            
            # Check cooldown period
            last_eval = self.last_evaluation.get(rule_id)
            if last_eval and (current_time - last_eval).total_seconds() < rule.cooldown_period:
                continue
            
            try:
                await self._evaluate_rule(rule, current_time)
                self.last_evaluation[rule_id] = current_time
            except Exception as e:
                logger.error(f"Failed to evaluate alert rule {rule_id}: {e}")
    
    async def _evaluate_rule(self, rule: AlertRule, current_time: datetime):
        """Evaluate a single alert rule."""
        metric_name = rule.metric_name
        
        if metric_name not in self.metrics_cache:
            return
        
        # Get metrics within evaluation window
        window_start = current_time - timedelta(seconds=rule.evaluation_window)
        recent_metrics = [
            entry for entry in self.metrics_cache[metric_name]
            if entry["timestamp"] >= window_start
        ]
        
        if not recent_metrics:
            return
        
        # Calculate metric value (average for now)
        metric_value = sum(entry["value"] for entry in recent_metrics) / len(recent_metrics)
        
        # Evaluate condition
        should_alert = self._evaluate_condition(metric_value, rule.condition, rule.threshold)
        
        if should_alert:
            await self._trigger_alert(rule, metric_value, current_time)
        else:
            # Check if we should resolve any active alerts for this rule
            await self._check_alert_resolution(rule, metric_value, current_time)
    
    def _evaluate_condition(self, value: float, condition: str, threshold: float) -> bool:
        """Evaluate alert condition."""
        if condition == "greater_than":
            return value > threshold
        elif condition == "less_than":
            return value < threshold
        elif condition == "equals":
            return abs(value - threshold) < 0.001
        elif condition == "not_equals":
            return abs(value - threshold) >= 0.001
        elif condition == "greater_than_or_equal":
            return value >= threshold
        elif condition == "less_than_or_equal":
            return value <= threshold
        else:
            logger.warning(f"Unknown condition: {condition}")
            return False
    
    async def _trigger_alert(self, rule: AlertRule, metric_value: float, timestamp: datetime):
        """Trigger a new alert."""
        # Check if there's already an active alert for this rule
        existing_alert = None
        for alert in self.active_alerts.values():
            if alert.rule_id == rule.rule_id and alert.status == AlertStatus.ACTIVE:
                existing_alert = alert
                break
        
        if existing_alert:
            # Update existing alert
            existing_alert.metric_value = metric_value
            existing_alert.triggered_at = timestamp
            logger.debug(f"Updated existing alert: {rule.name}")
            return
        
        # Create new alert
        alert = Alert(
            alert_id=str(uuid4()),
            rule_id=rule.rule_id,
            rule_name=rule.name,
            severity=rule.severity,
            status=AlertStatus.ACTIVE,
            message=f"{rule.description}. Current value: {metric_value:.2f}, Threshold: {rule.threshold:.2f}",
            metric_value=metric_value,
            threshold=rule.threshold,
            triggered_at=timestamp,
            metadata={
                "rule_tags": rule.tags,
                "evaluation_window": rule.evaluation_window,
                "condition": rule.condition
            }
        )
        
        self.active_alerts[alert.alert_id] = alert
        self.alert_history.append(alert)
        
        logger.warning(f"Alert triggered: {alert.rule_name} - {alert.message}")
        
        # Send notifications
        await self._send_notifications(alert)
    
    async def _check_alert_resolution(self, rule: AlertRule, metric_value: float, timestamp: datetime):
        """Check if any active alerts for this rule should be resolved."""
        for alert in list(self.active_alerts.values()):
            if alert.rule_id == rule.rule_id and alert.status == AlertStatus.ACTIVE:
                # Check if condition is no longer met
                should_alert = self._evaluate_condition(metric_value, rule.condition, rule.threshold)
                if not should_alert:
                    await self._resolve_alert(alert.alert_id, timestamp, "Condition no longer met")
    
    async def _send_notifications(self, alert: Alert):
        """Send notifications for an alert."""
        for channel_id, channel in self.notification_channels.items():
            if not channel.enabled:
                continue
            
            if alert.severity not in channel.severity_filter:
                continue
            
            try:
                await self._send_notification(channel, alert)
            except Exception as e:
                logger.error(f"Failed to send notification via {channel_id}: {e}")
    
    async def _send_notification(self, channel: NotificationChannel, alert: Alert):
        """Send notification via specific channel."""
        if channel.type == "console":
            logger.warning(f"ALERT [{alert.severity.value.upper()}] {alert.rule_name}: {alert.message}")
        
        elif channel.type == "email":
            # Email notification (placeholder - would need actual SMTP implementation)
            logger.info(f"Would send email notification for alert: {alert.rule_name}")
        
        elif channel.type == "webhook":
            # Webhook notification (placeholder - would need HTTP client)
            logger.info(f"Would send webhook notification for alert: {alert.rule_name}")
        
        elif channel.type == "slack":
            # Slack notification (placeholder - would need Slack API)
            logger.info(f"Would send Slack notification for alert: {alert.rule_name}")
        
        else:
            logger.warning(f"Unknown notification channel type: {channel.type}")
    
    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str = "system") -> bool:
        """Acknowledge an alert."""
        try:
            if alert_id in self.active_alerts:
                alert = self.active_alerts[alert_id]
                alert.status = AlertStatus.ACKNOWLEDGED
                alert.acknowledged_at = datetime.now()
                alert.metadata["acknowledged_by"] = acknowledged_by
                
                logger.info(f"Alert acknowledged: {alert.rule_name} by {acknowledged_by}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to acknowledge alert {alert_id}: {e}")
            return False
    
    async def _resolve_alert(self, alert_id: str, timestamp: datetime, reason: str = "Manual resolution") -> bool:
        """Resolve an alert."""
        try:
            if alert_id in self.active_alerts:
                alert = self.active_alerts[alert_id]
                alert.status = AlertStatus.RESOLVED
                alert.resolved_at = timestamp
                alert.metadata["resolution_reason"] = reason
                
                # Remove from active alerts
                del self.active_alerts[alert_id]
                
                logger.info(f"Alert resolved: {alert.rule_name} - {reason}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to resolve alert {alert_id}: {e}")
            return False
    
    async def resolve_alert(self, alert_id: str, reason: str = "Manual resolution") -> bool:
        """Manually resolve an alert."""
        return await self._resolve_alert(alert_id, datetime.now(), reason)
    
    def get_active_alerts(self, severity_filter: Optional[List[AlertSeverity]] = None) -> List[Alert]:
        """Get all active alerts, optionally filtered by severity."""
        alerts = list(self.active_alerts.values())
        
        if severity_filter:
            alerts = [alert for alert in alerts if alert.severity in severity_filter]
        
        return sorted(alerts, key=lambda x: x.triggered_at, reverse=True)
    
    def get_alert_history(self, limit: int = 100, rule_id: Optional[str] = None) -> List[Alert]:
        """Get alert history."""
        history = self.alert_history
        
        if rule_id:
            history = [alert for alert in history if alert.rule_id == rule_id]
        
        return sorted(history, key=lambda x: x.triggered_at, reverse=True)[:limit]
    
    def get_alert_statistics(self) -> Dict[str, Any]:
        """Get alert statistics."""
        now = datetime.now()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        
        # Count alerts by time period
        alerts_24h = [a for a in self.alert_history if a.triggered_at >= last_24h]
        alerts_7d = [a for a in self.alert_history if a.triggered_at >= last_7d]
        
        # Count by severity
        severity_counts = {}
        for severity in AlertSeverity:
            severity_counts[severity.value] = len([
                a for a in alerts_24h if a.severity == severity
            ])
        
        # Count by status
        status_counts = {}
        for status in AlertStatus:
            status_counts[status.value] = len([
                a for a in self.alert_history if a.status == status
            ])
        
        # Top alerting rules
        rule_counts = {}
        for alert in alerts_7d:
            rule_counts[alert.rule_name] = rule_counts.get(alert.rule_name, 0) + 1
        
        top_rules = sorted(rule_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        
        return {
            "active_alerts": len(self.active_alerts),
            "total_rules": len(self.alert_rules),
            "enabled_rules": len([r for r in self.alert_rules.values() if r.enabled]),
            "notification_channels": len(self.notification_channels),
            "enabled_channels": len([c for c in self.notification_channels.values() if c.enabled]),
            "alerts_last_24h": len(alerts_24h),
            "alerts_last_7d": len(alerts_7d),
            "severity_distribution": severity_counts,
            "status_distribution": status_counts,
            "top_alerting_rules": top_rules,
            "metrics_tracked": len(self.metrics_cache),
            "last_evaluation": max(self.last_evaluation.values()) if self.last_evaluation else None
        }
    
    def get_service_status(self) -> Dict[str, Any]:
        """Get alerting service status."""
        return {
            "status": "active",
            "service": "alerting",
            "features": {
                "alert_rules": True,
                "notification_channels": True,
                "metric_recording": True,
                "alert_evaluation": True,
                "alert_management": True,
                "statistics": True
            },
            "statistics": self.get_alert_statistics(),
            "configuration": {
                "evaluation_enabled": True,
                "default_rules_loaded": True,
                "default_channels_loaded": True
            }
        }

# Global alerting service instance
_alerting_service_instance = None

def get_alerting_service() -> AlertingService:
    """Get the global alerting service instance."""
    global _alerting_service_instance
    if _alerting_service_instance is None:
        _alerting_service_instance = AlertingService()
    return _alerting_service_instance