"""
Test suite for service health checks implementation.

Tests the enhanced service health monitoring system including:
- ServiceHealthMonitor functionality
- Component health checks
- Automatic restart capabilities
- Graceful degradation
- Health check system integration
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch
import time

from src.multimodal_librarian.monitoring.service_health_monitor import (
    ServiceHealthMonitor, HealthStatus
)
from src.multimodal_librarian.monitoring.component_health_checks import (
    DatabaseHealthCheck, VectorStoreHealthCheck, SearchServiceHealthCheck,
    AIServiceHealthCheck, CacheHealthCheck, SystemResourcesHealthCheck
)
from src.multimodal_librarian.monitoring.health_check_system import (
    HealthCheckSystem, HealthReport, get_health_check_system
)


class TestServiceHealthMonitor:
    """Test ServiceHealthMonitor functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.monitor = ServiceHealthMonitor()
    
    def test_initialization(self):
        """Test monitor initialization."""
        assert self.monitor is not None
        assert len(self.monitor.stats) == 0
        assert len(self.monitor.restart_handlers) == 0
        assert len(self.monitor.degradation_handlers) == 0
    
    def test_record_success(self):
        """Test recording successful operations."""
        service_name = "test_service"
        
        # Record success
        self.monitor.record_success(service_name)
        
        # Check statistics
        stats = self.monitor.stats[service_name]
        assert stats['success_count'] == 1
        assert stats['failure_count'] == 0
        assert stats['consecutive_failures'] == 0
        assert stats['last_success'] is not None
        assert stats['status'] == HealthStatus.HEALTHY
    
    def test_record_failure(self):
        """Test recording failed operations."""
        service_name = "test_service"
        
        # Record failure
        self.monitor.record_failure(service_name, "Test error")
        
        # Check statistics
        stats = self.monitor.stats[service_name]
        assert stats['success_count'] == 0
        assert stats['failure_count'] == 1
        assert stats['consecutive_failures'] == 1
        assert stats['last_failure'] is not None
    
    def test_should_fallback_consecutive_failures(self):
        """Test fallback decision based on consecutive failures."""
        service_name = "test_service"
        
        # Record failures below threshold
        for _ in range(2):
            self.monitor.record_failure(service_name)
        
        assert not self.monitor.should_fallback(service_name)
        
        # Record failure at threshold
        self.monitor.record_failure(service_name)
        assert self.monitor.should_fallback(service_name)
    
    def test_should_fallback_failure_rate(self):
        """Test fallback decision based on failure rate."""
        service_name = "test_service"
        
        # Record mixed operations (60% failure rate)
        for _ in range(4):
            self.monitor.record_success(service_name)
        for _ in range(6):
            self.monitor.record_failure(service_name)
        
        assert self.monitor.should_fallback(service_name)
    
    def test_can_retry_timing(self):
        """Test retry timing logic."""
        service_name = "test_service"
        
        # Initially can retry
        assert self.monitor.can_retry(service_name)
        
        # Record failure
        self.monitor.record_failure(service_name)
        
        # Should not be able to retry immediately
        assert not self.monitor.can_retry(service_name)
        
        # Simulate time passage
        stats = self.monitor.stats[service_name]
        stats['last_failure'] = datetime.now() - timedelta(seconds=400)
        
        # Should be able to retry now
        assert self.monitor.can_retry(service_name)
    
    def test_restart_handler_registration(self):
        """Test restart handler registration."""
        service_name = "test_service"
        handler = Mock()
        
        self.monitor.register_restart_handler(service_name, handler)
        
        assert service_name in self.monitor.restart_handlers
        assert self.monitor.restart_handlers[service_name] == handler
    
    def test_degradation_handler_registration(self):
        """Test degradation handler registration."""
        service_name = "test_service"
        handler = Mock()
        
        self.monitor.register_degradation_handler(service_name, handler)
        
        assert service_name in self.monitor.degradation_handlers
        assert self.monitor.degradation_handlers[service_name] == handler
    
    def test_health_callback_registration(self):
        """Test health callback registration."""
        service_name = "test_service"
        callback = Mock()
        
        self.monitor.register_health_callback(service_name, callback)
        
        assert service_name in self.monitor.health_callbacks
        assert callback in self.monitor.health_callbacks[service_name]
    
    def test_get_service_health(self):
        """Test getting service health information."""
        service_name = "test_service"
        
        # Record some operations
        self.monitor.record_success(service_name)
        self.monitor.record_failure(service_name)
        
        health_info = self.monitor.get_service_health(service_name)
        
        assert health_info['service_name'] == service_name
        assert 'status' in health_info
        assert 'statistics' in health_info
        assert 'timestamps' in health_info
        assert 'thresholds' in health_info
        
        stats = health_info['statistics']
        assert stats['success_count'] == 1
        assert stats['failure_count'] == 1
        assert stats['total_operations'] == 2
    
    def test_get_all_services_health(self):
        """Test getting all services health information."""
        # Record operations for multiple services
        self.monitor.record_success("service1")
        self.monitor.record_failure("service2")
        
        all_health = self.monitor.get_all_services_health()
        
        assert 'overall_status' in all_health
        assert 'services' in all_health
        assert 'summary' in all_health
        assert 'timestamp' in all_health
        
        assert 'service1' in all_health['services']
        assert 'service2' in all_health['services']
        
        summary = all_health['summary']
        assert summary['total_services'] == 2


