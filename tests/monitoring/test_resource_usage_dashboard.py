"""
Tests for Resource Usage Dashboard

This module tests the resource usage dashboard functionality including:
- Dashboard service initialization
- Resource monitoring and data collection
- Chart data generation
- Alert management
- Optimization recommendations
- API endpoints
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta
from fastapi.testclient import TestClient

from src.multimodal_librarian.monitoring.resource_usage_dashboard import (
    ResourceUsageDashboardService,
    ResourceAlert,
    ResourceOptimization,
    ResourceType,
    get_resource_usage_dashboard_service
)
from src.multimodal_librarian.api.routers.resource_usage_dashboard import router
from src.multimodal_librarian.main import app

class TestResourceUsageDashboardService:
    """Test the resource usage dashboard service."""
    
    @pytest.fixture
    def dashboard_service(self):
        """Create a dashboard service instance for testing."""
        with patch('src.multimodal_librarian.monitoring.resource_usage_dashboard.docker.from_env') as mock_docker:
            mock_docker.side_effect = Exception("Docker not available")
            service = ResourceUsageDashboardService()
            return service
    
    def test_service_initialization(self, dashboard_service):
        """Test that the service initializes correctly."""
        assert dashboard_service is not None
        assert not dashboard_service.monitoring_active
        assert not dashboard_service.docker_available
        assert len(dashboard_service.dashboards) == 3
        assert "system_resources" in dashboard_service.dashboards
        assert "container_resources" in dashboard_service.dashboards
        assert "resource_trends" in dashboard_service.dashboards
    
    def test_dashboard_initialization(self, dashboard_service):
        """Test that dashboards are properly initialized."""
        system_dashboard = dashboard_service.dashboards["system_resources"]
        assert system_dashboard.name == "System Resources Overview"
        assert len(system_dashboard.charts) == 4
        
        container_dashboard = dashboard_service.dashboards["container_resources"]
        assert container_dashboard.name == "Container Resources"
        assert len(container_dashboard.charts) == 4
        
        trends_dashboard = dashboard_service.dashboards["resource_trends"]
        assert trends_dashboard.name == "Resource Trends & Optimization"
        assert len(trends_dashboard.charts) == 4
    
    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self, dashboard_service):
        """Test starting and stopping monitoring."""
        # Test start monitoring
        with patch.object(dashboard_service.memory_monitor, 'start_monitoring', new_callable=AsyncMock):
            await dashboard_service.start_monitoring()
            assert dashboard_service.monitoring_active
            assert dashboard_service.monitor_task is not None
        
        # Test stop monitoring
        await dashboard_service.stop_monitoring()
        assert not dashboard_service.monitoring_active
        assert dashboard_service.monitor_task is None
    
    @pytest.mark.asyncio
    async def test_collect_system_metrics(self, dashboard_service):
        """Test system metrics collection."""
        with patch('src.multimodal_librarian.monitoring.resource_usage_dashboard.psutil') as mock_psutil:
            # Mock psutil responses
            mock_psutil.cpu_percent.return_value = 45.5
            mock_psutil.virtual_memory.return_value = Mock(
                percent=65.2, used=8589934592, available=4294967296
            )
            mock_psutil.disk_usage.return_value = Mock(
                percent=75.8, used=107374182400, free=35791394816
            )
            mock_psutil.net_io_counters.return_value = Mock(
                bytes_sent=1073741824, bytes_recv=2147483648
            )
            
            await dashboard_service._collect_system_metrics()
            
            assert len(dashboard_service.resource_history) == 1
            metrics = dashboard_service.resource_history[0]
            assert metrics["cpu_percent"] == 45.5
            assert metrics["memory_percent"] == 65.2
            assert metrics["disk_percent"] == 75.8
    
    @pytest.mark.asyncio
    async def test_update_resource_alerts(self, dashboard_service):
        """Test resource alert generation."""
        # Add some test metrics
        test_metrics = {
            "timestamp": datetime.now(),
            "cpu_percent": 85.5,  # Above critical threshold
            "memory_percent": 78.2,  # Above warning threshold
            "disk_percent": 45.0,  # Normal
            "memory_used_gb": 8.0,
            "memory_available_gb": 4.0,
            "disk_used_gb": 100.0,
            "disk_free_gb": 32.0,
            "network_bytes_sent": 1073741824,
            "network_bytes_recv": 2147483648
        }
        dashboard_service.resource_history.append(test_metrics)
        
        await dashboard_service._update_resource_alerts()
        
        # Should have alerts for CPU (critical) and Memory (warning)
        assert len(dashboard_service.active_alerts) >= 2
        
        cpu_alerts = [alert for alert in dashboard_service.active_alerts 
                     if alert.resource_type == ResourceType.CPU]
        memory_alerts = [alert for alert in dashboard_service.active_alerts 
                        if alert.resource_type == ResourceType.MEMORY]
        
        assert len(cpu_alerts) >= 1
        assert cpu_alerts[0].severity == "critical"
        assert len(memory_alerts) >= 1
        assert memory_alerts[0].severity == "warning"
    
    @pytest.mark.asyncio
    async def test_update_optimization_recommendations(self, dashboard_service):
        """Test optimization recommendation generation."""
        # Add test metrics with patterns that should generate recommendations
        for i in range(15):
            test_metrics = {
                "timestamp": datetime.now() - timedelta(minutes=i),
                "cpu_percent": 15.0,  # Underutilized
                "memory_percent": 85.0,  # High usage
                "disk_percent": 45.0,
                "memory_used_gb": 8.0,
                "memory_available_gb": 4.0,
                "disk_used_gb": 100.0,
                "disk_free_gb": 32.0,
                "network_bytes_sent": 1073741824,
                "network_bytes_recv": 2147483648
            }
            dashboard_service.resource_history.append(test_metrics)
        
        await dashboard_service._update_optimization_recommendations()
        
        # Should have recommendations for CPU underutilization and high memory usage
        assert len(dashboard_service.optimization_recommendations) >= 2
        
        cpu_recommendations = [rec for rec in dashboard_service.optimization_recommendations 
                              if rec.resource_type == ResourceType.CPU]
        memory_recommendations = [rec for rec in dashboard_service.optimization_recommendations 
                                 if rec.resource_type == ResourceType.MEMORY]
        
        assert len(cpu_recommendations) >= 1
        assert len(memory_recommendations) >= 1
    
    @pytest.mark.asyncio
    async def test_get_dashboard_data(self, dashboard_service):
        """Test getting dashboard data."""
        # Add some test data
        test_metrics = {
            "timestamp": datetime.now(),
            "cpu_percent": 45.5,
            "memory_percent": 65.2,
            "disk_percent": 75.8,
            "memory_used_gb": 8.0,
            "memory_available_gb": 4.0,
            "disk_used_gb": 100.0,
            "disk_free_gb": 32.0,
            "network_bytes_sent": 1073741824,
            "network_bytes_recv": 2147483648
        }
        dashboard_service.resource_history.append(test_metrics)
        
        dashboard_data = await dashboard_service.get_dashboard_data("system_resources")
        
        assert dashboard_data is not None
        assert dashboard_data["dashboard_id"] == "system_resources"
        assert dashboard_data["name"] == "System Resources Overview"
        assert len(dashboard_data["charts"]) == 4
        assert "last_updated" in dashboard_data
    
    def test_get_available_dashboards(self, dashboard_service):
        """Test getting available dashboards list."""
        dashboards = dashboard_service.get_available_dashboards()
        
        assert len(dashboards) == 3
        assert all("dashboard_id" in dashboard for dashboard in dashboards)
        assert all("name" in dashboard for dashboard in dashboards)
        assert all("description" in dashboard for dashboard in dashboards)
    
    def test_get_service_status(self, dashboard_service):
        """Test getting service status."""
        status = dashboard_service.get_service_status()
        
        assert status["service"] == "resource_usage_dashboard"
        assert "features" in status
        assert "statistics" in status
        assert "monitoring" in status
        assert "thresholds" in status
        
        # Check features
        features = status["features"]
        assert features["system_monitoring"] is True
        assert features["resource_alerts"] is True
        assert features["optimization_recommendations"] is True

class TestResourceUsageDashboardAPI:
    """Test the resource usage dashboard API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create a test client."""
        app.include_router(router)
        return TestClient(app)
    
    @pytest.fixture
    def mock_service(self):
        """Mock the dashboard service."""
        with patch('src.multimodal_librarian.api.routers.resource_usage_dashboard.get_resource_usage_dashboard_service') as mock:
            service = Mock()
            service.monitoring_active = False
            service.docker_available = False
            service.collection_interval = 60
            service.active_alerts = []
            service.optimization_recommendations = []
            service.resource_history = []
            service.container_history = {}
            service.thresholds = {
                "cpu_warning": 70.0,
                "cpu_critical": 85.0,
                "memory_warning": 75.0,
                "memory_critical": 90.0,
                "disk_warning": 80.0,
                "disk_critical": 95.0,
                "container_memory_warning": 80.0,
                "container_memory_critical": 95.0,
                "container_cpu_warning": 75.0,
                "container_cpu_critical": 90.0
            }
            mock.return_value = service
            yield service
    
    def test_get_dashboard_service_status(self, client, mock_service):
        """Test getting dashboard service status."""
        mock_service.get_service_status.return_value = {
            "status": "inactive",
            "service": "resource_usage_dashboard",
            "features": {"system_monitoring": True},
            "statistics": {"total_dashboards": 3},
            "monitoring": {"active": False}
        }
        
        response = client.get("/api/v1/resource-dashboard/status")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert "data" in data
        assert data["data"]["service"] == "resource_usage_dashboard"
    
    def test_start_monitoring(self, client, mock_service):
        """Test starting resource monitoring."""
        mock_service.monitoring_active = False
        
        with patch('src.multimodal_librarian.api.routers.resource_usage_dashboard.start_resource_monitoring', new_callable=AsyncMock):
            response = client.post("/api/v1/resource-dashboard/monitoring/start")
            assert response.status_code == 200
            
            data = response.json()
            assert data["success"] is True
            assert "Resource monitoring started" in data["message"]
    
    def test_stop_monitoring(self, client, mock_service):
        """Test stopping resource monitoring."""
        with patch('src.multimodal_librarian.api.routers.resource_usage_dashboard.stop_resource_monitoring', new_callable=AsyncMock):
            response = client.post("/api/v1/resource-dashboard/monitoring/stop")
            assert response.status_code == 200
            
            data = response.json()
            assert data["success"] is True
            assert "Resource monitoring stopped" in data["message"]
    
    def test_get_available_dashboards(self, client, mock_service):
        """Test getting available dashboards."""
        mock_service.get_available_dashboards.return_value = [
            {
                "dashboard_id": "system_resources",
                "name": "System Resources Overview",
                "description": "Real-time system resource monitoring",
                "chart_count": 4
            }
        ]
        
        response = client.get("/api/v1/resource-dashboard/dashboards")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert len(data["data"]["dashboards"]) == 1
        assert data["data"]["dashboards"][0]["dashboard_id"] == "system_resources"
    
    def test_get_dashboard_data(self, client, mock_service):
        """Test getting specific dashboard data."""
        mock_dashboard_data = {
            "dashboard_id": "system_resources",
            "name": "System Resources Overview",
            "charts": [],
            "last_updated": datetime.now().isoformat()
        }
        mock_service.get_dashboard_data = AsyncMock(return_value=mock_dashboard_data)
        
        response = client.get("/api/v1/resource-dashboard/dashboards/system_resources")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["data"]["dashboard_id"] == "system_resources"
    
    def test_get_dashboard_data_not_found(self, client, mock_service):
        """Test getting non-existent dashboard data."""
        mock_service.get_dashboard_data = AsyncMock(return_value=None)
        
        response = client.get("/api/v1/resource-dashboard/dashboards/nonexistent")
        assert response.status_code == 404
    
    def test_get_resource_alerts(self, client, mock_service):
        """Test getting resource alerts."""
        mock_alert = Mock()
        mock_alert.to_dict.return_value = {
            "alert_id": "test_alert",
            "severity": "warning",
            "message": "Test alert",
            "timestamp": datetime.now().isoformat()
        }
        mock_service.active_alerts = [mock_alert]
        
        response = client.get("/api/v1/resource-dashboard/alerts")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["data"]["summary"]["total_alerts"] == 1
    
    def test_get_optimization_recommendations(self, client, mock_service):
        """Test getting optimization recommendations."""
        mock_recommendation = Mock()
        mock_recommendation.to_dict.return_value = {
            "optimization_id": "test_opt",
            "priority": "high",
            "title": "Test Optimization",
            "description": "Test description"
        }
        mock_service.optimization_recommendations = [mock_recommendation]
        
        response = client.get("/api/v1/resource-dashboard/optimization")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert data["data"]["summary"]["total_recommendations"] == 1
    
    def test_get_system_resource_metrics(self, client, mock_service):
        """Test getting system resource metrics."""
        test_metrics = {
            "timestamp": datetime.now(),
            "cpu_percent": 45.5,
            "memory_percent": 65.2,
            "memory_used_gb": 8.0,
            "memory_available_gb": 4.0,
            "disk_percent": 75.8,
            "disk_used_gb": 100.0,
            "disk_free_gb": 32.0,
            "network_bytes_sent": 1073741824,
            "network_bytes_recv": 2147483648
        }
        mock_service.resource_history = [test_metrics]
        
        response = client.get("/api/v1/resource-dashboard/metrics/system")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert "cpu" in data["data"]
        assert "memory" in data["data"]
        assert "disk" in data["data"]
    
    def test_get_container_resource_metrics_docker_unavailable(self, client, mock_service):
        """Test getting container metrics when Docker is unavailable."""
        mock_service.docker_available = False
        
        response = client.get("/api/v1/resource-dashboard/metrics/containers")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is False
        assert "Docker is not available" in data["message"]
    
    def test_get_resource_trends(self, client, mock_service):
        """Test getting resource trends."""
        test_trends = [
            {
                "timestamp": datetime.now().isoformat(),
                "cpu_percent": 45.5,
                "memory_percent": 65.2,
                "disk_percent": 75.8
            }
        ]
        mock_service.resource_history = [
            {
                "timestamp": datetime.now(),
                "cpu_percent": 45.5,
                "memory_percent": 65.2,
                "disk_percent": 75.8,
                "memory_used_gb": 8.0,
                "disk_used_gb": 100.0
            }
        ]
        mock_service.collection_interval = 60
        
        response = client.get("/api/v1/resource-dashboard/trends?hours=1")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert "trends" in data["data"]
        assert "statistics" in data["data"]
    
    def test_get_resource_efficiency_analysis(self, client, mock_service):
        """Test getting resource efficiency analysis."""
        # Add enough history for analysis
        test_metrics = {
            "timestamp": datetime.now(),
            "cpu_percent": 45.5,
            "memory_percent": 65.2,
            "disk_percent": 75.8,
            "memory_used_gb": 8.0,
            "memory_available_gb": 4.0,
            "disk_used_gb": 100.0,
            "disk_free_gb": 32.0,
            "network_bytes_sent": 1073741824,
            "network_bytes_recv": 2147483648
        }
        mock_service.resource_history = [test_metrics] * 15
        mock_service.collection_interval = 60
        
        response = client.get("/api/v1/resource-dashboard/efficiency")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert "efficiency_score" in data["data"]
        assert "current_usage" in data["data"]
        assert "recommendations" in data["data"]
    
    def test_get_resource_dashboard_health(self, client, mock_service):
        """Test getting dashboard health status."""
        mock_service.resource_history = [{"timestamp": datetime.now()}]
        mock_service.monitoring_active = True
        mock_service.docker_available = True
        mock_service.active_alerts = []
        mock_service.optimization_recommendations = []
        mock_service.container_history = {}
        
        response = client.get("/api/v1/resource-dashboard/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert "overall_health" in data["data"]
        assert "components" in data["data"]
        assert "statistics" in data["data"]
    
    def test_update_resource_thresholds(self, client, mock_service):
        """Test updating resource thresholds."""
        new_thresholds = {
            "cpu_warning": 75.0,
            "memory_critical": 95.0
        }
        
        response = client.post("/api/v1/resource-dashboard/thresholds", json=new_thresholds)
        assert response.status_code == 200
        
        data = response.json()
        assert data["success"] is True
        assert "updated_thresholds" in data["data"]
    
    def test_update_invalid_thresholds(self, client, mock_service):
        """Test updating with invalid thresholds."""
        invalid_thresholds = {
            "invalid_threshold": 75.0,
            "cpu_warning": 150.0  # Invalid value > 100
        }
        
        response = client.post("/api/v1/resource-dashboard/thresholds", json=invalid_thresholds)
        assert response.status_code == 400

class TestResourceAlertAndOptimization:
    """Test resource alert and optimization classes."""
    
    def test_resource_alert_creation(self):
        """Test creating a resource alert."""
        alert = ResourceAlert(
            alert_id="test_alert",
            resource_type=ResourceType.CPU,
            severity="warning",
            message="CPU usage high",
            current_value=85.5,
            threshold=80.0,
            timestamp=datetime.now()
        )
        
        assert alert.alert_id == "test_alert"
        assert alert.resource_type == ResourceType.CPU
        assert alert.severity == "warning"
        assert alert.current_value == 85.5
        
        # Test to_dict method
        alert_dict = alert.to_dict()
        assert alert_dict["alert_id"] == "test_alert"
        assert alert_dict["resource_type"] == "cpu"
        assert alert_dict["severity"] == "warning"
    
    def test_resource_optimization_creation(self):
        """Test creating a resource optimization."""
        optimization = ResourceOptimization(
            optimization_id="test_opt",
            resource_type=ResourceType.MEMORY,
            priority="high",
            title="Reduce Memory Usage",
            description="Memory usage is too high",
            impact="High performance impact",
            implementation_effort="Medium",
            estimated_savings="20% memory reduction"
        )
        
        assert optimization.optimization_id == "test_opt"
        assert optimization.resource_type == ResourceType.MEMORY
        assert optimization.priority == "high"
        assert optimization.estimated_savings == "20% memory reduction"
        
        # Test to_dict method
        opt_dict = optimization.to_dict()
        assert opt_dict["optimization_id"] == "test_opt"
        assert opt_dict["resource_type"] == "memory"
        assert opt_dict["priority"] == "high"

if __name__ == "__main__":
    pytest.main([__file__])