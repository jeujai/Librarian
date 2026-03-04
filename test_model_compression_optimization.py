#!/usr/bin/env python3
"""
Test script for model compression and optimization functionality.

This script tests the enhanced model compression and optimization features
added to the OptimizedModelLoader.
"""

import asyncio
import logging
import numpy as np
import tempfile
import os
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import the modules we're testing
from src.multimodal_librarian.models.loader_optimized import (
    ModelCompressor, ModelOptimizer, CompressionLevel, CompressionMethod,
    OptimizationStrategy, OptimizedModelLoader
)
from src.multimodal_librarian.models.model_manager import ModelConfig, ModelPriority


async def test_model_compressor():
    """Test the ModelCompressor functionality."""
    logger.info("Testing ModelCompressor...")
    
    compressor = ModelCompressor()
    
    # Test data
    test_data = {
        "weights": np.random.randn(1000, 500).astype(np.float32),
        "biases": np.random.randn(500).astype(np.float32),
        "config": {
            "vocab_size": 50000,
            "hidden_size": 768,
            "num_layers": 12
        },
        "metadata": {
            "model_name": "test_model",
            "version": "1.0",
            "created_at": datetime.now().isoformat()
        }
    }
    
    # Test different compression methods
    methods_to_test = [
        CompressionMethod.GZIP,
        CompressionMethod.LZMA,
        CompressionMethod.ZLIB,
        CompressionMethod.PICKLE_GZIP
    ]
    
    for method in methods_to_test:
        logger.info(f"Testing compression method: {method.value}")
        
        # Test compression
        compressed_data, compression_result = await compressor.compress_model_data(
            test_data, method, CompressionLevel.MEDIUM
        )
        
        logger.info(f"Compression result: {compression_result.compression_ratio:.2f}x ratio, "
                   f"{compression_result.original_size_mb:.2f}MB -> {compression_result.compressed_size_mb:.2f}MB")
        
        # Test decompression
        decompressed_data, decompression_time = await compressor.decompress_model_data(
            compressed_data, method, dict
        )
        
        logger.info(f"Decompression time: {decompression_time:.4f}s")
        
        # Verify data integrity
        assert isinstance(decompressed_data, dict)
        assert "weights" in decompressed_data
        assert "config" in decompressed_data
        
        logger.info(f"✓ {method.value} compression/decompression successful")
    
    # Test NumPy array compression
    logger.info("Testing NumPy array compression...")
    numpy_array = np.random.randn(2000, 1000).astype(np.float32)
    
    compressed_data, compression_result = await compressor.compress_model_data(
        numpy_array, CompressionMethod.NUMPY_COMPRESSED, CompressionLevel.AGGRESSIVE
    )
    
    decompressed_array, _ = await compressor.decompress_model_data(
        compressed_data, CompressionMethod.NUMPY_COMPRESSED, np.ndarray
    )
    
    logger.info(f"NumPy compression: {compression_result.compression_ratio:.2f}x ratio")
    logger.info(f"Array shape preserved: {numpy_array.shape} -> {decompressed_array.shape}")
    
    # Get compression stats
    stats = compressor.get_compression_stats()
    logger.info(f"Compression stats: {stats}")
    
    logger.info("✓ ModelCompressor tests passed")


