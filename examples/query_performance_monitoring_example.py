"""
Query Performance Monitoring Example

This example demonstrates how to use the query performance monitoring system
in the local development environment. It shows how to:

1. Initialize and configure query performance monitoring
2. Integrate monitoring with database clients
3. Track query performance automatically
4. Generate and handle performance alerts
5. Export performance metrics

Run this example to see query performance monitoring in action.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import monitoring components
from multimodal_librarian.monitoring.query_performance_monitor import (
    QueryPerformanceMonitor, get_global_monitor
)
from multimodal_librarian.monitoring.query_performance_decorators import (
    track_query_performance, track_vector_operation, track_graph_operation
)
from multimodal_librarian.config.query_performance_config import (
    QueryPerformanceConfig, QueryPerformanceConfigFactory
)
from multimodal_librarian.monitoring.query_performance_integration import (
    initialize_query_monitoring, shutdown_query_monitoring, query_monitoring_context
)


class MockPostgreSQLClient:
    """Mock PostgreSQL client for demonstration."""
    
    @track_query_performance("postgresql")
    async def execute_query(self, query: str, parameters=None):
        """Execute a SQL query with performance monitoring."""
        # Simulate query execution time based on query type
        if "slow" in query.lower():
            await asyncio.sleep(1.2)  # Slow query
        elif "medium" in query.lower():
            await asyncio.sleep(0.5)  # Medium query
        else:
            await asyncio.sleep(0.1)  # Fast query
        
        # Simulate different result sizes
        if "large" in query.lower():
            return [{"id": i, "data": f"row_{i}"} for i in range(1000)]
        elif "medium" in query.lower():
            return [{"id": i, "data": f"row_{i}"} for i in range(100)]
        else:
            return [{"id": 1, "data": "single_row"}]
    
    @track_query_performance("postgresql", query_param="command")
    async def execute_command(self, command: str, parameters=None):
        """Execute a SQL command with performance monitoring."""
        await asyncio.sleep(0.05)  # Fast command
        return 1  # Affected rows


class MockMilvusClient:
    """Mock Milvus client for demonstration."""
    
    @track_vector_operation("vector_search")
    async def search_vectors(self, collection_name: str, query_vector: List[float], k: int = 10):
        """Search for similar vectors with performance monitoring."""
        # Simulate vector search time based on collection size
        if "large" in collection_name.lower():
            await asyncio.sleep(0.8)  # Large collection
        else:
            await asyncio.sleep(0.2)  # Small collection
        
        # Return mock results
        return [
            {"id": f"doc_{i}", "score": 0.9 - (i * 0.1), "metadata": {"content": f"Document {i}"}}
            for i in range(min(k, 5))
        ]
    
    @track_vector_operation("vector_insert", query_param="vectors")
    async def insert_vectors(self, collection_name: str, vectors: List[Dict[str, Any]]):
        """Insert vectors with performance monitoring."""
        # Simulate insertion time based on batch size
        batch_size = len(vectors)
        await asyncio.sleep(0.01 * batch_size)  # 10ms per vector
        return True


class MockNeo4jClient:
    """Mock Neo4j client for demonstration."""
    
    @track_graph_operation()
    async def execute_query(self, query: str, parameters=None):
        """Execute a Cypher query with performance monitoring."""
        # Simulate query execution time based on complexity
        if "complex" in query.lower() or "OPTIONAL MATCH" in query.upper():
            await asyncio.sleep(0.8)  # Complex query
        elif "MATCH" in query.upper():
            await asyncio.sleep(0.3)  # Simple match
        else:
            await asyncio.sleep(0.1)  # Very simple query
        
        # Return mock graph results
        return [
            {"n": {"id": 1, "labels": ["User"], "properties": {"name": "Alice"}}},
            {"n": {"id": 2, "labels": ["User"], "properties": {"name": "Bob"}}}
        ]


async def demonstrate_basic_monitoring():
    """Demonstrate basic query performance monitoring."""
    logger.info("=== Basic Query Performance Monitoring Demo ===")
    
    # Create configuration for development
    config = QueryPerformanceConfigFactory.create_development_config()
    config.slow_query_threshold_ms = 500.0  # Lower threshold for demo
    
    # Initialize monitoring
    async with query_monitoring_context(config) as manager:
        if not manager:
            logger.error("Failed to initialize monitoring")
            return
        
        logger.info("Query performance monitoring initialized")
        
        # Create mock clients
        pg_client = MockPostgreSQLClient()
        milvus_client = MockMilvusClient()
        neo4j_client = MockNeo4jClient()
        
        # Execute various queries
        logger.info("Executing PostgreSQL queries...")
        await pg_client.execute_query("SELECT * FROM users")  # Fast query
        await pg_client.execute_query("SELECT * FROM slow_table")  # Slow query
        await pg_client.execute_command("INSERT INTO logs (message) VALUES ('test')")
        
        logger.info("Executing Milvus operations...")
        await milvus_client.search_vectors("documents", [0.1, 0.2, 0.3], k=5)
        await milvus_client.search_vectors("large_collection", [0.4, 0.5, 0.6], k=10)
        await milvus_client.insert_vectors("documents", [
            {"id": "doc1", "vector": [0.1, 0.2], "metadata": {"title": "Test Doc"}}
        ])
        
        logger.info("Executing Neo4j queries...")
        await neo4j_client.execute_query("MATCH (n:User) RETURN n")
        await neo4j_client.execute_query("MATCH (u:User) OPTIONAL MATCH (u)-[:FRIEND]->(f) RETURN u, f")  # Complex
        
        # Wait a moment for processing
        await asyncio.sleep(0.5)
        
        # Get performance statistics
        stats = await manager.monitor.get_performance_stats()
        
        logger.info("Performance Statistics:")
        for db_type, db_stats in stats.items():
            logger.info(f"  {db_type.upper()}:")
            logger.info(f"    Total queries: {db_stats.total_queries}")
            logger.info(f"    Average time: {db_stats.avg_query_time_ms:.2f}ms")
            logger.info(f"    Slow queries: {db_stats.slow_query_count}")
            logger.info(f"    Error rate: {db_stats.error_rate:.2%}")
        
        # Get recent alerts
        alerts = await manager.monitor.get_recent_alerts(limit=10)
        if alerts:
            logger.info(f"Recent Alerts ({len(alerts)}):")
            for alert in alerts:
                logger.info(f"  [{alert.severity.upper()}] {alert.alert_type}: {alert.message}")
        else:
            logger.info("No performance alerts generated")


async def demonstrate_alert_handling():
    """Demonstrate performance alert handling."""
    logger.info("\n=== Performance Alert Handling Demo ===")
    
    # Create configuration with strict thresholds
    config = QueryPerformanceConfigFactory.create_development_config()
    config.slow_query_threshold_ms = 200.0  # Very strict threshold
    config.high_cpu_threshold = 30.0  # Low CPU threshold for demo
    
    alerts_received = []
    
    def alert_handler(alert):
        """Custom alert handler."""
        alerts_received.append(alert)
        logger.warning(f"ALERT: [{alert.severity}] {alert.alert_type} - {alert.message}")
        if alert.recommendations:
            logger.info(f"Recommendations: {'; '.join(alert.recommendations)}")
    
    async with query_monitoring_context(config) as manager:
        if not manager:
            return
        
        # Add custom alert handler
        manager.monitor.add_alert_callback(alert_handler)
        
        # Create client and execute slow queries
        pg_client = MockPostgreSQLClient()
        
        logger.info("Executing queries that should trigger alerts...")
        
        # Execute slow queries
        await pg_client.execute_query("SELECT * FROM slow_table")  # Should trigger slow query alert
        await pg_client.execute_query("SELECT * FROM very_slow_table")  # Another slow query
        
        # Wait for alert processing
        await asyncio.sleep(0.5)
        
        logger.info(f"Total alerts received: {len(alerts_received)}")
        
        # Show alert details
        for i, alert in enumerate(alerts_received, 1):
            logger.info(f"Alert {i}:")
            logger.info(f"  Type: {alert.alert_type}")
            logger.info(f"  Severity: {alert.severity}")
            logger.info(f"  Database: {alert.database_type.value}")
            logger.info(f"  Time: {alert.timestamp}")
            if alert.query_metrics:
                logger.info(f"  Query Duration: {alert.query_metrics.duration_ms:.2f}ms")


async def demonstrate_metrics_export():
    """Demonstrate metrics export functionality."""
    logger.info("\n=== Metrics Export Demo ===")
    
    config = QueryPerformanceConfigFactory.create_development_config()
    
    async with query_monitoring_context(config) as manager:
        if not manager:
            return
        
        # Execute some queries to generate metrics
        pg_client = MockPostgreSQLClient()
        milvus_client = MockMilvusClient()
        
        logger.info("Generating sample metrics...")
        
        for i in range(5):
            await pg_client.execute_query(f"SELECT * FROM table_{i}")
            await milvus_client.search_vectors("documents", [0.1 * i, 0.2 * i, 0.3 * i])
        
        # Export metrics to JSON
        import tempfile
        import os
        
        with tempfile.TemporaryDirectory() as temp_dir:
            json_file = os.path.join(temp_dir, "query_metrics.json")
            csv_file = os.path.join(temp_dir, "query_metrics.csv")
            
            # Export to JSON
            success = await manager.monitor.export_metrics(json_file, format="json")
            if success:
                logger.info(f"Metrics exported to JSON: {json_file}")
                
                # Show file size
                file_size = os.path.getsize(json_file)
                logger.info(f"JSON file size: {file_size} bytes")
            
            # Export to CSV
            success = await manager.monitor.export_metrics(csv_file, format="csv")
            if success:
                logger.info(f"Metrics exported to CSV: {csv_file}")
                
                # Show file size
                file_size = os.path.getsize(csv_file)
                logger.info(f"CSV file size: {file_size} bytes")


async def demonstrate_monitoring_dashboard_data():
    """Demonstrate getting data for monitoring dashboard."""
    logger.info("\n=== Monitoring Dashboard Data Demo ===")
    
    config = QueryPerformanceConfigFactory.create_development_config()
    
    async with query_monitoring_context(config) as manager:
        if not manager:
            return
        
        # Execute queries across different databases
        pg_client = MockPostgreSQLClient()
        milvus_client = MockMilvusClient()
        neo4j_client = MockNeo4jClient()
        
        logger.info("Generating diverse query patterns...")
        
        # Mix of fast and slow queries
        await pg_client.execute_query("SELECT COUNT(*) FROM users")  # Fast
        await pg_client.execute_query("SELECT * FROM large_table")  # Medium
        await milvus_client.search_vectors("documents", [0.1, 0.2, 0.3])  # Fast
        await neo4j_client.execute_query("MATCH (n) RETURN count(n)")  # Fast
        await neo4j_client.execute_query("MATCH (u:User) OPTIONAL MATCH (u)-[:FRIEND*2..3]->(f) RETURN u, f")  # Slow
        
        # Wait for processing
        await asyncio.sleep(0.5)
        
        # Get dashboard data
        from multimodal_librarian.monitoring.query_performance_integration import get_monitoring_dashboard_data
        
        dashboard_data = get_monitoring_dashboard_data()
        
        logger.info("Dashboard Data:")
        logger.info(f"  Monitoring Enabled: {dashboard_data.get('monitoring_enabled', False)}")
        
        if 'status' in dashboard_data:
            status = dashboard_data['status']
            logger.info(f"  Total Queries Tracked: {status.get('total_queries_tracked', 0)}")
            logger.info(f"  Total Alerts: {status.get('total_alerts', 0)}")
            logger.info(f"  Queries by Database: {status.get('queries_by_database', {})}")
        
        if 'config' in dashboard_data:
            config_info = dashboard_data['config']
            logger.info(f"  Monitoring Level: {config_info.get('monitoring_level', 'unknown')}")
            logger.info(f"  Slow Query Threshold: {config_info.get('slow_query_threshold_ms', 0)}ms")
            logger.info(f"  Sample Rate: {config_info.get('sample_rate', 0):.1%}")


async def demonstrate_error_handling():
    """Demonstrate error handling in query monitoring."""
    logger.info("\n=== Error Handling Demo ===")
    
    config = QueryPerformanceConfigFactory.create_development_config()
    
    async with query_monitoring_context(config) as manager:
        if not manager:
            return
        
        # Create a client that will raise errors
        class ErrorProneClient:
            @track_query_performance("postgresql")
            async def execute_query(self, query: str):
                if "error" in query.lower():
                    raise Exception(f"Database error: Invalid query '{query}'")
                return [{"result": "success"}]
        
        client = ErrorProneClient()
        
        logger.info("Executing queries with errors...")
        
        # Successful query
        try:
            result = await client.execute_query("SELECT 1")
            logger.info("Successful query executed")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
        
        # Query that will raise an error
        try:
            await client.execute_query("SELECT * FROM error_table")
        except Exception as e:
            logger.info(f"Expected error caught: {e}")
        
        # Check that errors were recorded
        await asyncio.sleep(0.1)
        
        stats = await manager.monitor.get_performance_stats("postgresql")
        if "postgresql" in stats:
            pg_stats = stats["postgresql"]
            logger.info(f"Total queries: {pg_stats.total_queries}")
            logger.info(f"Successful queries: {pg_stats.successful_queries}")
            logger.info(f"Failed queries: {pg_stats.failed_queries}")
            logger.info(f"Error rate: {pg_stats.error_rate:.2%}")
            
            if pg_stats.common_errors:
                logger.info("Common errors:")
                for error, count in pg_stats.common_errors.items():
                    logger.info(f"  {error}: {count} occurrences")


async def main():
    """Run all demonstration examples."""
    logger.info("Query Performance Monitoring Demonstration")
    logger.info("=" * 50)
    
    try:
        await demonstrate_basic_monitoring()
        await demonstrate_alert_handling()
        await demonstrate_metrics_export()
        await demonstrate_monitoring_dashboard_data()
        await demonstrate_error_handling()
        
        logger.info("\n" + "=" * 50)
        logger.info("Query Performance Monitoring Demo Complete!")
        logger.info("Key features demonstrated:")
        logger.info("  ✓ Automatic query performance tracking")
        logger.info("  ✓ Slow query detection and alerting")
        logger.info("  ✓ Multi-database support (PostgreSQL, Milvus, Neo4j)")
        logger.info("  ✓ Performance statistics calculation")
        logger.info("  ✓ Metrics export (JSON, CSV)")
        logger.info("  ✓ Error tracking and analysis")
        logger.info("  ✓ Dashboard data integration")
        
    except Exception as e:
        logger.error(f"Demo failed with error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())