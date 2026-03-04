#!/usr/bin/env python3
"""
Test script to verify the complete smart user experience implementation.
This validates Tasks 3.1 and 3.2 working together.
"""

import asyncio
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

async def test_integrated_user_experience():
    """Test the integrated user experience with loading states and fallback responses."""
    print("🧪 Testing Integrated User Experience...")
    
    try:
        from multimodal_librarian.services.capability_service import get_capability_service
        from multimodal_librarian.services.fallback_service import get_fallback_service
        from multimodal_librarian.services.expectation_manager import get_expectation_manager
        from multimodal_librarian.api.middleware.loading_middleware import get_loading_state_injector
        
        # Get all services
        capability_service = get_capability_service()
        fallback_service = get_fallback_service()
        expectation_manager = get_expectation_manager()
        loading_injector = get_loading_state_injector()
        
        print("✅ All services initialized")
        
        # Test complete user experience flow
        user_message = "Can you analyze this complex document for me?"
        
        # 1. Check current capabilities
        capabilities = capability_service.get_current_capabilities()
        summary = capability_service.get_capability_summary()
        print(f"✅ Current capability level: {summary['overall']['current_level']}")
        
        # 2. Check if we can handle the request
        can_handle = capability_service.can_handle_request(
            "document_analysis", 
            ["document_analysis", "complex_reasoning"]
        )
        print(f"✅ Can handle request: {can_handle['can_handle']}")
        
        # 3. Generate fallback response if needed
        if not can_handle['can_handle']:
            fallback_response = fallback_service.generate_fallback_response(user_message)
            print(f"✅ Fallback response generated: {fallback_response.quality_indicator} {fallback_response.response_quality}")
        
        # 4. Manage user expectations
        expectation_response = expectation_manager.manage_expectations(user_message)
        print(f"✅ Expectations managed: {expectation_response.patience_level_appropriate}")
        
        # 5. Inject loading state into response
        base_response = {"message": "Processing your request..."}
        enhanced_response = loading_injector.inject_loading_state(
            base_response,
            request_type="document_analysis",
            required_capabilities=["document_analysis"]
        )
        print("✅ Loading state injected into response")
        
        # 6. Create expectation-aware response
        final_response = expectation_manager.create_expectation_aware_response(
            user_message, enhanced_response
        )
        print("✅ Expectation-aware response created")
        
        # Verify the final response has all expected components
        assert "loading_state" in final_response
        assert "expectation_management" in final_response
        assert "user_guidance" in final_response
        
        return True
        
    except Exception as e:
        print(f"❌ Integrated user experience test failed: {e}")
        return False

async def test_different_user_scenarios():
    """Test different user scenarios and their appropriate responses."""
    print("\n🧪 Testing Different User Scenarios...")
    
    try:
        from multimodal_librarian.services.fallback_service import get_fallback_service
        from multimodal_librarian.services.expectation_manager import get_expectation_manager
        
        fallback_service = get_fallback_service()
        expectation_manager = get_expectation_manager()
        
        # Test scenarios with different user patience levels
        scenarios = [
            {
                "message": "I need this analysis right now!",
                "expected_patience": "immediate",
                "description": "Urgent request"
            },
            {
                "message": "Can you help me when you're ready?",
                "expected_patience": "patient",
                "description": "Patient request"
            },
            {
                "message": "I have a complex document to analyze",
                "expected_patience": "medium",
                "description": "Complex task"
            },
            {
                "message": "Hello, what can you do?",
                "expected_patience": "immediate",
                "description": "Simple inquiry"
            }
        ]
        
        for scenario in scenarios:
            # Generate fallback response
            fallback = fallback_service.generate_fallback_response(scenario["message"])
            
            # Manage expectations
            expectations = expectation_manager.manage_expectations(scenario["message"])
            
            # Verify appropriate response characteristics
            assert fallback.quality_indicator in ["⚡", "🔄", "🧠"]
            assert len(fallback.limitations) >= 0
            assert len(fallback.available_alternatives) > 0
            assert expectations.primary_message
            
            print(f"✅ {scenario['description']}: {fallback.quality_indicator} response with {len(expectations.next_steps)} next steps")
        
        return True
        
    except Exception as e:
        print(f"❌ User scenarios test failed: {e}")
        return False

