"""
Tests for Database Optimization Module

This module tests the database optimization features including:
- Connection pooling
- Query optimization
- Batch processing
- Performance monitoring
"""

import pytest
import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, Any, List

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.multimodal_librarian.database.database_optimizer import (
    AdvancedConnectionPool,
    QueryOptimizer,
    BatchProcessor,
    DatabaseOptimizer,
    ConnectionPoolMetrics,
    QueryMetrics,
    get_database_optimizer,
    optimize_database,
    get_database_status
)


class TestAdvancedConnectionPool:
    """Test advanced connection pool functionality."""
    
    @pytest.fixture
    def mock_database_url(self):
        """Mock database URL for testing."""
        return "postgresql://test:test@localhost:5432/test_db"
    
    @pytest.fixture
    def connection_pool(self, mock_database_url):
        """Create connection pool for testing."""
        with patch('src.multimodal_librarian.database.database_optimizer.create_engine'):
            pool = AdvancedConnectionPool(mock_database_url)
            yield pool
            pool.close()
    
    def test_connection_pool_initialization(self, mock_database_url):
        """Test connection pool initialization."""
        with patch('src.multimodal_librarian.database.database_optimizer.create_engine') as mock_engine:
            mock_engine.return_value = Mock()
            
            pool = AdvancedConnectionPool(mock_database_url)
            
            assert pool.database_url == mock_database_url
            assert pool.engine is not None
            assert pool.SessionLocal is not None
            assert isinstance(pool.metrics, ConnectionPoolMetrics)
            
            pool.close()
    
    def test_pool_metrics_collection(self, connection_pool):
        """Test connection pool metrics collection."""
        # Mock pool object
        mock_pool = Mock()
        mock_pool.size.return_value = 10
        mock_pool.checkedout.return_value = 5
        mock_pool.checkedin.return_value = 5
        mock_pool.overflow.return_value = 2
        
        connection_pool.engine = Mock()
        connection_pool.engine.pool = mock_pool
        
        metrics = connection_pool.get_pool_metrics()
        
        assert metrics.pool_size == 10
        assert metrics.checked_out == 5
        assert metrics.checked_in == 5
        assert metrics.overflow == 2
        assert isinstance(metrics.last_updated, datetime)
    
    def test_pool_optimization(self, connection_pool):
        """Test connection pool optimization."""
        # Mock pool metrics
        connection_pool.metrics.pool_size = 10
        connection_pool.metrics.checked_out = 9  # High utilization
        connection_pool.metrics.average_checkout_time = 1.5  # High checkout time
        
        with patch.object(connection_pool, 'get_pool_metrics', return_value=connection_pool.metrics):
            result = connection_pool.optimize_pool_settings()
            
            assert result["optimization"] == "completed"
            assert "recommendations" in result
            assert len(result["recommendations"]) > 0
            assert result["utilization"] == 0.9
    
    def test_health_check(self, connection_pool):
        """Test connection pool health check."""
        # Mock session and query execution
        mock_session = Mock()
        mock_session.execute.return_value.scalar.return_value = 1
        
        with patch.object(connection_pool, 'get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_session
            mock_get_session.return_value.__exit__.return_value = None
            
            with patch.object(connection_pool, 'get_pool_metrics') as mock_metrics:
                mock_metrics.return_value = ConnectionPoolMetrics(
                    pool_size=10, checked_out=3, checked_in=7
                )
                
                result = connection_pool.health_check()
                
                assert result["status"] == "healthy"
                assert result["connectivity"] == "ok"
                assert "pool_metrics" in result
                assert result["pool_metrics"]["utilization"] == 0.3


class TestQueryOptimizer:
    """Test query optimization functionality."""
    
    @pytest.fixture
    def query_optimizer(self):
        """Create query optimizer for testing."""
        return QueryOptimizer()
    
    def test_query_metrics_recording(self, query_optimizer):
        """Test query execution metrics recording."""
        query = "SELECT * FROM test_table WHERE id = 1"
        execution_time = 150.5
        rows_affected = 1
        
        query_optimizer.record_query_execution(query, execution_time, rows_affected)
        
        query_hash = query_optimizer._hash_query(query)
        assert query_hash in query_optimizer.query_metrics
        
        metrics = query_optimizer.query_metrics[query_hash]
        assert metrics.execution_count == 1
        assert metrics.total_time_ms == execution_time
        assert metrics.average_time_ms == execution_time
        assert metrics.rows_affected == rows_affected
        assert metrics.error_count == 0
    
    def test_slow_query_detection(self, query_optimizer):
        """Test slow query detection."""
        # Record a slow query
        slow_query = "SELECT * FROM large_table ORDER BY created_at"
        query_optimizer.record_query_execution(slow_query, 2500.0)  # 2.5 seconds
        
        # Record a fast query
        fast_query = "SELECT id FROM small_table WHERE id = 1"
        query_optimizer.record_query_execution(fast_query, 50.0)  # 50ms
        
        slow_queries = query_optimizer.get_slow_queries(threshold_ms=1000)
        
        assert len(slow_queries) == 1
        assert slow_queries[0].average_time_ms == 2500.0
        assert slow_query in slow_queries[0].query_text
    
    def test_frequent_query_detection(self, query_optimizer):
        """Test frequent query detection."""
        query = "SELECT count(*) FROM users"
        
        # Execute query multiple times
        for _ in range(15):
            query_optimizer.record_query_execution(query, 100.0)
        
        frequent_queries = query_optimizer.get_frequent_queries(min_executions=10)
        
        assert len(frequent_queries) == 1
        assert frequent_queries[0].execution_count == 15
        assert query in frequent_queries[0].query_text
    
    def test_query_optimization_suggestions(self, query_optimizer):
        """Test query optimization suggestions."""
        # Test SELECT * suggestion
        select_all_query = "SELECT * FROM users WHERE active = true"
        suggestions = query_optimizer.suggest_optimizations(select_all_query)
        
        select_all_suggestions = [s for s in suggestions if s["type"] == "column_selection"]
        assert len(select_all_suggestions) > 0
        assert "SELECT *" in select_all_suggestions[0]["description"]
        
        # Test ORDER BY without LIMIT suggestion
        order_query = "SELECT name FROM users ORDER BY created_at"
        suggestions = query_optimizer.suggest_optimizations(order_query)
        
        pagination_suggestions = [s for s in suggestions if s["type"] == "pagination"]
        assert len(pagination_suggestions) > 0
        assert "LIMIT" in pagination_suggestions[0]["description"]
    
    def test_query_performance_analysis(self, query_optimizer):
        """Test comprehensive query performance analysis."""
        # Record various queries
        queries = [
            ("SELECT * FROM users", 500.0, 100),
            ("SELECT id FROM posts", 50.0, 50),
            ("UPDATE users SET last_login = NOW()", 1500.0, 1),
            ("DELETE FROM logs WHERE created_at < NOW() - INTERVAL '30 days'", 3000.0, 1000)
        ]
        
        for query, time_ms, rows in queries:
            query_optimizer.record_query_execution(query, time_ms, rows)
        
        analysis = query_optimizer.analyze_query_performance()
        
        assert analysis["status"] == "analyzed"
        assert analysis["summary"]["total_unique_queries"] == 4
        assert analysis["summary"]["total_executions"] == 4
        assert analysis["summary"]["average_execution_time_ms"] > 0
        assert len(analysis["slow_queries"]) > 0
    
    def test_query_monitoring_context_manager(self, query_optimizer):
        """Test query monitoring context manager."""
        query = "SELECT count(*) FROM test_table"
        
        with query_optimizer.monitor_query(query):
            time.sleep(0.1)  # Simulate query execution
        
        query_hash = query_optimizer._hash_query(query)
        assert query_hash in query_optimizer.query_metrics
        
        metrics = query_optimizer.query_metrics[query_hash]
        assert metrics.execution_count == 1
        assert metrics.total_time_ms >= 100  # At least 100ms due to sleep


class TestBatchProcessor:
    """Test batch processing functionality."""
    
    @pytest.fixture
    def mock_connection_pool(self):
        """Create mock connection pool for testing."""
        pool = Mock()
        
        # Mock session context manager
        mock_session = Mock()
        mock_session.execute.return_value.rowcount = 100
        
        pool.get_session.return_value.__enter__.return_value = mock_session
        pool.get_session.return_value.__exit__.return_value = None
        
        return pool
    
    @pytest.fixture
    def batch_processor(self, mock_connection_pool):
        """Create batch processor for testing."""
        return BatchProcessor(mock_connection_pool)
    
    def test_batch_insert(self, batch_processor):
        """Test batch insert operation."""
        table_name = "test_table"
        data = [
            {"id": 1, "name": "Test 1", "value": 100},
            {"id": 2, "name": "Test 2", "value": 200},
            {"id": 3, "name": "Test 3", "value": 300}
        ]
        
        result = batch_processor.batch_insert(table_name, data, batch_size=2)
        
        assert result["status"] == "success"
        assert result["total_rows"] == 3
        assert result["batches_processed"] > 0
        assert result["execution_time_seconds"] > 0
        assert result["rows_per_second"] > 0
    
    def test_batch_update(self, batch_processor):
        """Test batch update operation."""
        table_name = "test_table"
        updates = [
            {"id": 1, "name": "Updated 1", "value": 150},
            {"id": 2, "name": "Updated 2", "value": 250}
        ]
        
        result = batch_processor.batch_update(table_name, updates, key_column="id")
        
        assert result["status"] == "success"
        assert result["total_rows"] == 2
        assert result["batches_processed"] > 0
        assert result["execution_time_seconds"] > 0
    
    def test_batch_delete(self, batch_processor):
        """Test batch delete operation."""
        table_name = "test_table"
        conditions = [
            {"id": 1},
            {"id": 2}
        ]
        
        result = batch_processor.batch_delete(table_name, conditions)
        
        assert result["status"] == "success"
        assert result["total_conditions"] == 2
        assert result["batches_processed"] > 0
        assert result["execution_time_seconds"] > 0
    
    def test_empty_batch_operations(self, batch_processor):
        """Test batch operations with empty data."""
        table_name = "test_table"
        
        # Test empty insert
        insert_result = batch_processor.batch_insert(table_name, [])
        assert insert_result["status"] == "success"
        assert insert_result["rows_inserted"] == 0
        
        # Test empty update
        update_result = batch_processor.batch_update(table_name, [])
        assert update_result["status"] == "success"
        assert update_result["rows_updated"] == 0
        
        # Test empty delete
        delete_result = batch_processor.batch_delete(table_name, [])
        assert delete_result["status"] == "success"
        assert delete_result["rows_deleted"] == 0


class TestDatabaseOptimizer:
    """Test main database optimizer functionality."""
    
    @pytest.fixture
    def mock_database_optimizer(self):
        """Create mock database optimizer for testing."""
        with patch('src.multimodal_librarian.database.database_optimizer.AdvancedConnectionPool'), \
             patch('src.multimodal_librarian.database.database_optimizer.QueryOptimizer'), \
             patch('src.multimodal_librarian.database.database_optimizer.BatchProcessor'):
            
            optimizer = DatabaseOptimizer("postgresql://test:test@localhost:5432/test")
            
            # Mock components
            optimizer.connection_pool = Mock()
            optimizer.query_optimizer = Mock()
            optimizer.batch_processor = Mock()
            
            return optimizer
    
    def test_optimization_status(self, mock_database_optimizer):
        """Test getting optimization status."""
        # Mock component responses
        mock_database_optimizer.connection_pool.get_pool_metrics.return_value = ConnectionPoolMetrics(
            pool_size=10, checked_out=3, total_connections=15
        )
        
        mock_database_optimizer.query_optimizer.analyze_query_performance.return_value = {
            "status": "analyzed",
            "summary": {"total_unique_queries": 5}
        }
        
        mock_database_optimizer.connection_pool.health_check.return_value = {
            "status": "healthy"
        }
        
        status = mock_database_optimizer.get_optimization_status()
        
        assert status["status"] == "active"
        assert "connection_pool" in status
        assert "query_performance" in status
        assert "batch_processing" in status
    
    def test_database_optimization(self, mock_database_optimizer):
        """Test comprehensive database optimization."""
        # Mock optimization results
        mock_database_optimizer.connection_pool.optimize_pool_settings.return_value = {
            "optimization": "completed",
            "recommendations": ["increase_pool_size"]
        }
        
        mock_database_optimizer.query_optimizer.analyze_query_performance.return_value = {
            "status": "analyzed",
            "slow_queries": [{"query": "SELECT * FROM large_table"}]
        }
        
        mock_database_optimizer.connection_pool.get_pool_metrics.return_value = ConnectionPoolMetrics(
            pool_size=10, checked_out=3
        )
        
        result = mock_database_optimizer.optimize_database_performance()
        
        assert "optimizations" in result
        assert "recommendations" in result
        assert len(result["optimizations"]) > 0
    
    def test_monitoring_lifecycle(self, mock_database_optimizer):
        """Test monitoring start/stop lifecycle."""
        # Test start monitoring
        start_result = mock_database_optimizer.start_monitoring()
        assert start_result["status"] == "started"
        assert mock_database_optimizer._monitoring_active is True
        
        # Test stop monitoring
        stop_result = mock_database_optimizer.stop_monitoring()
        assert stop_result["status"] == "stopped"
        assert mock_database_optimizer._monitoring_active is False
    
    def test_optimizer_cleanup(self, mock_database_optimizer):
        """Test optimizer cleanup."""
        mock_database_optimizer.start_monitoring()
        
        # Test close
        mock_database_optimizer.close()
        
        # Verify monitoring stopped and connections closed
        assert mock_database_optimizer._monitoring_active is False
        mock_database_optimizer.connection_pool.close.assert_called_once()


class TestGlobalFunctions:
    """Test global convenience functions."""
    
    def test_get_database_optimizer_singleton(self):
        """Test global database optimizer singleton."""
        with patch('src.multimodal_librarian.database.database_optimizer.DatabaseOptimizer') as mock_optimizer_class:
            mock_instance = Mock()
            mock_optimizer_class.return_value = mock_instance
            
            # First call should create instance
            optimizer1 = get_database_optimizer()
            assert optimizer1 == mock_instance
            mock_optimizer_class.assert_called_once()
            
            # Second call should return same instance
            optimizer2 = get_database_optimizer()
            assert optimizer2 == mock_instance
            assert optimizer1 is optimizer2
            # Should not create new instance
            mock_optimizer_class.assert_called_once()
    
    def test_optimize_database_function(self):
        """Test global optimize database function."""
        with patch('src.multimodal_librarian.database.database_optimizer.get_database_optimizer') as mock_get_optimizer:
            mock_optimizer = Mock()
            mock_optimizer.optimize_database_performance.return_value = {"status": "success"}
            mock_get_optimizer.return_value = mock_optimizer
            
            result = optimize_database()
            
            assert result["status"] == "success"
            mock_optimizer.optimize_database_performance.assert_called_once()
    
    def test_get_database_status_function(self):
        """Test global get database status function."""
        with patch('src.multimodal_librarian.database.database_optimizer.get_database_optimizer') as mock_get_optimizer:
            mock_optimizer = Mock()
            mock_optimizer.get_optimization_status.return_value = {"status": "active"}
            mock_get_optimizer.return_value = mock_optimizer
            
            result = get_database_status()
            
            assert result["status"] == "active"
            mock_optimizer.get_optimization_status.assert_called_once()


class TestIntegration:
    """Integration tests for database optimization."""
    
    @pytest.mark.integration
    def test_end_to_end_optimization_flow(self):
        """Test complete optimization workflow."""
        with patch('src.multimodal_librarian.database.database_optimizer.create_engine'), \
             patch('src.multimodal_librarian.database.database_optimizer.db_manager'):
            
            # Create optimizer
            optimizer = DatabaseOptimizer("postgresql://test:test@localhost:5432/test")
            
            # Mock database interactions
            with patch.object(optimizer.connection_pool, 'get_session') as mock_session:
                mock_session.return_value.__enter__.return_value = Mock()
                mock_session.return_value.__exit__.return_value = None
                
                # Test optimization flow
                status = optimizer.get_optimization_status()
                assert status["status"] == "active"
                
                optimization_result = optimizer.optimize_database_performance()
                assert "optimizations" in optimization_result
                
                # Test monitoring
                optimizer.start_monitoring()
                assert optimizer._monitoring_active is True
                
                optimizer.stop_monitoring()
                assert optimizer._monitoring_active is False
                
                # Cleanup
                optimizer.close()
    
    @pytest.mark.integration
    def test_batch_processing_integration(self):
        """Test batch processing integration."""
        with patch('src.multimodal_librarian.database.database_optimizer.create_engine'), \
             patch('src.multimodal_librarian.database.database_optimizer.db_manager'):
            
            optimizer = DatabaseOptimizer("postgresql://test:test@localhost:5432/test")
            
            # Mock successful batch operations
            with patch.object(optimizer.batch_processor, 'batch_insert') as mock_insert:
                mock_insert.return_value = {
                    "status": "success",
                    "rows_inserted": 1000,
                    "batches_processed": 1,
                    "execution_time_seconds": 2.5,
                    "rows_per_second": 400.0,
                    "errors": []
                }
                
                # Test batch insert
                data = [{"id": i, "name": f"Test {i}"} for i in range(1000)]
                result = optimizer.batch_processor.batch_insert("test_table", data)
                
                assert result["status"] == "success"
                assert result["rows_inserted"] == 1000
                assert result["rows_per_second"] == 400.0
                
                optimizer.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])