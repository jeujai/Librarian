"""
Vector Database Component for Multimodal Librarian.

This module implements the vector database integration using AWS OpenSearch for storing
and searching embeddings from all knowledge sources including books and conversations.
It provides unified storage and retrieval capabilities with metadata filtering.

Migrated from Milvus to OpenSearch as part of AWS-native database implementation.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ...clients.opensearch_client import OpenSearchClient, OpenSearchConnectionError
from ...config import get_settings
from ...models.core import ContentType, KnowledgeChunk, SourceType

logger = logging.getLogger(__name__)


class VectorStoreError(Exception):
    """Custom exception for vector store operations."""
    pass


class VectorStore:
    """
    Vector database component for storing and searching knowledge embeddings.
    
    This class manages the OpenSearch vector database connection and provides
    methods for storing, searching, and managing knowledge chunk embeddings
    with associated metadata.
    
    Migrated from Milvus to OpenSearch for AWS-native implementation.
    """
    
    def __init__(self, collection_name: Optional[str] = None):
        """
        Initialize the vector store.
        
        Args:
            collection_name: Name of the OpenSearch index to use (optional, uses default)
        """
        self.settings = get_settings()
        self.collection_name = collection_name  # For compatibility, but OpenSearch uses index_name
        self.opensearch_client: Optional[OpenSearchClient] = None
        self._connected = False
        
    def connect(self) -> None:
        """
        Connect to OpenSearch database and initialize index.
        
        Raises:
            VectorStoreError: If connection fails
        """
        try:
            # Create OpenSearch client
            self.opensearch_client = OpenSearchClient()
            self.opensearch_client.connect()
            self._connected = True
            logger.info(f"Connected to OpenSearch")
            
        except Exception as e:
            logger.error(f"Failed to connect to OpenSearch: {e}")
            raise VectorStoreError(f"Failed to connect to vector database: {e}")
    
    def disconnect(self) -> None:
        """Disconnect from OpenSearch database."""
        if self._connected and self.opensearch_client:
            self.opensearch_client.disconnect()
            self._connected = False
            logger.info("Disconnected from OpenSearch")
    
    def generate_embedding(self, text: str) -> np.ndarray:
        """
        Generate embedding for text using sentence transformer.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as numpy array
            
        Raises:
            VectorStoreError: If embedding generation fails
        """
        if not self.opensearch_client:
            raise VectorStoreError("OpenSearch client not initialized")
        
        try:
            embedding = self.opensearch_client.generate_embedding(text)
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise VectorStoreError(f"Failed to generate embedding: {e}")
    
    def store_embeddings(self, chunks: List[KnowledgeChunk]) -> None:
        """
        Store chunk embeddings with metadata in the vector database.
        
        Args:
            chunks: List of knowledge chunks to store
            
        Raises:
            VectorStoreError: If storage operation fails
        """
        if not self._connected or not self.opensearch_client:
            raise VectorStoreError("Vector store not connected")
        
        if not chunks:
            logger.warning("No chunks provided for storage")
            return
        
        try:
            # Prepare data for OpenSearch
            chunk_data = []
            
            for chunk in chunks:
                # Generate embedding if not present
                if chunk.embedding is None:
                    chunk.embedding = self.generate_embedding(chunk.content)
                
                # Prepare document
                doc = {
                    'chunk_id': chunk.id,
                    'id': chunk.id,  # For compatibility
                    'embedding': chunk.embedding if isinstance(chunk.embedding, list) else chunk.embedding.tolist(),
                    'source_type': chunk.source_type.value,
                    'source_id': chunk.source_id,
                    'content_type': chunk.content_type.value,
                    'location_reference': chunk.location_reference,
                    'section': chunk.section,
                    'content': chunk.content[:65535],  # Truncate if too long
                    'created_at': int(datetime.now().timestamp() * 1000)  # Milliseconds
                }
                
                chunk_data.append(doc)
            
            # Store using OpenSearch client
            self.opensearch_client.store_embeddings(chunk_data)
            
            logger.info(f"Successfully stored {len(chunks)} chunks in vector database")
            
        except Exception as e:
            logger.error(f"Failed to store embeddings: {e}")
            raise VectorStoreError(f"Failed to store embeddings: {e}")
    
    def store_bridge_chunks(self, bridge_chunks: List[KnowledgeChunk]) -> None:
        """
        Store bridge chunks with special metadata indicating their bridge nature.
        
        Args:
            bridge_chunks: List of bridge chunks to store
        """
        # Mark bridge chunks with special content type
        for chunk in bridge_chunks:
            if chunk.content_type == ContentType.GENERAL:
                # Add bridge indicator to section field
                chunk.section = f"BRIDGE_{chunk.section}" if chunk.section else "BRIDGE"
        
        self.store_embeddings(bridge_chunks)
        logger.info(f"Stored {len(bridge_chunks)} bridge chunks")
    
    def semantic_search(
        self, 
        query: str, 
        top_k: int = 10,
        source_type: Optional[SourceType] = None,
        content_type: Optional[ContentType] = None,
        source_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic similarity search across all stored content.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            source_type: Filter by source type (book/conversation)
            content_type: Filter by content type
            source_id: Filter by specific source ID
            
        Returns:
            List of search results with metadata and similarity scores
            
        Raises:
            VectorStoreError: If search operation fails
        """
        if not self._connected or not self.opensearch_client:
            raise VectorStoreError("Vector store not connected")
        
        try:
            # Use OpenSearch client's semantic search
            results = self.opensearch_client.semantic_search(
                query=query,
                top_k=top_k,
                source_type=source_type.value if source_type else None,
                content_type=content_type.value if content_type else None,
                source_id=source_id
            )
            
            logger.info(f"Found {len(results)} results for query: {query[:50]}...")
            return results
            
        except Exception as e:
            logger.error(f"Failed to perform semantic search: {e}")
            raise VectorStoreError(f"Failed to perform semantic search: {e}")
    
    def search_bridge_chunks(
        self, 
        query: str, 
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search specifically for bridge chunks.
        
        Args:
            query: Search query text
            top_k: Number of bridge chunks to return
            
        Returns:
            List of bridge chunk search results
        """
        try:
            # Generate query embedding
            query_embedding = self.generate_embedding(query)
            
            # Use OpenSearch client with wildcard filter for BRIDGE sections
            # Note: OpenSearch client's semantic_search doesn't support wildcard filters directly
            # So we'll do a broader search and filter results
            results = self.opensearch_client.semantic_search(
                query=query,
                top_k=top_k * 2  # Get more results to filter
            )
            
            # Filter for bridge chunks
            bridge_results = []
            for result in results:
                if result.get('section', '').startswith('BRIDGE'):
                    result['is_bridge'] = True
                    bridge_results.append(result)
                    if len(bridge_results) >= top_k:
                        break
            
            logger.info(f"Found {len(bridge_results)} bridge chunks for query")
            return bridge_results
            
        except Exception as e:
            logger.error(f"Failed to search bridge chunks: {e}")
            raise VectorStoreError(f"Failed to search bridge chunks: {e}")
    
    def _build_search_expression(
        self,
        source_type: Optional[SourceType] = None,
        content_type: Optional[ContentType] = None,
        source_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Build search expression for metadata filtering (legacy method for compatibility).
        
        Args:
            source_type: Filter by source type
            content_type: Filter by content type
            source_id: Filter by source ID
            
        Returns:
            Search expression string or None if no filters
        """
        # This method is kept for compatibility but not used with OpenSearch
        # OpenSearch uses dict-based filters instead
        return None
    
    def get_chunk_by_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific chunk by its ID.
        
        Args:
            chunk_id: ID of the chunk to retrieve
            
        Returns:
            Chunk data or None if not found
        """
        if not self._connected or not self.opensearch_client:
            raise VectorStoreError("Vector store not connected")
        
        try:
            result = self.opensearch_client.get_chunk_by_id(chunk_id)
            return result
            
        except Exception as e:
            logger.error(f"Failed to get chunk by ID: {e}")
            raise VectorStoreError(f"Failed to get chunk by ID: {e}")
    
    def delete_chunks_by_source(self, source_id: str) -> int:
        """
        Delete all chunks from a specific source.
        
        Args:
            source_id: ID of the source to delete chunks from
            
        Returns:
            Number of chunks deleted
        """
        if not self._connected or not self.opensearch_client:
            raise VectorStoreError("Vector store not connected")
        
        try:
            deleted_count = self.opensearch_client.delete_chunks_by_source(source_id)
            logger.info(f"Deleted {deleted_count} chunks for source: {source_id}")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to delete chunks by source: {e}")
            raise VectorStoreError(f"Failed to delete chunks by source: {e}")
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the vector collection.
        
        Returns:
            Dictionary with collection statistics
        """
        if not self._connected or not self.opensearch_client:
            raise VectorStoreError("Vector store not connected")
        
        try:
            stats = self.opensearch_client.get_collection_stats()
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            raise VectorStoreError(f"Failed to get collection stats: {e}")
    
    def health_check(self) -> bool:
        """
        Check if the vector store is healthy and operational.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            if not self._connected or not self.opensearch_client:
                return False
            
            health_result = self.opensearch_client.health_check()
            return health_result.get('status') == 'healthy'
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False
    
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
        
        This method offloads the CPU-bound embedding generation to a thread pool,
        preventing the event loop from being blocked.
        
        Args:
            text: Text to generate embedding for
            
        Returns:
            Embedding vector as numpy array
        """
        if not self.opensearch_client:
            raise VectorStoreError("OpenSearch client not initialized")
        
        return await self.opensearch_client.generate_embedding_async(text)
    
    async def semantic_search_async(
        self, 
        query: str, 
        top_k: int = 10,
        source_type: Optional[SourceType] = None,
        content_type: Optional[ContentType] = None,
        source_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Perform semantic similarity search asynchronously (non-blocking).
        
        This is the async version of semantic_search() that properly offloads
        the CPU-bound embedding generation to a thread pool.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            source_type: Filter by source type (book/conversation)
            content_type: Filter by content type
            source_id: Filter by specific source ID
            
        Returns:
            List of search results with metadata and similarity scores
        """
        if not self._connected or not self.opensearch_client:
            raise VectorStoreError("Vector store not connected")
        
        try:
            results = await self.opensearch_client.semantic_search_async(
                query=query,
                top_k=top_k,
                source_type=source_type.value if source_type else None,
                content_type=content_type.value if content_type else None,
                source_id=source_id
            )
            
            logger.info(f"Async search found {len(results)} results for query: {query[:50]}...")
            return results
            
        except Exception as e:
            logger.error(f"Failed to perform async semantic search: {e}")
            raise VectorStoreError(f"Failed to perform async semantic search: {e}")