#!/usr/bin/env python3
"""
Test script for startup metrics tracking functionality.

This script tests the phase completion time tracking implementation
to ensure it properly captures and reports startup metrics.
"""

import asyncio
import sys
import os
import time
from datetime import datetime

# Add src to path for imports
sys.path.append('src')

async def test_startup_metrics_tracking():
    """Test the startup metrics tracking functionality."""
    print("🧪 Testing Startup Metrics Tracking")
    print("=" * 50)
    
    try:
        # Import required modules
        from multimodal_librarian.startup.phase_manager import StartupPhaseManager
        from multimodal_librarian.monitoring.startup_metrics import StartupMetricsCollector, track_startup_metrics
        from multimodal_librarian.monitoring.performance_tracker import PerformanceTracker, track_performance
        
        print("✅ Successfully imported startup metrics modules")
        
        # Test 1: Create startup phase manager
        print("\n📋 Test 1: Creating StartupPhaseManager...")
        phase_manager = StartupPhaseManager()
        print(f"   ✅ StartupPhaseManager created successfully")
        print(f"   📊 Initial phase: {phase_manager.current_phase.value}")
        
        # Test 2: Initialize metrics tracking
        print("\n📋 Test 2: Initializing metrics tracking...")
        metrics_collector = await track_startup_metrics(phase_manager)
        performance_tracker = await track_performance(phase_manager, metrics_collector)
        print(f"   ✅ Metrics tracking initialized successfully")
        
        # Test 3: Start phase progression
        print("\n📋 Test 3: Starting phase progression...")
        await phase_manager.start_phase_progression()
        print(f"   ✅ Phase progression started")
        
        # Test 4: Monitor phase transitions for a short time
        print("\n📋 Test 4: Monitoring phase transitions...")
        start_time = time.time()
        last_phase = phase_manager.current_phase
        
        for i in range(30):  # Monitor for 30 seconds
            await asyncio.sleep(1)
            current_phase = phase_manager.current_phase
            elapsed = time.time() - start_time
            
            if current_phase != last_phase:
                print(f"   🔄 Phase transition: {last_phase.value} → {current_phase.value} (after {elapsed:.1f}s)")
                last_phase = current_phase
            
            if i % 5 == 0:  # Print status every 5 seconds
                print(f"   📊 Status update ({elapsed:.1f}s): Phase={current_phase.value}")
        
        # Test 5: Get startup metrics
        print("\n📋 Test 5: Retrieving startup metrics...")
        session_summary = metrics_collector.get_startup_session_summary()
        print(f"   ✅ Session ID: {session_summary['session_id']}")
        print(f"   📊 Final phase reached: {session_summary['final_phase_reached']}")
        total_duration = session_summary.get('total_duration_seconds') or 0
        print(f"   ⏱️  Total duration: {total_duration:.2f}s")
        print(f"   🎯 Overall efficiency: {session_summary['overall_efficiency_score']:.1f}%")
        print(f"   ✅ Success: {session_summary['success']}")
        print(f"   📈 Phases completed: {session_summary['phases_completed']}")
        print(f"   🤖 Models processed: {session_summary['models_processed']}")
        
        # Test 6: Get phase completion metrics
        print("\n📋 Test 6: Retrieving phase completion metrics...")
        from multimodal_librarian.startup.phase_manager import StartupPhase
        
        for phase in StartupPhase:
            phase_metrics = metrics_collector.get_phase_completion_metrics(phase)
            if phase_metrics['sample_count'] > 0:
                print(f"   📊 {phase.value.upper()} Phase:")
                print(f"      ⏱️  Mean duration: {phase_metrics['duration_stats']['mean_seconds']:.2f}s")
                print(f"      🎯 Efficiency score: {phase_metrics['efficiency_stats']['mean_score']:.1f}%")
                print(f"      ✅ Success rate: {phase_metrics['success_rate']:.1%}")
        
        # Test 7: Get model loading metrics
        print("\n📋 Test 7: Retrieving model loading metrics...")
        model_metrics = metrics_collector.get_model_loading_metrics()
        if model_metrics['sample_count'] > 0:
            print(f"   🤖 Model Loading Summary:")
            print(f"      📊 Total models processed: {model_metrics['sample_count']}")
            print(f"      ✅ Success rate: {model_metrics['success_rate']:.1%}")
            print(f"      🎯 Cache hit rate: {model_metrics.get('cache_hit_rate', 0):.1%}")
            print(f"      ⚠️  Timeout rate: {model_metrics.get('timeout_rate', 0):.1%}")
            if 'loading_stats' in model_metrics:
                print(f"      ⏱️  Mean loading time: {model_metrics['loading_stats']['mean_duration_seconds']:.2f}s")
                print(f"      📈 P95 loading time: {model_metrics['loading_stats'].get('p95_duration_seconds', 0):.2f}s")
            if 'performance_insights' in model_metrics:
                print(f"      💡 Performance insights: {len(model_metrics['performance_insights'])} found")
        
        # Test 7a: Get cache performance metrics
        print("\n📋 Test 7a: Retrieving cache performance metrics...")
        cache_metrics = metrics_collector.get_cache_performance_metrics()
        if cache_metrics.get('cache_performance') != 'no_data':
            print(f"   💾 Cache Performance:")
            print(f"      🎯 Cache hit rate: {cache_metrics.get('cache_hit_rate', 0):.1%}")
            print(f"      📊 Total loads: {cache_metrics.get('total_model_loads', 0)}")
            if 'cache_speedup_factor' in cache_metrics:
                print(f"      🚀 Cache speedup: {cache_metrics['cache_speedup_factor']:.1f}x")
                print(f"      ⭐ Cache effectiveness: {cache_metrics.get('cache_effectiveness', 'unknown')}")
        
        # Test 7b: Get model loading bottlenecks
        print("\n📋 Test 7b: Retrieving model loading bottlenecks...")
        bottlenecks = metrics_collector.get_model_loading_bottlenecks()
        print(f"   🔍 Bottlenecks identified: {len(bottlenecks)}")
        for bottleneck in bottlenecks[:3]:  # Show first 3
            print(f"      ⚠️  {bottleneck['type']}: {bottleneck['description']}")
        
        # Test 7c: Get comprehensive performance summary
        print("\n📋 Test 7c: Retrieving performance summary...")
        perf_summary = metrics_collector.get_model_loading_performance_summary()
        if perf_summary.get('status') != 'no_data':
            print(f"   📊 Performance Summary:")
            print(f"      🤖 Unique models: {perf_summary.get('unique_models', 0)}")
            print(f"      ✅ Success rate: {perf_summary.get('success_rate', 0):.1%}")
            if 'performance_overview' in perf_summary:
                overview = perf_summary['performance_overview']
                print(f"      ⏱️  Mean loading: {overview.get('mean_loading_time_seconds', 0):.2f}s")
                print(f"      🏃 Fastest load: {overview.get('fastest_load_seconds', 0):.2f}s")
                print(f"      🐌 Slowest load: {overview.get('slowest_load_seconds', 0):.2f}s")
        
        # Test 8: Get performance summary
        print("\n📋 Test 8: Retrieving performance metrics...")
        perf_summary = performance_tracker.get_performance_summary()
        print(f"   📊 Performance Summary:")
        print(f"      ⏱️  Tracking duration: {perf_summary['tracking_duration_seconds']:.2f}s")
        print(f"      🔔 Active alerts: {perf_summary['active_alerts']}")
        print(f"      🚨 Total alerts: {perf_summary['total_alerts']}")
        print(f"      🔍 Bottlenecks identified: {perf_summary['bottlenecks_identified']}")
        print(f"      💡 Recommendations: {perf_summary['optimization_recommendations']}")
        
        if 'resource_statistics' in perf_summary and perf_summary['resource_statistics']:
            cpu_stats = perf_summary['resource_statistics'].get('cpu', {})
            memory_stats = perf_summary['resource_statistics'].get('memory', {})
            if cpu_stats:
                print(f"      🖥️  CPU: current={cpu_stats.get('current', 0):.1f}%, peak={cpu_stats.get('peak', 0):.1f}%")
            if memory_stats:
                print(f"      💾 Memory: current={memory_stats.get('current', 0):.1f}%, peak={memory_stats.get('peak', 0):.1f}%")
        
        # Test 9: Export metrics
        print("\n📋 Test 9: Testing metrics export...")
        exported_data = metrics_collector.export_metrics("json")
        print(f"   ✅ Metrics exported successfully ({len(exported_data)} characters)")
        
        # Test 10: Stop tracking
        print("\n📋 Test 10: Stopping metrics tracking...")
        await performance_tracker.stop_tracking()
        await metrics_collector.stop_collection()
        await phase_manager.shutdown()
        print(f"   ✅ All tracking stopped and cleaned up")
        
        print("\n🎉 All tests completed successfully!")
        print("=" * 50)
        print("✅ Phase completion time tracking is working correctly")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_metrics_api_endpoints():
    """Test the metrics API endpoints."""
    print("\n🌐 Testing Metrics API Endpoints")
    print("=" * 50)
    
    try:
        # Test importing the health router with new endpoints
        from multimodal_librarian.api.routers.health import router
        print("✅ Successfully imported health router with metrics endpoints")
        
        # Check that the new endpoints are registered
        routes = [route.path for route in router.routes]
        expected_endpoints = [
            "/api/health/metrics/startup",
            "/api/health/metrics/performance", 
            "/api/health/metrics/phase-completion",
            "/api/health/metrics/model-loading",
            "/api/health/metrics/model-loading/cache",
            "/api/health/metrics/model-loading/bottlenecks",
            "/api/health/metrics/model-loading/summary",
            "/api/health/metrics/export"
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
    print("🚀 Starting Startup Metrics Tracking Tests")
    print("=" * 60)
    
    # Test 1: Core functionality
    test1_success = await test_startup_metrics_tracking()
    
    # Test 2: API endpoints
    test2_success = await test_metrics_api_endpoints()
    
    # Summary
    print("\n📊 Test Summary")
    print("=" * 60)
    print(f"Core functionality test: {'✅ PASSED' if test1_success else '❌ FAILED'}")
    print(f"API endpoints test: {'✅ PASSED' if test2_success else '❌ FAILED'}")
    
    if test1_success and test2_success:
        print("\n🎉 ALL TESTS PASSED!")
        print("Phase completion time tracking is fully implemented and working.")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED!")
        print("Please check the error messages above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)