#!/usr/bin/env python3
"""
Check ALB Target Group Health Status

This script checks the health status of targets in the ALB target group.
"""

import boto3
import json
import sys
from datetime import datetime

def check_alb_health_status():
    """Check the ALB target group health status."""
    
    elbv2_client = boto3.client('elbv2', region_name='us-east-1')
    
    target_group_arn = 'arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg-v2/7b63a6337a5c7a34'
    
    print("=" * 80)
    print("ALB TARGET GROUP HEALTH STATUS")
    print("=" * 80)
    
    # Get target group configuration
    print(f"\nFetching target group configuration...")
    
    tg_response = elbv2_client.describe_target_groups(
        TargetGroupArns=[target_group_arn]
    )
    
    target_group = tg_response['TargetGroups'][0]
    
    print(f"\nTarget Group: {target_group['TargetGroupName']}")
    print(f"Health Check Configuration:")
    print(f"  Path: {target_group.get('HealthCheckPath')}")
    print(f"  Protocol: {target_group.get('HealthCheckProtocol')}")
    print(f"  Port: {target_group.get('HealthCheckPort')}")
    print(f"  Interval: {target_group.get('HealthCheckIntervalSeconds')}s")
    print(f"  Timeout: {target_group.get('HealthCheckTimeoutSeconds')}s")
    print(f"  Healthy Threshold: {target_group.get('HealthyThresholdCount')}")
    print(f"  Unhealthy Threshold: {target_group.get('UnhealthyThresholdCount')}")
    print(f"  Matcher: {target_group.get('Matcher')}")
    
    # Get target health
    print(f"\nFetching target health status...")
    
    health_response = elbv2_client.describe_target_health(
        TargetGroupArn=target_group_arn
    )
    
    targets = health_response['TargetHealthDescriptions']
    
    print(f"\nRegistered Targets: {len(targets)}")
    print("-" * 80)
    
    healthy_count = 0
    unhealthy_count = 0
    draining_count = 0
    
    for target in targets:
        target_id = target['Target']['Id']
        target_port = target['Target']['Port']
        health_state = target['TargetHealth']['State']
        reason = target['TargetHealth'].get('Reason', 'N/A')
        description = target['TargetHealth'].get('Description', 'N/A')
        
        status_symbol = "✓" if health_state == "healthy" else "✗" if health_state == "unhealthy" else "⚠"
        
        print(f"\n{status_symbol} Target: {target_id}:{target_port}")
        print(f"  State: {health_state}")
        if reason != 'N/A':
            print(f"  Reason: {reason}")
        if description != 'N/A':
            print(f"  Description: {description}")
        
        if health_state == "healthy":
            healthy_count += 1
        elif health_state == "unhealthy":
            unhealthy_count += 1
        elif health_state == "draining":
            draining_count += 1
    
    print("\n" + "-" * 80)
    print(f"Summary:")
    print(f"  Healthy: {healthy_count}")
    print(f"  Unhealthy: {unhealthy_count}")
    print(f"  Draining: {draining_count}")
    print(f"  Total: {len(targets)}")
    
    # Overall status
    print("\n" + "=" * 80)
    if healthy_count > 0 and unhealthy_count == 0:
        print("✓ ALB HEALTH CHECK STATUS: HEALTHY")
    elif unhealthy_count > 0:
        print("✗ ALB HEALTH CHECK STATUS: UNHEALTHY")
    else:
        print("⚠ ALB HEALTH CHECK STATUS: NO HEALTHY TARGETS")
    print("=" * 80)
    
    # Save the status details
    status_details = {
        'timestamp': datetime.now().isoformat(),
        'target_group_arn': target_group_arn,
        'target_group_name': target_group['TargetGroupName'],
        'health_check_config': {
            'path': target_group.get('HealthCheckPath'),
            'protocol': target_group.get('HealthCheckProtocol'),
            'port': target_group.get('HealthCheckPort'),
            'interval': target_group.get('HealthCheckIntervalSeconds'),
            'timeout': target_group.get('HealthCheckTimeoutSeconds'),
            'healthy_threshold': target_group.get('HealthyThresholdCount'),
            'unhealthy_threshold': target_group.get('UnhealthyThresholdCount'),
            'matcher': target_group.get('Matcher')
        },
        'targets': [
            {
                'id': t['Target']['Id'],
                'port': t['Target']['Port'],
                'state': t['TargetHealth']['State'],
                'reason': t['TargetHealth'].get('Reason'),
                'description': t['TargetHealth'].get('Description')
            }
            for t in targets
        ],
        'summary': {
            'healthy': healthy_count,
            'unhealthy': unhealthy_count,
            'draining': draining_count,
            'total': len(targets)
        }
    }
    
    output_file = f'alb-health-status-{int(datetime.now().timestamp())}.json'
    with open(output_file, 'w') as f:
        json.dump(status_details, f, indent=2)
    
    print(f"\n✓ Status details saved to: {output_file}")
    
    return status_details

if __name__ == '__main__':
    try:
        result = check_alb_health_status()
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
