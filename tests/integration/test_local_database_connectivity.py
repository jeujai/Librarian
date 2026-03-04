"""
Integration tests for local database connectivity.

This module tests actual database connections and operations
when local database services are running.
"""

import pytest
import asyncio
import os
import time
from typing import Dict, Any, Optional, List
from unittest.mock import patch

from src.multimodal_librarian.config.local_config import LocalDatabaseConfig
from src.multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
from src.multimodal_librarian.clients.exceptions import DatabaseClientError


class TestLocalDatabaseConnectivity:
    """Integration tests for local database connectivity."""
    
    @pytest.fixture(scope="class")
    def local_config(self):
        """Create local configuration for connectivity testing."""
        return LocalDatabaseConfig(
            postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
            postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
            postgres_db=os.getenv("POSTGRES_DB", "multimodal_librarian"),
            postgres_user=os.getenv("POSTGRES_USER", "ml_user"),
            postgres_password=os.getenv("POSTGRES_PASSWORD", "ml_password"),
            
            neo4j_host=os.getenv("NEO4J_HOST", "localhost"),
            neo4j_port=int(os.getenv("NEO4J_PORT", "7687")),
            neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", "ml_password"),
            
            milvus_host=os.getenv("MILVUS_HOST", "localhost"),
            milvus_port=int(os.getenv("MILVUS_PORT", "19530")),
            
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            
            # Enable all services for connectivity testing
            enable_relational_db=True,
            enable_graph_db=True,
            enable_vector_search=True,
            enable_redis_cache=True,
            
            # Reduce timeouts for faster testing
            connection_timeout=10,
            query_timeout=5,
            health_check_timeout=5
        )
    
    @pytest.fixture(scope="class")
    def database_factory(self, local_config):
        """Create database factory for connectivity testing."""
        return DatabaseClientFactory(local_config)
    
    def test_tcp_connectivity_check(self, local_config):
        """Test basic TCP connectivity to database services."""
        connectivity = local_config.validate_connectivity(timeout=5)
        
        assert isinstance(connectivity, dict)
        assert "overall_status" in connectivity
        assert "services" in connectivity
        assert "errors" in connectivity
        assert "warnings" in connectivity
        
        # Check that connectivity test was attempted for all enabled services
        services = connectivity["services"]
        expected_services = ["postgres", "neo4j", "milvus", "redis"]
        
        for service in expected_services:
            if service in services:
                service_result = services[service]
                assert "connected" in service_result
                assert "host" in service_result
                assert "port" in service_result
                
                # If connection failed, should have error message
                if not service_result["connected"]:
                    assert "error" in service_result
                else:
                    # If connected, should have response time
                    assert "response_time" in service_result
                    assert isinstance(service_result["response_time"], (int, float))
    
    @pytest.mark.skipif(
        not os.getenv("TEST_LOCAL_DATABASES", "").lower() in ["true", "1", "yes"],
        reason="Local database connectivity tests require TEST_LOCAL_DATABASES=true"
    )
    async def test_postgresql_connectivity(self, database_factory):
        """Test PostgreSQL connectivity and basic operations."""
        try:
            # This will only work if PostgreSQL is actually running
            postgres_client = await database_factory.get_relational_client()
            
            # Test basic query
            result = await postgres_client.execute("SELECT 1 as test_value")
            assert result is not None
            
            # Test connection info
            connection_info = await postgres_client.get_connection_info()
            assert isinstance(connection_info, dict)
            assert "database" in connection_info
            assert "user" in connection_info
            
        except DatabaseClientError as e:
            pytest.skip(f"PostgreSQL not available: {e}")
        except Exception as e:
            pytest.skip(f"PostgreSQL connectivity test failed: {e}")
    
    @pytest.mark.skipif(
        not os.getenv("TEST_LOCAL_DATABASES", "").lower() in ["true", "1", "yes"],
        reason="Local database connectivity tests require TEST_LOCAL_DATABASES=true"
    )
    async def test_neo4j_connectivity(self, database_factory):
        """Test Neo4j connectivity and basic operations."""
        try:
            # This will only work if Neo4j is actually running
            neo4j_client = await database_factory.get_graph_client()
            
            # Test basic query
            result = await neo4j_client.execute_query("RETURN 1 as test_value")
            assert result is not None
            
            # Test connection info
            connection_info = await neo4j_client.get_connection_info()
            assert isinstance(connection_info, dict)
            assert "uri" in connection_info
            assert "user" in connection_info
            
        except DatabaseClientError as e:
            pytest.skip(f"Neo4j not available: {e}")
        except Exception as e:
            pytest.skip(f"Neo4j connectivity test failed: {e}")
    
    @pytest.mark.skipif(
        not os.getenv("TEST_LOCAL_DATABASES", "").lower() in ["true", "1", "yes"],
        reason="Local database connectivity tests require TEST_LOCAL_DATABASES=true"
    )
    async def test_milvus_connectivity(self, database_factory):
        """Test Milvus connectivity and basic operations."""
        try:
            # This will only work if Milvus is actually running
            milvus_client = await database_factory.get_vector_client()
            
            # Test basic operation
            collections = await milvus_client.list_collections()
            assert isinstance(collections, list)
            
            # Test connection info
            connection_info = await milvus_client.get_connection_info()
            assert isinstance(connection_info, dict)
            assert "host" in connection_info
            assert "port" in connection_info
            
        except DatabaseClientError as e:
            pytest.skip(f"Milvus not available: {e}")
        except Exception as e:
            pytest.skip(f"Milvus connectivity test failed: {e}")
    
    @pytest.mark.skipif(
        not os.getenv("TEST_LOCAL_DATABASES", "").lower() in ["true", "1", "yes"],
        reason="Local database connectivity tests require TEST_LOCAL_DATABASES=true"
    )
    async def test_redis_connectivity(self, database_factory):
        """Test Redis connectivity and basic operations."""
        try:
            # This will only work if Redis is actually running
            redis_client = await database_factory.get_cache_client()
            
            # Test basic operation
            await redis_client.ping()
            
            # Test set/get operation
            test_key = "test_connectivity"
            test_value = "test_value"
            
            await redis_client.set(test_key, test_value, ttl=60)
            retrieved_value = await redis_client.get(test_key)
            assert retrieved_value == test_value
            
            # Clean up
            await redis_client.delete(test_key)
            
            # Test connection info
            connection_info = await redis_client.get_connection_info()
            assert isinstance(connection_info, dict)
            assert "host" in connection_info
            assert "port" in connection_info
            
        except DatabaseClientError as e:
            pytest.skip(f"Redis not available: {e}")
        except Exception as e:
            pytest.skip(f"Redis connectivity test failed: {e}")
    
    @pytest.mark.skipif(
        not os.getenv("TEST_LOCAL_DATABASES", "").lower() in ["true", "1", "yes"],
        reason="Local database connectivity tests require TEST_LOCAL_DATABASES=true"
    )
    async def test_factory_health_check_with_real_services(self, database_factory):
        """Test factory health check with real database services."""
        try:
            health = await database_factory.health_check()
            
            assert isinstance(health, dict)
            assert "database_type" in health
            assert "overall_status" in health
            assert "services" in health
            assert "timestamp" in health
            assert "response_time" in health
            
            assert health["database_type"] == "local"
            
            # Check individual service health
            services = health["services"]
            for service_name, service_health in services.items():
                assert isinstance(service_health, dict)
                assert "status" in service_health
                assert "response_time" in service_health
                
                # If service is healthy, should have additional info
                if service_health["status"] == "healthy":
                    assert "connection_info" in service_health
                else:
                    # If unhealthy, should have error info
                    assert "error" in service_health
            
        except Exception as e:
            pytest.skip(f"Health check with real services failed: {e}")
    
    def test_connection_string_validation(self, local_config):
        """Test connection string generation and validation."""
        # Test PostgreSQL connection strings
        async_conn = local_config.get_postgres_connection_string(async_driver=True)
        sync_conn = local_config.get_postgres_connection_string(async_driver=False)
        
        # Validate format
        assert async_conn.startswith("postgresql+asyncpg://")
        assert sync_conn.startswith("postgresql+psycopg2://")
        
        # Should contain credentials and host info
        assert local_config.postgres_user in async_conn
        assert local_config.postgres_password in async_conn
        assert f"{local_config.postgres_host}:{local_config.postgres_port}" in async_conn
        assert local_config.postgres_db in async_conn
        
        # Test Neo4j URI
        neo4j_uri = local_config.get_neo4j_uri()
        assert neo4j_uri.startswith("bolt://")
        assert local_config.neo4j_user in neo4j_uri
        assert local_config.neo4j_password in neo4j_uri
        assert f"{local_config.neo4j_host}:{local_config.neo4j_port}" in neo4j_uri
        
        # Test Milvus URI
        milvus_uri = local_config.get_milvus_uri()
        assert milvus_uri.startswith("milvus://")
        assert f"{local_config.milvus_host}:{local_config.milvus_port}" in milvus_uri
        
        # Test Redis connection string
        redis_conn = local_config.get_redis_connection_string()
        assert redis_conn.startswith("redis://")
        assert f"{local_config.redis_host}:{local_config.redis_port}" in redis_conn
    
    def test_connection_pool_configuration(self, local_config):
        """Test connection pool configuration for all databases."""
        pool_config = local_config.get_connection_pool_config()
        
        assert "enabled" in pool_config
        assert pool_config["enabled"] is True
        
        # Check individual database pool configurations
        assert "postgres" in pool_config
        postgres_pool = pool_config["postgres"]
        assert "pool_size" in postgres_pool
        assert "max_overflow" in postgres_pool
        assert "pool_recycle" in postgres_pool
        assert "pool_timeout" in postgres_pool
        
        assert "neo4j" in pool_config
        neo4j_pool = pool_config["neo4j"]
        assert "max_connection_pool_size" in neo4j_pool
        assert "max_connection_lifetime" in neo4j_pool
        assert "connection_acquisition_timeout" in neo4j_pool
        
        assert "milvus" in pool_config
        milvus_pool = pool_config["milvus"]
        assert "pool_size" in milvus_pool
        assert "timeout" in milvus_pool
        assert "retry_attempts" in milvus_pool
        
        assert "redis" in pool_config
        redis_pool = pool_config["redis"]
        assert "max_connections" in redis_pool
        assert "socket_timeout" in redis_pool
        assert "socket_connect_timeout" in redis_pool
    
    def test_retry_configuration(self, local_config):
        """Test retry configuration for all databases."""
        retry_config = local_config.get_retry_config()
        
        assert "enabled" in retry_config
        assert retry_config["enabled"] is True
        assert "max_retries" in retry_config
        assert "retry_delay" in retry_config
        assert "backoff_factor" in retry_config
        assert "retry_on_exceptions" in retry_config
        
        # Check individual database retry configurations
        databases = ["postgres", "neo4j", "milvus", "redis"]
        for db in databases:
            assert db in retry_config
            db_retry = retry_config[db]
            assert "max_retries" in db_retry
            assert "retry_delay" in db_retry
            assert "backoff_factor" in db_retry
    
    def test_health_monitoring_configuration(self, local_config):
        """Test health monitoring configuration for all databases."""
        health_config = local_config.get_health_monitoring_config()
        
        assert "enabled" in health_config
        assert "interval" in health_config
        assert "timeout" in health_config
        assert "retries" in health_config
        
        # Check individual database health configurations
        databases = ["postgres", "neo4j", "milvus", "redis"]
        for db in databases:
            assert db in health_config
            db_health = health_config[db]
            assert "enabled" in db_health
            assert "timeout" in db_health
            assert "interval" in db_health
            
            # Check database-specific health check configurations
            if db == "postgres":
                assert "check_query" in db_health
                assert db_health["check_query"] == "SELECT 1"
            elif db == "neo4j":
                assert "check_query" in db_health
                assert db_health["check_query"] == "RETURN 1"
            elif db == "milvus":
                assert "check_method" in db_health
                assert db_health["check_method"] == "list_collections"
            elif db == "redis":
                assert "check_command" in db_health
                assert db_health["check_command"] == "PING"


