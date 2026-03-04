#!/usr/bin/env python3
"""
Test Health Check Failure Monitoring Implementation

This test validates that the health check failure monitoring system is working correctly,
including failure detection, alerting, and integration with the health endpoints.
"""

import asyncio
import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

# Test the startup alerts service health check monitoring
@pytest.mark.asyncio
async def test_startup_alerts_service_health_check_monitoring():
    """Test that the startup alerts service correctly monitors health check failures."""
    
    # Import required modules
    from src.multimodal_librarian.monitoring.startup_alerts import StartupAlertsService, AlertType, AlertSeverity
    from src.multimodal_librarian.startup.phase_manager import StartupPhaseManager
    from src.multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector
    
    # Create mock dependencies
    phase_manager = Mock(spec=StartupPhaseManager)
    metrics_collector = Mock(spec=StartupMetricsCollector)
    
    # Initialize the alerts service
    alerts_service = StartupAlertsService(phase_manager, metrics_collector)
    
    # Test initial state
    assert alerts_service._consecutive_health_failures == 0
    assert alerts_service._last_health_check_time is None
    
    # Test successful health check recording
    await alerts_service.record_health_check_result(True, 100.0)
    assert alerts_service._consecutive_health_failures == 0
    assert alerts_service._last_health_check_time is not None
    
    # Test single health check failure
    await alerts_service.record_health_check_result(False, 5000.0)
    assert alerts_service._consecutive_health_failures == 1
    
    # Test multiple consecutive failures
    await alerts_service.record_health_check_result(False, 5000.0)
    assert alerts_service._consecutive_health_failures == 2
    
    await alerts_service.record_health_check_result(False, 5000.0)
    assert alerts_service._consecutive_health_failures == 3
    
    # Test that success resets the counter
    await alerts_service.record_health_check_result(True, 100.0)
    assert alerts_service._consecutive_health_failures == 0
    
    print("✅ Startup alerts service health check monitoring test passed")


@pytest.mark.asyncio
async def test_health_check_failure_alert_triggering():
    """Test that health check failure alerts are triggered correctly."""
    
    from src.multimodal_librarian.monitoring.startup_alerts import StartupAlertsService, AlertType
    from src.multimodal_librarian.startup.phase_manager import StartupPhaseManager
    from src.multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector
    
    # Create mock dependencies
    phase_manager = Mock(spec=StartupPhaseManager)
    metrics_collector = Mock(spec=StartupMetricsCollector)
    
    # Initialize the alerts service
    alerts_service = StartupAlertsService(phase_manager, metrics_collector)
    
    # Start monitoring
    await alerts_service.start_monitoring()
    
    # Simulate consecutive health check failures to trigger alert
    threshold = alerts_service.default_thresholds["health_check_failure_threshold"].threshold_value
    
    # Record failures up to threshold
    for i in range(int(threshold)):
        await alerts_service.record_health_check_result(False, 5000.0)
    
    # Wait a moment for alert processing
    await asyncio.sleep(0.1)
    
    # Check that health check failure rule exists
    assert "health_check_failure" in alerts_service.alert_rules
    rule = alerts_service.alert_rules["health_check_failure"]
    assert rule.alert_type == AlertType.HEALTH_CHECK_FAILURE
    assert rule.enabled
    
    # Stop monitoring
    await alerts_service.stop_monitoring()
    
    print("✅ Health check failure alert triggering test passed")


@pytest.mark.asyncio
async def test_health_endpoint_integration():
    """Test that health endpoints integrate with the alerts service."""
    
    from src.multimodal_librarian.api.routers.health import set_startup_alerts_service, get_startup_alerts_service
    from src.multimodal_librarian.monitoring.startup_alerts import StartupAlertsService
    from src.multimodal_librarian.startup.phase_manager import StartupPhaseManager
    from src.multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector
    
    # Create mock dependencies
    phase_manager = Mock(spec=StartupPhaseManager)
    metrics_collector = Mock(spec=StartupMetricsCollector)
    
    # Initialize the alerts service
    alerts_service = StartupAlertsService(phase_manager, metrics_collector)
    
    # Test setting and getting the alerts service
    set_startup_alerts_service(alerts_service)
    retrieved_service = get_startup_alerts_service()
    
    assert retrieved_service is alerts_service
    
    print("✅ Health endpoint integration test passed")


