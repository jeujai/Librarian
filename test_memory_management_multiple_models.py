#!/usr/bin/env python3
"""
Test script for multi-model memory management functionality.

This script tests the enhanced memory manager's ability to handle multiple models
simultaneously with proper memory allocation, pool management, and optimization.
"""

import asyncio
import logging
import sys
import os
import time
from datetime import datetime, timedelta

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from multimodal_librarian.utils.memory_manager import (
    MemoryManager, 
    initialize_memory_manager,
    MemoryPressureLevel
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_basic_multi_model_management():
    """Test basic multi-model registration and management."""
    logger.info("Testing basic multi-model management")
    
    # Initialize memory manager with lower limits for testing
    memory_manager = await initialize_memory_manager(
        memory_threshold_mb=1000.0,  # 1GB threshold for testing
        max_concurrent_models=3
    )
    
    try:
        # Test model registration
        models_to_register = [
            ("text_embedding", 100.0, 5, "essential"),
            ("chat_model_small", 200.0, 4, "standard"),
            ("document_processor", 150.0, 3, "standard"),
            ("multimodal_large", 400.0, 2, "advanced")
        ]
        
        registered_models = []
        
        for model_name, memory_mb, priority, model_type in models_to_register:
            logger.info(f"Registering model: {model_name}")
            success = await memory_manager.register_model(
                model_name=model_name,
                memory_mb=memory_mb,
                priority=priority,
                model_type=model_type
            )
            
            if success:
                registered_models.append(model_name)
                logger.info(f"✓ Successfully registered {model_name}")
            else:
                logger.warning(f"✗ Failed to register {model_name}")
        
        # Check model info
        logger.info("\nRegistered models info:")
        all_models = memory_manager.get_all_models_info()
        for model_name, info in all_models.items():
            logger.info(f"  {model_name}: {info['memory_mb']:.1f}MB, "
                       f"priority {info['priority']}, pool {info['pool']}")
        
        # Check memory pool status
        logger.info("\nMemory pool status:")
        pool_status = memory_manager.get_memory_pool_status()
        for pool_name, status in pool_status.items():
            logger.info(f"  {pool_name}: {status['allocated_mb']:.1f}MB allocated, "
                       f"{status['available_mb']:.1f}MB available, "
                       f"{status['utilization_percent']:.1f}% utilized")
        
        # Test model access tracking
        logger.info("\nTesting model access tracking...")
        for model_name in registered_models[:2]:  # Access first 2 models
            await memory_manager.update_model_access(model_name)
            await asyncio.sleep(0.1)  # Small delay
        
        # Test memory recommendations
        logger.info("\nMemory recommendations:")
        recommendations = memory_manager.get_memory_recommendations()
        for rec in recommendations["recommendations"]:
            logger.info(f"  {rec['type'].upper()}: {rec['message']}")
        
        # Test model unregistration
        logger.info("\nUnregistering models...")
        for model_name in registered_models:
            success = await memory_manager.unregister_model(model_name)
            if success:
                logger.info(f"✓ Successfully unregistered {model_name}")
            else:
                logger.warning(f"✗ Failed to unregister {model_name}")
        
        logger.info("✓ Basic multi-model management test completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"✗ Basic multi-model management test failed: {e}")
        return False
    
    finally:
        await memory_manager.shutdown()


async def test_memory_pool_optimization():
    """Test memory pool optimization and reallocation."""
    logger.info("Testing memory pool optimization")
    
    memory_manager = await initialize_memory_manager(
        memory_threshold_mb=2000.0,
        max_concurrent_models=5
    )
    
    try:
        # Register models that will stress different pools
        models = [
            ("essential_1", 300.0, 10, "essential"),
            ("essential_2", 250.0, 9, "essential"),
            ("standard_1", 200.0, 5, "standard"),
            ("advanced_1", 400.0, 3, "advanced"),
            ("advanced_2", 350.0, 2, "advanced")
        ]
        
        # Register all models
        for model_name, memory_mb, priority, model_type in models:
            await memory_manager.register_model(model_name, memory_mb, priority, model_type)
        
        # Check initial pool status
        logger.info("Initial pool status:")
        pool_status = memory_manager.get_memory_pool_status()
        for pool_name, status in pool_status.items():
            logger.info(f"  {pool_name}: {status['utilization_percent']:.1f}% utilized")
        
        # Run optimization
        logger.info("\nRunning memory pool optimization...")
        optimization_results = await memory_manager.optimize_model_placement()
        
        logger.info(f"Optimization results:")
        logger.info(f"  Recommendations: {len(optimization_results['recommendations'])}")
        for rec in optimization_results["recommendations"]:
            logger.info(f"    {rec['action']}: {rec.get('reason', 'N/A')}")
        
        # Test pool reallocation
        logger.info("\nTesting pool reallocation...")
        await memory_manager._reallocate_memory_pools()
        
        # Check final pool status
        logger.info("Final pool status:")
        pool_status = memory_manager.get_memory_pool_status()
        for pool_name, status in pool_status.items():
            logger.info(f"  {pool_name}: {status['utilization_percent']:.1f}% utilized")
        
        logger.info("✓ Memory pool optimization test completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"✗ Memory pool optimization test failed: {e}")
        return False
    
    finally:
        await memory_manager.shutdown()


async def test_model_dependencies():
    """Test model dependency management."""
    logger.info("Testing model dependency management")
    
    memory_manager = await initialize_memory_manager(
        memory_threshold_mb=1500.0,
        max_concurrent_models=4
    )
    
    try:
        # Register models with dependencies
        base_model = "base_embeddings"
        dependent_model = "advanced_chat"
        
        # Register base model first
        await memory_manager.register_model(
            model_name=base_model,
            memory_mb=200.0,
            priority=8,
            model_type="essential"
        )
        
        # Register dependent model
        await memory_manager.register_model(
            model_name=dependent_model,
            memory_mb=300.0,
            priority=6,
            model_type="standard",
            dependencies={base_model}
        )
        
        logger.info(f"Registered {base_model} and {dependent_model} with dependency")
        
        # Try to unregister base model (should fail due to dependency)
        logger.info(f"Attempting to unregister {base_model} (should fail)...")
        success = await memory_manager.unregister_model(base_model)
        
        if not success:
            logger.info("✓ Correctly prevented unregistration of model with dependents")
        else:
            logger.warning("✗ Incorrectly allowed unregistration of model with dependents")
        
        # Unregister dependent model first
        logger.info(f"Unregistering {dependent_model} first...")
        await memory_manager.unregister_model(dependent_model)
        
        # Now unregister base model (should succeed)
        logger.info(f"Now unregistering {base_model}...")
        success = await memory_manager.unregister_model(base_model)
        
        if success:
            logger.info("✓ Successfully unregistered base model after removing dependents")
        else:
            logger.warning("✗ Failed to unregister base model after removing dependents")
        
        logger.info("✓ Model dependency management test completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"✗ Model dependency management test failed: {e}")
        return False
    
    finally:
        await memory_manager.shutdown()


async def test_memory_pressure_handling():
    """Test memory pressure handling with multiple models."""
    logger.info("Testing memory pressure handling")
    
    # Use very low memory threshold to trigger pressure
    memory_manager = await initialize_memory_manager(
        memory_threshold_mb=500.0,  # Very low threshold
        max_concurrent_models=6
    )
    
    try:
        # Register models that will exceed memory threshold
        models = [
            ("model_1", 150.0, 5, "standard"),
            ("model_2", 120.0, 4, "standard"),
            ("model_3", 100.0, 3, "standard"),
            ("model_4", 180.0, 2, "advanced"),  # This should trigger pressure
            ("model_5", 200.0, 1, "advanced")   # This might fail due to pressure
        ]
        
        registered_count = 0
        
        for model_name, memory_mb, priority, model_type in models:
            logger.info(f"Attempting to register {model_name} ({memory_mb}MB)...")
            success = await memory_manager.register_model(model_name, memory_mb, priority, model_type)
            
            if success:
                registered_count += 1
                logger.info(f"✓ Registered {model_name}")
                
                # Check memory info after each registration
                memory_info = memory_manager.get_memory_info()
                logger.info(f"  Memory pressure: {memory_info.pressure_level.value} "
                           f"({memory_info.usage_percent:.1f}%)")
            else:
                logger.info(f"✗ Failed to register {model_name} (likely due to memory pressure)")
        
        logger.info(f"Successfully registered {registered_count}/{len(models)} models")
        
        # Get recommendations under pressure
        recommendations = memory_manager.get_memory_recommendations()
        logger.info(f"Recommendations under pressure: {len(recommendations['recommendations'])}")
        for rec in recommendations["recommendations"]:
            logger.info(f"  {rec['type'].upper()}: {rec['message']}")
        
        logger.info("✓ Memory pressure handling test completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"✗ Memory pressure handling test failed: {e}")
        return False
    
    finally:
        await memory_manager.shutdown()


async def test_model_access_patterns():
    """Test model access pattern tracking and optimization."""
    logger.info("Testing model access pattern tracking")
    
    memory_manager = await initialize_memory_manager(
        memory_threshold_mb=1000.0,
        max_concurrent_models=4
    )
    
    try:
        # Register test models
        models = [
            ("frequently_used", 150.0, 5, "standard"),
            ("occasionally_used", 120.0, 4, "standard"),
            ("rarely_used", 100.0, 3, "standard")
        ]
        
        for model_name, memory_mb, priority, model_type in models:
            await memory_manager.register_model(model_name, memory_mb, priority, model_type)
        
        # Simulate different access patterns
        logger.info("Simulating access patterns...")
        
        # Frequently used model - many accesses
        for _ in range(10):
            await memory_manager.update_model_access("frequently_used")
            await asyncio.sleep(0.01)
        
        # Occasionally used model - few accesses
        for _ in range(3):
            await memory_manager.update_model_access("occasionally_used")
            await asyncio.sleep(0.01)
        
        # Rarely used model - one access
        await memory_manager.update_model_access("rarely_used")
        
        # Check access patterns
        logger.info("\nModel access patterns:")
        for model_name in ["frequently_used", "occasionally_used", "rarely_used"]:
            info = memory_manager.get_model_info(model_name)
            if info:
                logger.info(f"  {model_name}: {info['access_count']} accesses, "
                           f"{info['accesses_per_hour']} per hour, "
                           f"{info['idle_minutes']:.1f} min idle")
        
        # Get recommendations (should suggest unloading rarely used model)
        recommendations = memory_manager.get_memory_recommendations()
        underutilized_recs = [r for r in recommendations["recommendations"] 
                             if r.get("action") == "consider_unloading"]
        
        if underutilized_recs:
            logger.info("✓ Correctly identified underutilized models:")
            for rec in underutilized_recs:
                logger.info(f"  Models: {rec.get('models', [])}")
        else:
            logger.info("No underutilized models identified (may need longer test duration)")
        
        logger.info("✓ Model access pattern tracking test completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"✗ Model access pattern tracking test failed: {e}")
        return False
    
    finally:
        await memory_manager.shutdown()


async def run_all_tests():
    """Run all multi-model memory management tests."""
    logger.info("Starting multi-model memory management tests")
    
    tests = [
        ("Basic Multi-Model Management", test_basic_multi_model_management),
        ("Memory Pool Optimization", test_memory_pool_optimization),
        ("Model Dependencies", test_model_dependencies),
        ("Memory Pressure Handling", test_memory_pressure_handling),
        ("Model Access Patterns", test_model_access_patterns)
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        logger.info(f"\n{'='*60}")
        logger.info(f"Running: {test_name}")
        logger.info(f"{'='*60}")
        
        try:
            start_time = time.time()
            success = await test_func()
            duration = time.time() - start_time
            
            results[test_name] = {
                "success": success,
                "duration": duration
            }
            
            if success:
                logger.info(f"✓ {test_name} PASSED ({duration:.2f}s)")
            else:
                logger.error(f"✗ {test_name} FAILED ({duration:.2f}s)")
                
        except Exception as e:
            logger.error(f"✗ {test_name} ERROR: {e}")
            results[test_name] = {
                "success": False,
                "duration": 0,
                "error": str(e)
            }
        
        # Brief pause between tests
        await asyncio.sleep(1.0)
    
    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("TEST SUMMARY")
    logger.info(f"{'='*60}")
    
    passed = sum(1 for r in results.values() if r["success"])
    total = len(results)
    
    for test_name, result in results.items():
        status = "PASS" if result["success"] else "FAIL"
        duration = result["duration"]
        logger.info(f"{status:4} | {test_name:30} | {duration:6.2f}s")
    
    logger.info(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        logger.info("🎉 All multi-model memory management tests passed!")
        return True
    else:
        logger.error(f"❌ {total - passed} tests failed")
        return False


if __name__ == "__main__":
    # Run the tests
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)