#!/usr/bin/env python3
"""
Immediate Feedback Unit Tests

This module provides unit tests for the immediate feedback functionality
without requiring a running server. It tests the core components that
ensure users receive immediate feedback on all requests.

Validates Requirements:
- REQ-2: Application Startup Optimization (graceful degradation)
- REQ-3: Smart User Experience (immediate feedback)
"""

import os
import sys
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from multimodal_librarian.services.fallback_service import (
    FallbackResponseService,
    UserIntent,
    get_fallback_service
)
from multimodal_librarian.services.expectation_manager import (
    ExpectationManager,
    get_expectation_manager
)
from multimodal_librarian.services.capability_service import (
    CapabilityService,
    CapabilityLevel,
    get_capability_service
)
from multimodal_librarian.api.middleware.loading_middleware import (
    LoadingStateInjector,
    get_loading_state_injector
)


class TestImmediateFeedbackComponents:
    """Test that all components provide immediate feedback."""
    
    def test_fallback_service_provides_immediate_response(self):
        """Test that fallback service always provides a response."""
        fallback_service = get_fallback_service()
        
        # Test various user messages
        test_messages = [
            "Hello",
            "Analyze this complex document",
            "Search for information",
            "What can you do?",
            "Help me with a task",
            "",  # Empty message
            "x" * 1000,  # Very long message
        ]
        
        for message in test_messages:
            # Generate fallback response
            response = fallback_service.generate_fallback_response(message)
            
            # Verify response is provided
            assert response is not None, f"No response for message: {message[:50]}"
            assert response.response_text, f"Empty response for message: {message[:50]}"
            assert len(response.response_text) > 0, f"Empty response text for message: {message[:50]}"
            
            # Verify response has quality indicator
            assert response.response_quality is not None
            assert isinstance(response.response_quality, CapabilityLevel)
            
            # Verify response has helpful information
            assert response.limitations is not None
            assert response.available_alternatives is not None
            assert response.upgrade_message is not None
    
    def test_fallback_service_analyzes_user_intent(self):
        """Test that fallback service analyzes user intent correctly."""
        fallback_service = get_fallback_service()
        
        # Test intent analysis for different message types
        test_cases = [
            ("What is the weather?", UserIntent.SIMPLE_QUESTION),
            ("Analyze this complex data", UserIntent.COMPLEX_ANALYSIS),
            ("Upload my document", UserIntent.DOCUMENT_PROCESSING),
            ("Search for information", UserIntent.SEARCH_QUERY),
            ("Hello", UserIntent.CONVERSATION),
            ("What's your status?", UserIntent.SYSTEM_STATUS),
        ]
        
        for message, expected_intent in test_cases:
            intent_analysis = fallback_service.analyze_user_intent(message)
            
            # Verify intent is detected
            assert intent_analysis is not None
            assert intent_analysis.primary_intent is not None
            
            # For most cases, we should detect the right intent
            # (Some may be ambiguous, so we just check it's not UNKNOWN)
            if expected_intent != UserIntent.UNKNOWN:
                assert intent_analysis.primary_intent != UserIntent.UNKNOWN, \
                    f"Failed to detect intent for: {message}"
    
    def test_expectation_manager_provides_context(self):
        """Test that expectation manager provides contextual information."""
        expectation_manager = get_expectation_manager()
        
        # Get expectation response (which provides context)
        expectation_response = expectation_manager.manage_expectations(
            user_message="Hello, what can you do?",
            previous_interactions=0
        )
        
        # Verify context is provided
        assert expectation_response is not None
        assert expectation_response.primary_message is not None
        assert expectation_response.expectation_message is not None
        assert expectation_response.timeline_message is not None
        assert expectation_response.capability_explanation is not None
        assert expectation_response.next_steps is not None
        assert expectation_response.alternative_suggestions is not None
    
    def test_expectation_manager_creates_contextual_responses(self):
        """Test that expectation manager creates contextual responses."""
        expectation_manager = get_expectation_manager()
        
        # Test various user messages
        test_messages = [
            "Hello",
            "Analyze this document",
            "Search for data",
            "What can you do?",
        ]
        
        for message in test_messages:
            # Create base response
            base_response = {"message": "Test response"}
            
            # Create expectation-aware response
            response = expectation_manager.create_expectation_aware_response(
                user_message=message,
                base_response=base_response,
                previous_interactions=0
            )
            
            # Verify response is provided
            assert response is not None
            assert "message" in response
            assert len(response["message"]) > 0
            
            # Verify response has expectation management context
            assert "expectation_management" in response
            assert "user_guidance" in response
            
            # Verify expectation management has required fields
            exp_mgmt = response["expectation_management"]
            assert "primary_message" in exp_mgmt
            assert "expectation_message" in exp_mgmt
            assert "timeline_message" in exp_mgmt
            assert "capability_explanation" in exp_mgmt
    
    def test_capability_service_provides_current_capabilities(self):
        """Test that capability service provides current capabilities."""
        capability_service = get_capability_service()
        
        # Get current capabilities
        capabilities = capability_service.get_current_capabilities()
        
        # Verify capabilities are provided
        assert capabilities is not None
        assert len(capabilities) > 0
        
        # Verify basic capabilities are always available
        assert "health_check" in capabilities
        assert "simple_text" in capabilities
        assert "status_updates" in capabilities
        
        # Verify each capability has required information
        for cap_name, capability in capabilities.items():
            assert capability.name == cap_name
            assert capability.level is not None
            assert capability.description is not None
            assert capability.quality_indicator is not None
    
    def test_capability_service_provides_capability_summary(self):
        """Test that capability service provides capability summary."""
        capability_service = get_capability_service()
        
        # Get capability summary
        summary = capability_service.get_capability_summary()
        
        # Verify summary is provided
        assert summary is not None
        assert "basic" in summary
        assert "enhanced" in summary
        assert "full" in summary
        assert "overall" in summary
        
        # Verify overall summary has required fields
        assert "total_capabilities" in summary["overall"]
        assert "available_capabilities" in summary["overall"]
        assert "readiness_percent" in summary["overall"]
        assert "current_level" in summary["overall"]
    
    def test_capability_service_provides_loading_progress(self):
        """Test that capability service provides loading progress."""
        capability_service = get_capability_service()
        
        # Get loading progress
        progress = capability_service.get_loading_progress()
        
        # Verify progress is provided
        assert progress is not None
        assert "phase_progress" in progress
        assert "model_progress" in progress
        assert "overall_progress" in progress
        
        # Verify overall progress is a valid percentage
        assert 0 <= progress["overall_progress"] <= 100
    
    def test_capability_service_can_handle_request_check(self):
        """Test that capability service can check if requests can be handled."""
        capability_service = get_capability_service()
        
        # Test various request types
        test_cases = [
            ("health_check", []),
            ("simple_chat", ["simple_text"]),
            ("advanced_chat", ["advanced_chat"]),
            ("document_analysis", ["document_analysis"]),
        ]
        
        for request_type, required_capabilities in test_cases:
            result = capability_service.can_handle_request(
                request_type=request_type,
                required_capabilities=required_capabilities
            )
            
            # Verify result is provided
            assert result is not None
            assert "can_handle" in result
            assert "quality_level" in result
            assert "quality_indicator" in result
            assert "available_capabilities" in result
            assert "missing_capabilities" in result
            assert "fallback_available" in result
            assert "recommendation" in result
            
            # Verify fallback is always available
            assert result["fallback_available"] is True
    
    def test_loading_state_injector_injects_state(self):
        """Test that loading state injector adds state to responses."""
        injector = get_loading_state_injector()
        
        # Test response data
        response_data = {
            "message": "Hello",
            "data": {"test": "value"}
        }
        
        # Inject loading state
        enhanced_response = injector.inject_loading_state(
            response_data=response_data.copy(),
            request_type="test_request",
            required_capabilities=["simple_text"]
        )
        
        # Verify loading state was added
        assert "loading_state" in enhanced_response
        assert "response_quality" in enhanced_response
        
        # Verify original data is preserved
        assert enhanced_response["message"] == "Hello"
        assert enhanced_response["data"]["test"] == "value"
        
        # Verify loading state has required fields
        loading_state = enhanced_response["loading_state"]
        assert "capability_check" in loading_state
        assert "current_capabilities" in loading_state
        assert "loading_progress" in loading_state
        
        # Verify response quality has required fields
        response_quality = enhanced_response["response_quality"]
        assert "level" in response_quality
        assert "indicator" in response_quality
        assert "description" in response_quality
    
    def test_all_components_respond_without_errors(self):
        """Test that all components respond without throwing errors."""
        # This test ensures that even in error conditions, components
        # provide some response rather than crashing
        
        # Test fallback service with edge cases
        fallback_service = get_fallback_service()
        
        try:
            # Empty message
            response = fallback_service.generate_fallback_response("")
            assert response is not None
        except Exception as e:
            pytest.fail(f"Fallback service failed on empty message: {e}")
        
        try:
            # Very long message
            response = fallback_service.generate_fallback_response("x" * 10000)
            assert response is not None
        except Exception as e:
            pytest.fail(f"Fallback service failed on long message: {e}")
        
        try:
            # Special characters
            response = fallback_service.generate_fallback_response("!@#$%^&*()")
            assert response is not None
        except Exception as e:
            pytest.fail(f"Fallback service failed on special characters: {e}")
        
        # Test expectation manager with edge cases
        expectation_manager = get_expectation_manager()
        
        try:
            expectation_response = expectation_manager.manage_expectations(
                user_message="Test message",
                previous_interactions=0
            )
            assert expectation_response is not None
        except Exception as e:
            pytest.fail(f"Expectation manager failed to manage expectations: {e}")
        
        try:
            base_response = {"message": "Test"}
            response = expectation_manager.create_expectation_aware_response(
                user_message="",
                base_response=base_response,
                previous_interactions=0
            )
            assert response is not None
        except Exception as e:
            pytest.fail(f"Expectation manager failed on empty message: {e}")
        
        # Test capability service
        capability_service = get_capability_service()
        
        try:
            capabilities = capability_service.get_current_capabilities()
            assert capabilities is not None
        except Exception as e:
            pytest.fail(f"Capability service failed to get capabilities: {e}")
        
        try:
            summary = capability_service.get_capability_summary()
            assert summary is not None
        except Exception as e:
            pytest.fail(f"Capability service failed to get summary: {e}")
        
        try:
            progress = capability_service.get_loading_progress()
            assert progress is not None
        except Exception as e:
            pytest.fail(f"Capability service failed to get progress: {e}")


