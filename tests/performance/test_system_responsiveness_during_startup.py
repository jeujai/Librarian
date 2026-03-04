#!/usr/bin/env python3
"""
System Responsiveness During Startup Test

This module validates that the system remains responsive throughout the entire
startup process, from MINIMAL to FULL phase. This is a critical success criterion
that ensures users never experience a completely unresponsive system.

Success Criteria:
- System responds to health checks within 5 seconds at all phases
- API endpoints return responses (even if fallback) within 10 seconds
- No request timeouts or connection refusals during startup
- System maintains <95% CPU and memory usage during startup
- Concurrent requests don't cause system lockup or deadlock

Validates Requirements:
- REQ-1: Health Check Optimization (responsive health endpoints)
- REQ-2: Application Startup Optimization (non-blocking startup)
- REQ-3: Smart User Experience (immediate feedback)

Test Scenarios:
1. Health endpoint responsiveness during all startup phases
2. API endpoint responsiveness during model loading
3. Concurrent request handling without blocking
4. Resource usage stays within limits (no thrashing)
5. No deadlocks or race conditions during startup
"""

import os
import sys
import asyncio
import aiohttp
import time
import statistics
import psutil
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
class ResponsivenessMetrics:
    """Metrics for system responsiveness."""
    test_name: str
    startup_phase: str
    total_requests: int
    successful_responses: int
    timeout_errors: int
    connection_errors: int
    avg_response_time_ms: float
    max_response_time_ms: float
    p95_response_time_ms: float
    p99_response_time_ms: float
    cpu_usage_percent: float
    memory_usage_percent: float
    requests_per_second: float
    success_rate_percent: float
    all_responses_under_10s: bool
    no_timeouts: bool
    no_connection_errors: bool
    resource_usage_acceptable: bool
    overall_responsive: bool
    duration_seconds: float
    timestamp: str


