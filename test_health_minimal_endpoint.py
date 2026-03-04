#!/usr/bin/env python3
"""
Test script for the /health/minimal endpoint implementation.

This script tests the minimal health check endpoint to ensure it's working correctly
and returns the expected response format for ECS health checks.
"""

import asyncio
import sys
import os
import json
from datetime import datetime

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

async def test_minimal_health_endpoint():
    """Test the minimal health endpoint functionality."""
    print("Testing /health/minimal endpoint implementation...")
    
    try:
        # Import the health router
        from multimodal_librarian.api.routers.health import router, minimal_health_check
        from multimodal_librarian.startup.minimal_server import get_minimal_server, initialize_minimal_server
        
        print("✓ Successfully imported health router and minimal server")
        
        # Initialize the minimal server
        print("Initializing minimal server...")
        server = await initialize_minimal_server()
        print("✓ Minimal server initialized successfully")
        
        # Test the minimal health check function directly
        print("Testing minimal health check function...")
        response = await minimal_health_check()
        
        print("✓ Minimal health check executed successfully")
        print(f"Response type: {type(response)}")
        
        # Extract response content
        if hasattr(response, 'body'):
            # JSONResponse object
            content = json.loads(response.body.decode())
        elif isinstance(response, dict):
            # Direct dictionary response
            content = response
        else:
            content = response
        
        print(f"Response content: {json.dumps(content, indent=2)}")
        
        # Validate response structure
        required_fields = ['status', 'server_status', 'uptime_seconds', 'ready', 'timestamp']
        missing_fields = [field for field in required_fields if field not in content]
        
        if missing_fields:
            print(f"❌ Missing required fields: {missing_fields}")
            return False
        
        print("✓ All required fields present in response")
        
        # Validate response values
        if content['status'] not in ['healthy', 'starting', 'error']:
            print(f"❌ Invalid status value: {content['status']}")
            return False
        
        if not isinstance(content['uptime_seconds'], (int, float)):
            print(f"❌ Invalid uptime_seconds type: {type(content['uptime_seconds'])}")
            return False
        
        if not isinstance(content['ready'], bool):
            print(f"❌ Invalid ready type: {type(content['ready'])}")
            return False
        
        print("✓ Response values are valid")
        
        # Test server status
        server_status = server.get_status()
        print(f"Server status: {server_status.status.value}")
        print(f"Health check ready: {server_status.health_check_ready}")
        print(f"Uptime: {server_status.uptime_seconds:.2f} seconds")
        print(f"Capabilities: {list(server_status.capabilities.keys())}")
        
        print("✓ Minimal health endpoint test completed successfully")
        return True
        
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_health_endpoint_integration():
    """Test the health endpoint integration with FastAPI."""
    print("\nTesting FastAPI integration...")
    
    try:
        from fastapi.testclient import TestClient
        from multimodal_librarian.main import create_minimal_app
        
        # Create the FastAPI app
        app = create_minimal_app()
        client = TestClient(app)
        
        print("✓ FastAPI app created successfully")
        
        # Test the /api/health/minimal endpoint
        response = client.get("/api/health/minimal")
        
        print(f"HTTP Status Code: {response.status_code}")
        print(f"Response Headers: {dict(response.headers)}")
        
        if response.status_code in [200, 503]:  # Both are valid for health checks
            content = response.json()
            print(f"Response Content: {json.dumps(content, indent=2)}")
            print("✓ Health endpoint integration test passed")
            return True
        else:
            print(f"❌ Unexpected status code: {response.status_code}")
            print(f"Response text: {response.text}")
            return False
            
    except ImportError as e:
        print(f"❌ Import error for integration test: {e}")
        return False
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Run all health endpoint tests."""
    print("=" * 60)
    print("MINIMAL HEALTH ENDPOINT TEST SUITE")
    print("=" * 60)
    
    # Test 1: Direct function test
    test1_passed = await test_minimal_health_endpoint()
    
    # Test 2: FastAPI integration test
    test2_passed = await test_health_endpoint_integration()
    
    print("\n" + "=" * 60)
    print("TEST RESULTS SUMMARY")
    print("=" * 60)
    print(f"Direct function test: {'✓ PASSED' if test1_passed else '❌ FAILED'}")
    print(f"FastAPI integration test: {'✓ PASSED' if test2_passed else '❌ FAILED'}")
    
    if test1_passed and test2_passed:
        print("\n🎉 ALL TESTS PASSED - /health/minimal endpoint is working correctly!")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED - Check the output above for details")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)