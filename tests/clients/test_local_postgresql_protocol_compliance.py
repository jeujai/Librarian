"""
Protocol compliance tests for LocalPostgreSQLClient.

This module tests that LocalPostgreSQLClient properly implements the
RelationalStoreClient protocol, ensuring all required methods are present
with correct signatures and behavior.
"""

import pytest
import inspect
from typing import get_type_hints
from unittest.mock import Mock, AsyncMock, patch

from src.multimodal_librarian.clients.local_postgresql_client import LocalPostgreSQLClient
from src.multimodal_librarian.clients.protocols import RelationalStoreClient


class TestLocalPostgreSQLProtocolCompliance:
    """Test suite for protocol compliance."""
    
    @pytest.fixture
    def client(self):
        """Create a test client instance."""
        return LocalPostgreSQLClient()
    
    def test_implements_protocol(self, client):
        """Test that LocalPostgreSQLClient implements RelationalStoreClient protocol."""
        # Check that client is an instance of the protocol
        assert isinstance(client, RelationalStoreClient)
    
    def test_has_all_required_methods(self, client):
        """Test that all protocol methods are implemented."""
        protocol_methods = [
            # Connection Management
            "connect",
            "disconnect", 
            "health_check",
            
            # Session Management
            "get_async_session",
            "get_session",
            
            # Query Execution
            "execute_query",
            "execute_command",
            
            # Transaction Management
            "transaction",
            
            # Schema Management
            "create_tables",
            "drop_tables",
            "migrate_schema",
            
            # Connection Pool Management
            "get_pool_status",
            "reset_pool",
            
            # Backup and Restore
            "backup_database",
            "restore_database",
            
            # Database Information
            "get_database_info",
            "get_table_info",
            
            # Performance and Monitoring
            "get_performance_stats",
            "analyze_table"
        ]
        
        for method_name in protocol_methods:
            assert hasattr(client, method_name), f"Missing method: {method_name}"
            method = getattr(client, method_name)
            assert callable(method), f"Method {method_name} is not callable"
    
    def test_method_signatures(self, client):
        """Test that method signatures match the protocol."""
        # Test async methods
        async_methods = [
            "connect",
            "disconnect",
            "health_check",
            "execute_query", 
            "execute_command",
            "create_tables",
            "drop_tables",
            "migrate_schema",
            "reset_pool",
            "backup_database",
            "restore_database",
            "get_database_info",
            "get_table_info",
            "get_performance_stats",
            "analyze_table"
        ]
        
        for method_name in async_methods:
            method = getattr(client, method_name)
            assert inspect.iscoroutinefunction(method), f"Method {method_name} should be async"
    
    def test_context_manager_methods(self, client):
        """Test that context manager methods are properly implemented."""
        # Test async context manager
        get_async_session = getattr(client, "get_async_session")
        assert hasattr(get_async_session, "__aenter__"), "get_async_session should be async context manager"
        assert hasattr(get_async_session, "__aexit__"), "get_async_session should be async context manager"
        
        # Test sync context manager
        get_session = getattr(client, "get_session")
        assert hasattr(get_session, "__enter__"), "get_session should be context manager"
        assert hasattr(get_session, "__exit__"), "get_session should be context manager"
        
        # Test transaction context manager
        transaction = getattr(client, "transaction")
        assert hasattr(transaction, "__aenter__"), "transaction should be async context manager"
        assert hasattr(transaction, "__aexit__"), "transaction should be async context manager"
    
    @pytest.mark.asyncio
    async def test_connect_method_behavior(self, client):
        """Test connect method behavior matches protocol."""
        with patch("asyncpg.create_pool") as mock_create_pool, \
             patch("sqlalchemy.create_engine") as mock_create_engine, \
             patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_create_async_engine, \
             patch("sqlalchemy.orm.sessionmaker") as mock_sessionmaker, \
             patch("sqlalchemy.ext.asyncio.async_sessionmaker") as mock_async_sessionmaker:
            
            # Mock successful connection
            mock_pool = AsyncMock()
            mock_connection = AsyncMock()
            mock_connection.fetchval.return_value = 1
            
            async def mock_acquire():
                return mock_connection
            
            mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_connection)
            mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_create_pool.return_value = mock_pool
            
            # Should not raise exception
            await client.connect()
            
            # Should be idempotent
            await client.connect()
    
    @pytest.mark.asyncio
    async def test_health_check_return_type(self, client):
        """Test health_check returns proper HealthStatus type."""
        with patch.object(client, "connection_pool", None):
            health = await client.health_check()
            
            # Should return dictionary with required keys
            assert isinstance(health, dict)
            assert "status" in health
            assert health["status"] in ["healthy", "unhealthy", "degraded"]
            assert "response_time" in health
            assert "last_check" in health
    
    @pytest.mark.asyncio
    async def test_execute_query_return_type(self, client):
        """Test execute_query returns proper SearchResults type."""
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.fetchall.return_value = [("John", "john@example.com")]
        mock_result.keys.return_value = ["name", "email"]
        mock_session.execute.return_value = mock_result
        
        async def mock_get_session():
            yield mock_session
        
        with patch.object(client, "get_async_session", mock_get_session):
            results = await client.execute_query("SELECT name, email FROM users")
            
            # Should return list of dictionaries
            assert isinstance(results, list)
            if results:
                assert isinstance(results[0], dict)
    
    @pytest.mark.asyncio
    async def test_execute_command_return_type(self, client):
        """Test execute_command returns integer."""
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.rowcount = 5
        mock_session.execute.return_value = mock_result
        
        async def mock_get_session():
            yield mock_session
        
        with patch.object(client, "get_async_session", mock_get_session):
            affected = await client.execute_command("UPDATE users SET active = true")
            
            # Should return integer
            assert isinstance(affected, int)
    
    def test_get_pool_status_return_type(self, client):
        """Test get_pool_status returns proper ConnectionPoolStats type."""
        stats = client.get_pool_status()
        
        # Should return dictionary with required keys
        assert isinstance(stats, dict)
        assert "size" in stats
        assert "checked_in" in stats
        assert "checked_out" in stats
        assert "overflow" in stats
        assert "invalid" in stats
        
        # All values should be integers
        for key, value in stats.items():
            assert isinstance(value, int), f"Pool stat {key} should be integer"
    
    @pytest.mark.asyncio
    async def test_backup_restore_return_type(self, client):
        """Test backup and restore methods return boolean."""
        with patch("subprocess.run") as mock_run:
            mock_result = Mock()
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            
            # Test backup
            backup_result = await client.backup_database("/tmp/test.sql")
            assert isinstance(backup_result, bool)
            
            # Test restore
            restore_result = await client.restore_database("/tmp/test.sql")
            assert isinstance(restore_result, bool)
    
    @pytest.mark.asyncio
    async def test_get_database_info_return_type(self, client):
        """Test get_database_info returns proper DatabaseMetadata type."""
        mock_pool = AsyncMock()
        mock_connection = AsyncMock()
        mock_connection.fetchval.side_effect = [
            "PostgreSQL 13.7",  # version
            1073741824,         # size
            25,                 # table_count
            10,                 # connection_count
            86400.0,            # uptime
            "UTF8"              # charset
        ]
        
        async def mock_acquire():
            return mock_connection
        
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_connection)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        
        client.connection_pool = mock_pool
        
        info = await client.get_database_info()
        
        # Should return dictionary with required keys
        assert isinstance(info, dict)
        assert "version" in info
        assert "size" in info
        assert "table_count" in info
        assert "connection_count" in info
        assert "uptime" in info
        assert "charset" in info
    
    @pytest.mark.asyncio
    async def test_get_table_info_return_type(self, client):
        """Test get_table_info returns proper DatabaseMetadata type."""
        mock_pool = AsyncMock()
        mock_connection = AsyncMock()
        
        # Mock table existence and info queries
        mock_connection.fetchval.side_effect = [
            True,     # table exists
            1000,     # row count
            8192,     # table size
            None      # last analyzed
        ]
        
        mock_connection.fetch.side_effect = [
            [{"column_name": "id", "data_type": "integer", "is_nullable": "NO", "column_default": None, "character_maximum_length": None}],  # columns
            [{"name": "users_pkey", "definition": "CREATE UNIQUE INDEX..."}]  # indexes
        ]
        
        async def mock_acquire():
            return mock_connection
        
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_connection)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        
        client.connection_pool = mock_pool
        
        info = await client.get_table_info("users")
        
        # Should return dictionary with required keys
        assert isinstance(info, dict)
        assert "name" in info
        assert "columns" in info
        assert "indexes" in info
        assert "row_count" in info
        assert "size" in info
        assert isinstance(info["columns"], list)
        assert isinstance(info["indexes"], list)
    
    @pytest.mark.asyncio
    async def test_get_performance_stats_return_type(self, client):
        """Test get_performance_stats returns proper PerformanceMetrics type."""
        mock_pool = AsyncMock()
        mock_connection = AsyncMock()
        
        mock_stats = {
            "active_connections": 10,
            "transactions_committed": 1000,
            "transactions_rolled_back": 50,
            "blocks_read": 5000,
            "blocks_hit": 45000,
            "tuples_returned": 100000,
            "tuples_fetched": 80000,
            "tuples_inserted": 5000,
            "tuples_updated": 3000,
            "tuples_deleted": 1000
        }
        
        mock_connection.fetchrow.return_value = mock_stats
        mock_connection.fetchval.side_effect = [5, 86400.0]  # slow queries, uptime
        
        async def mock_acquire():
            return mock_connection
        
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_connection)
        mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        
        client.connection_pool = mock_pool
        
        stats = await client.get_performance_stats()
        
        # Should return dictionary with required keys
        assert isinstance(stats, dict)
        assert "queries_per_second" in stats
        assert "avg_query_time" in stats
        assert "slow_queries" in stats
        assert "cache_hit_ratio" in stats
        assert "active_connections" in stats
        
        # Numeric values should be proper types
        assert isinstance(stats["queries_per_second"], (int, float))
        assert isinstance(stats["avg_query_time"], (int, float))
        assert isinstance(stats["slow_queries"], int)
        assert isinstance(stats["cache_hit_ratio"], (int, float))
        assert isinstance(stats["active_connections"], int)
    
    def test_error_handling_compliance(self, client):
        """Test that proper exceptions are raised for error conditions."""
        from src.multimodal_librarian.clients.exceptions import (
            DatabaseClientError, ConnectionError as DBConnectionError,
            QueryError, ValidationError, TransactionError, SchemaError
        )
        
        # All these exception types should be importable and inherit from appropriate base classes
        assert issubclass(DBConnectionError, DatabaseClientError)
        assert issubclass(QueryError, DatabaseClientError)
        assert issubclass(ValidationError, DatabaseClientError)
        assert issubclass(TransactionError, DatabaseClientError)
        assert issubclass(SchemaError, DatabaseClientError)
    
    @pytest.mark.asyncio
    async def test_parameter_validation(self, client):
        """Test that methods properly validate parameters."""
        # Test empty query validation
        with pytest.raises(Exception):  # Should raise ValidationError
            await client.execute_query("")
        
        # Test empty command validation
        with pytest.raises(Exception):  # Should raise ValidationError
            await client.execute_command("")
        
        # Test empty table name validation
        with pytest.raises(Exception):  # Should raise ValidationError
            await client.get_table_info("")
        
        # Test empty migration script validation
        with pytest.raises(Exception):  # Should raise ValidationError
            await client.migrate_schema("")
        
        # Test empty table name for analysis
        with pytest.raises(Exception):  # Should raise ValidationError
            await client.analyze_table("")
    
    @pytest.mark.asyncio
    async def test_connection_state_validation(self, client):
        """Test that methods properly check connection state."""
        # Methods that require connection should raise appropriate errors
        with pytest.raises(Exception):  # Should raise ConnectionError
            async with client.get_async_session():
                pass
        
        with pytest.raises(Exception):  # Should raise ConnectionError
            with client.get_session():
                pass
        
        with pytest.raises(Exception):  # Should raise ConnectionError
            async with client.transaction():
                pass
        
        with pytest.raises(Exception):  # Should raise ConnectionError
            await client.create_tables()
    
    def test_initialization_parameters(self):
        """Test that client accepts proper initialization parameters."""
        # Test with all parameters
        client = LocalPostgreSQLClient(
            host="test_host",
            port=5433,
            database="test_db",
            user="test_user",
            password="test_pass",
            pool_size=5,
            max_overflow=15,
            pool_timeout=60,
            pool_recycle=7200,
            echo=True
        )
        
        assert client.host == "test_host"
        assert client.port == 5433
        assert client.database == "test_db"
        assert client.user == "test_user"
        assert client.password == "test_pass"
        assert client.pool_size == 5
        assert client.max_overflow == 15
        assert client.pool_timeout == 60
        assert client.pool_recycle == 7200
        assert client.echo is True
    
    def test_connection_url_generation(self):
        """Test that connection URLs are properly generated."""
        client = LocalPostgreSQLClient(
            host="localhost",
            port=5432,
            database="testdb",
            user="testuser",
            password="testpass"
        )
        
        expected_sync_url = "postgresql://testuser:testpass@localhost:5432/testdb"
        expected_async_url = "postgresql+asyncpg://testuser:testpass@localhost:5432/testdb"
        
        assert client.sync_url == expected_sync_url
        assert client.async_url == expected_async_url
    
    def test_performance_tracking_initialization(self, client):
        """Test that performance tracking variables are properly initialized."""
        assert client._query_count == 0
        assert client._total_query_time == 0.0
        assert client._slow_query_count == 0
        assert client._connection_errors == 0
        assert client._last_health_check is None


if __name__ == "__main__":
    pytest.main([__file__])