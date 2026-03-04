"""
Amazon OpenSearch Client for Multimodal Librarian

This module provides an OpenSearch client with vector search support, maintaining
compatibility with the existing Milvus-based vector store interface.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import boto3
import numpy as np
from opensearchpy import OpenSearch, RequestsHttpConnection
from opensearchpy.exceptions import OpenSearchException

logger = logging.getLogger(__name__)

# Flag to track if we should use model server or local fallback
_USE_MODEL_SERVER = True  # Default to model server


class OpenSearchConnectionError(Exception):
    """Raised when OpenSearch connection fails."""
    pass


class OpenSearchClient:
    """
    OpenSearch client with vector search support and Milvus-compatible interface.
    
    This client separates construction from connection to support dependency injection.
    The constructor only initializes configuration - no connections are made until
    connect() is explicitly called.
    
    Usage:
        # DI pattern (recommended):
        client = OpenSearchClient()  # No connection made
        client.connect()  # Connection established here
        
        # Context manager pattern:
        with OpenSearchClient() as client:
            client.semantic_search(...)
    """
    
    def __init__(
        self, 
        secret_name: str = "multimodal-librarian/aws-native/opensearch", 
        region: str = "us-east-1",
        auto_connect: bool = False
    ):
        """
        Initialize OpenSearch client configuration.
        
        This constructor only sets up configuration - no connections are made.
        Call connect() explicitly to establish the connection.
        
        Args:
            secret_name: AWS Secrets Manager secret name for OpenSearch configuration
            region: AWS region for OpenSearch and Secrets Manager
            auto_connect: If True, connect immediately (for backward compatibility).
                         Default is False for DI pattern support.
        """
        self.secret_name = secret_name
        self.region = region
        self.client: Optional[OpenSearch] = None
        self._model_server_client = None  # Model server client (lazy loaded)
        self._local_embedding_model = None  # Local fallback model (lazy loaded)
        self._credentials: Optional[Dict[str, Any]] = None
        self._last_health_check = 0
        self._health_check_interval = 30  # seconds
        self._is_healthy = False
        self.index_name = "knowledge_chunks"
        self.embedding_dimension = 384  # Default for all-MiniLM-L6-v2
        
        # Support backward compatibility with auto_connect
        if auto_connect:
            self.connect()
        
    def _get_credentials(self) -> Dict[str, Any]:
        """Get OpenSearch configuration from AWS Secrets Manager."""
        if self._credentials is None:
            try:
                secrets_client = boto3.client('secretsmanager', region_name=self.region)
                response = secrets_client.get_secret_value(SecretId=self.secret_name)
                self._credentials = json.loads(response['SecretString'])
                logger.info(f"Retrieved OpenSearch configuration from {self.secret_name}")
            except Exception as e:
                logger.error(f"Failed to get OpenSearch configuration: {e}")
                raise OpenSearchConnectionError(f"Failed to retrieve configuration: {e}")
        
        return self._credentials
    
    def _create_client(self) -> OpenSearch:
        """Create OpenSearch client with master user authentication."""
        credentials = self._get_credentials()
        
        # Extract endpoint
        domain_endpoint = credentials['domain_endpoint']
        
        # Remove https:// prefix if present
        if domain_endpoint.startswith('https://'):
            domain_endpoint = domain_endpoint[8:]
        
        try:
            # Get master user credentials for HTTP basic auth
            master_user = credentials.get('master_user', 'admin')
            master_password = credentials.get('master_password')
            
            if not master_password:
                raise OpenSearchConnectionError("Master password not found in credentials")
            
            logger.info(f"Connecting to OpenSearch with master user: {master_user}")
            
            # Create OpenSearch client with HTTP basic auth
            client = OpenSearch(
                hosts=[{'host': domain_endpoint, 'port': 443}],
                http_auth=(master_user, master_password),
                use_ssl=True,
                verify_certs=True,
                connection_class=RequestsHttpConnection,
                timeout=60,
                max_retries=3,
                retry_on_timeout=True
            )
            
            # Test the connection
            info = client.info()
            logger.info(f"Successfully connected to OpenSearch: {info['version']['number']}")
            return client
            
        except Exception as e:
            logger.error(f"Failed to connect to OpenSearch: {e}")
            raise OpenSearchConnectionError(f"Connection failed: {e}")
    
    def connect(self) -> None:
        """
        Establish connection to OpenSearch.
        
        NOTE: This method no longer loads the embedding model during connect().
        The embedding model is now loaded lazily on first use to prevent blocking
        the event loop during startup. This is critical for health check reliability.
        """
        if self.client is None:
            self.client = self._create_client()
            # IMPORTANT: Do NOT call _initialize_embedding_model() here!
            # The embedding model is loaded lazily on first use to prevent
            # blocking the event loop during startup, which would cause
            # health check timeouts.
            self._ensure_index_exists()
            self._is_healthy = True
            logger.info("OpenSearch connected (embedding model will load on first use)")
    
    def _initialize_embedding_model(self) -> None:
        """
        Initialize embedding capability (model server or local fallback).
        
        This method is called on first use of generate_embedding() rather than
        during connect() to prevent blocking the event loop during startup.
        
        Priority:
        1. Model server (non-blocking, recommended)
        2. Local SentenceTransformer (blocking, fallback only)
        """
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
                    # Initialize synchronously for first use
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Can't initialize in running loop, will use async method
                        logger.info("Model server client will be initialized on first async call")
                        return
                    else:
                        loop.run_until_complete(initialize_model_client())
                        client = get_model_client()
                
                if client and client.enabled:
                    self._model_server_client = client
                    logger.info("Using model server for embeddings (non-blocking)")
                    return
                    
            except Exception as e:
                logger.warning(f"Model server not available: {e}")
                _USE_MODEL_SERVER = False
        
        # Model server is required - no local fallback
        if self._local_embedding_model is None and not _USE_MODEL_SERVER:
            logger.error("Model server not available and no local fallback allowed")
            raise OpenSearchConnectionError(
                "Model server not available for embeddings. "
                "Ensure model-server container is running."
            )
    
    def _ensure_index_exists(self) -> None:
        """Ensure the knowledge chunks index exists with proper mapping."""
        try:
            if not self.client.indices.exists(index=self.index_name):
                self._create_index()
                logger.info(f"Created index: {self.index_name}")
            else:
                logger.info(f"Using existing index: {self.index_name}")
        except Exception as e:
            logger.error(f"Failed to ensure index exists: {e}")
            raise OpenSearchConnectionError(f"Failed to ensure index exists: {e}")
    
    def _create_index(self) -> None:
        """Create the knowledge chunks index with vector field mapping."""
        mapping = {
            "mappings": {
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": self.embedding_dimension,
                        "method": {
                            "name": "hnsw",
                            "space_type": "cosinesimil",
                            "engine": "nmslib",
                            "parameters": {
                                "ef_construction": 128,
                                "m": 24
                            }
                        }
                    },
                    "source_type": {"type": "keyword"},
                    "source_id": {"type": "keyword"},
                    "content_type": {"type": "keyword"},
                    "location_reference": {"type": "keyword"},
                    "section": {"type": "text"},
                    "content": {"type": "text"},
                    "created_at": {"type": "long"}
                }
            },
            "settings": {
                "index": {
                    "knn": True,
                    "knn.algo_param.ef_search": 100
                }
            }
        }
        
        self.client.indices.create(index=self.index_name, body=mapping)
    
    def disconnect(self) -> None:
        """Close OpenSearch connection."""
        if self.client:
            # OpenSearch client doesn't need explicit disconnection
            self.client = None
            self._is_healthy = False
            logger.info("Disconnected from OpenSearch")
    
    def is_connected(self) -> bool:
        """Check if client is connected to OpenSearch."""
        return self.client is not None and self._is_healthy
    
    def health_check(self, force: bool = False) -> Dict[str, Any]:
        """
        Perform health check on OpenSearch connection.
        
        Args:
            force: Force health check even if recently performed
            
        Returns:
            Dict with health status information
        """
        current_time = time.time()
        
        # Use cached result if recent and not forced
        if not force and (current_time - self._last_health_check) < self._health_check_interval:
            return {
                "status": "healthy" if self._is_healthy else "unhealthy",
                "cached": True,
                "last_check": self._last_health_check
            }
        
        try:
            if not self.client:
                self.connect()
            
            # Test with cluster health check
            health = self.client.cluster.health()
            
            if health['status'] in ['green', 'yellow']:
                self._is_healthy = True
                self._last_health_check = current_time
                
                # Get document count
                count_response = self.client.count(index=self.index_name)
                doc_count = count_response['count']
                
                return {
                    "status": "healthy",
                    "cached": False,
                    "last_check": current_time,
                    "cluster_status": health['status'],
                    "document_count": doc_count,
                    "engine": "opensearch"
                }
            else:
                raise OpenSearchConnectionError(f"Cluster status: {health['status']}")
                
        except Exception as e:
            self._is_healthy = False
            self._last_health_check = current_time
            logger.error(f"OpenSearch health check failed: {e}")
            
            return {
                "status": "unhealthy",
                "cached": False,
                "last_check": current_time,
                "error": str(e)
            }
    
    def generate_embedding(self, text: str) -> np.ndarray:
        """
        Generate embedding for text using model server or local fallback.
        
        The embedding model is loaded lazily on first call to this method.
        This prevents blocking the event loop during startup.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as numpy array
        """
        # Try model server first (non-blocking in async context)
        if self._model_server_client is not None:
            try:
                # Synchronous wrapper for model server
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in async context - caller should use generate_embedding_async
                    raise RuntimeError("Use generate_embedding_async() in async context")
                
                embeddings = loop.run_until_complete(
                    self._model_server_client.generate_embeddings([text])
                )
                if embeddings:
                    return np.array(embeddings[0])
            except RuntimeError:
                raise  # Re-raise the async context error
            except Exception as e:
                logger.warning(f"Model server embedding failed, trying fallback: {e}")
        
        # Initialize if needed
        if self._model_server_client is None and self._local_embedding_model is None:
            self._initialize_embedding_model()
        
        # Try model server again after initialization
        if self._model_server_client is not None:
            try:
                loop = asyncio.get_event_loop()
                if not loop.is_running():
                    embeddings = loop.run_until_complete(
                        self._model_server_client.generate_embeddings([text])
                    )
                    if embeddings:
                        return np.array(embeddings[0])
            except Exception as e:
                logger.warning(f"Model server embedding failed: {e}")
        
        # Fallback to local model
        if self._local_embedding_model is not None:
            try:
                embedding = self._local_embedding_model.encode([text])
                return embedding[0]
            except Exception as e:
                logger.error(f"Local embedding failed: {e}")
                raise OpenSearchConnectionError(f"Failed to generate embedding: {e}")
        
        raise OpenSearchConnectionError("No embedding model available")
    
    def index_document(self, doc_id: str, document: Dict[str, Any]) -> bool:
        """
        Index a document with vector embeddings.
        
        Args:
            doc_id: Document ID
            document: Document data including embedding
            
        Returns:
            True if successful
        """
        try:
            if not self.is_connected():
                self.connect()
            
            response = self.client.index(
                index=self.index_name,
                id=doc_id,
                body=document,
                refresh=True
            )
            
            return response['result'] in ['created', 'updated']
            
        except Exception as e:
            logger.error(f"Failed to index document: {e}")
            raise OpenSearchConnectionError(f"Document indexing failed: {e}")
    
    def vector_search(self, query_vector: List[float], k: int = 10, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Perform k-NN vector similarity search.
        
        Args:
            query_vector: Query vector
            k: Number of results to return
            filters: Optional filters for the search
            
        Returns:
            List of search results with scores
        """
        try:
            if not self.is_connected():
                self.connect()
            
            # Build the search query
            search_body = {
                "size": k,
                "query": {
                    "knn": {
                        "embedding": {
                            "vector": query_vector,
                            "k": k
                        }
                    }
                },
                "_source": {
                    "excludes": ["embedding"]  # Don't return the embedding vector
                }
            }
            
            # Add filters if provided
            if filters:
                search_body["query"] = {
                    "bool": {
                        "must": [search_body["query"]],
                        "filter": []
                    }
                }
                
                for field, value in filters.items():
                    search_body["query"]["bool"]["filter"].append({
                        "term": {field: value}
                    })
            
            response = self.client.search(
                index=self.index_name,
                body=search_body
            )
            
            # Format results
            results = []
            for hit in response['hits']['hits']:
                result = hit['_source'].copy()
                result['similarity_score'] = hit['_score']
                result['doc_id'] = hit['_id']
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            raise OpenSearchConnectionError(f"Vector search failed: {e}")
    
    # Milvus-compatible interface methods
    
    def store_embeddings(self, chunks: List[Dict[str, Any]]) -> None:
        """
        Store chunk embeddings with metadata (Milvus-compatible interface).
        
        Args:
            chunks: List of knowledge chunks to store
        """
        try:
            if not self.is_connected():
                self.connect()
            
            # Prepare bulk indexing
            bulk_body = []
            
            for chunk in chunks:
                # Generate embedding if not present
                if 'embedding' not in chunk or chunk['embedding'] is None:
                    chunk['embedding'] = self.generate_embedding(chunk['content']).tolist()
                elif isinstance(chunk['embedding'], np.ndarray):
                    chunk['embedding'] = chunk['embedding'].tolist()
                
                # Add timestamp if not present
                if 'created_at' not in chunk:
                    chunk['created_at'] = int(datetime.now().timestamp() * 1000)
                
                # Prepare document for indexing
                doc = {
                    "chunk_id": chunk.get('chunk_id', chunk.get('id')),
                    "embedding": chunk['embedding'],
                    "source_type": chunk.get('source_type'),
                    "source_id": chunk.get('source_id'),
                    "content_type": chunk.get('content_type'),
                    "location_reference": chunk.get('location_reference'),
                    "section": chunk.get('section'),
                    "content": chunk.get('content', '')[:65535],  # Truncate if too long
                    "created_at": chunk['created_at']
                }
                
                # Add to bulk body
                bulk_body.append({
                    "index": {
                        "_index": self.index_name,
                        "_id": doc["chunk_id"]
                    }
                })
                bulk_body.append(doc)
            
            # Execute bulk indexing
            if bulk_body:
                response = self.client.bulk(body=bulk_body, refresh=True)
                
                # Check for errors
                if response['errors']:
                    errors = [item for item in response['items'] if 'error' in item.get('index', {})]
                    logger.warning(f"Bulk indexing had {len(errors)} errors")
                
                logger.info(f"Successfully stored {len(chunks)} chunks in OpenSearch")
            
        except Exception as e:
            logger.error(f"Failed to store embeddings: {e}")
            raise OpenSearchConnectionError(f"Failed to store embeddings: {e}")
    
    def semantic_search(
        self, 
        query: str, 
        top_k: int = 10,
        source_type: Optional[str] = None,
        content_type: Optional[str] = None,
        source_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic similarity search (Milvus-compatible interface).
        
        Args:
            query: Search query text
            top_k: Number of results to return
            source_type: Filter by source type
            content_type: Filter by content type
            source_id: Filter by specific source ID
            
        Returns:
            List of search results with metadata and similarity scores
        """
        try:
            # Generate query embedding
            query_embedding = self.generate_embedding(query)
            
            # Build filters
            filters = {}
            if source_type:
                filters['source_type'] = source_type
            if content_type:
                filters['content_type'] = content_type
            if source_id:
                filters['source_id'] = source_id
            
            # Perform vector search
            results = self.vector_search(
                query_vector=query_embedding.tolist(),
                k=top_k,
                filters=filters if filters else None
            )
            
            logger.info(f"Found {len(results)} results for query: {query[:50]}...")
            return results
            
        except Exception as e:
            logger.error(f"Failed to perform semantic search: {e}")
            raise OpenSearchConnectionError(f"Failed to perform semantic search: {e}")
    
    def get_chunk_by_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific chunk by its ID.
        
        Args:
            chunk_id: ID of the chunk to retrieve
            
        Returns:
            Chunk data or None if not found
        """
        try:
            if not self.is_connected():
                self.connect()
            
            response = self.client.get(
                index=self.index_name,
                id=chunk_id,
                _source_excludes=["embedding"]
            )
            
            if response['found']:
                result = response['_source']
                result['doc_id'] = response['_id']
                return result
            
            return None
            
        except Exception as e:
            if "not_found" in str(e).lower():
                return None
            logger.error(f"Failed to get chunk by ID: {e}")
            raise OpenSearchConnectionError(f"Failed to get chunk by ID: {e}")
    
    def delete_chunks_by_source(self, source_id: str) -> int:
        """
        Delete all chunks from a specific source.
        
        Args:
            source_id: ID of the source to delete chunks from
            
        Returns:
            Number of chunks deleted
        """
        try:
            if not self.is_connected():
                self.connect()
            
            # Delete by query
            delete_body = {
                "query": {
                    "term": {
                        "source_id": source_id
                    }
                }
            }
            
            response = self.client.delete_by_query(
                index=self.index_name,
                body=delete_body,
                refresh=True
            )
            
            deleted_count = response['deleted']
            logger.info(f"Deleted {deleted_count} chunks for source: {source_id}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to delete chunks by source: {e}")
            raise OpenSearchConnectionError(f"Failed to delete chunks by source: {e}")
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the vector collection.
        
        Returns:
            Dictionary with collection statistics
        """
        try:
            if not self.is_connected():
                self.connect()
            
            # Get total count
            total_response = self.client.count(index=self.index_name)
            total_count = total_response['count']
            
            # Get counts by source type
            book_response = self.client.count(
                index=self.index_name,
                body={"query": {"term": {"source_type": "book"}}}
            )
            book_count = book_response['count']
            
            conversation_response = self.client.count(
                index=self.index_name,
                body={"query": {"term": {"source_type": "conversation"}}}
            )
            conversation_count = conversation_response['count']
            
            # Get bridge chunks count
            bridge_response = self.client.count(
                index=self.index_name,
                body={"query": {"wildcard": {"section": "BRIDGE*"}}}
            )
            bridge_count = bridge_response['count']
            
            return {
                "total_chunks": total_count,
                "book_chunks": book_count,
                "conversation_chunks": conversation_count,
                "bridge_chunks": bridge_count,
                "index_name": self.index_name,
                "embedding_model": "sentence-transformers/all-MiniLM-L6-v2"
            }
            
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            raise OpenSearchConnectionError(f"Failed to get collection stats: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
    
    # =========================================================================
    # ASYNC METHODS - Non-blocking versions for use in async contexts
    # =========================================================================
    
    async def generate_embedding_async(self, text: str) -> np.ndarray:
        """
        Generate embedding asynchronously (non-blocking).
        
        This method uses the model server for embedding generation,
        which is non-blocking and doesn't load models in the app container.
        
        Args:
            text: Text to generate embedding for
            
        Returns:
            Embedding vector as numpy array
        """
        # Try model server first
        if self._model_server_client is None:
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
        
        if self._model_server_client is not None:
            try:
                embeddings = await self._model_server_client.generate_embeddings([text])
                if embeddings:
                    return np.array(embeddings[0])
            except Exception as e:
                logger.warning(f"Model server embedding failed: {e}")
        
        # Fallback to async embedding service (which may use local model)
        from ..services.async_embedding_service import generate_embedding_async
        return await generate_embedding_async(text)
    
    async def generate_embeddings_batch_async(self, texts: List[str]) -> List[np.ndarray]:
        """
        Generate embeddings for multiple texts asynchronously (non-blocking).
        
        Args:
            texts: List of texts to generate embeddings for
            
        Returns:
            List of embedding vectors
        """
        # Try model server first
        if self._model_server_client is None:
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
        
        if self._model_server_client is not None:
            try:
                embeddings = await self._model_server_client.generate_embeddings(texts)
                if embeddings:
                    return [np.array(e) for e in embeddings]
            except Exception as e:
                logger.warning(f"Model server batch embedding failed: {e}")
        
        # Fallback to async embedding service
        from ..services.async_embedding_service import generate_embeddings_batch_async
        return await generate_embeddings_batch_async(texts)
    
    async def semantic_search_async(
        self,
        query: str,
        top_k: int = 10,
        source_type: Optional[str] = None,
        content_type: Optional[str] = None,
        source_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic similarity search asynchronously (non-blocking).
        
        This is the async version of semantic_search() that properly offloads
        the CPU-bound embedding generation to a thread pool.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            source_type: Filter by source type
            content_type: Filter by content type
            source_id: Filter by specific source ID
            
        Returns:
            List of search results with metadata and similarity scores
        """
        try:
            # Generate query embedding asynchronously (non-blocking)
            query_embedding = await self.generate_embedding_async(query)
            
            # Build filters
            filters = {}
            if source_type:
                filters['source_type'] = source_type
            if content_type:
                filters['content_type'] = content_type
            if source_id:
                filters['source_id'] = source_id
            
            # Perform vector search (this is I/O bound, could also be async)
            # For now, the OpenSearch client uses synchronous requests
            # but the main blocking issue was the embedding generation
            results = self.vector_search(
                query_vector=query_embedding.tolist(),
                k=top_k,
                filters=filters if filters else None
            )
            
            logger.info(f"Async search found {len(results)} results for query: {query[:50]}...")
            return results
            
        except Exception as e:
            logger.error(f"Failed to perform async semantic search: {e}")
            raise OpenSearchConnectionError(f"Failed to perform async semantic search: {e}")


# DEPRECATED: Module-level singleton pattern removed in favor of FastAPI DI
# Use api/dependencies/services.py get_opensearch_client() instead
#
# Migration guide:
#   Old: from .opensearch_client import get_opensearch_client
#        client = get_opensearch_client()
#
#   New: from ..api.dependencies import get_opensearch_client
#        # In FastAPI endpoint:
#        async def endpoint(client = Depends(get_opensearch_client)):
#            ...


def close_opensearch_client() -> None:
    """
    Close global OpenSearch client instance.
    
    DEPRECATED: Use cleanup_services() from api/dependencies/services.py instead.
    This function is kept for backward compatibility during migration.
    """
    # No-op since global client is removed
    # Use cleanup_services() from api/dependencies/services.py instead
    pass