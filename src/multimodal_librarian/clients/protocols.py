"""
Database client protocols for the Multimodal Librarian.

This module defines the protocol interfaces for different database types,
enabling consistent APIs across local and AWS implementations.

The protocols defined here ensure that both local development clients (Neo4j, Milvus, PostgreSQL)
and AWS production clients (Neptune, OpenSearch, RDS) implement the same interface, allowing
seamless switching between environments.

Type Aliases:
    DatabaseMetadata: Dictionary containing database metadata and statistics
    QueryParameters: Dictionary of parameters for parameterized queries
    VectorEmbedding: List of float values representing a vector embedding
    NodeProperties: Dictionary of node properties for graph operations
    CollectionStats: Dictionary containing vector collection statistics
    HealthStatus: Dictionary containing health check results
    
Example Usage:
    ```python
    from multimodal_librarian.clients.protocols import VectorStoreClient
    from multimodal_librarian.clients.database_factory import DatabaseClientFactory
    
    # Create a vector store client (local or AWS based on config)
    factory = DatabaseClientFactory(config)
    vector_client: VectorStoreClient = factory.create_vector_store_client()
    
    # Use the client with consistent API regardless of implementation
    await vector_client.connect()
    results = await vector_client.semantic_search("machine learning", top_k=5)
    await vector_client.disconnect()
    ```
"""

from typing import (
    Protocol, List, Dict, Any, Optional, Union, AsyncGenerator, Generator,
    TypeAlias, Literal, Callable, Awaitable, TypeVar, Generic, runtime_checkable
)
from contextlib import asynccontextmanager, contextmanager
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

# Type aliases for better code readability and type safety
DatabaseMetadata: TypeAlias = Dict[str, Any]
QueryParameters: TypeAlias = Dict[str, Any]
VectorEmbedding: TypeAlias = List[float]
NodeProperties: TypeAlias = Dict[str, Any]
CollectionStats: TypeAlias = Dict[str, Any]
HealthStatus: TypeAlias = Dict[str, Any]
ConnectionPoolStats: TypeAlias = Dict[str, Any]
PerformanceMetrics: TypeAlias = Dict[str, Any]
SearchFilters: TypeAlias = Dict[str, Any]
SearchResults: TypeAlias = List[Dict[str, Any]]
GraphPath: TypeAlias = List[Dict[str, Any]]
RelationshipDirection: TypeAlias = Literal["in", "out", "both"]
VectorMetricType: TypeAlias = Literal["L2", "IP", "COSINE"]

# Generic type variables for protocol methods
T = TypeVar('T')
P = TypeVar('P')


