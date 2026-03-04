#!/usr/bin/env python3
"""
Simple test for parallel model loading functionality.
"""

import asyncio
import logging
import time

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_parallel_loading_basic():
    """Test basic parallel loading functionality."""
    try:
        from src.multimodal_librarian.models.loader_optimized import OptimizedModelLoader
        from src.multimodal_librarian.models.model_manager import ModelConfig, ModelPriority
        from src.multimodal_librarian.utils.memory_manager import MemoryManager
        
        logger.info("Creating optimized loader and memory manager")
        
        # Create memory manager
        memory_manager = MemoryManager()
        await memory_manager.start()
        
        # Create optimized loader
        loader = OptimizedModelLoader(max_parallel_loads=2, memory_manager=memory_manager)
        await loader.start()
        
        # Create simple test configurations (no dependencies)
        test_configs = {
            "model-a": ModelConfig(
                name="model-a",
                priority=ModelPriority.ESSENTIAL,
                estimated_load_time_seconds=1.0,
                estimated_memory_mb=50.0,
                required_for_capabilities=["capability-a"]
            ),
            "model-b": ModelConfig(
                name="model-b", 
                priority=ModelPriority.ESSENTIAL,
                estimated_load_time_seconds=1.0,
                estimated_memory_mb=50.0,
                required_for_capabilities=["capability-b"]
            )
        }
        
        logger.info("Starting parallel loading test")
        start_time = time.time()
        
        # Test parallel loading
        results = await loader.load_models_parallel(test_configs)
        
        end_time = time.time()
        loading_time = end_time - start_time
        
        logger.info(f"Loading completed in {loading_time:.2f} seconds")
        logger.info(f"Results: {results}")
        
        # Get statistics
        stats = loader.get_optimization_statistics()
        logger.info(f"Optimization stats: {stats}")
        
        # Cleanup
        await loader.shutdown()
        await memory_manager.shutdown()
        
        # Check if both models loaded successfully
        success = all(results.values())
        logger.info(f"Test {'PASSED' if success else 'FAILED'}")
        
        return success
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_dependency_resolution():
    """Test dependency resolution in parallel loading."""
    try:
        from src.multimodal_librarian.models.loader_optimized import OptimizedModelLoader
        from src.multimodal_librarian.models.model_manager import ModelConfig, ModelPriority
        
        logger.info("Testing dependency resolution")
        
        loader = OptimizedModelLoader(max_parallel_loads=2)
        
        # Create configs with dependencies
        test_configs = {
            "base-model": ModelConfig(
                name="base-model",
                priority=ModelPriority.ESSENTIAL,
                estimated_load_time_seconds=0.5,
                estimated_memory_mb=30.0,
                required_for_capabilities=["base"]
            ),
            "dependent-model": ModelConfig(
                name="dependent-model",
                priority=ModelPriority.STANDARD,
                estimated_load_time_seconds=0.5,
                estimated_memory_mb=40.0,
                required_for_capabilities=["advanced"],
                dependencies=["base-model"]
            )
        }
        
        # Build dependency graph
        loader.build_dependency_graph(test_configs)
        
        # Check dependency graph
        logger.info(f"Dependency graph: {loader.dependency_graph}")
        logger.info(f"Reverse dependencies: {loader.reverse_dependency_graph}")
        
        # Create loading jobs
        jobs = loader.create_loading_jobs(test_configs)
        
        # Check job priorities (dependent should have lower priority)
        base_priority = jobs["base-model"].priority
        dependent_priority = jobs["dependent-model"].priority
        
        logger.info(f"Base model priority: {base_priority}")
        logger.info(f"Dependent model priority: {dependent_priority}")
        
        # Base model should have higher priority (loads first)
        dependency_test_passed = base_priority > dependent_priority
        
        await loader.shutdown()
        
        logger.info(f"Dependency test {'PASSED' if dependency_test_passed else 'FAILED'}")
        return dependency_test_passed
        
    except Exception as e:
        logger.error(f"Dependency test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run simple parallel loading tests."""
    logger.info("Starting simple parallel loading tests")
    
    tests = [
        ("Basic Parallel Loading", test_parallel_loading_basic),
        ("Dependency Resolution", test_dependency_resolution)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        logger.info(f"\n{'='*40}")
        logger.info(f"Running {test_name}")
        logger.info(f"{'='*40}")
        
        try:
            result = await test_func()
            results[test_name] = result
        except Exception as e:
            logger.error(f"{test_name} failed: {e}")
            results[test_name] = False
    
    # Summary
    logger.info(f"\n{'='*40}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*40}")
    
    passed = sum(results.values())
    total = len(results)
    
    for test_name, result in results.items():
        status = "PASSED" if result else "FAILED"
        logger.info(f"{test_name}: {status}")
    
    logger.info(f"\nOverall: {passed}/{total} tests passed")
    
    return passed == total

if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)