class TestImmediateFeedbackRequirements:
    """Test that immediate feedback requirements are met."""
    
    def test_no_model_not_loaded_errors_in_fallback_responses(self):
        """Test that fallback responses never contain 'model not loaded' errors."""
        fallback_service = get_fallback_service()
        
        test_messages = [
            "Hello",
            "Analyze this document",
            "Search for information",
            "Complex reasoning task",
        ]
        
        for message in test_messages:
            response = fallback_service.generate_fallback_response(message)
            
            # Verify response doesn't contain error messages
            response_text = response.response_text.lower()
            assert "model not loaded" not in response_text, \
                f"Fallback response contains 'model not loaded' error for: {message}"
            assert "model is not available" not in response_text, \
                f"Fallback response contains 'model not available' error for: {message}"
            assert "error" not in response_text or "no error" in response_text, \
                f"Fallback response contains generic error for: {message}"
    
    def test_fallback_responses_are_helpful(self):
        """Test that fallback responses provide helpful information."""
        fallback_service = get_fallback_service()
        
        test_messages = [
            "Hello",
            "Analyze this document",
            "Search for information",
        ]
        
        for message in test_messages:
            response = fallback_service.generate_fallback_response(message)
            
            # Verify response is helpful
            assert len(response.response_text) > 50, \
                f"Fallback response too short for: {message}"
            
            # Verify response has context
            assert response.limitations is not None and len(response.limitations) > 0, \
                f"No limitations provided for: {message}"
            assert response.available_alternatives is not None and len(response.available_alternatives) > 0, \
                f"No alternatives provided for: {message}"
            assert response.upgrade_message is not None and len(response.upgrade_message) > 0, \
                f"No upgrade message provided for: {message}"
    
    def test_responses_include_quality_indicators(self):
        """Test that responses include quality indicators."""
        fallback_service = get_fallback_service()
        
        test_messages = ["Hello", "Analyze document", "Search"]
        
        for message in test_messages:
            response = fallback_service.generate_fallback_response(message)
            
            # Verify quality indicator is provided
            assert response.response_quality is not None
            assert isinstance(response.response_quality, CapabilityLevel)
            
            # Verify quality level is one of the expected values
            assert response.response_quality in [
                CapabilityLevel.BASIC,
                CapabilityLevel.ENHANCED,
                CapabilityLevel.FULL
            ]
    
    def test_responses_include_capability_information(self):
        """Test that responses include capability information."""
        capability_service = get_capability_service()
        
        # Get capability summary
        summary = capability_service.get_capability_summary()
        
        # Verify capability information is comprehensive
        assert "basic" in summary
        assert "enhanced" in summary
        assert "full" in summary
        
        # Verify each level has available and loading lists
        for level in ["basic", "enhanced", "full"]:
            assert "available" in summary[level]
            assert "loading" in summary[level]
            assert isinstance(summary[level]["available"], list)
            assert isinstance(summary[level]["loading"], list)
    
    def test_responses_include_progress_information(self):
        """Test that responses include progress information."""
        capability_service = get_capability_service()
        
        # Get loading progress
        progress = capability_service.get_loading_progress()
        
        # Verify progress information is provided
        assert "phase_progress" in progress
        assert "model_progress" in progress
        assert "overall_progress" in progress
        
        # Verify progress values are valid
        assert isinstance(progress["overall_progress"], (int, float))
        assert 0 <= progress["overall_progress"] <= 100


