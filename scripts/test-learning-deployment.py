#!/usr/bin/env python3
"""
Test script for the learning deployment.
Verifies that all features are working correctly.
"""

import requests
import json
import time
import sys
from typing import Dict, Any

# Configuration
BASE_URL = "http://multimodal-librarian-learning-659419827.us-east-1.elb.amazonaws.com"

def test_endpoint(url: str, expected_status: int = 200, description: str = "") -> Dict[str, Any]:
    """Test a single endpoint."""
    try:
        print(f"Testing: {description or url}")
        response = requests.get(url, timeout=10)
        
        result = {
            "url": url,
            "status_code": response.status_code,
            "success": response.status_code == expected_status,
            "description": description
        }
        
        if response.status_code == expected_status:
            try:
                result["data"] = response.json()
            except:
                result["data"] = response.text[:200]
            print(f"  ✅ SUCCESS: {response.status_code}")
        else:
            print(f"  ❌ FAILED: {response.status_code} (expected {expected_status})")
            result["error"] = response.text[:200]
        
        return result
        
    except requests.exceptions.RequestException as e:
        print(f"  ❌ ERROR: {str(e)}")
        return {
            "url": url,
            "success": False,
            "error": str(e),
            "description": description
        }

def main():
    """Run all tests."""
    print("🧪 Testing Multimodal Librarian Learning Deployment")
    print("=" * 60)
    
    tests = [
        (f"{BASE_URL}/", "Root endpoint"),
        (f"{BASE_URL}/health/simple", "Simple health check"),
        (f"{BASE_URL}/health", "Comprehensive health check"),
        (f"{BASE_URL}/features", "Feature availability"),
        (f"{BASE_URL}/docs", "API documentation"),
        (f"{BASE_URL}/chat", "Chat interface"),
        (f"{BASE_URL}/test/database", "Database connectivity"),
        (f"{BASE_URL}/test/redis", "Redis connectivity"),
        (f"{BASE_URL}/test/config", "Configuration test"),
    ]
    
    results = []
    
    for url, description in tests:
        result = test_endpoint(url, description=description)
        results.append(result)
        time.sleep(0.5)  # Be nice to the server
        print()
    
    # Summary
    print("📊 Test Summary")
    print("=" * 60)
    
    successful = sum(1 for r in results if r.get("success", False))
    total = len(results)
    
    print(f"Total tests: {total}")
    print(f"Successful: {successful}")
    print(f"Failed: {total - successful}")
    print(f"Success rate: {(successful/total)*100:.1f}%")
    print()
    
    # Feature analysis
    feature_result = next((r for r in results if "/features" in r["url"]), None)
    if feature_result and feature_result.get("success") and "data" in feature_result:
        features = feature_result["data"].get("features", {})
        print("🎯 Available Features:")
        for feature, available in features.items():
            status = "✅" if available else "❌"
            print(f"  {status} {feature.replace('_', ' ').title()}")
        print()
    
    # Health analysis
    health_result = next((r for r in results if "/health" in r["url"] and "/simple" not in r["url"]), None)
    if health_result and health_result.get("success") and "data" in health_result:
        health_data = health_result["data"]
        print("🏥 Health Status:")
        print(f"  Overall: {health_data.get('overall_status', 'unknown')}")
        print(f"  Uptime: {health_data.get('uptime_seconds', 0):.1f} seconds")
        
        services = health_data.get("services", {})
        for service, status in services.items():
            service_status = status.get("status", "unknown") if isinstance(status, dict) else status
            print(f"  {service}: {service_status}")
        print()
    
    # Recommendations
    print("💡 Recommendations:")
    if successful == total:
        print("  🎉 All tests passed! Your deployment is working perfectly.")
        print("  🌐 You can now access the chat interface at:")
        print(f"     {BASE_URL}/chat")
    elif successful >= total * 0.8:
        print("  ⚠️  Most tests passed, but some features may be limited.")
        print("  📋 Check the failed tests above for details.")
    else:
        print("  🚨 Many tests failed. The deployment may have issues.")
        print("  🔧 Check the application logs for errors:")
        print("     aws logs tail /aws/ecs/multimodal-librarian-learning --follow")
    
    print()
    print("🔗 Useful URLs:")
    print(f"  Chat Interface: {BASE_URL}/chat")
    print(f"  API Docs: {BASE_URL}/docs")
    print(f"  Health Check: {BASE_URL}/health")
    print(f"  Feature Status: {BASE_URL}/features")
    
    return 0 if successful == total else 1

if __name__ == "__main__":
    sys.exit(main())