"""
Cold Start Optimization Tests

This module tests the cold start optimization functionality to ensure
that startup times are minimized while maintaining functionality.
"""

import pytest
import asyncio
import time
import os
import subprocess
import requests
from typing import Dict, Any, Optional
from unittest.mock import patch, MagicMock

# Test configuration
COLD_START_TIMEOUT = 120  # Maximum time to wait for cold start
HEALTH_CHECK_TIMEOUT = 30  # Maximum time to wait for health check
EXPECTED_COLD_START_TIME = 60  # Expected cold start time in seconds


class TestColdStartOptimization:
    """Test suite for cold start optimization functionality."""
    
    @pytest.fixture(autouse=True)
    def setup_cold_start_env(self):
        """Set up environment variables for cold start testing."""
        # Store original values
        original_env = {}
        cold_start_vars = {
            "COLD_START_OPTIMIZATION": "true",
            "STARTUP_MODE": "fast",
            "LAZY_LOAD_MODELS": "true",
            "LAZY_LOAD_SERVICES": "true",
            "BACKGROUND_INIT_ENABLED": "true",
            "FAST_HEALTH_CHECKS": "true",
            "HEALTH_CHECK_TIMEOUT": "2.0"
        }
        
        for key, value in cold_start_vars.items():
            original_env[key] = os.environ.get(key)
            os.environ[key] = value
        
        yield
        
        # Restore original values
        for key, original_value in original_env.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value
    
    def test_cold_start_optimizer_initialization(self):
        """Test that the cold start optimizer initializes correctly."""
        from multimodal_librarian.startup.cold_start_optimizer import (
            get_cold_start_optimizer,
            is_cold_start_mode,
            get_startup_mode
        )
        
        # Test environment detection
        assert is_cold_start_mode() is True
        assert get_startup_mode() == "fast"
        
        # Test optimizer initialization
        optimizer = get_cold_start_optimizer()
        assert optimizer is not None
        assert len(optimizer.essential_models) > 0
        assert len(optimizer.critical_services) > 0
        assert len(optimizer.deferred_services) > 0
        assert len(optimizer.deferred_models) > 0
    
    @pytest.mark.asyncio
    async def test_cold_start_optimization_sequence(self):
        """Test the complete cold start optimization sequence."""
        from multimodal_librarian.startup.cold_start_optimizer import (
            get_cold_start_optimizer,
            initialize_cold_start_optimization
        )
        
        optimizer = get_cold_start_optimizer()
        
        # Test optimization sequence
        start_time = time.time()
        result = await initialize_cold_start_optimization()
        optimization_time = time.time() - start_time
        
        # Verify results
        assert result["optimized"] is True
        assert result["startup_mode"] == "fast"
        assert "metrics" in result
        assert "services_ready" in result
        assert "models_loaded" in result
        
        # Verify timing (should be fast)
        assert optimization_time < 15.0, f"Optimization took too long: {optimization_time}s"
        
        # Verify critical services are ready
        for service in optimizer.critical_services:
            assert optimizer.is_service_ready(service), f"Critical service not ready: {service}"
        
        # Clean up
        await optimizer.shutdown()
    
    @pytest.mark.asyncio
    async def test_service_initialization_timing(self):
        """Test that services initialize within expected time limits."""
        from multimodal_librarian.startup.cold_start_optimizer import get_cold_start_optimizer
        
        optimizer = get_cold_start_optimizer()
        
        # Test critical service initialization
        for service_name in optimizer.critical_services:
            start_time = time.time()
            success = await optimizer._initialize_service(service_name)
            init_time = time.time() - start_time
            
            assert success is True, f"Failed to initialize service: {service_name}"
            assert init_time < 1.0, f"Service {service_name} took too long to initialize: {init_time}s"
            assert optimizer.is_service_ready(service_name), f"Service not ready: {service_name}"
        
        # Clean up
        await optimizer.shutdown()
    
    @pytest.mark.asyncio
    async def test_model_loading_optimization(self):
        """Test that model loading is optimized for cold start."""
        from multimodal_librarian.startup.cold_start_optimizer import get_cold_start_optimizer
        
        optimizer = get_cold_start_optimizer()
        
        # Test essential model loading (should be fast)
        for model_name in optimizer.essential_models:
            start_time = time.time()
            
            # Mock model loading to avoid actual downloads in tests
            with patch.object(optimizer, '_load_model_sync') as mock_load:
                mock_load.return_value = MagicMock()
                
                model = await optimizer._load_model_async(model_name)
                load_time = time.time() - start_time
                
                assert model is not None, f"Failed to load model: {model_name}"
                assert load_time < 5.0, f"Model {model_name} took too long to load: {load_time}s"
                assert optimizer.is_model_loaded(model_name), f"Model not cached: {model_name}"
        
        # Clean up
        await optimizer.shutdown()
    
    @pytest.mark.asyncio
    async def test_background_task_management(self):
        """Test that background tasks are managed correctly."""
        from multimodal_librarian.startup.cold_start_optimizer import get_cold_start_optimizer
        
        optimizer = get_cold_start_optimizer()
        
        # Start background initialization
        optimizer._start_background_initialization()
        
        # Verify background tasks are created
        assert len(optimizer._background_tasks) > 0, "No background tasks created"
        
        # Wait a bit for tasks to start
        await asyncio.sleep(0.5)
        
        # Verify tasks are running
        active_tasks = [task for task in optimizer._background_tasks if not task.done()]
        assert len(active_tasks) > 0, "No active background tasks"
        
        # Clean up (should cancel background tasks)
        await optimizer.shutdown()
        
        # Verify tasks are cleaned up
        assert len(optimizer._background_tasks) == 0, "Background tasks not cleaned up"
    
    def test_cold_start_health_check_endpoint(self):
        """Test the cold start optimized health check endpoint."""
        # This test requires the application to be running
        # We'll test the endpoint logic directly
        
        from multimodal_librarian.api.routers.cold_start_health import (
            cold_start_health_check,
            get_startup_progress,
            check_readiness
        )
        
        # Test health check endpoint (should be very fast)
        start_time = time.time()
        
        # Mock the optimizer for testing
        with patch('multimodal_librarian.api.routers.cold_start_health.get_cold_start_optimizer') as mock_optimizer:
            mock_optimizer.return_value._get_startup_metrics.return_value = {
                "total_startup_time": 5.0,
                "health_check_ready_time": 2.0,
                "essential_services_ready_time": None,
                "models_loaded_count": 0,
                "services_initialized_count": 2,
                "background_tasks_active": 3
            }
            mock_optimizer.return_value.critical_services = {"health_check", "basic_api"}
            mock_optimizer.return_value.is_service_ready.return_value = True
            
            # Test health check
            response = asyncio.run(cold_start_health_check())
            response_time = time.time() - start_time
            
            assert response.status_code == 200
            assert response_time < 0.1, f"Health check too slow: {response_time}s"
            
            # Verify response content
            content = response.body.decode()
            assert "cold_start_mode" in content
            assert "startup_progress" in content
    
    def test_cold_start_configuration(self):
        """Test cold start configuration loading and validation."""
        from multimodal_librarian.startup.cold_start_optimizer import (
            is_cold_start_mode,
            get_startup_mode,
            should_defer_service,
            should_defer_model
        )
        
        # Test configuration detection
        assert is_cold_start_mode() is True
        assert get_startup_mode() == "fast"
        
        # Test service deferral logic
        assert should_defer_service("vector_search") is True
        assert should_defer_service("health_check") is False
        
        # Test model deferral logic
        assert should_defer_model("spacy/en_core_web_sm") is True
        assert should_defer_model("sentence-transformers/all-MiniLM-L6-v2") is False
    
    @pytest.mark.asyncio
    async def test_service_waiting_functionality(self):
        """Test the service waiting functionality."""
        from multimodal_librarian.startup.cold_start_optimizer import (
            get_cold_start_optimizer,
            wait_for_service,
            wait_for_model
        )
        
        optimizer = get_cold_start_optimizer()
        
        # Initialize a service
        await optimizer._initialize_service("health_check")
        
        # Test waiting for ready service (should return immediately)
        start_time = time.time()
        result = await wait_for_service("health_check", timeout=5.0)
        wait_time = time.time() - start_time
        
        assert result is True
        assert wait_time < 0.5, f"Wait for ready service took too long: {wait_time}s"
        
        # Test waiting for non-existent service (should timeout)
        start_time = time.time()
        result = await wait_for_service("non_existent_service", timeout=1.0)
        wait_time = time.time() - start_time
        
        assert result is False
        assert 0.9 <= wait_time <= 1.5, f"Timeout not respected: {wait_time}s"
        
        # Clean up
        await optimizer.shutdown()
    
    def test_cold_start_metrics_collection(self):
        """Test that cold start metrics are collected correctly."""
        from multimodal_librarian.startup.cold_start_optimizer import get_cold_start_optimizer
        
        optimizer = get_cold_start_optimizer()
        
        # Verify initial metrics
        metrics = optimizer._get_startup_metrics()
        assert "total_startup_time" in metrics
        assert "models_loaded_count" in metrics
        assert "services_initialized_count" in metrics
        assert "background_tasks_active" in metrics
        
        # Verify metrics are reasonable
        assert metrics["total_startup_time"] >= 0
        assert metrics["models_loaded_count"] >= 0
        assert metrics["services_initialized_count"] >= 0
        assert metrics["background_tasks_active"] >= 0
    
    @pytest.mark.integration
    def test_docker_compose_cold_start_optimization(self):
        """Integration test for Docker Compose cold start optimization."""
        # This test requires Docker and the optimization files to be present
        
        # Check if optimization files exist
        required_files = [
            "docker-compose.cold-start-optimized.yml",
            "Dockerfile.cold-start-optimized",
            "scripts/fast-startup.sh"
        ]
        
        for file_path in required_files:
            if not os.path.exists(file_path):
                pytest.skip(f"Cold start optimization file not found: {file_path}")
        
        # Test Docker Compose startup
        try:
            # Stop any existing services
            subprocess.run([
                "docker", "compose", "-f", "docker-compose.cold-start-optimized.yml", "down"
            ], capture_output=True, timeout=30)
            
            # Start services with cold start optimization
            start_time = time.time()
            result = subprocess.run([
                "docker", "compose", "-f", "docker-compose.cold-start-optimized.yml", "up", "-d"
            ], capture_output=True, timeout=COLD_START_TIMEOUT)
            
            assert result.returncode == 0, f"Docker Compose failed: {result.stderr.decode()}"
            
            # Wait for health check to be ready
            health_ready_time = None
            for _ in range(HEALTH_CHECK_TIMEOUT):
                try:
                    response = requests.get("http://localhost:8000/health/cold-start", timeout=2)
                    if response.status_code == 200:
                        health_ready_time = time.time()
                        break
                except requests.RequestException:
                    pass
                time.sleep(1)
            
            assert health_ready_time is not None, "Health check never became ready"
            
            # Calculate timing
            health_check_time = health_ready_time - start_time
            
            # Verify performance
            assert health_check_time < EXPECTED_COLD_START_TIME, \
                f"Cold start took too long: {health_check_time}s (expected < {EXPECTED_COLD_START_TIME}s)"
            
            # Test health check response
            response = requests.get("http://localhost:8000/health/cold-start", timeout=5)
            assert response.status_code == 200
            
            data = response.json()
            assert data["status"] == "ok"
            assert data["cold_start_mode"] is True
            assert "startup_progress" in data
            
            print(f"✅ Cold start completed in {health_check_time:.2f}s")
            
        finally:
            # Clean up
            subprocess.run([
                "docker", "compose", "-f", "docker-compose.cold-start-optimized.yml", "down"
            ], capture_output=True, timeout=30)
    
    @pytest.mark.benchmark
    def test_cold_start_performance_benchmark(self):
        """Benchmark cold start performance against baseline."""
        # This test compares cold start optimized vs standard startup
        
        if not os.path.exists("docker-compose.cold-start-optimized.yml"):
            pytest.skip("Cold start optimization files not found")
        
        # Benchmark standard startup
        standard_time = self._benchmark_startup("docker-compose.local.yml")
        
        # Benchmark cold start optimized startup
        optimized_time = self._benchmark_startup("docker-compose.cold-start-optimized.yml")
        
        # Calculate improvement
        improvement = standard_time - optimized_time
        improvement_percent = (improvement / standard_time) * 100 if standard_time > 0 else 0
        
        print(f"Standard startup: {standard_time:.2f}s")
        print(f"Optimized startup: {optimized_time:.2f}s")
        print(f"Improvement: {improvement:.2f}s ({improvement_percent:.1f}%)")
        
        # Verify improvement (should be at least 10% faster)
        assert improvement > 0, "Cold start optimization should improve startup time"
        assert improvement_percent >= 10, f"Expected at least 10% improvement, got {improvement_percent:.1f}%"
    
    def _benchmark_startup(self, compose_file: str) -> float:
        """Benchmark startup time for a given compose file."""
        try:
            # Stop any existing services
            subprocess.run([
                "docker", "compose", "-f", compose_file, "down", "-v"
            ], capture_output=True, timeout=30)
            
            # Start services and measure time
            start_time = time.time()
            result = subprocess.run([
                "docker", "compose", "-f", compose_file, "up", "-d"
            ], capture_output=True, timeout=COLD_START_TIMEOUT)
            
            if result.returncode != 0:
                raise RuntimeError(f"Docker Compose failed: {result.stderr.decode()}")
            
            # Wait for health check
            for _ in range(HEALTH_CHECK_TIMEOUT):
                try:
                    response = requests.get("http://localhost:8000/health/simple", timeout=2)
                    if response.status_code == 200:
                        return time.time() - start_time
                except requests.RequestException:
                    pass
                time.sleep(1)
            
            raise TimeoutError("Health check never became ready")
            
        finally:
            # Clean up
            subprocess.run([
                "docker", "compose", "-f", compose_file, "down", "-v"
            ], capture_output=True, timeout=30)


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])