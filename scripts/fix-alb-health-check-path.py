#!/usr/bin/env python3
"""
Fix the ALB target group health check path.
The application has health endpoints at /health/simple, not /api/health/simple.
"""

import boto3
import json
import time
from datetime import datetime

def fix_target_group_health_check(target_group_arn, correct_path):
    """Fix the health check path for a target group."""
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    
    print(f"Updating health check path to: {correct_path}")
    
    response = elbv2.modify_target_group(
        TargetGroupArn=target_group_arn,
        HealthCheckPath=correct_path,
        HealthCheckProtocol='HTTP',
        HealthCheckPort='traffic-port',
        HealthCheckIntervalSeconds=30,
        HealthCheckTimeoutSeconds=29,
        HealthyThresholdCount=2,
        UnhealthyThresholdCount=2
    )
    
    return response['TargetGroups'][0]

def get_target_groups():
    """Get all multimodal target groups."""
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    
    response = elbv2.describe_target_groups()
    
    multimodal_tgs = [
        tg for tg in response['TargetGroups']
        if 'multimodal' in tg['TargetGroupName'].lower()
    ]
    
    return multimodal_tgs

def main():
    print("=" * 80)
    print("ALB Health Check Path Fix")
    print("=" * 80)
    print()
    print("ISSUE: ALB target groups are checking /api/health/simple")
    print("FIX: Application has health endpoint at /health/simple (no /api prefix)")
    print()
    
    # Get target groups
    print("1. Finding target groups...")
    target_groups = get_target_groups()
    
    if not target_groups:
        print("ERROR: No multimodal target groups found")
        return
    
    print(f"   Found {len(target_groups)} target groups")
    print()
    
    # Fix each target group
    results = []
    
    for tg in target_groups:
        tg_name = tg['TargetGroupName']
        tg_arn = tg['TargetGroupArn']
        current_path = tg.get('HealthCheckPath', 'N/A')
        
        print(f"2. Target Group: {tg_name}")
        print(f"   Current health check path: {current_path}")
        
        # Determine correct path
        if current_path == '/api/health/simple':
            correct_path = '/health/simple'
            print(f"   ✗ INCORRECT - Fixing to: {correct_path}")
            
            try:
                updated_tg = fix_target_group_health_check(tg_arn, correct_path)
                print(f"   ✓ Updated successfully")
                
                results.append({
                    'target_group': tg_name,
                    'old_path': current_path,
                    'new_path': correct_path,
                    'status': 'updated'
                })
            except Exception as e:
                print(f"   ✗ ERROR: {str(e)}")
                results.append({
                    'target_group': tg_name,
                    'old_path': current_path,
                    'new_path': correct_path,
                    'status': 'error',
                    'error': str(e)
                })
        elif current_path == '/health/simple' or current_path == '/health':
            print(f"   ✓ CORRECT - No change needed")
            results.append({
                'target_group': tg_name,
                'path': current_path,
                'status': 'correct'
            })
        else:
            print(f"   ⚠ UNKNOWN PATH - Manual review needed")
            results.append({
                'target_group': tg_name,
                'path': current_path,
                'status': 'unknown'
            })
        
        print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    updated = [r for r in results if r.get('status') == 'updated']
    correct = [r for r in results if r.get('status') == 'correct']
    errors = [r for r in results if r.get('status') == 'error']
    
    print(f"✓ Updated: {len(updated)}")
    print(f"✓ Already correct: {len(correct)}")
    print(f"✗ Errors: {len(errors)}")
    print()
    
    if updated:
        print("Updated target groups:")
        for r in updated:
            print(f"  - {r['target_group']}: {r['old_path']} → {r['new_path']}")
        print()
    
    if errors:
        print("Errors:")
        for r in errors:
            print(f"  - {r['target_group']}: {r['error']}")
        print()
    
    print("NEXT STEPS:")
    print("1. Wait 30-60 seconds for health checks to run")
    print("2. Check target health: aws elbv2 describe-target-health --target-group-arn <arn>")
    print("3. Monitor container logs for health check requests")
    print()
    
    # Save results
    output_file = f"health-check-path-fix-{int(time.time())}.json"
    with open(output_file, 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'results': results
        }, f, indent=2)
    
    print(f"Results saved to: {output_file}")

if __name__ == '__main__':
    main()
