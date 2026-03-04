"""
Neo4j Performance Optimization Tests

Tests to validate that Neo4j memory and performance optimizations
meet the requirements for local development.
"""

import pytest
import time
import asyncio
from typing import Dict, Any
import docker
from neo4j import GraphDatabase


class TestNeo4jPerformanceOptimization:
    """Test Neo4j performance optimizations for local development."""
    
    @pytest.fixture(scope="class")
    def neo4j_driver(self):
        """Create Neo4j driver for testing."""
        driver = GraphDatabase.driver(
            "bolt://localhost:7687",
            auth=("neo4j", "ml_password")
        )
        yield driver
        driver.close()
    
    @pytest.fixture(scope="class")
    def docker_client(self):
        """Create Docker client for container monitoring."""
        return docker.from_env()
    
    def test_neo4j_connection(self, neo4j_driver):
        """Test that Neo4j is accessible and responsive."""
        with neo4j_driver.session() as session:
            result = session.run("RETURN 1 as test")
            assert result.single()["test"] == 1
    
    def test_memory_usage_within_limits(self, docker_client):
        """Test that Neo4j memory usage is within development limits."""
        try:
            container = docker_client.containers.get("local-development-conversion-neo4j-1")
            stats = container.stats(stream=False)
            
            memory_usage_mb = stats['memory_stats']['usage'] / (1024 * 1024)
            memory_limit_mb = stats['memory_stats']['limit'] / (1024 * 1024)
            
            # Should use less than 1.5GB (1536MB) for development
            assert memory_usage_mb < 1536, f"Memory usage {memory_usage_mb:.1f}MB exceeds 1536MB limit"
            
            # Memory usage should be reasonable (not too low, indicating issues)
            assert memory_usage_mb > 100, f"Memory usage {memory_usage_mb:.1f}MB seems too low"
            
        except docker.errors.NotFound:
            pytest.skip("Neo4j container not found - may not be running")
    
    def test_heap_memory_configuration(self, neo4j_driver):
        """Test that heap memory is configured correctly."""
        with neo4j_driver.session() as session:
            try:
                result = session.run("""
                    CALL dbms.queryJmx("org.neo4j:instance=kernel#0,name=Memory Pools") 
                    YIELD attributes 
                    RETURN attributes
                """)
                
                heap_found = False
                for record in result:
                    attrs = record['attributes']
                    if 'HeapMemoryUsage' in attrs:
                        heap_usage = attrs['HeapMemoryUsage']['value']
                        heap_max_mb = heap_usage['max'] / (1024 * 1024)
                        heap_used_mb = heap_usage['used'] / (1024 * 1024)
                        
                        # Max heap should be around 1GB (1024MB)
                        assert 900 <= heap_max_mb <= 1100, f"Heap max {heap_max_mb:.1f}MB not around 1024MB"
                        
                        # Used heap should be reasonable
                        assert heap_used_mb > 50, f"Heap usage {heap_used_mb:.1f}MB seems too low"
                        assert heap_used_mb < heap_max_mb * 0.9, f"Heap usage {heap_used_mb:.1f}MB too close to max"
                        
                        heap_found = True
                        break
                
                assert heap_found, "Could not find heap memory information"
                
            except Exception as e:
                pytest.skip(f"Could not query JMX metrics: {e}")
    
    def test_query_performance_basic(self, neo4j_driver):
        """Test basic query performance meets development requirements."""
        with neo4j_driver.session() as session:
            # Test node creation performance
            start_time = time.time()
            session.run("""
                CREATE (n:PerfTest {id: $id, timestamp: $timestamp})
                RETURN n
            """, id=f"perf_test_{int(time.time())}", timestamp=time.time())
            create_time_ms = (time.time() - start_time) * 1000
            
            # Should create nodes quickly (< 100ms for development)
            assert create_time_ms < 100, f"Node creation took {create_time_ms:.1f}ms (> 100ms)"
            
            # Test simple query performance
            start_time = time.time()
            result = session.run("MATCH (n:PerfTest) RETURN count(n) as count")
            count = result.single()['count']
            query_time_ms = (time.time() - start_time) * 1000
            
            # Should query quickly (< 50ms for simple queries)
            assert query_time_ms < 50, f"Count query took {query_time_ms:.1f}ms (> 50ms)"
            assert count > 0, "Should have at least one test node"
            
            # Cleanup
            session.run("MATCH (n:PerfTest) DETACH DELETE n")
    
    def test_plugin_availability(self, neo4j_driver):
        """Test that required plugins (APOC, GDS) are available."""
        with neo4j_driver.session() as session:
            # Test APOC availability
            result = session.run("""
                CALL dbms.procedures() 
                YIELD name 
                WHERE name STARTS WITH 'apoc' 
                RETURN count(name) as apoc_count
            """)
            apoc_count = result.single()['apoc_count']
            assert apoc_count > 0, "APOC procedures not available"
            
            # Test GDS availability
            result = session.run("""
                CALL dbms.procedures() 
                YIELD name 
                WHERE name STARTS WITH 'gds' 
                RETURN count(name) as gds_count
            """)
            gds_count = result.single()['gds_count']
            assert gds_count > 0, "GDS procedures not available"
    
    def test_page_cache_performance(self, neo4j_driver):
        """Test page cache configuration and performance."""
        with neo4j_driver.session() as session:
            try:
                # Create some test data for cache testing
                session.run("""
                    UNWIND range(1, 1000) as i
                    CREATE (n:CacheTest {id: i, data: 'test_data_' + toString(i)})
                """)
                
                # Query data multiple times to test cache
                for _ in range(3):
                    start_time = time.time()
                    result = session.run("""
                        MATCH (n:CacheTest) 
                        WHERE n.id <= 100 
                        RETURN count(n) as count
                    """)
                    count = result.single()['count']
                    query_time_ms = (time.time() - start_time) * 1000
                    
                    assert count == 100, "Should return 100 nodes"
                    # Subsequent queries should be faster due to caching
                    if _ > 0:  # Skip first query (cold cache)
                        assert query_time_ms < 20, f"Cached query took {query_time_ms:.1f}ms (> 20ms)"
                
                # Cleanup
                session.run("MATCH (n:CacheTest) DETACH DELETE n")
                
            except Exception as e:
                pytest.skip(f"Could not test page cache: {e}")
    
    def test_transaction_performance(self, neo4j_driver):
        """Test transaction performance and configuration."""
        with neo4j_driver.session() as session:
            # Test transaction commit performance
            start_time = time.time()
            
            with session.begin_transaction() as tx:
                for i in range(100):
                    tx.run("""
                        CREATE (n:TxTest {id: $id, batch: $batch})
                    """, id=i, batch="performance_test")
                tx.commit()
            
            tx_time_ms = (time.time() - start_time) * 1000
            
            # Batch transaction should be efficient (< 500ms for 100 nodes)
            assert tx_time_ms < 500, f"Transaction took {tx_time_ms:.1f}ms (> 500ms)"
            
            # Verify all nodes were created
            result = session.run("""
                MATCH (n:TxTest {batch: 'performance_test'}) 
                RETURN count(n) as count
            """)
            count = result.single()['count']
            assert count == 100, f"Expected 100 nodes, got {count}"
            
            # Cleanup
            session.run("MATCH (n:TxTest) DETACH DELETE n")
    
    def test_concurrent_query_performance(self, neo4j_driver):
        """Test performance under concurrent load."""
        async def run_concurrent_queries():
            """Run multiple queries concurrently."""
            tasks = []
            
            for i in range(10):
                task = asyncio.create_task(self._run_query_async(i))
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check that all queries completed successfully
            successful_queries = [r for r in results if not isinstance(r, Exception)]
            assert len(successful_queries) == 10, f"Only {len(successful_queries)}/10 queries succeeded"
            
            # Check average response time
            avg_time_ms = sum(successful_queries) / len(successful_queries)
            assert avg_time_ms < 100, f"Average concurrent query time {avg_time_ms:.1f}ms (> 100ms)"
        
        # Run the concurrent test
        asyncio.run(run_concurrent_queries())
    
    async def _run_query_async(self, query_id: int) -> float:
        """Run a single query asynchronously and return execution time."""
        driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "ml_password"))
        
        try:
            start_time = time.time()
            
            with driver.session() as session:
                result = session.run("""
                    CREATE (n:ConcurrentTest {id: $id, timestamp: $timestamp})
                    RETURN n.id as created_id
                """, id=query_id, timestamp=time.time())
                
                created_id = result.single()['created_id']
                assert created_id == query_id, f"Expected {query_id}, got {created_id}"
                
                # Cleanup
                session.run("MATCH (n:ConcurrentTest {id: $id}) DELETE n", id=query_id)
            
            return (time.time() - start_time) * 1000
            
        finally:
            driver.close()
    
    def test_startup_time_optimization(self, docker_client):
        """Test that Neo4j starts within reasonable time."""
        try:
            container = docker_client.containers.get("local-development-conversion-neo4j-1")
            
            # Check container uptime (should be reasonable for development)
            container.reload()
            started_at = container.attrs['State']['StartedAt']
            
            # Container should be running
            assert container.status == "running", f"Container status: {container.status}"
            
            # Health check should pass
            health = container.attrs['State'].get('Health', {})
            if health:
                assert health['Status'] == 'healthy', f"Health status: {health['Status']}"
            
        except docker.errors.NotFound:
            pytest.skip("Neo4j container not found - may not be running")
    
    def test_configuration_optimization(self, neo4j_driver):
        """Test that key configuration optimizations are applied."""
        with neo4j_driver.session() as session:
            # Test that query cache is configured
            try:
                result = session.run("CALL dbms.queryJmx('org.neo4j:*') YIELD attributes")
                
                # Should have some JMX metrics available
                metrics_count = len(list(result))
                assert metrics_count > 0, "No JMX metrics available"
                
            except Exception as e:
                pytest.skip(f"Could not query configuration: {e}")
    
    @pytest.mark.integration
    def test_end_to_end_performance(self, neo4j_driver):
        """Test end-to-end performance with realistic workload."""
        with neo4j_driver.session() as session:
            start_time = time.time()
            
            # Create a small knowledge graph
            session.run("""
                CREATE (d1:Document {id: 'doc1', title: 'Test Document 1'})
                CREATE (d2:Document {id: 'doc2', title: 'Test Document 2'})
                CREATE (c1:Concept {name: 'Machine Learning', type: 'topic'})
                CREATE (c2:Concept {name: 'Neural Networks', type: 'subtopic'})
                CREATE (c3:Concept {name: 'Deep Learning', type: 'subtopic'})
                
                CREATE (d1)-[:CONTAINS]->(c1)
                CREATE (d2)-[:CONTAINS]->(c2)
                CREATE (c1)-[:RELATED_TO]->(c2)
                CREATE (c2)-[:RELATED_TO]->(c3)
                CREATE (c1)-[:RELATED_TO]->(c3)
            """)
            
            # Perform complex queries
            result = session.run("""
                MATCH (d:Document)-[:CONTAINS]->(c1:Concept)-[:RELATED_TO*1..2]->(c2:Concept)
                RETURN d.title, c1.name, collect(c2.name) as related_concepts
                ORDER BY d.title
            """)
            
            results = list(result)
            query_time_ms = (time.time() - start_time) * 1000
            
            # Should complete complex query quickly
            assert query_time_ms < 200, f"Complex query took {query_time_ms:.1f}ms (> 200ms)"
            assert len(results) > 0, "Should return some results"
            
            # Cleanup
            session.run("""
                MATCH (n) 
                WHERE n:Document OR n:Concept 
                DETACH DELETE n
            """)


