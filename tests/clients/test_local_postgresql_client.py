"""
Unit tests for LocalPostgreSQLClient.

This module contains comprehensive tests for the LocalPostgreSQLClient
implementation, including connection management, query execution,
transaction handling, and error scenarios.

The tests use pytest fixtures and mocking to avoid requiring a real
PostgreSQL database during testing.
"""

import pytest
import asyncio
import subprocess
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone

try:
    import asyncpg
    import psycopg2
except ImportError:
    # Skip tests if dependencies are not available
    pytest.skip("PostgreSQL dependencies not available", allow_module_level=True)

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.multimodal_librarian.clients.local_postgresql_client import LocalPostgreSQLClient
from src.multimodal_librarian.clients.exceptions import (
    DatabaseClientError, ConnectionError as DBConnectionError,
    QueryError, ValidationError, TransactionError, SchemaError
)


class TestLocalPostgreSQLClient:
    """Test suite for LocalPostgreSQLClient."""
    
    @pytest.fixture
    def client_config(self):
        """Configuration for test client."""
        return {
            "host": "localhost",
            "port": 5432,
            "database": "test_db",
            "user": "test_user",
            "password": "test_password",
            "pool_size": 5,
            "max_overflow": 10
        }
    
    @pytest.fixture
    def client(self, client_config):
        """Create a test client instance."""
        return LocalPostgreSQLClient(**client_config)
    
    @pytest.fixture
    def mock_asyncpg_pool(self):
        """Mock asyncpg connection pool."""
        pool = AsyncMock()
        connection = AsyncMock()
        
        @asynccontextmanager
        async def mock_acquire():
            yield connection
        
        pool.acquire = mock_acquire
        pool.close = AsyncMock()
        connection.fetchval = AsyncMock()
        connection.fetch = AsyncMock()
        connection.execute = AsyncMock()
        
        return pool, connection
    
    @pytest.fixture
    def mock_sqlalchemy_engines(self):
        """Mock SQLAlchemy engines and sessions."""
        sync_engine = Mock()
        async_engine = AsyncMock()
        session_factory = Mock()
        async_session_factory = Mock()
        
        # Mock session
        session = Mock(spec=Session)
        session.commit = Mock()
        session.rollback = Mock()
        session.close = Mock()
        session.execute = Mock()
        
        # Mock async session
        async_session = AsyncMock(spec=AsyncSession)
        async_session.commit = AsyncMock()
        async_session.rollback = AsyncMock()
        async_session.execute = AsyncMock()
        
        session_factory.return_value = session
        async_session_factory.return_value = async_session
        
        return {
            "sync_engine": sync_engine,
            "async_engine": async_engine,
            "session_factory": session_factory,
            "async_session_factory": async_session_factory,
            "session": session,
            "async_session": async_session
        }
    
    def test_client_initialization(self, client_config):
        """Test client initialization with configuration."""
        client = LocalPostgreSQLClient(**client_config)
        
        assert client.host == client_config["host"]
        assert client.port == client_config["port"]
        assert client.database == client_config["database"]
        assert client.user == client_config["user"]
        assert client.password == client_config["password"]
        assert client.pool_size == client_config["pool_size"]
        assert client.max_overflow == client_config["max_overflow"]
        
        # Check connection URLs
        expected_sync_url = (
            f"postgresql://{client_config['user']}:{client_config['password']}"
            f"@{client_config['host']}:{client_config['port']}/{client_config['database']}"
        )
        expected_async_url = expected_sync_url.replace("postgresql://", "postgresql+asyncpg://")
        
        assert client.sync_url == expected_sync_url
        assert client.async_url == expected_async_url
        
        # Check initial state
        assert client.engine is None
        assert client.async_engine is None
        assert client.connection_pool is None
    
    def test_client_initialization_defaults(self):
        """Test client initialization with default values."""
        client = LocalPostgreSQLClient()
        
        assert client.host == "localhost"
        assert client.port == 5432
        assert client.database == "multimodal_librarian"
        assert client.user == "postgres"
        assert client.password == "postgres"
        assert client.pool_size == 10
        assert client.max_overflow == 20
    
    @pytest.mark.asyncio
    async def test_connect_success(self, client, mock_asyncpg_pool, mock_sqlalchemy_engines):
        """Test successful database connection."""
        pool, connection = mock_asyncpg_pool
        engines = mock_sqlalchemy_engines
        
        # Mock successful connection verification
        connection.fetchval.return_value = 1
        
        with patch("asyncpg.create_pool", return_value=pool), \
             patch("sqlalchemy.create_engine", return_value=engines["sync_engine"]), \
             patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=engines["async_engine"]), \
             patch("sqlalchemy.orm.sessionmaker", return_value=engines["session_factory"]), \
             patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=engines["async_session_factory"]):
            
            await client.connect()
            
            # Verify connection components are set
            assert client.engine is not None
            assert client.async_engine is not None
            assert client.connection_pool is not None
            assert client.session_factory is not None
            assert client.async_session_factory is not None
            
            # Verify connection verification was called
            connection.fetchval.assert_called_once_with("SELECT 1")
    
    @pytest.mark.asyncio
    async def test_connect_already_connected(self, client, mock_asyncpg_pool, mock_sqlalchemy_engines):
        """Test connecting when already connected (idempotent)."""
        pool, connection = mock_asyncpg_pool
        engines = mock_sqlalchemy_engines
        
        # Set up client as already connected
        client.engine = engines["sync_engine"]
        client.async_engine = engines["async_engine"]
        
        with patch("asyncpg.create_pool") as mock_create_pool:
            await client.connect()
            
            # Should not create new connections
            mock_create_pool.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_connect_failure(self, client):
        """Test connection failure handling."""
        with patch("asyncpg.create_pool", side_effect=Exception("Connection failed")):
            with pytest.raises(DBConnectionError) as exc_info:
                await client.connect()
            
            assert "Failed to connect to PostgreSQL" in str(exc_info.value)
            assert client.engine is None
            assert client.async_engine is None
            assert client.connection_pool is None
    
    @pytest.mark.asyncio
    async def test_disconnect_success(self, client, mock_asyncpg_pool, mock_sqlalchemy_engines):
        """Test successful disconnection."""
        pool, connection = mock_asyncpg_pool
        engines = mock_sqlalchemy_engines
        
        # Set up client as connected
        client.connection_pool = pool
        client.async_engine = engines["async_engine"]
        client.engine = engines["sync_engine"]
        client.session_factory = engines["session_factory"]
        client.async_session_factory = engines["async_session_factory"]
        
        await client.disconnect()
        
        # Verify cleanup
        pool.close.assert_called_once()
        engines["async_engine"].dispose.assert_called_once()
        engines["sync_engine"].dispose.assert_called_once()
        
        assert client.connection_pool is None
        assert client.async_engine is None
        assert client.engine is None
        assert client.session_factory is None
        assert client.async_session_factory is None
    
    @pytest.mark.asyncio
    async def test_disconnect_error(self, client, mock_asyncpg_pool):
        """Test disconnection error handling."""
        pool, connection = mock_asyncpg_pool
        pool.close.side_effect = Exception("Disconnect failed")
        
        client.connection_pool = pool
        
        with pytest.raises(DBConnectionError) as exc_info:
            await client.disconnect()
        
        assert "Failed to disconnect from PostgreSQL" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_health_check_healthy(self, client, mock_asyncpg_pool):
        """Test health check when database is healthy."""
        pool, connection = mock_asyncpg_pool
        connection.fetchval.return_value = 1
        
        client.connection_pool = pool
        client.engine = Mock()
        client.engine.pool = Mock()
        client.engine.pool.size.return_value = 10
        client.engine.pool.checkedin.return_value = 8
        client.engine.pool.checkedout.return_value = 2
        client.engine.pool.overflow.return_value = 0
        client.engine.pool.invalid.return_value = 0
        
        health = await client.health_check()
        
        assert health["status"] == "healthy"
        assert "response_time" in health
        assert health["connection_count"] == 2
        assert health["pool_size"] == 10
        assert "last_check" in health
        
        connection.fetchval.assert_called_once_with("SELECT 1")
    
    @pytest.mark.asyncio
    async def test_health_check_no_pool(self, client):
        """Test health check when no connection pool is available."""
        health = await client.health_check()
        
        assert health["status"] == "unhealthy"
        assert health["error"] == "No connection pool available"
        assert health["connection_count"] == 0
    
    @pytest.mark.asyncio
    async def test_health_check_query_failure(self, client, mock_asyncpg_pool):
        """Test health check when query fails."""
        pool, connection = mock_asyncpg_pool
        connection.fetchval.side_effect = Exception("Query failed")
        
        client.connection_pool = pool
        
        health = await client.health_check()
        
        assert health["status"] == "unhealthy"
        assert "Query failed" in health["error"]
    
    @pytest.mark.asyncio
    async def test_get_async_session_success(self, client, mock_sqlalchemy_engines):
        """Test getting async session successfully."""
        engines = mock_sqlalchemy_engines
        client.async_session_factory = engines["async_session_factory"]
        
        # Mock context manager behavior
        @asynccontextmanager
        async def mock_session_context():
            yield engines["async_session"]
        
        engines["async_session_factory"].return_value = mock_session_context()
        
        async with client.get_async_session() as session:
            assert session is not None
            # Session should be the mocked async session
    
    @pytest.mark.asyncio
    async def test_get_async_session_not_connected(self, client):
        """Test getting async session when not connected."""
        with pytest.raises(DBConnectionError) as exc_info:
            async with client.get_async_session():
                pass
        
        assert "Database not connected" in str(exc_info.value)
    
    def test_get_session_success(self, client, mock_sqlalchemy_engines):
        """Test getting synchronous session successfully."""
        engines = mock_sqlalchemy_engines
        client.session_factory = engines["session_factory"]
        
        with client.get_session() as session:
            assert session == engines["session"]
        
        # Verify session lifecycle
        engines["session"].commit.assert_called_once()
        engines["session"].close.assert_called_once()
    
    def test_get_session_not_connected(self, client):
        """Test getting session when not connected."""
        with pytest.raises(DBConnectionError) as exc_info:
            with client.get_session():
                pass
        
        assert "Database not connected" in str(exc_info.value)
    
    def test_get_session_error_handling(self, client, mock_sqlalchemy_engines):
        """Test session error handling with rollback."""
        engines = mock_sqlalchemy_engines
        client.session_factory = engines["session_factory"]
        
        with pytest.raises(Exception):
            with client.get_session() as session:
                raise Exception("Test error")
        
        # Verify rollback was called
        engines["session"].rollback.assert_called_once()
        engines["session"].close.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_query_success(self, client, mock_sqlalchemy_engines):
        """Test successful query execution."""
        engines = mock_sqlalchemy_engines
        client.async_session_factory = engines["async_session_factory"]
        
        # Mock query result
        mock_result = Mock()
        mock_result.fetchall.return_value = [("John", "john@example.com"), ("Jane", "jane@example.com")]
        mock_result.keys.return_value = ["name", "email"]
        
        engines["async_session"].execute.return_value = mock_result
        
        # Mock context manager
        @asynccontextmanager
        async def mock_session_context():
            yield engines["async_session"]
        
        with patch.object(client, "get_async_session", mock_session_context):
            results = await client.execute_query(
                "SELECT name, email FROM users WHERE active = :active",
                {"active": True}
            )
        
        assert len(results) == 2
        assert results[0] == {"name": "John", "email": "john@example.com"}
        assert results[1] == {"name": "Jane", "email": "jane@example.com"}
        
        # Verify query was executed with parameters
        engines["async_session"].execute.assert_called_once()
        call_args = engines["async_session"].execute.call_args
        assert "SELECT name, email FROM users WHERE active = :active" in str(call_args[0][0])
    
    @pytest.mark.asyncio
    async def test_execute_query_empty_query(self, client):
        """Test query execution with empty query."""
        with pytest.raises(ValidationError) as exc_info:
            await client.execute_query("")
        
        assert "Query cannot be empty" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_execute_query_sql_error(self, client, mock_sqlalchemy_engines):
        """Test query execution with SQL error."""
        engines = mock_sqlalchemy_engines
        client.async_session_factory = engines["async_session_factory"]
        
        engines["async_session"].execute.side_effect = SQLAlchemyError("SQL syntax error")
        
        @asynccontextmanager
        async def mock_session_context():
            yield engines["async_session"]
        
        with patch.object(client, "get_async_session", mock_session_context):
            with pytest.raises(QueryError) as exc_info:
                await client.execute_query("INVALID SQL")
        
        assert "Query execution failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_execute_command_success(self, client, mock_sqlalchemy_engines):
        """Test successful command execution."""
        engines = mock_sqlalchemy_engines
        client.async_session_factory = engines["async_session_factory"]
        
        # Mock command result
        mock_result = Mock()
        mock_result.rowcount = 3
        
        engines["async_session"].execute.return_value = mock_result
        
        @asynccontextmanager
        async def mock_session_context():
            yield engines["async_session"]
        
        with patch.object(client, "get_async_session", mock_session_context):
            affected_rows = await client.execute_command(
                "UPDATE users SET active = :active WHERE department = :dept",
                {"active": False, "dept": "sales"}
            )
        
        assert affected_rows == 3
        engines["async_session"].execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_command_empty_command(self, client):
        """Test command execution with empty command."""
        with pytest.raises(ValidationError) as exc_info:
            await client.execute_command("")
        
        assert "Command cannot be empty" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_transaction_success(self, client, mock_sqlalchemy_engines):
        """Test successful transaction execution."""
        engines = mock_sqlalchemy_engines
        client.async_session_factory = engines["async_session_factory"]
        
        # Mock transaction context
        @asynccontextmanager
        async def mock_session_context():
            yield engines["async_session"]
        
        @asynccontextmanager
        async def mock_transaction_context():
            yield
        
        engines["async_session"].begin.return_value = mock_transaction_context()
        
        with patch.object(client, "async_session_factory", engines["async_session_factory"]):
            async with client.transaction() as session:
                assert session == engines["async_session"]
    
    @pytest.mark.asyncio
    async def test_transaction_not_connected(self, client):
        """Test transaction when not connected."""
        with pytest.raises(DBConnectionError) as exc_info:
            async with client.transaction():
                pass
        
        assert "Database not connected" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_transaction_error_handling(self, client, mock_sqlalchemy_engines):
        """Test transaction error handling."""
        engines = mock_sqlalchemy_engines
        client.async_session_factory = engines["async_session_factory"]
        
        @asynccontextmanager
        async def mock_session_context():
            yield engines["async_session"]
        
        @asynccontextmanager
        async def mock_transaction_context():
            yield
        
        engines["async_session"].begin.return_value = mock_transaction_context()
        
        with patch.object(client, "async_session_factory", engines["async_session_factory"]):
            with pytest.raises(TransactionError):
                async with client.transaction():
                    raise Exception("Transaction error")
    
    @pytest.mark.asyncio
    async def test_create_tables_success(self, client, mock_sqlalchemy_engines):
        """Test successful table creation."""
        engines = mock_sqlalchemy_engines
        client.engine = engines["sync_engine"]
        
        # Mock Base metadata
        mock_base = Mock()
        mock_metadata = Mock()
        mock_base.metadata = mock_metadata
        
        with patch("src.multimodal_librarian.clients.local_postgresql_client.Base", mock_base):
            await client.create_tables()
        
        mock_metadata.create_all.assert_called_once_with(bind=engines["sync_engine"])
    
    @pytest.mark.asyncio
    async def test_create_tables_not_connected(self, client):
        """Test table creation when not connected."""
        with pytest.raises(DBConnectionError) as exc_info:
            await client.create_tables()
        
        assert "Database not connected" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_tables_error(self, client, mock_sqlalchemy_engines):
        """Test table creation error handling."""
        engines = mock_sqlalchemy_engines
        client.engine = engines["sync_engine"]
        
        mock_base = Mock()
        mock_metadata = Mock()
        mock_metadata.create_all.side_effect = Exception("Table creation failed")
        mock_base.metadata = mock_metadata
        
        with patch("src.multimodal_librarian.clients.local_postgresql_client.Base", mock_base):
            with pytest.raises(SchemaError) as exc_info:
                await client.create_tables()
        
        assert "Failed to create database tables" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_drop_tables_success(self, client, mock_sqlalchemy_engines):
        """Test successful table dropping."""
        engines = mock_sqlalchemy_engines
        client.engine = engines["sync_engine"]
        
        mock_base = Mock()
        mock_metadata = Mock()
        mock_base.metadata = mock_metadata
        
        with patch("src.multimodal_librarian.clients.local_postgresql_client.Base", mock_base):
            await client.drop_tables()
        
        mock_metadata.drop_all.assert_called_once_with(bind=engines["sync_engine"])
    
    @pytest.mark.asyncio
    async def test_migrate_schema_success(self, client, mock_sqlalchemy_engines):
        """Test successful schema migration."""
        engines = mock_sqlalchemy_engines
        client.async_session_factory = engines["async_session_factory"]
        
        migration_script = """
        ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT NOW();
        CREATE INDEX idx_users_created_at ON users(created_at);
        """
        
        @asynccontextmanager
        async def mock_session_context():
            yield engines["async_session"]
        
        with patch.object(client, "get_async_session", mock_session_context):
            await client.migrate_schema(migration_script)
        
        # Should execute 2 statements
        assert engines["async_session"].execute.call_count == 2
    
    @pytest.mark.asyncio
    async def test_migrate_schema_empty_script(self, client):
        """Test schema migration with empty script."""
        with pytest.raises(ValidationError) as exc_info:
            await client.migrate_schema("")
        
        assert "Migration script cannot be empty" in str(exc_info.value)
    
    def test_get_pool_status_connected(self, client, mock_sqlalchemy_engines):
        """Test getting pool status when connected."""
        engines = mock_sqlalchemy_engines
        client.engine = engines["sync_engine"]
        
        # Mock pool methods
        mock_pool = Mock()
        mock_pool.size.return_value = 10
        mock_pool.checkedin.return_value = 8
        mock_pool.checkedout.return_value = 2
        mock_pool.overflow.return_value = 0
        mock_pool.invalid.return_value = 0
        
        engines["sync_engine"].pool = mock_pool
        
        stats = client.get_pool_status()
        
        assert stats["size"] == 10
        assert stats["checked_in"] == 8
        assert stats["checked_out"] == 2
        assert stats["overflow"] == 0
        assert stats["invalid"] == 0
    
    def test_get_pool_status_not_connected(self, client):
        """Test getting pool status when not connected."""
        stats = client.get_pool_status()
        
        assert stats["size"] == 0
        assert stats["checked_in"] == 0
        assert stats["checked_out"] == 0
        assert stats["overflow"] == 0
        assert stats["invalid"] == 0
    
    @pytest.mark.asyncio
    async def test_reset_pool_success(self, client, mock_asyncpg_pool, mock_sqlalchemy_engines):
        """Test successful pool reset."""
        pool, connection = mock_asyncpg_pool
        engines = mock_sqlalchemy_engines
        
        # Set up client as connected
        client.engine = engines["sync_engine"]
        client.async_engine = engines["async_engine"]
        client.connection_pool = pool
        
        # Mock reconnection
        with patch.object(client, "connect", new_callable=AsyncMock) as mock_connect:
            await client.reset_pool()
        
        # Verify cleanup and reconnection
        engines["sync_engine"].dispose.assert_called_once()
        engines["async_engine"].dispose.assert_called_once()
        pool.close.assert_called_once()
        mock_connect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_backup_database_success(self, client):
        """Test successful database backup."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            success = await client.backup_database("/tmp/backup.sql")
        
        assert success is True
        mock_run.assert_called_once()
        
        # Verify pg_dump command
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "pg_dump" in cmd
        assert f"--host={client.host}" in cmd
        assert f"--port={client.port}" in cmd
        assert f"--username={client.user}" in cmd
        assert f"--dbname={client.database}" in cmd
        assert "--file=/tmp/backup.sql" in cmd
    
    @pytest.mark.asyncio
    async def test_backup_database_failure(self, client):
        """Test database backup failure."""
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "pg_dump: error: connection failed"
        
        with patch("subprocess.run", return_value=mock_result):
            success = await client.backup_database("/tmp/backup.sql")
        
        assert success is False
    
    @pytest.mark.asyncio
    async def test_backup_database_timeout(self, client):
        """Test database backup timeout."""
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pg_dump", 300)):
            success = await client.backup_database("/tmp/backup.sql")
        
        assert success is False
    
    @pytest.mark.asyncio
    async def test_restore_database_success(self, client):
        """Test successful database restore."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            success = await client.restore_database("/tmp/backup.sql")
        
        assert success is True
        mock_run.assert_called_once()
        
        # Verify psql command
        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert "psql" in cmd
        assert f"--host={client.host}" in cmd
        assert f"--port={client.port}" in cmd
        assert f"--username={client.user}" in cmd
        assert f"--dbname={client.database}" in cmd
        assert "--file=/tmp/backup.sql" in cmd
    
    @pytest.mark.asyncio
    async def test_get_database_info_success(self, client, mock_asyncpg_pool):
        """Test getting database information successfully."""
        pool, connection = mock_asyncpg_pool
        client.connection_pool = pool
        
        # Mock database info queries
        connection.fetchval.side_effect = [
            "PostgreSQL 13.7",  # version
            1073741824,         # size (1GB)
            25,                 # table_count
            10,                 # connection_count
            86400.0,            # uptime (1 day)
            "UTF8"              # charset
        ]
        
        info = await client.get_database_info()
        
        assert info["version"] == "PostgreSQL 13.7"
        assert info["size"] == 1073741824
        assert info["table_count"] == 25
        assert info["connection_count"] == 10
        assert info["uptime"] == 86400.0
        assert info["charset"] == "UTF8"
        assert info["host"] == client.host
        assert info["port"] == client.port
        assert info["database"] == client.database
        assert "last_updated" in info
    
    @pytest.mark.asyncio
    async def test_get_table_info_success(self, client, mock_asyncpg_pool):
        """Test getting table information successfully."""
        pool, connection = mock_asyncpg_pool
        client.connection_pool = pool
        
        # Mock table info queries
        connection.fetchval.side_effect = [
            True,     # table exists
            1000,     # row count
            8192,     # table size
            datetime.now(timezone.utc)  # last analyzed
        ]
        
        # Mock columns query
        connection.fetch.side_effect = [
            [  # columns
                {"column_name": "id", "data_type": "integer", "is_nullable": "NO", "column_default": "nextval('users_id_seq'::regclass)", "character_maximum_length": None},
                {"column_name": "name", "data_type": "character varying", "is_nullable": "NO", "column_default": None, "character_maximum_length": 255},
                {"column_name": "email", "data_type": "character varying", "is_nullable": "YES", "column_default": None, "character_maximum_length": 255}
            ],
            [  # indexes
                {"name": "users_pkey", "definition": "CREATE UNIQUE INDEX users_pkey ON public.users USING btree (id)"},
                {"name": "idx_users_email", "definition": "CREATE INDEX idx_users_email ON public.users USING btree (email)"}
            ]
        ]
        
        info = await client.get_table_info("users")
        
        assert info["name"] == "users"
        assert len(info["columns"]) == 3
        assert len(info["indexes"]) == 2
        assert info["row_count"] == 1000
        assert info["size"] == 8192
        assert "last_analyzed" in info
        assert "last_updated" in info
    
    @pytest.mark.asyncio
    async def test_get_table_info_not_exists(self, client, mock_asyncpg_pool):
        """Test getting info for non-existent table."""
        pool, connection = mock_asyncpg_pool
        client.connection_pool = pool
        
        connection.fetchval.return_value = False  # table doesn't exist
        
        with pytest.raises(ValidationError) as exc_info:
            await client.get_table_info("nonexistent_table")
        
        assert "Table 'nonexistent_table' does not exist" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_table_info_empty_name(self, client):
        """Test getting table info with empty name."""
        with pytest.raises(ValidationError) as exc_info:
            await client.get_table_info("")
        
        assert "Table name cannot be empty" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_performance_stats_success(self, client, mock_asyncpg_pool):
        """Test getting performance statistics successfully."""
        pool, connection = mock_asyncpg_pool
        client.connection_pool = pool
        
        # Set up client performance tracking
        client._query_count = 100
        client._total_query_time = 50.0
        client._slow_query_count = 5
        client._connection_errors = 2
        
        # Mock database stats query
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
        
        connection.fetchrow.return_value = mock_stats
        connection.fetchval.side_effect = [
            5,        # slow queries
            86400.0   # uptime
        ]
        
        stats = await client.get_performance_stats()
        
        assert stats["active_connections"] == 10
        assert stats["transactions_committed"] == 1000
        assert stats["transactions_rolled_back"] == 50
        assert stats["cache_hit_ratio"] == 0.9  # 45000 / (5000 + 45000)
        assert stats["avg_query_time"] == 0.5   # 50.0 / 100
        assert stats["slow_queries"] == 5
        assert stats["connection_errors"] == 2
        assert "queries_per_second" in stats
        assert "last_updated" in stats
    
    @pytest.mark.asyncio
    async def test_analyze_table_success(self, client, mock_asyncpg_pool):
        """Test successful table analysis."""
        pool, connection = mock_asyncpg_pool
        client.connection_pool = pool
        client.async_session_factory = Mock()
        
        # Mock table existence check
        with patch.object(client, "get_table_info", return_value={"row_count": 1000}), \
             patch.object(client, "execute_command", return_value=0) as mock_execute:
            
            await client.analyze_table("users")
        
        mock_execute.assert_called_once_with("ANALYZE users")
    
    @pytest.mark.asyncio
    async def test_analyze_table_empty_name(self, client):
        """Test table analysis with empty name."""
        with pytest.raises(ValidationError) as exc_info:
            await client.analyze_table("")
        
        assert "Table name cannot be empty" in str(exc_info.value)
    
    def test_event_handlers(self, client):
        """Test connection event handlers."""
        # These methods should not raise exceptions
        client._on_connect(None, None)
        client._on_checkout(None, None, None)
        client._on_checkin(None, None)
    
    @pytest.mark.asyncio
    async def test_verify_connection_success(self, client, mock_asyncpg_pool):
        """Test successful connection verification."""
        pool, connection = mock_asyncpg_pool
        client.connection_pool = pool
        connection.fetchval.return_value = 1
        
        # Should not raise exception
        await client._verify_connection()
        
        connection.fetchval.assert_called_once_with("SELECT 1")
    
    @pytest.mark.asyncio
    async def test_verify_connection_failure(self, client, mock_asyncpg_pool):
        """Test connection verification failure."""
        pool, connection = mock_asyncpg_pool
        client.connection_pool = pool
        connection.fetchval.return_value = 0  # Unexpected result
        
        with pytest.raises(DBConnectionError) as exc_info:
            await client._verify_connection()
        
        assert "Connection verification failed" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_verify_connection_exception(self, client, mock_asyncpg_pool):
        """Test connection verification with exception."""
        pool, connection = mock_asyncpg_pool
        client.connection_pool = pool
        connection.fetchval.side_effect = Exception("Connection error")
        
        with pytest.raises(DBConnectionError) as exc_info:
            await client._verify_connection()
        
        assert "Connection verification failed" in str(exc_info.value)


if __name__ == "__main__":
    pytest.main([__file__])