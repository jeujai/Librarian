#!/usr/bin/env python3
"""
Fix ALB health check path mismatch.

The issue: ALB is checking /health/simple but the application endpoint is /api/health/simple
Solution: Update the ALB target group to use the correct path
"""

import boto3
import json
import sys
from datetime import datetime

def main():
    print("=" * 80)
    print("ALB Health Check Path Mismatch Fix")
    print("=" * 80)
    
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    
    # Get target group
    print("\n1. Finding target group...")
    try:
        tgs = elbv2.describe_target_groups(Names=['multimodal-lib-prod-tg-v2'])
        tg = tgs['TargetGroups'][0]
        tg_arn = tg['TargetGroupArn']
        
        print(f"✓ Found target group: {tg['TargetGroupName']}")
        print(f"  Current health check path: {tg['HealthCheckPath']}")
        print(f"  Current health check timeout: {tg['HealthCheckTimeoutSeconds']}s")
        print(f"  Current health check interval: {tg['HealthCheckIntervalSeconds']}s")
        
    except Exception as e:
        print(f"❌ Error finding target group: {e}")
        return 1
    
    # Check if path needs updating
    correct_path = "/api/health/simple"
    if tg['HealthCheckPath'] == correct_path:
        print(f"\n✓ Health check path is already correct: {correct_path}")
        return 0
    
    # Update target group health check
    print(f"\n2. Updating health check path to: {correct_path}")
    try:
        response = elbv2.modify_target_group(
            TargetGroupArn=tg_arn,
            HealthCheckPath=correct_path,
            HealthCheckIntervalSeconds=30,
            HealthCheckTimeoutSeconds=10,
            HealthyThresholdCount=2,
            UnhealthyThresholdCount=3
        )
        
        print("✓ Target group updated successfully!")
        print(f"  New health check path: {response['TargetGroups'][0]['HealthCheckPath']}")
        
    except Exception as e:
        print(f"❌ Error updating target group: {e}")
        return 1
    
    # Verify the change
    print("\n3. Verifying update...")
    try:
        tgs = elbv2.describe_target_groups(TargetGroupArns=[tg_arn])
        tg = tgs['TargetGroups'][0]
        
        if tg['HealthCheckPath'] == correct_path:
            print(f"✓ Verification successful! Health check path is now: {correct_path}")
        else:
            print(f"⚠️  Verification failed. Path is: {tg['HealthCheckPath']}")
            return 1
            
    except Exception as e:
        print(f"❌ Error verifying update: {e}")
        return 1
    
    print("\n" + "=" * 80)
    print("SUCCESS")
    print("=" * 80)
    print("\nThe ALB health check path has been updated to match the application endpoint.")
    print("The ALB should now be able to successfully health check the ECS tasks.")
    print("\nNext steps:")
    print("1. Wait 30-60 seconds for the next health check cycle")
    print("2. Check target health: aws elbv2 describe-target-health --target-group-arn", tg_arn)
    print("3. Monitor ECS service events for healthy status")
    
    return 0

if __name__ == '__main__':
    sys.exit(main())
