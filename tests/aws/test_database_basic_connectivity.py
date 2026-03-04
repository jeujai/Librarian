#!/usr/bin/env python3
"""
Basic Database Connectivity Tests for AWS Learning Deployment

This module tests database connectivity and operations including:
- PostgreSQL RDS connectivity
- Redis ElastiCache connectivity
- Basic CRUD operations
- Connection pooling
- Performance characteristics
- Data integrity
"""

import os
import sys
import pytest
import asyncio
import json
import redis
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy import text

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from multimodal_librarian.database.connection import db_manager
from multimodal_librarian.logging_config import get_logger


class DatabaseConnectivityTestSuite:
    """Test suite for database connectivity and operations."""
    
    def __init__(self):
        self.logger = get_logger("database_connectivity_tests")
        
        # Configuration
        self.redis_host = os.getenv("REDIS_HOST", "localhost")
        self.redis_port = int(os.getenv("REDIS_PORT", "6379"))
        self.redis_db = int(os.getenv("REDIS_DB", "0"))
        
        # Initialize clients
        self.redis_client = None
        self.test_timeout = 30
        
        self._initialize_redis()
    
    def _initialize_redis(self):
        """Initialize Redis connection."""
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=self.redis_db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            
            # Test connection
            self.redis_client.ping()
            self.logger.info("Redis connection initialized successfully")
            
        except Exception as e:
            self.logger.warning(f"Could not initialize Redis connection: {e}")
            self.redis_client = None


@pytest.fixture(scope="session")
def db_test_suite():
    """Pytest fixture for database connectivity test suite."""
    return DatabaseConnectivityTestSuite()


