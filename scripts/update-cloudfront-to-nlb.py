#!/usr/bin/env python3
"""
Update CloudFront distribution to point to NLB instead of deleted ALB.

This script:
1. Gets the current CloudFront distribution configuration
2. Updates the origin to point to the working NLB
3. Applies the updated configuration
"""

import boto3
import json
import time
from datetime import datetime

def update_cloudfront_to_nlb():
    """Update CloudFront distribution to point to NLB."""
    
    cloudfront = boto3.client('cloudfront')
    
    # Distribution ID that's pointing to the deleted ALB
    distribution_id = 'E3NVIH7ET1R4G9'
    
    # NLB DNS name
    nlb_dns = 'multimodal-lib-prod-nlb-9f03ee5dda51903f.elb.us-east-1.amazonaws.com'
    
    print(f"🔄 Updating CloudFront distribution {distribution_id}")
    print(f"   New origin: {nlb_dns}")
    
    try:
        # Get current distribution config
        print("\n📋 Getting current distribution configuration...")
        response = cloudfront.get_distribution_config(Id=distribution_id)
        config = response['DistributionConfig']
        etag = response['ETag']
        
        print(f"   Current ETag: {etag}")
        
        # Show current origin
        current_origin = config['Origins']['Items'][0]['DomainName']
        print(f"   Current origin: {current_origin}")
        
        # Update the origin to point to NLB
        print(f"\n🔧 Updating origin to NLB...")
        config['Origins']['Items'][0]['DomainName'] = nlb_dns
        config['Origins']['Items'][0]['Id'] = 'nlb-origin'
        
        # Update custom origin config for NLB
        config['Origins']['Items'][0]['CustomOriginConfig'] = {
            'HTTPPort': 80,
            'HTTPSPort': 443,
            'OriginProtocolPolicy': 'http-only',  # NLB listens on HTTP
            'OriginSslProtocols': {
                'Quantity': 3,
                'Items': ['TLSv1', 'TLSv1.1', 'TLSv1.2']
            },
            'OriginReadTimeout': 30,
            'OriginKeepaliveTimeout': 5
        }
        
        # Remove S3OriginConfig if present
        if 'S3OriginConfig' in config['Origins']['Items'][0]:
            del config['Origins']['Items'][0]['S3OriginConfig']
        
        # Update default cache behavior to use new origin
        config['DefaultCacheBehavior']['TargetOriginId'] = 'nlb-origin'
        
        # Apply the updated configuration
        print(f"\n✅ Applying updated configuration...")
        update_response = cloudfront.update_distribution(
            Id=distribution_id,
            DistributionConfig=config,
            IfMatch=etag
        )
        
        new_etag = update_response['ETag']
        status = update_response['Distribution']['Status']
        
        print(f"\n✅ CloudFront distribution updated successfully!")
        print(f"   New ETag: {new_etag}")
        print(f"   Status: {status}")
        print(f"   Distribution ID: {distribution_id}")
        print(f"   New origin: {nlb_dns}")
        
        # Get distribution domain name
        domain_name = update_response['Distribution']['DomainName']
        print(f"\n🌐 CloudFront URL: https://{domain_name}")
        
        print(f"\n⏳ Note: CloudFront is now deploying the changes.")
        print(f"   This typically takes 5-15 minutes to propagate globally.")
        print(f"   Status: {status}")
        
        # Save results
        timestamp = int(time.time())
        results = {
            'timestamp': datetime.now().isoformat(),
            'distribution_id': distribution_id,
            'old_origin': current_origin,
            'new_origin': nlb_dns,
            'status': status,
            'etag': new_etag,
            'domain_name': domain_name,
            'url': f'https://{domain_name}'
        }
        
        filename = f'cloudfront-nlb-update-{timestamp}.json'
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n💾 Results saved to: {filename}")
        
        return results
        
    except Exception as e:
        print(f"\n❌ Error updating CloudFront: {str(e)}")
        raise

if __name__ == '__main__':
    print("=" * 80)
    print("CloudFront to NLB Update Script")
    print("=" * 80)
    
    results = update_cloudfront_to_nlb()
    
    print("\n" + "=" * 80)
    print("✅ UPDATE COMPLETE")
    print("=" * 80)
    print(f"\nYour application will be accessible at:")
    print(f"   https://{results['domain_name']}")
    print(f"\nWait 5-15 minutes for CloudFront to deploy the changes globally.")
