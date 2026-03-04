#!/usr/bin/env python3
"""
Demonstration of Startup Phase Load Testing

This script demonstrates the complete startup phase load testing workflow,
showing how to use the framework to validate application behavior during
different startup phases.
"""

import asyncio
import sys
import os
from datetime import datetime

# Add tests directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests', 'performance'))

from test_startup_load import StartupPhaseLoadTester, run_startup_phase_load_tests


async def demo_individual_phase_tests():
    """Demonstrate testing individual startup phases."""
    print("=" * 80)
    print("DEMO 1: Individual Phase Testing")
    print("=" * 80)
    print()
    
    # Create tester
    tester = StartupPhaseLoadTester("http://httpbin.org")
    
    # Test MINIMAL phase
    print("1️⃣ Testing MINIMAL Phase (0-30 seconds)")
    print("-" * 80)
    print("This phase tests basic health checks and API availability")
    print("Expected: Fast responses, high fallback rate, health checks work")
    print()
    
    minimal_result = await tester.test_minimal_phase_load(
        duration_seconds=10,  # Short demo
        concurrent_users=3
    )
    
    print(f"✅ MINIMAL Phase Results:")
    print(f"   Duration: {minimal_result.phase_duration_seconds:.1f}s")
    print(f"   Requests: {minimal_result.total_requests}")
    print(f"   Success Rate: {100 - minimal_result.error_rate_percent:.1f}%")
    print(f"   Avg Response Time: {minimal_result.avg_response_time_ms:.1f}ms")
    print(f"   Health Check Success: {minimal_result.health_check_success_rate:.1f}%")
    print(f"   Fallback Rate: {minimal_result.fallback_response_rate:.1f}%")
    print()
    
    # Test ESSENTIAL phase
    print("2️⃣ Testing ESSENTIAL Phase (30s-2min)")
    print("-" * 80)
    print("This phase tests core functionality with essential models")
    print("Expected: Good responses, moderate fallback rate, chat works")
    print()
    
    essential_result = await tester.test_essential_phase_load(
        duration_seconds=10,  # Short demo
        concurrent_users=5
    )
    
    print(f"✅ ESSENTIAL Phase Results:")
    print(f"   Duration: {essential_result.phase_duration_seconds:.1f}s")
    print(f"   Requests: {essential_result.total_requests}")
    print(f"   Success Rate: {100 - essential_result.error_rate_percent:.1f}%")
    print(f"   Avg Response Time: {essential_result.avg_response_time_ms:.1f}ms")
    print(f"   Health Check Success: {essential_result.health_check_success_rate:.1f}%")
    print(f"   Fallback Rate: {essential_result.fallback_response_rate:.1f}%")
    print()
    
    # Test FULL phase
    print("3️⃣ Testing FULL Phase (2-5min)")
    print("-" * 80)
    print("This phase tests full functionality with all models")
    print("Expected: Excellent responses, low fallback rate, all features work")
    print()
    
    full_result = await tester.test_full_phase_load(
        duration_seconds=10,  # Short demo
        concurrent_users=7
    )
    
    print(f"✅ FULL Phase Results:")
    print(f"   Duration: {full_result.phase_duration_seconds:.1f}s")
    print(f"   Requests: {full_result.total_requests}")
    print(f"   Success Rate: {100 - full_result.error_rate_percent:.1f}%")
    print(f"   Avg Response Time: {full_result.avg_response_time_ms:.1f}ms")
    print(f"   Health Check Success: {full_result.health_check_success_rate:.1f}%")
    print(f"   Fallback Rate: {full_result.fallback_response_rate:.1f}%")
    print()


async def demo_progressive_load():
    """Demonstrate progressive load testing during startup."""
    print("=" * 80)
    print("DEMO 2: Progressive Load During Startup")
    print("=" * 80)
    print()
    print("This simulates realistic user arrival patterns:")
    print("- Few users during MINIMAL phase (0-30s)")
    print("- More users during ESSENTIAL phase (30s-2min)")
    print("- Full load during FULL phase (2-5min)")
    print()
    
    tester = StartupPhaseLoadTester("http://httpbin.org")
    
    results = await tester.test_progressive_load_during_startup(
        total_duration_seconds=30,  # Short demo (normally 240s)
        initial_users=2,
        max_users=6
    )
    
    print("📊 Progressive Load Results:")
    print("-" * 80)
    
    for phase_name, result in results.items():
        print(f"\n{phase_name.upper()} Phase:")
        print(f"  Requests: {result.total_requests}")
        print(f"  Success Rate: {100 - result.error_rate_percent:.1f}%")
        print(f"  Avg Response Time: {result.avg_response_time_ms:.1f}ms")
        print(f"  Fallback Rate: {result.fallback_response_rate:.1f}%")
    
    print()


