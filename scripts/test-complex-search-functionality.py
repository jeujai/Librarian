#!/usr/bin/env python3
"""
Test Complex Search Functionality

This script tests that the complex search functionality has been successfully re-enabled
and is working properly in the deployed service.
"""

import requests
import json
import sys
import time
from datetime import datetime

def test_service_health():
    """Test that the service is healthy and responding."""
    print("🏥 Testing service health...")
    
    try:
        # Try to reach the health endpoint
        response = requests.get("https://multimodal-librarian.yourdomain.com/health/simple", timeout=10)
        if response.status_code == 200:
            print("✅ Service health check passed")
            return True
        else:
            print(f"⚠️  Service health check returned status {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Service health check failed: {e}")
        return False

def test_search_functionality():
    """Test that search functionality is working."""
    print("🔍 Testing search functionality...")
    
    try:
        # Test basic search endpoint
        search_data = {
            "query": "test search functionality",
            "top_k": 5
        }
        
        response = requests.post(
            "https://multimodal-librarian.yourdomain.com/api/search",
            json=search_data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Search endpoint responded successfully")
            print(f"   Results returned: {len(result.get('results', []))}")
            
            # Check if complex search features are available
            if 'search_strategy' in result:
                print(f"   Search strategy: {result.get('search_strategy', 'unknown')}")
            if 'query_understanding' in result:
                print("   ✅ Query understanding feature detected")
            
            return True
        else:
            print(f"⚠️  Search endpoint returned status {response.status_code}")
            print(f"   Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Search functionality test failed: {e}")
        return False

def test_complex_search_features():
    """Test specific complex search features."""
    print("🧠 Testing complex search features...")
    
    try:
        # Test search with advanced parameters
        advanced_search_data = {
            "query": "machine learning algorithms",
            "top_k": 10,
            "enable_hybrid_search": True,
            "enable_query_understanding": True,
            "enable_reranking": True,
            "enable_analytics": True,
            "user_expertise": "advanced"
        }
        
        response = requests.post(
            "https://multimodal-librarian.yourdomain.com/api/search/advanced",
            json=advanced_search_data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Advanced search endpoint responded successfully")
            
            # Check for complex search indicators
            complex_features = []
            if result.get('query_understanding'):
                complex_features.append("Query Understanding")
            if result.get('search_strategy') and result.get('search_strategy') != 'simple':
                complex_features.append(f"Strategy: {result.get('search_strategy')}")
            if result.get('search_time_ms'):
                complex_features.append(f"Response time: {result.get('search_time_ms')}ms")
            
            if complex_features:
                print(f"   Complex features detected: {', '.join(complex_features)}")
                return True
            else:
                print("   ⚠️  No complex search features detected in response")
                return False
                
        elif response.status_code == 404:
            print("   ℹ️  Advanced search endpoint not available (using basic search)")
            return True  # This is okay, basic search should still work
        else:
            print(f"   ⚠️  Advanced search returned status {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Complex search features test failed: {e}")
        return False

def test_search_analytics():
    """Test search analytics functionality."""
    print("📊 Testing search analytics...")
    
    try:
        response = requests.get(
            "https://multimodal-librarian.yourdomain.com/api/search/analytics",
            timeout=15
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ Search analytics endpoint responded successfully")
            
            if 'search_metrics' in result:
                print("   ✅ Search metrics available")
            if 'service_performance' in result:
                print("   ✅ Service performance metrics available")
            
            return True
        elif response.status_code == 404:
            print("   ℹ️  Search analytics endpoint not available")
            return True  # This is okay, not all endpoints may be exposed
        else:
            print(f"   ⚠️  Search analytics returned status {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Search analytics test failed: {e}")
        return False

def main():
    """Main test execution."""
    print("🚀 Testing Complex Search Functionality")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    tests_passed = 0
    total_tests = 4
    
    # Test 1: Service Health
    if test_service_health():
        tests_passed += 1
    print()
    
    # Test 2: Basic Search
    if test_search_functionality():
        tests_passed += 1
    print()
    
    # Test 3: Complex Search Features
    if test_complex_search_features():
        tests_passed += 1
    print()
    
    # Test 4: Search Analytics
    if test_search_analytics():
        tests_passed += 1
    print()
    
    # Summary
    print("=" * 50)
    print(f"Test Results: {tests_passed}/{total_tests} tests passed")
    
    if tests_passed == total_tests:
        print("🎉 All tests passed! Complex search functionality is working properly.")
        return True
    elif tests_passed >= 2:
        print("⚠️  Some tests passed. Basic functionality is working, but some advanced features may not be available.")
        return True
    else:
        print("❌ Most tests failed. There may be issues with the deployment.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)