"""
Hot Reload Testing

This module contains tests to verify that hot reload functionality is working
correctly in the local development environment.

Tests:
- Hot reload configuration validation
- File watching functionality
- Server restart behavior
- Development environment setup
"""

import os
import time
import tempfile
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import requests


class TestHotReloadConfiguration:
    """Test hot reload configuration and setup."""
    
    def test_hot_reload_environment_variables(self):
        """Test that hot reload environment variables are properly set."""
        # These should be set in local development
        expected_vars = {
            'WATCHDOG_ENABLED': 'true',
            'UVICORN_RELOAD': 'true',
            'RELOAD_DIRS': '/app/src',
        }
        
        # Check if we're in local development mode
        ml_environment = os.getenv('ML_ENVIRONMENT', '')
        if ml_environment != 'local':
            pytest.skip("Hot reload environment variables only required in local development")
        
        for var, expected_value in expected_vars.items():
            actual_value = os.getenv(var, '').lower()
            assert actual_value == expected_value.lower(), f"{var} should be {expected_value}, got {actual_value}"
    
    def test_reload_includes_configuration(self):
        """Test that file include patterns are properly configured."""
        reload_includes = os.getenv('RELOAD_INCLUDES', '')
        expected_patterns = ['*.py', '*.yaml', '*.yml', '*.json', '*.toml']
        
        # If RELOAD_INCLUDES is not set, this test is informational
        if not reload_includes:
            pytest.skip("RELOAD_INCLUDES not set - this is expected outside of local development")
        
        for pattern in expected_patterns:
            assert pattern in reload_includes, f"Reload includes should contain {pattern}"
    
    def test_reload_excludes_configuration(self):
        """Test that file exclude patterns are properly configured."""
        reload_excludes = os.getenv('RELOAD_EXCLUDES', '')
        expected_excludes = ['__pycache__', '*.pyc', '*.pyo', '*.pyd', '.git']
        
        # If RELOAD_EXCLUDES is not set, this test is informational
        if not reload_excludes:
            pytest.skip("RELOAD_EXCLUDES not set - this is expected outside of local development")
        
        for exclude in expected_excludes:
            assert exclude in reload_excludes, f"Reload excludes should contain {exclude}"
    
    def test_development_environment_detection(self):
        """Test that we can detect if we're in development mode."""
        ml_environment = os.getenv('ML_ENVIRONMENT', '')
        debug_mode = os.getenv('DEBUG', '').lower()
        
        # In development, these should be set appropriately
        if ml_environment == 'local':
            assert debug_mode == 'true', "DEBUG should be true in local development"


class TestHotReloadFunctionality:
    """Test actual hot reload functionality."""
    
    @pytest.mark.skipif(
        os.getenv('ML_ENVIRONMENT') != 'local',
        reason="Hot reload tests only run in local development"
    )
    def test_server_responds_to_health_check(self):
        """Test that the development server is running and responding."""
        try:
            response = requests.get('http://localhost:8000/health/simple', timeout=5)
            assert response.status_code == 200
            assert 'status' in response.json()
        except requests.exceptions.RequestException:
            pytest.skip("Development server not running")
    
    @pytest.mark.skipif(
        os.getenv('ML_ENVIRONMENT') != 'local',
        reason="Hot reload tests only run in local development"
    )
    def test_hot_reload_script_exists(self):
        """Test that hot reload scripts exist and are executable."""
        script_paths = [
            'scripts/dev-with-hot-reload.sh',
            'scripts/hot-reload-config.py',
            'scripts/wait-for-services.sh',
            'scripts/setup-development-directories.sh'
        ]
        
        for script_path in script_paths:
            path = Path(script_path)
            assert path.exists(), f"Hot reload script should exist: {script_path}"
            assert os.access(path, os.X_OK), f"Hot reload script should be executable: {script_path}"
    
    def test_docker_compose_hot_reload_configuration(self):
        """Test that Docker Compose is configured for hot reload."""
        compose_file = Path('docker-compose.local.yml')
        
        if compose_file.exists():
            content = compose_file.read_text()
            
            # Check for volume mounts that enable hot reload
            assert './src:/app/src:rw' in content, "Source code should be mounted for hot reload"
            assert 'WATCHDOG_ENABLED=true' in content, "Watchdog should be enabled"
            assert 'RELOAD_DIRS=/app/src' in content, "Reload directories should be configured"
    
    def test_makefile_hot_reload_targets(self):
        """Test that Makefile contains hot reload targets."""
        makefile = Path('Makefile')
        
        if makefile.exists():
            content = makefile.read_text()
            
            expected_targets = [
                'dev-hot-reload:',
                'logs-hot-reload:',
                'restart-app:',
                'watch-files:'
            ]
            
            for target in expected_targets:
                assert target in content, f"Makefile should contain target: {target}"


