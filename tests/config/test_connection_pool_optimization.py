"""
Tests for Connection Pool Optimization

This module tests the connection pool optimization functionality including
the optimizer, database-specific optimizers, and the pool manager.
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from src.multimodal_librarian.config.connection_pool_optimizer import (
    ConnectionPoolOptimizer, OptimizationStrategy, PoolOptimizationMetrics,
    OptimizationRecommendation
)
from src.multimodal_librarian.config.database_pool_optimizers import (
    PostgreSQLPoolOptimizer, Neo4jPoolOptimizer, MilvusPoolOptimizer,
    create_pool_optimizer
)
from src.multimodal_librarian.config.connection_pool_manager import (
    ConnectionPoolManager, get_pool_manager
)
from src.multimodal_librarian.config.local_config import LocalDatabaseConfig


class TestConnectionPoolOptimizer:
    """Test the base connection pool optimizer."""
    
    def test_optimizer_initialization(self):
        """Test optimizer initialization with different strategies."""
        optimizer = ConnectionPoolOptimizer(
            pool_name="test_pool",
            optimization_strategy=OptimizationStrategy.BALANCED,
            enable_auto_optimization=True
        )
        
        assert optimizer.pool_name == "test_pool"
        assert optimizer.optimization_strategy == OptimizationStrategy.BALANCED
        assert optimizer.enable_auto_optimization is True
        assert optimizer.target_utilization == 0.7
        assert len(optimizer.active_recommendations) == 0
    
    def test_metrics_initialization(self):
        """Test that metrics are properly initialized."""
        optimizer = ConnectionPoolOptimizer("test_pool")
        
        assert optimizer.current_metrics.pool_size == 0
        assert optimizer.current_metrics.utilization_percentage == 0.0
        assert optimizer.current_metrics.connection_errors == 0
        assert len(optimizer.historical_metrics) == 0
    
    def test_connection_checkout_recording(self):
        """Test recording connection checkout events."""
        optimizer = ConnectionPoolOptimizer("test_pool")
        
        # Record a checkout
        optimizer.record_connection_checkout("conn_1", 0.5)
        
        assert len(optimizer.checkout_times) == 1
        assert optimizer.checkout_times[0] == 0.5
        assert len(optimizer.connection_events) == 1
        assert optimizer.connection_events[0]["event"] == "checkout"
        assert optimizer.current_metrics.total_connection_requests == 1
    
    def test_connection_checkin_recording(self):
        """Test recording connection checkin events."""
        optimizer = ConnectionPoolOptimizer("test_pool")
        
        # First checkout, then checkin
        optimizer.record_connection_checkout("conn_1", 0.5)
        optimizer.record_connection_checkin("conn_1", 0.2, had_error=False)
        
        assert len(optimizer.checkin_times) == 1
        assert optimizer.checkin_times[0] == 0.2
        assert optimizer.current_metrics.checked_in == 1
    
    def test_connection_error_recording(self):
        """Test recording connection errors."""
        optimizer = ConnectionPoolOptimizer("test_pool")
        
        # Record an error
        optimizer.record_connection_error("conn_1", "Connection timeout")
        
        assert len(optimizer.error_events) == 1
        assert optimizer.error_events[0]["error"] == "Connection timeout"
        assert optimizer.current_metrics.connection_errors == 1
    
    def test_optimization_recommendations_generation(self):
        """Test generation of optimization recommendations."""
        optimizer = ConnectionPoolOptimizer("test_pool")
        
        # Simulate high utilization
        optimizer.current_metrics.pool_size = 10
        optimizer.current_metrics.checked_out = 9
        optimizer.current_metrics.utilization_percentage = 90.0
        
        recommendations = optimizer.get_optimization_recommendations()
        
        # Should recommend increasing pool size
        assert len(recommendations) > 0
        increase_pool_rec = next(
            (r for r in recommendations if r.type == "increase_pool_size"), 
            None
        )
        assert increase_pool_rec is not None
        assert increase_pool_rec.priority == "high"
    
    def test_performance_report_generation(self):
        """Test performance report generation."""
        optimizer = ConnectionPoolOptimizer("test_pool")
        
        # Add some metrics
        optimizer.current_metrics.pool_size = 10
        optimizer.current_metrics.utilization_percentage = 60.0
        optimizer.current_metrics.connection_errors = 2
        optimizer.current_metrics.total_connection_requests = 100
        
        report = optimizer.get_performance_report()
        
        assert "pool_name" in report
        assert "overall_score" in report
        assert "metrics" in report
        assert report["pool_name"] == "test_pool"
        assert report["metrics"]["pool_size"] == 10
        assert report["metrics"]["utilization_percentage"] == 60.0
    
    def test_metrics_reset(self):
        """Test resetting metrics."""
        optimizer = ConnectionPoolOptimizer("test_pool")
        
        # Add some data
        optimizer.record_connection_checkout("conn_1", 0.5)
        optimizer.record_connection_error("conn_1", "Test error")
        
        # Reset metrics
        optimizer.reset_metrics()
        
        assert len(optimizer.checkout_times) == 0
        assert len(optimizer.error_events) == 0
        assert optimizer.current_metrics.connection_errors == 0
    
    @pytest.mark.asyncio
    async def test_monitoring_lifecycle(self):
        """Test starting and stopping monitoring."""
        optimizer = ConnectionPoolOptimizer(
            "test_pool",
            monitoring_interval=0.1,  # Fast for testing
            optimization_interval=0.2
        )
        
        # Start monitoring
        await optimizer.start_monitoring()
        assert optimizer._monitoring_task is not None
        
        # Let it run briefly
        await asyncio.sleep(0.15)
        
        # Stop monitoring
        await optimizer.stop_monitoring()
        assert optimizer._monitoring_task is None


class TestDatabaseSpecificOptimizers:
    """Test database-specific optimizers."""
    
    def test_postgresql_optimizer_creation(self):
        """Test PostgreSQL optimizer creation."""
        mock_client = Mock()
        mock_client.engine = Mock()
        mock_client.get_pool_status.return_value = {
            "size": 10, "checked_out": 3, "checked_in": 7, "overflow": 0, "invalid": 0
        }
        
        optimizer = PostgreSQLPoolOptimizer(
            mock_client,
            OptimizationStrategy.BALANCED
        )
        
        assert optimizer.pool_name == "postgresql"
        assert optimizer.postgresql_client == mock_client
        assert optimizer.optimization_strategy == OptimizationStrategy.BALANCED
    
    def test_neo4j_optimizer_creation(self):
        """Test Neo4j optimizer creation."""
        mock_client = Mock()
        mock_client.driver = Mock()
        mock_client.max_connection_pool_size = 50
        
        optimizer = Neo4jPoolOptimizer(
            mock_client,
            OptimizationStrategy.CONSERVATIVE
        )
        
        assert optimizer.pool_name == "neo4j"
        assert optimizer.neo4j_client == mock_client
        assert optimizer.optimization_strategy == OptimizationStrategy.CONSERVATIVE
    
    def test_milvus_optimizer_creation(self):
        """Test Milvus optimizer creation."""
        mock_client = Mock()
        mock_client._connected = True
        
        optimizer = MilvusPoolOptimizer(
            mock_client,
            OptimizationStrategy.AGGRESSIVE
        )
        
        assert optimizer.pool_name == "milvus"
        assert optimizer.milvus_client == mock_client
        assert optimizer.optimization_strategy == OptimizationStrategy.AGGRESSIVE
    
    def test_optimizer_factory(self):
        """Test the optimizer factory function."""
        mock_client = Mock()
        
        # Test PostgreSQL
        pg_optimizer = create_pool_optimizer("postgresql", mock_client)
        assert isinstance(pg_optimizer, PostgreSQLPoolOptimizer)
        
        # Test Neo4j
        neo4j_optimizer = create_pool_optimizer("neo4j", mock_client)
        assert isinstance(neo4j_optimizer, Neo4jPoolOptimizer)
        
        # Test Milvus
        milvus_optimizer = create_pool_optimizer("milvus", mock_client)
        assert isinstance(milvus_optimizer, MilvusPoolOptimizer)
        
        # Test invalid type
        with pytest.raises(ValueError):
            create_pool_optimizer("invalid_db", mock_client)


class TestConnectionPoolManager:
    """Test the connection pool manager."""
    
    def test_manager_initialization(self):
        """Test manager initialization."""
        config = LocalDatabaseConfig.create_test_config(
            enable_pool_optimization=True,
            pool_optimization_strategy="balanced"
        )
        
        manager = ConnectionPoolManager(config)
        
        assert manager.config == config
        assert manager.optimization_strategy == OptimizationStrategy.BALANCED
        assert len(manager.optimizers) == 0
        assert len(manager.clients) == 0
    
    @pytest.mark.asyncio
    async def test_client_registration(self):
        """Test registering database clients."""
        config = LocalDatabaseConfig.create_test_config(
            enable_pool_optimization=True,
            enable_pool_health_monitoring=False  # Disable to avoid async issues in test
        )
        
        manager = ConnectionPoolManager(config)
        mock_client = Mock()
        
        # Register a client
        await manager.register_client("postgresql", mock_client)
        
        assert "postgresql" in manager.clients
        assert "postgresql" in manager.optimizers
        assert isinstance(manager.optimizers["postgresql"], PostgreSQLPoolOptimizer)
    
    @pytest.mark.asyncio
    async def test_client_unregistration(self):
        """Test unregistering database clients."""
        config = LocalDatabaseConfig.create_test_config(
            enable_pool_optimization=True,
            enable_pool_health_monitoring=False
        )
        
        manager = ConnectionPoolManager(config)
        mock_client = Mock()
        
        # Register then unregister
        await manager.register_client("postgresql", mock_client)
        await manager.unregister_client("postgresql")
        
        assert "postgresql" not in manager.clients
        assert "postgresql" not in manager.optimizers
    
    def test_system_status(self):
        """Test getting system status."""
        config = LocalDatabaseConfig.create_test_config(
            enable_pool_optimization=True
        )
        
        manager = ConnectionPoolManager(config)
        status = manager.get_system_status()
        
        assert "timestamp" in status
        assert "optimization_enabled" in status
        assert "strategy" in status
        assert "databases" in status
        assert "system_metrics" in status
        assert status["optimization_enabled"] is True
        assert status["strategy"] == "balanced"
    
    @pytest.mark.asyncio
    async def test_monitoring_lifecycle(self):
        """Test manager monitoring lifecycle."""
        config = LocalDatabaseConfig.create_test_config(
            enable_pool_optimization=True,
            enable_pool_health_monitoring=True,
            pool_health_check_interval=0.1  # Fast for testing
        )
        
        manager = ConnectionPoolManager(config)
        
        # Start monitoring
        await manager.start_monitoring()
        assert manager._monitoring_task is not None
        
        # Let it run briefly
        await asyncio.sleep(0.15)
        
        # Stop monitoring
        await manager.stop_monitoring()
        assert manager._monitoring_task is None
    
    def test_optimization_report(self):
        """Test generating optimization report."""
        config = LocalDatabaseConfig.create_test_config(
            enable_pool_optimization=True
        )
        
        manager = ConnectionPoolManager(config)
        report = manager.get_optimization_report()
        
        assert "timestamp" in report
        assert "system_overview" in report
        assert "database_reports" in report
        assert "cross_database_analysis" in report
        assert "system_recommendations" in report


class TestLocalConfigIntegration:
    """Test integration with local configuration."""
    
    def test_pool_optimization_config(self):
        """Test pool optimization configuration."""
        config = LocalDatabaseConfig.create_test_config(
            enable_pool_optimization=True,
            pool_optimization_strategy="aggressive",
            pool_target_utilization=0.8,
            enable_auto_pool_optimization=True
        )
        
        pool_config = config.get_connection_pool_config()
        
        assert pool_config["enabled"] is True
        assert pool_config["optimization"]["enabled"] is True
        assert pool_config["optimization"]["strategy"] == "aggressive"
        assert pool_config["optimization"]["target_utilization"] == 0.8
        assert pool_config["optimization"]["auto_optimization"] is True
    
    def test_pool_config_validation(self):
        """Test validation of pool configuration."""
        # Test valid strategy
        config = LocalDatabaseConfig.create_test_config(
            pool_optimization_strategy="balanced"
        )
        assert config.pool_optimization_strategy == "balanced"
        
        # Test invalid strategy should raise error during validation
        with pytest.raises(ValueError):
            # Create config without using create_test_config to avoid bypassing validation
            LocalDatabaseConfig(
                pool_optimization_strategy="invalid_strategy",
                environment="development"  # Not 'test' to enable validation
            )
    
    def test_pool_utilization_validation(self):
        """Test validation of pool utilization settings."""
        # Test valid utilization
        config = LocalDatabaseConfig.create_test_config(
            pool_target_utilization=0.75
        )
        assert config.pool_target_utilization == 0.75
        
        # Test invalid utilization should raise error
        with pytest.raises(ValueError):
            # Create config without using create_test_config to avoid bypassing validation
            LocalDatabaseConfig(
                pool_target_utilization=1.5,  # Invalid: > 1.0
                environment="development"  # Not 'test' to enable validation
            )
    
    def test_database_specific_pool_config(self):
        """Test database-specific pool configuration."""
        config = LocalDatabaseConfig.create_test_config(
            postgres_pool_size=15,
            postgres_max_overflow=25,
            neo4j_pool_size=75,
            milvus_connection_pool_size=12
        )
        
        pool_config = config.get_connection_pool_config()
        
        assert pool_config["postgres"]["pool_size"] == 15
        assert pool_config["postgres"]["max_overflow"] == 25
        assert pool_config["neo4j"]["max_connection_pool_size"] == 75
        assert pool_config["milvus"]["pool_size"] == 12


class TestOptimizationRecommendations:
    """Test optimization recommendation system."""
    
    def test_recommendation_creation(self):
        """Test creating optimization recommendations."""
        recommendation = OptimizationRecommendation(
            type="increase_pool_size",
            priority="high",
            description="Pool utilization is high",
            current_value=10,
            recommended_value=15,
            expected_impact="Reduced connection wait times",
            implementation_complexity="low",
            estimated_improvement=20.0,
            risks=["Increased memory usage"],
            prerequisites=["Check system resources"]
        )
        
        assert recommendation.type == "increase_pool_size"
        assert recommendation.priority == "high"
        assert recommendation.estimated_improvement == 20.0
        assert len(recommendation.risks) == 1
        assert len(recommendation.prerequisites) == 1
    
    def test_recommendation_filtering_by_strategy(self):
        """Test filtering recommendations by optimization strategy."""
        optimizer = ConnectionPoolOptimizer(
            "test_pool",
            optimization_strategy=OptimizationStrategy.CONSERVATIVE
        )
        
        recommendations = [
            OptimizationRecommendation(
                type="low_risk_optimization",
                priority="medium",
                description="Low risk change",
                current_value=10,
                recommended_value=12,
                expected_impact="Minor improvement",
                implementation_complexity="low",
                estimated_improvement=15.0
            ),
            OptimizationRecommendation(
                type="high_risk_optimization",
                priority="high",
                description="High risk change",
                current_value=10,
                recommended_value=20,
                expected_impact="Major improvement",
                implementation_complexity="high",
                estimated_improvement=30.0
            )
        ]
        
        filtered = optimizer._filter_recommendations_by_strategy(recommendations)
        
        # Conservative strategy should only include low-complexity, high-impact changes
        assert len(filtered) == 1
        assert filtered[0].type == "low_risk_optimization"


@pytest.mark.asyncio
async def test_end_to_end_optimization():
    """Test end-to-end optimization workflow."""
    # Create configuration
    config = LocalDatabaseConfig.create_test_config(
        enable_pool_optimization=True,
        pool_optimization_strategy="balanced",
        enable_auto_pool_optimization=False,  # Manual optimization for testing
        enable_pool_health_monitoring=False   # Disable to avoid async complexity
    )
    
    # Create manager
    manager = ConnectionPoolManager(config)
    
    # Create mock clients
    mock_pg_client = Mock()
    mock_pg_client.engine = Mock()
    mock_pg_client.get_pool_status.return_value = {
        "size": 10, "checked_out": 8, "checked_in": 2, "overflow": 0, "invalid": 0
    }
    
    mock_neo4j_client = Mock()
    mock_neo4j_client.driver = Mock()
    mock_neo4j_client.max_connection_pool_size = 50
    
    # Register clients
    await manager.register_client("postgresql", mock_pg_client)
    await manager.register_client("neo4j", mock_neo4j_client)
    
    # Simulate some activity
    pg_optimizer = manager.optimizers["postgresql"]
    pg_optimizer.record_connection_checkout("conn_1", 0.5)
    pg_optimizer.record_connection_checkout("conn_2", 1.2)  # Slow checkout
    pg_optimizer.record_connection_checkin("conn_1", 0.1)
    
    # Get system status
    status = manager.get_system_status()
    assert len(status["databases"]) == 2
    assert "postgresql" in status["databases"]
    assert "neo4j" in status["databases"]
    
    # Run optimization
    optimization_results = await manager.optimize_all_pools()
    assert "optimization_results" in optimization_results
    assert "postgresql" in optimization_results["optimization_results"]
    assert "neo4j" in optimization_results["optimization_results"]
    
    # Get optimization report
    report = manager.get_optimization_report()
    assert "database_reports" in report
    assert "system_recommendations" in report
    
    # Clean up
    await manager.unregister_client("postgresql")
    await manager.unregister_client("neo4j")


if __name__ == "__main__":
    pytest.main([__file__])