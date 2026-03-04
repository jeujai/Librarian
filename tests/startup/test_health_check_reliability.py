"""
Health Check Reliability Tests

This module tests the reliability and performance of health check endpoints
for the application health and startup optimization feature.

Tests cover:
- All health check endpoints (/minimal, /ready, /full, etc.)
- Health check timing and reliability during startup phases
- Response consistency under load
- Error handling and edge cases
- ECS health check compatibility
- Performance metrics and monitoring

Feature: application-health-startup-optimization
Requirements: REQ-1, REQ-5
"""

import asyncio
import pytest
import time
import json
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
from fastapi import FastAPI

from src.multimodal_librarian.api.routers.health import router as health_router
from src.multimodal_librarian.startup.minimal_server import MinimalServer, get_minimal_server
from src.multimodal_librarian.startup.phase_manager import StartupPhaseManager, StartupPhase


class TestHealthCheckEndpoints:
    """Test all health check endpoints for reliability and correctness."""
    
    @pytest.fixture
    def app(self):
        """Create FastAPI app with health router."""
        app = FastAPI()
        app.include_router(health_router)
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def mock_minimal_server(self):
        """Create mock minimal server with predictable status."""
        server = Mock(spec=MinimalServer)
        
        # Mock server status
        mock_status = Mock()
        mock_status.status.value = "minimal"
        mock_status.uptime_seconds = 45.0
        mock_status.health_check_ready = True
        mock_status.capabilities = {
            "health_endpoints": True,
            "basic_api": True,
            "basic_chat": False,
            "simple_search": False
        }
        mock_status.model_statuses = {
            "text-embedding-small": "loading",
            "chat-model-base": "pending",
            "search-index": "pending"
        }
        mock_status.estimated_ready_times = {
            "basic_chat": 30.0,
            "simple_search": 60.0
        }
        mock_status.processed_requests = 5
        mock_status.failed_requests = 0
        
        server.get_status.return_value = mock_status
        server.get_queue_status.return_value = {
            "queue_size": 2,
            "processed_requests": 5,
            "failed_requests": 0,
            "queued_requests": []
        }
        server.request_queue = []
        
        return server
    
    def test_minimal_health_check_success(self, client, mock_minimal_server):
        """Test /health/minimal endpoint returns success when server is ready."""
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=mock_minimal_server):
            response = client.get("/api/health/minimal")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "healthy"
            assert data["server_status"] == "minimal"
            assert data["ready"] is True
            assert data["uptime_seconds"] == 45.0
            assert "timestamp" in data
    
    def test_minimal_health_check_starting(self, client, mock_minimal_server):
        """Test /health/minimal endpoint returns 503 when server is starting."""
        # Modify mock to simulate starting state
        mock_minimal_server.get_status.return_value.health_check_ready = False
        mock_minimal_server.get_status.return_value.status.value = "starting"
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=mock_minimal_server):
            response = client.get("/api/health/minimal")
            
            assert response.status_code == 503
            data = response.json()
            
            assert data["status"] == "starting"
            assert data["ready"] is False
    
    def test_readiness_health_check_not_ready(self, client, mock_minimal_server):
        """Test /health/ready endpoint returns 503 when essential models not loaded."""
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=mock_minimal_server):
            response = client.get("/api/health/ready")
            
            assert response.status_code == 503
            data = response.json()
            
            assert data["status"] == "not_ready"
            assert data["essential_models_ready"] is False
            assert "capabilities" in data
            assert "model_statuses" in data
    
    def test_readiness_health_check_ready(self, client, mock_minimal_server):
        """Test /health/ready endpoint returns 200 when essential models are loaded."""
        # Modify mock to simulate ready state
        mock_minimal_server.get_status.return_value.capabilities["basic_chat"] = True
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=mock_minimal_server):
            response = client.get("/api/health/ready")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "ready"
            assert data["essential_models_ready"] is True
    
    def test_full_health_check_not_ready(self, client, mock_minimal_server):
        """Test /health/full endpoint returns 503 when not all models are loaded."""
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=mock_minimal_server):
            response = client.get("/api/health/full")
            
            assert response.status_code == 503
            data = response.json()
            
            assert data["status"] == "not_ready"
            assert data["all_models_ready"] is False
            assert "queue_status" in data
    
    def test_full_health_check_ready(self, client, mock_minimal_server):
        """Test /health/full endpoint returns 200 when all models are loaded."""
        # Modify mock to simulate fully ready state
        mock_minimal_server.get_status.return_value.status.value = "ready"
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=mock_minimal_server):
            response = client.get("/api/health/full")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "ready"
            assert data["all_models_ready"] is True
    
    def test_startup_health_check(self, client, mock_minimal_server):
        """Test /health/startup endpoint provides detailed startup information."""
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=mock_minimal_server):
            response = client.get("/api/health/startup")
            
            assert response.status_code == 200
            data = response.json()
            
            assert "startup_metrics" in data
            assert "model_progress" in data
            assert "phase" in data["startup_metrics"]
            assert "within_targets" in data["startup_metrics"]
            assert "progress_percent" in data["model_progress"]
    
    def test_simple_health_check(self, client, mock_minimal_server):
        """Test /health/simple endpoint for load balancer compatibility."""
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=mock_minimal_server):
            response = client.get("/api/health/simple")
            
            assert response.status_code == 200
            data = response.json()
            
            assert data["status"] == "ok"
            assert "timestamp" in data
    
    def test_comprehensive_health_check(self, client, mock_minimal_server):
        """Test /health/ endpoint provides complete health report."""
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=mock_minimal_server):
            response = client.get("/api/health/")
            
            assert response.status_code == 200
            data = response.json()
            
            assert "overall_status" in data
            assert "startup_phase" in data
            assert "health_checks" in data
            assert "performance" in data
            assert data["health_checks"]["minimal"] is True
    
    def test_health_check_error_handling(self, client):
        """Test health check endpoints handle errors gracefully."""
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', side_effect=Exception("Server error")):
            response = client.get("/api/health/minimal")
            
            assert response.status_code == 503
            data = response.json()
            
            assert data["status"] == "error"
            assert "error" in data
            assert data["ready"] is False


