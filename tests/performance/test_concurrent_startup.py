#!/usr/bin/env python3
"""
Concurrent User Requests During Model Loading Test

This module tests how the application handles concurrent user requests
while models are still loading during startup. This validates that:

1. Requests don't fail due to "model not loaded" errors
2. Fallback responses are provided immediately
3. System remains responsive under concurrent load
4. No race conditions or deadlocks occur during model loading

Validates Requirements:
- REQ-2: Application Startup Optimization (graceful degradation)
- REQ-3: Smart User Experience (immediate feedback)

Test Scenarios:
1. Multiple concurrent requests during MINIMAL phase
2. Concurrent requests while essential models are loading
3. Mixed request types during progressive model loading
4. Stress test with high concurrency during startup
"""

import os
import sys
import asyncio
import aiohttp
import time
import statistics
from typing import Dict, Any, List, Optional, Tuple
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
class ConcurrentRequestResult:
    """Results from concurrent request testing."""
    test_name: str
    concurrent_users: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    model_not_loaded_errors: int
    fallback_responses: int
    avg_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    max_response_time_ms: float
    min_response_time_ms: float
    requests_per_second: float
    error_rate_percent: float
    fallback_rate_percent: float
    response_quality_distribution: Dict[str, int]
    errors: List[str]
    duration_seconds: float


