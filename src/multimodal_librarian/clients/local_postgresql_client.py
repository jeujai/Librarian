"""
Local PostgreSQL client implementation for development environments.

This module provides a PostgreSQL client that implements the RelationalStoreClient
protocol for local development. It uses asyncpg for async operations and psycopg2
for synchronous operations, with connection pooling and comprehensive error handling.

The client is designed to work with local PostgreSQL instances running in Docker
or natively, providing the same interface as AWS RDS clients for seamless
environment switching.

Example Usage:
    ```python
    from multimodal_librarian.clients.local_postgresql_client import LocalPostgreSQLClient
    from multimodal_librarian.config import get_settings
    
    settings = get_settings()
    client = LocalPostgreSQLClient(
        host=settings.postgres_host,
        port=settings.postgres_port,
        database=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password
    )
    
    await client.connect()
    
    # Execute queries
    results = await client.execute_query(
        "SELECT * FROM users WHERE active = :active",
        {"active": True}
    )
    
    # Use transactions
    async with client.transaction() as session:
        await session.execute(
            text("INSERT INTO users (name, email) VALUES (:name, :email)"),
            {"name": "John Doe", "email": "john@example.com"}
        )
    
    await client.disconnect()
    ```

Performance Considerations:
    - Uses connection pooling for efficient resource usage
    - Supports both sync and async operations
    - Implements connection health monitoring and recovery
    - Provides query performance metrics and monitoring
"""

import asyncio
import time
import json
import subprocess
from contextlib import asynccontextmanager, contextmanager
from typing import Dict, Any, List, Optional, Generator, AsyncGenerator
from datetime import datetime, timezone

import asyncpg
import psycopg2
import psycopg2.extras
from sqlalchemy import create_engine, text, Engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import SQLAlchemyError
import structlog

from .protocols import (
    RelationalStoreClient, DatabaseMetadata, QueryParameters, 
    HealthStatus, ConnectionPoolStats, PerformanceMetrics, SearchResults
)
from .exceptions import (
    DatabaseClientError, ConnectionError as DBConnectionError, 
    QueryError, ValidationError, TransactionError, SchemaError,
    TimeoutError as DBTimeoutError, ResourceError
)
from ..logging.query_logging_decorators import log_postgresql_queries

logger = structlog.get_logger(__name__)


