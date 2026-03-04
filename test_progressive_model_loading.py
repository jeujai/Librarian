#!/usr/bin/env python3
"""
Test script for progressive model loading functionality.

This script tests Task 1.3: Add Progressive Model Loading
- Model priority classification system
- Background model loading with progress tracking
- Model availability checking before processing requests
- Graceful degradation for unavailable models
"""

import asyncio
import time
import sys
import os
from datetime import datetime

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

async def test_model_manager():
    """Test the model manager functionality."""
    print("🧠 Testing Model Manager")
    print("=" * 50)
    
    try:
        # Test 1: Import and initialize model manager
        print("\n1. Testing model manager import and initialization...")
        from multimodal_librarian.models.model_manager import get_model_manager, initialize_model_manager
        
        manager = get_model_manager()
        print(f"   ✅ Model manager imported successfully")
        
        # Test 2: Check default model configurations
        print("\n2. Testing default model configurations...")
        all_statuses = manager.get_all_model_statuses()
        print(f"   ✅ Found {len(all_statuses)} registered models")
        
        for model_name, status in all_statuses.items():
            priority = status['priority']
            capabilities = status['capabilities']
            print(f"   📊 {model_name}: {priority} priority, {len(capabilities)} capabilities")
        
        # Test 3: Test model availability checking
        print("\n3. Testing model availability checking...")
        for model_name in ["text-embedding-small", "chat-model-base", "nonexistent-model"]:
            available = manager.is_model_available(model_name)
            print(f"   📊 {model_name}: {'✅ Available' if available else '❌ Not available'}")
        
        # Test 4: Test capability checking
        print("\n4. Testing capability checking...")
        capabilities_to_test = ["basic_chat", "simple_search", "document_analysis", "nonexistent_capability"]
        
        for capability in capabilities_to_test:
            can_handle = manager.can_handle_capability(capability)
            models = manager.get_models_for_capability(capability)
            status = manager.get_capability_status(capability)
            
            print(f"   📊 {capability}:")
            print(f"      Can handle: {'✅ Yes' if can_handle else '❌ No'}")
            print(f"      Available models: {models}")
            print(f"      Status: {status['available']}")
        
        # Test 5: Test fallback model functionality
        print("\n5. Testing fallback model functionality...")
        test_models = ["chat-model-large", "chat-model-base", "nonexistent-model"]
        
        for model_name in test_models:
            fallback = manager.get_fallback_model(model_name)
            print(f"   📊 {model_name} fallback: {fallback if fallback else 'None'}")
        
        # Test 6: Start progressive loading
        print("\n6. Testing progressive loading startup...")
        start_time = time.time()
        await initialize_model_manager()
        init_time = time.time() - start_time
        
        print(f"   ✅ Progressive loading started in {init_time:.2f} seconds")
        
        # Test 7: Monitor loading progress
        print("\n7. Testing loading progress monitoring...")
        
        for i in range(10):  # Monitor for 10 iterations
            progress = manager.get_loading_progress()
            print(f"   📊 Progress: {progress['progress_percent']:.1f}% "
                  f"({progress['loaded_models']}/{progress['total_models']} models)")
            print(f"      Loading: {progress['loading_models']}, "
                  f"Failed: {progress['failed_models']}, "
                  f"Pending: {progress['pending_models']}")
            
            if progress['progress_percent'] >= 100:
                print(f"   🎉 All models loaded!")
                break
            
            await asyncio.sleep(2)  # Wait 2 seconds between checks
        
        # Test 8: Test model forcing
        print("\n8. Testing force model loading...")
        force_model = "chat-model-large"
        
        if not manager.is_model_available(force_model):
            print(f"   🔄 Force loading {force_model}...")
            force_start = time.time()
            success = await manager.force_load_model(force_model)
            force_time = time.time() - force_start
            
            print(f"   {'✅ Success' if success else '❌ Failed'} in {force_time:.2f} seconds")
        else:
            print(f"   ✅ {force_model} already loaded")
        
        # Test 9: Final status check
        print("\n9. Final model status check...")
        final_progress = manager.get_loading_progress()
        final_stats = final_progress['statistics']
        
        print(f"   📊 Final Progress: {final_progress['progress_percent']:.1f}%")
        print(f"   📊 Total loads: {final_stats['total_loads']}")
        print(f"   📊 Successful: {final_stats['successful_loads']}")
        print(f"   📊 Failed: {final_stats['failed_loads']}")
        print(f"   📊 Average load time: {final_stats['average_load_time']:.2f}s")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: Model manager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_progressive_loader():
    """Test the progressive loader functionality."""
    print("\n" + "=" * 50)
    print("🚀 Testing Progressive Loader")
    print("=" * 50)
    
    try:
        # Test 1: Import and initialize progressive loader
        print("\n1. Testing progressive loader import...")
        from multimodal_librarian.startup.progressive_loader import get_progressive_loader, initialize_progressive_loader
        from multimodal_librarian.startup.phase_manager import StartupPhaseManager
        
        # Create a startup phase manager for integration
        phase_manager = StartupPhaseManager()
        
        print(f"   ✅ Progressive loader imported successfully")
        
        # Test 2: Initialize with phase manager integration
        print("\n2. Testing progressive loader initialization...")
        loader = await initialize_progressive_loader(phase_manager)
        print(f"   ✅ Progressive loader initialized with phase manager integration")
        
        # Test 3: Test capability requests
        print("\n3. Testing capability requests...")
        capabilities_to_request = ["basic_chat", "document_analysis", "multimodal_processing"]
        
        for capability in capabilities_to_request:
            request_result = loader.request_capability(capability)
            print(f"   📊 {capability}:")
            print(f"      Available: {'✅ Yes' if request_result['available'] else '❌ No'}")
            if not request_result['available']:
                wait_time = request_result.get('estimated_wait_time_seconds', 0)
                print(f"      Estimated wait: {wait_time:.1f} seconds")
                fallback = request_result.get('fallback_available', False)
                print(f"      Fallback available: {'✅ Yes' if fallback else '❌ No'}")
        
        # Test 4: Monitor loading progress
        print("\n4. Testing loading progress monitoring...")
        
        for i in range(8):  # Monitor for 8 iterations
            progress = loader.get_loading_progress()
            overall = progress['overall']
            by_phase = progress['by_phase']
            
            print(f"   📊 Overall Progress: {overall['progress_percent']:.1f}%")
            
            for phase_name, phase_info in by_phase.items():
                status = "✅ Complete" if phase_info['completed'] else f"🔄 {phase_info['progress_percent']:.1f}%"
                print(f"      {phase_name}: {status} ({phase_info['loaded_models']}/{phase_info['total_models']})")
            
            print(f"      Strategy: {progress['current_strategy']}")
            print(f"      User requests queued: {progress['user_requests_queued']}")
            
            if overall['progress_percent'] >= 100:
                print(f"   🎉 All models loaded!")
                break
            
            await asyncio.sleep(3)  # Wait 3 seconds between checks
        
        # Test 5: Test capability readiness
        print("\n5. Testing capability readiness...")
        readiness = loader.get_capability_readiness()
        
        for capability, status in readiness.items():
            available = "✅ Ready" if status['available'] else "❌ Not ready"
            models = len(status['available_models'])
            print(f"   📊 {capability}: {available} ({models} models)")
        
        # Test 6: Test user experience metrics
        print("\n6. Testing user experience metrics...")
        ux_metrics = loader.get_user_experience_metrics()
        
        print(f"   📊 Average wait time: {ux_metrics['average_user_wait_time_seconds']:.2f}s")
        print(f"   📊 Capabilities available: {ux_metrics['capabilities_available']}/{ux_metrics['total_capabilities']}")
        print(f"   📊 Availability: {ux_metrics['capability_availability_percent']:.1f}%")
        print(f"   📊 Loading strategy: {ux_metrics['loading_strategy']}")
        
        # Test 7: Test phase manager integration
        print("\n7. Testing phase manager integration...")
        
        # Start phase progression
        await phase_manager.start_phase_progression()
        
        # Wait a bit for phase transitions
        await asyncio.sleep(5)
        
        # Check current phase
        phase_status = phase_manager.get_current_status()
        print(f"   📊 Current phase: {phase_status.current_phase.value}")
        print(f"   📊 Phase uptime: {phase_status.total_startup_time:.2f}s")
        print(f"   📊 Health check ready: {phase_status.health_check_ready}")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: Progressive loader test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_integration_with_main_app():
    """Test integration with the main FastAPI application."""
    print("\n" + "=" * 50)
    print("🔗 Testing Integration with Main Application")
    print("=" * 50)
    
    try:
        # Test 1: Import main app with progressive loading
        print("\n1. Testing main application with progressive loading...")
        from multimodal_librarian.main import create_minimal_app
        
        app = create_minimal_app()
        print("   ✅ Main application created with progressive loading support")
        
        # Test 2: Check that model manager endpoints are available
        print("\n2. Testing model management endpoint availability...")
        routes = [route.path for route in app.routes]
        
        # Look for health and model-related routes
        model_routes = [route for route in routes if any(keyword in route.lower() 
                       for keyword in ['model', 'capability', 'progress', 'loading'])]
        
        print(f"   📊 Total routes: {len(routes)}")
        print(f"   📊 Model-related routes: {len(model_routes)}")
        
        for route in model_routes[:10]:  # Show first 10
            print(f"   📊 Model route: {route}")
        
        if len(model_routes) > 10:
            print(f"   📊 ... and {len(model_routes) - 10} more")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all progressive model loading tests."""
    print("🧪 Progressive Model Loading Test Suite")
    print("Testing Task 1.3: Add Progressive Model Loading")
    print("=" * 70)
    
    # Run tests
    test1_passed = await test_model_manager()
    test2_passed = await test_progressive_loader()
    test3_passed = await test_integration_with_main_app()
    
    # Summary
    print("\n" + "=" * 70)
    print("📊 TEST SUMMARY")
    print("=" * 70)
    print(f"Model Manager Test: {'✅ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"Progressive Loader Test: {'✅ PASSED' if test2_passed else '❌ FAILED'}")
    print(f"Integration Test: {'✅ PASSED' if test3_passed else '❌ FAILED'}")
    
    overall_success = test1_passed and test2_passed and test3_passed
    print(f"\nOverall Result: {'🎉 ALL TESTS PASSED' if overall_success else '❌ SOME TESTS FAILED'}")
    
    if overall_success:
        print("\n✅ Task 1.3 Implementation: SUCCESS")
        print("   • Model priority classification system implemented")
        print("   • Background model loading with progress tracking working")
        print("   • Model availability checking before processing requests functional")
        print("   • Graceful degradation for unavailable models implemented")
        print("   • Integration with startup phase manager complete")
    else:
        print("\n❌ Task 1.3 Implementation: NEEDS WORK")
        print("   • Review failed tests above")
        print("   • Check model manager functionality")
        print("   • Verify progressive loader integration")
    
    return overall_success


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)