#!/usr/bin/env python3
"""
Immediate Feedback on All Requests Test

This module validates that users receive immediate feedback on ALL requests,
regardless of system state or model loading status. This is a critical user
experience requirement that ensures no request goes unanswered.

Validates Requirements:
- REQ-2: Application Startup Optimization (graceful degradation)
- REQ-3: Smart User Experience (immediate feedback)

Test Scenarios:
1. All request types receive immediate responses (no timeouts)
2. Responses include loading state information
3. Fallback responses are provided when models not ready
4. Response times are within acceptable limits (<5 seconds)
5. No "model not loaded" errors are returned to users
"""

import os
import sys
import asyncio
import aiohttp
import time
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
class ImmediateFeedbackResult:
    """Results from immediate feedback testing."""
    request_type: str
    received_response: bool
    response_time_ms: float
    has_loading_state: bool
    has_fallback_info: bool
    has_quality_indicator: bool
    has_capability_info: bool
    response_within_limit: bool  # <5 seconds
    model_not_loaded_error: bool
    response_helpful: bool
    response_data: Dict[str, Any]
    error: Optional[str] = None


@dataclass
class TestSummary:
    """Summary of all immediate feedback tests."""
    total_requests: int
    successful_responses: int
    failed_responses: int
    avg_response_time_ms: float
    max_response_time_ms: float
    requests_with_loading_state: int
    requests_with_fallback: int
    requests_with_quality_indicator: int
    model_not_loaded_errors: int
    all_requests_responded: bool
    all_responses_within_limit: bool
    all_responses_helpful: bool
    pass_rate_percent: float


