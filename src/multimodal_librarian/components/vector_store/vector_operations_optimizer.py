"""
Vector Operations Optimizer for Multimodal Librarian.

This module provides optimized vector operations including:
- Improved embedding generation with batching and caching
- Optimized similarity calculations with efficient algorithms
- Reduced memory usage through smart resource management

Uses model server for embeddings (separate container).

Validates: Requirement 4.1 - Performance Optimization
"""

import asyncio
import gc
import hashlib
import logging
import pickle
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import psutil

# Caching imports
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Model server client imports
from ...clients.model_server_client import (
    ModelServerUnavailable,
    get_model_client,
    initialize_model_client,
)
from ...config import get_settings
from ...logging_config import get_logger

logger = get_logger("vector_operations_optimizer")


@dataclass
class EmbeddingCacheEntry:
    """Cache entry for embeddings with metadata."""
    embedding: np.ndarray
    text_hash: str
    model_name: str
    created_at: datetime
    access_count: int = 0
    last_accessed: Optional[datetime] = None


@dataclass
class BatchEmbeddingRequest:
    """Request for batch embedding generation."""
    texts: List[str]
    request_id: str
    priority: int = 0  # Higher priority processed first
    callback: Optional[callable] = None


@dataclass
class VectorOperationStats:
    """Statistics for vector operations performance."""
    total_embeddings_generated: int = 0
    total_batch_operations: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    avg_embedding_time_ms: float = 0.0
    avg_batch_size: float = 0.0
    memory_usage_mb: float = 0.0


