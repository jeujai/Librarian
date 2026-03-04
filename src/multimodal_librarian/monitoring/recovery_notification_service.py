"""
Recovery Notification Service for recovery workflow notifications.

This module provides specialized notification capabilities for recovery workflows:
- Recovery attempt notifications
- Recovery status updates
- Recovery success/failure alerts
- Recovery escalation notifications
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import uuid

from ..config import get_settings
from ..logging_config import get_logger
from .alerting_service import get_alerting_service, AlertSeverity, AlertingService


class RecoveryNotificationType(Enum):
    """Recovery notification types."""
    RECOVERY_STARTED = "recovery_started"
    RECOVERY_PROGRESS = "recovery_progress"
    RECOVERY_SUCCESS = "recovery_success"
    RECOVERY_FAILED = "recovery_failed"
    RECOVERY_TIMEOUT = "recovery_timeout"
    RECOVERY_ESCALATION = "recovery_escalation"
    MANUAL_INTERVENTION_REQUIRED = "manual_intervention_required"


class RecoveryNotificationPriority(Enum):
    """Recovery notification priority levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    URGENT = "urgent"


@dataclass
class RecoveryNotification:
    """Recovery notification data structure."""
    notification_id: str
    notification_type: RecoveryNotificationType
    priority: RecoveryNotificationPriority
    service_name: str
    workflow_id: str
    attempt_id: str
    title: str
    message: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    channels_sent: List[str] = field(default_factory=list)
    delivery_status: Dict[str, str] = field(default_factory=dict)
    escalation_level: int = 0
    requires_acknowledgment: bool = False
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None


@dataclass
class RecoveryNotificationRule:
    """Recovery notification rule configuration."""
    rule_id: str
    name: str
    description: str
    notification_types: List[RecoveryNotificationType]
    service_patterns: List[str]  # Service name patterns (supports wildcards)
    priority_threshold: RecoveryNotificationPriority
    channels: List[str]  # Channel IDs to send notifications to
    escalation_rules: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    conditions: Dict[str, Any] = field(default_factory=dict)


