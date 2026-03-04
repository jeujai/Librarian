#!/usr/bin/env python3
"""
Integration test for cache hit rate monitoring with startup metrics.

This test verifies that the cache hit rate monitoring integrates properly
with the existing startup metrics collection system.
"""

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector, ModelLoadingMetric
from multimodal_librarian.startup.phase_manager import StartupPhaseManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_cache_hit_rate_integration():
    """Test cache hit rate monitoring integration with startup metrics."""
    logger.info("Testing Cache Hit Rate Integration with Startup Metrics")
    
    try:
        # Initialize phase manager and metrics collector
        phase_manager = StartupPhaseManager()
        metrics_collector = StartupMetricsCollector(phase_manager)
        await metrics_collector.start_collection()
        
        # Simulate realistic model loading scenarios with cache data
        scenarios = [
            # Scenario 1: First startup - all cache misses
            {
                "name": "text-embedding-small",
                "priority": "essential",
                "duration": 45.0,
                "cache_hit": False,
                "cache_source": None
            },
            {
                "name": "chat-model-base", 
                "priority": "essential",
                "duration": 120.0,
                "cache_hit": False,
                "cache_source": None
            },
            # Scenario 2: Second startup - some cache hits
            {
                "name": "text-embedding-small",
                "priority": "essential", 
                "duration": 8.0,
                "cache_hit": True,
                "cache_source": "efs"
            },
            {
                "name": "document-processor",
                "priority": "standard",
                "duration": 90.0,
                "cache_hit": False,
                "cache_source": None
            },
            # Scenario 3: Third startup - more cache hits
            {
                "name": "text-embedding-small",
                "priority": "essential",
                "duration": 5.0,
                "cache_hit": True,
                "cache_source": "efs"
            },
            {
                "name": "chat-model-base",
                "priority": "essential",
                "duration": 12.0,
                "cache_hit": True,
                "cache_source": "local"
            },
            {
                "name": "document-processor",
                "priority": "standard",
                "duration": 15.0,
                "cache_hit": True,
                "cache_source": "efs"
            }
        ]
        
        # Create model loading metrics from scenarios
        base_time = datetime.now() - timedelta(minutes=10)
        
        for i, scenario in enumerate(scenarios):
            start_time = base_time + timedelta(minutes=i)
            end_time = start_time + timedelta(seconds=scenario["duration"])
            
            metric = ModelLoadingMetric(
                model_name=scenario["name"],
                priority=scenario["priority"],
                start_time=start_time,
                end_time=end_time,
                duration_seconds=scenario["duration"],
                success=True,
                cache_hit=scenario["cache_hit"],
                cache_source=scenario["cache_source"]
            )
            
            # Add to metrics collector history
            model_name = metric.model_name
            if model_name not in metrics_collector.model_loading_history:
                metrics_collector.model_loading_history[model_name] = []
            metrics_collector.model_loading_history[model_name].append(metric)
        
        # Test 1: Get cache hit rate monitoring data
        logger.info("\n" + "="*60)
        logger.info("CACHE HIT RATE MONITORING DATA")
        logger.info("="*60)
        
        cache_monitoring = metrics_collector.get_cache_hit_rate_monitoring()
        
        # Validate key metrics
        overall_stats = cache_monitoring["overall_statistics"]
        assert overall_stats["total_model_loads"] == 7, f"Expected 7 loads, got {overall_stats['total_model_loads']}"
        assert overall_stats["cache_hits"] == 4, f"Expected 4 hits, got {overall_stats['cache_hits']}"
        assert overall_stats["cache_misses"] == 3, f"Expected 3 misses, got {overall_stats['cache_misses']}"
        
        expected_hit_rate = 4/7  # 57.1%
        actual_hit_rate = overall_stats["overall_hit_rate"]
        assert abs(actual_hit_rate - expected_hit_rate) < 0.01, f"Expected hit rate ~{expected_hit_rate:.3f}, got {actual_hit_rate:.3f}"
        
        logger.info(f"✅ Overall hit rate: {actual_hit_rate:.1%}")
        logger.info(f"✅ Total loads: {overall_stats['total_model_loads']}")
        logger.info(f"✅ Cache hits: {overall_stats['cache_hits']}")
        logger.info(f"✅ Cache misses: {overall_stats['cache_misses']}")
        
        # Test 2: Verify model-specific performance
        model_performance = cache_monitoring["model_performance"]
        
        # text-embedding-small: 2 hits out of 3 loads = 66.7%
        text_embed_perf = model_performance["text-embedding-small"]
        assert text_embed_perf["total_loads"] == 3, "text-embedding-small should have 3 loads"
        assert text_embed_perf["cache_hits"] == 2, "text-embedding-small should have 2 hits"
        assert abs(text_embed_perf["overall_hit_rate"] - 2/3) < 0.01, "text-embedding-small hit rate should be ~66.7%"
        
        # chat-model-base: 1 hit out of 2 loads = 50%
        chat_perf = model_performance["chat-model-base"]
        assert chat_perf["total_loads"] == 2, "chat-model-base should have 2 loads"
        assert chat_perf["cache_hits"] == 1, "chat-model-base should have 1 hit"
        assert abs(chat_perf["overall_hit_rate"] - 0.5) < 0.01, "chat-model-base hit rate should be 50%"
        
        logger.info(f"✅ text-embedding-small hit rate: {text_embed_perf['overall_hit_rate']:.1%}")
        logger.info(f"✅ chat-model-base hit rate: {chat_perf['overall_hit_rate']:.1%}")
        
        # Test 3: Verify cache source analysis
        cache_source_analysis = cache_monitoring["cache_source_analysis"]
        assert "efs" in cache_source_analysis, "Should have EFS cache source data"
        assert "local" in cache_source_analysis, "Should have local cache source data"
        
        efs_hits = cache_source_analysis["efs"]["hits"]
        local_hits = cache_source_analysis["local"]["hits"]
        assert efs_hits == 3, f"Expected 3 EFS hits, got {efs_hits}"
        assert local_hits == 1, f"Expected 1 local hit, got {local_hits}"
        
        logger.info(f"✅ EFS cache hits: {efs_hits}")
        logger.info(f"✅ Local cache hits: {local_hits}")
        
        # Test 4: Verify effectiveness assessment
        effectiveness = cache_monitoring["effectiveness_assessment"]
        assert "overall_score" in effectiveness, "Should have overall effectiveness score"
        assert "grade" in effectiveness, "Should have effectiveness grade"
        
        logger.info(f"✅ Cache effectiveness score: {effectiveness['overall_score']:.1f}/100")
        logger.info(f"✅ Cache effectiveness grade: {effectiveness['grade']}")
        
        # Test 5: Test cache performance metrics method
        logger.info("\n" + "="*60)
        logger.info("CACHE PERFORMANCE METRICS")
        logger.info("="*60)
        
        cache_performance = metrics_collector.get_cache_performance_metrics()
        
        # Verify cache speedup calculation
        assert "cache_speedup_factor" in cache_performance, "Should have cache speedup factor"
        speedup = cache_performance["cache_speedup_factor"]
        
        # Calculate expected speedup: avg miss time / avg hit time
        # Miss times: 45.0, 120.0, 90.0 -> avg = 85.0
        # Hit times: 8.0, 5.0, 12.0, 15.0 -> avg = 10.0
        # Expected speedup: 85.0 / 10.0 = 8.5
        expected_speedup = 85.0 / 10.0
        assert abs(speedup - expected_speedup) < 0.1, f"Expected speedup ~{expected_speedup}, got {speedup}"
        
        logger.info(f"✅ Cache speedup factor: {speedup:.1f}x")
        
        # Test 6: Verify time-based hit rates
        time_based_rates = cache_performance["time_based_hit_rates"]
        for period in ["last_hour", "last_6_hours", "last_24_hours"]:
            assert period in time_based_rates, f"Should have {period} hit rate data"
            period_data = time_based_rates[period]
            assert period_data["hit_rate"] == expected_hit_rate, f"{period} hit rate should match overall"
        
        logger.info("✅ Time-based hit rates verified")
        
        # Test 7: Print comprehensive results
        logger.info("\n" + "="*60)
        logger.info("COMPREHENSIVE CACHE MONITORING RESULTS")
        logger.info("="*60)
        
        print(json.dumps({
            "cache_hit_rate_monitoring": {
                "overall_hit_rate": cache_monitoring["overall_statistics"]["overall_hit_rate"],
                "effectiveness_grade": cache_monitoring["effectiveness_assessment"]["grade"],
                "model_performance": {
                    name: {
                        "hit_rate": data["overall_hit_rate"],
                        "total_loads": data["total_loads"],
                        "avg_hit_time": data["avg_hit_time_seconds"],
                        "avg_miss_time": data["avg_miss_time_seconds"]
                    }
                    for name, data in cache_monitoring["model_performance"].items()
                },
                "cache_sources": cache_monitoring["cache_source_analysis"],
                "recommendations": cache_monitoring["recommendations"]
            },
            "cache_performance_metrics": {
                "hit_rate": cache_performance["cache_hit_rate"],
                "speedup_factor": cache_performance["cache_speedup_factor"],
                "effectiveness": cache_performance["cache_effectiveness"]
            }
        }, indent=2))
        
        logger.info("\n✅ Cache Hit Rate Integration Test PASSED")
        return True
        
    except Exception as e:
        logger.error(f"❌ Cache Hit Rate Integration Test FAILED: {e}")
        raise
    
    finally:
        # Cleanup
        await metrics_collector.stop_collection()


async def main():
    """Run the cache hit rate integration test."""
    logger.info("Starting Cache Hit Rate Integration Test")
    logger.info("="*80)
    
    try:
        success = await test_cache_hit_rate_integration()
        
        if success:
            logger.info("\n" + "="*80)
            logger.info("🎉 CACHE HIT RATE INTEGRATION TEST PASSED!")
            logger.info("="*80)
            return True
        
    except Exception as e:
        logger.error(f"\n❌ CACHE HIT RATE INTEGRATION TEST FAILED: {e}")
        logger.error("="*80)
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)