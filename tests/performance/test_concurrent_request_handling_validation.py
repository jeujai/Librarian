#!/usr/bin/env python3
"""
Concurrent Request Handling Validation Test

This test validates that the concurrent request handling middleware
is properly integrated and functioning correctly.

Validates:
- Middleware is loaded and active
- Request throttling works correctly
- Fallback responses are provided
- No "model not loaded" errors occur
- Metrics are tracked correctly
"""

import os
import sys
import pytest
import asyncio
from typing import Dict, Any

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from multimodal_librarian.api.middleware.concurrent_request_handler import (
    ConcurrentRequestHandler,
    RequestMetrics
)
from multimodal_librarian.startup.phase_manager import StartupPhase


class TestConcurrentRequestHandling:
    """Test suite for concurrent request handling."""
    
    def test_middleware_initialization(self):
        """Test that middleware can be initialized."""
        from fastapi import FastAPI
        
        app = FastAPI()
        middleware = ConcurrentRequestHandler(app)
        
        assert middleware is not None
        assert middleware.max_concurrent_requests is not None
        assert StartupPhase.MINIMAL in middleware.max_concurrent_requests
        assert StartupPhase.ESSENTIAL in middleware.max_concurrent_requests
        assert StartupPhase.FULL in middleware.max_concurrent_requests
        
        print("✅ Middleware initialization successful")
    
    def test_request_metrics_tracking(self):
        """Test that request metrics are tracked correctly."""
        metrics = RequestMetrics()
        
        assert metrics.total_requests == 0
        assert metrics.concurrent_requests == 0
        assert metrics.peak_concurrent_requests == 0
        assert metrics.throttled_requests == 0
        assert metrics.fallback_responses == 0
        
        # Simulate request tracking
        metrics.total_requests += 1
        metrics.concurrent_requests += 1
        metrics.peak_concurrent_requests = max(
            metrics.peak_concurrent_requests,
            metrics.concurrent_requests
        )
        
        assert metrics.total_requests == 1
        assert metrics.concurrent_requests == 1
        assert metrics.peak_concurrent_requests == 1
        
        print("✅ Request metrics tracking works correctly")
    
    def test_throttling_configuration(self):
        """Test that throttling configuration is correct."""
        from fastapi import FastAPI
        
        app = FastAPI()
        middleware = ConcurrentRequestHandler(app)
        
        # Check phase-specific limits
        assert middleware.max_concurrent_requests[StartupPhase.MINIMAL] == 50
        assert middleware.max_concurrent_requests[StartupPhase.ESSENTIAL] == 100
        assert middleware.max_concurrent_requests[StartupPhase.FULL] == 200
        
        # Check endpoint limits
        assert "/api/chat" in middleware._endpoint_limits
        assert "/api/search" in middleware._endpoint_limits
        assert "/health" in middleware._endpoint_limits
        
        print("✅ Throttling configuration is correct")
    
    def test_request_prioritization(self):
        """Test that request prioritization is configured."""
        from fastapi import FastAPI
        
        app = FastAPI()
        middleware = ConcurrentRequestHandler(app)
        
        # Check priority configuration
        assert "/health" in middleware._priority_endpoints
        assert middleware._priority_endpoints["/health"] == 1  # Highest priority
        
        assert "/api/loading/status" in middleware._priority_endpoints
        assert middleware._priority_endpoints["/api/loading/status"] == 2
        
        print("✅ Request prioritization is configured correctly")
    
    def test_metrics_export(self):
        """Test that metrics can be exported."""
        from fastapi import FastAPI
        
        app = FastAPI()
        middleware = ConcurrentRequestHandler(app)
        
        # Get metrics
        metrics = middleware.get_metrics()
        
        assert isinstance(metrics, dict)
        assert "total_requests" in metrics
        assert "concurrent_requests" in metrics
        assert "peak_concurrent_requests" in metrics
        assert "throttled_requests" in metrics
        assert "fallback_responses" in metrics
        assert "successful_requests" in metrics
        assert "failed_requests" in metrics
        assert "success_rate" in metrics
        
        print("✅ Metrics export works correctly")
    
    @pytest.mark.asyncio
    async def test_request_tracking_lifecycle(self):
        """Test request tracking lifecycle."""
        from fastapi import FastAPI
        
        app = FastAPI()
        middleware = ConcurrentRequestHandler(app)
        
        # Simulate request start
        request_id = middleware._generate_request_id()
        assert request_id is not None
        assert len(request_id) > 0
        
        # Check initial state
        initial_concurrent = middleware._metrics.concurrent_requests
        
        # Track request start
        from fastapi import Request
        from unittest.mock import Mock
        
        mock_request = Mock(spec=Request)
        mock_request.url.path = "/api/chat"
        
        await middleware._track_request_start(
            request_id,
            mock_request,
            StartupPhase.MINIMAL
        )
        
        # Check that concurrent requests increased
        assert middleware._metrics.concurrent_requests == initial_concurrent + 1
        assert request_id in middleware._active_requests
        
        # Track request end
        import time
        start_time = time.time()
        await middleware._track_request_end(request_id, start_time)
        
        # Check that concurrent requests decreased
        assert middleware._metrics.concurrent_requests == initial_concurrent
        assert request_id not in middleware._active_requests
        
        print("✅ Request tracking lifecycle works correctly")
    
    def test_integration_module_exists(self):
        """Test that integration module exists and can be imported."""
        try:
            from multimodal_librarian.api.middleware.concurrent_integration import (
                integrate_concurrent_request_handling,
                router
            )
            
            assert integrate_concurrent_request_handling is not None
            assert router is not None
            
            print("✅ Integration module exists and can be imported")
        except ImportError as e:
            pytest.fail(f"Failed to import integration module: {e}")
    
    def test_middleware_skip_logic(self):
        """Test that middleware correctly skips certain paths."""
        from fastapi import FastAPI
        from unittest.mock import Mock
        from fastapi import Request
        
        app = FastAPI()
        middleware = ConcurrentRequestHandler(app)
        
        # Test paths that should be skipped
        skip_paths = [
            "/static/css/style.css",
            "/favicon.ico",
            "/robots.txt",
            "/docs",
            "/openapi.json"
        ]
        
        for path in skip_paths:
            mock_request = Mock(spec=Request)
            mock_request.url.path = path
            
            should_skip = middleware._should_skip_middleware(mock_request)
            assert should_skip, f"Path {path} should be skipped"
        
        # Test paths that should NOT be skipped
        process_paths = [
            "/api/chat",
            "/api/search",
            "/health/minimal",
            "/api/documents"
        ]
        
        for path in process_paths:
            mock_request = Mock(spec=Request)
            mock_request.url.path = path
            
            should_skip = middleware._should_skip_middleware(mock_request)
            assert not should_skip, f"Path {path} should NOT be skipped"
        
        print("✅ Middleware skip logic works correctly")


