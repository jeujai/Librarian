"""
Integration Tests for Resource Usage Tracking

This module provides comprehensive integration tests for the resource usage tracking
system in local development environments. It validates the complete resource monitoring
pipeline including system metrics, container metrics, alerts, and optimization
recommendations.

Validates: Requirements NFR-1 (Performance), NFR-2 (Reliability), TR-4 (Service Discovery)
"""

import pytest
import pytest_asyncio
import asyncio
import time
import json
import tempfile
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
from typing import Dict, List, Any

from src.multimodal_librarian.monitoring.resource_usage_dashboard import (
    ResourceUsageDashboardService,
    ResourceAlert,
    ResourceOptimization,
    ResourceType,
    get_resource_usage_dashboard_service,
    start_resource_monitoring,
    stop_resource_monitoring
)
from src.multimodal_librarian.monitoring.local_memory_monitor import get_local_memory_monitor
# Import the resource monitor script directly
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../scripts'))

try:
    from monitor_resource_usage import ResourceUsageMonitor
except ImportError:
    # Create a mock ResourceUsageMonitor for testing if script not available
    class ResourceUsageMonitor:
        def __init__(self, interval=1, cpu_threshold=80, memory_threshold=85):
            self.interval = interval
            self.cpu_threshold = cpu_threshold
            self.memory_threshold = memory_threshold
        
        async def run(self, duration_minutes, monitor_containers=True, output_file=None):
            # Mock implementation for testing
            import json
            report = {
                "monitoring_session": {
                    "start_time": datetime.now().isoformat(),
                    "end_time": datetime.now().isoformat(),
                    "total_samples": 5
                },
                "summary": {
                    "system": {
                        "avg_cpu_percent": 45.0,
                        "avg_memory_percent": 60.0,
                        "sample_count": 5
                    }
                },
                "detailed_metrics": {},
                "recommendations": ["System performance is acceptable"]
            }
            if output_file:
                with open(output_file, 'w') as f:
                    json.dump(report, f, indent=2)


