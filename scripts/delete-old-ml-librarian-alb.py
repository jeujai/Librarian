#!/usr/bin/env python3
"""
Delete the old ml-librarian-prod-alb that might be interfering
"""
import boto3
import json
from datetime import datetime

def log(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def main():
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    ec2 = boto3.client('ec2', region_name='us-east-1')
    
    old_alb_arn = 'arn:aws:elasticloadbalancing:us-east-1:591222106065:loadbalancer/app/ml-librarian-prod-alb/ad9690d65d4eb7e2'
    old_sg_id = 'sg-0df1a4e3bfd2adefd'
    
    log("=" * 80)
    log("Deleting Old ml-librarian-prod-alb")
    log("=" * 80)
    
    # Check if ALB has any target groups
    log("\nChecking for target groups...")
    try:
        tg_resp = elbv2.describe_target_groups(LoadBalancerArn=old_alb_arn)
        if tg_resp['TargetGroups']:
            log(f"   Found {len(tg_resp['TargetGroups'])} target groups")
            for tg in tg_resp['TargetGroups']:
                log(f"   Deleting target group: {tg['TargetGroupName']}")
                elbv2.delete_target_group(TargetGroupArn=tg['TargetGroupArn'])
        else:
            log("   No target groups found")
    except Exception as e:
        log(f"   No target groups: {e}")
    
    # Delete the load balancer
    log("\nDeleting load balancer...")
    try:
        elbv2.delete_load_balancer(LoadBalancerArn=old_alb_arn)
        log("   ✓ Load balancer deletion initiated")
    except Exception as e:
        log(f"   Error deleting load balancer: {e}")
        return
    
    # Wait a moment for deletion to start
    import time
    log("\nWaiting for load balancer to be deleted...")
    time.sleep(5)
    
    # Delete the security group
    log("\nDeleting security group...")
    try:
        ec2.delete_security_group(GroupId=old_sg_id)
        log("   ✓ Security group deleted")
    except Exception as e:
        log(f"   Note: Security group deletion may take a moment: {e}")
        log("   You can delete it manually later if needed")
    
    log("\n" + "=" * 80)
    log("Old ALB Deletion Complete")
    log("=" * 80)
    log("\nThe old ml-librarian-prod-alb has been deleted.")
    log("This should eliminate any potential interference with the new ALB.")

if __name__ == '__main__':
    main()