@log_postgresql_queries()
class LocalPostgreSQLClient:
    """
    Local PostgreSQL client implementing RelationalStoreClient protocol.
    
    This client provides comprehensive PostgreSQL database operations for local
    development environments. It supports both synchronous and asynchronous
    operations, connection pooling, transaction management, and health monitoring.
    
    Features:
        - Async/await support with asyncpg
        - Synchronous operations with psycopg2
        - Connection pooling and health monitoring
        - Transaction management with context managers
        - Schema operations and migrations
        - Performance monitoring and statistics
        - Backup and restore operations
        - Comprehensive error handling
    
    Thread Safety:
        This client is thread-safe for connection pooling. Individual sessions
        should not be shared across threads.
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "multimodal_librarian",
        user: str = "postgres",
        password: str = "postgres",
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_timeout: int = 30,
        pool_recycle: int = 3600,
        echo: bool = False
    ):
        """
        Initialize PostgreSQL client with connection parameters.
        
        Args:
            host: PostgreSQL server host
            port: PostgreSQL server port
            database: Database name
            user: Username for authentication
            password: Password for authentication
            pool_size: Base connection pool size
            max_overflow: Maximum overflow connections
            pool_timeout: Connection timeout in seconds
            pool_recycle: Connection recycle time in seconds
            echo: Enable SQL query logging
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self.pool_timeout = pool_timeout
        self.pool_recycle = pool_recycle
        self.echo = echo
        
        # Connection components
        self.engine: Optional[Engine] = None
        self.async_engine: Optional[Engine] = None
        self.session_factory: Optional[sessionmaker] = None
        self.async_session_factory: Optional[async_sessionmaker] = None
        self.connection_pool: Optional[asyncpg.Pool] = None
        
        # Connection URLs
        self.sync_url = f"postgresql://{user}:{password}@{host}:{port}/{database}"
        self.async_url = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"
        
        # Performance tracking
        self._query_count = 0
        self._total_query_time = 0.0
        self._slow_query_count = 0
        self._connection_errors = 0
        self._last_health_check = None
        
        logger.info(
            "PostgreSQL client initialized",
            host=host,
            port=port,
            database=database,
            user=user,
            pool_size=pool_size
        )
    
    async def connect(self) -> None:
        """
        Establish connection to the PostgreSQL database.
        
        This method initializes the database connection pool and verifies
        connectivity. It's idempotent - calling it multiple times won't
        create multiple connection pools.
        
        Raises:
            ConnectionError: If connection cannot be established
            ConfigurationError: If database configuration is invalid
        """
        if self.engine is not None and self.async_engine is not None:
            logger.debug("PostgreSQL client already connected")
            return
        
        try:
            # Create synchronous engine
            self.engine = create_engine(
                self.sync_url,
                poolclass=QueuePool,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_timeout=self.pool_timeout,
                pool_pre_ping=True,
                pool_recycle=self.pool_recycle,
                echo=self.echo
            )
            
            # Create asynchronous engine
            self.async_engine = create_async_engine(
                self.async_url,
                pool_size=self.pool_size,
                max_overflow=self.max_overflow,
                pool_timeout=self.pool_timeout,
                pool_pre_ping=True,
                pool_recycle=self.pool_recycle,
                echo=self.echo
            )
            
            # Add connection event listeners
            event.listen(self.engine, "connect", self._on_connect)
            event.listen(self.engine, "checkout", self._on_checkout)
            event.listen(self.engine, "checkin", self._on_checkin)
            
            # Create session factories
            self.session_factory = sessionmaker(
                bind=self.engine,
                autocommit=False,
                autoflush=False
            )
            
            self.async_session_factory = async_sessionmaker(
                bind=self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            # Create asyncpg connection pool for raw operations
            self.connection_pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                min_size=2,
                max_size=self.pool_size,
                command_timeout=60
            )
            
            # Verify connection
            await self._verify_connection()
            
            logger.info(
                "PostgreSQL client connected successfully",
                host=self.host,
                database=self.database,
                pool_size=self.pool_size
            )
            
        except Exception as e:
            self._connection_errors += 1
            logger.error(
                "Failed to connect to PostgreSQL",
                error=str(e),
                host=self.host,
                database=self.database
            )
            raise DBConnectionError(
                f"Failed to connect to PostgreSQL at {self.host}:{self.port}/{self.database}",
                database_type="postgresql",
                host=self.host,
                port=self.port
            ) from e
    
    async def disconnect(self) -> None:
        """
        Close connection to the PostgreSQL database.
        
        This method closes all connections in the pool and cleans up resources.
        After calling this method, the client should not be used until connect()
        is called again.
        
        Raises:
            ConnectionError: If there are issues closing connections
        """
        try:
            # Close asyncpg pool
            if self.connection_pool:
                await self.connection_pool.close()
                self.connection_pool = None
            
            # Dispose SQLAlchemy engines
            if self.async_engine:
                await self.async_engine.dispose()
                self.async_engine = None
            
            if self.engine:
                self.engine.dispose()
                self.engine = None
            
            # Clear session factories
            self.session_factory = None
            self.async_session_factory = None
            
            logger.info("PostgreSQL client disconnected successfully")
            
        except Exception as e:
            logger.error("Error during PostgreSQL disconnect", error=str(e))
            raise DBConnectionError(
                f"Failed to disconnect from PostgreSQL: {str(e)}",
                database_type="postgresql"
            ) from e
    
    async def health_check(self) -> HealthStatus:
        """
        Perform health check on the PostgreSQL database.
        
        This method verifies that the database is accessible and responsive.
        It performs a lightweight query and returns comprehensive health information.
        
        Returns:
            Dictionary with health status information
        """
        start_time = time.time()
        
        try:
            if not self.connection_pool:
                return {
                    "status": "unhealthy",
                    "error": "No connection pool available",
                    "response_time": 0,
                    "connection_count": 0,
                    "last_check": datetime.now(timezone.utc).isoformat()
                }
            
            # Test connection with simple query
            async with self.connection_pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                if result != 1:
                    raise Exception("Health check query returned unexpected result")
            
            response_time = time.time() - start_time
            self._last_health_check = datetime.now(timezone.utc)
            
            # Get connection pool stats
            pool_stats = self.get_pool_status()
            
            return {
                "status": "healthy",
                "response_time": response_time,
                "connection_count": pool_stats.get("checked_out", 0),
                "pool_size": pool_stats.get("size", 0),
                "last_check": self._last_health_check.isoformat(),
                "query_count": self._query_count,
                "avg_query_time": (
                    self._total_query_time / self._query_count 
                    if self._query_count > 0 else 0
                ),
                "slow_queries": self._slow_query_count,
                "connection_errors": self._connection_errors
            }
            
        except Exception as e:
            response_time = time.time() - start_time
            logger.error("PostgreSQL health check failed", error=str(e))
            
            return {
                "status": "unhealthy",
                "error": str(e),
                "response_time": response_time,
                "connection_count": 0,
                "last_check": datetime.now(timezone.utc).isoformat()
            }
    
    @asynccontextmanager
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get an async database session with automatic cleanup.
        
        This context manager provides a database session that is automatically
        committed on success or rolled back on exception.
        
        Yields:
            AsyncSession: SQLAlchemy async session
        """
        if not self.async_session_factory:
            raise DBConnectionError(
                "Database not connected. Call connect() first.",
                database_type="postgresql"
            )
        
        async with self.async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error("Async session error", error=str(e))
                raise
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Get a synchronous database session with automatic cleanup.
        
        This context manager provides a synchronous database session for
        compatibility with synchronous code.
        
        Yields:
            Session: SQLAlchemy synchronous session
        """
        if not self.session_factory:
            raise DBConnectionError(
                "Database not connected. Call connect() first.",
                database_type="postgresql"
            )
        
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Sync session error", error=str(e))
            raise
        finally:
            session.close()
    
    async def execute_query(
        self, 
        query: str, 
        parameters: Optional[QueryParameters] = None
    ) -> SearchResults:
        """
        Execute a raw SQL query and return results.
        
        This method executes a SELECT query and returns the results as a list
        of dictionaries. Use parameterized queries to prevent SQL injection.
        
        Args:
            query: SQL query string (should be a SELECT statement)
            parameters: Query parameters for safe parameterized queries
            
        Returns:
            List of result rows as dictionaries with column names as keys
        """
        if not query.strip():
            raise ValidationError("Query cannot be empty")
        
        start_time = time.time()
        
        try:
            async with self.get_async_session() as session:
                # Convert parameters to SQLAlchemy format if needed
                if parameters:
                    result = await session.execute(text(query), parameters)
                else:
                    result = await session.execute(text(query))
                
                # Convert result to list of dictionaries
                rows = result.fetchall()
                columns = result.keys()
                
                results = [
                    dict(zip(columns, row)) for row in rows
                ]
                
                # Update performance metrics
                query_time = time.time() - start_time
                self._query_count += 1
                self._total_query_time += query_time
                
                if query_time > 1.0:  # Slow query threshold
                    self._slow_query_count += 1
                    logger.warning(
                        "Slow query detected",
                        query=query[:100] + "..." if len(query) > 100 else query,
                        execution_time=query_time,
                        parameters=parameters
                    )
                
                logger.debug(
                    "Query executed successfully",
                    query=query[:100] + "..." if len(query) > 100 else query,
                    execution_time=query_time,
                    result_count=len(results)
                )
                
                return results
                
        except SQLAlchemyError as e:
            logger.error(
                "Query execution failed",
                query=query[:100] + "..." if len(query) > 100 else query,
                error=str(e),
                parameters=parameters
            )
            raise QueryError(
                f"Query execution failed: {str(e)}",
                query=query,
                parameters=parameters
            ) from e
        except Exception as e:
            logger.error(
                "Unexpected error during query execution",
                query=query[:100] + "..." if len(query) > 100 else query,
                error=str(e)
            )
            raise DatabaseClientError(
                f"Unexpected error during query execution: {str(e)}"
            ) from e
    
    async def execute_command(
        self, 
        command: str, 
        parameters: Optional[QueryParameters] = None
    ) -> int:
        """
        Execute a SQL command (INSERT, UPDATE, DELETE) and return affected rows.
        
        This method executes data modification commands and returns the number
        of rows affected. The command is executed within a transaction.
        
        Args:
            command: SQL command string (INSERT, UPDATE, DELETE, etc.)
            parameters: Command parameters for safe parameterized queries
            
        Returns:
            Number of rows affected by the command
        """
        if not command.strip():
            raise ValidationError("Command cannot be empty")
        
        start_time = time.time()
        
        try:
            async with self.get_async_session() as session:
                if parameters:
                    result = await session.execute(text(command), parameters)
                else:
                    result = await session.execute(text(command))
                
                affected_rows = result.rowcount
                
                # Update performance metrics
                query_time = time.time() - start_time
                self._query_count += 1
                self._total_query_time += query_time
                
                logger.debug(
                    "Command executed successfully",
                    command=command[:100] + "..." if len(command) > 100 else command,
                    execution_time=query_time,
                    affected_rows=affected_rows
                )
                
                return affected_rows
                
        except SQLAlchemyError as e:
            logger.error(
                "Command execution failed",
                command=command[:100] + "..." if len(command) > 100 else command,
                error=str(e),
                parameters=parameters
            )
            raise QueryError(
                f"Command execution failed: {str(e)}",
                query=command,
                parameters=parameters
            ) from e
        except Exception as e:
            logger.error(
                "Unexpected error during command execution",
                command=command[:100] + "..." if len(command) > 100 else command,
                error=str(e)
            )
            raise DatabaseClientError(
                f"Unexpected error during command execution: {str(e)}"
            ) from e
    
    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Create a database transaction context.
        
        This context manager provides a database session within a transaction.
        The transaction is automatically committed on success or rolled back
        on exception.
        
        Yields:
            AsyncSession: Session within transaction context
        """
        if not self.async_session_factory:
            raise DBConnectionError(
                "Database not connected. Call connect() first.",
                database_type="postgresql"
            )
        
        async with self.async_session_factory() as session:
            async with session.begin():
                try:
                    yield session
                except Exception as e:
                    logger.error("Transaction failed", error=str(e))
                    raise TransactionError(
                        f"Transaction failed: {str(e)}"
                    ) from e
    
    async def create_tables(self) -> None:
        """
        Create all database tables based on SQLAlchemy models.
        
        This method creates all tables defined in the application's SQLAlchemy
        models. It's idempotent - calling it multiple times won't cause errors
        if tables already exist.
        """
        try:
            # Import Base from database models
            from ..database.models import Base
            
            if not self.engine:
                raise DBConnectionError(
                    "Database not connected. Call connect() first.",
                    database_type="postgresql"
                )
            
            # Create all tables
            Base.metadata.create_all(bind=self.engine)
            
            logger.info("Database tables created successfully")
            
        except Exception as e:
            logger.error("Failed to create database tables", error=str(e))
            raise SchemaError(
                f"Failed to create database tables: {str(e)}"
            ) from e
    
    async def drop_tables(self) -> None:
        """
        Drop all database tables. Use with caution!
        
        This method drops all tables in the database. This operation is
        irreversible and will result in data loss.
        """
        try:
            # Import Base from database models
            from ..database.models import Base
            
            if not self.engine:
                raise DBConnectionError(
                    "Database not connected. Call connect() first.",
                    database_type="postgresql"
                )
            
            # Drop all tables
            Base.metadata.drop_all(bind=self.engine)
            
            logger.warning("All database tables dropped")
            
        except Exception as e:
            logger.error("Failed to drop database tables", error=str(e))
            raise SchemaError(
                f"Failed to drop database tables: {str(e)}"
            ) from e
    
    async def migrate_schema(self, migration_script: str) -> None:
        """
        Execute a database migration script.
        
        This method executes a SQL migration script to update the database
        schema. The script should be idempotent and handle existing schema
        gracefully.
        
        Args:
            migration_script: SQL migration script to execute
        """
        if not migration_script.strip():
            raise ValidationError("Migration script cannot be empty")
        
        try:
            async with self.get_async_session() as session:
                # Split script into individual statements
                statements = [
                    stmt.strip() for stmt in migration_script.split(';')
                    if stmt.strip()
                ]
                
                for statement in statements:
                    await session.execute(text(statement))
                
                logger.info(
                    "Migration script executed successfully",
                    statements_count=len(statements)
                )
                
        except Exception as e:
            logger.error("Migration script execution failed", error=str(e))
            raise SchemaError(
                f"Migration script execution failed: {str(e)}"
            ) from e
    
    def get_pool_status(self) -> ConnectionPoolStats:
        """
        Get connection pool status information.
        
        This method returns information about the current state of the
        connection pool, useful for monitoring and debugging.
        
        Returns:
            Dictionary with pool statistics
        """
        if not self.engine:
            return {
                "size": 0,
                "checked_in": 0,
                "checked_out": 0,
                "overflow": 0,
                "invalid": 0
            }
        
        pool = self.engine.pool
        
        return {
            "size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "invalid": pool.invalid()
        }
    
    async def reset_pool(self) -> None:
        """
        Reset the connection pool.
        
        This method closes all connections in the pool and recreates it.
        Use this to recover from connection issues or to apply new
        configuration settings.
        """
        try:
            if self.engine:
                self.engine.dispose()
            
            if self.async_engine:
                await self.async_engine.dispose()
            
            if self.connection_pool:
                await self.connection_pool.close()
            
            # Reconnect
            await self.connect()
            
            logger.info("Connection pool reset successfully")
            
        except Exception as e:
            logger.error("Failed to reset connection pool", error=str(e))
            raise DBConnectionError(
                f"Failed to reset connection pool: {str(e)}",
                database_type="postgresql"
            ) from e
    
    async def backup_database(self, backup_path: str) -> bool:
        """
        Create a database backup using pg_dump.
        
        This method creates a backup of the database to the specified path
        using PostgreSQL's pg_dump utility.
        
        Args:
            backup_path: Path where backup should be stored
            
        Returns:
            True if backup was successful, False otherwise
        """
        try:
            # Build pg_dump command
            cmd = [
                "pg_dump",
                f"--host={self.host}",
                f"--port={self.port}",
                f"--username={self.user}",
                f"--dbname={self.database}",
                "--no-password",
                "--verbose",
                "--clean",
                "--if-exists",
                "--create",
                f"--file={backup_path}"
            ]
            
            # Set password via environment variable
            env = {"PGPASSWORD": self.password}
            
            # Execute pg_dump
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode == 0:
                logger.info(
                    "Database backup created successfully",
                    backup_path=backup_path,
                    database=self.database
                )
                return True
            else:
                logger.error(
                    "Database backup failed",
                    backup_path=backup_path,
                    error=result.stderr,
                    return_code=result.returncode
                )
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Database backup timed out", backup_path=backup_path)
            return False
        except Exception as e:
            logger.error(
                "Database backup failed with exception",
                backup_path=backup_path,
                error=str(e)
            )
            return False
    
    async def restore_database(self, backup_path: str) -> bool:
        """
        Restore database from backup using psql.
        
        This method restores the database from a backup file using
        PostgreSQL's psql utility.
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            True if restore was successful, False otherwise
        """
        try:
            # Build psql command
            cmd = [
                "psql",
                f"--host={self.host}",
                f"--port={self.port}",
                f"--username={self.user}",
                f"--dbname={self.database}",
                "--no-password",
                "--quiet",
                f"--file={backup_path}"
            ]
            
            # Set password via environment variable
            env = {"PGPASSWORD": self.password}
            
            # Execute psql
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )
            
            if result.returncode == 0:
                logger.info(
                    "Database restored successfully",
                    backup_path=backup_path,
                    database=self.database
                )
                return True
            else:
                logger.error(
                    "Database restore failed",
                    backup_path=backup_path,
                    error=result.stderr,
                    return_code=result.returncode
                )
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Database restore timed out", backup_path=backup_path)
            return False
        except Exception as e:
            logger.error(
                "Database restore failed with exception",
                backup_path=backup_path,
                error=str(e)
            )
            return False
    
    async def get_database_info(self) -> DatabaseMetadata:
        """
        Get database information and statistics.
        
        This method returns comprehensive information about the database
        including version, size, table count, and other metadata.
        
        Returns:
            Dictionary with database metadata
        """
        try:
            async with self.connection_pool.acquire() as conn:
                # Get PostgreSQL version
                version = await conn.fetchval("SELECT version()")
                
                # Get database size
                size_query = """
                SELECT pg_database_size(current_database()) as size
                """
                size = await conn.fetchval(size_query)
                
                # Get table count
                table_count_query = """
                SELECT COUNT(*) 
                FROM information_schema.tables 
                WHERE table_schema = 'public'
                """
                table_count = await conn.fetchval(table_count_query)
                
                # Get connection count
                connection_count_query = """
                SELECT COUNT(*) 
                FROM pg_stat_activity 
                WHERE datname = current_database()
                """
                connection_count = await conn.fetchval(connection_count_query)
                
                # Get uptime (approximate)
                uptime_query = """
                SELECT EXTRACT(EPOCH FROM (now() - pg_postmaster_start_time())) as uptime
                """
                uptime = await conn.fetchval(uptime_query)
                
                # Get charset
                charset_query = """
                SELECT pg_encoding_to_char(encoding) 
                FROM pg_database 
                WHERE datname = current_database()
                """
                charset = await conn.fetchval(charset_query)
                
                return {
                    "version": version,
                    "size": int(size) if size else 0,
                    "table_count": int(table_count) if table_count else 0,
                    "connection_count": int(connection_count) if connection_count else 0,
                    "uptime": float(uptime) if uptime else 0,
                    "charset": charset or "unknown",
                    "host": self.host,
                    "port": self.port,
                    "database": self.database,
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
                
        except Exception as e:
            logger.error("Failed to get database info", error=str(e))
            raise DatabaseClientError(
                f"Failed to get database info: {str(e)}"
            ) from e
    
    async def get_table_info(self, table_name: str) -> DatabaseMetadata:
        """
        Get information about a specific table.
        
        This method returns detailed information about a table including
        column definitions, indexes, constraints, and statistics.
        
        Args:
            table_name: Name of the table
            
        Returns:
            Dictionary with table metadata
        """
        if not table_name.strip():
            raise ValidationError("Table name cannot be empty")
        
        try:
            async with self.connection_pool.acquire() as conn:
                # Check if table exists
                exists_query = """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = $1
                )
                """
                exists = await conn.fetchval(exists_query, table_name)
                
                if not exists:
                    raise ValidationError(f"Table '{table_name}' does not exist")
                
                # Get column information
                columns_query = """
                SELECT 
                    column_name,
                    data_type,
                    is_nullable,
                    column_default,
                    character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = 'public' 
                AND table_name = $1
                ORDER BY ordinal_position
                """
                columns_rows = await conn.fetch(columns_query, table_name)
                columns = [dict(row) for row in columns_rows]
                
                # Get indexes
                indexes_query = """
                SELECT 
                    indexname as name,
                    indexdef as definition
                FROM pg_indexes
                WHERE schemaname = 'public' 
                AND tablename = $1
                """
                indexes_rows = await conn.fetch(indexes_query, table_name)
                indexes = [dict(row) for row in indexes_rows]
                
                # Get row count (approximate)
                row_count_query = f"""
                SELECT reltuples::BIGINT as row_count
                FROM pg_class
                WHERE relname = $1
                """
                row_count = await conn.fetchval(row_count_query, table_name)
                
                # Get table size
                size_query = f"""
                SELECT pg_total_relation_size($1) as size
                """
                size = await conn.fetchval(size_query, table_name)
                
                # Get last analyzed time
                analyzed_query = """
                SELECT last_analyzed
                FROM pg_stat_user_tables
                WHERE schemaname = 'public' 
                AND relname = $1
                """
                last_analyzed = await conn.fetchval(analyzed_query, table_name)
                
                return {
                    "name": table_name,
                    "columns": columns,
                    "indexes": indexes,
                    "row_count": int(row_count) if row_count else 0,
                    "size": int(size) if size else 0,
                    "last_analyzed": (
                        last_analyzed.isoformat() if last_analyzed 
                        else None
                    ),
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
                
        except ValidationError:
            raise
        except Exception as e:
            logger.error(
                "Failed to get table info",
                table_name=table_name,
                error=str(e)
            )
            raise DatabaseClientError(
                f"Failed to get table info for '{table_name}': {str(e)}"
            ) from e
    
    async def get_performance_stats(self) -> PerformanceMetrics:
        """
        Get database performance statistics.
        
        This method returns performance metrics useful for monitoring
        and optimization, including query statistics and resource usage.
        
        Returns:
            Dictionary with performance metrics
        """
        try:
            async with self.connection_pool.acquire() as conn:
                # Get database statistics
                db_stats_query = """
                SELECT 
                    numbackends as active_connections,
                    xact_commit as transactions_committed,
                    xact_rollback as transactions_rolled_back,
                    blks_read as blocks_read,
                    blks_hit as blocks_hit,
                    tup_returned as tuples_returned,
                    tup_fetched as tuples_fetched,
                    tup_inserted as tuples_inserted,
                    tup_updated as tuples_updated,
                    tup_deleted as tuples_deleted
                FROM pg_stat_database
                WHERE datname = current_database()
                """
                db_stats = await conn.fetchrow(db_stats_query)
                
                # Calculate cache hit ratio
                blocks_read = db_stats['blocks_read'] or 0
                blocks_hit = db_stats['blocks_hit'] or 0
                total_blocks = blocks_read + blocks_hit
                cache_hit_ratio = (
                    blocks_hit / total_blocks if total_blocks > 0 else 0
                )
                
                # Get slow queries count (queries taking > 1 second)
                slow_queries_query = """
                SELECT COUNT(*) as slow_queries
                FROM pg_stat_statements
                WHERE mean_time > 1000
                """
                try:
                    slow_queries = await conn.fetchval(slow_queries_query)
                except:
                    # pg_stat_statements extension might not be available
                    slow_queries = self._slow_query_count
                
                # Calculate queries per second (approximate)
                uptime_query = """
                SELECT EXTRACT(EPOCH FROM (now() - pg_postmaster_start_time())) as uptime
                """
                uptime = await conn.fetchval(uptime_query)
                
                total_queries = (
                    (db_stats['transactions_committed'] or 0) + 
                    (db_stats['transactions_rolled_back'] or 0)
                )
                queries_per_second = (
                    total_queries / uptime if uptime > 0 else 0
                )
                
                return {
                    "queries_per_second": queries_per_second,
                    "avg_query_time": (
                        self._total_query_time / self._query_count 
                        if self._query_count > 0 else 0
                    ),
                    "slow_queries": slow_queries or 0,
                    "cache_hit_ratio": cache_hit_ratio,
                    "active_connections": db_stats['active_connections'] or 0,
                    "transactions_committed": db_stats['transactions_committed'] or 0,
                    "transactions_rolled_back": db_stats['transactions_rolled_back'] or 0,
                    "tuples_returned": db_stats['tuples_returned'] or 0,
                    "tuples_fetched": db_stats['tuples_fetched'] or 0,
                    "tuples_inserted": db_stats['tuples_inserted'] or 0,
                    "tuples_updated": db_stats['tuples_updated'] or 0,
                    "tuples_deleted": db_stats['tuples_deleted'] or 0,
                    "connection_errors": self._connection_errors,
                    "last_updated": datetime.now(timezone.utc).isoformat()
                }
                
        except Exception as e:
            logger.error("Failed to get performance stats", error=str(e))
            raise DatabaseClientError(
                f"Failed to get performance stats: {str(e)}"
            ) from e
    
    async def analyze_table(self, table_name: str) -> None:
        """
        Analyze table statistics for query optimization.
        
        This method updates table statistics used by the query planner
        to optimize query execution plans.
        
        Args:
            table_name: Name of the table to analyze
        """
        if not table_name.strip():
            raise ValidationError("Table name cannot be empty")
        
        try:
            # Verify table exists
            table_info = await self.get_table_info(table_name)
            
            # Run ANALYZE command
            analyze_command = f"ANALYZE {table_name}"
            await self.execute_command(analyze_command)
            
            logger.info(
                "Table statistics updated",
                table_name=table_name,
                row_count=table_info.get("row_count", 0)
            )
            
        except ValidationError:
            raise
        except Exception as e:
            logger.error(
                "Failed to analyze table",
                table_name=table_name,
                error=str(e)
            )
            raise QueryError(
                f"Failed to analyze table '{table_name}': {str(e)}"
            ) from e
    
    # Event handlers for connection monitoring
    def _on_connect(self, dbapi_connection, connection_record):
        """Handle new database connections."""
        logger.debug("New PostgreSQL connection established")
    
    def _on_checkout(self, dbapi_connection, connection_record, connection_proxy):
        """Handle connection checkout from pool."""
        logger.debug("PostgreSQL connection checked out from pool")
    
    def _on_checkin(self, dbapi_connection, connection_record):
        """Handle connection checkin to pool."""
        logger.debug("PostgreSQL connection checked in to pool")
    
    async def _verify_connection(self) -> None:
        """Verify database connection is working."""
        try:
            async with self.connection_pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                if result != 1:
                    raise Exception("Connection verification failed")
        except Exception as e:
            raise DBConnectionError(
                f"Connection verification failed: {str(e)}",
                database_type="postgresql",
                host=self.host,
                port=self.port
            ) from e