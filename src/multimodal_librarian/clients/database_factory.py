"""
Database Client Factory for Multimodal Librarian

This module provides a factory for creating database clients that work with both
local development and AWS production environments. It supports automatic environment
detection and provides unified interfaces for all database operations.

The factory implements the database abstraction layer that allows seamless switching
between local development (PostgreSQL, Neo4j, Milvus) and AWS production 
(RDS PostgreSQL, Neptune, OpenSearch) environments.

Example Usage:
    ```python
    from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
    from multimodal_librarian.config.config_factory import get_database_config
    
    # Get configuration (auto-detects environment)
    config = get_database_config()
    
    # Create factory with configuration
    factory = DatabaseClientFactory(config)
    
    # Get database clients
    postgres_client = factory.get_relational_client()
    graph_client = factory.get_graph_client()
    vector_client = factory.get_vector_client()
    
    # Use unified interfaces
    await postgres_client.connect()
    results = await postgres_client.execute_query("SELECT * FROM users")
    
    await graph_client.connect()
    nodes = await graph_client.execute_query("MATCH (n:User) RETURN n")
    
    await vector_client.connect()
    similar = await vector_client.semantic_search("machine learning", top_k=5)
    ```

Environment Support:
    - Local Development: PostgreSQL + Neo4j + Milvus + Redis
    - AWS Production: RDS PostgreSQL + Neptune + OpenSearch + ElastiCache
    
Thread Safety:
    The factory is thread-safe. Individual clients may have their own
    thread safety characteristics - refer to client documentation.
"""

import logging
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Dict, List, Optional, Protocol, Union, runtime_checkable

logger = logging.getLogger(__name__)


class DatabaseClientError(Exception):
    """Raised when database client operations fail."""
    pass


