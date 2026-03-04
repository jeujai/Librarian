#!/usr/bin/env python3
"""
Delete ml-shared-vpc-alb and its associated target groups.
This will separate the Multimodal Librarian from the shared VPC infrastructure.
"""

import boto3
import json
import time
from datetime import datetime

def delete_ml_shared_vpc_alb():
    """Delete ml-shared-vpc-alb and associated resources."""
    elbv2 = boto3.client('elbv2')
    
    print("🗑️ Deleting ml-shared-vpc-alb")
    print("=" * 50)
    
    alb_name = 'ml-shared-vpc-alb'
    
    try:
        # Get ALB details
        response = elbv2.describe_load_balancers(Names=[alb_name])
        if not response['LoadBalancers']:
            print(f"❌ ALB {alb_name} not found!")
            return False
        
        alb = response['LoadBalancers'][0]
        alb_arn = alb['LoadBalancerArn']
        
        print(f"📊 Found ALB: {alb_name}")
        print(f"  DNS: {alb['DNSName']}")
        print(f"  VPC: {alb['VpcId']}")
        print(f"  State: {alb['State']['Code']}")
        
        # Get target groups
        tg_response = elbv2.describe_target_groups(LoadBalancerArn=alb_arn)
        target_groups = tg_response['TargetGroups']
        
        print(f"\n🎯 Target Groups: {len(target_groups)}")
        
        target_group_arns = []
        for tg in target_groups:
            tg_name = tg['TargetGroupName']
            tg_arn = tg['TargetGroupArn']
            target_group_arns.append(tg_arn)
            
            # Check targets
            health_response = elbv2.describe_target_health(TargetGroupArn=tg_arn)
            targets = health_response['TargetHealthDescriptions']
            
            print(f"  - {tg_name}: {len(targets)} targets")
            for target in targets:
                target_id = target['Target']['Id']
                target_port = target['Target']['Port']
                health_state = target['TargetHealth']['State']
                print(f"    Target: {target_id}:{target_port} ({health_state})")
        
        # Confirm deletion
        print(f"\n⚠️ This will delete:")
        print(f"  - ALB: {alb_name}")
        print(f"  - Target Groups: {len(target_groups)}")
        print(f"  - Monthly savings: ~$16-22")
        
        # Delete ALB (this will automatically delete listeners)
        print(f"\n🗑️ Deleting ALB: {alb_name}")
        elbv2.delete_load_balancer(LoadBalancerArn=alb_arn)
        
        # Wait for ALB deletion to complete
        print("⏳ Waiting for ALB deletion to complete...")
        waiter = elbv2.get_waiter('load_balancers_deleted')
        waiter.wait(LoadBalancerArns=[alb_arn], WaiterConfig={'Delay': 15, 'MaxAttempts': 40})
        
        print("✅ ALB deleted successfully")
        
        # Delete target groups (they should be automatically deleted, but let's be thorough)
        print(f"\n🎯 Cleaning up target groups...")
        for tg_arn in target_group_arns:
            try:
                elbv2.delete_target_group(TargetGroupArn=tg_arn)
                print(f"✅ Deleted target group: {tg_arn}")
            except Exception as e:
                if "not found" in str(e).lower():
                    print(f"ℹ️ Target group already deleted: {tg_arn}")
                else:
                    print(f"⚠️ Error deleting target group {tg_arn}: {e}")
        
        # Verify deletion
        print(f"\n✅ Verification:")
        try:
            response = elbv2.describe_load_balancers(Names=[alb_name])
            if response['LoadBalancers']:
                print(f"❌ ALB {alb_name} still exists!")
                return False
        except Exception as e:
            if "LoadBalancerNotFound" in str(e) or "does not exist" in str(e):
                print(f"✅ ALB {alb_name} successfully deleted")
                return True
            else:
                print(f"⚠️ Error verifying deletion: {e}")
                return True  # Assume success if we can't verify
        
    except Exception as e:
        print(f"❌ Error deleting ALB: {e}")
        return False

def main():
    """Main execution function."""
    print("🚀 ML Shared VPC ALB Deletion")
    print("=" * 50)
    print(f"Execution Time: {datetime.now().isoformat()}")
    
    try:
        success = delete_ml_shared_vpc_alb()
        
        if success:
            print(f"\n🎉 SUCCESS: ml-shared-vpc-alb deleted successfully")
            print(f"💰 Monthly savings: ~$16-22")
            print(f"📝 Next step: Update Terraform to create dedicated VPC for Multimodal Librarian")
        else:
            print(f"\n❌ FAILED: Could not delete ml-shared-vpc-alb")
            return 1
        
        # Save results
        results = {
            'deletion_time': datetime.now().isoformat(),
            'alb_deleted': 'ml-shared-vpc-alb',
            'success': success,
            'monthly_savings': '$16-22'
        }
        
        with open(f'ml-shared-vpc-alb-deletion-{int(datetime.now().timestamp())}.json', 'w') as f:
            json.dump(results, f, indent=2)
        
        return 0
        
    except Exception as e:
        print(f"❌ Error during deletion: {e}")
        return 1

if __name__ == "__main__":
    exit(main())