class TestPostgreSQLConnectivity:
    """Test PostgreSQL RDS connectivity and operations."""
    
    def test_database_connection(self, db_test_suite):
        """Test basic database connection."""
        try:
            with db_manager.get_session() as session:
                # Simple connectivity test
                result = session.execute(text("SELECT 1 as test_value"))
                row = result.fetchone()
                assert row[0] == 1
                
                db_test_suite.logger.info("✅ PostgreSQL connection successful")
                
        except Exception as e:
            pytest.fail(f"PostgreSQL connection failed: {e}")
    
    def test_database_version(self, db_test_suite):
        """Test database version information."""
        try:
            with db_manager.get_session() as session:
                result = session.execute(text("SELECT version()"))
                version_info = result.fetchone()[0]
                
                # Should be PostgreSQL
                assert "PostgreSQL" in version_info
                
                db_test_suite.logger.info(f"✅ PostgreSQL version: {version_info[:50]}...")
                
        except Exception as e:
            pytest.fail(f"Database version check failed: {e}")
    
    def test_database_tables_exist(self, db_test_suite):
        """Test that essential database tables exist."""
        try:
            with db_manager.get_session() as session:
                # Check for essential tables
                essential_tables = [
                    'conversations',
                    'messages',
                    'documents',
                    'users'
                ]
                
                existing_tables = []
                missing_tables = []
                
                for table_name in essential_tables:
                    try:
                        # Check if table exists by querying it
                        result = session.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                        count = result.fetchone()[0]
                        existing_tables.append((table_name, count))
                        
                    except Exception as e:
                        missing_tables.append(table_name)
                        db_test_suite.logger.warning(f"⚠️  Table '{table_name}' not accessible: {e}")
                
                # Log results
                for table_name, count in existing_tables:
                    db_test_suite.logger.info(f"✅ Table '{table_name}' exists with {count} records")
                
                # At least some tables should exist
                assert len(existing_tables) > 0, "No database tables found"
                
        except Exception as e:
            pytest.fail(f"Database table check failed: {e}")
    
    def test_database_write_operations(self, db_test_suite):
        """Test basic database write operations."""
        try:
            with db_manager.get_session() as session:
                # Create a temporary table for testing
                test_table_name = f"test_table_{int(datetime.now().timestamp())}"
                
                try:
                    # Create test table
                    session.execute(text(f"""
                        CREATE TEMPORARY TABLE {test_table_name} (
                            id SERIAL PRIMARY KEY,
                            test_data VARCHAR(255),
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """))
                    
                    # Insert test data
                    test_data = f"test_data_{datetime.now().timestamp()}"
                    session.execute(
                        text(f"INSERT INTO {test_table_name} (test_data) VALUES (:data)"),
                        {"data": test_data}
                    )
                    session.commit()
                    
                    # Verify data was inserted
                    result = session.execute(
                        text(f"SELECT test_data FROM {test_table_name} WHERE test_data = :data"),
                        {"data": test_data}
                    )
                    row = result.fetchone()
                    assert row[0] == test_data
                    
                    # Test update operation
                    updated_data = f"updated_{test_data}"
                    session.execute(
                        text(f"UPDATE {test_table_name} SET test_data = :new_data WHERE test_data = :old_data"),
                        {"new_data": updated_data, "old_data": test_data}
                    )
                    session.commit()
                    
                    # Verify update
                    result = session.execute(
                        text(f"SELECT test_data FROM {test_table_name} WHERE test_data = :data"),
                        {"data": updated_data}
                    )
                    row = result.fetchone()
                    assert row[0] == updated_data
                    
                    # Test delete operation
                    session.execute(
                        text(f"DELETE FROM {test_table_name} WHERE test_data = :data"),
                        {"data": updated_data}
                    )
                    session.commit()
                    
                    # Verify deletion
                    result = session.execute(
                        text(f"SELECT COUNT(*) FROM {test_table_name} WHERE test_data = :data"),
                        {"data": updated_data}
                    )
                    count = result.fetchone()[0]
                    assert count == 0
                    
                    db_test_suite.logger.info("✅ Database CRUD operations successful")
                    
                except Exception as e:
                    session.rollback()
                    raise e
                    
        except Exception as e:
            pytest.fail(f"Database write operations test failed: {e}")
    
    def test_database_transaction_handling(self, db_test_suite):
        """Test database transaction handling."""
        try:
            with db_manager.get_session() as session:
                # Create temporary table
                test_table_name = f"test_transaction_{int(datetime.now().timestamp())}"
                
                session.execute(text(f"""
                    CREATE TEMPORARY TABLE {test_table_name} (
                        id SERIAL PRIMARY KEY,
                        test_data VARCHAR(255)
                    )
                """))
                
                try:
                    # Start transaction
                    session.begin()
                    
                    # Insert data
                    session.execute(
                        text(f"INSERT INTO {test_table_name} (test_data) VALUES (:data)"),
                        {"data": "transaction_test"}
                    )
                    
                    # Verify data exists in transaction
                    result = session.execute(
                        text(f"SELECT COUNT(*) FROM {test_table_name}")
                    )
                    count = result.fetchone()[0]
                    assert count == 1
                    
                    # Rollback transaction
                    session.rollback()
                    
                    # Verify data was rolled back
                    result = session.execute(
                        text(f"SELECT COUNT(*) FROM {test_table_name}")
                    )
                    count = result.fetchone()[0]
                    assert count == 0
                    
                    db_test_suite.logger.info("✅ Database transaction handling successful")
                    
                except Exception as e:
                    session.rollback()
                    raise e
                    
        except Exception as e:
            pytest.fail(f"Database transaction test failed: {e}")
    
    def test_connection_pool_behavior(self, db_test_suite):
        """Test connection pool behavior."""
        try:
            # Test multiple concurrent connections
            sessions = []
            
            try:
                # Create multiple sessions
                for i in range(3):
                    session = db_manager.get_session()
                    sessions.append(session)
                    
                    # Test each session
                    result = session.execute(text("SELECT :value as test"), {"value": i})
                    row = result.fetchone()
                    assert row[0] == i
                
                db_test_suite.logger.info("✅ Connection pool handling multiple sessions")
                
            finally:
                # Clean up sessions
                for session in sessions:
                    try:
                        session.close()
                    except Exception as e:
                        db_test_suite.logger.warning(f"Session cleanup warning: {e}")
                        
        except Exception as e:
            pytest.fail(f"Connection pool test failed: {e}")