class ConcurrentStartupTester:
    """Tests concurrent user requests during model loading."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.logger = get_logger("concurrent_startup_tester")
        
        # Metrics
        self.response_times = []
        self.model_not_loaded_errors = 0
        self.fallback_responses = 0
        self.total_responses = 0
        self.response_quality = {"basic": 0, "enhanced": 0, "full": 0, "error": 0}
        self.errors = []
        
        self.logger.info(f"Initialized concurrent startup tester for {self.base_url}")
    
    async def test_concurrent_requests_minimal_phase(
        self,
        concurrent_users: int = 10,
        requests_per_user: int = 5
    ) -> ConcurrentRequestResult:
        """
        Test concurrent requests during MINIMAL phase.
        
        During this phase, models are not yet loaded, so all requests
        should receive fallback responses without errors.
        """
        self.logger.info(f"Testing {concurrent_users} concurrent users during MINIMAL phase...")
        self._reset_metrics()
        
        start_time = time.time()
        
        # Create concurrent user tasks
        tasks = []
        for user_id in range(concurrent_users):
            task = asyncio.create_task(
                self._simulate_user_requests(
                    user_id,
                    requests_per_user,
                    request_types=["health", "status", "chat"]
                )
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        duration = time.time() - start_time
        
        # Calculate results
        result = self._calculate_results(
            "concurrent_minimal_phase",
            concurrent_users,
            duration
        )
        
        self.logger.info(f"MINIMAL phase concurrent test completed: {result.total_requests} requests")
        return result
    
    async def test_concurrent_requests_during_model_loading(
        self,
        concurrent_users: int = 15,
        requests_per_user: int = 10,
        simulate_loading_delay: bool = True
    ) -> ConcurrentRequestResult:
        """
        Test concurrent requests while models are actively loading.
        
        This simulates the critical period when:
        - Some models are loaded, others are still loading
        - Users are making various types of requests
        - System must handle mixed availability gracefully
        """
        self.logger.info(f"Testing {concurrent_users} concurrent users during model loading...")
        self._reset_metrics()
        
        start_time = time.time()
        
        # Create concurrent user tasks with varied request patterns
        tasks = []
        for user_id in range(concurrent_users):
            # Different users try different features
            if user_id % 3 == 0:
                request_types = ["chat", "chat", "status"]
            elif user_id % 3 == 1:
                request_types = ["search", "documents", "status"]
            else:
                request_types = ["health", "chat", "search"]
            
            task = asyncio.create_task(
                self._simulate_user_requests(
                    user_id,
                    requests_per_user,
                    request_types=request_types,
                    think_time=0.5
                )
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        duration = time.time() - start_time
        
        # Calculate results
        result = self._calculate_results(
            "concurrent_during_loading",
            concurrent_users,
            duration
        )
        
        self.logger.info(f"Model loading concurrent test completed: {result.total_requests} requests")
        return result
    
    async def test_high_concurrency_stress(
        self,
        concurrent_users: int = 50,
        requests_per_user: int = 20
    ) -> ConcurrentRequestResult:
        """
        Stress test with high concurrency during startup.
        
        This validates that the system can handle many concurrent users
        without deadlocks, race conditions, or cascading failures.
        """
        self.logger.info(f"Stress testing with {concurrent_users} concurrent users...")
        self._reset_metrics()
        
        start_time = time.time()
        
        # Create many concurrent user tasks
        tasks = []
        for user_id in range(concurrent_users):
            task = asyncio.create_task(
                self._simulate_user_requests(
                    user_id,
                    requests_per_user,
                    request_types=["health", "chat", "search", "status"],
                    think_time=0.1  # Aggressive timing
                )
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        duration = time.time() - start_time
        
        # Calculate results
        result = self._calculate_results(
            "high_concurrency_stress",
            concurrent_users,
            duration
        )
        
        self.logger.info(f"Stress test completed: {result.total_requests} requests")
        return result
    
    async def test_mixed_request_patterns(
        self,
        concurrent_users: int = 20,
        duration_seconds: int = 30
    ) -> ConcurrentRequestResult:
        """
        Test mixed request patterns during startup.
        
        Simulates realistic scenario where different users:
        - Check health status
        - Try to chat
        - Search for documents
        - Check loading progress
        """
        self.logger.info(f"Testing mixed request patterns with {concurrent_users} users...")
        self._reset_metrics()
        
        start_time = time.time()
        
        # Create concurrent user tasks with different behaviors
        tasks = []
        for user_id in range(concurrent_users):
            # Assign different user behaviors
            if user_id % 4 == 0:
                # Impatient user - keeps checking status
                behavior = "status_checker"
            elif user_id % 4 == 1:
                # Chat user - tries to chat immediately
                behavior = "chat_user"
            elif user_id % 4 == 2:
                # Search user - tries to search
                behavior = "search_user"
            else:
                # Mixed user - tries everything
                behavior = "mixed_user"
            
            task = asyncio.create_task(
                self._simulate_user_behavior(
                    user_id,
                    behavior,
                    duration_seconds
                )
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        duration = time.time() - start_time
        
        # Calculate results
        result = self._calculate_results(
            "mixed_request_patterns",
            concurrent_users,
            duration
        )
        
        self.logger.info(f"Mixed patterns test completed: {result.total_requests} requests")
        return result
    
    async def _simulate_user_requests(
        self,
        user_id: int,
        num_requests: int,
        request_types: List[str],
        think_time: float = 1.0
    ):
        """Simulate a user making multiple requests."""
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for i in range(num_requests):
                try:
                    # Pick a request type
                    request_type = request_types[i % len(request_types)]
                    
                    # Make the request
                    await self._make_typed_request(session, request_type)
                    
                    # Think time between requests
                    await asyncio.sleep(think_time)
                    
                except Exception as e:
                    self.errors.append(f"User {user_id} request {i}: {str(e)}")
    
    async def _simulate_user_behavior(
        self,
        user_id: int,
        behavior: str,
        duration_seconds: int
    ):
        """Simulate specific user behavior patterns."""
        timeout = aiohttp.ClientTimeout(total=30)
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            end_time = time.time() + duration_seconds
            
            while time.time() < end_time:
                try:
                    if behavior == "status_checker":
                        # Keeps checking status frequently
                        await self._make_typed_request(session, "status")
                        await asyncio.sleep(0.5)
                    
                    elif behavior == "chat_user":
                        # Tries to chat, checks status if not ready
                        await self._make_typed_request(session, "chat")
                        await asyncio.sleep(2.0)
                    
                    elif behavior == "search_user":
                        # Tries to search
                        await self._make_typed_request(session, "search")
                        await asyncio.sleep(1.5)
                    
                    else:  # mixed_user
                        # Tries different things
                        for request_type in ["health", "chat", "search", "status"]:
                            await self._make_typed_request(session, request_type)
                            await asyncio.sleep(1.0)
                    
                except Exception as e:
                    self.errors.append(f"User {user_id} ({behavior}): {str(e)}")
    
    async def _make_typed_request(
        self,
        session: aiohttp.ClientSession,
        request_type: str
    ):
        """Make a specific type of request."""
        start_time = time.time()
        
        try:
            if request_type == "health":
                url = f"{self.base_url}/health/minimal"
                async with session.get(url) as response:
                    await self._process_response(response, start_time, request_type)
            
            elif request_type == "status":
                url = f"{self.base_url}/api/loading/status"
                async with session.get(url) as response:
                    await self._process_response(response, start_time, request_type)
            
            elif request_type == "chat":
                url = f"{self.base_url}/api/chat"
                payload = {"message": "Hello, are you ready?"}
                async with session.post(url, json=payload) as response:
                    await self._process_response(response, start_time, request_type)
            
            elif request_type == "search":
                url = f"{self.base_url}/api/search?q=test"
                async with session.get(url) as response:
                    await self._process_response(response, start_time, request_type)
            
            elif request_type == "documents":
                url = f"{self.base_url}/api/documents"
                async with session.get(url) as response:
                    await self._process_response(response, start_time, request_type)
        
        except asyncio.TimeoutError:
            self.errors.append(f"Timeout: {request_type}")
            self.response_quality["error"] += 1
        except Exception as e:
            self.errors.append(f"Error on {request_type}: {str(e)}")
            self.response_quality["error"] += 1
    
    async def _process_response(
        self,
        response: aiohttp.ClientResponse,
        start_time: float,
        request_type: str
    ):
        """Process a response and record metrics."""
        response_time = (time.time() - start_time) * 1000
        self.response_times.append(response_time)
        self.total_responses += 1
        
        try:
            response_data = await response.text()
            
            # Check for model not loaded errors
            if "model not loaded" in response_data.lower() or "model is not available" in response_data.lower():
                self.model_not_loaded_errors += 1
                self.errors.append(f"Model not loaded error on {request_type}")
            
            # Check for fallback responses
            if "loading" in response_data.lower() or "fallback" in response_data.lower():
                self.fallback_responses += 1
            
            # Determine response quality
            if response.status >= 500:
                self.response_quality["error"] += 1
            elif response.status >= 400:
                self.response_quality["error"] += 1
            elif "response_quality" in response_data.lower():
                # Try to parse quality indicator
                if "basic" in response_data.lower():
                    self.response_quality["basic"] += 1
                elif "enhanced" in response_data.lower():
                    self.response_quality["enhanced"] += 1
                elif "full" in response_data.lower():
                    self.response_quality["full"] += 1
                else:
                    self.response_quality["basic"] += 1
            else:
                # Default to basic if no quality indicator
                self.response_quality["basic"] += 1
        
        except Exception as e:
            self.errors.append(f"Error processing response: {str(e)}")
            self.response_quality["error"] += 1
    
    def _reset_metrics(self):
        """Reset metrics for a new test."""
        self.response_times = []
        self.model_not_loaded_errors = 0
        self.fallback_responses = 0
        self.total_responses = 0
        self.response_quality = {"basic": 0, "enhanced": 0, "full": 0, "error": 0}
        self.errors = []
    
    def _calculate_results(
        self,
        test_name: str,
        concurrent_users: int,
        duration: float
    ) -> ConcurrentRequestResult:
        """Calculate results from metrics."""
        total_requests = len(self.response_times)
        failed_requests = self.response_quality["error"]
        successful_requests = total_requests - failed_requests
        
        if total_requests == 0:
            return ConcurrentRequestResult(
                test_name=test_name,
                concurrent_users=concurrent_users,
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
                model_not_loaded_errors=0,
                fallback_responses=0,
                avg_response_time_ms=0,
                p95_response_time_ms=0,
                p99_response_time_ms=0,
                max_response_time_ms=0,
                min_response_time_ms=0,
                requests_per_second=0,
                error_rate_percent=0,
                fallback_rate_percent=0,
                response_quality_distribution={},
                errors=[],
                duration_seconds=duration
            )
        
        # Calculate response time statistics
        sorted_times = sorted(self.response_times)
        avg_response_time = statistics.mean(self.response_times)
        max_response_time = max(self.response_times)
        min_response_time = min(self.response_times)
        
        # Calculate percentiles
        p95_index = int(0.95 * len(sorted_times))
        p99_index = int(0.99 * len(sorted_times))
        
        p95_response_time = sorted_times[p95_index] if p95_index < len(sorted_times) else max_response_time
        p99_response_time = sorted_times[p99_index] if p99_index < len(sorted_times) else max_response_time
        
        # Calculate rates
        requests_per_second = total_requests / duration if duration > 0 else 0
        error_rate = (failed_requests / total_requests) * 100
        fallback_rate = (self.fallback_responses / self.total_responses) * 100 if self.total_responses > 0 else 0
        
        return ConcurrentRequestResult(
            test_name=test_name,
            concurrent_users=concurrent_users,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            model_not_loaded_errors=self.model_not_loaded_errors,
            fallback_responses=self.fallback_responses,
            avg_response_time_ms=avg_response_time,
            p95_response_time_ms=p95_response_time,
            p99_response_time_ms=p99_response_time,
            max_response_time_ms=max_response_time,
            min_response_time_ms=min_response_time,
            requests_per_second=requests_per_second,
            error_rate_percent=error_rate,
            fallback_rate_percent=fallback_rate,
            response_quality_distribution=self.response_quality.copy(),
            errors=list(set(self.errors[:10])),  # Unique errors, limited
            duration_seconds=duration
        )


async def run_concurrent_startup_tests(
    base_url: str = "http://localhost:8000",
    output_directory: str = "load_test_results"
) -> Dict[str, Any]:
    """Run comprehensive concurrent startup tests."""
    
    logger = get_logger("concurrent_startup_tests")
    logger.info("Starting concurrent startup tests")
    
    # Ensure output directory exists
    os.makedirs(output_directory, exist_ok=True)
    
    # Create tester
    tester = ConcurrentStartupTester(base_url)
    
    test_results = {
        "start_time": datetime.now().isoformat(),
        "base_url": base_url,
        "test_type": "concurrent_startup",
        "tests": {}
    }
    
    print("=" * 80)
    print("🔄 CONCURRENT REQUESTS DURING MODEL LOADING TESTS")
    print("=" * 80)
    print(f"Target: {base_url}")
    print()
    
    try:
        # Test 1: Concurrent requests during minimal phase
        print("📊 Test 1: Concurrent Requests During MINIMAL Phase")
        print("-" * 80)
        
        minimal_result = await tester.test_concurrent_requests_minimal_phase(
            concurrent_users=10,
            requests_per_user=5
        )
        
        test_results["tests"]["minimal_phase"] = asdict(minimal_result)
        
        print(f"✅ Completed: {minimal_result.total_requests} requests from {minimal_result.concurrent_users} users")
        print(f"   Success Rate: {100 - minimal_result.error_rate_percent:.1f}%")
        print(f"   Model Not Loaded Errors: {minimal_result.model_not_loaded_errors}")
        print(f"   Fallback Responses: {minimal_result.fallback_responses} ({minimal_result.fallback_rate_percent:.1f}%)")
        print(f"   Avg Response Time: {minimal_result.avg_response_time_ms:.1f}ms")
        print(f"   Requests/sec: {minimal_result.requests_per_second:.1f}")
        print()
        
        # Test 2: Concurrent requests during model loading
        print("📊 Test 2: Concurrent Requests During Model Loading")
        print("-" * 80)
        
        loading_result = await tester.test_concurrent_requests_during_model_loading(
            concurrent_users=15,
            requests_per_user=10
        )
        
        test_results["tests"]["during_loading"] = asdict(loading_result)
        
        print(f"✅ Completed: {loading_result.total_requests} requests from {loading_result.concurrent_users} users")
        print(f"   Success Rate: {100 - loading_result.error_rate_percent:.1f}%")
        print(f"   Model Not Loaded Errors: {loading_result.model_not_loaded_errors}")
        print(f"   Fallback Responses: {loading_result.fallback_responses} ({loading_result.fallback_rate_percent:.1f}%)")
        print(f"   Avg Response Time: {loading_result.avg_response_time_ms:.1f}ms")
        print(f"   Requests/sec: {loading_result.requests_per_second:.1f}")
        print()
        
        # Test 3: High concurrency stress test
        print("📊 Test 3: High Concurrency Stress Test")
        print("-" * 80)
        
        stress_result = await tester.test_high_concurrency_stress(
            concurrent_users=50,
            requests_per_user=20
        )
        
        test_results["tests"]["stress_test"] = asdict(stress_result)
        
        print(f"✅ Completed: {stress_result.total_requests} requests from {stress_result.concurrent_users} users")
        print(f"   Success Rate: {100 - stress_result.error_rate_percent:.1f}%")
        print(f"   Model Not Loaded Errors: {stress_result.model_not_loaded_errors}")
        print(f"   Fallback Responses: {stress_result.fallback_responses} ({stress_result.fallback_rate_percent:.1f}%)")
        print(f"   Avg Response Time: {stress_result.avg_response_time_ms:.1f}ms")
        print(f"   P95 Response Time: {stress_result.p95_response_time_ms:.1f}ms")
        print(f"   Requests/sec: {stress_result.requests_per_second:.1f}")
        print()
        
        # Test 4: Mixed request patterns
        print("📊 Test 4: Mixed Request Patterns")
        print("-" * 80)
        
        mixed_result = await tester.test_mixed_request_patterns(
            concurrent_users=20,
            duration_seconds=30
        )
        
        test_results["tests"]["mixed_patterns"] = asdict(mixed_result)
        
        print(f"✅ Completed: {mixed_result.total_requests} requests from {mixed_result.concurrent_users} users")
        print(f"   Success Rate: {100 - mixed_result.error_rate_percent:.1f}%")
        print(f"   Model Not Loaded Errors: {mixed_result.model_not_loaded_errors}")
        print(f"   Fallback Responses: {mixed_result.fallback_responses} ({mixed_result.fallback_rate_percent:.1f}%)")
        print(f"   Response Quality Distribution:")
        for quality, count in mixed_result.response_quality_distribution.items():
            print(f"     {quality}: {count}")
        print()
        
        # Calculate summary
        all_results = [minimal_result, loading_result, stress_result, mixed_result]
        total_requests = sum(r.total_requests for r in all_results)
        total_model_errors = sum(r.model_not_loaded_errors for r in all_results)
        avg_success_rate = statistics.mean([100 - r.error_rate_percent for r in all_results])
        
        test_results["summary"] = {
            "total_requests": total_requests,
            "total_model_not_loaded_errors": total_model_errors,
            "average_success_rate": avg_success_rate,
            "tests_run": len(all_results)
        }
        
        print("=" * 80)
        print("📊 SUMMARY")
        print("=" * 80)
        print(f"Total Requests: {total_requests}")
        print(f"Model Not Loaded Errors: {total_model_errors}")
        print(f"Average Success Rate: {avg_success_rate:.1f}%")
        print()
        
        # Validate requirements
        print("✅ REQUIREMENT VALIDATION")
        print("-" * 80)
        
        # REQ-2: No requests should fail due to "model not loaded" errors
        if total_model_errors == 0:
            print("✅ REQ-2: No requests failed due to 'model not loaded' errors")
        else:
            print(f"❌ REQ-2: {total_model_errors} requests failed due to 'model not loaded' errors")
        
        # REQ-3: System should remain responsive under concurrent load
        if avg_success_rate >= 95:
            print("✅ REQ-3: System remains responsive under concurrent load (>95% success)")
        else:
            print(f"⚠️  REQ-3: Success rate below 95% ({avg_success_rate:.1f}%)")
        
        # Fallback responses should be provided
        total_fallbacks = sum(r.fallback_responses for r in all_results)
        if total_fallbacks > 0:
            print(f"✅ REQ-3: Fallback responses provided ({total_fallbacks} total)")
        else:
            print("⚠️  REQ-3: No fallback responses detected")
        
        print()
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        test_results["error"] = str(e)
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Save results
    test_results["end_time"] = datetime.now().isoformat()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_directory, f"concurrent_startup_test_{timestamp}.json")
    
    with open(output_file, 'w') as f:
        json.dump(test_results, f, indent=2)
    
    print(f"📄 Results saved to: {output_file}")
    
    return test_results


def main():
    """Main test runner."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run Concurrent Startup Tests')
    parser.add_argument('--url', type=str, default='http://localhost:8000',
                       help='Base URL for testing')
    parser.add_argument('--output-dir', type=str, default='load_test_results',
                       help='Output directory for results')
    
    args = parser.parse_args()
    
    # Run tests
    results = asyncio.run(run_concurrent_startup_tests(
        base_url=args.url,
        output_directory=args.output_dir
    ))
    
    # Exit with appropriate code
    summary = results.get("summary", {})
    model_errors = summary.get("total_model_not_loaded_errors", 0)
    success_rate = summary.get("average_success_rate", 0)
    
    if model_errors == 0 and success_rate >= 95:
        print("\n✅ Concurrent startup testing completed successfully!")
        exit(0)
    elif model_errors == 0 and success_rate >= 90:
        print("\n⚠️  Concurrent startup testing completed with warnings.")
        exit(1)
    else:
        print("\n❌ Concurrent startup testing failed.")
        exit(2)


if __name__ == "__main__":
    main()
