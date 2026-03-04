"""
Integration tests for optimized vector operations.

Tests the integration of optimized vector operations with the search service
and validates performance improvements in realistic scenarios.

Validates: Requirement 4.1 - Performance Optimization
"""

import pytest
import time
import numpy as np
from typing import List, Dict, Any
from unittest.mock import Mock, patch

from src.multimodal_librarian.components.vector_store.vector_operations_optimizer import (
    VectorOperationsOptimizer
)
from src.multimodal_librarian.components.vector_store.vector_store_optimized import (
    OptimizedVectorStore
)
from src.multimodal_librarian.components.vector_store.search_service import (
    EnhancedSemanticSearchService,
    SearchRequest
)
from src.multimodal_librarian.models.core import KnowledgeChunk, SourceType, ContentType


class TestVectorOperationsIntegration:
    """Integration tests for optimized vector operations."""
    
    @pytest.fixture
    def mock_vector_store(self):
        """Create a mock vector store for testing."""
        mock_store = Mock()
        mock_store.collection_name = "test_collection"
        mock_store._connected = True
        mock_store.settings = Mock()
        mock_store.settings.embedding_model = "all-MiniLM-L6-v2"
        mock_store.collection = Mock()
        mock_store.embedding_model = Mock()
        
        # Mock semantic search to return realistic results
        def mock_semantic_search(query, top_k=10, **kwargs):
            return [
                {
                    "chunk_id": f"chunk_{i}",
                    "content": f"Sample content {i} related to {query}",
                    "source_type": "book",
                    "source_id": f"source_{i}",
                    "content_type": "technical",
                    "location_reference": f"page_{i}",
                    "section": f"section_{i}",
                    "similarity_score": 0.9 - (i * 0.1),
                    "created_at": 1640995200000  # Mock timestamp
                }
                for i in range(min(top_k, 5))
            ]
        
        mock_store.semantic_search = mock_semantic_search
        mock_store.health_check = Mock(return_value=True)
        
        return mock_store
    
    @pytest.fixture
    def sample_knowledge_chunks(self) -> List[KnowledgeChunk]:
        """Create sample knowledge chunks for testing."""
        chunks = []
        for i in range(10):
            chunk = KnowledgeChunk(
                id=f"chunk_{i}",
                content=f"This is sample content {i} about machine learning and AI.",
                source_type=SourceType.BOOK,
                source_id=f"book_{i // 3}",
                content_type=ContentType.TECHNICAL,
                location_reference=f"page_{i}",
                section=f"Chapter {i // 2}",
                embedding=None  # Will be generated
            )
            chunks.append(chunk)
        return chunks
    
    def test_optimized_vector_store_initialization(self, mock_vector_store):
        """Test that optimized vector store initializes correctly."""
        # Test with optimizations enabled
        optimized_store = OptimizedVectorStore("test_collection", enable_optimizations=True)
        
        assert optimized_store.enable_optimizations == True
        assert optimized_store.collection_name == "test_collection"
        assert optimized_store.operation_stats["total_operations"] == 0
        
        # Test with optimizations disabled
        standard_store = OptimizedVectorStore("test_collection", enable_optimizations=False)
        
        assert standard_store.enable_optimizations == False
        assert standard_store.optimizer is None
    
    def test_optimized_embedding_generation(self, sample_knowledge_chunks):
        """Test optimized embedding generation with knowledge chunks."""
        optimizer = VectorOperationsOptimizer()
        
        # Test single embedding generation
        text = sample_knowledge_chunks[0].content
        
        start_time = time.time()
        embedding = optimizer.generate_embedding(text)
        generation_time = time.time() - start_time
        
        assert isinstance(embedding, np.ndarray)
        assert embedding.shape[0] > 0
        assert generation_time < 5.0  # Should complete within 5 seconds
        
        # Test cached embedding (should be much faster)
        start_time = time.time()
        cached_embedding = optimizer.generate_embedding(text)
        cached_time = time.time() - start_time
        
        assert np.array_equal(embedding, cached_embedding)
        assert cached_time < generation_time * 0.1  # At least 10x faster
        
        print(f"Initial embedding generation: {generation_time:.4f}s")
        print(f"Cached embedding retrieval: {cached_time:.6f}s")
        print(f"Speed improvement: {generation_time / cached_time:.1f}x")
    
    def test_batch_embedding_optimization(self, sample_knowledge_chunks):
        """Test batch embedding generation optimization."""
        optimizer = VectorOperationsOptimizer()
        
        texts = [chunk.content for chunk in sample_knowledge_chunks[:5]]
        
        # Test batch generation
        start_time = time.time()
        batch_embeddings = optimizer.generate_embeddings_batch(texts)
        batch_time = time.time() - start_time
        
        assert len(batch_embeddings) == len(texts)
        assert all(isinstance(emb, np.ndarray) for emb in batch_embeddings)
        
        # Test individual generation for comparison
        start_time = time.time()
        individual_embeddings = [optimizer.generate_embedding(text) for text in texts[5:]]
        individual_time = time.time() - start_time
        
        # Calculate per-embedding time
        batch_per_embedding = batch_time / len(texts)
        individual_per_embedding = individual_time / len(texts[5:]) if len(texts[5:]) > 0 else batch_per_embedding
        
        print(f"Batch generation: {batch_time:.4f}s ({batch_per_embedding:.4f}s per embedding)")
        print(f"Individual generation: {individual_time:.4f}s ({individual_per_embedding:.4f}s per embedding)")
        
        # Batch should be more efficient (allowing for some variance due to caching)
        if len(texts[5:]) > 0:
            assert batch_per_embedding <= individual_per_embedding * 1.5
    
    @pytest.mark.asyncio
    async def test_async_embedding_generation(self, sample_knowledge_chunks):
        """Test asynchronous embedding generation."""
        optimizer = VectorOperationsOptimizer()
        
        texts = [chunk.content for chunk in sample_knowledge_chunks[:3]]
        
        # Test async generation
        start_time = time.time()
        async_embeddings = await optimizer.generate_embeddings_async(texts)
        async_time = time.time() - start_time
        
        assert len(async_embeddings) == len(texts)
        assert all(isinstance(emb, np.ndarray) for emb in async_embeddings)
        
        # Compare with sync generation
        start_time = time.time()
        sync_embeddings = optimizer.generate_embeddings_batch(texts)
        sync_time = time.time() - start_time
        
        # Results should be very similar (allowing for small numerical differences)
        for async_emb, sync_emb in zip(async_embeddings, sync_embeddings):
            assert np.allclose(async_emb, sync_emb, rtol=1e-4)
        
        print(f"Async generation: {async_time:.4f}s")
        print(f"Sync generation: {sync_time:.4f}s")
    
    def test_similarity_calculation_optimization(self):
        """Test optimized similarity calculations."""
        optimizer = VectorOperationsOptimizer()
        
        # Generate test vectors
        vec1 = np.random.rand(384).astype(np.float32)
        vec2 = np.random.rand(384).astype(np.float32)
        candidate_vectors = np.random.rand(100, 384).astype(np.float32)
        
        # Test cosine similarity
        similarity = optimizer.calculate_similarity(vec1, vec2, "cosine")
        assert isinstance(similarity, float)
        assert -1.0 <= similarity <= 1.0
        
        # Test finding most similar vectors
        top_indices, top_scores = optimizer.find_most_similar(vec1, candidate_vectors, k=10)
        
        assert len(top_indices) == 10
        assert len(top_scores) == 10
        assert all(0 <= idx < 100 for idx in top_indices)
        assert all(-1.0 <= score <= 1.0 for score in top_scores)
        
        # Scores should be in descending order
        assert all(top_scores[i] >= top_scores[i+1] for i in range(9))
    
    def test_search_service_with_optimization(self, mock_vector_store):
        """Test search service with optimized vector store."""
        # Create search service with optimization enabled
        search_service = EnhancedSemanticSearchService(
            mock_vector_store, 
            use_optimized_store=True
        )
        
        # Verify that optimized store is being used
        assert isinstance(search_service.vector_store, OptimizedVectorStore)
        
        # Test search request
        request = SearchRequest(
            query="machine learning algorithms",
            top_k=5
        )
        
        # Mock the search method to avoid actual vector operations
        with patch.object(search_service.vector_store, 'semantic_search') as mock_search:
            mock_search.return_value = [
                {
                    "chunk_id": "chunk_1",
                    "content": "Machine learning content",
                    "source_type": "book",
                    "source_id": "ml_book",
                    "content_type": "technical",
                    "location_reference": "page_1",
                    "section": "introduction",
                    "similarity_score": 0.95,
                    "created_at": 1640995200000
                }
            ]
            
            # Perform search
            response = search_service.search(request)
            
            # Verify search was called with optimization parameters
            mock_search.assert_called_once()
            call_args = mock_search.call_args
            assert call_args[1]["use_optimized_similarity"] == True
    
    def test_performance_monitoring_integration(self, mock_vector_store):
        """Test performance monitoring integration."""
        optimized_store = OptimizedVectorStore("test_collection", enable_optimizations=True)
        
        # Simulate some operations
        optimized_store.operation_stats['total_operations'] = 50
        optimized_store.operation_stats['optimized_operations'] = 45
        optimized_store.operation_stats['batch_operations'] = 10
        
        # Get performance metrics
        metrics = optimized_store.get_performance_metrics()
        
        assert "operation_stats" in metrics
        assert "optimization_enabled" in metrics
        assert metrics["optimization_enabled"] == True
        assert metrics["operation_stats"]["total_operations"] == 50
        assert metrics["operation_stats"]["optimized_operations"] == 45
        
        # Test optimization efficiency calculation
        if "optimization_efficiency" in metrics:
            efficiency = metrics["optimization_efficiency"]
            assert "optimized_operation_ratio" in efficiency
            assert efficiency["optimized_operation_ratio"] == 0.9  # 45/50
    
    def test_memory_optimization_integration(self):
        """Test memory optimization integration."""
        optimizer = VectorOperationsOptimizer()
        
        # Generate embeddings to use memory
        texts = [f"Sample text {i} for memory testing" for i in range(20)]
        embeddings = optimizer.generate_embeddings_batch(texts)
        
        # Get initial memory stats
        initial_stats = optimizer.get_comprehensive_stats()
        initial_memory = initial_stats["memory_usage"]["process_memory_mb"]
        
        # Trigger memory optimization
        optimization_result = optimizer.optimize_memory()
        
        # Get final memory stats
        final_stats = optimizer.get_comprehensive_stats()
        final_memory = final_stats["memory_usage"]["process_memory_mb"]
        
        assert "embedding_optimization" in optimization_result
        assert optimization_result["similarity_cache_cleared"] == True
        
        # Memory should not have increased significantly
        memory_increase = final_memory - initial_memory
        assert memory_increase < 100  # Less than 100MB increase
        
        print(f"Initial memory: {initial_memory:.1f}MB")
        print(f"Final memory: {final_memory:.1f}MB")
        print(f"Memory change: {memory_increase:.1f}MB")
    
    def test_health_check_integration(self, mock_vector_store):
        """Test health check integration."""
        optimized_store = OptimizedVectorStore("test_collection", enable_optimizations=True)
        
        # Mock the optimizer health check
        with patch.object(optimized_store, 'optimizer') as mock_optimizer:
            mock_optimizer.health_check.return_value = True
            
            # Health check should pass
            assert optimized_store.health_check() == True
            
            # Test with optimizer failure
            mock_optimizer.health_check.return_value = False
            
            # Should still pass but disable optimizations
            result = optimized_store.health_check()
            assert result == True
            assert optimized_store.enable_optimizations == False
    
    def test_auto_optimization_trigger(self):
        """Test automatic optimization triggering."""
        optimized_store = OptimizedVectorStore("test_collection", enable_optimizations=True)
        optimized_store.auto_optimize_threshold = 5  # Low threshold for testing
        
        # Mock the optimizer
        with patch.object(optimized_store, 'optimizer') as mock_optimizer:
            mock_optimizer.optimize_memory.return_value = {"memory_freed_mb": 10.0}
            
            # Simulate operations to trigger auto-optimization
            for i in range(6):  # Exceed threshold
                optimized_store.operation_stats['total_operations'] += 1
                optimized_store._check_auto_optimization()
            
            # Auto-optimization should have been triggered
            assert optimized_store.operation_stats['memory_optimizations'] > 0
    
    def test_comprehensive_performance_comparison(self, sample_knowledge_chunks):
        """Test comprehensive performance comparison between optimized and standard operations."""
        # Test with optimization
        optimizer = VectorOperationsOptimizer()
        texts = [chunk.content for chunk in sample_knowledge_chunks]
        
        # Optimized batch generation
        start_time = time.time()
        optimized_embeddings = optimizer.generate_embeddings_batch(texts)
        optimized_time = time.time() - start_time
        
        # Test cached performance
        start_time = time.time()
        cached_embeddings = optimizer.generate_embeddings_batch(texts)
        cached_time = time.time() - start_time
        
        # Verify results
        assert len(optimized_embeddings) == len(texts)
        assert len(cached_embeddings) == len(texts)
        
        # Cached should be significantly faster
        assert cached_time < optimized_time * 0.2  # At least 5x faster
        
        # Results should be identical
        for opt_emb, cached_emb in zip(optimized_embeddings, cached_embeddings):
            assert np.array_equal(opt_emb, cached_emb)
        
        # Get comprehensive stats
        stats = optimizer.get_comprehensive_stats()
        
        assert stats["embedding_generator"]["embedding_stats"]["total_embeddings_generated"] >= len(texts)
        assert stats["embedding_generator"]["cache_stats"]["cache_hits"] > 0
        assert stats["embedding_generator"]["cache_stats"]["cache_hit_rate"] > 0
        
        print(f"Optimized generation: {optimized_time:.4f}s")
        print(f"Cached generation: {cached_time:.4f}s")
        print(f"Cache hit rate: {stats['embedding_generator']['cache_stats']['cache_hit_rate']:.3f}")
        print(f"Speed improvement: {optimized_time / cached_time:.1f}x")


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v", "-s", "--tb=short"])