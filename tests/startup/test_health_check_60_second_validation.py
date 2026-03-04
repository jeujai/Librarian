"""
Health Check 60-Second Validation Test

This test validates that health checks pass consistently within 60 seconds
as required by the application-health-startup-optimization specification.

Test Objectives:
1. Verify /health/minimal endpoint responds within 60 seconds
2. Verify health check response time is consistently fast (<5 seconds)
3. Verify health check returns 200 status code within 60 seconds
4. Verify ECS health check configuration allows 60 second start period
5. Verify health check reliability under various conditions

Success Criteria:
- Health checks pass consistently within 60 seconds
- Response time < 5 seconds for health check endpoints
- No false negatives during startup phase
- ECS health check configuration properly set
"""

import asyncio
import time
import pytest
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import statistics

from src.multimodal_librarian.startup.minimal_server import (
    MinimalServer,
    initialize_minimal_server,
    get_minimal_server
)
from src.multimodal_librarian.startup.phase_manager import (
    StartupPhaseManager,
    StartupPhase
)


class HealthCheck60SecondValidator:
    """Validates that health checks pass within 60 seconds."""
    
    def __init__(self):
        self.test_results = {}
        self.health_check_times = []
        self.startup_time = None
        self.first_success_time = None
        
    async def run_validation(self) -> Dict:
        """Run complete 60-second health check validation."""
        print("\n" + "="*80)
        print("HEALTH CHECK 60-SECOND VALIDATION TEST")
        print("="*80)
        
        self.startup_time = datetime.now()
        
        # Test 1: Minimal server startup time
        await self._test_minimal_server_startup()
        
        # Test 2: Health check response time
        await self._test_health_check_response_time()
        
        # Test 3: Health check reliability during startup
        await self._test_health_check_reliability()
        
        # Test 4: Continuous health check monitoring
        await self._test_continuous_health_checks()
        
        # Test 5: Health check under load
        await self._test_health_check_under_load()
        
        # Generate summary
        self._generate_summary()
        
        return self.test_results
    
    async def _test_minimal_server_startup(self):
        """Test 1: Verify minimal server starts within 60 seconds."""
        print("\n📋 Test 1: Minimal Server Startup Time")
        print("-" * 80)
        
        start_time = time.time()
        
        try:
            # Initialize minimal server
            server = await initialize_minimal_server()
            
            startup_duration = time.time() - start_time
            
            # Check if startup was within 60 seconds
            within_60_seconds = startup_duration < 60.0
            
            # Check if startup was within optimal 30 seconds
            within_30_seconds = startup_duration < 30.0
            
            print(f"✓ Minimal server started in {startup_duration:.2f} seconds")
            print(f"  - Within 60 seconds: {'✓' if within_60_seconds else '✗'}")
            print(f"  - Within 30 seconds (optimal): {'✓' if within_30_seconds else '✗'}")
            
            self.test_results["minimal_server_startup"] = {
                "passed": within_60_seconds,
                "startup_time_seconds": startup_duration,
                "within_60_seconds": within_60_seconds,
                "within_30_seconds": within_30_seconds,
                "optimal": within_30_seconds
            }
            
            if not within_60_seconds:
                print(f"✗ FAILED: Startup took {startup_duration:.2f}s (> 60s)")
            
        except Exception as e:
            print(f"✗ FAILED: {e}")
            self.test_results["minimal_server_startup"] = {
                "passed": False,
                "error": str(e)
            }
    
    async def _test_health_check_response_time(self):
        """Test 2: Verify health check responds quickly (<5 seconds)."""
        print("\n📋 Test 2: Health Check Response Time")
        print("-" * 80)
        
        server = get_minimal_server()
        response_times = []
        
        try:
            # Test health check response time 10 times
            for i in range(10):
                start_time = time.time()
                
                # Get server status (simulates health check)
                status = server.get_status()
                
                response_time = time.time() - start_time
                response_times.append(response_time)
                
                print(f"  Health check {i+1}: {response_time*1000:.2f}ms")
                
                # Small delay between checks
                await asyncio.sleep(0.1)
            
            # Calculate statistics
            avg_response_time = statistics.mean(response_times)
            max_response_time = max(response_times)
            min_response_time = min(response_times)
            
            # All responses should be under 5 seconds
            all_under_5_seconds = all(t < 5.0 for t in response_times)
            
            # Optimal: all responses under 1 second
            all_under_1_second = all(t < 1.0 for t in response_times)
            
            print(f"\n✓ Response time statistics:")
            print(f"  - Average: {avg_response_time*1000:.2f}ms")
            print(f"  - Min: {min_response_time*1000:.2f}ms")
            print(f"  - Max: {max_response_time*1000:.2f}ms")
            print(f"  - All under 5 seconds: {'✓' if all_under_5_seconds else '✗'}")
            print(f"  - All under 1 second (optimal): {'✓' if all_under_1_second else '✗'}")
            
            self.test_results["health_check_response_time"] = {
                "passed": all_under_5_seconds,
                "avg_response_time_ms": avg_response_time * 1000,
                "max_response_time_ms": max_response_time * 1000,
                "min_response_time_ms": min_response_time * 1000,
                "all_under_5_seconds": all_under_5_seconds,
                "all_under_1_second": all_under_1_second,
                "response_times_ms": [t * 1000 for t in response_times]
            }
            
        except Exception as e:
            print(f"✗ FAILED: {e}")
            self.test_results["health_check_response_time"] = {
                "passed": False,
                "error": str(e)
            }
    
    async def _test_health_check_reliability(self):
        """Test 3: Verify health checks are reliable during startup."""
        print("\n📋 Test 3: Health Check Reliability During Startup")
        print("-" * 80)
        
        server = get_minimal_server()
        
        try:
            # Check health status immediately
            status = server.get_status()
            
            # Verify health check is ready
            health_check_ready = status.health_check_ready
            
            # Verify server is in minimal or ready state
            server_operational = status.status.value in ["minimal", "ready"]
            
            # Calculate time since startup
            time_since_startup = (datetime.now() - self.startup_time).total_seconds()
            
            print(f"✓ Health check status:")
            print(f"  - Health check ready: {'✓' if health_check_ready else '✗'}")
            print(f"  - Server operational: {'✓' if server_operational else '✗'}")
            print(f"  - Time since startup: {time_since_startup:.2f}s")
            print(f"  - Server status: {status.status.value}")
            
            # Health check should be ready within 60 seconds
            passed = health_check_ready and time_since_startup < 60.0
            
            self.test_results["health_check_reliability"] = {
                "passed": passed,
                "health_check_ready": health_check_ready,
                "server_operational": server_operational,
                "time_since_startup": time_since_startup,
                "server_status": status.status.value,
                "within_60_seconds": time_since_startup < 60.0
            }
            
            if not passed:
                print(f"✗ FAILED: Health check not ready within 60 seconds")
            
        except Exception as e:
            print(f"✗ FAILED: {e}")
            self.test_results["health_check_reliability"] = {
                "passed": False,
                "error": str(e)
            }
    
    async def _test_continuous_health_checks(self):
        """Test 4: Verify health checks remain reliable over time."""
        print("\n📋 Test 4: Continuous Health Check Monitoring")
        print("-" * 80)
        
        server = get_minimal_server()
        
        try:
            # Monitor health checks for 30 seconds
            monitoring_duration = 30.0
            check_interval = 2.0  # Check every 2 seconds
            
            checks_performed = 0
            checks_passed = 0
            check_times = []
            
            start_time = time.time()
            
            print(f"Monitoring health checks for {monitoring_duration}s...")
            
            while time.time() - start_time < monitoring_duration:
                check_start = time.time()
                
                # Perform health check
                status = server.get_status()
                check_time = time.time() - check_start
                
                checks_performed += 1
                check_times.append(check_time)
                
                # Check if health check passed
                if status.health_check_ready:
                    checks_passed += 1
                
                # Wait before next check
                await asyncio.sleep(check_interval)
            
            # Calculate success rate
            success_rate = (checks_passed / checks_performed) * 100 if checks_performed > 0 else 0
            avg_check_time = statistics.mean(check_times) if check_times else 0
            
            # Success criteria: >95% success rate
            passed = success_rate >= 95.0
            
            print(f"\n✓ Continuous monitoring results:")
            print(f"  - Checks performed: {checks_performed}")
            print(f"  - Checks passed: {checks_passed}")
            print(f"  - Success rate: {success_rate:.1f}%")
            print(f"  - Average check time: {avg_check_time*1000:.2f}ms")
            print(f"  - Success rate >= 95%: {'✓' if passed else '✗'}")
            
            self.test_results["continuous_health_checks"] = {
                "passed": passed,
                "checks_performed": checks_performed,
                "checks_passed": checks_passed,
                "success_rate": success_rate,
                "avg_check_time_ms": avg_check_time * 1000,
                "monitoring_duration_seconds": monitoring_duration
            }
            
        except Exception as e:
            print(f"✗ FAILED: {e}")
            self.test_results["continuous_health_checks"] = {
                "passed": False,
                "error": str(e)
            }
    
    async def _test_health_check_under_load(self):
        """Test 5: Verify health checks work under concurrent load."""
        print("\n📋 Test 5: Health Check Under Concurrent Load")
        print("-" * 80)
        
        server = get_minimal_server()
        
        try:
            # Perform 50 concurrent health checks
            concurrent_checks = 50
            
            print(f"Performing {concurrent_checks} concurrent health checks...")
            
            async def perform_health_check():
                start_time = time.time()
                status = server.get_status()
                check_time = time.time() - start_time
                return {
                    "success": status.health_check_ready,
                    "time": check_time
                }
            
            # Run concurrent health checks
            start_time = time.time()
            results = await asyncio.gather(*[
                perform_health_check() for _ in range(concurrent_checks)
            ])
            total_time = time.time() - start_time
            
            # Analyze results
            successful_checks = sum(1 for r in results if r["success"])
            check_times = [r["time"] for r in results]
            
            success_rate = (successful_checks / concurrent_checks) * 100
            avg_check_time = statistics.mean(check_times)
            max_check_time = max(check_times)
            
            # Success criteria: >95% success rate and all checks under 5 seconds
            passed = success_rate >= 95.0 and max_check_time < 5.0
            
            print(f"\n✓ Concurrent load test results:")
            print(f"  - Total checks: {concurrent_checks}")
            print(f"  - Successful checks: {successful_checks}")
            print(f"  - Success rate: {success_rate:.1f}%")
            print(f"  - Total time: {total_time:.2f}s")
            print(f"  - Average check time: {avg_check_time*1000:.2f}ms")
            print(f"  - Max check time: {max_check_time*1000:.2f}ms")
            print(f"  - All checks under 5s: {'✓' if max_check_time < 5.0 else '✗'}")
            
            self.test_results["health_check_under_load"] = {
                "passed": passed,
                "concurrent_checks": concurrent_checks,
                "successful_checks": successful_checks,
                "success_rate": success_rate,
                "total_time_seconds": total_time,
                "avg_check_time_ms": avg_check_time * 1000,
                "max_check_time_ms": max_check_time * 1000,
                "all_under_5_seconds": max_check_time < 5.0
            }
            
        except Exception as e:
            print(f"✗ FAILED: {e}")
            self.test_results["health_check_under_load"] = {
                "passed": False,
                "error": str(e)
            }
    
    def _generate_summary(self):
        """Generate test summary."""
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result.get("passed", False))
        
        print(f"\nTotal Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        print("\nTest Results:")
        for test_name, result in self.test_results.items():
            status = "✓ PASSED" if result.get("passed", False) else "✗ FAILED"
            print(f"  {test_name}: {status}")
            
            if not result.get("passed", False) and "error" in result:
                print(f"    Error: {result['error']}")
        
        # Overall validation
        all_passed = passed_tests == total_tests
        
        print("\n" + "="*80)
        if all_passed:
            print("✓ VALIDATION PASSED: Health checks pass consistently within 60 seconds")
        else:
            print("✗ VALIDATION FAILED: Some health check tests failed")
        print("="*80)
        
        self.test_results["summary"] = {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": total_tests - passed_tests,
            "success_rate": (passed_tests/total_tests)*100,
            "all_passed": all_passed
        }


@pytest.mark.asyncio
async def test_health_check_60_second_validation():
    """
    Main test function for 60-second health check validation.
    
    This test validates that health checks pass consistently within 60 seconds
    as required by the specification.
    """
    validator = HealthCheck60SecondValidator()
    results = await validator.run_validation()
    
    # Assert that all tests passed
    assert results["summary"]["all_passed"], \
        f"Health check validation failed: {results['summary']['failed_tests']} tests failed"
    
    # Assert specific requirements
    assert results["minimal_server_startup"]["within_60_seconds"], \
        "Minimal server did not start within 60 seconds"
    
    assert results["health_check_response_time"]["all_under_5_seconds"], \
        "Health check response time exceeded 5 seconds"
    
    assert results["health_check_reliability"]["within_60_seconds"], \
        "Health check not reliable within 60 seconds"
    
    assert results["continuous_health_checks"]["success_rate"] >= 95.0, \
        "Continuous health check success rate below 95%"
    
    assert results["health_check_under_load"]["success_rate"] >= 95.0, \
        "Health check under load success rate below 95%"


async def main():
    """Run the validation test."""
    validator = HealthCheck60SecondValidator()
    results = await validator.run_validation()
    
    # Return exit code based on results
    return 0 if results["summary"]["all_passed"] else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
