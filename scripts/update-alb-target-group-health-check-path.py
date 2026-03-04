#!/usr/bin/env python3
"""
Update ALB Target Group Health Check Path

This script updates the health check path in the ALB target group
from /health/minimal to /api/health/minimal to match the API router configuration.

The health check router is mounted at /api/health, so the correct path should be:
- Current: /health/minimal
- Updated: /api/health/minimal
"""

import boto3
import json
import time
from datetime import datetime

def get_target_groups():
    """Get all target groups and find the one used by our service."""
    elbv2 = boto3.client('elbv2')
    
    try:
        response = elbv2.describe_target_groups()
        
        # Look for target groups related to multimodal-lib-prod
        target_groups = []
        for tg in response['TargetGroups']:
            tg_name = tg['TargetGroupName']
            if 'multimodal-lib-prod' in tg_name or 'multimodal' in tg_name:
                target_groups.append(tg)
                print(f"📋 Found target group: {tg_name} ({tg['TargetGroupArn']})")
                print(f"   Health check path: {tg.get('HealthCheckPath', 'N/A')}")
                print(f"   Health check protocol: {tg.get('HealthCheckProtocol', 'N/A')}")
                print(f"   Health check port: {tg.get('HealthCheckPort', 'N/A')}")
                print()
        
        return target_groups
        
    except Exception as e:
        print(f"❌ Error getting target groups: {e}")
        return []

def update_target_group_health_check(target_group_arn, current_path):
    """Update the health check path for a target group."""
    elbv2 = boto3.client('elbv2')
    
    # Check if update is needed
    if current_path == '/api/health/minimal':
        print(f"✅ Target group already has correct health check path: {current_path}")
        return True
    
    if current_path != '/health/minimal':
        print(f"⚠️ Unexpected current path: {current_path}")
        print("Expected /health/minimal, but found different path.")
        
        # Ask user if they want to proceed
        response = input("Do you want to update this path to /api/health/minimal? (y/N): ")
        if response.lower() != 'y':
            print("❌ Update cancelled by user")
            return False
    
    try:
        print(f"🔧 Updating health check path from {current_path} to /api/health/minimal...")
        
        response = elbv2.modify_target_group(
            TargetGroupArn=target_group_arn,
            HealthCheckPath='/api/health/minimal'
        )
        
        print("✅ Target group health check path updated successfully!")
        return True
        
    except Exception as e:
        print(f"❌ Error updating target group: {e}")
        return False

def verify_target_group_update(target_group_arn):
    """Verify that the target group health check path was updated correctly."""
    elbv2 = boto3.client('elbv2')
    
    try:
        response = elbv2.describe_target_groups(
            TargetGroupArns=[target_group_arn]
        )
        
        if response['TargetGroups']:
            tg = response['TargetGroups'][0]
            health_check_path = tg.get('HealthCheckPath', 'N/A')
            
            if health_check_path == '/api/health/minimal':
                print("✅ Verification successful: Health check path is now /api/health/minimal")
                return True
            else:
                print(f"❌ Verification failed: Health check path is {health_check_path}")
                return False
        else:
            print("❌ Target group not found during verification")
            return False
            
    except Exception as e:
        print(f"❌ Error verifying target group update: {e}")
        return False

def check_target_health(target_group_arn):
    """Check the health of targets in the target group."""
    elbv2 = boto3.client('elbv2')
    
    try:
        response = elbv2.describe_target_health(
            TargetGroupArn=target_group_arn
        )
        
        print("🔍 Target Health Status:")
        for target in response['TargetHealthDescriptions']:
            target_id = target['Target']['Id']
            port = target['Target']['Port']
            health_state = target['TargetHealth']['State']
            description = target['TargetHealth'].get('Description', 'N/A')
            
            status_emoji = {
                'healthy': '✅',
                'unhealthy': '❌',
                'initial': '🔄',
                'draining': '⏳',
                'unavailable': '⚠️'
            }.get(health_state, '❓')
            
            print(f"  {status_emoji} Target {target_id}:{port} - {health_state}")
            if description != 'N/A':
                print(f"     Description: {description}")
        
        return response['TargetHealthDescriptions']
        
    except Exception as e:
        print(f"❌ Error checking target health: {e}")
        return []

def wait_for_healthy_targets(target_group_arn, timeout_minutes=10):
    """Wait for targets to become healthy after the health check path change."""
    print(f"⏳ Waiting for targets to become healthy (timeout: {timeout_minutes} minutes)...")
    
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    
    while time.time() - start_time < timeout_seconds:
        targets = check_target_health(target_group_arn)
        
        if not targets:
            print("❌ No targets found")
            return False
        
        healthy_count = sum(1 for t in targets if t['TargetHealth']['State'] == 'healthy')
        total_count = len(targets)
        
        print(f"📊 Health status: {healthy_count}/{total_count} targets healthy")
        
        if healthy_count == total_count:
            print("✅ All targets are healthy!")
            return True
        
        print("⏳ Waiting 30 seconds before next check...")
        time.sleep(30)
    
    print(f"⚠️ Timeout reached after {timeout_minutes} minutes")
    print("Some targets may still be becoming healthy. Check AWS console for current status.")
    return False

def main():
    """Main execution function."""
    print("🎯 ALB Target Group Health Check Path Update")
    print("=" * 60)
    print("Updating health check path from /health/minimal to /api/health/minimal")
    print()
    
    # Step 1: Get target groups
    print("📋 Step 1: Finding target groups...")
    target_groups = get_target_groups()
    
    if not target_groups:
        print("❌ No target groups found for multimodal-lib-prod")
        return
    
    print()
    
    # Step 2: Update each target group
    print("🔧 Step 2: Updating target group health check paths...")
    updated_groups = []
    
    for tg in target_groups:
        tg_name = tg['TargetGroupName']
        tg_arn = tg['TargetGroupArn']
        current_path = tg.get('HealthCheckPath', 'N/A')
        
        print(f"Processing target group: {tg_name}")
        
        if update_target_group_health_check(tg_arn, current_path):
            updated_groups.append((tg_arn, tg_name))
        
        print()
    
    if not updated_groups:
        print("❌ No target groups were updated")
        return
    
    # Step 3: Verify updates
    print("✅ Step 3: Verifying updates...")
    all_verified = True
    
    for tg_arn, tg_name in updated_groups:
        print(f"Verifying {tg_name}...")
        if not verify_target_group_update(tg_arn):
            all_verified = False
    
    print()
    
    if not all_verified:
        print("❌ Some target groups failed verification")
        return
    
    # Step 4: Check target health
    print("🔍 Step 4: Checking target health...")
    for tg_arn, tg_name in updated_groups:
        print(f"Checking health for {tg_name}...")
        check_target_health(tg_arn)
        print()
    
    # Step 5: Wait for healthy targets (optional)
    if len(updated_groups) == 1:
        tg_arn, tg_name = updated_groups[0]
        
        response = input("Do you want to wait for targets to become healthy? (y/N): ")
        if response.lower() == 'y':
            print()
            print("⏳ Step 5: Waiting for targets to become healthy...")
            wait_for_healthy_targets(tg_arn)
    
    print()
    print("🎉 ALB Target Group Health Check Path Update Completed!")
    print()
    print("Summary:")
    for tg_arn, tg_name in updated_groups:
        print(f"  • Updated {tg_name}: /health/minimal → /api/health/minimal")
    print()
    print("The ALB target group health check path now matches the API router configuration.")
    print("Health checks should start passing once the application responds correctly to /api/health/minimal")

if __name__ == "__main__":
    main()