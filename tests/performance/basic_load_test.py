#!/usr/bin/env python3
"""
Basic Load Testing Framework for AWS Learning Deployment

This module provides basic load testing capabilities for the Multimodal Librarian
system deployed on AWS. It focuses on learning-oriented testing with cost-optimized
scenarios suitable for understanding system behavior under light load.

Test Scenarios:
- Basic API endpoint load testing
- Database connection stress testing
- File upload/download performance
- WebSocket connection testing
- ML training API load testing
"""

import os
import sys
import asyncio
import aiohttp
import time
import json
import statistics
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from multimodal_librarian.logging_config import get_logger


@dataclass
class LoadTestResult:
    """Load test result data structure."""
    test_name: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    total_requests: int
    successful_requests: int
    failed_requests: int
    requests_per_second: float
    avg_response_time_ms: float
    min_response_time_ms: float
    max_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    error_rate_percent: float
    throughput_mb_per_sec: float
    errors: List[str]


@dataclass
class LoadTestConfig:
    """Load test configuration."""
    base_url: str
    concurrent_users: int
    test_duration_seconds: int
    ramp_up_seconds: int
    request_timeout_seconds: int
    think_time_seconds: float
    max_requests_per_user: Optional[int] = None


class BasicLoadTester:
    """Basic load testing framework for learning purposes."""
    
    def __init__(self, config: LoadTestConfig):
        self.config = config
        self.logger = get_logger("basic_load_tester")
        
        # Test results tracking
        self.results: List[LoadTestResult] = []
        self.active_sessions = 0
        self.session_lock = threading.Lock()
        
        # Performance metrics
        self.response_times = []
        self.request_sizes = []
        self.response_sizes = []
        self.errors = []
        
        self.logger.info(f"Initialized load tester for {config.base_url}")
        self.logger.info(f"Config: {config.concurrent_users} users, {config.test_duration_seconds}s duration")
    
    async def run_load_test(self, test_scenarios: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Run comprehensive load test with multiple scenarios."""
        self.logger.info("🚀 Starting basic load test suite")
        
        test_suite_results = {
            "start_time": datetime.now(),
            "config": asdict(self.config),
            "scenario_results": [],
            "summary": {}
        }
        
        print("=" * 80)
        print("🚀 BASIC LOAD TEST SUITE")
        print("=" * 80)
        print(f"📅 Started: {test_suite_results['start_time'].isoformat()}")
        print(f"🎯 Target: {self.config.base_url}")
        print(f"👥 Concurrent Users: {self.config.concurrent_users}")
        print(f"⏱️  Duration: {self.config.test_duration_seconds}s")
        print()
        
        # Run each test scenario
        for i, scenario in enumerate(test_scenarios, 1):
            print(f"📋 [{i}/{len(test_scenarios)}] {scenario['name']}")
            print(f"   {scenario.get('description', 'No description')}")
            print("-" * 60)
            
            try:
                result = await self._run_scenario(scenario)
                test_suite_results["scenario_results"].append(result)
                
                # Print scenario summary
                self._print_scenario_summary(result)
                
            except Exception as e:
                self.logger.error(f"Error in scenario {scenario['name']}: {e}")
                error_result = LoadTestResult(
                    test_name=scenario['name'],
                    start_time=datetime.now(),
                    end_time=datetime.now(),
                    duration_seconds=0,
                    total_requests=0,
                    successful_requests=0,
                    failed_requests=0,
                    requests_per_second=0,
                    avg_response_time_ms=0,
                    min_response_time_ms=0,
                    max_response_time_ms=0,
                    p95_response_time_ms=0,
                    p99_response_time_ms=0,
                    error_rate_percent=100,
                    throughput_mb_per_sec=0,
                    errors=[str(e)]
                )
                test_suite_results["scenario_results"].append(error_result)
            
            print()
        
        # Calculate final summary
        test_suite_results["end_time"] = datetime.now()
        test_suite_results["total_duration"] = (
            test_suite_results["end_time"] - test_suite_results["start_time"]
        ).total_seconds()
        test_suite_results["summary"] = self._calculate_suite_summary(test_suite_results["scenario_results"])
        
        # Print final summary
        self._print_suite_summary(test_suite_results)
        
        return test_suite_results
    
    async def _run_scenario(self, scenario: Dict[str, Any]) -> LoadTestResult:
        """Run a single load test scenario."""
        scenario_name = scenario['name']
        endpoint = scenario['endpoint']
        method = scenario.get('method', 'GET')
        payload = scenario.get('payload')
        headers = scenario.get('headers', {})
        
        self.logger.info(f"Starting scenario: {scenario_name}")
        
        # Reset metrics for this scenario
        self.response_times = []
        self.request_sizes = []
        self.response_sizes = []
        self.errors = []
        
        start_time = datetime.now()
        
        # Create semaphore to limit concurrent requests
        semaphore = asyncio.Semaphore(self.config.concurrent_users)
        
        # Create tasks for concurrent users
        tasks = []
        for user_id in range(self.config.concurrent_users):
            task = asyncio.create_task(
                self._simulate_user(
                    user_id, endpoint, method, payload, headers, semaphore
                )
            )
            tasks.append(task)
            
            # Ramp up delay
            if self.config.ramp_up_seconds > 0:
                ramp_delay = self.config.ramp_up_seconds / self.config.concurrent_users
                await asyncio.sleep(ramp_delay)
        
        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Calculate results
        result = self._calculate_scenario_results(
            scenario_name, start_time, end_time, duration
        )
        
        self.logger.info(f"Completed scenario: {scenario_name}")
        return result
    
    async def _simulate_user(
        self, 
        user_id: int, 
        endpoint: str, 
        method: str, 
        payload: Optional[Dict], 
        headers: Dict[str, str],
        semaphore: asyncio.Semaphore
    ):
        """Simulate a single user's load testing behavior."""
        url = f"{self.config.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        
        async with semaphore:
            with self.session_lock:
                self.active_sessions += 1
            
            try:
                timeout = aiohttp.ClientTimeout(total=self.config.request_timeout_seconds)
                
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    start_time = time.time()
                    end_test_time = start_time + self.config.test_duration_seconds
                    request_count = 0
                    
                    while time.time() < end_test_time:
                        # Check max requests limit
                        if (self.config.max_requests_per_user and 
                            request_count >= self.config.max_requests_per_user):
                            break
                        
                        try:
                            request_start = time.time()
                            
                            # Make request
                            if method.upper() == 'POST':
                                async with session.post(url, json=payload, headers=headers) as response:
                                    response_data = await response.read()
                                    response_time = (time.time() - request_start) * 1000
                                    
                                    # Record metrics
                                    self.response_times.append(response_time)
                                    if payload:
                                        self.request_sizes.append(len(json.dumps(payload).encode()))
                                    self.response_sizes.append(len(response_data))
                                    
                                    if response.status >= 400:
                                        self.errors.append(f"HTTP {response.status}: {response.reason}")
                            
                            elif method.upper() == 'GET':
                                async with session.get(url, headers=headers) as response:
                                    response_data = await response.read()
                                    response_time = (time.time() - request_start) * 1000
                                    
                                    # Record metrics
                                    self.response_times.append(response_time)
                                    self.response_sizes.append(len(response_data))
                                    
                                    if response.status >= 400:
                                        self.errors.append(f"HTTP {response.status}: {response.reason}")
                            
                            request_count += 1
                            
                            # Think time between requests
                            if self.config.think_time_seconds > 0:
                                await asyncio.sleep(self.config.think_time_seconds)
                        
                        except asyncio.TimeoutError:
                            self.errors.append("Request timeout")
                        except Exception as e:
                            self.errors.append(f"Request error: {str(e)}")
                        
                        # Small delay to prevent overwhelming
                        await asyncio.sleep(0.01)
            
            finally:
                with self.session_lock:
                    self.active_sessions -= 1
    
    def _calculate_scenario_results(
        self, 
        scenario_name: str, 
        start_time: datetime, 
        end_time: datetime, 
        duration: float
    ) -> LoadTestResult:
        """Calculate results for a completed scenario."""
        total_requests = len(self.response_times)
        failed_requests = len(self.errors)
        successful_requests = total_requests - failed_requests
        
        if total_requests == 0:
            return LoadTestResult(
                test_name=scenario_name,
                start_time=start_time,
                end_time=end_time,
                duration_seconds=duration,
                total_requests=0,
                successful_requests=0,
                failed_requests=0,
                requests_per_second=0,
                avg_response_time_ms=0,
                min_response_time_ms=0,
                max_response_time_ms=0,
                p95_response_time_ms=0,
                p99_response_time_ms=0,
                error_rate_percent=0,
                throughput_mb_per_sec=0,
                errors=self.errors[:10]  # Limit error list
            )
        
        # Calculate response time statistics
        avg_response_time = statistics.mean(self.response_times)
        min_response_time = min(self.response_times)
        max_response_time = max(self.response_times)
        
        # Calculate percentiles
        sorted_times = sorted(self.response_times)
        p95_index = int(0.95 * len(sorted_times))
        p99_index = int(0.99 * len(sorted_times))
        p95_response_time = sorted_times[p95_index] if p95_index < len(sorted_times) else max_response_time
        p99_response_time = sorted_times[p99_index] if p99_index < len(sorted_times) else max_response_time
        
        # Calculate throughput
        total_bytes = sum(self.response_sizes)
        throughput_mb_per_sec = (total_bytes / (1024 * 1024)) / max(duration, 0.001)
        
        return LoadTestResult(
            test_name=scenario_name,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            total_requests=total_requests,
            successful_requests=successful_requests,
            failed_requests=failed_requests,
            requests_per_second=total_requests / max(duration, 0.001),
            avg_response_time_ms=avg_response_time,
            min_response_time_ms=min_response_time,
            max_response_time_ms=max_response_time,
            p95_response_time_ms=p95_response_time,
            p99_response_time_ms=p99_response_time,
            error_rate_percent=(failed_requests / total_requests) * 100,
            throughput_mb_per_sec=throughput_mb_per_sec,
            errors=list(set(self.errors[:10]))  # Unique errors, limited
        )
    
    def _calculate_suite_summary(self, scenario_results: List[LoadTestResult]) -> Dict[str, Any]:
        """Calculate summary statistics for the entire test suite."""
        if not scenario_results:
            return {}
        
        total_requests = sum(r.total_requests for r in scenario_results)
        total_successful = sum(r.successful_requests for r in scenario_results)
        total_failed = sum(r.failed_requests for r in scenario_results)
        
        avg_rps = statistics.mean([r.requests_per_second for r in scenario_results if r.requests_per_second > 0])
        avg_response_time = statistics.mean([r.avg_response_time_ms for r in scenario_results if r.avg_response_time_ms > 0])
        avg_error_rate = statistics.mean([r.error_rate_percent for r in scenario_results])
        
        return {
            "total_scenarios": len(scenario_results),
            "successful_scenarios": len([r for r in scenario_results if r.error_rate_percent < 5]),
            "total_requests": total_requests,
            "total_successful_requests": total_successful,
            "total_failed_requests": total_failed,
            "overall_success_rate": (total_successful / max(total_requests, 1)) * 100,
            "average_requests_per_second": avg_rps,
            "average_response_time_ms": avg_response_time,
            "average_error_rate": avg_error_rate,
            "max_response_time_ms": max([r.max_response_time_ms for r in scenario_results], default=0),
            "total_throughput_mb_per_sec": sum(r.throughput_mb_per_sec for r in scenario_results)
        }
    
    def _print_scenario_summary(self, result: LoadTestResult):
        """Print summary for a single scenario."""
        status_icon = "✅" if result.error_rate_percent < 5 else "⚠️" if result.error_rate_percent < 20 else "❌"
        
        print(f"{status_icon} {result.test_name}")
        print(f"   Duration: {result.duration_seconds:.1f}s")
        print(f"   Requests: {result.total_requests} ({result.successful_requests} success, {result.failed_requests} failed)")
        print(f"   RPS: {result.requests_per_second:.1f}")
        print(f"   Avg Response: {result.avg_response_time_ms:.1f}ms")
        print(f"   P95 Response: {result.p95_response_time_ms:.1f}ms")
        print(f"   Error Rate: {result.error_rate_percent:.1f}%")
        print(f"   Throughput: {result.throughput_mb_per_sec:.2f} MB/s")
        
        if result.errors:
            print(f"   Top Errors: {', '.join(result.errors[:3])}")
    
    def _print_suite_summary(self, test_suite_results: Dict[str, Any]):
        """Print final test suite summary."""
        summary = test_suite_results["summary"]
        
        print("=" * 80)
        print("📊 LOAD TEST SUITE SUMMARY")
        print("=" * 80)
        print(f"⏱️  Total Duration: {test_suite_results['total_duration']:.1f} seconds")
        print()
        
        print("📋 Scenarios:")
        print(f"   Total: {summary.get('total_scenarios', 0)}")
        print(f"   ✅ Successful: {summary.get('successful_scenarios', 0)}")
        print(f"   ❌ Failed: {summary.get('total_scenarios', 0) - summary.get('successful_scenarios', 0)}")
        print()
        
        print("🧪 Requests:")
        print(f"   Total: {summary.get('total_requests', 0)}")
        print(f"   ✅ Successful: {summary.get('total_successful_requests', 0)}")
        print(f"   ❌ Failed: {summary.get('total_failed_requests', 0)}")
        print(f"   📈 Success Rate: {summary.get('overall_success_rate', 0):.1f}%")
        print()
        
        print("⚡ Performance:")
        print(f"   Average RPS: {summary.get('average_requests_per_second', 0):.1f}")
        print(f"   Average Response Time: {summary.get('average_response_time_ms', 0):.1f}ms")
        print(f"   Max Response Time: {summary.get('max_response_time_ms', 0):.1f}ms")
        print(f"   Total Throughput: {summary.get('total_throughput_mb_per_sec', 0):.2f} MB/s")
        print()
        
        # Overall result
        overall_success_rate = summary.get('overall_success_rate', 0)
        if overall_success_rate >= 95:
            print("🎉 EXCELLENT PERFORMANCE - System handled load very well!")
        elif overall_success_rate >= 90:
            print("✅ GOOD PERFORMANCE - System performed well under load")
        elif overall_success_rate >= 80:
            print("⚠️  ACCEPTABLE PERFORMANCE - Some issues detected")
        else:
            print("❌ POOR PERFORMANCE - System struggled under load")
        
        print("=" * 80)


def create_basic_test_scenarios(base_url: str) -> List[Dict[str, Any]]:
    """Create basic load test scenarios for the application."""
    return [
        {
            "name": "Health Check Load Test",
            "description": "Test system health endpoint under load",
            "endpoint": "/health",
            "method": "GET"
        },
        {
            "name": "API Info Load Test",
            "description": "Test API info endpoint performance",
            "endpoint": "/api/info",
            "method": "GET"
        },
        {
            "name": "Chat Interface Load Test",
            "description": "Test chat interface under concurrent users",
            "endpoint": "/",
            "method": "GET"
        },
        {
            "name": "Conversation List Load Test",
            "description": "Test conversation listing performance",
            "endpoint": "/api/conversations",
            "method": "GET",
            "headers": {"Authorization": "Bearer test-token"}
        },
        {
            "name": "Document Upload Simulation",
            "description": "Simulate document upload requests",
            "endpoint": "/api/documents/upload",
            "method": "POST",
            "payload": {
                "filename": "test_document.pdf",
                "content_type": "application/pdf",
                "size": 1024
            },
            "headers": {"Content-Type": "application/json"}
        }
    ]


async def run_basic_load_test(
    base_url: str = "http://localhost:8000",
    concurrent_users: int = 10,
    test_duration: int = 30,
    output_file: Optional[str] = None
) -> Dict[str, Any]:
    """Run basic load test with default configuration."""
    
    # Create load test configuration
    config = LoadTestConfig(
        base_url=base_url,
        concurrent_users=concurrent_users,
        test_duration_seconds=test_duration,
        ramp_up_seconds=5,
        request_timeout_seconds=30,
        think_time_seconds=0.1,
        max_requests_per_user=100
    )
    
    # Create test scenarios
    scenarios = create_basic_test_scenarios(base_url)
    
    # Run load test
    tester = BasicLoadTester(config)
    results = await tester.run_load_test(scenarios)
    
    # Save results if requested
    if output_file:
        try:
            # Convert datetime objects to strings for JSON serialization
            results_copy = json.loads(json.dumps(results, default=str))
            
            with open(output_file, 'w') as f:
                json.dump(results_copy, f, indent=2)
            
            print(f"📄 Results saved to: {output_file}")
            
        except Exception as e:
            print(f"⚠️  Could not save results: {e}")
    
    return results


def main():
    """Main load test runner function."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run Basic Load Tests')
    parser.add_argument('--url', type=str, default='http://localhost:8000',
                       help='Base URL for load testing')
    parser.add_argument('--users', type=int, default=10,
                       help='Number of concurrent users')
    parser.add_argument('--duration', type=int, default=30,
                       help='Test duration in seconds')
    parser.add_argument('--output', type=str,
                       help='Output file for results (JSON)')
    
    args = parser.parse_args()
    
    # Run load test
    results = asyncio.run(run_basic_load_test(
        base_url=args.url,
        concurrent_users=args.users,
        test_duration=args.duration,
        output_file=args.output
    ))
    
    # Exit with appropriate code
    summary = results.get("summary", {})
    success_rate = summary.get("overall_success_rate", 0)
    
    if success_rate >= 90:
        exit(0)  # Success
    elif success_rate >= 80:
        exit(1)  # Warning
    else:
        exit(2)  # Failure


if __name__ == "__main__":
    main()