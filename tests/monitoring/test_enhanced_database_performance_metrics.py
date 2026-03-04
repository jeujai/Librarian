"""
Test Enhanced Database Performance Metrics

This test validates the enhanced database performance metrics implementation
for the local development conversion, ensuring comprehensive metrics collection
across all database services.
"""

import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.multimodal_librarian.api.routers.health_local import (
    _collect_postgres_performance,
    _collect_neo4j_performance,
    _collect_milvus_performance,
    _collect_redis_performance,
    database_performance_metrics
)
from src.multimodal_librarian.clients.database_factory import DatabaseClientFactory
from src.multimodal_librarian.config.local_config import LocalDatabaseConfig


@pytest.fixture
def mock_database_factory():
    """Create a mock database factory for testing."""
    factory = MagicMock(spec=DatabaseClientFactory)
    config = MagicMock(spec=LocalDatabaseConfig)
    config.database_type = 'local'
    config.enable_relational_db = True
    config.enable_graph_db = True
    config.enable_vector_search = True
    config.enable_redis_cache = True
    factory.config = config
    return factory


@pytest.fixture
def mock_postgres_client():
    """Create a mock PostgreSQL client."""
    client = AsyncMock()
    
    # Mock basic query
    client.execute.return_value = None
    
    # Mock connection statistics
    client.execute.side_effect = [
        None,  # Basic SELECT 1
        [(10, 5, 3, 2)],  # Connection stats
        [(1024*1024*100, 5, 10)],  # Database stats
        [(1000, 5000.0, 5.0, 50.0, 2.5)],  # Query performance stats
        [(95.5,)],  # Cache hit ratio
        [  # Slow queries
            ("SELECT * FROM large_table WHERE condition", 50, 150.0, 7500.0),
            ("UPDATE users SET status = 'active'", 25, 120.0, 3000.0)
        ]
    ]
    
    return client


@pytest.fixture
def mock_neo4j_client():
    """Create a mock Neo4j client."""
    client = AsyncMock()
    
    client.execute_query.side_effect = [
        None,  # Basic RETURN 1
        [{"node_count": 1000, "relationship_count": 2500}],  # Database stats
        [{"attributes": {"HeapMemoryUsage": {"used": 512*1024*1024, "max": 1024*1024*1024}}}],  # Memory stats
        [{"open_transactions": 3, "committed_transactions": 15000}],  # Transaction stats
        [  # Index information
            {"name": "user_index", "type": "BTREE", "state": "ONLINE", "populationPercent": 100.0},
            {"name": "product_index", "type": "BTREE", "state": "ONLINE", "populationPercent": 95.0}
        ],
        [(500,)]  # Complex query count
    ]
    
    return client


@pytest.fixture
def mock_milvus_client():
    """Create a mock Milvus client."""
    client = AsyncMock()
    
    client.list_collections.return_value = ["documents", "embeddings", "test_collection"]
    
    client.describe_collection.side_effect = [
        {"dimension": 384, "index_type": "IVF_FLAT"},
        {"dimension": 768, "index_type": "HNSW"},
        {"dimension": 512, "index_type": "unknown"}
    ]
    
    client.get_collection_stats.side_effect = [
        {"row_count": 10000},
        {"row_count": 5000},
        {"row_count": 0}
    ]
    
    client.search.return_value = [{"id": 1, "distance": 0.85}]
    client.get_server_version.return_value = {"version": "2.3.4"}
    
    return client


@pytest.fixture
def mock_redis_client():
    """Create a mock Redis client."""
    client = AsyncMock()
    
    client.ping.return_value = True
    
    client.info.return_value = {
        "used_memory": 50 * 1024 * 1024,  # 50MB
        "used_memory_peak": 75 * 1024 * 1024,  # 75MB
        "used_memory_rss": 60 * 1024 * 1024,  # 60MB
        "maxmemory": 512 * 1024 * 1024,  # 512MB
        "connected_clients": 5,
        "blocked_clients": 0,
        "total_connections_received": 1000,
        "rejected_connections": 0,
        "total_commands_processed": 50000,
        "instantaneous_ops_per_sec": 100,
        "keyspace_hits": 8000,
        "keyspace_misses": 2000,
        "expired_keys": 500,
        "evicted_keys": 0,
        "db0": {"keys": 1000, "expires": 100}
    }
    
    client.set.return_value = True
    client.get.return_value = "test_value"
    client.delete.return_value = 1
    
    return client


