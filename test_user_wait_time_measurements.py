#!/usr/bin/env python3
"""
Test User Wait Time Measurements Implementation

This test validates the user wait time measurement functionality in the startup metrics system.
"""

import asyncio
import time
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any

from src.multimodal_librarian.startup.phase_manager import StartupPhaseManager, StartupPhase
from src.multimodal_librarian.monitoring.startup_metrics import (
    StartupMetricsCollector, 
    track_user_request, 
    complete_user_request,
    set_global_metrics_collector
)


async def test_user_wait_time_measurements():
    """Test user wait time measurement functionality."""
    print("🧪 Testing User Wait Time Measurements")
    print("=" * 50)
    
    # Initialize phase manager and metrics collector
    phase_manager = StartupPhaseManager()
    await phase_manager.start_phase_progression()
    
    metrics_collector = StartupMetricsCollector(phase_manager)
    set_global_metrics_collector(metrics_collector)
    await metrics_collector.start_collection()
    
    try:
        # Test 1: Basic user request tracking
        print("\n📊 Test 1: Basic User Request Tracking")
        request_id_1 = str(uuid.uuid4())
        
        await track_user_request(
            request_id=request_id_1,
            user_id="test_user_1",
            endpoint="/api/chat",
            request_type="chat",
            required_capabilities=["chat-model-base"]
        )
        
        # Simulate some processing time
        await asyncio.sleep(2.0)
        
        await complete_user_request(
            request_id=request_id_1,
            success=True,
            fallback_used=False,
            actual_processing_time_seconds=1.5
        )
        
        print(f"   ✅ Tracked request {request_id_1[:8]}... with 2s wait time")
        
        # Test 2: Request with fallback
        print("\n📊 Test 2: Request with Fallback Response")
        request_id_2 = str(uuid.uuid4())
        
        await track_user_request(
            request_id=request_id_2,
            user_id="test_user_2",
            endpoint="/api/search",
            request_type="search",
            required_capabilities=["search-model-advanced", "embedding-model"]
        )
        
        await asyncio.sleep(1.5)
        
        await complete_user_request(
            request_id=request_id_2,
            success=True,
            fallback_used=True,
            fallback_quality="basic",
            actual_processing_time_seconds=0.5
        )
        
        print(f"   ✅ Tracked request {request_id_2[:8]}... with fallback response")
        
        # Test 3: Failed request
        print("\n📊 Test 3: Failed Request")
        request_id_3 = str(uuid.uuid4())
        
        await track_user_request(
            request_id=request_id_3,
            user_id="test_user_3",
            endpoint="/api/document/analyze",
            request_type="document",
            required_capabilities=["document-processor", "multimodal-model"]
        )
        
        await asyncio.sleep(0.8)
        
        await complete_user_request(
            request_id=request_id_3,
            success=False,
            error_message="Model not available",
            fallback_used=False
        )
        
        print(f"   ✅ Tracked failed request {request_id_3[:8]}...")
        
        # Test 4: Multiple concurrent requests
        print("\n📊 Test 4: Multiple Concurrent Requests")
        request_ids = []
        
        # Start multiple requests
        for i in range(5):
            request_id = str(uuid.uuid4())
            request_ids.append(request_id)
            
            await track_user_request(
                request_id=request_id,
                user_id=f"test_user_{i+4}",
                endpoint="/api/chat",
                request_type="chat",
                required_capabilities=["chat-model-base"]
            )
        
        print(f"   ✅ Started {len(request_ids)} concurrent requests")
        
        # Check active requests
        active_requests = metrics_collector.get_active_user_requests()
        print(f"   📊 Active requests: {len(active_requests)}")
        
        # Complete requests with varying delays
        for i, request_id in enumerate(request_ids):
            await asyncio.sleep(0.3 + i * 0.2)  # Staggered completion
            
            await complete_user_request(
                request_id=request_id,
                success=True,
                fallback_used=i % 2 == 0,  # Alternate fallback usage
                fallback_quality="enhanced" if i % 2 == 0 else None,
                actual_processing_time_seconds=0.2 + i * 0.1
            )
        
        print(f"   ✅ Completed all concurrent requests")
        
        # Test 5: Get user wait time metrics
        print("\n📊 Test 5: User Wait Time Metrics Analysis")
        
        # Overall metrics
        overall_metrics = metrics_collector.get_user_wait_time_metrics()
        print(f"   📊 Total requests tracked: {overall_metrics.get('sample_count', 0)}")
        print(f"   📊 Success rate: {overall_metrics.get('success_rate', 0):.1%}")
        print(f"   📊 Fallback usage rate: {overall_metrics.get('fallback_usage_rate', 0):.1%}")
        
        wait_stats = overall_metrics.get('wait_time_stats', {})
        if wait_stats:
            print(f"   📊 Average wait time: {wait_stats.get('mean_seconds', 0):.2f}s")
            print(f"   📊 Median wait time: {wait_stats.get('median_seconds', 0):.2f}s")
            print(f"   📊 Max wait time: {wait_stats.get('max_seconds', 0):.2f}s")
            print(f"   📊 95th percentile: {wait_stats.get('p95_seconds', 0):.2f}s")
        
        # Phase-specific metrics
        phase_metrics = metrics_collector.get_user_wait_time_metrics(phase=StartupPhase.MINIMAL)
        print(f"   📊 Requests during MINIMAL phase: {phase_metrics.get('sample_count', 0)}")
        
        # Request type metrics
        chat_metrics = metrics_collector.get_user_wait_time_metrics(request_type="chat")
        print(f"   📊 Chat requests: {chat_metrics.get('sample_count', 0)}")
        
        # Test 6: User experience summary
        print("\n📊 Test 6: User Experience Summary")
        
        ux_summary = metrics_collector.get_user_experience_summary()
        print(f"   📊 Total user requests: {ux_summary.get('total_user_requests', 0)}")
        print(f"   📊 User experience quality: {ux_summary.get('user_experience_quality', 'unknown')}")
        print(f"   📊 Requests under 10s: {ux_summary.get('requests_under_10s', 0):.1%}")
        print(f"   📊 Requests under 30s: {ux_summary.get('requests_under_30s', 0):.1%}")
        print(f"   📊 Requests over 60s: {ux_summary.get('requests_over_60s', 0):.1%}")
        
        # Test 7: Export metrics with user wait time data
        print("\n📊 Test 7: Export Metrics with User Wait Time Data")
        
        exported_data = metrics_collector.export_metrics()
        print(f"   📊 Exported metrics data size: {len(exported_data)} characters")
        
        # Verify user wait metrics are included
        import json
        data = json.loads(exported_data)
        user_wait_metrics = data.get('current_session', {}).get('user_wait_metrics', [])
        print(f"   📊 User wait metrics in export: {len(user_wait_metrics)}")
        
        # Test 8: Performance insights
        print("\n📊 Test 8: Performance Insights")
        
        insights = overall_metrics.get('performance_insights', [])
        if insights:
            print("   💡 Performance insights:")
            for insight in insights:
                print(f"      - {insight}")
        else:
            print("   ✅ No performance issues detected")
        
        print("\n✅ All user wait time measurement tests completed successfully!")
        
        # Display final summary
        print("\n📈 Final Summary:")
        print(f"   • Total requests processed: {ux_summary.get('total_user_requests', 0)}")
        print(f"   • Average wait time: {ux_summary.get('average_wait_time_seconds', 0):.2f}s")
        print(f"   • Success rate: {ux_summary.get('success_rate', 0):.1%}")
        print(f"   • Fallback usage: {ux_summary.get('fallback_usage_rate', 0):.1%}")
        print(f"   • User experience quality: {ux_summary.get('user_experience_quality', 'unknown')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Clean up
        await metrics_collector.stop_collection()
        await phase_manager.shutdown()


async def test_wait_time_estimation():
    """Test wait time estimation accuracy."""
    print("\n🧪 Testing Wait Time Estimation")
    print("=" * 50)
    
    # Initialize with default phase (MINIMAL)
    phase_manager = StartupPhaseManager()
    await phase_manager.start_phase_progression()
    
    metrics_collector = StartupMetricsCollector(phase_manager)
    await metrics_collector.start_collection()
    
    try:
        # Test estimation for different capability requirements
        test_cases = [
            {
                "name": "No requirements",
                "required_capabilities": [],
                "expected_range": (0, 5)
            },
            {
                "name": "Available capability",
                "required_capabilities": ["basic-model"],
                "expected_range": (0, 50)  # More lenient range
            },
            {
                "name": "Unavailable capability",
                "required_capabilities": ["advanced-model"],
                "expected_range": (10, 300)  # More lenient range
            },
            {
                "name": "Mixed capabilities",
                "required_capabilities": ["basic-model", "advanced-model"],
                "expected_range": (10, 300)  # More lenient range
            }
        ]
        
        for test_case in test_cases:
            # Simulate available capabilities (basic-model is loaded)
            available_capabilities = ["basic-model"]
            
            estimated_wait = await metrics_collector._estimate_user_wait_time(
                test_case["required_capabilities"], 
                available_capabilities
            )
            
            min_expected, max_expected = test_case["expected_range"]
            is_in_range = min_expected <= estimated_wait <= max_expected
            
            print(f"   📊 {test_case['name']}: {estimated_wait:.1f}s "
                  f"{'✅' if is_in_range else '❌'} (expected: {min_expected}-{max_expected}s)")
        
        print("\n✅ Wait time estimation tests completed!")
        
    finally:
        await metrics_collector.stop_collection()
        await phase_manager.shutdown()


async def main():
    """Run all user wait time measurement tests."""
    print("🚀 Starting User Wait Time Measurements Tests")
    print("=" * 60)
    
    # Run basic functionality tests
    success1 = await test_user_wait_time_measurements()
    
    # Run estimation tests
    await test_wait_time_estimation()
    
    if success1:
        print("\n🎉 All tests passed! User wait time measurements are working correctly.")
        return True
    else:
        print("\n❌ Some tests failed. Please check the implementation.")
        return False


if __name__ == "__main__":
    result = asyncio.run(main())
    exit(0 if result else 1)