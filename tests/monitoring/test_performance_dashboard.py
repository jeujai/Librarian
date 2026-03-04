"""
Tests for Performance Dashboard Service

This module tests the performance dashboard functionality including:
- Real-time metrics display
- Performance trend analysis
- Alert visualization
- Dashboard management
- Chart data generation

Validates: Requirement 6.2 - Performance monitoring and alerting
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock

from src.multimodal_librarian.monitoring.performance_dashboard import (
    PerformanceDashboardService, DashboardChart, PerformanceDashboard, ChartType
)


class TestPerformanceDashboardService:
    """Test suite for PerformanceDashboardService."""
    
    @pytest.fixture
    def dashboard_service(self):
        """Create a performance dashboard service instance for testing."""
        with patch('src.multimodal_librarian.monitoring.performance_dashboard.ComprehensiveMetricsCollector'), \
             patch('src.multimodal_librarian.monitoring.performance_dashboard.SearchPerformanceMonitor'), \
             patch('src.multimodal_librarian.monitoring.performance_dashboard.PerformanceMonitor'), \
             patch('src.multimodal_librarian.monitoring.performance_dashboard.get_alerting_service'):
            
            service = PerformanceDashboardService()
            
            # Mock the monitoring services
            service.metrics_collector = Mock()
            service.search_monitor = Mock()
            service.performance_monitor = Mock()
            service.alerting_service = Mock()
            
            return service
    
    def test_service_initialization(self, dashboard_service):
        """Test that the dashboard service initializes correctly."""
        assert dashboard_service is not None
        assert len(dashboard_service.dashboards) == 3  # Default dashboards
        assert "realtime_performance" in dashboard_service.dashboards
        assert "performance_trends" in dashboard_service.dashboards
        assert "search_performance" in dashboard_service.dashboards
    
    def test_get_available_dashboards(self, dashboard_service):
        """Test getting list of available dashboards."""
        dashboards = dashboard_service.get_available_dashboards()
        
        assert len(dashboards) == 3
        assert all("dashboard_id" in dashboard for dashboard in dashboards)
        assert all("name" in dashboard for dashboard in dashboards)
        assert all("description" in dashboard for dashboard in dashboards)
        assert all("chart_count" in dashboard for dashboard in dashboards)
    
    @pytest.mark.asyncio
    async def test_get_dashboard_data_success(self, dashboard_service):
        """Test successful dashboard data retrieval."""
        # Mock the chart data methods
        dashboard_service._get_response_time_trend_data = AsyncMock(return_value=[
            {"timestamp": "2024-01-01T12:00:00", "value": 200, "label": "12:00:00"}
        ])
        dashboard_service._get_search_performance_gauge_data = AsyncMock(return_value=[
            {"value": 180, "status": "good", "label": "180ms avg"}
        ])
        dashboard_service._get_system_resources_data = AsyncMock(return_value=[
            {"label": "CPU", "value": 45, "unit": "%"}
        ])
        dashboard_service._get_active_alerts_data = AsyncMock(return_value=[])
        
        dashboard_data = await dashboard_service.get_dashboard_data("realtime_performance")
        
        assert dashboard_data is not None
        assert dashboard_data["dashboard_id"] == "realtime_performance"
        assert "charts" in dashboard_data
        assert len(dashboard_data["charts"]) == 4  # realtime dashboard has 4 charts
        assert "last_updated" in dashboard_data
    
    @pytest.mark.asyncio
    async def test_get_dashboard_data_not_found(self, dashboard_service):
        """Test dashboard data retrieval for non-existent dashboard."""
        dashboard_data = await dashboard_service.get_dashboard_data("non_existent")
        assert dashboard_data is None
    
    @pytest.mark.asyncio
    async def test_response_time_trend_data(self, dashboard_service):
        """Test response time trend data generation."""
        # Mock metrics collector
        dashboard_service.metrics_collector.get_real_time_metrics.return_value = {
            "response_time_metrics": {"avg_response_time_ms": 200}
        }
        
        data = await dashboard_service._get_response_time_trend_data()
        
        assert isinstance(data, list)
        assert len(data) == 30  # 30 data points for 5 minutes
        assert all("timestamp" in point for point in data)
        assert all("value" in point for point in data)
        assert all("label" in point for point in data)
        assert all(isinstance(point["value"], (int, float)) for point in data)
    
    @pytest.mark.asyncio
    async def test_search_performance_gauge_data(self, dashboard_service):
        """Test search performance gauge data generation."""
        # Mock search monitor
        dashboard_service.search_monitor.get_current_search_performance.return_value = {
            "latency_metrics": {"avg_latency_ms": 350}
        }
        
        data = await dashboard_service._get_search_performance_gauge_data()
        
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["value"] == 350
        assert data[0]["status"] == "good"  # 350ms is in good range
        assert "label" in data[0]
    
    @pytest.mark.asyncio
    async def test_search_performance_gauge_data_error(self, dashboard_service):
        """Test search performance gauge data when search monitor returns error."""
        # Mock search monitor to return error
        dashboard_service.search_monitor.get_current_search_performance.return_value = {
            "error": "No search performance data available"
        }
        
        data = await dashboard_service._get_search_performance_gauge_data()
        
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["value"] == 0
        assert data[0]["status"] == "unknown"
    
    @pytest.mark.asyncio
    async def test_system_resources_data(self, dashboard_service):
        """Test system resources data generation."""
        # Mock metrics collector
        dashboard_service.metrics_collector.get_real_time_metrics.return_value = {
            "resource_usage": {
                "cpu": {"percent": 45},
                "memory": {"percent": 62},
                "disk": {"percent": 78}
            }
        }
        
        data = await dashboard_service._get_system_resources_data()
        
        assert isinstance(data, list)
        assert len(data) == 3
        
        labels = [item["label"] for item in data]
        assert "CPU" in labels
        assert "Memory" in labels
        assert "Disk" in labels
        
        assert all("value" in item for item in data)
        assert all("unit" in item for item in data)
        assert all(item["unit"] == "%" for item in data)
    
    @pytest.mark.asyncio
    async def test_active_alerts_data(self, dashboard_service):
        """Test active alerts data generation."""
        # Mock alerting service
        mock_alert = Mock()
        mock_alert.alert_id = "alert_1"
        mock_alert.rule_name = "High Response Time"
        mock_alert.message = "Response time exceeds threshold"
        mock_alert.severity.value = "warning"
        mock_alert.triggered_at = datetime.now()
        mock_alert.metric_value = 1200
        mock_alert.threshold = 1000
        
        dashboard_service.alerting_service.get_active_alerts.return_value = [mock_alert]
        
        data = await dashboard_service._get_active_alerts_data()
        
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "alert_1"
        assert data[0]["title"] == "High Response Time"
        assert data[0]["severity"] == "warning"
        assert "timestamp" in data[0]
        assert "duration" in data[0]
    
    @pytest.mark.asyncio
    async def test_active_alerts_data_error(self, dashboard_service):
        """Test active alerts data when alerting service fails."""
        # Mock alerting service to raise exception
        dashboard_service.alerting_service.get_active_alerts.side_effect = Exception("Service unavailable")
        
        data = await dashboard_service._get_active_alerts_data()
        
        assert isinstance(data, list)
        assert len(data) == 0  # Should return empty list on error
    
    @pytest.mark.asyncio
    async def test_hourly_performance_trend_data(self, dashboard_service):
        """Test hourly performance trend data generation."""
        # Mock metrics collector
        dashboard_service.metrics_collector.get_performance_trends.return_value = {
            "hourly_trends": [
                {
                    "hour": "2024-01-01 12:00",
                    "avg_response_time": 200,
                    "requests": 100,
                    "errors": 2
                },
                {
                    "hour": "2024-01-01 13:00",
                    "avg_response_time": 250,
                    "requests": 120,
                    "errors": 1
                }
            ]
        }
        
        data = await dashboard_service._get_hourly_performance_trend_data()
        
        assert isinstance(data, list)
        assert len(data) == 2
        assert all("timestamp" in point for point in data)
        assert all("average" in point for point in data)
        assert all("p95" in point for point in data)
        assert all("p99" in point for point in data)
        assert all("label" in point for point in data)
    
    @pytest.mark.asyncio
    async def test_search_performance_heatmap_data(self, dashboard_service):
        """Test search performance heatmap data generation."""
        data = await dashboard_service._get_search_performance_heatmap_data()
        
        assert isinstance(data, list)
        assert len(data) == 7 * 24  # 7 days * 24 hours
        assert all("x" in point for point in data)  # hour
        assert all("y" in point for point in data)  # day
        assert all("value" in point for point in data)  # latency
        assert all("day_label" in point for point in data)
        assert all("hour_label" in point for point in data)
    
    @pytest.mark.asyncio
    async def test_cache_performance_data(self, dashboard_service):
        """Test cache performance data generation."""
        # Mock metrics collector
        dashboard_service.metrics_collector.get_real_time_metrics.return_value = {
            "cache_metrics": {"hit_rate_percent": 75}
        }
        
        data = await dashboard_service._get_cache_performance_data()
        
        assert isinstance(data, list)
        assert len(data) == 2
        
        labels = [item["label"] for item in data]
        assert "Cache Hits" in labels
        assert "Cache Misses" in labels
        
        hits_data = next(item for item in data if item["label"] == "Cache Hits")
        misses_data = next(item for item in data if item["label"] == "Cache Misses")
        
        assert hits_data["value"] == 75
        assert misses_data["value"] == 25
    
    @pytest.mark.asyncio
    async def test_search_bottlenecks_data(self, dashboard_service):
        """Test search bottlenecks data generation."""
        # Mock search monitor
        dashboard_service.search_monitor.analyze_search_bottlenecks.return_value = [
            {
                "component": "vector_search",
                "avg_time_ms": 450,
                "impact_level": "high",
                "recommendations": [
                    "Optimize vector database indexing",
                    "Consider vector dimension reduction",
                    "Implement vector result caching"
                ]
            }
        ]
        
        data = await dashboard_service._get_search_bottlenecks_data()
        
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["Component"] == "vector_search"
        assert data[0]["Avg Time (ms)"] == 450
        assert data[0]["Impact"] == "High"
        assert "Recommendations" in data[0]
    
    @pytest.mark.asyncio
    async def test_chart_data_caching(self, dashboard_service):
        """Test that chart data is properly cached."""
        # Create a mock chart with response_time_trend chart_id
        chart = DashboardChart(
            chart_id="response_time_trend",
            title="Test Chart",
            chart_type=ChartType.LINE,
            data_points=[],
            config={},
            last_updated=datetime.now()
        )
        
        # Mock the specific chart data method
        dashboard_service._get_response_time_trend_data = AsyncMock(return_value=[
            {"timestamp": "2024-01-01T12:00:00", "value": 200, "label": "12:00:00"}
        ])
        
        # First call should execute the method
        result1 = await dashboard_service._get_chart_data(chart)
        assert dashboard_service._get_response_time_trend_data.call_count == 1
        
        # Second call within cache TTL should use cache
        result2 = await dashboard_service._get_chart_data(chart)
        assert dashboard_service._get_response_time_trend_data.call_count == 1  # No additional call
        
        # Results should be the same (excluding timestamps which may differ)
        assert result1["chart_id"] == result2["chart_id"]
        assert result1["title"] == result2["title"]
    
    @pytest.mark.asyncio
    async def test_export_dashboard_data(self, dashboard_service):
        """Test dashboard data export functionality."""
        # Mock the get_dashboard_data method
        dashboard_service.get_dashboard_data = AsyncMock(return_value={
            "dashboard_id": "test_dashboard",
            "name": "Test Dashboard",
            "charts": []
        })
        
        with patch("builtins.open", create=True) as mock_open:
            with patch("json.dump") as mock_json_dump:
                filename = await dashboard_service.export_dashboard_data("test_dashboard", "json")
                
                assert filename is not None
                assert filename.endswith(".json")
                assert "dashboard_test_dashboard_" in filename
                mock_open.assert_called_once()
                mock_json_dump.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_export_dashboard_data_not_found(self, dashboard_service):
        """Test dashboard data export for non-existent dashboard."""
        # Mock the get_dashboard_data method to return None
        dashboard_service.get_dashboard_data = AsyncMock(return_value=None)
        
        filename = await dashboard_service.export_dashboard_data("non_existent", "json")
        assert filename is None
    
    def test_get_service_status(self, dashboard_service):
        """Test service status retrieval."""
        status = dashboard_service.get_service_status()
        
        assert status["status"] == "active"
        assert status["service"] == "performance_dashboard"
        assert "features" in status
        assert "statistics" in status
        assert "monitoring_services" in status
        
        # Check features
        features = status["features"]
        assert features["real_time_dashboards"] is True
        assert features["performance_trends"] is True
        assert features["alert_visualization"] is True
        
        # Check statistics
        statistics = status["statistics"]
        assert "total_dashboards" in statistics
        assert "total_charts" in statistics
        assert "cache_size" in statistics


class TestDashboardChart:
    """Test suite for DashboardChart class."""
    
    def test_chart_creation(self):
        """Test dashboard chart creation."""
        chart = DashboardChart(
            chart_id="test_chart",
            title="Test Chart",
            chart_type=ChartType.LINE,
            data_points=[{"x": 1, "y": 2}],
            config={"color": "blue"},
            last_updated=datetime.now()
        )
        
        assert chart.chart_id == "test_chart"
        assert chart.title == "Test Chart"
        assert chart.chart_type == ChartType.LINE
        assert len(chart.data_points) == 1
        assert chart.config["color"] == "blue"
        assert chart.refresh_interval == 30  # default
    
    def test_chart_to_dict(self):
        """Test chart serialization to dictionary."""
        now = datetime.now()
        chart = DashboardChart(
            chart_id="test_chart",
            title="Test Chart",
            chart_type=ChartType.BAR,
            data_points=[{"x": 1, "y": 2}],
            config={"color": "red"},
            last_updated=now,
            refresh_interval=60
        )
        
        chart_dict = chart.to_dict()
        
        assert chart_dict["chart_id"] == "test_chart"
        assert chart_dict["title"] == "Test Chart"
        assert chart_dict["chart_type"] == "bar"
        assert chart_dict["data_points"] == [{"x": 1, "y": 2}]
        assert chart_dict["config"]["color"] == "red"
        assert chart_dict["last_updated"] == now.isoformat()
        assert chart_dict["refresh_interval"] == 60


class TestPerformanceDashboard:
    """Test suite for PerformanceDashboard class."""
    
    def test_dashboard_creation(self):
        """Test performance dashboard creation."""
        charts = [
            DashboardChart(
                chart_id="chart1",
                title="Chart 1",
                chart_type=ChartType.LINE,
                data_points=[],
                config={},
                last_updated=datetime.now()
            )
        ]
        
        dashboard = PerformanceDashboard(
            dashboard_id="test_dashboard",
            name="Test Dashboard",
            description="A test dashboard",
            charts=charts,
            layout={"columns": 2}
        )
        
        assert dashboard.dashboard_id == "test_dashboard"
        assert dashboard.name == "Test Dashboard"
        assert dashboard.description == "A test dashboard"
        assert len(dashboard.charts) == 1
        assert dashboard.layout["columns"] == 2
        assert dashboard.auto_refresh is True  # default
        assert dashboard.created_at is not None
    
    def test_dashboard_to_dict(self):
        """Test dashboard serialization to dictionary."""
        charts = [
            DashboardChart(
                chart_id="chart1",
                title="Chart 1",
                chart_type=ChartType.PIE,
                data_points=[],
                config={},
                last_updated=datetime.now()
            )
        ]
        
        dashboard = PerformanceDashboard(
            dashboard_id="test_dashboard",
            name="Test Dashboard",
            description="A test dashboard",
            charts=charts,
            layout={"columns": 1},
            auto_refresh=False,
            refresh_interval=120
        )
        
        dashboard_dict = dashboard.to_dict()
        
        assert dashboard_dict["dashboard_id"] == "test_dashboard"
        assert dashboard_dict["name"] == "Test Dashboard"
        assert dashboard_dict["description"] == "A test dashboard"
        assert len(dashboard_dict["charts"]) == 1
        assert dashboard_dict["layout"]["columns"] == 1
        assert dashboard_dict["auto_refresh"] is False
        assert dashboard_dict["refresh_interval"] == 120
        assert "created_at" in dashboard_dict


@pytest.mark.integration
class TestPerformanceDashboardIntegration:
    """Integration tests for performance dashboard service."""
    
    @pytest.mark.asyncio
    async def test_full_dashboard_workflow(self):
        """Test complete dashboard workflow from creation to data retrieval."""
        with patch('src.multimodal_librarian.monitoring.performance_dashboard.ComprehensiveMetricsCollector'), \
             patch('src.multimodal_librarian.monitoring.performance_dashboard.SearchPerformanceMonitor'), \
             patch('src.multimodal_librarian.monitoring.performance_dashboard.PerformanceMonitor'), \
             patch('src.multimodal_librarian.monitoring.performance_dashboard.get_alerting_service'):
            
            service = PerformanceDashboardService()
            
            # Mock all the data methods
            service._get_response_time_trend_data = AsyncMock(return_value=[])
            service._get_search_performance_gauge_data = AsyncMock(return_value=[])
            service._get_system_resources_data = AsyncMock(return_value=[])
            service._get_active_alerts_data = AsyncMock(return_value=[])
            
            # Test workflow
            dashboards = service.get_available_dashboards()
            assert len(dashboards) > 0
            
            dashboard_id = dashboards[0]["dashboard_id"]
            dashboard_data = await service.get_dashboard_data(dashboard_id)
            
            assert dashboard_data is not None
            assert dashboard_data["dashboard_id"] == dashboard_id
            assert "charts" in dashboard_data
            assert "last_updated" in dashboard_data
    
    def test_service_singleton(self):
        """Test that the service follows singleton pattern."""
        from src.multimodal_librarian.monitoring.performance_dashboard import get_performance_dashboard_service
        
        with patch('src.multimodal_librarian.monitoring.performance_dashboard.ComprehensiveMetricsCollector'), \
             patch('src.multimodal_librarian.monitoring.performance_dashboard.SearchPerformanceMonitor'), \
             patch('src.multimodal_librarian.monitoring.performance_dashboard.PerformanceMonitor'), \
             patch('src.multimodal_librarian.monitoring.performance_dashboard.get_alerting_service'):
            
            service1 = get_performance_dashboard_service()
            service2 = get_performance_dashboard_service()
            
            assert service1 is service2  # Same instance