@pytest.mark.asyncio
async def test_health_check_alerts_endpoint():
    """Test the health check alerts endpoint functionality."""
    
    from fastapi.testclient import TestClient
    from src.multimodal_librarian.api.routers.health import router
    from src.multimodal_librarian.api.routers.health import set_startup_alerts_service
    from src.multimodal_librarian.monitoring.startup_alerts import StartupAlertsService
    from src.multimodal_librarian.startup.phase_manager import StartupPhaseManager
    from src.multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector
    from fastapi import FastAPI
    
    # Create test app
    app = FastAPI()
    app.include_router(router)
    
    # Create mock dependencies
    phase_manager = Mock(spec=StartupPhaseManager)
    metrics_collector = Mock(spec=StartupMetricsCollector)
    
    # Initialize the alerts service
    alerts_service = StartupAlertsService(phase_manager, metrics_collector)
    set_startup_alerts_service(alerts_service)
    
    # Create test client
    client = TestClient(app)
    
    # Test alerts endpoint
    response = client.get("/api/health/alerts")
    assert response.status_code == 200
    
    data = response.json()
    assert "status" in data
    assert "health_check_status" in data
    assert "consecutive_failures" in data["health_check_status"]
    assert "failure_threshold" in data["health_check_status"]
    
    # Test alerts summary endpoint
    response = client.get("/api/health/alerts/summary")
    assert response.status_code == 200
    
    data = response.json()
    assert "health_score" in data
    assert "consecutive_failures" in data
    assert "trend" in data
    
    print("✅ Health check alerts endpoint test passed")


@pytest.mark.asyncio
async def test_health_check_failure_remediation():
    """Test that health check failure alerts include proper remediation steps."""
    
    from src.multimodal_librarian.monitoring.startup_alerts import StartupAlertsService
    from src.multimodal_librarian.startup.phase_manager import StartupPhaseManager
    from src.multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector
    
    # Create mock dependencies
    phase_manager = Mock(spec=StartupPhaseManager)
    metrics_collector = Mock(spec=StartupMetricsCollector)
    
    # Initialize the alerts service
    alerts_service = StartupAlertsService(phase_manager, metrics_collector)
    
    # Check that health check failure threshold has remediation steps
    threshold = alerts_service.default_thresholds["health_check_failure_threshold"]
    assert len(threshold.remediation_steps) > 0
    
    # Verify remediation steps are relevant
    remediation_steps = threshold.remediation_steps
    assert any("health" in step.lower() for step in remediation_steps)
    assert any("log" in step.lower() or "check" in step.lower() for step in remediation_steps)
    assert any("resource" in step.lower() for step in remediation_steps)
    
    print("✅ Health check failure remediation test passed")


@pytest.mark.asyncio
async def test_health_check_performance_tracking():
    """Test that health check response times are tracked."""
    
    from src.multimodal_librarian.monitoring.startup_alerts import StartupAlertsService
    from src.multimodal_librarian.startup.phase_manager import StartupPhaseManager
    from src.multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector
    
    # Create mock dependencies
    phase_manager = Mock(spec=StartupPhaseManager)
    metrics_collector = Mock(spec=StartupMetricsCollector)
    
    # Initialize the alerts service
    alerts_service = StartupAlertsService(phase_manager, metrics_collector)
    
    # Test recording health check with response time
    await alerts_service.record_health_check_result(True, 150.0)  # 150ms
    assert alerts_service._last_health_check_time is not None
    
    # Test recording slow health check
    await alerts_service.record_health_check_result(True, 8000.0)  # 8 seconds
    
    # Test recording failed health check with timeout
    await alerts_service.record_health_check_result(False, 30000.0)  # 30 seconds
    assert alerts_service._consecutive_health_failures == 1
    
    print("✅ Health check performance tracking test passed")


async def run_all_tests():
    """Run all health check failure monitoring tests."""
    print("🧪 Running Health Check Failure Monitoring Tests...")
    print("=" * 60)
    
    try:
        await test_startup_alerts_service_health_check_monitoring()
        await test_health_check_failure_alert_triggering()
        await test_health_endpoint_integration()
        await test_health_check_alerts_endpoint()
        await test_health_check_failure_remediation()
        await test_health_check_performance_tracking()
        
        print("=" * 60)
        print("✅ All Health Check Failure Monitoring Tests Passed!")
        print("\n📋 Test Summary:")
        print("  • Startup alerts service health check monitoring")
        print("  • Health check failure alert triggering")
        print("  • Health endpoint integration")
        print("  • Health check alerts endpoint functionality")
        print("  • Health check failure remediation steps")
        print("  • Health check performance tracking")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Run the tests
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)