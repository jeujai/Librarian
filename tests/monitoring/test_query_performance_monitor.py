"""
Tests for Query Performance Monitor

This module contains tests for the query performance monitoring system,
including the monitor, decorators, configuration, and integration components.

The tests validate that query performance is properly tracked, alerts are
generated for slow queries, and the monitoring system integrates correctly
with database clients.
"""

import asyncio
import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from src.multimodal_librarian.monitoring.query_performance_monitor import (
    QueryPerformanceMonitor, QueryMetrics, PerformanceAlert, PerformanceStats,
    QueryType, DatabaseType, QueryTracker
)
from src.multimodal_librarian.monitoring.query_performance_decorators import (
    track_query_performance, track_vector_operation, track_graph_operation
)
from src.multimodal_librarian.config.query_performance_config import (
    QueryPerformanceConfig, QueryPerformanceConfigFactory, MonitoringLevel
)
from src.multimodal_librarian.monitoring.query_performance_integration import (
    QueryMonitoringManager, initialize_query_monitoring, shutdown_query_monitoring
)


class TestQueryPerformanceMonitor:
    """Test cases for QueryPerformanceMonitor."""
    
    @pytest.fixture
    async def monitor(self):
        """Create a test monitor instance."""
        monitor = QueryPerformanceMonitor(
            slow_query_threshold_ms=100.0,  # Low threshold for testing
            high_cpu_threshold=50.0,
            high_memory_threshold_mb=100.0,
            max_metrics_history=100,
            stats_window_minutes=5
        )
        await monitor.start()
        yield monitor
        await monitor.stop()
    
    @pytest.mark.asyncio
    async def test_monitor_initialization(self):
        """Test monitor initialization and shutdown."""
        monitor = QueryPerformanceMonitor()
        
        assert not monitor.is_monitoring
        
        await monitor.start()
        assert monitor.is_monitoring
        
        await monitor.stop()
        assert not monitor.is_monitoring
    
    @pytest.mark.asyncio
    async def test_query_tracking(self, monitor):
        """Test basic query tracking functionality."""
        # Track a simple query
        async with monitor.track_query("postgresql", "SELECT * FROM users") as tracker:
            await asyncio.sleep(0.05)  # Simulate query execution
            tracker.set_result_count(10)
        
        # Verify metrics were recorded
        assert len(monitor.query_metrics) == 1
        
        metrics = monitor.query_metrics[0]
        assert metrics.database_type == DatabaseType.POSTGRESQL
        assert metrics.query_type == QueryType.SELECT
        assert metrics.query_text == "SELECT * FROM users"
        assert metrics.result_count == 10
        assert metrics.duration_ms is not None
        assert metrics.duration_ms > 0
    
    @pytest.mark.asyncio
    async def test_slow_query_alert(self, monitor):
        """Test slow query alert generation."""
        alerts_received = []
        
        def alert_callback(alert):
            alerts_received.append(alert)
        
        monitor.add_alert_callback(alert_callback)
        
        # Execute a slow query (sleep longer than threshold)
        async with monitor.track_query("postgresql", "SELECT * FROM large_table") as tracker:
            await asyncio.sleep(0.15)  # Longer than 100ms threshold
            tracker.set_result_count(1000)
        
        # Wait for alert processing
        await asyncio.sleep(0.1)
        
        # Verify alert was generated
        assert len(alerts_received) == 1
        alert = alerts_received[0]
        assert alert.alert_type == "slow_query"
        assert alert.severity in ["medium", "high"]
        assert "slow query detected" in alert.message.lower()
    
    @pytest.mark.asyncio
    async def test_query_error_tracking(self, monitor):
        """Test tracking of query errors."""
        try:
            async with monitor.track_query("postgresql", "INVALID SQL") as tracker:
                raise Exception("SQL syntax error")
        except Exception:
            pass  # Expected
        
        # Verify error was recorded
        assert len(monitor.query_metrics) == 1
        metrics = monitor.query_metrics[0]
        assert metrics.error is not None
        assert "SQL syntax error" in metrics.error
    
    @pytest.mark.asyncio
    async def test_performance_stats_calculation(self, monitor):
        """Test performance statistics calculation."""
        # Execute several queries with different characteristics
        queries = [
            ("SELECT * FROM users", 50, 10),
            ("SELECT * FROM orders", 150, 100),  # Slow query
            ("INSERT INTO logs", 25, 1),
            ("UPDATE users SET last_login = NOW()", 75, 5)
        ]
        
        for query, sleep_ms, result_count in queries:
            async with monitor.track_query("postgresql", query) as tracker:
                await asyncio.sleep(sleep_ms / 1000)  # Convert to seconds
                tracker.set_result_count(result_count)
        
        # Get performance stats
        stats = await monitor.get_performance_stats("postgresql")
        
        assert "postgresql" in stats
        pg_stats = stats["postgresql"]
        
        assert pg_stats.total_queries == 4
        assert pg_stats.successful_queries == 4
        assert pg_stats.failed_queries == 0
        assert pg_stats.slow_query_count == 1  # One query > 100ms threshold
        assert pg_stats.avg_query_time_ms > 0
    
    @pytest.mark.asyncio
    async def test_query_type_detection(self, monitor):
        """Test automatic query type detection."""
        test_queries = [
            ("SELECT * FROM users", QueryType.SELECT),
            ("INSERT INTO users (name) VALUES ('test')", QueryType.INSERT),
            ("UPDATE users SET name = 'updated'", QueryType.UPDATE),
            ("DELETE FROM users WHERE id = 1", QueryType.DELETE),
            ("CREATE TABLE test (id INT)", QueryType.CREATE),
            ("MATCH (n:User) RETURN n", QueryType.GRAPH_QUERY),
            ("search vector similarity", QueryType.VECTOR_SEARCH)
        ]
        
        for query_text, expected_type in test_queries:
            async with monitor.track_query("postgresql", query_text) as tracker:
                await asyncio.sleep(0.01)
            
            # Get the last recorded metrics
            metrics = monitor.query_metrics[-1]
            assert metrics.query_type == expected_type
    
    @pytest.mark.asyncio
    async def test_metrics_export(self, monitor, tmp_path):
        """Test metrics export functionality."""
        # Generate some test metrics
        async with monitor.track_query("postgresql", "SELECT 1") as tracker:
            await asyncio.sleep(0.01)
            tracker.set_result_count(1)
        
        # Export to JSON
        json_file = tmp_path / "metrics.json"
        success = await monitor.export_metrics(str(json_file), format="json")
        
        assert success
        assert json_file.exists()
        
        # Verify JSON content
        import json
        with open(json_file) as f:
            data = json.load(f)
        
        assert len(data) == 1
        assert data[0]["database_type"] == "postgresql"
        assert data[0]["query_text"] == "SELECT 1"


