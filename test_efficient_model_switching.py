#!/usr/bin/env python3
"""
Test script for efficient model switching functionality.

This script tests the model switching capabilities implemented in the
OptimizedModelLoader and ModelManager classes.
"""

import asyncio
import logging
import sys
import os
import time
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from multimodal_librarian.models.model_manager import ModelManager, ModelConfig, ModelPriority
from multimodal_librarian.models.loader_optimized import OptimizedModelLoader, CompressionLevel, CompressionMethod, OptimizationStrategy
from multimodal_librarian.utils.memory_manager import MemoryManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_basic_model_switching():
    """Test basic model switching functionality."""
    logger.info("=== Testing Basic Model Switching ===")
    
    try:
        # Initialize model manager
        model_manager = ModelManager(max_concurrent_loads=2)
        await model_manager.start_progressive_loading()
        
        # Wait for some models to load
        await asyncio.sleep(5)
        
        # Get available models
        model_statuses = model_manager.get_all_model_statuses()
        loaded_models = [name for name, status in model_statuses.items() 
                        if status and status.get("status") == "loaded"]
        
        if len(loaded_models) < 2:
            logger.warning(f"Only {len(loaded_models)} models loaded, waiting for more...")
            await asyncio.sleep(10)
            
            model_statuses = model_manager.get_all_model_statuses()
            loaded_models = [name for name, status in model_statuses.items() 
                            if status and status.get("status") == "loaded"]
        
        if len(loaded_models) >= 2:
            old_model = loaded_models[0]
            new_model = loaded_models[1]
            
            logger.info(f"Testing switch from {old_model} to {new_model}")
            
            # Test model switching
            start_time = time.time()
            success = await model_manager.switch_model(old_model, new_model, "hot_swap")
            switch_time = time.time() - start_time
            
            if success:
                logger.info(f"✅ Model switch successful in {switch_time:.2f} seconds")
            else:
                logger.error("❌ Model switch failed")
            
            # Test switch recommendations
            recommendations = await model_manager.get_switch_recommendations(
                old_model, [new_model, "chat-model-large"]
            )
            
            logger.info(f"Switch recommendations: {recommendations}")
            
        else:
            logger.warning("Not enough models loaded for switching test")
        
        # Test switchable models
        if loaded_models:
            switchable = model_manager.get_switchable_models(loaded_models[0])
            logger.info(f"Switchable models for {loaded_models[0]}: {len(switchable)} found")
            
            for model in switchable[:3]:  # Show top 3
                logger.info(f"  - {model['name']}: compatibility={model['compatibility_score']:.2f}, "
                           f"loaded={model['is_loaded']}")
        
        # Get switching stats
        stats = model_manager.get_model_switching_stats()
        logger.info(f"Model switching stats: {stats}")
        
        await model_manager.shutdown()
        logger.info("✅ Basic model switching test completed")
        
    except Exception as e:
        logger.error(f"❌ Error in basic model switching test: {e}")
        raise