@runtime_checkable
class RelationalStoreClient(Protocol):
    """
    Protocol for relational database operations (PostgreSQL).
    
    This protocol defines the interface that both local PostgreSQL clients
    and AWS RDS PostgreSQL clients must implement to ensure consistent
    behavior across different environments.
    
    The protocol supports both synchronous and asynchronous operations,
    connection pooling, transaction management, and schema operations.
    
    Example Implementation:
        ```python
        class LocalPostgreSQLClient:
            async def connect(self) -> None:
                self.engine = create_async_engine(self.connection_string)
                
            async def health_check(self) -> HealthStatus:
                async with self.get_async_session() as session:
                    result = await session.execute(text("SELECT 1"))
                    return {"status": "healthy", "response_time": 0.05}
        ```
    
    Thread Safety:
        Implementations should be thread-safe for connection pooling.
        Individual sessions should not be shared across threads.
    
    Error Handling:
        All methods may raise DatabaseClientError or its subclasses.
        Implementations should provide meaningful error messages and context.
    """
    
    # Connection Management
    async def connect(self) -> None:
        """
        Establish connection to the PostgreSQL database.
        
        This method initializes the database connection pool and verifies
        connectivity. It should be idempotent - calling it multiple times
        should not create multiple connection pools.
        
        Raises:
            ConnectionError: If connection cannot be established
            ConfigurationError: If database configuration is invalid
            
        Example:
            ```python
            client = LocalPostgreSQLClient(config)
            await client.connect()  # Safe to call multiple times
            ```
        """
        ...
    
    async def disconnect(self) -> None:
        """
        Close connection to the PostgreSQL database.
        
        This method closes all connections in the pool and cleans up resources.
        After calling this method, the client should not be used until connect()
        is called again.
        
        Raises:
            ConnectionError: If there are issues closing connections
            
        Example:
            ```python
            await client.disconnect()
            # Client is now unusable until connect() is called again
            ```
        """
        ...
    
    async def health_check(self) -> HealthStatus:
        """
        Perform health check on the PostgreSQL database.
        
        This method verifies that the database is accessible and responsive.
        It should be lightweight and not perform expensive operations.
        
        Returns:
            Dictionary with health status information including:
            - status: "healthy" | "unhealthy" | "degraded"
            - response_time: Response time in seconds
            - connection_count: Number of active connections
            - last_check: Timestamp of last successful check
            
        Raises:
            ConnectionError: If health check cannot be performed
            
        Example:
            ```python
            health = await client.health_check()
            if health["status"] == "healthy":
                print(f"Database responsive in {health['response_time']}s")
            ```
        """
        ...
    
    # Session Management
    @asynccontextmanager
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get an async database session with automatic cleanup.
        
        This context manager provides a database session that is automatically
        committed on success or rolled back on exception. The session is
        properly closed when the context exits.
        
        Yields:
            AsyncSession: SQLAlchemy async session configured for this database
            
        Raises:
            ConnectionError: If session cannot be created
            ResourceError: If connection pool is exhausted
            
        Example:
            ```python
            async with client.get_async_session() as session:
                result = await session.execute(
                    text("SELECT * FROM users WHERE id = :id"),
                    {"id": user_id}
                )
                users = result.fetchall()
            # Session is automatically closed here
            ```
        """
        ...
    
    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Get a synchronous database session with automatic cleanup.
        
        This context manager provides a synchronous database session for
        compatibility with synchronous code. Prefer get_async_session()
        for new code.
        
        Yields:
            Session: SQLAlchemy synchronous session
            
        Raises:
            ConnectionError: If session cannot be created
            ResourceError: If connection pool is exhausted
            
        Example:
            ```python
            with client.get_session() as session:
                users = session.execute(
                    text("SELECT * FROM users WHERE active = :active"),
                    {"active": True}
                ).fetchall()
            # Session is automatically closed here
            ```
        """
        ...
    
    # Query Execution
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
            parameters: Query parameters for safe parameterized queries.
                       Keys should match parameter placeholders in the query.
                       
        Returns:
            List of result rows as dictionaries with column names as keys
            
        Raises:
            QueryError: If query execution fails or has syntax errors
            ValidationError: If parameters are invalid
            TimeoutError: If query execution times out
            
        Example:
            ```python
            results = await client.execute_query(
                "SELECT id, name, email FROM users WHERE created_at > :date",
                {"date": datetime(2023, 1, 1)}
            )
            for row in results:
                print(f"User: {row['name']} ({row['email']})")
            ```
        """
        ...
    
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
            
        Raises:
            QueryError: If command execution fails
            ValidationError: If parameters are invalid
            TransactionError: If transaction cannot be committed
            
        Example:
            ```python
            affected = await client.execute_command(
                "UPDATE users SET last_login = :now WHERE id = :user_id",
                {"now": datetime.utcnow(), "user_id": 123}
            )
            print(f"Updated {affected} user records")
            ```
        """
        ...
    
    # Transaction Management
    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Create a database transaction context.
        
        This context manager provides a database session within a transaction.
        The transaction is automatically committed on success or rolled back
        on exception. Use this for operations that require atomicity.
        
        Yields:
            AsyncSession: Session within transaction context
            
        Raises:
            TransactionError: If transaction cannot be started or committed
            ConnectionError: If database connection is lost during transaction
            
        Example:
            ```python
            async with client.transaction() as session:
                # Create user
                user_result = await session.execute(
                    text("INSERT INTO users (name, email) VALUES (:name, :email) RETURNING id"),
                    {"name": "John Doe", "email": "john@example.com"}
                )
                user_id = user_result.scalar()
                
                # Create user profile
                await session.execute(
                    text("INSERT INTO profiles (user_id, bio) VALUES (:user_id, :bio)"),
                    {"user_id": user_id, "bio": "Software developer"}
                )
            # Both operations committed atomically
            ```
        """
        ...
    
    # Schema Management
    async def create_tables(self) -> None:
        """
        Create all database tables based on SQLAlchemy models.
        
        This method creates all tables defined in the application's SQLAlchemy
        models. It should be idempotent - calling it multiple times should not
        cause errors if tables already exist.
        
        Raises:
            SchemaError: If table creation fails
            ConnectionError: If database is not accessible
            
        Example:
            ```python
            await client.create_tables()
            print("All database tables created successfully")
            ```
        """
        ...
    
    async def drop_tables(self) -> None:
        """
        Drop all database tables. Use with caution!
        
        This method drops all tables in the database. This operation is
        irreversible and will result in data loss. Only use in development
        or testing environments.
        
        Raises:
            SchemaError: If table dropping fails
            ConnectionError: If database is not accessible
            
        Warning:
            This operation will permanently delete all data in the database.
            
        Example:
            ```python
            # Only in development/testing!
            if config.environment == "development":
                await client.drop_tables()
                print("All tables dropped")
            ```
        """
        ...
    
    async def migrate_schema(self, migration_script: str) -> None:
        """
        Execute a database migration script.
        
        This method executes a SQL migration script to update the database
        schema. The script should be idempotent and handle existing schema
        gracefully.
        
        Args:
            migration_script: SQL migration script to execute
            
        Raises:
            SchemaError: If migration execution fails
            QueryError: If migration script has syntax errors
            
        Example:
            ```python
            migration = '''
            ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();
            CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at);
            '''
            await client.migrate_schema(migration)
            ```
        """
        ...
    
    # Connection Pool Management
    def get_pool_status(self) -> ConnectionPoolStats:
        """
        Get connection pool status information.
        
        This method returns information about the current state of the
        connection pool, useful for monitoring and debugging.
        
        Returns:
            Dictionary with pool statistics including:
            - size: Total pool size
            - checked_in: Number of connections currently in use
            - checked_out: Number of available connections
            - overflow: Number of overflow connections
            - invalid: Number of invalid connections
            
        Example:
            ```python
            stats = client.get_pool_status()
            print(f"Pool usage: {stats['checked_out']}/{stats['size']}")
            if stats['checked_out'] / stats['size'] > 0.8:
                print("Warning: Connection pool usage is high")
            ```
        """
        ...
    
    async def reset_pool(self) -> None:
        """
        Reset the connection pool.
        
        This method closes all connections in the pool and recreates it.
        Use this to recover from connection issues or to apply new
        configuration settings.
        
        Raises:
            ConnectionError: If pool cannot be reset
            
        Example:
            ```python
            # Reset pool after configuration change
            await client.reset_pool()
            print("Connection pool reset successfully")
            ```
        """
        ...
    
    # Backup and Restore
    async def backup_database(self, backup_path: str) -> bool:
        """
        Create a database backup.
        
        This method creates a backup of the database to the specified path.
        The backup format depends on the implementation (SQL dump, binary, etc.).
        
        Args:
            backup_path: Path where backup should be stored
            
        Returns:
            True if backup was successful, False otherwise
            
        Raises:
            SchemaError: If backup operation fails
            ValidationError: If backup path is invalid
            
        Example:
            ```python
            backup_file = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
            success = await client.backup_database(backup_file)
            if success:
                print(f"Database backed up to {backup_file}")
            ```
        """
        ...
    
    async def restore_database(self, backup_path: str) -> bool:
        """
        Restore database from backup.
        
        This method restores the database from a backup file. This operation
        will overwrite existing data, so use with caution.
        
        Args:
            backup_path: Path to backup file
            
        Returns:
            True if restore was successful, False otherwise
            
        Raises:
            SchemaError: If restore operation fails
            ValidationError: If backup file is invalid or not found
            
        Warning:
            This operation will overwrite existing database data.
            
        Example:
            ```python
            success = await client.restore_database("backup_20231201_120000.sql")
            if success:
                print("Database restored successfully")
            ```
        """
        ...
    
    # Database Information
    async def get_database_info(self) -> DatabaseMetadata:
        """
        Get database information and statistics.
        
        This method returns comprehensive information about the database
        including version, size, table count, and other metadata.
        
        Returns:
            Dictionary with database metadata including:
            - version: Database version string
            - size: Database size in bytes
            - table_count: Number of tables
            - connection_count: Current connection count
            - uptime: Database uptime in seconds
            - charset: Database character set
            
        Example:
            ```python
            info = await client.get_database_info()
            print(f"PostgreSQL {info['version']}")
            print(f"Database size: {info['size'] / 1024 / 1024:.2f} MB")
            print(f"Tables: {info['table_count']}")
            ```
        """
        ...
    
    async def get_table_info(self, table_name: str) -> DatabaseMetadata:
        """
        Get information about a specific table.
        
        This method returns detailed information about a table including
        column definitions, indexes, constraints, and statistics.
        
        Args:
            table_name: Name of the table
            
        Returns:
            Dictionary with table metadata including:
            - name: Table name
            - columns: List of column definitions
            - indexes: List of indexes
            - row_count: Approximate number of rows
            - size: Table size in bytes
            - last_analyzed: Last statistics update timestamp
            
        Raises:
            ValidationError: If table does not exist
            
        Example:
            ```python
            table_info = await client.get_table_info("users")
            print(f"Table: {table_info['name']}")
            print(f"Rows: {table_info['row_count']}")
            for column in table_info['columns']:
                print(f"  {column['name']}: {column['type']}")
            ```
        """
        ...
    
    # Performance and Monitoring
    async def get_performance_stats(self) -> PerformanceMetrics:
        """
        Get database performance statistics.
        
        This method returns performance metrics useful for monitoring
        and optimization, including query statistics and resource usage.
        
        Returns:
            Dictionary with performance metrics including:
            - queries_per_second: Average queries per second
            - avg_query_time: Average query execution time
            - slow_queries: Number of slow queries
            - cache_hit_ratio: Query cache hit ratio
            - active_connections: Number of active connections
            - cpu_usage: CPU usage percentage
            - memory_usage: Memory usage in bytes
            
        Example:
            ```python
            stats = await client.get_performance_stats()
            print(f"QPS: {stats['queries_per_second']:.2f}")
            print(f"Avg query time: {stats['avg_query_time']:.3f}s")
            if stats['cache_hit_ratio'] < 0.9:
                print("Warning: Low cache hit ratio")
            ```
        """
        ...
    
    async def analyze_table(self, table_name: str) -> None:
        """
        Analyze table statistics for query optimization.
        
        This method updates table statistics used by the query planner
        to optimize query execution plans. Run this after significant
        data changes.
        
        Args:
            table_name: Name of the table to analyze
            
        Raises:
            ValidationError: If table does not exist
            QueryError: If analysis fails
            
        Example:
            ```python
            # After bulk data insert
            await client.execute_command(
                "INSERT INTO users SELECT * FROM temp_users"
            )
            await client.analyze_table("users")
            print("Table statistics updated")
            ```
        """
        ...


class VectorStoreClient(Protocol):
    """
    Protocol for vector database operations (Milvus/OpenSearch).
    
    This protocol defines the interface that both local Milvus clients
    and AWS OpenSearch clients must implement for vector similarity search.
    
    The protocol supports vector storage, similarity search, collection management,
    and high-level operations for document chunk storage and retrieval.
    
    Vector Operations:
        - Store and retrieve high-dimensional vectors (typically 384-1536 dimensions)
        - Perform similarity search using various distance metrics (L2, cosine, inner product)
        - Manage collections/indexes for different document types
        - Support metadata filtering and hybrid search
    
    Example Implementation:
        ```python
        class MilvusClient:
            async def connect(self) -> None:
                connections.connect(host=self.host, port=self.port)
                
            async def semantic_search(
                self, query: str, top_k: int = 10
            ) -> SearchResults:
                embedding = self.generate_embedding(query)
                return await self.search_vectors("documents", embedding, top_k)
        ```
    
    Performance Considerations:
        - Vector operations can be memory-intensive for large collections
        - Index building may take significant time for large datasets
        - Consider batch operations for bulk inserts
        - Use appropriate distance metrics for your embedding model
    
    Thread Safety:
        Implementations should be thread-safe for concurrent search operations.
        Collection modifications should be properly synchronized.
    """
    
    # Connection Management
    async def connect(self) -> None:
        """
        Establish connection to the vector database.
        
        This method initializes the connection to the vector database and
        verifies that the service is accessible. For Milvus, this establishes
        a connection to the server. For OpenSearch, this verifies cluster health.
        
        Raises:
            ConnectionError: If connection cannot be established
            ConfigurationError: If vector database configuration is invalid
            
        Example:
            ```python
            client = MilvusClient(host="localhost", port=19530)
            await client.connect()
            print("Connected to Milvus successfully")
            ```
        """
        ...
    
    async def disconnect(self) -> None:
        """
        Close connection to the vector database.
        
        This method closes the connection and cleans up resources. After calling
        this method, the client should not be used until connect() is called again.
        
        Raises:
            ConnectionError: If there are issues closing the connection
            
        Example:
            ```python
            await client.disconnect()
            print("Disconnected from vector database")
            ```
        """
        ...
    
    async def health_check(self) -> HealthStatus:
        """
        Perform health check on the vector database.
        
        This method verifies that the vector database is accessible and responsive.
        It checks service availability, memory usage, and basic functionality.
        
        Returns:
            Dictionary with health status information including:
            - status: "healthy" | "unhealthy" | "degraded"
            - response_time: Response time in seconds
            - memory_usage: Memory usage percentage
            - collection_count: Number of collections
            - total_vectors: Total number of vectors stored
            - index_status: Status of vector indexes
            
        Raises:
            ConnectionError: If health check cannot be performed
            
        Example:
            ```python
            health = await client.health_check()
            if health["status"] == "healthy":
                print(f"Vector DB healthy with {health['total_vectors']} vectors")
            else:
                print(f"Vector DB issues: {health.get('error', 'Unknown')}")
            ```
        """
        ...
    
    # Collection/Index Management
    async def create_collection(
        self, 
        collection_name: str, 
        dimension: int,
        metric_type: VectorMetricType = "L2"
    ) -> bool:
        """
        Create a vector collection/index.
        
        This method creates a new collection for storing vectors with the
        specified dimension and distance metric. The collection will be
        optimized for the chosen metric type.
        
        Args:
            collection_name: Name of the collection (must be unique)
            dimension: Vector dimension (e.g., 384 for sentence-transformers,
                      1536 for OpenAI embeddings)
            metric_type: Distance metric for similarity search:
                        - "L2": Euclidean distance (default)
                        - "IP": Inner product (for normalized vectors)
                        - "COSINE": Cosine similarity
                       
        Returns:
            True if collection was created successfully, False if it already exists
            
        Raises:
            SchemaError: If collection creation fails
            ValidationError: If parameters are invalid
            
        Example:
            ```python
            # Create collection for sentence-transformer embeddings
            success = await client.create_collection(
                "document_chunks", 
                dimension=384, 
                metric_type="COSINE"
            )
            if success:
                print("Collection created for document embeddings")
            ```
        """
        ...
    
    async def delete_collection(self, collection_name: str) -> bool:
        """
        Delete a vector collection.
        
        This method permanently deletes a collection and all its vectors.
        This operation cannot be undone.
        
        Args:
            collection_name: Name of the collection to delete
            
        Returns:
            True if collection was deleted successfully, False if it didn't exist
            
        Raises:
            SchemaError: If collection deletion fails
            
        Warning:
            This operation permanently deletes all vectors in the collection.
            
        Example:
            ```python
            # Delete old collection
            success = await client.delete_collection("old_embeddings")
            if success:
                print("Collection deleted successfully")
            ```
        """
        ...
    
    async def list_collections(self) -> List[str]:
        """
        List all available collections.
        
        This method returns the names of all collections in the vector database.
        
        Returns:
            List of collection names
            
        Raises:
            ConnectionError: If database is not accessible
            
        Example:
            ```python
            collections = await client.list_collections()
            print(f"Available collections: {', '.join(collections)}")
            for collection in collections:
                stats = await client.get_collection_stats(collection)
                print(f"  {collection}: {stats['vector_count']} vectors")
            ```
        """
        ...
    
    # Vector Operations
    async def insert_vectors(
        self, 
        collection_name: str,
        vectors: List[Dict[str, Any]]
    ) -> bool:
        """
        Insert vectors into a collection.
        
        This method inserts a batch of vectors with their metadata into the
        specified collection. Each vector should include an embedding and
        associated metadata.
        
        Args:
            collection_name: Name of the target collection
            vectors: List of vector documents, each containing:
                    - id: Unique identifier for the vector
                    - vector: List of float values (embedding)
                    - metadata: Dictionary with additional fields like:
                      - content: Original text content
                      - source_id: ID of source document
                      - chunk_index: Position in source document
                      - content_type: Type of content (text, image, etc.)
                      
        Returns:
            True if vectors were inserted successfully
            
        Raises:
            ValidationError: If vector format is invalid
            SchemaError: If collection doesn't exist
            ResourceError: If storage quota is exceeded
            
        Example:
            ```python
            vectors = [
                {
                    "id": "doc1_chunk1",
                    "vector": [0.1, 0.2, 0.3, ...],  # 384-dim embedding
                    "metadata": {
                        "content": "Machine learning is a subset of AI...",
                        "source_id": "doc1",
                        "chunk_index": 0,
                        "content_type": "text"
                    }
                },
                # ... more vectors
            ]
            success = await client.insert_vectors("document_chunks", vectors)
            print(f"Inserted {len(vectors)} vectors")
            ```
        """
        ...
    
    async def search_vectors(
        self, 
        collection_name: str,
        query_vector: VectorEmbedding, 
        k: int = 10,
        filters: Optional[SearchFilters] = None
    ) -> SearchResults:
        """
        Search for similar vectors.
        
        This method performs similarity search to find the k most similar
        vectors to the query vector, optionally filtered by metadata.
        
        Args:
            collection_name: Name of the collection to search
            query_vector: Query vector for similarity search (must match
                         collection dimension)
            k: Number of results to return (default: 10)
            filters: Optional metadata filters, e.g.:
                    - {"source_id": "doc123"}: Only from specific document
                    - {"content_type": "text"}: Only text content
                    - {"chunk_index": {"$gte": 5}}: Advanced filtering
            
        Returns:
            List of similar vectors with scores and metadata, each containing:
            - id: Vector ID
            - score: Similarity score (lower is more similar for L2)
            - metadata: Associated metadata
            - vector: Original vector (optional, for debugging)
            
        Raises:
            ValidationError: If query vector dimension doesn't match
            QueryError: If search fails
            
        Example:
            ```python
            # Search for similar content
            query_embedding = model.encode("What is machine learning?")
            results = await client.search_vectors(
                "document_chunks",
                query_embedding.tolist(),
                k=5,
                filters={"content_type": "text"}
            )
            
            for result in results:
                print(f"Score: {result['score']:.3f}")
                print(f"Content: {result['metadata']['content'][:100]}...")
            ```
        """
        ...
    
    async def get_vector_by_id(
        self, 
        collection_name: str,
        vector_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific vector by ID.
        
        This method retrieves a vector and its metadata by its unique ID.
        
        Args:
            collection_name: Name of the collection
            vector_id: ID of the vector to retrieve
            
        Returns:
            Vector document with id, vector, and metadata, or None if not found
            
        Raises:
            ValidationError: If collection doesn't exist
            
        Example:
            ```python
            vector_doc = await client.get_vector_by_id("documents", "doc1_chunk5")
            if vector_doc:
                print(f"Found vector: {vector_doc['metadata']['content'][:50]}...")
            else:
                print("Vector not found")
            ```
        """
        ...
    
    async def delete_vectors(
        self, 
        collection_name: str,
        vector_ids: List[str]
    ) -> int:
        """
        Delete vectors by IDs.
        
        This method deletes multiple vectors from a collection by their IDs.
        
        Args:
            collection_name: Name of the collection
            vector_ids: List of vector IDs to delete
            
        Returns:
            Number of vectors actually deleted
            
        Raises:
            ValidationError: If collection doesn't exist
            
        Example:
            ```python
            # Delete specific chunks
            deleted_count = await client.delete_vectors(
                "documents", 
                ["doc1_chunk1", "doc1_chunk2", "doc1_chunk3"]
            )
            print(f"Deleted {deleted_count} vectors")
            ```
        """
        ...
    
    # Collection Statistics
    async def get_collection_stats(self, collection_name: str) -> CollectionStats:
        """
        Get statistics about a collection.
        
        This method returns comprehensive statistics about a collection
        including size, performance metrics, and configuration.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            Dictionary with collection statistics including:
            - name: Collection name
            - vector_count: Number of vectors stored
            - dimension: Vector dimension
            - metric_type: Distance metric used
            - index_type: Type of index (IVF_FLAT, HNSW, etc.)
            - memory_usage: Memory usage in bytes
            - disk_usage: Disk usage in bytes
            - last_updated: Last modification timestamp
            
        Raises:
            ValidationError: If collection doesn't exist
            
        Example:
            ```python
            stats = await client.get_collection_stats("document_chunks")
            print(f"Collection: {stats['name']}")
            print(f"Vectors: {stats['vector_count']:,}")
            print(f"Dimension: {stats['dimension']}")
            print(f"Memory: {stats['memory_usage'] / 1024 / 1024:.2f} MB")
            ```
        """
        ...
    
    # High-level Operations (for compatibility with existing codebase)
    async def store_embeddings(self, chunks: List[Dict[str, Any]]) -> None:
        """
        Store chunk embeddings with metadata (high-level interface).
        
        This method provides a high-level interface for storing document chunks
        with their embeddings and metadata, compatible with existing codebase.
        It handles embedding generation if not provided and manages collection
        creation automatically.
        
        Args:
            chunks: List of knowledge chunks to store, each containing:
                   - content: Text content (required)
                   - embedding: Vector embedding (optional, will be generated)
                   - metadata: Additional metadata fields like:
                     - source_id: Document ID
                     - chunk_index: Position in document
                     - content_type: Type of content
                     - title: Document title
                     - author: Document author
                     
        Raises:
            ValidationError: If chunk format is invalid
            SchemaError: If collection operations fail
            
        Example:
            ```python
            chunks = [
                {
                    "content": "Machine learning is a method of data analysis...",
                    "metadata": {
                        "source_id": "ml_textbook",
                        "chunk_index": 0,
                        "title": "Introduction to ML",
                        "content_type": "text"
                    }
                },
                # ... more chunks
            ]
            await client.store_embeddings(chunks)
            print(f"Stored {len(chunks)} document chunks")
            ```
        """
        ...
    
    async def semantic_search(
        self, 
        query: str, 
        top_k: int = 10,
        filters: Optional[SearchFilters] = None
    ) -> SearchResults:
        """
        Perform semantic similarity search using text query.
        
        This method provides a high-level interface that handles embedding
        generation internally and returns formatted results. It's the main
        interface for semantic search in the application.
        
        Args:
            query: Search query text (will be embedded automatically)
            top_k: Number of results to return (default: 10)
            filters: Optional metadata filters for search refinement:
                    - source_type: Filter by document type
                    - content_type: Filter by content type
                    - date_range: Filter by date range
                    - author: Filter by author
                    
        Returns:
            List of search results with metadata and similarity scores:
            - content: Original text content
            - score: Similarity score (normalized 0-1, higher is better)
            - metadata: Document metadata
            - source_id: Source document ID
            - chunk_index: Position in source document
            
        Raises:
            ValidationError: If query is empty or invalid
            QueryError: If search fails
            
        Example:
            ```python
            # Search for machine learning content
            results = await client.semantic_search(
                "What are neural networks?",
                top_k=5,
                filters={"content_type": "text", "source_type": "academic"}
            )
            
            for i, result in enumerate(results, 1):
                print(f"{i}. Score: {result['score']:.3f}")
                print(f"   Source: {result['metadata']['title']}")
                print(f"   Content: {result['content'][:100]}...")
                print()
            ```
        """
        ...
    
    async def get_chunk_by_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific chunk by its ID.
        
        This method retrieves a document chunk by its unique identifier,
        returning both the content and metadata.
        
        Args:
            chunk_id: ID of the chunk to retrieve
            
        Returns:
            Chunk data with metadata or None if not found:
            - id: Chunk ID
            - content: Text content
            - metadata: Associated metadata
            - embedding: Vector embedding (optional)
            
        Example:
            ```python
            chunk = await client.get_chunk_by_id("doc1_chunk_5")
            if chunk:
                print(f"Chunk content: {chunk['content']}")
                print(f"From document: {chunk['metadata']['source_id']}")
            ```
        """
        ...
    
    async def delete_chunks_by_source(self, source_id: str) -> int:
        """
        Delete all chunks from a specific source.
        
        This method deletes all document chunks that belong to a specific
        source document. Useful when removing or updating documents.
        
        Args:
            source_id: ID of the source to delete chunks from
            
        Returns:
            Number of chunks deleted
            
        Example:
            ```python
            # Remove all chunks from a document
            deleted = await client.delete_chunks_by_source("old_document_123")
            print(f"Removed {deleted} chunks from document")
            ```
        """
        ...
    
    # Embedding Operations
    def generate_embedding(self, text: str) -> VectorEmbedding:
        """
        Generate embedding vector for text.
        
        This method generates a vector embedding for the given text using
        the configured embedding model. The embedding dimension should match
        the collection dimension.
        
        Note: This method is synchronous as embedding generation is typically
        CPU-bound and doesn't benefit from async/await.
        
        Args:
            text: Text to embed (should be preprocessed/cleaned)
            
        Returns:
            Embedding vector as list of floats
            
        Raises:
            ValidationError: If text is empty or too long
            ResourceError: If embedding model is not available
            
        Example:
            ```python
            # Generate embedding for search query
            text = "What is machine learning?"
            embedding = client.generate_embedding(text)
            print(f"Generated {len(embedding)}-dimensional embedding")
            
            # Use embedding for search
            results = await client.search_vectors("documents", embedding, k=5)
            ```
        """
        ...
    
    # Index Management (for advanced use cases)
    async def create_index(
        self, 
        collection_name: str,
        field_name: str,
        index_params: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Create an index on a collection field for optimized search.
        
        This method creates an index to optimize search performance on
        specific fields. Different index types are suitable for different
        use cases and data sizes.
        
        Args:
            collection_name: Name of the collection
            field_name: Name of the field to index (usually "vector")
            index_params: Index-specific parameters:
                         - index_type: "IVF_FLAT", "IVF_SQ8", "HNSW", etc.
                         - metric_type: Distance metric
                         - params: Index-specific configuration
                         
        Returns:
            True if index was created successfully
            
        Raises:
            SchemaError: If index creation fails
            ValidationError: If parameters are invalid
            
        Example:
            ```python
            # Create HNSW index for fast approximate search
            index_params = {
                "index_type": "HNSW",
                "metric_type": "L2",
                "params": {"M": 16, "efConstruction": 200}
            }
            success = await client.create_index(
                "document_chunks", 
                "vector", 
                index_params
            )
            if success:
                print("HNSW index created for fast search")
            ```
        """
        ...
    
    async def drop_index(
        self, 
        collection_name: str,
        index_name: str
    ) -> bool:
        """
        Drop an index from a collection.
        
        This method removes an index from a collection. This will slow down
        search operations but may be necessary for index rebuilding or
        configuration changes.
        
        Args:
            collection_name: Name of the collection
            index_name: Name of the index to drop
            
        Returns:
            True if index was dropped successfully
            
        Raises:
            SchemaError: If index dropping fails
            
        Example:
            ```python
            # Drop old index before creating new one
            success = await client.drop_index("documents", "vector_index")
            if success:
                print("Old index dropped, ready for rebuild")
            ```
        """
        ...


