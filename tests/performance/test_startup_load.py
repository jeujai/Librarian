#!/usr/bin/env python3
"""
Startup Phase Load Testing

This module implements load testing specifically for the startup phases of the
multimodal-librarian application. It validates system behavior and performance
during MINIMAL, ESSENTIAL, and FULL startup phases.

Validates Requirements:
- REQ-1: Health Check Optimization
- REQ-2: Application Startup Optimization
- REQ-3: Startup Logging Enhancement

Test Scenarios:
1. Load during MINIMAL phase (0-30s)
2. Load during ESSENTIAL phase (30s-2min)
3. Load during FULL phase (2-5min)
4. Progressive load increase during startup
5. Concurrent requests during model loading
"""

import os
import sys
import asyncio
import aiohttp
import time
import statistics
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
import json

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

try:
    from multimodal_librarian.logging_config import get_logger
except ImportError:
    import logging
    def get_logger(name):
        logger = logging.getLogger(name)
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger


@dataclass
class StartupPhaseLoadResult:
    """Results from load testing a specific startup phase."""
    phase_name: str
    phase_duration_seconds: float
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    max_response_time_ms: float
    error_rate_percent: float
    health_check_success_rate: float
    fallback_response_rate: float
    capability_availability: Dict[str, bool]
    errors: List[str]