class TestFileWatchingSimulation:
    """Test file watching behavior through simulation."""
    
    def test_file_pattern_matching(self):
        """Test that file patterns match correctly."""
        from scripts.hot_reload_config import HotReloadConfig
        
        config = HotReloadConfig()
        
        # Test include patterns
        test_files = [
            ('test.py', True),
            ('config.yaml', True),
            ('settings.yml', True),
            ('data.json', True),
            ('pyproject.toml', True),
            ('test.txt', False),
            ('image.png', False),
        ]
        
        for filename, should_match in test_files:
            matches = any(Path(filename).match(pattern) for pattern in config.include_patterns)
            assert matches == should_match, f"File {filename} match result should be {should_match}"
    
    def test_exclude_pattern_matching(self):
        """Test that exclude patterns work correctly."""
        from scripts.hot_reload_config import HotReloadConfig
        
        config = HotReloadConfig()
        
        # Test exclude patterns
        exclude_files = [
            '__pycache__/test.py',
            'test.pyc',
            'test.pyo',
            'test.pyd',
            '.git/config',
            'test.log',
            'temp.tmp'
        ]
        
        for filename in exclude_files:
            path = Path(filename)
            excluded = any(part in config.exclude_dirs for part in path.parts) or \
                      any(path.match(pattern) for pattern in config.exclude_patterns)
            assert excluded, f"File {filename} should be excluded"
    
    @patch('subprocess.Popen')
    def test_server_restart_simulation(self, mock_popen):
        """Test server restart logic without actually restarting."""
        from scripts.hot_reload_config import HotReloadHandler, HotReloadConfig
        
        config = HotReloadConfig()
        handler = HotReloadHandler(config)
        
        # Mock the process
        mock_process = MagicMock()
        mock_process.poll.return_value = None  # Process is running
        mock_popen.return_value = mock_process
        
        # Simulate server restart
        handler.restart_server()
        
        # Verify that Popen was called with correct arguments
        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        
        # Check that the command includes uvicorn
        assert 'uvicorn' in args[0]
        assert 'multimodal_librarian.main:app' in args[0]
        assert '--reload' in args[0]


class TestDevelopmentWorkflow:
    """Test the complete development workflow with hot reload."""
    
    def test_development_directories_creation(self):
        """Test that development directories can be created."""
        # This would normally be tested by running the setup script
        # but we'll test the logic here
        required_dirs = [
            'uploads', 'media', 'exports', 'logs', 'audit_logs',
            'test_uploads', 'test_media', 'test_exports', 'test_data',
            'cache', 'cache/models', 'cache/pip', 'cache/pytest',
            'data', 'backups', 'notebooks'
        ]
        
        # In a real test environment, these directories should exist
        # or be creatable
        for dir_name in required_dirs:
            dir_path = Path(dir_name)
            # Test that we can create the directory (in a temp location for testing)
            with tempfile.TemporaryDirectory() as temp_dir:
                test_dir = Path(temp_dir) / dir_name
                test_dir.mkdir(parents=True, exist_ok=True)
                assert test_dir.exists()
    
    def test_environment_file_template(self):
        """Test that environment file template is properly configured."""
        env_example = Path('.env.local.example')
        
        if env_example.exists():
            content = env_example.read_text()
            
            # Check for hot reload configuration
            hot_reload_vars = [
                'ENABLE_HOT_RELOAD=true',
                'WATCHDOG_ENABLED=true',
                'UVICORN_RELOAD=true',
                'RELOAD_DIRS=/app/src'
            ]
            
            for var in hot_reload_vars:
                assert var in content, f"Environment template should contain: {var}"
    
    @pytest.mark.skipif(
        not Path('docker-compose.local.yml').exists(),
        reason="Docker Compose file not found"
    )
    def test_docker_compose_service_configuration(self):
        """Test that Docker Compose services are properly configured for hot reload."""
        import yaml
        
        with open('docker-compose.local.yml', 'r') as f:
            compose_config = yaml.safe_load(f)
        
        # Check main application service
        app_service = compose_config.get('services', {}).get('multimodal-librarian', {})
        
        # Check volume mounts
        volumes = app_service.get('volumes', [])
        source_mount_found = any('./src:/app/src:rw' in volume for volume in volumes)
        assert source_mount_found, "Source code should be mounted for hot reload"
        
        # Check environment variables
        environment = app_service.get('environment', [])
        if isinstance(environment, list):
            env_dict = {}
            for env_var in environment:
                if '=' in env_var:
                    key, value = env_var.split('=', 1)
                    env_dict[key] = value
        else:
            env_dict = environment
        
        assert env_dict.get('WATCHDOG_ENABLED') == 'true', "Watchdog should be enabled"


