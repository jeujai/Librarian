"""
Tests for GIL Contention Detection Alerts

This test module validates the GIL contention detection alerting functionality
in the startup alerts system. It tests the alert rules, thresholds, and
condition checking methods for detecting GIL contention during model loading.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch

from multimodal_librarian.monitoring.startup_alerts import (
    StartupAlertsService,
    AlertType,
    AlertSeverity,
    AlertThreshold,
    AlertRule,
    Alert,
)
from multimodal_librarian.monitoring.startup_metrics import (
    StartupMetricsCollector,
    HealthCheckLatencyMetric,
)
from multimodal_librarian.startup.phase_manager import (
    StartupPhase,
    StartupPhaseManager,
    StartupStatus,
    ModelLoadingStatus,
)


class TestGILContentionAlertThresholds:
    """Test GIL contention alert threshold configuration."""
    
    @pytest.fixture
    def mock_phase_manager(self):
        """Create a mock phase manager."""
        manager = MagicMock(spec=StartupPhaseManager)
        manager.current_phase = StartupPhase.ESSENTIAL
        manager.status = MagicMock()
        manager.status.phase_transitions = []
        manager.status.model_statuses = {}
        manager.phase_configs = {
            StartupPhase.MINIMAL: MagicMock(timeout_seconds=60),
            StartupPhase.ESSENTIAL: MagicMock(timeout_seconds=180),
            StartupPhase.FULL: MagicMock(timeout_seconds=600),
        }
        
        # Mock get_current_status
        status = MagicMock(spec=StartupStatus)
        status.current_phase = StartupPhase.ESSENTIAL
        status.phase_start_time = datetime.now() - timedelta(seconds=30)
        status.model_statuses = {}
        manager.get_current_status.return_value = status
        
        return manager
    
    @pytest.fixture
    def mock_metrics_collector(self, mock_phase_manager):
        """Create a mock metrics collector."""
        collector = MagicMock(spec=StartupMetricsCollector)
        collector.phase_manager = mock_phase_manager
        
        # Mock methods
        collector.get_phase_completion_metrics.return_value = {}
        collector.get_model_loading_metrics.return_value = {}
        collector.get_user_wait_time_metrics.return_value = {}
        collector.get_cache_performance_metrics.return_value = {}
        collector.get_active_user_requests.return_value = {}
        collector.get_health_check_latency_metrics.return_value = {}
        
        return collector
    
    @pytest.fixture
    def alerts_service(self, mock_phase_manager, mock_metrics_collector):
        """Create an alerts service instance."""
        return StartupAlertsService(mock_phase_manager, mock_metrics_collector)
    
    def test_gil_contention_thresholds_exist(self, alerts_service):
        """Test that GIL contention thresholds are properly configured."""
        thresholds = alerts_service.default_thresholds
        
        # Check slow rate threshold
        assert "gil_contention_slow_rate_threshold" in thresholds
        slow_rate = thresholds["gil_contention_slow_rate_threshold"]
        assert slow_rate.threshold_value == 0.1  # 10%
        assert slow_rate.severity == AlertSeverity.HIGH
        
        # Check max latency threshold
        assert "gil_contention_max_latency_threshold" in thresholds
        max_latency = thresholds["gil_contention_max_latency_threshold"]
        assert max_latency.threshold_value == 500.0  # 500ms
        assert max_latency.severity == AlertSeverity.CRITICAL
        
        # Check avg latency threshold
        assert "gil_contention_avg_latency_threshold" in thresholds
        avg_latency = thresholds["gil_contention_avg_latency_threshold"]
        assert avg_latency.threshold_value == 50.0  # 50ms
        assert avg_latency.severity == AlertSeverity.MEDIUM
        
        # Check loading correlation threshold
        assert "gil_contention_loading_correlation_threshold" in thresholds
        correlation = thresholds["gil_contention_loading_correlation_threshold"]
        assert correlation.threshold_value == 0.8  # 80%
        assert correlation.severity == AlertSeverity.HIGH
        
        print("✅ All GIL contention thresholds are properly configured")
    
    def test_gil_contention_alert_rules_exist(self, alerts_service):
        """Test that GIL contention alert rules are properly configured."""
        rules = alerts_service.alert_rules
        
        # Check slow rate rule
        assert "gil_contention_slow_rate" in rules
        slow_rate_rule = rules["gil_contention_slow_rate"]
        assert slow_rate_rule.alert_type == AlertType.GIL_CONTENTION
        assert "gil" in slow_rate_rule.tags
        
        # Check extreme latency rule
        assert "gil_contention_extreme_latency" in rules
        extreme_rule = rules["gil_contention_extreme_latency"]
        assert extreme_rule.alert_type == AlertType.GIL_CONTENTION
        assert extreme_rule.severity == AlertSeverity.CRITICAL
        
        # Check elevated latency rule
        assert "gil_contention_elevated_latency" in rules
        elevated_rule = rules["gil_contention_elevated_latency"]
        assert elevated_rule.alert_type == AlertType.GIL_CONTENTION
        
        # Check model loading correlation rule
        assert "gil_contention_model_loading_correlation" in rules
        correlation_rule = rules["gil_contention_model_loading_correlation"]
        assert correlation_rule.alert_type == AlertType.GIL_CONTENTION
        
        print("✅ All GIL contention alert rules are properly configured")


class TestGILContentionConditionChecking:
    """Test GIL contention condition checking methods."""
    
    @pytest.fixture
    def mock_phase_manager(self):
        """Create a mock phase manager."""
        manager = MagicMock(spec=StartupPhaseManager)
        manager.current_phase = StartupPhase.ESSENTIAL
        manager.status = MagicMock()
        manager.status.phase_transitions = []
        manager.status.model_statuses = {}
        manager.phase_configs = {
            StartupPhase.MINIMAL: MagicMock(timeout_seconds=60),
            StartupPhase.ESSENTIAL: MagicMock(timeout_seconds=180),
            StartupPhase.FULL: MagicMock(timeout_seconds=600),
        }
        
        status = MagicMock(spec=StartupStatus)
        status.current_phase = StartupPhase.ESSENTIAL
        status.phase_start_time = datetime.now() - timedelta(seconds=30)
        status.model_statuses = {}
        manager.get_current_status.return_value = status
        
        return manager
    
    @pytest.fixture
    def mock_metrics_collector(self, mock_phase_manager):
        """Create a mock metrics collector."""
        collector = MagicMock(spec=StartupMetricsCollector)
        collector.phase_manager = mock_phase_manager
        collector.get_phase_completion_metrics.return_value = {}
        collector.get_model_loading_metrics.return_value = {}
        collector.get_user_wait_time_metrics.return_value = {}
        collector.get_cache_performance_metrics.return_value = {}
        collector.get_active_user_requests.return_value = {}
        collector.get_health_check_latency_metrics.return_value = {}
        return collector
    
    @pytest.fixture
    def alerts_service(self, mock_phase_manager, mock_metrics_collector):
        """Create an alerts service instance."""
        return StartupAlertsService(mock_phase_manager, mock_metrics_collector)
    
    def test_check_gil_contention_slow_rate_no_data(self, alerts_service, mock_phase_manager):
        """Test slow rate check with insufficient data."""
        monitoring_data = {
            "timestamp": datetime.now(),
            "phase_manager_status": mock_phase_manager.get_current_status(),
            "metrics_summary": {
                "health_check_latency": {
                    "sample_count": 3,  # Less than 5
                    "slow_response_rate": 0.5
                }
            }
        }
        
        result = alerts_service._check_gil_contention_slow_rate(monitoring_data)
        assert result is False  # Should not alert with insufficient data
        
        print("✅ Slow rate check correctly handles insufficient data")
    
    def test_check_gil_contention_slow_rate_triggered(self, alerts_service, mock_phase_manager):
        """Test slow rate check when threshold is exceeded."""
        monitoring_data = {
            "timestamp": datetime.now(),
            "phase_manager_status": mock_phase_manager.get_current_status(),
            "metrics_summary": {
                "health_check_latency": {
                    "sample_count": 10,
                    "slow_response_rate": 0.15  # 15% > 10% threshold
                }
            }
        }
        
        result = alerts_service._check_gil_contention_slow_rate(monitoring_data)
        assert result is True
        
        print("✅ Slow rate check correctly triggers when threshold exceeded")
    
    def test_check_gil_contention_slow_rate_not_triggered(self, alerts_service, mock_phase_manager):
        """Test slow rate check when threshold is not exceeded."""
        monitoring_data = {
            "timestamp": datetime.now(),
            "phase_manager_status": mock_phase_manager.get_current_status(),
            "metrics_summary": {
                "health_check_latency": {
                    "sample_count": 10,
                    "slow_response_rate": 0.05  # 5% < 10% threshold
                }
            }
        }
        
        result = alerts_service._check_gil_contention_slow_rate(monitoring_data)
        assert result is False
        
        print("✅ Slow rate check correctly does not trigger below threshold")
    
    def test_check_gil_contention_extreme_latency_triggered(self, alerts_service, mock_phase_manager):
        """Test extreme latency check when threshold is exceeded."""
        monitoring_data = {
            "timestamp": datetime.now(),
            "phase_manager_status": mock_phase_manager.get_current_status(),
            "metrics_summary": {
                "health_check_latency": {
                    "latency_stats": {
                        "max_ms": 600.0  # 600ms > 500ms threshold
                    }
                }
            }
        }
        
        result = alerts_service._check_gil_contention_extreme_latency(monitoring_data)
        assert result is True
        
        print("✅ Extreme latency check correctly triggers when threshold exceeded")
    
    def test_check_gil_contention_extreme_latency_not_triggered(self, alerts_service, mock_phase_manager):
        """Test extreme latency check when threshold is not exceeded."""
        monitoring_data = {
            "timestamp": datetime.now(),
            "phase_manager_status": mock_phase_manager.get_current_status(),
            "metrics_summary": {
                "health_check_latency": {
                    "latency_stats": {
                        "max_ms": 200.0  # 200ms < 500ms threshold
                    }
                }
            }
        }
        
        result = alerts_service._check_gil_contention_extreme_latency(monitoring_data)
        assert result is False
        
        print("✅ Extreme latency check correctly does not trigger below threshold")
    
    def test_check_gil_contention_elevated_latency_triggered(self, alerts_service, mock_phase_manager):
        """Test elevated latency check when threshold is exceeded."""
        monitoring_data = {
            "timestamp": datetime.now(),
            "phase_manager_status": mock_phase_manager.get_current_status(),
            "metrics_summary": {
                "health_check_latency": {
                    "sample_count": 15,
                    "latency_stats": {
                        "mean_ms": 75.0  # 75ms > 50ms threshold
                    }
                }
            }
        }
        
        result = alerts_service._check_gil_contention_elevated_latency(monitoring_data)
        assert result is True
        
        print("✅ Elevated latency check correctly triggers when threshold exceeded")
    
    def test_check_gil_contention_loading_correlation_triggered(self, alerts_service, mock_phase_manager):
        """Test loading correlation check when threshold is exceeded."""
        monitoring_data = {
            "timestamp": datetime.now(),
            "phase_manager_status": mock_phase_manager.get_current_status(),
            "metrics_summary": {
                "health_check_latency": {
                    "gil_contention_analysis": {
                        "contention_detected": True,
                        "total_slow_checks": 5,
                        "loading_correlation_rate": 0.9  # 90% > 80% threshold
                    }
                }
            }
        }
        
        result = alerts_service._check_gil_contention_loading_correlation(monitoring_data)
        assert result is True
        
        print("✅ Loading correlation check correctly triggers when threshold exceeded")
    
    def test_check_gil_contention_loading_correlation_no_contention(self, alerts_service, mock_phase_manager):
        """Test loading correlation check when no contention detected."""
        monitoring_data = {
            "timestamp": datetime.now(),
            "phase_manager_status": mock_phase_manager.get_current_status(),
            "metrics_summary": {
                "health_check_latency": {
                    "gil_contention_analysis": {
                        "contention_detected": False
                    }
                }
            }
        }
        
        result = alerts_service._check_gil_contention_loading_correlation(monitoring_data)
        assert result is False
        
        print("✅ Loading correlation check correctly handles no contention")


class TestGILContentionAlertGeneration:
    """Test GIL contention alert generation and context extraction."""
    
    @pytest.fixture
    def mock_phase_manager(self):
        """Create a mock phase manager."""
        manager = MagicMock(spec=StartupPhaseManager)
        manager.current_phase = StartupPhase.ESSENTIAL
        manager.status = MagicMock()
        manager.status.phase_transitions = []
        manager.status.model_statuses = {
            "text-embedding": MagicMock(status="loading", priority="essential"),
            "chat-model": MagicMock(status="loaded", priority="essential"),
        }
        manager.phase_configs = {
            StartupPhase.MINIMAL: MagicMock(timeout_seconds=60),
            StartupPhase.ESSENTIAL: MagicMock(timeout_seconds=180),
            StartupPhase.FULL: MagicMock(timeout_seconds=600),
        }
        
        status = MagicMock(spec=StartupStatus)
        status.current_phase = StartupPhase.ESSENTIAL
        status.phase_start_time = datetime.now() - timedelta(seconds=30)
        status.model_statuses = manager.status.model_statuses
        manager.get_current_status.return_value = status
        
        return manager
    
    @pytest.fixture
    def mock_metrics_collector(self, mock_phase_manager):
        """Create a mock metrics collector."""
        collector = MagicMock(spec=StartupMetricsCollector)
        collector.phase_manager = mock_phase_manager
        collector.get_phase_completion_metrics.return_value = {}
        collector.get_model_loading_metrics.return_value = {}
        collector.get_user_wait_time_metrics.return_value = {}
        collector.get_cache_performance_metrics.return_value = {}
        collector.get_active_user_requests.return_value = {}
        collector.get_health_check_latency_metrics.return_value = {
            "sample_count": 20,
            "slow_response_rate": 0.15,
            "latency_stats": {
                "mean_ms": 75.0,
                "max_ms": 600.0,
                "p95_ms": 150.0,
                "p99_ms": 400.0
            },
            "gil_contention_analysis": {
                "contention_detected": True,
                "total_slow_checks": 3,
                "loading_correlation_rate": 0.85,
                "models_associated_with_slow_checks": {
                    "text-embedding": 2,
                    "chat-model": 1
                },
                "recommendations": [
                    "Use ProcessPoolExecutor for CPU-bound model loading"
                ]
            }
        }
        return collector
    
    @pytest.fixture
    def alerts_service(self, mock_phase_manager, mock_metrics_collector):
        """Create an alerts service instance."""
        return StartupAlertsService(mock_phase_manager, mock_metrics_collector)
    
    @pytest.mark.asyncio
    async def test_extract_gil_contention_context(self, alerts_service, mock_phase_manager):
        """Test context extraction for GIL contention alerts."""
        monitoring_data = {
            "timestamp": datetime.now(),
            "phase_manager_status": mock_phase_manager.get_current_status(),
            "metrics_summary": {
                "health_check_latency": {
                    "sample_count": 20,
                    "slow_response_rate": 0.15,
                    "elevated_response_rate": 0.3,
                    "latency_stats": {
                        "mean_ms": 75.0,
                        "max_ms": 600.0,
                        "p95_ms": 150.0,
                        "p99_ms": 400.0
                    },
                    "gil_contention_analysis": {
                        "contention_detected": True,
                        "total_slow_checks": 3,
                        "slow_during_model_loading": 2,
                        "loading_correlation_rate": 0.85,
                        "models_associated_with_slow_checks": {
                            "text-embedding": 2
                        },
                        "recommendations": ["Use ProcessPoolExecutor"]
                    },
                    "model_loading_correlation": {
                        "latency_increase_percent": 150.0
                    },
                    "performance_insights": ["High slow response rate"]
                }
            }
        }
        
        context = await alerts_service._extract_alert_context(
            AlertType.GIL_CONTENTION, monitoring_data
        )
        
        # Verify context contains expected fields
        assert "sample_count" in context
        assert context["sample_count"] == 20
        assert "slow_response_rate" in context
        assert context["slow_response_rate"] == 0.15
        assert "mean_latency_ms" in context
        assert context["mean_latency_ms"] == 75.0
        assert "max_latency_ms" in context
        assert context["max_latency_ms"] == 600.0
        assert "contention_detected" in context
        assert context["contention_detected"] is True
        assert "models_currently_loading" in context
        assert "models_causing_contention" in context
        assert "recommendations" in context
        
        print("✅ GIL contention context extraction works correctly")
    
    @pytest.mark.asyncio
    async def test_identify_gil_contention_affected_resources(self, alerts_service, mock_phase_manager):
        """Test affected resources identification for GIL contention alerts."""
        monitoring_data = {
            "timestamp": datetime.now(),
            "phase_manager_status": mock_phase_manager.get_current_status(),
            "metrics_summary": {
                "health_check_latency": {
                    "gil_contention_analysis": {
                        "models_associated_with_slow_checks": {
                            "text-embedding": 2,
                            "chat-model": 1
                        }
                    }
                }
            }
        }
        
        resources = await alerts_service._identify_affected_resources(
            AlertType.GIL_CONTENTION, monitoring_data
        )
        
        # Verify expected resources
        assert "startup_system" in resources
        assert "event_loop" in resources
        assert "health_endpoints" in resources
        assert "model_loading" in resources
        assert "model_text-embedding_gil_contention" in resources
        assert "model_chat-model_gil_contention" in resources
        
        print("✅ GIL contention affected resources identification works correctly")
    
    @pytest.mark.asyncio
    async def test_extract_gil_contention_metrics(self, alerts_service, mock_phase_manager):
        """Test metrics extraction for GIL contention alerts."""
        monitoring_data = {
            "timestamp": datetime.now(),
            "phase_manager_status": mock_phase_manager.get_current_status(),
            "metrics_summary": {
                "health_check_latency": {
                    "sample_count": 20,
                    "slow_response_rate": 0.15,
                    "elevated_response_rate": 0.3,
                    "latency_stats": {
                        "mean_ms": 75.0,
                        "median_ms": 60.0,
                        "max_ms": 600.0,
                        "p95_ms": 150.0,
                        "p99_ms": 400.0
                    },
                    "gil_contention_analysis": {
                        "total_slow_checks": 3,
                        "slow_during_model_loading": 2,
                        "loading_correlation_rate": 0.85
                    }
                }
            }
        }
        
        metrics = await alerts_service._extract_alert_metrics(
            AlertType.GIL_CONTENTION, monitoring_data
        )
        
        # Verify expected metrics
        assert "sample_count" in metrics
        assert metrics["sample_count"] == 20
        assert "slow_response_rate" in metrics
        assert metrics["slow_response_rate"] == 0.15
        assert "mean_latency_ms" in metrics
        assert metrics["mean_latency_ms"] == 75.0
        assert "max_latency_ms" in metrics
        assert metrics["max_latency_ms"] == 600.0
        assert "total_slow_checks" in metrics
        assert metrics["total_slow_checks"] == 3
        assert "loading_correlation_rate" in metrics
        assert metrics["loading_correlation_rate"] == 0.85
        
        print("✅ GIL contention metrics extraction works correctly")


class TestGILContentionAlertDescriptions:
    """Test GIL contention alert description generation."""
    
    @pytest.fixture
    def mock_phase_manager(self):
        """Create a mock phase manager."""
        manager = MagicMock(spec=StartupPhaseManager)
        manager.current_phase = StartupPhase.ESSENTIAL
        manager.status = MagicMock()
        manager.status.phase_transitions = []
        manager.status.model_statuses = {
            "text-embedding": MagicMock(status="loading", priority="essential"),
        }
        manager.phase_configs = {
            StartupPhase.MINIMAL: MagicMock(timeout_seconds=60),
            StartupPhase.ESSENTIAL: MagicMock(timeout_seconds=180),
            StartupPhase.FULL: MagicMock(timeout_seconds=600),
        }
        
        status = MagicMock(spec=StartupStatus)
        status.current_phase = StartupPhase.ESSENTIAL
        status.phase_start_time = datetime.now() - timedelta(seconds=30)
        status.model_statuses = manager.status.model_statuses
        manager.get_current_status.return_value = status
        
        return manager
    
    @pytest.fixture
    def mock_metrics_collector(self, mock_phase_manager):
        """Create a mock metrics collector."""
        collector = MagicMock(spec=StartupMetricsCollector)
        collector.phase_manager = mock_phase_manager
        collector.get_phase_completion_metrics.return_value = {}
        collector.get_model_loading_metrics.return_value = {}
        collector.get_user_wait_time_metrics.return_value = {}
        collector.get_cache_performance_metrics.return_value = {}
        collector.get_active_user_requests.return_value = {}
        collector.get_health_check_latency_metrics.return_value = {}
        return collector
    
    @pytest.fixture
    def alerts_service(self, mock_phase_manager, mock_metrics_collector):
        """Create an alerts service instance."""
        return StartupAlertsService(mock_phase_manager, mock_metrics_collector)
    
    @pytest.mark.asyncio
    async def test_generate_slow_rate_description(self, alerts_service, mock_phase_manager):
        """Test description generation for slow rate alert."""
        rule = alerts_service.alert_rules["gil_contention_slow_rate"]
        
        monitoring_data = {
            "timestamp": datetime.now(),
            "phase_manager_status": mock_phase_manager.get_current_status(),
            "metrics_summary": {
                "health_check_latency": {
                    "slow_response_rate": 0.15,
                    "latency_stats": {},
                    "gil_contention_analysis": {
                        "total_slow_checks": 5
                    }
                }
            }
        }
        
        description = await alerts_service._generate_alert_description(rule, monitoring_data)
        
        assert "15.0%" in description
        assert "slow" in description.lower()
        assert "5" in description  # total slow checks
        
        print("✅ Slow rate alert description generated correctly")
    
    @pytest.mark.asyncio
    async def test_generate_extreme_latency_description(self, alerts_service, mock_phase_manager):
        """Test description generation for extreme latency alert."""
        rule = alerts_service.alert_rules["gil_contention_extreme_latency"]
        
        monitoring_data = {
            "timestamp": datetime.now(),
            "phase_manager_status": mock_phase_manager.get_current_status(),
            "metrics_summary": {
                "health_check_latency": {
                    "latency_stats": {
                        "max_ms": 750.0
                    },
                    "gil_contention_analysis": {}
                }
            }
        }
        
        description = await alerts_service._generate_alert_description(rule, monitoring_data)
        
        assert "750.0ms" in description
        assert "timeout" in description.lower() or "restart" in description.lower()
        
        print("✅ Extreme latency alert description generated correctly")
    
    @pytest.mark.asyncio
    async def test_generate_loading_correlation_description(self, alerts_service, mock_phase_manager):
        """Test description generation for loading correlation alert."""
        rule = alerts_service.alert_rules["gil_contention_model_loading_correlation"]
        
        monitoring_data = {
            "timestamp": datetime.now(),
            "phase_manager_status": mock_phase_manager.get_current_status(),
            "metrics_summary": {
                "health_check_latency": {
                    "latency_stats": {},
                    "gil_contention_analysis": {
                        "loading_correlation_rate": 0.9,
                        "models_associated_with_slow_checks": {
                            "text-embedding": 3,
                            "chat-model": 2
                        }
                    }
                }
            }
        }
        
        description = await alerts_service._generate_alert_description(rule, monitoring_data)
        
        assert "90.0%" in description
        assert "model loading" in description.lower()
        
        print("✅ Loading correlation alert description generated correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
