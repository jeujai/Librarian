"""
Integration tests for the Error Monitoring System.

Tests the complete error monitoring workflow including:
- Real-time error tracking and rate monitoring
- Alert threshold configuration and triggering
- Integration with error logging and alerting services
- API endpoints and system status monitoring
"""

import asyncio
import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from typing import Dict, Any

from src.multimodal_librarian.monitoring.error_monitoring_system import (
    ErrorMonitoringSystem,
    ErrorThresholdConfig,
    get_error_monitoring_system,
    start_error_monitoring,
    stop_error_monitoring,
    record_operation_result
)
from src.multimodal_librarian.monitoring.error_logging_service import (
    ErrorCategory,
    ErrorSeverity
)
from src.multimodal_librarian.monitoring.alerting_service import AlertSeverity


class TestErrorMonitoringIntegration:
    """Integration tests for error monitoring system."""
    
    @pytest.fixture
    async def monitoring_system(self):
        """Create a fresh error monitoring system for testing."""
        # Create new instance to avoid global state issues
        system = ErrorMonitoringSystem()
        yield system
        
        # Cleanup
        if system._monitoring_active:
            await system.stop_monitoring()
    
    @pytest.fixture
    async def started_monitoring_system(self, monitoring_system):
        """Create and start a monitoring system."""
        await monitoring_system.start_monitoring()
        # Give it a moment to initialize
        await asyncio.sleep(0.1)
        yield monitoring_system
        await monitoring_system.stop_monitoring()
    
    @pytest.mark.asyncio
    async def test_monitoring_system_initialization(self, monitoring_system):
        """Test that monitoring system initializes correctly."""
        assert monitoring_system is not None
        assert not monitoring_system._monitoring_active
        assert len(monitoring_system._threshold_configs) > 0  # Default configs loaded
        assert len(monitoring_system._active_alerts) == 0
        
        # Check default threshold configs
        assert "api" in [config.service for config in monitoring_system._threshold_configs.values()]
        assert "database" in [config.service for config in monitoring_system._threshold_configs.values()]
        assert "*" in [config.service for config in monitoring_system._threshold_configs.values()]
    
    async def test_monitoring_system_start_stop(self, monitoring_system):
        """Test starting and stopping the monitoring system."""
        # Initially not active
        assert not monitoring_system._monitoring_active
        
        # Start monitoring
        await monitoring_system.start_monitoring()
        assert monitoring_system._monitoring_active
        assert monitoring_system._monitoring_task is not None
        
        # Stop monitoring
        await monitoring_system.stop_monitoring()
        assert not monitoring_system._monitoring_active
        assert monitoring_system._monitoring_task is None
    
    @pytest.mark.asyncio
    async def test_threshold_config_management(self, monitoring_system):
        """Test adding, updating, and removing threshold configurations."""
        # Add custom threshold config
        config = ErrorThresholdConfig(
            service="test_service",
            operation="test_operation",
            warning_rate=2.0,
            critical_rate=5.0,
            warning_percentage=1.0,
            critical_percentage=3.0
        )
        
        success = monitoring_system.add_threshold_config(config)
        assert success
        
        # Verify config was added
        found_config = monitoring_system._find_threshold_config("test_service", "test_operation")
        assert found_config is not None
        assert found_config.service == "test_service"
        assert found_config.operation == "test_operation"
        assert found_config.warning_rate == 2.0
        
        # Remove config
        success = monitoring_system.remove_threshold_config("test_service", "test_operation")
        assert success
        
        # Verify config was removed
        found_config = monitoring_system._find_threshold_config("test_service", "test_operation")
        # Should fall back to wildcard config
        assert found_config.service == "*"
    
    @pytest.mark.asyncio
    async def test_operation_recording(self, monitoring_system):
        """Test recording operations and calculating error rates."""
        service = "test_service"
        operation = "test_operation"
        
        # Record some successful operations
        for _ in range(5):
            monitoring_system.record_operation(service, operation, success=True)
        
        # Record some failed operations
        for _ in range(2):
            monitoring_system.record_operation(
                service, operation, success=False,
                error_category=ErrorCategory.SERVICE_FAILURE,
                error_severity=ErrorSeverity.MEDIUM
            )
        
        # Get error rate
        error_rate = monitoring_system.get_error_rate(service, operation, window_minutes=5)
        
        assert error_rate['service'] == service
        assert error_rate['operation'] == operation
        assert error_rate['total_operations'] == 7
        assert error_rate['total_errors'] == 2
        assert error_rate['total_successes'] == 5
        assert abs(error_rate['error_rate_percentage'] - 28.57) < 0.1  # 2/7 * 100
        assert abs(error_rate['errors_per_minute'] - 0.4) < 0.1  # 2/5
    
    @pytest.mark.asyncio
    async def test_system_error_metrics(self, monitoring_system):
        """Test system-wide error metrics calculation."""
        # Record operations for multiple services
        services = ["api", "database", "search"]
        
        for service in services:
            # Record successful operations
            for _ in range(5):
                monitoring_system.record_operation(service, "test_op", success=True)
            
            # Record failed operations (different amounts)
            error_count = {"api": 1, "database": 1, "search": 2}[service]
            for _ in range(error_count):
                monitoring_system.record_operation(service, "test_op", success=False)
        
        # Get system metrics
        metrics = monitoring_system.get_system_error_metrics(window_minutes=5)
        
        assert metrics.total_operations == 19  # 15 successes + 4 errors
        assert metrics.total_errors == 4
        assert abs(metrics.error_rate - 21.05) < 0.1  # 4/19 * 100
        assert len(metrics.errors_by_service) == 3
        assert metrics.errors_by_service["api"] == 1
        assert metrics.errors_by_service["database"] == 1
        assert metrics.errors_by_service["search"] == 2
    
    async def test_threshold_evaluation_and_alerting(self, monitoring_system):
        """Test that threshold violations trigger alerts."""
        # Add a sensitive threshold config
        config = ErrorThresholdConfig(
            service="test_service",
            warning_rate=1.0,      # 1 error per minute
            critical_rate=2.0,     # 2 errors per minute
            warning_percentage=10.0, # 10% error rate
            critical_percentage=20.0, # 20% error rate
            evaluation_window_minutes=1,
            cooldown_minutes=1
        )
        
        monitoring_system.add_threshold_config(config)
        
        # Start monitoring
        await monitoring_system.start_monitoring()
        
        # Record operations that exceed warning threshold
        for _ in range(8):  # 80% success rate
            monitoring_system.record_operation("test_service", "test_op", success=True)
        
        for _ in range(3):  # 3 errors in 1 minute = 3 errors/min, 27% error rate
            monitoring_system.record_operation("test_service", "test_op", success=False)
        
        # Wait for monitoring loop to evaluate
        await asyncio.sleep(1.5)
        
        # Check that alert was triggered
        active_alerts = monitoring_system.get_active_alerts()
        assert len(active_alerts) > 0
        
        # Find our alert
        test_alert = None
        for alert in active_alerts:
            if alert.threshold_config.service == "test_service":
                test_alert = alert
                break
        
        assert test_alert is not None
        assert test_alert.severity == AlertSeverity.CRITICAL  # Should be critical due to high rate
        assert "test_service" in test_alert.message
        
        await monitoring_system.stop_monitoring()
    
    async def test_alert_management(self, monitoring_system):
        """Test alert acknowledgment and resolution."""
        # Manually create an alert for testing
        from src.multimodal_librarian.monitoring.error_monitoring_system import ErrorAlert
        
        config = ErrorThresholdConfig(service="test_service")
        alert = ErrorAlert(
            alert_id="test_alert_123",
            threshold_config=config,
            triggered_at=datetime.now(),
            current_rate=5.0,
            current_percentage=15.0,
            threshold_exceeded="warning_rate",
            severity=AlertSeverity.HIGH,
            message="Test alert message"
        )
        
        # Add alert to active alerts
        monitoring_system._active_alerts[alert.alert_id] = alert
        
        # Test acknowledgment
        success = monitoring_system.acknowledge_alert(alert.alert_id)
        assert success
        assert alert.metadata.get('acknowledged') is True
        
        # Test resolution
        success = monitoring_system.resolve_alert(alert.alert_id, "Test resolution")
        assert success
        assert alert.alert_id not in monitoring_system._active_alerts
        assert alert.metadata.get('resolved') is True
        assert alert.metadata.get('resolution_reason') == "Test resolution"
    
    def test_monitoring_status(self, monitoring_system):
        """Test monitoring system status reporting."""
        status = monitoring_system.get_monitoring_status()
        
        assert isinstance(status, dict)
        assert 'monitoring_active' in status
        assert 'last_evaluation' in status
        assert 'threshold_configs' in status
        assert 'active_alerts' in status
        assert 'critical_alerts' in status
        assert 'current_system_metrics' in status
        assert 'services_monitored' in status
        
        assert status['monitoring_active'] is False  # Not started yet
        assert status['threshold_configs'] > 0  # Default configs
        assert status['active_alerts'] == 0
        assert status['critical_alerts'] == 0
    
    async def test_integration_with_alerting_service(self, started_monitoring_system):
        """Test integration with the alerting service."""
        # The monitoring system should register alert rules with the alerting service
        alerting_service = started_monitoring_system.alerting_service
        
        # Check that error monitoring rules were registered
        error_rules = [
            rule for rule in alerting_service.alert_rules.values()
            if 'error_monitoring' in rule.rule_id
        ]
        
        assert len(error_rules) > 0
        
        # Check specific rules
        rule_ids = [rule.rule_id for rule in error_rules]
        assert "error_monitoring_high_rate" in rule_ids
        assert "error_monitoring_critical_rate" in rule_ids
        assert "error_monitoring_spike" in rule_ids
    
    def test_data_export(self, monitoring_system):
        """Test exporting monitoring data."""
        # Add some test data
        monitoring_system.record_operation("test_service", "test_op", success=True)
        monitoring_system.record_operation("test_service", "test_op", success=False)
        
        # Export data
        filepath = monitoring_system.export_monitoring_data()
        
        assert filepath is not None
        assert filepath.endswith('.json')
        
        # Verify file exists and contains data
        import os
        import json
        
        assert os.path.exists(filepath)
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        assert 'export_timestamp' in data
        assert 'monitoring_status' in data
        assert 'threshold_configs' in data
        assert 'active_alerts' in data
        assert 'metrics_history' in data
        
        # Cleanup
        os.remove(filepath)
    
    async def test_global_convenience_functions(self):
        """Test global convenience functions."""
        # Test getting global instance
        system1 = get_error_monitoring_system()
        system2 = get_error_monitoring_system()
        assert system1 is system2  # Should be singleton
        
        # Test global start/stop functions
        await start_error_monitoring()
        assert system1._monitoring_active
        
        await stop_error_monitoring()
        assert not system1._monitoring_active
        
        # Test operation recording function
        record_operation_result("test_service", "test_op", True)
        
        error_rate = system1.get_error_rate("test_service", "test_op")
        assert error_rate['total_operations'] >= 1
    
    async def test_error_pattern_detection(self, monitoring_system):
        """Test that the system can detect error patterns."""
        # Record multiple similar errors
        for i in range(5):
            monitoring_system.record_operation(
                "pattern_service", "pattern_op", success=False,
                error_category=ErrorCategory.DATABASE_ERROR,
                error_severity=ErrorSeverity.HIGH
            )
        
        # Record some successes to avoid 100% error rate
        for i in range(10):
            monitoring_system.record_operation("pattern_service", "pattern_op", success=True)
        
        # Get metrics and check for pattern detection
        metrics = monitoring_system.get_system_error_metrics()
        
        assert metrics.total_errors >= 5
        assert "database_error" in metrics.errors_by_category
        assert metrics.errors_by_category["database_error"] >= 5
    
    async def test_concurrent_monitoring(self, monitoring_system):
        """Test monitoring system under concurrent load."""
        await monitoring_system.start_monitoring()
        
        async def record_operations(service_name: str, count: int):
            """Record operations concurrently."""
            for i in range(count):
                success = i % 4 != 0  # 25% error rate
                monitoring_system.record_operation(
                    service_name, f"op_{i}", success=success
                )
                await asyncio.sleep(0.001)  # Small delay
        
        # Run concurrent operations
        tasks = [
            record_operations("service_1", 20),
            record_operations("service_2", 15),
            record_operations("service_3", 25)
        ]
        
        await asyncio.gather(*tasks)
        
        # Wait for monitoring to process
        await asyncio.sleep(1)
        
        # Check that all operations were recorded
        metrics = monitoring_system.get_system_error_metrics()
        assert metrics.total_operations >= 60  # Should have recorded all operations
        
        # Check individual service metrics
        for service in ["service_1", "service_2", "service_3"]:
            service_rate = monitoring_system.get_error_rate(service)
            assert service_rate['total_operations'] > 0
        
        await monitoring_system.stop_monitoring()
    
    def test_threshold_config_validation(self, monitoring_system):
        """Test validation of threshold configurations."""
        # Test valid config
        valid_config = ErrorThresholdConfig(
            service="valid_service",
            warning_rate=5.0,
            critical_rate=10.0,
            warning_percentage=5.0,
            critical_percentage=15.0
        )
        
        success = monitoring_system.add_threshold_config(valid_config)
        assert success
        
        # Test that the system handles edge cases gracefully
        edge_config = ErrorThresholdConfig(
            service="edge_service",
            warning_rate=0.1,  # Very low threshold
            critical_rate=0.2,
            warning_percentage=0.1,
            critical_percentage=0.5,
            evaluation_window_minutes=1,  # Short window
            cooldown_minutes=1
        )
        
        success = monitoring_system.add_threshold_config(edge_config)
        assert success
    
    async def test_monitoring_system_resilience(self, monitoring_system):
        """Test that monitoring system handles errors gracefully."""
        await monitoring_system.start_monitoring()
        
        # Simulate error in monitoring loop by corrupting data
        original_get_system_metrics = monitoring_system.get_system_error_metrics
        
        def failing_get_metrics(*args, **kwargs):
            raise Exception("Simulated monitoring error")
        
        # Temporarily replace method
        monitoring_system.get_system_error_metrics = failing_get_metrics
        
        # Wait for a monitoring cycle
        await asyncio.sleep(1)
        
        # System should still be running despite the error
        assert monitoring_system._monitoring_active
        
        # Restore original method
        monitoring_system.get_system_error_metrics = original_get_system_metrics
        
        # System should recover
        await asyncio.sleep(1)
        
        await monitoring_system.stop_monitoring()


