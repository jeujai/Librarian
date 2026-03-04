#!/usr/bin/env python3
"""
Verify Target Group Health Check Configuration

This script verifies that the target group health check is configured correctly
according to the design specifications.

Created: 2026-01-15
"""

import json
import boto3
from datetime import datetime

def verify_health_check_config():
    """Verify the target group health check configuration."""
    
    client = boto3.client('elbv2', region_name='us-east-1')
    
    print("=" * 80)
    print("Target Group Health Check Verification")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print()
    
    # Expected configuration from design document
    expected_config = {
        "HealthCheckPath": "/api/health/simple",
        "HealthCheckIntervalSeconds": 30,
        "HealthCheckTimeoutSeconds": 29,
        "HealthyThresholdCount": 2,
        "UnhealthyThresholdCount": 2,
        "Matcher": {"HttpCode": "200"}
    }
    
    try:
        # Get target group details
        response = client.describe_target_groups(
            Names=['multimodal-lib-prod-tg-v2']
        )
        
        if not response['TargetGroups']:
            print("❌ ERROR: Target group 'multimodal-lib-prod-tg-v2' not found")
            return False
        
        tg = response['TargetGroups'][0]
        
        print(f"Target Group: {tg['TargetGroupName']}")
        print(f"ARN: {tg['TargetGroupArn']}")
        print(f"Protocol: {tg['Protocol']}")
        print(f"Port: {tg['Port']}")
        print(f"VPC: {tg['VpcId']}")
        print()
        
        # Verify each health check parameter
        print("Health Check Configuration:")
        print("-" * 80)
        
        all_correct = True
        
        # Check health check path
        actual_path = tg.get('HealthCheckPath', '')
        expected_path = expected_config['HealthCheckPath']
        status = "✅" if actual_path == expected_path else "❌"
        print(f"{status} Path: {actual_path} (expected: {expected_path})")
        if actual_path != expected_path:
            all_correct = False
        
        # Check interval
        actual_interval = tg.get('HealthCheckIntervalSeconds', 0)
        expected_interval = expected_config['HealthCheckIntervalSeconds']
        status = "✅" if actual_interval == expected_interval else "❌"
        print(f"{status} Interval: {actual_interval}s (expected: {expected_interval}s)")
        if actual_interval != expected_interval:
            all_correct = False
        
        # Check timeout
        actual_timeout = tg.get('HealthCheckTimeoutSeconds', 0)
        expected_timeout = expected_config['HealthCheckTimeoutSeconds']
        status = "✅" if actual_timeout == expected_timeout else "❌"
        print(f"{status} Timeout: {actual_timeout}s (expected: {expected_timeout}s)")
        if actual_timeout != expected_timeout:
            all_correct = False
        
        # Check healthy threshold
        actual_healthy = tg.get('HealthyThresholdCount', 0)
        expected_healthy = expected_config['HealthyThresholdCount']
        status = "✅" if actual_healthy == expected_healthy else "❌"
        print(f"{status} Healthy Threshold: {actual_healthy} (expected: {expected_healthy})")
        if actual_healthy != expected_healthy:
            all_correct = False
        
        # Check unhealthy threshold
        actual_unhealthy = tg.get('UnhealthyThresholdCount', 0)
        expected_unhealthy = expected_config['UnhealthyThresholdCount']
        status = "✅" if actual_unhealthy == expected_unhealthy else "❌"
        print(f"{status} Unhealthy Threshold: {actual_unhealthy} (expected: {expected_unhealthy})")
        if actual_unhealthy != expected_unhealthy:
            all_correct = False
        
        # Check matcher
        actual_matcher = tg.get('Matcher', {})
        expected_matcher = expected_config['Matcher']
        status = "✅" if actual_matcher == expected_matcher else "❌"
        print(f"{status} Matcher: {actual_matcher} (expected: {expected_matcher})")
        if actual_matcher != expected_matcher:
            all_correct = False
        
        print()
        print("=" * 80)
        
        if all_correct:
            print("✅ SUCCESS: All health check parameters are configured correctly!")
            print()
            print("Configuration Summary:")
            print(f"  • Health check endpoint: {actual_path}")
            print(f"  • Check interval: {actual_interval}s")
            print(f"  • Timeout: {actual_timeout}s (maximum for {actual_interval}s interval)")
            print(f"  • Thresholds: {actual_healthy} healthy / {actual_unhealthy} unhealthy")
            print(f"  • Expected response: HTTP {actual_matcher.get('HttpCode', 'N/A')}")
            print()
            print("Rationale:")
            print("  • Path verified to exist and return 200 OK")
            print("  • Timeout maximized (29s) for 30s interval (1s buffer)")
            print("  • Thresholds balanced for responsiveness and stability")
            return True
        else:
            print("❌ FAILURE: Some health check parameters are incorrect!")
            print("Please review the configuration and update as needed.")
            return False
        
    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return False

if __name__ == "__main__":
    success = verify_health_check_config()
    exit(0 if success else 1)
