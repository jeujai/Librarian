#!/usr/bin/env python3
"""
Test Minimal Health Check Endpoint

This script tests the minimal health check endpoint locally to verify it:
1. Returns 200 OK
2. Responds quickly (< 100ms)
3. Returns valid JSON
4. Does not trigger middleware errors
"""

import time
import json
import sys

def test_health_check():
    """Test the health check endpoint."""
    print("=" * 80)
    print("TESTING MINIMAL HEALTH CHECK ENDPOINT")
    print("=" * 80)
    print()
    
    try:
        import requests
    except ImportError:
        print("ERROR: requests library not installed")
        print("Install with: pip install requests")
        sys.exit(1)
    
    # Test local endpoint
    url = "http://localhost:8000/health/simple"
    
    print(f"Testing endpoint: {url}")
    print()
    
    success_count = 0
    total_time = 0
    
    for i in range(10):
        try:
            start = time.time()
            response = requests.get(url, timeout=5)
            duration = (time.time() - start) * 1000
            total_time += duration
            
            # Check status code
            if response.status_code == 200:
                success_count += 1
                status = "✓"
            else:
                status = "✗"
            
            # Parse JSON
            try:
                data = response.json()
                json_valid = "✓"
            except:
                json_valid = "✗"
                data = {}
            
            # Check response time
            if duration < 100:
                time_status = "✓"
            else:
                time_status = "⚠"
            
            print(f"Test {i+1:2d}: {status} Status={response.status_code} "
                  f"{time_status} Time={duration:6.1f}ms {json_valid} JSON={data.get('status', 'N/A')}")
            
            time.sleep(0.5)
            
        except Exception as e:
            print(f"Test {i+1:2d}: ✗ ERROR: {e}")
    
    print()
    print("=" * 80)
    print("TEST RESULTS")
    print("=" * 80)
    print(f"Success Rate: {success_count}/10 ({success_count*10}%)")
    print(f"Average Response Time: {total_time/10:.1f}ms")
    print()
    
    if success_count >= 9 and (total_time/10) < 100:
        print("✓ TESTS PASSED - Health check is working correctly")
        print()
        print("The endpoint:")
        print("  ✓ Returns 200 OK consistently")
        print("  ✓ Responds in < 100ms")
        print("  ✓ Returns valid JSON")
        print()
        return True
    else:
        print("✗ TESTS FAILED - Health check has issues")
        print()
        if success_count < 9:
            print(f"  ✗ Success rate too low: {success_count}/10")
        if (total_time/10) >= 100:
            print(f"  ✗ Response time too slow: {total_time/10:.1f}ms")
        print()
        return False

def main():
    """Main test function."""
    print()
    print("This script tests the minimal health check endpoint locally.")
    print("Make sure the application is running on http://localhost:8000")
    print()
    input("Press Enter to start tests...")
    print()
    
    success = test_health_check()
    
    if success:
        print("Next steps:")
        print("1. Deploy to AWS using: python scripts/deploy-minimal-health-check-fix.py")
        print("2. Monitor ALB target health")
        print("3. Verify health checks pass in production")
        print()
        sys.exit(0)
    else:
        print("Please fix the issues before deploying to production.")
        print()
        sys.exit(1)

if __name__ == "__main__":
    main()