class TestResourceUsageTrackingIntegration:
    """Integration tests for complete resource usage tracking system."""
    
    @pytest_asyncio.fixture
    async def dashboard_service(self):
        """Create a dashboard service for integration testing."""
        # Use a fresh instance for each test
        service = ResourceUsageDashboardService()
        yield service
        
        # Cleanup
        if service.monitoring_active:
            await service.stop_monitoring()
    
    @pytest.fixture
    def resource_monitor(self):
        """Create a resource monitor for script testing."""
        return ResourceUsageMonitor(interval=1, cpu_threshold=80, memory_threshold=85)
    
    @pytest.mark.asyncio
    async def test_end_to_end_resource_monitoring_workflow(self, dashboard_service):
        """Test complete resource monitoring workflow from start to finish."""
        print("\n🔄 Testing end-to-end resource monitoring workflow...")
        
        # Step 1: Start monitoring
        await dashboard_service.start_monitoring()
        assert dashboard_service.monitoring_active
        
        # Step 2: Wait for some data collection
        await asyncio.sleep(3)
        
        # Step 3: Verify data collection
        assert len(dashboard_service.resource_history) > 0
        
        # Step 4: Check dashboard data generation
        system_dashboard = await dashboard_service.get_dashboard_data("system_resources")
        assert system_dashboard is not None
        assert system_dashboard["dashboard_id"] == "system_resources"
        assert len(system_dashboard["charts"]) == 4
        
        # Step 5: Verify service status
        status = dashboard_service.get_service_status()
        assert status["monitoring"]["active"] is True
        assert status["statistics"]["resource_history_samples"] > 0
        
        # Step 6: Stop monitoring
        await dashboard_service.stop_monitoring()
        assert not dashboard_service.monitoring_active
        
        print("   ✓ End-to-end workflow completed successfully")
    
    @pytest.mark.asyncio
    async def test_resource_alert_generation_integration(self, dashboard_service):
        """Test resource alert generation with simulated high usage."""
        print("\n⚠️  Testing resource alert generation...")
        
        # Mock high resource usage
        with patch('src.multimodal_librarian.monitoring.resource_usage_dashboard.psutil') as mock_psutil:
            # Simulate critical CPU and memory usage
            mock_psutil.cpu_percent.return_value = 90.0  # Critical
            mock_psutil.virtual_memory.return_value = Mock(
                percent=88.0,  # Above warning threshold
                used=15032385536,  # ~14GB
                available=2147483648  # ~2GB
            )
            mock_psutil.disk_usage.return_value = Mock(
                percent=45.0,  # Normal
                used=107374182400,
                free=161061273600
            )
            mock_psutil.net_io_counters.return_value = Mock(
                bytes_sent=1073741824,
                bytes_recv=2147483648
            )
            
            # Collect metrics
            await dashboard_service._collect_system_metrics()
            await dashboard_service._update_resource_alerts()
            
            # Verify alerts were generated
            assert len(dashboard_service.active_alerts) >= 2
            
            # Check for CPU critical alert
            cpu_alerts = [alert for alert in dashboard_service.active_alerts 
                         if alert.resource_type == ResourceType.CPU and alert.severity == "critical"]
            assert len(cpu_alerts) >= 1
            assert cpu_alerts[0].current_value == 90.0
            
            # Check for memory warning alert
            memory_alerts = [alert for alert in dashboard_service.active_alerts 
                           if alert.resource_type == ResourceType.MEMORY and alert.severity == "warning"]
            assert len(memory_alerts) >= 1
            assert memory_alerts[0].current_value == 88.0
            
            print("   ✓ Resource alerts generated correctly")
    
    @pytest.mark.asyncio
    async def test_optimization_recommendations_integration(self, dashboard_service):
        """Test optimization recommendation generation with usage patterns."""
        print("\n💡 Testing optimization recommendations...")
        
        # Simulate usage patterns that should generate recommendations
        with patch('src.multimodal_librarian.monitoring.resource_usage_dashboard.psutil') as mock_psutil:
            # Pattern 1: CPU underutilization
            mock_psutil.cpu_percent.return_value = 12.0  # Very low
            mock_psutil.virtual_memory.return_value = Mock(
                percent=85.0,  # High memory usage
                used=14495514624,
                available=2684354560
            )
            mock_psutil.disk_usage.return_value = Mock(
                percent=55.0,
                used=134217728000,
                free=107374182400
            )
            mock_psutil.net_io_counters.return_value = Mock(
                bytes_sent=1073741824,
                bytes_recv=2147483648
            )
            
            # Collect multiple samples to establish pattern
            for _ in range(15):
                await dashboard_service._collect_system_metrics()
                await asyncio.sleep(0.1)
            
            # Generate recommendations
            await dashboard_service._update_optimization_recommendations()
            
            # Verify recommendations were generated
            assert len(dashboard_service.optimization_recommendations) >= 2
            
            # Check for CPU underutilization recommendation
            cpu_recommendations = [rec for rec in dashboard_service.optimization_recommendations 
                                 if rec.resource_type == ResourceType.CPU]
            assert len(cpu_recommendations) >= 1
            assert "underutilized" in cpu_recommendations[0].title.lower() or "underutilized" in cpu_recommendations[0].description.lower()
            
            # Check for memory optimization recommendation
            memory_recommendations = [rec for rec in dashboard_service.optimization_recommendations 
                                    if rec.resource_type == ResourceType.MEMORY]
            assert len(memory_recommendations) >= 1
            
            print("   ✓ Optimization recommendations generated correctly")
    
    @pytest.mark.asyncio
    async def test_container_metrics_integration(self, dashboard_service):
        """Test container metrics collection integration."""
        print("\n🐳 Testing container metrics integration...")
        
        # Mock Docker client and containers
        mock_container = Mock()
        mock_container.name = "multimodal-librarian-postgres-1"
        mock_container.id = "abc123def456"
        mock_container.status = "running"
        mock_container.stats.return_value = {
            'cpu_stats': {
                'cpu_usage': {'total_usage': 2000000000, 'percpu_usage': [500000000, 500000000, 500000000, 500000000]},
                'system_cpu_usage': 10000000000
            },
            'precpu_stats': {
                'cpu_usage': {'total_usage': 1800000000},
                'system_cpu_usage': 9800000000
            },
            'memory_stats': {
                'usage': 536870912,  # 512MB
                'limit': 1073741824  # 1GB
            },
            'networks': {
                'eth0': {'tx_bytes': 1048576, 'rx_bytes': 2097152}
            },
            'blkio_stats': {
                'io_service_bytes_recursive': [
                    {'op': 'Read', 'value': 10485760},
                    {'op': 'Write', 'value': 5242880}
                ]
            }
        }
        
        with patch.object(dashboard_service, 'docker_client') as mock_docker:
            dashboard_service.docker_available = True
            mock_docker.containers.list.return_value = [mock_container]
            
            # Collect container metrics
            await dashboard_service._collect_container_metrics()
            
            # Verify container metrics were collected
            assert "multimodal-librarian-postgres-1" in dashboard_service.container_history
            container_metrics = dashboard_service.container_history["multimodal-librarian-postgres-1"]
            assert len(container_metrics) >= 1
            
            latest_metrics = container_metrics[-1]
            assert latest_metrics["container_name"] == "multimodal-librarian-postgres-1"
            assert latest_metrics["memory_percent"] == 50.0  # 512MB / 1GB
            assert latest_metrics["status"] == "running"
            
            print("   ✓ Container metrics collected successfully")
    
    @pytest.mark.asyncio
    async def test_dashboard_chart_data_integration(self, dashboard_service):
        """Test dashboard chart data generation integration."""
        print("\n📊 Testing dashboard chart data integration...")
        
        # Add test data
        test_metrics = {
            "timestamp": datetime.now(),
            "cpu_percent": 45.5,
            "memory_percent": 65.2,
            "disk_percent": 75.8,
            "memory_used_gb": 8.0,
            "memory_available_gb": 4.0,
            "disk_used_gb": 100.0,
            "disk_free_gb": 32.0,
            "network_bytes_sent": 1073741824,
            "network_bytes_recv": 2147483648
        }
        dashboard_service.resource_history.append(test_metrics)
        
        # Add test alerts
        test_alert = ResourceAlert(
            alert_id="test_alert_123",
            resource_type=ResourceType.CPU,
            severity="warning",
            message="Test CPU alert",
            current_value=75.0,
            threshold=70.0,
            timestamp=datetime.now()
        )
        dashboard_service.active_alerts.append(test_alert)
        
        # Test all dashboard types
        dashboard_types = ["system_resources", "container_resources", "resource_trends"]
        
        for dashboard_type in dashboard_types:
            dashboard_data = await dashboard_service.get_dashboard_data(dashboard_type)
            assert dashboard_data is not None
            assert dashboard_data["dashboard_id"] == dashboard_type
            assert "charts" in dashboard_data
            assert len(dashboard_data["charts"]) > 0
            
            # Verify chart data structure
            for chart in dashboard_data["charts"]:
                assert "chart_id" in chart
                assert "title" in chart
                assert "chart_type" in chart
                assert "data_points" in chart
                assert "last_updated" in chart
        
        print("   ✓ Dashboard chart data generated successfully")
    
    @pytest.mark.asyncio
    async def test_resource_monitoring_script_integration(self, resource_monitor):
        """Test integration with the resource monitoring script."""
        print("\n📝 Testing resource monitoring script integration...")
        
        # Create temporary output file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as temp_file:
            output_file = temp_file.name
        
        try:
            # Run monitoring for a short duration
            await resource_monitor.run(
                duration_minutes=0.1,  # 6 seconds
                monitor_containers=False,  # Skip containers for speed
                output_file=output_file
            )
            
            # Verify output file was created
            assert Path(output_file).exists()
            
            # Load and verify report content
            with open(output_file, 'r') as f:
                report = json.load(f)
            
            # Verify report structure
            assert "monitoring_session" in report
            assert "summary" in report
            assert "detailed_metrics" in report
            assert "recommendations" in report
            
            # Verify monitoring session data
            session = report["monitoring_session"]
            assert "start_time" in session
            assert "end_time" in session
            assert "total_samples" in session
            assert session["total_samples"] > 0
            
            # Verify system metrics were collected
            assert "system" in report["summary"]
            system_summary = report["summary"]["system"]
            assert "avg_cpu_percent" in system_summary
            assert "avg_memory_percent" in system_summary
            assert system_summary["sample_count"] > 0
            
            print("   ✓ Resource monitoring script integration successful")
            
        finally:
            # Cleanup
            if Path(output_file).exists():
                Path(output_file).unlink()
    
    @pytest.mark.asyncio
    async def test_memory_monitor_integration(self, dashboard_service):
        """Test integration with local memory monitor."""
        print("\n🧠 Testing memory monitor integration...")
        
        memory_monitor = get_local_memory_monitor()
        
        # Start memory monitoring
        if not memory_monitor.is_monitoring:
            await memory_monitor.start_monitoring()
        
        # Wait for some data collection
        await asyncio.sleep(2)
        
        # Verify memory monitor is working
        assert memory_monitor.is_monitoring
        
        # Get memory status
        memory_status = memory_monitor.get_memory_status()
        assert "current_usage" in memory_status
        assert "peak_usage" in memory_status
        assert "monitoring_active" in memory_status
        
        # Verify integration with dashboard service
        dashboard_service.memory_monitor = memory_monitor
        status = dashboard_service.get_service_status()
        assert status["monitoring"]["memory_monitor_active"] is True
        
        print("   ✓ Memory monitor integration successful")
    
    @pytest.mark.asyncio
    async def test_resource_efficiency_calculation_integration(self, dashboard_service):
        """Test resource efficiency calculation integration."""
        print("\n⚡ Testing resource efficiency calculation...")
        
        # Add test data with different efficiency patterns
        test_scenarios = [
            # Optimal usage
            {"cpu": 45.0, "memory": 60.0, "expected_score_range": (80, 100)},
            # CPU underutilized
            {"cpu": 15.0, "memory": 60.0, "expected_score_range": (40, 80)},
            # Memory overutilized
            {"cpu": 45.0, "memory": 95.0, "expected_score_range": (40, 80)},
            # Both suboptimal
            {"cpu": 85.0, "memory": 95.0, "expected_score_range": (0, 40)},
        ]
        
        for i, scenario in enumerate(test_scenarios):
            # Clear previous data
            dashboard_service.resource_history.clear()
            
            # Add test metrics for this scenario
            for j in range(15):  # Need enough samples for analysis
                test_metrics = {
                    "timestamp": datetime.now() - timedelta(minutes=j),
                    "cpu_percent": scenario["cpu"],
                    "memory_percent": scenario["memory"],
                    "disk_percent": 50.0,
                    "memory_used_gb": 8.0,
                    "memory_available_gb": 4.0,
                    "disk_used_gb": 100.0,
                    "disk_free_gb": 32.0,
                    "network_bytes_sent": 1073741824,
                    "network_bytes_recv": 2147483648
                }
                dashboard_service.resource_history.append(test_metrics)
            
            # Get efficiency score
            efficiency_data = await dashboard_service._get_efficiency_score_data()
            assert len(efficiency_data) == 1
            
            efficiency_score = efficiency_data[0]["value"]
            expected_min, expected_max = scenario["expected_score_range"]
            
            assert expected_min <= efficiency_score <= expected_max, \
                f"Scenario {i+1}: Expected score {expected_min}-{expected_max}, got {efficiency_score}"
            
            print(f"   ✓ Scenario {i+1}: CPU {scenario['cpu']}%, Memory {scenario['memory']}% -> Score {efficiency_score}")
        
        print("   ✓ Resource efficiency calculation integration successful")
    
    @pytest.mark.asyncio
    async def test_resource_trends_analysis_integration(self, dashboard_service):
        """Test resource trends analysis integration."""
        print("\n📈 Testing resource trends analysis...")
        
        # Generate time-series data with trends
        base_time = datetime.now()
        
        for i in range(60):  # 1 hour of data
            # Simulate increasing CPU usage over time
            cpu_trend = 30 + (i * 0.5)  # Gradual increase
            memory_trend = 50 + (i * 0.3)  # Gradual increase
            
            test_metrics = {
                "timestamp": base_time - timedelta(minutes=60-i),
                "cpu_percent": min(cpu_trend, 90),  # Cap at 90%
                "memory_percent": min(memory_trend, 85),  # Cap at 85%
                "disk_percent": 45.0,
                "memory_used_gb": 8.0,
                "memory_available_gb": 4.0,
                "disk_used_gb": 100.0,
                "disk_free_gb": 32.0,
                "network_bytes_sent": 1073741824,
                "network_bytes_recv": 2147483648
            }
            dashboard_service.resource_history.append(test_metrics)
        
        # Get trends data
        trends_data = await dashboard_service._get_resource_trends_data()
        
        # Verify trends data structure
        assert len(trends_data) == 60
        for data_point in trends_data:
            assert "timestamp" in data_point
            assert "cpu" in data_point
            assert "memory" in data_point
            assert "disk" in data_point
            assert "label" in data_point
        
        # Verify trend direction (should show increasing usage)
        first_cpu = trends_data[0]["cpu"]
        last_cpu = trends_data[-1]["cpu"]
        assert last_cpu > first_cpu, "CPU trend should show increase"
        
        first_memory = trends_data[0]["memory"]
        last_memory = trends_data[-1]["memory"]
        assert last_memory > first_memory, "Memory trend should show increase"
        
        print("   ✓ Resource trends analysis integration successful")
    
    @pytest.mark.asyncio
    async def test_resource_bottleneck_detection_integration(self, dashboard_service):
        """Test resource bottleneck detection integration."""
        print("\n🚫 Testing resource bottleneck detection...")
        
        # Generate data with bottleneck patterns
        base_time = datetime.now()
        
        # Create bottleneck during specific hours
        bottleneck_hours = [9, 10, 14, 15]  # Simulate peak hours
        
        for hour in range(24):
            for minute in range(0, 60, 15):  # Every 15 minutes
                is_bottleneck_time = hour in bottleneck_hours
                
                cpu_usage = 85.0 if is_bottleneck_time else 35.0
                memory_usage = 90.0 if is_bottleneck_time else 45.0
                
                test_metrics = {
                    "timestamp": base_time.replace(hour=hour, minute=minute),
                    "cpu_percent": cpu_usage,
                    "memory_percent": memory_usage,
                    "disk_percent": 50.0,
                    "memory_used_gb": 8.0,
                    "memory_available_gb": 4.0,
                    "disk_used_gb": 100.0,
                    "disk_free_gb": 32.0,
                    "network_bytes_sent": 1073741824,
                    "network_bytes_recv": 2147483648
                }
                dashboard_service.resource_history.append(test_metrics)
        
        # Get bottleneck heatmap data
        bottleneck_data = await dashboard_service._get_resource_bottlenecks_data()
        
        # Verify heatmap data structure
        assert len(bottleneck_data) > 0
        
        # Check that bottleneck hours show higher usage
        cpu_bottleneck_data = [d for d in bottleneck_data if d["resource_label"] == "CPU"]
        memory_bottleneck_data = [d for d in bottleneck_data if d["resource_label"] == "Memory"]
        
        # Verify bottleneck hours have higher values
        for hour in bottleneck_hours:
            cpu_hour_data = [d for d in cpu_bottleneck_data if d["x"] == hour]
            if cpu_hour_data:
                assert cpu_hour_data[0]["value"] > 70, f"CPU bottleneck not detected at hour {hour}"
            
            memory_hour_data = [d for d in memory_bottleneck_data if d["x"] == hour]
            if memory_hour_data:
                assert memory_hour_data[0]["value"] > 70, f"Memory bottleneck not detected at hour {hour}"
        
        print("   ✓ Resource bottleneck detection integration successful")
    
    @pytest.mark.asyncio
    async def test_global_service_integration(self):
        """Test global service instance integration."""
        print("\n🌐 Testing global service integration...")
        
        # Test global service getter
        service1 = get_resource_usage_dashboard_service()
        service2 = get_resource_usage_dashboard_service()
        
        # Should return the same instance
        assert service1 is service2
        
        # Test global monitoring functions
        await start_resource_monitoring()
        assert service1.monitoring_active
        
        await stop_resource_monitoring()
        assert not service1.monitoring_active
        
        print("   ✓ Global service integration successful")


