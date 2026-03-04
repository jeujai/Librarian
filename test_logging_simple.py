#!/usr/bin/env python3
"""
Simple test for comprehensive logging implementation.
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8001"

def test_logging_health():
    """Test logging service health."""
    try:
        response = requests.get(f"{BASE_URL}/api/logging/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print("✅ Logging Health:", data.get("status"))
            return True
        else:
            print("❌ Logging Health Failed:", response.status_code)
            return False
    except Exception as e:
        print("❌ Logging Health Error:", str(e))
        return False

def test_structured_logging():
    """Test structured logging."""
    try:
        response = requests.post(
            f"{BASE_URL}/api/logging/log",
            params={
                "level": "INFO",
                "service": "test",
                "operation": "simple_test",
                "message": "Test message"
            },
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            print("✅ Structured Logging:", data.get("success"))
            return True
        else:
            print("❌ Structured Logging Failed:", response.status_code)
            return False
    except Exception as e:
        print("❌ Structured Logging Error:", str(e))
        return False

def test_middleware():
    """Test middleware integration."""
    try:
        response = requests.get(f"{BASE_URL}/features", timeout=5)
        if response.status_code == 200:
            correlation_id = response.headers.get("X-Correlation-ID")
            trace_id = response.headers.get("X-Trace-ID")
            print("✅ Middleware Integration:", correlation_id is not None and trace_id is not None)
            return correlation_id is not None and trace_id is not None
        else:
            print("❌ Middleware Failed:", response.status_code)
            return False
    except Exception as e:
        print("❌ Middleware Error:", str(e))
        return False

def main():
    print("🚀 Simple Comprehensive Logging Test")
    print("=" * 50)
    
    results = []
    results.append(test_logging_health())
    results.append(test_structured_logging())
    results.append(test_middleware())
    
    passed = sum(results)
    total = len(results)
    
    print("=" * 50)
    print(f"Results: {passed}/{total} passed ({passed/total*100:.1f}%)")
    
    if passed == total:
        print("🎉 All tests passed! Comprehensive logging is working!")
    elif passed >= total * 0.7:
        print("✅ Most tests passed! Comprehensive logging is mostly working!")
    else:
        print("❌ Some tests failed. Check the implementation.")

if __name__ == "__main__":
    main()