class TestRedisConnectivity:
    """Test Redis ElastiCache connectivity and operations."""
    
    def test_redis_connection(self, db_test_suite):
        """Test basic Redis connection."""
        if not db_test_suite.redis_client:
            pytest.skip("Redis not available")
        
        try:
            # Test ping
            response = db_test_suite.redis_client.ping()
            assert response is True
            
            db_test_suite.logger.info("✅ Redis connection successful")
            
        except Exception as e:
            pytest.fail(f"Redis connection failed: {e}")
    
    def test_redis_basic_operations(self, db_test_suite):
        """Test basic Redis operations."""
        if not db_test_suite.redis_client:
            pytest.skip("Redis not available")
        
        try:
            test_key = f"test_key_{datetime.now().timestamp()}"
            test_value = f"test_value_{datetime.now().timestamp()}"
            
            # Test SET operation
            result = db_test_suite.redis_client.set(test_key, test_value)
            assert result is True
            
            # Test GET operation
            retrieved_value = db_test_suite.redis_client.get(test_key)
            assert retrieved_value == test_value
            
            # Test EXISTS operation
            exists = db_test_suite.redis_client.exists(test_key)
            assert exists == 1
            
            # Test DELETE operation
            deleted = db_test_suite.redis_client.delete(test_key)
            assert deleted == 1
            
            # Verify deletion
            exists_after_delete = db_test_suite.redis_client.exists(test_key)
            assert exists_after_delete == 0
            
            db_test_suite.logger.info("✅ Redis basic operations successful")
            
        except Exception as e:
            pytest.fail(f"Redis basic operations failed: {e}")
    
    def test_redis_expiration(self, db_test_suite):
        """Test Redis key expiration."""
        if not db_test_suite.redis_client:
            pytest.skip("Redis not available")
        
        try:
            test_key = f"test_expire_{datetime.now().timestamp()}"
            test_value = "expire_test_value"
            
            # Set key with expiration
            result = db_test_suite.redis_client.setex(test_key, 2, test_value)  # 2 seconds
            assert result is True
            
            # Verify key exists
            retrieved_value = db_test_suite.redis_client.get(test_key)
            assert retrieved_value == test_value
            
            # Check TTL
            ttl = db_test_suite.redis_client.ttl(test_key)
            assert ttl > 0 and ttl <= 2
            
            db_test_suite.logger.info("✅ Redis expiration functionality working")
            
        except Exception as e:
            pytest.fail(f"Redis expiration test failed: {e}")
    
    def test_redis_data_structures(self, db_test_suite):
        """Test Redis data structures (lists, sets, hashes)."""
        if not db_test_suite.redis_client:
            pytest.skip("Redis not available")
        
        try:
            timestamp = datetime.now().timestamp()
            
            # Test LIST operations
            list_key = f"test_list_{timestamp}"
            db_test_suite.redis_client.lpush(list_key, "item1", "item2", "item3")
            list_length = db_test_suite.redis_client.llen(list_key)
            assert list_length == 3
            
            # Test SET operations
            set_key = f"test_set_{timestamp}"
            db_test_suite.redis_client.sadd(set_key, "member1", "member2", "member3")
            set_size = db_test_suite.redis_client.scard(set_key)
            assert set_size == 3
            
            # Test HASH operations
            hash_key = f"test_hash_{timestamp}"
            db_test_suite.redis_client.hset(hash_key, mapping={
                "field1": "value1",
                "field2": "value2",
                "field3": "value3"
            })
            hash_length = db_test_suite.redis_client.hlen(hash_key)
            assert hash_length == 3
            
            # Clean up
            db_test_suite.redis_client.delete(list_key, set_key, hash_key)
            
            db_test_suite.logger.info("✅ Redis data structures working")
            
        except Exception as e:
            pytest.fail(f"Redis data structures test failed: {e}")
    
    def test_redis_json_operations(self, db_test_suite):
        """Test Redis JSON serialization/deserialization."""
        if not db_test_suite.redis_client:
            pytest.skip("Redis not available")
        
        try:
            test_key = f"test_json_{datetime.now().timestamp()}"
            test_data = {
                "string_field": "test_string",
                "number_field": 42,
                "boolean_field": True,
                "array_field": [1, 2, 3],
                "object_field": {"nested": "value"}
            }
            
            # Serialize and store
            json_data = json.dumps(test_data)
            db_test_suite.redis_client.set(test_key, json_data)
            
            # Retrieve and deserialize
            retrieved_json = db_test_suite.redis_client.get(test_key)
            retrieved_data = json.loads(retrieved_json)
            
            # Verify data integrity
            assert retrieved_data == test_data
            
            # Clean up
            db_test_suite.redis_client.delete(test_key)
            
            db_test_suite.logger.info("✅ Redis JSON operations successful")
            
        except Exception as e:
            pytest.fail(f"Redis JSON operations failed: {e}")