class TestQueryPerformanceDecorators:
    """Test cases for query performance decorators."""
    
    @pytest.fixture
    async def monitor(self):
        """Create a test monitor instance."""
        monitor = QueryPerformanceMonitor(slow_query_threshold_ms=50.0)
        await monitor.start()
        
        # Set as global monitor for decorator tests
        from src.multimodal_librarian.monitoring.query_performance_monitor import set_global_monitor
        set_global_monitor(monitor)
        
        yield monitor
        
        await monitor.stop()
        set_global_monitor(None)
    
    @pytest.mark.asyncio
    async def test_track_query_performance_decorator(self, monitor):
        """Test the track_query_performance decorator."""
        
        class MockDatabaseClient:
            @track_query_performance("postgresql")
            async def execute_query(self, query: str, parameters=None):
                await asyncio.sleep(0.02)  # Simulate query execution
                return [{"id": 1, "name": "test"}]
        
        client = MockDatabaseClient()
        result = await client.execute_query("SELECT * FROM users")
        
        # Verify result is unchanged
        assert result == [{"id": 1, "name": "test"}]
        
        # Verify monitoring was applied
        assert len(monitor.query_metrics) == 1
        metrics = monitor.query_metrics[0]
        assert metrics.database_type == DatabaseType.POSTGRESQL
        assert metrics.query_text == "SELECT * FROM users"
        assert metrics.result_count == 1
    
    @pytest.mark.asyncio
    async def test_track_vector_operation_decorator(self, monitor):
        """Test the track_vector_operation decorator."""
        
        class MockVectorClient:
            @track_vector_operation("vector_search")
            async def search_vectors(self, collection_name: str, query_vector: list, k: int = 10):
                await asyncio.sleep(0.01)
                return [{"id": "doc1", "score": 0.95}, {"id": "doc2", "score": 0.87}]
        
        client = MockVectorClient()
        result = await client.search_vectors("documents", [0.1, 0.2, 0.3], k=5)
        
        # Verify result is unchanged
        assert len(result) == 2
        
        # Verify monitoring was applied
        assert len(monitor.query_metrics) == 1
        metrics = monitor.query_metrics[0]
        assert metrics.database_type == DatabaseType.MILVUS
        assert "VECTOR_SEARCH" in metrics.query_text
        assert metrics.result_count == 2
    
    @pytest.mark.asyncio
    async def test_track_graph_operation_decorator(self, monitor):
        """Test the track_graph_operation decorator."""
        
        class MockGraphClient:
            @track_graph_operation()
            async def execute_query(self, query: str, parameters=None):
                await asyncio.sleep(0.01)
                return [{"n": {"id": 1, "name": "Alice"}}]
        
        client = MockGraphClient()
        result = await client.execute_query("MATCH (n:User) RETURN n")
        
        # Verify result is unchanged
        assert len(result) == 1
        
        # Verify monitoring was applied
        assert len(monitor.query_metrics) == 1
        metrics = monitor.query_metrics[0]
        assert metrics.database_type == DatabaseType.NEO4J
        assert metrics.query_type == QueryType.GRAPH_QUERY
        assert metrics.result_count == 1