class GraphStoreClient(Protocol):
    """
    Protocol for graph database operations (Neo4j/Neptune).
    
    This protocol defines the interface that both local Neo4j clients
    and AWS Neptune clients must implement for graph operations.
    
    The protocol supports node and relationship operations, graph traversal,
    path finding, and complex graph analytics. It abstracts the differences
    between Cypher (Neo4j) and Gremlin (Neptune) query languages.
    
    Graph Operations:
        - Create, read, update, delete nodes and relationships
        - Execute complex graph queries and traversals
        - Perform graph analytics (shortest path, centrality, etc.)
        - Support both property graphs and RDF graphs
    
    Example Implementation:
        ```python
        class Neo4jClient:
            async def connect(self) -> None:
                self.driver = GraphDatabase.driver(
                    self.uri, auth=(self.user, self.password)
                )
                
            async def create_node(
                self, labels: List[str], properties: NodeProperties
            ) -> str:
                query = "CREATE (n:" + ":".join(labels) + " $props) RETURN id(n)"
                result = await self.execute_query(query, {"props": properties})
                return str(result[0]["id(n)"])
        ```
    
    Query Language Abstraction:
        Implementations should handle query language differences internally:
        - Neo4j: Use Cypher queries
        - Neptune: Use Gremlin traversals
        - The protocol provides a unified interface regardless of backend
    
    Performance Considerations:
        - Graph operations can be expensive for large graphs
        - Use indexes on frequently queried properties
        - Consider query optimization for complex traversals
        - Batch operations when possible for bulk updates
    
    Thread Safety:
        Implementations should be thread-safe for concurrent read operations.
        Write operations should be properly synchronized to maintain consistency.
    """
    
    # Connection Management
    async def connect(self) -> None:
        """
        Establish connection to the graph database.
        
        This method initializes the connection to the graph database and
        verifies connectivity. For Neo4j, this creates a driver instance.
        For Neptune, this establishes a connection to the cluster.
        
        Raises:
            ConnectionError: If connection cannot be established
            ConfigurationError: If graph database configuration is invalid
            
        Example:
            ```python
            client = Neo4jClient(uri="bolt://localhost:7687", 
                               user="neo4j", password="password")
            await client.connect()
            print("Connected to Neo4j successfully")
            ```
        """
        ...
    
    async def disconnect(self) -> None:
        """
        Close connection to the graph database.
        
        This method closes all connections and cleans up resources. After
        calling this method, the client should not be used until connect()
        is called again.
        
        Raises:
            ConnectionError: If there are issues closing connections
            
        Example:
            ```python
            await client.disconnect()
            print("Disconnected from graph database")
            ```
        """
        ...
    
    async def health_check(self) -> HealthStatus:
        """
        Perform health check on the graph database.
        
        This method verifies that the graph database is accessible and
        responsive. It checks connectivity, memory usage, and basic functionality.
        
        Returns:
            Dictionary with health status information including:
            - status: "healthy" | "unhealthy" | "degraded"
            - response_time: Response time in seconds
            - node_count: Total number of nodes
            - relationship_count: Total number of relationships
            - memory_usage: Memory usage percentage
            - active_transactions: Number of active transactions
            - query_cache_hit_ratio: Query cache performance
            
        Raises:
            ConnectionError: If health check cannot be performed
            
        Example:
            ```python
            health = await client.health_check()
            if health["status"] == "healthy":
                print(f"Graph DB: {health['node_count']} nodes, "
                      f"{health['relationship_count']} relationships")
            else:
                print(f"Graph DB issues: {health.get('error', 'Unknown')}")
            ```
        """
        ...
    
    # Query Execution
    async def execute_query(
        self, 
        query: str, 
        parameters: Optional[QueryParameters] = None
    ) -> SearchResults:
        """
        Execute a graph query and return results.
        
        This method executes a graph query in the appropriate query language
        (Cypher for Neo4j, Gremlin for Neptune) and returns standardized results.
        
        Args:
            query: Graph query string in the appropriate language:
                  - Neo4j: Cypher query (e.g., "MATCH (n:User) RETURN n")
                  - Neptune: Gremlin traversal (e.g., "g.V().hasLabel('User')")
            parameters: Query parameters for safe parameterized queries
            
        Returns:
            List of result records as dictionaries
            
        Raises:
            QueryError: If query execution fails or has syntax errors
            ValidationError: If parameters are invalid
            TimeoutError: If query execution times out
            
        Example:
            ```python
            # Find users and their connections
            query = '''
            MATCH (u:User)-[r:FOLLOWS]->(f:User)
            WHERE u.name = $username
            RETURN u.name, f.name, r.since
            '''
            results = await client.execute_query(
                query, 
                {"username": "alice"}
            )
            
            for result in results:
                print(f"{result['u.name']} follows {result['f.name']} "
                      f"since {result['r.since']}")
            ```
        """
        ...
    
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
            properties: Node properties as key-value pairs:
                       - name: Node name or identifier
                       - type: Node type or category
                       - created_at: Creation timestamp
                       - Any domain-specific properties
                       
        Returns:
            Unique node ID assigned by the database
            
        Raises:
            ValidationError: If labels or properties are invalid
            SchemaError: If node creation violates constraints
            
        Example:
            ```python
            # Create a user node
            node_id = await client.create_node(
                labels=["User", "Person"],
                properties={
                    "name": "Alice Johnson",
                    "email": "alice@example.com",
                    "age": 30,
                    "created_at": datetime.utcnow().isoformat()
                }
            )
            print(f"Created user node with ID: {node_id}")
            ```
        """
        ...
    
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
            
        Example:
            ```python
            node = await client.get_node("123")
            if node:
                print(f"Node: {node['properties']['name']}")
                print(f"Labels: {', '.join(node['labels'])}")
                print(f"Properties: {node['properties']}")
            else:
                print("Node not found")
            ```
        """
        ...
    
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
            
        Example:
            ```python
            # Update user's last login time
            success = await client.update_node(
                "123",
                {
                    "last_login": datetime.utcnow().isoformat(),
                    "login_count": 42
                }
            )
            if success:
                print("Node updated successfully")
            ```
        """
        ...
    
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
            
        Warning:
            This operation also deletes all relationships connected to the node.
            
        Example:
            ```python
            success = await client.delete_node("123")
            if success:
                print("Node and all its relationships deleted")
            ```
        """
        ...
    
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
            properties: Optional relationship properties:
                       - weight: Relationship strength or weight
                       - created_at: Creation timestamp
                       - since: Start date of relationship
                       - Any domain-specific properties
                       
        Returns:
            Unique relationship ID assigned by the database
            
        Raises:
            ValidationError: If node IDs don't exist or relationship type is invalid
            SchemaError: If relationship creation violates constraints
            
        Example:
            ```python
            # Create a "follows" relationship
            rel_id = await client.create_relationship(
                from_node_id="user_123",
                to_node_id="user_456", 
                relationship_type="FOLLOWS",
                properties={
                    "since": "2023-01-15",
                    "weight": 0.8,
                    "created_at": datetime.utcnow().isoformat()
                }
            )
            print(f"Created relationship with ID: {rel_id}")
            ```
        """
        ...
    
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
            
        Example:
            ```python
            # Get all relationships for a user
            relationships = await client.get_relationships("user_123", "out")
            
            for rel in relationships:
                print(f"User follows {rel['to_node_id']} "
                      f"since {rel['properties'].get('since', 'unknown')}")
            ```
        """
        ...
    
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
            
        Example:
            ```python
            success = await client.delete_relationship("rel_789")
            if success:
                print("Relationship deleted successfully")
            ```
        """
        ...
    
    # Graph Analysis
    async def find_path(
        self, 
        from_node_id: str, 
        to_node_id: str,
        max_depth: int = 5
    ) -> GraphPath:
        """
        Find paths between two nodes.
        
        This method finds paths between two nodes up to a specified maximum
        depth. It can return shortest paths or all paths depending on
        implementation.
        
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
            
        Example:
            ```python
            # Find shortest path between users
            paths = await client.find_path("user_123", "user_789", max_depth=3)
            
            if paths:
                shortest = min(paths, key=lambda p: p['length'])
                print(f"Shortest path: {shortest['length']} hops")
                print(f"Path: {' -> '.join(shortest['nodes'])}")
            else:
                print("No path found")
            ```
        """
        ...
    
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
            
        Example:
            ```python
            # Get immediate neighbors
            neighbors = await client.get_neighbors("user_123", depth=1)
            
            print(f"User has {len(neighbors)} direct connections:")
            for neighbor in neighbors:
                print(f"  - {neighbor['properties']['name']} "
                      f"({neighbor['id']})")
                      
            # Get extended network (2 hops)
            extended = await client.get_neighbors("user_123", depth=2)
            print(f"Extended network: {len(extended)} users within 2 hops")
            ```
        """
        ...
    
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
            - memory_usage: Memory usage in bytes
            - disk_usage: Disk usage in bytes
            - index_count: Number of indexes
            - constraint_count: Number of constraints
            - uptime: Database uptime in seconds
            
        Example:
            ```python
            info = await client.get_database_info()
            print(f"Graph Database: {info['version']}")
            print(f"Nodes: {info['node_count']:,}")
            print(f"Relationships: {info['relationship_count']:,}")
            print(f"Labels: {info['label_count']}")
            print(f"Memory: {info['memory_usage'] / 1024 / 1024:.2f} MB")
            ```
        """
        ...


# Base exception classes for database errors
class DatabaseClientError(Exception):
    """
    Base exception for all database client errors.
    
    This is the root exception class for all database-related errors in the
    Multimodal Librarian application. It provides common functionality for
    error handling, logging, and debugging.
    
    Attributes:
        message: Human-readable error message
        error_code: Optional error code for programmatic handling
        context: Additional context information about the error
        original_exception: The original exception that caused this error (if any)
    """
    
    def __init__(
        self, 
        message: str, 
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        original_exception: Optional[Exception] = None
    ):
        """
        Initialize database client error.
        
        Args:
            message: Human-readable error message
            error_code: Optional error code for programmatic handling
            context: Additional context information about the error
            original_exception: The original exception that caused this error
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or {}
        self.original_exception = original_exception
    
    def __str__(self) -> str:
        """Return string representation of the error."""
        parts = [self.message]
        
        if self.error_code:
            parts.append(f"Error Code: {self.error_code}")
        
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            parts.append(f"Context: {context_str}")
        
        if self.original_exception:
            parts.append(f"Caused by: {type(self.original_exception).__name__}: {self.original_exception}")
        
        return " | ".join(parts)
    
    def __repr__(self) -> str:
        """Return detailed representation of the error."""
        return (
            f"{self.__class__.__name__}("
            f"message='{self.message}', "
            f"error_code='{self.error_code}', "
            f"context={self.context}, "
            f"original_exception={self.original_exception})"
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert error to dictionary for serialization.
        
        Returns:
            Dictionary representation of the error
        """
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "context": self.context,
            "original_exception": (
                f"{type(self.original_exception).__name__}: {self.original_exception}" 
                if self.original_exception else None
            )
        }


class ConnectionError(DatabaseClientError):
    """
    Raised when database connection operations fail.
    
    This exception is raised when:
    - Initial connection to database fails
    - Connection is lost during operation
    - Connection pool exhaustion
    - Authentication/authorization failures
    - Network connectivity issues
    """
    
    def __init__(
        self, 
        message: str, 
        database_type: Optional[str] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database_name: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize connection error.
        
        Args:
            message: Human-readable error message
            database_type: Type of database (postgresql, neo4j, milvus, etc.)
            host: Database host
            port: Database port
            database_name: Database name
            **kwargs: Additional arguments passed to parent class
        """
        context = kwargs.get('context', {})
        context.update({
            k: v for k, v in {
                'database_type': database_type,
                'host': host,
                'port': port,
                'database_name': database_name
            }.items() if v is not None
        })
        kwargs['context'] = context
        
        super().__init__(message, **kwargs)


class QueryError(DatabaseClientError):
    """
    Raised when database query execution fails.
    
    This exception is raised when:
    - SQL/Cypher/Gremlin query syntax errors
    - Query execution timeouts
    - Constraint violations
    - Data type mismatches
    - Permission denied for query execution
    """
    
    def __init__(
        self, 
        message: str, 
        query: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        query_type: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize query error.
        
        Args:
            message: Human-readable error message
            query: The query that failed (truncated for security)
            parameters: Query parameters (sanitized)
            query_type: Type of query (SELECT, INSERT, UPDATE, etc.)
            **kwargs: Additional arguments passed to parent class
        """
        context = kwargs.get('context', {})
        
        # Truncate query for security and readability
        if query:
            context['query'] = query[:200] + "..." if len(query) > 200 else query
        
        # Sanitize parameters (remove sensitive data)
        if parameters:
            sanitized_params = {}
            for key, value in parameters.items():
                if any(sensitive in key.lower() for sensitive in ['password', 'secret', 'token', 'key']):
                    sanitized_params[key] = "[REDACTED]"
                else:
                    sanitized_params[key] = str(value)[:100]  # Truncate long values
            context['parameters'] = sanitized_params
        
        if query_type:
            context['query_type'] = query_type
        
        kwargs['context'] = context
        super().__init__(message, **kwargs)


class TransactionError(DatabaseClientError):
    """
    Raised when database transaction operations fail.
    
    This exception is raised when:
    - Transaction commit failures
    - Transaction rollback failures
    - Deadlock detection
    - Transaction timeout
    - Isolation level conflicts
    """
    
    def __init__(
        self, 
        message: str, 
        transaction_id: Optional[str] = None,
        operation: Optional[str] = None,
        isolation_level: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize transaction error.
        
        Args:
            message: Human-readable error message
            transaction_id: ID of the failed transaction
            operation: Transaction operation that failed (commit, rollback, etc.)
            isolation_level: Transaction isolation level
            **kwargs: Additional arguments passed to parent class
        """
        context = kwargs.get('context', {})
        context.update({
            k: v for k, v in {
                'transaction_id': transaction_id,
                'operation': operation,
                'isolation_level': isolation_level
            }.items() if v is not None
        })
        kwargs['context'] = context
        
        super().__init__(message, **kwargs)


class SchemaError(DatabaseClientError):
    """
    Raised when database schema operations fail.
    
    This exception is raised when:
    - Table/collection creation failures
    - Index creation/deletion failures
    - Migration script execution failures
    - Schema validation errors
    - Constraint definition errors
    """
    
    def __init__(
        self, 
        message: str, 
        schema_object: Optional[str] = None,
        operation: Optional[str] = None,
        migration_version: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize schema error.
        
        Args:
            message: Human-readable error message
            schema_object: Name of schema object (table, index, etc.)
            operation: Schema operation that failed (create, drop, alter, etc.)
            migration_version: Version of migration that failed
            **kwargs: Additional arguments passed to parent class
        """
        context = kwargs.get('context', {})
        context.update({
            k: v for k, v in {
                'schema_object': schema_object,
                'operation': operation,
                'migration_version': migration_version
            }.items() if v is not None
        })
        kwargs['context'] = context
        
        super().__init__(message, **kwargs)


class ValidationError(DatabaseClientError):
    """
    Raised when data validation fails before database operations.
    
    This exception is raised when:
    - Input data validation failures
    - Data type conversion errors
    - Required field missing
    - Data format validation errors
    - Business rule validation failures
    """
    
    def __init__(
        self, 
        message: str, 
        field_name: Optional[str] = None,
        field_value: Optional[Any] = None,
        validation_rule: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize validation error.
        
        Args:
            message: Human-readable error message
            field_name: Name of the field that failed validation
            field_value: Value that failed validation (sanitized)
            validation_rule: Validation rule that was violated
            **kwargs: Additional arguments passed to parent class
        """
        context = kwargs.get('context', {})
        
        if field_name:
            context['field_name'] = field_name
        
        # Sanitize field value
        if field_value is not None:
            if isinstance(field_value, str) and len(field_value) > 100:
                context['field_value'] = field_value[:100] + "..."
            else:
                context['field_value'] = str(field_value)
        
        if validation_rule:
            context['validation_rule'] = validation_rule
        
        kwargs['context'] = context
        super().__init__(message, **kwargs)


class TimeoutError(DatabaseClientError):
    """
    Raised when database operations timeout.
    
    This exception is raised when:
    - Query execution timeout
    - Connection timeout
    - Transaction timeout
    - Lock acquisition timeout
    """
    
    def __init__(
        self, 
        message: str, 
        timeout_duration: Optional[float] = None,
        operation_type: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize timeout error.
        
        Args:
            message: Human-readable error message
            timeout_duration: Duration of timeout in seconds
            operation_type: Type of operation that timed out
            **kwargs: Additional arguments passed to parent class
        """
        context = kwargs.get('context', {})
        context.update({
            k: v for k, v in {
                'timeout_duration': timeout_duration,
                'operation_type': operation_type
            }.items() if v is not None
        })
        kwargs['context'] = context
        
        super().__init__(message, **kwargs)


class ConfigurationError(DatabaseClientError):
    """
    Raised when database configuration is invalid or missing.
    
    This exception is raised when:
    - Missing required configuration parameters
    - Invalid configuration values
    - Configuration file parsing errors
    - Environment variable issues
    """
    
    def __init__(
        self, 
        message: str, 
        config_key: Optional[str] = None,
        config_value: Optional[str] = None,
        config_source: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize configuration error.
        
        Args:
            message: Human-readable error message
            config_key: Configuration key that is invalid/missing
            config_value: Configuration value (sanitized)
            config_source: Source of configuration (env, file, etc.)
            **kwargs: Additional arguments passed to parent class
        """
        context = kwargs.get('context', {})
        
        if config_key:
            context['config_key'] = config_key
        
        # Sanitize config value (don't expose secrets)
        if config_value and not any(sensitive in config_key.lower() for sensitive in ['password', 'secret', 'token', 'key']):
            context['config_value'] = config_value
        elif config_value:
            context['config_value'] = "[REDACTED]"
        
        if config_source:
            context['config_source'] = config_source
        
        kwargs['context'] = context
        super().__init__(message, **kwargs)


class ResourceError(DatabaseClientError):
    """
    Raised when database resource operations fail.
    
    This exception is raised when:
    - Insufficient memory/disk space
    - Connection pool exhaustion
    - Resource allocation failures
    - Quota/limit exceeded
    """
    
    def __init__(
        self, 
        message: str, 
        resource_type: Optional[str] = None,
        current_usage: Optional[Union[int, float]] = None,
        limit: Optional[Union[int, float]] = None,
        **kwargs
    ):
        """
        Initialize resource error.
        
        Args:
            message: Human-readable error message
            resource_type: Type of resource (memory, connections, disk, etc.)
            current_usage: Current resource usage
            limit: Resource limit
            **kwargs: Additional arguments passed to parent class
        """
        context = kwargs.get('context', {})
        context.update({
            k: v for k, v in {
                'resource_type': resource_type,
                'current_usage': current_usage,
                'limit': limit
            }.items() if v is not None
        })
        kwargs['context'] = context
        
        super().__init__(message, **kwargs)