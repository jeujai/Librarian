#!/usr/bin/env python3
"""
Test script for cache hit rate monitoring functionality.

This script tests the enhanced cache hit rate monitoring capabilities
added to the startup metrics and model cache systems.
"""

import asyncio
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from multimodal_librarian.cache.model_cache import ModelCache, CacheConfig
from multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector
from multimodal_librarian.startup.phase_manager import StartupPhaseManager, StartupPhase

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_model_cache_hit_rate_monitoring():
    """Test the model cache hit rate monitoring functionality."""
    logger.info("Testing Model Cache Hit Rate Monitoring")
    
    # Create a temporary cache directory
    import tempfile
    temp_dir = tempfile.mkdtemp(prefix="test_cache_")
    
    try:
        # Initialize cache with test configuration
        config = CacheConfig(
            cache_dir=temp_dir,
            max_cache_size_gb=1.0,
            max_model_age_days=1,
            download_timeout_seconds=30,
            max_concurrent_downloads=2
        )
        
        cache = ModelCache(config)
        await cache.initialize()
        
        # Simulate cache requests to generate hit rate data
        test_models = [
            ("text-embedding-small", "v1.0"),
            ("chat-model-base", "v2.1"),
            ("search-index", "latest"),
            ("document-processor", "v1.5")
        ]
        
        logger.info("Simulating cache requests...")
        
        # First round - all misses (models not cached)
        for model_name, version in test_models:
            is_cached = cache.is_cached(model_name, version)
            logger.info(f"Cache check for {model_name}:{version} - {'HIT' if is_cached else 'MISS'}")
        
        # Add some models to cache (simulate successful downloads)
        # Note: In a real scenario, these would be actual model files
        for i, (model_name, version) in enumerate(test_models[:2]):  # Cache first 2 models
            cache_key = f"{model_name}:{version}"
            # Simulate a cached entry (this is a simplified version)
            logger.info(f"Simulating cached model: {cache_key}")
        
        # Second round - some hits, some misses
        await asyncio.sleep(0.1)  # Small delay to show time progression
        for model_name, version in test_models:
            is_cached = cache.is_cached(model_name, version)
            logger.info(f"Cache check for {model_name}:{version} - {'HIT' if is_cached else 'MISS'}")
        
        # Third round - more requests to build up statistics
        for _ in range(3):
            await asyncio.sleep(0.05)
            for model_name, version in test_models[:3]:  # Focus on first 3 models
                is_cached = cache.is_cached(model_name, version)
        
        # Get cache hit rate metrics
        logger.info("\n" + "="*60)
        logger.info("CACHE HIT RATE METRICS")
        logger.info("="*60)
        
        hit_rate_metrics = cache.get_cache_hit_rate_metrics()
        print(json.dumps(hit_rate_metrics, indent=2, default=str))
        
        # Get overall cache statistics
        logger.info("\n" + "="*60)
        logger.info("OVERALL CACHE STATISTICS")
        logger.info("="*60)
        
        cache_stats = cache.get_cache_statistics()
        print(json.dumps(cache_stats, indent=2, default=str))
        
        # Test results validation
        overall_stats = hit_rate_metrics["overall_statistics"]
        assert overall_stats["total_requests"] > 0, "Should have recorded cache requests"
        assert "hit_rate" in overall_stats, "Should have calculated hit rate"
        assert "model_specific_rates" in hit_rate_metrics, "Should have model-specific rates"
        
        logger.info("\n✅ Model Cache Hit Rate Monitoring Test PASSED")
        
    except Exception as e:
        logger.error(f"❌ Model Cache Hit Rate Monitoring Test FAILED: {e}")
        raise
    
    finally:
        # Cleanup
        await cache.shutdown()
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


