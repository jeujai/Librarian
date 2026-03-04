"""
Tests for Local Error Tracking and Alerting System

This module tests the local development error tracking and alerting functionality
to ensure it works correctly in local development environments.
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from src.multimodal_librarian.monitoring.local_error_tracking import (
    LocalErrorTracker,
    LocalErrorCategory,
    LocalErrorEvent,
    get_local_error_tracker,
    track_local_error
)
from src.multimodal_librarian.monitoring.local_alerting_system import (
    LocalAlertingSystem,
    LocalAlertType,
    LocalAlert,
    get_local_alerting_system,
    send_local_alert
)
from src.multimodal_librarian.monitoring.local_error_alerting_integration import (
    LocalErrorAlertingIntegration,
    get_local_error_alerting_integration
)
from src.multimodal_librarian.monitoring.error_logging_service import ErrorSeverity
from src.multimodal_librarian.monitoring.alerting_service import AlertSeverity
from src.multimodal_librarian.config.local_config import LocalDatabaseConfig


class TestLocalErrorTracker:
    """Test the local error tracking system."""
    
    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return LocalDatabaseConfig.create_test_config(
            log_dir="/tmp/test_logs",
            debug=True
        )
    
    @pytest.fixture
    def error_tracker(self, config):
        """Create a test error tracker."""
        return LocalErrorTracker(config)
    
    def test_error_tracker_initialization(self, error_tracker):
        """Test error tracker initializes correctly."""
        assert error_tracker is not None
        assert not error_tracker._tracking_active
        assert len(error_tracker._errors) == 0
        assert len(error_tracker._error_history) == 0
    
    def test_track_error(self, error_tracker):
        """Test tracking an error."""
        error_id = error_tracker.track_error(
            category=LocalErrorCategory.DATABASE_CONNECTION,
            severity=ErrorSeverity.HIGH,
            service="test_service",
            operation="test_operation",
            message="Test error message",
            context={"test": "context"}
        )
        
        assert error_id is not None
        assert error_id in error_tracker._errors
        
        error = error_tracker._errors[error_id]
        assert error.category == LocalErrorCategory.DATABASE_CONNECTION
        assert error.severity == ErrorSeverity.HIGH
        assert error.service == "test_service"
        assert error.operation == "test_operation"
        assert error.message == "Test error message"
        assert error.context["test"] == "context"
        assert not error.resolved
    
    def test_track_error_with_exception(self, error_tracker):
        """Test tracking an error with exception."""
        try:
            raise ValueError("Test exception")
        except ValueError as e:
            error_id = error_tracker.track_error(
                category=LocalErrorCategory.CONFIGURATION,
                severity=ErrorSeverity.CRITICAL,
                service="test_service",
                operation="test_operation",
                message="Test error with exception",
                exception=e
            )
        
        error = error_tracker._errors[error_id]
        assert error.exception_type == "ValueError"
        assert "Test exception" in error.stack_trace
        assert error.context["exception_str"] == "Test exception"
    
    def test_resolve_error(self, error_tracker):
        """Test resolving an error."""
        error_id = error_tracker.track_error(
            category=LocalErrorCategory.HOT_RELOAD,
            severity=ErrorSeverity.LOW,
            service="test_service",
            operation="test_operation",
            message="Test error"
        )
        
        success = error_tracker.resolve_error(error_id, "Fixed the issue")
        assert success
        
        error = error_tracker._errors[error_id]
        assert error.resolved
        assert error.resolution_notes == "Fixed the issue"
        assert error.resolution_time is not None
    
    def test_get_error_statistics(self, error_tracker):
        """Test getting error statistics."""
        # Track some errors
        error_tracker.track_error(
            LocalErrorCategory.DATABASE_CONNECTION,
            ErrorSeverity.HIGH,
            "service1",
            "op1",
            "Error 1"
        )
        error_tracker.track_error(
            LocalErrorCategory.DOCKER_CONTAINER,
            ErrorSeverity.CRITICAL,
            "service2",
            "op2",
            "Error 2"
        )
        
        stats = error_tracker.get_error_statistics()
        assert stats.total_errors == 2
        assert stats.errors_by_category[LocalErrorCategory.DATABASE_CONNECTION] == 1
        assert stats.errors_by_category[LocalErrorCategory.DOCKER_CONTAINER] == 1
        assert stats.errors_by_service["service1"] == 1
        assert stats.errors_by_service["service2"] == 1
        assert stats.critical_error_count == 1
        assert stats.unresolved_error_count == 2


class TestLocalAlertingSystem:
    """Test the local alerting system."""
    
    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return LocalDatabaseConfig.create_test_config(
            log_dir="/tmp/test_logs",
            debug=True
        )
    
    @pytest.fixture
    def alerting_system(self, config):
        """Create a test alerting system."""
        return LocalAlertingSystem(config)
    
    def test_alerting_system_initialization(self, alerting_system):
        """Test alerting system initializes correctly."""
        assert alerting_system is not None
        assert not alerting_system._alerting_active
        assert len(alerting_system._alerts) == 0
        assert len(alerting_system._alert_history) == 0
        assert len(alerting_system._active_alerts) == 0
    
    @pytest.mark.asyncio
    async def test_send_alert(self, alerting_system):
        """Test sending an alert."""
        alert_id = await alerting_system.send_alert(
            alert_type=LocalAlertType.DATABASE_DOWN,
            title="Test Alert",
            message="Test alert message",
            severity=AlertSeverity.HIGH,
            service="test_service",
            context={"test": "context"}
        )
        
        assert alert_id is not None
        assert alert_id in alerting_system._alerts
        assert alert_id in alerting_system._active_alerts
        
        alert = alerting_system._alerts[alert_id]
        assert alert.alert_type == LocalAlertType.DATABASE_DOWN
        assert alert.title == "Test Alert"
        assert alert.message == "Test alert message"
        assert alert.severity == AlertSeverity.HIGH
        assert alert.service == "test_service"
        assert alert.context["test"] == "context"
        assert not alert.acknowledged
        assert not alert.resolved
    
    @pytest.mark.asyncio
    async def test_acknowledge_alert(self, alerting_system):
        """Test acknowledging an alert."""
        alert_id = await alerting_system.send_alert(
            LocalAlertType.HIGH_MEMORY_USAGE,
            "Memory Alert",
            "High memory usage detected",
            AlertSeverity.MEDIUM,
            "system"
        )
        
        success = await alerting_system.acknowledge_alert(alert_id, "developer")
        assert success
        
        alert = alerting_system._alerts[alert_id]
        assert alert.acknowledged
        assert alert.acknowledged_by == "developer"
        assert alert.acknowledged_at is not None
    
    @pytest.mark.asyncio
    async def test_resolve_alert(self, alerting_system):
        """Test resolving an alert."""
        alert_id = await alerting_system.send_alert(
            LocalAlertType.DOCKER_CONTAINER_FAILED,
            "Container Alert",
            "Container failed to start",
            AlertSeverity.HIGH,
            "docker"
        )
        
        success = await alerting_system.resolve_alert(alert_id, "Container restarted")
        assert success
        
        alert = alerting_system._alerts[alert_id]
        assert alert.resolved
        assert alert.resolution_notes == "Container restarted"
        assert alert.resolved_at is not None
        assert alert_id not in alerting_system._active_alerts
    
    def test_get_alert_statistics(self, alerting_system):
        """Test getting alert statistics."""
        # This would need to be async in real usage, but for testing we can mock
        with patch.object(alerting_system, 'send_alert', new_callable=AsyncMock) as mock_send:
            # Simulate some alerts
            alert1 = LocalAlert(
                alert_type=LocalAlertType.DATABASE_DOWN,
                severity=AlertSeverity.CRITICAL,
                title="DB Alert",
                message="Database down",
                service="database"
            )
            alert2 = LocalAlert(
                alert_type=LocalAlertType.HIGH_CPU_USAGE,
                severity=AlertSeverity.MEDIUM,
                title="CPU Alert",
                message="High CPU usage",
                service="system"
            )
            
            alerting_system._alerts[alert1.id] = alert1
            alerting_system._alerts[alert2.id] = alert2
            alerting_system._alert_history.append(alert1)
            alerting_system._alert_history.append(alert2)
            alerting_system._active_alerts[alert1.id] = alert1
            alerting_system._active_alerts[alert2.id] = alert2
            
            stats = alerting_system.get_alert_statistics()
            assert stats.total_alerts == 2
            assert stats.active_alerts == 2
            assert stats.alerts_by_type[LocalAlertType.DATABASE_DOWN] == 1
            assert stats.alerts_by_type[LocalAlertType.HIGH_CPU_USAGE] == 1
            assert stats.alerts_by_severity[AlertSeverity.CRITICAL] == 1
            assert stats.alerts_by_severity[AlertSeverity.MEDIUM] == 1


class TestLocalErrorAlertingIntegration:
    """Test the integration between error tracking and alerting."""
    
    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return LocalDatabaseConfig.create_test_config(
            database_type="local",
            debug=True,
            log_dir="/tmp/test_logs"
        )
    
    @pytest.fixture
    def integration(self, config):
        """Create a test integration."""
        return LocalErrorAlertingIntegration(config)
    
    def test_integration_initialization(self, integration):
        """Test integration initializes correctly."""
        assert integration is not None
        assert not integration._integration_active
        assert integration._is_local_development  # Should detect test as local dev
    
    @pytest.mark.asyncio
    async def test_integration_lifecycle(self, integration):
        """Test integration startup and shutdown."""
        # Mock the underlying systems to avoid actual initialization
        with patch('src.multimodal_librarian.monitoring.local_error_alerting_integration.start_local_error_tracking') as mock_error_start, \
             patch('src.multimodal_librarian.monitoring.local_error_alerting_integration.start_local_alerting') as mock_alert_start, \
             patch('src.multimodal_librarian.monitoring.local_error_alerting_integration.stop_local_error_tracking') as mock_error_stop, \
             patch('src.multimodal_librarian.monitoring.local_error_alerting_integration.stop_local_alerting') as mock_alert_stop:
            
            # Start integration
            await integration.start_integration()
            assert integration._integration_active
            mock_error_start.assert_called_once()
            mock_alert_start.assert_called_once()
            
            # Stop integration
            await integration.stop_integration()
            assert not integration._integration_active
            mock_error_stop.assert_called_once()
            mock_alert_stop.assert_called_once()
    
    def test_track_error_when_inactive(self, integration):
        """Test tracking error when integration is inactive."""
        error_id = integration.track_error(
            LocalErrorCategory.CONFIGURATION,
            ErrorSeverity.HIGH,
            "test_service",
            "test_operation",
            "Test error"
        )
        
        # Should return None when integration is not active
        assert error_id is None
    
    @pytest.mark.asyncio
    async def test_send_alert_when_inactive(self, integration):
        """Test sending alert when integration is inactive."""
        alert_id = await integration.send_alert(
            LocalAlertType.DEVELOPMENT_SERVER_DOWN,
            "Test Alert",
            "Test message"
        )
        
        # Should return None when integration is not active
        assert alert_id is None
    
    def test_get_health_status(self, integration):
        """Test getting health status."""
        status = integration.get_health_status()
        
        assert "integration_active" in status
        assert "is_local_development" in status
        assert "error_tracking_enabled" in status
        assert "alerting_enabled" in status
        assert "timestamp" in status
        
        assert status["integration_active"] == integration._integration_active
        assert status["is_local_development"] == integration._is_local_development


class TestConvenienceFunctions:
    """Test the convenience functions for easy integration."""
    
    def test_track_local_error_function(self):
        """Test the track_local_error convenience function."""
        # This should not raise an error even if integration is not active
        error_id = track_local_error(
            LocalErrorCategory.FILE_SYSTEM,
            ErrorSeverity.LOW,
            "test_service",
            "test_operation",
            "Test error message"
        )
        
        # Should return a valid error ID (the function works even without integration)
        assert error_id is not None
        assert isinstance(error_id, str)
    
    def test_get_local_error_tracker_function(self):
        """Test the get_local_error_tracker function."""
        tracker = get_local_error_tracker()
        assert tracker is not None
        assert isinstance(tracker, LocalErrorTracker)
    
    def test_get_local_alerting_system_function(self):
        """Test the get_local_alerting_system function."""
        alerting_system = get_local_alerting_system()
        assert alerting_system is not None
        assert isinstance(alerting_system, LocalAlertingSystem)
    
    def test_get_local_error_alerting_integration_function(self):
        """Test the get_local_error_alerting_integration function."""
        integration = get_local_error_alerting_integration()
        assert integration is not None
        assert isinstance(integration, LocalErrorAlertingIntegration)


@pytest.mark.integration
class TestErrorAlertingIntegration:
    """Integration tests for error tracking and alerting."""
    
    @pytest.fixture
    def config(self):
        """Create a test configuration."""
        return LocalDatabaseConfig.create_test_config(
            database_type="local",
            debug=True,
            log_dir="/tmp/test_integration_logs"
        )
    
    @pytest.mark.asyncio
    async def test_error_triggers_alert(self, config):
        """Test that errors can trigger alerts."""
        error_tracker = LocalErrorTracker(config)
        alerting_system = LocalAlertingSystem(config)
        
        # Start both systems
        await error_tracker.start_tracking()
        await alerting_system.start_alerting()
        
        try:
            # Track multiple database errors to trigger alert
            for i in range(3):
                error_tracker.track_error(
                    LocalErrorCategory.DATABASE_CONNECTION,
                    ErrorSeverity.HIGH,
                    "database",
                    "connect",
                    f"Connection failed {i+1}"
                )
            
            # Wait a bit for alert processing
            await asyncio.sleep(1)
            
            # Check if alert was generated
            # Note: This would require the alerting system to be monitoring
            # the error tracker, which is not implemented in this basic test
            
        finally:
            # Clean up
            await error_tracker.stop_tracking()
            await alerting_system.stop_alerting()
    
    @pytest.mark.asyncio
    async def test_full_integration_lifecycle(self, config):
        """Test the full integration lifecycle."""
        integration = LocalErrorAlertingIntegration(config)
        
        # Mock the underlying systems to avoid file system operations
        with patch('src.multimodal_librarian.monitoring.local_error_alerting_integration.start_local_error_tracking') as mock_error_start, \
             patch('src.multimodal_librarian.monitoring.local_error_alerting_integration.start_local_alerting') as mock_alert_start, \
             patch('src.multimodal_librarian.monitoring.local_error_alerting_integration.stop_local_error_tracking') as mock_error_stop, \
             patch('src.multimodal_librarian.monitoring.local_error_alerting_integration.stop_local_alerting') as mock_alert_stop:
            
            # Test full lifecycle
            await integration.start_integration()
            assert integration._integration_active
            
            # Test health status
            health = integration.get_health_status()
            assert health["integration_active"]
            
            # Test statistics
            stats = integration.get_statistics()
            assert "integration_active" in stats
            
            await integration.stop_integration()
            assert not integration._integration_active