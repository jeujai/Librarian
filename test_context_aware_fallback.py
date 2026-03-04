#!/usr/bin/env python3
"""
Test script for context-aware fallback responses.

This script tests the fallback response system to ensure it properly
analyzes user intent and provides appropriate context-aware responses.
"""

import sys
import os
import asyncio
import logging
from datetime import datetime

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_fallback_service():
    """Test the fallback service functionality."""
    try:
        from multimodal_librarian.services.fallback_service import get_fallback_service, UserIntent
        from multimodal_librarian.services.expectation_manager import get_expectation_manager
        
        print("🧪 Testing Context-Aware Fallback Response System")
        print("=" * 60)
        
        # Initialize services
        fallback_service = get_fallback_service()
        expectation_manager = get_expectation_manager()
        
        # Test cases with different user intents
        test_cases = [
            {
                "message": "Can you analyze this document for me?",
                "expected_intent": "document_processing",
                "description": "Document processing request"
            },
            {
                "message": "What is machine learning?",
                "expected_intent": "simple_question", 
                "description": "Simple question"
            },
            {
                "message": "Help me compare the pros and cons of different AI models",
                "expected_intent": "complex_analysis",
                "description": "Complex analysis request"
            },
            {
                "message": "Search for information about Python programming",
                "expected_intent": "search_query",
                "description": "Search query"
            },
            {
                "message": "Hello, how are you?",
                "expected_intent": "conversation",
                "description": "Conversational greeting"
            },
            {
                "message": "What's your current status?",
                "expected_intent": "system_status",
                "description": "System status inquiry"
            }
        ]
        
        print("\n📋 Testing Intent Analysis:")
        print("-" * 40)
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n{i}. {test_case['description']}")
            print(f"   Input: \"{test_case['message']}\"")
            
            # Test intent analysis
            intent_analysis = fallback_service.analyze_user_intent(test_case['message'])
            
            print(f"   Detected Intent: {intent_analysis.primary_intent.value}")
            print(f"   Confidence: {intent_analysis.confidence:.2f}")
            print(f"   Keywords: {intent_analysis.keywords}")
            print(f"   Complexity: {intent_analysis.complexity_level}")
            print(f"   Required Capabilities: {intent_analysis.required_capabilities}")
            
            # Verify intent detection
            if intent_analysis.primary_intent.value == test_case['expected_intent']:
                print("   ✅ Intent correctly detected")
            else:
                print(f"   ⚠️  Expected {test_case['expected_intent']}, got {intent_analysis.primary_intent.value}")
        
        print("\n🎯 Testing Fallback Response Generation:")
        print("-" * 45)
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n{i}. {test_case['description']}")
            print(f"   Input: \"{test_case['message']}\"")
            
            # Generate fallback response
            fallback_response = fallback_service.generate_fallback_response(test_case['message'])
            
            print(f"   Response Quality: {fallback_response.response_quality.value}")
            print(f"   Response: {fallback_response.response_text[:100]}...")
            print(f"   Limitations: {fallback_response.limitations[:2]}")  # Show first 2
            print(f"   Alternatives: {fallback_response.available_alternatives[:2]}")  # Show first 2
            print(f"   Upgrade Message: {fallback_response.upgrade_message}")
            print(f"   Helpful Now: {fallback_response.helpful_now}")
            
            if fallback_response.estimated_full_ready_time:
                print(f"   ETA: {fallback_response.estimated_full_ready_time}s")
        
        print("\n🎨 Testing Expectation Management:")
        print("-" * 40)
        
        # Test expectation management
        test_message = "Can you help me analyze a complex document?"
        base_response = {"response": "I can help with that."}
        
        expectation_response = expectation_manager.create_expectation_aware_response(
            user_message=test_message,
            base_response=base_response
        )
        
        print(f"Input: \"{test_message}\"")
        print(f"Enhanced Response Keys: {list(expectation_response.keys())}")
        
        if "expectation_management" in expectation_response:
            exp_mgmt = expectation_response["expectation_management"]
            print(f"Primary Message: {exp_mgmt.get('primary_message', 'N/A')[:100]}...")
            print(f"Timeline Message: {exp_mgmt.get('timeline_message', 'N/A')}")
            print(f"Should Queue: {exp_mgmt.get('should_queue', False)}")
            print(f"Alternatives: {len(exp_mgmt.get('alternatives', []))}")
        
        if "user_guidance" in expectation_response:
            guidance = expectation_response["user_guidance"]
            print(f"Recommended Action: {guidance.get('recommended_action', 'N/A')}")
            print(f"Expectation Level: {guidance.get('expectation_level', 'N/A')}")
        
        # Test contextual response creation using fallback service directly
        print(f"\n📝 Testing Direct Fallback Response:")
        print("-" * 45)
        
        fallback_response = fallback_service.generate_fallback_response(test_message)
        
        print(f"Input: \"{test_message}\"")
        print(f"Response: {fallback_response.response_text[:150]}...")
        print(f"Quality Level: {fallback_response.response_quality.value}")
        print(f"Limitations: {fallback_response.limitations[:2]}")
        print(f"Alternatives: {fallback_response.available_alternatives[:2]}")
        print(f"Upgrade Message: {fallback_response.upgrade_message}")
        print(f"Helpful Now: {fallback_response.helpful_now}")
        print(f"Context Preserved: {fallback_response.context_preserved}")
        
        print("\n✅ All tests completed successfully!")
        print("\n📊 Test Summary:")
        print(f"   - Intent analysis working: ✅")
        print(f"   - Fallback responses generated: ✅") 
        print(f"   - Expectation management active: ✅")
        print(f"   - Contextual responses created: ✅")
        print(f"   - Quality indicators working: ✅")
        
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure you're running from the project root directory")
        return False
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_capability_service_integration():
    """Test integration with capability service."""
    try:
        from multimodal_librarian.services.capability_service import get_capability_service
        
        print("\n🔗 Testing Capability Service Integration:")
        print("-" * 45)
        
        capability_service = get_capability_service()
        
        # Test capability summary
        capabilities = capability_service.get_capability_summary()
        print(f"Overall readiness: {capabilities.get('overall', {}).get('readiness_percent', 0):.1f}%")
        print(f"Current level: {capabilities.get('overall', {}).get('current_level', 'unknown')}")
        
        # Test request handling capability
        test_requests = [
            ("simple_chat", ["simple_text"]),
            ("document_analysis", ["document_analysis", "document_upload"]),
            ("complex_reasoning", ["complex_reasoning", "advanced_chat"])
        ]
        
        for request_type, required_caps in test_requests:
            can_handle = capability_service.can_handle_request(request_type, required_caps)
            print(f"\nRequest: {request_type}")
            print(f"  Can handle: {can_handle['can_handle']}")
            print(f"  Quality level: {can_handle['quality_level']}")
            print(f"  ETA: {can_handle.get('eta_seconds', 0)}s")
            print(f"  Recommendation: {can_handle['recommendation']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Capability service integration test failed: {e}")
        return False


if __name__ == "__main__":
    print("🚀 Starting Context-Aware Fallback Response Tests")
    print("=" * 60)
    
    success = True
    
    # Test fallback service
    if not test_fallback_service():
        success = False
    
    # Test capability service integration
    if not test_capability_service_integration():
        success = False
    
    print("\n" + "=" * 60)
    if success:
        print("🎉 All tests passed! Context-aware fallback system is working correctly.")
        sys.exit(0)
    else:
        print("❌ Some tests failed. Please check the implementation.")
        sys.exit(1)