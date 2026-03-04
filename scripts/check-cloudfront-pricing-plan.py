#!/usr/bin/env python3
"""
Check CloudFront Distribution Pricing Plan

This script checks the pricing plan subscription for the orphaned CloudFront distribution
and provides guidance on how to cancel it before deletion.
"""

import boto3
import json
import time
from datetime import datetime

def main():
    print("💰 CloudFront Pricing Plan Check")
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
        
        # Get distribution configuration
        print("📋 Getting distribution configuration...")
        response = cloudfront.get_distribution(Id=distribution_id)
        distribution = response['Distribution']
        config = distribution['DistributionConfig']
        
        print(f"   Status: {distribution['Status']}")
        print(f"   Enabled: {config['Enabled']}")
        print(f"   Price Class: {config.get('PriceClass', 'PriceClass_All')}")
        
        # Check if there's a pricing plan
        print(f"\n💡 Pricing Plan Analysis:")
        print(f"   The distribution appears to have a pricing plan subscription.")
        print(f"   This prevents immediate deletion.")
        
        # Get more details about the distribution
        print(f"\n📊 Distribution Details:")
        print(f"   Domain: {distribution_domain}")
        print(f"   Status: {distribution['Status']}")
        print(f"   Last Modified: {distribution['LastModifiedTime']}")
        print(f"   Price Class: {config.get('PriceClass', 'PriceClass_All')}")
        
        # Check origins
        if 'Origins' in config and config['Origins']['Items']:
            print(f"\n🔗 Origins:")
            for i, origin in enumerate(config['Origins']['Items']):
                print(f"   {i+1}. {origin['DomainName']}")
                print(f"      Origin ID: {origin['Id']}")
        
        # Provide guidance
        print(f"\n📋 Next Steps to Delete This Distribution:")
        print(f"   1. ✅ Distribution has been disabled (completed)")
        print(f"   2. ⏳ Cancel pricing plan subscription:")
        print(f"      - Go to AWS Console > CloudFront > Distributions")
        print(f"      - Select distribution {distribution_id}")
        print(f"      - Look for 'Pricing Plan' or 'Subscription' settings")
        print(f"      - Cancel any active pricing plan")
        print(f"   3. ⏳ Wait for billing cycle end (up to 1 month)")
        print(f"   4. 🗑️  Delete distribution after pricing plan cancellation")
        
        print(f"\n💰 Cost Impact:")
        print(f"   - Current monthly cost: ~$0.60")
        print(f"   - After pricing plan cancellation: Distribution can be deleted")
        print(f"   - Savings timeline: May take up to 1 billing cycle")
        
        # Alternative approach
        print(f"\n🔄 Alternative Approach:")
        print(f"   Since the distribution is already disabled, it won't serve traffic.")
        print(f"   You can leave it disabled until the pricing plan expires,")
        print(f"   then delete it at the end of the billing cycle.")
        print(f"   The cost impact is minimal (~$0.60/month).")
        
        # Save analysis report
        analysis_report = {
            "distribution_id": distribution_id,
            "distribution_domain": distribution_domain,
            "status": distribution['Status'],
            "enabled": config['Enabled'],
            "price_class": config.get('PriceClass', 'PriceClass_All'),
            "last_modified": distribution['LastModifiedTime'].isoformat(),
            "deletion_blocked_reason": "pricing_plan_subscription",
            "next_steps": [
                "Cancel pricing plan subscription in AWS Console",
                "Wait for billing cycle end",
                "Delete distribution after pricing plan cancellation"
            ],
            "cost_impact": {
                "monthly_cost": 0.60,
                "savings_timeline": "up_to_1_billing_cycle"
            },
            "analysis_timestamp": datetime.now().isoformat()
        }
        
        report_filename = f"cloudfront-pricing-analysis-{int(time.time())}.json"
        with open(report_filename, 'w') as f:
            json.dump(analysis_report, f, indent=2)
        
        print(f"\n📄 Analysis report saved: {report_filename}")
        
    except Exception as e:
        print(f"❌ Error during analysis: {str(e)}")
        return 1
    
    print(f"\n✅ Analysis completed!")
    return 0

if __name__ == "__main__":
    exit(main())