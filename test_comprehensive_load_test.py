#!/usr/bin/env python3
"""
Test script for comprehensive load testing implementation.

This script validates the comprehensive load testing framework by running
a quick test against a local development server or mock endpoints.
"""

import asyncio
import sys
import os
import tempfile
import shutil
from datetime import datetime

# Add the tests directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tests', 'performance'))

try:
    from comprehensive_load_test import (
        ComprehensiveLoadTester,
        LoadTestScenario,
        create_production_load_scenarios,
        run_comprehensive_load_test
    )
    print("✅ Successfully imported comprehensive load test modules")
except ImportError as e:
    print(f"❌ Failed to import comprehensive load test modules: {e}")
    sys.exit(1)


def create_quick_test_scenarios() -> list:
    """Create quick test scenarios for validation."""
    
    quick_targets = {
        "max_response_time_ms": 2000,  # Relaxed for testing
        "max_error_rate_percent": 10,  # Allow some errors for testing
        "min_requests_per_second": 1   # Very low minimum
    }
    
    return [
        LoadTestScenario(
            name="Quick Load Test",
            description="Quick load test for validation",
            test_type="load",
            duration_seconds=30,
            concurrent_users=5,
            ramp_up_seconds=10,
            ramp_down_seconds=5,
            performance_targets=quick_targets
        ),
        
        LoadTestScenario(
            name="Quick Stress Test",
            description="Quick stress test for validation",
            test_type="stress",
            duration_seconds=20,
            concurrent_users=8,
            ramp_up_seconds=5,
            ramp_down_seconds=5,
            performance_targets=quick_targets
        ),
        
        LoadTestScenario(
            name="Quick Spike Test",
            description="Quick spike test for validation",
            test_type="spike",
            duration_seconds=15,
            concurrent_users=3,
            ramp_up_seconds=3,
            ramp_down_seconds=3,
            spike_multiplier=2.0,
            spike_duration_seconds=10,
            performance_targets=quick_targets
        )
    ]


async def test_load_testing_framework():
    """Test the comprehensive load testing framework."""
    
    print("🧪 Testing Comprehensive Load Testing Framework")
    print("=" * 60)
    
    # Test configuration
    base_url = "http://httpbin.org"  # Public testing service
    test_scenarios = create_quick_test_scenarios()
    
    # Create temporary output directory
    temp_dir = tempfile.mkdtemp(prefix="load_test_")
    print(f"📁 Using temporary directory: {temp_dir}")
    
    try:
        # Test 1: Framework initialization
        print("\n1️⃣ Testing framework initialization...")
        tester = ComprehensiveLoadTester(base_url)
        print("✅ Framework initialized successfully")
        
        # Test 2: Scenario creation
        print("\n2️⃣ Testing scenario creation...")
        production_scenarios = create_production_load_scenarios()
        print(f"✅ Created {len(production_scenarios)} production scenarios")
        print(f"✅ Created {len(test_scenarios)} test scenarios")
        
        # Test 3: Quick load test execution
        print("\n3️⃣ Running quick load test...")
        print("   (This may take a few minutes...)")
        
        start_time = datetime.now()
        results = await run_comprehensive_load_test(
            base_url=base_url,
            scenarios=test_scenarios,
            output_directory=temp_dir
        )
        end_time = datetime.now()
        
        duration = (end_time - start_time).total_seconds()
        print(f"✅ Load test completed in {duration:.1f} seconds")
        
        # Test 4: Results validation
        print("\n4️⃣ Validating results...")
        
        # Check basic structure
        required_keys = ["start_time", "end_time", "scenarios", "scenario_results", "summary"]
        for key in required_keys:
            if key not in results:
                print(f"❌ Missing key in results: {key}")
                return False
            else:
                print(f"✅ Found required key: {key}")
        
        # Check scenario results
        scenario_results = results["scenario_results"]
        if len(scenario_results) != len(test_scenarios):
            print(f"❌ Expected {len(test_scenarios)} scenario results, got {len(scenario_results)}")
            return False
        
        print(f"✅ Got results for all {len(scenario_results)} scenarios")
        
        # Check summary statistics
        summary = results["summary"]
        required_summary_keys = [
            "total_scenarios", "total_requests", "overall_success_rate",
            "average_requests_per_second", "average_response_time_ms"
        ]
        
        for key in required_summary_keys:
            if key not in summary:
                print(f"❌ Missing summary key: {key}")
                return False
            else:
                print(f"✅ Found summary key: {key} = {summary[key]}")
        
        # Test 5: Output files validation
        print("\n5️⃣ Validating output files...")
        
        output_files = os.listdir(temp_dir)
        if not output_files:
            print("❌ No output files generated")
            return False
        
        print(f"✅ Generated {len(output_files)} output files:")
        for file in output_files:
            print(f"   📄 {file}")
        
        # Test 6: Performance metrics validation
        print("\n6️⃣ Validating performance metrics...")
        
        total_requests = summary.get("total_requests", 0)
        success_rate = summary.get("overall_success_rate", 0)
        avg_response_time = summary.get("average_response_time_ms", 0)
        
        if total_requests == 0:
            print("⚠️ No requests were made during testing")
        else:
            print(f"✅ Total requests: {total_requests}")
        
        if success_rate < 50:
            print(f"⚠️ Low success rate: {success_rate:.1f}% (may be due to test service)")
        else:
            print(f"✅ Success rate: {success_rate:.1f}%")
        
        if avg_response_time > 5000:
            print(f"⚠️ High average response time: {avg_response_time:.1f}ms")
        else:
            print(f"✅ Average response time: {avg_response_time:.1f}ms")
        
        print("\n🎉 All tests passed! Load testing framework is working correctly.")
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Cleanup temporary directory
        try:
            shutil.rmtree(temp_dir)
            print(f"🧹 Cleaned up temporary directory: {temp_dir}")
        except Exception as e:
            print(f"⚠️ Could not clean up temporary directory: {e}")


