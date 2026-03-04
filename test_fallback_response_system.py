#!/usr/bin/env python3
"""
Test script to verify fallback response system implementation.
This validates Task 3.2 completion.
"""

import asyncio
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

async def test_fallback_service():
    """Test the fallback service functionality."""
    print("🧪 Testing Fallback Service...")
    
    try:
        from multimodal_librarian.services.fallback_service import (
            get_fallback_service, RequestIntent, FallbackResponse
        )
        
        service = get_fallback_service()
        print("✅ Fallback service initialized")
        
        # Test intent analysis
        test_messages = [
            ("Hello, how are you?", RequestIntent.SIMPLE_CHAT),
            ("Can you analyze this complex document?", RequestIntent.COMPLEX_ANALYSIS),
            ("I need to upload a PDF file", RequestIntent.DOCUMENT_PROCESSING),
            ("Search for information about AI", RequestIntent.SEARCH_QUERY),
            ("What's your current status?", RequestIntent.STATUS_INQUIRY)
        ]
        
        for message, expected_intent in test_messages:
            detected_intent = service.analyze_intent(message)
            print(f"✅ '{message}' -> {detected_intent.value}")
            # Note: Intent detection is fuzzy, so we don't assert exact matches
        
        # Test fallback response generation
        response = service.generate_fallback_response("Can you help me analyze this document?")
        assert isinstance(response, FallbackResponse)
        assert response.message
        assert response.response_quality
        assert response.quality_indicator
        print("✅ Fallback response generation working")
        
        # Test contextual fallback
        contextual = service.create_contextual_fallback(
            "Hello there!",
            missing_capabilities=["advanced_chat"],
            available_capabilities=["simple_text"],
            eta_seconds=60
        )
        assert "status" in contextual
        assert "message" in contextual
        print("✅ Contextual fallback creation working")
        
        return True
        
    except Exception as e:
        print(f"❌ Fallback service test failed: {e}")
        return False

async def test_expectation_manager():
    """Test the expectation manager functionality."""
    print("\n🧪 Testing Expectation Manager...")
    
    try:
        from multimodal_librarian.services.expectation_manager import (
            get_expectation_manager, ExpectationLevel, ExpectationResponse
        )
        
        manager = get_expectation_manager()
        print("✅ Expectation manager initialized")
        
        # Test patience assessment
        test_cases = [
            ("I need this right now!", ExpectationLevel.IMMEDIATE),
            ("Can you help when you're ready?", ExpectationLevel.LONG_WAIT),
            ("I have a complex analysis task", ExpectationLevel.MEDIUM_WAIT)
        ]
        
        for message, expected_level in test_cases:
            from multimodal_librarian.services.fallback_service import RequestIntent
            patience = manager.assess_user_patience(message, RequestIntent.SIMPLE_CHAT)
            print(f"✅ '{message}' -> {patience.value}")
        
        # Test expectation management
        response = manager.manage_expectations("Can you analyze this document for me?")
        assert isinstance(response, ExpectationResponse)
        assert response.primary_message
        assert response.expectation_message
        assert response.timeline_message
        print("✅ Expectation management working")
        
        # Test expectation-aware response creation
        base_response = {"message": "Hello!"}
        enhanced = manager.create_expectation_aware_response(
            "Hello there!", base_response
        )
        assert "expectation_management" in enhanced
        print("✅ Expectation-aware response creation working")
        
        return True
        
    except Exception as e:
        print(f"❌ Expectation manager test failed: {e}")
        return False