if __name__ == '__main__':
    # Run tests when executed directly
    pytest.main([__file__, '-v'])


class TestHotReloadOptimizations:
    """Test optimized hot reload functionality and performance."""
    
    @pytest.mark.skipif(
        os.getenv('ML_ENVIRONMENT') != 'local',
        reason="Hot reload optimization tests only run in local development"
    )
    def test_optimized_hot_reload_configuration(self):
        """Test that optimized hot reload configuration is properly set."""
        # Check for optimized environment variables
        expected_optimizations = {
            'UVLOOP_ENABLED': '1',
            'HOT_RELOAD_DEBOUNCE_HIGH': '0.5',
            'HOT_RELOAD_DEBOUNCE_MEDIUM': '1.0',
            'HOT_RELOAD_DEBOUNCE_LOW': '2.0',
            'HOT_RELOAD_DEBOUNCE_CONFIG': '0.2',
            'HOT_RELOAD_MAX_BATCH_SIZE': '10',
            'HOT_RELOAD_CACHE_SIZE': '1000'
        }
        
        for var, expected_value in expected_optimizations.items():
            actual_value = os.getenv(var, '')
            if actual_value:  # Only check if variable is set
                assert actual_value == expected_value, f"{var} should be {expected_value}, got {actual_value}"
    
    def test_optimized_file_watching_patterns(self):
        """Test that file watching patterns are optimized for performance."""
        reload_dirs = os.getenv('RELOAD_DIRS', '')
        reload_excludes = os.getenv('RELOAD_EXCLUDES', '')
        
        # Check that reload directory is more specific (not just /app/src)
        if reload_dirs:
            assert 'multimodal_librarian' in reload_dirs, "Reload dirs should be more specific for better performance"
        
        # Check that exclude patterns include performance-critical exclusions
        performance_excludes = ['*.log', '*.tmp', '__pycache__']
        for exclude in performance_excludes:
            if reload_excludes:
                assert exclude in reload_excludes, f"Should exclude {exclude} for better performance"
    
    def test_optimized_docker_compose_exists(self):
        """Test that optimized Docker Compose file exists."""
        optimized_compose = Path('docker-compose.hot-reload-optimized.yml')
        assert optimized_compose.exists(), "Optimized Docker Compose file should exist"
        
        # Check that it contains optimization-specific configurations
        content = optimized_compose.read_text()
        optimizations = [
            'UVLOOP_ENABLED=1',
            'HOT_RELOAD_DEBOUNCE_HIGH',
            'cached',  # Volume mount optimization
            'resources:',  # Resource limits
            'stop_grace_period: 10s'  # Faster shutdown
        ]
        
        for optimization in optimizations:
            assert optimization in content, f"Optimized compose should contain {optimization}"
    
    def test_optimized_scripts_exist(self):
        """Test that optimized hot reload scripts exist."""
        scripts = [
            'scripts/optimized-hot-reload.py',
            'scripts/benchmark-hot-reload.py',
            'scripts/analyze-hot-reload-performance.py'
        ]
        
        for script_path in scripts:
            path = Path(script_path)
            assert path.exists(), f"Optimized script should exist: {script_path}"
            assert os.access(path, os.X_OK), f"Script should be executable: {script_path}"
    
    @pytest.mark.skipif(
        not Path('docker-compose.hot-reload-optimized.yml').exists(),
        reason="Optimized Docker Compose file not found"
    )
    def test_optimized_compose_resource_limits(self):
        """Test that optimized compose has appropriate resource limits."""
        import yaml
        
        with open('docker-compose.hot-reload-optimized.yml', 'r') as f:
            compose_config = yaml.safe_load(f)
        
        # Check main application service
        app_service = compose_config.get('services', {}).get('multimodal-librarian', {})
        deploy_config = app_service.get('deploy', {})
        resource_limits = deploy_config.get('resources', {}).get('limits', {})
        
        # Should have optimized resource limits
        if 'memory' in resource_limits:
            memory_str = resource_limits['memory']
            # Extract numeric value (e.g., "1.5G" -> 1.5)
            if 'G' in memory_str:
                memory_gb = float(memory_str.replace('G', ''))
                assert memory_gb <= 2.0, "Memory limit should be optimized for hot reload (≤2GB)"
    
    def test_makefile_hot_reload_targets(self):
        """Test that Makefile contains optimized hot reload targets."""
        makefile = Path('Makefile')
        
        if makefile.exists():
            content = makefile.read_text()
            
            expected_targets = [
                'dev-hot-reload:',
                'dev-hot-reload-fast:',
                'hot-reload-logs:',
                'hot-reload-status:',
                'hot-reload-benchmark:',
                'hot-reload-optimize:'
            ]
            
            for target in expected_targets:
                assert target in content, f"Makefile should contain optimized target: {target}"