class TestQueryPerformanceConfig:
    """Test cases for query performance configuration."""
    
    def test_default_config_creation(self):
        """Test default configuration creation."""
        config = QueryPerformanceConfig()
        
        assert config.monitoring_enabled is True
        assert config.monitoring_level == MonitoringLevel.DETAILED
        assert config.slow_query_threshold_ms == 1000.0
        assert config.sample_rate == 1.0
    
    def test_config_factory_presets(self):
        """Test configuration factory presets."""
        # Development config
        dev_config = QueryPerformanceConfigFactory.create_development_config()
        assert dev_config.monitoring_enabled is True
        assert dev_config.debug_monitoring is True
        
        # Testing config
        test_config = QueryPerformanceConfigFactory.create_testing_config()
        assert test_config.monitoring_level == MonitoringLevel.BASIC
        assert test_config.enable_alerts is False
        
        # Minimal config
        minimal_config = QueryPerformanceConfigFactory.create_minimal_config()
        assert minimal_config.sample_rate == 0.01
        assert minimal_config.sample_slow_queries_only is True
        
        # Disabled config
        disabled_config = QueryPerformanceConfigFactory.create_disabled_config()
        assert disabled_config.monitoring_enabled is False
    
    def test_database_specific_config(self):
        """Test database-specific configuration."""
        config = QueryPerformanceConfig()
        
        # Test PostgreSQL config
        pg_config = config.get_database_config("postgresql")
        assert pg_config.enabled is True
        assert pg_config.slow_query_threshold_ms == 1000.0
        
        # Test Neo4j config
        neo4j_config = config.get_database_config("neo4j")
        assert neo4j_config.enabled is True
        assert neo4j_config.slow_query_threshold_ms == 2000.0  # Higher threshold for graph queries
        
        # Test Milvus config
        milvus_config = config.get_database_config("milvus")
        assert milvus_config.enabled is True
        assert milvus_config.slow_query_threshold_ms == 500.0  # Lower threshold for vector searches
    
    def test_config_validation(self):
        """Test configuration validation."""
        # Test invalid sample rate
        with pytest.raises(ValueError):
            QueryPerformanceConfig(sample_rate=1.5)
        
        with pytest.raises(ValueError):
            QueryPerformanceConfig(sample_rate=-0.1)
        
        # Test valid sample rates
        config = QueryPerformanceConfig(sample_rate=0.5)
        assert config.sample_rate == 0.5
    
    def test_should_monitor_database(self):
        """Test database monitoring decision logic."""
        config = QueryPerformanceConfig(monitoring_enabled=True)
        
        assert config.should_monitor_database("postgresql") is True
        assert config.should_monitor_database("neo4j") is True
        assert config.should_monitor_database("milvus") is True
        
        # Test with monitoring disabled
        config.monitoring_enabled = False
        assert config.should_monitor_database("postgresql") is False


