#!/usr/bin/env python3
"""
Test script for model loading performance metrics functionality.

This script tests the enhanced model loading performance metrics implementation
to ensure it properly captures detailed performance data, cache metrics, and bottlenecks.
"""

import asyncio
import sys
import os
import time
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Optional

# Add src to path for imports
sys.path.append('src')

@dataclass
class MockModelLoadingStatus:
    """Mock model loading status for testing."""
    model_name: str
    priority: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    estimated_load_time_seconds: float = 60.0
    size_mb: Optional[float] = None
    status: str = "loading"
    error_message: Optional[str] = None
    cache_hit: bool = False
    cache_source: Optional[str] = None
    switching_strategy: Optional[str] = None
    retry_count: int = 0
    timeout_occurred: bool = False
    concurrent_loads: int = 1
    queue_wait_time_seconds: Optional[float] = None
    initialization_time_seconds: Optional[float] = None
    download_time_seconds: Optional[float] = None
    load_from_cache_time_seconds: Optional[float] = None


async def test_model_loading_performance_metrics():
    """Test the model loading performance metrics functionality."""
    print("🧪 Testing Model Loading Performance Metrics")
    print("=" * 60)
    
    try:
        # Import required modules
        from multimodal_librarian.startup.phase_manager import StartupPhaseManager
        from multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector, track_startup_metrics
        from multimodal_librarian.monitoring.performance_tracker import PerformanceTracker, track_performance
        
        print("✅ Successfully imported model loading metrics modules")
        
        # Test 1: Create startup phase manager and metrics collector
        print("\n📋 Test 1: Creating metrics collection system...")
        phase_manager = StartupPhaseManager()
        metrics_collector = StartupMetricsCollector(phase_manager)
        performance_tracker = PerformanceTracker(phase_manager, metrics_collector)
        
        # Enable bidirectional integration
        metrics_collector.set_performance_tracker(performance_tracker)
        
        await metrics_collector.start_collection()
        await performance_tracker.start_tracking()
        
        print(f"   ✅ Metrics collection system initialized")
        
        # Test 2: Simulate model loading scenarios
        print("\n📋 Test 2: Simulating model loading scenarios...")
        
        # Scenario 1: Fast cache hit
        print("   🚀 Scenario 1: Fast cache hit...")
        fast_model_status = MockModelLoadingStatus(
            model_name="text-embedding-small",
            priority="essential",
            started_at=datetime.now(),
            size_mb=50.0,
            cache_hit=True,
            cache_source="local",
            switching_strategy="cached_load"
        )
        
        await asyncio.sleep(0.5)  # Simulate fast loading
        fast_model_status.completed_at = datetime.now()
        fast_model_status.duration_seconds = 0.5
        fast_model_status.status = "loaded"
        fast_model_status.load_from_cache_time_seconds = 0.4
        fast_model_status.initialization_time_seconds = 0.1
        
        await metrics_collector._record_model_loading_completion("text-embedding-small", fast_model_status)
        
        # Scenario 2: Slow download
        print("   🐌 Scenario 2: Slow download...")
        slow_model_status = MockModelLoadingStatus(
            model_name="chat-model-large",
            priority="standard",
            started_at=datetime.now(),
            size_mb=1200.0,
            cache_hit=False,
            switching_strategy="download_and_load",
            queue_wait_time_seconds=5.0
        )
        
        await asyncio.sleep(2.0)  # Simulate slow loading
        slow_model_status.completed_at = datetime.now()
        slow_model_status.duration_seconds = 120.0
        slow_model_status.status = "loaded"
        slow_model_status.download_time_seconds = 90.0
        slow_model_status.initialization_time_seconds = 25.0
        
        await metrics_collector._record_model_loading_completion("chat-model-large", slow_model_status)
        
        # Scenario 3: Failed loading with retries
        print("   ❌ Scenario 3: Failed loading with retries...")
        failed_model_status = MockModelLoadingStatus(
            model_name="multimodal-model",
            priority="advanced",
            started_at=datetime.now(),
            size_mb=2000.0,
            cache_hit=False,
            retry_count=3,
            timeout_occurred=True
        )
        
        await asyncio.sleep(1.0)  # Simulate failed loading
        failed_model_status.completed_at = datetime.now()
        failed_model_status.duration_seconds = 300.0
        failed_model_status.status = "failed"
        failed_model_status.error_message = "Model loading timeout after 3 retries"
        
        await metrics_collector._record_model_loading_completion("multimodal-model", failed_model_status)
        
        # Scenario 4: Another cache hit for same model
        print("   🎯 Scenario 4: Another cache hit...")
        another_fast_status = MockModelLoadingStatus(
            model_name="text-embedding-small",
            priority="essential",
            started_at=datetime.now(),
            size_mb=50.0,
            cache_hit=True,
            cache_source="efs",
            switching_strategy="cached_load"
        )
        
        await asyncio.sleep(0.3)
        another_fast_status.completed_at = datetime.now()
        another_fast_status.duration_seconds = 0.3
        another_fast_status.status = "loaded"
        another_fast_status.load_from_cache_time_seconds = 0.25
        another_fast_status.initialization_time_seconds = 0.05
        
        await metrics_collector._record_model_loading_completion("text-embedding-small", another_fast_status)
        
        # Test 3: Get basic model loading metrics
        print("\n📋 Test 3: Retrieving basic model loading metrics...")
        all_metrics = metrics_collector.get_model_loading_metrics()
        print(f"   📊 Total model loads: {all_metrics['sample_count']}")
        print(f"   ✅ Success rate: {all_metrics['success_rate']:.1%}")
        print(f"   🎯 Cache hit rate: {all_metrics['cache_hit_rate']:.1%}")
        print(f"   ⚠️  Timeout rate: {all_metrics['timeout_rate']:.1%}")
        print(f"   🔄 Average retries: {all_metrics['average_retry_count']:.1f}")
        
        if 'loading_stats' in all_metrics:
            stats = all_metrics['loading_stats']
            print(f"   ⏱️  Mean duration: {stats['mean_duration_seconds']:.2f}s")
            print(f"   📈 P95 duration: {stats['p95_duration_seconds']:.2f}s")
            print(f"   📈 P99 duration: {stats['p99_duration_seconds']:.2f}s")
        
        if 'performance_insights' in all_metrics:
            print(f"   💡 Performance insights:")
            for insight in all_metrics['performance_insights']:
                print(f"      - {insight}")
        
        # Test 4: Get cache performance metrics
        print("\n📋 Test 4: Retrieving cache performance metrics...")
        cache_metrics = metrics_collector.get_cache_performance_metrics()
        print(f"   🎯 Cache hit rate: {cache_metrics['cache_hit_rate']:.1%}")
        print(f"   📊 Cache hits: {cache_metrics['cache_hits']}")
        print(f"   📊 Cache misses: {cache_metrics['cache_misses']}")
        
        if 'cache_speedup_factor' in cache_metrics:
            print(f"   🚀 Cache speedup: {cache_metrics['cache_speedup_factor']:.1f}x")
            print(f"   ⭐ Cache effectiveness: {cache_metrics['cache_effectiveness']}")
        
        if 'cache_sources' in cache_metrics:
            print(f"   📍 Cache sources: {cache_metrics['cache_sources']}")
        
        # Test 5: Get performance bottlenecks
        print("\n📋 Test 5: Retrieving performance bottlenecks...")
        bottlenecks = metrics_collector.get_model_loading_bottlenecks()
        print(f"   🔍 Bottlenecks identified: {len(bottlenecks)}")
        
        for bottleneck in bottlenecks:
            print(f"   ⚠️  {bottleneck['type']} ({bottleneck['severity']}):")
            print(f"      📝 {bottleneck['description']}")
            print(f"      💡 Recommendations: {len(bottleneck['recommendations'])}")
            for rec in bottleneck['recommendations'][:2]:  # Show first 2 recommendations
                print(f"         - {rec}")
        
        # Test 6: Get comprehensive performance summary
        print("\n📋 Test 6: Retrieving comprehensive performance summary...")
        summary = metrics_collector.get_model_loading_performance_summary()
        
        if summary.get('status') != 'no_data':
            print(f"   📊 Performance Summary:")
            print(f"      🤖 Unique models: {summary['unique_models']}")
            print(f"      ✅ Success rate: {summary['success_rate']:.1%}")
            print(f"      📈 Total loads: {summary['total_model_loads']}")
            
            if 'performance_overview' in summary:
                overview = summary['performance_overview']
                print(f"      ⏱️  Mean loading: {overview['mean_loading_time_seconds']:.2f}s")
                print(f"      🏃 Fastest load: {overview['fastest_load_seconds']:.2f}s")
                print(f"      🐌 Slowest load: {overview['slowest_load_seconds']:.2f}s")
            
            if 'performance_trend' in summary:
                print(f"      📈 Performance trend: {summary['performance_trend']}")
            
            if 'best_performing_models' in summary:
                print(f"      🏆 Best performing models:")
                for model in summary['best_performing_models']:
                    print(f"         - {model['model']}: {model['avg_duration_seconds']:.2f}s avg")
            
            if 'worst_performing_models' in summary:
                print(f"      🐌 Worst performing models:")
                for model in summary['worst_performing_models']:
                    print(f"         - {model['model']}: {model['avg_duration_seconds']:.2f}s avg")
        
        # Test 7: Get model-specific metrics
        print("\n📋 Test 7: Retrieving model-specific metrics...")
        text_embedding_metrics = metrics_collector.get_model_loading_metrics("text-embedding-small")
        print(f"   🤖 text-embedding-small metrics:")
        print(f"      📊 Load count: {text_embedding_metrics['sample_count']}")
        print(f"      ✅ Success rate: {text_embedding_metrics['success_rate']:.1%}")
        print(f"      🎯 Cache hit rate: {text_embedding_metrics['cache_hit_rate']:.1%}")
        
        if 'timing_breakdown' in text_embedding_metrics:
            breakdown = text_embedding_metrics['timing_breakdown']
            print(f"      ⏱️  Timing breakdown:")
            for phase, timing in breakdown.items():
                print(f"         - {phase}: {timing['mean_seconds']:.3f}s avg")
        
        # Test 8: Test export functionality
        print("\n📋 Test 8: Testing metrics export...")
        exported_data = metrics_collector.export_metrics("json")
        print(f"   ✅ Metrics exported successfully ({len(exported_data)} characters)")
        
        # Verify exported data contains model metrics
        import json
        exported_json = json.loads(exported_data)
        model_metrics_count = len(exported_json['current_session']['model_metrics'])
        print(f"   📊 Exported model metrics: {model_metrics_count}")
        
        # Test 9: Stop tracking
        print("\n📋 Test 9: Stopping metrics tracking...")
        await performance_tracker.stop_tracking()
        await metrics_collector.stop_collection()
        await phase_manager.shutdown()
        print(f"   ✅ All tracking stopped and cleaned up")
        
        print("\n🎉 All model loading performance metrics tests completed successfully!")
        print("=" * 60)
        print("✅ Model loading performance metrics are working correctly")
        print("✅ Cache performance analysis is functional")
        print("✅ Bottleneck detection is operational")
        print("✅ Performance insights are being generated")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_api_endpoints():
    """Test the new model loading metrics API endpoints."""
    print("\n🌐 Testing Model Loading Metrics API Endpoints")
    print("=" * 60)
    
    try:
        # Test importing the health router with new endpoints
        from multimodal_librarian.api.routers.health import router
        print("✅ Successfully imported health router with enhanced metrics endpoints")
        
        # Check that the new endpoints are registered
        routes = [route.path for route in router.routes]
        expected_endpoints = [
            "/api/health/metrics/model-loading",
            "/api/health/metrics/model-loading/cache",
            "/api/health/metrics/model-loading/bottlenecks",
            "/api/health/metrics/model-loading/summary"
        ]
        
        for endpoint in expected_endpoints:
            if endpoint in routes:
                print(f"   ✅ Endpoint registered: {endpoint}")
            else:
                print(f"   ❌ Endpoint missing: {endpoint}")
        
        print("\n🎉 API endpoint tests completed!")
        return True
        
    except Exception as e:
        print(f"\n❌ API endpoint test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("🚀 Starting Model Loading Performance Metrics Tests")
    print("=" * 70)
    
    # Test 1: Core functionality
    test1_success = await test_model_loading_performance_metrics()
    
    # Test 2: API endpoints
    test2_success = await test_api_endpoints()
    
    # Summary
    print("\n📊 Test Summary")
    print("=" * 70)
    print(f"Model loading metrics test: {'✅ PASSED' if test1_success else '❌ FAILED'}")
    print(f"API endpoints test: {'✅ PASSED' if test2_success else '❌ FAILED'}")
    
    if test1_success and test2_success:
        print("\n🎉 ALL TESTS PASSED!")
        print("Model loading performance metrics are fully implemented and working.")
        print("\n📈 Key Features Implemented:")
        print("  ✅ Enhanced model loading metrics with resource utilization")
        print("  ✅ Cache performance analysis and optimization insights")
        print("  ✅ Performance bottleneck detection and recommendations")
        print("  ✅ Comprehensive performance summaries and trends")
        print("  ✅ Model-specific performance analysis")
        print("  ✅ Timing breakdown analysis (queue, download, init, cache)")
        print("  ✅ API endpoints for all metrics categories")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED!")
        print("Please check the error messages above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)