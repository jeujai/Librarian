#!/usr/bin/env python3
"""
Analyze All CloudFront Distribution Pricing Plans

This script checks all CloudFront distributions for pricing plan subscriptions
and identifies any shared pricing plans that might affect deletion.
"""

import boto3
import json
import time
from datetime import datetime

def main():
    print("💰 CloudFront Pricing Plan Analysis")
    print("=" * 60)
    
    try:
        # Initialize CloudFront client
        cloudfront = boto3.client('cloudfront')
        
        # Get all distributions
        print("📋 Getting all CloudFront distributions...")
        paginator = cloudfront.get_paginator('list_distributions')
        distributions = []
        
        for page in paginator.paginate():
            if 'Items' in page['DistributionList']:
                distributions.extend(page['DistributionList']['Items'])
        
        print(f"   Found {len(distributions)} distributions")
        print()
        
        # Analyze each distribution
        pricing_plan_analysis = {}
        distribution_details = []
        
        for dist in distributions:
            dist_id = dist['Id']
            domain = dist['DomainName']
            status = dist['Status']
            enabled = dist['Enabled']
            
            print(f"🔍 Analyzing {domain} ({dist_id})...")
            
            try:
                # Get detailed distribution configuration
                response = cloudfront.get_distribution(Id=dist_id)
                config = response['Distribution']['DistributionConfig']
                
                # Extract pricing plan information
                price_class = config.get('PriceClass', 'PriceClass_All')
                
                # Check for origins
                origins = []
                if 'Origins' in config and config['Origins']['Items']:
                    for origin in config['Origins']['Items']:
                        origins.append({
                            'domain': origin['DomainName'],
                            'id': origin['Id']
                        })
                
                dist_info = {
                    'id': dist_id,
                    'domain': domain,
                    'status': status,
                    'enabled': enabled,
                    'price_class': price_class,
                    'origins': origins,
                    'last_modified': dist['LastModifiedTime'].isoformat()
                }
                
                distribution_details.append(dist_info)
                
                # Group by pricing plan
                if price_class not in pricing_plan_analysis:
                    pricing_plan_analysis[price_class] = []
                pricing_plan_analysis[price_class].append(dist_info)
                
                print(f"   Status: {status}")
                print(f"   Enabled: {enabled}")
                print(f"   Price Class: {price_class}")
                print(f"   Origins: {len(origins)}")
                
            except Exception as e:
                print(f"   ❌ Error analyzing {dist_id}: {str(e)}")
            
            print()
        
        # Summary analysis
        print("📊 Pricing Plan Summary:")
        print("=" * 40)
        
        for price_class, dists in pricing_plan_analysis.items():
            print(f"\n💰 {price_class}:")
            print(f"   Distributions: {len(dists)}")
            
            for dist in dists:
                status_icon = "🟢" if dist['enabled'] else "🔴"
                print(f"   {status_icon} {dist['domain']} ({dist['id']})")
                if not dist['enabled']:
                    print(f"      ⚠️  DISABLED - May have deletion restrictions")
        
        # Identify potential issues
        print(f"\n🚨 Deletion Impact Analysis:")
        print("=" * 40)
        
        orphaned_dist = None
        for dist in distribution_details:
            if dist['id'] == 'EG4POF7D2NLA4':
                orphaned_dist = dist
                break
        
        if orphaned_dist:
            orphaned_price_class = orphaned_dist['price_class']
            same_plan_dists = [d for d in distribution_details 
                             if d['price_class'] == orphaned_price_class and d['id'] != 'EG4POF7D2NLA4']
            
            print(f"🎯 Orphaned Distribution Analysis:")
            print(f"   Distribution: {orphaned_dist['domain']}")
            print(f"   Price Class: {orphaned_price_class}")
            print(f"   Status: {orphaned_dist['status']}")
            print(f"   Enabled: {orphaned_dist['enabled']}")
            
            if same_plan_dists:
                print(f"\n⚠️  OTHER DISTRIBUTIONS USING SAME PRICING PLAN:")
                for dist in same_plan_dists:
                    status_icon = "🟢" if dist['enabled'] else "🔴"
                    print(f"   {status_icon} {dist['domain']} ({dist['id']})")
                    if dist['enabled']:
                        print(f"      🔥 ACTIVE - Pricing plan cannot be cancelled")
                
                print(f"\n💡 RECOMMENDATION:")
                print(f"   The orphaned distribution shares its pricing plan with {len(same_plan_dists)} other distribution(s).")
                active_count = len([d for d in same_plan_dists if d['enabled']])
                if active_count > 0:
                    print(f"   {active_count} of these are ACTIVE, so the pricing plan cannot be cancelled.")
                    print(f"   The orphaned distribution will remain disabled but cannot be deleted.")
                    print(f"   Cost impact: Minimal (~$0.60/month) since it's disabled.")
                else:
                    print(f"   All other distributions are also disabled.")
                    print(f"   You may be able to cancel the pricing plan and delete all disabled distributions.")
            else:
                print(f"\n✅ GOOD NEWS:")
                print(f"   No other distributions use the same pricing plan.")
                print(f"   You should be able to cancel the pricing plan and delete this distribution.")
        
        # Cost analysis
        print(f"\n💰 Cost Analysis:")
        print("=" * 40)
        
        total_distributions = len(distribution_details)
        enabled_distributions = len([d for d in distribution_details if d['enabled']])
        disabled_distributions = total_distributions - enabled_distributions
        
        print(f"   Total Distributions: {total_distributions}")
        print(f"   Active (Enabled): {enabled_distributions}")
        print(f"   Disabled: {disabled_distributions}")
        print(f"   Estimated Monthly Cost:")
        print(f"     - Active distributions: ~${enabled_distributions * 0.60:.2f}")
        print(f"     - Disabled distributions: ~${disabled_distributions * 0.10:.2f} (minimal)")
        print(f"     - Total: ~${enabled_distributions * 0.60 + disabled_distributions * 0.10:.2f}")
        
        # Save comprehensive analysis
        analysis_report = {
            "analysis_timestamp": datetime.now().isoformat(),
            "total_distributions": total_distributions,
            "enabled_distributions": enabled_distributions,
            "disabled_distributions": disabled_distributions,
            "pricing_plan_breakdown": pricing_plan_analysis,
            "distribution_details": distribution_details,
            "orphaned_distribution_analysis": {
                "distribution_id": "EG4POF7D2NLA4",
                "can_delete": len(same_plan_dists) == 0 if orphaned_dist else False,
                "blocking_distributions": same_plan_dists if orphaned_dist else [],
                "recommendation": "Cannot delete due to shared pricing plan" if orphaned_dist and same_plan_dists else "May be able to delete after pricing plan cancellation"
            },
            "cost_analysis": {
                "monthly_cost_active": enabled_distributions * 0.60,
                "monthly_cost_disabled": disabled_distributions * 0.10,
                "total_monthly_cost": enabled_distributions * 0.60 + disabled_distributions * 0.10
            }
        }
        
        report_filename = f"cloudfront-pricing-analysis-comprehensive-{int(time.time())}.json"
        with open(report_filename, 'w') as f:
            json.dump(analysis_report, f, indent=2)
        
        print(f"\n📄 Comprehensive analysis saved: {report_filename}")
        
    except Exception as e:
        print(f"❌ Error during analysis: {str(e)}")
        return 1
    
    print(f"\n✅ Analysis completed!")
    return 0

if __name__ == "__main__":
    exit(main())