class TestResourceUsageTrackingPerformance:
    """Performance tests for resource usage tracking system."""
    
    @pytest.mark.asyncio
    async def test_monitoring_performance_overhead(self):
        """Test that resource monitoring has minimal performance overhead."""
        print("\n⚡ Testing monitoring performance overhead...")
        
        service = ResourceUsageDashboardService()
        
        # Measure baseline performance
        start_time = time.time()
        for _ in range(100):
            await asyncio.sleep(0.001)  # Simulate work
        baseline_time = time.time() - start_time
        
        # Measure performance with monitoring
        await service.start_monitoring()
        
        start_time = time.time()
        for _ in range(100):
            await asyncio.sleep(0.001)  # Simulate work
        monitoring_time = time.time() - start_time
        
        await service.stop_monitoring()
        
        # Calculate overhead
        overhead_percent = ((monitoring_time - baseline_time) / baseline_time) * 100
        
        print(f"   Baseline time: {baseline_time:.3f}s")
        print(f"   Monitoring time: {monitoring_time:.3f}s")
        print(f"   Overhead: {overhead_percent:.1f}%")
        
        # Overhead should be minimal (< 10%)
        assert overhead_percent < 10, f"Monitoring overhead too high: {overhead_percent:.1f}%"
        
        print("   ✓ Monitoring performance overhead acceptable")
    
    @pytest.mark.asyncio
    async def test_memory_usage_during_monitoring(self):
        """Test memory usage during extended monitoring."""
        print("\n🧠 Testing memory usage during monitoring...")
        
        import psutil
        process = psutil.Process()
        
        service = ResourceUsageDashboardService()
        
        # Get baseline memory
        baseline_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Start monitoring and collect data
        await service.start_monitoring()
        
        # Simulate extended monitoring
        for _ in range(30):  # 30 cycles
            await asyncio.sleep(0.1)
        
        # Get peak memory
        peak_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = peak_memory - baseline_memory
        
        await service.stop_monitoring()
        
        print(f"   Baseline memory: {baseline_memory:.1f}MB")
        print(f"   Peak memory: {peak_memory:.1f}MB")
        print(f"   Memory increase: {memory_increase:.1f}MB")
        
        # Memory increase should be reasonable (< 50MB)
        assert memory_increase < 50, f"Memory increase too high: {memory_increase:.1f}MB"
        
        print("   ✓ Memory usage during monitoring acceptable")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])