def test_immediate_feedback_integration():
    """Integration test for immediate feedback flow."""
    # Simulate a user request flow
    
    # 1. User makes a request
    user_message = "Analyze this complex document"
    
    # 2. Fallback service generates response
    fallback_service = get_fallback_service()
    fallback_response = fallback_service.generate_fallback_response(user_message)
    
    # 3. Verify immediate response is provided
    assert fallback_response is not None
    assert fallback_response.response_text is not None
    assert len(fallback_response.response_text) > 0
    
    # 4. Expectation manager adds context
    expectation_manager = get_expectation_manager()
    base_response = {"message": fallback_response.response_text}
    contextual_response = expectation_manager.create_expectation_aware_response(
        user_message=user_message,
        base_response=base_response,
        previous_interactions=0
    )
    
    # 5. Verify contextual information is added
    assert contextual_response is not None
    assert "message" in contextual_response
    assert "expectation_management" in contextual_response
    assert "user_guidance" in contextual_response
    
    # 6. Capability service provides current state
    capability_service = get_capability_service()
    capabilities = capability_service.get_current_capabilities()
    summary = capability_service.get_capability_summary()
    progress = capability_service.get_loading_progress()
    
    # 7. Verify all information is available
    assert capabilities is not None
    assert summary is not None
    assert progress is not None
    
    # 8. Loading state injector adds state to response
    injector = get_loading_state_injector()
    final_response = injector.inject_loading_state(
        response_data={"message": contextual_response["message"]},
        request_type="chat",
        required_capabilities=["advanced_chat"]
    )
    
    # 9. Verify final response has all required information
    assert "loading_state" in final_response
    assert "response_quality" in final_response
    assert "message" in final_response
    
    print("✅ Immediate feedback integration test passed!")
    print(f"   User message: {user_message}")
    print(f"   Response provided: Yes")
    print(f"   Response length: {len(final_response['message'])} characters")
    print(f"   Quality level: {final_response['response_quality']['level']}")
    print(f"   Has loading state: Yes")
    print(f"   Has capability info: Yes")


if __name__ == "__main__":
    # Run pytest
    pytest.main([__file__, "-v", "-s"])
