#!/usr/bin/env python3
"""
Simple test script for Full ML Configuration deployment
Tests basic connectivity and functionality
"""

import requests
import sys
import time

def test_basic_connectivity(url: str) -> bool:
    """Test basic connectivity to the service"""
    try:
        response = requests.get(f"{url}/health/simple", timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Connection failed: {e}")
        return False

def main():
    if len(sys.argv) != 2:
        print("Usage: python test-full-ml-deployment-simple.py <public_ip>")
        print("Example: python test-full-ml-deployment-simple.py 98.92.215.174")
        sys.exit(1)
    
    public_ip = sys.argv[1]
    base_url = f"http://{public_ip}:8000"
    
    print(f"🧪 Testing Full ML Configuration at: {base_url}")
    print("=" * 60)
    
    # Test basic connectivity
    print("Testing basic connectivity...", end=" ")
    if test_basic_connectivity(base_url):
        print("✅ Connected successfully!")
        
        # Test additional endpoints
        endpoints = ["/", "/features", "/docs"]
        for endpoint in endpoints:
            try:
                response = requests.get(f"{base_url}{endpoint}", timeout=10)
                print(f"  {endpoint}: ✅ {response.status_code}")
            except Exception as e:
                print(f"  {endpoint}: ❌ {e}")
        
        print("\n🎉 Full ML deployment is accessible!")
        print(f"🌐 Share this URL: {base_url}")
        return 0
    else:
        print("❌ Connection failed")
        print("\n🔍 Troubleshooting steps:")
        print("1. Check if the ECS task is running")
        print("2. Verify security group allows port 8000")
        print("3. Check CloudWatch logs for errors")
        print("4. Ensure the container started successfully")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)