#!/usr/bin/env python3
"""
Test script for AWS deployment validation
Tests key endpoints and functionality of the deployed application
"""

import requests
import json
import time
import sys
from urllib.parse import urljoin

# Configuration
BASE_URL = "http://multimodal-librarian-learning-659419827.us-east-1.elb.amazonaws.com"
TIMEOUT = 10

def test_endpoint(endpoint, expected_status=200, method='GET', data=None):
    """Test a single endpoint"""
    url = urljoin(BASE_URL, endpoint)
    try:
        if method == 'GET':
            response = requests.get(url, timeout=TIMEOUT)
        elif method == 'POST':
            response = requests.post(url, json=data, timeout=TIMEOUT)
        
        print(f"✓ {method} {endpoint}: {response.status_code}")
        
        if response.status_code == expected_status:
            return True, response
        else:
            print(f"  Expected {expected_status}, got {response.status_code}")
            return False, response
            
    except Exception as e:
        print(f"✗ {method} {endpoint}: ERROR - {str(e)}")
        return False, None

def main():
    """Run all tests"""
    print("🚀 Testing AWS Deployment...")
    print(f"Base URL: {BASE_URL}")
    print("-" * 50)
    
    tests_passed = 0
    tests_total = 0
    
    # Test 1: Health check
    tests_total += 1
    success, response = test_endpoint("/health")
    if success:
        tests_passed += 1
        
    # Test 2: Simple health check
    tests_total += 1
    success, response = test_endpoint("/health/simple")
    if success:
        tests_passed += 1
    
    # Test 3: Root endpoint
    tests_total += 1
    success, response = test_endpoint("/")
    if success:
        tests_passed += 1
        try:
            data = response.json()
            print(f"  Version: {data.get('version', 'unknown')}")
            print(f"  Status: {data.get('status', 'unknown')}")
            print(f"  Features: {len(data.get('features', {}))}")
        except:
            pass
    
    # Test 4: API docs
    tests_total += 1
    success, response = test_endpoint("/docs")
    if success:
        tests_passed += 1
    
    # Test 5: Chat interface
    tests_total += 1
    success, response = test_endpoint("/chat")
    if success:
        tests_passed += 1
        if "Multimodal Librarian" in response.text:
            print("  Chat interface HTML loaded correctly")
    
    # Test 6: Features endpoint
    tests_total += 1
    success, response = test_endpoint("/features")
    if success:
        tests_passed += 1
        try:
            data = response.json()
            print(f"  Available features: {list(data.keys())}")
        except:
            pass
    
    # Test 7: Database test endpoint
    tests_total += 1
    success, response = test_endpoint("/test/database")
    if success:
        tests_passed += 1
        try:
            data = response.json()
            print(f"  Database status: {data.get('status', 'unknown')}")
        except:
            pass
    
    # Test 8: Redis test endpoint
    tests_total += 1
    success, response = test_endpoint("/test/redis")
    if success:
        tests_passed += 1
        try:
            data = response.json()
            print(f"  Redis status: {data.get('status', 'unknown')}")
        except:
            pass
    
    # Test 9: Config test endpoint
    tests_total += 1
    success, response = test_endpoint("/test/config")
    if success:
        tests_passed += 1
        try:
            data = response.json()
            print(f"  Config status: {data.get('status', 'unknown')}")
        except:
            pass
    
    print("-" * 50)
    print(f"📊 Test Results: {tests_passed}/{tests_total} tests passed")
    
    if tests_passed == tests_total:
        print("🎉 All tests passed! Deployment is working correctly.")
        return 0
    else:
        print("⚠️  Some tests failed. Check the deployment.")
        return 1

if __name__ == "__main__":
    sys.exit(main())