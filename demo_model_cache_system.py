#!/usr/bin/env python3
"""
Demo script for the EFS-based model cache system.

This script demonstrates the model cache system functionality including:
- Cache initialization and configuration
- Model caching and retrieval
- Cache warming strategies
- Integration with model manager
- Cache statistics and monitoring
"""

import asyncio
import tempfile
import shutil
import logging
import json
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import the cache system
from src.multimodal_librarian.cache.model_cache import ModelCache, CacheConfig, initialize_model_cache
from src.multimodal_librarian.startup.cache_warmer import CacheWarmer, WarmingConfig, WarmingStrategy
from src.multimodal_librarian.models.model_manager import initialize_model_manager


async def demo_cache_system():
    """Demonstrate the complete model cache system."""
    logger.info("🚀 Starting EFS-based Model Cache System Demo")
    
    # Create temporary directory for demo
    temp_dir = tempfile.mkdtemp(prefix="model_cache_demo_")
    logger.info(f"📁 Using temporary cache directory: {temp_dir}")
    
    try:
        # 1. Initialize Cache System
        logger.info("\n" + "="*60)
        logger.info("1️⃣  INITIALIZING CACHE SYSTEM")
        logger.info("="*60)
        
        cache_config = CacheConfig(
            cache_dir=temp_dir,
            max_cache_size_gb=2.0,
            max_model_age_days=7,
            max_concurrent_downloads=2,
            validation_enabled=True,
            cleanup_interval_hours=1
        )
        
        cache = await initialize_model_cache(cache_config)
        logger.info("✅ Model cache initialized successfully")
        
        # 2. Initialize Model Manager with Cache Integration
        logger.info("\n" + "="*60)
        logger.info("2️⃣  INITIALIZING MODEL MANAGER WITH CACHE")
        logger.info("="*60)
        
        model_manager = await initialize_model_manager()
        logger.info("✅ Model manager initialized with cache integration")
        
        # 3. Display Initial Statistics
        logger.info("\n" + "="*60)
        logger.info("3️⃣  INITIAL CACHE STATISTICS")
        logger.info("="*60)
        
        stats = cache.get_cache_statistics()
        logger.info(f"📊 Cache Statistics:")
        logger.info(f"   • Total entries: {stats['total_entries']}")
        logger.info(f"   • Total size: {stats['total_size_mb']:.1f} MB")
        logger.info(f"   • Hit rate: {stats['hit_rate_percent']:.1f}%")
        logger.info(f"   • Cache directory: {stats['config']['cache_dir']}")
        
        # 4. Demonstrate Cache Warming
        logger.info("\n" + "="*60)
        logger.info("4️⃣  DEMONSTRATING CACHE WARMING")
        logger.info("="*60)
        
        warming_config = WarmingConfig(
            strategy=WarmingStrategy.ESSENTIAL_ONLY,
            max_concurrent_warming=1,
            background_warming=False,
            model_urls={
                # Mock URLs for demo - in production these would be real model URLs
                "text-embedding-small": "https://example.com/models/text-embedding-small.bin",
                "chat-model-base": "https://example.com/models/chat-model-base.bin",
                "search-index": "https://example.com/models/search-index.bin"
            }
        )
        
        warmer = CacheWarmer(warming_config)
        await warmer.initialize()
        
        logger.info("🔥 Starting cache warming for essential models...")
        # Note: This will fail in demo since URLs are fake, but shows the process
        try:
            warming_results = await warmer.warm_essential_models()
            logger.info(f"📈 Warming Results:")
            logger.info(f"   • Models to warm: {len(warming_results['models_to_warm'])}")
            logger.info(f"   • Models warmed: {len(warming_results['models_warmed'])}")
            logger.info(f"   • Models failed: {len(warming_results['models_failed'])}")
            logger.info(f"   • Success rate: {warming_results['success_rate']:.1f}%")
        except Exception as e:
            logger.info(f"⚠️  Warming failed as expected (demo URLs): {e}")
        
        # 5. Demonstrate Model Loading Progress
        logger.info("\n" + "="*60)
        logger.info("5️⃣  MODEL LOADING PROGRESS")
        logger.info("="*60)
        
        progress = model_manager.get_loading_progress()
        logger.info(f"📊 Loading Progress:")
        logger.info(f"   • Total models: {progress['total_models']}")
        logger.info(f"   • Loaded models: {progress['loaded_models']}")
        logger.info(f"   • Loading models: {progress['loading_models']}")
        logger.info(f"   • Progress: {progress['progress_percent']:.1f}%")
        logger.info(f"   • Cache hits: {progress['statistics']['cache_hits']}")
        logger.info(f"   • Cache misses: {progress['statistics']['cache_misses']}")
        
        # 6. Demonstrate Cache Operations
        logger.info("\n" + "="*60)
        logger.info("6️⃣  CACHE OPERATIONS")
        logger.info("="*60)
        
        # Check if models are cached
        test_models = ["text-embedding-small", "chat-model-base", "nonexistent-model"]
        
        for model_name in test_models:
            is_cached = cache.is_cached(model_name)
            logger.info(f"🔍 Model '{model_name}' cached: {is_cached}")
            
            if is_cached:
                cached_path = await cache.get_cached_model_path(model_name)
                logger.info(f"   📂 Cache path: {cached_path}")
        
        # 7. Display Model Manager Statistics
        logger.info("\n" + "="*60)
        logger.info("7️⃣  MODEL MANAGER STATISTICS")
        logger.info("="*60)
        
        all_statuses = model_manager.get_all_model_statuses()
        logger.info(f"📋 Registered Models ({len(all_statuses)}):")
        
        for model_name, status in all_statuses.items():
            logger.info(f"   • {model_name}:")
            logger.info(f"     - Status: {status['status']}")
            logger.info(f"     - Priority: {status['priority']}")
            logger.info(f"     - Type: {status['type']}")
            logger.info(f"     - Capabilities: {', '.join(status['capabilities'][:2])}...")
        
        # 8. Demonstrate Cache Cleanup
        logger.info("\n" + "="*60)
        logger.info("8️⃣  CACHE CLEANUP")
        logger.info("="*60)
        
        cleanup_stats = await cache.cleanup_cache()
        logger.info(f"🧹 Cleanup Results:")
        logger.info(f"   • Entries checked: {cleanup_stats['entries_checked']}")
        logger.info(f"   • Entries removed: {cleanup_stats['entries_removed']}")
        logger.info(f"   • Bytes freed: {cleanup_stats['bytes_freed'] / (1024*1024):.1f} MB")
        
        # 9. Final Statistics
        logger.info("\n" + "="*60)
        logger.info("9️⃣  FINAL STATISTICS")
        logger.info("="*60)
        
        final_stats = cache.get_cache_statistics()
        warming_stats = warmer.get_warming_statistics()
        
        logger.info(f"📊 Final Cache Statistics:")
        logger.info(f"   • Total entries: {final_stats['total_entries']}")
        logger.info(f"   • Total size: {final_stats['total_size_mb']:.1f} MB")
        logger.info(f"   • Hit rate: {final_stats['hit_rate_percent']:.1f}%")
        logger.info(f"   • Downloads completed: {final_stats['statistics']['downloads_completed']}")
        logger.info(f"   • Downloads failed: {final_stats['statistics']['downloads_failed']}")
        
        logger.info(f"🔥 Warming Statistics:")
        logger.info(f"   • Warming sessions: {warming_stats['warming_stats']['warming_sessions']}")
        logger.info(f"   • Models warmed: {warming_stats['warming_stats']['models_warmed']}")
        logger.info(f"   • Warming failures: {warming_stats['warming_stats']['warming_failures']}")
        
        # 10. Demonstrate Configuration
        logger.info("\n" + "="*60)
        logger.info("🔟 CONFIGURATION DETAILS")
        logger.info("="*60)
        
        logger.info(f"⚙️  Cache Configuration:")
        logger.info(f"   • Cache directory: {cache_config.cache_dir}")
        logger.info(f"   • Max cache size: {cache_config.max_cache_size_gb} GB")
        logger.info(f"   • Max model age: {cache_config.max_model_age_days} days")
        logger.info(f"   • Max concurrent downloads: {cache_config.max_concurrent_downloads}")
        logger.info(f"   • Validation enabled: {cache_config.validation_enabled}")
        logger.info(f"   • Compression enabled: {cache_config.compression_enabled}")
        
        logger.info(f"🔥 Warming Configuration:")
        logger.info(f"   • Strategy: {warming_config.strategy.value}")
        logger.info(f"   • Max concurrent warming: {warming_config.max_concurrent_warming}")
        logger.info(f"   • Background warming: {warming_config.background_warming}")
        logger.info(f"   • Warm on startup: {warming_config.warm_on_startup}")
        
        # Wait a moment to see some model loading progress
        logger.info("\n⏳ Waiting 10 seconds to observe model loading...")
        await asyncio.sleep(10)
        
        final_progress = model_manager.get_loading_progress()
        logger.info(f"📊 Updated Loading Progress:")
        logger.info(f"   • Loaded models: {final_progress['loaded_models']}")
        logger.info(f"   • Loading models: {final_progress['loading_models']}")
        logger.info(f"   • Progress: {final_progress['progress_percent']:.1f}%")
        
        logger.info("\n" + "="*60)
        logger.info("✅ DEMO COMPLETED SUCCESSFULLY")
        logger.info("="*60)
        
        # Shutdown components
        await warmer.shutdown()
        await model_manager.shutdown()
        await cache.shutdown()
        
    finally:
        # Cleanup temporary directory
        shutil.rmtree(temp_dir, ignore_errors=True)
        logger.info(f"🧹 Cleaned up temporary directory: {temp_dir}")


async def main():
    """Run the model cache system demo."""
    try:
        await demo_cache_system()
        logger.info("\n🎉 Model Cache System Demo completed successfully!")
        
    except Exception as e:
        logger.error(f"\n❌ Demo failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())