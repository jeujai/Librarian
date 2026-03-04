"""
Database connection management for PostgreSQL.

This module provides connection pooling, session management, and database
configuration for the Multimodal Librarian system.
"""

import os
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncGenerator, Generator, Optional

import psycopg2
import structlog
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

logger = structlog.get_logger(__name__)

# Base class for all database models
Base = declarative_base()

class DatabaseManager:
    """Manages database connections and sessions."""
    
    def __init__(self, database_url: Optional[str] = None):
        """Initialize database manager with connection URL."""
        self.database_url = database_url or self._get_database_url()
        self.async_database_url = self._get_async_database_url()
        self.engine: Optional[Engine] = None
        self.async_engine: Optional[Engine] = None
        self.SessionLocal: Optional[sessionmaker] = None
        self.AsyncSessionLocal: Optional[async_sessionmaker] = None
        
    def _get_database_url(self) -> str:
        """Get database URL from environment variables or configuration."""
        # Try to get from configuration factory first
        try:
            from ..config.config_factory import get_database_config
            config = get_database_config()
            
            # Use the enhanced connection string generation
            if hasattr(config, 'get_postgres_connection_string'):
                return config.get_postgres_connection_string(async_driver=False)
            elif hasattr(config, 'get_relational_db_config'):
                db_config = config.get_relational_db_config()
                return db_config.get('sync_connection_string', db_config.get('connection_string'))
        except Exception as e:
            logger.warning(f"Could not get connection string from config: {e}")
        
        # Fallback to environment variables
        host = os.getenv("DB_HOST", os.getenv("ML_POSTGRES_HOST", "localhost"))
        port = os.getenv("DB_PORT", os.getenv("ML_POSTGRES_PORT", "5432"))
        database = os.getenv("DB_NAME", os.getenv("ML_POSTGRES_DB", "multimodal_librarian"))
        username = os.getenv("DB_USER", os.getenv("ML_POSTGRES_USER", "postgres"))
        password = os.getenv("DB_PASSWORD", os.getenv("ML_POSTGRES_PASSWORD", "postgres"))
        
        return f"postgresql://{username}:{password}@{host}:{port}/{database}"
    
    def _get_async_database_url(self) -> str:
        """Get async database URL from environment variables or configuration."""
        # Try to get from configuration factory first
        try:
            from ..config.config_factory import get_database_config
            config = get_database_config()
            
            # Use the enhanced connection string generation
            if hasattr(config, 'get_postgres_connection_string'):
                return config.get_postgres_connection_string(async_driver=True)
            elif hasattr(config, 'get_relational_db_config'):
                db_config = config.get_relational_db_config()
                return db_config.get('connection_string')
        except Exception as e:
            logger.warning(f"Could not get async connection string from config: {e}")
        
        # Fallback to converting sync URL to async URL
        sync_url = self._get_database_url()
        return sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    def initialize(self) -> None:
        """Initialize database engine and session factory."""
        try:
            # Create sync engine with connection pooling
            self.engine = create_engine(
                self.database_url,
                poolclass=QueuePool,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600,  # Recycle connections after 1 hour
                echo=os.getenv("DB_ECHO", "false").lower() == "true"
            )
            
            # Create async engine
            self.async_engine = create_async_engine(
                self.async_database_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
                pool_recycle=3600,
                echo=os.getenv("DB_ECHO", "false").lower() == "true"
            )
            
            # Add connection event listeners
            event.listen(self.engine, "connect", self._on_connect)
            event.listen(self.engine, "checkout", self._on_checkout)
            
            # Create session factories
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine
            )
            
            self.AsyncSessionLocal = async_sessionmaker(
                bind=self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False
            )
            
            logger.info("Database connections initialized", 
                       sync_url=self.database_url,
                       async_url=self.async_database_url)
            
        except Exception as e:
            logger.error("Failed to initialize database connection", error=str(e))
            raise
    
    def _on_connect(self, dbapi_connection, connection_record):
        """Handle new database connections."""
        logger.debug("New database connection established")
    
    def _on_checkout(self, dbapi_connection, connection_record, connection_proxy):
        """Handle connection checkout from pool."""
        logger.debug("Database connection checked out from pool")
    
    @asynccontextmanager
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Get an async database session with automatic cleanup."""
        if not self.AsyncSessionLocal:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        
        async with self.AsyncSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error("Async database session error", error=str(e))
                raise
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """Get a database session with automatic cleanup."""
        if not self.SessionLocal:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("Database session error", error=str(e))
            raise
        finally:
            session.close()
    
    def create_all_tables(self) -> None:
        """Create all database tables."""
        if not self.engine:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("All database tables created successfully")
        except Exception as e:
            logger.error("Failed to create database tables", error=str(e))
            raise
    
    def drop_all_tables(self) -> None:
        """Drop all database tables. Use with caution!"""
        if not self.engine:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        
        try:
            Base.metadata.drop_all(bind=self.engine)
            logger.warning("All database tables dropped")
        except Exception as e:
            logger.error("Failed to drop database tables", error=str(e))
            raise
    
    def close(self) -> None:
        """Close database connections and cleanup."""
        if self.engine:
            self.engine.dispose()
        if self.async_engine:
            self.async_engine.dispose()
        logger.info("Database connections closed")


# Global database manager instance
db_manager = DatabaseManager()


def get_database_session() -> Generator[Session, None, None]:
    """Dependency function for FastAPI to get database sessions."""
    with db_manager.get_session() as session:
        yield session


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency function for FastAPI to get async database sessions."""
    async with db_manager.get_async_session() as session:
        yield session


