"""
Health Check Integration Tests

This module tests health check endpoints with real server instances
to validate actual reliability and performance in realistic conditions.

Tests cover:
- Real HTTP server health check responses
- Actual startup phase transitions
- Real timing measurements
- Integration with minimal server and phase manager
- End-to-end health check workflows

Feature: application-health-startup-optimization
Requirements: REQ-1, REQ-5
"""

import asyncio
import pytest
import time
import requests
import threading
from datetime import datetime
from typing import Dict, Any
from unittest.mock import patch
import uvicorn
from fastapi import FastAPI

from src.multimodal_librarian.api.routers.health import router as health_router
from src.multimodal_librarian.startup.minimal_server import MinimalServer, initialize_minimal_server
from src.multimodal_librarian.startup.phase_manager import StartupPhaseManager, StartupPhase


class TestHealthCheckIntegration:
    """Integration tests with real server instances."""
    
    @pytest.fixture
    def test_app(self):
        """Create test FastAPI application."""
        app = FastAPI(title="Health Check Test App")
        app.include_router(health_router)
        return app
    
    @pytest.fixture
    async def minimal_server(self):
        """Create and initialize real minimal server."""
        server = await initialize_minimal_server()
        yield server
        await server.shutdown()
    
    @pytest.fixture
    def phase_manager(self):
        """Create real startup phase manager."""
        manager = StartupPhaseManager()
        yield manager
        # Cleanup
        asyncio.create_task(manager.shutdown())
    
    @pytest.mark.asyncio
    async def test_real_minimal_server_health_checks(self, minimal_server):
        """Test health checks with real minimal server instance."""
        # Wait for server to be ready
        await asyncio.sleep(1)
        
        # Test server status
        status = minimal_server.get_status()
        assert status.health_check_ready is True
        assert status.status.value in ["minimal", "essential", "ready"]
        
        # Test capabilities
        assert "health_endpoints" in status.capabilities
        assert status.capabilities["health_endpoints"] is True
        
        # Test queue functionality
        queue_status = minimal_server.get_queue_status()
        assert "queue_size" in queue_status
        assert "processed_requests" in queue_status
    
    @pytest.mark.asyncio
    async def test_phase_manager_health_integration(self, phase_manager):
        """Test health checks during real phase transitions."""
        # Start phase progression
        await phase_manager.start_phase_progression()
        
        # Wait for minimal phase
        await asyncio.sleep(2)
        
        # Check minimal phase status
        status = phase_manager.get_current_status()
        assert status.current_phase == StartupPhase.MINIMAL
        assert status.health_check_ready is True
        
        # Get phase health status
        health_status = phase_manager.get_phase_health_status()
        assert health_status["healthy"] is True
        assert health_status["ready_for_traffic"] is True
        assert health_status["health_check_ready"] is True
    
    @pytest.mark.asyncio
    async def test_health_check_timing_integration(self, test_app, minimal_server):
        """Test actual health check response times with real server."""
        from fastapi.testclient import TestClient
        
        client = TestClient(test_app)
        
        # Test multiple endpoints for timing
        endpoints = [
            "/api/health/minimal",
            "/api/health/simple",
            "/api/health/ready",
            "/api/health/startup"
        ]
        
        response_times = {}
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=minimal_server):
            for endpoint in endpoints:
                start_time = time.time()
                response = client.get(endpoint)
                end_time = time.time()
                
                response_time = end_time - start_time
                response_times[endpoint] = response_time
                
                # All endpoints should respond quickly
                assert response_time < 1.0
                assert response.status_code in [200, 503]  # Either healthy or not ready
        
        # Log timing results for analysis
        print(f"\nHealth check response times: {response_times}")
        
        # Check that simple endpoint is fastest (for load balancers)
        assert response_times["/api/health/simple"] <= min(response_times.values())
    
    @pytest.mark.asyncio
    async def test_concurrent_health_check_integration(self, test_app, minimal_server):
        """Test concurrent health checks with real server."""
        from fastapi.testclient import TestClient
        import concurrent.futures
        
        client = TestClient(test_app)
        
        def make_health_request():
            start_time = time.time()
            response = client.get("/api/health/minimal")
            end_time = time.time()
            return {
                "status_code": response.status_code,
                "response_time": end_time - start_time,
                "data": response.json()
            }
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=minimal_server):
            # Make 20 concurrent requests
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(make_health_request) for _ in range(20)]
                results = [future.result() for future in concurrent.futures.as_completed(futures)]
            
            # Analyze results
            status_codes = [r["status_code"] for r in results]
            response_times = [r["response_time"] for r in results]
            
            # All requests should succeed
            assert all(code in [200, 503] for code in status_codes)
            
            # Response times should be consistent
            max_time = max(response_times)
            avg_time = sum(response_times) / len(response_times)
            
            assert max_time < 2.0  # Even under load
            assert avg_time < 0.5  # Average should be fast
            
            print(f"\nConcurrent test - Max: {max_time:.3f}s, Avg: {avg_time:.3f}s")
    
    @pytest.mark.asyncio
    async def test_health_check_during_model_loading(self, test_app, minimal_server):
        """Test health checks remain responsive during model loading simulation."""
        from fastapi.testclient import TestClient
        
        client = TestClient(test_app)
        
        # Simulate model loading by updating server status
        original_get_status = minimal_server.get_status
        
        def get_status_with_loading():
            status = original_get_status()
            # Simulate some models loading
            status.model_statuses.update({
                "text-embedding-small": "loading",
                "chat-model-base": "loading",
                "search-index": "pending"
            })
            status.estimated_ready_times.update({
                "basic_chat": 45.0,
                "simple_search": 90.0
            })
            return status
        
        minimal_server.get_status = get_status_with_loading
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=minimal_server):
            # Test health checks during "loading"
            response = client.get("/api/health/minimal")
            assert response.status_code == 200  # Should still be healthy
            
            response = client.get("/api/health/ready")
            assert response.status_code == 503  # Not ready yet
            
            response = client.get("/api/health/startup")
            assert response.status_code == 200
            data = response.json()
            assert "model_progress" in data
            assert data["model_progress"]["loading_models"] > 0
    
    def test_ecs_health_check_command_integration(self, test_app, minimal_server):
        """Test the actual ECS health check command with real server."""
        from fastapi.testclient import TestClient
        
        client = TestClient(test_app)
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=minimal_server):
            # Simulate the exact curl command used in ECS
            # curl -f http://localhost:8000/api/health/minimal || exit 1
            
            response = client.get("/api/health/minimal")
            
            # ECS expects:
            # - HTTP 200 for healthy (curl -f succeeds)
            # - HTTP 4xx/5xx for unhealthy (curl -f fails)
            assert response.status_code == 200
            
            # Response should be valid JSON
            data = response.json()
            assert isinstance(data, dict)
            assert "status" in data
            assert data["status"] in ["healthy", "starting"]
            
            # Response should be fast (ECS timeout is 15s)
            # This is tested implicitly by the test completing quickly