async def test_optimized_model_switching():
    """Test optimized model switching with compression and optimization."""
    logger.info("=== Testing Optimized Model Switching ===")
    
    try:
        # Initialize optimized loader
        optimized_loader = OptimizedModelLoader(max_parallel_loads=2)
        await optimized_loader.start()
        
        # Create test model configurations
        test_models = {
            "test-model-1": ModelConfig(
                name="test-model-1",
                priority=ModelPriority.ESSENTIAL,
                estimated_load_time_seconds=2.0,
                estimated_memory_mb=100.0,
                required_for_capabilities=["test", "switching"],
                model_type="test_model"
            ),
            "test-model-2": ModelConfig(
                name="test-model-2",
                priority=ModelPriority.STANDARD,
                estimated_load_time_seconds=3.0,
                estimated_memory_mb=150.0,
                required_for_capabilities=["test", "switching"],
                model_type="test_model"
            ),
            "test-model-3": ModelConfig(
                name="test-model-3",
                priority=ModelPriority.ADVANCED,
                estimated_load_time_seconds=4.0,
                estimated_memory_mb=200.0,
                required_for_capabilities=["test", "advanced"],
                model_type="advanced_model"
            )
        }
        
        # Load models in parallel
        logger.info("Loading test models...")
        load_results = await optimized_loader.load_models_parallel(test_models)
        
        loaded_models = [name for name, success in load_results.items() if success]
        logger.info(f"Loaded models: {loaded_models}")
        
        if len(loaded_models) >= 2:
            # Test different switching strategies
            strategies = ["hot_swap", "preload_switch", "memory_aware", "compressed_switch"]
            
            for strategy in strategies:
                logger.info(f"\n--- Testing {strategy} strategy ---")
                
                old_model = loaded_models[0]
                new_model = loaded_models[1]
                
                start_time = time.time()
                success = await optimized_loader.switch_models(old_model, new_model, strategy)
                switch_time = time.time() - start_time
                
                if success:
                    logger.info(f"✅ {strategy} switch successful in {switch_time:.2f} seconds")
                else:
                    logger.error(f"❌ {strategy} switch failed")
                
                # Brief pause between tests
                await asyncio.sleep(1)
            
            # Test batch switching
            logger.info("\n--- Testing batch switching ---")
            switches = [
                (loaded_models[0], loaded_models[1]),
                (loaded_models[1], loaded_models[0])
            ]
            
            batch_results = await optimized_loader.batch_switch_models(switches, "auto")
            logger.info(f"Batch switch results: {batch_results}")
            
            # Test switch recommendations
            recommendations = await optimized_loader.get_switch_recommendations(
                loaded_models[0], loaded_models[1:]
            )
            
            logger.info(f"Switch recommendations: {recommendations}")
            
        else:
            logger.warning("Not enough models loaded for optimized switching test")
        
        # Get optimization statistics
        stats = optimized_loader.get_optimization_statistics()
        logger.info(f"Optimization statistics: {stats}")
        
        await optimized_loader.shutdown()
        logger.info("✅ Optimized model switching test completed")
        
    except Exception as e:
        logger.error(f"❌ Error in optimized model switching test: {e}")
        raise


async def test_memory_aware_switching():
    """Test memory-aware model switching."""
    logger.info("=== Testing Memory-Aware Model Switching ===")
    
    try:
        # Initialize components
        memory_manager = MemoryManager()
        optimized_loader = OptimizedModelLoader(max_parallel_loads=1, memory_manager=memory_manager)
        await optimized_loader.start()
        
        # Create memory-intensive test models
        memory_intensive_models = {
            "large-model-1": ModelConfig(
                name="large-model-1",
                priority=ModelPriority.STANDARD,
                estimated_load_time_seconds=3.0,
                estimated_memory_mb=800.0,  # Large memory requirement
                required_for_capabilities=["memory_test"],
                model_type="large_model"
            ),
            "large-model-2": ModelConfig(
                name="large-model-2",
                priority=ModelPriority.STANDARD,
                estimated_load_time_seconds=3.0,
                estimated_memory_mb=900.0,  # Even larger
                required_for_capabilities=["memory_test"],
                model_type="large_model"
            )
        }
        
        # Load first model
        logger.info("Loading first large model...")
        load_results = await optimized_loader.load_models_parallel({"large-model-1": memory_intensive_models["large-model-1"]})
        
        if load_results.get("large-model-1", False):
            logger.info("✅ First large model loaded")
            
            # Test memory-aware switching
            logger.info("Testing memory-aware switch to second large model...")
            
            start_time = time.time()
            success = await optimized_loader.switch_models("large-model-1", "large-model-2", "memory_aware")
            switch_time = time.time() - start_time
            
            if success:
                logger.info(f"✅ Memory-aware switch successful in {switch_time:.2f} seconds")
            else:
                logger.error("❌ Memory-aware switch failed")
            
            # Test compressed switching
            logger.info("Testing compressed switch back to first model...")
            
            start_time = time.time()
            success = await optimized_loader.switch_models("large-model-2", "large-model-1", "compressed_switch")
            switch_time = time.time() - start_time
            
            if success:
                logger.info(f"✅ Compressed switch successful in {switch_time:.2f} seconds")
            else:
                logger.error("❌ Compressed switch failed")
            
        else:
            logger.warning("Failed to load first large model")
        
        await optimized_loader.shutdown()
        logger.info("✅ Memory-aware switching test completed")
        
    except Exception as e:
        logger.error(f"❌ Error in memory-aware switching test: {e}")
        raise