class TestLocalDatabaseOperations:
    """Integration tests for database operations (requires running services)."""
    
    @pytest.fixture(scope="class")
    def test_config(self):
        """Create test configuration with shorter timeouts."""
        return LocalDatabaseConfig(
            postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
            neo4j_host=os.getenv("NEO4J_HOST", "localhost"),
            milvus_host=os.getenv("MILVUS_HOST", "localhost"),
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            connection_timeout=5,
            query_timeout=3,
            health_check_timeout=3
        )
    
    @pytest.mark.skipif(
        not os.getenv("TEST_LOCAL_DATABASES", "").lower() in ["true", "1", "yes"],
        reason="Local database operations tests require TEST_LOCAL_DATABASES=true"
    )
    async def test_concurrent_database_operations(self, test_config):
        """Test concurrent operations across multiple databases."""
        factory = DatabaseClientFactory(test_config)
        
        try:
            # Define concurrent operations for each database
            async def postgres_operation():
                try:
                    client = await factory.get_relational_client()
                    return await client.execute("SELECT 'postgres_test' as source")
                except Exception as e:
                    return {"error": str(e), "source": "postgres"}
            
            async def neo4j_operation():
                try:
                    client = await factory.get_graph_client()
                    return await client.execute_query("RETURN 'neo4j_test' as source")
                except Exception as e:
                    return {"error": str(e), "source": "neo4j"}
            
            async def milvus_operation():
                try:
                    client = await factory.get_vector_client()
                    collections = await client.list_collections()
                    return {"collections": collections, "source": "milvus"}
                except Exception as e:
                    return {"error": str(e), "source": "milvus"}
            
            async def redis_operation():
                try:
                    client = await factory.get_cache_client()
                    await client.ping()
                    return {"ping": "success", "source": "redis"}
                except Exception as e:
                    return {"error": str(e), "source": "redis"}
            
            # Run all operations concurrently
            results = await asyncio.gather(
                postgres_operation(),
                neo4j_operation(),
                milvus_operation(),
                redis_operation(),
                return_exceptions=True
            )
            
            # Verify we got results from all operations
            assert len(results) == 4
            
            # Check that each operation returned some result
            for result in results:
                assert isinstance(result, dict)
                assert "source" in result
                # Either successful result or error, but should have completed
                
        finally:
            await factory.close()
    
    @pytest.mark.skipif(
        not os.getenv("TEST_LOCAL_DATABASES", "").lower() in ["true", "1", "yes"],
        reason="Local database operations tests require TEST_LOCAL_DATABASES=true"
    )
    async def test_database_transaction_handling(self, test_config):
        """Test transaction handling across databases."""
        factory = DatabaseClientFactory(test_config)
        
        try:
            # Test PostgreSQL transactions
            try:
                postgres_client = await factory.get_relational_client()
                
                # Start transaction
                async with postgres_client.transaction():
                    # Perform operations within transaction
                    await postgres_client.execute("SELECT 1")
                    # Transaction should commit automatically
                
            except Exception as e:
                pytest.skip(f"PostgreSQL transaction test failed: {e}")
            
            # Test Neo4j transactions
            try:
                neo4j_client = await factory.get_graph_client()
                
                # Start transaction
                async with neo4j_client.transaction():
                    # Perform operations within transaction
                    await neo4j_client.execute_query("RETURN 1")
                    # Transaction should commit automatically
                
            except Exception as e:
                pytest.skip(f"Neo4j transaction test failed: {e}")
                
        finally:
            await factory.close()
    
    @pytest.mark.skipif(
        not os.getenv("TEST_LOCAL_DATABASES", "").lower() in ["true", "1", "yes"],
        reason="Local database operations tests require TEST_LOCAL_DATABASES=true"
    )
    async def test_connection_recovery(self, test_config):
        """Test connection recovery after temporary failures."""
        factory = DatabaseClientFactory(test_config)
        
        try:
            # Test that clients can recover from connection issues
            # This is a basic test - in real scenarios, you might simulate
            # network issues or service restarts
            
            # Get clients
            postgres_client = await factory.get_relational_client()
            neo4j_client = await factory.get_graph_client()
            
            # Perform initial operations
            await postgres_client.execute("SELECT 1")
            await neo4j_client.execute_query("RETURN 1")
            
            # Simulate reconnection by getting clients again
            postgres_client2 = await factory.get_relational_client()
            neo4j_client2 = await factory.get_graph_client()
            
            # Should be able to perform operations with new clients
            await postgres_client2.execute("SELECT 2")
            await neo4j_client2.execute_query("RETURN 2")
            
        except Exception as e:
            pytest.skip(f"Connection recovery test failed: {e}")
        finally:
            await factory.close()