class StartupPhaseLoadTester:
    """Load tester specifically designed for startup phases."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.logger = get_logger("startup_phase_load_tester")
        
        # Metrics
        self.response_times = []
        self.health_check_results = []
        self.fallback_responses = 0
        self.total_responses = 0
        self.errors = []
        
        self.logger.info(f"Initialized startup phase load tester for {self.base_url}")
    
    async def test_minimal_phase_load(
        self,
        duration_seconds: int = 30,
        concurrent_users: int = 5
    ) -> StartupPhaseLoadResult:
        """
        Test load during MINIMAL startup phase (0-30 seconds).
        
        During this phase:
        - Health endpoints should respond quickly
        - Basic API should be available
        - Most features return fallback responses
        - No model loading should block requests
        """
        self.logger.info("Testing MINIMAL phase load...")
        self._reset_metrics()
        
        start_time = time.time()
        
        # Create concurrent user tasks
        tasks = []
        for user_id in range(concurrent_users):
            task = asyncio.create_task(
                self._minimal_phase_user_behavior(user_id, duration_seconds)
            )
            tasks.append(task)
        
        # Wait for all tasks
        await asyncio.gather(*tasks, return_exceptions=True)
        
        phase_duration = time.time() - start_time
        
        # Calculate results
        result = self._calculate_phase_results(
            "MINIMAL",
            phase_duration,
            expected_capabilities={
                "health_check": True,
                "basic_api": True,
                "chat": False,  # Should use fallback
                "document_processing": False,
                "advanced_search": False
            }
        )
        
        self.logger.info(f"MINIMAL phase test completed: {result.total_requests} requests")
        return result
    
    async def test_essential_phase_load(
        self,
        duration_seconds: int = 90,
        concurrent_users: int = 10
    ) -> StartupPhaseLoadResult:
        """
        Test load during ESSENTIAL startup phase (30s-2min).
        
        During this phase:
        - Essential models are loading
        - Basic chat functionality becomes available
        - Simple search operations work
        - Some features still use fallbacks
        """
        self.logger.info("Testing ESSENTIAL phase load...")
        self._reset_metrics()
        
        start_time = time.time()
        
        # Create concurrent user tasks
        tasks = []
        for user_id in range(concurrent_users):
            task = asyncio.create_task(
                self._essential_phase_user_behavior(user_id, duration_seconds)
            )
            tasks.append(task)
        
        # Wait for all tasks
        await asyncio.gather(*tasks, return_exceptions=True)
        
        phase_duration = time.time() - start_time
        
        # Calculate results
        result = self._calculate_phase_results(
            "ESSENTIAL",
            phase_duration,
            expected_capabilities={
                "health_check": True,
                "basic_api": True,
                "chat": True,  # Should be available
                "simple_search": True,
                "document_processing": False,  # Still loading
                "advanced_search": False
            }
        )
        
        self.logger.info(f"ESSENTIAL phase test completed: {result.total_requests} requests")
        return result
    
    async def test_full_phase_load(
        self,
        duration_seconds: int = 120,
        concurrent_users: int = 15
    ) -> StartupPhaseLoadResult:
        """
        Test load during FULL startup phase (2-5min).
        
        During this phase:
        - All models should be loaded or loading
        - Full functionality available
        - Advanced features work
        - No fallback responses needed
        """
        self.logger.info("Testing FULL phase load...")
        self._reset_metrics()
        
        start_time = time.time()
        
        # Create concurrent user tasks
        tasks = []
        for user_id in range(concurrent_users):
            task = asyncio.create_task(
                self._full_phase_user_behavior(user_id, duration_seconds)
            )
            tasks.append(task)
        
        # Wait for all tasks
        await asyncio.gather(*tasks, return_exceptions=True)
        
        phase_duration = time.time() - start_time
        
        # Calculate results
        result = self._calculate_phase_results(
            "FULL",
            phase_duration,
            expected_capabilities={
                "health_check": True,
                "basic_api": True,
                "chat": True,
                "simple_search": True,
                "document_processing": True,
                "advanced_search": True
            }
        )
        
        self.logger.info(f"FULL phase test completed: {result.total_requests} requests")
        return result
    
    async def test_progressive_load_during_startup(
        self,
        total_duration_seconds: int = 300,
        initial_users: int = 5,
        max_users: int = 20
    ) -> Dict[str, StartupPhaseLoadResult]:
        """
        Test progressive load increase during entire startup sequence.
        
        Simulates realistic scenario where users start arriving as soon as
        the application becomes available, with load increasing over time.
        """
        self.logger.info("Testing progressive load during startup...")
        
        results = {}
        
        # Phase 1: MINIMAL (0-30s) - Low load
        self.logger.info("Phase 1: MINIMAL (0-30s)")
        results["minimal"] = await self.test_minimal_phase_load(
            duration_seconds=30,
            concurrent_users=initial_users
        )
        
        # Phase 2: ESSENTIAL (30s-2min) - Increasing load
        self.logger.info("Phase 2: ESSENTIAL (30s-2min)")
        mid_users = (initial_users + max_users) // 2
        results["essential"] = await self.test_essential_phase_load(
            duration_seconds=90,
            concurrent_users=mid_users
        )
        
        # Phase 3: FULL (2min+) - Full load
        self.logger.info("Phase 3: FULL (2min+)")
        results["full"] = await self.test_full_phase_load(
            duration_seconds=120,
            concurrent_users=max_users
        )
        
        return results
    
    async def _minimal_phase_user_behavior(self, user_id: int, duration_seconds: int):
        """User behavior during MINIMAL phase - mostly health checks and basic requests."""
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            end_time = time.time() + duration_seconds
            
            while time.time() < end_time:
                try:
                    # During minimal phase, users mostly check health and try basic endpoints
                    endpoints = [
                        ("/health/minimal", "GET"),
                        ("/health", "GET"),
                        ("/", "GET"),
                        ("/api/status", "GET"),
                    ]
                    
                    endpoint, method = endpoints[user_id % len(endpoints)]
                    await self._make_request(session, endpoint, method)
                    
                    # Short think time
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    self.errors.append(f"Minimal phase user {user_id}: {str(e)}")
    
    async def _essential_phase_user_behavior(self, user_id: int, duration_seconds: int):
        """User behavior during ESSENTIAL phase - trying chat and search."""
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            end_time = time.time() + duration_seconds
            
            while time.time() < end_time:
                try:
                    # During essential phase, users try chat and search
                    endpoints = [
                        ("/health/ready", "GET"),
                        ("/api/chat", "POST"),
                        ("/api/search", "GET"),
                        ("/api/conversations", "GET"),
                    ]
                    
                    endpoint, method = endpoints[user_id % len(endpoints)]
                    
                    payload = None
                    if method == "POST" and "/chat" in endpoint:
                        payload = {"message": "Hello, are you ready?"}
                    
                    await self._make_request(session, endpoint, method, payload)
                    
                    # Normal think time
                    await asyncio.sleep(1.0)
                    
                except Exception as e:
                    self.errors.append(f"Essential phase user {user_id}: {str(e)}")
    
    async def _full_phase_user_behavior(self, user_id: int, duration_seconds: int):
        """User behavior during FULL phase - using all features."""
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            end_time = time.time() + duration_seconds
            
            while time.time() < end_time:
                try:
                    # During full phase, users use all features
                    endpoints = [
                        ("/health/full", "GET"),
                        ("/api/chat", "POST"),
                        ("/api/search", "GET"),
                        ("/api/documents", "GET"),
                        ("/api/conversations", "GET"),
                    ]
                    
                    endpoint, method = endpoints[user_id % len(endpoints)]
                    
                    payload = None
                    if method == "POST" and "/chat" in endpoint:
                        payload = {"message": "Can you analyze this document?"}
                    
                    await self._make_request(session, endpoint, method, payload)
                    
                    # Realistic think time
                    await asyncio.sleep(1.5)
                    
                except Exception as e:
                    self.errors.append(f"Full phase user {user_id}: {str(e)}")
    
    async def _make_request(
        self,
        session: aiohttp.ClientSession,
        endpoint: str,
        method: str,
        payload: Optional[Dict] = None
    ):
        """Make a request and record metrics."""
        url = f"{self.base_url}{endpoint}"
        start_time = time.time()
        
        try:
            if method.upper() == "POST":
                async with session.post(url, json=payload) as response:
                    response_data = await response.text()
                    response_time = (time.time() - start_time) * 1000
                    
                    self.response_times.append(response_time)
                    self.total_responses += 1
                    
                    # Check for fallback responses
                    if "loading" in response_data.lower() or "fallback" in response_data.lower():
                        self.fallback_responses += 1
                    
                    # Track health check results
                    if "/health" in endpoint:
                        self.health_check_results.append(response.status == 200)
                    
                    if response.status >= 400:
                        self.errors.append(f"HTTP {response.status}: {endpoint}")
            
            elif method.upper() == "GET":
                async with session.get(url) as response:
                    response_data = await response.text()
                    response_time = (time.time() - start_time) * 1000
                    
                    self.response_times.append(response_time)
                    self.total_responses += 1
                    
                    # Check for fallback responses
                    if "loading" in response_data.lower() or "fallback" in response_data.lower():
                        self.fallback_responses += 1
                    
                    # Track health check results
                    if "/health" in endpoint:
                        self.health_check_results.append(response.status == 200)
                    
                    if response.status >= 400:
                        self.errors.append(f"HTTP {response.status}: {endpoint}")
        
        except asyncio.TimeoutError:
            self.errors.append(f"Timeout: {endpoint}")
        except Exception as e:
            self.errors.append(f"Error on {endpoint}: {str(e)}")
    
    def _reset_metrics(self):
        """Reset metrics for a new test."""
        self.response_times = []
        self.health_check_results = []
        self.fallback_responses = 0
        self.total_responses = 0
        self.errors = []
    
    def _calculate_phase_results(
        self,
        phase_name: str,
        phase_duration: float,
        expected_capabilities: Dict[str, bool]
    ) -> StartupPhaseLoadResult:
        """Calculate results for a phase test."""
        total_requests = len(self.response_times)
        failed_requests = len(self.errors)
        successful_requests = total_requests - failed_requests
        
        if total_requests == 0:
            return StartupPhaseLoadResult(
                phase_name=phase_name,
                phase_duration_seconds=phase_duration,
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
                avg_response_time_ms=0,
                p95_response_time_ms=0,
                p99_response_time_ms=0,
                max_response_time_ms=0,
                error_rate_percent=0,
                health_check_success_rate=0,
                fallback_response_rate=0,
                capability_availability=expected_capabilities,
                errors=[]
            )
        
        # Calculate response time statistics
        sorted_times = sorted(self.response_times)
        avg_response_time = statistics.mean(self.response_times)
        max_response_time = max(self.response_times)
        
        # Calculate percentiles
        p95_index = int(0.95 * len(sorted_times))
        p99_index = int(0.99 * len(sorted_times))
        
        p95_response_time = sorted_times[p95_index] if p95_index < len(sorted_times) else max_response_time
        p99_response_time = sorted_times[p99_index] if p99_index < len(sorted_times) else max_response_time
        
        # Calculate health check success rate
        health_check_success_rate = (
            (sum(self.health_check_results) / len(self.health_check_results) * 100)
            if self.health_check_results else 100.0
        )
        
        # Calculate fallback response rate
        fallback_response_rate = (
            (self.fallback_responses / self.total_responses * 100)
            if self.total_responses > 0 else 0.0
        )
        
        return StartupPhaseLoadResult(
            phase_name=phase_name,
            phase_duration_seconds=phase_duration,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            avg_response_time_ms=avg_response_time,
            p95_response_time_ms=p95_response_time,
            p99_response_time_ms=p99_response_time,
            max_response_time_ms=max_response_time,
            error_rate_percent=(failed_requests / total_requests) * 100,
            health_check_success_rate=health_check_success_rate,
            fallback_response_rate=fallback_response_rate,
            capability_availability=expected_capabilities,
            errors=list(set(self.errors[:10]))  # Unique errors, limited
        )


async def run_startup_phase_load_tests(
    base_url: str = "http://localhost:8000",
    output_directory: str = "load_test_results"
) -> Dict[str, Any]:
    """Run comprehensive startup phase load tests."""
    
    logger = get_logger("startup_phase_load_tests")
    logger.info("Starting startup phase load tests")
    
    # Ensure output directory exists
    os.makedirs(output_directory, exist_ok=True)
    
    # Create tester
    tester = StartupPhaseLoadTester(base_url)
    
    test_results = {
        "start_time": datetime.now().isoformat(),
        "base_url": base_url,
        "test_type": "startup_phase_load",
        "phases": {}
    }
    
    print("=" * 80)
    print("🚀 STARTUP PHASE LOAD TESTING")
    print("=" * 80)
    print(f"Target: {base_url}")
    print()
    
    try:
        # Test 1: Progressive load during startup
        print("📊 Test 1: Progressive Load During Startup")
        print("-" * 80)
        
        progressive_results = await tester.test_progressive_load_during_startup(
            total_duration_seconds=240,  # 4 minutes total
            initial_users=5,
            max_users=20
        )
        
        test_results["phases"] = {
            phase: asdict(result)
            for phase, result in progressive_results.items()
        }
        
        # Print results for each phase
        for phase_name, result in progressive_results.items():
            print(f"\n{phase_name.upper()} Phase Results:")
            print(f"  Duration: {result.phase_duration_seconds:.1f}s")
            print(f"  Requests: {result.total_requests} ({result.successful_requests} success)")
            print(f"  Avg Response Time: {result.avg_response_time_ms:.1f}ms")
            print(f"  P95 Response Time: {result.p95_response_time_ms:.1f}ms")
            print(f"  Error Rate: {result.error_rate_percent:.1f}%")
            print(f"  Health Check Success: {result.health_check_success_rate:.1f}%")
            print(f"  Fallback Response Rate: {result.fallback_response_rate:.1f}%")
            
            if result.errors:
                print(f"  Top Errors: {', '.join(result.errors[:2])}")
        
        # Calculate summary
        total_requests = sum(r.total_requests for r in progressive_results.values())
        total_successful = sum(r.successful_requests for r in progressive_results.values())
        avg_response_time = statistics.mean([r.avg_response_time_ms for r in progressive_results.values()])
        
        test_results["summary"] = {
            "total_requests": total_requests,
            "total_successful": total_successful,
            "overall_success_rate": (total_successful / total_requests * 100) if total_requests > 0 else 0,
            "average_response_time_ms": avg_response_time,
            "phases_tested": len(progressive_results)
        }
        
        print("\n" + "=" * 80)
        print("📊 SUMMARY")
        print("=" * 80)
        print(f"Total Requests: {total_requests}")
        print(f"Success Rate: {test_results['summary']['overall_success_rate']:.1f}%")
        print(f"Average Response Time: {avg_response_time:.1f}ms")
        print()
        
        # Validate requirements
        print("✅ REQUIREMENT VALIDATION")
        print("-" * 80)
        
        # REQ-1: Health Check Optimization
        minimal_result = progressive_results.get("minimal")
        if minimal_result and minimal_result.health_check_success_rate >= 95:
            print("✅ REQ-1: Health checks pass consistently (>95%)")
        else:
            print("❌ REQ-1: Health check success rate below 95%")
        
        # REQ-2: Application Startup Optimization
        if minimal_result and minimal_result.phase_duration_seconds <= 60:
            print("✅ REQ-2: Minimal phase completes within 60 seconds")
        else:
            print("❌ REQ-2: Minimal phase took too long")
        
        essential_result = progressive_results.get("essential")
        if essential_result and essential_result.fallback_response_rate < 50:
            print("✅ REQ-2: Essential models provide real responses (>50%)")
        else:
            print("⚠️  REQ-2: High fallback response rate in essential phase")
        
        # REQ-3: User Experience
        if avg_response_time < 1000:
            print("✅ REQ-3: Average response time < 1 second")
        else:
            print("⚠️  REQ-3: Average response time > 1 second")
        
        print()
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        test_results["error"] = str(e)
        print(f"\n❌ Test failed: {e}")
    
    # Save results
    test_results["end_time"] = datetime.now().isoformat()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_directory, f"startup_phase_load_test_{timestamp}.json")
    
    with open(output_file, 'w') as f:
        json.dump(test_results, f, indent=2)
    
    print(f"📄 Results saved to: {output_file}")
    
    return test_results


def main():
    """Main test runner."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run Startup Phase Load Tests')
    parser.add_argument('--url', type=str, default='http://localhost:8000',
                       help='Base URL for load testing')
    parser.add_argument('--output-dir', type=str, default='load_test_results',
                       help='Output directory for results')
    
    args = parser.parse_args()
    
    # Run tests
    results = asyncio.run(run_startup_phase_load_tests(
        base_url=args.url,
        output_directory=args.output_dir
    ))
    
    # Exit with appropriate code
    summary = results.get("summary", {})
    success_rate = summary.get("overall_success_rate", 0)
    
    if success_rate >= 95:
        print("\n✅ Startup phase load testing completed successfully!")
        exit(0)
    elif success_rate >= 90:
        print("\n⚠️  Startup phase load testing completed with warnings.")
        exit(1)
    else:
        print("\n❌ Startup phase load testing failed.")
        exit(2)


if __name__ == "__main__":
    main()