class DatabaseClientFactory:
    """
    Factory for creating database clients based on configuration.
    
    This factory provides a unified interface for creating database clients
    that work with both local development and AWS production environments.
    It handles environment detection, connection management, and provides
    consistent interfaces across different database backends.
    
    The factory supports:
        - Automatic environment detection and client selection
        - Connection pooling and lifecycle management
        - Health monitoring and error handling
        - Graceful degradation when services are unavailable
        - Configuration validation and connection string generation
    
    Configuration Types:
        - LocalDatabaseConfig: For local development with Docker services
        - AWSNativeConfig: For AWS production with managed services
    """
    
    def __init__(self, config: Union["LocalDatabaseConfig", "AWSNativeConfig"]):
        """
        Initialize the database client factory.
        
        Args:
            config: Database configuration object (LocalDatabaseConfig or AWSNativeConfig)
        """
        self.config = config
        self._relational_client = None
        self._graph_client = None
        self._vector_client = None
        self._cache_client = None
        
        # Determine backend type
        self.backend_type = getattr(config, 'database_type', 'unknown')
        if hasattr(config, 'get_backend_type'):
            self.backend_type = config.get_backend_type()
        
        logger.info(f"Initialized DatabaseClientFactory with {self.backend_type} backend")
    
    def get_relational_client(self):
        """
        Get the relational database client (PostgreSQL).
        
        Returns:
            PostgreSQL client implementing RelationalStoreClient protocol
            
        Raises:
            DatabaseClientError: If relational database is disabled or unavailable
        """
        if not getattr(self.config, 'enable_relational_db', True):
            raise DatabaseClientError("Relational database is disabled in configuration")
        
        if self._relational_client is None:
            if self.backend_type == "local":
                self._relational_client = self._create_local_postgresql_client()
            elif self.backend_type == "aws":
                self._relational_client = self._create_aws_postgresql_client()
            else:
                raise DatabaseClientError(f"Unknown backend type: {self.backend_type}")
            
            logger.info(f"Created {self.backend_type} PostgreSQL client")
        
        return self._relational_client
    
    def get_graph_client(self):
        """
        Get the graph database client (Neo4j or Neptune).
        
        Returns:
            Graph database client implementing GraphStoreClient protocol
            
        Raises:
            DatabaseClientError: If graph database is disabled or unavailable
        """
        if not getattr(self.config, 'enable_graph_db', True):
            raise DatabaseClientError("Graph database is disabled in configuration")
        
        if self._graph_client is None:
            if self.backend_type == "local":
                self._graph_client = self._create_local_neo4j_client()
            elif self.backend_type == "aws":
                self._graph_client = self._create_aws_neptune_client()
            else:
                raise DatabaseClientError(f"Unknown backend type: {self.backend_type}")
            
            logger.info(f"Created {self.backend_type} graph database client")
        
        return self._graph_client
    
    def get_vector_client(self):
        """
        Get the vector database client (Milvus or OpenSearch).
        
        Returns:
            Vector database client implementing VectorStoreClient protocol
            
        Raises:
            DatabaseClientError: If vector search is disabled or unavailable
        """
        if not getattr(self.config, 'enable_vector_search', True):
            raise DatabaseClientError("Vector search is disabled in configuration")
        
        if self._vector_client is None:
            if self.backend_type == "local":
                self._vector_client = self._create_local_milvus_client()
            elif self.backend_type == "aws":
                self._vector_client = self._create_aws_opensearch_client()
            else:
                raise DatabaseClientError(f"Unknown backend type: {self.backend_type}")
            
            logger.info(f"Created {self.backend_type} vector database client")
        
        return self._vector_client
    
    def get_cache_client(self):
        """
        Get the cache client (Redis or ElastiCache).
        
        Returns:
            Cache client implementing CacheClient protocol
            
        Raises:
            DatabaseClientError: If caching is disabled or unavailable
        """
        if not getattr(self.config, 'enable_redis_cache', True):
            raise DatabaseClientError("Redis cache is disabled in configuration")
        
        if self._cache_client is None:
            if self.backend_type == "local":
                self._cache_client = self._create_local_redis_client()
            elif self.backend_type == "aws":
                self._cache_client = self._create_aws_elasticache_client()
            else:
                raise DatabaseClientError(f"Unknown backend type: {self.backend_type}")
            
            logger.info(f"Created {self.backend_type} cache client")
        
        return self._cache_client
    
    def _create_local_postgresql_client(self):
        """Create local PostgreSQL client with enhanced connection strings."""
        try:
            from .local_postgresql_client import LocalPostgreSQLClient

            # Get database configuration with connection strings
            db_config = self.config.get_relational_db_config()
            
            client = LocalPostgreSQLClient(
                host=db_config["host"],
                port=db_config["port"],
                database=db_config["database"],
                user=db_config["user"],
                password=db_config["password"],
                pool_size=db_config["pool_size"],
                max_overflow=db_config["max_overflow"],
                pool_recycle=db_config["pool_recycle"],
                echo=db_config.get("echo", False)
            )
            
            # Store connection strings for reference
            client.async_connection_string = db_config["connection_string"]
            client.sync_connection_string = db_config["sync_connection_string"]
            client.pooled_connection_string = db_config["connection_string_with_pool"]
            
            return client
            
        except ImportError as e:
            raise DatabaseClientError(
                f"Local PostgreSQL client not available: {e}. "
                "Ensure local development dependencies are installed."
            )
    
    def _create_local_neo4j_client(self):
        """Create local Neo4j client with enhanced connection strings."""
        try:
            from .neo4j_client import Neo4jClient

            # Get graph database configuration with connection strings
            graph_config = self.config.get_graph_db_config()
            
            client = Neo4jClient(
                uri=graph_config["uri"],
                user=graph_config["user"],
                password=graph_config["password"],
                database="neo4j",  # Default database for local Neo4j
                max_connection_lifetime=graph_config["max_connection_lifetime"],
                max_connection_pool_size=graph_config["pool_size"],
                connection_acquisition_timeout=graph_config["timeout"],
                encrypted=graph_config["encrypted"],
                trust=graph_config["trust"]
            )
            
            # Store connection URIs for reference
            client.bolt_uri = graph_config["uri"]
            client.neo4j_uri = graph_config["neo4j_uri"]
            client.http_uri = graph_config["http_uri"]
            client.https_uri = graph_config["https_uri"]
            
            return client
            
        except ImportError as e:
            raise DatabaseClientError(
                f"Local Neo4j client not available: {e}. "
                "Ensure Neo4j dependencies are installed."
            )
    
    def _create_local_milvus_client(self):
        """Create local Milvus client with enhanced connection configuration."""
        try:
            from .milvus_client import MilvusClient

            # Get vector database configuration with connection strings
            vector_config = self.config.get_vector_db_config()
            connection_config = vector_config["connection_config"]
            
            client = MilvusClient(
                host=connection_config["host"],
                port=connection_config["port"],
                user=connection_config["user"],
                password=connection_config["password"],
                timeout=connection_config["timeout"],
                retry_attempts=connection_config["retry_attempts"],
                embedding_model=vector_config["embedding_model"]
            )
            
            # Store connection information for reference
            client.connection_uri = vector_config["uri"]
            client.connection_config = connection_config
            client.default_collection = vector_config["default_collection"]
            client.embedding_dimension = vector_config["embedding_dimension"]
            
            return client
            
        except ImportError as e:
            raise DatabaseClientError(
                f"Local Milvus client not available: {e}. "
                "Ensure Milvus dependencies are installed."
            )
    
    def _create_local_redis_client(self):
        """Create local Redis client with enhanced connection configuration."""
        try:
            import redis.asyncio as redis

            # Get Redis configuration with connection strings
            redis_config = self.config.get_redis_config()
            connection_config = redis_config["connection_config"]
            
            # Create Redis client with connection pool
            client = redis.Redis(
                host=connection_config["host"],
                port=connection_config["port"],
                db=connection_config["db"],
                password=connection_config["password"],
                max_connections=connection_config["max_connections"],
                socket_timeout=connection_config["socket_timeout"],
                socket_connect_timeout=connection_config["socket_connect_timeout"],
                retry_on_timeout=connection_config["retry_on_timeout"],
                health_check_interval=connection_config["health_check_interval"]
            )
            
            # Store connection information for reference
            client.connection_string = redis_config["connection_string"]
            client.connection_string_no_auth = redis_config["connection_string_no_auth"]
            client.connection_config = connection_config
            
            return client
            
        except ImportError as e:
            raise DatabaseClientError(
                f"Redis client not available: {e}. "
                "Ensure Redis dependencies are installed."
            )
    
    def _create_aws_postgresql_client(self):
        """Create AWS RDS PostgreSQL client."""
        try:
            from .aws_postgresql_client import AWSPostgreSQLClient

            # Get AWS database configuration
            db_config = self.config.get_relational_db_config()
            
            return AWSPostgreSQLClient(
                endpoint=db_config["endpoint"],
                database=db_config["database"],
                port=db_config["port"],
                credentials_secret_arn=db_config["credentials_secret_arn"],
                region=self.config.aws_region
            )
            
        except ImportError as e:
            raise DatabaseClientError(
                f"AWS PostgreSQL client not available: {e}. "
                "Ensure AWS dependencies are installed."
            )
    
    def _create_aws_neptune_client(self):
        """Create AWS Neptune client."""
        try:
            from .neptune_client import NeptuneClient

            # Get AWS graph database configuration
            graph_config = self.config.get_graph_db_config()
            
            return NeptuneClient(
                endpoint=graph_config["endpoint"],
                region=self.config.aws_region,
                port=graph_config["port"]
            )
            
        except ImportError as e:
            raise DatabaseClientError(
                f"AWS Neptune client not available: {e}. "
                "Ensure AWS dependencies are installed."
            )
    
    def _create_aws_opensearch_client(self):
        """Create AWS OpenSearch client."""
        try:
            from .opensearch_client import OpenSearchClient

            # Get AWS vector database configuration
            vector_config = self.config.get_vector_db_config()
            
            client = OpenSearchClient()
            client.connect()  # OpenSearch client handles AWS configuration internally
            
            return client
            
        except ImportError as e:
            raise DatabaseClientError(
                f"AWS OpenSearch client not available: {e}. "
                "Ensure AWS dependencies are installed."
            )
    
    def _create_aws_elasticache_client(self):
        """Create AWS ElastiCache Redis client."""
        try:
            import redis.asyncio as redis

            # Get AWS cache configuration
            cache_config = self.config.get_redis_config()
            
            return redis.Redis(
                host=cache_config["endpoint"],
                port=cache_config["port"],
                ssl=cache_config.get("ssl", True),
                ssl_cert_reqs=None if cache_config.get("ssl", True) else "required"
            )
            
        except ImportError as e:
            raise DatabaseClientError(
                f"AWS ElastiCache client not available: {e}. "
                "Ensure Redis dependencies are installed."
            )
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on all enabled database services.
        
        Returns:
            Health check results for all services
        """
        results = {
            "overall_status": "healthy",
            "backend_type": self.backend_type,
            "services": {}
        }
        
        # Check relational database
        if getattr(self.config, 'enable_relational_db', True):
            try:
                client = self.get_relational_client()
                if hasattr(client, 'health_check'):
                    health = await client.health_check()
                    results["services"]["relational_db"] = health
                    if health.get("status") != "healthy":
                        results["overall_status"] = "degraded"
                else:
                    results["services"]["relational_db"] = {"status": "unknown", "error": "No health check method"}
                    results["overall_status"] = "degraded"
            except Exception as e:
                results["services"]["relational_db"] = {"status": "unhealthy", "error": str(e)}
                results["overall_status"] = "unhealthy"
        
        # Check graph database
        if getattr(self.config, 'enable_graph_db', True):
            try:
                client = self.get_graph_client()
                if hasattr(client, 'health_check'):
                    health = await client.health_check()
                    results["services"]["graph_db"] = health
                    if health.get("status") != "healthy":
                        results["overall_status"] = "degraded"
                else:
                    results["services"]["graph_db"] = {"status": "unknown", "error": "No health check method"}
                    results["overall_status"] = "degraded"
            except Exception as e:
                results["services"]["graph_db"] = {"status": "unhealthy", "error": str(e)}
                results["overall_status"] = "unhealthy"
        
        # Check vector database
        if getattr(self.config, 'enable_vector_search', True):
            try:
                client = self.get_vector_client()
                if hasattr(client, 'health_check'):
                    health = await client.health_check()
                    results["services"]["vector_db"] = health
                    if health.get("status") != "healthy":
                        results["overall_status"] = "degraded"
                else:
                    results["services"]["vector_db"] = {"status": "unknown", "error": "No health check method"}
                    results["overall_status"] = "degraded"
            except Exception as e:
                results["services"]["vector_db"] = {"status": "unhealthy", "error": str(e)}
                results["overall_status"] = "unhealthy"
        
        # Check cache
        if getattr(self.config, 'enable_redis_cache', True):
            try:
                client = self.get_cache_client()
                if hasattr(client, 'ping'):
                    await client.ping()
                    results["services"]["cache"] = {"status": "healthy"}
                else:
                    results["services"]["cache"] = {"status": "unknown", "error": "No ping method"}
                    results["overall_status"] = "degraded"
            except Exception as e:
                results["services"]["cache"] = {"status": "unhealthy", "error": str(e)}
                results["overall_status"] = "unhealthy"
        
        return results
    
    async def close_connections(self) -> None:
        """Close all database connections gracefully."""
        logger.info("Starting graceful shutdown of database connections...")
        
        clients = [
            ("relational", self._relational_client),
            ("graph", self._graph_client),
            ("vector", self._vector_client),
            ("cache", self._cache_client)
        ]
        
        shutdown_tasks = []
        
        for client_type, client in clients:
            if client:
                shutdown_tasks.append(self._shutdown_client(client_type, client))
        
        # Execute all shutdowns concurrently with timeout
        if shutdown_tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*shutdown_tasks, return_exceptions=True),
                    timeout=30.0
                )
            except asyncio.TimeoutError:
                logger.error("Database connection shutdown timed out after 30 seconds")
        
        # Clear client references
        self._relational_client = None
        self._graph_client = None
        self._vector_client = None
        self._cache_client = None
        
        logger.info("✅ All database connections closed gracefully")
    
    async def _shutdown_client(self, client_type: str, client) -> None:
        """Shutdown a single database client with proper error handling."""
        try:
            logger.debug(f"Shutting down {client_type} client...")
            
            # Try different shutdown methods based on client type
            if hasattr(client, 'disconnect'):
                await client.disconnect()
            elif hasattr(client, 'close'):
                if asyncio.iscoroutinefunction(client.close):
                    await client.close()
                else:
                    client.close()
            elif hasattr(client, 'quit'):
                if asyncio.iscoroutinefunction(client.quit):
                    await client.quit()
                else:
                    client.quit()
            elif hasattr(client, 'shutdown'):
                if asyncio.iscoroutinefunction(client.shutdown):
                    await client.shutdown()
                else:
                    client.shutdown()
            else:
                logger.warning(f"No shutdown method found for {client_type} client")
            
            logger.info(f"✅ {client_type} database connection closed")
            
        except Exception as e:
            logger.error(f"❌ Error closing {client_type} connection: {e}")
            # Don't re-raise - we want to continue shutting down other clients


# Global factory instance
_database_factory: Optional[DatabaseClientFactory] = None
_shutdown_handlers: List[callable] = []


def register_shutdown_handler(handler: callable) -> None:
    """Register a shutdown handler to be called during graceful shutdown."""
    _shutdown_handlers.append(handler)


async def graceful_shutdown() -> None:
    """Perform graceful shutdown of all database connections and handlers."""
    logger.info("🛑 Starting graceful database shutdown...")
    
    # Execute custom shutdown handlers first
    for handler in _shutdown_handlers:
        try:
            if asyncio.iscoroutinefunction(handler):
                await handler()
            else:
                handler()
        except Exception as e:
            logger.error(f"Error in shutdown handler: {e}")
    
    # Close database factory connections
    global _database_factory
    if _database_factory:
        await _database_factory.close_connections()
        _database_factory = None
    
    logger.info("✅ Database graceful shutdown completed")


def get_database_factory(config: Optional[Union["LocalDatabaseConfig", "AWSNativeConfig"]] = None) -> DatabaseClientFactory:
    """
    Get or create global database factory instance.
    
    Args:
        config: Optional database configuration. If not provided, will auto-detect.
        
    Returns:
        DatabaseClientFactory instance
    """
    global _database_factory
    
    if _database_factory is None or config is not None:
        if config is None:
            # Auto-detect configuration
            from ..config.config_factory import get_database_config
            config = get_database_config()
        
        _database_factory = DatabaseClientFactory(config)
    
    return _database_factory


@contextmanager
def get_relational_client(config: Optional[Union["LocalDatabaseConfig", "AWSNativeConfig"]] = None):
    """Context manager for relational database client."""
    factory = get_database_factory(config)
    client = factory.get_relational_client()
    try:
        yield client
    finally:
        # Connection cleanup is handled by the factory
        pass


@contextmanager
def get_graph_client(config: Optional[Union["LocalDatabaseConfig", "AWSNativeConfig"]] = None):
    """Context manager for graph database client."""
    factory = get_database_factory(config)
    client = factory.get_graph_client()
    try:
        yield client
    finally:
        # Connection cleanup is handled by the factory
        pass


@contextmanager
def get_vector_client(config: Optional[Union["LocalDatabaseConfig", "AWSNativeConfig"]] = None):
    """Context manager for vector database client."""
    factory = get_database_factory(config)
    client = factory.get_vector_client()
    try:
        yield client
    finally:
        # Connection cleanup is handled by the factory
        pass