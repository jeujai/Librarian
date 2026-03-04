#!/usr/bin/env python3
"""
Test Model Loading Failure Notifications

This test validates the enhanced model loading failure notification system
in the startup alerts service.
"""

import asyncio
import sys
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from multimodal_librarian.startup.phase_manager import (
    StartupPhaseManager, StartupPhase, ModelLoadingStatus
)
from multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector
from multimodal_librarian.monitoring.startup_alerts import (
    StartupAlertsService, Alert, AlertType, AlertSeverity
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MockPhaseManager:
    """Mock phase manager for testing."""
    
    def __init__(self):
        self.current_phase = StartupPhase.ESSENTIAL
        self.phase_start_time = datetime.now() - timedelta(seconds=30)
        self.model_statuses = {}
        self.phase_transitions = []
    
    def get_current_status(self):
        """Return mock status."""
        class MockStatus:
            def __init__(self, manager):
                self.current_phase = manager.current_phase
                self.phase_start_time = manager.phase_start_time
                self.model_statuses = manager.model_statuses
                self.phase_transitions = manager.phase_transitions
        
        return MockStatus(self)
    
    def add_failed_model(self, name: str, priority: str = "standard", 
                        error_message: str = "Loading failed", retry_count: int = 0):
        """Add a failed model for testing."""
        self.model_statuses[name] = ModelLoadingStatus(
            model_name=name,
            priority=priority,
            status="failed",
            started_at=datetime.now() - timedelta(seconds=60),
            error_message=error_message
        )
        # Add retry_count attribute
        setattr(self.model_statuses[name], 'retry_count', retry_count)
    
    def add_loading_model(self, name: str, priority: str = "standard", 
                         started_seconds_ago: int = 30):
        """Add a loading model for testing."""
        self.model_statuses[name] = ModelLoadingStatus(
            model_name=name,
            priority=priority,
            status="loading",
            started_at=datetime.now() - timedelta(seconds=started_seconds_ago)
        )
    
    def add_loaded_model(self, name: str, priority: str = "standard"):
        """Add a loaded model for testing."""
        self.model_statuses[name] = ModelLoadingStatus(
            model_name=name,
            priority=priority,
            status="loaded",
            started_at=datetime.now() - timedelta(seconds=30),
            completed_at=datetime.now() - timedelta(seconds=10),
            duration_seconds=20.0
        )


class MockMetricsCollector:
    """Mock metrics collector for testing."""
    
    def get_phase_completion_metrics(self, phase):
        return {"sample_count": 1, "success_rate": 1.0}
    
    def get_model_loading_metrics(self):
        return {
            "sample_count": 5,
            "success_rate": 0.6,
            "loading_stats": {"mean_duration_seconds": 45.0}
        }
    
    def get_user_wait_time_metrics(self):
        return {
            "wait_time_stats": {"mean_seconds": 15.0, "p95_seconds": 30.0},
            "success_rate": 0.9
        }
    
    def get_cache_performance_metrics(self):
        return {
            "cache_hit_rate": 0.8,
            "cache_effectiveness": "good",
            "total_model_loads": 10
        }
    
    def get_active_user_requests(self):
        return {}


async def test_basic_model_failure_detection():
    """Test basic model failure detection."""
    logger.info("Testing basic model failure detection...")
    
    # Create mock components
    phase_manager = MockPhaseManager()
    metrics_collector = MockMetricsCollector()
    
    # Add some failed models
    phase_manager.add_failed_model("text-embedding", "standard", "Out of memory")
    phase_manager.add_failed_model("chat-model", "essential", "Network timeout")
    phase_manager.add_loaded_model("search-index", "essential")
    
    # Create alerts service
    alerts_service = StartupAlertsService(phase_manager, metrics_collector)
    
    # Collect monitoring data
    monitoring_data = await alerts_service._collect_monitoring_data()
    
    # Test model loading issue detection
    has_issues = alerts_service._check_model_loading_issues(monitoring_data)
    assert has_issues, "Should detect model loading issues"
    
    # Test essential model failure detection
    has_essential_failures = alerts_service._check_essential_model_failures(monitoring_data)
    assert has_essential_failures, "Should detect essential model failures"
    
    logger.info("✓ Basic model failure detection working")


async def test_model_timeout_detection():
    """Test model loading timeout detection."""
    logger.info("Testing model timeout detection...")
    
    # Create mock components
    phase_manager = MockPhaseManager()
    metrics_collector = MockMetricsCollector()
    
    # Add models that have been loading for too long
    phase_manager.add_loading_model("slow-model", "standard", started_seconds_ago=400)  # > 5 minutes
    phase_manager.add_loading_model("normal-model", "standard", started_seconds_ago=30)  # < 5 minutes
    
    # Create alerts service
    alerts_service = StartupAlertsService(phase_manager, metrics_collector)
    
    # Collect monitoring data
    monitoring_data = await alerts_service._collect_monitoring_data()
    
    # Test timeout detection
    has_timeouts = alerts_service._check_model_loading_timeouts(monitoring_data)
    assert has_timeouts, "Should detect model loading timeouts"
    
    logger.info("✓ Model timeout detection working")


async def test_repeated_failure_detection():
    """Test repeated model failure detection."""
    logger.info("Testing repeated failure detection...")
    
    # Create mock components
    phase_manager = MockPhaseManager()
    metrics_collector = MockMetricsCollector()
    
    # Add models with different retry counts
    phase_manager.add_failed_model("retry-model", "standard", "Persistent error", retry_count=5)
    phase_manager.add_failed_model("normal-fail", "standard", "One-time error", retry_count=1)
    
    # Create alerts service
    alerts_service = StartupAlertsService(phase_manager, metrics_collector)
    
    # Collect monitoring data
    monitoring_data = await alerts_service._collect_monitoring_data()
    
    # Test repeated failure detection
    has_repeated_failures = alerts_service._check_repeated_model_failures(monitoring_data)
    assert has_repeated_failures, "Should detect repeated model failures"
    
    logger.info("✓ Repeated failure detection working")


async def test_alert_generation():
    """Test alert generation for model failures."""
    logger.info("Testing alert generation...")
    
    try:
        # Create mock components
        phase_manager = MockPhaseManager()
        metrics_collector = MockMetricsCollector()
        
        # Add various failure scenarios
        phase_manager.add_failed_model("essential-model", "essential", "Critical failure")
        phase_manager.add_failed_model("retry-model", "standard", "Repeated failure", retry_count=4)
        phase_manager.add_loading_model("timeout-model", "standard", started_seconds_ago=400)
        
        # Create alerts service
        alerts_service = StartupAlertsService(phase_manager, metrics_collector)
        
        # Collect monitoring data
        monitoring_data = await alerts_service._collect_monitoring_data()
        
        # Test alert creation for general model loading failure (which should work)
        general_rule = alerts_service.alert_rules["model_loading_failure"]
        alert = await alerts_service._create_alert(general_rule, monitoring_data)
        
        assert alert.alert_type == AlertType.MODEL_LOADING_FAILURE
        assert alert.severity == AlertSeverity.HIGH  # This is the severity for general model failures
        assert len(alert.affected_resources) > 0
        
        # Debug: print the alert details
        logger.info(f"Alert title: {alert.title}")
        logger.info(f"Affected resources: {alert.affected_resources}")
        logger.info(f"Alert description: {alert.description}")
        
        # Check if any resource contains a model name
        has_model_resource = any("model_" in resource for resource in alert.affected_resources)
        assert has_model_resource, f"Should have model resource, got: {alert.affected_resources}"
        
        logger.info("✓ Alert generation working")
        
    except Exception as e:
        logger.error(f"Alert generation test failed with error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise


async def test_error_classification():
    """Test error message classification."""
    logger.info("Testing error classification...")
    
    # Create mock components
    phase_manager = MockPhaseManager()
    metrics_collector = MockMetricsCollector()
    alerts_service = StartupAlertsService(phase_manager, metrics_collector)
    
    # Test different error types
    test_cases = [
        ("Out of memory error", "memory"),
        ("Network connection timeout", "network"),
        ("Disk space full", "storage"),
        ("Corrupted model file", "corruption"),
        ("Model path not found", "configuration"),
        ("Unknown error occurred", "unknown")
    ]
    
    for error_message, expected_type in test_cases:
        error_type = alerts_service._classify_model_error(error_message)
        assert error_type == expected_type, f"Expected {expected_type}, got {error_type} for '{error_message}'"
    
    logger.info("✓ Error classification working")


async def test_remediation_generation():
    """Test remediation step generation."""
    logger.info("Testing remediation generation...")
    
    # Create mock components
    phase_manager = MockPhaseManager()
    metrics_collector = MockMetricsCollector()
    alerts_service = StartupAlertsService(phase_manager, metrics_collector)
    
    # Test remediation for different scenarios
    test_cases = [
        ("test-model", "Out of memory", "essential", 0),
        ("retry-model", "Network timeout", "standard", 5),
        ("storage-model", "Disk full", "standard", 1)
    ]
    
    for model_name, error_message, priority, retry_count in test_cases:
        remediation = alerts_service._generate_model_failure_remediation(
            model_name, error_message, priority, retry_count
        )
        
        assert len(remediation) > 0, "Should generate remediation steps"
        assert any(model_name in step for step in remediation), "Should mention model name"
        
        if priority == "essential":
            assert any("URGENT" in step for step in remediation), "Should have urgent steps for essential models"
        
        if retry_count >= 3:
            assert any("retry" in step.lower() for step in remediation), "Should mention retries"
    
    logger.info("✓ Remediation generation working")


async def test_model_failure_summary():
    """Test model failure summary generation."""
    logger.info("Testing model failure summary...")
    
    # Create mock components
    phase_manager = MockPhaseManager()
    metrics_collector = MockMetricsCollector()
    
    # Add various models
    phase_manager.add_failed_model("failed-1", "essential", "Critical error")
    phase_manager.add_failed_model("failed-2", "standard", "Network error", retry_count=4)
    phase_manager.add_loaded_model("loaded-1", "essential")
    phase_manager.add_loading_model("loading-1", "standard")
    
    # Create alerts service
    alerts_service = StartupAlertsService(phase_manager, metrics_collector)
    
    # Get summary
    summary = alerts_service.get_model_failure_summary()
    
    assert summary["total_models"] == 4
    assert summary["failed_count"] == 2
    assert summary["essential_failed_count"] == 1
    assert summary["repeated_failures_count"] == 1
    assert "failed-1" in summary["failed_models"]
    assert "failed-1" in summary["essential_failed"]
    assert "failed-2" in summary["repeated_failures"]
    
    logger.info("✓ Model failure summary working")


async def test_immediate_alert_recording():
    """Test immediate alert recording for critical failures."""
    logger.info("Testing immediate alert recording...")
    
    # Create mock components
    phase_manager = MockPhaseManager()
    metrics_collector = MockMetricsCollector()
    alerts_service = StartupAlertsService(phase_manager, metrics_collector)
    
    # Start monitoring (but don't wait for it)
    await alerts_service.start_monitoring()
    
    # Record a critical model failure
    await alerts_service.record_model_loading_failure(
        "critical-model", 
        "Essential model failed to load", 
        priority="essential",
        retry_count=0
    )
    
    # Give it a moment to process
    await asyncio.sleep(0.2)
    
    # Check that alert was processed (should be in active alerts now)
    active_alerts = alerts_service.get_active_alerts()
    assert len(active_alerts) > 0, f"Should have active alerts, but got {len(active_alerts)}"
    
    # Check that the alert is for the critical model
    critical_alert = None
    for alert in active_alerts:
        if "critical-model" in alert.title:
            critical_alert = alert
            break
    
    assert critical_alert is not None, "Should have alert for critical-model"
    assert critical_alert.severity == AlertSeverity.CRITICAL, "Should be critical severity"
    
    # Stop monitoring
    await alerts_service.stop_monitoring()
    
    logger.info("✓ Immediate alert recording working")


async def run_all_tests():
    """Run all model loading failure notification tests."""
    logger.info("Starting model loading failure notification tests...")
    
    test_functions = [
        test_basic_model_failure_detection,
        test_model_timeout_detection,
        test_repeated_failure_detection,
        test_alert_generation,
        test_error_classification,
        test_remediation_generation,
        test_model_failure_summary,
        test_immediate_alert_recording
    ]
    
    passed = 0
    failed = 0
    
    for test_func in test_functions:
        try:
            await test_func()
            passed += 1
        except Exception as e:
            logger.error(f"Test {test_func.__name__} failed: {e}")
            failed += 1
    
    logger.info(f"\nTest Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        logger.info("🎉 All model loading failure notification tests passed!")
        return True
    else:
        logger.error("❌ Some tests failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)