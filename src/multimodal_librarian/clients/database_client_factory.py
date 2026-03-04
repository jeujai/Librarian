"""
Database Client Factory for Multimodal Librarian

This module provides a factory for creating database clients that work with both
local development environments (Neo4j, Milvus, PostgreSQL) and AWS production
environments (Neptune, OpenSearch, RDS).

The factory implements the factory pattern to abstract database client creation
and provides environment-based client selection, caching, and lifecycle management.

Example Usage:
    ```python
    from multimodal_librarian.clients.database_client_factory import DatabaseClientFactory
    from multimodal_librarian.config.local_config import LocalDatabaseConfig
    
    # Create factory with local configuration
    config = LocalDatabaseConfig()
    factory = DatabaseClientFactory(config)
    
    # Get clients with consistent interfaces
    postgres_client = await factory.get_relational_client()
    vector_client = await factory.get_vector_client()
    graph_client = await factory.get_graph_client()
    
    # Use clients with same API regardless of backend
    await postgres_client.connect()
    results = await postgres_client.execute_query("SELECT * FROM users")
    ```

Architecture:
    The factory supports multiple database backends:
    - Local Development: PostgreSQL + Neo4j + Milvus
    - AWS Production: RDS PostgreSQL + Neptune + OpenSearch
    
    All clients implement the same protocol interfaces, ensuring consistent
    behavior across environments.
"""

import asyncio
import logging
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional, Type, Union

from .protocols import (
    ConfigurationError,
    ConnectionError,
    DatabaseClientError,
    GraphStoreClient,
    RelationalStoreClient,
    ValidationError,
    VectorStoreClient,
)

logger = logging.getLogger(__name__)

# Type aliases for better code readability
DatabaseType = Literal["local", "aws"]
ClientType = Literal["relational", "vector", "graph"]
HealthStatus = Dict[str, Any]
FactoryStats = Dict[str, Any]


@dataclass
class DatabaseConfig:
    """
    Base configuration class for database settings.
    
    This class defines the common interface that both LocalDatabaseConfig
    and AWSNativeConfig should implement or be compatible with.
    """
    database_type: DatabaseType
    environment: str = "development"
    
    # Connection settings
    connection_timeout: int = 60
    query_timeout: int = 30
    max_retries: int = 3
    
    # Feature flags
    enable_relational_db: bool = True
    enable_vector_search: bool = True
    enable_graph_db: bool = True
    
    # Performance settings
    connection_pooling: bool = True
    query_caching: bool = True
    enable_query_logging: bool = False


