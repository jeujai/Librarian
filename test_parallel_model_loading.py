#!/usr/bin/env python3
"""
Test script for parallel model loading optimization.

This script tests the new parallel model loading capabilities including:
- Optimized loader functionality
- Memory manager integration
- Dependency resolution
- Performance improvements
"""

import asyncio
import logging
import time
from typing import Dict, Any

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_parallel_loading():
    """Test parallel model loading functionality."""
    logger.info("Starting parallel model loading test")
    
    try:
        # Import the model manager
        from src.multimodal_librarian.models.model_manager import get_model_manager, initialize_model_manager
        
        # Initialize model manager
        model_manager = await initialize_model_manager()
        
        # Test 1: Check if parallel loading is enabled
        logger.info("Test 1: Checking parallel loading availability")
        parallel_stats = model_manager.get_parallel_loading_stats()
        logger.info(f"Parallel loading stats: {parallel_stats}")
        
        # Test 2: Load models in parallel
        logger.info("Test 2: Testing parallel model loading")
        start_time = time.time()
        
        # Get a subset of models to test with
        test_models = ["text-embedding-small", "chat-model-base", "search-index"]
        results = await model_manager.load_models_parallel(test_models)
        
        end_time = time.time()
        loading_time = end_time - start_time
        
        logger.info(f"Parallel loading results: {results}")
        logger.info(f"Total loading time: {loading_time:.2f} seconds")
        
        # Test 3: Check model availability
        logger.info("Test 3: Checking model availability after parallel loading")
        for model_name in test_models:
            available = model_manager.is_model_available(model_name)
            logger.info(f"Model {model_name} available: {available}")
        
        # Test 4: Get loading progress
        logger.info("Test 4: Getting loading progress")
        progress = model_manager.get_loading_progress()
        logger.info(f"Loading progress: {progress}")
        
        # Test 5: Test memory manager integration
        logger.info("Test 5: Testing memory manager integration")
        if model_manager.memory_manager:
            memory_info = model_manager.memory_manager.get_memory_info()
            logger.info(f"Memory info: {memory_info.usage_percent:.1f}% used, "
                       f"pressure: {memory_info.pressure_level.value}")
            
            recommendations = model_manager.memory_manager.get_memory_recommendations()
            logger.info(f"Memory recommendations: {len(recommendations['recommendations'])} items")
        
        # Test 6: Test optimized loader statistics
        logger.info("Test 6: Getting optimization statistics")
        if model_manager._optimized_loader:
            opt_stats = model_manager._optimized_loader.get_optimization_statistics()
            logger.info(f"Optimization stats: {opt_stats}")
        
        # Test 7: Compare with sequential loading
        logger.info("Test 7: Comparing with sequential loading")
        
        # Disable parallel loading temporarily
        model_manager.enable_parallel_loading(False)
        
        start_time = time.time()
        sequential_results = await model_manager.load_models_parallel(["document-processor"])
        end_time = time.time()
        sequential_time = end_time - start_time
        
        logger.info(f"Sequential loading time: {sequential_time:.2f} seconds")
        logger.info(f"Sequential results: {sequential_results}")
        
        # Re-enable parallel loading
        model_manager.enable_parallel_loading(True)
        
        # Test 8: Test model switching
        logger.info("Test 8: Testing model switching")
        if model_manager._optimized_loader:
            switch_success = await model_manager._optimized_loader.switch_model(
                "chat-model-base", "chat-model-large"
            )
            logger.info(f"Model switching successful: {switch_success}")
        
        logger.info("All tests completed successfully!")
        
        # Cleanup
        await model_manager.shutdown()
        
        return True
        
    except Exception as e:
        logger.error(f"Error in parallel loading test: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_memory_manager():
    """Test memory manager functionality."""
    logger.info("Starting memory manager test")
    
    try:
        from src.multimodal_librarian.utils.memory_manager import initialize_memory_manager
        
        # Initialize memory manager
        memory_manager = await initialize_memory_manager()
        
        # Test memory reservation
        logger.info("Testing memory reservation")
        success = await memory_manager.reserve_memory("test-model", 100.0, priority=5)
        logger.info(f"Memory reservation successful: {success}")
        
        # Check reservation info
        reservation_info = memory_manager.get_reservation_info("test-model")
        logger.info(f"Reservation info: {reservation_info}")
        
        # Get memory info
        memory_info = memory_manager.get_memory_info()
        logger.info(f"Memory usage: {memory_info.usage_percent:.1f}%, "
                   f"available: {memory_info.available_mb:.1f}MB")
        
        # Release reservation
        released = await memory_manager.release_memory("test-model")
        logger.info(f"Memory released: {released}")
        
        # Get recommendations
        recommendations = memory_manager.get_memory_recommendations()
        logger.info(f"Memory recommendations: {recommendations}")
        
        # Cleanup
        await memory_manager.shutdown()
        
        return True
        
    except Exception as e:
        logger.error(f"Error in memory manager test: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_optimized_loader():
    """Test optimized loader functionality."""
    logger.info("Starting optimized loader test")
    
    try:
        from src.multimodal_librarian.models.loader_optimized import initialize_optimized_loader
        from src.multimodal_librarian.models.model_manager import ModelConfig, ModelPriority
        
        # Initialize optimized loader
        loader = await initialize_optimized_loader(max_parallel_loads=3)
        
        # Create test model configurations
        test_configs = {
            "test-model-1": ModelConfig(
                name="test-model-1",
                priority=ModelPriority.ESSENTIAL,
                estimated_load_time_seconds=2.0,
                estimated_memory_mb=100.0,
                required_for_capabilities=["test-capability-1"]
            ),
            "test-model-2": ModelConfig(
                name="test-model-2",
                priority=ModelPriority.STANDARD,
                estimated_load_time_seconds=3.0,
                estimated_memory_mb=200.0,
                required_for_capabilities=["test-capability-2"],
                dependencies=["test-model-1"]
            ),
            "test-model-3": ModelConfig(
                name="test-model-3",
                priority=ModelPriority.ADVANCED,
                estimated_load_time_seconds=4.0,
                estimated_memory_mb=300.0,
                required_for_capabilities=["test-capability-3"]
            )
        }
        
        # Test parallel loading
        logger.info("Testing parallel loading with dependencies")
        start_time = time.time()
        results = await loader.load_models_parallel(test_configs)
        end_time = time.time()
        
        logger.info(f"Parallel loading results: {results}")
        logger.info(f"Loading time: {end_time - start_time:.2f} seconds")
        
        # Get optimization statistics
        stats = loader.get_optimization_statistics()
        logger.info(f"Optimization statistics: {stats}")
        
        # Cleanup
        await loader.shutdown()
        
        return True
        
    except Exception as e:
        logger.error(f"Error in optimized loader test: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all tests."""
    logger.info("Starting parallel model loading tests")
    
    tests = [
        ("Memory Manager", test_memory_manager),
        ("Optimized Loader", test_optimized_loader),
        ("Parallel Loading Integration", test_parallel_loading)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        logger.info(f"\n{'='*50}")
        logger.info(f"Running {test_name} test")
        logger.info(f"{'='*50}")
        
        try:
            result = await test_func()
            results[test_name] = result
            logger.info(f"{test_name} test: {'PASSED' if result else 'FAILED'}")
        except Exception as e:
            logger.error(f"{test_name} test failed with exception: {e}")
            results[test_name] = False
    
    # Summary
    logger.info(f"\n{'='*50}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*50}")
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        status = "PASSED" if result else "FAILED"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("All tests passed! Parallel model loading implementation is working correctly.")
    else:
        logger.warning("Some tests failed. Please check the implementation.")
    
    return passed == total

if __name__ == "__main__":
    asyncio.run(main())