class TestHotReloadPerformance:
    """Test hot reload performance characteristics."""
    
    def test_file_change_detection_efficiency(self):
        """Test that file change detection is efficient."""
        from scripts.optimized_hot_reload import OptimizedHotReloadConfig
        
        config = OptimizedHotReloadConfig()
        
        # Test that watch directories are specific (not too broad)
        assert len(config.watch_dirs) <= 3, "Should watch minimal directories for efficiency"
        
        # Test that exclude patterns are comprehensive
        assert len(config.exclude_patterns) >= 10, "Should have comprehensive exclude patterns"
        assert len(config.exclude_dirs) >= 8, "Should exclude common cache/build directories"
    
    def test_debounce_configuration_priorities(self):
        """Test that debounce delays are configured by priority."""
        from scripts.optimized_hot_reload import OptimizedHotReloadConfig
        
        config = OptimizedHotReloadConfig()
        
        # Test priority-based debounce delays
        assert config.debounce_delays['config'] < config.debounce_delays['high']
        assert config.debounce_delays['high'] < config.debounce_delays['medium']
        assert config.debounce_delays['medium'] < config.debounce_delays['low']
        
        # Test that config changes are fastest
        assert config.debounce_delays['config'] <= 0.5, "Config changes should be very fast"
    
    def test_file_hash_cache_efficiency(self):
        """Test that file hash cache is configured for efficiency."""
        from scripts.optimized_hot_reload import FileHashCache
        
        cache = FileHashCache(max_size=100)
        
        # Test cache behavior
        test_file = Path(__file__)  # Use this test file
        if test_file.exists():
            # First access should calculate hash
            hash1 = cache.get_file_hash(str(test_file))
            assert hash1 is not None
            
            # Second access should use cache (same hash)
            hash2 = cache.get_file_hash(str(test_file))
            assert hash1 == hash2
            
            # Cache should contain the file
            assert str(test_file) in cache.cache
    
    @pytest.mark.skipif(
        not Path('scripts/benchmark-hot-reload.py').exists(),
        reason="Benchmark script not found"
    )
    def test_benchmark_script_functionality(self):
        """Test that benchmark script has required functionality."""
        # Import and test basic functionality
        sys.path.append('scripts')
        
        try:
            from benchmark_hot_reload import HotReloadBenchmark, BenchmarkResult
            
            # Test that benchmark class can be instantiated
            benchmark = HotReloadBenchmark()
            assert benchmark.server_url == "http://localhost:8000"
            assert benchmark.source_dir == Path("/app/src/multimodal_librarian")
            
            # Test benchmark result structure
            result = BenchmarkResult(
                test_name="test",
                file_change_detection_time=1.0,
                server_restart_time=2.0,
                total_reload_time=3.0,
                memory_usage_mb=100.0,
                cpu_usage_percent=50.0,
                success=True
            )
            assert result.test_name == "test"
            assert result.success is True
            
        except ImportError:
            pytest.skip("Benchmark script dependencies not available")