class DatabaseClientFactory:
    """
    Factory for creating and managing database clients across environments.
    
    This factory provides a unified interface for creating database clients
    that work with both local development and AWS production environments.
    It handles client caching, lifecycle management, and configuration validation.
    
    Features:
    - Environment-based client selection (local vs AWS)
    - Client caching and reuse for performance
    - Automatic connection management and cleanup
    - Health checking across all database services
    - Configuration validation and error handling
    - Graceful degradation when services are unavailable
    
    Thread Safety:
        This factory is thread-safe for client creation and caching.
        Individual clients should handle their own thread safety.
    """
    
    def __init__(self, config: Union[DatabaseConfig, Any]):
        """
        Initialize the database client factory.
        
        Args:
            config: Database configuration object (LocalDatabaseConfig or AWSNativeConfig)
                   Must have database_type attribute to determine environment
                   
        Raises:
            ConfigurationError: If configuration is invalid or missing required fields
            ValidationError: If configuration values are invalid
        """
        self.config = config
        self._validate_config()
        
        # Client cache for reuse
        self._clients: Dict[ClientType, Any] = {}
        self._client_locks: Dict[ClientType, asyncio.Lock] = {
            "relational": asyncio.Lock(),
            "vector": asyncio.Lock(),
            "graph": asyncio.Lock()
        }
        
        # Factory state
        self._initialized = False
        self._closed = False
        
        logger.info(
            f"Initialized DatabaseClientFactory for {self.config.database_type} environment"
        )
    
    def _validate_config(self) -> None:
        """
        Validate the provided configuration.
        
        Raises:
            ConfigurationError: If configuration is invalid
            ValidationError: If configuration values are invalid
        """
        if not hasattr(self.config, 'database_type'):
            raise ConfigurationError(
                "Configuration must have 'database_type' attribute",
                config_key="database_type"
            )
        
        if self.config.database_type not in ["local", "aws"]:
            raise ValidationError(
                f"Invalid database_type: {self.config.database_type}. Must be 'local' or 'aws'",
                field_name="database_type",
                field_value=self.config.database_type,
                validation_rule="Must be 'local' or 'aws'"
            )
        
        # Validate timeout settings
        if hasattr(self.config, 'connection_timeout'):
            if self.config.connection_timeout <= 0:
                raise ValidationError(
                    "Connection timeout must be positive",
                    field_name="connection_timeout",
                    field_value=self.config.connection_timeout
                )
        
        if hasattr(self.config, 'query_timeout'):
            if self.config.query_timeout <= 0:
                raise ValidationError(
                    "Query timeout must be positive",
                    field_name="query_timeout", 
                    field_value=self.config.query_timeout
                )
        
        logger.debug(f"Configuration validated for {self.config.database_type} environment")
    
    async def get_relational_client(self) -> RelationalStoreClient:
        """
        Get a relational database client (PostgreSQL).
        
        This method returns a client that implements the RelationalStoreClient protocol.
        For local environments, it returns a LocalPostgreSQLClient.
        For AWS environments, it returns an AWSPostgreSQLClient.
        
        The client is cached for reuse and automatically connected on first use.
        
        Returns:
            RelationalStoreClient: PostgreSQL client for the configured environment
            
        Raises:
            ConfigurationError: If relational database is disabled or misconfigured
            ConnectionError: If client creation or connection fails
            
        Example:
            ```python
            client = await factory.get_relational_client()
            async with client.get_async_session() as session:
                result = await session.execute(text("SELECT COUNT(*) FROM users"))
                count = result.scalar()
                print(f"Total users: {count}")
            ```
        """
        if self._closed:
            raise DatabaseClientError("Factory has been closed")
        
        # Check if relational database is enabled
        if hasattr(self.config, 'enable_relational_db') and not self.config.enable_relational_db:
            raise ConfigurationError(
                "Relational database is disabled in configuration",
                config_key="enable_relational_db",
                config_value="False"
            )
        
        async with self._client_locks["relational"]:
            if "relational" not in self._clients:
                try:
                    if self.config.database_type == "local":
                        client = await self._create_local_postgres_client()
                    else:  # aws
                        client = await self._create_aws_postgres_client()
                    
                    # Connect the client
                    await client.connect()
                    self._clients["relational"] = client
                    
                    logger.info(f"Created and connected {self.config.database_type} PostgreSQL client")
                    
                except Exception as e:
                    logger.error(f"Failed to create relational client: {e}")
                    raise ConnectionError(
                        f"Failed to create {self.config.database_type} PostgreSQL client",
                        database_type="postgresql",
                        original_exception=e
                    )
            
            return self._clients["relational"]
    
    async def get_vector_client(self) -> VectorStoreClient:
        """
        Get a vector database client (Milvus or OpenSearch).
        
        This method returns a client that implements the VectorStoreClient protocol.
        For local environments, it returns a MilvusClient.
        For AWS environments, it returns an OpenSearchClient.
        
        The client is cached for reuse and automatically connected on first use.
        
        Returns:
            VectorStoreClient: Vector database client for the configured environment
            
        Raises:
            ConfigurationError: If vector search is disabled or misconfigured
            ConnectionError: If client creation or connection fails
            
        Example:
            ```python
            client = await factory.get_vector_client()
            
            # Store document embeddings
            chunks = [
                {
                    "content": "Machine learning is...",
                    "metadata": {"source_id": "doc1", "chunk_index": 0}
                }
            ]
            await client.store_embeddings(chunks)
            
            # Search for similar content
            results = await client.semantic_search("What is AI?", top_k=5)
            ```
        """
        if self._closed:
            raise DatabaseClientError("Factory has been closed")
        
        # Check if vector search is enabled
        if hasattr(self.config, 'enable_vector_search') and not self.config.enable_vector_search:
            raise ConfigurationError(
                "Vector search is disabled in configuration",
                config_key="enable_vector_search",
                config_value="False"
            )
        
        async with self._client_locks["vector"]:
            if "vector" not in self._clients:
                try:
                    if self.config.database_type == "local":
                        client = await self._create_local_milvus_client()
                    else:  # aws
                        client = await self._create_aws_opensearch_client()
                    
                    # Connect the client
                    await client.connect()
                    self._clients["vector"] = client
                    
                    logger.info(f"Created and connected {self.config.database_type} vector client")
                    
                except Exception as e:
                    logger.error(f"Failed to create vector client: {e}")
                    raise ConnectionError(
                        f"Failed to create {self.config.database_type} vector client",
                        database_type="vector",
                        original_exception=e
                    )
            
            return self._clients["vector"]
    
    async def get_graph_client(self) -> GraphStoreClient:
        """
        Get a graph database client (Neo4j or Neptune).
        
        This method returns a client that implements the GraphStoreClient protocol.
        For local environments, it returns a Neo4jClient.
        For AWS environments, it returns a NeptuneClient.
        
        The client is cached for reuse and automatically connected on first use.
        
        Returns:
            GraphStoreClient: Graph database client for the configured environment
            
        Raises:
            ConfigurationError: If graph database is disabled or misconfigured
            ConnectionError: If client creation or connection fails
            
        Example:
            ```python
            client = await factory.get_graph_client()
            
            # Create nodes and relationships
            user_id = await client.create_node(
                labels=["User"], 
                properties={"name": "Alice", "email": "alice@example.com"}
            )
            
            doc_id = await client.create_node(
                labels=["Document"],
                properties={"title": "ML Guide", "type": "pdf"}
            )
            
            rel_id = await client.create_relationship(
                user_id, doc_id, "OWNS", {"created_at": "2023-01-01"}
            )
            ```
        """
        if self._closed:
            raise DatabaseClientError("Factory has been closed")
        
        # Check if graph database is enabled
        if hasattr(self.config, 'enable_graph_db') and not self.config.enable_graph_db:
            raise ConfigurationError(
                "Graph database is disabled in configuration",
                config_key="enable_graph_db",
                config_value="False"
            )
        
        async with self._client_locks["graph"]:
            if "graph" not in self._clients:
                try:
                    if self.config.database_type == "local":
                        client = await self._create_local_neo4j_client()
                    else:  # aws
                        client = await self._create_aws_neptune_client()
                    
                    # Connect the client
                    await client.connect()
                    self._clients["graph"] = client
                    
                    logger.info(f"Created and connected {self.config.database_type} graph client")
                    
                except Exception as e:
                    logger.error(f"Failed to create graph client: {e}")
                    raise ConnectionError(
                        f"Failed to create {self.config.database_type} graph client",
                        database_type="graph",
                        original_exception=e
                    )
            
            return self._clients["graph"]
    
    async def _create_local_postgres_client(self) -> RelationalStoreClient:
        """Create a local PostgreSQL client."""
        from .local_postgresql_client import LocalPostgreSQLClient

        # Build connection parameters from config
        connection_params = {
            "host": getattr(self.config, 'postgres_host', 'localhost'),
            "port": getattr(self.config, 'postgres_port', 5432),
            "database": getattr(self.config, 'postgres_db', 'multimodal_librarian'),
            "user": getattr(self.config, 'postgres_user', 'ml_user'),
            "password": getattr(self.config, 'postgres_password', 'ml_password'),
            "pool_size": getattr(self.config, 'postgres_pool_size', 10),
            "max_overflow": getattr(self.config, 'postgres_max_overflow', 20),
            "pool_timeout": getattr(self.config, 'connection_timeout', 60),
            "pool_recycle": getattr(self.config, 'postgres_pool_recycle', 3600),
        }
        
        return LocalPostgreSQLClient(**connection_params)
    
    async def _create_aws_postgres_client(self) -> RelationalStoreClient:
        """Create an AWS RDS PostgreSQL client."""
        # Import AWS client when needed to avoid import errors in local development
        try:
            from .aws_postgresql_client import AWSPostgreSQLClient
        except ImportError:
            raise ConfigurationError(
                "AWS PostgreSQL client not available. Install AWS dependencies.",
                config_key="database_type",
                config_value="aws"
            )
        
        # Get AWS-specific configuration
        aws_config = {
            "endpoint": getattr(self.config, 'rds_endpoint', None),
            "region": getattr(self.config, 'region', 'us-east-1'),
            "secret_name": getattr(self.config, 'rds_secret_name', None),
            "database": getattr(self.config, 'rds_database', 'multimodal_librarian'),
            "connection_timeout": getattr(self.config, 'connection_timeout', 60),
            "max_retries": getattr(self.config, 'max_retries', 3),
        }
        
        return AWSPostgreSQLClient(**aws_config)
    
    async def _create_local_milvus_client(self) -> VectorStoreClient:
        """Create a local Milvus client."""
        from .milvus_client import MilvusClient

        # Build connection parameters from config
        # Note: MilvusClient uses 'timeout' not 'connection_timeout'
        connection_params = {
            "host": getattr(self.config, 'milvus_host', 'localhost'),
            "port": getattr(self.config, 'milvus_port', 19530),
            "user": getattr(self.config, 'milvus_user', ''),
            "password": getattr(self.config, 'milvus_password', ''),
            "timeout": float(getattr(self.config, 'connection_timeout', 60)),
            "retry_attempts": getattr(self.config, 'max_retries', 3),
        }
        
        return MilvusClient(**connection_params)
    
    async def _create_aws_opensearch_client(self) -> VectorStoreClient:
        """Create an AWS OpenSearch client."""
        try:
            from .opensearch_client import OpenSearchClient
        except ImportError:
            raise ConfigurationError(
                "AWS OpenSearch client not available. Install AWS dependencies.",
                config_key="database_type",
                config_value="aws"
            )
        
        # Get AWS-specific configuration
        aws_config = {
            "endpoint": getattr(self.config, 'opensearch_endpoint', None),
            "region": getattr(self.config, 'region', 'us-east-1'),
            "secret_name": getattr(self.config, 'opensearch_secret_name', None),
            "connection_timeout": getattr(self.config, 'connection_timeout', 60),
            "max_retries": getattr(self.config, 'max_retries', 3),
        }
        
        return OpenSearchClient(**aws_config)
    
    async def _create_local_neo4j_client(self) -> GraphStoreClient:
        """Create a local Neo4j client."""
        from .neo4j_client import Neo4jClient

        # Build connection parameters from config
        # Note: Neo4jClient uses 'connection_acquisition_timeout' not 'connection_timeout'
        connection_params = {
            "uri": f"bolt://{getattr(self.config, 'neo4j_host', 'localhost')}:{getattr(self.config, 'neo4j_port', 7687)}",
            "user": getattr(self.config, 'neo4j_user', 'neo4j'),
            "password": getattr(self.config, 'neo4j_password', 'ml_password'),
            "connection_acquisition_timeout": getattr(self.config, 'connection_timeout', 60),
            "max_connection_lifetime": getattr(self.config, 'neo4j_max_connection_lifetime', 3600),
            "max_connection_pool_size": getattr(self.config, 'neo4j_pool_size', 100),
        }
        
        return Neo4jClient(**connection_params)
    
    async def _create_aws_neptune_client(self) -> GraphStoreClient:
        """Create an AWS Neptune client."""
        try:
            from .neptune_client import NeptuneClient
        except ImportError:
            raise ConfigurationError(
                "AWS Neptune client not available. Install AWS dependencies.",
                config_key="database_type",
                config_value="aws"
            )
        
        # Get AWS-specific configuration
        aws_config = {
            "endpoint": getattr(self.config, 'neptune_endpoint', None),
            "region": getattr(self.config, 'region', 'us-east-1'),
            "secret_name": getattr(self.config, 'neptune_secret_name', None),
            "connection_timeout": getattr(self.config, 'connection_timeout', 60),
            "max_retries": getattr(self.config, 'max_retries', 3),
        }
        
        return NeptuneClient(**aws_config)
    
    async def health_check(self) -> HealthStatus:
        """
        Perform comprehensive health check on all database services.
        
        This method checks the health of all enabled database services and
        returns a comprehensive status report. It's useful for monitoring
        and debugging database connectivity issues.
        
        Returns:
            Dictionary with health status for all services:
            - overall_status: "healthy" | "degraded" | "unhealthy"
            - database_type: "local" | "aws"
            - services: Individual service health status
            - timestamp: Health check timestamp
            - response_time: Total health check time
            
        Raises:
            DatabaseClientError: If factory has been closed
            
        Example:
            ```python
            health = await factory.health_check()
            print(f"Overall status: {health['overall_status']}")
            
            for service, status in health['services'].items():
                if status['status'] == 'healthy':
                    print(f"✓ {service}: OK ({status['response_time']:.3f}s)")
                else:
                    print(f"✗ {service}: {status.get('error', 'Unknown error')}")
            ```
        """
        if self._closed:
            raise DatabaseClientError("Factory has been closed")
        
        import time
        start_time = time.time()
        
        health_status = {
            "overall_status": "healthy",
            "database_type": self.config.database_type,
            "services": {},
            "timestamp": time.time(),
            "response_time": 0.0
        }
        
        # Check each enabled service
        services_to_check = []
        
        if getattr(self.config, 'enable_relational_db', True):
            services_to_check.append(("relational", self.get_relational_client))
        
        if getattr(self.config, 'enable_vector_search', True):
            services_to_check.append(("vector", self.get_vector_client))
        
        if getattr(self.config, 'enable_graph_db', True):
            services_to_check.append(("graph", self.get_graph_client))
        
        # Perform health checks concurrently
        async def check_service(service_name: str, get_client_func):
            try:
                service_start = time.time()
                client = await get_client_func()
                service_health = await client.health_check()
                service_time = time.time() - service_start
                
                # Normalize health status format
                if isinstance(service_health, bool):
                    service_health = {
                        "status": "healthy" if service_health else "unhealthy",
                        "response_time": service_time
                    }
                elif isinstance(service_health, dict):
                    service_health["response_time"] = service_time
                else:
                    service_health = {
                        "status": "unknown",
                        "response_time": service_time,
                        "raw_response": service_health
                    }
                
                return service_name, service_health
                
            except Exception as e:
                return service_name, {
                    "status": "unhealthy",
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "response_time": time.time() - service_start
                }
        
        # Run all health checks concurrently
        if services_to_check:
            health_results = await asyncio.gather(
                *[check_service(name, func) for name, func in services_to_check],
                return_exceptions=True
            )
            
            # Process results
            for result in health_results:
                if isinstance(result, Exception):
                    health_status["services"]["unknown"] = {
                        "status": "unhealthy",
                        "error": str(result),
                        "error_type": type(result).__name__
                    }
                    health_status["overall_status"] = "unhealthy"
                else:
                    service_name, service_health = result
                    health_status["services"][service_name] = service_health
                    
                    # Update overall status
                    if service_health["status"] == "unhealthy":
                        health_status["overall_status"] = "unhealthy"
                    elif service_health["status"] != "healthy" and health_status["overall_status"] == "healthy":
                        health_status["overall_status"] = "degraded"
        
        health_status["response_time"] = time.time() - start_time
        
        logger.info(
            f"Health check completed: {health_status['overall_status']} "
            f"({health_status['response_time']:.3f}s)"
        )
        
        return health_status
    
    def get_factory_stats(self) -> FactoryStats:
        """
        Get factory statistics and information.
        
        Returns:
            Dictionary with factory statistics:
            - database_type: Environment type (local/aws)
            - cached_clients: List of cached client types
            - initialized: Whether factory is initialized
            - closed: Whether factory is closed
            - configuration: Sanitized configuration info
        """
        return {
            "database_type": self.config.database_type,
            "cached_clients": list(self._clients.keys()),
            "initialized": self._initialized,
            "closed": self._closed,
            "configuration": {
                "enable_relational_db": getattr(self.config, 'enable_relational_db', True),
                "enable_vector_search": getattr(self.config, 'enable_vector_search', True),
                "enable_graph_db": getattr(self.config, 'enable_graph_db', True),
                "connection_timeout": getattr(self.config, 'connection_timeout', 60),
                "query_timeout": getattr(self.config, 'query_timeout', 30),
            }
        }
    
    async def close(self) -> None:
        """
        Close all database connections and clean up resources.
        
        This method should be called when the factory is no longer needed
        to ensure proper cleanup of database connections and resources.
        
        After calling this method, the factory should not be used until
        a new instance is created.
        
        Example:
            ```python
            factory = DatabaseClientFactory(config)
            try:
                # Use factory...
                client = await factory.get_relational_client()
                # ... do work ...
            finally:
                await factory.close()
            ```
        """
        if self._closed:
            return
        
        logger.info("Closing database client factory...")
        
        # Close all cached clients
        close_tasks = []
        for client_type, client in self._clients.items():
            if hasattr(client, 'disconnect'):
                close_tasks.append(client.disconnect())
            elif hasattr(client, 'close'):
                close_tasks.append(client.close())
        
        if close_tasks:
            try:
                await asyncio.gather(*close_tasks, return_exceptions=True)
            except Exception as e:
                logger.warning(f"Error during client cleanup: {e}")
        
        # Clear client cache
        self._clients.clear()
        self._closed = True
        
        logger.info("Database client factory closed successfully")
    
    @asynccontextmanager
    async def get_all_clients(self):
        """
        Context manager to get all enabled clients at once.
        
        This is a convenience method for getting all enabled database clients
        in a single context manager. Clients are automatically cleaned up
        when the context exits.
        
        Yields:
            Dictionary with client instances for enabled services:
            - relational: RelationalStoreClient (if enabled)
            - vector: VectorStoreClient (if enabled)  
            - graph: GraphStoreClient (if enabled)
            
        Example:
            ```python
            async with factory.get_all_clients() as clients:
                if 'relational' in clients:
                    users = await clients['relational'].execute_query("SELECT * FROM users")
                
                if 'vector' in clients:
                    results = await clients['vector'].semantic_search("machine learning")
                
                if 'graph' in clients:
                    nodes = await clients['graph'].execute_query("MATCH (n) RETURN count(n)")
            ```
        """
        clients = {}
        
        try:
            # Get all enabled clients
            if getattr(self.config, 'enable_relational_db', True):
                clients['relational'] = await self.get_relational_client()
            
            if getattr(self.config, 'enable_vector_search', True):
                clients['vector'] = await self.get_vector_client()
            
            if getattr(self.config, 'enable_graph_db', True):
                clients['graph'] = await self.get_graph_client()
            
            yield clients
            
        except Exception as e:
            logger.error(f"Error in get_all_clients context manager: {e}")
            raise
        finally:
            # Cleanup is handled by the factory's close method
            # Individual clients remain cached for reuse
            pass
    
    def __repr__(self) -> str:
        """Return string representation of the factory."""
        return (
            f"DatabaseClientFactory("
            f"database_type='{self.config.database_type}', "
            f"cached_clients={list(self._clients.keys())}, "
            f"closed={self._closed})"
        )