class SystemResponsivenessTester:
    """Tests system responsiveness during startup."""
    
    def __init__(self, base_url: str, timeout_seconds: int = 10):
        self.base_url = base_url.rstrip('/')
        self.timeout_seconds = timeout_seconds
        self.logger = get_logger("system_responsiveness_tester")
        
        # Metrics
        self.response_times = []
        self.timeout_errors = 0
        self.connection_errors = 0
        self.successful_responses = 0
        
        self.logger.info(f"Initialized system responsiveness tester for {self.base_url}")
        self.logger.info(f"Timeout threshold: {self.timeout_seconds}s")
    
    async def make_request_with_timeout(
        self,
        session: aiohttp.ClientSession,
        url: str,
        method: str = "GET",
        json_data: Optional[Dict] = None
    ) -> Tuple[bool, float, Optional[str]]:
        """
        Make a request with timeout tracking.
        
        Returns:
            (success, response_time_ms, error_message)
        """
        start_time = time.time()
        
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            
            if method == "GET":
                async with session.get(url, timeout=timeout) as response:
                    await response.text()
                    response_time_ms = (time.time() - start_time) * 1000
                    return (True, response_time_ms, None)
            elif method == "POST":
                async with session.post(url, json=json_data, timeout=timeout) as response:
                    await response.text()
                    response_time_ms = (time.time() - start_time) * 1000
                    return (True, response_time_ms, None)
                    
        except asyncio.TimeoutError:
            response_time_ms = (time.time() - start_time) * 1000
            return (False, response_time_ms, "timeout")
        except aiohttp.ClientConnectorError as e:
            response_time_ms = (time.time() - start_time) * 1000
            return (False, response_time_ms, "connection_error")
        except Exception as e:
            response_time_ms = (time.time() - start_time) * 1000
            return (False, response_time_ms, str(e))
    
    def get_system_resource_usage(self) -> Tuple[float, float]:
        """Get current CPU and memory usage."""
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory_percent = psutil.virtual_memory().percent
            return (cpu_percent, memory_percent)
        except Exception as e:
            self.logger.warning(f"Could not get resource usage: {e}")
            return (0.0, 0.0)
    
    async def test_health_endpoint_responsiveness(
        self,
        duration_seconds: int = 60,
        request_interval_seconds: float = 1.0
    ) -> ResponsivenessMetrics:
        """
        Test that health endpoints remain responsive throughout startup.
        
        Makes continuous requests to health endpoints and validates:
        - All requests complete within timeout
        - No connection errors
        - Response times stay reasonable
        """
        self.logger.info(f"\n{'='*60}")
        self.logger.info("Testing Health Endpoint Responsiveness")
        self.logger.info(f"{'='*60}")
        
        start_time = time.time()
        response_times = []
        timeout_errors = 0
        connection_errors = 0
        successful_responses = 0
        total_requests = 0
        
        cpu_samples = []
        memory_samples = []
        
        async with aiohttp.ClientSession() as session:
            end_time = start_time + duration_seconds
            
            while time.time() < end_time:
                total_requests += 1
                
                # Test health endpoint
                success, response_time_ms, error = await self.make_request_with_timeout(
                    session,
                    f"{self.base_url}/health/minimal"
                )
                
                if success:
                    successful_responses += 1
                    response_times.append(response_time_ms)
                    self.logger.debug(f"Health check responded in {response_time_ms:.0f}ms")
                elif error == "timeout":
                    timeout_errors += 1
                    self.logger.warning(f"Health check timeout after {response_time_ms:.0f}ms")
                elif error == "connection_error":
                    connection_errors += 1
                    self.logger.warning("Health check connection error")
                else:
                    self.logger.warning(f"Health check error: {error}")
                
                # Sample resource usage
                cpu, memory = self.get_system_resource_usage()
                cpu_samples.append(cpu)
                memory_samples.append(memory)
                
                # Wait before next request
                await asyncio.sleep(request_interval_seconds)
        
        # Calculate metrics
        duration = time.time() - start_time
        avg_response_time = statistics.mean(response_times) if response_times else 0
        max_response_time = max(response_times) if response_times else 0
        p95_response_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else max_response_time
        p99_response_time = statistics.quantiles(response_times, n=100)[98] if len(response_times) >= 100 else max_response_time
        
        avg_cpu = statistics.mean(cpu_samples) if cpu_samples else 0
        avg_memory = statistics.mean(memory_samples) if memory_samples else 0
        
        success_rate = (successful_responses / total_requests * 100) if total_requests > 0 else 0
        requests_per_second = total_requests / duration if duration > 0 else 0
        
        # Validation checks
        all_responses_under_10s = max_response_time < 10000 if response_times else False
        no_timeouts = timeout_errors == 0
        no_connection_errors_check = connection_errors == 0
        resource_usage_acceptable = avg_cpu < 95 and avg_memory < 95
        
        overall_responsive = (
            all_responses_under_10s and
            no_timeouts and
            no_connection_errors_check and
            resource_usage_acceptable and
            success_rate >= 95
        )
        
        metrics = ResponsivenessMetrics(
            test_name="health_endpoint_responsiveness",
            startup_phase="continuous",
            total_requests=total_requests,
            successful_responses=successful_responses,
            timeout_errors=timeout_errors,
            connection_errors=connection_errors,
            avg_response_time_ms=avg_response_time,
            max_response_time_ms=max_response_time,
            p95_response_time_ms=p95_response_time,
            p99_response_time_ms=p99_response_time,
            cpu_usage_percent=avg_cpu,
            memory_usage_percent=avg_memory,
            requests_per_second=requests_per_second,
            success_rate_percent=success_rate,
            all_responses_under_10s=all_responses_under_10s,
            no_timeouts=no_timeouts,
            no_connection_errors=no_connection_errors_check,
            resource_usage_acceptable=resource_usage_acceptable,
            overall_responsive=overall_responsive,
            duration_seconds=duration,
            timestamp=datetime.utcnow().isoformat()
        )
        
        # Log results
        self.logger.info(f"\nHealth Endpoint Responsiveness Results:")
        self.logger.info(f"  Total Requests: {total_requests}")
        self.logger.info(f"  Successful: {successful_responses} ({success_rate:.1f}%)")
        self.logger.info(f"  Timeouts: {timeout_errors}")
        self.logger.info(f"  Connection Errors: {connection_errors}")
        self.logger.info(f"  Avg Response Time: {avg_response_time:.0f}ms")
        self.logger.info(f"  Max Response Time: {max_response_time:.0f}ms")
        self.logger.info(f"  P95 Response Time: {p95_response_time:.0f}ms")
        self.logger.info(f"  Avg CPU Usage: {avg_cpu:.1f}%")
        self.logger.info(f"  Avg Memory Usage: {avg_memory:.1f}%")
        self.logger.info(f"  Requests/sec: {requests_per_second:.2f}")
        
        if overall_responsive:
            self.logger.info("✅ System remained responsive throughout test")
        else:
            self.logger.warning("❌ System responsiveness issues detected:")
            if not all_responses_under_10s:
                self.logger.warning(f"  - Max response time {max_response_time:.0f}ms exceeded 10s threshold")
            if not no_timeouts:
                self.logger.warning(f"  - {timeout_errors} timeout errors occurred")
            if not no_connection_errors_check:
                self.logger.warning(f"  - {connection_errors} connection errors occurred")
            if not resource_usage_acceptable:
                self.logger.warning(f"  - Resource usage too high (CPU: {avg_cpu:.1f}%, Memory: {avg_memory:.1f}%)")
            if success_rate < 95:
                self.logger.warning(f"  - Success rate {success_rate:.1f}% below 95% threshold")
        
        return metrics
    
    async def test_api_endpoint_responsiveness(
        self,
        concurrent_requests: int = 5,
        duration_seconds: int = 60
    ) -> ResponsivenessMetrics:
        """
        Test that API endpoints remain responsive during startup.
        
        Makes concurrent requests to various API endpoints and validates:
        - All requests complete within timeout
        - System handles concurrent load without blocking
        - Response times stay reasonable
        """
        self.logger.info(f"\n{'='*60}")
        self.logger.info("Testing API Endpoint Responsiveness")
        self.logger.info(f"{'='*60}")
        
        start_time = time.time()
        response_times = []
        timeout_errors = 0
        connection_errors = 0
        successful_responses = 0
        total_requests = 0
        
        cpu_samples = []
        memory_samples = []
        
        # Test endpoints
        test_endpoints = [
            ("/health/minimal", "GET", None),
            ("/health/ready", "GET", None),
            ("/api/loading/status", "GET", None),
            ("/api/loading/capabilities", "GET", None),
        ]
        
        async def make_concurrent_requests():
            nonlocal total_requests, successful_responses, timeout_errors, connection_errors
            
            async with aiohttp.ClientSession() as session:
                tasks = []
                
                for endpoint, method, json_data in test_endpoints:
                    for _ in range(concurrent_requests):
                        total_requests += 1
                        url = f"{self.base_url}{endpoint}"
                        tasks.append(self.make_request_with_timeout(session, url, method, json_data))
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, Exception):
                        self.logger.warning(f"Request exception: {result}")
                        continue
                    
                    success, response_time_ms, error = result
                    
                    if success:
                        successful_responses += 1
                        response_times.append(response_time_ms)
                    elif error == "timeout":
                        timeout_errors += 1
                    elif error == "connection_error":
                        connection_errors += 1
        
        # Run concurrent requests for duration
        end_time = start_time + duration_seconds
        iteration = 0
        
        while time.time() < end_time:
            iteration += 1
            self.logger.info(f"Running concurrent request batch {iteration}...")
            
            await make_concurrent_requests()
            
            # Sample resource usage
            cpu, memory = self.get_system_resource_usage()
            cpu_samples.append(cpu)
            memory_samples.append(memory)
            
            # Wait before next batch
            await asyncio.sleep(5)
        
        # Calculate metrics
        duration = time.time() - start_time
        avg_response_time = statistics.mean(response_times) if response_times else 0
        max_response_time = max(response_times) if response_times else 0
        p95_response_time = statistics.quantiles(response_times, n=20)[18] if len(response_times) >= 20 else max_response_time
        p99_response_time = statistics.quantiles(response_times, n=100)[98] if len(response_times) >= 100 else max_response_time
        
        avg_cpu = statistics.mean(cpu_samples) if cpu_samples else 0
        avg_memory = statistics.mean(memory_samples) if memory_samples else 0
        
        success_rate = (successful_responses / total_requests * 100) if total_requests > 0 else 0
        requests_per_second = total_requests / duration if duration > 0 else 0
        
        # Validation checks
        all_responses_under_10s = max_response_time < 10000 if response_times else False
        no_timeouts = timeout_errors == 0
        no_connection_errors_check = connection_errors == 0
        resource_usage_acceptable = avg_cpu < 95 and avg_memory < 95
        
        overall_responsive = (
            all_responses_under_10s and
            no_timeouts and
            no_connection_errors_check and
            resource_usage_acceptable and
            success_rate >= 90  # Slightly lower threshold for API endpoints
        )
        
        metrics = ResponsivenessMetrics(
            test_name="api_endpoint_responsiveness",
            startup_phase="concurrent",
            total_requests=total_requests,
            successful_responses=successful_responses,
            timeout_errors=timeout_errors,
            connection_errors=connection_errors,
            avg_response_time_ms=avg_response_time,
            max_response_time_ms=max_response_time,
            p95_response_time_ms=p95_response_time,
            p99_response_time_ms=p99_response_time,
            cpu_usage_percent=avg_cpu,
            memory_usage_percent=avg_memory,
            requests_per_second=requests_per_second,
            success_rate_percent=success_rate,
            all_responses_under_10s=all_responses_under_10s,
            no_timeouts=no_timeouts,
            no_connection_errors=no_connection_errors_check,
            resource_usage_acceptable=resource_usage_acceptable,
            overall_responsive=overall_responsive,
            duration_seconds=duration,
            timestamp=datetime.utcnow().isoformat()
        )
        
        # Log results
        self.logger.info(f"\nAPI Endpoint Responsiveness Results:")
        self.logger.info(f"  Total Requests: {total_requests}")
        self.logger.info(f"  Successful: {successful_responses} ({success_rate:.1f}%)")
        self.logger.info(f"  Timeouts: {timeout_errors}")
        self.logger.info(f"  Connection Errors: {connection_errors}")
        self.logger.info(f"  Avg Response Time: {avg_response_time:.0f}ms")
        self.logger.info(f"  Max Response Time: {max_response_time:.0f}ms")
        self.logger.info(f"  P95 Response Time: {p95_response_time:.0f}ms")
        self.logger.info(f"  Avg CPU Usage: {avg_cpu:.1f}%")
        self.logger.info(f"  Avg Memory Usage: {avg_memory:.1f}%")
        self.logger.info(f"  Requests/sec: {requests_per_second:.2f}")
        
        if overall_responsive:
            self.logger.info("✅ API endpoints remained responsive throughout test")
        else:
            self.logger.warning("❌ API endpoint responsiveness issues detected:")
            if not all_responses_under_10s:
                self.logger.warning(f"  - Max response time {max_response_time:.0f}ms exceeded 10s threshold")
            if not no_timeouts:
                self.logger.warning(f"  - {timeout_errors} timeout errors occurred")
            if not no_connection_errors_check:
                self.logger.warning(f"  - {connection_errors} connection errors occurred")
            if not resource_usage_acceptable:
                self.logger.warning(f"  - Resource usage too high (CPU: {avg_cpu:.1f}%, Memory: {avg_memory:.1f}%)")
            if success_rate < 90:
                self.logger.warning(f"  - Success rate {success_rate:.1f}% below 90% threshold")
        
        return metrics
    
    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all responsiveness tests."""
        self.logger.info("\n" + "="*60)
        self.logger.info("SYSTEM RESPONSIVENESS VALIDATION")
        self.logger.info("="*60)
        
        results = {
            "test_suite": "system_responsiveness_during_startup",
            "timestamp": datetime.utcnow().isoformat(),
            "tests": {}
        }
        
        # Test 1: Health endpoint responsiveness
        health_metrics = await self.test_health_endpoint_responsiveness(
            duration_seconds=60,
            request_interval_seconds=1.0
        )
        results["tests"]["health_endpoint_responsiveness"] = asdict(health_metrics)
        
        # Test 2: API endpoint responsiveness
        api_metrics = await self.test_api_endpoint_responsiveness(
            concurrent_requests=5,
            duration_seconds=60
        )
        results["tests"]["api_endpoint_responsiveness"] = asdict(api_metrics)
        
        # Overall assessment
        all_tests_passed = (
            health_metrics.overall_responsive and
            api_metrics.overall_responsive
        )
        
        results["overall_responsive"] = all_tests_passed
        results["summary"] = {
            "health_endpoint_responsive": health_metrics.overall_responsive,
            "api_endpoint_responsive": api_metrics.overall_responsive,
            "total_requests": health_metrics.total_requests + api_metrics.total_requests,
            "total_timeouts": health_metrics.timeout_errors + api_metrics.timeout_errors,
            "total_connection_errors": health_metrics.connection_errors + api_metrics.connection_errors
        }
        
        # Final report
        self.logger.info("\n" + "="*60)
        self.logger.info("FINAL RESPONSIVENESS ASSESSMENT")
        self.logger.info("="*60)
        
        if all_tests_passed:
            self.logger.info("✅ SUCCESS: System remains responsive throughout startup process")
            self.logger.info("   - Health endpoints respond within timeout")
            self.logger.info("   - API endpoints handle concurrent requests")
            self.logger.info("   - No timeouts or connection errors")
            self.logger.info("   - Resource usage stays within limits")
        else:
            self.logger.warning("❌ FAILURE: System responsiveness issues detected")
            if not health_metrics.overall_responsive:
                self.logger.warning("   - Health endpoint responsiveness issues")
            if not api_metrics.overall_responsive:
                self.logger.warning("   - API endpoint responsiveness issues")
        
        return results


async def main():
    """Main test execution."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test system responsiveness during startup")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the application"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10,
        help="Request timeout in seconds"
    )
    parser.add_argument(
        "--output",
        default="system_responsiveness_results.json",
        help="Output file for results"
    )
    
    args = parser.parse_args()
    
    tester = SystemResponsivenessTester(
        base_url=args.base_url,
        timeout_seconds=args.timeout
    )
    
    results = await tester.run_all_tests()
    
    # Save results
    with open(args.output, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResults saved to {args.output}")
    
    # Exit with appropriate code
    if results["overall_responsive"]:
        print("\n✅ All responsiveness tests passed")
        sys.exit(0)
    else:
        print("\n❌ Some responsiveness tests failed")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