class TestHealthCheckReliabilityScenarios:
    """Test health check reliability in various failure scenarios."""
    
    @pytest.fixture
    def test_app(self):
        """Create test FastAPI application."""
        app = FastAPI(title="Health Check Reliability Test")
        app.include_router(health_router)
        return app
    
    def test_health_check_with_server_errors(self, test_app):
        """Test health check behavior when server has errors."""
        from fastapi.testclient import TestClient
        from unittest.mock import Mock
        
        client = TestClient(test_app)
        
        # Create mock server with errors
        error_server = Mock()
        error_server.get_status.side_effect = Exception("Database connection failed")
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=error_server):
            response = client.get("/api/health/minimal")
            
            # Should return 503 with error information
            assert response.status_code == 503
            data = response.json()
            assert data["status"] == "error"
            assert "error" in data
            assert data["ready"] is False
    
    def test_health_check_with_slow_responses(self, test_app):
        """Test health check behavior with slow server responses."""
        from fastapi.testclient import TestClient
        from unittest.mock import Mock
        
        client = TestClient(test_app)
        
        # Create mock server with slow responses
        slow_server = Mock()
        
        def slow_get_status():
            time.sleep(0.1)  # 100ms delay
            status = Mock()
            status.status.value = "minimal"
            status.health_check_ready = True
            status.uptime_seconds = 60.0
            status.capabilities = {"health_endpoints": True}
            status.model_statuses = {}
            status.estimated_ready_times = {}
            status.processed_requests = 0
            status.failed_requests = 0
            return status
        
        slow_server.get_status.side_effect = slow_get_status
        slow_server.get_queue_status.return_value = {"queue_size": 0}
        slow_server.request_queue = []
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=slow_server):
            start_time = time.time()
            response = client.get("/api/health/minimal")
            end_time = time.time()
            
            response_time = end_time - start_time
            
            # Should still respond successfully but with delay
            assert response.status_code == 200
            assert response_time >= 0.1  # At least the delay we added
            assert response_time < 5.0   # But still under timeout
    
    def test_health_check_memory_usage(self, test_app):
        """Test health check memory usage remains reasonable."""
        from fastapi.testclient import TestClient
        from unittest.mock import Mock
        import psutil
        import os
        
        client = TestClient(test_app)
        
        # Create mock server
        mock_server = Mock()
        status = Mock()
        status.status.value = "minimal"
        status.health_check_ready = True
        status.uptime_seconds = 30.0
        status.capabilities = {"health_endpoints": True}
        status.model_statuses = {}
        status.estimated_ready_times = {}
        status.processed_requests = 0
        status.failed_requests = 0
        
        mock_server.get_status.return_value = status
        mock_server.get_queue_status.return_value = {"queue_size": 0}
        
        # Measure memory before
        process = psutil.Process(os.getpid())
        memory_before = process.memory_info().rss
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=mock_server):
            # Make many health check requests
            for _ in range(100):
                response = client.get("/api/health/minimal")
                assert response.status_code == 200
        
        # Measure memory after
        memory_after = process.memory_info().rss
        memory_increase = memory_after - memory_before
        
        # Memory increase should be minimal (less than 10MB)
        assert memory_increase < 10 * 1024 * 1024
        
        print(f"\nMemory increase after 100 health checks: {memory_increase / 1024 / 1024:.2f} MB")