class TestEnhancedDatabasePerformanceMetrics:
    """Test enhanced database performance metrics collection."""
    
    @pytest.mark.asyncio
    async def test_postgres_performance_metrics(self, mock_database_factory, mock_postgres_client):
        """Test comprehensive PostgreSQL performance metrics collection."""
        mock_database_factory.get_relational_client.return_value = mock_postgres_client
        
        result = await _collect_postgres_performance(mock_database_factory)
        
        # Verify basic structure
        assert result["service"] == "postgres"
        assert result["status"] == "healthy"
        assert "response_time_ms" in result
        assert isinstance(result["response_time_ms"], (int, float))
        
        # Verify connection statistics
        assert "connections" in result
        connections = result["connections"]
        assert connections["total"] == 10
        assert connections["active"] == 5
        assert connections["idle"] == 3
        assert connections["idle_in_transaction"] == 2
        
        # Verify database statistics
        assert "database_stats" in result
        db_stats = result["database_stats"]
        assert "size_mb" in db_stats
        assert db_stats["table_count"] == 5
        assert db_stats["index_count"] == 10
        
        # Verify cache performance
        assert "cache_performance" in result
        assert result["cache_performance"]["hit_ratio_percent"] == 95.5
        
        # Verify query performance
        assert "query_performance" in result
        query_perf = result["query_performance"]
        assert query_perf["total_queries"] == 1000
        assert query_perf["avg_time_ms"] == 5.0
        
        # Verify slow queries
        assert "slow_queries" in result
        assert len(result["slow_queries"]) == 2
        
        # Verify performance score and recommendations
        assert "performance_score" in result
        assert 0 <= result["performance_score"] <= 100
        assert "recommendations" in result
        assert isinstance(result["recommendations"], list)
    
    @pytest.mark.asyncio
    async def test_neo4j_performance_metrics(self, mock_database_factory, mock_neo4j_client):
        """Test comprehensive Neo4j performance metrics collection."""
        mock_database_factory.get_graph_client.return_value = mock_neo4j_client
        
        result = await _collect_neo4j_performance(mock_database_factory)
        
        # Verify basic structure
        assert result["service"] == "neo4j"
        assert result["status"] == "healthy"
        assert "response_time_ms" in result
        
        # Verify database statistics
        assert "database_stats" in result
        db_stats = result["database_stats"]
        assert db_stats["node_count"] == 1000
        assert db_stats["relationship_count"] == 2500
        
        # Verify memory statistics
        assert "memory_stats" in result
        memory_stats = result["memory_stats"]
        assert "heap_used_mb" in memory_stats
        assert "heap_max_mb" in memory_stats
        
        # Verify transaction statistics
        assert "transaction_stats" in result
        tx_stats = result["transaction_stats"]
        assert tx_stats["open_transactions"] == 3
        assert tx_stats["committed_transactions"] == 15000
        
        # Verify index statistics
        assert "index_stats" in result
        index_stats = result["index_stats"]
        assert index_stats["count"] == 2
        assert len(index_stats["indexes"]) == 2
        
        # Verify performance score and recommendations
        assert "performance_score" in result
        assert 0 <= result["performance_score"] <= 100
        assert "recommendations" in result
    
    @pytest.mark.asyncio
    async def test_milvus_performance_metrics(self, mock_database_factory, mock_milvus_client):
        """Test comprehensive Milvus performance metrics collection."""
        mock_database_factory.get_vector_client.return_value = mock_milvus_client
        
        result = await _collect_milvus_performance(mock_database_factory)
        
        # Verify basic structure
        assert result["service"] == "milvus"
        assert result["status"] == "healthy"
        assert "response_time_ms" in result
        
        # Verify collection statistics
        assert result["collection_count"] == 3
        assert result["total_entities"] == 15000  # 10000 + 5000 + 0
        
        # Verify collection details
        assert "collection_stats" in result
        collection_stats = result["collection_stats"]
        assert len(collection_stats) == 3
        
        # Check first collection
        first_collection = collection_stats[0]
        assert first_collection["name"] == "documents"
        assert first_collection["entity_count"] == 10000
        assert first_collection["dimension"] == 384
        assert "search_time_ms" in first_collection
        
        # Verify system information
        assert "system_info" in result
        assert result["system_info"]["version"] == "2.3.4"
        
        # Verify performance metrics
        assert "avg_search_time_ms" in result
        assert "performance_score" in result
        assert "recommendations" in result
    
    @pytest.mark.asyncio
    async def test_redis_performance_metrics(self, mock_database_factory, mock_redis_client):
        """Test comprehensive Redis performance metrics collection."""
        mock_database_factory.get_cache_client.return_value = mock_redis_client
        
        result = await _collect_redis_performance(mock_database_factory)
        
        # Verify basic structure
        assert result["service"] == "redis"
        assert result["status"] == "healthy"
        assert "response_time_ms" in result
        
        # Verify memory statistics
        assert "memory_stats" in result
        memory_stats = result["memory_stats"]
        assert memory_stats["used_memory_mb"] == 50.0
        assert memory_stats["maxmemory_mb"] == 512.0
        
        # Verify connection statistics
        assert "connection_stats" in result
        conn_stats = result["connection_stats"]
        assert conn_stats["connected_clients"] == 5
        assert conn_stats["rejected_connections"] == 0
        
        # Verify performance statistics
        assert "performance_stats" in result
        perf_stats = result["performance_stats"]
        assert perf_stats["total_commands_processed"] == 50000
        assert perf_stats["keyspace_hits"] == 8000
        assert perf_stats["keyspace_misses"] == 2000
        
        # Verify cache performance
        assert "cache_performance" in result
        cache_perf = result["cache_performance"]
        assert cache_perf["hit_ratio_percent"] == 80.0  # 8000 / (8000 + 2000) * 100
        assert cache_perf["total_requests"] == 10000
        
        # Verify operation times
        assert "operation_times" in result
        op_times = result["operation_times"]
        assert "set_ms" in op_times
        assert "get_ms" in op_times
        assert "del_ms" in op_times
        
        # Verify database statistics
        assert "database_stats" in result
        db_stats = result["database_stats"]
        assert "db0" in db_stats
        assert db_stats["db0"]["keys"] == 1000
        
        # Verify performance score and recommendations
        assert "performance_score" in result
        assert 0 <= result["performance_score"] <= 100
        assert "recommendations" in result
    
    @pytest.mark.asyncio
    async def test_error_handling(self, mock_database_factory):
        """Test error handling in performance metrics collection."""
        # Test PostgreSQL error handling
        mock_postgres_client = AsyncMock()
        mock_postgres_client.execute.side_effect = Exception("Connection failed")
        mock_database_factory.get_relational_client.return_value = mock_postgres_client
        
        result = await _collect_postgres_performance(mock_database_factory)
        assert result["service"] == "postgres"
        assert result["status"] == "error"
        assert "error" in result
        assert "Connection failed" in result["error"]
        
        # Test Neo4j error handling
        mock_neo4j_client = AsyncMock()
        mock_neo4j_client.execute_query.side_effect = Exception("Graph database unavailable")
        mock_database_factory.get_graph_client.return_value = mock_neo4j_client
        
        result = await _collect_neo4j_performance(mock_database_factory)
        assert result["service"] == "neo4j"
        assert result["status"] == "error"
        assert "Graph database unavailable" in result["error"]
    
    @pytest.mark.asyncio
    async def test_performance_score_calculation(self, mock_database_factory, mock_postgres_client):
        """Test performance score calculation logic."""
        mock_database_factory.get_relational_client.return_value = mock_postgres_client
        
        # Test with good performance metrics
        mock_postgres_client.execute.side_effect = [
            None,  # Basic query
            [(5, 3, 2, 0)],  # Good connection stats (no idle in transaction)
            [(1024*1024*50, 3, 5)],  # Database stats
            [(100, 1000.0, 10.0, 50.0, 5.0)],  # Good query performance
            [(95.0,)],  # Good cache hit ratio
            []  # No slow queries
        ]
        
        result = await _collect_postgres_performance(mock_database_factory)
        
        # Should have high performance score
        assert result["performance_score"] >= 90
        assert len(result["recommendations"]) == 0  # No recommendations for good performance
    
    @pytest.mark.asyncio
    async def test_recommendations_generation(self, mock_database_factory, mock_postgres_client):
        """Test performance recommendations generation."""
        mock_database_factory.get_relational_client.return_value = mock_postgres_client
        
        # Test with poor performance metrics
        mock_postgres_client.execute.side_effect = [
            None,  # Basic query (will be slow due to sleep simulation)
            [(20, 15, 3, 2)],  # Poor connection stats (idle in transaction)
            [(1024*1024*200, 10, 20)],  # Database stats
            [(5000, 25000.0, 200.0, 1000.0, 100.0)],  # Poor query performance
            [(70.0,)],  # Poor cache hit ratio
            [  # Multiple slow queries
                ("SELECT * FROM huge_table", 100, 500.0, 50000.0),
                ("UPDATE all_records SET field = 'value'", 50, 800.0, 40000.0),
                ("DELETE FROM logs WHERE date < '2020-01-01'", 25, 1200.0, 30000.0)
            ]
        ]
        
        # Simulate slow response time
        with patch('time.time', side_effect=[0, 0.15]):  # 150ms response time
            result = await _collect_postgres_performance(mock_database_factory)
        
        # Should have low performance score and multiple recommendations
        assert result["performance_score"] <= 70
        assert len(result["recommendations"]) >= 3
        
        recommendations_text = " ".join(result["recommendations"])
        assert "cache" in recommendations_text.lower()
        assert "idle in transaction" in recommendations_text.lower()
        assert "slow queries" in recommendations_text.lower()
    
    @pytest.mark.asyncio
    async def test_integration_with_health_endpoint(self, mock_database_factory):
        """Test integration with the main health endpoint."""
        # Mock all clients
        mock_postgres = AsyncMock()
        mock_postgres.execute.side_effect = [
            None, [(5, 3, 2, 0)], [(1024*1024*50, 3, 5)], 
            [(100, 1000.0, 10.0, 50.0, 5.0)], [(95.0,)], []
        ]
        
        mock_neo4j = AsyncMock()
        mock_neo4j.execute_query.side_effect = [
            None, [{"node_count": 100, "relationship_count": 250}], 
            [{"attributes": {"HeapMemoryUsage": {"used": 256*1024*1024, "max": 512*1024*1024}}}],
            [{"open_transactions": 1, "committed_transactions": 1000}], [], [(50,)]
        ]
        
        mock_milvus = AsyncMock()
        mock_milvus.list_collections.return_value = ["test_collection"]
        mock_milvus.describe_collection.return_value = {"dimension": 384, "index_type": "IVF_FLAT"}
        mock_milvus.get_collection_stats.return_value = {"row_count": 1000}
        mock_milvus.search.return_value = [{"id": 1, "distance": 0.85}]
        mock_milvus.get_server_version.return_value = {"version": "2.3.4"}
        
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis.info.return_value = {
            "used_memory": 25 * 1024 * 1024, "connected_clients": 3,
            "total_commands_processed": 10000, "keyspace_hits": 800, "keyspace_misses": 200
        }
        mock_redis.set.return_value = True
        mock_redis.get.return_value = "test"
        mock_redis.delete.return_value = 1
        
        mock_database_factory.get_relational_client.return_value = mock_postgres
        mock_database_factory.get_graph_client.return_value = mock_neo4j
        mock_database_factory.get_vector_client.return_value = mock_milvus
        mock_database_factory.get_cache_client.return_value = mock_redis
        
        # Test the main performance endpoint
        result = await database_performance_metrics(mock_database_factory)
        
        # Verify overall structure
        assert result["check_type"] == "performance"
        assert "timestamp" in result
        assert "services" in result
        assert "summary" in result
        
        # Verify all services are included
        services = result["services"]
        assert "postgres" in services
        assert "neo4j" in services
        assert "milvus" in services
        assert "redis" in services
        
        # Verify summary metrics
        summary = result["summary"]
        assert "avg_response_time_ms" in summary
        assert "total_connections" in summary
        assert "performance_score" in summary
        assert "recommendations" in summary
        
        # Verify performance scores are calculated
        for service_data in services.values():
            if service_data.get("status") == "healthy":
                assert "performance_score" in service_data
                assert 0 <= service_data["performance_score"] <= 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])