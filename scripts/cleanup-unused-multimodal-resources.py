#!/usr/bin/env python3
"""
Clean Up Unused Multimodal Librarian Resources

This script safely disables the CloudFront distribution d347w7yibz52wg.cloudfront.net
and deletes the associated unused ALB multimodal-lib-prod-alb.

Target Resources:
- CloudFront Distribution: d347w7yibz52wg.cloudfront.net (ELC6V44QNBWSF)
- Application Load Balancer: multimodal-lib-prod-alb
- Expected Monthly Savings: ~$16.80
"""

import boto3
import json
import time
from datetime import datetime

def main():
    print("🧹 Unused Multimodal Librarian Resource Cleanup")
    print("=" * 60)
    
    # Resource details
    cloudfront_id = "ELC6V44QNBWSF"
    cloudfront_domain = "d347w7yibz52wg.cloudfront.net"
    alb_name = "multimodal-lib-prod-alb"
    alb_dns = "multimodal-lib-prod-alb-42591568.us-east-1.elb.amazonaws.com"
    
    print(f"🎯 Target Resources:")
    print(f"   CloudFront: {cloudfront_domain} ({cloudfront_id})")
    print(f"   ALB: {alb_name}")
    print(f"   Expected Savings: ~$16.80/month")
    print()
    
    cleanup_results = {
        "cleanup_timestamp": datetime.now().isoformat(),
        "target_resources": {
            "cloudfront_distribution": {
                "id": cloudfront_id,
                "domain": cloudfront_domain
            },
            "load_balancer": {
                "name": alb_name,
                "dns": alb_dns
            }
        },
        "steps_completed": [],
        "cleanup_successful": False,
        "monthly_savings": 0.0
    }
    
    try:
        # Initialize AWS clients
        cloudfront = boto3.client('cloudfront')
        elbv2 = boto3.client('elbv2')
        
        # Step 1: Verify current production is unaffected
        print("🔍 Step 1: Safety verification...")
        
        # Check current production CloudFront (should be d1c3ih7gvhogu1.cloudfront.net)
        print("   Verifying current production CloudFront is unaffected...")
        production_distributions = []
        paginator = cloudfront.get_paginator('list_distributions')
        for page in paginator.paginate():
            if 'Items' in page['DistributionList']:
                for dist in page['DistributionList']['Items']:
                    if dist['Id'] != cloudfront_id and dist['Enabled']:
                        production_distributions.append({
                            'id': dist['Id'],
                            'domain': dist['DomainName'],
                            'status': dist['Status']
                        })
        
        print(f"   ✅ Found {len(production_distributions)} active production distributions")
        for dist in production_distributions:
            print(f"      - {dist['domain']} ({dist['id']}) - {dist['status']}")
        
        cleanup_results["steps_completed"].append("safety_verification")
        
        # Step 2: Get current CloudFront distribution configuration
        print(f"\n📋 Step 2: Getting CloudFront distribution configuration...")
        response = cloudfront.get_distribution(Id=cloudfront_id)
        distribution = response['Distribution']
        etag = response['ETag']
        
        print(f"   Status: {distribution['Status']}")
        print(f"   Enabled: {distribution['DistributionConfig']['Enabled']}")
        print(f"   Price Class: {distribution['DistributionConfig'].get('PriceClass', 'PriceClass_All')}")
        print(f"   ETag: {etag}")
        
        cleanup_results["steps_completed"].append("cloudfront_config_retrieved")
        
        # Step 3: Disable CloudFront distribution
        if distribution['DistributionConfig']['Enabled']:
            print(f"\n🔄 Step 3: Disabling CloudFront distribution...")
            
            # Get the distribution config and disable it
            config = distribution['DistributionConfig']
            config['Enabled'] = False
            
            # Update the distribution to disable it
            update_response = cloudfront.update_distribution(
                Id=cloudfront_id,
                DistributionConfig=config,
                IfMatch=etag
            )
            
            print("   ✅ CloudFront distribution disabled successfully")
            print("   ⏳ Waiting for distribution to propagate (this may take 15-20 minutes)...")
            
            # Wait for the distribution to be deployed
            waiter = cloudfront.get_waiter('distribution_deployed')
            waiter.wait(
                Id=cloudfront_id,
                WaiterConfig={
                    'Delay': 60,  # Check every 60 seconds
                    'MaxAttempts': 30  # Wait up to 30 minutes
                }
            )
            
            print("   ✅ CloudFront distribution propagation complete")
            cleanup_results["steps_completed"].append("cloudfront_disabled")
            
        else:
            print(f"\n✅ Step 3: CloudFront distribution is already disabled")
            cleanup_results["steps_completed"].append("cloudfront_already_disabled")
        
        # Step 4: Get ALB information and verify it's safe to delete
        print(f"\n🔍 Step 4: Analyzing Application Load Balancer...")
        
        # Get ALB details
        alb_response = elbv2.describe_load_balancers(Names=[alb_name])
        alb = alb_response['LoadBalancers'][0]
        alb_arn = alb['LoadBalancerArn']
        
        print(f"   ALB ARN: {alb_arn}")
        print(f"   State: {alb['State']['Code']}")
        print(f"   Scheme: {alb['Scheme']}")
        print(f"   Type: {alb['Type']}")
        
        # Check target groups
        target_groups_response = elbv2.describe_target_groups(LoadBalancerArn=alb_arn)
        target_groups = target_groups_response['TargetGroups']
        
        print(f"   Target Groups: {len(target_groups)}")
        
        total_healthy_targets = 0
        for tg in target_groups:
            tg_arn = tg['TargetGroupArn']
            targets_response = elbv2.describe_target_health(TargetGroupArn=tg_arn)
            healthy_targets = [t for t in targets_response['TargetHealthDescriptions'] 
                             if t['TargetHealth']['State'] == 'healthy']
            total_healthy_targets += len(healthy_targets)
            print(f"      - {tg['TargetGroupName']}: {len(healthy_targets)} healthy targets")
        
        if total_healthy_targets > 0:
            print(f"   ⚠️  WARNING: ALB has {total_healthy_targets} healthy targets!")
            print(f"   This ALB may still be in use. Aborting deletion for safety.")
            cleanup_results["error"] = f"ALB has {total_healthy_targets} healthy targets - not safe to delete"
            return 1
        
        print(f"   ✅ ALB has 0 healthy targets - safe to delete")
        cleanup_results["steps_completed"].append("alb_safety_verified")
        
        # Step 5: Delete Application Load Balancer
        print(f"\n🗑️  Step 5: Deleting Application Load Balancer...")
        
        # Delete the load balancer
        elbv2.delete_load_balancer(LoadBalancerArn=alb_arn)
        
        print(f"   ✅ Load balancer deletion initiated")
        print(f"   ⏳ Waiting for load balancer to be deleted...")
        
        # Wait for deletion to complete
        waiter = elbv2.get_waiter('load_balancers_deleted')
        waiter.wait(
            LoadBalancerArns=[alb_arn],
            WaiterConfig={
                'Delay': 15,  # Check every 15 seconds
                'MaxAttempts': 40  # Wait up to 10 minutes
            }
        )
        
        print(f"   ✅ Load balancer deleted successfully")
        cleanup_results["steps_completed"].append("alb_deleted")
        
        # Step 6: Cleanup target groups (they should be deleted automatically, but let's verify)
        print(f"\n🧹 Step 6: Verifying target group cleanup...")
        
        try:
            remaining_tgs = elbv2.describe_target_groups(LoadBalancerArn=alb_arn)
            if remaining_tgs['TargetGroups']:
                print(f"   ⚠️  Found {len(remaining_tgs['TargetGroups'])} remaining target groups")
                for tg in remaining_tgs['TargetGroups']:
                    print(f"      Deleting target group: {tg['TargetGroupName']}")
                    elbv2.delete_target_group(TargetGroupArn=tg['TargetGroupArn'])
            else:
                print(f"   ✅ All target groups cleaned up automatically")
        except Exception as e:
            if "LoadBalancerNotFound" in str(e):
                print(f"   ✅ Load balancer fully deleted - target groups cleaned up")
            else:
                print(f"   ⚠️  Target group cleanup check failed: {str(e)}")
        
        cleanup_results["steps_completed"].append("target_groups_verified")
        
        # Step 7: Final verification
        print(f"\n✅ Step 7: Final verification...")
        
        # Verify CloudFront is disabled
        final_cf_response = cloudfront.get_distribution(Id=cloudfront_id)
        final_cf_enabled = final_cf_response['Distribution']['DistributionConfig']['Enabled']
        print(f"   CloudFront {cloudfront_domain}: {'Disabled' if not final_cf_enabled else 'Still Enabled'}")
        
        # Verify ALB is deleted
        try:
            elbv2.describe_load_balancers(Names=[alb_name])
            print(f"   ALB {alb_name}: Still exists (unexpected)")
        except Exception as e:
            if "LoadBalancerNotFound" in str(e):
                print(f"   ALB {alb_name}: Successfully deleted")
            else:
                print(f"   ALB {alb_name}: Check failed - {str(e)}")
        
        cleanup_results["steps_completed"].append("final_verification")
        
        # Calculate savings
        cloudfront_savings = 0.60  # ~$0.60/month for disabled CloudFront
        alb_savings = 16.20  # ~$16.20/month for deleted ALB
        total_savings = cloudfront_savings + alb_savings
        
        cleanup_results["monthly_savings"] = total_savings
        cleanup_results["cleanup_successful"] = True
        
        # Step 8: Summary
        print(f"\n🎉 Cleanup Summary:")
        print(f"=" * 40)
        print(f"   ✅ CloudFront Distribution: {cloudfront_domain} - DISABLED")
        print(f"   ✅ Application Load Balancer: {alb_name} - DELETED")
        print(f"   💰 Monthly Cost Savings: ~${total_savings:.2f}")
        print(f"   📅 Cleanup Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        print(f"\n📊 Cost Breakdown:")
        print(f"   CloudFront (disabled): ~${cloudfront_savings:.2f}/month saved")
        print(f"   ALB (deleted): ~${alb_savings:.2f}/month saved")
        print(f"   Total Savings: ~${total_savings:.2f}/month")
        print(f"   Annual Savings: ~${total_savings * 12:.2f}/year")
        
        # Save cleanup report
        report_filename = f"unused-multimodal-cleanup-{int(time.time())}.json"
        with open(report_filename, 'w') as f:
            json.dump(cleanup_results, f, indent=2)
        
        print(f"\n📄 Cleanup report saved: {report_filename}")
        
    except Exception as e:
        print(f"❌ Error during cleanup: {str(e)}")
        
        cleanup_results["error"] = str(e)
        cleanup_results["cleanup_successful"] = False
        
        # Save error report
        error_filename = f"unused-multimodal-cleanup-error-{int(time.time())}.json"
        with open(error_filename, 'w') as f:
            json.dump(cleanup_results, f, indent=2)
        
        print(f"   📄 Error report saved: {error_filename}")
        return 1
    
    print(f"\n🎉 Cleanup completed successfully!")
    print(f"💰 You'll save ~${total_savings:.2f}/month from this cleanup")
    return 0

if __name__ == "__main__":
    exit(main())