async def test_startup_metrics_cache_monitoring():
    """Test the startup metrics cache monitoring functionality."""
    logger.info("Testing Startup Metrics Cache Monitoring")
    
    try:
        # Create a mock phase manager
        phase_manager = StartupPhaseManager()
        
        # Initialize metrics collector
        metrics_collector = StartupMetricsCollector(phase_manager)
        await metrics_collector.start_collection()
        
        # Simulate some model loading metrics with cache data
        from multimodal_librarian.monitoring.startup_metrics import ModelLoadingMetric
        
        # Create sample model loading metrics with cache information
        sample_metrics = [
            ModelLoadingMetric(
                model_name="text-embedding-small",
                priority="essential",
                start_time=datetime.now() - timedelta(minutes=5),
                end_time=datetime.now() - timedelta(minutes=4, seconds=30),
                duration_seconds=30.0,
                success=True,
                cache_hit=True,
                cache_source="efs"
            ),
            ModelLoadingMetric(
                model_name="chat-model-base",
                priority="essential", 
                start_time=datetime.now() - timedelta(minutes=4),
                end_time=datetime.now() - timedelta(minutes=2),
                duration_seconds=120.0,
                success=True,
                cache_hit=False
            ),
            ModelLoadingMetric(
                model_name="document-processor",
                priority="standard",
                start_time=datetime.now() - timedelta(minutes=3),
                end_time=datetime.now() - timedelta(minutes=1, seconds=30),
                duration_seconds=90.0,
                success=True,
                cache_hit=True,
                cache_source="local"
            ),
            ModelLoadingMetric(
                model_name="text-embedding-small",
                priority="essential",
                start_time=datetime.now() - timedelta(minutes=2),
                end_time=datetime.now() - timedelta(minutes=1, seconds=45),
                duration_seconds=15.0,
                success=True,
                cache_hit=True,
                cache_source="efs"
            )
        ]
        
        # Add metrics to the collector's history
        for metric in sample_metrics:
            model_name = metric.model_name
            if model_name not in metrics_collector.model_loading_history:
                metrics_collector.model_loading_history[model_name] = []
            metrics_collector.model_loading_history[model_name].append(metric)
        
        # Test cache hit rate monitoring
        logger.info("\n" + "="*60)
        logger.info("STARTUP METRICS CACHE HIT RATE MONITORING")
        logger.info("="*60)
        
        cache_monitoring = metrics_collector.get_cache_hit_rate_monitoring()
        print(json.dumps(cache_monitoring, indent=2, default=str))
        
        # Test cache performance metrics
        logger.info("\n" + "="*60)
        logger.info("CACHE PERFORMANCE METRICS")
        logger.info("="*60)
        
        cache_performance = metrics_collector.get_cache_performance_metrics()
        print(json.dumps(cache_performance, indent=2, default=str))
        
        # Validate results
        assert "overall_statistics" in cache_monitoring, "Should have overall statistics"
        assert "model_performance" in cache_monitoring, "Should have model performance data"
        assert "effectiveness_assessment" in cache_monitoring, "Should have effectiveness assessment"
        assert "recommendations" in cache_monitoring, "Should have recommendations"
        
        # Check that we have cache hit rate data
        overall_stats = cache_monitoring["overall_statistics"]
        assert overall_stats["cache_hits"] > 0, "Should have recorded cache hits"
        assert overall_stats["overall_hit_rate"] > 0, "Should have calculated hit rate"
        
        logger.info("\n✅ Startup Metrics Cache Monitoring Test PASSED")
        
    except Exception as e:
        logger.error(f"❌ Startup Metrics Cache Monitoring Test FAILED: {e}")
        raise
    
    finally:
        # Cleanup
        await metrics_collector.stop_collection()


async def test_cache_hit_rate_alerts():
    """Test cache hit rate alerting functionality."""
    logger.info("Testing Cache Hit Rate Alerts")
    
    try:
        # Create metrics collector
        phase_manager = StartupPhaseManager()
        metrics_collector = StartupMetricsCollector(phase_manager)
        
        # Create test data with low hit rates to trigger alerts
        from multimodal_librarian.monitoring.startup_metrics import ModelLoadingMetric
        
        # Create metrics with low cache hit rate
        low_hit_rate_metrics = []
        for i in range(10):
            metric = ModelLoadingMetric(
                model_name="problematic-model",
                priority="standard",
                start_time=datetime.now() - timedelta(minutes=10-i),
                end_time=datetime.now() - timedelta(minutes=9-i),
                duration_seconds=60.0,
                success=True,
                cache_hit=(i < 2)  # Only 2 out of 10 are cache hits (20% hit rate)
            )
            low_hit_rate_metrics.append(metric)
        
        # Add to history
        metrics_collector.model_loading_history["problematic-model"] = low_hit_rate_metrics
        
        # Get monitoring data with alerts
        cache_monitoring = metrics_collector.get_cache_hit_rate_monitoring()
        
        logger.info("\n" + "="*60)
        logger.info("CACHE HIT RATE ALERTS")
        logger.info("="*60)
        
        alerts = cache_monitoring.get("alerts", [])
        print(json.dumps(alerts, indent=2, default=str))
        
        # Validate alerts
        assert len(alerts) > 0, "Should have generated alerts for low hit rate"
        
        # Check for specific alert types
        alert_types = [alert["type"] for alert in alerts]
        assert "low_hit_rate" in alert_types or "model_low_hit_rate" in alert_types, "Should have low hit rate alerts"
        
        logger.info(f"\n✅ Generated {len(alerts)} cache hit rate alerts")
        logger.info("✅ Cache Hit Rate Alerts Test PASSED")
        
    except Exception as e:
        logger.error(f"❌ Cache Hit Rate Alerts Test FAILED: {e}")
        raise


async def main():
    """Run all cache hit rate monitoring tests."""
    logger.info("Starting Cache Hit Rate Monitoring Tests")
    logger.info("="*80)
    
    try:
        # Test 1: Model Cache Hit Rate Monitoring
        await test_model_cache_hit_rate_monitoring()
        
        # Test 2: Startup Metrics Cache Monitoring
        await test_startup_metrics_cache_monitoring()
        
        # Test 3: Cache Hit Rate Alerts
        await test_cache_hit_rate_alerts()
        
        logger.info("\n" + "="*80)
        logger.info("🎉 ALL CACHE HIT RATE MONITORING TESTS PASSED!")
        logger.info("="*80)
        
        return True
        
    except Exception as e:
        logger.error(f"\n❌ CACHE HIT RATE MONITORING TESTS FAILED: {e}")
        logger.error("="*80)
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)