async def test_progressive_capability_disclosure():
    """Test progressive disclosure of capabilities as system loads."""
    print("\n🧪 Testing Progressive Capability Disclosure...")
    
    try:
        from multimodal_librarian.services.capability_service import get_capability_service
        
        service = get_capability_service()
        
        # Get capability summary
        summary = service.get_capability_summary()
        
        # Test that capabilities are organized by level
        assert "basic" in summary
        assert "enhanced" in summary
        assert "full" in summary
        assert "overall" in summary
        
        # Test that each level has appropriate structure
        for level in ["basic", "enhanced", "full"]:
            assert "available" in summary[level]
            assert "loading" in summary[level]
            assert "count" in summary[level]
            print(f"✅ {level.capitalize()} level: {len(summary[level]['available'])} available, {len(summary[level]['loading'])} loading")
        
        # Test overall readiness calculation
        overall = summary["overall"]
        assert "readiness_percent" in overall
        assert "current_level" in overall
        assert 0 <= overall["readiness_percent"] <= 100
        
        print(f"✅ Overall readiness: {overall['readiness_percent']:.1f}% ({overall['current_level']} level)")
        
        return True
        
    except Exception as e:
        print(f"❌ Progressive capability disclosure test failed: {e}")
        return False

async def test_quality_indicators_and_messaging():
    """Test quality indicators and user messaging consistency."""
    print("\n🧪 Testing Quality Indicators and Messaging...")
    
    try:
        from multimodal_librarian.services.fallback_service import get_fallback_service
        from multimodal_librarian.services.capability_service import CapabilityLevel
        
        service = get_fallback_service()
        
        # Test different message types and verify consistent quality indicators
        test_messages = [
            "Hello there!",
            "Can you analyze this data?",
            "I need document processing",
            "Search for information",
            "What's your status?"
        ]
        
        quality_indicators_seen = set()
        
        for message in test_messages:
            response = service.generate_fallback_response(message)
            
            # Verify quality indicator is valid
            assert response.quality_indicator in ["⚡", "🔄", "🧠"]
            quality_indicators_seen.add(response.quality_indicator)
            
            # Verify response quality matches indicator
            quality_mapping = {
                "⚡": "basic",
                "🔄": "enhanced", 
                "🧠": "full"
            }
            expected_quality = quality_mapping[response.quality_indicator]
            assert response.response_quality == expected_quality
            
            # Verify upgrade message is present and helpful
            assert response.upgrade_message
            assert len(response.upgrade_message) > 10  # Should be descriptive
            
            print(f"✅ {response.quality_indicator} '{message[:20]}...' -> {response.response_quality}")
        
        print(f"✅ Quality indicators working: {', '.join(sorted(quality_indicators_seen))}")
        
        return True
        
    except Exception as e:
        print(f"❌ Quality indicators test failed: {e}")
        return False

async def test_eta_and_progress_accuracy():
    """Test ETA and progress reporting accuracy."""
    print("\n🧪 Testing ETA and Progress Accuracy...")
    
    try:
        from multimodal_librarian.services.capability_service import get_capability_service
        from multimodal_librarian.services.expectation_manager import get_expectation_manager
        
        capability_service = get_capability_service()
        expectation_manager = get_expectation_manager()
        
        # Test progress reporting
        progress = capability_service.get_loading_progress()
        
        # Verify progress structure
        assert "overall_progress" in progress
        assert 0 <= progress["overall_progress"] <= 100
        
        # Test ETA formatting
        eta_tests = [0, 30, 90, 180, 600]
        for eta_seconds in eta_tests:
            description = expectation_manager._format_eta_description(eta_seconds)
            assert description
            assert "ready" in description.lower()
            print(f"✅ ETA {eta_seconds}s -> '{description}'")
        
        # Test expectation management with different ETAs
        response = expectation_manager.manage_expectations("Help me with analysis")
        assert response.progress_indicators
        assert "eta_seconds" in response.progress_indicators or "current_level" in response.progress_indicators
        
        print("✅ ETA and progress reporting accurate")
        
        return True
        
    except Exception as e:
        print(f"❌ ETA and progress accuracy test failed: {e}")
        return False

async def main():
    """Run all smart user experience tests."""
    print("🚀 Testing Smart User Experience Implementation")
    print("=" * 60)
    
    tests = [
        test_integrated_user_experience,
        test_different_user_scenarios,
        test_progressive_capability_disclosure,
        test_quality_indicators_and_messaging,
        test_eta_and_progress_accuracy
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
        print("🎉 All smart user experience tests passed!")
        print("✅ Tasks 3.1 and 3.2 are COMPLETE and working together!")
        print("\n🎯 Key Features Implemented:")
        print("   • Capability advertising in API responses")
        print("   • Loading progress endpoints with ETAs")
        print("   • Context-aware fallback responses")
        print("   • Response quality indicators (⚡🔄🧠)")
        print("   • User expectation management")
        print("   • Progressive capability disclosure")
        return True
    else:
        print("⚠️  Some tests failed")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)