async def demo_metrics_analysis():
    """Demonstrate metrics analysis capabilities."""
    print("=" * 80)
    print("DEMO 3: Metrics Analysis")
    print("=" * 80)
    print()
    
    tester = StartupPhaseLoadTester("http://httpbin.org")
    
    # Run a quick test
    result = await tester.test_minimal_phase_load(
        duration_seconds=5,
        concurrent_users=2
    )
    
    print("📈 Detailed Metrics Analysis:")
    print("-" * 80)
    print()
    
    print("Response Time Analysis:")
    print(f"  Average: {result.avg_response_time_ms:.1f}ms")
    print(f"  P95: {result.p95_response_time_ms:.1f}ms")
    print(f"  P99: {result.p99_response_time_ms:.1f}ms")
    print(f"  Maximum: {result.max_response_time_ms:.1f}ms")
    print()
    
    print("Request Analysis:")
    print(f"  Total: {result.total_requests}")
    print(f"  Successful: {result.successful_requests}")
    print(f"  Failed: {result.failed_requests}")
    print(f"  Error Rate: {result.error_rate_percent:.1f}%")
    print()
    
    print("Startup-Specific Metrics:")
    print(f"  Health Check Success: {result.health_check_success_rate:.1f}%")
    print(f"  Fallback Response Rate: {result.fallback_response_rate:.1f}%")
    print()
    
    print("Capability Availability:")
    for capability, available in result.capability_availability.items():
        status = "✅ Available" if available else "⏳ Loading"
        print(f"  {capability}: {status}")
    print()
    
    if result.errors:
        print("Error Summary:")
        for error in result.errors[:3]:
            print(f"  - {error}")
        print()


async def demo_requirement_validation():
    """Demonstrate requirement validation."""
    print("=" * 80)
    print("DEMO 4: Requirement Validation")
    print("=" * 80)
    print()
    
    tester = StartupPhaseLoadTester("http://httpbin.org")
    
    # Run tests for each phase
    minimal_result = await tester.test_minimal_phase_load(
        duration_seconds=5,
        concurrent_users=2
    )
    
    essential_result = await tester.test_essential_phase_load(
        duration_seconds=5,
        concurrent_users=3
    )
    
    full_result = await tester.test_full_phase_load(
        duration_seconds=5,
        concurrent_users=4
    )
    
    print("✅ Requirement Validation Results:")
    print("-" * 80)
    print()
    
    # REQ-1: Health Check Optimization
    print("REQ-1: Health Check Optimization")
    health_check_success = (
        minimal_result.health_check_success_rate >= 95 and
        essential_result.health_check_success_rate >= 95 and
        full_result.health_check_success_rate >= 95
    )
    status = "✅ PASS" if health_check_success else "❌ FAIL"
    print(f"  {status} - Health checks pass consistently (>95%)")
    print(f"    MINIMAL: {minimal_result.health_check_success_rate:.1f}%")
    print(f"    ESSENTIAL: {essential_result.health_check_success_rate:.1f}%")
    print(f"    FULL: {full_result.health_check_success_rate:.1f}%")
    print()
    
    # REQ-2: Application Startup Optimization
    print("REQ-2: Application Startup Optimization")
    startup_optimized = (
        minimal_result.phase_duration_seconds <= 60 and
        essential_result.fallback_response_rate < 80
    )
    status = "✅ PASS" if startup_optimized else "❌ FAIL"
    print(f"  {status} - Progressive loading works correctly")
    print(f"    MINIMAL phase duration: {minimal_result.phase_duration_seconds:.1f}s (<60s)")
    print(f"    ESSENTIAL fallback rate: {essential_result.fallback_response_rate:.1f}% (<80%)")
    print()
    
    # REQ-3: User Experience
    print("REQ-3: User Experience During Startup")
    avg_response_time = (
        minimal_result.avg_response_time_ms +
        essential_result.avg_response_time_ms +
        full_result.avg_response_time_ms
    ) / 3
    ux_good = avg_response_time < 1000
    status = "✅ PASS" if ux_good else "❌ FAIL"
    print(f"  {status} - Response times acceptable (<1000ms)")
    print(f"    Average across all phases: {avg_response_time:.1f}ms")
    print()


async def main():
    """Run all demonstrations."""
    print("\n")
    print("🚀 STARTUP PHASE LOAD TESTING DEMONSTRATION")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    print("This demonstration shows how to use the startup phase load testing")
    print("framework to validate application behavior during different startup phases.")
    print()
    
    try:
        # Demo 1: Individual phase tests
        await demo_individual_phase_tests()
        
        # Demo 2: Progressive load
        await demo_progressive_load()
        
        # Demo 3: Metrics analysis
        await demo_metrics_analysis()
        
        # Demo 4: Requirement validation
        await demo_requirement_validation()
        
        # Summary
        print("=" * 80)
        print("🎉 DEMONSTRATION COMPLETE")
        print("=" * 80)
        print()
        print("Key Takeaways:")
        print("1. ✅ Individual phase testing validates specific startup stages")
        print("2. ✅ Progressive load testing simulates realistic user patterns")
        print("3. ✅ Comprehensive metrics track performance and behavior")
        print("4. ✅ Requirement validation ensures compliance with specs")
        print()
        print("Next Steps:")
        print("- Run tests against your local development server")
        print("- Integrate into CI/CD pipeline")
        print("- Set up monitoring and alerting")
        print("- Establish performance baselines")
        print()
        print("For more information, see:")
        print("- tests/performance/README_STARTUP_LOAD_TESTING.md")
        print("- STARTUP_PHASE_LOAD_TESTING_IMPLEMENTATION.md")
        print()
        
    except Exception as e:
        print(f"\n❌ Demonstration failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