def init_database() -> None:
    """Initialize the database connection."""
    db_manager.initialize()


def create_tables() -> None:
    """Create all database tables."""
    db_manager.create_all_tables()


def close_database() -> None:
    """Close database connections."""
    db_manager.close()


@contextmanager
def get_database_connection():
    """Get a raw database connection for direct SQL operations."""
    # Parse database URL to get connection parameters
    url = db_manager.database_url
    # Extract connection parameters from URL
    # Format: postgresql://username:password@host:port/database
    import re
    match = re.match(r'postgresql://([^:]+):([^@]*)@([^:]+):(\d+)/(.+)', url)
    if not match:
        raise ValueError(f"Invalid database URL format: {url}")

    username, password, host, port, database = match.groups()

    conn = None
    try:
        conn = psycopg2.connect(
            host=host,
            port=int(port),
            database=database,
            user=username,
            password=password
        )
        yield conn
        conn.commit()
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error("Database connection error", error=str(e))
        raise
    finally:
        if conn:
            conn.close()


# Async connection pool for Celery workers and background tasks
# This provides better performance than SQLAlchemy for raw SQL operations
_async_pool = None
_async_pool_lock = None


def _get_db_params() -> dict:
    """Extract database connection parameters from URL."""
    import re
    url = db_manager.database_url
    # Handle both postgresql:// and postgresql+driver:// formats
    match = re.match(
        r'postgresql(?:\+\w+)?://([^:]+):([^@]*)@([^:]+):(\d+)/(.+)',
        url
    )
    if not match:
        raise ValueError(f"Invalid database URL format: {url}")

    username, password, host, port, database = match.groups()
    return {
        'host': host,
        'port': int(port),
        'database': database,
        'user': username,
        'password': password
    }


async def get_async_connection():
    """
    Get a fresh asyncpg connection for background tasks.

    This creates a new connection each time, which is safer for Celery workers
    where each asyncio.run() creates a new event loop. The connection is
    NOT automatically closed - caller must close it.

    Usage:
        conn = await get_async_connection()
        try:
            await conn.execute("SELECT 1")
        finally:
            await conn.close()

    Returns:
        asyncpg.Connection: A database connection
    """
    import asyncpg

    params = _get_db_params()
    conn = await asyncpg.connect(
        host=params['host'],
        port=params['port'],
        database=params['database'],
        user=params['user'],
        password=params['password'],
        timeout=60
    )
    return conn


async def get_async_pool():
    """
    Get or create a shared asyncpg connection pool for background tasks.

    This pool is optimized for Celery workers and other background processes
    that need high-performance async database access without ORM overhead.

    Returns:
        asyncpg.Pool: A connection pool for async database operations
    """
    import asyncio

    import asyncpg

    global _async_pool, _async_pool_lock

    # Initialize lock if needed (thread-safe for first access)
    if _async_pool_lock is None:
        _async_pool_lock = asyncio.Lock()

    async with _async_pool_lock:
        if _async_pool is None:
            params = _get_db_params()
            _async_pool = await asyncpg.create_pool(
                host=params['host'],
                port=params['port'],
                database=params['database'],
                user=params['user'],
                password=params['password'],
                min_size=2,
                max_size=10,
                max_inactive_connection_lifetime=300,
                command_timeout=60
            )
            logger.info("Async connection pool created",
                       host=params['host'],
                       database=params['database'])

    return _async_pool


async def close_async_pool():
    """Close the async connection pool."""
    global _async_pool
    if _async_pool is not None:
        await _async_pool.close()
        _async_pool = None
        logger.info("Async connection pool closed")