class TestHealthCheckPerformanceBaseline:
    """Establish performance baselines for health check endpoints."""
    
    @pytest.fixture
    def test_app(self):
        """Create test FastAPI application."""
        app = FastAPI(title="Health Check Performance Test")
        app.include_router(health_router)
        return app
    
    def test_health_check_performance_baseline(self, test_app):
        """Establish performance baselines for monitoring."""
        from fastapi.testclient import TestClient
        from unittest.mock import Mock
        import statistics
        
        client = TestClient(test_app)
        
        # Create optimized mock server
        mock_server = Mock()
        status = Mock()
        status.status.value = "ready"
        status.health_check_ready = True
        status.uptime_seconds = 120.0
        status.capabilities = {
            "health_endpoints": True,
            "basic_chat": True,
            "simple_search": True
        }
        status.model_statuses = {
            "text-embedding-small": "loaded",
            "chat-model-base": "loaded",
            "search-index": "loaded"
        }
        status.estimated_ready_times = {}
        status.processed_requests = 100
        status.failed_requests = 2
        
        mock_server.get_status.return_value = status
        mock_server.get_queue_status.return_value = {
            "queue_size": 0,
            "processed_requests": 100,
            "failed_requests": 2
        }
        mock_server.request_queue = []
        
        # Test different endpoints
        endpoints = {
            "/api/health/simple": [],
            "/api/health/minimal": [],
            "/api/health/ready": [],
            "/api/health/startup": [],
            "/api/health/performance": []
        }
        
        with patch('src.multimodal_librarian.api.routers.health.get_minimal_server', return_value=mock_server):
            # Warm up
            for endpoint in endpoints.keys():
                client.get(endpoint)
            
            # Measure performance
            for _ in range(50):
                for endpoint in endpoints.keys():
                    start_time = time.time()
                    response = client.get(endpoint)
                    end_time = time.time()
                    
                    assert response.status_code == 200
                    endpoints[endpoint].append(end_time - start_time)
        
        # Analyze and report baselines
        baselines = {}
        for endpoint, times in endpoints.items():
            baselines[endpoint] = {
                "mean": statistics.mean(times),
                "median": statistics.median(times),
                "p95": sorted(times)[int(len(times) * 0.95)],
                "max": max(times),
                "min": min(times)
            }
        
        print("\nHealth Check Performance Baselines:")
        for endpoint, metrics in baselines.items():
            print(f"{endpoint}:")
            print(f"  Mean: {metrics['mean']*1000:.2f}ms")
            print(f"  P95:  {metrics['p95']*1000:.2f}ms")
            print(f"  Max:  {metrics['max']*1000:.2f}ms")
        
        # Assert performance requirements
        for endpoint, metrics in baselines.items():
            assert metrics["mean"] < 0.1    # Mean under 100ms
            assert metrics["p95"] < 0.2     # P95 under 200ms
            assert metrics["max"] < 1.0     # Max under 1s


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v", "--tb=short", "-s"])