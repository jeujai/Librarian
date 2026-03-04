"""
Tests for Performance Debugging Tools

Tests the performance debugger functionality including monitoring,
metrics collection, and profiling capabilities.
"""

import pytest
import asyncio
import time
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timedelta

from src.multimodal_librarian.development.performance_debugger import (
    PerformanceDebugger, 
    PerformanceMetric, 
    QueryPerformanceData,
    ResourceUsageSnapshot,
    get_performance_debugger
)
from src.multimodal_librarian.config.local_config import LocalDatabaseConfig


class TestPerformanceDebugger:
    """Test suite for PerformanceDebugger class."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return LocalDatabaseConfig()
    
    @pytest.fixture
    def debugger(self, config):
        """Create test debugger instance."""
        return PerformanceDebugger(config)
    
    def test_debugger_initialization(self, debugger):
        """Test debugger initialization."""
        assert debugger.config is not None
        assert debugger.factory is not None
        assert debugger.metrics == []
        assert debugger.query_data == []
        assert debugger.resource_snapshots == []
        assert debugger.monitoring_active is False
    
    @pytest.mark.asyncio
    async def test_start_stop_monitoring(self, debugger):
        """Test starting and stopping monitoring."""
        # Test start monitoring
        result = await debugger.start_monitoring(1)
        assert result["status"] == "started"
        assert debugger.monitoring_active is True
        
        # Wait a moment for monitoring to collect data
        await asyncio.sleep(2)
        
        # Test stop monitoring
        result = await debugger.stop_monitoring()
        assert result["status"] == "stopped"
        assert debugger.monitoring_active is False
        assert result["metrics_collected"] >= 0
    
    @pytest.mark.asyncio
    async def test_start_monitoring_already_running(self, debugger):
        """Test starting monitoring when already running."""
        await debugger.start_monitoring(1)
        
        # Try to start again
        result = await debugger.start_monitoring(1)
        assert result["status"] == "already_running"
        
        # Cleanup
        await debugger.stop_monitoring()
    
    @pytest.mark.asyncio
    async def test_stop_monitoring_not_running(self, debugger):
        """Test stopping monitoring when not running."""
        result = await debugger.stop_monitoring()
        assert result["status"] == "not_running"
    
    @pytest.mark.asyncio
    async def test_measure_operation_context_manager(self, debugger):
        """Test the measure_operation context manager."""
        initial_metrics_count = len(debugger.metrics)
        
        async with debugger.measure_operation("test_operation", {"test": True}):
            # Simulate some work
            await asyncio.sleep(0.1)
        
        # Check that metrics were added
        assert len(debugger.metrics) > initial_metrics_count
        
        # Find the execution time metric
        execution_metrics = [m for m in debugger.metrics if "execution_time" in m.name]
        assert len(execution_metrics) > 0
        
        metric = execution_metrics[-1]
        assert metric.name == "test_operation_execution_time"
        assert metric.value >= 100  # At least 100ms
        assert metric.unit == "ms"
        assert metric.context == {"test": True}
    
    def test_performance_metric_creation(self):
        """Test PerformanceMetric creation."""
        metric = PerformanceMetric(
            name="test_metric",
            value=123.45,
            unit="ms",
            timestamp=datetime.now(),
            context={"test": True}
        )
        
        assert metric.name == "test_metric"
        assert metric.value == 123.45
        assert metric.unit == "ms"
        assert metric.context == {"test": True}
    
    def test_query_performance_data_creation(self):
        """Test QueryPerformanceData creation."""
        query_data = QueryPerformanceData(
            query_type="SELECT",
            database="postgresql",
            execution_time=0.05,
            rows_affected=10
        )
        
        assert query_data.query_type == "SELECT"
        assert query_data.database == "postgresql"
        assert query_data.execution_time == 0.05
        assert query_data.rows_affected == 10
        assert query_data.timestamp is not None
    
    def test_resource_usage_snapshot_creation(self):
        """Test ResourceUsageSnapshot creation."""
        snapshot = ResourceUsageSnapshot(
            timestamp=datetime.now(),
            cpu_percent=50.0,
            memory_percent=60.0,
            memory_used_mb=1024.0,
            disk_io_read_mb=10.0,
            disk_io_write_mb=5.0,
            network_sent_mb=2.0,
            network_recv_mb=3.0,
            docker_containers={"test": {"status": "running"}}
        )
        
        assert snapshot.cpu_percent == 50.0
        assert snapshot.memory_percent == 60.0
        assert snapshot.docker_containers == {"test": {"status": "running"}}
    
    def test_get_performance_summary_no_data(self, debugger):
        """Test performance summary with no data."""
        summary = debugger.get_performance_summary(10)
        
        assert summary["time_range_minutes"] == 10
        assert summary["metrics_count"] == 0
        assert summary["queries_analyzed"] == 0
        assert summary["resource_snapshots"] == 0
        assert summary["database_performance"] == {"status": "no_data"}
        assert summary["resource_usage"] == {"status": "no_data"}
    
    def test_get_performance_summary_with_data(self, debugger):
        """Test performance summary with sample data."""
        # Add sample metrics
        now = datetime.now()
        debugger.metrics.append(PerformanceMetric(
            name="test_metric",
            value=100.0,
            unit="ms",
            timestamp=now
        ))
        
        # Add sample query data
        debugger.query_data.append(QueryPerformanceData(
            query_type="SELECT",
            database="postgresql",
            execution_time=0.05,
            timestamp=now
        ))
        
        # Add sample resource snapshot
        debugger.resource_snapshots.append(ResourceUsageSnapshot(
            timestamp=now,
            cpu_percent=50.0,
            memory_percent=60.0,
            memory_used_mb=1024.0,
            disk_io_read_mb=10.0,
            disk_io_write_mb=5.0,
            network_sent_mb=2.0,
            network_recv_mb=3.0,
            docker_containers={}
        ))
        
        summary = debugger.get_performance_summary(10)
        
        assert summary["metrics_count"] == 1
        assert summary["queries_analyzed"] == 1
        assert summary["resource_snapshots"] == 1
        assert "postgresql" in summary["database_performance"]
        assert "cpu" in summary["resource_usage"]
    
    def test_identify_bottlenecks(self, debugger):
        """Test bottleneck identification."""
        # Add high CPU usage snapshot
        debugger.resource_snapshots.append(ResourceUsageSnapshot(
            timestamp=datetime.now(),
            cpu_percent=95.0,  # High CPU
            memory_percent=50.0,
            memory_used_mb=1024.0,
            disk_io_read_mb=10.0,
            disk_io_write_mb=5.0,
            network_sent_mb=2.0,
            network_recv_mb=3.0,
            docker_containers={}
        ))
        
        # Add slow query metric
        debugger.metrics.append(PerformanceMetric(
            name="slow_query_time",
            value=2000.0,  # 2 seconds
            unit="ms",
            timestamp=datetime.now()
        ))
        
        summary = debugger.get_performance_summary(10)
        bottlenecks = summary["bottlenecks"]
        
        assert len(bottlenecks) >= 2
        
        # Check for high CPU bottleneck
        cpu_bottlenecks = [b for b in bottlenecks if b["type"] == "high_cpu_usage"]
        assert len(cpu_bottlenecks) > 0
        assert cpu_bottlenecks[0]["severity"] == "high"
        
        # Check for slow query bottleneck
        query_bottlenecks = [b for b in bottlenecks if b["type"] == "slow_database_query"]
        assert len(query_bottlenecks) > 0
    
    def test_generate_recommendations(self, debugger):
        """Test recommendation generation."""
        # Add high memory usage
        debugger.resource_snapshots.append(ResourceUsageSnapshot(
            timestamp=datetime.now(),
            cpu_percent=50.0,
            memory_percent=85.0,  # High memory
            memory_used_mb=2048.0,
            disk_io_read_mb=10.0,
            disk_io_write_mb=5.0,
            network_sent_mb=2.0,
            network_recv_mb=3.0,
            docker_containers={}
        ))
        
        summary = debugger.get_performance_summary(10)
        recommendations = summary["recommendations"]
        
        assert len(recommendations) > 0
        assert any("memory" in rec.lower() for rec in recommendations)
    
    def test_export_metrics(self, debugger, tmp_path):
        """Test metrics export functionality."""
        # Add sample data
        debugger.metrics.append(PerformanceMetric(
            name="test_metric",
            value=100.0,
            unit="ms",
            timestamp=datetime.now()
        ))
        
        # Export to temporary file
        filepath = tmp_path / "test_export.json"
        result = debugger.export_metrics(str(filepath))
        
        assert result["status"] == "success"
        assert result["filepath"] == str(filepath)
        assert result["metrics_exported"] == 1
        assert filepath.exists()
        
        # Verify file content
        import json
        with open(filepath) as f:
            data = json.load(f)
        
        assert "export_timestamp" in data
        assert "metrics" in data
        assert len(data["metrics"]) == 1
    
    def test_clear_data(self, debugger):
        """Test data clearing functionality."""
        # Add sample data
        debugger.metrics.append(PerformanceMetric(
            name="test_metric",
            value=100.0,
            unit="ms",
            timestamp=datetime.now()
        ))
        
        debugger.query_data.append(QueryPerformanceData(
            query_type="SELECT",
            database="postgresql",
            execution_time=0.05
        ))
        
        # Clear data
        result = debugger.clear_data()
        
        assert result["status"] == "cleared"
        assert result["metrics_cleared"] == 1
        assert result["queries_cleared"] == 1
        assert len(debugger.metrics) == 0
        assert len(debugger.query_data) == 0
    
    def test_global_debugger_instance(self):
        """Test global debugger instance management."""
        config = LocalDatabaseConfig()
        
        # Get first instance
        debugger1 = get_performance_debugger(config)
        
        # Get second instance (should be same)
        debugger2 = get_performance_debugger()
        
        assert debugger1 is debugger2
    
    @patch('psutil.cpu_percent')
    @patch('psutil.virtual_memory')
    @patch('psutil.disk_io_counters')
    @patch('psutil.net_io_counters')
    def test_collect_resource_snapshot_mocked(self, mock_net, mock_disk, mock_memory, mock_cpu, debugger):
        """Test resource snapshot collection with mocked psutil."""
        # Mock psutil returns
        mock_cpu.return_value = 75.0
        
        mock_memory_obj = Mock()
        mock_memory_obj.percent = 80.0
        mock_memory_obj.used = 2048 * 1024 * 1024  # 2GB in bytes
        mock_memory.return_value = mock_memory_obj
        
        mock_disk_obj = Mock()
        mock_disk_obj.read_bytes = 100 * 1024 * 1024  # 100MB
        mock_disk_obj.write_bytes = 50 * 1024 * 1024   # 50MB
        mock_disk.return_value = mock_disk_obj
        
        mock_net_obj = Mock()
        mock_net_obj.bytes_sent = 10 * 1024 * 1024     # 10MB
        mock_net_obj.bytes_recv = 20 * 1024 * 1024     # 20MB
        mock_net.return_value = mock_net_obj
        
        # Test resource collection
        initial_count = len(debugger.resource_snapshots)
        
        # Call the private method directly for testing
        asyncio.run(debugger._collect_resource_snapshot())
        
        assert len(debugger.resource_snapshots) == initial_count + 1
        
        snapshot = debugger.resource_snapshots[-1]
        assert snapshot.cpu_percent == 75.0
        assert snapshot.memory_percent == 80.0
        assert snapshot.memory_used_mb == 2048.0
        assert snapshot.disk_io_read_mb == 100.0
        assert snapshot.disk_io_write_mb == 50.0
        assert snapshot.network_sent_mb == 10.0
        assert snapshot.network_recv_mb == 20.0


class TestPerformanceDebuggingIntegration:
    """Integration tests for performance debugging tools."""
    
    @pytest.mark.asyncio
    async def test_end_to_end_monitoring(self):
        """Test end-to-end monitoring workflow."""
        config = LocalDatabaseConfig()
        debugger = get_performance_debugger(config)
        
        try:
            # Start monitoring
            result = await debugger.start_monitoring(1)
            assert result["status"] == "started"
            
            # Perform some operations
            async with debugger.measure_operation("test_workflow"):
                await asyncio.sleep(0.1)
            
            # Wait for monitoring to collect data
            await asyncio.sleep(2)
            
            # Get summary
            summary = debugger.get_performance_summary(1)
            assert summary["metrics_count"] > 0
            
            # Stop monitoring
            result = await debugger.stop_monitoring()
            assert result["status"] == "stopped"
            
        finally:
            # Ensure monitoring is stopped
            if debugger.monitoring_active:
                await debugger.stop_monitoring()
            
            # Clear data for clean state
            debugger.clear_data()
    
    def test_percentile_calculation(self):
        """Test percentile calculation utility."""
        debugger = PerformanceDebugger(LocalDatabaseConfig())
        
        # Test with sample data
        data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        
        # Test various percentiles
        assert debugger._percentile(data, 50) == 5.5  # Median
        assert abs(debugger._percentile(data, 90) - 9.1) < 0.01  # 90th percentile
        assert abs(debugger._percentile(data, 95) - 9.55) < 0.01  # 95th percentile
        
        # Test edge cases
        assert debugger._percentile([], 50) == 0.0
        assert debugger._percentile([5.0], 50) == 5.0
    
    def test_docker_cpu_calculation(self):
        """Test Docker CPU percentage calculation."""
        debugger = PerformanceDebugger(LocalDatabaseConfig())
        
        # Mock Docker stats
        stats = {
            "cpu_stats": {
                "cpu_usage": {
                    "total_usage": 1000000000,  # 1 billion nanoseconds
                    "percpu_usage": [250000000, 250000000, 250000000, 250000000]  # 4 CPUs
                },
                "system_cpu_usage": 10000000000  # 10 billion nanoseconds
            },
            "precpu_stats": {
                "cpu_usage": {
                    "total_usage": 500000000,  # 0.5 billion nanoseconds
                    "percpu_usage": [125000000, 125000000, 125000000, 125000000]
                },
                "system_cpu_usage": 9000000000  # 9 billion nanoseconds
            }
        }
        
        cpu_percent = debugger._calculate_cpu_percent(stats)
        
        # Expected: (500M / 1B) * 4 CPUs * 100 = 200%
        assert cpu_percent == 200.0
    
    def test_database_performance_analysis(self):
        """Test database performance analysis."""
        debugger = PerformanceDebugger(LocalDatabaseConfig())
        
        # Add sample query data
        queries = [
            QueryPerformanceData("SELECT", "postgresql", 0.01),
            QueryPerformanceData("SELECT", "postgresql", 0.02),
            QueryPerformanceData("SELECT", "postgresql", 0.03),
            QueryPerformanceData("MATCH", "neo4j", 0.05),
            QueryPerformanceData("MATCH", "neo4j", 0.07),
            QueryPerformanceData("search", "milvus", 0.1),
        ]
        
        analysis = debugger._analyze_database_performance_summary(queries)
        
        assert "postgresql" in analysis
        assert "neo4j" in analysis
        assert "milvus" in analysis
        
        # Check PostgreSQL stats
        pg_stats = analysis["postgresql"]
        assert pg_stats["query_count"] == 3
        assert pg_stats["avg_time_ms"] == 20.0  # (10+20+30)/3 = 20ms
        assert pg_stats["min_time_ms"] == 10.0
        assert pg_stats["max_time_ms"] == 30.0
        
        # Check Neo4j stats
        neo4j_stats = analysis["neo4j"]
        assert neo4j_stats["query_count"] == 2
        assert abs(neo4j_stats["avg_time_ms"] - 60.0) < 0.01  # (50+70)/2 = 60ms