class TestHealthCheckTiming:
    """Test health check timing and performance requirements."""
    
    @pytest.fixture
    def mock_server_with_timing(self):
        """Create mock server with timing simulation."""
        server = Mock(spec=MinimalServer)
        
        def get_status_with_delay():
            # Simulate processing time
            time.sleep(0.001)  # 1ms delay
            
            mock_status = Mock()
            mock_status.status.value = "minimal"
            mock_status.uptime_seconds = 30.0
            mock_status.health_check_ready = True
            mock_status.capabilities = {"health_endpoints": True}
            mock_status.model_statuses = {}
            mock_status.estimated_ready_times = {}
            mock_status.processed_requests = 0
            mock_status.failed_requests = 0
            return mock_status
        
        server.get_status.side_effect = get_status_with_delay
        server.get_queue_status.return_value = {"queue_size": 0}
        server.request_queue = []
        
        return server
    
    def test_health_check_response_time(self, mock_server_with_timing):
        """Test health check endpoints respond within 5 seconds (REQ-5)."""
        app = FastAPI()
        app.include_router(health_router)
        client = TestClient(app)
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=mock_server_with_timing):
            start_time = time.time()
            response = client.get("/api/health/minimal")
            end_time = time.time()
            
            response_time = end_time - start_time
            
            assert response.status_code == 200
            assert response_time < 5.0  # Must respond within 5 seconds
            assert response_time < 1.0  # Should be much faster in practice
    
    def test_health_check_consistency(self, mock_server_with_timing):
        """Test health check response time consistency."""
        app = FastAPI()
        app.include_router(health_router)
        client = TestClient(app)
        
        response_times = []
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=mock_server_with_timing):
            # Test 20 consecutive requests
            for _ in range(20):
                start_time = time.time()
                response = client.get("/api/health/minimal")
                end_time = time.time()
                
                assert response.status_code == 200
                response_times.append(end_time - start_time)
        
        # Check consistency
        avg_time = statistics.mean(response_times)
        max_time = max(response_times)
        std_dev = statistics.stdev(response_times)
        
        assert avg_time < 0.1  # Average should be under 100ms
        assert max_time < 1.0  # No request should take over 1 second
        assert std_dev < 0.05  # Low standard deviation indicates consistency
    
    def test_concurrent_health_checks(self, mock_server_with_timing):
        """Test health check performance under concurrent load."""
        app = FastAPI()
        app.include_router(health_router)
        client = TestClient(app)
        
        def make_request():
            start_time = time.time()
            response = client.get("/api/health/minimal")
            end_time = time.time()
            return response.status_code, end_time - start_time
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=mock_server_with_timing):
            # Simulate concurrent requests
            import concurrent.futures
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(make_request) for _ in range(50)]
                results = [future.result() for future in concurrent.futures.as_completed(futures)]
            
            # Check all requests succeeded
            status_codes = [result[0] for result in results]
            response_times = [result[1] for result in results]
            
            assert all(code == 200 for code in status_codes)
            assert max(response_times) < 2.0  # Even under load, should be fast
            assert statistics.mean(response_times) < 0.5


