"""
Test: Basic API Functionality Available Within 30 Seconds

This test validates that basic API functionality is available within 30 seconds
of application startup, as required by the startup optimization specification.

**Validates: Requirements 1.1, 2.1, 2.4**

Test Strategy:
- Start the application
- Wait up to 30 seconds
- Verify basic API endpoints are responding
- Verify health checks are passing
- Verify request queuing is active
- Verify model status reporting is available
"""

import pytest
import asyncio
import time
import httpx
from datetime import datetime, timedelta


class TestBasicAPI30SecondAvailability:
    """Test suite for basic API availability within 30 seconds."""
    
    @pytest.mark.asyncio
    async def test_health_endpoints_available_within_30_seconds(self):
        """
        Test that health endpoints are available within 30 seconds.
        
        **Validates: Requirement 1.1, 1.4**
        """
        start_time = time.time()
        max_wait_time = 30.0
        
        # Import and initialize the minimal server
        from src.multimodal_librarian.startup.minimal_server import initialize_minimal_server, get_minimal_server
        
        # Initialize minimal server
        server = await initialize_minimal_server()
        
        # Wait for server to be ready (should be immediate)
        await asyncio.sleep(2)
        
        # Check that initialization took less than 30 seconds
        initialization_time = time.time() - start_time
        assert initialization_time < max_wait_time, \
            f"Server initialization took {initialization_time:.2f}s, expected < {max_wait_time}s"
        
        # Verify server status
        status = server.get_status()
        assert status.health_check_ready, "Health check should be ready"
        assert status.status.value in ["minimal", "ready"], \
            f"Server status should be 'minimal' or 'ready', got '{status.status.value}'"
        
        print(f"✓ Health endpoints available in {initialization_time:.2f}s (target: <30s)")
    
    @pytest.mark.asyncio
    async def test_basic_capabilities_available_within_30_seconds(self):
        """
        Test that basic capabilities are available within 30 seconds.
        
        **Validates: Requirement 2.1, 2.4**
        """
        start_time = time.time()
        max_wait_time = 30.0
        
        # Import and initialize
        from src.multimodal_librarian.startup.minimal_server import initialize_minimal_server
        
        server = await initialize_minimal_server()
        await asyncio.sleep(2)
        
        # Check capabilities
        status = server.get_status()
        
        # Required basic capabilities
        required_capabilities = [
            "health_endpoints",
            "basic_api",
            "status_reporting",
            "request_queuing",
            "fallback_responses"
        ]
        
        for capability in required_capabilities:
            assert status.capabilities.get(capability, False), \
                f"Required capability '{capability}' not available"
        
        elapsed_time = time.time() - start_time
        assert elapsed_time < max_wait_time, \
            f"Capability check took {elapsed_time:.2f}s, expected < {max_wait_time}s"
        
        print(f"✓ Basic capabilities available in {elapsed_time:.2f}s (target: <30s)")
        print(f"  Available capabilities: {list(status.capabilities.keys())}")
    
    @pytest.mark.asyncio
    async def test_model_status_reporting_available_within_30_seconds(self):
        """
        Test that model status reporting is available within 30 seconds.
        
        **Validates: Requirement 2.4**
        """
        start_time = time.time()
        max_wait_time = 30.0
        
        # Import and initialize
        from src.multimodal_librarian.startup.minimal_server import initialize_minimal_server
        
        server = await initialize_minimal_server()
        await asyncio.sleep(2)
        
        # Check model status reporting
        status = server.get_status()
        
        # Should have model statuses available
        assert len(status.model_statuses) > 0, "Model statuses should be available"
        
        # Should be able to get status for specific models
        for model_name in status.model_statuses.keys():
            model_status = server.get_model_status(model_name)
            assert model_status in ["pending", "loading", "loaded", "failed", "unknown"], \
                f"Invalid model status: {model_status}"
        
        elapsed_time = time.time() - start_time
        assert elapsed_time < max_wait_time, \
            f"Model status check took {elapsed_time:.2f}s, expected < {max_wait_time}s"
        
        print(f"✓ Model status reporting available in {elapsed_time:.2f}s (target: <30s)")
        print(f"  Tracking {len(status.model_statuses)} models")
    
    @pytest.mark.asyncio
    async def test_request_queuing_available_within_30_seconds(self):
        """
        Test that request queuing is available within 30 seconds.
        
        **Validates: Requirement 2.1, 2.4**
        """
        start_time = time.time()
        max_wait_time = 30.0
        
        # Import and initialize
        from src.multimodal_librarian.startup.minimal_server import initialize_minimal_server
        
        server = await initialize_minimal_server()
        await asyncio.sleep(2)
        
        # Test request queuing
        queued_request = server.queue_request(
            request_id="test-123",
            endpoint="/api/chat",
            method="POST",
            user_message="Test message",
            priority="normal"
        )
        
        assert queued_request is not None, "Request should be queued"
        assert queued_request.request_id == "test-123"
        assert queued_request.endpoint == "/api/chat"
        
        # Check queue status
        queue_status = server.get_queue_status()
        assert queue_status["queue_size"] >= 1, "Queue should contain at least 1 request"
        
        elapsed_time = time.time() - start_time
        assert elapsed_time < max_wait_time, \
            f"Request queuing check took {elapsed_time:.2f}s, expected < {max_wait_time}s"
        
        print(f"✓ Request queuing available in {elapsed_time:.2f}s (target: <30s)")
        print(f"  Queue size: {queue_status['queue_size']}")
    
    @pytest.mark.asyncio
    async def test_fallback_responses_available_within_30_seconds(self):
        """
        Test that fallback responses are available within 30 seconds.
        
        **Validates: Requirement 2.5**
        """
        start_time = time.time()
        max_wait_time = 30.0
        
        # Import and initialize
        from src.multimodal_librarian.startup.minimal_server import initialize_minimal_server
        
        server = await initialize_minimal_server()
        await asyncio.sleep(2)
        
        # Test fallback responses for different endpoints
        test_endpoints = [
            "/api/chat",
            "/api/search",
            "/api/documents"
        ]
        
        for endpoint in test_endpoints:
            fallback = server.get_fallback_response(endpoint, "Test message")
            
            assert fallback is not None, f"Fallback response should be available for {endpoint}"
            assert "status" in fallback, "Fallback should have status"
            assert "message" in fallback or "fallback_response" in fallback, \
                "Fallback should have message or fallback_response"
        
        elapsed_time = time.time() - start_time
        assert elapsed_time < max_wait_time, \
            f"Fallback response check took {elapsed_time:.2f}s, expected < {max_wait_time}s"
        
        print(f"✓ Fallback responses available in {elapsed_time:.2f}s (target: <30s)")
        print(f"  Tested {len(test_endpoints)} endpoints")
    
    @pytest.mark.asyncio
    async def test_phase_manager_minimal_phase_within_30_seconds(self):
        """
        Test that phase manager reaches MINIMAL phase within 30 seconds.
        
        **Validates: Requirement 1.1, 2.1**
        """
        start_time = time.time()
        max_wait_time = 30.0
        
        # Import and initialize
        from src.multimodal_librarian.startup.phase_manager import StartupPhaseManager, StartupPhase
        
        phase_manager = StartupPhaseManager()
        
        # Start phase progression
        await phase_manager.start_phase_progression()
        
        # Wait a bit for initialization
        await asyncio.sleep(5)
        
        # Check that we're in MINIMAL phase
        assert phase_manager.current_phase == StartupPhase.MINIMAL, \
            f"Should be in MINIMAL phase, got {phase_manager.current_phase}"
        
        # Check that health check is ready
        assert phase_manager.status.health_check_ready, "Health check should be ready"
        
        elapsed_time = time.time() - start_time
        assert elapsed_time < max_wait_time, \
            f"Phase manager initialization took {elapsed_time:.2f}s, expected < {max_wait_time}s"
        
        # Cleanup
        await phase_manager.shutdown()
        
        print(f"✓ Phase manager reached MINIMAL phase in {elapsed_time:.2f}s (target: <30s)")
    
    @pytest.mark.asyncio
    async def test_complete_basic_api_stack_within_30_seconds(self):
        """
        Integration test: Complete basic API stack available within 30 seconds.
        
        This test validates the complete integration of:
        - Minimal server
        - Phase manager
        - Health endpoints
        - Request queuing
        - Fallback responses
        - Model status reporting
        
        **Validates: Requirements 1.1, 1.4, 2.1, 2.4, 2.5**
        """
        start_time = time.time()
        max_wait_time = 30.0
        
        # Initialize complete stack
        from src.multimodal_librarian.startup.minimal_server import initialize_minimal_server
        from src.multimodal_librarian.startup.phase_manager import StartupPhaseManager, StartupPhase
        
        # Start phase manager
        phase_manager = StartupPhaseManager()
        await phase_manager.start_phase_progression()
        
        # Start minimal server
        server = await initialize_minimal_server()
        
        # Wait for initialization
        await asyncio.sleep(5)
        
        # Verify all components
        checks = {
            "phase_manager_minimal": phase_manager.current_phase == StartupPhase.MINIMAL,
            "health_check_ready": phase_manager.status.health_check_ready,
            "server_ready": server.get_status().health_check_ready,
            "capabilities_available": len(server.get_status().capabilities) >= 5,
            "model_status_tracking": len(server.get_status().model_statuses) > 0,
            "request_queuing": server.get_status().capabilities.get("request_queuing", False),
            "fallback_responses": server.get_status().capabilities.get("fallback_responses", False)
        }
        
        # All checks should pass
        failed_checks = [name for name, passed in checks.items() if not passed]
        assert len(failed_checks) == 0, \
            f"Failed checks: {failed_checks}"
        
        elapsed_time = time.time() - start_time
        assert elapsed_time < max_wait_time, \
            f"Complete stack initialization took {elapsed_time:.2f}s, expected < {max_wait_time}s"
        
        # Cleanup
        await phase_manager.shutdown()
        
        print(f"✓ Complete basic API stack available in {elapsed_time:.2f}s (target: <30s)")
        print(f"  All {len(checks)} integration checks passed")
        print(f"  Components: phase_manager, minimal_server, health_endpoints, queuing, fallbacks")


