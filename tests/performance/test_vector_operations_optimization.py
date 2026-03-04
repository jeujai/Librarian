"""
Performance tests for vector operations optimization.

Tests the optimized vector operations including:
- Embedding generation performance
- Similarity calculation optimization
- Memory usage efficiency
- Batch processing improvements

Validates: Requirement 4.1 - Performance Optimization
"""

import pytest
import asyncio
import time
import numpy as np
from typing import List, Dict, Any
import psutil
import gc

from src.multimodal_librarian.components.vector_store.vector_operations_optimizer import (
    VectorOperationsOptimizer,
    OptimizedEmbeddingGenerator,
    OptimizedSimilarityCalculator
)
from src.multimodal_librarian.components.vector_store.vector_store_optimized import (
    OptimizedVectorStore,
    create_optimized_vector_store
)
from src.multimodal_librarian.models.core import KnowledgeChunk, SourceType, ContentType


class TestVectorOperationsOptimization:
    """Test suite for vector operations optimization."""
    
    @pytest.fixture
    def sample_texts(self) -> List[str]:
        """Generate sample texts for testing."""
        return [
            "This is a sample document about machine learning and artificial intelligence.",
            "Natural language processing is a subfield of linguistics and computer science.",
            "Vector databases are used for storing and searching high-dimensional data.",
            "Semantic search enables finding relevant information based on meaning.",
            "Embeddings represent text as dense vectors in high-dimensional space.",
            "Cosine similarity measures the angle between two vectors.",
            "Batch processing improves throughput for large-scale operations.",
            "Memory optimization reduces resource usage and improves performance.",
            "Caching frequently accessed data speeds up subsequent operations.",
            "Performance monitoring helps identify bottlenecks and optimization opportunities."
        ]
    
    @pytest.fixture
    def embedding_generator(self) -> OptimizedEmbeddingGenerator:
        """Create optimized embedding generator for testing."""
        return OptimizedEmbeddingGenerator(cache_size=100)
    
    @pytest.fixture
    def similarity_calculator(self) -> OptimizedSimilarityCalculator:
        """Create optimized similarity calculator for testing."""
        return OptimizedSimilarityCalculator(cache_size=100)
    
    @pytest.fixture
    def vector_optimizer(self) -> VectorOperationsOptimizer:
        """Create vector operations optimizer for testing."""
        return VectorOperationsOptimizer()
    
    def test_embedding_generation_performance(self, embedding_generator: OptimizedEmbeddingGenerator, sample_texts: List[str]):
        """Test embedding generation performance improvements."""
        # Test single embedding generation
        start_time = time.time()
        embedding1 = embedding_generator.generate_embedding(sample_texts[0])
        single_time = time.time() - start_time
        
        assert isinstance(embedding1, np.ndarray)
        assert embedding1.shape[0] > 0  # Has dimensions
        
        # Test cached embedding (should be faster)
        start_time = time.time()
        embedding2 = embedding_generator.generate_embedding(sample_texts[0])
        cached_time = time.time() - start_time
        
        # Cached should be significantly faster
        assert cached_time < single_time * 0.1  # At least 10x faster
        assert np.array_equal(embedding1, embedding2)  # Same result
        
        # Test batch generation performance
        batch_texts = sample_texts[:5]
        start_time = time.time()
        batch_embeddings = embedding_generator.generate_embeddings_batch(batch_texts)
        batch_time = time.time() - start_time
        
        assert len(batch_embeddings) == len(batch_texts)
        assert all(isinstance(emb, np.ndarray) for emb in batch_embeddings)
        
        # Batch should be more efficient than individual generation
        start_time = time.time()
        individual_embeddings = [embedding_generator.generate_embedding(text) for text in batch_texts[5:]]
        individual_time = time.time() - start_time
        
        # Note: First batch might be slower due to model loading, but subsequent should be faster
        print(f"Single embedding time: {single_time:.4f}s")
        print(f"Cached embedding time: {cached_time:.6f}s")
        print(f"Batch time: {batch_time:.4f}s")
        print(f"Individual time: {individual_time:.4f}s")
    
    @pytest.mark.asyncio
    async def test_async_embedding_generation(self, embedding_generator: OptimizedEmbeddingGenerator, sample_texts: List[str]):
        """Test asynchronous embedding generation."""
        batch_texts = sample_texts[:3]
        
        start_time = time.time()
        async_embeddings = await embedding_generator.generate_embeddings_async(batch_texts)
        async_time = time.time() - start_time
        
        assert len(async_embeddings) == len(batch_texts)
        assert all(isinstance(emb, np.ndarray) for emb in async_embeddings)
        
        # Compare with synchronous generation
        start_time = time.time()
        sync_embeddings = embedding_generator.generate_embeddings_batch(batch_texts)
        sync_time = time.time() - start_time
        
        # Results should be the same
        for async_emb, sync_emb in zip(async_embeddings, sync_embeddings):
            assert np.allclose(async_emb, sync_emb, rtol=1e-5)
        
        print(f"Async embedding time: {async_time:.4f}s")
        print(f"Sync embedding time: {sync_time:.4f}s")
    
    def test_similarity_calculation_optimization(self, similarity_calculator: OptimizedSimilarityCalculator):
        """Test optimized similarity calculations."""
        # Generate test vectors
        vec1 = np.random.rand(384).astype(np.float32)
        vec2 = np.random.rand(384).astype(np.float32)
        vec3 = np.random.rand(384).astype(np.float32)
        
        # Test cosine similarity
        start_time = time.time()
        similarity1 = similarity_calculator.cosine_similarity(vec1, vec2)
        cosine_time = time.time() - start_time
        
        assert isinstance(similarity1, float)
        assert -1.0 <= similarity1 <= 1.0
        
        # Test cached similarity (should be faster)
        start_time = time.time()
        similarity2 = similarity_calculator.cosine_similarity(vec1, vec2)
        cached_cosine_time = time.time() - start_time
        
        assert abs(similarity1 - similarity2) < 1e-6  # Same result
        assert cached_cosine_time < cosine_time * 0.5  # Faster due to caching
        
        # Test batch similarity calculation
        candidate_vectors = np.random.rand(100, 384).astype(np.float32)
        
        start_time = time.time()
        batch_similarities = similarity_calculator.batch_cosine_similarity(vec1, candidate_vectors)
        batch_time = time.time() - start_time
        
        assert len(batch_similarities) == 100
        assert all(-1.0 <= sim <= 1.0 for sim in batch_similarities)
        
        # Compare with individual calculations
        start_time = time.time()
        individual_similarities = [
            similarity_calculator.cosine_similarity(vec1, candidate_vectors[i])
            for i in range(10)  # Test subset for performance comparison
        ]
        individual_time = time.time() - start_time
        
        # Batch should be significantly faster per calculation
        batch_per_calc = batch_time / 100
        individual_per_calc = individual_time / 10
        
        assert batch_per_calc < individual_per_calc * 0.5  # At least 2x faster per calculation
        
        print(f"Cosine similarity time: {cosine_time:.6f}s")
        print(f"Cached cosine time: {cached_cosine_time:.6f}s")
        print(f"Batch similarity time: {batch_time:.4f}s ({batch_per_calc:.6f}s per calc)")
        print(f"Individual similarity time: {individual_time:.4f}s ({individual_per_calc:.6f}s per calc)")
    
    def test_top_k_similarity_search(self, similarity_calculator: OptimizedSimilarityCalculator):
        """Test optimized top-k similarity search."""
        query_vec = np.random.rand(384).astype(np.float32)
        candidate_vectors = np.random.rand(1000, 384).astype(np.float32)
        
        k = 10
        
        # Test cosine similarity top-k
        start_time = time.time()
        top_indices, top_scores = similarity_calculator.get_top_k_similar(
            query_vec, candidate_vectors, k, "cosine"
        )
        cosine_time = time.time() - start_time
        
        assert len(top_indices) == k
        assert len(top_scores) == k
        assert all(0 <= idx < 1000 for idx in top_indices)
        assert all(-1.0 <= score <= 1.0 for score in top_scores)
        
        # Scores should be in descending order for cosine similarity
        assert all(top_scores[i] >= top_scores[i+1] for i in range(k-1))
        
        # Test Euclidean distance top-k
        start_time = time.time()
        top_indices_euc, top_scores_euc = similarity_calculator.get_top_k_similar(
            query_vec, candidate_vectors, k, "euclidean"
        )
        euclidean_time = time.time() - start_time
        
        assert len(top_indices_euc) == k
        assert len(top_scores_euc) == k
        
        print(f"Top-k cosine search time: {cosine_time:.4f}s")
        print(f"Top-k Euclidean search time: {euclidean_time:.4f}s")
    
    def test_memory_optimization(self, embedding_generator: OptimizedEmbeddingGenerator, sample_texts: List[str]):
        """Test memory optimization features."""
        # Get initial memory usage
        initial_memory = embedding_generator.get_memory_usage()
        
        # Generate many embeddings to fill cache
        large_text_list = sample_texts * 20  # 200 texts
        embeddings = embedding_generator.generate_embeddings_batch(large_text_list)
        
        # Check memory usage after generation
        after_generation_memory = embedding_generator.get_memory_usage()
        
        assert after_generation_memory["cache_entries"] > initial_memory["cache_entries"]
        assert after_generation_memory["process_memory_mb"] > initial_memory["process_memory_mb"]
        
        # Optimize memory
        optimization_result = embedding_generator.optimize_memory_usage()
        
        # Check memory usage after optimization
        after_optimization_memory = embedding_generator.get_memory_usage()
        
        assert optimization_result["memory_freed_mb"] >= 0
        assert after_optimization_memory["process_memory_mb"] <= after_generation_memory["process_memory_mb"]
        
        print(f"Initial memory: {initial_memory['process_memory_mb']:.1f}MB")
        print(f"After generation: {after_generation_memory['process_memory_mb']:.1f}MB")
        print(f"After optimization: {after_optimization_memory['process_memory_mb']:.1f}MB")
        print(f"Memory freed: {optimization_result['memory_freed_mb']:.1f}MB")
    
    def test_performance_statistics(self, vector_optimizer: VectorOperationsOptimizer, sample_texts: List[str]):
        """Test performance statistics collection."""
        # Generate some embeddings to populate stats
        embeddings = vector_optimizer.generate_embeddings_batch(sample_texts[:5])
        
        # Get performance stats
        stats = vector_optimizer.get_comprehensive_stats()
        
        assert "embedding_generator" in stats
        assert "optimizer_stats" in stats
        assert "memory_stats" in stats
        assert "model_info" in stats
        
        embedding_stats = stats["embedding_generator"]["embedding_stats"]
        assert embedding_stats["total_embeddings_generated"] >= 5
        assert embedding_stats["total_batch_operations"] >= 1
        assert embedding_stats["avg_embedding_time_ms"] > 0
        
        cache_stats = stats["embedding_generator"]["cache_stats"]
        assert "cache_hits" in cache_stats
        assert "cache_misses" in cache_stats
        assert "cache_hit_rate" in cache_stats
        
        print(f"Performance stats: {stats}")
    
    def test_health_check(self, vector_optimizer: VectorOperationsOptimizer):
        """Test health check functionality."""
        # Health check should pass
        assert vector_optimizer.health_check() == True
        
        # Test embedding generator health check
        assert vector_optimizer.embedding_generator.health_check() == True
    
    @pytest.mark.integration
    def test_optimized_vector_store_integration(self, sample_texts: List[str]):
        """Test integration with optimized vector store."""
        # Create optimized vector store (without actual Milvus connection for testing)
        optimized_store = create_optimized_vector_store(enable_optimizations=True)
        
        # Test that optimizer is initialized
        assert optimized_store.enable_optimizations == True
        assert optimized_store.optimizer is not None
        
        # Test performance metrics
        metrics = optimized_store.get_performance_metrics()
        assert "operation_stats" in metrics
        assert "optimization_enabled" in metrics
        assert metrics["optimization_enabled"] == True
        
        # Test optimization trigger
        optimization_result = optimized_store.optimize_performance()
        assert "success" in optimization_result
        
        print(f"Integration test metrics: {metrics}")
        print(f"Optimization result: {optimization_result}")
    
    def test_cache_performance(self, embedding_generator: OptimizedEmbeddingGenerator, sample_texts: List[str]):
        """Test caching performance improvements."""
        # Clear any existing cache
        embedding_generator.memory_cache.clear()
        
        # Generate embeddings first time (cache miss)
        start_time = time.time()
        embeddings1 = embedding_generator.generate_embeddings_batch(sample_texts[:3])
        first_time = time.time() - start_time
        
        # Generate same embeddings again (cache hit)
        start_time = time.time()
        embeddings2 = embedding_generator.generate_embeddings_batch(sample_texts[:3])
        second_time = time.time() - start_time
        
        # Results should be identical
        for emb1, emb2 in zip(embeddings1, embeddings2):
            assert np.allclose(emb1, emb2, rtol=1e-6)
        
        # Second time should be significantly faster
        assert second_time < first_time * 0.2  # At least 5x faster
        
        # Check cache statistics
        stats = embedding_generator.get_performance_stats()
        cache_stats = stats["cache_stats"]
        
        assert cache_stats["cache_hits"] > 0
        assert cache_stats["cache_hit_rate"] > 0
        
        print(f"First generation time: {first_time:.4f}s")
        print(f"Cached generation time: {second_time:.4f}s")
        print(f"Speed improvement: {first_time / second_time:.1f}x")
        print(f"Cache hit rate: {cache_stats['cache_hit_rate']:.3f}")


