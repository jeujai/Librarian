#!/usr/bin/env python3
"""
Test script for Milvus indexing and search optimization.

This script validates that the Milvus optimization features work correctly:
1. Dynamic index type selection based on collection size
2. Optimized search parameter calculation
3. Performance measurement and tuning
4. Memory usage optimization
5. Automatic optimization recommendations

Usage:
    pytest tests/performance/test_milvus_optimization.py -v
    python tests/performance/test_milvus_optimization.py
"""

import asyncio
import pytest
import time
import numpy as np
from typing import List, Dict, Any
import logging

# Add project root to path
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "src"))

# Test imports
from multimodal_librarian.clients.milvus_client import MilvusClient
from multimodal_librarian.config.local_config import LocalDatabaseConfig
from database.milvus.optimization_config import (
    MilvusOptimizationConfig, 
    IndexType, 
    get_recommended_index_params,
    get_recommended_search_params
)

logger = logging.getLogger(__name__)


class TestMilvusOptimization:
    """Test suite for Milvus optimization features."""
    
    @pytest.fixture
    async def milvus_client(self):
        """Create and connect Milvus client for testing."""
        config = LocalDatabaseConfig()
        client = MilvusClient(
            host=config.milvus_host,
            port=config.milvus_port,
            user=config.milvus_user,
            password=config.milvus_password
        )
        
        try:
            await client.connect()
            yield client
        finally:
            await client.disconnect()
    
    @pytest.fixture
    def test_collection_name(self):
        """Generate unique test collection name."""
        return f"test_optimization_{int(time.time())}"
    
    @pytest.fixture
    def sample_vectors(self):
        """Generate sample vectors for testing."""
        dimension = 384
        num_vectors = 1000
        
        vectors = []
        for i in range(num_vectors):
            vector = np.random.random(dimension).astype(np.float32).tolist()
            vectors.append({
                "id": f"test_vector_{i}",
                "vector": vector,
                "metadata": {
                    "content": f"Test content {i}",
                    "source_id": f"test_doc_{i // 100}",
                    "chunk_index": i % 100
                }
            })
        
        return vectors
    
    @pytest.mark.asyncio
    async def test_dynamic_index_selection(self, milvus_client, test_collection_name):
        """Test that index type is selected dynamically based on collection size."""
        # Create collection
        await milvus_client.create_collection(test_collection_name, 384)
        
        try:
            # Test small collection (should use FLAT)
            small_vectors = [
                {
                    "id": f"small_{i}",
                    "vector": np.random.random(384).astype(np.float32).tolist(),
                    "metadata": {"content": f"Small content {i}"}
                }
                for i in range(100)
            ]
            
            await milvus_client.insert_vectors(test_collection_name, small_vectors)
            
            # Create index (should auto-select FLAT for small collection)
            success = await milvus_client.create_index(test_collection_name, "vector")
            assert success, "Index creation should succeed"
            
            # Check index type
            index_info = await milvus_client.get_index_info(test_collection_name)
            assert len(index_info) > 0, "Index should be created"
            
            index_type = index_info[0]["index_type"]
            logger.info(f"Selected index type for small collection: {index_type}")
            
            # For small collections, should use FLAT or IVF_FLAT
            assert index_type in ["FLAT", "IVF_FLAT"], f"Unexpected index type: {index_type}"
            
        finally:
            # Cleanup
            await milvus_client.delete_collection(test_collection_name)
    
    @pytest.mark.asyncio
    async def test_optimized_search_parameters(self, milvus_client, test_collection_name):
        """Test that search parameters are optimized based on collection characteristics."""
        # Create collection with medium size
        await milvus_client.create_collection(test_collection_name, 384)
        
        try:
            # Insert medium-sized dataset
            medium_vectors = [
                {
                    "id": f"medium_{i}",
                    "vector": np.random.random(384).astype(np.float32).tolist(),
                    "metadata": {"content": f"Medium content {i}"}
                }
                for i in range(5000)
            ]
            
            await milvus_client.insert_vectors(test_collection_name, medium_vectors)
            
            # Create index
            await milvus_client.create_index(test_collection_name, "vector")
            
            # Test optimized search parameters for different k values
            test_cases = [
                {"k": 5, "expected_min_nprobe": 5},
                {"k": 20, "expected_min_nprobe": 10},
                {"k": 100, "expected_min_nprobe": 20}
            ]
            
            for case in test_cases:
                k = case["k"]
                search_params = await milvus_client._get_optimized_search_params(
                    test_collection_name, k
                )
                
                logger.info(f"Search params for k={k}: {search_params}")
                
                assert "params" in search_params, "Search params should contain 'params'"
                
                # Check that nprobe is reasonable for the k value
                if "nprobe" in search_params["params"]:
                    nprobe = search_params["params"]["nprobe"]
                    assert nprobe >= case["expected_min_nprobe"], \
                        f"nprobe {nprobe} should be >= {case['expected_min_nprobe']} for k={k}"
                    assert nprobe <= 1000, f"nprobe {nprobe} should be reasonable"
        
        finally:
            # Cleanup
            await milvus_client.delete_collection(test_collection_name)
    
    @pytest.mark.asyncio
    async def test_performance_measurement(self, milvus_client, test_collection_name):
        """Test that performance measurement works correctly."""
        # Create collection
        await milvus_client.create_collection(test_collection_name, 384)
        
        try:
            # Insert test data
            test_vectors = [
                {
                    "id": f"perf_{i}",
                    "vector": np.random.random(384).astype(np.float32).tolist(),
                    "metadata": {"content": f"Performance test content {i}"}
                }
                for i in range(1000)
            ]
            
            await milvus_client.insert_vectors(test_collection_name, test_vectors)
            await milvus_client.create_index(test_collection_name, "vector")
            
            # Generate test queries
            test_queries = await milvus_client._generate_test_queries(test_collection_name, 5)
            assert len(test_queries) > 0, "Should generate test queries"
            assert len(test_queries[0]) == 384, "Query vectors should have correct dimension"
            
            # Measure performance
            performance = await milvus_client._measure_search_performance(
                test_collection_name, test_queries
            )
            
            logger.info(f"Performance measurement: {performance}")
            
            # Validate performance metrics
            assert "avg_latency_ms" in performance, "Should measure average latency"
            assert "p95_latency_ms" in performance, "Should measure P95 latency"
            assert "num_queries" in performance, "Should report number of queries"
            
            assert performance["avg_latency_ms"] > 0, "Average latency should be positive"
            assert performance["avg_latency_ms"] < 10000, "Average latency should be reasonable"
            assert performance["num_queries"] == len(test_queries), "Should test all queries"
        
        finally:
            # Cleanup
            await milvus_client.delete_collection(test_collection_name)
    
    @pytest.mark.asyncio
    async def test_optimization_recommendations(self, milvus_client, test_collection_name):
        """Test that optimization recommendations are generated correctly."""
        # Create collection
        await milvus_client.create_collection(test_collection_name, 384)
        
        try:
            # Test recommendations for empty collection
            empty_recommendations = await milvus_client.get_optimization_recommendations(
                test_collection_name
            )
            
            logger.info(f"Empty collection recommendations: {empty_recommendations}")
            
            assert "recommendations" in empty_recommendations
            assert len(empty_recommendations["recommendations"]) > 0
            
            # Should recommend creating an index
            has_index_recommendation = any(
                rec["type"] == "create_index" 
                for rec in empty_recommendations["recommendations"]
            )
            assert has_index_recommendation, "Should recommend creating index for empty collection"
            
            # Insert some data
            test_vectors = [
                {
                    "id": f"rec_{i}",
                    "vector": np.random.random(384).astype(np.float32).tolist(),
                    "metadata": {"content": f"Recommendation test content {i}"}
                }
                for i in range(500)
            ]
            
            await milvus_client.insert_vectors(test_collection_name, test_vectors)
            
            # Test recommendations for collection with data but no index
            no_index_recommendations = await milvus_client.get_optimization_recommendations(
                test_collection_name
            )
            
            logger.info(f"No index recommendations: {no_index_recommendations}")
            
            # Should still recommend creating an index
            has_index_recommendation = any(
                rec["type"] == "create_index" 
                for rec in no_index_recommendations["recommendations"]
            )
            assert has_index_recommendation, "Should recommend creating index"
            
            # Create index
            await milvus_client.create_index(test_collection_name, "vector")
            
            # Test recommendations for optimized collection
            optimized_recommendations = await milvus_client.get_optimization_recommendations(
                test_collection_name
            )
            
            logger.info(f"Optimized recommendations: {optimized_recommendations}")
            
            # Should have fewer high-priority recommendations
            high_priority_count = sum(
                1 for rec in optimized_recommendations["recommendations"]
                if rec.get("priority") == "high"
            )
            
            assert high_priority_count == 0, "Optimized collection should have no high-priority recommendations"
        
        finally:
            # Cleanup
            await milvus_client.delete_collection(test_collection_name)
    
    def test_optimization_config_selection(self):
        """Test the optimization configuration selection logic."""
        # Test small collection
        small_config = MilvusOptimizationConfig.get_optimal_index_config(
            vector_count=1000, dimension=384
        )
        assert small_config.index_type == IndexType.FLAT, "Small collections should use FLAT"
        
        # Test medium collection
        medium_config = MilvusOptimizationConfig.get_optimal_index_config(
            vector_count=50000, dimension=384
        )
        assert medium_config.index_type == IndexType.IVF_FLAT, "Medium collections should use IVF_FLAT"
        
        # Test large collection
        large_config = MilvusOptimizationConfig.get_optimal_index_config(
            vector_count=500000, dimension=384
        )
        assert large_config.index_type == IndexType.HNSW, "Large collections should use HNSW"
        
        # Test memory-constrained selection
        memory_config = MilvusOptimizationConfig.get_optimal_index_config(
            vector_count=100000, dimension=384, memory_limit_mb=1024, priority="memory"
        )
        # Should prefer memory-efficient options
        assert memory_config.memory_multiplier <= 1.0, "Memory-constrained config should be efficient"
        
        # Test speed-prioritized selection
        speed_config = MilvusOptimizationConfig.get_optimal_index_config(
            vector_count=100000, dimension=384, priority="speed"
        )
        assert speed_config.search_speed in ["medium", "fast"], "Speed config should prioritize fast search"
    
    def test_search_parameter_optimization(self):
        """Test search parameter optimization logic."""
        # Test IVF_FLAT parameters
        ivf_params = get_recommended_search_params("IVF_FLAT", k=10, preference="balanced")
        assert "params" in ivf_params
        assert "nprobe" in ivf_params["params"]
        assert ivf_params["params"]["nprobe"] > 0
        
        # Test HNSW parameters
        hnsw_params = get_recommended_search_params("HNSW", k=20, preference="accuracy")
        assert "params" in hnsw_params
        if "ef" in hnsw_params["params"]:
            assert hnsw_params["params"]["ef"] >= 20  # Should be at least k
        
        # Test parameter scaling with k
        small_k_params = get_recommended_search_params("IVF_FLAT", k=5)
        large_k_params = get_recommended_search_params("IVF_FLAT", k=50)
        
        if "nprobe" in small_k_params["params"] and "nprobe" in large_k_params["params"]:
            assert (large_k_params["params"]["nprobe"] >= 
                   small_k_params["params"]["nprobe"]), "nprobe should scale with k"
    
    def test_memory_estimation(self):
        """Test memory usage estimation."""
        config = MilvusOptimizationConfig.get_optimal_index_config(10000, 384)
        
        memory_est = MilvusOptimizationConfig.estimate_memory_usage(
            vector_count=10000,
            dimension=384,
            index_config=config
        )
        
        assert "base_vectors_mb" in memory_est
        assert "total_estimated_mb" in memory_est
        assert memory_est["base_vectors_mb"] > 0
        assert memory_est["total_estimated_mb"] >= memory_est["base_vectors_mb"]
        
        # Rough sanity check: 10K vectors * 384 dims * 4 bytes ≈ 15MB
        expected_base = 10000 * 384 * 4 / (1024 * 1024)
        assert abs(memory_est["base_vectors_mb"] - expected_base) < 1.0, \
            "Memory estimation should be approximately correct"
    
    def test_performance_recommendations(self):
        """Test performance recommendation generation."""
        # Test recommendations for collection without index
        recommendations = MilvusOptimizationConfig.get_performance_recommendations(
            vector_count=10000,
            dimension=384,
            current_index_type=None
        )
        
        assert len(recommendations) > 0, "Should generate recommendations"
        
        # Should recommend creating an index
        has_create_index = any(rec["type"] == "create_index" for rec in recommendations)
        assert has_create_index, "Should recommend creating index"
        
        # Test recommendations for high latency
        high_latency_recommendations = MilvusOptimizationConfig.get_performance_recommendations(
            vector_count=10000,
            dimension=384,
            current_index_type="IVF_FLAT",
            avg_search_latency_ms=500.0
        )
        
        # Should recommend optimizing search parameters
        has_optimize_params = any(
            rec["type"] == "optimize_search_params" 
            for rec in high_latency_recommendations
        )
        assert has_optimize_params, "Should recommend optimizing search parameters for high latency"
        
        # Test recommendations for high memory usage
        high_memory_recommendations = MilvusOptimizationConfig.get_performance_recommendations(
            vector_count=10000,
            dimension=384,
            current_index_type="IVF_FLAT",
            memory_usage_mb=3000.0
        )
        
        # Should recommend memory optimization
        has_memory_opt = any(
            rec["type"] == "reduce_memory" 
            for rec in high_memory_recommendations
        )
        assert has_memory_opt, "Should recommend memory optimization for high usage"


