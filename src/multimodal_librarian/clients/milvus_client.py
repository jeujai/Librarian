"""
Milvus Client Implementation for Local Development

This module provides a Milvus client that implements the VectorStoreClient protocol
for local development environments. It provides vector storage, similarity search,
and collection management capabilities using Milvus standalone.

The client supports:
- Connection management with automatic reconnection
- Collection creation and management
- Vector insertion and search operations
- Index management and optimization
- Error handling and retry logic
- High-level operations compatible with existing codebase

Example Usage:
    ```python
    from multimodal_librarian.clients.milvus_client import MilvusClient
    
    # Initialize client
    client = MilvusClient(host="localhost", port=19530)
    await client.connect()
    
    # Create collection
    await client.create_collection("documents", dimension=384)
    
    # Insert vectors
    vectors = [
        {
            "id": "doc1_chunk1",
            "vector": [0.1, 0.2, 0.3, ...],  # 384-dim embedding
            "metadata": {
                "content": "Sample text content",
                "source_id": "doc1",
                "chunk_index": 0
            }
        }
    ]
    await client.insert_vectors("documents", vectors)
    
    # Search similar vectors
    query_vector = [0.1, 0.2, 0.3, ...]  # 384-dim query
    results = await client.search_vectors("documents", query_vector, k=5)
    
    # High-level semantic search
    results = await client.semantic_search("What is machine learning?", top_k=5)
    
    await client.disconnect()
    ```

Thread Safety:
    This client is thread-safe for concurrent read operations. Write operations
    are synchronized to maintain data consistency.

Performance Considerations:
    - Connection pooling is handled internally by pymilvus
    - Batch operations are preferred for bulk inserts
    - Index creation improves search performance but takes time
    - Memory usage scales with collection size and vector dimensions
"""

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

# Import Milvus dependencies
try:
    from pymilvus import (
        Collection,
        CollectionSchema,
        DataType,
        FieldSchema,
        MilvusException,
        connections,
        utility,
    )
    MILVUS_AVAILABLE = True
except ImportError as e:
    MILVUS_AVAILABLE = False
    MILVUS_IMPORT_ERROR = str(e)

# Model server flag - prefer model server over local SentenceTransformer
_USE_MODEL_SERVER = True

from ..logging.query_logging_decorators import log_milvus_queries
from .protocols import (
    CollectionStats,
    ConfigurationError,
    ConnectionError,
    HealthStatus,
    PerformanceMetrics,
    QueryError,
    ResourceError,
    SchemaError,
    SearchFilters,
    SearchResults,
    TimeoutError,
    ValidationError,
    VectorEmbedding,
    VectorMetricType,
    VectorStoreClient,
)

logger = logging.getLogger(__name__)