class TestComponentHealthChecks:
    """Test individual component health checks."""
    
    @pytest.mark.asyncio
    async def test_database_health_check_success(self):
        """Test successful database health check."""
        with patch('psycopg2.connect') as mock_connect:
            # Mock successful database connection
            mock_conn = Mock()
            mock_cursor = Mock()
            mock_cursor.fetchone.side_effect = [
                (1,),  # SELECT 1 result
                (1024*1024*100, 5, 10, '100'),  # Database stats
                (0,)   # Long queries
            ]
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn
            
            check = DatabaseHealthCheck()
            result = await check.run()
            
            assert result['status'] == HealthStatus.HEALTHY.value
            assert result['component'] == 'database'
            assert 'response_time_ms' in result
            assert result['details']['connection'] == 'ok'
    
    @pytest.mark.asyncio
    async def test_database_health_check_failure(self):
        """Test failed database health check."""
        with patch('psycopg2.connect', side_effect=Exception("Connection failed")):
            check = DatabaseHealthCheck()
            result = await check.run()
            
            assert result['status'] == HealthStatus.CRITICAL.value
            assert result['component'] == 'database'
            assert 'error' in result['details']
    
    @pytest.mark.asyncio
    async def test_vector_store_health_check_success(self):
        """Test successful vector store health check."""
        with patch('pymilvus.connections.connect'), \
             patch('pymilvus.utility.has_collection', return_value=True), \
             patch('pymilvus.connections.disconnect'):
            
            # Mock collection
            with patch('pymilvus.Collection') as mock_collection_class:
                mock_collection = Mock()
                mock_collection.num_entities = 1000
                mock_collection.is_loaded = True
                mock_collection_class.return_value = mock_collection
                
                check = VectorStoreHealthCheck()
                result = await check.run()
                
                assert result['status'] == HealthStatus.HEALTHY.value
                assert result['component'] == 'vector_store'
                assert result['details']['connection'] == 'ok'
                assert result['details']['collection_exists'] is True
    
    @pytest.mark.asyncio
    async def test_search_service_health_check_success(self):
        """Test successful search service health check."""
        with patch('src.multimodal_librarian.components.vector_store.search_service.SearchService') as mock_service_class:
            # Mock search service
            mock_service = AsyncMock()
            mock_result = Mock()
            mock_result.results = []
            mock_service.search.return_value = mock_result
            mock_service_class.return_value = mock_service
            
            check = SearchServiceHealthCheck()
            result = await check.run()
            
            assert result['status'] == HealthStatus.HEALTHY.value
            assert result['component'] == 'search_service'
            assert result['details']['search_execution'] == 'ok'
    
    @pytest.mark.asyncio
    async def test_ai_service_health_check_success(self):
        """Test successful AI service health check."""
        with patch('src.multimodal_librarian.services.ai_service.AIService') as mock_service_class:
            # Mock AI service
            mock_service = AsyncMock()
            mock_service.generate_response.return_value = "Test response"
            mock_service_class.return_value = mock_service
            
            check = AIServiceHealthCheck()
            result = await check.run()
            
            assert result['status'] == HealthStatus.HEALTHY.value
            assert result['component'] == 'ai_services'
            assert result['details']['ai_response_generation'] == 'ok'
    
    @pytest.mark.asyncio
    async def test_cache_health_check_success(self):
        """Test successful cache health check."""
        with patch('src.multimodal_librarian.services.cache_service.CacheService') as mock_service_class:
            # Mock cache service
            mock_service = AsyncMock()
            mock_service.set.return_value = None
            mock_service.get.return_value = {"timestamp": "2024-01-01", "test": True}
            mock_service.delete.return_value = None
            mock_service_class.return_value = mock_service
            
            check = CacheHealthCheck()
            result = await check.run()
            
            assert result['status'] == HealthStatus.HEALTHY.value
            assert result['component'] == 'cache'
            assert result['details']['cache_operations'] == 'ok'
    
    @pytest.mark.asyncio
    async def test_system_resources_health_check(self):
        """Test system resources health check."""
        with patch('psutil.cpu_percent', return_value=50.0), \
             patch('psutil.virtual_memory') as mock_memory, \
             patch('psutil.disk_usage') as mock_disk, \
             patch('psutil.net_io_counters') as mock_network, \
             patch('psutil.pids', return_value=list(range(100))):
            
            # Mock system metrics
            mock_memory.return_value = Mock(percent=60.0, available=4*1024**3, total=8*1024**3)
            mock_disk.return_value = Mock(percent=70.0, free=100*1024**3, total=500*1024**3)
            mock_network.return_value = Mock(bytes_sent=1000000, bytes_recv=2000000)
            
            check = SystemResourcesHealthCheck()
            result = await check.run()
            
            assert result['status'] == HealthStatus.HEALTHY.value
            assert result['component'] == 'system_resources'
            assert result['details']['cpu_percent'] == 50.0
            assert result['details']['memory_percent'] == 60.0


