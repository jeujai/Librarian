"""
Test: No User Requests Fail Due to "Model Not Loaded" Errors

This test validates the critical success criterion that NO user requests
fail due to "model not loaded" errors, regardless of system state.

Test Coverage:
1. Requests during minimal startup phase
2. Requests during model loading
3. Requests when models fail to load
4. Concurrent requests during startup
5. All API endpoints
6. WebSocket connections
7. Emergency fallback scenarios
"""

import pytest
import asyncio
import time
from typing import Dict, List, Any
from datetime import datetime


class TestNoModelNotLoadedErrors:
    """Test suite ensuring no requests fail due to model unavailability."""
    
    @pytest.mark.asyncio
    async def test_requests_during_minimal_phase(self):
        """Test that requests during minimal phase never fail with model errors."""
        from src.multimodal_librarian.api.middleware.model_availability_middleware import ModelAvailabilityMiddleware
        from src.multimodal_librarian.models.model_manager import get_model_manager
        from fastapi import Request
        from fastapi.responses import JSONResponse
        
        # Initialize middleware
        middleware = ModelAvailabilityMiddleware(app=None)
        
        # Simulate requests during minimal phase (no models loaded)
        model_manager = get_model_manager()
        
        # Ensure no models are loaded
        for model_name in model_manager.models.keys():
            model_instance = model_manager.models[model_name]
            from src.multimodal_librarian.models.model_manager import ModelStatus
            model_instance.status = ModelStatus.PENDING
        
        # Test various request types
        test_requests = [
            {"path": "/api/chat", "method": "POST", "body": {"message": "Hello"}},
            {"path": "/api/search", "method": "GET", "query": "test query"},
            {"path": "/api/documents", "method": "GET"},
            {"path": "/api/analyze", "method": "POST", "body": {"text": "analyze this"}}
        ]
        
        errors = []
        for req_data in test_requests:
            try:
                # Create mock request
                from unittest.mock import Mock
                request = Mock(spec=Request)
                request.url.path = req_data["path"]
                request.method = req_data["method"]
                request.query_params = req_data.get("query", {})
                
                # Process through middleware
                async def mock_call_next(req):
                    # Simulate endpoint that requires models
                    return JSONResponse({"status": "success"})
                
                response = await middleware.dispatch(request, mock_call_next)
                
                # Verify response is successful (no errors)
                assert response.status_code == 200, f"Request to {req_data['path']} failed with status {response.status_code}"
                
                # Verify no "model not loaded" errors in response
                if hasattr(response, 'body'):
                    body_text = response.body.decode() if isinstance(response.body, bytes) else str(response.body)
                    assert "model not loaded" not in body_text.lower(), f"Found 'model not loaded' error in response to {req_data['path']}"
                    assert "model is not available" not in body_text.lower(), f"Found 'model not available' error in response to {req_data['path']}"
                
            except Exception as e:
                errors.append(f"Request to {req_data['path']} raised exception: {e}")
        
        # Assert no errors occurred
        assert len(errors) == 0, f"Errors occurred during minimal phase testing:\n" + "\n".join(errors)
        
        print("✅ All requests during minimal phase handled successfully without model errors")
    
    @pytest.mark.asyncio
    async def test_requests_during_model_loading(self):
        """Test that requests during model loading never fail with model errors."""
        from src.multimodal_librarian.models.model_manager import get_model_manager, ModelStatus
        from src.multimodal_librarian.utils.model_request_wrapper import get_model_request_wrapper
        
        model_manager = get_model_manager()
        wrapper = get_model_request_wrapper()
        
        # Set some models to loading state
        for i, model_name in enumerate(list(model_manager.models.keys())[:3]):
            model_instance = model_manager.models[model_name]
            model_instance.status = ModelStatus.LOADING
        
        # Test function that requires models
        async def test_function(message: str):
            return {"response": f"Processed: {message}"}
        
        # Execute with fallback
        result = await wrapper.execute_with_fallback(
            test_function,
            "Test message",
            required_models=["chat-model-base", "text-embedding-small"]
        )
        
        # Verify result is successful
        assert result is not None, "Result should not be None"
        assert "status" in result or "response" in result, "Result should contain status or response"
        
        # Verify no error status
        if "status" in result:
            assert result["status"] in ["success", "error_handled"], f"Unexpected status: {result['status']}"
        
        # Verify fallback mode is indicated
        if "fallback_mode" in result:
            assert result["fallback_mode"] == True, "Fallback mode should be True when models unavailable"
        
        print("✅ Requests during model loading handled successfully with fallback")
    
    @pytest.mark.asyncio
    async def test_requests_when_models_failed(self):
        """Test that requests when models fail to load still succeed with fallback."""
        from src.multimodal_librarian.models.model_manager import get_model_manager, ModelStatus
        from src.multimodal_librarian.utils.model_request_wrapper import get_model_request_wrapper
        
        model_manager = get_model_manager()
        wrapper = get_model_request_wrapper()
        
        # Set some models to failed state
        for i, model_name in enumerate(list(model_manager.models.keys())[:2]):
            model_instance = model_manager.models[model_name]
            model_instance.status = ModelStatus.FAILED
            model_instance.error_message = "Simulated failure for testing"
        
        # Test function that requires failed models
        async def test_function(message: str):
            return {"response": f"Processed: {message}"}
        
        # Execute with fallback
        result = await wrapper.execute_with_fallback(
            test_function,
            "Test message with failed models",
            required_models=["chat-model-base"]
        )
        
        # Verify result is successful despite model failure
        assert result is not None, "Result should not be None even with failed models"
        assert "response" in result or "status" in result, "Result should contain response or status"
        
        # Verify no exception was raised
        if "status" in result:
            assert result["status"] != "error", "Status should not be 'error' - should use fallback"
        
        print("✅ Requests with failed models handled successfully with fallback")
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_no_errors(self):
        """Test that concurrent requests during startup never produce model errors."""
        from src.multimodal_librarian.utils.model_request_wrapper import get_model_request_wrapper
        from src.multimodal_librarian.models.model_manager import get_model_manager, ModelStatus
        
        model_manager = get_model_manager()
        wrapper = get_model_request_wrapper()
        
        # Set models to various states
        model_states = [ModelStatus.PENDING, ModelStatus.LOADING, ModelStatus.FAILED]
        for i, model_name in enumerate(model_manager.models.keys()):
            model_instance = model_manager.models[model_name]
            model_instance.status = model_states[i % len(model_states)]
        
        # Test function
        async def test_function(message: str, request_id: int):
            await asyncio.sleep(0.01)  # Simulate processing
            return {"response": f"Request {request_id}: {message}"}
        
        # Execute many concurrent requests
        num_requests = 50
        tasks = []
        
        for i in range(num_requests):
            task = wrapper.execute_with_fallback(
                test_function,
                f"Message {i}",
                request_id=i,
                required_models=["chat-model-base", "text-embedding-small"]
            )
            tasks.append(task)
        
        # Wait for all requests to complete
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify all requests succeeded (no exceptions)
        errors = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                errors.append(f"Request {i} raised exception: {result}")
            elif result is None:
                errors.append(f"Request {i} returned None")
            elif isinstance(result, dict):
                # Check for error indicators
                if "error" in result and result.get("status") == "error":
                    errors.append(f"Request {i} returned error status")
        
        # Assert no errors
        assert len(errors) == 0, f"Concurrent requests produced errors:\n" + "\n".join(errors)
        
        print(f"✅ All {num_requests} concurrent requests handled successfully without model errors")
    
    @pytest.mark.asyncio
    async def test_all_api_endpoints_no_model_errors(self):
        """Test that all API endpoints handle model unavailability gracefully."""
        from src.multimodal_librarian.api.middleware.model_availability_middleware import ModelAvailabilityMiddleware
        from src.multimodal_librarian.models.model_manager import get_model_manager, ModelStatus
        from unittest.mock import Mock
        from fastapi import Request
        from fastapi.responses import JSONResponse
        
        middleware = ModelAvailabilityMiddleware(app=None)
        model_manager = get_model_manager()
        
        # Set all models to unavailable
        for model_name in model_manager.models.keys():
            model_instance = model_manager.models[model_name]
            model_instance.status = ModelStatus.PENDING
        
        # Test all major API endpoints
        endpoints = [
            "/api/chat",
            "/api/v1/chat",
            "/api/search",
            "/api/v1/search",
            "/api/documents",
            "/api/v1/documents",
            "/api/analyze",
            "/api/v1/analyze"
        ]
        
        errors = []
        for endpoint in endpoints:
            try:
                # Create mock request
                request = Mock(spec=Request)
                request.url.path = endpoint
                request.method = "POST"
                request.query_params = {}
                
                # Mock call_next
                async def mock_call_next(req):
                    return JSONResponse({"status": "success"})
                
                # Process through middleware
                response = await middleware.dispatch(request, mock_call_next)
                
                # Verify successful response
                assert response.status_code == 200, f"Endpoint {endpoint} returned status {response.status_code}"
                
                # Verify no model errors in response
                if hasattr(response, 'body'):
                    body_text = response.body.decode() if isinstance(response.body, bytes) else str(response.body)
                    if "model not loaded" in body_text.lower() or "model is not available" in body_text.lower():
                        errors.append(f"Endpoint {endpoint} returned model error in response")
                
            except Exception as e:
                errors.append(f"Endpoint {endpoint} raised exception: {e}")
        
        # Assert no errors
        assert len(errors) == 0, f"API endpoints produced model errors:\n" + "\n".join(errors)
        
        print(f"✅ All {len(endpoints)} API endpoints handled model unavailability gracefully")
    
    @pytest.mark.asyncio
    async def test_emergency_fallback_never_fails(self):
        """Test that emergency fallback always succeeds even in worst-case scenarios."""
        from src.multimodal_librarian.utils.model_request_wrapper import get_model_request_wrapper
        
        wrapper = get_model_request_wrapper()
        
        # Test function that will fail
        async def failing_function(message: str):
            raise Exception("Simulated catastrophic failure")
        
        # Execute with fallback - should never raise exception
        result = await wrapper.execute_with_fallback(
            failing_function,
            "Test message",
            required_models=["nonexistent-model"]
        )
        
        # Verify we got a result (not an exception)
        assert result is not None, "Emergency fallback should always return a result"
        assert isinstance(result, dict), "Emergency fallback should return a dict"
        
        # Verify it indicates fallback mode
        assert "fallback_mode" in result or "emergency_fallback" in result, "Result should indicate fallback mode"
        
        # Verify it has a response
        assert "response" in result, "Emergency fallback should always provide a response"
        
        print("✅ Emergency fallback handled catastrophic failure successfully")
    
    @pytest.mark.asyncio
    async def test_decorator_prevents_model_errors(self):
        """Test that decorators prevent model not loaded errors."""
        from src.multimodal_librarian.utils.model_request_wrapper import require_models, require_capability
        from src.multimodal_librarian.models.model_manager import get_model_manager, ModelStatus
        
        model_manager = get_model_manager()
        
        # Set models to unavailable
        for model_name in model_manager.models.keys():
            model_instance = model_manager.models[model_name]
            model_instance.status = ModelStatus.PENDING
        
        # Test function with require_models decorator
        @require_models(required_models=["chat-model-base"], allow_fallback_response=True)
        async def test_function_with_models(message: str):
            return {"response": f"Processed: {message}"}
        
        # Execute function - should not raise exception
        result = await test_function_with_models("Test message")
        
        # Verify result is successful
        assert result is not None, "Decorated function should return result"
        assert isinstance(result, dict), "Decorated function should return dict"
        
        # Test function with require_capability decorator
        @require_capability(required_capability="basic_chat", allow_fallback_response=True)
        async def test_function_with_capability(message: str):
            return {"response": f"Processed: {message}"}
        
        # Execute function - should not raise exception
        result2 = await test_function_with_capability("Test message")
        
        # Verify result is successful
        assert result2 is not None, "Decorated function should return result"
        assert isinstance(result2, dict), "Decorated function should return dict"
        
        print("✅ Decorators successfully prevented model not loaded errors")
    
    @pytest.mark.asyncio
    async def test_middleware_statistics_tracking(self):
        """Test that middleware tracks statistics correctly."""
        from src.multimodal_librarian.api.middleware.model_availability_middleware import ModelAvailabilityMiddleware
        
        middleware = ModelAvailabilityMiddleware(app=None)
        
        # Get initial statistics
        stats = middleware.get_statistics()
        
        # Verify statistics structure
        assert "total_requests" in stats, "Statistics should include total_requests"
        assert "model_available_requests" in stats, "Statistics should include model_available_requests"
        assert "fallback_responses" in stats, "Statistics should include fallback_responses"
        assert "model_not_loaded_prevented" in stats, "Statistics should include model_not_loaded_prevented"
        assert "fallback_rate" in stats, "Statistics should include fallback_rate"
        assert "model_available_rate" in stats, "Statistics should include model_available_rate"
        
        # Verify statistics are numeric
        for key, value in stats.items():
            assert isinstance(value, (int, float)), f"Statistic {key} should be numeric, got {type(value)}"
        
        print("✅ Middleware statistics tracking working correctly")
        print(f"   Statistics: {stats}")