class TestQueryMonitoringIntegration:
    """Test cases for query monitoring integration."""
    
    @pytest.mark.asyncio
    async def test_monitoring_manager_lifecycle(self):
        """Test monitoring manager initialization and shutdown."""
        config = QueryPerformanceConfigFactory.create_testing_config()
        manager = await initialize_query_monitoring(config)
        
        assert manager is not None
        assert manager.is_initialized is True
        
        await shutdown_query_monitoring()
        assert manager.is_initialized is False
    
    @pytest.mark.asyncio
    async def test_client_wrapping(self):
        """Test automatic client wrapping with monitoring."""
        config = QueryPerformanceConfigFactory.create_development_config()
        manager = await initialize_query_monitoring(config)
        
        # Create a mock client
        class MockClient:
            async def execute_query(self, query: str):
                await asyncio.sleep(0.01)
                return [{"result": "data"}]
        
        client = MockClient()
        wrapped_client = manager.wrap_database_client(client, "postgresql")
        
        # Execute query through wrapped client
        result = await wrapped_client.execute_query("SELECT 1")
        
        # Verify result is unchanged
        assert result == [{"result": "data"}]
        
        # Verify monitoring was applied
        assert len(manager.monitor.query_metrics) == 1
        
        await shutdown_query_monitoring()
    
    @pytest.mark.asyncio
    async def test_monitoring_with_disabled_config(self):
        """Test monitoring behavior with disabled configuration."""
        config = QueryPerformanceConfigFactory.create_disabled_config()
        manager = await initialize_query_monitoring(config)
        
        # Should return None for disabled monitoring
        assert manager is None


class TestQueryTracker:
    """Test cases for QueryTracker context manager."""
    
    @pytest.fixture
    async def monitor(self):
        """Create a test monitor instance."""
        monitor = QueryPerformanceMonitor()
        await monitor.start()
        yield monitor
        await monitor.stop()
    
    @pytest.mark.asyncio
    async def test_query_tracker_context_manager(self, monitor):
        """Test QueryTracker as context manager."""
        from src.multimodal_librarian.monitoring.query_performance_monitor import QueryMetrics
        
        metrics = QueryMetrics(
            query_id="test_1",
            database_type=DatabaseType.POSTGRESQL,
            query_type=QueryType.SELECT,
            query_text="SELECT 1",
            start_time=datetime.utcnow()
        )
        
        tracker = monitor.QueryTracker(monitor, metrics)
        
        async with tracker:
            await asyncio.sleep(0.01)
            tracker.set_result_count(5)
            tracker.set_query_complexity("simple")
            tracker.add_metadata("test_key", "test_value")
        
        # Verify metrics were updated
        assert metrics.end_time is not None
        assert metrics.duration_ms is not None
        assert metrics.duration_ms > 0
        assert metrics.result_count == 5
        assert metrics.query_complexity == "simple"
        assert metrics.metadata["test_key"] == "test_value"
    
    @pytest.mark.asyncio
    async def test_query_tracker_exception_handling(self, monitor):
        """Test QueryTracker exception handling."""
        from src.multimodal_librarian.monitoring.query_performance_monitor import QueryMetrics
        
        metrics = QueryMetrics(
            query_id="test_error",
            database_type=DatabaseType.POSTGRESQL,
            query_type=QueryType.SELECT,
            query_text="INVALID SQL",
            start_time=datetime.utcnow()
        )
        
        tracker = monitor.QueryTracker(monitor, metrics)
        
        try:
            async with tracker:
                raise ValueError("Test error")
        except ValueError:
            pass  # Expected
        
        # Verify error was recorded
        assert metrics.error is not None
        assert "Test error" in metrics.error


if __name__ == "__main__":
    pytest.main([__file__])