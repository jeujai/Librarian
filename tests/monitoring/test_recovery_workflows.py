"""
Tests for Recovery Workflow System

Tests the complete recovery workflow system including:
- Recovery workflow manager
- Recovery notification service
- Recovery integration service
- API endpoints
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

from src.multimodal_librarian.monitoring.recovery_workflow_manager import (
    RecoveryWorkflowManager,
    RecoveryWorkflow,
    RecoveryAction,
    RecoveryStrategy,
    RecoveryPriority,
    RecoveryStatus,
    RecoveryAttempt
)
from src.multimodal_librarian.monitoring.recovery_notification_service import (
    RecoveryNotificationService,
    RecoveryNotificationType,
    RecoveryNotificationPriority,
    RecoveryNotification
)
from src.multimodal_librarian.monitoring.recovery_integration import (
    RecoveryIntegrationService,
    RecoveryTrigger
)
from src.multimodal_librarian.monitoring.service_health_monitor import HealthStatus
from src.multimodal_librarian.monitoring.error_logging_service import ErrorCategory


class TestRecoveryWorkflowManager:
    """Test recovery workflow manager functionality."""
    
    @pytest.fixture
    def recovery_manager(self):
        """Create recovery workflow manager for testing."""
        return RecoveryWorkflowManager()
    
    @pytest.fixture
    def mock_recovery_action(self):
        """Create mock recovery action."""
        async def mock_handler(service_name: str) -> bool:
            return True
        
        async def mock_validator(service_name: str) -> bool:
            return True
        
        return RecoveryAction(
            action_id="test_action",
            name="Test Action",
            description="Test recovery action",
            strategy=RecoveryStrategy.RESTART_SERVICE,
            handler=mock_handler,
            validation_checks=[mock_validator]
        )
    
    @pytest.fixture
    def mock_recovery_workflow(self, mock_recovery_action):
        """Create mock recovery workflow."""
        return RecoveryWorkflow(
            workflow_id="test_workflow",
            name="Test Workflow",
            description="Test recovery workflow",
            service_name="test_service",
            trigger_conditions={"consecutive_failures": 3},
            actions=[mock_recovery_action],
            priority=RecoveryPriority.MEDIUM
        )
    
    def test_workflow_registration(self, recovery_manager, mock_recovery_workflow):
        """Test workflow registration."""
        # Register workflow
        recovery_manager.register_workflow(mock_recovery_workflow)
        
        # Verify registration
        assert mock_recovery_workflow.workflow_id in recovery_manager._workflows
        assert "test_service" in recovery_manager._service_workflows
        assert mock_recovery_workflow.workflow_id in recovery_manager._service_workflows["test_service"]
    
    def test_workflow_unregistration(self, recovery_manager, mock_recovery_workflow):
        """Test workflow unregistration."""
        # Register and then unregister
        recovery_manager.register_workflow(mock_recovery_workflow)
        success = recovery_manager.unregister_workflow(mock_recovery_workflow.workflow_id)
        
        # Verify unregistration
        assert success
        assert mock_recovery_workflow.workflow_id not in recovery_manager._workflows
    
    @pytest.mark.asyncio
    async def test_trigger_recovery(self, recovery_manager, mock_recovery_workflow):
        """Test triggering recovery workflows."""
        # Register workflow
        recovery_manager.register_workflow(mock_recovery_workflow)
        
        # Trigger recovery
        attempt_ids = await recovery_manager.trigger_recovery(
            service_name="test_service",
            trigger_reason="Test trigger",
            health_status=HealthStatus.UNHEALTHY
        )
        
        # Verify attempt was created
        assert len(attempt_ids) == 1
        
        # Wait a bit for the workflow to start
        await asyncio.sleep(0.1)
        
        # Check if attempt is in active attempts or history (it might have completed quickly)
        attempt_id = attempt_ids[0]
        is_active = attempt_id in recovery_manager._active_attempts
        is_in_history = any(attempt.attempt_id == attempt_id for attempt in recovery_manager._attempt_history)
        
        assert is_active or is_in_history, f"Attempt {attempt_id} not found in active attempts or history"
    
    @pytest.mark.asyncio
    async def test_recovery_workflow_execution(self, recovery_manager, mock_recovery_workflow):
        """Test recovery workflow execution."""
        # Register workflow
        recovery_manager.register_workflow(mock_recovery_workflow)
        
        # Create recovery attempt
        attempt = RecoveryAttempt(
            attempt_id="test_attempt",
            workflow_id=mock_recovery_workflow.workflow_id,
            service_name="test_service",
            trigger_reason="Test execution",
            start_time=datetime.now()
        )
        
        # Execute workflow
        await recovery_manager._execute_recovery_workflow(mock_recovery_workflow, attempt)
        
        # Verify execution
        assert attempt.status in [RecoveryStatus.SUCCESS, RecoveryStatus.FAILED]
        assert len(attempt.actions_executed) > 0
        assert attempt.end_time is not None
    
    def test_recovery_statistics(self, recovery_manager, mock_recovery_workflow):
        """Test recovery statistics collection."""
        # Register workflow
        recovery_manager.register_workflow(mock_recovery_workflow)
        
        # Get statistics
        stats = recovery_manager.get_recovery_statistics()
        
        # Verify statistics structure
        assert "overall_statistics" in stats
        assert "workflow_statistics" in stats
        assert "total_attempts" in stats["overall_statistics"]
        assert "success_rate" in stats["overall_statistics"]
    
    def test_workflow_details(self, recovery_manager, mock_recovery_workflow):
        """Test getting workflow details."""
        # Register workflow
        recovery_manager.register_workflow(mock_recovery_workflow)
        
        # Get details
        details = recovery_manager.get_workflow_details(mock_recovery_workflow.workflow_id)
        
        # Verify details
        assert details is not None
        assert details["workflow_id"] == mock_recovery_workflow.workflow_id
        assert details["name"] == mock_recovery_workflow.name
        assert details["service_name"] == mock_recovery_workflow.service_name
        assert "actions" in details
        assert len(details["actions"]) == 1


class TestRecoveryNotificationService:
    """Test recovery notification service functionality."""
    
    @pytest.fixture
    def notification_service(self):
        """Create recovery notification service for testing."""
        return RecoveryNotificationService()
    
    @pytest.mark.asyncio
    async def test_send_recovery_notification(self, notification_service):
        """Test sending recovery notifications."""
        # Send notification
        notification_id = await notification_service.send_recovery_notification(
            notification_type=RecoveryNotificationType.RECOVERY_STARTED,
            service_name="test_service",
            workflow_id="test_workflow",
            attempt_id="test_attempt",
            title="Test Recovery Started",
            message="Test recovery workflow has started",
            priority=RecoveryNotificationPriority.MEDIUM
        )
        
        # Verify notification was created
        assert notification_id in notification_service._notifications
        notification = notification_service._notifications[notification_id]
        assert notification.title == "Test Recovery Started"
        assert notification.service_name == "test_service"
    
    @pytest.mark.asyncio
    async def test_acknowledge_notification(self, notification_service):
        """Test acknowledging notifications."""
        # Send notification that requires acknowledgment
        notification_id = await notification_service.send_recovery_notification(
            notification_type=RecoveryNotificationType.RECOVERY_FAILED,
            service_name="test_service",
            workflow_id="test_workflow",
            attempt_id="test_attempt",
            title="Test Recovery Failed",
            message="Test recovery workflow has failed",
            priority=RecoveryNotificationPriority.CRITICAL
        )
        
        # Acknowledge notification
        success = await notification_service.acknowledge_notification(
            notification_id=notification_id,
            acknowledged_by="test_user"
        )
        
        # Verify acknowledgment
        assert success
        notification = notification_service._notifications[notification_id]
        assert notification.acknowledged
        assert notification.acknowledged_by == "test_user"
    
    def test_get_active_notifications(self, notification_service):
        """Test getting active notifications."""
        # Create test notification
        notification = RecoveryNotification(
            notification_id="test_notification",
            notification_type=RecoveryNotificationType.RECOVERY_FAILED,
            priority=RecoveryNotificationPriority.HIGH,
            service_name="test_service",
            workflow_id="test_workflow",
            attempt_id="test_attempt",
            title="Test Notification",
            message="Test message",
            timestamp=datetime.now(),
            requires_acknowledgment=True
        )
        
        notification_service._notifications[notification.notification_id] = notification
        
        # Get active notifications
        active = notification_service.get_active_notifications()
        
        # Verify results
        assert len(active) == 1
        assert active[0]["notification_id"] == "test_notification"
    
    def test_notification_statistics(self, notification_service):
        """Test notification statistics."""
        # Get statistics
        stats = notification_service.get_notification_statistics()
        
        # Verify statistics structure
        assert "total_notifications" in stats
        assert "active_notifications" in stats
        assert "delivery_statistics" in stats
        assert "acknowledgment_statistics" in stats
        assert "escalation_statistics" in stats
    
    def test_cleanup_old_notifications(self, notification_service):
        """Test cleaning up old notifications."""
        # Create old notification
        old_notification = RecoveryNotification(
            notification_id="old_notification",
            notification_type=RecoveryNotificationType.RECOVERY_SUCCESS,
            priority=RecoveryNotificationPriority.LOW,
            service_name="test_service",
            workflow_id="test_workflow",
            attempt_id="test_attempt",
            title="Old Notification",
            message="Old message",
            timestamp=datetime.now() - timedelta(days=35),
            acknowledged=True
        )
        
        notification_service._notifications[old_notification.notification_id] = old_notification
        
        # Cleanup old notifications
        removed_count = notification_service.cleanup_old_notifications(days=30)
        
        # Verify cleanup
        assert removed_count == 1
        assert old_notification.notification_id not in notification_service._notifications


class TestRecoveryIntegrationService:
    """Test recovery integration service functionality."""
    
    @pytest.fixture
    def integration_service(self):
        """Create recovery integration service for testing."""
        with patch('src.multimodal_librarian.monitoring.recovery_integration.get_health_check_system'), \
             patch('src.multimodal_librarian.monitoring.recovery_integration.get_error_logging_service'), \
             patch('src.multimodal_librarian.monitoring.recovery_integration.get_recovery_workflow_manager'), \
             patch('src.multimodal_librarian.monitoring.recovery_integration.get_recovery_notification_service'):
            return RecoveryIntegrationService()
    
    def test_add_recovery_trigger(self, integration_service):
        """Test adding recovery triggers."""
        trigger = RecoveryTrigger(
            trigger_id="test_trigger",
            name="Test Trigger",
            description="Test recovery trigger",
            service_name="test_service",
            conditions={"consecutive_failures": 3},
            recovery_priority=RecoveryPriority.MEDIUM
        )
        
        # Add trigger
        success = integration_service.add_recovery_trigger(trigger)
        
        # Verify addition
        assert success
        assert trigger.trigger_id in integration_service._trigger_conditions
    
    def test_remove_recovery_trigger(self, integration_service):
        """Test removing recovery triggers."""
        trigger = RecoveryTrigger(
            trigger_id="test_trigger",
            name="Test Trigger",
            description="Test recovery trigger",
            service_name="test_service",
            conditions={"consecutive_failures": 3},
            recovery_priority=RecoveryPriority.MEDIUM
        )
        
        # Add and then remove trigger
        integration_service.add_recovery_trigger(trigger)
        success = integration_service.remove_recovery_trigger(trigger.trigger_id)
        
        # Verify removal
        assert success
        assert trigger.trigger_id not in integration_service._trigger_conditions
    
    @pytest.mark.asyncio
    async def test_handle_health_status_change(self, integration_service):
        """Test handling health status changes."""
        # Mock dependencies
        integration_service.recovery_workflow_manager = Mock()
        integration_service.recovery_workflow_manager.trigger_recovery = AsyncMock(return_value=["attempt_1"])
        
        integration_service.recovery_notification_service = Mock()
        integration_service.recovery_notification_service.send_recovery_notification = AsyncMock(return_value="notification_1")
        
        # Add trigger for test service
        trigger = RecoveryTrigger(
            trigger_id="test_trigger",
            name="Test Trigger",
            description="Test recovery trigger",
            service_name="test_service",
            conditions={"health_status": [HealthStatus.UNHEALTHY.value]},
            recovery_priority=RecoveryPriority.MEDIUM
        )
        integration_service.add_recovery_trigger(trigger)
        
        # Handle health status change
        await integration_service._handle_health_status_change("test_service", HealthStatus.UNHEALTHY)
        
        # Verify recovery was triggered
        integration_service.recovery_workflow_manager.trigger_recovery.assert_called_once()
    
    def test_integration_status(self, integration_service):
        """Test getting integration status."""
        # Get status
        status = integration_service.get_integration_status()
        
        # Verify status structure
        assert "integration_active" in status
        assert "registered_triggers" in status
        assert "active_cooldowns" in status
        assert "triggers" in status
        assert "cooldowns" in status
        assert "last_health_status" in status
    
    @pytest.mark.asyncio
    async def test_validate_recovery_success(self, integration_service):
        """Test validating recovery success."""
        # Mock health check system
        mock_health_report = Mock()
        mock_health_report.results = {
            "test_service": {"status": HealthStatus.HEALTHY.value}
        }
        
        integration_service.health_check_system = Mock()
        integration_service.health_check_system.run_all_checks = AsyncMock(return_value=mock_health_report)
        
        integration_service.recovery_notification_service = Mock()
        integration_service.recovery_notification_service.send_recovery_notification = AsyncMock(return_value="notification_1")
        
        # Validate recovery
        result = await integration_service.validate_recovery_success("test_service", "attempt_1")
        
        # Verify validation
        assert result is True
        integration_service.health_check_system.run_all_checks.assert_called_once()


class TestRecoveryWorkflowsAPI:
    """Test recovery workflows API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from src.multimodal_librarian.api.routers.recovery_workflows import router
        from fastapi import FastAPI
        
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)
    
    @patch('src.multimodal_librarian.api.routers.recovery_workflows.get_recovery_workflow_manager')
    def test_trigger_recovery_endpoint(self, mock_get_manager, client):
        """Test trigger recovery endpoint."""
        # Mock recovery manager
        mock_manager = Mock()
        mock_manager.trigger_recovery = AsyncMock(return_value=["attempt_1"])
        mock_get_manager.return_value = mock_manager
        
        # Make request
        response = client.post("/recovery/trigger", json={
            "service_name": "test_service",
            "reason": "Test trigger",
            "priority": "high"
        })
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "attempt_ids" in data
    
    @patch('src.multimodal_librarian.api.routers.recovery_workflows.get_recovery_workflow_manager')
    def test_get_active_attempts_endpoint(self, mock_get_manager, client):
        """Test get active attempts endpoint."""
        # Mock recovery manager
        mock_manager = Mock()
        mock_manager.get_active_attempts.return_value = [
            {
                "attempt_id": "attempt_1",
                "service_name": "test_service",
                "status": "in_progress"
            }
        ]
        mock_get_manager.return_value = mock_manager
        
        # Make request
        response = client.get("/recovery/attempts/active")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["attempt_id"] == "attempt_1"
    
    @patch('src.multimodal_librarian.api.routers.recovery_workflows.get_recovery_workflow_manager')
    def test_get_recovery_statistics_endpoint(self, mock_get_manager, client):
        """Test get recovery statistics endpoint."""
        # Mock recovery manager
        mock_manager = Mock()
        mock_manager.get_recovery_statistics.return_value = {
            "overall_statistics": {
                "total_attempts": 10,
                "successful_attempts": 8,
                "success_rate": 80.0
            }
        }
        mock_get_manager.return_value = mock_manager
        
        # Make request
        response = client.get("/recovery/statistics")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert "overall_statistics" in data
        assert data["overall_statistics"]["success_rate"] == 80.0
    
    @patch('src.multimodal_librarian.api.routers.recovery_workflows.get_recovery_notification_service')
    def test_acknowledge_notification_endpoint(self, mock_get_service, client):
        """Test acknowledge notification endpoint."""
        # Mock notification service
        mock_service = Mock()
        mock_service.acknowledge_notification = AsyncMock(return_value=True)
        mock_get_service.return_value = mock_service
        
        # Make request
        response = client.post("/recovery/notifications/test_notification/acknowledge", json={
            "acknowledged_by": "test_user"
        })
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["acknowledged_by"] == "test_user"
    
    @patch('src.multimodal_librarian.api.routers.recovery_workflows.get_recovery_integration_service')
    def test_get_integration_status_endpoint(self, mock_get_service, client):
        """Test get integration status endpoint."""
        # Mock integration service
        mock_service = Mock()
        mock_service.get_integration_status.return_value = {
            "integration_active": True,
            "registered_triggers": 5,
            "active_cooldowns": 2
        }
        mock_get_service.return_value = mock_service
        
        # Make request
        response = client.get("/recovery/integration/status")
        
        # Verify response
        assert response.status_code == 200
        data = response.json()
        assert data["integration_active"] is True
        assert data["registered_triggers"] == 5


