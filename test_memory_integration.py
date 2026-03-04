#!/usr/bin/env python3
"""
Integration test for memory manager with optimized loader.

This test verifies that the enhanced memory manager integrates properly
with the optimized model loader for multi-model scenarios.
"""

import asyncio
import logging
import sys
import os
import time

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from multimodal_librarian.utils.memory_manager import initialize_memory_manager
from multimodal_librarian.models.loader_optimized import OptimizedModelLoader
from multimodal_librarian.models.model_manager import ModelConfig, ModelPriority

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_memory_manager_integration():
    """Test integration between memory manager and optimized loader."""
    logger.info("Testing memory manager integration with optimized loader")
    
    # Initialize memory manager
    memory_manager = await initialize_memory_manager(
        memory_threshold_mb=2000.0,
        max_concurrent_models=4
    )
    
    # Initialize optimized loader with the memory manager
    loader = OptimizedModelLoader(
        max_parallel_loads=2,
        memory_manager=memory_manager
    )
    await loader.start()
    
    try:
        # Create test model configurations
        model_configs = {
            "embedding_model": ModelConfig(
                name="embedding_model",
                priority=ModelPriority.ESSENTIAL,
                estimated_load_time_seconds=5.0,
                estimated_memory_mb=150.0,
                required_for_capabilities=["text_embedding"],
                model_type="embedding",
                dependencies=[]
            ),
            "chat_model": ModelConfig(
                name="chat_model",
                priority=ModelPriority.STANDARD,
                estimated_load_time_seconds=10.0,
                estimated_memory_mb=300.0,
                required_for_capabilities=["chat"],
                model_type="language_model",
                dependencies=["embedding_model"]
            ),
            "multimodal_model": ModelConfig(
                name="multimodal_model",
                priority=ModelPriority.ADVANCED,
                estimated_load_time_seconds=15.0,
                estimated_memory_mb=500.0,
                required_for_capabilities=["multimodal"],
                model_type="multimodal",
                dependencies=["embedding_model"]
            )
        }
        
        # Register models with memory manager
        logger.info("Registering models with memory manager...")
        for model_name, config in model_configs.items():
            success = await memory_manager.register_model(
                model_name=model_name,
                memory_mb=config.estimated_memory_mb,
                priority=config.priority.value,
                model_type=config.model_type,
                dependencies=set(config.dependencies)
            )
            
            if success:
                logger.info(f"✓ Registered {model_name} with memory manager")
            else:
                logger.warning(f"✗ Failed to register {model_name}")
        
        # Load models using optimized loader
        logger.info("Loading models with optimized loader...")
        results = await loader.load_models_parallel(model_configs)
        
        successful_loads = sum(results.values())
        logger.info(f"Loaded {successful_loads}/{len(model_configs)} models successfully")
        
        # Check memory manager status
        logger.info("\nMemory manager status after loading:")
        all_models = memory_manager.get_all_models_info()
        for model_name, info in all_models.items():
            logger.info(f"  {model_name}: {info['memory_mb']:.1f}MB, "
                       f"{info['access_count']} accesses, pool {info['pool']}")
        
        # Check memory pool status
        logger.info("\nMemory pool status:")
        pool_status = memory_manager.get_memory_pool_status()
        for pool_name, status in pool_status.items():
            logger.info(f"  {pool_name}: {status['utilization_percent']:.1f}% utilized, "
                       f"{status['models_count']} models")
        
        # Test model access tracking
        logger.info("\nTesting model access tracking...")
        for model_name in ["embedding_model", "chat_model"]:
            await memory_manager.update_model_access(model_name)
        
        # Get optimization statistics
        logger.info("\nOptimization statistics:")
        loader_stats = loader.get_optimization_statistics()
        logger.info(f"  Loading mode: {loader_stats['current_loading_mode']}")
        logger.info(f"  Cached models: {loader_stats['cached_models']}")
        logger.info(f"  Compressed models: {loader_stats['compressed_models']}")
        
        # Get memory recommendations
        logger.info("\nMemory recommendations:")
        recommendations = memory_manager.get_memory_recommendations()
        for rec in recommendations["recommendations"]:
            logger.info(f"  {rec['type'].upper()}: {rec['message']}")
        
        # Test model switching with memory awareness
        logger.info("\nTesting memory-aware model switching...")
        switch_recommendations = await loader.get_switch_recommendations(
            "chat_model", 
            ["multimodal_model"]
        )
        
        for target_model, rec in switch_recommendations.items():
            logger.info(f"  Switch to {target_model}: {rec['recommended_strategy']} "
                       f"({rec['estimated_switch_time_seconds']:.1f}s)")
        
        logger.info("✓ Memory manager integration test completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"✗ Memory manager integration test failed: {e}")
        return False
    
    finally:
        # Cleanup
        await loader.shutdown()
        await memory_manager.shutdown()


async def main():
    """Run the integration test."""
    logger.info("Starting memory manager integration test")
    
    start_time = time.time()
    success = await test_memory_manager_integration()
    duration = time.time() - start_time
    
    if success:
        logger.info(f"🎉 Integration test PASSED ({duration:.2f}s)")
        return 0
    else:
        logger.error(f"❌ Integration test FAILED ({duration:.2f}s)")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)