@pytest.mark.asyncio
class TestErrorMonitoringAPIIntegration:
    """Integration tests for error monitoring API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client for API testing."""
        from fastapi.testclient import TestClient
        from src.multimodal_librarian.main import app
        
        return TestClient(app)
    
    def test_monitoring_status_endpoint(self, client):
        """Test the monitoring status API endpoint."""
        response = client.get("/error-monitoring/status")
        assert response.status_code == 200
        
        data = response.json()
        assert "monitoring_active" in data
        assert "threshold_configs" in data
        assert "active_alerts" in data
        assert "current_system_metrics" in data
    
    def test_start_stop_monitoring_endpoints(self, client):
        """Test start/stop monitoring API endpoints."""
        # Start monitoring
        response = client.post("/error-monitoring/start")
        assert response.status_code == 200
        assert "started successfully" in response.json()["message"]
        
        # Stop monitoring
        response = client.post("/error-monitoring/stop")
        assert response.status_code == 200
        assert "stopped successfully" in response.json()["message"]
    
    def test_error_rate_endpoint(self, client):
        """Test the error rate API endpoint."""
        # Record some operations first
        client.post("/error-monitoring/record-operation", json={
            "service": "test_api_service",
            "operation": "test_operation",
            "success": True
        })
        
        client.post("/error-monitoring/record-operation", json={
            "service": "test_api_service",
            "operation": "test_operation",
            "success": False,
            "error_category": "service_failure",
            "error_severity": "medium"
        })
        
        # Get error rate
        response = client.get("/error-monitoring/error-rate", params={
            "service": "test_api_service",
            "operation": "test_operation",
            "window_minutes": 5
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "test_api_service"
        assert data["operation"] == "test_operation"
        assert data["total_operations"] >= 2
        assert data["total_errors"] >= 1
    
    def test_threshold_config_endpoints(self, client):
        """Test threshold configuration API endpoints."""
        # Add threshold config
        config_data = {
            "service": "api_test_service",
            "operation": "api_test_operation",
            "warning_rate": 3.0,
            "critical_rate": 8.0,
            "warning_percentage": 5.0,
            "critical_percentage": 15.0,
            "evaluation_window_minutes": 5,
            "cooldown_minutes": 10,
            "enabled": True
        }
        
        response = client.post("/error-monitoring/thresholds", json=config_data)
        assert response.status_code == 200
        
        returned_config = response.json()
        assert returned_config["service"] == "api_test_service"
        assert returned_config["warning_rate"] == 3.0
        
        # Get all threshold configs
        response = client.get("/error-monitoring/thresholds")
        assert response.status_code == 200
        
        configs = response.json()
        assert isinstance(configs, list)
        assert len(configs) > 0
        
        # Find our config
        our_config = None
        for config in configs:
            if config["service"] == "api_test_service":
                our_config = config
                break
        
        assert our_config is not None
        assert our_config["operation"] == "api_test_operation"
        
        # Remove threshold config
        response = client.delete("/error-monitoring/thresholds/api_test_service", params={
            "operation": "api_test_operation"
        })
        assert response.status_code == 200
    
    def test_alerts_endpoints(self, client):
        """Test alert management API endpoints."""
        # Get active alerts (should be empty initially)
        response = client.get("/error-monitoring/alerts")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        
        # Get alert history
        response = client.get("/error-monitoring/alerts/history", params={"limit": 10})
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_export_endpoint(self, client):
        """Test the data export API endpoint."""
        response = client.get("/error-monitoring/export", params={"format": "json"})
        assert response.status_code == 200
        
        data = response.json()
        assert "message" in data
        assert "data" in data
        assert "filepath" in data
    
    def test_health_check_endpoint(self, client):
        """Test the health check API endpoint."""
        response = client.get("/error-monitoring/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["service"] == "error_monitoring"
        assert "status" in data
        assert "timestamp" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])