class TestHealthCheckReliability:
    """Test health check reliability during different startup phases."""
    
    @pytest.fixture
    def phase_manager(self):
        """Create startup phase manager for testing."""
        return StartupPhaseManager()
    
    @pytest.fixture
    def app_with_phase_manager(self, phase_manager):
        """Create app with phase manager integration."""
        app = FastAPI()
        app.include_router(health_router)
        return app
    
    def test_health_check_during_minimal_phase(self, phase_manager):
        """Test health checks work correctly during minimal startup phase."""
        # Simulate minimal phase
        phase_manager.current_phase = StartupPhase.MINIMAL
        phase_manager.status.health_check_ready = True
        phase_manager.status.capabilities = {"health_endpoints": True}
        
        # Create mock server based on phase manager state
        server = Mock(spec=MinimalServer)
        mock_status = Mock()
        mock_status.status.value = "minimal"
        mock_status.health_check_ready = True
        mock_status.capabilities = phase_manager.status.capabilities
        mock_status.uptime_seconds = 25.0
        mock_status.model_statuses = {}
        mock_status.estimated_ready_times = {"basic_chat": 60.0}
        mock_status.processed_requests = 0
        mock_status.failed_requests = 0
        
        server.get_status.return_value = mock_status
        server.get_queue_status.return_value = {"queue_size": 0}
        
        app = FastAPI()
        app.include_router(health_router)
        client = TestClient(app)
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=server):
            # Test minimal health check
            response = client.get("/api/health/minimal")
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"
            
            # Test readiness check (should not be ready yet)
            response = client.get("/api/health/ready")
            assert response.status_code == 503
            assert response.json()["status"] == "not_ready"
    
    def test_health_check_during_essential_phase(self, phase_manager):
        """Test health checks work correctly during essential startup phase."""
        # Simulate essential phase
        phase_manager.current_phase = StartupPhase.ESSENTIAL
        phase_manager.status.health_check_ready = True
        phase_manager.status.capabilities = {
            "health_endpoints": True,
            "basic_chat": True,
            "simple_search": False
        }
        
        server = Mock(spec=MinimalServer)
        mock_status = Mock()
        mock_status.status.value = "essential"
        mock_status.health_check_ready = True
        mock_status.capabilities = phase_manager.status.capabilities
        mock_status.uptime_seconds = 90.0
        mock_status.model_statuses = {
            "text-embedding-small": "loaded",
            "chat-model-base": "loaded",
            "search-index": "loading"
        }
        mock_status.estimated_ready_times = {"simple_search": 30.0}
        mock_status.processed_requests = 10
        mock_status.failed_requests = 0
        
        server.get_status.return_value = mock_status
        server.get_queue_status.return_value = {"queue_size": 1}
        
        app = FastAPI()
        app.include_router(health_router)
        client = TestClient(app)
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=server):
            # Test minimal health check
            response = client.get("/api/health/minimal")
            assert response.status_code == 200
            
            # Test readiness check (should be ready with basic chat)
            response = client.get("/api/health/ready")
            assert response.status_code == 200
            assert response.json()["status"] == "ready"
            
            # Test full check (should not be fully ready yet)
            response = client.get("/api/health/full")
            assert response.status_code == 503
    
    def test_health_check_during_full_phase(self, phase_manager):
        """Test health checks work correctly during full startup phase."""
        # Simulate full phase
        phase_manager.current_phase = StartupPhase.FULL
        phase_manager.status.health_check_ready = True
        phase_manager.status.capabilities = {
            "health_endpoints": True,
            "basic_chat": True,
            "simple_search": True,
            "advanced_ai": True,
            "document_analysis": True
        }
        
        server = Mock(spec=MinimalServer)
        mock_status = Mock()
        mock_status.status.value = "ready"
        mock_status.health_check_ready = True
        mock_status.capabilities = phase_manager.status.capabilities
        mock_status.uptime_seconds = 300.0
        mock_status.model_statuses = {
            "text-embedding-small": "loaded",
            "chat-model-base": "loaded",
            "search-index": "loaded",
            "chat-model-large": "loaded",
            "document-processor": "loaded"
        }
        mock_status.estimated_ready_times = {}
        mock_status.processed_requests = 50
        mock_status.failed_requests = 1
        
        server.get_status.return_value = mock_status
        server.get_queue_status.return_value = {"queue_size": 0}
        
        app = FastAPI()
        app.include_router(health_router)
        client = TestClient(app)
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=server):
            # All health checks should pass
            response = client.get("/api/health/minimal")
            assert response.status_code == 200
            
            response = client.get("/api/health/ready")
            assert response.status_code == 200
            
            response = client.get("/api/health/full")
            assert response.status_code == 200
            assert response.json()["status"] == "ready"