class TestHealthCheckSystem:
    """Test HealthCheckSystem integration."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.health_system = HealthCheckSystem()
    
    @pytest.mark.asyncio
    async def test_run_all_checks(self):
        """Test running all health checks."""
        # Mock all component checks to return healthy status
        for check in self.health_system.checks.values():
            check.run = AsyncMock(return_value={
                'status': HealthStatus.HEALTHY.value,
                'component': check.component_name,
                'response_time_ms': 100,
                'details': {'test': 'ok'},
                'timestamp': datetime.now().isoformat()
            })
        
        report = await self.health_system.run_all_checks()
        
        assert isinstance(report, HealthReport)
        assert report.get_overall_status() == HealthStatus.HEALTHY
        assert len(report.results) == len(self.health_system.checks)
    
    @pytest.mark.asyncio
    async def test_readiness_status(self):
        """Test readiness status check."""
        # Mock critical services as healthy
        for service_name in self.health_system.critical_services:
            if service_name in self.health_system.checks:
                self.health_system.checks[service_name].run = AsyncMock(return_value={
                    'status': HealthStatus.HEALTHY.value,
                    'component': service_name,
                    'response_time_ms': 100,
                    'details': {'test': 'ok'},
                    'timestamp': datetime.now().isoformat()
                })
        
        is_ready = await self.health_system.get_readiness_status()
        assert is_ready is True
    
    @pytest.mark.asyncio
    async def test_liveness_status(self):
        """Test liveness status check."""
        # Mock database ping
        if 'database' in self.health_system.checks:
            self.health_system.checks['database'].ping = AsyncMock(return_value=True)
        
        is_alive = await self.health_system.get_liveness_status()
        assert is_alive is True
    
    @pytest.mark.asyncio
    async def test_detailed_status(self):
        """Test getting detailed status."""
        # Mock all checks
        for check in self.health_system.checks.values():
            check.run = AsyncMock(return_value={
                'status': HealthStatus.HEALTHY.value,
                'component': check.component_name,
                'response_time_ms': 100,
                'details': {'test': 'ok'},
                'timestamp': datetime.now().isoformat()
            })
        
        detailed_status = await self.health_system.get_detailed_status()
        
        assert 'overall_status' in detailed_status
        assert 'components' in detailed_status
        assert 'service_monitor' in detailed_status
        assert 'readiness' in detailed_status
        assert 'liveness' in detailed_status
    
    def test_register_custom_check(self):
        """Test registering custom health check."""
        custom_check = Mock()
        custom_check.component_name = "custom_component"
        
        self.health_system.register_custom_check("custom", custom_check)
        
        assert "custom" in self.health_system.checks
        assert self.health_system.checks["custom"] == custom_check
    
    def test_monitoring_lifecycle(self):
        """Test starting and stopping monitoring."""
        # Start monitoring
        self.health_system.start_monitoring(interval=10)
        assert self.health_system._monitoring_active is True
        assert self.health_system._monitoring_task is not None
        
        # Stop monitoring
        self.health_system.stop_monitoring()
        assert self.health_system._monitoring_active is False


class TestHealthReport:
    """Test HealthReport functionality."""
    
    def test_initialization(self):
        """Test report initialization."""
        report = HealthReport()
        
        assert len(report.results) == 0
        assert report.overall_status == HealthStatus.UNKNOWN
        assert report.total_response_time == 0
    
    def test_add_check_result(self):
        """Test adding check results."""
        report = HealthReport()
        
        result = {
            'status': HealthStatus.HEALTHY.value,
            'component': 'test',
            'response_time_ms': 150,
            'details': {'test': 'ok'}
        }
        
        report.add_check_result('test_component', result)
        
        assert 'test_component' in report.results
        assert report.results['test_component'] == result
        assert report.total_response_time == 150
    
    def test_get_overall_status(self):
        """Test overall status calculation."""
        report = HealthReport()
        
        # Add healthy component
        report.add_check_result('healthy', {'status': HealthStatus.HEALTHY.value})
        assert report.get_overall_status() == HealthStatus.HEALTHY
        
        # Add degraded component
        report.add_check_result('degraded', {'status': HealthStatus.DEGRADED.value})
        assert report.get_overall_status() == HealthStatus.DEGRADED
        
        # Add critical component
        report.add_check_result('critical', {'status': HealthStatus.CRITICAL.value})
        assert report.get_overall_status() == HealthStatus.CRITICAL
    
    def test_to_dict(self):
        """Test converting report to dictionary."""
        report = HealthReport()
        
        report.add_check_result('test', {
            'status': HealthStatus.HEALTHY.value,
            'response_time_ms': 100
        })
        
        result_dict = report.to_dict()
        
        assert 'overall_status' in result_dict
        assert 'components' in result_dict
        assert 'summary' in result_dict
        assert 'timestamp' in result_dict
        
        summary = result_dict['summary']
        assert summary['total_components'] == 1
        assert summary['healthy_components'] == 1
        assert summary['total_response_time_ms'] == 100


class TestIntegration:
    """Integration tests for the complete health check system."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_health_check(self):
        """Test complete end-to-end health check flow."""
        health_system = get_health_check_system()
        
        # Mock all component checks
        for check in health_system.checks.values():
            check.run = AsyncMock(return_value={
                'status': HealthStatus.HEALTHY.value,
                'component': check.component_name,
                'response_time_ms': 100,
                'details': {'test': 'ok'},
                'timestamp': datetime.now().isoformat()
            })
        
        # Run comprehensive health check
        detailed_status = await health_system.get_detailed_status()
        
        # Verify results
        assert detailed_status['overall_status'] == HealthStatus.HEALTHY.value
        assert len(detailed_status['components']) > 0
        assert detailed_status['readiness'] is True
        assert detailed_status['liveness'] is True
    
    @pytest.mark.asyncio
    async def test_failure_handling_and_recovery(self):
        """Test failure handling and recovery mechanisms."""
        health_system = get_health_check_system()
        
        # Mock restart handler
        restart_called = False
        async def mock_restart():
            nonlocal restart_called
            restart_called = True
            return True
        
        health_system.register_custom_restart_handler('test_service', mock_restart)
        
        # Simulate multiple failures to trigger restart
        monitor = health_system.health_monitor
        for _ in range(6):  # Exceed restart threshold
            monitor.record_failure('test_service', 'Test failure')
        
        # Wait a bit for async restart to potentially trigger
        await asyncio.sleep(0.1)
        
        # Verify failure was recorded
        service_health = monitor.get_service_health('test_service')
        assert service_health['statistics']['failure_count'] == 6
        assert service_health['status'] == HealthStatus.CRITICAL.value


if __name__ == "__main__":
    pytest.main([__file__, "-v"])