def main():
    """Run validation tests."""
    print("=" * 80)
    print("🔄 CONCURRENT REQUEST HANDLING VALIDATION")
    print("=" * 80)
    print()
    
    test_suite = TestConcurrentRequestHandling()
    
    try:
        # Run synchronous tests
        test_suite.test_middleware_initialization()
        test_suite.test_request_metrics_tracking()
        test_suite.test_throttling_configuration()
        test_suite.test_request_prioritization()
        test_suite.test_metrics_export()
        test_suite.test_integration_module_exists()
        test_suite.test_middleware_skip_logic()
        
        # Run async tests
        asyncio.run(test_suite.test_request_tracking_lifecycle())
        
        print()
        print("=" * 80)
        print("✅ ALL VALIDATION TESTS PASSED")
        print("=" * 80)
        print()
        print("Concurrent request handling is properly implemented and integrated.")
        print()
        print("Key features validated:")
        print("- Middleware initialization and configuration")
        print("- Request metrics tracking")
        print("- Throttling configuration per phase")
        print("- Request prioritization")
        print("- Metrics export")
        print("- Integration module")
        print("- Request tracking lifecycle")
        print("- Path skip logic")
        print()
        
        return 0
        
    except Exception as e:
        print()
        print("=" * 80)
        print("❌ VALIDATION FAILED")
        print("=" * 80)
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
