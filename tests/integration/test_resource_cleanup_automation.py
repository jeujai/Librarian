"""
Integration tests for resource cleanup automation.

Tests the automated cleanup system including:
- Manual cleanup script functionality
- Scheduled cleanup service
- Resource usage monitoring
- Configuration management
"""

import os
import sys
import json
import tempfile
import subprocess
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.cleanup_local_resources import LocalResourceCleaner
from scripts.scheduled_cleanup import ScheduledCleanupService


class TestResourceCleanupAutomation:
    """Test suite for resource cleanup automation."""
    
    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Create project structure
            (temp_path / "src").mkdir()
            (temp_path / "tests").mkdir()
            (temp_path / "logs").mkdir()
            (temp_path / "uploads").mkdir()
            (temp_path / "cache").mkdir()
            (temp_path / "__pycache__").mkdir()
            
            # Create some test files
            (temp_path / "logs" / "app.log").write_text("test log content")
            (temp_path / "logs" / "old.log").write_text("old log content")
            (temp_path / "uploads" / "test.pdf").write_text("test upload")
            (temp_path / "cache" / "cache.json").write_text('{"test": "data"}')
            (temp_path / "__pycache__" / "test.pyc").write_bytes(b"compiled python")
            (temp_path / "test.pyc").write_bytes(b"compiled python")
            
            # Create docker-compose file
            compose_content = """
version: '3.8'
services:
  test-service:
    image: nginx
"""
            (temp_path / "docker-compose.local.yml").write_text(compose_content)
            
            yield temp_path
    
    @pytest.fixture
    def mock_docker_commands(self):
        """Mock Docker commands for testing."""
        with patch('subprocess.run') as mock_run:
            # Mock successful Docker commands
            mock_run.return_value = subprocess.CompletedProcess(
                [], 0, "container1\ncontainer2", ""
            )
            yield mock_run
    
    def test_local_resource_cleaner_initialization(self, temp_project_dir):
        """Test LocalResourceCleaner initialization."""
        with patch.object(Path, 'parent', temp_project_dir):
            cleaner = LocalResourceCleaner(dry_run=True)
            
            assert cleaner.dry_run is True
            assert cleaner.force is False
            assert cleaner.project_root == temp_project_dir.parent
    
    def test_cleanup_application_files(self, temp_project_dir):
        """Test cleanup of application files."""
        with patch.object(LocalResourceCleaner, 'project_root', temp_project_dir):
            cleaner = LocalResourceCleaner(dry_run=False)
            
            # Verify files exist before cleanup
            assert (temp_project_dir / "uploads" / "test.pdf").exists()
            assert (temp_project_dir / "cache" / "cache.json").exists()
            assert (temp_project_dir / "__pycache__").exists()
            assert (temp_project_dir / "test.pyc").exists()
            
            # Run cleanup
            result = cleaner.cleanup_application_files()
            
            assert result is True
            # Verify files were removed
            assert not (temp_project_dir / "uploads").exists()
            assert not (temp_project_dir / "cache").exists()
            assert not (temp_project_dir / "__pycache__").exists()
            assert not (temp_project_dir / "test.pyc").exists()
    
    def test_cleanup_application_files_dry_run(self, temp_project_dir):
        """Test dry run mode doesn't actually delete files."""
        with patch.object(LocalResourceCleaner, 'project_root', temp_project_dir):
            cleaner = LocalResourceCleaner(dry_run=True)
            
            # Verify files exist before cleanup
            assert (temp_project_dir / "uploads" / "test.pdf").exists()
            assert (temp_project_dir / "cache" / "cache.json").exists()
            
            # Run cleanup in dry run mode
            result = cleaner.cleanup_application_files()
            
            assert result is True
            # Verify files still exist (dry run)
            assert (temp_project_dir / "uploads" / "test.pdf").exists()
            assert (temp_project_dir / "cache" / "cache.json").exists()
    
    def test_cleanup_docker_containers(self, mock_docker_commands):
        """Test Docker container cleanup."""
        cleaner = LocalResourceCleaner(dry_run=False)
        
        result = cleaner.cleanup_docker_containers()
        
        assert result is True
        # Verify Docker commands were called
        assert mock_docker_commands.called
    
    def test_cleanup_docker_containers_dry_run(self, mock_docker_commands):
        """Test Docker container cleanup in dry run mode."""
        cleaner = LocalResourceCleaner(dry_run=True)
        
        result = cleaner.cleanup_docker_containers()
        
        assert result is True
        # In dry run mode, commands should not be executed
        assert not mock_docker_commands.called
    
    def test_get_resource_usage_report(self, mock_docker_commands, temp_project_dir):
        """Test resource usage report generation."""
        with patch.object(LocalResourceCleaner, 'project_root', temp_project_dir):
            cleaner = LocalResourceCleaner()
            
            report = cleaner.get_resource_usage_report()
            
            assert isinstance(report, dict)
            assert 'containers' in report
            assert 'volumes' in report
            assert 'images' in report
            assert 'project_disk_usage' in report
    
    def test_run_full_cleanup(self, mock_docker_commands, temp_project_dir):
        """Test full cleanup process."""
        with patch.object(LocalResourceCleaner, 'project_root', temp_project_dir):
            cleaner = LocalResourceCleaner(dry_run=False, force=True)
            
            result = cleaner.run_full_cleanup(include_data=False)
            
            assert result is True
    
    def test_scheduled_cleanup_service_initialization(self):
        """Test ScheduledCleanupService initialization."""
        service = ScheduledCleanupService()
        
        assert service.config is not None
        assert 'daily_cleanup' in service.config
        assert 'weekly_cleanup' in service.config
        assert 'thresholds' in service.config
    
    def test_scheduled_cleanup_service_custom_config(self):
        """Test ScheduledCleanupService with custom configuration."""
        custom_config = {
            'daily_cleanup': {'enabled': False},
            'thresholds': {'log_retention_days': 14}
        }
        
        service = ScheduledCleanupService(custom_config)
        
        assert service.config['daily_cleanup']['enabled'] is False
        assert service.config['thresholds']['log_retention_days'] == 14
    
    def test_daily_cleanup_task(self, temp_project_dir):
        """Test daily cleanup task execution."""
        with patch.object(LocalResourceCleaner, 'project_root', temp_project_dir):
            service = ScheduledCleanupService()
            
            # Mock the cleaner methods
            with patch.object(service.cleaner, 'cleanup_log_files') as mock_logs, \
                 patch.object(service.cleaner, 'cleanup_application_files') as mock_files, \
                 patch.object(service.cleaner, 'cleanup_test_artifacts') as mock_tests:
                
                mock_logs.return_value = True
                mock_files.return_value = True
                mock_tests.return_value = True
                
                service.daily_cleanup_task()
                
                mock_logs.assert_called_once()
                mock_files.assert_called_once()
                mock_tests.assert_called_once()
    
    def test_weekly_cleanup_task(self, temp_project_dir):
        """Test weekly cleanup task execution."""
        with patch.object(LocalResourceCleaner, 'project_root', temp_project_dir):
            service = ScheduledCleanupService()
            
            # Mock the cleaner methods
            with patch.object(service.cleaner, 'cleanup_docker_images') as mock_images, \
                 patch.object(service.cleaner, 'cleanup_backup_files') as mock_backups, \
                 patch.object(service.cleaner, 'cleanup_docker_networks') as mock_networks:
                
                mock_images.return_value = True
                mock_backups.return_value = True
                mock_networks.return_value = True
                
                service.weekly_cleanup_task()
                
                mock_images.assert_called_once()
                mock_backups.assert_called_once()
                mock_networks.assert_called_once()
    
    def test_disk_usage_check_normal(self, temp_project_dir):
        """Test disk usage check with normal usage."""
        with patch.object(LocalResourceCleaner, 'project_root', temp_project_dir):
            service = ScheduledCleanupService()
            
            # Mock small disk usage
            with patch('os.walk') as mock_walk:
                mock_walk.return_value = [
                    (str(temp_project_dir), [], ['small_file.txt'])
                ]
                
                with patch.object(Path, 'stat') as mock_stat:
                    mock_stat.return_value.st_size = 1024  # 1KB
                    
                    # Should not trigger emergency cleanup
                    with patch.object(service, 'emergency_cleanup') as mock_emergency:
                        service.disk_usage_check()
                        mock_emergency.assert_not_called()
    
    def test_disk_usage_check_high(self, temp_project_dir):
        """Test disk usage check with high usage triggering emergency cleanup."""
        with patch.object(LocalResourceCleaner, 'project_root', temp_project_dir):
            service = ScheduledCleanupService()
            
            # Mock high disk usage
            with patch('os.walk') as mock_walk:
                mock_walk.return_value = [
                    (str(temp_project_dir), [], ['large_file.txt'])
                ]
                
                with patch.object(Path, 'stat') as mock_stat:
                    mock_stat.return_value.st_size = 20 * 1024**3  # 20GB
                    
                    # Should trigger emergency cleanup
                    with patch.object(service, 'emergency_cleanup') as mock_emergency:
                        service.disk_usage_check()
                        mock_emergency.assert_called_once()
    
    def test_emergency_cleanup(self, temp_project_dir):
        """Test emergency cleanup execution."""
        with patch.object(LocalResourceCleaner, 'project_root', temp_project_dir):
            service = ScheduledCleanupService()
            
            # Mock all cleanup methods
            with patch.object(service.cleaner, 'cleanup_application_files') as mock_files, \
                 patch.object(service.cleaner, 'cleanup_test_artifacts') as mock_tests, \
                 patch.object(service.cleaner, 'cleanup_log_files') as mock_logs, \
                 patch.object(service.cleaner, 'cleanup_backup_files') as mock_backups, \
                 patch.object(service.cleaner, 'cleanup_docker_images') as mock_images, \
                 patch.object(service.cleaner, 'cleanup_docker_networks') as mock_networks:
                
                mock_files.return_value = True
                mock_tests.return_value = True
                mock_logs.return_value = True
                mock_backups.return_value = True
                mock_images.return_value = True
                mock_networks.return_value = True
                
                service.emergency_cleanup()
                
                # Verify all emergency cleanup methods were called
                mock_files.assert_called_once()
                mock_tests.assert_called_once()
                mock_logs.assert_called_once_with(days_old=1)  # More aggressive
                mock_backups.assert_called_once_with(days_old=7)  # More aggressive
                mock_images.assert_called_once()
                mock_networks.assert_called_once()
    
    def test_generate_status_report(self, temp_project_dir):
        """Test status report generation."""
        with patch.object(LocalResourceCleaner, 'project_root', temp_project_dir):
            service = ScheduledCleanupService()
            
            # Mock the cleaner's report method
            mock_report = {
                'containers': 'test containers',
                'volumes': 'test volumes',
                'images': 'test images'
            }
            
            with patch.object(service.cleaner, 'get_resource_usage_report') as mock_get_report:
                mock_get_report.return_value = mock_report
                
                service.generate_status_report()
                
                mock_get_report.assert_called_once()
    
    def test_cleanup_script_command_line(self, temp_project_dir):
        """Test cleanup script command line interface."""
        script_path = project_root / "scripts" / "cleanup-local-resources.py"
        
        if not script_path.exists():
            pytest.skip("Cleanup script not found")
        
        # Test dry run mode
        result = subprocess.run([
            sys.executable, str(script_path), "--dry-run", "--report-only"
        ], capture_output=True, text=True)
        
        assert result.returncode == 0
        assert "RESOURCE USAGE REPORT" in result.stdout
    
    def test_scheduled_cleanup_script_command_line(self, temp_project_dir):
        """Test scheduled cleanup script command line interface."""
        script_path = project_root / "scripts" / "scheduled-cleanup.py"
        
        if not script_path.exists():
            pytest.skip("Scheduled cleanup script not found")
        
        # Test the test mode
        result = subprocess.run([
            sys.executable, str(script_path), "--test"
        ], capture_output=True, text=True, timeout=30)
        
        # Should complete without error
        assert result.returncode == 0
    
    def test_cleanup_config_file_exists(self):
        """Test that cleanup configuration file exists and is valid."""
        config_path = project_root / "config" / "cleanup-config.json"
        
        assert config_path.exists(), "Cleanup configuration file not found"
        
        # Test that it's valid JSON
        with open(config_path) as f:
            config = json.load(f)
        
        # Verify required sections
        assert 'daily_cleanup' in config
        assert 'weekly_cleanup' in config
        assert 'thresholds' in config
        assert 'monitoring' in config
        
        # Verify structure
        assert 'enabled' in config['daily_cleanup']
        assert 'time' in config['daily_cleanup']
        assert 'log_retention_days' in config['thresholds']
    
    def test_makefile_targets_exist(self):
        """Test that Makefile contains the new cleanup targets."""
        makefile_path = project_root / "Makefile"
        
        if not makefile_path.exists():
            pytest.skip("Makefile not found")
        
        with open(makefile_path) as f:
            makefile_content = f.read()
        
        # Check for new cleanup targets
        expected_targets = [
            'cleanup-local:',
            'cleanup-local-dry-run:',
            'cleanup-local-force:',
            'cleanup-report:',
            'cleanup-scheduled-start:',
            'cleanup-emergency:'
        ]
        
        for target in expected_targets:
            assert target in makefile_content, f"Makefile target {target} not found"
    
    @pytest.mark.integration
    def test_full_integration_cleanup_cycle(self, temp_project_dir):
        """Test a full integration cleanup cycle."""
        with patch.object(LocalResourceCleaner, 'project_root', temp_project_dir):
            # Create test files and directories
            test_files = [
                temp_project_dir / "logs" / "test.log",
                temp_project_dir / "cache" / "test.cache",
                temp_project_dir / "__pycache__" / "test.pyc",
                temp_project_dir / "test_uploads" / "test.pdf"
            ]
            
            for test_file in test_files:
                test_file.parent.mkdir(parents=True, exist_ok=True)
                test_file.write_text("test content")
            
            # Run cleanup
            cleaner = LocalResourceCleaner(dry_run=False, force=True)
            
            # Test individual cleanup methods
            assert cleaner.cleanup_application_files() is True
            assert cleaner.cleanup_test_artifacts() is True
            
            # Verify cleanup worked
            for test_file in test_files:
                if test_file.exists():
                    # Some files might be in directories that were removed
                    assert not test_file.parent.exists()
    
    def test_error_handling_in_cleanup(self, temp_project_dir):
        """Test error handling in cleanup operations."""
        with patch.object(LocalResourceCleaner, 'project_root', temp_project_dir):
            cleaner = LocalResourceCleaner(dry_run=False)
            
            # Test with permission error
            with patch('shutil.rmtree', side_effect=PermissionError("Permission denied")):
                # Should handle the error gracefully
                result = cleaner.cleanup_application_files()
                # The method should still return True and continue with other operations
                assert result is True
    
    def test_configuration_validation(self):
        """Test configuration validation for scheduled cleanup."""
        # Test with invalid configuration
        invalid_config = {
            'daily_cleanup': {'enabled': 'not_boolean'},  # Invalid type
            'thresholds': {'log_retention_days': 'not_number'}  # Invalid type
        }
        
        # Should handle invalid config gracefully
        service = ScheduledCleanupService(invalid_config)
        assert service.config is not None
        
        # Test with missing required fields
        minimal_config = {}
        service = ScheduledCleanupService(minimal_config)
        assert service.config is not None
        # Should use defaults for missing fields
        assert 'daily_cleanup' in service.config


if __name__ == "__main__":
    pytest.main([__file__, "-v"])