# Global factory instance for dependency injection
_global_factory: Optional[DatabaseClientFactory] = None


def get_database_factory(config: Optional[Union[DatabaseConfig, Any]] = None) -> DatabaseClientFactory:
    """
    Get or create global database factory instance.
    
    This function provides a global factory instance for use in dependency
    injection systems. It creates a new factory if one doesn't exist or
    if a new configuration is provided.
    
    Args:
        config: Optional database configuration. If not provided, uses existing
               factory or raises error if no factory exists.
               
    Returns:
        DatabaseClientFactory: Global factory instance
        
    Raises:
        ConfigurationError: If no config provided and no existing factory
        
    Example:
        ```python
        # Initialize global factory
        config = LocalDatabaseConfig()
        factory = get_database_factory(config)
        
        # Later, get existing factory
        factory = get_database_factory()  # Uses existing instance
        ```
    """
    global _global_factory
    
    if config is not None:
        # Create new factory with provided config
        _global_factory = DatabaseClientFactory(config)
    elif _global_factory is None:
        raise ConfigurationError(
            "No database factory exists and no configuration provided",
            config_key="database_factory"
        )
    
    return _global_factory


async def close_global_factory() -> None:
    """
    Close the global database factory instance.
    
    This function closes the global factory and cleans up all its resources.
    It should be called during application shutdown.
    
    Example:
        ```python
        # During application shutdown
        await close_global_factory()
        ```
    """
    global _global_factory
    
    if _global_factory is not None:
        await _global_factory.close()
        _global_factory = None


def reset_global_factory() -> None:
    """
    Reset the global factory instance (useful for testing).
    
    This function clears the global factory reference without closing it.
    Use this in tests to ensure a clean state between test runs.
    
    Warning:
        This does not close existing connections. Use close_global_factory()
        for proper cleanup.
    """
    global _global_factory
    _global_factory = None