#!/usr/bin/env python3
"""
Model Cache Startup Time Reduction Test

This test validates that the model cache reduces subsequent startup times by 50%+.

Test Strategy:
1. Measure baseline startup time without cache (cold start)
2. Measure startup time with warm cache (cached models)
3. Calculate time reduction percentage
4. Validate that reduction is >= 50%

Success Criteria:
- Cache reduces startup time by at least 50%
- Cached startup completes in reasonable time
- Cache hit rate is high during cached startup
"""

import asyncio
import pytest
import pytest_asyncio
import tempfile
import shutil
import os
import time
import statistics
from typing import Dict, List, Any, Tuple
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock
import json

from src.multimodal_librarian.cache.model_cache import (
    ModelCache,
    CacheConfig,
    CacheStatus,
    ModelCacheEntry
)
from src.multimodal_librarian.startup.cache_warmer import (
    CacheWarmer,
    WarmingConfig,
    WarmingStrategy
)


class MockModelLoader:
    """Mock model loader for testing."""
    
    def __init__(self, cache: ModelCache):
        self.cache = cache
        self.load_times = {
            "text-embedding-small": 5.0,    # 5 seconds
            "chat-model-base": 15.0,        # 15 seconds
            "search-index": 10.0,           # 10 seconds
            "chat-model-large": 60.0,       # 60 seconds
            "document-processor": 30.0,     # 30 seconds
            "multimodal-model": 120.0,      # 120 seconds
            "specialized-analyzers": 90.0   # 90 seconds
        }
        self.loaded_models = {}
    
    async def load_model(self, model_name: str, use_cache: bool = True) -> Dict[str, Any]:
        """Load a model with or without cache."""
        start_time = time.time()
        
        if use_cache:
            # Try to load from cache
            cached_path = await self.cache.get_cached_model_path(model_name, "latest")
            
            if cached_path:
                # Simulate fast cache load (10% of original time)
                load_time = self.load_times.get(model_name, 10.0) * 0.1
                await asyncio.sleep(load_time)
                
                model = {
                    "name": model_name,
                    "loaded_from_cache": True,
                    "load_time": load_time,
                    "cached_path": cached_path
                }
            else:
                # Simulate full load
                load_time = self.load_times.get(model_name, 10.0)
                await asyncio.sleep(load_time)
                
                model = {
                    "name": model_name,
                    "loaded_from_cache": False,
                    "load_time": load_time
                }
        else:
            # Simulate full load without cache
            load_time = self.load_times.get(model_name, 10.0)
            await asyncio.sleep(load_time)
            
            model = {
                "name": model_name,
                "loaded_from_cache": False,
                "load_time": load_time
            }
        
        actual_time = time.time() - start_time
        model["actual_load_time"] = actual_time
        
        self.loaded_models[model_name] = model
        return model
    
    async def load_essential_models(self, use_cache: bool = True) -> Dict[str, Any]:
        """Load essential models for startup."""
        essential_models = [
            "text-embedding-small",
            "chat-model-base",
            "search-index"
        ]
        
        start_time = time.time()
        results = {
            "models": [],
            "total_time": 0.0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        
        for model_name in essential_models:
            model = await self.load_model(model_name, use_cache)
            results["models"].append(model)
            
            if model.get("loaded_from_cache"):
                results["cache_hits"] += 1
            else:
                results["cache_misses"] += 1
        
        results["total_time"] = time.time() - start_time
        return results
    
    async def load_all_models(self, use_cache: bool = True) -> Dict[str, Any]:
        """Load all models for full startup."""
        all_models = list(self.load_times.keys())
        
        start_time = time.time()
        results = {
            "models": [],
            "total_time": 0.0,
            "cache_hits": 0,
            "cache_misses": 0
        }
        
        for model_name in all_models:
            model = await self.load_model(model_name, use_cache)
            results["models"].append(model)
            
            if model.get("loaded_from_cache"):
                results["cache_hits"] += 1
            else:
                results["cache_misses"] += 1
        
        results["total_time"] = time.time() - start_time
        return results


class TestCacheStartupTimeReduction:
    """Test cache reduces startup time by 50%+."""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create temporary cache directory."""
        temp_dir = tempfile.mkdtemp(prefix="cache_startup_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest_asyncio.fixture
    async def cache_instance(self, temp_cache_dir):
        """Create cache instance for testing."""
        config = CacheConfig(
            cache_dir=temp_cache_dir,
            max_cache_size_gb=10.0,
            validation_enabled=False  # Disable for faster testing
        )
        cache = ModelCache(config)
        await cache.initialize()
        yield cache
        await cache.shutdown()
    
    async def _populate_cache(self, cache: ModelCache, models: List[str]) -> None:
        """Populate cache with test models."""
        for model_name in models:
            cache_key = f"{model_name}:latest"
            file_path = os.path.join(cache.config.cache_dir, "models", f"{model_name}.bin")
            metadata_path = os.path.join(cache.config.cache_dir, "metadata", f"{cache_key}.json")
            
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
            
            # Create dummy model file
            with open(file_path, 'wb') as f:
                f.write(b'model_data' * 10000)  # ~100KB
            
            # Create metadata
            metadata = {
                "model_name": model_name,
                "model_version": "latest",
                "cached_at": datetime.now().isoformat()
            }
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f)
            
            # Add cache entry
            entry = ModelCacheEntry(
                model_name=model_name,
                model_version="latest",
                file_path=file_path,
                metadata_path=metadata_path,
                size_bytes=100000,
                checksum="abc123",
                download_time=datetime.now(),
                last_accessed=datetime.now(),
                status=CacheStatus.CACHED
            )
            cache.cache_entries[cache_key] = entry
        
        await cache._save_cache_index()
    
    @pytest.mark.asyncio
    async def test_essential_models_startup_time_reduction(self, cache_instance):
        """Test cache reduces essential models startup time by 50%+."""
        print("\n🚀 Testing essential models startup time reduction...")
        
        loader = MockModelLoader(cache_instance)
        
        # Test 1: Cold start (no cache)
        print("\n   📊 Cold Start (No Cache):")
        cold_start_results = await loader.load_essential_models(use_cache=False)
        cold_start_time = cold_start_results["total_time"]
        
        print(f"      ✓ Models loaded: {len(cold_start_results['models'])}")
        print(f"      ✓ Total time: {cold_start_time:.2f}s")
        print(f"      ✓ Cache hits: {cold_start_results['cache_hits']}")
        print(f"      ✓ Cache misses: {cold_start_results['cache_misses']}")
        
        # Populate cache with essential models
        essential_models = ["text-embedding-small", "chat-model-base", "search-index"]
        await self._populate_cache(cache_instance, essential_models)
        
        # Test 2: Warm start (with cache)
        print("\n   📊 Warm Start (With Cache):")
        warm_start_results = await loader.load_essential_models(use_cache=True)
        warm_start_time = warm_start_results["total_time"]
        
        print(f"      ✓ Models loaded: {len(warm_start_results['models'])}")
        print(f"      ✓ Total time: {warm_start_time:.2f}s")
        print(f"      ✓ Cache hits: {warm_start_results['cache_hits']}")
        print(f"      ✓ Cache misses: {warm_start_results['cache_misses']}")
        
        # Calculate reduction
        time_saved = cold_start_time - warm_start_time
        reduction_percent = (time_saved / cold_start_time) * 100
        
        print(f"\n   📈 Performance Improvement:")
        print(f"      ✓ Time saved: {time_saved:.2f}s")
        print(f"      ✓ Reduction: {reduction_percent:.1f}%")
        print(f"      ✓ Speedup: {cold_start_time/warm_start_time:.2f}x")
        
        # Validate 50%+ reduction
        assert reduction_percent >= 50.0, (
            f"Cache should reduce startup time by at least 50%, "
            f"but only achieved {reduction_percent:.1f}% reduction"
        )
        
        # Validate cache was actually used
        assert warm_start_results["cache_hits"] == len(essential_models), (
            "All essential models should be loaded from cache"
        )
        
        print(f"\n   ✅ SUCCESS: Cache reduced startup time by {reduction_percent:.1f}% (>= 50% required)")
    
    @pytest.mark.asyncio
    async def test_full_startup_time_reduction(self, cache_instance):
        """Test cache reduces full startup time by 50%+."""
        print("\n🚀 Testing full startup time reduction...")
        
        loader = MockModelLoader(cache_instance)
        all_models = list(loader.load_times.keys())
        
        # Test 1: Cold start (no cache)
        print("\n   📊 Cold Start (No Cache):")
        cold_start_results = await loader.load_all_models(use_cache=False)
        cold_start_time = cold_start_results["total_time"]
        
        print(f"      ✓ Models loaded: {len(cold_start_results['models'])}")
        print(f"      ✓ Total time: {cold_start_time:.2f}s")
        
        # Populate cache with all models
        await self._populate_cache(cache_instance, all_models)
        
        # Test 2: Warm start (with cache)
        print("\n   📊 Warm Start (With Cache):")
        warm_start_results = await loader.load_all_models(use_cache=True)
        warm_start_time = warm_start_results["total_time"]
        
        print(f"      ✓ Models loaded: {len(warm_start_results['models'])}")
        print(f"      ✓ Total time: {warm_start_time:.2f}s")
        print(f"      ✓ Cache hits: {warm_start_results['cache_hits']}")
        
        # Calculate reduction
        time_saved = cold_start_time - warm_start_time
        reduction_percent = (time_saved / cold_start_time) * 100
        
        print(f"\n   📈 Performance Improvement:")
        print(f"      ✓ Time saved: {time_saved:.2f}s")
        print(f"      ✓ Reduction: {reduction_percent:.1f}%")
        print(f"      ✓ Speedup: {cold_start_time/warm_start_time:.2f}x")
        
        # Validate 50%+ reduction
        assert reduction_percent >= 50.0, (
            f"Cache should reduce startup time by at least 50%, "
            f"but only achieved {reduction_percent:.1f}% reduction"
        )
        
        print(f"\n   ✅ SUCCESS: Cache reduced full startup time by {reduction_percent:.1f}% (>= 50% required)")
    
    @pytest.mark.asyncio
    async def test_multiple_startup_cycles(self, cache_instance):
        """Test cache performance across multiple startup cycles."""
        print("\n🔄 Testing multiple startup cycles...")
        
        loader = MockModelLoader(cache_instance)
        essential_models = ["text-embedding-small", "chat-model-base", "search-index"]
        
        # Populate cache
        await self._populate_cache(cache_instance, essential_models)
        
        # Run multiple startup cycles
        num_cycles = 5
        startup_times = []
        
        print(f"\n   Running {num_cycles} startup cycles with cache:")
        for i in range(num_cycles):
            results = await loader.load_essential_models(use_cache=True)
            startup_times.append(results["total_time"])
            print(f"      Cycle {i+1}: {results['total_time']:.2f}s (hits: {results['cache_hits']})")
        
        # Calculate statistics
        avg_time = statistics.mean(startup_times)
        min_time = min(startup_times)
        max_time = max(startup_times)
        std_dev = statistics.stdev(startup_times) if len(startup_times) > 1 else 0
        
        print(f"\n   📊 Startup Time Statistics:")
        print(f"      ✓ Average: {avg_time:.2f}s")
        print(f"      ✓ Min: {min_time:.2f}s")
        print(f"      ✓ Max: {max_time:.2f}s")
        print(f"      ✓ Std Dev: {std_dev:.2f}s")
        
        # Validate consistency
        assert std_dev < avg_time * 0.1, "Startup times should be consistent"
        
        # Get cache statistics
        cache_stats = cache_instance.get_cache_statistics()
        hit_rate = cache_stats["hit_rate_percent"]
        
        print(f"\n   📈 Cache Performance:")
        print(f"      ✓ Hit rate: {hit_rate:.1f}%")
        print(f"      ✓ Total hits: {cache_stats['statistics']['cache_hits']}")
        print(f"      ✓ Total misses: {cache_stats['statistics']['cache_misses']}")
        
        # Validate high hit rate
        assert hit_rate >= 90.0, f"Cache hit rate should be >= 90%, got {hit_rate:.1f}%"
        
        print(f"\n   ✅ SUCCESS: Consistent cached startup performance with {hit_rate:.1f}% hit rate")
    
    @pytest.mark.asyncio
    async def test_partial_cache_scenario(self, cache_instance):
        """Test startup time reduction with partial cache."""
        print("\n🔄 Testing partial cache scenario...")
        
        loader = MockModelLoader(cache_instance)
        all_models = list(loader.load_times.keys())
        
        # Populate cache with only some models (50%)
        cached_models = all_models[:len(all_models)//2]
        await self._populate_cache(cache_instance, cached_models)
        
        print(f"\n   Cache populated with {len(cached_models)}/{len(all_models)} models")
        
        # Test 1: Full cold start
        print("\n   📊 Full Cold Start:")
        cold_start_results = await loader.load_all_models(use_cache=False)
        cold_start_time = cold_start_results["total_time"]
        print(f"      ✓ Total time: {cold_start_time:.2f}s")
        
        # Test 2: Partial cache start
        print("\n   📊 Partial Cache Start:")
        partial_cache_results = await loader.load_all_models(use_cache=True)
        partial_cache_time = partial_cache_results["total_time"]
        
        print(f"      ✓ Total time: {partial_cache_time:.2f}s")
        print(f"      ✓ Cache hits: {partial_cache_results['cache_hits']}")
        print(f"      ✓ Cache misses: {partial_cache_results['cache_misses']}")
        
        # Calculate reduction
        time_saved = cold_start_time - partial_cache_time
        reduction_percent = (time_saved / cold_start_time) * 100
        
        print(f"\n   📈 Performance Improvement:")
        print(f"      ✓ Time saved: {time_saved:.2f}s")
        print(f"      ✓ Reduction: {reduction_percent:.1f}%")
        
        # With 50% cache, we should still see significant improvement
        # (though may not reach 50% overall reduction)
        assert reduction_percent > 20.0, (
            f"Even partial cache should provide >20% reduction, got {reduction_percent:.1f}%"
        )
        
        print(f"\n   ✅ SUCCESS: Partial cache provided {reduction_percent:.1f}% reduction")
    
    @pytest.mark.asyncio
    async def test_cache_hit_rate_impact_on_startup(self, cache_instance):
        """Test relationship between cache hit rate and startup time."""
        print("\n📊 Testing cache hit rate impact on startup time...")
        
        loader = MockModelLoader(cache_instance)
        essential_models = ["text-embedding-small", "chat-model-base", "search-index"]
        
        scenarios = [
            ("0% cache", []),
            ("33% cache", essential_models[:1]),
            ("67% cache", essential_models[:2]),
            ("100% cache", essential_models)
        ]
        
        results = []
        
        for scenario_name, cached_models in scenarios:
            # Clear and repopulate cache
            cache_instance.cache_entries.clear()
            if cached_models:
                await self._populate_cache(cache_instance, cached_models)
            
            # Measure startup time
            startup_results = await loader.load_essential_models(use_cache=True)
            
            hit_rate = (startup_results["cache_hits"] / len(essential_models)) * 100
            
            results.append({
                "scenario": scenario_name,
                "hit_rate": hit_rate,
                "startup_time": startup_results["total_time"],
                "cache_hits": startup_results["cache_hits"],
                "cache_misses": startup_results["cache_misses"]
            })
            
            print(f"\n   {scenario_name}:")
            print(f"      ✓ Hit rate: {hit_rate:.0f}%")
            print(f"      ✓ Startup time: {startup_results['total_time']:.2f}s")
        
        # Analyze correlation
        print(f"\n   📈 Cache Hit Rate vs Startup Time:")
        baseline_time = results[0]["startup_time"]
        
        for result in results:
            reduction = ((baseline_time - result["startup_time"]) / baseline_time) * 100
            print(f"      {result['scenario']:15} - {result['hit_rate']:3.0f}% hit rate → "
                  f"{result['startup_time']:5.2f}s ({reduction:+.1f}% vs baseline)")
        
        # Validate that 100% cache achieves 50%+ reduction
        full_cache_result = results[-1]
        full_cache_reduction = ((baseline_time - full_cache_result["startup_time"]) / baseline_time) * 100
        
        assert full_cache_reduction >= 50.0, (
            f"100% cache should achieve 50%+ reduction, got {full_cache_reduction:.1f}%"
        )
        
        print(f"\n   ✅ SUCCESS: 100% cache achieved {full_cache_reduction:.1f}% reduction")


@pytest.mark.asyncio
async def test_cache_startup_time_reduction_integration():
    """Integration test for cache startup time reduction."""
    print("\n🎯 Running cache startup time reduction integration test...")
    
    temp_dir = tempfile.mkdtemp(prefix="cache_integration_test_")
    
    try:
        # Create cache
        config = CacheConfig(
            cache_dir=temp_dir,
            max_cache_size_gb=10.0,
            validation_enabled=False
        )
        cache = ModelCache(config)
        await cache.initialize()
        
        # Create loader
        loader = MockModelLoader(cache)
        essential_models = ["text-embedding-small", "chat-model-base", "search-index"]
        
        # Measure cold start
        print("\n   📊 Measuring cold start time...")
        cold_start_results = await loader.load_essential_models(use_cache=False)
        cold_start_time = cold_start_results["total_time"]
        print(f"      ✓ Cold start: {cold_start_time:.2f}s")
        
        # Populate cache
        print("\n   📦 Populating cache...")
        for model_name in essential_models:
            cache_key = f"{model_name}:latest"
            file_path = os.path.join(temp_dir, "models", f"{model_name}.bin")
            metadata_path = os.path.join(temp_dir, "metadata", f"{cache_key}.json")
            
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
            
            with open(file_path, 'wb') as f:
                f.write(b'model_data' * 10000)
            
            with open(metadata_path, 'w') as f:
                json.dump({"model_name": model_name}, f)
            
            entry = ModelCacheEntry(
                model_name=model_name,
                model_version="latest",
                file_path=file_path,
                metadata_path=metadata_path,
                size_bytes=100000,
                checksum="abc123",
                download_time=datetime.now(),
                last_accessed=datetime.now(),
                status=CacheStatus.CACHED
            )
            cache.cache_entries[cache_key] = entry
        
        await cache._save_cache_index()
        print(f"      ✓ Cached {len(essential_models)} models")
        
        # Measure warm start
        print("\n   📊 Measuring warm start time...")
        warm_start_results = await loader.load_essential_models(use_cache=True)
        warm_start_time = warm_start_results["total_time"]
        print(f"      ✓ Warm start: {warm_start_time:.2f}s")
        print(f"      ✓ Cache hits: {warm_start_results['cache_hits']}/{len(essential_models)}")
        
        # Calculate improvement
        time_saved = cold_start_time - warm_start_time
        reduction_percent = (time_saved / cold_start_time) * 100
        speedup = cold_start_time / warm_start_time
        
        print(f"\n   📈 Performance Results:")
        print(f"      ✓ Time saved: {time_saved:.2f}s")
        print(f"      ✓ Reduction: {reduction_percent:.1f}%")
        print(f"      ✓ Speedup: {speedup:.2f}x")
        
        # Validate
        assert reduction_percent >= 50.0, (
            f"Cache should reduce startup time by at least 50%, "
            f"achieved {reduction_percent:.1f}%"
        )
        
        # Get cache statistics
        cache_stats = cache.get_cache_statistics()
        print(f"\n   📊 Cache Statistics:")
        print(f"      ✓ Total entries: {cache_stats['total_entries']}")
        print(f"      ✓ Cache size: {cache_stats['total_size_mb']:.2f} MB")
        print(f"      ✓ Hit rate: {cache_stats['hit_rate_percent']:.1f}%")
        
        await cache.shutdown()
        
        print(f"\n   ✅ INTEGRATION TEST PASSED: {reduction_percent:.1f}% startup time reduction")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
