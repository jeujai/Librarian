#!/usr/bin/env python3
"""
Fix ALB health check path

The application has the health endpoint at /health/minimal
but the target group is configured to check /api/health/minimal
"""

import boto3
import json
from datetime import datetime

def fix_health_check_path():
    elbv2 = boto3.client('elbv2')
    
    print("=" * 80)
    print("FIX ALB HEALTH CHECK PATH")
    print("=" * 80)
    
    # Find target group
    tgs = elbv2.describe_target_groups()['TargetGroups']
    
    target_group = None
    for tg in tgs:
        if 'multimodal-lib-prod-tg' in tg['TargetGroupName']:
            target_group = tg
            break
    
    if not target_group:
        print("❌ Target group not found")
        return
    
    tg_arn = target_group['TargetGroupArn']
    
    print(f"\nTarget Group: {target_group['TargetGroupName']}")
    print(f"\nCurrent Health Check Path: {target_group['HealthCheckPath']}")
    print(f"Correct Health Check Path: /health/minimal")
    
    print(f"\n🔧 Updating health check path...")
    
    try:
        response = elbv2.modify_target_group(
            TargetGroupArn=tg_arn,
            HealthCheckPath='/health/minimal',
            HealthCheckIntervalSeconds=60,
            HealthCheckTimeoutSeconds=30,
            HealthyThresholdCount=2,
            UnhealthyThresholdCount=3
        )
        
        print("\n✅ Health check path updated successfully!")
        
        new_tg = response['TargetGroups'][0]
        print(f"\nNew Settings:")
        print(f"  Health Check Path: {new_tg['HealthCheckPath']}")
        print(f"  Health Check Interval: {new_tg['HealthCheckIntervalSeconds']}s")
        print(f"  Health Check Timeout: {new_tg['HealthCheckTimeoutSeconds']}s")
        print(f"  Healthy Threshold: {new_tg['HealthyThresholdCount']}")
        print(f"  Unhealthy Threshold: {new_tg['UnhealthyThresholdCount']}")
        
        print("\n⏱️  Expected time to become healthy: ~120 seconds")
        print("    (2 successful checks at 60-second intervals)")
        
        # Save results
        output_file = f"health-check-path-fix-{int(datetime.now().timestamp())}.json"
        with open(output_file, 'w') as f:
            json.dump({
                'timestamp': datetime.now().isoformat(),
                'target_group': target_group['TargetGroupName'],
                'old_path': target_group['HealthCheckPath'],
                'new_path': new_tg['HealthCheckPath'],
                'settings': {
                    'interval': new_tg['HealthCheckIntervalSeconds'],
                    'timeout': new_tg['HealthCheckTimeoutSeconds'],
                    'healthy_threshold': new_tg['HealthyThresholdCount'],
                    'unhealthy_threshold': new_tg['UnhealthyThresholdCount']
                }
            }, f, indent=2)
        
        print(f"\n📄 Results saved to: {output_file}")
        
    except Exception as e:
        print(f"\n❌ Error updating health check path: {e}")

if __name__ == '__main__':
    fix_health_check_path()