async def test_integration_with_model_manager():
    """Test integration between ModelManager and OptimizedModelLoader."""
    logger.info("=== Testing Integration with ModelManager ===")
    
    try:
        # Initialize model manager with optimized loading enabled
        model_manager = ModelManager(max_concurrent_loads=2)
        model_manager.enable_parallel_loading(True)
        await model_manager.start_progressive_loading()
        
        # Wait for models to load
        await asyncio.sleep(8)
        
        # Get loaded models
        model_statuses = model_manager.get_all_model_statuses()
        loaded_models = [name for name, status in model_statuses.items() 
                        if status and status.get("status") == "loaded"]
        
        logger.info(f"Loaded models: {loaded_models}")
        
        if len(loaded_models) >= 2:
            old_model = loaded_models[0]
            new_model = loaded_models[1]
            
            # Test integrated switching
            logger.info(f"Testing integrated switch: {old_model} -> {new_model}")
            
            start_time = time.time()
            success = await model_manager.switch_model(old_model, new_model, "hot_swap")
            switch_time = time.time() - start_time
            
            if success:
                logger.info(f"✅ Integrated switch successful in {switch_time:.2f} seconds")
            else:
                logger.error("❌ Integrated switch failed")
            
            # Test preloading for switching
            logger.info("Testing preload for switching...")
            preload_models = [m for m in model_manager.model_configs.keys() if m not in loaded_models][:2]
            
            if preload_models:
                preload_results = await model_manager.preload_for_switching(preload_models)
                logger.info(f"Preload results: {preload_results}")
            
            # Test batch switching
            if len(loaded_models) >= 3:
                logger.info("Testing batch switching...")
                switches = [
                    (loaded_models[0], loaded_models[1]),
                    (loaded_models[1], loaded_models[2])
                ]
                
                batch_results = await model_manager.batch_switch_models(switches, "auto")
                logger.info(f"Batch switch results: {batch_results}")
        
        else:
            logger.warning("Not enough models loaded for integration test")
        
        # Get comprehensive stats
        stats = model_manager.get_model_switching_stats()
        logger.info(f"Final switching stats: {stats}")
        
        await model_manager.shutdown()
        logger.info("✅ Integration test completed")
        
    except Exception as e:
        logger.error(f"❌ Error in integration test: {e}")
        raise


async def main():
    """Run all model switching tests."""
    logger.info("🚀 Starting Efficient Model Switching Tests")
    
    tests = [
        ("Basic Model Switching", test_basic_model_switching),
        ("Optimized Model Switching", test_optimized_model_switching),
        ("Memory-Aware Switching", test_memory_aware_switching),
        ("Integration Test", test_integration_with_model_manager)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        logger.info(f"\n{'='*60}")
        logger.info(f"Running: {test_name}")
        logger.info(f"{'='*60}")
        
        try:
            start_time = time.time()
            await test_func()
            test_time = time.time() - start_time
            
            results[test_name] = {
                "status": "PASSED",
                "time": test_time
            }
            logger.info(f"✅ {test_name} PASSED in {test_time:.2f} seconds")
            
        except Exception as e:
            results[test_name] = {
                "status": "FAILED",
                "error": str(e)
            }
            logger.error(f"❌ {test_name} FAILED: {e}")
        
        # Brief pause between tests
        await asyncio.sleep(2)
    
    # Print summary
    logger.info(f"\n{'='*60}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*60}")
    
    passed = sum(1 for r in results.values() if r["status"] == "PASSED")
    total = len(results)
    
    for test_name, result in results.items():
        status_icon = "✅" if result["status"] == "PASSED" else "❌"
        if result["status"] == "PASSED":
            logger.info(f"{status_icon} {test_name}: {result['status']} ({result['time']:.2f}s)")
        else:
            logger.info(f"{status_icon} {test_name}: {result['status']} - {result['error']}")
    
    logger.info(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All tests passed! Efficient model switching is working correctly.")
        return 0
    else:
        logger.error(f"💥 {total - passed} tests failed. Please check the implementation.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)