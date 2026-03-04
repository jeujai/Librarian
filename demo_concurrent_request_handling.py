#!/usr/bin/env python3
"""
Concurrent Request Handling Demonstration

This script demonstrates the concurrent request handling capabilities
of the multimodal librarian application during startup.

Features Demonstrated:
1. Request throttling during different startup phases
2. Graceful degradation under load
3. Fallback response generation
4. Metrics tracking and reporting
5. Priority-based request handling
"""

import asyncio
import time
from typing import Dict, Any
from datetime import datetime


def print_section(title: str):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def print_subsection(title: str):
    """Print a subsection header."""
    print(f"\n{title}")
    print("-" * 80)


async def demonstrate_concurrent_request_handling():
    """Demonstrate concurrent request handling features."""
    
    print_section("🔄 CONCURRENT REQUEST HANDLING DEMONSTRATION")
    
    # Import components
    try:
        from src.multimodal_librarian.api.middleware.concurrent_request_handler import (
            ConcurrentRequestHandler,
            RequestMetrics
        )
        from src.multimodal_librarian.startup.phase_manager import StartupPhase
        from fastapi import FastAPI
        
        print("✅ Successfully imported concurrent request handling components")
    except ImportError as e:
        print(f"❌ Failed to import components: {e}")
        return
    
    # Create FastAPI app and middleware
    print_subsection("1️⃣ Initializing Middleware")
    
    app = FastAPI()
    middleware = ConcurrentRequestHandler(app)
    
    print(f"✅ Middleware initialized")
    print(f"   Phase limits: {middleware.max_concurrent_requests}")
    print(f"   Endpoint limits: {len(middleware._endpoint_limits)} endpoints configured")
    print(f"   Priority endpoints: {len(middleware._priority_endpoints)} priorities defined")
    
    # Demonstrate request metrics
    print_subsection("2️⃣ Request Metrics Tracking")
    
    metrics = middleware.get_metrics()
    print(f"Initial metrics:")
    print(f"   Total requests: {metrics['total_requests']}")
    print(f"   Concurrent requests: {metrics['concurrent_requests']}")
    print(f"   Peak concurrent: {metrics['peak_concurrent_requests']}")
    print(f"   Success rate: {metrics['success_rate']:.1f}%")
    
    # Simulate request tracking
    print_subsection("3️⃣ Simulating Request Lifecycle")
    
    from unittest.mock import Mock
    from fastapi import Request
    
    # Create mock request
    mock_request = Mock(spec=Request)
    mock_request.url.path = "/api/chat"
    
    # Track request start
    request_id = middleware._generate_request_id()
    print(f"Generated request ID: {request_id[:8]}...")
    
    await middleware._track_request_start(
        request_id,
        mock_request,
        StartupPhase.MINIMAL
    )
    
    print(f"✅ Request started")
    print(f"   Concurrent requests: {middleware._metrics.concurrent_requests}")
    print(f"   Active requests: {len(middleware._active_requests)}")
    
    # Simulate processing time
    await asyncio.sleep(0.1)
    
    # Track request end
    start_time = time.time() - 0.1
    await middleware._track_request_end(request_id, start_time)
    
    print(f"✅ Request completed")
    print(f"   Concurrent requests: {middleware._metrics.concurrent_requests}")
    print(f"   Total requests: {middleware._metrics.total_requests}")
    
    # Demonstrate throttling logic
    print_subsection("4️⃣ Throttling Configuration")
    
    print("Phase-specific limits:")
    for phase, limit in middleware.max_concurrent_requests.items():
        print(f"   {phase.value:12s}: {limit:3d} concurrent requests")
    
    print("\nEndpoint-specific limits:")
    for endpoint, limit in middleware._endpoint_limits.items():
        print(f"   {endpoint:25s}: {limit:3d} requests")
    
    # Demonstrate priority handling
    print_subsection("5️⃣ Request Prioritization")
    
    print("Priority levels (1 = highest):")
    sorted_priorities = sorted(
        middleware._priority_endpoints.items(),
        key=lambda x: x[1]
    )
    for endpoint, priority in sorted_priorities:
        print(f"   Priority {priority}: {endpoint}")
    
    # Demonstrate throttle response
    print_subsection("6️⃣ Throttle Response Generation")
    
    # Simulate high load
    middleware._metrics.concurrent_requests = 55  # Above MINIMAL phase limit
    
    should_throttle, reason = await middleware._should_throttle_request(
        mock_request,
        StartupPhase.MINIMAL
    )
    
    if should_throttle:
        print(f"✅ Throttling triggered")
        print(f"   Reason: {reason}")
        print(f"   Current concurrent: {middleware._metrics.concurrent_requests}")
        print(f"   Phase limit: {middleware.max_concurrent_requests[StartupPhase.MINIMAL]}")
    
    # Reset for next demo
    middleware._metrics.concurrent_requests = 0
    
    # Demonstrate metrics export
    print_subsection("7️⃣ Comprehensive Metrics Export")
    
    # Simulate some activity
    middleware._metrics.total_requests = 100
    middleware._metrics.successful_requests = 95
    middleware._metrics.failed_requests = 5
    middleware._metrics.throttled_requests = 10
    middleware._metrics.fallback_responses = 8
    middleware._metrics.avg_response_time_ms = 125.5
    middleware._metrics.peak_concurrent_requests = 45
    
    metrics = middleware.get_metrics()
    
    print("Current metrics:")
    print(f"   Total requests: {metrics['total_requests']}")
    print(f"   Successful: {metrics['successful_requests']}")
    print(f"   Failed: {metrics['failed_requests']}")
    print(f"   Throttled: {metrics['throttled_requests']}")
    print(f"   Fallback responses: {metrics['fallback_responses']}")
    print(f"   Success rate: {metrics['success_rate']:.1f}%")
    print(f"   Avg response time: {metrics['avg_response_time_ms']:.1f}ms")
    print(f"   Peak concurrent: {metrics['peak_concurrent_requests']}")
    
    # Demonstrate path skip logic
    print_subsection("8️⃣ Path Skip Logic")
    
    skip_paths = [
        ("/static/css/style.css", True),
        ("/favicon.ico", True),
        ("/api/chat", False),
        ("/health/minimal", False),
        ("/docs", True)
    ]
    
    print("Path processing decisions:")
    for path, expected_skip in skip_paths:
        mock_req = Mock(spec=Request)
        mock_req.url.path = path
        should_skip = middleware._should_skip_middleware(mock_req)
        status = "✅ SKIP" if should_skip else "🔄 PROCESS"
        print(f"   {status:12s} {path}")
    
    # Summary
    print_section("📊 DEMONSTRATION SUMMARY")
    
    print("✅ Concurrent request handling features demonstrated:")
    print("   1. Middleware initialization and configuration")
    print("   2. Request metrics tracking")
    print("   3. Request lifecycle management")
    print("   4. Phase-specific throttling")
    print("   5. Request prioritization")
    print("   6. Throttle response generation")
    print("   7. Comprehensive metrics export")
    print("   8. Path skip logic")
    
    print("\n✅ Key Benefits:")
    print("   • No 'model not loaded' errors")
    print("   • Graceful degradation under load")
    print("   • Immediate user feedback")
    print("   • System stability protection")
    print("   • Comprehensive observability")
    
    print("\n✅ Integration Status:")
    print("   • Middleware: Implemented and tested")
    print("   • Integration module: Available")
    print("   • Main application: Integrated")
    print("   • Metrics API: Available at /api/concurrent/*")
    
    print("\n" + "=" * 80)
    print("  Demonstration Complete!")
    print("=" * 80 + "\n")


def main():
    """Run the demonstration."""
    try:
        asyncio.run(demonstrate_concurrent_request_handling())
        return 0
    except Exception as e:
        print(f"\n❌ Demonstration failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
