#!/usr/bin/env python3
"""
Quick validation test for startup phase load testing implementation.

This script validates that the startup phase load testing framework is
properly implemented and can execute tests successfully.
"""

import asyncio
import sys
import os

# Add tests directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests', 'performance'))

try:
    from test_startup_load import (
        StartupPhaseLoadTester,
        StartupPhaseLoadResult,
        run_startup_phase_load_tests
    )
    print("✅ Successfully imported startup phase load test modules")
except ImportError as e:
    print(f"❌ Failed to import modules: {e}")
    sys.exit(1)


async def test_framework_initialization():
    """Test that the framework initializes correctly."""
    print("\n1️⃣ Testing framework initialization...")
    
    try:
        tester = StartupPhaseLoadTester("http://httpbin.org")
        print("✅ StartupPhaseLoadTester initialized successfully")
        
        # Check attributes
        assert hasattr(tester, 'base_url')
        assert hasattr(tester, 'response_times')
        assert hasattr(tester, 'health_check_results')
        assert hasattr(tester, 'fallback_responses')
        print("✅ All required attributes present")
        
        return True
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        return False


async def test_minimal_phase_quick():
    """Test minimal phase with very short duration."""
    print("\n2️⃣ Testing MINIMAL phase (quick test)...")
    
    try:
        tester = StartupPhaseLoadTester("http://httpbin.org")
        
        # Run a very short test
        result = await tester.test_minimal_phase_load(
            duration_seconds=5,  # Just 5 seconds
            concurrent_users=2
        )
        
        print(f"✅ MINIMAL phase test completed")
        print(f"   Requests: {result.total_requests}")
        print(f"   Success rate: {100 - result.error_rate_percent:.1f}%")
        print(f"   Avg response time: {result.avg_response_time_ms:.1f}ms")
        
        # Validate result structure
        assert result.phase_name == "MINIMAL"
        assert result.total_requests >= 0
        assert result.phase_duration_seconds > 0
        print("✅ Result structure is correct")
        
        return True
    except Exception as e:
        print(f"❌ MINIMAL phase test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_essential_phase_quick():
    """Test essential phase with very short duration."""
    print("\n3️⃣ Testing ESSENTIAL phase (quick test)...")
    
    try:
        tester = StartupPhaseLoadTester("http://httpbin.org")
        
        # Run a very short test
        result = await tester.test_essential_phase_load(
            duration_seconds=5,  # Just 5 seconds
            concurrent_users=2
        )
        
        print(f"✅ ESSENTIAL phase test completed")
        print(f"   Requests: {result.total_requests}")
        print(f"   Success rate: {100 - result.error_rate_percent:.1f}%")
        print(f"   Avg response time: {result.avg_response_time_ms:.1f}ms")
        
        # Validate result structure
        assert result.phase_name == "ESSENTIAL"
        assert result.total_requests >= 0
        assert result.phase_duration_seconds > 0
        print("✅ Result structure is correct")
        
        return True
    except Exception as e:
        print(f"❌ ESSENTIAL phase test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_full_phase_quick():
    """Test full phase with very short duration."""
    print("\n4️⃣ Testing FULL phase (quick test)...")
    
    try:
        tester = StartupPhaseLoadTester("http://httpbin.org")
        
        # Run a very short test
        result = await tester.test_full_phase_load(
            duration_seconds=5,  # Just 5 seconds
            concurrent_users=2
        )
        
        print(f"✅ FULL phase test completed")
        print(f"   Requests: {result.total_requests}")
        print(f"   Success rate: {100 - result.error_rate_percent:.1f}%")
        print(f"   Avg response time: {result.avg_response_time_ms:.1f}ms")
        
        # Validate result structure
        assert result.phase_name == "FULL"
        assert result.total_requests >= 0
        assert result.phase_duration_seconds > 0
        print("✅ Result structure is correct")
        
        return True
    except Exception as e:
        print(f"❌ FULL phase test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_metrics_tracking():
    """Test that metrics are tracked correctly."""
    print("\n5️⃣ Testing metrics tracking...")
    
    try:
        tester = StartupPhaseLoadTester("http://httpbin.org")
        
        # Reset metrics
        tester._reset_metrics()
        assert len(tester.response_times) == 0
        assert len(tester.errors) == 0
        print("✅ Metrics reset works")
        
        # Make a test request
        import aiohttp
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            await tester._make_request(session, "/get", "GET")
        
        # Check metrics were recorded
        assert len(tester.response_times) > 0
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
        tester = StartupPhaseLoadTester("http://httpbin.org")
        
        # Add some mock data
        tester.response_times = [100, 200, 300, 400, 500]
        tester.health_check_results = [True, True, True, False, True]
        tester.fallback_responses = 2
        tester.total_responses = 5
        tester.errors = ["Error 1", "Error 2"]
        
        # Calculate results
        result = tester._calculate_phase_results(
            "TEST",
            10.0,
            {"test_capability": True}
        )
        
        print(f"✅ Result calculated successfully")
        print(f"   Total requests: {result.total_requests}")
        print(f"   Avg response time: {result.avg_response_time_ms:.1f}ms")
        print(f"   Health check success: {result.health_check_success_rate:.1f}%")
        print(f"   Fallback rate: {result.fallback_response_rate:.1f}%")
        
        # Validate calculations
        assert result.total_requests == 5
        assert result.avg_response_time_ms == 300.0  # Mean of [100,200,300,400,500]
        assert result.health_check_success_rate == 80.0  # 4/5 = 80%
        assert result.fallback_response_rate == 40.0  # 2/5 = 40%
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
    print("🧪 STARTUP PHASE LOAD TESTING - QUICK VALIDATION")
    print("=" * 80)
    
    test_results = []
    
    # Run tests
    test_results.append(await test_framework_initialization())
    test_results.append(await test_metrics_tracking())
    test_results.append(await test_result_calculation())
    test_results.append(await test_minimal_phase_quick())
    test_results.append(await test_essential_phase_quick())
    test_results.append(await test_full_phase_quick())
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 VALIDATION SUMMARY")
    print("=" * 80)
    
    passed = sum(test_results)
    total = len(test_results)
    
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED!")
        print("\n✅ Startup phase load testing framework is working correctly")
        print("\nKey features validated:")
        print("- Framework initialization")
        print("- MINIMAL phase load testing")
        print("- ESSENTIAL phase load testing")
        print("- FULL phase load testing")
        print("- Metrics tracking and calculation")
        print("- Result structure and validation")
        print("\nThe framework is ready for:")
        print("- Testing load during different startup phases")
        print("- Validating health check behavior under load")
        print("- Measuring fallback response rates")
        print("- Tracking user experience during startup")
        return True
    else:
        print(f"\n❌ {total - passed} tests failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
