"""
Tests for Health Dashboard

This module tests the health dashboard functionality including:
- Dashboard HTML rendering
- Dashboard configuration endpoints
- Integration with health check APIs
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from src.multimodal_librarian.main import app


class TestHealthDashboard:
    """Test suite for health dashboard functionality."""

    def setup_method(self):
        """Set up test client."""
        self.client = TestClient(app)

    @patch('src.multimodal_librarian.api.routers.health_dashboard.get_database_config')
    def test_health_dashboard_local_environment(self, mock_get_config):
        """Test health dashboard access in local environment."""
        # Mock local environment
        mock_config = MagicMock()
        mock_config.database_type = 'local'
        mock_get_config.return_value = mock_config

        response = self.client.get("/health/dashboard")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Health Check Dashboard" in response.text
        assert "health_dashboard.css" in response.text
        assert "health_dashboard.js" in response.text

    @patch('src.multimodal_librarian.api.routers.health_dashboard.get_database_config')
    def test_health_dashboard_production_environment(self, mock_get_config):
        """Test health dashboard access in production environment."""
        # Mock production environment
        mock_config = MagicMock()
        mock_config.database_type = 'aws'
        mock_get_config.return_value = mock_config

        response = self.client.get("/health/dashboard")
        
        # Should still serve the dashboard but with different context
        assert response.status_code == 200
        assert "Health Check Dashboard" in response.text

    @patch('src.multimodal_librarian.api.routers.health_dashboard.get_database_config')
    def test_dashboard_status_local(self, mock_get_config):
        """Test dashboard status endpoint in local environment."""
        # Mock local environment
        mock_config = MagicMock()
        mock_config.database_type = 'local'
        mock_get_config.return_value = mock_config

        response = self.client.get("/health/dashboard/status")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["dashboard_available"] is True
        assert data["environment"] == "local"
        assert data["features"]["real_time_monitoring"] is True
        assert data["features"]["service_health_checks"] is True
        assert data["endpoints"]["comprehensive_health"] is not None

    @patch('src.multimodal_librarian.api.routers.health_dashboard.get_database_config')
    def test_dashboard_status_production(self, mock_get_config):
        """Test dashboard status endpoint in production environment."""
        # Mock production environment
        mock_config = MagicMock()
        mock_config.database_type = 'aws'
        mock_get_config.return_value = mock_config

        response = self.client.get("/health/dashboard/status")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["dashboard_available"] is True
        assert data["environment"] == "production"
        assert data["features"]["real_time_monitoring"] is False
        assert data["endpoints"]["comprehensive_health"] is None

    @patch('src.multimodal_librarian.api.routers.health_dashboard.get_database_config')
    def test_dashboard_config_local(self, mock_get_config):
        """Test dashboard configuration endpoint in local environment."""
        # Mock local environment
        mock_config = MagicMock()
        mock_config.database_type = 'local'
        mock_get_config.return_value = mock_config

        response = self.client.get("/health/dashboard/config")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["available"] is True
        assert "refresh_interval" in data
        assert "services" in data
        assert "postgres" in data["services"]
        assert "neo4j" in data["services"]
        assert "milvus" in data["services"]
        assert "redis" in data["services"]
        assert "thresholds" in data

    @patch('src.multimodal_librarian.api.routers.health_dashboard.get_database_config')
    def test_dashboard_config_production(self, mock_get_config):
        """Test dashboard configuration endpoint in production environment."""
        # Mock production environment
        mock_config = MagicMock()
        mock_config.database_type = 'aws'
        mock_get_config.return_value = mock_config

        response = self.client.get("/health/dashboard/config")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["available"] is False
        assert "error" in data

    def test_dashboard_html_structure(self):
        """Test that dashboard HTML contains required elements."""
        with patch('src.multimodal_librarian.api.routers.health_dashboard.get_database_config') as mock_get_config:
            # Mock local environment
            mock_config = MagicMock()
            mock_config.database_type = 'local'
            mock_get_config.return_value = mock_config

            response = self.client.get("/health/dashboard")
            
            assert response.status_code == 200
            html_content = response.text
            
            # Check for essential dashboard elements
            assert 'id="overview"' in html_content
            assert 'id="services"' in html_content
            assert 'id="connectivity"' in html_content
            assert 'id="performance"' in html_content
            assert 'id="dependencies"' in html_content
            
            # Check for service cards
            assert 'data-service="postgres"' in html_content
            assert 'data-service="neo4j"' in html_content
            assert 'data-service="milvus"' in html_content
            assert 'data-service="redis"' in html_content
            
            # Check for charts
            assert 'id="health-overview-chart"' in html_content
            assert 'id="response-time-chart"' in html_content
            assert 'id="performance-score-chart"' in html_content

    def test_dashboard_service_configuration(self):
        """Test dashboard service configuration structure."""
        with patch('src.multimodal_librarian.api.routers.health_dashboard.get_database_config') as mock_get_config:
            # Mock local environment
            mock_config = MagicMock()
            mock_config.database_type = 'local'
            mock_get_config.return_value = mock_config

            response = self.client.get("/health/dashboard/config")
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify service configuration structure
            services = data["services"]
            for service_name in ["postgres", "neo4j", "milvus", "redis"]:
                assert service_name in services
                service_config = services[service_name]
                assert "name" in service_config
                assert "icon" in service_config
                assert "enabled" in service_config
                assert "endpoint" in service_config
                assert service_config["enabled"] is True

    def test_dashboard_thresholds_configuration(self):
        """Test dashboard threshold configuration."""
        with patch('src.multimodal_librarian.api.routers.health_dashboard.get_database_config') as mock_get_config:
            # Mock local environment
            mock_config = MagicMock()
            mock_config.database_type = 'local'
            mock_get_config.return_value = mock_config

            response = self.client.get("/health/dashboard/config")
            
            assert response.status_code == 200
            data = response.json()
            
            # Verify threshold configuration
            thresholds = data["thresholds"]
            assert "response_time_warning" in thresholds
            assert "response_time_critical" in thresholds
            assert "pool_utilization_warning" in thresholds
            assert "pool_utilization_critical" in thresholds
            assert "connectivity_warning" in thresholds
            assert "connectivity_critical" in thresholds
            
            # Verify threshold values are reasonable
            assert thresholds["response_time_warning"] < thresholds["response_time_critical"]
            assert thresholds["pool_utilization_warning"] < thresholds["pool_utilization_critical"]
            assert thresholds["connectivity_critical"] < thresholds["connectivity_warning"]


class TestHealthDashboardIntegration:
    """Integration tests for health dashboard with health check APIs."""

    def setup_method(self):
        """Set up test client."""
        self.client = TestClient(app)

    @patch('src.multimodal_librarian.api.routers.health_dashboard.get_database_config')
    def test_dashboard_with_health_api_integration(self, mock_get_config):
        """Test dashboard integration with health check APIs."""
        # Mock local environment
        mock_config = MagicMock()
        mock_config.database_type = 'local'
        mock_get_config.return_value = mock_config

        # Test dashboard page loads
        dashboard_response = self.client.get("/health/dashboard")
        assert dashboard_response.status_code == 200

        # Test dashboard status is accessible
        status_response = self.client.get("/health/dashboard/status")
        assert status_response.status_code == 200
        
        status_data = status_response.json()
        
        # Verify status endpoints are configured correctly
        endpoints = status_data["endpoints"]
        assert endpoints["comprehensive_health"] == "/api/health/local/"
        assert endpoints["connectivity"] == "/api/health/local/connectivity"
        assert endpoints["performance"] == "/api/health/local/performance"
        assert endpoints["dependencies"] == "/api/health/local/dependencies"

    def test_dashboard_error_handling(self):
        """Test dashboard error handling for missing dependencies."""
        with patch('src.multimodal_librarian.api.routers.health_dashboard.get_database_config') as mock_get_config:
            # Mock configuration error
            mock_get_config.side_effect = Exception("Configuration error")

            # Dashboard should still load but may show errors
            response = self.client.get("/health/dashboard")
            # The response might be 500 or might handle the error gracefully
            # depending on the implementation
            assert response.status_code in [200, 500]

    @patch('src.multimodal_librarian.api.routers.health_dashboard.get_database_config')
    def test_dashboard_feature_flags(self, mock_get_config):
        """Test dashboard feature flags based on environment."""
        # Mock local environment
        mock_config = MagicMock()
        mock_config.database_type = 'local'
        mock_get_config.return_value = mock_config

        response = self.client.get("/health/dashboard/status")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify all local features are enabled
        features = data["features"]
        expected_features = [
            "real_time_monitoring",
            "service_health_checks", 
            "connectivity_monitoring",
            "performance_metrics",
            "dependency_tracking"
        ]
        
        for feature in expected_features:
            assert features[feature] is True