async def run_integration_test():
    """Run integration test with real Milvus instance."""
    print("Running Milvus optimization integration test...")
    
    try:
        config = LocalDatabaseConfig()
        
        async with MilvusClient(
            host=config.milvus_host,
            port=config.milvus_port,
            user=config.milvus_user,
            password=config.milvus_password
        ) as client:
            
            test_collection = f"integration_test_{int(time.time())}"
            
            try:
                print(f"Creating test collection: {test_collection}")
                await client.create_collection(test_collection, 384)
                
                # Insert test data
                print("Inserting test vectors...")
                test_vectors = [
                    {
                        "id": f"integration_{i}",
                        "vector": np.random.random(384).astype(np.float32).tolist(),
                        "metadata": {"content": f"Integration test content {i}"}
                    }
                    for i in range(2000)
                ]
                
                await client.insert_vectors(test_collection, test_vectors)
                
                # Test optimization
                print("Running optimization...")
                await client.optimize_collection(test_collection)
                
                # Test search performance optimization
                print("Testing search performance optimization...")
                optimization_results = await client.optimize_search_performance(
                    test_collection,
                    target_latency_ms=50.0,
                    accuracy_threshold=0.9
                )
                
                print(f"Optimization results: {optimization_results}")
                
                # Test recommendations
                print("Getting optimization recommendations...")
                recommendations = await client.get_optimization_recommendations(test_collection)
                print(f"Recommendations: {len(recommendations['recommendations'])} items")
                
                # Test search with optimized parameters
                print("Testing optimized search...")
                query_vector = np.random.random(384).astype(np.float32).tolist()
                results = await client.search_vectors(test_collection, query_vector, k=10)
                
                print(f"Search returned {len(results)} results")
                
                print("✓ Integration test completed successfully")
                
            finally:
                # Cleanup
                try:
                    await client.delete_collection(test_collection)
                    print(f"Cleaned up test collection: {test_collection}")
                except:
                    pass
    
    except Exception as e:
        print(f"✗ Integration test failed: {e}")
        raise


if __name__ == "__main__":
    # Run integration test
    asyncio.run(run_integration_test())