# Integration tests
class TestRecoveryWorkflowIntegration:
    """Test complete recovery workflow integration."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_recovery_workflow(self):
        """Test complete end-to-end recovery workflow."""
        # This would test the complete flow from health status change
        # through recovery workflow execution to notification
        
        # Mock all dependencies
        with patch('src.multimodal_librarian.monitoring.recovery_integration.get_health_check_system'), \
             patch('src.multimodal_librarian.monitoring.recovery_integration.get_error_logging_service'), \
             patch('src.multimodal_librarian.monitoring.recovery_integration.get_recovery_workflow_manager'), \
             patch('src.multimodal_librarian.monitoring.recovery_integration.get_recovery_notification_service'):
            
            # Create integration service
            integration_service = RecoveryIntegrationService()
            
            # Mock workflow manager
            mock_workflow_manager = Mock()
            mock_workflow_manager.trigger_recovery = AsyncMock(return_value=["attempt_1"])
            integration_service.recovery_workflow_manager = mock_workflow_manager
            
            # Mock notification service
            mock_notification_service = Mock()
            mock_notification_service.send_recovery_notification = AsyncMock(return_value="notification_1")
            integration_service.recovery_notification_service = mock_notification_service
            
            # Add trigger
            trigger = RecoveryTrigger(
                trigger_id="test_trigger",
                name="Test Trigger",
                description="Test recovery trigger",
                service_name="test_service",
                conditions={"health_status": [HealthStatus.UNHEALTHY.value]},
                recovery_priority=RecoveryPriority.MEDIUM
            )
            integration_service.add_recovery_trigger(trigger)
            
            # Simulate health status change
            await integration_service._handle_health_status_change("test_service", HealthStatus.UNHEALTHY)
            
            # Verify complete workflow
            mock_workflow_manager.trigger_recovery.assert_called_once()
            mock_notification_service.send_recovery_notification.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__])