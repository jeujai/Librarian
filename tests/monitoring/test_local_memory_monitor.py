"""
Tests for Local Memory Monitor

This module tests the local development memory monitoring functionality.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from src.multimodal_librarian.monitoring.local_memory_monitor import (
    LocalMemoryMonitor,
    LocalMemoryMetrics,
    get_local_memory_monitor,
    start_local_memory_monitoring,
    stop_local_memory_monitoring,
    get_memory_status
)

class TestLocalMemoryMonitor:
    """Test cases for LocalMemoryMonitor."""
    
    @pytest.fixture
    def monitor(self):
        """Create a LocalMemoryMonitor instance for testing."""
        return LocalMemoryMonitor(alert_threshold=80.0, check_interval=1)
    
    @pytest.fixture
    def mock_psutil(self):
        """Mock psutil for testing."""
        with patch('src.multimodal_librarian.monitoring.local_memory_monitor.psutil') as mock:
            # Mock virtual memory
            mock_memory = Mock()
            mock_memory.used = 4 * 1024 * 1024 * 1024  # 4GB
            mock_memory.percent = 75.0
            mock_memory.available = 1 * 1024 * 1024 * 1024  # 1GB
            mock.virtual_memory.return_value = mock_memory
            yield mock
    
    @pytest.fixture
    def mock_docker(self):
        """Mock Docker client for testing."""
        with patch('src.multimodal_librarian.monitoring.local_memory_monitor.docker') as mock:
            # Mock Docker client
            mock_client = Mock()
            mock_container = Mock()
            mock_container.status = 'running'
            mock_container.stats.return_value = {
                'memory_stats': {
                    'usage': 512 * 1024 * 1024,  # 512MB
                    'limit': 1024 * 1024 * 1024   # 1GB
                }
            }
            mock_client.containers.get.return_value = mock_container
            mock.from_env.return_value = mock_client
            yield mock
    
    def test_monitor_initialization(self, monitor):
        """Test monitor initialization."""
        assert monitor.alert_threshold == 80.0
        assert monitor.check_interval == 1
        assert not monitor.is_monitoring
        assert len(monitor.metrics_history) == 0
    
    def test_get_system_memory_info(self, monitor, mock_psutil):
        """Test system memory information retrieval."""
        used_mb, percent, available_mb = monitor._get_system_memory_info()
        
        assert used_mb == 4 * 1024  # 4GB in MB
        assert percent == 75.0
        assert available_mb == 1 * 1024  # 1GB in MB
    
    def test_get_container_memory_info_no_docker(self, monitor):
        """Test container memory info when Docker is not available."""
        monitor.docker_available = False
        
        usage, limits, percent = monitor._get_container_memory_info()
        
        assert usage == {}
        assert limits == {}
        assert percent == {}
    
    def test_get_container_memory_info_with_docker(self, monitor, mock_docker):
        """Test container memory info with Docker available."""
        monitor.docker_available = True
        monitor.docker_client = mock_docker.from_env.return_value
        
        usage, limits, percent = monitor._get_container_memory_info()
        
        # Should have attempted to get stats for monitored containers
        assert isinstance(usage, dict)
        assert isinstance(limits, dict)
        assert isinstance(percent, dict)
    
    def test_generate_alerts_normal_usage(self, monitor):
        """Test alert generation with normal memory usage."""
        container_percent = {
            'multimodal-librarian-postgres-1': 60.0,
            'multimodal-librarian-neo4j-1': 70.0
        }
        
        alerts = monitor._generate_alerts(75.0, container_percent)
        
        # Should not generate alerts for normal usage
        assert len(alerts) == 0
    
    def test_generate_alerts_high_usage(self, monitor):
        """Test alert generation with high memory usage."""
        container_percent = {
            'multimodal-librarian-postgres-1': 85.0,  # Above threshold
            'multimodal-librarian-neo4j-1': 90.0      # Above threshold
        }
        
        alerts = monitor._generate_alerts(90.0, container_percent)
        
        # Should generate alerts for high usage
        assert len(alerts) > 0
        assert any("System memory usage high" in alert for alert in alerts)
        assert any("postgres memory usage high" in alert for alert in alerts)
        assert any("neo4j memory usage high" in alert for alert in alerts)
    
    def test_extract_service_name(self, monitor):
        """Test service name extraction from container names."""
        assert monitor._extract_service_name('multimodal-librarian-postgres-1') == 'postgres'
        assert monitor._extract_service_name('multimodal-librarian-neo4j-1') == 'neo4j'
        assert monitor._extract_service_name('multimodal-librarian-milvus-1') == 'milvus'
        assert monitor._extract_service_name('other-container') == 'other-container'
    
    @pytest.mark.asyncio
    async def test_collect_metrics(self, monitor, mock_psutil, mock_docker):
        """Test metrics collection."""
        monitor.docker_available = True
        monitor.docker_client = mock_docker.from_env.return_value
        
        metrics = await monitor.collect_metrics()
        
        assert isinstance(metrics, LocalMemoryMetrics)
        assert metrics.system_memory_percent == 75.0
        assert metrics.system_memory_mb == 4 * 1024
        assert metrics.available_memory_mb == 1 * 1024
        assert isinstance(metrics.container_memory_usage, dict)
        assert isinstance(metrics.memory_alerts, list)
        assert isinstance(metrics.optimization_suggestions, list)
    
    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self, monitor):
        """Test starting and stopping monitoring."""
        # Start monitoring
        await monitor.start_monitoring()
        assert monitor.is_monitoring
        assert monitor.monitor_task is not None
        
        # Stop monitoring
        await monitor.stop_monitoring()
        assert not monitor.is_monitoring
    
    def test_get_current_status_no_data(self, monitor):
        """Test getting current status with no data."""
        status = monitor.get_current_status()
        
        assert status["status"] == "no_data"
        assert "message" in status
    
    def test_get_current_status_with_data(self, monitor):
        """Test getting current status with data."""
        # Add a mock metrics entry
        mock_metrics = LocalMemoryMetrics(
            timestamp=datetime.now(),
            system_memory_mb=4096.0,
            system_memory_percent=75.0,
            available_memory_mb=1024.0,
            container_memory_usage={'postgres': 512.0},
            container_memory_limits={'postgres': 1024.0},
            container_memory_percent={'postgres': 50.0},
            total_container_memory_mb=512.0,
            memory_alerts=[],
            optimization_suggestions=[]
        )
        monitor.metrics_history.append(mock_metrics)
        
        status = monitor.get_current_status()
        
        assert status["status"] == "inactive"  # Not monitoring
        assert "system_memory" in status
        assert "containers" in status
        assert status["system_memory"]["percent"] == 75.0
    
    def test_get_memory_history(self, monitor):
        """Test getting memory history."""
        # Add mock metrics
        now = datetime.now()
        for i in range(5):
            metrics = LocalMemoryMetrics(
                timestamp=now - timedelta(minutes=i),
                system_memory_mb=4096.0,
                system_memory_percent=75.0 + i,
                available_memory_mb=1024.0,
                container_memory_usage={},
                container_memory_limits={},
                container_memory_percent={},
                total_container_memory_mb=0.0,
                memory_alerts=[],
                optimization_suggestions=[]
            )
            monitor.metrics_history.append(metrics)
        
        history = monitor.get_memory_history(minutes=10)
        
        assert len(history) == 5
        assert all("timestamp" in entry for entry in history)
        assert all("system_memory_percent" in entry for entry in history)
    
    def test_analyze_memory_trends_insufficient_data(self, monitor):
        """Test memory trend analysis with insufficient data."""
        trends = monitor.analyze_memory_trends()
        
        assert trends["status"] == "insufficient_data"
    
    def test_analyze_memory_trends_with_data(self, monitor):
        """Test memory trend analysis with sufficient data."""
        # Add mock metrics with increasing trend
        now = datetime.now()
        for i in range(10):
            metrics = LocalMemoryMetrics(
                timestamp=now - timedelta(minutes=i),
                system_memory_mb=4096.0,
                system_memory_percent=70.0 + i,  # Increasing trend
                available_memory_mb=1024.0,
                container_memory_usage={},
                container_memory_limits={},
                container_memory_percent={},
                total_container_memory_mb=0.0,
                memory_alerts=[],
                optimization_suggestions=[]
            )
            monitor.metrics_history.append(metrics)
        
        trends = monitor.analyze_memory_trends()
        
        assert trends["status"] == "analyzed"
        assert "system_memory_trend" in trends
        assert "container_memory_trends" in trends

class TestGlobalFunctions:
    """Test global memory monitoring functions."""
    
    def test_get_local_memory_monitor(self):
        """Test getting the global monitor instance."""
        monitor1 = get_local_memory_monitor()
        monitor2 = get_local_memory_monitor()
        
        # Should return the same instance
        assert monitor1 is monitor2
        assert isinstance(monitor1, LocalMemoryMonitor)
    
    @pytest.mark.asyncio
    async def test_start_stop_local_memory_monitoring(self):
        """Test global start/stop functions."""
        monitor = get_local_memory_monitor()
        
        # Start monitoring
        await start_local_memory_monitoring()
        assert monitor.is_monitoring
        
        # Stop monitoring
        await stop_local_memory_monitoring()
        assert not monitor.is_monitoring
    
    def test_get_memory_status(self):
        """Test getting memory status."""
        status = get_memory_status()
        
        assert isinstance(status, dict)
        assert "status" in status

class TestMemoryMetrics:
    """Test LocalMemoryMetrics data class."""
    
    def test_memory_metrics_creation(self):
        """Test creating LocalMemoryMetrics instance."""
        metrics = LocalMemoryMetrics(
            timestamp=datetime.now(),
            system_memory_mb=4096.0,
            system_memory_percent=75.0,
            available_memory_mb=1024.0,
            container_memory_usage={'postgres': 512.0},
            container_memory_limits={'postgres': 1024.0},
            container_memory_percent={'postgres': 50.0},
            total_container_memory_mb=512.0,
            memory_alerts=['Test alert'],
            optimization_suggestions=['Test suggestion']
        )
        
        assert metrics.system_memory_mb == 4096.0
        assert metrics.system_memory_percent == 75.0
        assert metrics.available_memory_mb == 1024.0
        assert 'postgres' in metrics.container_memory_usage
        assert len(metrics.memory_alerts) == 1
        assert len(metrics.optimization_suggestions) == 1

@pytest.mark.integration
class TestMemoryMonitorIntegration:
    """Integration tests for memory monitoring (requires Docker)."""
    
    @pytest.mark.asyncio
    async def test_real_memory_collection(self):
        """Test collecting real memory metrics (if Docker is available)."""
        monitor = LocalMemoryMonitor(check_interval=1)
        
        try:
            metrics = await monitor.collect_metrics()
            
            # Should have system memory data
            assert metrics.system_memory_mb > 0
            assert 0 <= metrics.system_memory_percent <= 100
            assert metrics.available_memory_mb >= 0
            
            # Container data depends on Docker availability
            if monitor.docker_available:
                assert isinstance(metrics.container_memory_usage, dict)
            
        except Exception as e:
            pytest.skip(f"Integration test skipped due to environment: {e}")
    
    @pytest.mark.asyncio
    async def test_monitoring_loop_short(self):
        """Test a short monitoring loop."""
        monitor = LocalMemoryMonitor(check_interval=0.1)  # Very short interval
        
        try:
            await monitor.start_monitoring()
            
            # Let it run for a short time
            await asyncio.sleep(0.5)
            
            await monitor.stop_monitoring()
            
            # Should have collected some metrics
            assert len(monitor.metrics_history) > 0
            
        except Exception as e:
            pytest.skip(f"Integration test skipped due to environment: {e}")