class ImmediateFeedbackTester:
    """Tests that all requests receive immediate feedback."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.logger = get_logger("immediate_feedback_tester")
        self.max_acceptable_response_time = 5000  # 5 seconds in milliseconds
        
        self.logger.info(f"Initialized immediate feedback tester for {self.base_url}")
    
    async def test_all_request_types(self) -> List[ImmediateFeedbackResult]:
        """Test that all request types receive immediate feedback."""
        self.logger.info("Testing immediate feedback for all request types...")
        
        # Define all request types that users might make
        request_types = [
            ("health_check", "GET", "/health/minimal", None),
            ("health_ready", "GET", "/health/ready", None),
            ("health_full", "GET", "/health/full", None),
            ("loading_status", "GET", "/api/loading/status", None),
            ("loading_progress", "GET", "/api/loading/progress", None),
            ("chat_capabilities", "GET", "/api/chat/capabilities", None),
            ("chat_progress", "GET", "/api/chat/progress", None),
            ("simple_chat", "POST", "/api/chat", {"message": "Hello"}),
            ("complex_chat", "POST", "/api/chat", {"message": "Analyze this complex document"}),
            ("document_query", "POST", "/api/chat", {"message": "What documents do I have?"}),
            ("search_query", "GET", "/api/search?q=test", None),
            ("documents_list", "GET", "/api/documents", None),
            ("system_status", "GET", "/api/status", None),
        ]
        
        results = []
        
        timeout = aiohttp.ClientTimeout(total=10)  # 10 second timeout for safety
        
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for request_name, method, endpoint, payload in request_types:
                result = await self._test_single_request(
                    session, request_name, method, endpoint, payload
                )
                results.append(result)
                
                # Small delay between requests
                await asyncio.sleep(0.1)
        
        return results
    
    async def _test_single_request(
        self,
        session: aiohttp.ClientSession,
        request_name: str,
        method: str,
        endpoint: str,
        payload: Optional[Dict[str, Any]]
    ) -> ImmediateFeedbackResult:
        """Test a single request for immediate feedback."""
        url = f"{self.base_url}{endpoint}"
        start_time = time.time()
        
        try:
            # Make the request
            if method == "GET":
                async with session.get(url) as response:
                    response_data = await response.json()
                    response_time = (time.time() - start_time) * 1000
                    
                    return self._analyze_response(
                        request_name, response_data, response_time, response.status
                    )
            
            elif method == "POST":
                async with session.post(url, json=payload) as response:
                    response_data = await response.json()
                    response_time = (time.time() - start_time) * 1000
                    
                    return self._analyze_response(
                        request_name, response_data, response_time, response.status
                    )
            
            else:
                return ImmediateFeedbackResult(
                    request_type=request_name,
                    received_response=False,
                    response_time_ms=0,
                    has_loading_state=False,
                    has_fallback_info=False,
                    has_quality_indicator=False,
                    has_capability_info=False,
                    response_within_limit=False,
                    model_not_loaded_error=False,
                    response_helpful=False,
                    response_data={},
                    error=f"Unsupported method: {method}"
                )
        
        except asyncio.TimeoutError:
            response_time = (time.time() - start_time) * 1000
            return ImmediateFeedbackResult(
                request_type=request_name,
                received_response=False,
                response_time_ms=response_time,
                has_loading_state=False,
                has_fallback_info=False,
                has_quality_indicator=False,
                has_capability_info=False,
                response_within_limit=False,
                model_not_loaded_error=False,
                response_helpful=False,
                response_data={},
                error="Request timed out"
            )
        
        except Exception as e:
            response_time = (time.time() - start_time) * 1000
            return ImmediateFeedbackResult(
                request_type=request_name,
                received_response=False,
                response_time_ms=response_time,
                has_loading_state=False,
                has_fallback_info=False,
                has_quality_indicator=False,
                has_capability_info=False,
                response_within_limit=False,
                model_not_loaded_error=False,
                response_helpful=False,
                response_data={},
                error=str(e)
            )
    
    def _analyze_response(
        self,
        request_name: str,
        response_data: Dict[str, Any],
        response_time: float,
        status_code: int
    ) -> ImmediateFeedbackResult:
        """Analyze a response for immediate feedback characteristics."""
        
        # Check if response was received
        received_response = status_code < 500
        
        # Check for loading state information
        has_loading_state = (
            "loading_state" in response_data or
            "loading_progress" in response_data or
            "progress" in response_data or
            "phase" in response_data
        )
        
        # Check for fallback information
        has_fallback_info = (
            "fallback" in str(response_data).lower() or
            "loading" in str(response_data).lower() or
            "starting up" in str(response_data).lower() or
            "not ready" in str(response_data).lower()
        )
        
        # Check for quality indicator
        has_quality_indicator = (
            "quality_indicator" in response_data or
            "response_quality" in response_data or
            "⚡" in str(response_data) or
            "🔄" in str(response_data) or
            "🧠" in str(response_data)
        )
        
        # Check for capability information
        has_capability_info = (
            "capabilities" in response_data or
            "available" in response_data or
            "features" in response_data
        )
        
        # Check response time
        response_within_limit = response_time < self.max_acceptable_response_time
        
        # Check for model not loaded errors
        model_not_loaded_error = (
            "model not loaded" in str(response_data).lower() or
            "model is not available" in str(response_data).lower() or
            "model not ready" in str(response_data).lower()
        )
        
        # Check if response is helpful
        response_helpful = (
            received_response and
            not model_not_loaded_error and
            (has_loading_state or has_fallback_info or has_capability_info) and
            len(str(response_data)) > 50  # Has substantial content
        )
        
        return ImmediateFeedbackResult(
            request_type=request_name,
            received_response=received_response,
            response_time_ms=response_time,
            has_loading_state=has_loading_state,
            has_fallback_info=has_fallback_info,
            has_quality_indicator=has_quality_indicator,
            has_capability_info=has_capability_info,
            response_within_limit=response_within_limit,
            model_not_loaded_error=model_not_loaded_error,
            response_helpful=response_helpful,
            response_data=response_data,
            error=None if received_response else f"HTTP {status_code}"
        )
    
    def calculate_summary(self, results: List[ImmediateFeedbackResult]) -> TestSummary:
        """Calculate summary statistics from test results."""
        total_requests = len(results)
        successful_responses = sum(1 for r in results if r.received_response)
        failed_responses = total_requests - successful_responses
        
        response_times = [r.response_time_ms for r in results if r.received_response]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        max_response_time = max(response_times) if response_times else 0
        
        requests_with_loading_state = sum(1 for r in results if r.has_loading_state)
        requests_with_fallback = sum(1 for r in results if r.has_fallback_info)
        requests_with_quality_indicator = sum(1 for r in results if r.has_quality_indicator)
        model_not_loaded_errors = sum(1 for r in results if r.model_not_loaded_error)
        
        all_requests_responded = successful_responses == total_requests
        all_responses_within_limit = all(r.response_within_limit for r in results if r.received_response)
        all_responses_helpful = all(r.response_helpful for r in results if r.received_response)
        
        # Calculate pass rate
        passing_requests = sum(
            1 for r in results 
            if r.received_response and 
            r.response_within_limit and 
            not r.model_not_loaded_error and
            r.response_helpful
        )
        pass_rate = (passing_requests / total_requests) * 100 if total_requests > 0 else 0
        
        return TestSummary(
            total_requests=total_requests,
            successful_responses=successful_responses,
            failed_responses=failed_responses,
            avg_response_time_ms=avg_response_time,
            max_response_time_ms=max_response_time,
            requests_with_loading_state=requests_with_loading_state,
            requests_with_fallback=requests_with_fallback,
            requests_with_quality_indicator=requests_with_quality_indicator,
            model_not_loaded_errors=model_not_loaded_errors,
            all_requests_responded=all_requests_responded,
            all_responses_within_limit=all_responses_within_limit,
            all_responses_helpful=all_responses_helpful,
            pass_rate_percent=pass_rate
        )


async def run_immediate_feedback_tests(
    base_url: str = "http://localhost:8000",
    output_directory: str = "test_results"
) -> Dict[str, Any]:
    """Run comprehensive immediate feedback tests."""
    
    logger = get_logger("immediate_feedback_tests")
    logger.info("Starting immediate feedback tests")
    
    # Ensure output directory exists
    os.makedirs(output_directory, exist_ok=True)
    
    # Create tester
    tester = ImmediateFeedbackTester(base_url)
    
    test_results = {
        "start_time": datetime.now().isoformat(),
        "base_url": base_url,
        "test_type": "immediate_feedback",
        "max_acceptable_response_time_ms": tester.max_acceptable_response_time
    }
    
    print("=" * 80)
    print("📬 IMMEDIATE FEEDBACK ON ALL REQUESTS TEST")
    print("=" * 80)
    print(f"Target: {base_url}")
    print(f"Max Acceptable Response Time: {tester.max_acceptable_response_time}ms")
    print()
    
    try:
        # Test all request types
        print("📊 Testing All Request Types for Immediate Feedback")
        print("-" * 80)
        
        results = await tester.test_all_request_types()
        
        # Calculate summary
        summary = tester.calculate_summary(results)
        
        # Store results
        test_results["results"] = [asdict(r) for r in results]
        test_results["summary"] = asdict(summary)
        
        # Print detailed results
        print(f"\n✅ Tested {summary.total_requests} request types")
        print()
        
        print("📋 DETAILED RESULTS")
        print("-" * 80)
        
        for result in results:
            status_icon = "✅" if result.received_response and not result.model_not_loaded_error else "❌"
            time_icon = "⚡" if result.response_within_limit else "⏱️"
            
            print(f"{status_icon} {result.request_type}")
            print(f"   Response Time: {time_icon} {result.response_time_ms:.1f}ms")
            print(f"   Received Response: {'Yes' if result.received_response else 'No'}")
            print(f"   Has Loading State: {'Yes' if result.has_loading_state else 'No'}")
            print(f"   Has Fallback Info: {'Yes' if result.has_fallback_info else 'No'}")
            print(f"   Has Quality Indicator: {'Yes' if result.has_quality_indicator else 'No'}")
            print(f"   Response Helpful: {'Yes' if result.response_helpful else 'No'}")
            
            if result.model_not_loaded_error:
                print(f"   ⚠️  Model Not Loaded Error Detected!")
            
            if result.error:
                print(f"   Error: {result.error}")
            
            print()
        
        # Print summary
        print("=" * 80)
        print("📊 SUMMARY")
        print("=" * 80)
        print(f"Total Requests: {summary.total_requests}")
        print(f"Successful Responses: {summary.successful_responses}/{summary.total_requests}")
        print(f"Failed Responses: {summary.failed_responses}")
        print(f"Average Response Time: {summary.avg_response_time_ms:.1f}ms")
        print(f"Max Response Time: {summary.max_response_time_ms:.1f}ms")
        print(f"Requests with Loading State: {summary.requests_with_loading_state}")
        print(f"Requests with Fallback Info: {summary.requests_with_fallback}")
        print(f"Requests with Quality Indicator: {summary.requests_with_quality_indicator}")
        print(f"Model Not Loaded Errors: {summary.model_not_loaded_errors}")
        print(f"Pass Rate: {summary.pass_rate_percent:.1f}%")
        print()
        
        # Validate requirements
        print("✅ REQUIREMENT VALIDATION")
        print("-" * 80)
        
        # REQ-3: All requests receive immediate feedback
        if summary.all_requests_responded:
            print("✅ REQ-3: All requests received immediate responses")
        else:
            print(f"❌ REQ-3: {summary.failed_responses} requests did not receive responses")
        
        # REQ-3: No model not loaded errors
        if summary.model_not_loaded_errors == 0:
            print("✅ REQ-3: No 'model not loaded' errors returned to users")
        else:
            print(f"❌ REQ-3: {summary.model_not_loaded_errors} 'model not loaded' errors detected")
        
        # REQ-3: All responses within acceptable time limit
        if summary.all_responses_within_limit:
            print(f"✅ REQ-3: All responses within {tester.max_acceptable_response_time}ms limit")
        else:
            slow_responses = [r for r in results if not r.response_within_limit]
            print(f"⚠️  REQ-3: {len(slow_responses)} responses exceeded time limit")
        
        # REQ-3: All responses are helpful
        if summary.all_responses_helpful:
            print("✅ REQ-3: All responses are helpful with context")
        else:
            unhelpful_responses = [r for r in results if not r.response_helpful and r.received_response]
            print(f"⚠️  REQ-3: {len(unhelpful_responses)} responses lack helpful context")
        
        # Overall pass/fail
        print()
        if summary.pass_rate_percent >= 95:
            print(f"✅ OVERALL: PASSED ({summary.pass_rate_percent:.1f}% pass rate)")
            test_results["overall_result"] = "PASSED"
        elif summary.pass_rate_percent >= 80:
            print(f"⚠️  OVERALL: PASSED WITH WARNINGS ({summary.pass_rate_percent:.1f}% pass rate)")
            test_results["overall_result"] = "PASSED_WITH_WARNINGS"
        else:
            print(f"❌ OVERALL: FAILED ({summary.pass_rate_percent:.1f}% pass rate)")
            test_results["overall_result"] = "FAILED"
        
        print()
        
    except Exception as e:
        logger.error(f"Test failed: {e}")
        test_results["error"] = str(e)
        test_results["overall_result"] = "ERROR"
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Save results
    test_results["end_time"] = datetime.now().isoformat()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(output_directory, f"immediate_feedback_test_{timestamp}.json")
    
    with open(output_file, 'w') as f:
        json.dump(test_results, f, indent=2)
    
    print(f"📄 Results saved to: {output_file}")
    
    return test_results


def main():
    """Main test runner."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Run Immediate Feedback Tests')
    parser.add_argument('--url', type=str, default='http://localhost:8000',
                       help='Base URL for testing')
    parser.add_argument('--output-dir', type=str, default='test_results',
                       help='Output directory for results')
    
    args = parser.parse_args()
    
    # Run tests
    results = asyncio.run(run_immediate_feedback_tests(
        base_url=args.url,
        output_directory=args.output_dir
    ))
    
    # Exit with appropriate code
    overall_result = results.get("overall_result", "ERROR")
    
    if overall_result == "PASSED":
        print("\n✅ Immediate feedback testing completed successfully!")
        exit(0)
    elif overall_result == "PASSED_WITH_WARNINGS":
        print("\n⚠️  Immediate feedback testing completed with warnings.")
        exit(1)
    else:
        print("\n❌ Immediate feedback testing failed.")
        exit(2)


if __name__ == "__main__":
    main()