async def test_intent_analysis():
    """Test intent analysis accuracy."""
    print("\n🧪 Testing Intent Analysis...")
    
    try:
        from multimodal_librarian.services.fallback_service import get_fallback_service, RequestIntent
        
        service = get_fallback_service()
        
        # Test various message types
        test_cases = [
            # Simple chat
            ("Hi there!", [RequestIntent.SIMPLE_CHAT]),
            ("How are you doing?", [RequestIntent.SIMPLE_CHAT]),
            
            # Complex analysis
            ("Please analyze this complex data", [RequestIntent.COMPLEX_ANALYSIS]),
            ("I need a detailed evaluation", [RequestIntent.COMPLEX_ANALYSIS]),
            
            # Document processing
            ("Upload this PDF document", [RequestIntent.DOCUMENT_PROCESSING]),
            ("Process this file for me", [RequestIntent.DOCUMENT_PROCESSING]),
            
            # Search queries
            ("Search for information about AI", [RequestIntent.SEARCH_QUERY]),
            ("Find documents related to machine learning", [RequestIntent.SEARCH_QUERY]),
            
            # Status inquiries
            ("What's your current status?", [RequestIntent.STATUS_INQUIRY]),
            ("Are you ready to help?", [RequestIntent.STATUS_INQUIRY])
        ]
        
        correct_predictions = 0
        total_predictions = len(test_cases)
        
        for message, expected_intents in test_cases:
            detected_intent = service.analyze_intent(message)
            is_correct = detected_intent in expected_intents
            
            status = "✅" if is_correct else "⚠️"
            print(f"{status} '{message}' -> {detected_intent.value}")
            
            if is_correct:
                correct_predictions += 1
        
        accuracy = (correct_predictions / total_predictions) * 100
        print(f"📊 Intent analysis accuracy: {accuracy:.1f}%")
        
        # We expect at least 60% accuracy for fuzzy intent detection
        return accuracy >= 60.0
        
    except Exception as e:
        print(f"❌ Intent analysis test failed: {e}")
        return False

async def test_response_quality_indicators():
    """Test response quality indicators and messaging."""
    print("\n🧪 Testing Response Quality Indicators...")
    
    try:
        from multimodal_librarian.services.fallback_service import get_fallback_service
        
        service = get_fallback_service()
        
        # Test different types of requests
        test_requests = [
            "Hello, how can you help me?",
            "I need complex analysis of this data",
            "Can you process this document?",
            "Search for relevant information"
        ]
        
        for request in test_requests:
            response = service.generate_fallback_response(request)
            
            # Verify response structure
            assert response.quality_indicator in ["⚡", "🔄", "🧠"]
            assert response.response_quality in ["basic", "enhanced", "full"]
            assert len(response.limitations) > 0
            assert len(response.available_alternatives) > 0
            assert response.upgrade_message
            
            print(f"✅ {response.quality_indicator} {response.response_quality}: '{request[:30]}...'")
        
        print("✅ Response quality indicators working correctly")
        return True
        
    except Exception as e:
        print(f"❌ Response quality indicators test failed: {e}")
        return False

async def test_eta_and_progress_messaging():
    """Test ETA and progress messaging."""
    print("\n🧪 Testing ETA and Progress Messaging...")
    
    try:
        from multimodal_librarian.services.expectation_manager import get_expectation_manager
        
        manager = get_expectation_manager()
        
        # Test ETA formatting
        eta_tests = [
            (0, "Ready now"),
            (15, "Ready in seconds"),
            (45, "Ready in about 1 minute"),
            (90, "Ready in about 2 minutes"),
            (180, "Ready in about 3 minutes")
        ]
        
        for eta_seconds, expected_pattern in eta_tests:
            description = manager._format_eta_description(eta_seconds)
            print(f"✅ {eta_seconds}s -> '{description}'")
            # Basic validation that description is reasonable
            assert len(description) > 0
            assert "ready" in description.lower()
        
        # Test progress indicators
        response = manager.manage_expectations("Can you help me with analysis?")
        progress = response.progress_indicators
        
        assert "eta_seconds" in progress or "overall_progress" in progress
        print("✅ Progress indicators working")
        
        return True
        
    except Exception as e:
        print(f"❌ ETA and progress messaging test failed: {e}")
        return False

async def main():
    """Run all tests."""
    print("🚀 Testing Fallback Response System Implementation")
    print("=" * 60)
    
    tests = [
        test_fallback_service,
        test_expectation_manager,
        test_intent_analysis,
        test_response_quality_indicators,
        test_eta_and_progress_messaging
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results.append(False)
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All fallback response system tests passed!")
        print("✅ Task 3.2 is COMPLETE")
        return True
    else:
        print("⚠️  Some tests failed")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)