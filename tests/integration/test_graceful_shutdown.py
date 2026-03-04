"""
Integration tests for graceful shutdown procedures.

These tests validate that the graceful shutdown implementation works correctly
in the local development environment, ensuring all services are properly
stopped and resources are cleaned up.
"""

import asyncio
import pytest
import subprocess
import time
import requests
from pathlib import Path


class TestGracefulShutdown:
    """Test graceful shutdown procedures for local development environment."""
    
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Ensure clean state before and after tests."""
        # Ensure services are stopped before test
        subprocess.run([
            "docker-compose", "-f", "docker-compose.local.yml", "down"
        ], capture_output=True)
        
        yield
        
        # Clean up after test
        subprocess.run([
            "docker-compose", "-f", "docker-compose.local.yml", "down", "-v"
        ], capture_output=True)
    
    def test_graceful_shutdown_script_exists(self):
        """Test that the graceful shutdown script exists and is executable."""
        script_path = Path("scripts/graceful-shutdown.py")
        assert script_path.exists(), "Graceful shutdown script not found"
        assert script_path.is_file(), "Graceful shutdown script is not a file"
    
    def test_graceful_shutdown_dry_run(self):
        """Test graceful shutdown in dry-run mode."""
        result = subprocess.run([
            "python", "scripts/graceful-shutdown.py", "--dry-run"
        ], capture_output=True, text=True, timeout=30)
        
        assert result.returncode == 0, f"Dry run failed: {result.stderr}"
        assert "DRY RUN MODE" in result.stdout
        assert "Would check for running services" in result.stdout
    
    def test_graceful_shutdown_with_no_services(self):
        """Test graceful shutdown when no services are running."""
        result = subprocess.run([
            "python", "scripts/graceful-shutdown.py", "--timeout", "10"
        ], capture_output=True, text=True, timeout=30)
        
        # Should succeed even with no services running
        assert result.returncode == 0, f"Shutdown failed: {result.stderr}"
        assert "GRACEFUL SHUTDOWN COMPLETED" in result.stdout
    
    @pytest.mark.slow
    def test_graceful_shutdown_with_running_services(self):
        """Test graceful shutdown with actual running services."""
        # Start services
        start_result = subprocess.run([
            "docker-compose", "-f", "docker-compose.local.yml", "up", "-d"
        ], capture_output=True, text=True, timeout=120)
        
        assert start_result.returncode == 0, f"Failed to start services: {start_result.stderr}"
        
        # Wait a bit for services to be ready
        time.sleep(10)
        
        # Verify services are running
        ps_result = subprocess.run([
            "docker-compose", "-f", "docker-compose.local.yml", "ps", "--services", "--filter", "status=running"
        ], capture_output=True, text=True, timeout=10)
        
        running_services = [s.strip() for s in ps_result.stdout.split('\n') if s.strip()]
        assert len(running_services) > 0, "No services are running"
        
        # Perform graceful shutdown
        shutdown_result = subprocess.run([
            "python", "scripts/graceful-shutdown.py", "--timeout", "60"
        ], capture_output=True, text=True, timeout=120)
        
        assert shutdown_result.returncode == 0, f"Graceful shutdown failed: {shutdown_result.stderr}"
        assert "GRACEFUL SHUTDOWN COMPLETED" in shutdown_result.stdout
        
        # Verify services are stopped
        time.sleep(5)
        ps_result_after = subprocess.run([
            "docker-compose", "-f", "docker-compose.local.yml", "ps", "--services", "--filter", "status=running"
        ], capture_output=True, text=True, timeout=10)
        
        running_services_after = [s.strip() for s in ps_result_after.stdout.split('\n') if s.strip()]
        assert len(running_services_after) == 0, f"Services still running: {running_services_after}"
    
    def test_graceful_shutdown_specific_services(self):
        """Test graceful shutdown of specific services only."""
        # Start services
        start_result = subprocess.run([
            "docker-compose", "-f", "docker-compose.local.yml", "up", "-d", "postgres", "redis"
        ], capture_output=True, text=True, timeout=60)
        
        assert start_result.returncode == 0, f"Failed to start services: {start_result.stderr}"
        
        # Wait for services to be ready
        time.sleep(5)
        
        # Shutdown specific services
        shutdown_result = subprocess.run([
            "python", "scripts/graceful-shutdown.py", "--services", "postgres", "--timeout", "30"
        ], capture_output=True, text=True, timeout=60)
        
        assert shutdown_result.returncode == 0, f"Specific service shutdown failed: {shutdown_result.stderr}"
        
        # Verify postgres is stopped but redis might still be running
        ps_result = subprocess.run([
            "docker-compose", "-f", "docker-compose.local.yml", "ps", "postgres"
        ], capture_output=True, text=True, timeout=10)
        
        # Postgres should not be in "Up" state
        assert "Up" not in ps_result.stdout, "PostgreSQL should be stopped"
    
    def test_graceful_shutdown_force_mode(self):
        """Test graceful shutdown with force mode."""
        result = subprocess.run([
            "python", "scripts/graceful-shutdown.py", "--force", "--timeout", "5", "--dry-run"
        ], capture_output=True, text=True, timeout=30)
        
        assert result.returncode == 0, f"Force mode test failed: {result.stderr}"
        assert "DRY RUN MODE" in result.stdout
    
    def test_makefile_shutdown_targets(self):
        """Test that Makefile shutdown targets work correctly."""
        # Test dry-run target
        result = subprocess.run([
            "make", "dev-shutdown-dry-run"
        ], capture_output=True, text=True, timeout=30)
        
        assert result.returncode == 0, f"Makefile dry-run target failed: {result.stderr}"
        assert "DRY RUN MODE" in result.stdout or "Showing what graceful shutdown would do" in result.stdout


class TestShutdownHandler:
    """Test the graceful shutdown handler module."""
    
    @pytest.mark.asyncio
    async def test_shutdown_handler_import(self):
        """Test that the shutdown handler can be imported."""
        from src.multimodal_librarian.shutdown import (
            get_shutdown_handler,
            register_cleanup_function,
            get_shutdown_status
        )
        
        # Should not raise any exceptions
        handler = get_shutdown_handler()
        assert handler is not None
        
        # Test status
        status = get_shutdown_status()
        assert isinstance(status, dict)
        assert "phase" in status
        assert "shutdown_requested" in status
    
    @pytest.mark.asyncio
    async def test_cleanup_function_registration(self):
        """Test registering cleanup functions."""
        from src.multimodal_librarian.shutdown import (
            get_shutdown_handler,
            register_cleanup_function
        )
        
        handler = get_shutdown_handler()
        initial_count = len(handler.cleanup_functions)
        
        def dummy_cleanup():
            pass
        
        register_cleanup_function(dummy_cleanup)
        
        assert len(handler.cleanup_functions) == initial_count + 1
        assert dummy_cleanup in handler.cleanup_functions
    
    @pytest.mark.asyncio
    async def test_background_task_registration(self):
        """Test registering background tasks."""
        from src.multimodal_librarian.shutdown import (
            get_shutdown_handler,
            register_background_task
        )
        
        handler = get_shutdown_handler()
        initial_count = len(handler.background_tasks)
        
        async def dummy_task():
            await asyncio.sleep(1)
        
        task = asyncio.create_task(dummy_task())
        register_background_task(task)
        
        assert len(handler.background_tasks) == initial_count + 1
        assert task in handler.background_tasks
        
        # Clean up
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class TestDatabaseFactoryShutdown:
    """Test database factory graceful shutdown."""
    
    @pytest.mark.asyncio
    async def test_database_factory_shutdown_import(self):
        """Test that database factory shutdown functions can be imported."""
        from src.multimodal_librarian.clients.database_factory import (
            graceful_shutdown,
            register_shutdown_handler
        )
        
        # Should not raise any exceptions
        assert callable(graceful_shutdown)
        assert callable(register_shutdown_handler)
    
    @pytest.mark.asyncio
    async def test_shutdown_handler_registration(self):
        """Test registering shutdown handlers with database factory."""
        from src.multimodal_librarian.clients.database_factory import (
            register_shutdown_handler,
            _shutdown_handlers
        )
        
        initial_count = len(_shutdown_handlers)
        
        def dummy_handler():
            pass
        
        register_shutdown_handler(dummy_handler)
        
        assert len(_shutdown_handlers) == initial_count + 1
        assert dummy_handler in _shutdown_handlers


@pytest.mark.integration
class TestDockerComposeShutdownConfiguration:
    """Test Docker Compose shutdown configuration."""
    
    def test_docker_compose_has_shutdown_config(self):
        """Test that Docker Compose file has proper shutdown configuration."""
        compose_file = Path("docker-compose.local.yml")
        assert compose_file.exists(), "docker-compose.local.yml not found"
        
        content = compose_file.read_text()
        
        # Check for graceful shutdown configuration
        assert "stop_signal: SIGTERM" in content, "SIGTERM signal not configured"
        assert "stop_grace_period:" in content, "Grace period not configured"
        assert "init: true" in content, "Init process not configured"
    
    def test_docker_compose_service_shutdown_order(self):
        """Test that services have appropriate shutdown timeouts."""
        compose_file = Path("docker-compose.local.yml")
        content = compose_file.read_text()
        
        # Application should have reasonable grace period
        assert "stop_grace_period: 30s" in content, "Application grace period not found"
        
        # Database services should have appropriate grace periods
        grace_periods = ["20s", "25s", "30s", "15s", "10s"]
        for period in grace_periods:
            assert f"stop_grace_period: {period}" in content, f"Grace period {period} not found"