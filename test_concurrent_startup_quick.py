#!/usr/bin/env python3
"""
Quick validation test for concurrent startup testing implementation.

This script validates that the concurrent startup testing framework is
properly implemented and can execute tests successfully.
"""

import asyncio
import sys
import os

# Add tests directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests', 'performance'))

try:
    from test_concurrent_startup import (
        ConcurrentStartupTester,
        ConcurrentRequestResult,
        run_concurrent_startup_tests
    )
    print("✅ Successfully imported concurrent startup test modules")
except ImportError as e:
    print(f"❌ Failed to import modules: {e}")
    sys.exit(1)


async def test_framework_initialization():
    """Test that the framework initializes correctly."""
    print("\n1️⃣ Testing framework initialization...")
    
    try:
        tester = ConcurrentStartupTester("http://httpbin.org")
        print("✅ ConcurrentStartupTester initialized successfully")
        
        # Check attributes
        assert hasattr(tester, 'base_url')
        assert hasattr(tester, 'response_times')
        assert hasattr(tester, 'model_not_loaded_errors')
        assert hasattr(tester, 'fallback_responses')
        assert hasattr(tester, 'response_quality')
        print("✅ All required attributes present")
        
        return True
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        return False


async def test_concurrent_minimal_phase_quick():
    """Test concurrent requests during minimal phase with very short duration."""
    print("\n2️⃣ Testing concurrent requests during MINIMAL phase (quick test)...")
    
    try:
        tester = ConcurrentStartupTester("http://httpbin.org")
        
        # Run a very short test with few users
        result = await tester.test_concurrent_requests_minimal_phase(
            concurrent_users=3,
            requests_per_user=2
        )
        
        print(f"✅ MINIMAL phase concurrent test completed")
        print(f"   Concurrent users: {result.concurrent_users}")
        print(f"   Total requests: {result.total_requests}")
        print(f"   Success rate: {100 - result.error_rate_percent:.1f}%")
        print(f"   Model not loaded errors: {result.model_not_loaded_errors}")
        print(f"   Fallback responses: {result.fallback_responses}")
        
        # Validate result structure
        assert result.test_name == "concurrent_minimal_phase"
        assert result.concurrent_users == 3
        assert result.total_requests >= 0
        assert result.model_not_loaded_errors >= 0
        print("✅ Result structure is correct")
        
        return True
    except Exception as e:
        print(f"❌ MINIMAL phase concurrent test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_concurrent_during_loading_quick():
    """Test concurrent requests during model loading with very short duration."""
    print("\n3️⃣ Testing concurrent requests during model loading (quick test)...")
    
    try:
        tester = ConcurrentStartupTester("http://httpbin.org")
        
        # Run a very short test with few users
        result = await tester.test_concurrent_requests_during_model_loading(
            concurrent_users=3,
            requests_per_user=2
        )
        
        print(f"✅ Model loading concurrent test completed")
        print(f"   Concurrent users: {result.concurrent_users}")
        print(f"   Total requests: {result.total_requests}")
        print(f"   Success rate: {100 - result.error_rate_percent:.1f}%")
        print(f"   Model not loaded errors: {result.model_not_loaded_errors}")
        print(f"   Fallback responses: {result.fallback_responses}")
        
        # Validate result structure
        assert result.test_name == "concurrent_during_loading"
        assert result.concurrent_users == 3
        assert result.total_requests >= 0
        print("✅ Result structure is correct")
        
        return True
    except Exception as e:
        print(f"❌ Model loading concurrent test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_stress_test_quick():
    """Test high concurrency stress test with very short duration."""
    print("\n4️⃣ Testing high concurrency stress test (quick test)...")
    
    try:
        tester = ConcurrentStartupTester("http://httpbin.org")
        
        # Run a very short test with moderate users
        result = await tester.test_high_concurrency_stress(
            concurrent_users=5,
            requests_per_user=2
        )
        
        print(f"✅ Stress test completed")
        print(f"   Concurrent users: {result.concurrent_users}")
        print(f"   Total requests: {result.total_requests}")
        print(f"   Success rate: {100 - result.error_rate_percent:.1f}%")
        print(f"   Requests/sec: {result.requests_per_second:.1f}")
        print(f"   P95 response time: {result.p95_response_time_ms:.1f}ms")
        
        # Validate result structure
        assert result.test_name == "high_concurrency_stress"
        assert result.concurrent_users == 5
        assert result.total_requests >= 0
        assert result.requests_per_second >= 0
        print("✅ Result structure is correct")
        
        return True
    except Exception as e:
        print(f"❌ Stress test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_metrics_tracking():
    """Test that metrics are tracked correctly."""
    print("\n5️⃣ Testing metrics tracking...")
    
    try:
        tester = ConcurrentStartupTester("http://httpbin.org")
        
        # Reset metrics
        tester._reset_metrics()
        assert len(tester.response_times) == 0
        assert tester.model_not_loaded_errors == 0
        assert tester.fallback_responses == 0
        assert len(tester.errors) == 0
        print("✅ Metrics reset works")
        
        # Make a test request
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            await tester._make_typed_request(session, "health")
        
        # Check metrics were recorded
        assert len(tester.response_times) > 0
        assert tester.total_responses > 0
        print(f"✅ Metrics tracked: {len(tester.response_times)} response times")
        
        return True
    except Exception as e:
        print(f"❌ Metrics tracking test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_result_calculation():
    """Test result calculation logic."""
    print("\n6️⃣ Testing result calculation...")
    
    try:
        tester = ConcurrentStartupTester("http://httpbin.org")
        
        # Add some mock data
        tester.response_times = [100, 200, 300, 400, 500]
        tester.model_not_loaded_errors = 2
        tester.fallback_responses = 3
        tester.total_responses = 5
        tester.response_quality = {"basic": 2, "enhanced": 1, "full": 1, "error": 1}
        tester.errors = ["Error 1", "Error 2"]
        
        # Calculate results
        result = tester._calculate_results(
            "test",
            10,
            5.0
        )
        
        print(f"✅ Result calculated successfully")
        print(f"   Total requests: {result.total_requests}")
        print(f"   Model not loaded errors: {result.model_not_loaded_errors}")
        print(f"   Fallback responses: {result.fallback_responses}")
        print(f"   Avg response time: {result.avg_response_time_ms:.1f}ms")
        print(f"   Requests/sec: {result.requests_per_second:.1f}")
        
        # Validate calculations
        assert result.total_requests == 5
        assert result.model_not_loaded_errors == 2
        assert result.fallback_responses == 3
        assert result.avg_response_time_ms == 300.0  # Mean of [100,200,300,400,500]
        assert result.requests_per_second == 1.0  # 5 requests / 5 seconds
        print("✅ Calculations are correct")
        
        return True
    except Exception as e:
        print(f"❌ Result calculation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all validation tests."""
    print("=" * 80)
    print("🧪 CONCURRENT STARTUP TESTING - QUICK VALIDATION")
    print("=" * 80)
    
    test_results = []
    
    # Run tests
    test_results.append(await test_framework_initialization())
    test_results.append(await test_metrics_tracking())
    test_results.append(await test_result_calculation())
    test_results.append(await test_concurrent_minimal_phase_quick())
    test_results.append(await test_concurrent_during_loading_quick())
    test_results.append(await test_stress_test_quick())
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 VALIDATION SUMMARY")
    print("=" * 80)
    
    passed = sum(test_results)
    total = len(test_results)
    
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print("\n✅ Concurrent startup testing framework is working correctly")
        print("\nKey features validated:")
        print("- Framework initialization")
        print("- Concurrent requests during MINIMAL phase")
        print("- Concurrent requests during model loading")
        print("- High concurrency stress testing")
        print("- Metrics tracking and calculation")
        print("- Result structure and validation")
        print("\nThe framework is ready for:")
        print("- Testing concurrent user requests during startup")
        print("- Validating no 'model not loaded' errors occur")
        print("- Measuring fallback response rates under load")
        print("- Stress testing with high concurrency")
        print("- Tracking response quality distribution")
        return True
    else:
        print(f"\n❌ {total - passed} tests failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