class TestECSHealthCheckCompatibility:
    """Test health check compatibility with AWS ECS requirements."""
    
    def test_ecs_health_check_command(self):
        """Test that the ECS health check command works correctly."""
        app = FastAPI()
        app.include_router(health_router)
        client = TestClient(app)
        
        # Mock server in healthy state
        server = Mock(spec=MinimalServer)
        mock_status = Mock()
        mock_status.status.value = "minimal"
        mock_status.health_check_ready = True
        mock_status.uptime_seconds = 45.0
        mock_status.capabilities = {"health_endpoints": True}
        mock_status.model_statuses = {}
        mock_status.estimated_ready_times = {}
        mock_status.processed_requests = 0
        mock_status.failed_requests = 0
        
        server.get_status.return_value = mock_status
        server.get_queue_status.return_value = {"queue_size": 0}
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=server):
            # Test the exact endpoint used in ECS health check
            response = client.get("/api/health/minimal")
            
            # Should return 200 for healthy state (ECS expects this)
            assert response.status_code == 200
            
            # Response should be JSON (curl -f will succeed)
            data = response.json()
            assert isinstance(data, dict)
            assert "status" in data
    
    def test_ecs_health_check_failure_scenarios(self):
        """Test ECS health check behavior during failure scenarios."""
        app = FastAPI()
        app.include_router(health_router)
        client = TestClient(app)
        
        # Test server not ready
        server = Mock(spec=MinimalServer)
        mock_status = Mock()
        mock_status.status.value = "starting"
        mock_status.health_check_ready = False
        mock_status.uptime_seconds = 10.0
        mock_status.capabilities = {}
        mock_status.model_statuses = {}
        mock_status.estimated_ready_times = {}
        mock_status.processed_requests = 0
        mock_status.failed_requests = 0
        
        server.get_status.return_value = mock_status
        server.get_queue_status.return_value = {"queue_size": 0}
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=server):
            response = client.get("/api/health/minimal")
            
            # Should return 503 for not ready (ECS will retry)
            assert response.status_code == 503
            
            data = response.json()
            assert data["status"] == "starting"
            assert data["ready"] is False
    
    def test_ecs_health_check_timing_requirements(self):
        """Test health check meets ECS timing requirements."""
        # ECS configuration: interval=30s, timeout=15s, retries=5, startPeriod=300s
        
        app = FastAPI()
        app.include_router(health_router)
        client = TestClient(app)
        
        server = Mock(spec=MinimalServer)
        mock_status = Mock()
        mock_status.status.value = "minimal"
        mock_status.health_check_ready = True
        mock_status.uptime_seconds = 45.0
        mock_status.capabilities = {"health_endpoints": True}
        mock_status.model_statuses = {}
        mock_status.estimated_ready_times = {}
        mock_status.processed_requests = 0
        mock_status.failed_requests = 0
        
        server.get_status.return_value = mock_status
        server.get_queue_status.return_value = {"queue_size": 0}
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=server):
            # Test response time is well under ECS timeout (15s)
            start_time = time.time()
            response = client.get("/api/health/minimal")
            end_time = time.time()
            
            response_time = end_time - start_time
            
            assert response.status_code == 200
            assert response_time < 10.0  # Well under 15s timeout
            assert response_time < 1.0   # Should be much faster
    
    def test_startup_period_behavior(self):
        """Test health check behavior during ECS startPeriod (300s)."""
        app = FastAPI()
        app.include_router(health_router)
        client = TestClient(app)
        
        # Test different uptime scenarios within startup period
        test_scenarios = [
            (15.0, "starting", False),   # Very early startup
            (45.0, "minimal", True),     # Minimal phase reached
            (120.0, "essential", True),  # Essential phase
            (280.0, "ready", True),      # Near end of startup period
        ]
        
        for uptime, expected_status, should_be_ready in test_scenarios:
            server = Mock(spec=MinimalServer)
            mock_status = Mock()
            mock_status.status.value = expected_status
            mock_status.health_check_ready = should_be_ready
            mock_status.uptime_seconds = uptime
            mock_status.capabilities = {"health_endpoints": True} if should_be_ready else {}
            mock_status.model_statuses = {}
            mock_status.estimated_ready_times = {}
            mock_status.processed_requests = 0
            mock_status.failed_requests = 0
            
            server.get_status.return_value = mock_status
            server.get_queue_status.return_value = {"queue_size": 0}
            
            with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=server):
                response = client.get("/api/health/minimal")
                
                if should_be_ready:
                    assert response.status_code == 200
                    assert response.json()["status"] == "healthy"
                else:
                    assert response.status_code == 503
                    assert response.json()["status"] == "starting"


