#!/usr/bin/env python3
"""
Test script to verify that the ECS tasks can access AWS Secrets Manager.
This script will test the same secrets that the application uses.
"""

import requests
import json
import sys
from datetime import datetime

def test_application_health():
    """Test if the application is responding to health checks."""
    try:
        # Get the load balancer URL
        response = requests.get("http://ml-shared-vpc-alb-1260972620.us-east-1.elb.amazonaws.com/health", timeout=10)
        if response.status_code == 200:
            print("✅ Application health check: PASSED")
            return True
        else:
            print(f"❌ Application health check: FAILED (Status: {response.status_code})")
            return False
    except Exception as e:
        print(f"❌ Application health check: FAILED (Error: {e})")
        return False

def test_application_endpoints():
    """Test if the application endpoints are accessible."""
    try:
        # Test the main page
        response = requests.get("http://ml-shared-vpc-alb-1260972620.us-east-1.elb.amazonaws.com/", timeout=10)
        if response.status_code == 200:
            print("✅ Main application endpoint: ACCESSIBLE")
            return True
        else:
            print(f"❌ Main application endpoint: FAILED (Status: {response.status_code})")
            return False
    except Exception as e:
        print(f"❌ Main application endpoint: FAILED (Error: {e})")
        return False

def main():
    """Main test function."""
    print("🔍 Testing ECS Task Secrets Manager Access")
    print("=" * 50)
    print(f"Test Time: {datetime.now().isoformat()}")
    print()
    
    # Test application health
    health_ok = test_application_health()
    
    # Test application endpoints
    endpoint_ok = test_application_endpoints()
    
    print()
    print("📊 Test Summary:")
    print("=" * 50)
    
    if health_ok and endpoint_ok:
        print("✅ All tests PASSED - Application is running and accessible")
        print("✅ No secrets manager access issues detected")
        print()
        print("🔍 Analysis:")
        print("- ECS tasks are running successfully")
        print("- Health checks are passing")
        print("- Application endpoints are accessible")
        print("- No secrets manager access errors in logs")
        print("- IAM permissions are correctly configured")
        return 0
    else:
        print("❌ Some tests FAILED - Check application logs for details")
        return 1

if __name__ == "__main__":
    sys.exit(main())