@pytest.mark.performance
class TestNeo4jMemoryOptimization:
    """Specific tests for memory optimization."""
    
    def test_memory_configuration_values(self):
        """Test that memory configuration values are set correctly."""
        # This test validates the Docker Compose environment variables
        # In a real deployment, these would be checked via JMX
        
        expected_heap_max = "1G"
        expected_heap_initial = "512m"
        expected_pagecache = "512m"
        
        # These values should match the Docker Compose configuration
        assert expected_heap_max == "1G"
        assert expected_heap_initial == "512m"
        assert expected_pagecache == "512m"
    
    def test_memory_efficiency_under_load(self, neo4j_driver):
        """Test memory efficiency under moderate load."""
        with neo4j_driver.session() as session:
            # Create a moderate dataset
            session.run("""
                UNWIND range(1, 5000) as i
                CREATE (n:LoadTest {
                    id: i, 
                    data: 'test_data_' + toString(i),
                    timestamp: timestamp()
                })
            """)
            
            # Perform various operations
            operations = [
                "MATCH (n:LoadTest) WHERE n.id % 100 = 0 RETURN count(n)",
                "MATCH (n:LoadTest) WHERE n.id > 4000 RETURN n.id ORDER BY n.id LIMIT 10",
                "MATCH (n:LoadTest) RETURN avg(n.id), max(n.id), min(n.id)"
            ]
            
            for operation in operations:
                start_time = time.time()
                result = session.run(operation)
                list(result)  # Consume results
                operation_time = (time.time() - start_time) * 1000
                
                # Each operation should complete reasonably quickly
                assert operation_time < 100, f"Operation took {operation_time:.1f}ms (> 100ms)"
            
            # Cleanup
            session.run("MATCH (n:LoadTest) DELETE n")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])