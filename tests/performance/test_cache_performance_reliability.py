#!/usr/bin/env python3
"""
Cache Performance and Reliability Tests

This test suite validates the performance and reliability of the model cache system,
including cache hit rates, download performance, validation, cleanup, and concurrent access.

Tests cover:
- Cache hit rate performance
- Download and caching performance
- Cache validation reliability
- Cleanup effectiveness
- Concurrent access handling
- Cache warming performance
- Long-term reliability
"""

import asyncio
import pytest
import pytest_asyncio
import tempfile
import shutil
import os
import time
import statistics
from typing import Dict, List, Any
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, AsyncMock
import aiohttp

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


class TestCachePerformance:
    """Test cache performance characteristics."""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create temporary cache directory."""
        temp_dir = tempfile.mkdtemp(prefix="cache_perf_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest_asyncio.fixture
    async def cache_instance(self, temp_cache_dir):
        """Create cache instance for testing."""
        config = CacheConfig(
            cache_dir=temp_cache_dir,
            max_cache_size_gb=1.0,
            max_model_age_days=7,
            validation_enabled=True,
            max_concurrent_downloads=3
        )
        cache = ModelCache(config)
        await cache.initialize()
        yield cache
        await cache.shutdown()
    
    @pytest.mark.asyncio
    async def test_cache_hit_rate_performance(self, cache_instance):
        """Test cache hit rate tracking and performance."""
        print("\n🎯 Testing cache hit rate performance...")
        
        # Simulate cache requests
        test_models = [
            ("model-a", "v1.0"),
            ("model-b", "v1.0"),
            ("model-c", "v1.0"),
            ("model-a", "v1.0"),  # Hit
            ("model-b", "v1.0"),  # Hit
            ("model-d", "v1.0"),  # Miss
            ("model-a", "v1.0"),  # Hit
        ]
        
        # Add some models to cache
        for model_name in ["model-a", "model-b", "model-c"]:
            cache_key = f"{model_name}:v1.0"
            entry = ModelCacheEntry(
                model_name=model_name,
                model_version="v1.0",
                file_path=os.path.join(cache_instance.config.cache_dir, f"{model_name}.bin"),
                metadata_path=os.path.join(cache_instance.config.cache_dir, f"{model_name}.json"),
                size_bytes=1024 * 1024,  # 1MB
                checksum="abc123",
                download_time=datetime.now(),
                last_accessed=datetime.now(),
                status=CacheStatus.CACHED
            )
            cache_instance.cache_entries[cache_key] = entry
            
            # Create dummy files
            os.makedirs(os.path.dirname(entry.file_path), exist_ok=True)
            with open(entry.file_path, 'wb') as f:
                f.write(b'dummy')
            with open(entry.metadata_path, 'w') as f:
                f.write('{}')
        
        # Test cache requests
        start_time = time.time()
        for model_name, version in test_models:
            cache_instance.is_cached(model_name, version)
        request_time = time.time() - start_time
        
        # Get hit rate metrics
        metrics = cache_instance.get_cache_hit_rate_metrics()
        
        print(f"   ✓ Processed {len(test_models)} requests in {request_time*1000:.2f}ms")
        print(f"   ✓ Average request time: {(request_time/len(test_models))*1000:.2f}ms")
        print(f"   ✓ Overall hit rate: {metrics['overall_statistics']['hit_rate']:.1%}")
        print(f"   ✓ Total hits: {metrics['overall_statistics']['total_hits']}")
        print(f"   ✓ Total misses: {metrics['overall_statistics']['total_misses']}")
        
        # Validate performance
        assert request_time < 0.1, "Cache requests should be fast"
        assert metrics['overall_statistics']['hit_rate'] > 0.4, "Should have reasonable hit rate"
        assert 'model_specific_rates' in metrics
        assert 'performance_insights' in metrics
    
    @pytest.mark.asyncio
    async def test_cache_lookup_performance(self, cache_instance):
        """Test cache lookup performance under load."""
        print("\n⚡ Testing cache lookup performance...")
        
        # Add multiple models to cache
        num_models = 100
        for i in range(num_models):
            model_name = f"model-{i}"
            cache_key = f"{model_name}:v1.0"
            entry = ModelCacheEntry(
                model_name=model_name,
                model_version="v1.0",
                file_path=os.path.join(cache_instance.config.cache_dir, f"{model_name}.bin"),
                metadata_path=os.path.join(cache_instance.config.cache_dir, f"{model_name}.json"),
                size_bytes=1024 * 1024,
                checksum="abc123",
                download_time=datetime.now(),
                last_accessed=datetime.now(),
                status=CacheStatus.CACHED
            )
            cache_instance.cache_entries[cache_key] = entry
            
            # Create dummy files
            os.makedirs(os.path.dirname(entry.file_path), exist_ok=True)
            with open(entry.file_path, 'wb') as f:
                f.write(b'dummy')
            with open(entry.metadata_path, 'w') as f:
                f.write('{}')
        
        # Test lookup performance
        lookup_times = []
        for i in range(1000):
            model_idx = i % num_models
            model_name = f"model-{model_idx}"
            
            start = time.time()
            cache_instance.is_cached(model_name, "v1.0")
            lookup_times.append(time.time() - start)
        
        avg_time = statistics.mean(lookup_times)
        p95_time = statistics.quantiles(lookup_times, n=20)[18]  # 95th percentile
        p99_time = statistics.quantiles(lookup_times, n=100)[98]  # 99th percentile
        
        print(f"   ✓ Performed 1000 lookups across {num_models} models")
        print(f"   ✓ Average lookup time: {avg_time*1000:.3f}ms")
        print(f"   ✓ P95 lookup time: {p95_time*1000:.3f}ms")
        print(f"   ✓ P99 lookup time: {p99_time*1000:.3f}ms")
        
        # Validate performance
        assert avg_time < 0.001, "Average lookup should be under 1ms"
        assert p95_time < 0.005, "P95 lookup should be under 5ms"
        assert p99_time < 0.010, "P99 lookup should be under 10ms"
    
    @pytest.mark.asyncio
    async def test_concurrent_cache_access(self, cache_instance):
        """Test concurrent cache access performance."""
        print("\n🔄 Testing concurrent cache access...")
        
        # Add models to cache
        for i in range(10):
            model_name = f"model-{i}"
            cache_key = f"{model_name}:v1.0"
            entry = ModelCacheEntry(
                model_name=model_name,
                model_version="v1.0",
                file_path=os.path.join(cache_instance.config.cache_dir, f"{model_name}.bin"),
                metadata_path=os.path.join(cache_instance.config.cache_dir, f"{model_name}.json"),
                size_bytes=1024 * 1024,
                checksum="abc123",
                download_time=datetime.now(),
                last_accessed=datetime.now(),
                status=CacheStatus.CACHED
            )
            cache_instance.cache_entries[cache_key] = entry
            
            # Create dummy files
            os.makedirs(os.path.dirname(entry.file_path), exist_ok=True)
            with open(entry.file_path, 'wb') as f:
                f.write(b'dummy')
            with open(entry.metadata_path, 'w') as f:
                f.write('{}')
        
        # Test concurrent access
        async def access_cache(worker_id: int, num_requests: int):
            times = []
            for i in range(num_requests):
                model_idx = (worker_id + i) % 10
                model_name = f"model-{model_idx}"
                
                start = time.time()
                await cache_instance.get_cached_model_path(model_name, "v1.0")
                times.append(time.time() - start)
            return times
        
        # Run concurrent workers
        num_workers = 10
        requests_per_worker = 100
        
        start_time = time.time()
        tasks = [access_cache(i, requests_per_worker) for i in range(num_workers)]
        results = await asyncio.gather(*tasks)
        total_time = time.time() - start_time
        
        # Analyze results
        all_times = [t for worker_times in results for t in worker_times]
        avg_time = statistics.mean(all_times)
        total_requests = num_workers * requests_per_worker
        throughput = total_requests / total_time
        
        print(f"   ✓ {num_workers} workers, {requests_per_worker} requests each")
        print(f"   ✓ Total requests: {total_requests}")
        print(f"   ✓ Total time: {total_time:.2f}s")
        print(f"   ✓ Throughput: {throughput:.0f} requests/sec")
        print(f"   ✓ Average latency: {avg_time*1000:.2f}ms")
        
        # Validate performance
        assert throughput > 100, "Should handle >100 requests/sec"
        assert avg_time < 0.1, "Average latency should be under 100ms"


class TestCacheReliability:
    """Test cache reliability and correctness."""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create temporary cache directory."""
        temp_dir = tempfile.mkdtemp(prefix="cache_rel_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest_asyncio.fixture
    async def cache_instance(self, temp_cache_dir):
        """Create cache instance for testing."""
        config = CacheConfig(
            cache_dir=temp_cache_dir,
            max_cache_size_gb=1.0,
            validation_enabled=True
        )
        cache = ModelCache(config)
        await cache.initialize()
        yield cache
        await cache.shutdown()
    
    @pytest.mark.asyncio
    async def test_cache_validation_reliability(self, cache_instance):
        """Test cache validation detects corruption."""
        print("\n🔍 Testing cache validation reliability...")
        
        # Add a valid entry
        model_name = "test-model"
        cache_key = f"{model_name}:v1.0"
        file_path = os.path.join(cache_instance.config.cache_dir, "models", f"{model_name}.bin")
        metadata_path = os.path.join(cache_instance.config.cache_dir, "metadata", f"{cache_key}.json")
        
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
        
        # Write test data
        test_data = b"test model data" * 1000
        with open(file_path, 'wb') as f:
            f.write(test_data)
        
        # Calculate checksum
        import hashlib
        checksum = hashlib.sha256(test_data).hexdigest()
        
        entry = ModelCacheEntry(
            model_name=model_name,
            model_version="v1.0",
            file_path=file_path,
            metadata_path=metadata_path,
            size_bytes=len(test_data),
            checksum=checksum,
            download_time=datetime.now(),
            last_accessed=datetime.now(),
            status=CacheStatus.CACHED
        )
        cache_instance.cache_entries[cache_key] = entry
        
        with open(metadata_path, 'w') as f:
            f.write('{}')
        
        # Test 1: Valid entry should pass validation
        is_valid = await cache_instance.validate_cache_entry(model_name, "v1.0")
        print(f"   ✓ Valid entry validation: {is_valid}")
        assert is_valid, "Valid entry should pass validation"
        
        # Test 2: Corrupted file should fail validation
        with open(file_path, 'wb') as f:
            f.write(b"corrupted data")
        
        is_valid = await cache_instance.validate_cache_entry(model_name, "v1.0")
        print(f"   ✓ Corrupted entry validation: {is_valid}")
        assert not is_valid, "Corrupted entry should fail validation"
        assert entry.status == CacheStatus.CORRUPTED
        
        # Test 3: Missing file should fail validation
        os.remove(file_path)
        is_valid = await cache_instance.validate_cache_entry(model_name, "v1.0")
        print(f"   ✓ Missing file validation: {is_valid}")
        assert not is_valid, "Missing file should fail validation"
    
    @pytest.mark.asyncio
    async def test_cache_cleanup_reliability(self, cache_instance):
        """Test cache cleanup removes old entries correctly."""
        print("\n🧹 Testing cache cleanup reliability...")
        
        # Add entries with different ages
        now = datetime.now()
        test_entries = [
            ("old-model-1", now - timedelta(days=40)),  # Should be removed
            ("old-model-2", now - timedelta(days=35)),  # Should be removed
            ("recent-model-1", now - timedelta(days=5)),  # Should be kept
            ("recent-model-2", now - timedelta(days=2)),  # Should be kept
        ]
        
        for model_name, download_time in test_entries:
            cache_key = f"{model_name}:v1.0"
            file_path = os.path.join(cache_instance.config.cache_dir, "models", f"{model_name}.bin")
            metadata_path = os.path.join(cache_instance.config.cache_dir, "metadata", f"{cache_key}.json")
            
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
            
            with open(file_path, 'wb') as f:
                f.write(b'dummy')
            with open(metadata_path, 'w') as f:
                f.write('{}')
            
            entry = ModelCacheEntry(
                model_name=model_name,
                model_version="v1.0",
                file_path=file_path,
                metadata_path=metadata_path,
                size_bytes=1024,
                checksum="abc123",
                download_time=download_time,
                last_accessed=download_time,
                status=CacheStatus.CACHED
            )
            cache_instance.cache_entries[cache_key] = entry
        
        print(f"   ✓ Created {len(test_entries)} cache entries")
        
        # Run cleanup
        cleanup_stats = await cache_instance.cleanup_cache()
        
        print(f"   ✓ Cleanup removed {cleanup_stats['entries_removed']} entries")
        print(f"   ✓ Freed {cleanup_stats['bytes_freed']} bytes")
        
        # Verify old entries removed
        assert not cache_instance.is_cached("old-model-1", "v1.0")
        assert not cache_instance.is_cached("old-model-2", "v1.0")
        
        # Verify recent entries kept
        assert cache_instance.is_cached("recent-model-1", "v1.0")
        assert cache_instance.is_cached("recent-model-2", "v1.0")
        
        print(f"   ✓ Old entries removed, recent entries preserved")
    
    @pytest.mark.asyncio
    async def test_cache_persistence_reliability(self, cache_instance, temp_cache_dir):
        """Test cache index persistence and recovery."""
        print("\n💾 Testing cache persistence reliability...")
        
        # Add entries
        for i in range(5):
            model_name = f"model-{i}"
            cache_key = f"{model_name}:v1.0"
            file_path = os.path.join(temp_cache_dir, "models", f"{model_name}.bin")
            metadata_path = os.path.join(temp_cache_dir, "metadata", f"{cache_key}.json")
            
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
            
            with open(file_path, 'wb') as f:
                f.write(b'dummy')
            with open(metadata_path, 'w') as f:
                f.write('{}')
            
            entry = ModelCacheEntry(
                model_name=model_name,
                model_version="v1.0",
                file_path=file_path,
                metadata_path=metadata_path,
                size_bytes=1024,
                checksum="abc123",
                download_time=datetime.now(),
                last_accessed=datetime.now(),
                status=CacheStatus.CACHED
            )
            cache_instance.cache_entries[cache_key] = entry
        
        # Save index
        await cache_instance._save_cache_index()
        print(f"   ✓ Saved cache index with {len(cache_instance.cache_entries)} entries")
        
        # Shutdown and create new instance
        await cache_instance.shutdown()
        
        # Create new cache instance
        config = CacheConfig(cache_dir=temp_cache_dir)
        new_cache = ModelCache(config)
        await new_cache.initialize()
        
        print(f"   ✓ Loaded cache index with {len(new_cache.cache_entries)} entries")
        
        # Verify entries recovered
        assert len(new_cache.cache_entries) == 5
        for i in range(5):
            assert new_cache.is_cached(f"model-{i}", "v1.0")
        
        print(f"   ✓ All entries successfully recovered")
        
        await new_cache.shutdown()


class TestCacheWarmingPerformance:
    """Test cache warming performance."""
    
    @pytest.fixture
    def temp_cache_dir(self):
        """Create temporary cache directory."""
        temp_dir = tempfile.mkdtemp(prefix="cache_warm_test_")
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    @pytest_asyncio.fixture
    async def cache_warmer(self, temp_cache_dir):
        """Create cache warmer for testing."""
        # Create cache
        cache_config = CacheConfig(
            cache_dir=temp_cache_dir,
            validation_enabled=False
        )
        cache = ModelCache(cache_config)
        await cache.initialize()
        
        # Create warmer
        warming_config = WarmingConfig(
            max_concurrent_warming=2,
            model_urls={}  # Empty for testing
        )
        warmer = CacheWarmer(warming_config)
        warmer.model_cache = cache
        
        yield warmer
        
        await warmer.shutdown()
        await cache.shutdown()
    
    @pytest.mark.asyncio
    async def test_warming_strategy_selection(self, cache_warmer):
        """Test different warming strategies."""
        print("\n🔥 Testing cache warming strategies...")
        
        # Mock model manager
        from src.multimodal_librarian.models.model_manager import ModelPriority
        
        mock_configs = {
            "model-essential": Mock(priority=ModelPriority.ESSENTIAL),
            "model-standard": Mock(priority=ModelPriority.STANDARD),
            "model-advanced": Mock(priority=ModelPriority.ADVANCED),
        }
        
        cache_warmer.model_manager = Mock()
        cache_warmer.model_manager.model_configs = mock_configs
        
        # Test essential only strategy
        models = await cache_warmer._get_models_to_warm(WarmingStrategy.ESSENTIAL_ONLY)
        print(f"   ✓ Essential only: {len(models)} models")
        assert len(models) == 1
        
        # Test priority based strategy
        models = await cache_warmer._get_models_to_warm(WarmingStrategy.PRIORITY_BASED)
        print(f"   ✓ Priority based: {len(models)} models")
        assert len(models) == 3
        
        # Test usage based strategy
        models = await cache_warmer._get_models_to_warm(WarmingStrategy.USAGE_BASED)
        print(f"   ✓ Usage based: {len(models)} models")
        assert len(models) > 0
    
    @pytest.mark.asyncio
    async def test_warming_statistics(self, cache_warmer):
        """Test warming statistics tracking."""
        print("\n📊 Testing warming statistics...")
        
        # Get initial stats
        stats = cache_warmer.get_warming_statistics()
        print(f"   ✓ Initial warming sessions: {stats['warming_stats']['warming_sessions']}")
        assert stats['warming_stats']['warming_sessions'] == 0
        
        # Update stats manually for testing
        cache_warmer.stats['warming_sessions'] = 5
        cache_warmer.stats['models_warmed'] = 15
        cache_warmer.stats['warming_failures'] = 2
        cache_warmer.stats['total_warming_time'] = 120.5
        
        stats = cache_warmer.get_warming_statistics()
        print(f"   ✓ Warming sessions: {stats['warming_stats']['warming_sessions']}")
        print(f"   ✓ Models warmed: {stats['warming_stats']['models_warmed']}")
        print(f"   ✓ Failures: {stats['warming_stats']['warming_failures']}")
        print(f"   ✓ Total time: {stats['warming_stats']['total_warming_time']:.1f}s")
        
        assert stats['warming_stats']['warming_sessions'] == 5
        assert stats['warming_stats']['models_warmed'] == 15


@pytest.mark.asyncio
async def test_end_to_end_cache_performance():
    """End-to-end cache performance test."""
    print("\n🎯 Running end-to-end cache performance test...")
    
    temp_dir = tempfile.mkdtemp(prefix="cache_e2e_test_")
    
    try:
        # Create cache
        config = CacheConfig(
            cache_dir=temp_dir,
            max_cache_size_gb=1.0,
            validation_enabled=True
        )
        cache = ModelCache(config)
        await cache.initialize()
        
        # Add test entries
        num_models = 50
        for i in range(num_models):
            model_name = f"model-{i}"
            cache_key = f"{model_name}:v1.0"
            file_path = os.path.join(temp_dir, "models", f"{model_name}.bin")
            metadata_path = os.path.join(temp_dir, "metadata", f"{cache_key}.json")
            
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
            
            with open(file_path, 'wb') as f:
                f.write(b'dummy' * 1000)
            with open(metadata_path, 'w') as f:
                f.write('{}')
            
            entry = ModelCacheEntry(
                model_name=model_name,
                model_version="v1.0",
                file_path=file_path,
                metadata_path=metadata_path,
                size_bytes=5000,
                checksum="abc123",
                download_time=datetime.now(),
                last_accessed=datetime.now(),
                status=CacheStatus.CACHED
            )
            cache.cache_entries[cache_key] = entry
        
        # Simulate workload
        start_time = time.time()
        for _ in range(1000):
            model_idx = _ % num_models
            cache.is_cached(f"model-{model_idx}", "v1.0")
        workload_time = time.time() - start_time
        
        # Get statistics
        stats = cache.get_cache_statistics()
        metrics = cache.get_cache_hit_rate_metrics()
        
        print(f"   ✓ Processed 1000 requests in {workload_time:.2f}s")
        print(f"   ✓ Throughput: {1000/workload_time:.0f} requests/sec")
        print(f"   ✓ Cache hit rate: {metrics['overall_statistics']['hit_rate']:.1%}")
        print(f"   ✓ Total cache size: {stats['total_size_mb']:.1f} MB")
        print(f"   ✓ Cache effectiveness: {metrics['cache_effectiveness']['grade']}")
        
        # Validate performance
        assert workload_time < 1.0, "Should process 1000 requests in under 1 second"
        assert metrics['overall_statistics']['hit_rate'] > 0.9, "Should have high hit rate"
        
        await cache.shutdown()
        
        print("   ✓ End-to-end test completed successfully")
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
