#!/usr/bin/env python3
"""
Test script to verify all health endpoints are implemented and working.
This validates Task 2.2 completion.
"""

import asyncio
import sys
import os

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

async def test_health_endpoints():
    """Test all health endpoints to verify they're implemented."""
    try:
        from multimodal_librarian.api.routers.health import (
            minimal_health_check,
            readiness_health_check,
            full_health_check,
            startup_health_check,
            model_status_check,
            capabilities_check,
            queue_status_check,
            performance_health_check,
            simple_health_check,
            comprehensive_health_check
        )
        
        print("✅ All health endpoints imported successfully")
        
        # Test each endpoint
        endpoints = [
            ("minimal", minimal_health_check),
            ("ready", readiness_health_check),
            ("full", full_health_check),
            ("startup", startup_health_check),
            ("models", model_status_check),
            ("capabilities", capabilities_check),
            ("queue", queue_status_check),
            ("performance", performance_health_check),
            ("simple", simple_health_check),
            ("comprehensive", comprehensive_health_check)
        ]
        
        results = {}
        for name, endpoint_func in endpoints:
            try:
                result = await endpoint_func()
                results[name] = "✅ Working"
                print(f"✅ /{name} endpoint: Working")
            except Exception as e:
                results[name] = f"❌ Error: {str(e)}"
                print(f"❌ /{name} endpoint: Error - {str(e)}")
        
        # Summary
        working_count = sum(1 for status in results.values() if status == "✅ Working")
        total_count = len(results)
        
        print(f"\n📊 Summary: {working_count}/{total_count} endpoints working")
        
        if working_count == total_count:
            print("🎉 All health endpoints are implemented and functional!")
            print("✅ Task 2.2 is COMPLETE")
            return True
        else:
            print("⚠️  Some endpoints have issues")
            return False
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_health_endpoints())
    sys.exit(0 if success else 1)