@pytest.mark.asyncio
async def test_comprehensive_no_model_errors():
    """
    Comprehensive test that validates the success criterion:
    "No user requests fail due to 'model not loaded' errors"
    
    This test runs all sub-tests and provides a summary.
    """
    test_suite = TestNoModelNotLoadedErrors()
    
    print("\n" + "=" * 80)
    print("COMPREHENSIVE TEST: No User Requests Fail Due to 'Model Not Loaded' Errors")
    print("=" * 80 + "\n")
    
    tests = [
        ("Requests During Minimal Phase", test_suite.test_requests_during_minimal_phase),
        ("Requests During Model Loading", test_suite.test_requests_during_model_loading),
        ("Requests When Models Failed", test_suite.test_requests_when_models_failed),
        ("Concurrent Requests", test_suite.test_concurrent_requests_no_errors),
        ("All API Endpoints", test_suite.test_all_api_endpoints_no_model_errors),
        ("Emergency Fallback", test_suite.test_emergency_fallback_never_fails),
        ("Decorator Prevention", test_suite.test_decorator_prevents_model_errors),
        ("Statistics Tracking", test_suite.test_middleware_statistics_tracking)
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\nRunning: {test_name}")
        print("-" * 80)
        try:
            await test_func()
            results.append((test_name, "PASSED", None))
        except Exception as e:
            results.append((test_name, "FAILED", str(e)))
            print(f"❌ FAILED: {e}")
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    passed = sum(1 for _, status, _ in results if status == "PASSED")
    failed = sum(1 for _, status, _ in results if status == "FAILED")
    
    for test_name, status, error in results:
        symbol = "✅" if status == "PASSED" else "❌"
        print(f"{symbol} {test_name}: {status}")
        if error:
            print(f"   Error: {error}")
    
    print("\n" + "-" * 80)
    print(f"Total Tests: {len(results)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success Rate: {(passed / len(results)) * 100:.1f}%")
    print("=" * 80)
    
    # Assert all tests passed
    assert failed == 0, f"{failed} tests failed - see summary above"
    
    print("\n✅ SUCCESS CRITERION VALIDATED:")
    print("   NO user requests fail due to 'model not loaded' errors")
    print("   All requests are handled gracefully with fallback responses")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    # Run the comprehensive test
    asyncio.run(test_comprehensive_no_model_errors())