@log_milvus_queries()
class MilvusClient:
    """
    Milvus client implementing VectorStoreClient protocol.
    
    This client provides vector database operations using Milvus standalone
    for local development environments. It implements the same interface as
    the AWS OpenSearch client to enable seamless environment switching.
    
    Connection Management:
        - Automatic connection establishment and health monitoring
        - Connection pooling handled by pymilvus internally
        - Automatic reconnection on connection loss
        - Graceful connection cleanup on shutdown
    
    Collection Management:
        - Dynamic collection creation with configurable schemas
        - Index management for optimized search performance
        - Collection statistics and monitoring
        - Schema validation and migration support
    
    Vector Operations:
        - Batch vector insertion with metadata
        - Similarity search with multiple distance metrics
        - Vector retrieval by ID
        - Bulk vector deletion
    
    Error Handling:
        - Comprehensive error classification and reporting
        - Automatic retry logic for transient failures
        - Connection recovery and failover
        - Detailed error context for debugging
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 19530,
        user: str = "",
        password: str = "",
        connection_name: str = "default",
        timeout: float = 30.0,
        retry_attempts: int = 3,
        retry_delay: float = 1.0,
        embedding_model: str = "all-MiniLM-L6-v2",
        collection_name: Optional[str] = None,
    ):
        """
        Initialize Milvus client.
        
        Args:
            host: Milvus server host (default: localhost)
            port: Milvus server port (default: 19530)
            user: Username for authentication (optional)
            password: Password for authentication (optional)
            connection_name: Name for the connection (default: "default")
            timeout: Connection timeout in seconds (default: 30.0)
            retry_attempts: Number of retry attempts for failed operations (default: 3)
            retry_delay: Delay between retry attempts in seconds (default: 1.0)
            embedding_model: Sentence transformer model for text embeddings
            collection_name: Default collection name (default: from settings or "knowledge_chunks")
        
        Raises:
            ConfigurationError: If Milvus dependencies are not available
        """
        if not MILVUS_AVAILABLE:
            raise ConfigurationError(
                f"Milvus dependencies not available: {MILVUS_IMPORT_ERROR}",
                config_key="pymilvus",
                config_source="requirements.txt"
            )
        
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.connection_name = connection_name
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        
        # Default collection name from param, config, or fallback
        if collection_name is not None:
            self._default_collection_name = collection_name
        else:
            try:
                from multimodal_librarian.config import get_settings
                self._default_collection_name = get_settings().milvus_collection_name
            except Exception:
                self._default_collection_name = "knowledge_chunks"
        
        # Connection state
        self._connected = False
        self._connection_lock = asyncio.Lock()
        self._last_health_check = 0
        self._health_check_interval = 30  # seconds
        
        # Embedding model for semantic search
        self._embedding_model = None
        self._embedding_model_name = embedding_model
        self._embedding_dimension = None
        
        # Collection cache
        self._collection_cache: Dict[str, Collection] = {}
        self._collection_stats_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_ttl = 300  # 5 minutes
        
        logger.info(f"Initialized MilvusClient for {host}:{port}")
    
    async def connect(self) -> None:
        """
        Establish connection to Milvus server.
        
        This method creates a connection to the Milvus server and verifies
        connectivity. It's idempotent - calling multiple times is safe.
        The connection is cached and reused for subsequent operations.
        
        Connection pooling is handled internally by pymilvus, so this method
        primarily establishes the initial connection and verifies server health.
        
        Raises:
            ConnectionError: If connection cannot be established
            ConfigurationError: If connection parameters are invalid
            TimeoutError: If connection times out
        """
        async with self._connection_lock:
            if self._connected:
                # Verify existing connection is still healthy
                try:
                    await self._verify_connection()
                    return
                except Exception:
                    # Connection is stale, reconnect
                    self._connected = False
            
            await self._establish_connection()
    
    async def _establish_connection(self) -> None:
        """Establish new connection to Milvus server."""
        try:
            logger.info(f"Connecting to Milvus at {self.host}:{self.port}")
            
            # Build connection parameters
            connection_params = {
                "host": self.host,
                "port": str(self.port),
                "timeout": self.timeout
            }
            
            if self.user:
                connection_params["user"] = self.user
            if self.password:
                connection_params["password"] = self.password
            
            # Establish connection with retry logic
            for attempt in range(self.retry_attempts):
                try:
                    # Connect to Milvus (run in thread pool to avoid blocking event loop)
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: connections.connect(
                            alias=self.connection_name,
                            **connection_params
                        )
                    )
                    
                    # Verify connection by listing collections
                    await self._verify_connection()
                    
                    self._connected = True
                    self._last_health_check = time.time()
                    
                    logger.info(f"Successfully connected to Milvus (attempt {attempt + 1})")
                    return
                    
                except MilvusException as e:
                    if attempt == self.retry_attempts - 1:
                        raise ConnectionError(
                            f"Failed to connect to Milvus after {self.retry_attempts} attempts: {e}",
                            database_type="milvus",
                            host=self.host,
                            port=self.port,
                            original_exception=e
                        )
                    
                    logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                
                except Exception as e:
                    if attempt == self.retry_attempts - 1:
                        raise ConnectionError(
                            f"Unexpected error connecting to Milvus: {e}",
                            database_type="milvus",
                            host=self.host,
                            port=self.port,
                            original_exception=e
                        )
                    
                    logger.warning(f"Unexpected connection error (attempt {attempt + 1}): {e}")
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
        
        except Exception as e:
            if isinstance(e, (ConnectionError, ConfigurationError, TimeoutError)):
                raise
            
            raise ConnectionError(
                f"Failed to establish Milvus connection: {e}",
                database_type="milvus",
                host=self.host,
                port=self.port,
                original_exception=e
            )
    
    async def _verify_connection(self) -> None:
        """Verify that the connection is healthy."""
        try:
            # Run in thread pool since pymilvus is synchronous
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, utility.list_collections)
        except Exception as e:
            raise ConnectionError(
                f"Connection verification failed: {e}",
                database_type="milvus",
                host=self.host,
                port=self.port,
                original_exception=e
            )
    
    async def disconnect(self) -> None:
        """
        Close connection to Milvus server.
        
        This method closes the connection and cleans up resources. After calling
        this method, the client should not be used until connect() is called again.
        
        The method is idempotent - calling it multiple times is safe.
        
        Raises:
            ConnectionError: If there are issues closing the connection
        """
        async with self._connection_lock:
            if not self._connected:
                return
            
            try:
                logger.info("Disconnecting from Milvus")
                
                # Clear collection cache
                self._collection_cache.clear()
                self._collection_stats_cache.clear()
                
                # Close connection
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None, 
                    connections.disconnect, 
                    self.connection_name
                )
                
                self._connected = False
                logger.info("Successfully disconnected from Milvus")
                
            except Exception as e:
                logger.error(f"Error disconnecting from Milvus: {e}")
                raise ConnectionError(
                    f"Failed to disconnect from Milvus: {e}",
                    database_type="milvus",
                    host=self.host,
                    port=self.port,
                    original_exception=e
                )
    
    async def health_check(self) -> HealthStatus:
        """
        Perform health check on Milvus server.
        
        This method verifies that Milvus is accessible and responsive.
        It checks connectivity, memory usage, and basic functionality.
        Results are cached for a short period to avoid excessive health checks.
        
        Returns:
            Dictionary with health status information including:
            - status: "healthy" | "unhealthy" | "degraded"
            - response_time: Response time in seconds
            - memory_usage: Memory usage percentage (if available)
            - collection_count: Number of collections
            - total_vectors: Total number of vectors stored
            - connection_status: Connection state
            - server_version: Milvus server version
            
        Raises:
            ConnectionError: If health check cannot be performed
        """
        start_time = time.time()
        
        try:
            # Check if we need to perform health check
            current_time = time.time()
            if (current_time - self._last_health_check) < self._health_check_interval:
                # Return cached status if recent
                if hasattr(self, '_cached_health_status'):
                    return self._cached_health_status
            
            # Ensure connection
            if not self._connected:
                await self.connect()
            
            # Run health checks in thread pool
            loop = asyncio.get_event_loop()
            
            # Get collections
            collections = await loop.run_in_executor(None, utility.list_collections)
            
            # Get server version (if available)
            server_version = "unknown"
            try:
                # This might not be available in all Milvus versions
                server_version = await loop.run_in_executor(None, utility.get_server_version)
            except:
                pass
            
            # Count total vectors across all collections
            total_vectors = 0
            for collection_name in collections:
                try:
                    collection = Collection(collection_name)
                    await loop.run_in_executor(None, collection.load)
                    stats = await loop.run_in_executor(None, collection.num_entities)
                    total_vectors += stats
                except:
                    # Skip collections that can't be loaded
                    pass
            
            response_time = time.time() - start_time
            
            health_status = {
                "status": "healthy",
                "response_time": response_time,
                "collection_count": len(collections),
                "total_vectors": total_vectors,
                "connection_status": "connected" if self._connected else "disconnected",
                "server_version": server_version,
                "host": self.host,
                "port": self.port,
                "last_check": datetime.utcnow().isoformat()
            }
            
            # Cache the result
            self._cached_health_status = health_status
            self._last_health_check = current_time
            
            logger.debug(f"Health check completed in {response_time:.3f}s")
            return health_status
            
        except Exception as e:
            response_time = time.time() - start_time
            
            error_status = {
                "status": "unhealthy",
                "response_time": response_time,
                "error": str(e),
                "connection_status": "disconnected",
                "host": self.host,
                "port": self.port,
                "last_check": datetime.utcnow().isoformat()
            }
            
            logger.error(f"Health check failed: {e}")
            
            if isinstance(e, (ConnectionError, TimeoutError)):
                raise
            
            raise ConnectionError(
                f"Health check failed: {e}",
                database_type="milvus",
                host=self.host,
                port=self.port,
                original_exception=e
            )
    
    def _ensure_connected(self) -> None:
        """Ensure client is connected, raise error if not."""
        if not self._connected:
            raise ConnectionError(
                "Client is not connected to Milvus. Call connect() first.",
                database_type="milvus",
                host=self.host,
                port=self.port
            )
    
    async def _run_with_retry(self, operation, *args, **kwargs):
        """Run operation with retry logic.
        
        Note: run_in_executor doesn't support kwargs directly, so we use
        functools.partial to bind them.
        """
        import functools
        
        for attempt in range(self.retry_attempts):
            try:
                loop = asyncio.get_event_loop()
                # Use functools.partial to bind kwargs since run_in_executor
                # doesn't support keyword arguments
                if kwargs:
                    bound_operation = functools.partial(operation, *args, **kwargs)
                    return await loop.run_in_executor(None, bound_operation)
                else:
                    return await loop.run_in_executor(None, operation, *args)
            
            except MilvusException as e:
                if attempt == self.retry_attempts - 1:
                    raise QueryError(
                        f"Operation failed after {self.retry_attempts} attempts: {e}",
                        query_type=operation.__name__ if hasattr(operation, '__name__') else str(operation),
                        original_exception=e
                    )
                
                op_name = operation.__name__ if hasattr(operation, '__name__') else str(operation)
                logger.warning(f"Operation {op_name} failed (attempt {attempt + 1}): {e}")
                await asyncio.sleep(self.retry_delay * (attempt + 1))
            
            except Exception as e:
                # Don't retry for non-Milvus exceptions
                op_name = operation.__name__ if hasattr(operation, '__name__') else str(operation)
                raise QueryError(
                    f"Operation {op_name} failed: {e}",
                    query_type=op_name,
                    original_exception=e
                )
    
    # High-level Operations (for compatibility with existing codebase)
    
    async def store_embeddings(self, chunks: List[Dict[str, Any]]) -> None:
        """
        Store chunk embeddings with metadata (high-level interface).
        
        This method provides a high-level interface for storing document chunks
        with their embeddings and metadata, compatible with existing codebase.
        It handles embedding generation if not provided and manages collection
        creation automatically.
        
        OPTIMIZATION: Uses batch embedding generation instead of sequential
        to reduce embedding storage time from ~3-5 minutes to ~30-60 seconds
        for large documents.
        
        IMPORTANT: Each chunk MUST have a valid UUID as its 'id' field. This ensures
        consistency between PostgreSQL and Milvus storage systems for RAG search.
        
        Args:
            chunks: List of knowledge chunks to store, each containing:
                   - id: Valid UUID string (REQUIRED)
                   - content: Text content (required)
                   - embedding: Vector embedding (optional, will be generated)
                   - metadata: Additional metadata fields like:
                     - source_id: Document ID
                     - chunk_index: Position in document
                     - content_type: Type of content
                     - title: Document title
                     - author: Document author
                     
        Raises:
            ValidationError: If chunk format is invalid or ID is not a valid UUID
            SchemaError: If collection operations fail
            ConnectionError: If not connected to Milvus
        """
        import uuid as uuid_module
        
        self._ensure_connected()
        
        if not chunks:
            logger.warning("No chunks provided for storage")
            return
        
        try:
            logger.info(f"Storing {len(chunks)} document chunks")
            
            # Ensure embedding model is loaded
            await self._ensure_embedding_model()
            
            # Default collection name for document chunks
            collection_name = self._default_collection_name
            
            # Ensure collection exists
            await self._ensure_collection_exists(collection_name, self._embedding_dimension)
            
            # OPTIMIZATION: Batch embedding generation configuration
            EMBEDDING_BATCH_SIZE = 50  # Process 50 embeddings at a time
            
            # First pass: validate all chunks and collect texts needing embeddings
            validated_chunks = []
            texts_needing_embeddings = []
            embedding_indices = []  # Track which chunks need embeddings
            
            for i, chunk in enumerate(chunks):
                if "content" not in chunk:
                    raise ValidationError(
                        f"Chunk at index {i} missing required 'content' field",
                        field_name=f"chunks[{i}].content"
                    )
                
                # Require and validate chunk ID as UUID
                chunk_id = chunk.get("id")
                if chunk_id is None:
                    raise ValidationError(
                        f"Chunk at index {i} missing required 'id' field. All chunks must have a valid UUID.",
                        field_name=f"chunks[{i}].id"
                    )
                
                try:
                    uuid_module.UUID(chunk_id)
                except (ValueError, TypeError):
                    raise ValidationError(
                        f"Chunk ID must be a valid UUID, got: {chunk_id}",
                        field_name=f"chunks[{i}].id"
                    )
                
                validated_chunks.append(chunk)
                
                # Track chunks that need embedding generation
                if chunk.get("embedding") is None:
                    texts_needing_embeddings.append(chunk["content"])
                    embedding_indices.append(i)
            
            # OPTIMIZATION: Generate embeddings in batches
            generated_embeddings = {}
            if texts_needing_embeddings:
                logger.info(f"Generating {len(texts_needing_embeddings)} embeddings in batches of {EMBEDDING_BATCH_SIZE}")
                
                for batch_start in range(0, len(texts_needing_embeddings), EMBEDDING_BATCH_SIZE):
                    batch_end = min(batch_start + EMBEDDING_BATCH_SIZE, len(texts_needing_embeddings))
                    batch_texts = texts_needing_embeddings[batch_start:batch_end]
                    batch_indices = embedding_indices[batch_start:batch_end]
                    
                    # Try batch generation via model server
                    try:
                        if hasattr(self, '_model_server_client') and self._model_server_client is not None:
                            batch_embeddings = await self._model_server_client.generate_embeddings(batch_texts)
                            if batch_embeddings:
                                for idx, embedding in zip(batch_indices, batch_embeddings):
                                    if hasattr(embedding, 'tolist'):
                                        generated_embeddings[idx] = embedding.tolist()
                                    else:
                                        generated_embeddings[idx] = list(embedding)
                                logger.debug(f"Batch {batch_start//EMBEDDING_BATCH_SIZE + 1}: generated {len(batch_texts)} embeddings")
                                continue
                    except Exception as e:
                        logger.warning(f"Batch embedding failed, falling back to sequential: {e}")
                    
                    # Fallback: generate embeddings sequentially for this batch
                    for idx, text in zip(batch_indices, batch_texts):
                        embedding = await self.generate_embedding_async(text)
                        generated_embeddings[idx] = embedding
            
            # Prepare vectors for insertion
            vectors = []
            for i, chunk in enumerate(validated_chunks):
                # Use pre-generated embedding or existing one
                embedding = chunk.get("embedding")
                if embedding is None:
                    embedding = generated_embeddings.get(i)
                
                # Prepare metadata
                metadata = chunk.get("metadata", {}).copy()
                metadata.update({
                    "content": chunk["content"],
                    "content_type": metadata.get("content_type", "text"),
                    "stored_at": datetime.utcnow().isoformat()
                })
                
                vectors.append({
                    "id": chunk.get("id"),
                    "vector": embedding,
                    "metadata": metadata
                })
            
            # Insert vectors in batch
            await self.insert_vectors(collection_name, vectors)
            
            logger.info(f"Successfully stored {len(chunks)} document chunks")
            
        except Exception as e:
            if isinstance(e, (ValidationError, SchemaError)):
                raise
            
            raise SchemaError(
                f"Failed to store embeddings: {e}",
                schema_object=self._default_collection_name,
                operation="store_embeddings",
                original_exception=e
            )
    
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
            ConnectionError: If not connected to Milvus
        """
        self._ensure_connected()
        
        if not query or not query.strip():
            raise ValidationError(
                "Query cannot be empty",
                field_name="query",
                field_value=query
            )
        
        try:
            logger.debug(f"Performing semantic search for: '{query[:50]}...'")
            
            # Ensure embedding model is loaded
            await self._ensure_embedding_model()
            
            # Generate query embedding (ASYNC - non-blocking)
            query_embedding = await self.generate_embedding_async(query.strip())
            
            # Default collection name
            collection_name = self._default_collection_name
            
            # Ensure collection exists
            collections = await self.list_collections()
            if collection_name not in collections:
                logger.warning(f"Collection '{collection_name}' does not exist, returning empty results")
                return []
            
            # Perform vector search
            raw_results = await self.search_vectors(
                collection_name, 
                query_embedding, 
                top_k, 
                filters
            )
            
            # Format results for compatibility
            formatted_results = []
            for result in raw_results:
                metadata = result.get("metadata", {})
                
                # Normalize score (convert L2 distance to similarity)
                # For L2 distance, smaller is better, so we invert it
                distance = result.get("score", 1.0)
                similarity_score = 1.0 / (1.0 + distance)  # Convert to 0-1 similarity
                
                formatted_result = {
                    "content": metadata.get("content", ""),
                    "score": similarity_score,
                    "metadata": metadata,
                    "source_id": metadata.get("source_id", ""),
                    "chunk_index": metadata.get("chunk_index", 0),
                    "id": result.get("id", ""),
                    "raw_score": distance  # Keep original distance for debugging
                }
                
                formatted_results.append(formatted_result)
            
            logger.debug(f"Found {len(formatted_results)} results for semantic search")
            return formatted_results
            
        except Exception as e:
            if isinstance(e, (ValidationError, QueryError)):
                raise
            
            raise QueryError(
                f"Semantic search failed: {e}",
                query_type="semantic_search",
                parameters={"query": query[:100], "top_k": top_k},
                original_exception=e
            )
    
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
            
        Raises:
            ValidationError: If chunk ID is invalid
            ConnectionError: If not connected to Milvus
        """
        self._ensure_connected()
        
        try:
            # Default collection name
            collection_name = self._default_collection_name
            
            # Check if collection exists
            collections = await self.list_collections()
            if collection_name not in collections:
                return None
            
            # Retrieve vector
            vector_data = await self.get_vector_by_id(collection_name, chunk_id)
            
            if vector_data:
                # Format for compatibility
                metadata = vector_data.get("metadata", {})
                return {
                    "id": vector_data.get("id"),
                    "content": metadata.get("content", ""),
                    "metadata": metadata,
                    "embedding": vector_data.get("vector")
                }
            
            return None
            
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            
            raise ValidationError(
                f"Failed to retrieve chunk '{chunk_id}': {e}",
                field_name="chunk_id",
                field_value=chunk_id,
                original_exception=e
            )

    async def get_chunks_by_ids(self, chunk_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Retrieve multiple chunks by their IDs in a single batch query.
        
        OPTIMIZED: Uses a single Milvus query with IN expression instead of
        multiple individual queries. Much more efficient for bulk retrieval.
        
        Args:
            chunk_ids: List of chunk IDs to retrieve
            
        Returns:
            List of chunk data dictionaries (may be fewer than requested if some not found):
            - id: Chunk ID
            - content: Text content
            - metadata: Associated metadata
            - embedding: Vector embedding (optional)
            
        Raises:
            ConnectionError: If not connected to Milvus
        """
        if not chunk_ids:
            return []
        
        self._ensure_connected()
        
        try:
            collection_name = self._default_collection_name
            
            # Check if collection exists
            collections = await self.list_collections()
            if collection_name not in collections:
                return []
            
            # Get collection
            collection = await self._get_collection(collection_name)
            
            # Ensure collection is loaded into memory
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, collection.load)
            
            # Build IN expression for batch query
            # Escape quotes in IDs and format as list
            escaped_ids = [id.replace('"', '\\"') for id in chunk_ids]
            ids_str = '", "'.join(escaped_ids)
            query_expr = f'id in ["{ids_str}"]'
            
            # Query all chunks in one call
            results = await loop.run_in_executor(
                None,
                lambda: collection.query(
                    expr=query_expr,
                    output_fields=["id", "metadata", "vector"],
                    limit=len(chunk_ids)
                )
            )
            
            if not results:
                return []
            
            # Format results for compatibility
            chunks = []
            for result in results:
                metadata = result.get("metadata", {})
                chunks.append({
                    "id": result.get("id"),
                    "content": metadata.get("content", ""),
                    "metadata": metadata,
                    "embedding": result.get("vector")
                })
            
            logger.debug(f"Batch retrieved {len(chunks)}/{len(chunk_ids)} chunks")
            return chunks
            
        except Exception as e:
            logger.warning(f"Batch chunk retrieval failed: {e}")
            # Return empty list on error - caller can fall back to individual queries
            return []
    
    async def delete_chunks_by_source(self, source_id: str) -> int:
        """
        Delete all chunks from a specific source.
        
        This method deletes all document chunks that belong to a specific
        source document. Useful when removing or updating documents.
        
        Args:
            source_id: ID of the source to delete chunks from
            
        Returns:
            Number of chunks deleted
            
        Raises:
            ValidationError: If source_id is invalid
            ConnectionError: If not connected to Milvus
        """
        self._ensure_connected()
        
        try:
            logger.info(f"Deleting chunks from source '{source_id}'")
            
            # Default collection name
            collection_name = self._default_collection_name
            
            # Check if collection exists
            collections = await self.list_collections()
            if collection_name not in collections:
                logger.warning(f"Collection '{collection_name}' does not exist")
                return 0
            
            # Get collection
            collection = await self._get_collection(collection_name)
            
            # Build delete expression for source_id
            delete_expr = f'metadata["source_id"] == "{source_id}"'
            
            # Delete vectors
            loop = asyncio.get_event_loop()
            delete_result = await loop.run_in_executor(
                None,
                collection.delete,
                delete_expr
            )
            
            # Flush to ensure deletion is persisted
            await loop.run_in_executor(None, collection.flush)
            
            # Get number of deleted vectors
            deleted_count = 0
            if hasattr(delete_result, 'delete_count'):
                deleted_count = delete_result.delete_count
            
            logger.info(f"Deleted {deleted_count} chunks from source '{source_id}'")
            
            # Clear stats cache
            self._collection_stats_cache.pop(collection_name, None)
            
            return deleted_count
            
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            
            raise ValidationError(
                f"Failed to delete chunks from source '{source_id}': {e}",
                field_name="source_id",
                field_value=source_id,
                original_exception=e
            )
    
    # Embedding Operations
    
    def generate_embedding(self, text: str) -> VectorEmbedding:
        """
        Generate embedding vector for text.
        
        This method generates a vector embedding for the given text using
        the model server or local fallback. The embedding dimension should match
        the collection dimension.
        
        Note: This method is synchronous. For async contexts, use generate_embedding_async().
        
        Args:
            text: Text to embed (should be preprocessed/cleaned)
            
        Returns:
            Embedding vector as list of floats
            
        Raises:
            ValidationError: If text is empty or too long
            ResourceError: If embedding model is not available
        """
        if not text or not text.strip():
            raise ValidationError(
                "Text cannot be empty for embedding generation",
                field_name="text",
                field_value=text
            )
        
        # Truncate very long text (512 tokens ≈ 2000-2500 chars for English)
        # Using 2000 chars as a safe limit for sentence transformers
        max_length = 2000
        if len(text) > max_length:
            text = text[:max_length]
            logger.warning(f"Text truncated to {max_length} characters for embedding")
        
        try:
            # Try model server first
            if hasattr(self, '_model_server_client') and self._model_server_client is not None:
                try:
                    loop = asyncio.get_event_loop()
                    if not loop.is_running():
                        embeddings = loop.run_until_complete(
                            self._model_server_client.generate_embeddings([text.strip()])
                        )
                        if embeddings:
                            embedding = embeddings[0]
                            if hasattr(embedding, 'tolist'):
                                return embedding.tolist()
                            return list(embedding)
                except Exception as e:
                    logger.warning(f"Model server embedding failed: {e}")
            
            # Ensure embedding model is loaded (will try model server first, then local)
            if self._embedding_model is None and not hasattr(self, '_model_server_client'):
                self._load_embedding_model()
            
            # Try model server again after initialization
            if hasattr(self, '_model_server_client') and self._model_server_client is not None:
                try:
                    loop = asyncio.get_event_loop()
                    if not loop.is_running():
                        embeddings = loop.run_until_complete(
                            self._model_server_client.generate_embeddings([text.strip()])
                        )
                        if embeddings:
                            embedding = embeddings[0]
                            if hasattr(embedding, 'tolist'):
                                return embedding.tolist()
                            return list(embedding)
                except Exception as e:
                    logger.warning(f"Model server embedding failed: {e}")
            
            # Fallback to local model
            if self._embedding_model is not None:
                embedding = self._embedding_model.encode(text.strip())
                
                # Convert to list of floats
                if hasattr(embedding, 'tolist'):
                    embedding = embedding.tolist()
                elif hasattr(embedding, 'numpy'):
                    embedding = embedding.numpy().tolist()
                
                return embedding
            
            raise ResourceError(
                "No embedding model available",
                resource_type="embedding_model"
            )
            
        except Exception as e:
            if isinstance(e, (ValidationError, ResourceError)):
                raise
            raise ResourceError(
                f"Failed to generate embedding: {e}",
                resource_type="embedding_model",
                original_exception=e
            )
    
    async def generate_embedding_async(self, text: str) -> VectorEmbedding:
        """
        Generate embedding vector for text asynchronously (non-blocking).
        
        This method uses the model server for embedding generation,
        which is non-blocking and doesn't load models in the app container.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as list of floats
            
        Raises:
            ValidationError: If text is empty
            ResourceError: If embedding generation fails
        """
        if not text or not text.strip():
            raise ValidationError(
                "Text cannot be empty for embedding generation",
                field_name="text",
                field_value=text
            )
        
        # Truncate very long text (512 tokens ≈ 2000-2500 chars for English)
        # Using 2000 chars as a safe limit for sentence transformers
        max_length = 2000
        if len(text) > max_length:
            text = text[:max_length]
            logger.warning(f"Text truncated to {max_length} characters for embedding")
        
        try:
            # Try model server first (non-blocking)
            if not hasattr(self, '_model_server_client') or self._model_server_client is None:
                try:
                    from .model_server_client import (
                        get_model_client,
                        initialize_model_client,
                    )
                    
                    client = get_model_client()
                    if client is None:
                        await initialize_model_client()
                        client = get_model_client()
                    
                    if client and client.enabled:
                        self._model_server_client = client
                except Exception as e:
                    logger.warning(f"Model server not available: {e}")
            
            if hasattr(self, '_model_server_client') and self._model_server_client is not None:
                try:
                    embeddings = await self._model_server_client.generate_embeddings([text.strip()])
                    if embeddings:
                        embedding = embeddings[0]
                        if hasattr(embedding, 'tolist'):
                            return embedding.tolist()
                        return list(embedding)
                except Exception as e:
                    logger.warning(f"Model server embedding failed: {e}")
            
            # Fallback to local model via thread pool (blocking but offloaded)
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self.generate_embedding, text)
            
        except Exception as e:
            if isinstance(e, (ValidationError, ResourceError)):
                raise
            raise ResourceError(
                f"Failed to generate embedding async: {e}",
                resource_type="embedding_model",
                original_exception=e
            )
    
    def _load_embedding_model(self) -> None:
        """Load the embedding model (model server or local fallback)."""
        global _USE_MODEL_SERVER
        
        # Try model server first
        if _USE_MODEL_SERVER:
            try:
                from .model_server_client import (
                    get_model_client,
                    initialize_model_client,
                )
                
                client = get_model_client()
                if client is None:
                    # Initialize synchronously
                    loop = asyncio.get_event_loop()
                    if not loop.is_running():
                        loop.run_until_complete(initialize_model_client())
                        client = get_model_client()
                
                if client and client.enabled:
                    self._model_server_client = client
                    self._embedding_dimension = 384  # Default for all-MiniLM-L6-v2
                    logger.info("Using model server for embeddings (non-blocking)")
                    return
                    
            except Exception as e:
                logger.warning(f"Model server not available: {e}")
                _USE_MODEL_SERVER = False
        
        # Model server is required - no local fallback
        # Raise error if model server is not available
        raise ResourceError(
            f"Model server not available for embedding model '{self._embedding_model_name}'. "
            "Ensure model-server container is running.",
            resource_type="embedding_model",
            original_exception=None
        )
    
    async def _ensure_embedding_model(self) -> None:
        """
        Ensure embedding capability is available (model server or local fallback).
        
        This method tries the model server first (non-blocking), then falls back
        to local model loading via thread pool if needed.
        """
        # Try model server first (non-blocking)
        if not hasattr(self, '_model_server_client') or self._model_server_client is None:
            try:
                from .model_server_client import (
                    get_model_client,
                    initialize_model_client,
                )
                
                client = get_model_client()
                if client is None:
                    await initialize_model_client()
                    client = get_model_client()
                
                if client and client.enabled:
                    self._model_server_client = client
                    self._embedding_dimension = 384  # Default for all-MiniLM-L6-v2
                    logger.info("Using model server for embeddings (non-blocking)")
                    return
            except Exception as e:
                logger.warning(f"Model server not available: {e}")
        
        # Model server client already available
        if hasattr(self, '_model_server_client') and self._model_server_client is not None:
            return
        
        # Fallback to local model (blocking, offloaded to thread pool)
        if self._embedding_model is None:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._load_embedding_model)
    
    async def _ensure_collection_exists(self, collection_name: str, dimension: int) -> None:
        """Ensure collection exists, create if it doesn't."""
        collections = await self.list_collections()
        if collection_name not in collections:
            logger.info(f"Creating collection '{collection_name}' with dimension {dimension}")
            await self.create_collection(collection_name, dimension, "L2")
            
            # Create index for better performance
            await self.create_index(collection_name, "vector")
    
    # Performance and Monitoring
    
    async def get_performance_stats(self) -> PerformanceMetrics:
        """
        Get database performance statistics.
        
        This method returns performance metrics useful for monitoring
        and optimization, including query statistics and resource usage.
        
        Returns:
            Dictionary with performance metrics including:
            - total_collections: Number of collections
            - total_vectors: Total number of vectors across all collections
            - memory_usage: Estimated memory usage in bytes
            - avg_search_time: Average search time (if available)
            - connection_status: Connection health status
            - server_info: Server version and configuration
            
        Raises:
            ConnectionError: If not connected to Milvus
        """
        self._ensure_connected()
        
        try:
            # Get basic stats
            collections = await self.list_collections()
            total_vectors = 0
            total_memory = 0
            
            for collection_name in collections:
                try:
                    stats = await self.get_collection_stats(collection_name)
                    total_vectors += stats.get("vector_count", 0)
                    total_memory += stats.get("memory_usage", 0)
                except:
                    # Skip collections that can't be accessed
                    pass
            
            # Get health status
            health = await self.health_check()
            
            performance_stats = {
                "total_collections": len(collections),
                "total_vectors": total_vectors,
                "memory_usage": total_memory,
                "connection_status": health.get("status", "unknown"),
                "server_version": health.get("server_version", "unknown"),
                "response_time": health.get("response_time", 0),
                "host": self.host,
                "port": self.port,
                "last_updated": datetime.utcnow().isoformat()
            }
            
            return performance_stats
            
        except Exception as e:
            if isinstance(e, ConnectionError):
                raise
            
            raise ConnectionError(
                f"Failed to get performance stats: {e}",
                database_type="milvus",
                host=self.host,
                port=self.port,
                original_exception=e
            )
    
    # Context Manager Support
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
    
    def __repr__(self) -> str:
        """String representation of the client."""
        status = "connected" if self._connected else "disconnected"
        return f"MilvusClient(host='{self.host}', port={self.port}, status='{status}')"
    
    # Collection/Index Management Methods
    
    async def create_collection(
        self, 
        collection_name: str, 
        dimension: int,
        metric_type: VectorMetricType = "L2"
    ) -> bool:
        """
        Create a vector collection with specified dimension and metric.
        
        This method creates a new collection for storing vectors with the
        specified dimension and distance metric. The collection schema includes:
        - id field (primary key, string)
        - vector field (float vector with specified dimension)
        - metadata field (JSON for additional data)
        
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
            ConnectionError: If not connected to Milvus
        """
        self._ensure_connected()
        
        # Validate parameters
        if not collection_name or not isinstance(collection_name, str):
            raise ValidationError(
                "Collection name must be a non-empty string",
                field_name="collection_name",
                field_value=collection_name
            )
        
        if not isinstance(dimension, int) or dimension <= 0:
            raise ValidationError(
                "Dimension must be a positive integer",
                field_name="dimension",
                field_value=dimension
            )
        
        if metric_type not in ["L2", "IP", "COSINE"]:
            raise ValidationError(
                "Metric type must be one of: L2, IP, COSINE",
                field_name="metric_type",
                field_value=metric_type
            )
        
        try:
            logger.info(f"Creating collection '{collection_name}' with dimension {dimension}")
            
            # Check if collection already exists
            loop = asyncio.get_event_loop()
            existing_collections = await loop.run_in_executor(None, utility.list_collections)
            
            if collection_name in existing_collections:
                logger.info(f"Collection '{collection_name}' already exists")
                return False
            
            # Define collection schema
            fields = [
                FieldSchema(
                    name="id",
                    dtype=DataType.VARCHAR,
                    is_primary=True,
                    max_length=512,
                    description="Unique identifier for the vector"
                ),
                FieldSchema(
                    name="vector",
                    dtype=DataType.FLOAT_VECTOR,
                    dim=dimension,
                    description="Vector embedding"
                ),
                FieldSchema(
                    name="metadata",
                    dtype=DataType.JSON,
                    description="Additional metadata as JSON"
                )
            ]
            
            schema = CollectionSchema(
                fields=fields,
                description=f"Vector collection for {collection_name} with {dimension}D embeddings"
            )
            
            # Create collection
            collection = await self._run_with_retry(
                Collection,
                name=collection_name,
                schema=schema,
                using=self.connection_name
            )
            
            # Cache the collection
            self._collection_cache[collection_name] = collection
            
            logger.info(f"Successfully created collection '{collection_name}'")
            return True
            
        except Exception as e:
            if isinstance(e, (ValidationError, SchemaError)):
                raise
            
            raise SchemaError(
                f"Failed to create collection '{collection_name}': {e}",
                schema_object=collection_name,
                operation="create",
                original_exception=e
            )
    
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
            ConnectionError: If not connected to Milvus
        """
        self._ensure_connected()
        
        try:
            logger.info(f"Deleting collection '{collection_name}'")
            
            # Check if collection exists
            loop = asyncio.get_event_loop()
            existing_collections = await loop.run_in_executor(None, utility.list_collections)
            
            if collection_name not in existing_collections:
                logger.info(f"Collection '{collection_name}' does not exist")
                return False
            
            # Drop collection
            await self._run_with_retry(utility.drop_collection, collection_name)
            
            # Remove from cache
            self._collection_cache.pop(collection_name, None)
            self._collection_stats_cache.pop(collection_name, None)
            
            logger.info(f"Successfully deleted collection '{collection_name}'")
            return True
            
        except Exception as e:
            if isinstance(e, SchemaError):
                raise
            
            raise SchemaError(
                f"Failed to delete collection '{collection_name}': {e}",
                schema_object=collection_name,
                operation="delete",
                original_exception=e
            )
    
    async def list_collections(self) -> List[str]:
        """
        List all available collections.
        
        This method returns the names of all collections in the Milvus database.
        
        Returns:
            List of collection names
            
        Raises:
            ConnectionError: If database is not accessible
        """
        self._ensure_connected()
        
        try:
            loop = asyncio.get_event_loop()
            collections = await loop.run_in_executor(None, utility.list_collections)
            
            logger.debug(f"Found {len(collections)} collections")
            return collections
            
        except Exception as e:
            raise ConnectionError(
                f"Failed to list collections: {e}",
                database_type="milvus",
                host=self.host,
                port=self.port,
                original_exception=e
            )
    
    async def get_collection_stats(self, collection_name: str) -> CollectionStats:
        """
        Get statistics about a collection.
        
        This method returns comprehensive statistics about a collection
        including size, performance metrics, and configuration. Results
        are cached for performance.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            Dictionary with collection statistics including:
            - name: Collection name
            - vector_count: Number of vectors stored
            - dimension: Vector dimension
            - metric_type: Distance metric used
            - index_type: Type of index (if any)
            - memory_usage: Memory usage in bytes (estimated)
            - disk_usage: Disk usage in bytes (estimated)
            - last_updated: Last modification timestamp
            - schema: Collection schema information
            
        Raises:
            ValidationError: If collection doesn't exist
            ConnectionError: If not connected to Milvus
        """
        self._ensure_connected()
        
        # Check cache first
        current_time = time.time()
        if collection_name in self._collection_stats_cache:
            cached_stats = self._collection_stats_cache[collection_name]
            if current_time - cached_stats.get('_cache_time', 0) < self._cache_ttl:
                return cached_stats
        
        try:
            # Get or create collection object
            collection = await self._get_collection(collection_name)
            
            loop = asyncio.get_event_loop()
            
            # Load collection to get accurate stats
            await loop.run_in_executor(None, collection.load)
            
            # Get basic stats
            vector_count = await loop.run_in_executor(None, collection.num_entities)
            
            # Get schema information
            schema = collection.schema
            vector_field = None
            dimension = 0
            
            for field in schema.fields:
                if field.dtype == DataType.FLOAT_VECTOR:
                    vector_field = field
                    dimension = field.params.get('dim', 0)
                    break
            
            # Get index information
            indexes = await loop.run_in_executor(None, collection.indexes)
            index_info = {}
            if indexes:
                index = indexes[0]  # Get first index
                index_info = {
                    "index_type": index.params.get("index_type", "unknown"),
                    "metric_type": index.params.get("metric_type", "unknown"),
                    "params": index.params
                }
            
            # Estimate memory usage (rough calculation)
            estimated_memory = vector_count * dimension * 4  # 4 bytes per float
            estimated_disk = estimated_memory * 1.2  # Add overhead
            
            stats = {
                "name": collection_name,
                "vector_count": vector_count,
                "dimension": dimension,
                "metric_type": index_info.get("metric_type", "unknown"),
                "index_type": index_info.get("index_type", "none"),
                "memory_usage": estimated_memory,
                "disk_usage": estimated_disk,
                "last_updated": datetime.utcnow().isoformat(),
                "schema": {
                    "fields": [
                        {
                            "name": field.name,
                            "type": str(field.dtype),
                            "is_primary": field.is_primary,
                            "description": field.description
                        }
                        for field in schema.fields
                    ],
                    "description": schema.description
                },
                "index_info": index_info,
                "_cache_time": current_time
            }
            
            # Cache the stats
            self._collection_stats_cache[collection_name] = stats
            
            logger.debug(f"Retrieved stats for collection '{collection_name}': {vector_count} vectors")
            return stats
            
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            
            raise ValidationError(
                f"Failed to get stats for collection '{collection_name}': {e}",
                field_name="collection_name",
                field_value=collection_name,
                original_exception=e
            )
    
    async def _get_collection(self, collection_name: str) -> Collection:
        """Get collection object, using cache if available."""
        if collection_name in self._collection_cache:
            return self._collection_cache[collection_name]
        
        # Check if collection exists
        loop = asyncio.get_event_loop()
        existing_collections = await loop.run_in_executor(None, utility.list_collections)
        
        if collection_name not in existing_collections:
            raise ValidationError(
                f"Collection '{collection_name}' does not exist",
                field_name="collection_name",
                field_value=collection_name
            )
        
        # Create collection object and cache it
        collection = Collection(collection_name, using=self.connection_name)
        self._collection_cache[collection_name] = collection
        
        return collection
    
    # Vector Operations Methods
    
    async def insert_vectors(
        self, 
        collection_name: str,
        vectors: List[Dict[str, Any]]
    ) -> bool:
        """
        Insert vectors into a collection.
        
        This method inserts a batch of vectors with their metadata into the
        specified collection. Each vector should include an ID, vector embedding,
        and optional metadata.
        
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
            ConnectionError: If not connected to Milvus
        """
        self._ensure_connected()
        
        if not vectors:
            logger.warning("No vectors provided for insertion")
            return True
        
        # Validate vector format
        for i, vector_doc in enumerate(vectors):
            if not isinstance(vector_doc, dict):
                raise ValidationError(
                    f"Vector at index {i} must be a dictionary",
                    field_name=f"vectors[{i}]",
                    field_value=type(vector_doc).__name__
                )
            
            if "id" not in vector_doc:
                raise ValidationError(
                    f"Vector at index {i} missing required 'id' field",
                    field_name=f"vectors[{i}].id"
                )
            
            if "vector" not in vector_doc:
                raise ValidationError(
                    f"Vector at index {i} missing required 'vector' field",
                    field_name=f"vectors[{i}].vector"
                )
            
            if not isinstance(vector_doc["vector"], list):
                raise ValidationError(
                    f"Vector at index {i} 'vector' field must be a list",
                    field_name=f"vectors[{i}].vector",
                    field_value=type(vector_doc["vector"]).__name__
                )
        
        try:
            logger.info(f"Inserting {len(vectors)} vectors into collection '{collection_name}'")
            
            # Get collection
            collection = await self._get_collection(collection_name)
            
            # Prepare data for insertion
            ids = []
            vector_data = []
            metadata_data = []
            
            for vector_doc in vectors:
                ids.append(str(vector_doc["id"]))
                vector_data.append(vector_doc["vector"])
                
                # Prepare metadata (ensure it's JSON serializable)
                metadata = vector_doc.get("metadata", {})
                if not isinstance(metadata, dict):
                    metadata = {"raw_metadata": str(metadata)}
                
                # Add vector ID to metadata for easier retrieval
                metadata["_vector_id"] = str(vector_doc["id"])
                metadata_data.append(metadata)
            
            # Insert data
            data = [ids, vector_data, metadata_data]
            
            loop = asyncio.get_event_loop()
            insert_result = await loop.run_in_executor(None, collection.insert, data)
            
            # Flush to ensure data is persisted
            await loop.run_in_executor(None, collection.flush)
            
            logger.info(f"Successfully inserted {len(vectors)} vectors into '{collection_name}'")
            
            # Clear stats cache for this collection
            self._collection_stats_cache.pop(collection_name, None)
            
            return True
            
        except Exception as e:
            if isinstance(e, (ValidationError, SchemaError, ResourceError)):
                raise
            
            raise ResourceError(
                f"Failed to insert vectors into collection '{collection_name}': {e}",
                resource_type="vectors",
                current_usage=len(vectors),
                original_exception=e
            )
    
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
            ConnectionError: If not connected to Milvus
        """
        self._ensure_connected()
        
        # Validate parameters
        if not isinstance(query_vector, list):
            raise ValidationError(
                "Query vector must be a list of floats",
                field_name="query_vector",
                field_value=type(query_vector).__name__
            )
        
        if k <= 0:
            raise ValidationError(
                "k must be a positive integer",
                field_name="k",
                field_value=k
            )
        
        try:
            logger.debug(f"Searching for {k} similar vectors in collection '{collection_name}'")
            
            # Get collection
            collection = await self._get_collection(collection_name)
            
            # Ensure collection is loaded
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, collection.load)
            
            # Prepare search parameters with dynamic optimization
            search_params = await self._get_optimized_search_params(collection_name, k)
            
            # Build filter expression if provided
            filter_expr = None
            if filters:
                filter_expr = self._build_filter_expression(filters)
            
            # Perform search using functools.partial to support keyword arguments
            import functools
            search_func = functools.partial(
                collection.search,
                data=[query_vector],
                anns_field="vector",
                param=search_params,
                limit=k,
                expr=filter_expr,
                output_fields=["id", "metadata"]
            )
            search_result = await loop.run_in_executor(None, search_func)
            
            # Process results
            results = []
            if search_result and len(search_result) > 0:
                hits = search_result[0]  # First query results
                
                for hit in hits:
                    result = {
                        "id": hit.id,
                        "score": float(hit.distance),  # Distance score
                        "metadata": hit.entity.get("metadata", {}),
                    }
                    
                    # Add vector if requested (for debugging)
                    if filters and filters.get("include_vector", False):
                        try:
                            vector_data = await self._get_vector_by_id_internal(collection, hit.id)
                            if vector_data:
                                result["vector"] = vector_data.get("vector")
                        except:
                            pass  # Skip if vector retrieval fails
                    
                    results.append(result)
            
            logger.debug(f"Found {len(results)} similar vectors")
            return results
            
        except Exception as e:
            if isinstance(e, (ValidationError, QueryError)):
                raise
            
            raise QueryError(
                f"Vector search failed in collection '{collection_name}': {e}",
                query_type="vector_search",
                parameters={"k": k, "filters": filters},
                original_exception=e
            )
    
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
            ConnectionError: If not connected to Milvus
        """
        self._ensure_connected()
        
        try:
            # Get collection
            collection = await self._get_collection(collection_name)
            
            # Retrieve vector
            vector_data = await self._get_vector_by_id_internal(collection, vector_id)
            
            if vector_data:
                logger.debug(f"Retrieved vector '{vector_id}' from collection '{collection_name}'")
            else:
                logger.debug(f"Vector '{vector_id}' not found in collection '{collection_name}'")
            
            return vector_data
            
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            
            raise ValidationError(
                f"Failed to retrieve vector '{vector_id}' from collection '{collection_name}': {e}",
                field_name="vector_id",
                field_value=vector_id,
                original_exception=e
            )
    
    async def _get_vector_by_id_internal(
        self, 
        collection: Collection, 
        vector_id: str
    ) -> Optional[Dict[str, Any]]:
        """Internal method to retrieve vector by ID."""
        try:
            loop = asyncio.get_event_loop()
            
            # Ensure collection is loaded
            await loop.run_in_executor(None, collection.load)
            
            # Query by ID
            query_result = await loop.run_in_executor(
                None,
                collection.query,
                f'id == "{vector_id}"',  # Filter expression
                ["id", "vector", "metadata"]  # Output fields
            )
            
            if query_result and len(query_result) > 0:
                entity = query_result[0]
                return {
                    "id": entity.get("id"),
                    "vector": entity.get("vector"),
                    "metadata": entity.get("metadata", {})
                }
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to retrieve vector '{vector_id}': {e}")
            return None
    
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
            ConnectionError: If not connected to Milvus
        """
        self._ensure_connected()
        
        if not vector_ids:
            logger.warning("No vector IDs provided for deletion")
            return 0
        
        try:
            logger.info(f"Deleting {len(vector_ids)} vectors from collection '{collection_name}'")
            
            # Get collection
            collection = await self._get_collection(collection_name)
            
            # Build delete expression
            id_list = [f'"{vid}"' for vid in vector_ids]
            delete_expr = f"id in [{', '.join(id_list)}]"
            
            # Delete vectors
            loop = asyncio.get_event_loop()
            delete_result = await loop.run_in_executor(
                None,
                collection.delete,
                delete_expr
            )
            
            # Flush to ensure deletion is persisted
            await loop.run_in_executor(None, collection.flush)
            
            # Get number of deleted vectors (if available in result)
            deleted_count = len(vector_ids)  # Assume all were deleted
            if hasattr(delete_result, 'delete_count'):
                deleted_count = delete_result.delete_count
            
            logger.info(f"Successfully deleted {deleted_count} vectors from '{collection_name}'")
            
            # Clear stats cache for this collection
            self._collection_stats_cache.pop(collection_name, None)
            
            return deleted_count
            
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            
            raise ValidationError(
                f"Failed to delete vectors from collection '{collection_name}': {e}",
                field_name="vector_ids",
                field_value=f"{len(vector_ids)} IDs",
                original_exception=e
            )
    
    async def _get_optimized_search_params(
        self, 
        collection_name: str, 
        k: int
    ) -> Dict[str, Any]:
        """
        Get optimized search parameters based on collection characteristics.
        
        This method dynamically adjusts search parameters based on:
        - Collection size and index type
        - Number of results requested (k)
        - Performance vs accuracy trade-offs
        
        Args:
            collection_name: Name of the collection
            k: Number of results requested
            
        Returns:
            Optimized search parameters dictionary
        """
        try:
            # Get collection stats and index info
            stats = await self.get_collection_stats(collection_name)
            vector_count = stats.get("vector_count", 0)
            index_type = stats.get("index_type", "unknown")
            
            # Base search parameters
            search_params = {
                "metric_type": stats.get("metric_type", "L2"),
                "params": {}
            }
            
            # Optimize parameters based on index type
            if index_type == "IVF_FLAT" or index_type == "IVF_SQ8":
                # For IVF indexes, optimize nprobe based on collection size and k
                nlist = stats.get("index_info", {}).get("params", {}).get("nlist", 1024)
                
                # Dynamic nprobe calculation
                if vector_count < 10000:
                    nprobe = min(max(k * 2, 10), nlist // 4)
                elif vector_count < 100000:
                    nprobe = min(max(k * 3, 20), nlist // 2)
                else:
                    nprobe = min(max(k * 4, 50), nlist)
                
                search_params["params"]["nprobe"] = nprobe
                
            elif index_type == "HNSW":
                # For HNSW, optimize ef (search time accuracy trade-off)
                if k <= 10:
                    ef = max(k * 8, 64)  # Higher accuracy for small k
                elif k <= 50:
                    ef = max(k * 6, 100)
                else:
                    ef = max(k * 4, 200)
                
                search_params["params"]["ef"] = min(ef, 512)  # Cap at 512 for performance
                
            elif index_type == "FLAT":
                # FLAT index doesn't need special parameters
                pass
            
            else:
                # Unknown index type, use conservative defaults
                search_params["params"]["nprobe"] = min(max(k * 2, 10), 100)
            
            logger.debug(f"Optimized search params for {index_type}: {search_params}")
            return search_params
            
        except Exception as e:
            logger.warning(f"Failed to optimize search parameters: {e}")
            # Fallback to safe defaults
            return {
                "metric_type": "L2",
                "params": {"nprobe": min(max(k * 2, 10), 100)}
            }
    
    def _build_filter_expression(self, filters: SearchFilters) -> Optional[str]:
        """
        Build Milvus filter expression from search filters.
        
        This method converts a dictionary of filters into a Milvus-compatible
        filter expression string.
        
        Args:
            filters: Dictionary of filter conditions
            
        Returns:
            Filter expression string or None if no valid filters
        """
        if not filters:
            return None
        
        expressions = []
        
        for key, value in filters.items():
            if key.startswith("_"):  # Skip internal keys
                continue
            
            if isinstance(value, str):
                expressions.append(f'metadata["{key}"] == "{value}"')
            elif isinstance(value, (int, float)):
                expressions.append(f'metadata["{key}"] == {value}')
            elif isinstance(value, dict):
                # Handle range queries like {"$gte": 5}
                for op, op_value in value.items():
                    if op == "$gte":
                        expressions.append(f'metadata["{key}"] >= {op_value}')
                    elif op == "$lte":
                        expressions.append(f'metadata["{key}"] <= {op_value}')
                    elif op == "$gt":
                        expressions.append(f'metadata["{key}"] > {op_value}')
                    elif op == "$lt":
                        expressions.append(f'metadata["{key}"] < {op_value}')
                    elif op == "$eq":
                        if isinstance(op_value, str):
                            expressions.append(f'metadata["{key}"] == "{op_value}"')
                        else:
                            expressions.append(f'metadata["{key}"] == {op_value}')
            elif isinstance(value, list):
                # Handle "in" queries
                if all(isinstance(v, str) for v in value):
                    value_list = [f'"{v}"' for v in value]
                    expressions.append(f'metadata["{key}"] in [{", ".join(value_list)}]')
                else:
                    value_list = [str(v) for v in value]
                    expressions.append(f'metadata["{key}"] in [{", ".join(value_list)}]')
        
        if expressions:
            return " and ".join(expressions)
        
        return None
    
    # Index Management Methods
    
    async def create_index(
        self, 
        collection_name: str,
        field_name: str = "vector",
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
                         - metric_type: Distance metric ("L2", "IP", "COSINE")
                         - params: Index-specific configuration
                         
        Returns:
            True if index was created successfully
            
        Raises:
            SchemaError: If index creation fails
            ValidationError: If parameters are invalid
            ConnectionError: If not connected to Milvus
        """
        self._ensure_connected()
        
        # Default index parameters optimized for development
        if index_params is None:
            # Get collection stats to determine optimal index parameters
            try:
                stats = await self.get_collection_stats(collection_name)
                vector_count = stats.get("vector_count", 0)
                
                # Choose index type based on collection size and performance requirements
                if vector_count < 10000:
                    # For small collections, use FLAT for exact search
                    index_params = {
                        "index_type": "FLAT",
                        "metric_type": "L2",
                        "params": {}
                    }
                elif vector_count < 100000:
                    # For medium collections, use IVF_FLAT with optimized nlist
                    nlist = min(max(vector_count // 100, 128), 4096)
                    index_params = {
                        "index_type": "IVF_FLAT",
                        "metric_type": "L2",
                        "params": {"nlist": nlist}
                    }
                else:
                    # For large collections, use HNSW for better performance
                    index_params = {
                        "index_type": "HNSW",
                        "metric_type": "L2",
                        "params": {
                            "M": 16,  # Number of bi-directional links for each node
                            "efConstruction": 200  # Size of dynamic candidate list
                        }
                    }
                    
                logger.info(f"Auto-selected index type '{index_params['index_type']}' for {vector_count} vectors")
                
            except Exception as e:
                logger.warning(f"Failed to get collection stats for index optimization: {e}")
                # Fallback to default IVF_FLAT
                index_params = {
                    "index_type": "IVF_FLAT",
                    "metric_type": "L2",
                    "params": {"nlist": 1024}
                }
        
        try:
            logger.info(f"Creating index on field '{field_name}' in collection '{collection_name}'")
            
            # Get collection
            collection = await self._get_collection(collection_name)
            
            # Create index
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                collection.create_index,
                field_name,
                index_params
            )
            
            logger.info(f"Successfully created index on '{field_name}' with type '{index_params.get('index_type')}'")
            
            # Clear stats cache for this collection
            self._collection_stats_cache.pop(collection_name, None)
            
            return True
            
        except Exception as e:
            if isinstance(e, (ValidationError, SchemaError)):
                raise
            
            raise SchemaError(
                f"Failed to create index on field '{field_name}' in collection '{collection_name}': {e}",
                schema_object=f"{collection_name}.{field_name}",
                operation="create_index",
                original_exception=e
            )
    
    async def drop_index(
        self, 
        collection_name: str,
        field_name: str = "vector"
    ) -> bool:
        """
        Drop an index from a collection field.
        
        This method removes an index from a collection field. This will slow down
        search operations but may be necessary for index rebuilding or
        configuration changes.
        
        Args:
            collection_name: Name of the collection
            field_name: Name of the field to drop index from
            
        Returns:
            True if index was dropped successfully
            
        Raises:
            SchemaError: If index dropping fails
            ConnectionError: If not connected to Milvus
        """
        self._ensure_connected()
        
        try:
            logger.info(f"Dropping index on field '{field_name}' in collection '{collection_name}'")
            
            # Get collection
            collection = await self._get_collection(collection_name)
            
            # Drop index
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                collection.drop_index,
                field_name
            )
            
            logger.info(f"Successfully dropped index on '{field_name}'")
            
            # Clear stats cache for this collection
            self._collection_stats_cache.pop(collection_name, None)
            
            return True
            
        except Exception as e:
            if isinstance(e, SchemaError):
                raise
            
            raise SchemaError(
                f"Failed to drop index on field '{field_name}' in collection '{collection_name}': {e}",
                schema_object=f"{collection_name}.{field_name}",
                operation="drop_index",
                original_exception=e
            )
    
    async def get_index_info(self, collection_name: str) -> List[Dict[str, Any]]:
        """
        Get information about indexes in a collection.
        
        Args:
            collection_name: Name of the collection
            
        Returns:
            List of index information dictionaries
            
        Raises:
            ValidationError: If collection doesn't exist
            ConnectionError: If not connected to Milvus
        """
        self._ensure_connected()
        
        try:
            # Get collection
            collection = await self._get_collection(collection_name)
            
            # Get indexes
            loop = asyncio.get_event_loop()
            indexes = await loop.run_in_executor(None, collection.indexes)
            
            index_info = []
            for index in indexes:
                info = {
                    "field_name": index.field_name,
                    "index_name": index.index_name,
                    "index_type": index.params.get("index_type", "unknown"),
                    "metric_type": index.params.get("metric_type", "unknown"),
                    "params": index.params
                }
                index_info.append(info)
            
            return index_info
            
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            
            raise ValidationError(
                f"Failed to get index info for collection '{collection_name}': {e}",
                field_name="collection_name",
                field_value=collection_name,
                original_exception=e
            )
    
    async def optimize_collection(self, collection_name: str) -> bool:
        """
        Optimize a collection for better performance.
        
        This method performs optimization operations on a collection including:
        - Creating appropriate indexes if they don't exist
        - Compacting data for better storage efficiency
        - Loading collection into memory for faster access
        
        Args:
            collection_name: Name of the collection to optimize
            
        Returns:
            True if optimization was successful
            
        Raises:
            SchemaError: If optimization fails
            ConnectionError: If not connected to Milvus
        """
        self._ensure_connected()
        
        try:
            logger.info(f"Optimizing collection '{collection_name}'")
            
            # Get collection
            collection = await self._get_collection(collection_name)
            
            loop = asyncio.get_event_loop()
            
            # Check if vector field has an index
            indexes = await loop.run_in_executor(None, collection.indexes)
            has_vector_index = any(
                index.field_name == "vector" for index in indexes
            )
            
            # Create index if it doesn't exist
            if not has_vector_index:
                logger.info("Creating default index for vector field")
                await self.create_index(collection_name, "vector")
            
            # Compact collection (if supported)
            try:
                await loop.run_in_executor(None, collection.compact)
                logger.info("Collection compaction completed")
            except Exception as e:
                logger.warning(f"Collection compaction failed (may not be supported): {e}")
            
            # Load collection into memory
            await loop.run_in_executor(None, collection.load)
            logger.info("Collection loaded into memory")
            
            # Clear stats cache to force refresh
            self._collection_stats_cache.pop(collection_name, None)
            
            logger.info(f"Successfully optimized collection '{collection_name}'")
            return True
            
        except Exception as e:
            if isinstance(e, SchemaError):
                raise
            
            raise SchemaError(
                f"Failed to optimize collection '{collection_name}': {e}",
                schema_object=collection_name,
                operation="optimize",
                original_exception=e
            )
    
    async def optimize_search_performance(
        self, 
        collection_name: str,
        target_latency_ms: float = 100.0,
        accuracy_threshold: float = 0.95
    ) -> Dict[str, Any]:
        """
        Optimize search performance for a collection by tuning index parameters.
        
        This method performs automated performance tuning by:
        1. Analyzing current search performance
        2. Testing different parameter combinations
        3. Finding optimal balance between speed and accuracy
        
        Args:
            collection_name: Name of the collection to optimize
            target_latency_ms: Target search latency in milliseconds
            accuracy_threshold: Minimum acceptable search accuracy (0-1)
            
        Returns:
            Dictionary with optimization results and recommended parameters
            
        Raises:
            SchemaError: If optimization fails
            ConnectionError: If not connected to Milvus
        """
        self._ensure_connected()
        
        try:
            logger.info(f"Starting search performance optimization for '{collection_name}'")
            
            # Get collection stats
            stats = await self.get_collection_stats(collection_name)
            vector_count = stats.get("vector_count", 0)
            
            if vector_count < 100:
                logger.warning("Collection too small for meaningful optimization")
                return {
                    "status": "skipped",
                    "reason": "Collection too small",
                    "recommendations": ["Add more vectors before optimizing"]
                }
            
            # Get current index info
            index_info = await self.get_index_info(collection_name)
            if not index_info:
                logger.info("No index found, creating optimized index first")
                await self.create_index(collection_name, "vector")
                index_info = await self.get_index_info(collection_name)
            
            current_index = index_info[0] if index_info else {}
            index_type = current_index.get("index_type", "unknown")
            
            # Generate test queries for performance measurement
            test_queries = await self._generate_test_queries(collection_name, num_queries=10)
            
            optimization_results = {
                "collection_name": collection_name,
                "vector_count": vector_count,
                "current_index_type": index_type,
                "target_latency_ms": target_latency_ms,
                "accuracy_threshold": accuracy_threshold,
                "test_results": [],
                "optimal_params": None,
                "performance_improvement": 0.0
            }
            
            # Test current performance
            current_performance = await self._measure_search_performance(
                collection_name, test_queries
            )
            
            optimization_results["baseline_performance"] = current_performance
            logger.info(f"Baseline performance: {current_performance['avg_latency_ms']:.2f}ms avg latency")
            
            # Test different parameter combinations based on index type
            if index_type in ["IVF_FLAT", "IVF_SQ8"]:
                optimal_params = await self._optimize_ivf_parameters(
                    collection_name, test_queries, target_latency_ms, accuracy_threshold
                )
            elif index_type == "HNSW":
                optimal_params = await self._optimize_hnsw_parameters(
                    collection_name, test_queries, target_latency_ms, accuracy_threshold
                )
            else:
                logger.warning(f"Optimization not supported for index type: {index_type}")
                optimal_params = None
            
            if optimal_params:
                optimization_results["optimal_params"] = optimal_params
                
                # Calculate performance improvement
                improvement = (
                    (current_performance["avg_latency_ms"] - optimal_params["avg_latency_ms"]) /
                    current_performance["avg_latency_ms"] * 100
                )
                optimization_results["performance_improvement"] = improvement
                
                logger.info(f"Optimization complete: {improvement:.1f}% latency improvement")
                
                # Store optimal parameters for future use
                self._store_optimization_results(collection_name, optimal_params)
            
            return optimization_results
            
        except Exception as e:
            if isinstance(e, SchemaError):
                raise
            
            raise SchemaError(
                f"Failed to optimize search performance for '{collection_name}': {e}",
                schema_object=collection_name,
                operation="optimize_search",
                original_exception=e
            )
    
    async def _generate_test_queries(
        self, 
        collection_name: str, 
        num_queries: int = 10
    ) -> List[VectorEmbedding]:
        """Generate representative test queries from existing vectors."""
        try:
            # Get a sample of existing vectors to use as queries
            collection = await self._get_collection(collection_name)
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, collection.load)
            
            # Query random vectors
            sample_results = await loop.run_in_executor(
                None,
                collection.query,
                "",  # Empty expression to get all
                ["vector"],
                limit=num_queries
            )
            
            test_queries = []
            for result in sample_results:
                if "vector" in result:
                    test_queries.append(result["vector"])
            
            # If we don't have enough vectors, generate synthetic ones
            if len(test_queries) < num_queries:
                await self._ensure_embedding_model()
                synthetic_texts = [
                    f"test query {i}" for i in range(num_queries - len(test_queries))
                ]
                for text in synthetic_texts:
                    test_queries.append(self.generate_embedding(text))
            
            return test_queries[:num_queries]
            
        except Exception as e:
            logger.warning(f"Failed to generate test queries: {e}")
            # Fallback to synthetic queries
            await self._ensure_embedding_model()
            return [
                self.generate_embedding(f"synthetic test query {i}")
                for i in range(num_queries)
            ]
    
    async def _measure_search_performance(
        self, 
        collection_name: str, 
        test_queries: List[VectorEmbedding],
        search_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, float]:
        """Measure search performance with given parameters."""
        import time
        
        latencies = []
        
        for query_vector in test_queries:
            start_time = time.time()
            
            try:
                if search_params:
                    # Use custom search parameters
                    collection = await self._get_collection(collection_name)
                    loop = asyncio.get_event_loop()
                    
                    await loop.run_in_executor(
                        None,
                        collection.search,
                        [query_vector],
                        "vector",
                        search_params,
                        10,  # k=10 for testing
                        None,  # No filters
                        ["id"]  # Minimal output fields
                    )
                else:
                    # Use default search
                    await self.search_vectors(collection_name, query_vector, k=10)
                
                latency_ms = (time.time() - start_time) * 1000
                latencies.append(latency_ms)
                
            except Exception as e:
                logger.warning(f"Search failed during performance measurement: {e}")
                continue
        
        if not latencies:
            return {"avg_latency_ms": float('inf'), "p95_latency_ms": float('inf')}
        
        latencies.sort()
        avg_latency = sum(latencies) / len(latencies)
        p95_latency = latencies[int(len(latencies) * 0.95)] if latencies else avg_latency
        
        return {
            "avg_latency_ms": avg_latency,
            "p95_latency_ms": p95_latency,
            "min_latency_ms": min(latencies),
            "max_latency_ms": max(latencies),
            "num_queries": len(latencies)
        }
    
    async def _optimize_ivf_parameters(
        self,
        collection_name: str,
        test_queries: List[VectorEmbedding],
        target_latency_ms: float,
        accuracy_threshold: float
    ) -> Optional[Dict[str, Any]]:
        """Optimize IVF index parameters (nprobe)."""
        try:
            # Get current index info
            index_info = await self.get_index_info(collection_name)
            current_index = index_info[0] if index_info else {}
            nlist = current_index.get("params", {}).get("nlist", 1024)
            
            best_params = None
            best_performance = None
            
            # Test different nprobe values
            nprobe_values = [
                max(1, nlist // 100),
                max(1, nlist // 50),
                max(1, nlist // 20),
                max(1, nlist // 10),
                max(1, nlist // 5),
                max(1, nlist // 2)
            ]
            
            # Remove duplicates and sort
            nprobe_values = sorted(list(set(nprobe_values)))
            
            logger.info(f"Testing nprobe values: {nprobe_values}")
            
            for nprobe in nprobe_values:
                search_params = {
                    "metric_type": "L2",
                    "params": {"nprobe": nprobe}
                }
                
                performance = await self._measure_search_performance(
                    collection_name, test_queries, search_params
                )
                
                logger.debug(f"nprobe={nprobe}: {performance['avg_latency_ms']:.2f}ms avg")
                
                # Check if this meets our criteria
                if (performance["avg_latency_ms"] <= target_latency_ms and
                    (best_params is None or 
                     performance["avg_latency_ms"] < best_performance["avg_latency_ms"])):
                    
                    best_params = {
                        "search_params": search_params,
                        "nprobe": nprobe,
                        "avg_latency_ms": performance["avg_latency_ms"],
                        "p95_latency_ms": performance["p95_latency_ms"]
                    }
                    best_performance = performance
            
            return best_params
            
        except Exception as e:
            logger.error(f"Failed to optimize IVF parameters: {e}")
            return None
    
    async def _optimize_hnsw_parameters(
        self,
        collection_name: str,
        test_queries: List[VectorEmbedding],
        target_latency_ms: float,
        accuracy_threshold: float
    ) -> Optional[Dict[str, Any]]:
        """Optimize HNSW index parameters (ef)."""
        try:
            best_params = None
            best_performance = None
            
            # Test different ef values
            ef_values = [16, 32, 64, 128, 256, 512]
            
            logger.info(f"Testing ef values: {ef_values}")
            
            for ef in ef_values:
                search_params = {
                    "metric_type": "L2",
                    "params": {"ef": ef}
                }
                
                performance = await self._measure_search_performance(
                    collection_name, test_queries, search_params
                )
                
                logger.debug(f"ef={ef}: {performance['avg_latency_ms']:.2f}ms avg")
                
                # Check if this meets our criteria
                if (performance["avg_latency_ms"] <= target_latency_ms and
                    (best_params is None or 
                     performance["avg_latency_ms"] < best_performance["avg_latency_ms"])):
                    
                    best_params = {
                        "search_params": search_params,
                        "ef": ef,
                        "avg_latency_ms": performance["avg_latency_ms"],
                        "p95_latency_ms": performance["p95_latency_ms"]
                    }
                    best_performance = performance
            
            return best_params
            
        except Exception as e:
            logger.error(f"Failed to optimize HNSW parameters: {e}")
            return None
    
    def _store_optimization_results(
        self, 
        collection_name: str, 
        optimal_params: Dict[str, Any]
    ) -> None:
        """Store optimization results for future use."""
        try:
            # Store in instance cache for immediate use
            if not hasattr(self, '_optimization_cache'):
                self._optimization_cache = {}
            
            self._optimization_cache[collection_name] = {
                "params": optimal_params,
                "timestamp": time.time()
            }
            
            logger.info(f"Stored optimization results for collection '{collection_name}'")
            
        except Exception as e:
            logger.warning(f"Failed to store optimization results: {e}")
    
    async def get_optimization_recommendations(
        self, 
        collection_name: str
    ) -> Dict[str, Any]:
        """
        Get optimization recommendations for a collection.
        
        This method analyzes collection characteristics and provides
        recommendations for improving search performance.
        
        Args:
            collection_name: Name of the collection to analyze
            
        Returns:
            Dictionary with optimization recommendations
            
        Raises:
            ValidationError: If collection doesn't exist
            ConnectionError: If not connected to Milvus
        """
        self._ensure_connected()
        
        try:
            # Get collection stats
            stats = await self.get_collection_stats(collection_name)
            vector_count = stats.get("vector_count", 0)
            dimension = stats.get("dimension", 0)
            index_type = stats.get("index_type", "none")
            memory_usage = stats.get("memory_usage", 0)
            
            recommendations = {
                "collection_name": collection_name,
                "current_stats": stats,
                "recommendations": [],
                "priority": "low",
                "estimated_improvement": "minimal"
            }
            
            # Analyze and provide recommendations
            if index_type == "none":
                recommendations["recommendations"].append({
                    "type": "create_index",
                    "description": "Create an index to improve search performance",
                    "action": "Create index with appropriate type for collection size",
                    "priority": "high",
                    "estimated_improvement": "10-100x faster searches"
                })
                recommendations["priority"] = "high"
                recommendations["estimated_improvement"] = "significant"
            
            elif vector_count > 100000 and index_type == "IVF_FLAT":
                recommendations["recommendations"].append({
                    "type": "upgrade_index",
                    "description": "Consider upgrading to HNSW index for large collections",
                    "action": "Recreate index with HNSW type",
                    "priority": "medium",
                    "estimated_improvement": "2-5x faster searches with better scalability"
                })
                recommendations["priority"] = "medium"
                recommendations["estimated_improvement"] = "moderate"
            
            elif vector_count < 10000 and index_type in ["IVF_FLAT", "HNSW"]:
                recommendations["recommendations"].append({
                    "type": "simplify_index",
                    "description": "FLAT index may be more efficient for small collections",
                    "action": "Consider using FLAT index for exact search",
                    "priority": "low",
                    "estimated_improvement": "Slightly faster for small datasets"
                })
            
            # Memory usage recommendations
            if memory_usage > 2 * 1024 * 1024 * 1024:  # > 2GB
                recommendations["recommendations"].append({
                    "type": "memory_optimization",
                    "description": "High memory usage detected",
                    "action": "Consider using quantized index (IVF_SQ8) to reduce memory",
                    "priority": "medium",
                    "estimated_improvement": "50-75% memory reduction"
                })
            
            # Dimension-specific recommendations
            if dimension > 1024:
                recommendations["recommendations"].append({
                    "type": "dimension_optimization",
                    "description": "High-dimensional vectors detected",
                    "action": "Consider dimensionality reduction or PCA preprocessing",
                    "priority": "low",
                    "estimated_improvement": "Faster searches and lower memory usage"
                })
            
            # Search parameter optimization
            if hasattr(self, '_optimization_cache') and collection_name not in self._optimization_cache:
                recommendations["recommendations"].append({
                    "type": "parameter_tuning",
                    "description": "Search parameters not optimized",
                    "action": "Run search performance optimization",
                    "priority": "medium",
                    "estimated_improvement": "10-30% faster searches"
                })
            
            # General recommendations
            if not recommendations["recommendations"]:
                recommendations["recommendations"].append({
                    "type": "monitoring",
                    "description": "Collection appears well-optimized",
                    "action": "Monitor performance and re-evaluate as data grows",
                    "priority": "low",
                    "estimated_improvement": "Maintain current performance"
                })
            
            logger.info(f"Generated {len(recommendations['recommendations'])} recommendations for '{collection_name}'")
            return recommendations
            
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            
            raise ValidationError(
                f"Failed to get optimization recommendations for '{collection_name}': {e}",
                field_name="collection_name",
                field_value=collection_name,
                original_exception=e
            )