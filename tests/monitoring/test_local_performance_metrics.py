"""
Tests for Local Development Performance Metrics Collection

This test suite validates the local development performance metrics collection
functionality, including service monitoring, Docker integration, and API endpoints.
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Dict, Any

from src.multimodal_librarian.monitoring.local_performance_metrics import (
    LocalPerformanceMetricsCollector,
    LocalServiceMetrics,
    LocalDevelopmentSession,
    start_local_performance_monitoring
)
from src.multimodal_librarian.clients.database_factory import DatabaseClientFactory
from src.multimodal_librarian.config.local_config import LocalDatabaseConfig


@pytest.fixture
def mock_local_config():
    """Create a mock local database configuration."""
    config = MagicMock(spec=LocalDatabaseConfig)
    config.database_type = "local"
    config.postgres_host = "localhost"
    config.postgres_port = 5432
    config.neo4j_host = "localhost"
    config.neo4j_port = 7687
    config.milvus_host = "localhost"
    config.milvus_port = 19530
    config.redis_port = 6379
    return config


@pytest.fixture
def mock_database_factory(mock_local_config):
    """Create a mock database factory."""
    factory = MagicMock(spec=DatabaseClientFactory)
    factory.config = mock_local_config
    
    # Mock database clients
    factory.get_relational_client.return_value = AsyncMock()
    factory.get_graph_client.return_value = AsyncMock()
    factory.get_vector_client.return_value = AsyncMock()
    factory.get_cache_client.return_value = AsyncMock()
    
    return factory


@pytest.fixture
def mock_docker_client():
    """Create a mock Docker client."""
    with patch('docker.from_env') as mock_docker:
        mock_client = MagicMock()
        mock_docker.return_value = mock_client
        
        # Mock container
        mock_container = MagicMock()
        mock_container.name = "test_postgres"
        mock_container.status = "running"
        mock_container.stats.return_value = {
            'cpu_stats': {
                'cpu_usage': {'total_usage': 1000000},
                'system_cpu_usage': 10000000
            },
            'precpu_stats': {
                'cpu_usage': {'total_usage': 900000},
                'system_cpu_usage': 9000000
            },
            'memory_stats': {
                'usage': 512 * 1024 * 1024,  # 512MB
                'limit': 1024 * 1024 * 1024  # 1GB
            },
            'networks': {
                'eth0': {
                    'rx_bytes': 1024 * 1024,  # 1MB
                    'tx_bytes': 512 * 1024    # 512KB
                }
            },
            'blkio_stats': {
                'io_service_bytes_recursive': [
                    {'op': 'Read', 'value': 10 * 1024 * 1024},   # 10MB
                    {'op': 'Write', 'value': 5 * 1024 * 1024}    # 5MB
                ]
            }
        }
        
        mock_client.containers.list.return_value = [mock_container]
        yield mock_client


class TestLocalPerformanceMetricsCollector:
    """Test suite for LocalPerformanceMetricsCollector."""
    
    @pytest.mark.asyncio
    async def test_collector_initialization(self, mock_database_factory, mock_local_config):
        """Test collector initialization."""
        collector = LocalPerformanceMetricsCollector(
            database_factory=mock_database_factory,
            config=mock_local_config
        )
        
        assert collector.database_factory == mock_database_factory
        assert collector.config == mock_local_config
        assert not collector.is_collecting
        assert collector.session_id.startswith("local_dev_")
        assert len(collector.monitored_services) == 4  # postgres, neo4j, milvus, redis
    
    @pytest.mark.asyncio
    async def test_start_stop_collection(self, mock_database_factory, mock_local_config):
        """Test starting and stopping metrics collection."""
        with patch.object(LocalPerformanceMetricsCollector, '_collection_loop') as mock_loop:
            mock_loop.return_value = AsyncMock()
            
            collector = LocalPerformanceMetricsCollector(
                database_factory=mock_database_factory,
                config=mock_local_config
            )
            
            # Test start collection
            await collector.start_collection()
            assert collector.is_collecting
            
            # Test stop collection
            await collector.stop_collection()
            assert not collector.is_collecting
            assert collector.current_session.end_time is not None
    
    @pytest.mark.asyncio
    async def test_postgres_health_check(self, mock_database_factory, mock_local_config):
        """Test PostgreSQL health check and metrics collection."""
        collector = LocalPerformanceMetricsCollector(
            database_factory=mock_database_factory,
            config=mock_local_config
        )
        
        # Mock PostgreSQL client responses
        postgres_client = mock_database_factory.get_relational_client.return_value
        postgres_client.execute.side_effect = [
            None,  # SELECT 1 query
            [[5]],  # Connection count query
            [[100, 1500.0, 15.0]]  # Query statistics
        ]
        
        container_info = {
            'container_name': 'test_postgres',
            'cpu_percent': 25.5,
            'memory_usage_mb': 512.0,
            'memory_limit_mb': 1024.0
        }
        
        timestamp = datetime.now()
        metrics = await collector._check_postgres_health(timestamp, container_info)
        
        assert metrics.service_name == 'postgres'
        assert metrics.container_name == 'test_postgres'
        assert metrics.status == 'running'
        assert metrics.response_time_ms is not None
        assert metrics.connection_count == 5
        assert metrics.cpu_percent == 25.5
        assert metrics.memory_usage_mb == 512.0
        assert 'total_queries' in metrics.custom_metrics
    
    @pytest.mark.asyncio
    async def test_neo4j_health_check(self, mock_database_factory, mock_local_config):
        """Test Neo4j health check and metrics collection."""
        collector = LocalPerformanceMetricsCollector(
            database_factory=mock_database_factory,
            config=mock_local_config
        )
        
        # Mock Neo4j client responses
        neo4j_client = mock_database_factory.get_graph_client.return_value
        neo4j_client.execute_query.side_effect = [
            None,  # RETURN 1 query
            [{'open_transactions': 3}]  # Statistics query
        ]
        
        container_info = {
            'container_name': 'test_neo4j',
            'cpu_percent': 15.2,
            'memory_usage_mb': 768.0
        }
        
        timestamp = datetime.now()
        metrics = await collector._check_neo4j_health(timestamp, container_info)
        
        assert metrics.service_name == 'neo4j'
        assert metrics.container_name == 'test_neo4j'
        assert metrics.status == 'running'
        assert metrics.response_time_ms is not None
        assert metrics.cpu_percent == 15.2
        assert metrics.memory_usage_mb == 768.0
        assert 'open_transactions' in metrics.custom_metrics
    
    @pytest.mark.asyncio
    async def test_milvus_health_check(self, mock_database_factory, mock_local_config):
        """Test Milvus health check and metrics collection."""
        collector = LocalPerformanceMetricsCollector(
            database_factory=mock_database_factory,
            config=mock_local_config
        )
        
        # Mock Milvus client responses
        milvus_client = mock_database_factory.get_vector_client.return_value
        milvus_client.list_collections.return_value = ['collection1', 'collection2']
        
        container_info = {
            'container_name': 'test_milvus',
            'cpu_percent': 30.1,
            'memory_usage_mb': 1024.0
        }
        
        timestamp = datetime.now()
        metrics = await collector._check_milvus_health(timestamp, container_info)
        
        assert metrics.service_name == 'milvus'
        assert metrics.container_name == 'test_milvus'
        assert metrics.status == 'running'
        assert metrics.response_time_ms is not None
        assert metrics.cpu_percent == 30.1
        assert metrics.memory_usage_mb == 1024.0
        assert metrics.custom_metrics['collection_count'] == 2
    
    @pytest.mark.asyncio
    async def test_redis_health_check(self, mock_database_factory, mock_local_config):
        """Test Redis health check and metrics collection."""
        collector = LocalPerformanceMetricsCollector(
            database_factory=mock_database_factory,
            config=mock_local_config
        )
        
        # Mock Redis client responses
        redis_client = mock_database_factory.get_cache_client.return_value
        redis_client.ping.return_value = True
        redis_client.info.return_value = {
            'connected_clients': 10,
            'used_memory': 64 * 1024 * 1024,  # 64MB
            'keyspace_hits': 1000,
            'keyspace_misses': 100,
            'total_commands_processed': 5000
        }
        
        container_info = {
            'container_name': 'test_redis',
            'cpu_percent': 5.5,
            'memory_usage_mb': 128.0
        }
        
        timestamp = datetime.now()
        metrics = await collector._check_redis_health(timestamp, container_info)
        
        assert metrics.service_name == 'redis'
        assert metrics.container_name == 'test_redis'
        assert metrics.status == 'running'
        assert metrics.response_time_ms is not None
        assert metrics.connection_count == 10
        assert metrics.cpu_percent == 5.5
        assert metrics.memory_usage_mb == 128.0
        assert 'used_memory_mb' in metrics.custom_metrics
        assert 'keyspace_hits' in metrics.custom_metrics
    
    @pytest.mark.asyncio
    async def test_docker_container_info(self, mock_database_factory, mock_local_config, mock_docker_client):
        """Test Docker container information collection."""
        collector = LocalPerformanceMetricsCollector(
            database_factory=mock_database_factory,
            config=mock_local_config
        )
        
        container_info = await collector._get_container_info('postgres')
        
        assert container_info is not None
        assert container_info['container_name'] == 'test_postgres'
        assert container_info['status'] == 'running'
        assert 'cpu_percent' in container_info
        assert 'memory_usage_mb' in container_info
        assert 'network_rx_mb' in container_info
        assert 'disk_read_mb' in container_info
    
    @pytest.mark.asyncio
    async def test_performance_score_calculation(self, mock_database_factory, mock_local_config):
        """Test performance score calculation."""
        collector = LocalPerformanceMetricsCollector(
            database_factory=mock_database_factory,
            config=mock_local_config
        )
        
        # Set up session metrics
        collector.current_session.avg_response_time_ms = 50.0  # Good response time
        collector.current_session.total_queries = 100
        collector.current_session.total_errors = 2  # 2% error rate
        collector.current_session.avg_cpu_usage_percent = 60.0  # Reasonable CPU
        collector.current_session.peak_memory_usage_mb = 4000.0  # Under 6GB threshold
        collector.current_session.container_restarts = 0
        
        score = await collector._calculate_performance_score()
        
        # Should be a high score with these good metrics
        assert score > 80.0
        assert score <= 100.0
    
    @pytest.mark.asyncio
    async def test_performance_summary(self, mock_database_factory, mock_local_config):
        """Test performance summary generation."""
        collector = LocalPerformanceMetricsCollector(
            database_factory=mock_database_factory,
            config=mock_local_config
        )
        
        # Add some mock metrics
        timestamp = datetime.now()
        mock_metric = LocalServiceMetrics(
            service_name='postgres',
            container_name='test_postgres',
            timestamp=timestamp,
            status='running',
            response_time_ms=25.5,
            cpu_percent=30.0,
            memory_usage_mb=512.0,
            connection_count=5
        )
        
        collector.service_metrics_history['postgres'] = [mock_metric]
        collector.current_session.performance_score = 85.5
        
        summary = collector.get_performance_summary()
        
        assert 'session_id' in summary
        assert 'performance_score' in summary
        assert 'service_status' in summary
        assert 'session_metrics' in summary
        assert 'recommendations' in summary
        assert summary['performance_score'] == 85.5
        assert 'postgres' in summary['service_status']
    
    @pytest.mark.asyncio
    async def test_recommendations_generation(self, mock_database_factory, mock_local_config):
        """Test performance recommendations generation."""
        collector = LocalPerformanceMetricsCollector(
            database_factory=mock_database_factory,
            config=mock_local_config
        )
        
        # Set up metrics that should trigger recommendations
        collector.current_session.avg_response_time_ms = 150.0  # High response time
        collector.current_session.avg_cpu_usage_percent = 85.0  # High CPU
        collector.current_session.peak_memory_usage_mb = 7000.0  # High memory
        collector.current_session.total_queries = 100
        collector.current_session.total_errors = 10  # 10% error rate
        collector.current_session.container_restarts = 2
        collector.current_session.performance_score = 45.0  # Low score
        
        recommendations = collector._generate_recommendations()
        
        assert len(recommendations) > 0
        assert any('database queries' in rec for rec in recommendations)
        assert any('CPU usage' in rec for rec in recommendations)
        assert any('memory usage' in rec for rec in recommendations)
        assert any('error rate' in rec for rec in recommendations)
        assert any('Container restarts' in rec for rec in recommendations)
        assert any('performance score' in rec for rec in recommendations)
    
    @pytest.mark.asyncio
    async def test_metrics_export(self, mock_database_factory, mock_local_config):
        """Test metrics export functionality."""
        collector = LocalPerformanceMetricsCollector(
            database_factory=mock_database_factory,
            config=mock_local_config
        )
        
        # Add some mock data
        timestamp = datetime.now()
        mock_metric = LocalServiceMetrics(
            service_name='postgres',
            container_name='test_postgres',
            timestamp=timestamp,
            status='running',
            response_time_ms=25.5
        )
        
        collector.service_metrics_history['postgres'] = [mock_metric]
        
        exported_data = collector.export_metrics(format="json")
        
        assert isinstance(exported_data, str)
        import json
        data = json.loads(exported_data)
        
        assert 'session' in data
        assert 'performance_summary' in data
        assert 'service_metrics' in data
        assert 'postgres' in data['service_metrics']


class TestLocalPerformanceMetricsAPI:
    """Test suite for Local Performance Metrics API endpoints."""
    
    @pytest.mark.asyncio
    async def test_convenience_function(self, mock_database_factory, mock_local_config):
        """Test the convenience function for starting performance monitoring."""
        with patch.object(LocalPerformanceMetricsCollector, 'start_collection') as mock_start:
            mock_start.return_value = AsyncMock()
            
            collector = await start_local_performance_monitoring(
                database_factory=mock_database_factory,
                config=mock_local_config
            )
            
            assert isinstance(collector, LocalPerformanceMetricsCollector)
            mock_start.assert_called_once()


@pytest.mark.integration
class TestLocalPerformanceMetricsIntegration:
    """Integration tests for local performance metrics collection."""
    
    @pytest.mark.asyncio
    async def test_full_collection_cycle(self, mock_database_factory, mock_local_config):
        """Test a full metrics collection cycle."""
        collector = LocalPerformanceMetricsCollector(
            database_factory=mock_database_factory,
            config=mock_local_config
        )
        
        # Mock the database clients to return successful responses
        postgres_client = mock_database_factory.get_relational_client.return_value
        postgres_client.execute.side_effect = [None, [[5]], [[100, 1500.0, 15.0]]]
        
        neo4j_client = mock_database_factory.get_graph_client.return_value
        neo4j_client.execute_query.side_effect = [None, [{'open_transactions': 3}]]
        
        milvus_client = mock_database_factory.get_vector_client.return_value
        milvus_client.list_collections.return_value = ['collection1']
        
        redis_client = mock_database_factory.get_cache_client.return_value
        redis_client.ping.return_value = True
        redis_client.info.return_value = {'connected_clients': 5}
        
        # Start collection
        await collector.start_collection()
        
        # Wait a short time for collection
        await asyncio.sleep(0.1)
        
        # Manually trigger one collection cycle
        await collector._collect_service_metrics()
        await collector._update_session_metrics()
        
        # Stop collection
        await collector.stop_collection()
        
        # Verify metrics were collected
        assert len(collector.current_session.service_metrics) > 0
        assert collector.current_session.end_time is not None
        assert collector.current_session.duration_seconds is not None
        
        # Verify performance summary
        summary = collector.get_performance_summary()
        assert 'service_status' in summary
        assert len(summary['service_status']) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])