async def test_model_optimizer():
    """Test the ModelOptimizer functionality."""
    logger.info("Testing ModelOptimizer...")
    
    optimizer = ModelOptimizer()
    
    # Test data with realistic model structure
    test_model = {
        "weights": np.random.randn(1000, 768).astype(np.float64),
        "embeddings": np.random.randn(50000, 768).astype(np.float32),
        "layer_weights": [
            np.random.randn(768, 3072).astype(np.float32) for _ in range(12)
        ],
        "config": {
            "vocab_size": 50000,
            "hidden_size": 768,
            "num_layers": 12,
            "attention_heads": 12
        },
        "metadata": {
            "parameters": 110000000,
            "model_type": "transformer"
        }
    }
    
    # Test different optimization strategies
    strategies_to_test = [
        OptimizationStrategy.QUANTIZATION,
        OptimizationStrategy.PRUNING,
        OptimizationStrategy.DISTILLATION,
        OptimizationStrategy.CACHING
    ]
    
    for strategy in strategies_to_test:
        logger.info(f"Testing optimization strategy: {strategy.value}")
        
        # Apply optimization
        optimized_model, optimization_result = await optimizer.optimize_model(
            test_model.copy(), strategy
        )
        
        logger.info(f"Optimization result: {optimization_result.optimization_ratio:.2f}x ratio, "
                   f"{optimization_result.memory_savings_mb:.2f}MB saved, "
                   f"{optimization_result.performance_impact_percent:.1f}% performance impact")
        
        # Verify optimization was applied
        assert optimized_model is not None
        
        if strategy == OptimizationStrategy.QUANTIZATION:
            # Check that float64 was converted to float32
            if "weights" in optimized_model:
                assert optimized_model["weights"].dtype == np.float32
        
        elif strategy == OptimizationStrategy.DISTILLATION:
            # Check that model was reduced in size
            if "embeddings" in optimized_model:
                original_shape = test_model["embeddings"].shape
                optimized_shape = optimized_model["embeddings"].shape
                assert optimized_shape[1] <= original_shape[1]  # Reduced dimensions
        
        elif strategy == OptimizationStrategy.CACHING:
            # Check that caching metadata was added
            assert optimized_model.get("_cache_optimized") is True
        
        logger.info(f"✓ {strategy.value} optimization successful")
    
    # Get optimization stats
    stats = optimizer.get_optimization_stats()
    logger.info(f"Optimization stats: {stats}")
    
    logger.info("✓ ModelOptimizer tests passed")


async def test_optimized_loader_integration():
    """Test the integration of compression and optimization in OptimizedModelLoader."""
    logger.info("Testing OptimizedModelLoader integration...")
    
    # Create a temporary directory for cache
    with tempfile.TemporaryDirectory() as temp_dir:
        loader = OptimizedModelLoader(max_parallel_loads=2)
        loader.compression_cache_dir = temp_dir
        
        await loader.start()
        
        try:
            # Create test model configs
            model_configs = {
                "test_model_1": ModelConfig(
                    name="test_model_1",
                    model_type="embedding",
                    estimated_memory_mb=500,
                    estimated_load_time_seconds=2,
                    priority=ModelPriority.ESSENTIAL,
                    required_for_capabilities=["text_embedding"],
                    dependencies=[]
                ),
                "test_model_2": ModelConfig(
                    name="test_model_2",
                    model_type="large_language_model",
                    estimated_memory_mb=2000,
                    estimated_load_time_seconds=5,
                    priority=ModelPriority.STANDARD,
                    required_for_capabilities=["text_generation"],
                    dependencies=[]
                )
            }
            
            # Load models with compression and optimization
            results = await loader.load_models_parallel(model_configs)
            
            logger.info(f"Loading results: {results}")
            
            # Check that models were loaded successfully
            assert all(results.values()), "Not all models loaded successfully"
            
            # Test compression of existing model
            compression_success = await loader.compress_existing_model(
                "test_model_1", CompressionLevel.MEDIUM, CompressionMethod.GZIP
            )
            assert compression_success, "Failed to compress existing model"
            
            # Test optimization of existing model
            optimization_success = await loader.optimize_existing_model(
                "test_model_2", OptimizationStrategy.QUANTIZATION
            )
            assert optimization_success, "Failed to optimize existing model"
            
            # Get compression info
            compression_info = await loader.get_model_compression_info("test_model_1")
            assert compression_info is not None, "Failed to get compression info"
            logger.info(f"Compression info: {compression_info}")
            
            # Get optimization info
            optimization_info = await loader.get_model_optimization_info("test_model_2")
            assert optimization_info is not None, "Failed to get optimization info"
            logger.info(f"Optimization info: {optimization_info}")
            
            # Get overall statistics
            stats = loader.get_optimization_statistics()
            logger.info(f"Loader statistics: {stats}")
            
            # Verify statistics
            assert stats["loading_stats"]["total_models_compressed"] > 0
            assert stats["loading_stats"]["total_models_optimized"] > 0
            assert stats["loading_stats"]["compression_saves_mb"] > 0
            assert stats["loading_stats"]["optimization_saves_mb"] > 0
            
            logger.info("✓ OptimizedModelLoader integration tests passed")
            
        finally:
            await loader.shutdown()


async def main():
    """Run all tests."""
    logger.info("Starting model compression and optimization tests...")
    
    try:
        await test_model_compressor()
        await test_model_optimizer()
        await test_optimized_loader_integration()
        
        logger.info("🎉 All tests passed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())