"""
Tests for Enhanced Alerting System

This module tests the enhanced alerting system including:
- Performance threshold monitoring and alerting
- Error rate monitoring with intelligent thresholds
- Multi-level escalation procedures
- External notification channel integration
- Alert correlation and noise reduction
- Comprehensive alerting analytics

Validates: Requirement 6.4 - Alerting system with performance alerts, error rate monitoring, and escalation procedures
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any

from src.multimodal_librarian.monitoring.enhanced_alerting_system import (
    EnhancedAlertingSystem, EscalationRule, PerformanceThreshold,
    AlertCategory, EscalationLevel, AlertSeverity, EscalatedAlert
)
from src.multimodal_librarian.monitoring.alerting_service import Alert, AlertStatus


class TestEnhancedAlertingSystem:
    """Test suite for the Enhanced Alerting System."""
    
    @pytest.fixture
    def enhanced_alerting_system(self):
        """Create an enhanced alerting system instance for testing."""
        with patch('src.multimodal_librarian.monitoring.enhanced_alerting_system.get_alerting_service'), \
             patch('src.multimodal_librarian.monitoring.enhanced_alerting_system.get_error_monitoring_system'):
            system = EnhancedAlertingSystem()
            return system
    
    @pytest.fixture
    def sample_escalation_rule(self):
        """Create a sample escalation rule for testing."""
        return EscalationRule(
            rule_id="test_performance",
            name="Test Performance Rule",
            category=AlertCategory.PERFORMANCE,
            severity_threshold=AlertSeverity.HIGH,
            level_1_duration_minutes=5,
            level_2_duration_minutes=15,
            level_3_duration_minutes=30,
            level_1_channels=["console"],
            level_2_channels=["console", "email"],
            level_3_channels=["console", "email", "slack"],
            auto_escalate=True,
            require_acknowledgment=True
        )
    
    @pytest.fixture
    def sample_performance_threshold(self):
        """Create a sample performance threshold for testing."""
        return PerformanceThreshold(
            metric_name="test_response_time",
            threshold_value=1000.0,
            comparison="greater_than",
            severity=AlertSeverity.HIGH,
            evaluation_window_minutes=5,
            consecutive_violations=2,
            description="Test response time threshold",
            category=AlertCategory.PERFORMANCE
        )
    
    @pytest.fixture
    def sample_alert(self):
        """Create a sample alert for testing."""
        return Alert(
            alert_id="test_alert_123",
            rule_id="test_rule",
            rule_name="Test Alert Rule",
            severity=AlertSeverity.HIGH,
            status=AlertStatus.ACTIVE,
            message="Test alert message",
            metric_value=1500.0,
            threshold=1000.0,
            triggered_at=datetime.now(),
            metadata={"category": "performance"}
        )
    
    def test_initialization(self, enhanced_alerting_system):
        """Test enhanced alerting system initialization."""
        system = enhanced_alerting_system
        
        # Check that default escalation rules are loaded
        assert len(system._escalation_rules) > 0
        assert "critical_performance" in system._escalation_rules
        assert "high_error_rate" in system._escalation_rules
        
        # Check that default performance thresholds are loaded
        assert len(system._performance_thresholds) > 0
        assert "avg_response_time_ms" in system._performance_thresholds
        assert "cpu_percent" in system._performance_thresholds
        
        # Check that external channels are initialized
        assert len(system._external_channels) > 0
        assert "email_ops" in system._external_channels
        assert "slack_alerts" in system._external_channels
        
        # Check initial state
        assert not system._system_active
        assert len(system._escalated_alerts) == 0
        assert len(system._alert_correlations) == 0
    
    def test_add_escalation_rule(self, enhanced_alerting_system, sample_escalation_rule):
        """Test adding escalation rules."""
        system = enhanced_alerting_system
        
        # Add escalation rule
        success = system.add_escalation_rule(sample_escalation_rule)
        assert success
        
        # Verify rule was added
        assert sample_escalation_rule.rule_id in system._escalation_rules
        stored_rule = system._escalation_rules[sample_escalation_rule.rule_id]
        assert stored_rule.name == sample_escalation_rule.name
        assert stored_rule.category == sample_escalation_rule.category
        assert stored_rule.severity_threshold == sample_escalation_rule.severity_threshold
    
    def test_add_performance_threshold(self, enhanced_alerting_system, sample_performance_threshold):
        """Test adding performance thresholds."""
        system = enhanced_alerting_system
        
        # Add performance threshold
        success = system.add_performance_threshold(sample_performance_threshold)
        assert success
        
        # Verify threshold was added
        assert sample_performance_threshold.metric_name in system._performance_thresholds
        stored_threshold = system._performance_thresholds[sample_performance_threshold.metric_name]
        assert stored_threshold.threshold_value == sample_performance_threshold.threshold_value
        assert stored_threshold.comparison == sample_performance_threshold.comparison
        assert stored_threshold.severity == sample_performance_threshold.severity
    
    def test_configure_external_channel(self, enhanced_alerting_system):
        """Test configuring external notification channels."""
        system = enhanced_alerting_system
        
        # Configure email channel
        email_config = {
            "smtp_server": "smtp.test.com",
            "smtp_port": 587,
            "username": "test@example.com",
            "password": "test_password",
            "recipients": ["admin@example.com"]
        }
        
        success = system.configure_external_channel("email_ops", email_config)
        assert success
        
        # Verify configuration
        channel = system._external_channels["email_ops"]
        assert channel["enabled"]
        assert channel["config"]["smtp_server"] == "smtp.test.com"
        assert channel["config"]["username"] == "test@example.com"
    
    def test_extract_metric_value(self, enhanced_alerting_system):
        """Test metric value extraction from nested structures."""
        system = enhanced_alerting_system
        
        # Test metrics structure
        metrics = {
            "response_time_metrics": {
                "avg_response_time_ms": 1200.5,
                "p95_response_time_ms": 2500.0
            },
            "resource_usage": {
                "cpu": {"percent": 85.2},
                "memory": {"percent": 78.5}
            },
            "cache_metrics": {
                "hit_rate_percent": 65.3
            }
        }
        
        # Test direct nested access
        assert system._extract_metric_value(metrics, "response_time_metrics.avg_response_time_ms") == 1200.5
        assert system._extract_metric_value(metrics, "resource_usage.cpu.percent") == 85.2
        
        # Test predefined metric locations
        assert system._extract_metric_value(metrics, "avg_response_time_ms") == 1200.5
        assert system._extract_metric_value(metrics, "cpu_percent") == 85.2
        assert system._extract_metric_value(metrics, "cache_hit_rate_percent") == 65.3
        
        # Test non-existent metrics
        assert system._extract_metric_value(metrics, "non_existent_metric") is None
        assert system._extract_metric_value(metrics, "response_time_metrics.non_existent") is None
    
    def test_evaluate_threshold(self, enhanced_alerting_system, sample_performance_threshold):
        """Test threshold evaluation logic."""
        system = enhanced_alerting_system
        
        # Test greater_than comparison
        threshold = sample_performance_threshold  # threshold_value = 1000.0, comparison = "greater_than"
        assert system._evaluate_threshold(1500.0, threshold) == True  # Violation
        assert system._evaluate_threshold(800.0, threshold) == False  # No violation
        assert system._evaluate_threshold(1000.0, threshold) == False  # Exactly at threshold
        
        # Test less_than comparison
        threshold.comparison = "less_than"
        assert system._evaluate_threshold(500.0, threshold) == True  # Violation
        assert system._evaluate_threshold(1200.0, threshold) == False  # No violation
        
        # Test equals comparison
        threshold.comparison = "equals"
        assert system._evaluate_threshold(1000.0, threshold) == True  # Match
        assert system._evaluate_threshold(1000.001, threshold) == False  # Close but not equal
    
    @pytest.mark.asyncio
    async def test_start_stop_enhanced_alerting(self, enhanced_alerting_system):
        """Test starting and stopping the enhanced alerting system."""
        system = enhanced_alerting_system
        
        # Mock the error monitoring system
        system.error_monitoring = Mock()
        system.error_monitoring.start_monitoring = AsyncMock()
        system.error_monitoring.stop_monitoring = AsyncMock()
        
        # Test starting
        await system.start_enhanced_alerting()
        assert system._system_active
        assert system._escalation_task is not None
        
        # Test stopping
        await system.stop_enhanced_alerting()
        assert not system._system_active
        assert system._escalation_task is None
    
    def test_find_escalation_rule(self, enhanced_alerting_system, sample_escalation_rule, sample_alert):
        """Test finding appropriate escalation rules for alerts."""
        system = enhanced_alerting_system
        
        # Add escalation rule
        system.add_escalation_rule(sample_escalation_rule)
        
        # Test finding rule for matching alert
        rule = system._find_escalation_rule(sample_alert)
        assert rule is not None
        assert rule.rule_id == sample_escalation_rule.rule_id
        
        # Test with alert that doesn't match severity threshold
        low_severity_alert = sample_alert
        low_severity_alert.severity = AlertSeverity.LOW
        rule = system._find_escalation_rule(low_severity_alert)
        assert rule is None  # Should not match because severity is too low
    
    @pytest.mark.asyncio
    async def test_trigger_performance_alert(self, enhanced_alerting_system, sample_performance_threshold):
        """Test triggering performance-based alerts."""
        system = enhanced_alerting_system
        
        # Mock the base alerting service
        system.alerting_service.active_alerts = {}
        system.alerting_service.alert_history = []
        
        # Add performance threshold
        system.add_performance_threshold(sample_performance_threshold)
        
        # Mock metrics
        current_metrics = {
            "response_time_metrics": {"avg_response_time_ms": 1500.0},
            "timestamp": datetime.now().isoformat()
        }
        
        # Trigger performance alert
        await system._trigger_performance_alert(
            sample_performance_threshold, 
            1500.0, 
            current_metrics
        )
        
        # Verify alert was created
        assert len(system.alerting_service.active_alerts) == 1
        assert len(system.alerting_service.alert_history) == 1
        
        # Check alert details
        alert = list(system.alerting_service.active_alerts.values())[0]
        assert alert.severity == sample_performance_threshold.severity
        assert alert.metric_value == 1500.0
        assert alert.threshold == sample_performance_threshold.threshold_value
        assert "Performance threshold exceeded" in alert.message
    
    @pytest.mark.asyncio
    async def test_escalation_process(self, enhanced_alerting_system, sample_escalation_rule, sample_alert):
        """Test the alert escalation process."""
        system = enhanced_alerting_system
        
        # Add escalation rule
        system.add_escalation_rule(sample_escalation_rule)
        
        # Mock external notification sending
        system._send_external_notification = AsyncMock()
        
        # Create escalated alert
        escalated_alert = EscalatedAlert(
            alert_id="esc_123",
            original_alert=sample_alert,
            escalation_rule=sample_escalation_rule,
            current_level=EscalationLevel.LEVEL_1
        )
        
        # Test escalation to level 2
        await system._escalate_alert(escalated_alert, EscalationLevel.LEVEL_2)
        
        # Verify escalation
        assert escalated_alert.current_level == EscalationLevel.LEVEL_2
        assert len(escalated_alert.escalation_history) == 1
        assert escalated_alert.escalation_history[0]["level"] == "level_2"
        
        # Verify notifications were sent
        assert system._send_external_notification.called
    
    def test_acknowledge_escalated_alert(self, enhanced_alerting_system, sample_escalation_rule, sample_alert):
        """Test acknowledging escalated alerts."""
        system = enhanced_alerting_system
        
        # Mock base alerting service
        system.alerting_service.acknowledge_alert = Mock(return_value=True)
        
        # Create escalated alert
        escalated_alert = EscalatedAlert(
            alert_id="esc_123",
            original_alert=sample_alert,
            escalation_rule=sample_escalation_rule,
            current_level=EscalationLevel.LEVEL_1
        )
        
        # Add to active escalations
        system._escalated_alerts[escalated_alert.alert_id] = escalated_alert
        
        # Acknowledge alert
        success = system.acknowledge_escalated_alert(escalated_alert.alert_id, "test_user")
        
        # Verify acknowledgment
        assert success
        assert escalated_alert.acknowledged
        assert escalated_alert.acknowledged_by == "test_user"
        assert escalated_alert.acknowledged_at is not None
        
        # Verify base alert was also acknowledged
        system.alerting_service.acknowledge_alert.assert_called_once_with(
            sample_alert.alert_id, "test_user"
        )
    
    def test_resolve_escalated_alert(self, enhanced_alerting_system, sample_escalation_rule, sample_alert):
        """Test resolving escalated alerts."""
        system = enhanced_alerting_system
        
        # Mock base alerting service
        system.alerting_service.resolve_alert = Mock(return_value=True)
        
        # Create escalated alert
        escalated_alert = EscalatedAlert(
            alert_id="esc_123",
            original_alert=sample_alert,
            escalation_rule=sample_escalation_rule,
            current_level=EscalationLevel.LEVEL_2
        )
        
        # Add to active escalations
        system._escalated_alerts[escalated_alert.alert_id] = escalated_alert
        
        # Resolve alert
        success = system.resolve_escalated_alert(escalated_alert.alert_id, "Issue fixed")
        
        # Verify resolution
        assert success
        assert escalated_alert.resolved
        assert escalated_alert.resolved_at is not None
        
        # Verify alert was removed from active escalations
        assert escalated_alert.alert_id not in system._escalated_alerts
        
        # Verify base alert was also resolved
        system.alerting_service.resolve_alert.assert_called_once_with(
            sample_alert.alert_id, "Issue fixed"
        )
    
    @pytest.mark.asyncio
    async def test_alert_correlation(self, enhanced_alerting_system):
        """Test alert correlation functionality."""
        system = enhanced_alerting_system
        
        # Create multiple related alerts
        alerts = []
        for i in range(3):
            alert = Alert(
                alert_id=f"alert_{i}",
                rule_id=f"rule_{i}",
                rule_name=f"Test Rule {i}",
                severity=AlertSeverity.HIGH,
                status=AlertStatus.ACTIVE,
                message=f"Test alert {i}",
                metric_value=100.0 + i,
                threshold=100.0,
                triggered_at=datetime.now(),
                metadata={"category": "performance"}
            )
            alerts.append(alert)
        
        # Mock the base alerting service to return these alerts
        system.alerting_service.get_active_alerts = Mock(return_value=alerts)
        
        # Run correlation
        await system._correlate_alerts()
        
        # Verify correlation was created
        assert len(system._alert_correlations) > 0
        
        # Check correlation details
        correlation = list(system._alert_correlations.values())[0]
        assert len(correlation.related_alerts) == 3
        assert correlation.root_cause_alert is not None
        assert len(correlation.suppressed_alerts) == 2  # All except root cause
    
    def test_get_escalation_status(self, enhanced_alerting_system, sample_escalation_rule, sample_alert):
        """Test getting escalation system status."""
        system = enhanced_alerting_system
        
        # Add some test data
        system.add_escalation_rule(sample_escalation_rule)
        
        escalated_alert = EscalatedAlert(
            alert_id="esc_123",
            original_alert=sample_alert,
            escalation_rule=sample_escalation_rule,
            current_level=EscalationLevel.LEVEL_2
        )
        system._escalated_alerts[escalated_alert.alert_id] = escalated_alert
        
        # Get status
        status = system.get_escalation_status()
        
        # Verify status information
        assert isinstance(status, dict)
        assert "system_active" in status
        assert "active_escalations" in status
        assert "escalation_rules" in status
        assert "performance_thresholds" in status
        assert "external_channels" in status
        
        assert status["active_escalations"] == 1
        assert status["escalation_rules"] > 0  # Default rules + added rule
        assert status["performance_thresholds"] > 0  # Default thresholds
    
    @pytest.mark.asyncio
    async def test_performance_monitoring_loop(self, enhanced_alerting_system):
        """Test the performance monitoring loop."""
        system = enhanced_alerting_system
        
        # Mock metrics collector
        mock_metrics_collector = Mock()
        mock_metrics_collector.get_real_time_metrics.return_value = {
            "response_time_metrics": {"avg_response_time_ms": 1500.0},
            "resource_usage": {"cpu": {"percent": 90.0}},
            "timestamp": datetime.now().isoformat()
        }
        system.metrics_collector = mock_metrics_collector
        
        # Mock alert triggering
        system._trigger_performance_alert = AsyncMock()
        
        # Add a threshold that will be violated
        threshold = PerformanceThreshold(
            metric_name="avg_response_time_ms",
            threshold_value=1000.0,
            comparison="greater_than",
            severity=AlertSeverity.HIGH,
            consecutive_violations=1  # Trigger immediately
        )
        system.add_performance_threshold(threshold)
        
        # Run one iteration of performance evaluation
        await system._evaluate_performance_thresholds()
        
        # Verify metrics were collected and threshold was evaluated
        mock_metrics_collector.get_real_time_metrics.assert_called_once()
        
        # Verify alert was triggered (threshold violated)
        system._trigger_performance_alert.assert_called_once()
    
    def test_export_escalation_report(self, enhanced_alerting_system, tmp_path):
        """Test exporting escalation reports."""
        system = enhanced_alerting_system
        
        # Create test file path
        test_file = tmp_path / "test_report.json"
        
        # Export report
        filepath = system.export_escalation_report(str(test_file))
        
        # Verify file was created
        assert test_file.exists()
        assert filepath == str(test_file)
        
        # Verify file contains valid JSON
        import json
        with open(test_file, 'r') as f:
            report_data = json.load(f)
        
        # Check report structure
        assert "export_timestamp" in report_data
        assert "system_status" in report_data
        assert "escalation_rules" in report_data
        assert "performance_thresholds" in report_data
        assert "active_escalations" in report_data
        assert "alert_correlations" in report_data
    
    @pytest.mark.asyncio
    async def test_external_notification_channels(self, enhanced_alerting_system, sample_escalation_rule, sample_alert):
        """Test external notification channel functionality."""
        system = enhanced_alerting_system
        
        # Configure email channel
        email_config = {
            "smtp_server": "smtp.test.com",
            "smtp_port": 587,
            "username": "test@example.com",
            "password": "test_password",
            "recipients": ["admin@example.com"]
        }
        system.configure_external_channel("email_ops", email_config)
        
        # Create escalated alert
        escalated_alert = EscalatedAlert(
            alert_id="esc_123",
            original_alert=sample_alert,
            escalation_rule=sample_escalation_rule,
            current_level=EscalationLevel.LEVEL_1
        )
        
        # Mock email sending
        with patch('smtplib.SMTP') as mock_smtp:
            mock_server = Mock()
            mock_smtp.return_value = mock_server
            
            # Test email notification
            await system._send_email_notification(
                system._external_channels["email_ops"]["config"],
                "Test Alert",
                "Test message"
            )
            
            # Give time for background thread to execute
            await asyncio.sleep(0.1)
    
    def test_threshold_violation_tracking(self, enhanced_alerting_system, sample_performance_threshold):
        """Test threshold violation tracking and consecutive violation logic."""
        system = enhanced_alerting_system
        
        # Add threshold with consecutive violations = 3
        sample_performance_threshold.consecutive_violations = 3
        system.add_performance_threshold(sample_performance_threshold)
        
        metric_name = sample_performance_threshold.metric_name
        
        # Simulate violations
        assert system._threshold_violations[metric_name] == 0
        
        # First violation
        violation = system._evaluate_threshold(1500.0, sample_performance_threshold)
        assert violation
        system._threshold_violations[metric_name] += 1
        assert system._threshold_violations[metric_name] == 1
        
        # Second violation
        system._threshold_violations[metric_name] += 1
        assert system._threshold_violations[metric_name] == 2
        
        # Third violation - should trigger alert
        system._threshold_violations[metric_name] += 1
        assert system._threshold_violations[metric_name] == 3
        
        # Reset on non-violation
        no_violation = system._evaluate_threshold(500.0, sample_performance_threshold)
        assert not no_violation
        system._threshold_violations[metric_name] = 0
        assert system._threshold_violations[metric_name] == 0


class TestEnhancedAlertingIntegration:
    """Integration tests for the Enhanced Alerting System."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_escalation_flow(self):
        """Test complete end-to-end escalation flow."""
        with patch('src.multimodal_librarian.monitoring.enhanced_alerting_system.get_alerting_service'), \
             patch('src.multimodal_librarian.monitoring.enhanced_alerting_system.get_error_monitoring_system'):
            
            system = EnhancedAlertingSystem()
            
            # Configure system
            escalation_rule = EscalationRule(
                rule_id="test_e2e",
                name="End-to-End Test Rule",
                category=AlertCategory.PERFORMANCE,
                severity_threshold=AlertSeverity.HIGH,
                level_1_duration_minutes=1,  # Short duration for testing
                level_2_duration_minutes=2,
                level_3_duration_minutes=3,
                level_1_channels=["console"],
                level_2_channels=["console"],
                level_3_channels=["console"],
                auto_escalate=True,
                require_acknowledgment=False
            )
            system.add_escalation_rule(escalation_rule)
            
            # Create high-severity alert
            alert = Alert(
                alert_id="e2e_alert",
                rule_id="e2e_rule",
                rule_name="End-to-End Test Alert",
                severity=AlertSeverity.HIGH,
                status=AlertStatus.ACTIVE,
                message="End-to-end test alert",
                metric_value=2000.0,
                threshold=1000.0,
                triggered_at=datetime.now(),
                metadata={"category": "performance"}
            )
            
            # Mock base alerting service
            system.alerting_service.get_active_alerts = Mock(return_value=[alert])
            system._send_external_notification = AsyncMock()
            
            # Process escalation (simulate finding the alert)
            await system._process_escalations()
            
            # Verify escalated alert was created
            assert len(system._escalated_alerts) == 1
            escalated_alert = list(system._escalated_alerts.values())[0]
            assert escalated_alert.original_alert.alert_id == alert.alert_id
            assert escalated_alert.current_level == EscalationLevel.LEVEL_1
            
            # Verify notification was sent
            system._send_external_notification.assert_called()
    
    @pytest.mark.asyncio
    async def test_performance_threshold_integration(self):
        """Test integration between performance monitoring and alerting."""
        with patch('src.multimodal_librarian.monitoring.enhanced_alerting_system.get_alerting_service'), \
             patch('src.multimodal_librarian.monitoring.enhanced_alerting_system.get_error_monitoring_system'):
            
            system = EnhancedAlertingSystem()
            
            # Mock metrics collector
            mock_metrics_collector = Mock()
            mock_metrics_collector.get_real_time_metrics.return_value = {
                "response_time_metrics": {"avg_response_time_ms": 1500.0},
                "resource_usage": {"cpu": {"percent": 95.0}},
                "cache_metrics": {"hit_rate_percent": 30.0}
            }
            system.metrics_collector = mock_metrics_collector
            
            # Mock base alerting service
            system.alerting_service.active_alerts = {}
            system.alerting_service.alert_history = []
            
            # Add performance thresholds
            thresholds = [
                PerformanceThreshold(
                    metric_name="avg_response_time_ms",
                    threshold_value=1000.0,
                    comparison="greater_than",
                    severity=AlertSeverity.HIGH,
                    consecutive_violations=1
                ),
                PerformanceThreshold(
                    metric_name="cpu_percent",
                    threshold_value=90.0,
                    comparison="greater_than",
                    severity=AlertSeverity.CRITICAL,
                    consecutive_violations=1
                ),
                PerformanceThreshold(
                    metric_name="cache_hit_rate_percent",
                    threshold_value=50.0,
                    comparison="less_than",
                    severity=AlertSeverity.MEDIUM,
                    consecutive_violations=1
                )
            ]
            
            for threshold in thresholds:
                system.add_performance_threshold(threshold)
            
            # Run performance evaluation
            await system._evaluate_performance_thresholds()
            
            # Verify alerts were created for violated thresholds
            assert len(system.alerting_service.active_alerts) == 3  # All thresholds violated
            
            # Check alert details
            alerts = list(system.alerting_service.active_alerts.values())
            severities = [alert.severity for alert in alerts]
            assert AlertSeverity.HIGH in severities
            assert AlertSeverity.CRITICAL in severities
            assert AlertSeverity.MEDIUM in severities


if __name__ == "__main__":
    pytest.main([__file__, "-v"])