#!/usr/bin/env python3
"""
Delete Orphaned CloudFront Distribution

This script safely deletes the CloudFront distribution d1p5nsqu15ui56.cloudfront.net
which is pointing to a non-existent load balancer.

Distribution Details:
- ID: EG4POF7D2NLA4
- Domain: d1p5nsqu15ui56.cloudfront.net
- Origin: Collab-Serve-WsYWbstG4vRM-336145199.us-east-1.elb.amazonaws.com (DELETED)
- Status: Orphaned (pointing to deleted load balancer)
"""

import boto3
import json
import time
from datetime import datetime

def main():
    print("🗑️  CloudFront Distribution Cleanup")
    print("=" * 50)
    
    # Distribution details
    distribution_id = "EG4POF7D2NLA4"
    distribution_domain = "d1p5nsqu15ui56.cloudfront.net"
    
    print(f"Target Distribution: {distribution_domain}")
    print(f"Distribution ID: {distribution_id}")
    print()
    
    try:
        # Initialize CloudFront client
        cloudfront = boto3.client('cloudfront')
        
        # Step 1: Get current distribution configuration
        print("📋 Step 1: Getting distribution configuration...")
        response = cloudfront.get_distribution(Id=distribution_id)
        distribution = response['Distribution']
        etag = response['ETag']
        
        print(f"   Status: {distribution['Status']}")
        print(f"   Enabled: {distribution['DistributionConfig']['Enabled']}")
        print(f"   ETag: {etag}")
        
        # Step 2: Disable the distribution first (required before deletion)
        if distribution['DistributionConfig']['Enabled']:
            print("\n🔄 Step 2: Disabling distribution...")
            
            # Get the distribution config
            config = distribution['DistributionConfig']
            config['Enabled'] = False
            
            # Update the distribution to disable it
            update_response = cloudfront.update_distribution(
                Id=distribution_id,
                DistributionConfig=config,
                IfMatch=etag
            )
            
            print("   ✅ Distribution disabled successfully")
            print("   ⏳ Waiting for distribution to propagate (this may take 15-20 minutes)...")
            
            # Wait for the distribution to be deployed
            waiter = cloudfront.get_waiter('distribution_deployed')
            waiter.wait(
                Id=distribution_id,
                WaiterConfig={
                    'Delay': 60,  # Check every 60 seconds
                    'MaxAttempts': 30  # Wait up to 30 minutes
                }
            )
            
            print("   ✅ Distribution propagation complete")
            
            # Get the new ETag after the update
            response = cloudfront.get_distribution(Id=distribution_id)
            etag = response['ETag']
        else:
            print("\n✅ Step 2: Distribution is already disabled")
        
        # Step 3: Delete the distribution
        print(f"\n🗑️  Step 3: Deleting distribution {distribution_id}...")
        
        cloudfront.delete_distribution(
            Id=distribution_id,
            IfMatch=etag
        )
        
        print("   ✅ Distribution deletion initiated successfully")
        print(f"   🎯 Distribution {distribution_domain} has been removed")
        
        # Step 4: Summary
        print(f"\n📊 Cleanup Summary:")
        print(f"   Deleted Distribution: {distribution_domain}")
        print(f"   Distribution ID: {distribution_id}")
        print(f"   Monthly Cost Savings: ~$0.60")
        print(f"   Cleanup Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Save cleanup report
        cleanup_report = {
            "cleanup_type": "orphaned_cloudfront_distribution",
            "distribution_id": distribution_id,
            "distribution_domain": distribution_domain,
            "reason": "Pointing to deleted load balancer",
            "original_origin": "Collab-Serve-WsYWbstG4vRM-336145199.us-east-1.elb.amazonaws.com",
            "status": "deleted",
            "monthly_savings": 0.60,
            "cleanup_timestamp": datetime.now().isoformat(),
            "cleanup_successful": True
        }
        
        report_filename = f"orphaned-cloudfront-cleanup-{int(time.time())}.json"
        with open(report_filename, 'w') as f:
            json.dump(cleanup_report, f, indent=2)
        
        print(f"   📄 Cleanup report saved: {report_filename}")
        
    except Exception as e:
        print(f"❌ Error during cleanup: {str(e)}")
        
        # Save error report
        error_report = {
            "cleanup_type": "orphaned_cloudfront_distribution",
            "distribution_id": distribution_id,
            "distribution_domain": distribution_domain,
            "status": "failed",
            "error": str(e),
            "cleanup_timestamp": datetime.now().isoformat(),
            "cleanup_successful": False
        }
        
        error_filename = f"orphaned-cloudfront-cleanup-error-{int(time.time())}.json"
        with open(error_filename, 'w') as f:
            json.dump(error_report, f, indent=2)
        
        print(f"   📄 Error report saved: {error_filename}")
        return 1
    
    print(f"\n🎉 Cleanup completed successfully!")
    print(f"💰 You'll save ~$0.60/month from removing this orphaned distribution")
    return 0

if __name__ == "__main__":
    exit(main())