#!/usr/bin/env python3
"""
Demo script for model compression and optimization features.

This script demonstrates the enhanced model compression and optimization
capabilities of the OptimizedModelLoader.
"""

import asyncio
import logging
import numpy as np
import tempfile
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import the modules
from src.multimodal_librarian.models.loader_optimized import (
    OptimizedModelLoader, CompressionLevel, CompressionMethod, OptimizationStrategy
)
from src.multimodal_librarian.models.model_manager import ModelConfig, ModelPriority


async def demo_compression_and_optimization():
    """Demonstrate model compression and optimization features."""
    logger.info("🚀 Starting Model Compression and Optimization Demo")
    
    # Create a temporary directory for cache
    with tempfile.TemporaryDirectory() as temp_dir:
        # Initialize the optimized loader
        loader = OptimizedModelLoader(max_parallel_loads=3)
        loader.compression_cache_dir = temp_dir
        
        await loader.start()
        
        try:
            # Create realistic model configurations
            model_configs = {
                "text_embedding_model": ModelConfig(
                    name="text_embedding_model",
                    model_type="embedding",
                    estimated_memory_mb=800,
                    estimated_load_time_seconds=3,
                    priority=ModelPriority.ESSENTIAL,
                    required_for_capabilities=["text_embedding", "semantic_search"],
                    dependencies=[]
                ),
                "chat_model_small": ModelConfig(
                    name="chat_model_small",
                    model_type="language_model",
                    estimated_memory_mb=1200,
                    estimated_load_time_seconds=4,
                    priority=ModelPriority.STANDARD,
                    required_for_capabilities=["text_generation", "chat"],
                    dependencies=["text_embedding_model"]
                ),
                "multimodal_model": ModelConfig(
                    name="multimodal_model",
                    model_type="multimodal",
                    estimated_memory_mb=3000,
                    estimated_load_time_seconds=8,
                    priority=ModelPriority.ADVANCED,
                    required_for_capabilities=["image_analysis", "multimodal_chat"],
                    dependencies=["text_embedding_model", "chat_model_small"]
                )
            }
            
            logger.info("📊 Model Configuration Summary:")
            total_memory = sum(config.estimated_memory_mb for config in model_configs.values())
            total_load_time = sum(config.estimated_load_time_seconds for config in model_configs.values())
            logger.info(f"  • Total models: {len(model_configs)}")
            logger.info(f"  • Total estimated memory: {total_memory:.1f}MB")
            logger.info(f"  • Total estimated load time: {total_load_time}s")
            
            # Load models with automatic compression and optimization
            logger.info("\n🔄 Loading models with automatic compression and optimization...")
            start_time = datetime.now()
            
            results = await loader.load_models_parallel(model_configs)
            
            end_time = datetime.now()
            load_duration = (end_time - start_time).total_seconds()
            
            logger.info(f"✅ Model loading completed in {load_duration:.2f}s")
            logger.info(f"   Success rate: {sum(results.values())}/{len(results)} models")
            
            # Display loading results
            for model_name, success in results.items():
                status = "✅ SUCCESS" if success else "❌ FAILED"
                logger.info(f"   {model_name}: {status}")
            
            # Get initial statistics
            stats = loader.get_optimization_statistics()
            logger.info(f"\n📈 Initial Loading Statistics:")
            logger.info(f"  • Models compressed: {stats['loading_stats']['total_models_compressed']}")
            logger.info(f"  • Models optimized: {stats['loading_stats']['total_models_optimized']}")
            logger.info(f"  • Compression savings: {stats['loading_stats']['compression_saves_mb']:.2f}MB")
            logger.info(f"  • Optimization savings: {stats['loading_stats']['optimization_saves_mb']:.2f}MB")
            logger.info(f"  • Average compression ratio: {stats['loading_stats']['average_compression_ratio']:.2f}x")
            logger.info(f"  • Average optimization ratio: {stats['loading_stats']['average_optimization_ratio']:.2f}x")
            
            # Demonstrate manual compression of existing models
            logger.info("\n🗜️  Demonstrating manual compression...")
            
            # Compress the embedding model with different levels
            compression_levels = [
                (CompressionLevel.LIGHT, CompressionMethod.GZIP),
                (CompressionLevel.MEDIUM, CompressionMethod.LZMA),
                (CompressionLevel.AGGRESSIVE, CompressionMethod.LZMA)
            ]
            
            for level, method in compression_levels:
                success = await loader.compress_existing_model(
                    "text_embedding_model", level, method
                )
                
                if success:
                    compression_info = await loader.get_model_compression_info("text_embedding_model")
                    logger.info(f"  ✅ {level.value} compression with {method.value}: "
                               f"{compression_info['compressed_size_mb']:.2f}MB")
                else:
                    logger.warning(f"  ❌ Failed to compress with {level.value}/{method.value}")
            
            # Demonstrate manual optimization of existing models
            logger.info("\n⚡ Demonstrating manual optimization...")
            
            optimization_strategies = [
                OptimizationStrategy.QUANTIZATION,
                OptimizationStrategy.PRUNING,
                OptimizationStrategy.CACHING
            ]
            
            for strategy in optimization_strategies:
                success = await loader.optimize_existing_model("multimodal_model", strategy)
                
                if success:
                    optimization_info = await loader.get_model_optimization_info("multimodal_model")
                    logger.info(f"  ✅ {strategy.value} optimization applied")
                else:
                    logger.warning(f"  ❌ Failed to apply {strategy.value} optimization")
            
            # Show compression details for each model
            logger.info("\n🔍 Model Compression Details:")
            for model_name in model_configs.keys():
                compression_info = await loader.get_model_compression_info(model_name)
                if compression_info:
                    logger.info(f"  • {model_name}:")
                    logger.info(f"    - Method: {compression_info['compression_method']}")
                    logger.info(f"    - Size: {compression_info['compressed_size_mb']:.2f}MB")
                    logger.info(f"    - Cached: {compression_info['is_cached']}")
                    logger.info(f"    - Cache file: {compression_info['cache_file_exists']}")
                else:
                    logger.info(f"  • {model_name}: Not compressed")
            
            # Show optimization details
            logger.info("\n⚙️  Model Optimization Details:")
            for model_name in model_configs.keys():
                optimization_info = await loader.get_model_optimization_info(model_name)
                if optimization_info:
                    logger.info(f"  • {model_name}:")
                    logger.info(f"    - Optimized: {optimization_info['is_optimized']}")
                    logger.info(f"    - Memory usage: {optimization_info['memory_usage_mb']:.1f}MB")
                    logger.info(f"    - Cached: {optimization_info['is_cached']}")
                else:
                    logger.info(f"  • {model_name}: Not optimized")
            
            # Final statistics
            final_stats = loader.get_optimization_statistics()
            logger.info(f"\n📊 Final Statistics:")
            logger.info(f"  • Total compressions: {final_stats['compression_stats']['compressions_performed']}")
            logger.info(f"  • Total optimizations: {final_stats['optimization_stats']['optimizations_performed']}")
            logger.info(f"  • Total compression savings: {final_stats['compression_stats']['total_size_saved_mb']:.2f}MB")
            logger.info(f"  • Total optimization savings: {final_stats['optimization_stats']['total_memory_saved_mb']:.2f}MB")
            logger.info(f"  • Cache files created: {final_stats['cache_files']}")
            
            # Memory information
            memory_info = final_stats['memory_info']
            logger.info(f"\n💾 Memory Status:")
            logger.info(f"  • Total system memory: {memory_info.total_mb:.1f}MB")
            logger.info(f"  • Available memory: {memory_info.available_mb:.1f}MB")
            logger.info(f"  • Memory usage: {memory_info.usage_percent:.1f}%")
            logger.info(f"  • Memory pressure: {memory_info.pressure_level.value}")
            
            # Demonstrate cache cleanup
            logger.info("\n🧹 Demonstrating cache cleanup...")
            cleaned_files = await loader.cleanup_compressed_cache(max_age_hours=0)  # Clean all files
            logger.info(f"  • Cleaned up {cleaned_files} cache files")
            
            logger.info("\n🎉 Demo completed successfully!")
            
        except Exception as e:
            logger.error(f"❌ Demo failed: {e}")
            raise
        
        finally:
            await loader.shutdown()
            logger.info("🔄 OptimizedModelLoader shutdown complete")


async def main():
    """Run the demo."""
    try:
        await demo_compression_and_optimization()
    except KeyboardInterrupt:
        logger.info("Demo interrupted by user")
    except Exception as e:
        logger.error(f"Demo failed with error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())