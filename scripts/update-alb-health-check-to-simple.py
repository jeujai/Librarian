#!/usr/bin/env python3
"""
Update ALB Target Group Health Check Path to /api/health/simple

This script updates the ALB target group health check path from /api/health/minimal
to /api/health/simple in AWS.
"""

import boto3
import json
import sys
from datetime import datetime

def get_target_groups(elbv2_client, name_prefix='multimodal-lib-prod'):
    """Get all target groups matching the name prefix."""
    try:
        response = elbv2_client.describe_target_groups()
        target_groups = [
            tg for tg in response['TargetGroups']
            if name_prefix in tg['TargetGroupName']
        ]
        return target_groups
    except Exception as e:
        print(f"❌ Error getting target groups: {e}")
        return []

def update_health_check_path(elbv2_client, target_group_arn, new_path='/api/health/simple'):
    """Update the health check path for a target group."""
    try:
        response = elbv2_client.modify_target_group(
            TargetGroupArn=target_group_arn,
            HealthCheckPath=new_path
        )
        return response
    except Exception as e:
        print(f"❌ Error updating health check path: {e}")
        return None

def get_target_health(elbv2_client, target_group_arn):
    """Get the health status of targets in the target group."""
    try:
        response = elbv2_client.describe_target_health(
            TargetGroupArn=target_group_arn
        )
        return response['TargetHealthDescriptions']
    except Exception as e:
        print(f"❌ Error getting target health: {e}")
        return []

def main():
    print("=" * 80)
    print("UPDATE ALB HEALTH CHECK PATH TO /api/health/simple")
    print("=" * 80)
    print()
    
    # Initialize AWS clients
    elbv2_client = boto3.client('elbv2', region_name='us-east-1')
    
    # Get target groups
    print("🔍 Finding target groups...")
    target_groups = get_target_groups(elbv2_client)
    
    if not target_groups:
        print("❌ No target groups found matching 'multimodal-lib-prod'")
        return 1
    
    print(f"✅ Found {len(target_groups)} target group(s)")
    print()
    
    # Process each target group
    results = []
    for tg in target_groups:
        tg_name = tg['TargetGroupName']
        tg_arn = tg['TargetGroupArn']
        current_path = tg.get('HealthCheckPath', 'N/A')
        
        print(f"📋 Target Group: {tg_name}")
        print(f"   ARN: {tg_arn}")
        print(f"   Current Health Check Path: {current_path}")
        
        # Check if update is needed
        if current_path == '/api/health/simple':
            print(f"   ✅ Already using /api/health/simple - no update needed")
            results.append({
                'target_group': tg_name,
                'status': 'already_correct',
                'path': current_path
            })
        else:
            print(f"   🔄 Updating health check path to /api/health/simple...")
            
            # Update the health check path
            response = update_health_check_path(elbv2_client, tg_arn)
            
            if response:
                updated_tg = response['TargetGroups'][0]
                new_path = updated_tg['HealthCheckPath']
                print(f"   ✅ Successfully updated to: {new_path}")
                
                results.append({
                    'target_group': tg_name,
                    'status': 'updated',
                    'old_path': current_path,
                    'new_path': new_path
                })
            else:
                print(f"   ❌ Failed to update health check path")
                results.append({
                    'target_group': tg_name,
                    'status': 'failed',
                    'path': current_path
                })
        
        # Get target health status
        print(f"   📊 Checking target health...")
        targets = get_target_health(elbv2_client, tg_arn)
        
        if targets:
            for target in targets:
                target_id = target['Target']['Id']
                target_port = target['Target']['Port']
                health_state = target['TargetHealth']['State']
                reason = target['TargetHealth'].get('Reason', 'N/A')
                
                status_icon = "✅" if health_state == "healthy" else "⚠️"
                print(f"   {status_icon} Target {target_id}:{target_port} - {health_state}")
                if reason != 'N/A':
                    print(f"      Reason: {reason}")
        else:
            print(f"   ℹ️  No targets registered")
        
        print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    updated_count = sum(1 for r in results if r['status'] == 'updated')
    already_correct_count = sum(1 for r in results if r['status'] == 'already_correct')
    failed_count = sum(1 for r in results if r['status'] == 'failed')
    
    print(f"✅ Updated: {updated_count}")
    print(f"✅ Already Correct: {already_correct_count}")
    print(f"❌ Failed: {failed_count}")
    print()
    
    # Save results to file
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = f'alb-health-check-update-{timestamp}.json'
    
    with open(output_file, 'w') as f:
        json.dump({
            'timestamp': timestamp,
            'results': results
        }, f, indent=2, default=str)
    
    print(f"📄 Results saved to: {output_file}")
    print()
    
    # Next steps
    if updated_count > 0:
        print("=" * 80)
        print("NEXT STEPS")
        print("=" * 80)
        print("1. Monitor the target health status to ensure targets become healthy")
        print("2. The ALB will start using the new health check path immediately")
        print("3. Verify the endpoint responds correctly:")
        print("   curl http://<ALB-DNS>/api/health/simple")
        print()
    
    return 0 if failed_count == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
