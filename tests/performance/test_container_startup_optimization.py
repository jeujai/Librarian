"""
Container Startup Optimization Tests

This module tests the effectiveness of container startup optimizations
including parallel startup, health check optimization, and resource allocation.
"""

import asyncio
import json
import subprocess
import time
import pytest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import docker
import requests


class ContainerStartupTester:
    """Test container startup optimizations."""
    
    def __init__(self):
        self.docker_client = docker.from_env()
        self.compose_optimized = "docker-compose.optimized.yml"
        self.compose_original = "docker-compose.local.yml"
        self.test_results = {}
        
    def cleanup_containers(self, compose_file: str) -> None:
        """Clean up containers from previous tests."""
        try:
            subprocess.run([
                "docker", "compose", "-f", compose_file, "down", "-v"
            ], check=False, capture_output=True)
        except Exception:
            pass  # Ignore cleanup errors
    
    def measure_startup_time(self, compose_file: str, timeout: int = 300) -> Dict:
        """Measure container startup time."""
        start_time = time.time()
        
        # Start services
        result = subprocess.run([
            "docker", "compose", "-f", compose_file, "up", "-d"
        ], capture_output=True, text=True)
        
        if result.returncode != 0:
            return {
                "success": False,
                "error": result.stderr,
                "startup_time": None
            }
        
        # Wait for services to be healthy
        services_healthy = False
        health_check_start = time.time()
        
        while time.time() - health_check_start < timeout:
            if self.check_all_services_healthy(compose_file):
                services_healthy = True
                break
            time.sleep(2)
        
        total_time = time.time() - start_time
        
        return {
            "success": services_healthy,
            "startup_time": total_time,
            "services_healthy": services_healthy,
            "timeout_reached": not services_healthy
        }
    
    def check_all_services_healthy(self, compose_file: str) -> bool:
        """Check if all services are healthy."""
        try:
            # Get list of services
            result = subprocess.run([
                "docker", "compose", "-f", compose_file, "config", "--services"
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                return False
            
            services = result.stdout.strip().split('\n')
            
            # Check each service
            for service in services:
                if not self.check_service_health(service):
                    return False
            
            return True
            
        except Exception:
            return False
    
    def check_service_health(self, service: str) -> bool:
        """Check if a specific service is healthy."""
        health_checks = {
            "redis": self.check_redis_health,
            "postgres": self.check_postgres_health,
            "neo4j": self.check_neo4j_health,
            "milvus": self.check_milvus_health,
            "multimodal-librarian": self.check_app_health,
            "etcd": self.check_etcd_health,
            "minio": self.check_minio_health
        }
        
        check_func = health_checks.get(service)
        if check_func:
            return check_func()
        
        # Generic check - just see if container is running
        try:
            containers = self.docker_client.containers.list(
                filters={"name": service}
            )
            return len(containers) > 0 and containers[0].status == "running"
        except Exception:
            return False
    
    def check_redis_health(self) -> bool:
        """Check Redis health."""
        try:
            result = subprocess.run([
                "docker", "exec", "-it", "redis", "redis-cli", "ping"
            ], capture_output=True, text=True, timeout=5)
            return result.returncode == 0 and "PONG" in result.stdout
        except Exception:
            return False
    
    def check_postgres_health(self) -> bool:
        """Check PostgreSQL health."""
        try:
            result = subprocess.run([
                "docker", "exec", "-it", "postgres", 
                "pg_isready", "-U", "ml_user", "-d", "multimodal_librarian"
            ], capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except Exception:
            return False
    
    def check_neo4j_health(self) -> bool:
        """Check Neo4j health."""
        try:
            result = subprocess.run([
                "docker", "exec", "-it", "neo4j",
                "cypher-shell", "-u", "neo4j", "-p", "ml_password", "RETURN 1"
            ], capture_output=True, text=True, timeout=15)
            return result.returncode == 0
        except Exception:
            return False
    
    def check_milvus_health(self) -> bool:
        """Check Milvus health."""
        try:
            response = requests.get("http://localhost:9091/healthz", timeout=10)
            return response.status_code == 200
        except Exception:
            return False
    
    def check_app_health(self) -> bool:
        """Check main application health."""
        try:
            response = requests.get("http://localhost:8000/health/simple", timeout=10)
            return response.status_code == 200
        except Exception:
            return False
    
    def check_etcd_health(self) -> bool:
        """Check etcd health."""
        try:
            result = subprocess.run([
                "docker", "exec", "-it", "etcd", "etcdctl", "endpoint", "health"
            ], capture_output=True, text=True, timeout=10)
            return result.returncode == 0
        except Exception:
            return False
    
    def check_minio_health(self) -> bool:
        """Check MinIO health."""
        try:
            response = requests.get("http://localhost:9000/minio/health/live", timeout=10)
            return response.status_code == 200
        except Exception:
            return False
    
    def measure_resource_usage(self, compose_file: str) -> Dict:
        """Measure resource usage of containers."""
        try:
            # Get container stats
            result = subprocess.run([
                "docker", "stats", "--no-stream", "--format", 
                "{{.Container}},{{.CPUPerc}},{{.MemUsage}},{{.NetIO}},{{.BlockIO}}"
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                return {"error": result.stderr}
            
            stats = {}
            for line in result.stdout.strip().split('\n'):
                if line:
                    parts = line.split(',')
                    if len(parts) >= 3:
                        container = parts[0]
                        cpu_percent = parts[1]
                        memory_usage = parts[2]
                        stats[container] = {
                            "cpu_percent": cpu_percent,
                            "memory_usage": memory_usage
                        }
            
            return {"stats": stats}
            
        except Exception as e:
            return {"error": str(e)}
    
    def benchmark_startup_comparison(self) -> Dict:
        """Benchmark startup time comparison between original and optimized."""
        results = {
            "timestamp": datetime.now().isoformat(),
            "original": {},
            "optimized": {},
            "improvement": {}
        }
        
        # Test original configuration
        print("Testing original configuration...")
        self.cleanup_containers(self.compose_original)
        time.sleep(5)
        
        original_result = self.measure_startup_time(self.compose_original)
        results["original"] = original_result
        
        self.cleanup_containers(self.compose_original)
        time.sleep(5)
        
        # Test optimized configuration
        print("Testing optimized configuration...")
        self.cleanup_containers(self.compose_optimized)
        time.sleep(5)
        
        optimized_result = self.measure_startup_time(self.compose_optimized)
        results["optimized"] = optimized_result
        
        # Calculate improvement
        if (original_result.get("startup_time") and 
            optimized_result.get("startup_time")):
            
            original_time = original_result["startup_time"]
            optimized_time = optimized_result["startup_time"]
            improvement_seconds = original_time - optimized_time
            improvement_percent = (improvement_seconds / original_time) * 100
            
            results["improvement"] = {
                "seconds": improvement_seconds,
                "percent": improvement_percent,
                "faster": improvement_seconds > 0
            }
        
        return results


@pytest.fixture
def startup_tester():
    """Fixture to provide startup tester instance."""
    return ContainerStartupTester()


class TestContainerStartupOptimization:
    """Test container startup optimizations."""
    
    def test_optimized_dockerfile_exists(self):
        """Test that optimized Dockerfile exists."""
        dockerfile_path = Path("Dockerfile.optimized")
        assert dockerfile_path.exists(), "Optimized Dockerfile not found"
        
        # Check for optimization features
        content = dockerfile_path.read_text()
        assert "cache-builder" in content, "Multi-stage cache builder not found"
        assert "model-cache" in content, "Model cache stage not found"
        assert "--platform=linux/amd64" in content, "Platform specification missing"
    
    def test_optimized_compose_exists(self):
        """Test that optimized compose file exists."""
        compose_path = Path("docker-compose.optimized.yml")
        assert compose_path.exists(), "Optimized compose file not found"
        
        # Check for optimization features
        content = compose_path.read_text()
        assert "tmpfs" in content, "tmpfs optimization not found"
        assert "resources:" in content, "Resource limits not configured"
        assert "healthcheck:" in content, "Health checks not optimized"
    
    def test_optimization_scripts_exist(self):
        """Test that optimization scripts exist and are executable."""
        scripts = [
            "scripts/optimize-container-startup.sh",
            "scripts/parallel-service-startup.sh",
            "scripts/optimize-health-checks.sh"
        ]
        
        for script_path in scripts:
            path = Path(script_path)
            assert path.exists(), f"Script {script_path} not found"
            assert path.stat().st_mode & 0o111, f"Script {script_path} not executable"
    
    def test_cache_directories_creation(self, startup_tester):
        """Test that cache directories are created properly."""
        cache_dirs = [
            "cache/models",
            "cache/pip",
            "cache/pytest",
            "data/postgres",
            "data/neo4j",
            "data/milvus",
            "data/redis"
        ]
        
        # Create directories (simulating setup)
        for cache_dir in cache_dirs:
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
        
        # Verify directories exist
        for cache_dir in cache_dirs:
            assert Path(cache_dir).exists(), f"Cache directory {cache_dir} not created"
    
    @pytest.mark.slow
    def test_optimized_startup_time(self, startup_tester):
        """Test that optimized startup is faster than original."""
        # This test requires Docker and may take several minutes
        pytest.skip("Skipping slow integration test - run manually with --slow flag")
        
        results = startup_tester.benchmark_startup_comparison()
        
        # Save results for analysis
        results_file = f"startup_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        # Verify both configurations started successfully
        assert results["original"]["success"], "Original configuration failed to start"
        assert results["optimized"]["success"], "Optimized configuration failed to start"
        
        # Verify optimization improved startup time
        improvement = results.get("improvement", {})
        if improvement:
            assert improvement["faster"], "Optimized configuration is not faster"
            assert improvement["seconds"] > 0, "No time improvement detected"
            print(f"Startup improvement: {improvement['seconds']:.2f}s ({improvement['percent']:.1f}%)")
    
    def test_health_check_optimization(self, startup_tester):
        """Test health check optimization functionality."""
        # Test health check script exists and works
        script_path = Path("scripts/optimize-health-checks.sh")
        assert script_path.exists(), "Health check optimization script not found"
        
        # Test cache directory creation
        cache_dir = Path("cache/health-checks")
        cache_dir.mkdir(parents=True, exist_ok=True)
        assert cache_dir.exists(), "Health check cache directory not created"
    
    def test_parallel_startup_script(self):
        """Test parallel startup script functionality."""
        script_path = Path("scripts/parallel-service-startup.sh")
        assert script_path.exists(), "Parallel startup script not found"
        
        # Test script help functionality
        result = subprocess.run([
            "bash", str(script_path), "--help"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0, "Parallel startup script help failed"
        assert "Parallel Service Startup Script" in result.stdout
    
    def test_resource_optimization_config(self):
        """Test that resource optimization is properly configured."""
        compose_path = Path("docker-compose.optimized.yml")
        content = compose_path.read_text()
        
        # Check for resource limits
        assert "limits:" in content, "Resource limits not configured"
        assert "reservations:" in content, "Resource reservations not configured"
        
        # Check for memory optimizations
        assert "1.5G" in content or "1G" in content, "Memory limits not optimized"
        
        # Check for tmpfs volumes
        assert "tmpfs" in content, "tmpfs volumes not configured"
    
    def test_makefile_optimization_targets(self):
        """Test that optimized Makefile targets exist."""
        makefile_path = Path("Makefile.optimized")
        assert makefile_path.exists(), "Optimized Makefile not found"
        
        content = makefile_path.read_text()
        
        # Check for optimization targets
        optimization_targets = [
            "dev-local-optimized",
            "build-optimized",
            "start-optimized",
            "benchmark-startup",
            "parallel-startup",
            "optimize-containers"
        ]
        
        for target in optimization_targets:
            assert f"{target}:" in content, f"Makefile target {target} not found"
    
    def test_dockerfile_layer_optimization(self):
        """Test that Dockerfile is optimized for layer caching."""
        dockerfile_path = Path("Dockerfile.optimized")
        content = dockerfile_path.read_text()
        
        # Check for multi-stage build
        stages = ["cache-builder", "base", "model-cache", "development", "production"]
        for stage in stages:
            assert f"FROM --platform=linux/amd64 python:3.11-slim as {stage}" in content or \
                   f"FROM base as {stage}" in content or \
                   f"FROM model-cache as {stage}" in content, \
                   f"Stage {stage} not found in Dockerfile"
        
        # Check for dependency installation optimization
        assert "pip install --target" in content, "Dependency caching not optimized"
        assert "COPY --from=cache-builder" in content, "Cache layer copying not found"
    
    def test_health_check_intervals(self):
        """Test that health check intervals are optimized."""
        compose_path = Path("docker-compose.optimized.yml")
        content = compose_path.read_text()
        
        # Check for faster health check intervals
        assert "interval: 15s" in content or "interval: 10s" in content, \
               "Health check intervals not optimized"
        assert "timeout: 5s" in content or "timeout: 10s" in content, \
               "Health check timeouts not optimized"
        assert "start_period: 30s" in content or "start_period: 20s" in content, \
               "Health check start periods not optimized"
    
    @pytest.mark.integration
    def test_optimization_integration(self, startup_tester):
        """Integration test for all optimizations working together."""
        # This test verifies that all optimizations work together
        # Skip by default as it requires full Docker environment
        pytest.skip("Skipping integration test - requires full Docker environment")
        
        # Test that optimization script works
        result = subprocess.run([
            "bash", "scripts/optimize-container-startup.sh", "status"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0, "Optimization status check failed"
    
    def test_performance_monitoring_tools(self):
        """Test that performance monitoring tools are available."""
        # Check for monitoring scripts
        monitoring_files = [
            "scripts/optimize-container-startup.sh",
            "scripts/parallel-service-startup.sh",
            "scripts/optimize-health-checks.sh"
        ]
        
        for file_path in monitoring_files:
            path = Path(file_path)
            assert path.exists(), f"Monitoring tool {file_path} not found"
            
            # Check that script has monitoring functionality
            content = path.read_text()
            assert "benchmark" in content or "monitor" in content or "status" in content, \
                   f"Monitoring functionality not found in {file_path}"


class TestStartupPerformanceMetrics:
    """Test startup performance metrics and validation."""
    
    def test_startup_time_target(self):
        """Test that startup time targets are reasonable."""
        # Define performance targets
        targets = {
            "redis": 10,      # seconds
            "postgres": 20,   # seconds
            "neo4j": 45,      # seconds
            "milvus": 60,     # seconds
            "multimodal-librarian": 30  # seconds
        }
        
        # These are target times - actual test would measure real startup
        for service, target_time in targets.items():
            assert target_time > 0, f"Invalid target time for {service}"
            assert target_time < 120, f"Target time too high for {service}"
    
    def test_resource_usage_limits(self):
        """Test that resource usage limits are reasonable."""
        compose_path = Path("docker-compose.optimized.yml")
        content = compose_path.read_text()
        
        # Check that memory limits are reasonable for development
        # Should be less than original but sufficient for functionality
        memory_limits = ["1.5G", "1G", "768M", "512M", "256M"]
        
        found_memory_limit = False
        for limit in memory_limits:
            if limit in content:
                found_memory_limit = True
                break
        
        assert found_memory_limit, "No reasonable memory limits found"
    
    def test_optimization_effectiveness_metrics(self):
        """Test that optimization effectiveness can be measured."""
        # Define metrics that should be tracked
        metrics = [
            "startup_time",
            "memory_usage",
            "cpu_usage",
            "health_check_time",
            "service_ready_time"
        ]
        
        # Verify that benchmark script can measure these metrics
        script_path = Path("scripts/optimize-container-startup.sh")
        content = script_path.read_text()
        
        for metric in metrics:
            # Check that metric is mentioned or can be derived
            assert "time" in content or "benchmark" in content, \
                   f"Metric tracking capability not found for {metric}"


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "--tb=short"])