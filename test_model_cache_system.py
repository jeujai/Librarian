#!/usr/bin/env python3
"""
Test script for the EFS-based model cache system.

This script tests the basic functionality of the model cache system
including cache initialization, model caching, validation, and cleanup.
"""

import asyncio
import tempfile
import shutil
import os
import json
import logging
from pathlib import Path

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import the cache system
from src.multimodal_librarian.cache.model_cache import ModelCache, CacheConfig
from src.multimodal_librarian.startup.cache_warmer import CacheWarmer, WarmingConfig


async def test_model_cache_basic():
    """Test basic model cache functionality."""
    logger.info("Testing basic model cache functionality")
    
    # Create temporary directory for testing
    temp_dir = tempfile.mkdtemp(prefix="model_cache_test_")
    
    try:
        # Create cache configuration
        config = CacheConfig(
            cache_dir=temp_dir,
            max_cache_size_gb=1.0,
            max_model_age_days=1,
            validation_enabled=True
        )
        
        # Initialize cache
        cache = ModelCache(config)
        await cache.initialize()
        
        # Test cache statistics
        stats = cache.get_cache_statistics()
        logger.info(f"Initial cache stats: {stats}")
        
        assert stats["total_entries"] == 0
        assert stats["total_size_bytes"] == 0
        
        # Test is_cached for non-existent model
        assert not cache.is_cached("test-model", "v1.0")
        
        # Test get_cached_model_path for non-existent model
        path = await cache.get_cached_model_path("test-model", "v1.0")
        assert path is None
        
        # Test get_cached_models
        models = cache.get_cached_models()
        assert len(models) == 0
        
        logger.info("✓ Basic cache functionality tests passed")
        
        # Test cache cleanup
        cleanup_stats = await cache.cleanup_cache()
        logger.info(f"Cleanup stats: {cleanup_stats}")
        
        # Shutdown cache
        await cache.shutdown()
        
        logger.info("✓ Model cache basic tests completed successfully")
        
    finally:
        # Cleanup temporary directory
        shutil.rmtree(temp_dir, ignore_errors=True)


async def test_cache_warmer_basic():
    """Test basic cache warmer functionality."""
    logger.info("Testing basic cache warmer functionality")
    
    # Create temporary directory for testing
    temp_dir = tempfile.mkdtemp(prefix="cache_warmer_test_")
    
    try:
        # Create cache configuration
        cache_config = CacheConfig(
            cache_dir=temp_dir,
            max_cache_size_gb=1.0,
            validation_enabled=False  # Disable validation for testing
        )
        
        # Initialize cache
        cache = ModelCache(cache_config)
        await cache.initialize()
        
        # Create warming configuration
        warming_config = WarmingConfig(
            max_concurrent_warming=1,
            warming_timeout_seconds=60,
            background_warming=False,
            model_urls={}  # Empty URLs for testing
        )
        
        # Initialize cache warmer
        warmer = CacheWarmer(warming_config)
        await warmer.initialize()
        
        # Test warming statistics
        stats = warmer.get_warming_statistics()
        logger.info(f"Initial warming stats: {stats}")
        
        assert stats["warming_stats"]["warming_sessions"] == 0
        assert stats["warming_stats"]["models_warmed"] == 0
        
        logger.info("✓ Basic cache warmer functionality tests passed")
        
        # Shutdown components
        await warmer.shutdown()
        await cache.shutdown()
        
        logger.info("✓ Cache warmer basic tests completed successfully")
        
    finally:
        # Cleanup temporary directory
        shutil.rmtree(temp_dir, ignore_errors=True)


async def test_cache_integration():
    """Test integration between cache and model manager."""
    logger.info("Testing cache integration with model manager")
    
    try:
        # Import model manager
        from src.multimodal_librarian.models.model_manager import ModelManager, initialize_model_manager
        from src.multimodal_librarian.cache.model_cache import initialize_model_cache
        
        # Create temporary directory for cache
        temp_dir = tempfile.mkdtemp(prefix="cache_integration_test_")
        
        # Initialize cache
        cache_config = CacheConfig(
            cache_dir=temp_dir,
            validation_enabled=False
        )
        cache = await initialize_model_cache(cache_config)
        
        # Initialize model manager
        model_manager = await initialize_model_manager()
        
        # Test loading progress with cache statistics
        progress = model_manager.get_loading_progress()
        logger.info(f"Loading progress with cache: {progress}")
        
        assert "cache_statistics" in progress
        assert "total_entries" in progress["cache_statistics"]
        
        logger.info("✓ Cache integration tests passed")
        
        # Shutdown components
        await model_manager.shutdown()
        await cache.shutdown()
        
        # Cleanup temporary directory
        shutil.rmtree(temp_dir, ignore_errors=True)
        
        logger.info("✓ Cache integration tests completed successfully")
        
    except Exception as e:
        logger.error(f"Cache integration test failed: {e}")
        raise


async def main():
    """Run all cache system tests."""
    logger.info("Starting EFS-based model cache system tests")
    
    try:
        await test_model_cache_basic()
        await test_cache_warmer_basic()
        await test_cache_integration()
        
        logger.info("🎉 All cache system tests passed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Cache system tests failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())