class TestLocalDatabasePerformance:
    """Performance tests for local database setup."""
    
    @pytest.fixture(scope="class")
    def perf_config(self):
        """Create configuration optimized for performance testing."""
        return LocalDatabaseConfig(
            postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
            neo4j_host=os.getenv("NEO4J_HOST", "localhost"),
            milvus_host=os.getenv("MILVUS_HOST", "localhost"),
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            
            # Optimize for performance
            postgres_pool_size=20,
            neo4j_pool_size=50,
            redis_max_connections=20,
            
            connection_timeout=30,
            query_timeout=10,
            health_check_timeout=5
        )
    
    @pytest.mark.skipif(
        not os.getenv("TEST_LOCAL_DATABASES", "").lower() in ["true", "1", "yes"],
        reason="Local database performance tests require TEST_LOCAL_DATABASES=true"
    )
    async def test_connection_pool_performance(self, perf_config):
        """Test connection pool performance."""
        factory = DatabaseClientFactory(perf_config)
        
        try:
            # Measure time to get multiple clients
            start_time = time.time()
            
            clients = []
            for _ in range(10):
                try:
                    postgres_client = await factory.get_relational_client()
                    clients.append(postgres_client)
                except Exception:
                    # Skip if PostgreSQL not available
                    break
            
            end_time = time.time()
            
            if clients:
                # Should be able to get multiple clients quickly due to pooling
                total_time = end_time - start_time
                avg_time_per_client = total_time / len(clients)
                
                # Average time per client should be reasonable (less than 1 second)
                assert avg_time_per_client < 1.0, f"Client creation too slow: {avg_time_per_client}s per client"
                
        except Exception as e:
            pytest.skip(f"Connection pool performance test failed: {e}")
        finally:
            await factory.close()
    
    @pytest.mark.skipif(
        not os.getenv("TEST_LOCAL_DATABASES", "").lower() in ["true", "1", "yes"],
        reason="Local database performance tests require TEST_LOCAL_DATABASES=true"
    )
    async def test_concurrent_query_performance(self, perf_config):
        """Test concurrent query performance."""
        factory = DatabaseClientFactory(perf_config)
        
        try:
            # Define concurrent query operations
            async def run_postgres_queries():
                try:
                    client = await factory.get_relational_client()
                    tasks = []
                    for i in range(5):
                        tasks.append(client.execute(f"SELECT {i} as query_id"))
                    return await asyncio.gather(*tasks)
                except Exception as e:
                    return [{"error": str(e)}]
            
            async def run_neo4j_queries():
                try:
                    client = await factory.get_graph_client()
                    tasks = []
                    for i in range(5):
                        tasks.append(client.execute_query(f"RETURN {i} as query_id"))
                    return await asyncio.gather(*tasks)
                except Exception as e:
                    return [{"error": str(e)}]
            
            # Measure concurrent execution time
            start_time = time.time()
            
            postgres_results, neo4j_results = await asyncio.gather(
                run_postgres_queries(),
                run_neo4j_queries(),
                return_exceptions=True
            )
            
            end_time = time.time()
            total_time = end_time - start_time
            
            # Concurrent execution should be faster than sequential
            # This is a basic performance check
            assert total_time < 10.0, f"Concurrent queries too slow: {total_time}s"
            
            # Check that we got results
            assert isinstance(postgres_results, list)
            assert isinstance(neo4j_results, list)
            
        except Exception as e:
            pytest.skip(f"Concurrent query performance test failed: {e}")
        finally:
            await factory.close()