if __name__ == "__main__":
    """Run tests directly for quick validation."""
    import sys
    
    async def run_tests():
        """Run all tests."""
        test_suite = TestBasicAPI30SecondAvailability()
        
        tests = [
            ("Health Endpoints", test_suite.test_health_endpoints_available_within_30_seconds),
            ("Basic Capabilities", test_suite.test_basic_capabilities_available_within_30_seconds),
            ("Model Status Reporting", test_suite.test_model_status_reporting_available_within_30_seconds),
            ("Request Queuing", test_suite.test_request_queuing_available_within_30_seconds),
            ("Fallback Responses", test_suite.test_fallback_responses_available_within_30_seconds),
            ("Phase Manager Minimal", test_suite.test_phase_manager_minimal_phase_within_30_seconds),
            ("Complete API Stack", test_suite.test_complete_basic_api_stack_within_30_seconds)
        ]
        
        print("\n" + "="*80)
        print("BASIC API 30-SECOND AVAILABILITY TEST SUITE")
        print("="*80 + "\n")
        
        passed = 0
        failed = 0
        
        for test_name, test_func in tests:
            try:
                print(f"\nRunning: {test_name}")
                print("-" * 80)
                await test_func()
                passed += 1
                print(f"✓ PASSED: {test_name}\n")
            except Exception as e:
                failed += 1
                print(f"✗ FAILED: {test_name}")
                print(f"  Error: {str(e)}\n")
        
        print("="*80)
        print(f"RESULTS: {passed} passed, {failed} failed out of {len(tests)} tests")
        print("="*80 + "\n")
        
        return failed == 0
    
    # Run tests
    success = asyncio.run(run_tests())
    sys.exit(0 if success else 1)
