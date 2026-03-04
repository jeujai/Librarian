#!/usr/bin/env python3
"""
Test Health Check Latency Metrics Implementation

This test validates the health check latency metrics tracking functionality
during model loading, including GIL contention detection and correlation analysis.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, MagicMock, AsyncMock

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import pytest


class TestHealthCheckLatencyMetric:
    """Test the HealthCheckLatencyMetric dataclass."""
    
    def test_health_check_latency_metric_creation(self):
        """Test creating a HealthCheckLatencyMetric."""
        from multimodal_librarian.monitoring.startup_metrics import HealthCheckLatencyMetric
        from multimodal_librarian.startup.phase_manager import StartupPhase
        
        metric = HealthCheckLatencyMetric(
            timestamp=datetime.now(),
            response_time_ms=50.0,
            success=True,
            startup_phase=StartupPhase.MINIMAL,
            models_loading=["model-a", "model-b"],
            models_loaded_count=2,
            models_total_count=5,
            is_slow=False,
            is_elevated=True,
            endpoint="/health/simple"
        )
        
        assert metric.response_time_ms == 50.0
        assert metric.success is True
        assert metric.startup_phase == StartupPhase.MINIMAL
        assert len(metric.models_loading) == 2
        assert metric.is_slow is False
        assert metric.is_elevated is True
        print("✅ HealthCheckLatencyMetric creation works correctly")
    
    def test_slow_threshold_detection(self):
        """Test that slow threshold (>100ms) is correctly identified."""
        from multimodal_librarian.monitoring.startup_metrics import HealthCheckLatencyMetric
        from multimodal_librarian.startup.phase_manager import StartupPhase
        
        # Normal response
        normal_metric = HealthCheckLatencyMetric(
            timestamp=datetime.now(),
            response_time_ms=10.0,
            success=True,
            startup_phase=StartupPhase.MINIMAL,
            is_slow=10.0 > 100,  # False
            is_elevated=10.0 > 50  # False
        )
        assert normal_metric.is_slow is False
        assert normal_metric.is_elevated is False
        
        # Elevated response
        elevated_metric = HealthCheckLatencyMetric(
            timestamp=datetime.now(),
            response_time_ms=75.0,
            success=True,
            startup_phase=StartupPhase.ESSENTIAL,
            is_slow=75.0 > 100,  # False
            is_elevated=75.0 > 50  # True
        )
        assert elevated_metric.is_slow is False
        assert elevated_metric.is_elevated is True
        
        # Slow response (GIL contention)
        slow_metric = HealthCheckLatencyMetric(
            timestamp=datetime.now(),
            response_time_ms=150.0,
            success=True,
            startup_phase=StartupPhase.ESSENTIAL,
            is_slow=150.0 > 100,  # True
            is_elevated=150.0 > 50  # True
        )
        assert slow_metric.is_slow is True
        assert slow_metric.is_elevated is True
        
        print("✅ Slow threshold detection works correctly")


class TestStartupMetricsCollectorHealthCheckLatency:
    """Test the StartupMetricsCollector health check latency methods."""
    
    @pytest.fixture
    def mock_phase_manager(self):
        """Create a mock phase manager."""
        from multimodal_librarian.startup.phase_manager import StartupPhase
        
        mock = Mock()
        mock.current_phase = StartupPhase.ESSENTIAL
        
        # Create mock status
        mock_status = Mock()
        mock_status.current_phase = StartupPhase.ESSENTIAL
        mock_status.model_statuses = {
            "model-a": Mock(status="loading"),
            "model-b": Mock(status="loaded"),
            "model-c": Mock(status="pending")
        }
        mock.get_current_status.return_value = mock_status
        
        return mock
    
    @pytest.fixture
    def metrics_collector(self, mock_phase_manager):
        """Create a metrics collector for testing."""
        from multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector
        return StartupMetricsCollector(mock_phase_manager)
    
    @pytest.mark.asyncio
    async def test_record_health_check_latency(self, metrics_collector):
        """Test recording health check latency."""
        # Record a normal latency
        await metrics_collector.record_health_check_latency(
            response_time_ms=15.0,
            success=True,
            endpoint="/health/simple"
        )
        
        assert len(metrics_collector.health_check_latency_history) == 1
        metric = metrics_collector.health_check_latency_history[0]
        assert metric.response_time_ms == 15.0
        assert metric.success is True
        assert metric.is_slow is False
        assert metric.is_elevated is False
        
        print("✅ Recording health check latency works correctly")
    
    @pytest.mark.asyncio
    async def test_record_slow_health_check(self, metrics_collector):
        """Test recording a slow health check (GIL contention)."""
        # Record a slow latency
        await metrics_collector.record_health_check_latency(
            response_time_ms=150.0,
            success=True,
            endpoint="/health/simple"
        )
        
        metric = metrics_collector.health_check_latency_history[0]
        assert metric.is_slow is True
        assert metric.is_elevated is True
        assert "model-a" in metric.models_loading  # Should capture loading models
        
        print("✅ Recording slow health check works correctly")
    
    @pytest.mark.asyncio
    async def test_get_health_check_latency_metrics(self, metrics_collector):
        """Test getting health check latency metrics."""
        # Record multiple latencies
        for i in range(10):
            await metrics_collector.record_health_check_latency(
                response_time_ms=10.0 + i * 10,  # 10, 20, 30, ..., 100
                success=True
            )
        
        metrics = metrics_collector.get_health_check_latency_metrics()
        
        assert metrics["sample_count"] == 10
        assert "latency_stats" in metrics
        assert metrics["latency_stats"]["mean_ms"] == 55.0  # Average of 10-100
        assert metrics["latency_stats"]["min_ms"] == 10.0
        assert metrics["latency_stats"]["max_ms"] == 100.0
        
        print("✅ Getting health check latency metrics works correctly")
    
    @pytest.mark.asyncio
    async def test_get_health_check_latency_metrics_filtered(self, metrics_collector):
        """Test getting filtered health check latency metrics."""
        from multimodal_librarian.startup.phase_manager import StartupPhase
        
        # Record latencies
        for i in range(5):
            await metrics_collector.record_health_check_latency(
                response_time_ms=20.0,
                success=True
            )
        
        # Test filtering by during_model_loading
        metrics = metrics_collector.get_health_check_latency_metrics(during_model_loading=True)
        assert metrics["sample_count"] == 5  # All should have models loading
        
        print("✅ Filtered health check latency metrics work correctly")
    
    @pytest.mark.asyncio
    async def test_get_health_check_latency_summary(self, metrics_collector):
        """Test getting health check latency summary."""
        # Record various latencies
        # Note: is_elevated is > 50, so 50 is NOT elevated
        latencies = [5, 10, 15, 20, 51, 75, 100, 150, 200]  # Changed 50 to 51
        for latency in latencies:
            await metrics_collector.record_health_check_latency(
                response_time_ms=float(latency),
                success=True
            )
        
        summary = metrics_collector.get_health_check_latency_summary()
        
        assert summary["total_health_checks"] == 9
        assert summary["successful_checks"] == 9
        assert summary["success_rate"] == 1.0
        assert summary["slow_checks"] == 2  # 150, 200 > 100ms
        assert summary["elevated_checks"] == 5  # 51, 75, 100, 150, 200 > 50ms
        assert "average_latency_ms" in summary
        assert "health_check_quality" in summary
        
        print("✅ Health check latency summary works correctly")
    
    @pytest.mark.asyncio
    async def test_model_loading_correlation_analysis(self, metrics_collector, mock_phase_manager):
        """Test model loading correlation analysis."""
        # Record latencies during model loading
        for i in range(5):
            await metrics_collector.record_health_check_latency(
                response_time_ms=80.0,
                success=True
            )
        
        # Simulate idle state (no models loading)
        mock_phase_manager.get_current_status.return_value.model_statuses = {
            "model-a": Mock(status="loaded"),
            "model-b": Mock(status="loaded"),
            "model-c": Mock(status="loaded")
        }
        
        # Record latencies during idle
        for i in range(5):
            await metrics_collector.record_health_check_latency(
                response_time_ms=5.0,
                success=True
            )
        
        metrics = metrics_collector.get_health_check_latency_metrics()
        
        assert "model_loading_correlation" in metrics
        correlation = metrics["model_loading_correlation"]
        assert correlation["during_loading"]["mean_latency_ms"] == 80.0
        assert correlation["during_idle"]["mean_latency_ms"] == 5.0
        assert correlation["latency_increase_percent"] > 0
        
        print("✅ Model loading correlation analysis works correctly")
    
    @pytest.mark.asyncio
    async def test_gil_contention_analysis(self, metrics_collector):
        """Test GIL contention analysis."""
        # Record some slow health checks
        for i in range(3):
            await metrics_collector.record_health_check_latency(
                response_time_ms=150.0,
                success=True
            )
        
        # Record some normal health checks
        for i in range(7):
            await metrics_collector.record_health_check_latency(
                response_time_ms=10.0,
                success=True
            )
        
        metrics = metrics_collector.get_health_check_latency_metrics()
        
        assert "gil_contention_analysis" in metrics
        gil_analysis = metrics["gil_contention_analysis"]
        assert gil_analysis["contention_detected"] is True
        assert gil_analysis["total_slow_checks"] == 3
        assert "recommendations" in gil_analysis
        
        print("✅ GIL contention analysis works correctly")


class TestStartupAlertsServiceHealthCheckLatency:
    """Test the StartupAlertsService health check latency recording."""
    
    @pytest.mark.asyncio
    async def test_record_health_check_result_with_latency(self):
        """Test that record_health_check_result records latency metrics."""
        from multimodal_librarian.monitoring.startup_alerts import StartupAlertsService
        from multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector
        from multimodal_librarian.startup.phase_manager import StartupPhase
        
        # Create mock phase manager
        mock_phase_manager = Mock()
        mock_phase_manager.current_phase = StartupPhase.MINIMAL
        mock_status = Mock()
        mock_status.current_phase = StartupPhase.MINIMAL
        mock_status.model_statuses = {}
        mock_phase_manager.get_current_status.return_value = mock_status
        
        # Create metrics collector
        metrics_collector = StartupMetricsCollector(mock_phase_manager)
        
        # Create alerts service
        alerts_service = StartupAlertsService(mock_phase_manager, metrics_collector)
        
        # Record health check result with latency
        await alerts_service.record_health_check_result(
            success=True,
            response_time_ms=25.0
        )
        
        # Verify latency was recorded
        assert len(metrics_collector.health_check_latency_history) == 1
        metric = metrics_collector.health_check_latency_history[0]
        assert metric.response_time_ms == 25.0
        assert metric.success is True
        
        print("✅ StartupAlertsService records health check latency correctly")


def run_tests():
    """Run all tests."""
    print("=" * 60)
    print("Testing Health Check Latency Metrics Implementation")
    print("=" * 60)
    
    # Run pytest
    exit_code = pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-x"  # Stop on first failure
    ])
    
    return exit_code


if __name__ == "__main__":
    exit_code = run_tests()
    sys.exit(exit_code)
