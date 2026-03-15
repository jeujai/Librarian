"""
Neo4j Client for Local Development

This module provides a Neo4j client that implements the GraphStoreClient protocol
for local development environments. It provides connection pooling, transaction
management, and comprehensive error handling.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import neo4j
from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession, Driver, GraphDatabase
from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable, TransientError

from ..logging.query_logging_decorators import log_neo4j_queries
from .protocols import (
    ConnectionError,
    DatabaseMetadata,
    GraphPath,
    GraphStoreClient,
    HealthStatus,
    NodeProperties,
    QueryError,
    QueryParameters,
    RelationshipDirection,
    SchemaError,
    SearchResults,
    TimeoutError,
    TransactionError,
    ValidationError,
)

logger = logging.getLogger(__name__)


@log_neo4j_queries()
class Neo4jClient:
    """
    Neo4j client implementing GraphStoreClient protocol.
    
    This client provides a local Neo4j implementation with connection pooling,
    transaction management, and comprehensive error handling. It implements
    the GraphStoreClient protocol to ensure compatibility with the application's
    database abstraction layer.
    
    Features:
        - Async/await support for non-blocking operations
        - Connection pooling with configurable limits
        - Automatic retry logic for transient failures
        - Health monitoring and connection recovery
        - Transaction management with proper rollback
        - Query parameter sanitization and validation
        - Comprehensive error handling and logging
    
    Example:
        ```python
        client = Neo4jClient(
            uri="bolt://localhost:7687",
            user="neo4j", 
            password="password"
        )
        await client.connect()
        
        # Create a node
        node_id = await client.create_node(
            ["User", "Person"], 
            {"name": "Alice", "email": "alice@example.com"}
        )
        
        # Execute a query
        results = await client.execute_query(
            "MATCH (u:User) WHERE u.name = $name RETURN u",
            {"name": "Alice"}
        )
        
        await client.disconnect()
        ```
    """
    
    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "password",
        database: str = "neo4j",
        max_connection_lifetime: int = 3600,
        max_connection_pool_size: int = 50,
        connection_acquisition_timeout: int = 60,
        max_transaction_retry_time: int = 30,
        initial_address_resolution_timeout: int = 5,
        keep_alive: bool = True,
        encrypted: bool = False,
        trust: bool = True
    ):
        """
        Initialize Neo4j client with connection configuration.
        
        Args:
            uri: Neo4j connection URI (e.g., "bolt://localhost:7687")
            user: Username for authentication
            password: Password for authentication
            database: Database name to connect to (default: "neo4j")
            max_connection_lifetime: Maximum lifetime of connections in seconds
            max_connection_pool_size: Maximum number of connections in pool
            connection_acquisition_timeout: Timeout for acquiring connections
            max_transaction_retry_time: Maximum time to retry transactions
            initial_address_resolution_timeout: DNS resolution timeout
            keep_alive: Enable TCP keep-alive
            encrypted: Enable TLS encryption (False for local development)
            trust: Trust server certificates (True for local development)
        """
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        
        # Connection pool configuration
        self.max_connection_lifetime = max_connection_lifetime
        self.max_connection_pool_size = max_connection_pool_size
        self.connection_acquisition_timeout = connection_acquisition_timeout
        self.max_transaction_retry_time = max_transaction_retry_time
        self.initial_address_resolution_timeout = initial_address_resolution_timeout
        self.keep_alive = keep_alive
        self.encrypted = encrypted
        self.trust = trust
        
        # Connection state
        self.driver: Optional[AsyncDriver] = None
        self._is_connected = False
        self._indexes_ensured = False  # Track if indexes have been created (skip on reconnect)
        self._last_health_check = 0
        self._health_check_interval = 30  # seconds
        self._connection_attempts = 0
        self._max_connection_attempts = 3
        self._keepalive_task: Optional[asyncio.Task] = None
        self._keepalive_interval = 15  # seconds - ping Neo4j to prevent TCP transport closing
        
        logger.info(f"Initialized Neo4j client for {uri}")
    
    async def connect(self) -> None:
        """
        Establish connection to the Neo4j database.
        
        This method creates an async driver with connection pooling and verifies
        connectivity. It implements retry logic for transient connection failures.
        
        Raises:
            ConnectionError: If connection cannot be established after retries
            ConfigurationError: If Neo4j configuration is invalid
        """
        if self._is_connected and self.driver:
            logger.debug("Neo4j client already connected")
            return
        
        self._connection_attempts = 0
        
        while self._connection_attempts < self._max_connection_attempts:
            try:
                self._connection_attempts += 1
                
                # Create and verify connection
                self.driver = await self._create_connection_and_verify()
                
                self._is_connected = True
                self._connection_attempts = 0
                
                logger.info(f"Successfully connected to Neo4j at {self.uri}")
                logger.debug(f"Connection pool size: {self.max_connection_pool_size}")
                
                # Only ensure indexes on first connect, not on reconnects.
                # Running CREATE FULLTEXT INDEX on reconnect can temporarily
                # make the index unavailable, causing queries to return empty.
                if not self._indexes_ensured:
                    await self.ensure_indexes()
                    self._indexes_ensured = True
                else:
                    logger.debug("Skipping ensure_indexes on reconnect (already ensured)")
                
                # Start background keepalive to prevent TCP transport closing
                self._start_keepalive()
                return
                
            except (ServiceUnavailable, AuthError) as e:
                error_msg = f"Neo4j connection failed (attempt {self._connection_attempts}/{self._max_connection_attempts}): {e}"
                
                if self._connection_attempts >= self._max_connection_attempts:
                    logger.error(error_msg)
                    raise ConnectionError(
                        f"Failed to connect to Neo4j after {self._max_connection_attempts} attempts",
                        database_type="neo4j",
                        host=self.uri,
                        database_name=self.database,
                        original_exception=e
                    )
                else:
                    logger.warning(error_msg)
                    # Exponential backoff
                    await asyncio.sleep(2 ** self._connection_attempts)
                    
            except Exception as e:
                logger.error(f"Unexpected error connecting to Neo4j: {e}")
                raise ConnectionError(
                    f"Unexpected connection error: {e}",
                    database_type="neo4j",
                    host=self.uri,
                    database_name=self.database,
                    original_exception=e
                )
    
    async def disconnect(self) -> None:
        """
        Close connection to the Neo4j database.
        
        This method closes the driver and all connections in the pool.
        After calling this method, the client should not be used until
        connect() is called again.
        
        Raises:
            ConnectionError: If there are issues closing connections
        """
        self._stop_keepalive()
        
        if not self.driver:
            logger.debug("Neo4j client not connected, nothing to disconnect")
            return
        
        try:
            await self.driver.close()
            self.driver = None
            self._is_connected = False
            logger.info("Disconnected from Neo4j")
            
        except Exception as e:
            logger.error(f"Error disconnecting from Neo4j: {e}")
            raise ConnectionError(
                f"Failed to disconnect: {e}",
                database_type="neo4j",
                original_exception=e
            )
    
    async def close(self) -> None:
        """Close the Neo4j connection (alias for disconnect)."""
        await self.disconnect()
    
    async def ensure_indexes(self) -> None:
        """
        Ensure required indexes and constraints exist in the database.
        
        This method creates the necessary indexes for optimal query performance,
        including full-text indexes for KG-guided retrieval query decomposition.
        Uses IF NOT EXISTS to be idempotent - safe to call multiple times.
        
        The indexes created are:
        - concept_name_fulltext: Full-text index on Concept.name for query decomposition
        - concept_id_index: Index on Concept.concept_id for fast lookups
        - concept_source_document_index: Index on Concept.source_document for document queries
        - concept_type_index: Index on Concept.type for filtering
        - document_id_index: Index on Document.document_id for document lookups
        - concept_id_unique: Unique constraint on Concept.concept_id
        - chunk_id_unique: Unique constraint on Chunk.chunk_id for graph-native chunk relationships
        - chunk_source_id: Index on Chunk.source_id for per-document lookups
        
        Raises:
            SchemaError: If index creation fails
            ConnectionError: If database connection is lost
        """
        if not self._is_connected or not self.driver:
            logger.warning("Cannot ensure indexes - not connected to Neo4j")
            return
        
        index_statements = [
            # Full-text index for query decomposition (KG-guided retrieval)
            "CREATE FULLTEXT INDEX concept_name_fulltext IF NOT EXISTS FOR (c:Concept) ON EACH [c.name]",
            # Standard indexes for performance
            "CREATE INDEX concept_id_index IF NOT EXISTS FOR (c:Concept) ON (c.concept_id)",
            "CREATE INDEX concept_source_document_index IF NOT EXISTS FOR (c:Concept) ON (c.source_document)",
            "CREATE INDEX concept_type_index IF NOT EXISTS FOR (c:Concept) ON (c.type)",
            "CREATE INDEX document_id_index IF NOT EXISTS FOR (d:Document) ON (d.document_id)",
            # Unique constraint for data integrity
            "CREATE CONSTRAINT concept_id_unique IF NOT EXISTS FOR (c:Concept) REQUIRE c.concept_id IS UNIQUE",
            # Chunk node constraint and index for graph-native chunk relationships
            "CREATE CONSTRAINT chunk_id_unique IF NOT EXISTS FOR (ch:Chunk) REQUIRE ch.chunk_id IS UNIQUE",
            "CREATE INDEX chunk_source_id IF NOT EXISTS FOR (ch:Chunk) ON (ch.source_id)",
        ]
        
        # Vector index uses a separate procedure call (idempotent - Neo4j ignores if exists)
        vector_index_statement = (
            "CALL db.index.vector.createNodeIndex("
            "'concept_embedding_index', 'Concept', 'embedding', 768, 'cosine')"
        )
        
        try:
            async with self.driver.session(database=self.database) as session:
                for statement in index_statements:
                    try:
                        await session.run(statement)
                        logger.debug(f"Executed index statement: {statement[:60]}...")
                    except Exception as e:
                        # Log but don't fail - index might already exist in different form
                        logger.warning(f"Index creation warning (may already exist): {e}")
                
                # Create vector index for semantic concept matching
                try:
                    await session.run(vector_index_statement)
                    logger.debug("Created vector index: concept_embedding_index")
                except Exception as e:
                    # Index may already exist - this is expected and safe to ignore
                    logger.warning(f"Vector index creation warning (may already exist): {e}")
                
                logger.info("Neo4j indexes and constraints ensured")
                
        except Exception as e:
            logger.error(f"Failed to ensure Neo4j indexes: {e}")
            # Don't raise - indexes are important but not critical for basic operation
            # The application can still function, just with potentially slower queries
    
    async def health_check(self) -> HealthStatus:
        """
        Perform health check on the Neo4j database.
        
        This method verifies that the database is accessible and responsive.
        It includes connection pool status, query performance, and database
        statistics.
        
        Returns:
            Dictionary with health status information including:
            - status: "healthy" | "unhealthy" | "degraded"
            - response_time: Response time in seconds
            - node_count: Total number of nodes
            - relationship_count: Total number of relationships
            - memory_usage: Memory usage percentage (if available)
            - active_transactions: Number of active transactions
            - connection_pool_size: Current connection pool size
            
        Raises:
            ConnectionError: If health check cannot be performed
        """
        current_time = time.time()
        
        # Use cached result if recent
        if (current_time - self._last_health_check) < self._health_check_interval:
            return {
                "status": "healthy" if self._is_connected else "unhealthy",
                "cached": True,
                "last_check": self._last_health_check
            }
        
        start_time = time.time()
        
        try:
            if not self._is_connected or not self.driver:
                await self.connect()
            
            async with self.driver.session(database=self.database) as session:
                # Basic connectivity test
                result = await session.run("RETURN 1 as test")
                record = await result.single()
                if not record or record["test"] != 1:
                    raise ConnectionError("Health check query failed")
                
                # Get database statistics
                stats_queries = {
                    "node_count": "MATCH (n) RETURN count(n) as count",
                    "relationship_count": "MATCH ()-[r]->() RETURN count(r) as count",
                    "label_count": "CALL db.labels() YIELD label RETURN count(label) as count",
                    "relationship_type_count": "CALL db.relationshipTypes() YIELD relationshipType RETURN count(relationshipType) as count"
                }
                
                stats = {}
                for stat_name, query in stats_queries.items():
                    try:
                        result = await session.run(query)
                        record = await result.single()
                        stats[stat_name] = record["count"] if record else 0
                    except Exception as e:
                        logger.warning(f"Failed to get {stat_name}: {e}")
                        stats[stat_name] = -1
                
                # Try to get system information
                try:
                    system_result = await session.run("CALL dbms.components() YIELD name, versions, edition")
                    components = []
                    async for record in system_result:
                        components.append({
                            "name": record["name"],
                            "versions": record["versions"],
                            "edition": record["edition"]
                        })
                    stats["components"] = components
                except Exception as e:
                    logger.debug(f"Could not get system components: {e}")
                    stats["components"] = []
                
                response_time = time.time() - start_time
                self._last_health_check = current_time
                
                return {
                    "status": "healthy",
                    "response_time": response_time,
                    "cached": False,
                    "last_check": current_time,
                    "database": self.database,
                    "uri": self.uri,
                    **stats
                }
                
        except Exception as e:
            self._is_connected = False
            self._last_health_check = current_time
            response_time = time.time() - start_time
            
            logger.error(f"Neo4j health check failed: {e}")
            
            return {
                "status": "unhealthy",
                "response_time": response_time,
                "cached": False,
                "last_check": current_time,
                "error": str(e),
                "database": self.database,
                "uri": self.uri
            }
    
    def _validate_connection(self) -> None:
        """Validate that the client is connected."""
        if not self._is_connected or not self.driver:
            raise ConnectionError(
                "Neo4j client not connected. Call connect() first.",
                database_type="neo4j"
            )
    
    def _start_keepalive(self) -> None:
        """Start background keepalive task to prevent TCP transport closing."""
        self._stop_keepalive()
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._keepalive_task = loop.create_task(self._keepalive_loop())
                logger.debug(f"Neo4j keepalive started (interval={self._keepalive_interval}s)")
        except RuntimeError:
            logger.debug("No running event loop, skipping keepalive start")
    
    def _stop_keepalive(self) -> None:
        """Stop the background keepalive task."""
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            logger.debug("Neo4j keepalive stopped")
        self._keepalive_task = None
    
    async def _keepalive_loop(self) -> None:
        """Periodically ping Neo4j to keep the TCP connection alive."""
        while True:
            try:
                await asyncio.sleep(self._keepalive_interval)
                if self._is_connected and self.driver:
                    async with self.driver.session(database=self.database) as session:
                        result = await session.run("RETURN 1")
                        await result.consume()
                    logger.debug("Neo4j keepalive ping OK")
                else:
                    logger.debug("Neo4j keepalive: not connected, skipping ping")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Neo4j keepalive ping failed: {e}")
                # Don't crash the loop — the reconnect logic will handle it
                # on the next actual query
    
    async def _create_connection_and_verify(self) -> AsyncDriver:
        """Create and verify Neo4j connection (extracted for testing)."""
        # Build driver kwargs - only include encrypted and trust if using TLS
        driver_kwargs = {
            "auth": (self.user, self.password),
            "max_connection_lifetime": self.max_connection_lifetime,
            "max_connection_pool_size": self.max_connection_pool_size,
            "connection_acquisition_timeout": self.connection_acquisition_timeout,
            "max_transaction_retry_time": self.max_transaction_retry_time,
            "keep_alive": self.keep_alive,
        }
        
        # Only add encrypted/trust for TLS connections
        if self.encrypted or self.uri.startswith("bolt+s") or self.uri.startswith("neo4j+s"):
            driver_kwargs["encrypted"] = True
            # Neo4j 5.x uses TrustStore enum values
            from neo4j import TrustAll, TrustSystemCAs
            driver_kwargs["trusted_certificates"] = TrustAll() if self.trust else TrustSystemCAs()
        
        # Create async driver with connection pooling
        driver = AsyncGraphDatabase.driver(self.uri, **driver_kwargs)
        
        # Verify connectivity with a simple query
        await driver.verify_connectivity()
        
        # Test database access
        async with driver.session(database=self.database) as session:
            result = await session.run("RETURN 1 as test")
            record = await result.single()
            if not record or record["test"] != 1:
                raise ConnectionError("Connectivity test failed")
        
        return driver
    
    def _sanitize_parameters(self, parameters: Optional[QueryParameters]) -> Dict[str, Any]:
        """
        Sanitize query parameters to prevent injection attacks.
        
        Args:
            parameters: Raw query parameters
            
        Returns:
            Sanitized parameters dictionary
            
        Raises:
            ValidationError: If parameters contain invalid values
        """
        if not parameters:
            return {}
        
        if not isinstance(parameters, dict):
            raise ValidationError(
                "Query parameters must be a dictionary",
                field_name="parameters",
                field_value=type(parameters).__name__
            )
        
        sanitized = {}
        for key, value in parameters.items():
            # Validate parameter key
            if not isinstance(key, str) or not key.isidentifier():
                raise ValidationError(
                    f"Invalid parameter key: {key}. Must be a valid identifier.",
                    field_name="parameter_key",
                    field_value=key
                )
            
            # Basic value validation
            if value is None:
                sanitized[key] = None
            elif isinstance(value, (str, int, float, bool, list, dict)):
                sanitized[key] = value
            else:
                # Convert other types to string
                sanitized[key] = str(value)
        
        return sanitized

    def _is_connection_closed_error(self, error: Exception) -> bool:
        """Check if an error indicates a closed TCP transport."""
        error_str = str(error).lower()
        return (
            'tcptransport closed' in error_str
            or 'handler is closed' in error_str
            or 'connection has been closed' in error_str
            or 'session has been closed' in error_str
        )

    async def _run_query_session(
        self,
        query: str,
        sanitized_params: Dict[str, Any]
    ) -> SearchResults:
        """Execute a query within a session with transient retry."""
        async with self.driver.session(
            database=self.database
        ) as session:
            start_time = time.time()
            max_retries = 3
            retry_count = 0

            while retry_count < max_retries:
                try:
                    result = await session.run(
                        query, sanitized_params
                    )
                    records = []

                    async for record in result:
                        record_dict = {}
                        for key in record.keys():
                            value = record[key]
                            if hasattr(value, '__dict__'):
                                if hasattr(value, 'labels'):
                                    record_dict[key] = {
                                        'id': value.id,
                                        'labels': list(
                                            value.labels
                                        ),
                                        'properties': dict(
                                            value
                                        )
                                    }
                                elif hasattr(value, 'type'):
                                    record_dict[key] = {
                                        'id': value.id,
                                        'type': value.type,
                                        'start_node': (
                                            value.start_node.id
                                        ),
                                        'end_node': (
                                            value.end_node.id
                                        ),
                                        'properties': dict(
                                            value
                                        )
                                    }
                                else:
                                    record_dict[key] = (
                                        dict(value)
                                        if hasattr(
                                            value, '__iter__'
                                        )
                                        else value
                                    )
                            else:
                                record_dict[key] = value

                        records.append(record_dict)

                    execution_time = time.time() - start_time
                    logger.debug(
                        f"Executed Neo4j query in "
                        f"{execution_time:.3f}s, "
                        f"returned {len(records)} records"
                    )
                    return records

                except TransientError as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        raise QueryError(
                            f"Query failed after "
                            f"{max_retries} retries",
                            query=query,
                            parameters=sanitized_params,
                            query_type="READ",
                            original_exception=e
                        )
                    await asyncio.sleep(
                        0.1 * (2 ** retry_count)
                    )
                    logger.warning(
                        f"Retrying query due to "
                        f"transient error "
                        f"(attempt {retry_count}): {e}"
                    )

                except Exception as e:
                    # Non-transient error, don't retry
                    # in this loop
                    raise

    async def _execute_query_with_reconnect(
        self,
        query: str,
        sanitized_params: Dict[str, Any]
    ) -> SearchResults:
        """Execute query with automatic reconnection on
        closed transport errors."""
        try:
            return await self._run_query_session(
                query, sanitized_params
            )
        except Exception as e:
            if self._is_connection_closed_error(e):
                logger.warning(
                    "Neo4j TCP transport closed, "
                    "reconnecting and retrying..."
                )
                # Stop keepalive before tearing down driver
                self._stop_keepalive()
                self._is_connected = False
                try:
                    if self.driver:
                        await self.driver.close()
                except Exception:
                    pass
                self.driver = None
                await self.connect()

                # Retry the query once after reconnect
                return await self._run_query_session(
                    query, sanitized_params
                )
            raise

    async def _run_write_session(
        self,
        query: str,
        sanitized_params: Dict[str, Any]
    ) -> SearchResults:
        """Execute a write query within a session transaction."""
        async with self.driver.session(
            database=self.database
        ) as session:
            start_time = time.time()

            async def write_transaction(tx):
                result = await tx.run(query, sanitized_params)
                records = []
                async for record in result:
                    record_dict = {}
                    for key in record.keys():
                        value = record[key]
                        if hasattr(value, '__dict__'):
                            if hasattr(value, 'labels'):
                                record_dict[key] = {
                                    'id': value.id,
                                    'labels': list(value.labels),
                                    'properties': dict(value)
                                }
                            elif hasattr(value, 'type'):
                                record_dict[key] = {
                                    'id': value.id,
                                    'type': value.type,
                                    'start_node': value.start_node.id,
                                    'end_node': value.end_node.id,
                                    'properties': dict(value)
                                }
                            else:
                                record_dict[key] = (
                                    dict(value)
                                    if hasattr(value, '__iter__')
                                    else value
                                )
                        else:
                            record_dict[key] = value
                    records.append(record_dict)
                return records

            records = await session.execute_write(write_transaction)
            execution_time = time.time() - start_time
            logger.debug(
                f"Executed Neo4j write query in "
                f"{execution_time:.3f}s, "
                f"returned {len(records)} records"
            )
            return records

    async def _execute_write_with_reconnect(
        self,
        query: str,
        sanitized_params: Dict[str, Any]
    ) -> SearchResults:
        """Execute write query with automatic reconnection on
        closed transport errors."""
        try:
            return await self._run_write_session(
                query, sanitized_params
            )
        except Exception as e:
            if self._is_connection_closed_error(e):
                logger.warning(
                    "Neo4j TCP transport closed during write, "
                    "reconnecting and retrying..."
                )
                self._stop_keepalive()
                self._is_connected = False
                try:
                    if self.driver:
                        await self.driver.close()
                except Exception:
                    pass
                self.driver = None
                await self.connect()
                return await self._run_write_session(
                    query, sanitized_params
                )
            raise

    async def execute_query(
        self, 
        query: str, 
        parameters: Optional[QueryParameters] = None
    ) -> SearchResults:
        """
        Execute a Cypher query and return results.
        
        This method executes a Cypher query with optional parameters and returns
        standardized results. It includes retry logic for transient failures and
        comprehensive error handling.
        
        Args:
            query: Cypher query string (e.g., "MATCH (n:User) RETURN n")
            parameters: Query parameters for safe parameterized queries
            
        Returns:
            List of result records as dictionaries
            
        Raises:
            QueryError: If query execution fails or has syntax errors
            ValidationError: If parameters are invalid
            TimeoutError: If query execution times out
            ConnectionError: If database connection is lost
        """
        self._validate_connection()
        
        if not query or not isinstance(query, str):
            raise ValidationError(
                "Query must be a non-empty string",
                field_name="query",
                field_value=query
            )
        
        sanitized_params = self._sanitize_parameters(parameters)
        
        try:
            return await self._execute_query_with_reconnect(
                query, sanitized_params
            )
        except Neo4jError as e:
            logger.error(f"Neo4j query error: {e}")
            raise QueryError(
                f"Query execution failed: {e}",
                query=query,
                parameters=sanitized_params,
                query_type="READ",
                original_exception=e
            )
        except asyncio.TimeoutError as e:
            logger.error(f"Neo4j query timeout: {e}")
            raise TimeoutError(
                f"Query execution timed out",
                timeout_duration=self.connection_acquisition_timeout,
                operation_type="query_execution",
                original_exception=e
            )
        except Exception as e:
            logger.error(f"Unexpected error executing Neo4j query: {e}")
            raise QueryError(
                f"Unexpected query error: {e}",
                query=query,
                parameters=sanitized_params,
                query_type="READ",
                original_exception=e
            )
    
    async def execute_write_query(
        self, 
        query: str, 
        parameters: Optional[QueryParameters] = None
    ) -> SearchResults:
        """
        Execute a write Cypher query and return results.
        
        This method executes a write query (CREATE, UPDATE, DELETE, MERGE) within
        a write transaction to ensure data consistency. It includes retry logic
        for transient failures.
        
        Args:
            query: Cypher write query string
            parameters: Query parameters for safe parameterized queries
            
        Returns:
            List of result records as dictionaries
            
        Raises:
            QueryError: If query execution fails
            ValidationError: If parameters are invalid
            TransactionError: If transaction fails
            ConnectionError: If database connection is lost
        """
        self._validate_connection()
        
        if not query or not isinstance(query, str):
            raise ValidationError(
                "Query must be a non-empty string",
                field_name="query",
                field_value=query
            )
        
        sanitized_params = self._sanitize_parameters(parameters)
        
        try:
            return await self._execute_write_with_reconnect(
                query, sanitized_params
            )
        except Neo4jError as e:
            logger.error(f"Neo4j write query error: {e}")
            raise QueryError(
                f"Write query execution failed: {e}",
                query=query,
                parameters=sanitized_params,
                query_type="WRITE",
                original_exception=e
            )
        except asyncio.TimeoutError as e:
            logger.error(f"Neo4j write query timeout: {e}")
            raise TimeoutError(
                f"Write query execution timed out",
                timeout_duration=self.connection_acquisition_timeout,
                operation_type="write_query_execution",
                original_exception=e
            )
        except Exception as e:
            logger.error(f"Unexpected error executing Neo4j write query: {e}")
            raise TransactionError(
                f"Write transaction failed: {e}",
                operation="write_query",
                original_exception=e
            )
    
    def _format_cypher_query(self, template: str, **kwargs) -> str:
        """
        Format a Cypher query template with safe parameter substitution.
        
        This method provides safe query formatting for dynamic query construction
        while preventing injection attacks.
        
        Args:
            template: Cypher query template with placeholders
            **kwargs: Template parameters
            
        Returns:
            Formatted Cypher query string
            
        Raises:
            ValidationError: If template parameters are invalid
        """
        try:
            # Only allow alphanumeric identifiers and underscores
            safe_kwargs = {}
            for key, value in kwargs.items():
                if not key.replace('_', '').isalnum():
                    raise ValidationError(
                        f"Invalid template parameter: {key}",
                        field_name="template_parameter",
                        field_value=key
                    )
                
                # Escape string values for Cypher
                if isinstance(value, str):
                    # Basic escaping for Cypher identifiers
                    if not value.replace('_', '').replace('-', '').isalnum():
                        raise ValidationError(
                            f"Invalid identifier value: {value}",
                            field_name=key,
                            field_value=value
                        )
                    safe_kwargs[key] = value
                elif isinstance(value, (int, float, bool)):
                    safe_kwargs[key] = value
                else:
                    raise ValidationError(
                        f"Unsupported template parameter type: {type(value)}",
                        field_name=key,
                        field_value=str(value)
                    )
            
            return template.format(**safe_kwargs)
            
        except KeyError as e:
            raise ValidationError(
                f"Missing template parameter: {e}",
                field_name="template_parameter",
                validation_rule="required_parameter"
            )
        except Exception as e:
            raise ValidationError(
                f"Query template formatting failed: {e}",
                validation_rule="template_formatting",
                original_exception=e
            )
    
    @asynccontextmanager
    async def transaction(self):
        """
        Create a database transaction context.
        
        This context manager provides a Neo4j session within a transaction.
        The transaction is automatically committed on success or rolled back
        on exception. Use this for operations that require atomicity.
        
        Yields:
            AsyncSession: Neo4j session within transaction context
            
        Raises:
            TransactionError: If transaction cannot be started or committed
            ConnectionError: If database connection is lost during transaction
            
        Example:
            ```python
            async with client.transaction() as session:
                # Create user
                user_result = await session.run(
                    "CREATE (u:User {name: $name, email: $email}) RETURN u",
                    {"name": "John Doe", "email": "john@example.com"}
                )
                user_record = await user_result.single()
                user_id = user_record["u"].id
                
                # Create user profile
                await session.run(
                    "CREATE (p:Profile {user_id: $user_id, bio: $bio})",
                    {"user_id": user_id, "bio": "Software developer"}
                )
            # Both operations committed atomically
            ```
        """
        self._validate_connection()
        
        session = None
        transaction = None
        
        try:
            session = self.driver.session(database=self.database)
            transaction = await session.begin_transaction()
            
            logger.debug("Started Neo4j transaction")
            
            # Create a transaction wrapper that provides the same interface as session
            class TransactionWrapper:
                def __init__(self, tx):
                    self._tx = tx
                
                async def run(self, query: str, parameters: Optional[Dict[str, Any]] = None):
                    return await self._tx.run(query, parameters or {})
                
                async def execute_read(self, work, **kwargs):
                    return await work(self._tx, **kwargs)
                
                async def execute_write(self, work, **kwargs):
                    return await work(self._tx, **kwargs)
            
            yield TransactionWrapper(transaction)
            
            # Commit transaction if no exception occurred
            await transaction.commit()
            logger.debug("Committed Neo4j transaction")
            
        except Exception as e:
            # Rollback transaction on any exception
            if transaction:
                try:
                    await transaction.rollback()
                    logger.debug("Rolled back Neo4j transaction due to error")
                except Exception as rollback_error:
                    logger.error(f"Failed to rollback transaction: {rollback_error}")
            
            logger.error(f"Transaction failed: {e}")
            raise TransactionError(
                f"Transaction failed: {e}",
                operation="transaction_execution",
                original_exception=e
            )
        finally:
            # Clean up session
            if session:
                try:
                    await session.close()
                except Exception as cleanup_error:
                    logger.warning(f"Error closing session: {cleanup_error}")
    
    async def execute_in_transaction(
        self,
        queries: List[Dict[str, Any]],
        rollback_on_error: bool = True
    ) -> List[SearchResults]:
        """
        Execute multiple queries in a single transaction.
        
        This method executes a list of queries atomically within a single
        transaction. All queries succeed or all fail together.
        
        Args:
            queries: List of query dictionaries, each containing:
                    - query: Cypher query string
                    - parameters: Optional query parameters
                    - description: Optional description for logging
            rollback_on_error: Whether to rollback on any error (default: True)
            
        Returns:
            List of results for each query
            
        Raises:
            TransactionError: If transaction fails
            ValidationError: If queries format is invalid
            
        Example:
            ```python
            queries = [
                {
                    "query": "CREATE (u:User {name: $name}) RETURN u",
                    "parameters": {"name": "Alice"},
                    "description": "Create user"
                },
                {
                    "query": "CREATE (p:Profile {user_name: $name}) RETURN p",
                    "parameters": {"name": "Alice"},
                    "description": "Create profile"
                }
            ]
            results = await client.execute_in_transaction(queries)
            ```
        """
        if not queries or not isinstance(queries, list):
            raise ValidationError(
                "Queries must be a non-empty list",
                field_name="queries",
                field_value=type(queries).__name__
            )
        
        # Validate query format
        for i, query_dict in enumerate(queries):
            if not isinstance(query_dict, dict) or 'query' not in query_dict:
                raise ValidationError(
                    f"Query {i} must be a dictionary with 'query' key",
                    field_name=f"queries[{i}]",
                    field_value=str(query_dict)
                )
        
        results = []
        
        try:
            async with self.transaction() as tx:
                for i, query_dict in enumerate(queries):
                    query = query_dict['query']
                    parameters = query_dict.get('parameters', {})
                    description = query_dict.get('description', f'Query {i+1}')
                    
                    try:
                        logger.debug(f"Executing transaction query: {description}")
                        
                        result = await tx.run(query, parameters)
                        records = []
                        
                        async for record in result:
                            # Convert Neo4j record to dictionary
                            record_dict = {}
                            for key in record.keys():
                                value = record[key]
                                if hasattr(value, '__dict__'):
                                    if hasattr(value, 'labels'):  # Node
                                        record_dict[key] = {
                                            'id': value.id,
                                            'labels': list(value.labels),
                                            'properties': dict(value)
                                        }
                                    elif hasattr(value, 'type'):  # Relationship
                                        record_dict[key] = {
                                            'id': value.id,
                                            'type': value.type,
                                            'start_node': value.start_node.id,
                                            'end_node': value.end_node.id,
                                            'properties': dict(value)
                                        }
                                    else:
                                        record_dict[key] = dict(value) if hasattr(value, '__iter__') else value
                                else:
                                    record_dict[key] = value
                            
                            records.append(record_dict)
                        
                        results.append(records)
                        
                    except Exception as e:
                        error_msg = f"Query {i+1} ({description}) failed: {e}"
                        logger.error(error_msg)
                        
                        if rollback_on_error:
                            raise TransactionError(
                                error_msg,
                                operation="multi_query_transaction",
                                original_exception=e
                            )
                        else:
                            # Continue with empty result for failed query
                            results.append([])
                
                logger.debug(f"Successfully executed {len(queries)} queries in transaction")
                return results
                
        except TransactionError:
            # Re-raise transaction errors
            raise
        except Exception as e:
            logger.error(f"Unexpected error in multi-query transaction: {e}")
            raise TransactionError(
                f"Multi-query transaction failed: {e}",
                operation="multi_query_transaction",
                original_exception=e
            )
    
    async def retry_transaction(
        self,
        work_function,
        max_retries: int = 3,
        base_delay: float = 0.1,
        max_delay: float = 5.0,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute a function with transaction retry logic.
        
        This method provides automatic retry logic for transaction functions
        that may fail due to transient errors like deadlocks or temporary
        network issues.
        
        Args:
            work_function: Async function to execute in transaction
            max_retries: Maximum number of retry attempts
            base_delay: Base delay between retries in seconds
            max_delay: Maximum delay between retries in seconds
            *args: Arguments to pass to work_function
            **kwargs: Keyword arguments to pass to work_function
            
        Returns:
            Result of work_function
            
        Raises:
            TransactionError: If all retry attempts fail
            
        Example:
            ```python
            async def create_user_with_profile(tx, name, email):
                user_result = await tx.run(
                    "CREATE (u:User {name: $name, email: $email}) RETURN u",
                    {"name": name, "email": email}
                )
                user = await user_result.single()
                
                await tx.run(
                    "CREATE (p:Profile {user_id: $user_id})",
                    {"user_id": user["u"].id}
                )
                return user["u"].id
            
            user_id = await client.retry_transaction(
                create_user_with_profile,
                name="Alice",
                email="alice@example.com"
            )
            ```
        """
        last_exception = None
        
        for attempt in range(max_retries + 1):
            try:
                async with self.transaction() as tx:
                    return await work_function(tx, *args, **kwargs)
                    
            except TransientError as e:
                last_exception = e
                if attempt < max_retries:
                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    logger.warning(
                        f"Transaction attempt {attempt + 1} failed with transient error, "
                        f"retrying in {delay:.2f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Transaction failed after {max_retries + 1} attempts")
                    break
                    
            except Exception as e:
                # Non-transient error, don't retry
                logger.error(f"Transaction failed with non-transient error: {e}")
                raise TransactionError(
                    f"Transaction failed: {e}",
                    operation="retry_transaction",
                    original_exception=e
                )
        
        # All retries exhausted
        raise TransactionError(
            f"Transaction failed after {max_retries + 1} attempts",
            operation="retry_transaction",
            original_exception=last_exception
        )
    
    # Node Operations
    async def create_node(
        self, 
        labels: List[str], 
        properties: NodeProperties
    ) -> str:
        """
        Create a node with given labels and properties.
        
        This method creates a new node in the graph with the specified
        labels and properties. Labels are used for categorization and
        indexing.
        
        Args:
            labels: List of node labels (e.g., ["User", "Person"])
            properties: Node properties as key-value pairs
                       
        Returns:
            Unique node ID assigned by the database
            
        Raises:
            ValidationError: If labels or properties are invalid
            SchemaError: If node creation violates constraints
            QueryError: If node creation fails
        """
        if not labels or not isinstance(labels, list):
            raise ValidationError(
                "Labels must be a non-empty list",
                field_name="labels",
                field_value=labels
            )
        
        if not properties or not isinstance(properties, dict):
            raise ValidationError(
                "Properties must be a non-empty dictionary",
                field_name="properties",
                field_value=properties
            )
        
        # Validate labels
        for label in labels:
            if not isinstance(label, str) or not label.strip():
                raise ValidationError(
                    f"Invalid label: {label}. Labels must be non-empty strings.",
                    field_name="label",
                    field_value=label
                )
        
        # Create labels string for Cypher
        labels_str = ":".join(labels)
        
        try:
            query = f"CREATE (n:{labels_str} $properties) RETURN id(n) as node_id"
            result = await self.execute_write_query(query, {"properties": properties})
            
            if result and len(result) > 0:
                node_id = result[0]["node_id"]
                logger.debug(f"Created node with ID {node_id} and labels {labels}")
                return str(node_id)
            else:
                raise SchemaError(
                    "Node creation returned no results",
                    schema_object="node",
                    operation="create"
                )
                
        except QueryError:
            # Re-raise query errors
            raise
        except Exception as e:
            logger.error(f"Failed to create node: {e}")
            raise SchemaError(
                f"Node creation failed: {e}",
                schema_object="node",
                operation="create",
                original_exception=e
            )
    
    async def get_node(
        self, 
        node_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get a node by ID.
        
        This method retrieves a node and all its properties by its unique ID.
        
        Args:
            node_id: ID of the node to retrieve
            
        Returns:
            Node data including:
            - id: Node ID
            - labels: List of node labels
            - properties: Dictionary of node properties
            Returns None if node is not found
            
        Raises:
            ValidationError: If node ID format is invalid
            QueryError: If query execution fails
        """
        if not node_id or not isinstance(node_id, str):
            raise ValidationError(
                "Node ID must be a non-empty string",
                field_name="node_id",
                field_value=node_id
            )
        
        try:
            # Convert to integer for Neo4j internal ID
            node_id_int = int(node_id)
        except ValueError:
            raise ValidationError(
                f"Invalid node ID format: {node_id}. Must be a numeric string.",
                field_name="node_id",
                field_value=node_id
            )
        
        try:
            query = "MATCH (n) WHERE id(n) = $node_id RETURN n, labels(n) as labels"
            result = await self.execute_query(query, {"node_id": node_id_int})
            
            if result and len(result) > 0:
                record = result[0]
                node = record["n"]
                
                return {
                    "id": str(node["id"]),
                    "labels": record["labels"],
                    "properties": node["properties"]
                }
            else:
                return None
                
        except QueryError:
            # Re-raise query errors
            raise
        except Exception as e:
            logger.error(f"Failed to get node {node_id}: {e}")
            raise QueryError(
                f"Failed to retrieve node: {e}",
                query="get_node",
                parameters={"node_id": node_id},
                original_exception=e
            )
    
    async def update_node(
        self, 
        node_id: str, 
        properties: NodeProperties
    ) -> bool:
        """
        Update node properties.
        
        This method updates the properties of an existing node. Properties
        not included in the update will remain unchanged.
        
        Args:
            node_id: ID of the node to update
            properties: Properties to update (partial update supported)
            
        Returns:
            True if node was updated successfully, False if node not found
            
        Raises:
            ValidationError: If node ID or properties are invalid
            QueryError: If update operation fails
        """
        if not node_id or not isinstance(node_id, str):
            raise ValidationError(
                "Node ID must be a non-empty string",
                field_name="node_id",
                field_value=node_id
            )
        
        if not properties or not isinstance(properties, dict):
            raise ValidationError(
                "Properties must be a non-empty dictionary",
                field_name="properties",
                field_value=properties
            )
        
        try:
            node_id_int = int(node_id)
        except ValueError:
            raise ValidationError(
                f"Invalid node ID format: {node_id}. Must be a numeric string.",
                field_name="node_id",
                field_value=node_id
            )
        
        try:
            # Build SET clause for properties
            set_clauses = []
            params = {"node_id": node_id_int}
            
            for key, value in properties.items():
                param_key = f"prop_{key}"
                set_clauses.append(f"n.{key} = ${param_key}")
                params[param_key] = value
            
            set_clause = ", ".join(set_clauses)
            query = f"MATCH (n) WHERE id(n) = $node_id SET {set_clause} RETURN count(n) as updated_count"
            
            result = await self.execute_write_query(query, params)
            
            if result and len(result) > 0:
                updated_count = result[0]["updated_count"]
                success = updated_count > 0
                
                if success:
                    logger.debug(f"Updated node {node_id} with properties {list(properties.keys())}")
                else:
                    logger.debug(f"Node {node_id} not found for update")
                
                return success
            else:
                return False
                
        except QueryError:
            # Re-raise query errors
            raise
        except Exception as e:
            logger.error(f"Failed to update node {node_id}: {e}")
            raise QueryError(
                f"Failed to update node: {e}",
                query="update_node",
                parameters={"node_id": node_id, "properties": properties},
                original_exception=e
            )
    
    async def delete_node(self, node_id: str) -> bool:
        """
        Delete a node.
        
        This method deletes a node and all its relationships. This operation
        cannot be undone.
        
        Args:
            node_id: ID of the node to delete
            
        Returns:
            True if node was deleted successfully, False if node not found
            
        Raises:
            ValidationError: If node ID format is invalid
            SchemaError: If node deletion violates constraints
            QueryError: If deletion operation fails
        """
        if not node_id or not isinstance(node_id, str):
            raise ValidationError(
                "Node ID must be a non-empty string",
                field_name="node_id",
                field_value=node_id
            )
        
        try:
            node_id_int = int(node_id)
        except ValueError:
            raise ValidationError(
                f"Invalid node ID format: {node_id}. Must be a numeric string.",
                field_name="node_id",
                field_value=node_id
            )
        
        try:
            # Delete node and all its relationships
            query = "MATCH (n) WHERE id(n) = $node_id DETACH DELETE n RETURN count(n) as deleted_count"
            result = await self.execute_write_query(query, {"node_id": node_id_int})
            
            if result and len(result) > 0:
                deleted_count = result[0]["deleted_count"]
                success = deleted_count > 0
                
                if success:
                    logger.debug(f"Deleted node {node_id} and all its relationships")
                else:
                    logger.debug(f"Node {node_id} not found for deletion")
                
                return success
            else:
                return False
                
        except QueryError:
            # Re-raise query errors
            raise
        except Exception as e:
            logger.error(f"Failed to delete node {node_id}: {e}")
            raise SchemaError(
                f"Failed to delete node: {e}",
                schema_object="node",
                operation="delete",
                original_exception=e
            )
    
    # Relationship Operations
    async def create_relationship(
        self, 
        from_node_id: str, 
        to_node_id: str,
        relationship_type: str, 
        properties: Optional[NodeProperties] = None
    ) -> str:
        """
        Create a relationship between two nodes.
        
        This method creates a directed relationship between two existing nodes
        with the specified type and optional properties.
        
        Args:
            from_node_id: Source node ID
            to_node_id: Target node ID
            relationship_type: Type of relationship (e.g., "FOLLOWS", "LIKES", "CONTAINS")
            properties: Optional relationship properties
                       
        Returns:
            Unique relationship ID assigned by the database
            
        Raises:
            ValidationError: If node IDs don't exist or relationship type is invalid
            SchemaError: If relationship creation violates constraints
            QueryError: If relationship creation fails
        """
        # Validate inputs
        if not from_node_id or not isinstance(from_node_id, str):
            raise ValidationError(
                "From node ID must be a non-empty string",
                field_name="from_node_id",
                field_value=from_node_id
            )
        
        if not to_node_id or not isinstance(to_node_id, str):
            raise ValidationError(
                "To node ID must be a non-empty string",
                field_name="to_node_id",
                field_value=to_node_id
            )
        
        if not relationship_type or not isinstance(relationship_type, str):
            raise ValidationError(
                "Relationship type must be a non-empty string",
                field_name="relationship_type",
                field_value=relationship_type
            )
        
        # Sanitize relationship type - replace slashes with underscores
        sanitized_relationship_type = self._sanitize_relationship_type(relationship_type)
        
        # Validate relationship type format
        if not sanitized_relationship_type.replace('_', '').isalnum():
            raise ValidationError(
                f"Invalid relationship type: {relationship_type}. Must contain only alphanumeric characters and underscores.",
                field_name="relationship_type",
                field_value=relationship_type
            )
        
        try:
            from_node_id_int = int(from_node_id)
            to_node_id_int = int(to_node_id)
        except ValueError as e:
            raise ValidationError(
                f"Invalid node ID format. Must be numeric strings.",
                field_name="node_ids",
                field_value=f"from: {from_node_id}, to: {to_node_id}",
                original_exception=e
            )
        
        try:
            # Build query with optional properties
            params = {
                "from_id": from_node_id_int,
                "to_id": to_node_id_int
            }
            
            if properties:
                params["properties"] = properties
            else:
                params["properties"] = {}
            
            query = f"""
            MATCH (a), (b)
            WHERE id(a) = $from_id AND id(b) = $to_id
            MERGE (a)-[r:{sanitized_relationship_type}]->(b)
            ON CREATE SET r += $properties
            ON MATCH SET r += $properties
            RETURN id(r) as relationship_id
            """
            
            result = await self.execute_write_query(query, params)
            
            if result and len(result) > 0:
                relationship_id = result[0]["relationship_id"]
                logger.debug(
                    f"Created relationship {relationship_type} from {from_node_id} to {to_node_id} "
                    f"with ID {relationship_id}"
                )
                return str(relationship_id)
            else:
                raise SchemaError(
                    "Relationship creation returned no results. Check that both nodes exist.",
                    schema_object="relationship",
                    operation="create"
                )
                
        except QueryError:
            # Re-raise query errors
            raise
        except Exception as e:
            logger.error(f"Failed to create relationship: {e}")
            raise SchemaError(
                f"Relationship creation failed: {e}",
                schema_object="relationship",
                operation="create",
                original_exception=e
            )
    
    @staticmethod
    def _sanitize_relationship_type(relationship_type: str) -> str:
        """
        Sanitize a relationship type for safe use in Cypher queries.

        Replaces any non-alphanumeric character (except underscores) with
        an underscore.  For example ``dbpedia/genre`` becomes
        ``dbpedia_genre`` and ``dbpedia/influencedBy`` becomes
        ``dbpedia_influencedBy``.

        Args:
            relationship_type: Raw relationship type string.

        Returns:
            Sanitized string containing only ``[A-Za-z0-9_]``.
        """
        import re
        return re.sub(r'[^A-Za-z0-9_]', '_', relationship_type)

    async def get_relationships(
        self, 
        node_id: str,
        direction: RelationshipDirection = "both"
    ) -> SearchResults:
        """
        Get relationships for a node.
        
        This method retrieves all relationships connected to a node,
        optionally filtered by direction.
        
        Args:
            node_id: ID of the node
            direction: Direction of relationships:
                      - "in": Incoming relationships only
                      - "out": Outgoing relationships only  
                      - "both": All relationships (default)
                      
        Returns:
            List of relationships, each containing:
            - id: Relationship ID
            - type: Relationship type
            - from_node_id: Source node ID
            - to_node_id: Target node ID
            - properties: Relationship properties
            
        Raises:
            ValidationError: If node ID or direction is invalid
            QueryError: If query execution fails
        """
        if not node_id or not isinstance(node_id, str):
            raise ValidationError(
                "Node ID must be a non-empty string",
                field_name="node_id",
                field_value=node_id
            )
        
        if direction not in ["in", "out", "both"]:
            raise ValidationError(
                f"Invalid direction: {direction}. Must be 'in', 'out', or 'both'.",
                field_name="direction",
                field_value=direction
            )
        
        try:
            node_id_int = int(node_id)
        except ValueError:
            raise ValidationError(
                f"Invalid node ID format: {node_id}. Must be a numeric string.",
                field_name="node_id",
                field_value=node_id
            )
        
        try:
            # Build query based on direction
            if direction == "in":
                query = """
                MATCH (other)-[r]->(n)
                WHERE id(n) = $node_id
                RETURN id(r) as id, type(r) as type, id(startNode(r)) as from_node_id, 
                       id(endNode(r)) as to_node_id, properties(r) as properties
                """
            elif direction == "out":
                query = """
                MATCH (n)-[r]->(other)
                WHERE id(n) = $node_id
                RETURN id(r) as id, type(r) as type, id(startNode(r)) as from_node_id, 
                       id(endNode(r)) as to_node_id, properties(r) as properties
                """
            else:  # both
                query = """
                MATCH (n)-[r]-(other)
                WHERE id(n) = $node_id
                RETURN id(r) as id, type(r) as type, id(startNode(r)) as from_node_id, 
                       id(endNode(r)) as to_node_id, properties(r) as properties
                """
            
            result = await self.execute_query(query, {"node_id": node_id_int})
            
            # Convert results to standard format
            relationships = []
            for record in result:
                relationships.append({
                    "id": str(record["id"]),
                    "type": record["type"],
                    "from_node_id": str(record["from_node_id"]),
                    "to_node_id": str(record["to_node_id"]),
                    "properties": record["properties"] or {}
                })
            
            logger.debug(f"Retrieved {len(relationships)} relationships for node {node_id} (direction: {direction})")
            return relationships
            
        except QueryError:
            # Re-raise query errors
            raise
        except Exception as e:
            logger.error(f"Failed to get relationships for node {node_id}: {e}")
            raise QueryError(
                f"Failed to retrieve relationships: {e}",
                query="get_relationships",
                parameters={"node_id": node_id, "direction": direction},
                original_exception=e
            )
    
    async def delete_relationship(self, relationship_id: str) -> bool:
        """
        Delete a relationship.
        
        This method deletes a specific relationship by its ID. The connected
        nodes remain unchanged.
        
        Args:
            relationship_id: ID of the relationship to delete
            
        Returns:
            True if relationship was deleted successfully, False if not found
            
        Raises:
            ValidationError: If relationship ID format is invalid
            QueryError: If deletion operation fails
        """
        if not relationship_id or not isinstance(relationship_id, str):
            raise ValidationError(
                "Relationship ID must be a non-empty string",
                field_name="relationship_id",
                field_value=relationship_id
            )
        
        try:
            relationship_id_int = int(relationship_id)
        except ValueError:
            raise ValidationError(
                f"Invalid relationship ID format: {relationship_id}. Must be a numeric string.",
                field_name="relationship_id",
                field_value=relationship_id
            )
        
        try:
            query = "MATCH ()-[r]->() WHERE id(r) = $relationship_id DELETE r RETURN count(r) as deleted_count"
            result = await self.execute_write_query(query, {"relationship_id": relationship_id_int})
            
            if result and len(result) > 0:
                deleted_count = result[0]["deleted_count"]
                success = deleted_count > 0
                
                if success:
                    logger.debug(f"Deleted relationship {relationship_id}")
                else:
                    logger.debug(f"Relationship {relationship_id} not found for deletion")
                
                return success
            else:
                return False
                
        except QueryError:
            # Re-raise query errors
            raise
        except Exception as e:
            logger.error(f"Failed to delete relationship {relationship_id}: {e}")
            raise QueryError(
                f"Failed to delete relationship: {e}",
                query="delete_relationship",
                parameters={"relationship_id": relationship_id},
                original_exception=e
            )
    
    # Graph Analysis Operations
    async def find_path(
        self, 
        from_node_id: str, 
        to_node_id: str,
        max_depth: int = 5
    ) -> GraphPath:
        """
        Find paths between two nodes.
        
        This method finds paths between two nodes up to a specified maximum
        depth. It returns the shortest paths found.
        
        Args:
            from_node_id: Source node ID
            to_node_id: Target node ID
            max_depth: Maximum path depth to search (default: 5)
            
        Returns:
            List of paths, each path containing:
            - length: Path length (number of hops)
            - nodes: List of node IDs in the path
            - relationships: List of relationship IDs in the path
            - weight: Total path weight (if applicable)
            
        Raises:
            ValidationError: If node IDs don't exist
            TimeoutError: If path finding takes too long
            QueryError: If path finding query fails
        """
        if not from_node_id or not isinstance(from_node_id, str):
            raise ValidationError(
                "From node ID must be a non-empty string",
                field_name="from_node_id",
                field_value=from_node_id
            )
        
        if not to_node_id or not isinstance(to_node_id, str):
            raise ValidationError(
                "To node ID must be a non-empty string",
                field_name="to_node_id",
                field_value=to_node_id
            )
        
        if not isinstance(max_depth, int) or max_depth < 1:
            raise ValidationError(
                "Max depth must be a positive integer",
                field_name="max_depth",
                field_value=max_depth
            )
        
        try:
            from_node_id_int = int(from_node_id)
            to_node_id_int = int(to_node_id)
        except ValueError:
            raise ValidationError(
                "Invalid node ID format. Must be numeric strings.",
                field_name="node_ids",
                field_value=f"from: {from_node_id}, to: {to_node_id}"
            )
        
        try:
            query = f"""
            MATCH path = shortestPath((start)-[*1..{max_depth}]-(end))
            WHERE id(start) = $from_id AND id(end) = $to_id
            RETURN path,
                   length(path) as length,
                   [n in nodes(path) | id(n)] as node_ids,
                   [r in relationships(path) | id(r)] as relationship_ids
            ORDER BY length(path)
            LIMIT 10
            """
            
            result = await self.execute_query(query, {
                "from_id": from_node_id_int,
                "to_id": to_node_id_int
            })
            
            paths = []
            for record in result:
                paths.append({
                    "length": record["length"],
                    "nodes": [str(node_id) for node_id in record["node_ids"]],
                    "relationships": [str(rel_id) for rel_id in record["relationship_ids"]],
                    "weight": record["length"]  # Use path length as weight
                })
            
            logger.debug(f"Found {len(paths)} paths from {from_node_id} to {to_node_id}")
            return paths
            
        except QueryError:
            # Re-raise query errors
            raise
        except Exception as e:
            logger.error(f"Failed to find path from {from_node_id} to {to_node_id}: {e}")
            raise QueryError(
                f"Path finding failed: {e}",
                query="find_path",
                parameters={"from_node_id": from_node_id, "to_node_id": to_node_id, "max_depth": max_depth},
                original_exception=e
            )
    
    async def get_neighbors(
        self, 
        node_id: str, 
        depth: int = 1
    ) -> SearchResults:
        """
        Get neighboring nodes.
        
        This method retrieves all nodes within a specified distance
        (number of hops) from the given node.
        
        Args:
            node_id: ID of the central node
            depth: Depth of neighborhood (number of hops, default: 1)
            
        Returns:
            List of neighboring nodes, each containing:
            - id: Node ID
            - labels: Node labels
            - properties: Node properties
            - distance: Distance from central node
            - path: Path from central node (for depth > 1)
            
        Raises:
            ValidationError: If node ID doesn't exist or depth is invalid
            QueryError: If neighbor query fails
        """
        if not node_id or not isinstance(node_id, str):
            raise ValidationError(
                "Node ID must be a non-empty string",
                field_name="node_id",
                field_value=node_id
            )
        
        if not isinstance(depth, int) or depth < 1:
            raise ValidationError(
                "Depth must be a positive integer",
                field_name="depth",
                field_value=depth
            )
        
        try:
            node_id_int = int(node_id)
        except ValueError:
            raise ValidationError(
                f"Invalid node ID format: {node_id}. Must be a numeric string.",
                field_name="node_id",
                field_value=node_id
            )
        
        try:
            query = f"""
            MATCH path = (start)-[*1..{depth}]-(neighbor)
            WHERE id(start) = $node_id AND id(neighbor) <> $node_id
            RETURN DISTINCT neighbor,
                   labels(neighbor) as labels,
                   properties(neighbor) as properties,
                   length(path) as distance,
                   id(neighbor) as neighbor_id
            ORDER BY distance, neighbor_id
            """
            
            result = await self.execute_query(query, {"node_id": node_id_int})
            
            neighbors = []
            for record in result:
                neighbors.append({
                    "id": str(record["neighbor_id"]),
                    "labels": record["labels"],
                    "properties": record["properties"] or {},
                    "distance": record["distance"]
                })
            
            logger.debug(f"Found {len(neighbors)} neighbors for node {node_id} within depth {depth}")
            return neighbors
            
        except QueryError:
            # Re-raise query errors
            raise
        except Exception as e:
            logger.error(f"Failed to get neighbors for node {node_id}: {e}")
            raise QueryError(
                f"Failed to retrieve neighbors: {e}",
                query="get_neighbors",
                parameters={"node_id": node_id, "depth": depth},
                original_exception=e
            )
    
    # Database Information
    async def get_database_info(self) -> DatabaseMetadata:
        """
        Get graph database information and statistics.
        
        This method returns comprehensive information about the graph database
        including size, performance metrics, and configuration.
        
        Returns:
            Dictionary with database metadata including:
            - version: Database version string
            - node_count: Total number of nodes
            - relationship_count: Total number of relationships
            - label_count: Number of distinct node labels
            - relationship_type_count: Number of distinct relationship types
            - memory_usage: Memory usage in bytes (if available)
            - disk_usage: Disk usage in bytes (if available)
            - index_count: Number of indexes
            - constraint_count: Number of constraints
            - uptime: Database uptime in seconds (if available)
        """
        try:
            info = {
                "database_type": "neo4j",
                "uri": self.uri,
                "database": self.database
            }
            
            # Get basic statistics
            stats_queries = {
                "node_count": "MATCH (n) RETURN count(n) as count",
                "relationship_count": "MATCH ()-[r]->() RETURN count(r) as count",
                "label_count": "CALL db.labels() YIELD label RETURN count(label) as count",
                "relationship_type_count": "CALL db.relationshipTypes() YIELD relationshipType RETURN count(relationshipType) as count"
            }
            
            for stat_name, query in stats_queries.items():
                try:
                    result = await self.execute_query(query)
                    if result and len(result) > 0:
                        info[stat_name] = result[0]["count"]
                    else:
                        info[stat_name] = 0
                except Exception as e:
                    logger.warning(f"Failed to get {stat_name}: {e}")
                    info[stat_name] = -1
            
            # Get system information
            try:
                system_result = await self.execute_query("CALL dbms.components() YIELD name, versions, edition")
                components = []
                for record in system_result:
                    components.append({
                        "name": record["name"],
                        "versions": record["versions"],
                        "edition": record["edition"]
                    })
                info["components"] = components
                
                # Extract version from components
                if components:
                    neo4j_component = next((c for c in components if c["name"] == "Neo4j Kernel"), None)
                    if neo4j_component and neo4j_component["versions"]:
                        info["version"] = neo4j_component["versions"][0]
                    else:
                        info["version"] = "unknown"
                else:
                    info["version"] = "unknown"
                    
            except Exception as e:
                logger.debug(f"Could not get system components: {e}")
                info["components"] = []
                info["version"] = "unknown"
            
            # Get index and constraint information
            try:
                index_result = await self.execute_query("SHOW INDEXES YIELD name")
                info["index_count"] = len(index_result)
            except Exception as e:
                logger.debug(f"Could not get index count: {e}")
                info["index_count"] = -1
            
            try:
                constraint_result = await self.execute_query("SHOW CONSTRAINTS YIELD name")
                info["constraint_count"] = len(constraint_result)
            except Exception as e:
                logger.debug(f"Could not get constraint count: {e}")
                info["constraint_count"] = -1
            
            # Set default values for unavailable metrics
            info.setdefault("memory_usage", -1)
            info.setdefault("disk_usage", -1)
            info.setdefault("uptime", -1)
            
            return info
            
        except Exception as e:
            logger.error(f"Failed to get database info: {e}")
            return {
                "database_type": "neo4j",
                "uri": self.uri,
                "database": self.database,
                "error": str(e),
                "node_count": -1,
                "relationship_count": -1,
                "label_count": -1,
                "relationship_type_count": -1,
                "version": "unknown"
            }
    
    # Gremlin Compatibility Layer (Optional)
    class GremlinCompatibilityLayer:
        """
        Optional Gremlin compatibility layer for Neo4j.
        
        This class provides basic Gremlin-like operations that can be translated
        to Cypher queries. This is useful for maintaining compatibility with
        existing Neptune/Gremlin code while using Neo4j as the backend.
        
        Note: This is a simplified compatibility layer and does not support
        the full Gremlin query language. For complex Gremlin queries, consider
        using the neo4j-gremlin plugin or rewriting queries in Cypher.
        """
        
        def __init__(self, neo4j_client: 'Neo4jClient'):
            """Initialize Gremlin compatibility layer."""
            self.client = neo4j_client
        
        async def add_vertex(self, label: str, properties: Dict[str, Any]) -> str:
            """
            Add a vertex (equivalent to create_node).
            
            Args:
                label: Vertex label
                properties: Vertex properties
                
            Returns:
                Vertex ID
            """
            return await self.client.create_node([label], properties)
        
        async def add_edge(
            self, 
            from_vertex_id: str, 
            to_vertex_id: str, 
            edge_label: str,
            properties: Optional[Dict[str, Any]] = None
        ) -> str:
            """
            Add an edge (equivalent to create_relationship).
            
            Args:
                from_vertex_id: Source vertex ID
                to_vertex_id: Target vertex ID
                edge_label: Edge label
                properties: Edge properties
                
            Returns:
                Edge ID
            """
            return await self.client.create_relationship(
                from_vertex_id, to_vertex_id, edge_label, properties
            )
        
        async def get_vertex(self, vertex_id: str) -> Optional[Dict[str, Any]]:
            """
            Get a vertex by ID (equivalent to get_node).
            
            Args:
                vertex_id: Vertex ID
                
            Returns:
                Vertex data or None if not found
            """
            return await self.client.get_node(vertex_id)
        
        async def has_label(self, label: str) -> SearchResults:
            """
            Find all vertices with a specific label.
            
            Args:
                label: Label to search for
                
            Returns:
                List of vertices with the specified label
            """
            query = f"MATCH (n:{label}) RETURN id(n) as id, labels(n) as labels, properties(n) as properties"
            result = await self.client.execute_query(query)
            
            vertices = []
            for record in result:
                vertices.append({
                    "id": str(record["id"]),
                    "labels": record["labels"],
                    "properties": record["properties"] or {}
                })
            
            return vertices
        
        async def has_property(self, property_name: str, property_value: Any) -> SearchResults:
            """
            Find all vertices with a specific property value.
            
            Args:
                property_name: Property name
                property_value: Property value
                
            Returns:
                List of vertices with the specified property
            """
            query = f"MATCH (n) WHERE n.{property_name} = $value RETURN id(n) as id, labels(n) as labels, properties(n) as properties"
            result = await self.client.execute_query(query, {"value": property_value})
            
            vertices = []
            for record in result:
                vertices.append({
                    "id": str(record["id"]),
                    "labels": record["labels"],
                    "properties": record["properties"] or {}
                })
            
            return vertices
        
        async def out_edges(self, vertex_id: str, edge_label: Optional[str] = None) -> SearchResults:
            """
            Get outgoing edges from a vertex.
            
            Args:
                vertex_id: Vertex ID
                edge_label: Optional edge label filter
                
            Returns:
                List of outgoing edges
            """
            if edge_label:
                query = f"""
                MATCH (n)-[r:{edge_label}]->(m)
                WHERE id(n) = $vertex_id
                RETURN id(r) as id, type(r) as type, id(n) as from_vertex_id, 
                       id(m) as to_vertex_id, properties(r) as properties
                """
            else:
                query = """
                MATCH (n)-[r]->(m)
                WHERE id(n) = $vertex_id
                RETURN id(r) as id, type(r) as type, id(n) as from_vertex_id, 
                       id(m) as to_vertex_id, properties(r) as properties
                """
            
            try:
                vertex_id_int = int(vertex_id)
            except ValueError:
                raise ValidationError(
                    f"Invalid vertex ID format: {vertex_id}",
                    field_name="vertex_id",
                    field_value=vertex_id
                )
            
            result = await self.client.execute_query(query, {"vertex_id": vertex_id_int})
            
            edges = []
            for record in result:
                edges.append({
                    "id": str(record["id"]),
                    "type": record["type"],
                    "from_vertex_id": str(record["from_vertex_id"]),
                    "to_vertex_id": str(record["to_vertex_id"]),
                    "properties": record["properties"] or {}
                })
            
            return edges
        
        async def in_edges(self, vertex_id: str, edge_label: Optional[str] = None) -> SearchResults:
            """
            Get incoming edges to a vertex.
            
            Args:
                vertex_id: Vertex ID
                edge_label: Optional edge label filter
                
            Returns:
                List of incoming edges
            """
            if edge_label:
                query = f"""
                MATCH (n)-[r:{edge_label}]->(m)
                WHERE id(m) = $vertex_id
                RETURN id(r) as id, type(r) as type, id(n) as from_vertex_id, 
                       id(m) as to_vertex_id, properties(r) as properties
                """
            else:
                query = """
                MATCH (n)-[r]->(m)
                WHERE id(m) = $vertex_id
                RETURN id(r) as id, type(r) as type, id(n) as from_vertex_id, 
                       id(m) as to_vertex_id, properties(r) as properties
                """
            
            try:
                vertex_id_int = int(vertex_id)
            except ValueError:
                raise ValidationError(
                    f"Invalid vertex ID format: {vertex_id}",
                    field_name="vertex_id",
                    field_value=vertex_id
                )
            
            result = await self.client.execute_query(query, {"vertex_id": vertex_id_int})
            
            edges = []
            for record in result:
                edges.append({
                    "id": str(record["id"]),
                    "type": record["type"],
                    "from_vertex_id": str(record["from_vertex_id"]),
                    "to_vertex_id": str(record["to_vertex_id"]),
                    "properties": record["properties"] or {}
                })
            
            return edges
    
    def get_gremlin_compatibility(self) -> 'Neo4jClient.GremlinCompatibilityLayer':
        """
        Get Gremlin compatibility layer for this client.
        
        Returns:
            GremlinCompatibilityLayer instance for basic Gremlin operations
        """
        return self.GremlinCompatibilityLayer(self)
    
    # Context Manager Support
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()


# Factory function for creating Neo4j clients
def create_neo4j_client(
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = "password",
    database: str = "neo4j",
    **kwargs
) -> Neo4jClient:
    """
    Factory function to create a Neo4j client.
    
    Args:
        uri: Neo4j connection URI
        user: Username for authentication
        password: Password for authentication
        database: Database name
        **kwargs: Additional configuration options
        
    Returns:
        Configured Neo4jClient instance
    """
    return Neo4jClient(
        uri=uri,
        user=user,
        password=password,
        database=database,
        **kwargs
    )


# Global client instance for singleton pattern
_neo4j_client: Optional[Neo4jClient] = None


def get_neo4j_client(
    uri: str = "bolt://localhost:7687",
    user: str = "neo4j",
    password: str = "password",
    database: str = "neo4j"
) -> Neo4jClient:
    """
    Get or create global Neo4j client instance.
    
    Args:
        uri: Neo4j connection URI
        user: Username for authentication
        password: Password for authentication
        database: Database name
        
    Returns:
        Global Neo4jClient instance
    """
    global _neo4j_client
    
    if _neo4j_client is None:
        _neo4j_client = Neo4jClient(
            uri=uri,
            user=user,
            password=password,
            database=database
        )
    
    return _neo4j_client


async def close_neo4j_client() -> None:
    """Close global Neo4j client instance."""
    global _neo4j_client
    
    if _neo4j_client:
        await _neo4j_client.disconnect()
        _neo4j_client = None