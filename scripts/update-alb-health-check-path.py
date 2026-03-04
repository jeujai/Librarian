#!/usr/bin/env python3
"""
Update ALB Health Check Path

This script updates the ALB target group health check path to /health/simple.

IMPORTANT: /health/simple is the correct endpoint for ALB health checks because:
- It's registered BEFORE all middleware (bypasses middleware completely)
- Has zero dependencies (no startup_phase_manager, no database, no models)
- Returns immediately (< 100ms response time)
- Always returns 200 OK (never returns 503 or other error codes)

/health/minimal should NOT be used for ALB because:
- It's registered AFTER middleware (goes through middleware stack)
- Depends on startup_phase_manager (can fail if not initialized)
- Can return 503 during startup phases
- Slower response time due to middleware and dependency checks
"""

import boto3
import json
import sys
from datetime import datetime

def update_alb_health_check_path():
    """Update the ALB target group health check path to /health/simple."""
    
    elbv2_client = boto3.client('elbv2', region_name='us-east-1')
    
    target_group_arn = 'arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg-v2/7b63a6337a5c7a34'
    
    print("=" * 80)
    print("UPDATE ALB HEALTH CHECK PATH TO /health/simple")
    print("=" * 80)
    
    # Get current configuration
    print(f"\nFetching current target group configuration...")
    
    tg_response = elbv2_client.describe_target_groups(
        TargetGroupArns=[target_group_arn]
    )
    
    target_group = tg_response['TargetGroups'][0]
    current_path = target_group.get('HealthCheckPath')
    
    print(f"\nTarget Group: {target_group['TargetGroupName']}")
    print(f"Current Health Check Path: {current_path}")
    
    # Update the health check path to /health/simple
    new_path = '/health/simple'
    
    print(f"\nUpdating health check path to: {new_path}")
    print(f"\nWhy /health/simple is correct for ALB:")
    print(f"  ✓ Bypasses ALL middleware (registered before middleware)")
    print(f"  ✓ Zero dependencies (no startup_phase_manager, database, models)")
    print(f"  ✓ Always returns 200 OK (never 503 or errors)")
    print(f"  ✓ Ultra-fast response (< 100ms)")
    print(f"\nWhy /health/minimal is NOT suitable for ALB:")
    print(f"  ✗ Goes through middleware stack (slower)")
    print(f"  ✗ Depends on startup_phase_manager (can fail)")
    print(f"  ✗ Can return 503 during startup")
    print(f"  ✗ Slower response time")
    
    update_response = elbv2_client.modify_target_group(
        TargetGroupArn=target_group_arn,
        HealthCheckPath=new_path
    )
    
    updated_tg = update_response['TargetGroups'][0]
    updated_path = updated_tg.get('HealthCheckPath')
    
    print(f"\n✓ Health check path updated successfully!")
    print(f"  Old Path: {current_path}")
    print(f"  New Path: {updated_path}")
    
    # Display full health check configuration
    print(f"\nUpdated Health Check Configuration:")
    print(f"  Path: {updated_tg.get('HealthCheckPath')}")
    print(f"  Protocol: {updated_tg.get('HealthCheckProtocol')}")
    print(f"  Port: {updated_tg.get('HealthCheckPort')}")
    print(f"  Interval: {updated_tg.get('HealthCheckIntervalSeconds')}s")
    print(f"  Timeout: {updated_tg.get('HealthCheckTimeoutSeconds')}s")
    print(f"  Healthy Threshold: {updated_tg.get('HealthyThresholdCount')}")
    print(f"  Unhealthy Threshold: {updated_tg.get('UnhealthyThresholdCount')}")
    print(f"  Matcher: {updated_tg.get('Matcher')}")
    
    print("\n" + "=" * 80)
    print("✓ ALB HEALTH CHECK PATH UPDATE COMPLETE")
    print("=" * 80)
    
    print("\nNote: It may take a few moments for the health checks to start")
    print("using the new path. Monitor target health status to verify.")
    
    # Save the update details
    update_details = {
        'timestamp': datetime.now().isoformat(),
        'target_group_arn': target_group_arn,
        'target_group_name': target_group['TargetGroupName'],
        'old_path': current_path,
        'new_path': updated_path,
        'health_check_config': {
            'path': updated_tg.get('HealthCheckPath'),
            'protocol': updated_tg.get('HealthCheckProtocol'),
            'port': updated_tg.get('HealthCheckPort'),
            'interval': updated_tg.get('HealthCheckIntervalSeconds'),
            'timeout': updated_tg.get('HealthCheckTimeoutSeconds'),
            'healthy_threshold': updated_tg.get('HealthyThresholdCount'),
            'unhealthy_threshold': updated_tg.get('UnhealthyThresholdCount'),
            'matcher': updated_tg.get('Matcher')
        }
    }
    
    output_file = f'alb-health-check-path-update-{int(datetime.now().timestamp())}.json'
    with open(output_file, 'w') as f:
        json.dump(update_details, f, indent=2)
    
    print(f"\n✓ Update details saved to: {output_file}")
    
    return update_details

if __name__ == '__main__':
    try:
        result = update_alb_health_check_path()
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