class RecoveryNotificationService:
    """
    Specialized notification service for recovery workflows.
    
    Provides comprehensive notification capabilities for recovery operations
    including escalation, acknowledgment tracking, and delivery status monitoring.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.logger = get_logger("recovery_notification_service")
        self.alerting_service = get_alerting_service()
        
        # Notification storage
        self._notifications: Dict[str, RecoveryNotification] = {}
        self._notification_rules: Dict[str, RecoveryNotificationRule] = {}
        self._notification_history: List[RecoveryNotification] = []
        
        # Escalation tracking
        self._escalation_timers: Dict[str, asyncio.Task] = {}
        
        # Delivery tracking
        self._delivery_stats = {
            'total_sent': 0,
            'successful_deliveries': 0,
            'failed_deliveries': 0,
            'pending_deliveries': 0
        }
        
        # Initialize default notification rules
        self._initialize_default_rules()
        
        self.logger.info("Recovery notification service initialized")
    
    def _initialize_default_rules(self) -> None:
        """Initialize default notification rules for recovery workflows."""
        
        # Critical service recovery notifications
        self.add_notification_rule(RecoveryNotificationRule(
            rule_id="critical_service_recovery",
            name="Critical Service Recovery",
            description="Notifications for critical service recovery attempts",
            notification_types=[
                RecoveryNotificationType.RECOVERY_STARTED,
                RecoveryNotificationType.RECOVERY_SUCCESS,
                RecoveryNotificationType.RECOVERY_FAILED,
                RecoveryNotificationType.RECOVERY_TIMEOUT
            ],
            service_patterns=["database", "vector_store", "search_service"],
            priority_threshold=RecoveryNotificationPriority.HIGH,
            channels=["console", "email"],
            escalation_rules={
                "escalate_after_minutes": 15,
                "escalation_channels": ["slack", "sms"],
                "max_escalation_level": 3
            }
        ))
        
        # General service recovery notifications
        self.add_notification_rule(RecoveryNotificationRule(
            rule_id="general_service_recovery",
            name="General Service Recovery",
            description="Notifications for general service recovery attempts",
            notification_types=[
                RecoveryNotificationType.RECOVERY_FAILED,
                RecoveryNotificationType.MANUAL_INTERVENTION_REQUIRED
            ],
            service_patterns=["*"],  # All services
            priority_threshold=RecoveryNotificationPriority.MEDIUM,
            channels=["console"],
            escalation_rules={
                "escalate_after_minutes": 30,
                "escalation_channels": ["email"],
                "max_escalation_level": 2
            }
        ))
        
        # Manual intervention notifications
        self.add_notification_rule(RecoveryNotificationRule(
            rule_id="manual_intervention_required",
            name="Manual Intervention Required",
            description="Notifications when manual intervention is required",
            notification_types=[RecoveryNotificationType.MANUAL_INTERVENTION_REQUIRED],
            service_patterns=["*"],
            priority_threshold=RecoveryNotificationPriority.CRITICAL,
            channels=["console", "email", "slack"],
            escalation_rules={
                "escalate_after_minutes": 5,
                "escalation_channels": ["sms"],
                "max_escalation_level": 5
            }
        ))
    
    def add_notification_rule(self, rule: RecoveryNotificationRule) -> bool:
        """Add or update a notification rule."""
        try:
            self._notification_rules[rule.rule_id] = rule
            self.logger.info(f"Added recovery notification rule: {rule.name}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to add notification rule: {e}")
            return False
    
    def remove_notification_rule(self, rule_id: str) -> bool:
        """Remove a notification rule."""
        try:
            if rule_id in self._notification_rules:
                del self._notification_rules[rule_id]
                self.logger.info(f"Removed recovery notification rule: {rule_id}")
                return True
            return False
        except Exception as e:
            self.logger.error(f"Failed to remove notification rule: {e}")
            return False
    
    async def send_recovery_notification(
        self,
        notification_type: RecoveryNotificationType,
        service_name: str,
        workflow_id: str,
        attempt_id: str,
        title: str,
        message: str,
        priority: Optional[RecoveryNotificationPriority] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Send a recovery notification."""
        
        # Create notification
        notification = RecoveryNotification(
            notification_id=str(uuid.uuid4()),
            notification_type=notification_type,
            priority=priority or self._determine_priority(notification_type, service_name),
            service_name=service_name,
            workflow_id=workflow_id,
            attempt_id=attempt_id,
            title=title,
            message=message,
            timestamp=datetime.now(),
            metadata=metadata or {},
            requires_acknowledgment=self._requires_acknowledgment(notification_type, priority)
        )
        
        # Store notification
        self._notifications[notification.notification_id] = notification
        
        # Find applicable rules and send notifications
        applicable_rules = self._find_applicable_rules(notification)
        
        for rule in applicable_rules:
            await self._send_notification_via_rule(notification, rule)
        
        # Set up escalation if needed
        if notification.requires_acknowledgment:
            await self._setup_escalation(notification)
        
        # Update statistics
        self._delivery_stats['total_sent'] += 1
        
        self.logger.info(f"Sent recovery notification: {notification.title}")
        return notification.notification_id
    
    def _determine_priority(self, notification_type: RecoveryNotificationType, 
                          service_name: str) -> RecoveryNotificationPriority:
        """Determine notification priority based on type and service."""
        
        # Critical services get higher priority
        critical_services = ["database", "vector_store", "search_service"]
        is_critical_service = service_name in critical_services
        
        if notification_type == RecoveryNotificationType.MANUAL_INTERVENTION_REQUIRED:
            return RecoveryNotificationPriority.URGENT
        elif notification_type == RecoveryNotificationType.RECOVERY_FAILED:
            return RecoveryNotificationPriority.CRITICAL if is_critical_service else RecoveryNotificationPriority.HIGH
        elif notification_type == RecoveryNotificationType.RECOVERY_TIMEOUT:
            return RecoveryNotificationPriority.HIGH
        elif notification_type == RecoveryNotificationType.RECOVERY_STARTED:
            return RecoveryNotificationPriority.MEDIUM if is_critical_service else RecoveryNotificationPriority.LOW
        elif notification_type == RecoveryNotificationType.RECOVERY_SUCCESS:
            return RecoveryNotificationPriority.LOW
        else:
            return RecoveryNotificationPriority.MEDIUM
    
    def _requires_acknowledgment(self, notification_type: RecoveryNotificationType,
                               priority: Optional[RecoveryNotificationPriority]) -> bool:
        """Determine if notification requires acknowledgment."""
        
        if notification_type == RecoveryNotificationType.MANUAL_INTERVENTION_REQUIRED:
            return True
        
        if priority and priority in [RecoveryNotificationPriority.CRITICAL, RecoveryNotificationPriority.URGENT]:
            return True
        
        if notification_type in [RecoveryNotificationType.RECOVERY_FAILED, RecoveryNotificationType.RECOVERY_TIMEOUT]:
            return True
        
        return False
    
    def _find_applicable_rules(self, notification: RecoveryNotification) -> List[RecoveryNotificationRule]:
        """Find notification rules that apply to the given notification."""
        
        applicable_rules = []
        
        for rule in self._notification_rules.values():
            if not rule.enabled:
                continue
            
            # Check notification type
            if notification.notification_type not in rule.notification_types:
                continue
            
            # Check service pattern
            if not self._matches_service_pattern(notification.service_name, rule.service_patterns):
                continue
            
            # Check priority threshold
            if notification.priority.value < rule.priority_threshold.value:
                continue
            
            # Check additional conditions
            if not self._check_rule_conditions(notification, rule):
                continue
            
            applicable_rules.append(rule)
        
        return applicable_rules
    
    def _matches_service_pattern(self, service_name: str, patterns: List[str]) -> bool:
        """Check if service name matches any of the patterns."""
        import fnmatch
        
        for pattern in patterns:
            if fnmatch.fnmatch(service_name, pattern):
                return True
        
        return False
    
    def _check_rule_conditions(self, notification: RecoveryNotification, 
                             rule: RecoveryNotificationRule) -> bool:
        """Check if notification meets rule conditions."""
        
        if not rule.conditions:
            return True
        
        # Check metadata conditions
        if "metadata_conditions" in rule.conditions:
            metadata_conditions = rule.conditions["metadata_conditions"]
            for key, expected_value in metadata_conditions.items():
                if key not in notification.metadata or notification.metadata[key] != expected_value:
                    return False
        
        # Check time-based conditions
        if "time_conditions" in rule.conditions:
            time_conditions = rule.conditions["time_conditions"]
            current_hour = notification.timestamp.hour
            
            if "business_hours_only" in time_conditions and time_conditions["business_hours_only"]:
                if current_hour < 9 or current_hour > 17:  # Outside 9 AM - 5 PM
                    return False
        
        return True
    
    async def _send_notification_via_rule(self, notification: RecoveryNotification,
                                        rule: RecoveryNotificationRule) -> None:
        """Send notification via channels specified in rule."""
        
        for channel_id in rule.channels:
            try:
                # For now, just log the notification (console channel)
                if channel_id == "console":
                    self.logger.info(f"RECOVERY NOTIFICATION [{notification.priority.value.upper()}]: {notification.title}")
                    self.logger.info(f"Service: {notification.service_name}, Message: {notification.message}")
                
                # Track delivery
                notification.channels_sent.append(channel_id)
                notification.delivery_status[channel_id] = "sent"
                
                self._delivery_stats['successful_deliveries'] += 1
                
            except Exception as e:
                self.logger.error(f"Failed to send notification via {channel_id}: {e}")
                notification.delivery_status[channel_id] = f"failed: {str(e)}"
                self._delivery_stats['failed_deliveries'] += 1
    
    def _map_priority_to_severity(self, priority: RecoveryNotificationPriority) -> str:
        """Map recovery notification priority to alert severity."""
        mapping = {
            RecoveryNotificationPriority.LOW: "low",
            RecoveryNotificationPriority.MEDIUM: "medium",
            RecoveryNotificationPriority.HIGH: "high",
            RecoveryNotificationPriority.CRITICAL: "critical",
            RecoveryNotificationPriority.URGENT: "critical"
        }
        return mapping.get(priority, "medium")
    
    async def _setup_escalation(self, notification: RecoveryNotification) -> None:
        """Set up escalation timer for notification."""
        
        # Find escalation rules
        escalation_rules = []
        applicable_rules = self._find_applicable_rules(notification)
        
        for rule in applicable_rules:
            if rule.escalation_rules:
                escalation_rules.append(rule.escalation_rules)
        
        if not escalation_rules:
            return
        
        # Use the most aggressive escalation rule
        escalation_config = min(escalation_rules, key=lambda x: x.get("escalate_after_minutes", 60))
        
        escalate_after_seconds = escalation_config.get("escalate_after_minutes", 15) * 60
        
        # Create escalation task
        escalation_task = asyncio.create_task(
            self._escalation_timer(notification.notification_id, escalate_after_seconds)
        )
        
        self._escalation_timers[notification.notification_id] = escalation_task
    
    async def _escalation_timer(self, notification_id: str, delay_seconds: int) -> None:
        """Escalation timer task."""
        
        try:
            await asyncio.sleep(delay_seconds)
            
            # Check if notification was acknowledged
            notification = self._notifications.get(notification_id)
            if not notification or notification.acknowledged:
                return
            
            # Escalate notification
            await self._escalate_notification(notification)
            
        except asyncio.CancelledError:
            # Timer was cancelled (notification was acknowledged)
            pass
        except Exception as e:
            self.logger.error(f"Error in escalation timer: {e}")
    
    async def _escalate_notification(self, notification: RecoveryNotification) -> None:
        """Escalate a notification."""
        
        notification.escalation_level += 1
        
        # Find escalation rules
        applicable_rules = self._find_applicable_rules(notification)
        escalation_channels = set()
        max_escalation_level = 1
        
        for rule in applicable_rules:
            if rule.escalation_rules:
                escalation_channels.update(rule.escalation_rules.get("escalation_channels", []))
                max_escalation_level = max(max_escalation_level, 
                                         rule.escalation_rules.get("max_escalation_level", 1))
        
        # Check if we've reached max escalation level
        if notification.escalation_level > max_escalation_level:
            self.logger.warning(f"Max escalation level reached for notification: {notification.notification_id}")
            return
        
        # Send escalated notification
        escalated_title = f"[ESCALATED L{notification.escalation_level}] {notification.title}"
        escalated_message = f"ESCALATION LEVEL {notification.escalation_level}\n\n{notification.message}\n\nThis notification requires immediate attention."
        
        for channel_id in escalation_channels:
            try:
                # For now, just log the escalated notification
                if channel_id == "console":
                    self.logger.critical(f"ESCALATED RECOVERY NOTIFICATION L{notification.escalation_level}: {escalated_title}")
                    self.logger.critical(f"Service: {notification.service_name}, Message: {escalated_message}")
                
                notification.channels_sent.append(f"{channel_id}_escalated")
                notification.delivery_status[f"{channel_id}_escalated"] = "sent"
                
            except Exception as e:
                self.logger.error(f"Failed to send escalated notification via {channel_id}: {e}")
        
        # Set up next escalation if not at max level
        if notification.escalation_level < max_escalation_level:
            escalation_task = asyncio.create_task(
                self._escalation_timer(notification.notification_id, 15 * 60)  # 15 minutes
            )
            self._escalation_timers[notification.notification_id] = escalation_task
        
        self.logger.warning(f"Escalated notification to level {notification.escalation_level}: {notification.title}")
    
    async def acknowledge_notification(self, notification_id: str, 
                                     acknowledged_by: str) -> bool:
        """Acknowledge a recovery notification."""
        
        notification = self._notifications.get(notification_id)
        if not notification:
            return False
        
        if notification.acknowledged:
            self.logger.info(f"Notification already acknowledged: {notification_id}")
            return True
        
        # Mark as acknowledged
        notification.acknowledged = True
        notification.acknowledged_by = acknowledged_by
        notification.acknowledged_at = datetime.now()
        
        # Cancel escalation timer
        if notification_id in self._escalation_timers:
            self._escalation_timers[notification_id].cancel()
            del self._escalation_timers[notification_id]
        
        # Send acknowledgment notification
        await self.send_recovery_notification(
            notification_type=RecoveryNotificationType.RECOVERY_PROGRESS,
            service_name=notification.service_name,
            workflow_id=notification.workflow_id,
            attempt_id=notification.attempt_id,
            title=f"Acknowledged: {notification.title}",
            message=f"Recovery notification acknowledged by {acknowledged_by}",
            priority=RecoveryNotificationPriority.LOW,
            metadata={'acknowledged_notification_id': notification_id}
        )
        
        self.logger.info(f"Acknowledged recovery notification: {notification_id} by {acknowledged_by}")
        return True
    
    def get_active_notifications(self, service_name: Optional[str] = None,
                               priority_filter: Optional[List[RecoveryNotificationPriority]] = None) -> List[Dict[str, Any]]:
        """Get active recovery notifications."""
        
        notifications = []
        
        for notification in self._notifications.values():
            # Filter by service name
            if service_name and notification.service_name != service_name:
                continue
            
            # Filter by priority
            if priority_filter and notification.priority not in priority_filter:
                continue
            
            # Only include unacknowledged notifications that require acknowledgment
            if notification.requires_acknowledgment and not notification.acknowledged:
                notifications.append({
                    'notification_id': notification.notification_id,
                    'type': notification.notification_type.value,
                    'priority': notification.priority.value,
                    'service_name': notification.service_name,
                    'workflow_id': notification.workflow_id,
                    'attempt_id': notification.attempt_id,
                    'title': notification.title,
                    'message': notification.message,
                    'timestamp': notification.timestamp.isoformat(),
                    'escalation_level': notification.escalation_level,
                    'channels_sent': notification.channels_sent,
                    'delivery_status': notification.delivery_status,
                    'metadata': notification.metadata
                })
        
        return sorted(notifications, key=lambda x: x['timestamp'], reverse=True)
    
    def get_notification_history(self, hours: int = 24, 
                               service_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recovery notification history."""
        
        cutoff_time = datetime.now() - timedelta(hours=hours)
        notifications = []
        
        for notification in self._notifications.values():
            if notification.timestamp < cutoff_time:
                continue
            
            if service_name and notification.service_name != service_name:
                continue
            
            notifications.append({
                'notification_id': notification.notification_id,
                'type': notification.notification_type.value,
                'priority': notification.priority.value,
                'service_name': notification.service_name,
                'workflow_id': notification.workflow_id,
                'attempt_id': notification.attempt_id,
                'title': notification.title,
                'message': notification.message,
                'timestamp': notification.timestamp.isoformat(),
                'acknowledged': notification.acknowledged,
                'acknowledged_by': notification.acknowledged_by,
                'acknowledged_at': notification.acknowledged_at.isoformat() if notification.acknowledged_at else None,
                'escalation_level': notification.escalation_level,
                'channels_sent': notification.channels_sent,
                'delivery_status': notification.delivery_status
            })
        
        return sorted(notifications, key=lambda x: x['timestamp'], reverse=True)
    
    def get_notification_statistics(self) -> Dict[str, Any]:
        """Get recovery notification statistics."""
        
        now = datetime.now()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        
        # Count notifications by time period
        notifications_24h = [n for n in self._notifications.values() if n.timestamp >= last_24h]
        notifications_7d = [n for n in self._notifications.values() if n.timestamp >= last_7d]
        
        # Count by type
        type_counts = {}
        for notification_type in RecoveryNotificationType:
            type_counts[notification_type.value] = len([
                n for n in notifications_24h if n.notification_type == notification_type
            ])
        
        # Count by priority
        priority_counts = {}
        for priority in RecoveryNotificationPriority:
            priority_counts[priority.value] = len([
                n for n in notifications_24h if n.priority == priority
            ])
        
        # Count by service
        service_counts = {}
        for notification in notifications_24h:
            service_counts[notification.service_name] = service_counts.get(notification.service_name, 0) + 1
        
        # Acknowledgment statistics
        requiring_ack = [n for n in notifications_24h if n.requires_acknowledgment]
        acknowledged = [n for n in requiring_ack if n.acknowledged]
        
        return {
            'total_notifications': len(self._notifications),
            'active_notifications': len([n for n in self._notifications.values() 
                                       if n.requires_acknowledgment and not n.acknowledged]),
            'notifications_last_24h': len(notifications_24h),
            'notifications_last_7d': len(notifications_7d),
            'delivery_statistics': self._delivery_stats.copy(),
            'type_distribution_24h': type_counts,
            'priority_distribution_24h': priority_counts,
            'service_distribution_24h': service_counts,
            'acknowledgment_statistics': {
                'requiring_acknowledgment': len(requiring_ack),
                'acknowledged': len(acknowledged),
                'acknowledgment_rate': (len(acknowledged) / max(1, len(requiring_ack))) * 100,
                'pending_acknowledgment': len(requiring_ack) - len(acknowledged)
            },
            'escalation_statistics': {
                'active_escalations': len(self._escalation_timers),
                'notifications_escalated': len([n for n in notifications_24h if n.escalation_level > 0])
            }
        }
    
    def cleanup_old_notifications(self, days: int = 30) -> int:
        """Clean up old notifications."""
        
        cutoff_time = datetime.now() - timedelta(days=days)
        removed_count = 0
        
        # Move old notifications to history and remove from active storage
        notifications_to_remove = []
        
        for notification_id, notification in self._notifications.items():
            if notification.timestamp < cutoff_time and notification.acknowledged:
                notifications_to_remove.append(notification_id)
                self._notification_history.append(notification)
        
        for notification_id in notifications_to_remove:
            del self._notifications[notification_id]
            removed_count += 1
        
        # Limit history size
        if len(self._notification_history) > 10000:
            self._notification_history = self._notification_history[-10000:]
        
        self.logger.info(f"Cleaned up {removed_count} old recovery notifications")
        return removed_count


# Global recovery notification service instance
_recovery_notification_service = None


def get_recovery_notification_service() -> RecoveryNotificationService:
    """Get the global recovery notification service instance."""
    global _recovery_notification_service
    if _recovery_notification_service is None:
        _recovery_notification_service = RecoveryNotificationService()
    return _recovery_notification_service


# Convenience functions
async def send_recovery_notification(notification_type: RecoveryNotificationType,
                                   service_name: str, workflow_id: str, attempt_id: str,
                                   title: str, message: str, **kwargs) -> str:
    """Send a recovery notification."""
    return await get_recovery_notification_service().send_recovery_notification(
        notification_type, service_name, workflow_id, attempt_id, title, message, **kwargs
    )


async def acknowledge_recovery_notification(notification_id: str, acknowledged_by: str) -> bool:
    """Acknowledge a recovery notification."""
    return await get_recovery_notification_service().acknowledge_notification(
        notification_id, acknowledged_by
    )