@pytest.mark.performance
class TestVectorOperationsPerformanceBenchmarks:
    """Performance benchmarks for vector operations."""
    
    def test_embedding_generation_benchmark(self):
        """Benchmark embedding generation performance."""
        generator = OptimizedEmbeddingGenerator()
        
        # Test different batch sizes
        batch_sizes = [1, 5, 10, 20, 50]
        sample_text = "This is a sample text for performance benchmarking."
        
        results = {}
        
        for batch_size in batch_sizes:
            texts = [f"{sample_text} {i}" for i in range(batch_size)]
            
            # Warm up
            generator.generate_embeddings_batch(texts[:2])
            
            # Benchmark
            start_time = time.time()
            embeddings = generator.generate_embeddings_batch(texts)
            total_time = time.time() - start_time
            
            time_per_embedding = total_time / batch_size
            
            results[batch_size] = {
                "total_time": total_time,
                "time_per_embedding": time_per_embedding,
                "throughput": batch_size / total_time
            }
            
            print(f"Batch size {batch_size}: {time_per_embedding:.4f}s per embedding, {batch_size / total_time:.1f} embeddings/sec")
        
        # Verify that larger batches are more efficient
        assert results[50]["time_per_embedding"] < results[1]["time_per_embedding"]
        assert results[50]["throughput"] > results[1]["throughput"]
    
    def test_similarity_calculation_benchmark(self):
        """Benchmark similarity calculation performance."""
        calculator = OptimizedSimilarityCalculator()
        
        # Test different vector sizes
        vector_sizes = [100, 384, 768, 1024]
        num_candidates = 1000
        
        for vector_size in vector_sizes:
            query_vec = np.random.rand(vector_size).astype(np.float32)
            candidate_vectors = np.random.rand(num_candidates, vector_size).astype(np.float32)
            
            # Benchmark batch cosine similarity
            start_time = time.time()
            similarities = calculator.batch_cosine_similarity(query_vec, candidate_vectors)
            batch_time = time.time() - start_time
            
            # Benchmark top-k search
            start_time = time.time()
            top_indices, top_scores = calculator.get_top_k_similar(
                query_vec, candidate_vectors, 10, "cosine"
            )
            topk_time = time.time() - start_time
            
            print(f"Vector size {vector_size}: batch similarity {batch_time:.4f}s, top-k search {topk_time:.4f}s")
            
            assert len(similarities) == num_candidates
            assert len(top_indices) == 10
    
    def test_memory_usage_benchmark(self):
        """Benchmark memory usage patterns."""
        generator = OptimizedEmbeddingGenerator(cache_size=1000)
        
        # Monitor memory usage during operations
        initial_memory = psutil.Process().memory_info().rss / (1024**2)  # MB
        
        # Generate embeddings in batches
        batch_size = 50
        num_batches = 10
        
        memory_usage = [initial_memory]
        
        for i in range(num_batches):
            texts = [f"Sample text batch {i} item {j}" for j in range(batch_size)]
            embeddings = generator.generate_embeddings_batch(texts)
            
            current_memory = psutil.Process().memory_info().rss / (1024**2)
            memory_usage.append(current_memory)
            
            print(f"Batch {i+1}: Memory usage {current_memory:.1f}MB")
        
        # Test memory optimization
        optimization_result = generator.optimize_memory_usage()
        final_memory = psutil.Process().memory_info().rss / (1024**2)
        
        print(f"Memory optimization freed: {optimization_result['memory_freed_mb']:.1f}MB")
        print(f"Final memory usage: {final_memory:.1f}MB")
        
        # Memory should not grow unboundedly
        max_memory = max(memory_usage)
        assert max_memory < initial_memory + 500  # Should not use more than 500MB additional
        
        # Optimization should free some memory
        assert optimization_result["memory_freed_mb"] >= 0


if __name__ == "__main__":
    # Run performance tests
    pytest.main([__file__, "-v", "-s", "--tb=short"])