class TestHealthCheckMonitoring:
    """Test health check monitoring and metrics collection."""
    
    def test_health_check_metrics_collection(self):
        """Test that health checks provide useful metrics for monitoring."""
        app = FastAPI()
        app.include_router(health_router)
        client = TestClient(app)
        
        server = Mock(spec=MinimalServer)
        mock_status = Mock()
        mock_status.status.value = "essential"
        mock_status.health_check_ready = True
        mock_status.uptime_seconds = 150.0
        mock_status.capabilities = {
            "health_endpoints": True,
            "basic_chat": True,
            "simple_search": False
        }
        mock_status.model_statuses = {
            "text-embedding-small": "loaded",
            "chat-model-base": "loaded",
            "search-index": "loading",
            "chat-model-large": "pending"
        }
        mock_status.estimated_ready_times = {
            "simple_search": 30.0,
            "full_capabilities": 180.0
        }
        mock_status.processed_requests = 25
        mock_status.failed_requests = 2
        
        server.get_status.return_value = mock_status
        server.get_queue_status.return_value = {
            "queue_size": 3,
            "processed_requests": 25,
            "failed_requests": 2
        }
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=server):
            # Test performance health check
            response = client.get("/api/health/performance")
            
            assert response.status_code == 200
            data = response.json()
            
            # Check metrics are present
            assert "performance_score" in data
            assert "performance_grade" in data
            assert "metrics" in data
            
            metrics = data["metrics"]
            assert "startup_time_seconds" in metrics
            assert "queue_processing_rate" in metrics
            assert "error_rate" in metrics
            assert "within_startup_targets" in metrics
            
            # Check performance scoring
            assert isinstance(data["performance_score"], (int, float))
            assert 0 <= data["performance_score"] <= 100
            assert data["performance_grade"] in ["excellent", "good", "acceptable", "poor"]
    
    def test_health_check_alerting_data(self):
        """Test health checks provide data suitable for alerting systems."""
        app = FastAPI()
        app.include_router(health_router)
        client = TestClient(app)
        
        # Test scenario with some issues
        server = Mock(spec=MinimalServer)
        mock_status = Mock()
        mock_status.status.value = "essential"
        mock_status.health_check_ready = True
        mock_status.uptime_seconds = 200.0  # Taking longer than expected
        mock_status.capabilities = {"health_endpoints": True, "basic_chat": True}
        mock_status.model_statuses = {
            "text-embedding-small": "loaded",
            "chat-model-base": "failed",  # Failed model
            "search-index": "loading"
        }
        mock_status.estimated_ready_times = {"simple_search": 120.0}  # Long wait
        mock_status.processed_requests = 15
        mock_status.failed_requests = 5  # High error rate
        
        server.get_status.return_value = mock_status
        server.get_queue_status.return_value = {"queue_size": 10}  # Large queue
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=server):
            # Test startup health check for alerting data
            response = client.get("/api/health/startup")
            
            assert response.status_code == 200
            data = response.json()
            
            # Check alerting-relevant data
            assert "startup_metrics" in data
            assert "model_progress" in data
            
            startup_metrics = data["startup_metrics"]
            assert "within_targets" in startup_metrics
            
            model_progress = data["model_progress"]
            assert "failed_models" in model_progress
            assert model_progress["failed_models"] > 0  # Should detect failed model
            
            # Check queue status for alerting
            assert "queue_status" in data
            queue_status = data["queue_status"]
            assert queue_status["queue_size"] > 5  # Should detect large queue


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])