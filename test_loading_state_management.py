#!/usr/bin/env python3
"""
Test script to verify loading state management implementation.
This validates Task 3.1 completion.
"""

import asyncio
import sys
import os
import json

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

async def test_capability_service():
    """Test the capability service functionality."""
    print("🧪 Testing Capability Service...")
    
    try:
        from multimodal_librarian.services.capability_service import (
            get_capability_service, CapabilityLevel, CapabilityInfo
        )
        
        service = get_capability_service()
        print("✅ Capability service initialized")
        
        # Test getting current capabilities
        capabilities = service.get_current_capabilities()
        print(f"✅ Retrieved {len(capabilities)} capabilities")
        
        # Test capability summary
        summary = service.get_capability_summary()
        print(f"✅ Capability summary: {summary['overall']['readiness_percent']:.1f}% ready")
        
        # Test loading progress
        progress = service.get_loading_progress()
        print(f"✅ Loading progress: {progress['overall_progress']:.1f}%")
        
        # Test request handling capability
        can_handle = service.can_handle_request("chat", ["basic_chat"])
        print(f"✅ Can handle chat request: {can_handle['can_handle']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Capability service test failed: {e}")
        return False

async def test_loading_middleware():
    """Test the loading middleware functionality."""
    print("\n🧪 Testing Loading Middleware...")
    
    try:
        from multimodal_librarian.api.middleware.loading_middleware import (
            LoadingStateMiddleware, LoadingStateInjector, get_loading_state_injector
        )
        
        # Test loading state injector
        injector = get_loading_state_injector()
        print("✅ Loading state injector initialized")
        
        # Test injecting loading state into response
        test_response = {"message": "Hello, world!"}
        enhanced_response = injector.inject_loading_state(
            test_response, 
            request_type="chat",
            required_capabilities=["basic_chat"]
        )
        
        # Verify loading state was added
        assert "loading_state" in enhanced_response
        assert "response_quality" in enhanced_response
        print("✅ Loading state injection working")
        
        # Test middleware initialization
        from fastapi import FastAPI
        app = FastAPI()
        middleware = LoadingStateMiddleware(app)
        print("✅ Loading middleware initialized")
        
        return True
        
    except Exception as e:
        print(f"❌ Loading middleware test failed: {e}")
        return False

async def test_capability_levels():
    """Test capability level definitions and logic."""
    print("\n🧪 Testing Capability Levels...")
    
    try:
        from multimodal_librarian.services.capability_service import CapabilityLevel, CapabilityInfo
        
        # Test capability levels
        levels = [CapabilityLevel.BASIC, CapabilityLevel.ENHANCED, CapabilityLevel.FULL]
        print(f"✅ Capability levels defined: {[level.value for level in levels]}")
        
        # Test capability info creation
        test_capability = CapabilityInfo(
            name="test_capability",
            available=True,
            level=CapabilityLevel.ENHANCED,
            description="Test capability for validation"
        )
        
        assert test_capability.quality_indicator == "🔄"
        print("✅ Capability info creation working")
        
        return True
        
    except Exception as e:
        print(f"❌ Capability levels test failed: {e}")
        return False

async def test_progress_tracking():
    """Test progress tracking functionality."""
    print("\n🧪 Testing Progress Tracking...")
    
    try:
        from multimodal_librarian.services.capability_service import get_capability_service
        
        service = get_capability_service()
        
        # Test progress calculation
        progress = service.get_loading_progress()
        
        # Verify progress structure
        assert "phase_progress" in progress
        assert "model_progress" in progress
        assert "overall_progress" in progress
        print("✅ Progress tracking structure correct")
        
        # Verify progress values are reasonable
        overall_progress = progress["overall_progress"]
        assert 0 <= overall_progress <= 100
        print(f"✅ Overall progress: {overall_progress:.1f}%")
        
        return True
        
    except Exception as e:
        print(f"❌ Progress tracking test failed: {e}")
        return False

async def test_request_capability_mapping():
    """Test request to capability mapping."""
    print("\n🧪 Testing Request Capability Mapping...")
    
    try:
        from multimodal_librarian.api.middleware.loading_middleware import LoadingStateMiddleware
        from fastapi import FastAPI
        
        app = FastAPI()
        middleware = LoadingStateMiddleware(app)
        
        # Test capability mapping for different request types
        test_cases = [
            ("/api/health", []),
            ("/api/chat/simple", ["simple_text"]),
            ("/api/chat", ["advanced_chat"]),
            ("/api/search", ["semantic_search"]),
            ("/unknown/endpoint", ["basic_chat"])  # default
        ]
        
        for path, expected_capabilities in test_cases:
            # Create mock request
            class MockRequest:
                def __init__(self, path):
                    self.url = type('MockURL', (), {'path': path})()
            
            request = MockRequest(path)
            capabilities = middleware._get_required_capabilities(request)
            
            assert capabilities == expected_capabilities, f"Path {path}: expected {expected_capabilities}, got {capabilities}"
            print(f"✅ {path} -> {capabilities}")
        
        return True
        
    except Exception as e:
        print(f"❌ Request capability mapping test failed: {e}")
        return False

async def main():
    """Run all tests."""
    print("🚀 Testing Loading State Management Implementation")
    print("=" * 60)
    
    tests = [
        test_capability_service,
        test_loading_middleware,
        test_capability_levels,
        test_progress_tracking,
        test_request_capability_mapping
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
        print("🎉 All loading state management tests passed!")
        print("✅ Task 3.1 is COMPLETE")
        return True
    else:
        print("⚠️  Some tests failed")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)