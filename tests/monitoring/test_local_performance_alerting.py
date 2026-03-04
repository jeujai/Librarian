"""
Tests for Local Performance Alerting

This module contains comprehensive tests for the local development performance
alerting system, including threshold evaluation, alert generation, and
integration with monitoring components.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
from typing import Dict, Any

from src.multimodal_librarian.monitoring.local_performance_alerting import (
    LocalPerformanceAlerting,
    PerformanceAlertType,
    PerformanceThreshold,
    PerformanceAlertRule,
    get_local_performance_alerting
)
from src.multimodal_librarian.monitoring.alerting_service import AlertSeverity
from src.multimodal_librarian.monitoring.local_performance_metrics import LocalServiceMetrics
from src.multimodal_librarian.config.local_config import LocalDatabaseConfig


@pytest.fixture
def mock_config():
    """Mock local database configuration."""
    config = Mock(spec=LocalDatabaseConfig)
    config.log_dir = "/tmp/test_logs"
    config.api_host = "localhost"
    config.api_port = 8000
    return config


@pytest.fixture
def performance_alerting(mock_config):
    """Create performance alerting instance for testing."""
    return LocalPerformanceAlerting(mock_config)


@pytest.fixture
def mock_performance_tracker():
    """Mock performance tracker."""
    tracker = Mock()
    tracker.register_alert_callback = Mock()
    tracker.get_performance_summary = Mock(return_value={
        "memory_usage_percent": 75.0,
        "cpu_usage_percent": 60.0,
        "query_response_time_ms": 1500.0,
        "error_rate_percent": 5.0
    })
    return tracker


@pytest.fixture
def mock_metrics_collector():
    """Mock metrics collector."""
    collector = Mock()
    collector.get_current_service_metrics = AsyncMock(return_value={
        "postgres": LocalServiceMetrics(
            service_name="postgres",
            container_name="postgres_container",
            timestamp=datetime.now(),
            status="running",
            response_time_ms=800.0,
            query_count=100,
            error_count=2,
            memory_usage_mb=512.0,
            memory_limit_mb=1024.0,
            cpu_percent=45.0
        ),
        "neo4j": LocalServiceMetrics(
            service_name="neo4j",
            container_name="neo4j_container",
            timestamp=datetime.now(),
            status="running",
            response_time_ms=1200.0,
            query_count=50,
            error_count=1,
            memory_usage_mb=768.0,
            memory_limit_mb=1024.0,
            cpu_percent=35.0
        )
    })
    return collector


@pytest.fixture
def mock_query_monitor():
    """Mock query performance monitor."""
    monitor = Mock()
    monitor.add_alert_callback = Mock()
    return monitor


class TestLocalPerformanceAlerting:
    """Test cases for LocalPerformanceAlerting class."""
    
    def test_initialization(self, performance_alerting, mock_config):
        """Test performance alerting initialization."""
        assert performance_alerting.config == mock_config
        assert not performance_alerting._alerting_active
        assert len(performance_alerting._alert_rules) > 0
        
        # Check that default alert rules are configured
        assert PerformanceAlertType.SLOW_DATABASE_QUERY in performance_alerting._alert_rules
        assert PerformanceAlertType.HIGH_QUERY_ERROR_RATE in performance_alerting._alert_rules
        assert PerformanceAlertType.CONTAINER_MEMORY_LIMIT_EXCEEDED in performance_alerting._alert_rules
    
    @pytest.mark.asyncio
    async def test_start_stop_alerting(self, performance_alerting, mock_performance_tracker):
        """Test starting and stopping alerting system."""
        # Test start
        await performance_alerting.start_alerting(performance_tracker=mock_performance_tracker)
        assert performance_alerting._alerting_active
        assert performance_alerting._alerting_task is not None
        
        # Verify callback registration
        mock_performance_tracker.register_alert_callback.assert_called_once()
        
        # Test stop
        await performance_alerting.stop_alerting()
        assert not performance_alerting._alerting_active
    
    def test_extract_metric_value(self, performance_alerting):
        """Test metric value extraction from nested dictionaries."""
        metrics = {
            "memory": {
                "usage_percent": 85.5
            },
            "cpu_usage_percent": 70.0,
            "nested": {
                "deep": {
                    "value": 42.0
                }
            }
        }
        
        # Test simple key
        assert performance_alerting._extract_metric_value(metrics, "cpu_usage_percent") == 70.0
        
        # Test nested key
        assert performance_alerting._extract_metric_value(metrics, "memory.usage_percent") == 85.5
        
        # Test deeply nested key
        assert performance_alerting._extract_metric_value(metrics, "nested.deep.value") == 42.0
        
        # Test non-existent key
        assert performance_alerting._extract_metric_value(metrics, "non_existent") is None
        
        # Test invalid nested key
        assert performance_alerting._extract_metric_value(metrics, "memory.invalid") is None
    
    @pytest.mark.asyncio
    async def test_evaluate_threshold_exceeded(self, performance_alerting):
        """Test threshold evaluation when threshold is exceeded."""
        alert_type = PerformanceAlertType.SLOW_DATABASE_QUERY
        rule = performance_alerting._alert_rules[alert_type]
        threshold = rule.thresholds[0]
        
        # Mock metrics with high response time
        metrics = {"query_response_time_ms": 8000.0}  # Above 5000ms threshold
        
        with patch.object(performance_alerting, '_send_performance_alert') as mock_send:
            # Add enough samples to trigger evaluation
            for _ in range(threshold.min_samples):
                await performance_alerting._evaluate_threshold(alert_type, rule, threshold, metrics)
            
            # Should trigger alert
            mock_send.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_evaluate_threshold_not_exceeded(self, performance_alerting):
        """Test threshold evaluation when threshold is not exceeded."""
        alert_type = PerformanceAlertType.SLOW_DATABASE_QUERY
        rule = performance_alerting._alert_rules[alert_type]
        threshold = rule.thresholds[0]
        
        # Mock metrics with normal response time
        metrics = {"query_response_time_ms": 1000.0}  # Below 5000ms threshold
        
        with patch.object(performance_alerting, '_send_performance_alert') as mock_send:
            # Add enough samples
            for _ in range(threshold.min_samples):
                await performance_alerting._evaluate_threshold(alert_type, rule, threshold, metrics)
            
            # Should not trigger alert
            mock_send.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_check_service_specific_thresholds_memory(self, performance_alerting):
        """Test service-specific threshold checking for memory usage."""
        # Create metrics with high memory usage
        metrics = LocalServiceMetrics(
            service_name="postgres",
            container_name="postgres_container",
            timestamp=datetime.now(),
            status="running",
            memory_usage_mb=950.0,  # 95% of 1000MB limit
            memory_limit_mb=1000.0
        )
        
        with patch.object(performance_alerting, '_send_service_alert') as mock_send:
            await performance_alerting._check_service_specific_thresholds("postgres", metrics)
            
            # Should trigger memory alert
            mock_send.assert_called()
            call_args = mock_send.call_args
            assert call_args[1]["alert_type"] == PerformanceAlertType.CONTAINER_MEMORY_LIMIT_EXCEEDED
    
    @pytest.mark.asyncio
    async def test_check_service_specific_thresholds_response_time(self, performance_alerting):
        """Test service-specific threshold checking for response time."""
        # Create metrics with slow response time
        metrics = LocalServiceMetrics(
            service_name="neo4j",
            container_name="neo4j_container",
            timestamp=datetime.now(),
            status="running",
            response_time_ms=3000.0,  # Above 2000ms threshold
            query_count=10,
            error_count=0
        )
        
        with patch.object(performance_alerting, '_send_service_alert') as mock_send:
            await performance_alerting._check_service_specific_thresholds("neo4j", metrics)
            
            # Should trigger response time alert
            mock_send.assert_called()
            call_args = mock_send.call_args
            assert call_args[1]["alert_type"] == PerformanceAlertType.SERVICE_RESPONSE_TIME_DEGRADED
    
    @pytest.mark.asyncio
    async def test_check_service_specific_thresholds_error_rate(self, performance_alerting):
        """Test service-specific threshold checking for error rate."""
        # Create metrics with high error rate
        metrics = LocalServiceMetrics(
            service_name="milvus",
            container_name="milvus_container",
            timestamp=datetime.now(),
            status="running",
            query_count=100,
            error_count=15  # 15% error rate
        )
        
        with patch.object(performance_alerting, '_send_service_alert') as mock_send:
            await performance_alerting._check_service_specific_thresholds("milvus", metrics)
            
            # Should trigger error rate alert
            mock_send.assert_called()
            call_args = mock_send.call_args
            assert call_args[1]["alert_type"] == PerformanceAlertType.HIGH_QUERY_ERROR_RATE
    
    @pytest.mark.asyncio
    async def test_cooldown_prevents_duplicate_alerts(self, performance_alerting):
        """Test that cooldown prevents duplicate alerts."""
        alert_type = PerformanceAlertType.SLOW_DATABASE_QUERY
        rule = performance_alerting._alert_rules[alert_type]
        threshold = rule.thresholds[0]
        
        # Mock metrics with high response time
        metrics = {"query_response_time_ms": 8000.0}
        
        with patch('src.multimodal_librarian.monitoring.local_performance_alerting.send_local_alert') as mock_send:
            # First alert should be sent
            await performance_alerting._send_performance_alert(
                alert_type=alert_type,
                rule=rule,
                threshold=threshold,
                current_value=8000.0,
                metric_name="query_response_time_ms"
            )
            
            # Second alert within cooldown should be suppressed
            await performance_alerting._send_performance_alert(
                alert_type=alert_type,
                rule=rule,
                threshold=threshold,
                current_value=8500.0,
                metric_name="query_response_time_ms"
            )
            
            # Only one alert should be sent
            assert mock_send.call_count == 1
    
    def test_map_to_local_alert_type(self, performance_alerting):
        """Test mapping of performance alert types to local alert types."""
        from src.multimodal_librarian.monitoring.local_alerting_system import LocalAlertType
        
        # Test database-related mappings
        assert performance_alerting._map_to_local_alert_type(
            PerformanceAlertType.SLOW_DATABASE_QUERY
        ) == LocalAlertType.DATABASE_DOWN
        
        assert performance_alerting._map_to_local_alert_type(
            PerformanceAlertType.HIGH_QUERY_ERROR_RATE
        ) == LocalAlertType.DATABASE_DOWN
        
        # Test resource-related mappings
        assert performance_alerting._map_to_local_alert_type(
            PerformanceAlertType.CONTAINER_MEMORY_LIMIT_EXCEEDED
        ) == LocalAlertType.HIGH_MEMORY_USAGE
        
        assert performance_alerting._map_to_local_alert_type(
            PerformanceAlertType.CONTAINER_CPU_THROTTLING
        ) == LocalAlertType.HIGH_CPU_USAGE
        
        # Test service-related mappings
        assert performance_alerting._map_to_local_alert_type(
            PerformanceAlertType.SERVICE_RESPONSE_TIME_DEGRADED
        ) == LocalAlertType.DEVELOPMENT_SERVER_DOWN
    
    def test_alert_rule_configuration(self, performance_alerting):
        """Test alert rule configuration methods."""
        alert_type = PerformanceAlertType.SLOW_DATABASE_QUERY
        
        # Test getting rules
        rules = performance_alerting.get_alert_rules()
        assert alert_type in rules
        
        # Test enabling/disabling rules
        performance_alerting.disable_alert_rule(alert_type)
        assert not performance_alerting._alert_rules[alert_type].enabled
        
        performance_alerting.enable_alert_rule(alert_type)
        assert performance_alerting._alert_rules[alert_type].enabled
        
        # Test updating rules
        new_rule = PerformanceAlertRule(
            alert_type=alert_type,
            service_pattern=r"test_pattern",
            thresholds=[],
            description="Test rule"
        )
        
        performance_alerting.update_alert_rule(alert_type, new_rule)
        assert performance_alerting._alert_rules[alert_type].description == "Test rule"
    
    @pytest.mark.asyncio
    async def test_cleanup_old_alerts(self, performance_alerting):
        """Test cleanup of old alert state."""
        # Add some old alert times
        old_time = datetime.now() - timedelta(hours=2)
        recent_time = datetime.now() - timedelta(minutes=30)
        
        performance_alerting._last_alert_times = {
            "old_alert": old_time,
            "recent_alert": recent_time
        }
        
        # Add some performance history
        performance_alerting._performance_history = {
            "test_metric": list(range(200))  # More than 100 samples
        }
        
        await performance_alerting._cleanup_old_alerts()
        
        # Old alert time should be removed
        assert "old_alert" not in performance_alerting._last_alert_times
        assert "recent_alert" in performance_alerting._last_alert_times
        
        # Performance history should be trimmed
        assert len(performance_alerting._performance_history["test_metric"]) == 100


class TestPerformanceAlertingIntegration:
    """Test cases for performance alerting integration."""
    
    @pytest.mark.asyncio
    async def test_integration_lifecycle(self, mock_config):
        """Test integration lifecycle management."""
        from src.multimodal_librarian.monitoring.performance_alerting_integration import (
            PerformanceAlertingIntegration
        )
        
        integration = PerformanceAlertingIntegration(mock_config)
        
        # Test start
        await integration.start_integration()
        assert integration._integration_active
        
        # Test stop
        await integration.stop_integration()
        assert not integration._integration_active
    
    @pytest.mark.asyncio
    async def test_integration_with_components(self, mock_config, mock_performance_tracker, 
                                             mock_metrics_collector, mock_query_monitor):
        """Test integration with monitoring components."""
        from src.multimodal_librarian.monitoring.performance_alerting_integration import (
            PerformanceAlertingIntegration
        )
        
        integration = PerformanceAlertingIntegration(mock_config)
        
        await integration.start_integration(
            performance_tracker=mock_performance_tracker,
            metrics_collector=mock_metrics_collector,
            query_monitor=mock_query_monitor
        )
        
        assert integration._performance_tracker == mock_performance_tracker
        assert integration._metrics_collector == mock_metrics_collector
        assert integration._query_monitor == mock_query_monitor
        
        await integration.stop_integration()
    
    def test_custom_threshold_configuration(self, mock_config):
        """Test custom threshold configuration."""
        from src.multimodal_librarian.monitoring.performance_alerting_integration import (
            PerformanceAlertingIntegration
        )
        
        integration = PerformanceAlertingIntegration(mock_config)
        
        integration.configure_custom_threshold(
            alert_type=PerformanceAlertType.SLOW_DATABASE_QUERY,
            metric_name="custom_metric",
            threshold_value=1000.0,
            comparison="greater_than",
            severity="high"
        )
        
        assert len(integration._custom_thresholds) == 1
        
        threshold_key = f"{PerformanceAlertType.SLOW_DATABASE_QUERY.value}_custom_metric"
        assert threshold_key in integration._custom_thresholds
    
    def test_alerting_status(self, mock_config):
        """Test alerting status reporting."""
        from src.multimodal_librarian.monitoring.performance_alerting_integration import (
            PerformanceAlertingIntegration
        )
        
        integration = PerformanceAlertingIntegration(mock_config)
        status = integration.get_alerting_status()
        
        assert "integration_active" in status
        assert "alerting_system_active" in status
        assert "components_initialized" in status
        assert "custom_thresholds_count" in status
        assert "timestamp" in status


@pytest.mark.asyncio
async def test_global_functions():
    """Test global convenience functions."""
    from src.multimodal_librarian.monitoring.local_performance_alerting import (
        get_local_performance_alerting,
        start_local_performance_alerting,
        stop_local_performance_alerting
    )
    
    # Test getting global instance
    alerting1 = get_local_performance_alerting()
    alerting2 = get_local_performance_alerting()
    assert alerting1 is alerting2  # Should be singleton
    
    # Test start/stop functions
    await start_local_performance_alerting()
    await stop_local_performance_alerting()


if __name__ == "__main__":
    pytest.main([__file__])