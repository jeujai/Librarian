"""
Optimized Vector Store for Multimodal Librarian.

This module provides an optimized version of the vector store with:
- Improved embedding generation using batch processing and caching
- Optimized similarity calculations with efficient algorithms
- Reduced memory usage through smart resource management
- Enhanced performance monitoring and optimization

Migrated from Milvus to OpenSearch for AWS-native implementation.

Validates: Requirement 4.1 - Performance Optimization
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
import uuid
from datetime import datetime
import asyncio

import numpy as np

from ...models.core import KnowledgeChunk, SourceType, ContentType
from ...config import get_settings
from .vector_store import VectorStore, VectorStoreError
from .vector_operations_optimizer import VectorOperationsOptimizer

logger = logging.getLogger(__name__)


class OptimizedVectorStore(VectorStore):
    """
    Optimized vector database component with enhanced performance.
    
    This class extends the base VectorStore with optimizations for:
    - Batch embedding generation with caching
    - Optimized similarity calculations
    - Memory-efficient operations
    - Performance monitoring and auto-optimization
    """
    
    def __init__(self, collection_name: Optional[str] = None, enable_optimizations: bool = True):
        """
        Initialize the optimized vector store.
        
        Args:
            collection_name: Name of the Milvus collection to use
            enable_optimizations: Whether to enable performance optimizations
        """
        super().__init__(collection_name)
        
        self.enable_optimizations = enable_optimizations
        self.optimizer: Optional[VectorOperationsOptimizer] = None
        
        # Performance tracking
        self.operation_stats = {
            'total_operations': 0,
            'optimized_operations': 0,
            'batch_operations': 0,
            'cache_hits': 0,
            'memory_optimizations': 0
        }
        
        # Auto-optimization settings
        self.auto_optimize_threshold = 100  # Operations before auto-optimization
        self.last_optimization = datetime.now()
        self.optimization_interval = 300  # 5 minutes
        
        logger.info(f"Optimized vector store initialized (optimizations: {enable_optimizations})")
    
    def connect(self) -> None:
        """
        Connect to Milvus database and initialize optimized components.
        
        Raises:
            VectorStoreError: If connection fails
        """
        # Call parent connect method
        super().connect()
        
        # Initialize optimizer if optimizations are enabled
        if self.enable_optimizations:
            try:
                self.optimizer = VectorOperationsOptimizer(self.settings.embedding_model)
                logger.info("Vector operations optimizer initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize optimizer, falling back to standard operations: {e}")
                self.enable_optimizations = False
    
    def generate_embedding(self, text: str) -> np.ndarray:
        """
        Generate embedding for text using optimized methods.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as numpy array
            
        Raises:
            VectorStoreError: If embedding generation fails
        """
        self.operation_stats['total_operations'] += 1
        
        if self.enable_optimizations and self.optimizer:
            try:
                embedding = self.optimizer.generate_embedding(text)
                self.operation_stats['optimized_operations'] += 1
                
                # Check if auto-optimization is needed
                self._check_auto_optimization()
                
                return embedding
                
            except Exception as e:
                logger.warning(f"Optimized embedding generation failed, falling back: {e}")
                # Fall back to parent method
                return super().generate_embedding(text)
        else:
            # Use parent method
            return super().generate_embedding(text)
    
    def generate_embeddings_batch(self, texts: List[str]) -> List[np.ndarray]:
        """
        Generate embeddings for multiple texts using optimized batch processing.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
            
        Raises:
            VectorStoreError: If batch embedding generation fails
        """
        if not texts:
            return []
        
        self.operation_stats['total_operations'] += len(texts)
        self.operation_stats['batch_operations'] += 1
        
        if self.enable_optimizations and self.optimizer:
            try:
                embeddings = self.optimizer.generate_embeddings_batch(texts)
                self.operation_stats['optimized_operations'] += len(texts)
                
                # Check if auto-optimization is needed
                self._check_auto_optimization()
                
                return embeddings
                
            except Exception as e:
                logger.warning(f"Optimized batch embedding generation failed, falling back: {e}")
                # Fall back to individual generation
                return [self.generate_embedding(text) for text in texts]
        else:
            # Fall back to individual generation using parent method
            return [super().generate_embedding(text) for text in texts]
    
    async def generate_embeddings_async(self, texts: List[str]) -> List[np.ndarray]:
        """
        Generate embeddings asynchronously using optimized methods.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        if self.enable_optimizations and self.optimizer:
            try:
                embeddings = await self.optimizer.generate_embeddings_async(texts)
                self.operation_stats['optimized_operations'] += len(texts)
                return embeddings
                
            except Exception as e:
                logger.warning(f"Async embedding generation failed, falling back: {e}")
        
        # Fall back to synchronous batch generation
        return self.generate_embeddings_batch(texts)
    
    def store_embeddings(self, chunks: List[KnowledgeChunk]) -> None:
        """
        Store chunk embeddings with optimized batch processing.
        
        Args:
            chunks: List of knowledge chunks to store
            
        Raises:
            VectorStoreError: If storage operation fails
        """
        if not self._connected or not self.collection:
            raise VectorStoreError("Vector store not connected")
        
        if not chunks:
            logger.warning("No chunks provided for storage")
            return
        
        try:
            # Separate chunks that need embeddings
            chunks_needing_embeddings = []
            texts_for_embedding = []
            
            for chunk in chunks:
                if chunk.embedding is None:
                    chunks_needing_embeddings.append(chunk)
                    texts_for_embedding.append(chunk.content)
            
            # Generate embeddings in batch if needed
            if texts_for_embedding:
                if self.enable_optimizations and self.optimizer:
                    logger.info(f"Generating {len(texts_for_embedding)} embeddings using optimized batch processing")
                    embeddings = self.generate_embeddings_batch(texts_for_embedding)
                else:
                    logger.info(f"Generating {len(texts_for_embedding)} embeddings using standard processing")
                    embeddings = [super().generate_embedding(text) for text in texts_for_embedding]
                
                # Assign embeddings to chunks
                for chunk, embedding in zip(chunks_needing_embeddings, embeddings):
                    chunk.embedding = embedding
            
            # Use parent method for actual storage
            super().store_embeddings(chunks)
            
            logger.info(f"Successfully stored {len(chunks)} chunks with optimized processing")
            
        except Exception as e:
            logger.error(f"Failed to store embeddings with optimization: {e}")
            raise VectorStoreError(f"Failed to store embeddings: {e}")
    
    def semantic_search(
        self, 
        query: str, 
        top_k: int = 10,
        source_type: Optional[SourceType] = None,
        content_type: Optional[ContentType] = None,
        source_id: Optional[str] = None,
        use_optimized_similarity: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Perform optimized semantic similarity search.
        
        Args:
            query: Search query text
            top_k: Number of results to return
            source_type: Filter by source type (book/conversation)
            content_type: Filter by content type
            source_id: Filter by specific source ID
            use_optimized_similarity: Whether to use optimized similarity calculations
            
        Returns:
            List of search results with metadata and similarity scores
            
        Raises:
            VectorStoreError: If search operation fails
        """
        if not self._connected or not self.collection:
            raise VectorStoreError("Vector store not connected")
        
        try:
            # Generate query embedding using optimized method
            if self.enable_optimizations and self.optimizer:
                query_embedding = self.optimizer.generate_embedding(query)
                self.operation_stats['optimized_operations'] += 1
            else:
                query_embedding = super().generate_embedding(query)
            
            # Build search expression for filtering
            search_expr = self._build_search_expression(source_type, content_type, source_id)
            
            # Perform search with optimized parameters
            search_params = {
                "metric_type": "COSINE",
                "params": {"ef": min(128, top_k * 4)}  # Optimize ef parameter based on top_k
            }
            
            # Increase search limit for better optimization opportunities
            search_limit = min(top_k * 2, 100) if use_optimized_similarity else top_k
            
            results = self.collection.search(
                data=[query_embedding.tolist()],
                anns_field="embedding",
                param=search_params,
                limit=search_limit,
                expr=search_expr,
                output_fields=[
                    "chunk_id", "source_type", "source_id", "content_type",
                    "location_reference", "section", "content", "created_at"
                ]
            )
            
            # Format results
            formatted_results = []
            for hits in results:
                for hit in hits:
                    result = {
                        "chunk_id": hit.entity.get("chunk_id"),
                        "content": hit.entity.get("content"),
                        "source_type": hit.entity.get("source_type"),
                        "source_id": hit.entity.get("source_id"),
                        "content_type": hit.entity.get("content_type"),
                        "location_reference": hit.entity.get("location_reference"),
                        "section": hit.entity.get("section"),
                        "similarity_score": float(hit.score),
                        "created_at": hit.entity.get("created_at")
                    }
                    formatted_results.append(result)
            
            # Apply additional optimization if enabled and we have more results than needed
            if (use_optimized_similarity and 
                self.enable_optimizations and 
                self.optimizer and 
                len(formatted_results) > top_k):
                
                try:
                    # Re-rank results using optimized similarity calculation
                    optimized_results = self._rerank_results_optimized(
                        query_embedding, formatted_results, top_k
                    )
                    formatted_results = optimized_results
                    
                except Exception as e:
                    logger.warning(f"Optimized re-ranking failed, using original results: {e}")
                    formatted_results = formatted_results[:top_k]
            else:
                formatted_results = formatted_results[:top_k]
            
            logger.info(f"Found {len(formatted_results)} results for query: {query[:50]}...")
            return formatted_results
            
        except Exception as e:
            logger.error(f"Failed to perform optimized semantic search: {e}")
            raise VectorStoreError(f"Failed to perform semantic search: {e}")
    
    def _rerank_results_optimized(
        self, 
        query_embedding: np.ndarray, 
        results: List[Dict[str, Any]], 
        top_k: int
    ) -> List[Dict[str, Any]]:
        """
        Re-rank search results using optimized similarity calculations.
        
        Args:
            query_embedding: Query embedding vector
            results: List of search results
            top_k: Number of top results to return
            
        Returns:
            Re-ranked list of results
        """
        if not self.optimizer:
            return results[:top_k]
        
        try:
            # Extract embeddings from results (would need to be stored or re-generated)
            # For now, use the existing similarity scores as they're already optimized by Milvus
            # In a full implementation, we might store embeddings separately for re-ranking
            
            # Sort by similarity score (higher is better for cosine similarity)
            sorted_results = sorted(results, key=lambda x: x['similarity_score'], reverse=True)
            
            return sorted_results[:top_k]
            
        except Exception as e:
            logger.error(f"Optimized re-ranking failed: {e}")
            return results[:top_k]
    
    def _check_auto_optimization(self) -> None:
        """Check if auto-optimization should be triggered."""
        now = datetime.now()
        
        # Check if enough operations have been performed
        if (self.operation_stats['total_operations'] % self.auto_optimize_threshold == 0 or
            (now - self.last_optimization).total_seconds() > self.optimization_interval):
            
            self._auto_optimize()
    
    def _auto_optimize(self) -> None:
        """Perform automatic optimization."""
        try:
            logger.info("Performing automatic optimization")
            
            if self.optimizer:
                optimization_result = self.optimizer.optimize_memory()
                self.operation_stats['memory_optimizations'] += 1
                
                logger.info(f"Auto-optimization completed: {optimization_result}")
            
            self.last_optimization = datetime.now()
            
        except Exception as e:
            logger.error(f"Auto-optimization failed: {e}")
    
    def optimize_performance(self) -> Dict[str, Any]:
        """
        Manually trigger performance optimization.
        
        Returns:
            Dictionary with optimization results
        """
        logger.info("Manual performance optimization triggered")
        
        optimization_results = {
            "timestamp": datetime.now().isoformat(),
            "operations_before_optimization": self.operation_stats.copy()
        }
        
        try:
            if self.optimizer:
                # Optimize memory usage
                memory_optimization = self.optimizer.optimize_memory()
                optimization_results["memory_optimization"] = memory_optimization
                
                # Get performance stats
                performance_stats = self.optimizer.get_comprehensive_stats()
                optimization_results["performance_stats"] = performance_stats
                
                self.operation_stats['memory_optimizations'] += 1
            
            # Force garbage collection
            import gc
            gc.collect()
            
            optimization_results["operations_after_optimization"] = self.operation_stats.copy()
            optimization_results["success"] = True
            
            logger.info("Manual performance optimization completed successfully")
            
        except Exception as e:
            logger.error(f"Manual performance optimization failed: {e}")
            optimization_results["error"] = str(e)
            optimization_results["success"] = False
        
        return optimization_results
    
    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get comprehensive performance metrics.
        
        Returns:
            Dictionary with performance metrics
        """
        metrics = {
            "timestamp": datetime.now().isoformat(),
            "operation_stats": self.operation_stats.copy(),
            "optimization_enabled": self.enable_optimizations,
            "last_optimization": self.last_optimization.isoformat()
        }
        
        if self.optimizer:
            try:
                optimizer_stats = self.optimizer.get_comprehensive_stats()
                metrics["optimizer_stats"] = optimizer_stats
                
                # Calculate efficiency metrics
                if self.operation_stats['total_operations'] > 0:
                    metrics["optimization_efficiency"] = {
                        "optimized_operation_ratio": (
                            self.operation_stats['optimized_operations'] / 
                            self.operation_stats['total_operations']
                        ),
                        "batch_operation_ratio": (
                            self.operation_stats['batch_operations'] / 
                            max(1, self.operation_stats['total_operations'] // 10)  # Rough estimate
                        )
                    }
                
            except Exception as e:
                logger.error(f"Failed to get optimizer stats: {e}")
                metrics["optimizer_error"] = str(e)
        
        return metrics
    
    def health_check(self) -> bool:
        """
        Enhanced health check including optimizer status.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            # Check parent health
            parent_healthy = super().health_check()
            
            if not parent_healthy:
                return False
            
            # Check optimizer health if enabled
            if self.enable_optimizations and self.optimizer:
                optimizer_healthy = self.optimizer.health_check()
                if not optimizer_healthy:
                    logger.warning("Optimizer health check failed, but vector store is still functional")
                    # Don't fail the entire health check, just disable optimizations
                    self.enable_optimizations = False
            
            return True
            
        except Exception as e:
            logger.error(f"Enhanced health check failed: {e}")
            return False
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get enhanced collection statistics including optimization metrics.
        
        Returns:
            Dictionary with collection statistics
        """
        try:
            # Get parent stats
            stats = super().get_collection_stats()
            
            # Add optimization stats
            stats["optimization_stats"] = self.operation_stats.copy()
            stats["optimization_enabled"] = self.enable_optimizations
            
            if self.optimizer:
                try:
                    optimizer_stats = self.optimizer.get_comprehensive_stats()
                    stats["optimizer_performance"] = optimizer_stats
                except Exception as e:
                    logger.error(f"Failed to get optimizer stats for collection stats: {e}")
                    stats["optimizer_error"] = str(e)
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get enhanced collection stats: {e}")
            return {"error": str(e)}
    
    def cleanup(self) -> None:
        """Clean up optimized vector store resources."""
        logger.info("Cleaning up optimized vector store resources")
        
        try:
            if self.optimizer:
                self.optimizer.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up optimizer: {e}")
        
        # Call parent cleanup
        super().disconnect()
        
        logger.info("Optimized vector store cleanup completed")
    
    def disconnect(self) -> None:
        """Disconnect from Milvus database and clean up optimizer."""
        self.cleanup()
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        try:
            self.cleanup()
        except:
            pass  # Ignore errors during cleanup


# Factory function for creating optimized vector store
def create_optimized_vector_store(
    collection_name: Optional[str] = None,
    enable_optimizations: bool = True
) -> OptimizedVectorStore:
    """
    Factory function to create an optimized vector store instance.
    
    Args:
        collection_name: Name of the Milvus collection to use
        enable_optimizations: Whether to enable performance optimizations
        
    Returns:
        OptimizedVectorStore instance
    """
    return OptimizedVectorStore(collection_name, enable_optimizations)