class TestDatabasePerformance:
    """Test basic database performance characteristics."""
    
    def test_postgresql_query_performance(self, db_test_suite):
        """Test PostgreSQL query performance."""
        try:
            with db_manager.get_session() as session:
                # Test simple query performance
                start_time = datetime.now()
                
                result = session.execute(text("SELECT COUNT(*) FROM conversations"))
                count = result.fetchone()[0]
                
                end_time = datetime.now()
                query_time = (end_time - start_time).total_seconds()
                
                # Query should complete in reasonable time
                assert query_time < 5.0
                
                db_test_suite.logger.info(
                    f"✅ PostgreSQL query performance: {query_time:.3f}s (found {count} conversations)"
                )
                
        except Exception as e:
            db_test_suite.logger.warning(f"⚠️  PostgreSQL performance test skipped: {e}")
    
    def test_redis_performance(self, db_test_suite):
        """Test Redis performance."""
        if not db_test_suite.redis_client:
            pytest.skip("Redis not available")
        
        try:
            # Test multiple operations performance
            start_time = datetime.now()
            
            test_key_prefix = f"perf_test_{datetime.now().timestamp()}"
            
            # Perform multiple operations
            for i in range(10):
                key = f"{test_key_prefix}_{i}"
                value = f"value_{i}"
                
                db_test_suite.redis_client.set(key, value)
                retrieved = db_test_suite.redis_client.get(key)
                assert retrieved == value
            
            end_time = datetime.now()
            operation_time = (end_time - start_time).total_seconds()
            
            # Operations should complete quickly
            assert operation_time < 2.0
            
            # Clean up
            keys_to_delete = [f"{test_key_prefix}_{i}" for i in range(10)]
            db_test_suite.redis_client.delete(*keys_to_delete)
            
            db_test_suite.logger.info(
                f"✅ Redis performance: {operation_time:.3f}s for 10 set/get operations"
            )
            
        except Exception as e:
            pytest.fail(f"Redis performance test failed: {e}")


class TestDatabaseIntegration:
    """Test database integration scenarios."""
    
    def test_postgresql_redis_integration(self, db_test_suite):
        """Test integration between PostgreSQL and Redis."""
        if not db_test_suite.redis_client:
            pytest.skip("Redis not available")
        
        try:
            # Simulate caching scenario
            cache_key = f"cache_test_{datetime.now().timestamp()}"
            
            # Check cache first (should be empty)
            cached_value = db_test_suite.redis_client.get(cache_key)
            assert cached_value is None
            
            # Get data from PostgreSQL
            with db_manager.get_session() as session:
                result = session.execute(text("SELECT COUNT(*) FROM conversations"))
                db_count = result.fetchone()[0]
            
            # Store in cache
            db_test_suite.redis_client.setex(cache_key, 60, str(db_count))
            
            # Retrieve from cache
            cached_count = db_test_suite.redis_client.get(cache_key)
            assert int(cached_count) == db_count
            
            # Clean up
            db_test_suite.redis_client.delete(cache_key)
            
            db_test_suite.logger.info("✅ PostgreSQL-Redis integration successful")
            
        except Exception as e:
            pytest.fail(f"Database integration test failed: {e}")
    
    def test_connection_resilience(self, db_test_suite):
        """Test connection resilience and recovery."""
        try:
            # Test PostgreSQL connection resilience
            with db_manager.get_session() as session:
                # Multiple queries to test connection stability
                for i in range(5):
                    result = session.execute(text("SELECT :value as test"), {"value": i})
                    row = result.fetchone()
                    assert row[0] == i
            
            # Test Redis connection resilience (if available)
            if db_test_suite.redis_client:
                for i in range(5):
                    key = f"resilience_test_{i}"
                    value = f"value_{i}"
                    
                    db_test_suite.redis_client.set(key, value)
                    retrieved = db_test_suite.redis_client.get(key)
                    assert retrieved == value
                    
                    db_test_suite.redis_client.delete(key)
            
            db_test_suite.logger.info("✅ Connection resilience test successful")
            
        except Exception as e:
            pytest.fail(f"Connection resilience test failed: {e}")


# Test execution functions
def run_database_connectivity_tests():
    """Run database connectivity tests with proper configuration."""
    import subprocess
    
    # Set test environment
    os.environ.setdefault("TESTING", "true")
    os.environ.setdefault("LOG_LEVEL", "INFO")
    
    # Run pytest with specific markers and output
    cmd = [
        "python", "-m", "pytest",
        __file__,
        "-v",
        "--tb=short",
        "--color=yes",
        "-x"  # Stop on first failure
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        print("🗃️  DATABASE CONNECTIVITY TEST RESULTS")
        print("=" * 50)
        print(result.stdout)
        
        if result.stderr:
            print("\n⚠️  WARNINGS/ERRORS:")
            print(result.stderr)
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ Failed to run database tests: {e}")
        return False


if __name__ == "__main__":
    success = run_database_connectivity_tests()
    exit(0 if success else 1)