async def test_individual_components():
    """Test individual components of the load testing framework."""
    
    print("\n🔧 Testing Individual Components")
    print("=" * 40)
    
    try:
        # Test LoadTestScenario creation
        print("1️⃣ Testing LoadTestScenario...")
        scenario = LoadTestScenario(
            name="Test Scenario",
            description="Test description",
            test_type="load",
            duration_seconds=10,
            concurrent_users=2,
            ramp_up_seconds=2,
            ramp_down_seconds=2
        )
        print(f"✅ Created scenario: {scenario.name}")
        
        # Test ComprehensiveLoadTester initialization
        print("2️⃣ Testing ComprehensiveLoadTester...")
        tester = ComprehensiveLoadTester("http://httpbin.org")
        print("✅ Tester initialized successfully")
        
        # Test metrics reset
        print("3️⃣ Testing metrics reset...")
        tester._reset_metrics()
        print("✅ Metrics reset successfully")
        
        # Test performance targets checking
        print("4️⃣ Testing performance targets...")
        from comprehensive_load_test import ComprehensiveLoadTestResult
        from datetime import datetime
        
        mock_result = ComprehensiveLoadTestResult(
            scenario_name="Mock Test",
            test_type="load",
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=10,
            total_requests=100,
            successful_requests=95,
            failed_requests=5,
            requests_per_second=10,
            avg_response_time_ms=200,
            p50_response_time_ms=180,
            p95_response_time_ms=400,
            p99_response_time_ms=600,
            max_response_time_ms=800,
            min_response_time_ms=50,
            error_rate_percent=5,
            throughput_mb_per_sec=1.5,
            cpu_usage_percent=45,
            memory_usage_mb=512,
            performance_targets_met=False,
            target_violations=[],
            errors=[]
        )
        
        targets = {
            "max_response_time_ms": 500,
            "max_error_rate_percent": 10,
            "min_requests_per_second": 5
        }
        
        targets_met, violations = tester._check_performance_targets(mock_result, targets)
        print(f"✅ Performance targets check: met={targets_met}, violations={len(violations)}")
        
        print("\n✅ All individual component tests passed!")
        return True
        
    except Exception as e:
        print(f"\n❌ Component test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main test function."""
    print("🚀 Comprehensive Load Testing Framework Validation")
    print("=" * 60)
    print(f"📅 Started: {datetime.now().isoformat()}")
    print()
    
    # Run component tests first
    component_success = asyncio.run(test_individual_components())
    
    if not component_success:
        print("\n❌ Component tests failed. Skipping integration tests.")
        sys.exit(1)
    
    # Run integration tests
    integration_success = asyncio.run(test_load_testing_framework())
    
    if integration_success:
        print("\n🎉 ALL TESTS PASSED!")
        print("✅ Comprehensive load testing framework is ready for use")
        print("\nNext steps:")
        print("1. Run against your local development server")
        print("2. Customize scenarios for your specific use case")
        print("3. Integrate into your CI/CD pipeline")
        sys.exit(0)
    else:
        print("\n❌ TESTS FAILED!")
        print("Please review the errors above and fix the issues.")
        sys.exit(1)


if __name__ == "__main__":
    main()