class OptimizedEmbeddingGenerator:
    """
    Optimized embedding generator with batching, caching, and memory management.
    
    Features:
    - Model server integration for embeddings
    - Batch processing for improved throughput
    - Multi-level caching (memory + Redis)
    - Memory-efficient operations
    - Async processing support
    """
    
    def __init__(self, model_name: str = None, cache_size: int = 10000):
        """
        Initialize optimized embedding generator.
        
        Args:
            model_name: Name of the sentence transformer model
            cache_size: Maximum number of embeddings to cache in memory
        """
        self.settings = get_settings()
        self.model_name = model_name or self.settings.embedding_model
        self.cache_size = cache_size
        
        # Caching
        self.memory_cache: Dict[str, EmbeddingCacheEntry] = {}
        self.redis_client = self._initialize_redis_cache()
        
        # Batch processing
        self.batch_queue: List[BatchEmbeddingRequest] = []
        self.batch_size = 32  # Optimal batch size for most models
        self.max_batch_wait_ms = 100  # Maximum wait time for batching
        self.batch_processor_active = False
        
        # Thread pool for async operations
        self.thread_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="embedding")
        
        # Performance tracking
        self.stats = VectorOperationStats()
        self._lock = threading.Lock()
        
        # Memory monitoring
        self.memory_threshold_mb = 1024  # 1GB threshold
        self.cleanup_interval = 300  # 5 minutes
        self.last_cleanup = datetime.now()
        
        logger.info(f"Optimized embedding generator initialized with model: {self.model_name}")
        logger.info("Using model server for embeddings")
    
    def _initialize_redis_cache(self) -> Optional[redis.Redis]:
        """Initialize Redis cache if available."""
        if not REDIS_AVAILABLE:
            logger.info("Redis not available, using memory cache only")
            return None
        
        try:
            redis_client = redis.Redis(
                host=self.settings.redis_host,
                port=self.settings.redis_port,
                db=self.settings.redis_db,
                password=self.settings.redis_password,
                ssl=self.settings.redis_ssl,
                decode_responses=False  # We'll store binary data
            )
            
            # Test connection
            redis_client.ping()
            logger.info("Redis cache initialized successfully")
            return redis_client
            
        except Exception as e:
            logger.warning(f"Failed to initialize Redis cache: {e}")
            return None
    
    async def _get_model_client(self):
        """Get or initialize the model server client."""
        client = get_model_client()
        if client is None:
            await initialize_model_client()
            client = get_model_client()
        return client
    
    def _generate_text_hash(self, text: str) -> str:
        """Generate a hash for text to use as cache key."""
        # Include model name in hash to avoid conflicts between models
        combined = f"{self.model_name}:{text}"
        return hashlib.sha256(combined.encode()).hexdigest()[:16]
    
    def _get_cached_embedding(self, text: str) -> Optional[np.ndarray]:
        """Get embedding from cache (memory first, then Redis)."""
        text_hash = self._generate_text_hash(text)
        
        # Check memory cache first
        if text_hash in self.memory_cache:
            entry = self.memory_cache[text_hash]
            entry.access_count += 1
            entry.last_accessed = datetime.now()
            self.stats.cache_hits += 1
            return entry.embedding
        
        # Check Redis cache
        if self.redis_client:
            try:
                cached_data = self.redis_client.get(f"embedding:{text_hash}")
                if cached_data:
                    embedding = pickle.loads(cached_data)
                    
                    # Store in memory cache for faster access
                    self._store_in_memory_cache(text, embedding, text_hash)
                    
                    self.stats.cache_hits += 1
                    return embedding
                    
            except Exception as e:
                logger.warning(f"Redis cache read error: {e}")
        
        self.stats.cache_misses += 1
        return None
    
    def _store_in_memory_cache(self, text: str, embedding: np.ndarray, text_hash: str = None) -> None:
        """Store embedding in memory cache."""
        if text_hash is None:
            text_hash = self._generate_text_hash(text)
        
        # Check if we need to clean up cache
        if len(self.memory_cache) >= self.cache_size:
            self._cleanup_memory_cache()
        
        entry = EmbeddingCacheEntry(
            embedding=embedding,
            text_hash=text_hash,
            model_name=self.model_name,
            created_at=datetime.now(),
            access_count=1,
            last_accessed=datetime.now()
        )
        
        self.memory_cache[text_hash] = entry
    
    def _store_in_redis_cache(self, text: str, embedding: np.ndarray, ttl: int = 3600) -> None:
        """Store embedding in Redis cache."""
        if not self.redis_client:
            return
        
        try:
            text_hash = self._generate_text_hash(text)
            cached_data = pickle.dumps(embedding)
            
            self.redis_client.setex(
                f"embedding:{text_hash}",
                ttl,
                cached_data
            )
            
        except Exception as e:
            logger.warning(f"Redis cache write error: {e}")
    
    def _cleanup_memory_cache(self) -> None:
        """Clean up memory cache by removing least recently used entries."""
        if len(self.memory_cache) < self.cache_size:
            return
        
        # Sort by last accessed time and access count
        sorted_entries = sorted(
            self.memory_cache.items(),
            key=lambda x: (x[1].last_accessed or datetime.min, x[1].access_count)
        )
        
        # Remove oldest 25% of entries
        remove_count = len(self.memory_cache) // 4
        for i in range(remove_count):
            text_hash, _ = sorted_entries[i]
            del self.memory_cache[text_hash]
        
        logger.debug(f"Cleaned up {remove_count} entries from memory cache")
    
    async def generate_embedding(self, text: str) -> np.ndarray:
        """
        Generate embedding for a single text with caching.
        
        Uses model server for embedding generation.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as numpy array
            
        Raises:
            ModelServerUnavailable: If model server is not available
        """
        # Check cache first
        cached_embedding = self._get_cached_embedding(text)
        if cached_embedding is not None:
            return cached_embedding
        
        # Generate new embedding via model server
        start_time = datetime.now()
        
        client = await self._get_model_client()
        if not client or not client.enabled:
            raise ModelServerUnavailable("Model server is not enabled")
        
        embeddings = await client.generate_embeddings([text])
        if not embeddings:
            raise ModelServerUnavailable("Failed to generate embedding from model server")
        
        embedding = np.array(embeddings[0])
        
        # Cache the result
        self._store_in_memory_cache(text, embedding)
        self._store_in_redis_cache(text, embedding)
        
        # Update stats
        generation_time = (datetime.now() - start_time).total_seconds() * 1000
        with self._lock:
            self.stats.total_embeddings_generated += 1
            self.stats.avg_embedding_time_ms = (
                (self.stats.avg_embedding_time_ms * (self.stats.total_embeddings_generated - 1) + 
                 generation_time) / self.stats.total_embeddings_generated
            )
        
        return embedding
    
    async def generate_embeddings_batch(self, texts: List[str]) -> List[np.ndarray]:
        """
        Generate embeddings for multiple texts with optimized batching.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
            
        Raises:
            ModelServerUnavailable: If model server is not available
        """
        if not texts:
            return []
        
        start_time = datetime.now()
        
        # Check cache for all texts
        embeddings = []
        uncached_texts = []
        uncached_indices = []
        
        for i, text in enumerate(texts):
            cached_embedding = self._get_cached_embedding(text)
            if cached_embedding is not None:
                embeddings.append((i, cached_embedding))
            else:
                uncached_texts.append(text)
                uncached_indices.append(i)
        
        # Generate embeddings for uncached texts via model server
        if uncached_texts:
            client = await self._get_model_client()
            if not client or not client.enabled:
                raise ModelServerUnavailable("Model server is not enabled")
            
            batch_embeddings = await client.generate_embeddings(uncached_texts)
            if not batch_embeddings:
                raise ModelServerUnavailable("Failed to generate embeddings from model server")
            
            # Cache new embeddings and add to results
            for i, (text, embedding) in enumerate(zip(uncached_texts, batch_embeddings)):
                original_index = uncached_indices[i]
                emb_array = np.array(embedding)
                embeddings.append((original_index, emb_array))
                
                # Cache the result
                self._store_in_memory_cache(text, emb_array)
                self._store_in_redis_cache(text, emb_array)
        
        # Sort by original index and extract embeddings
        embeddings.sort(key=lambda x: x[0])
        result_embeddings = [emb for _, emb in embeddings]
        
        # Update stats
        generation_time = (datetime.now() - start_time).total_seconds() * 1000
        with self._lock:
            self.stats.total_batch_operations += 1
            self.stats.total_embeddings_generated += len(uncached_texts)
            self.stats.avg_batch_size = (
                (self.stats.avg_batch_size * (self.stats.total_batch_operations - 1) + 
                 len(texts)) / self.stats.total_batch_operations
            )
            
            if len(uncached_texts) > 0:
                self.stats.avg_embedding_time_ms = (
                    (self.stats.avg_embedding_time_ms * (self.stats.total_embeddings_generated - len(uncached_texts)) + 
                     generation_time) / self.stats.total_embeddings_generated
                )
        
        return result_embeddings
    
    async def generate_embeddings_async(self, texts: List[str]) -> List[np.ndarray]:
        """
        Generate embeddings asynchronously.
        
        Uses model server (truly async).
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        return await self.generate_embeddings_batch(texts)
    
    def get_memory_usage(self) -> Dict[str, float]:
        """Get current memory usage statistics."""
        process = psutil.Process()
        memory_info = process.memory_info()
        
        return {
            "process_memory_mb": memory_info.rss / (1024**2),
            "cache_entries": len(self.memory_cache),
            "cache_memory_estimate_mb": len(self.memory_cache) * 0.1  # Rough estimate
        }
    
    def optimize_memory_usage(self) -> Dict[str, Any]:
        """Optimize memory usage by cleaning up caches and running garbage collection."""
        initial_memory = self.get_memory_usage()
        
        # Clean up memory cache
        old_cache_size = len(self.memory_cache)
        self._cleanup_memory_cache()
        
        # Force garbage collection
        gc.collect()
        
        final_memory = self.get_memory_usage()
        
        optimization_result = {
            "initial_memory_mb": initial_memory["process_memory_mb"],
            "final_memory_mb": final_memory["process_memory_mb"],
            "memory_freed_mb": initial_memory["process_memory_mb"] - final_memory["process_memory_mb"],
            "cache_entries_removed": old_cache_size - len(self.memory_cache),
        }
        
        logger.info(f"Memory optimization completed: freed {optimization_result['memory_freed_mb']:.1f}MB")
        return optimization_result
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        memory_usage = self.get_memory_usage()
        
        cache_hit_rate = 0.0
        if self.stats.cache_hits + self.stats.cache_misses > 0:
            cache_hit_rate = self.stats.cache_hits / (self.stats.cache_hits + self.stats.cache_misses)
        
        # Get model server status
        model_server_status = {
            "enabled": False,
            "healthy": False,
        }
        try:
            client = get_model_client()
            if client:
                model_server_status["enabled"] = client.enabled
                model_server_status["healthy"] = client._healthy
        except Exception:
            pass
        
        return {
            "embedding_stats": {
                "total_embeddings_generated": self.stats.total_embeddings_generated,
                "total_batch_operations": self.stats.total_batch_operations,
                "avg_embedding_time_ms": round(self.stats.avg_embedding_time_ms, 2),
                "avg_batch_size": round(self.stats.avg_batch_size, 2)
            },
            "cache_stats": {
                "cache_hits": self.stats.cache_hits,
                "cache_misses": self.stats.cache_misses,
                "cache_hit_rate": round(cache_hit_rate, 3),
                "memory_cache_entries": len(self.memory_cache),
                "redis_available": self.redis_client is not None
            },
            "memory_stats": memory_usage,
            "model_info": {
                "model_name": self.model_name,
            },
            "model_server": model_server_status
        }
    
    async def health_check(self) -> bool:
        """Check if the embedding generator is healthy."""
        try:
            client = await self._get_model_client()
            if client and client.enabled:
                # Try to generate a test embedding
                test_embedding = await self.generate_embedding("health check test")
                if test_embedding is not None and len(test_embedding) > 0:
                    return True
            return False
        except Exception as e:
            logger.error(f"Embedding generator health check failed: {e}")
            return False
    
    def cleanup(self) -> None:
        """Clean up resources."""
        logger.info("Cleaning up embedding generator resources")
        
        # Clear caches
        self.memory_cache.clear()
        
        # Shutdown thread pool
        self.thread_pool.shutdown(wait=True)
        
        # Force garbage collection
        gc.collect()
        
        logger.info("Embedding generator cleanup completed")
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        try:
            self.cleanup()
        except:
            pass  # Ignore errors during cleanup


class OptimizedSimilarityCalculator:
    """
    Optimized similarity calculator with efficient algorithms and caching.
    
    Features:
    - Multiple similarity metrics (cosine, dot product, euclidean)
    - Batch similarity calculations
    - Result caching
    - Memory-efficient operations
    """
    
    def __init__(self, cache_size: int = 5000):
        """
        Initialize optimized similarity calculator.
        
        Args:
            cache_size: Maximum number of similarity results to cache
        """
        self.cache_size = cache_size
        self.similarity_cache: Dict[str, float] = {}
        self._lock = threading.Lock()
    
    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        # Check cache
        cache_key = self._generate_cache_key(vec1, vec2)
        if cache_key in self.similarity_cache:
            return self.similarity_cache[cache_key]
        
        # Calculate similarity
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        similarity = float(np.dot(vec1, vec2) / (norm1 * norm2))
        
        # Cache result
        self._cache_result(cache_key, similarity)
        
        return similarity
    
    def dot_product_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate dot product similarity between two vectors."""
        return float(np.dot(vec1, vec2))
    
    def euclidean_distance(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate euclidean distance between two vectors."""
        return float(np.linalg.norm(vec1 - vec2))
    
    def batch_cosine_similarity(self, query_vec: np.ndarray, 
                               candidate_vecs: List[np.ndarray]) -> List[float]:
        """Calculate cosine similarity between query and multiple candidates."""
        if not candidate_vecs:
            return []
        
        # Stack candidates for efficient computation
        candidates_matrix = np.vstack(candidate_vecs)
        
        # Normalize vectors
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-10)
        candidates_norms = candidates_matrix / (
            np.linalg.norm(candidates_matrix, axis=1, keepdims=True) + 1e-10
        )
        
        # Calculate similarities
        similarities = np.dot(candidates_norms, query_norm)
        
        return similarities.tolist()
    
    def find_top_k_similar(self, query_vec: np.ndarray, 
                          candidate_vecs: List[np.ndarray],
                          k: int = 10) -> List[tuple]:
        """Find top-k most similar vectors."""
        similarities = self.batch_cosine_similarity(query_vec, candidate_vecs)
        
        # Get top-k indices
        indexed_similarities = list(enumerate(similarities))
        indexed_similarities.sort(key=lambda x: x[1], reverse=True)
        
        return indexed_similarities[:k]
    
    def _generate_cache_key(self, vec1: np.ndarray, vec2: np.ndarray) -> str:
        """Generate cache key for vector pair."""
        # Use hash of concatenated vectors
        combined = np.concatenate([vec1.flatten(), vec2.flatten()])
        return hashlib.md5(combined.tobytes()).hexdigest()
    
    def _cache_result(self, key: str, value: float) -> None:
        """Cache similarity result with size limit."""
        with self._lock:
            if len(self.similarity_cache) >= self.cache_size:
                # Remove oldest entries (simple FIFO)
                keys_to_remove = list(self.similarity_cache.keys())[:self.cache_size // 4]
                for k in keys_to_remove:
                    del self.similarity_cache[k]
            
            self.similarity_cache[key] = value
    
    def clear_cache(self) -> None:
        """Clear the similarity cache."""
        with self._lock:
            self.similarity_cache.clear()


class VectorOperationsOptimizer:
    """
    Unified vector operations optimizer combining embedding generation and similarity calculation.
    
    This class provides a single interface for all vector operations with:
    - Optimized embedding generation with batching and caching
    - Efficient similarity calculations
    - Memory management and cleanup
    - Performance statistics tracking
    """
    
    def __init__(self, model_name: str = None, cache_size: int = 10000):
        """
        Initialize the vector operations optimizer.
        
        Args:
            model_name: Name of the embedding model to use
            cache_size: Maximum number of embeddings to cache
        """
        self.embedding_generator = OptimizedEmbeddingGenerator(
            model_name=model_name,
            cache_size=cache_size
        )
        self.similarity_calculator = OptimizedSimilarityCalculator(
            cache_size=cache_size // 2
        )
    
    async def generate_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for a single text."""
        return await self.embedding_generator.generate_embedding(text)
    
    async def generate_embeddings(self, texts: List[str]) -> List[np.ndarray]:
        """Generate embeddings for multiple texts."""
        return await self.embedding_generator.generate_embeddings_batch(texts)
    
    async def generate_embeddings_async(self, texts: List[str]) -> List[np.ndarray]:
        """Generate embeddings asynchronously."""
        return await self.embedding_generator.generate_embeddings_async(texts)
    
    def cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calculate cosine similarity between two vectors."""
        return self.similarity_calculator.cosine_similarity(vec1, vec2)
    
    def batch_cosine_similarity(self, query_vec: np.ndarray, 
                               candidate_vecs: List[np.ndarray]) -> List[float]:
        """Calculate cosine similarity between query and multiple candidates."""
        return self.similarity_calculator.batch_cosine_similarity(query_vec, candidate_vecs)
    
    def find_top_k_similar(self, query_vec: np.ndarray,
                          candidate_vecs: List[np.ndarray],
                          k: int = 10) -> List[tuple]:
        """Find top-k most similar vectors."""
        return self.similarity_calculator.find_top_k_similar(query_vec, candidate_vecs, k)
    
    def get_memory_usage(self) -> Dict[str, float]:
        """Get current memory usage statistics."""
        return self.embedding_generator.get_memory_usage()
    
    def optimize_memory_usage(self) -> Dict[str, Any]:
        """Optimize memory usage by cleaning up caches."""
        result = self.embedding_generator.optimize_memory_usage()
        self.similarity_calculator.clear_cache()
        return result
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        return self.embedding_generator.get_performance_stats()
    
    async def health_check(self) -> bool:
        """Check if the optimizer is healthy."""
        return await self.embedding_generator.health_check()
    
    def cleanup(self) -> None:
        """Clean up resources."""
        self.embedding_generator.cleanup()
        self.similarity_calculator.clear_cache()


# Global instances for convenience
_embedding_generator: Optional[OptimizedEmbeddingGenerator] = None
_similarity_calculator: Optional[OptimizedSimilarityCalculator] = None
_vector_optimizer: Optional[VectorOperationsOptimizer] = None


def get_embedding_generator() -> OptimizedEmbeddingGenerator:
    """Get or create the global embedding generator instance."""
    global _embedding_generator
    if _embedding_generator is None:
        _embedding_generator = OptimizedEmbeddingGenerator()
    return _embedding_generator


def get_similarity_calculator() -> OptimizedSimilarityCalculator:
    """Get or create the global similarity calculator instance."""
    global _similarity_calculator
    if _similarity_calculator is None:
        _similarity_calculator = OptimizedSimilarityCalculator()
    return _similarity_calculator


def get_vector_optimizer(model_name: str = None) -> VectorOperationsOptimizer:
    """Get or create the global vector operations optimizer instance."""
    global _vector_optimizer
    if _vector_optimizer is None:
        _vector_optimizer = VectorOperationsOptimizer(model_name=model_name)
    return _vector_optimizer


async def generate_optimized_embeddings(texts: List[str]) -> List[np.ndarray]:
    """Convenience function for generating embeddings."""
    generator = get_embedding_generator()
    return await generator.generate_embeddings_batch(texts)


def calculate_similarity(vec1: np.ndarray, vec2: np.ndarray, 
                        metric: str = "cosine") -> float:
    """Convenience function for calculating similarity."""
    calculator = get_similarity_calculator()
    
    if metric == "cosine":
        return calculator.cosine_similarity(vec1, vec2)
    elif metric == "dot":
        return calculator.dot_product_similarity(vec1, vec2)
    elif metric == "euclidean":
        return calculator.euclidean_distance(vec1, vec2)
    else:
        raise ValueError(f"Unknown similarity metric: {metric}")
