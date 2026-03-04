#!/usr/bin/env python3
"""
Test the /health/minimal endpoint

This script tests the /health/minimal endpoint to ensure it's working correctly
after the health check path update.
"""

import json
import requests
import subprocess
import sys
import time
from datetime import datetime

def get_alb_dns():
    """Get ALB DNS name from Terraform output."""
    try:
        result = subprocess.run(
            ["terraform", "output", "-raw", "alb_dns_name"],
            cwd="infrastructure/aws-native",
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            print(f"❌ Failed to get ALB DNS: {result.stderr}")
            return None
            
    except Exception as e:
        print(f"💥 Error getting ALB DNS: {e}")
        return None

def test_health_endpoint(url, timeout=10):
    """Test a health endpoint."""
    try:
        print(f"🔍 Testing: {url}")
        
        start_time = time.time()
        response = requests.get(url, timeout=timeout)
        response_time = (time.time() - start_time) * 1000
        
        print(f"📊 Response Time: {response_time:.1f}ms")
        print(f"📊 Status Code: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"📊 Response Data: {json.dumps(data, indent=2)}")
                return True, data, response_time
            except json.JSONDecodeError:
                print(f"📊 Response Text: {response.text}")
                return True, response.text, response_time
        else:
            print(f"❌ HTTP {response.status_code}: {response.text}")
            return False, response.text, response_time
            
    except requests.exceptions.Timeout:
        print(f"⏰ Request timed out after {timeout} seconds")
        return False, "Timeout", timeout * 1000
    except requests.exceptions.ConnectionError:
        print(f"🔌 Connection error - endpoint may not be available")
        return False, "Connection Error", 0
    except Exception as e:
        print(f"💥 Error testing endpoint: {e}")
        return False, str(e), 0

def main():
    """Main execution function."""
    print("=" * 80)
    print("🏥 TESTING /health/minimal ENDPOINT")
    print("=" * 80)
    
    test_results = {
        "timestamp": datetime.now().isoformat(),
        "test_type": "health_minimal_endpoint",
        "results": []
    }
    
    # Get ALB DNS name
    print("\n📋 Step 1: Get ALB DNS Name")
    alb_dns = get_alb_dns()
    
    if not alb_dns:
        print("❌ Could not retrieve ALB DNS name. Cannot test endpoint.")
        return False
    
    print(f"✅ ALB DNS: {alb_dns}")
    
    # Test endpoints
    endpoints_to_test = [
        f"http://{alb_dns}/health/minimal",
        f"https://{alb_dns}/health/minimal",  # Try HTTPS if available
        f"http://{alb_dns}/api/health/minimal",  # Alternative path
        f"http://{alb_dns}/health/simple",  # Compare with simple endpoint
    ]
    
    print(f"\n📋 Step 2: Test Health Endpoints")
    
    all_passed = True
    
    for endpoint in endpoints_to_test:
        print(f"\n🔍 Testing endpoint: {endpoint}")
        success, data, response_time = test_health_endpoint(endpoint)
        
        test_results["results"].append({
            "endpoint": endpoint,
            "success": success,
            "response_time_ms": response_time,
            "data": data if isinstance(data, dict) else str(data)[:200]
        })
        
        if success:
            print(f"✅ {endpoint} - SUCCESS ({response_time:.1f}ms)")
        else:
            print(f"❌ {endpoint} - FAILED")
            if endpoint.endswith("/health/minimal"):
                all_passed = False
    
    # Test direct container health (if possible)
    print(f"\n📋 Step 3: Additional Health Checks")
    
    # Try to get ECS service status
    try:
        result = subprocess.run([
            "aws", "ecs", "describe-services",
            "--cluster", "multimodal-lib-prod-cluster",
            "--services", "multimodal-lib-prod-service-alb",
            "--query", "services[0].runningCount"
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            running_count = result.stdout.strip().strip('"')
            print(f"📊 ECS Running Tasks: {running_count}")
            test_results["ecs_running_tasks"] = running_count
        else:
            print(f"⚠️  Could not get ECS service status: {result.stderr}")
    except Exception as e:
        print(f"⚠️  Could not check ECS service: {e}")
    
    # Save test results
    log_filename = f"health-minimal-test-{int(time.time())}.json"
    with open(log_filename, 'w') as f:
        json.dump(test_results, f, indent=2)
    
    print(f"\n📄 Test results saved to: {log_filename}")
    
    # Summary
    print("\n" + "=" * 80)
    if all_passed:
        print("🎉 ALL HEALTH ENDPOINT TESTS PASSED")
    else:
        print("⚠️  SOME HEALTH ENDPOINT TESTS FAILED")
    print("=" * 80)
    
    primary_endpoint = f"http://{alb_dns}/health/minimal"
    primary_success = any(
        result["endpoint"] == primary_endpoint and result["success"]
        for result in test_results["results"]
    )
    
    if primary_success:
        print(f"✅ Primary endpoint working: {primary_endpoint}")
    else:
        print(f"❌ Primary endpoint failed: {primary_endpoint}")
    
    print(f"📄 Detailed results: {log_filename}")
    
    return primary_success

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n💥 Unexpected error: {e}")
        sys.exit(1)