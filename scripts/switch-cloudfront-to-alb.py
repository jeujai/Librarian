#!/usr/bin/env python3
"""
Switch CloudFront from NLB to ALB for better HTTP/HTTPS support.

ALBs are designed for HTTP/HTTPS traffic and work much better with CloudFront.
NLBs are designed for TCP/UDP traffic and don't handle HTTP as well.
"""

import boto3
import json
import time
from datetime import datetime

def switch_cloudfront_to_alb():
    """Switch CloudFront distribution from NLB to ALB."""
    
    cloudfront = boto3.client('cloudfront')
    elbv2 = boto3.client('elbv2')
    
    distribution_id = 'E3NVIH7ET1R4G9'
    
    print("=" * 80)
    print("Switch CloudFront from NLB to ALB")
    print("=" * 80)
    
    # Get ALB DNS
    print("\n📋 Finding best ALB...")
    lbs = elbv2.describe_load_balancers()
    
    alb_candidates = [lb for lb in lbs['LoadBalancers'] 
                      if lb['Type'] == 'application' and 'multimodal' in lb['LoadBalancerName']]
    
    if not alb_candidates:
        print("   ❌ No ALB found!")
        return
    
    # Use the v2 ALB if available, otherwise use the first one
    alb = next((lb for lb in alb_candidates if 'v2' in lb['LoadBalancerName']), alb_candidates[0])
    alb_dns = alb['DNSName']
    alb_name = alb['LoadBalancerName']
    
    print(f"   Selected ALB: {alb_name}")
    print(f"   DNS: {alb_dns}")
    
    # Check ALB health
    print("\n🏥 Checking ALB health...")
    tgs = elbv2.describe_target_groups(LoadBalancerArn=alb['LoadBalancerArn'])
    
    all_healthy = True
    for tg in tgs['TargetGroups']:
        health = elbv2.describe_target_health(TargetGroupArn=tg['TargetGroupArn'])
        for target in health['TargetHealthDescriptions']:
            state = target['TargetHealth']['State']
            if state != 'healthy':
                all_healthy = False
                print(f"   ⚠️  Target {target['Target']['Id']} is {state}")
    
    if all_healthy:
        print(f"   ✅ All targets are healthy")
    
    # Get current CloudFront config
    print("\n📋 Getting CloudFront configuration...")
    response = cloudfront.get_distribution_config(Id=distribution_id)
    config = response['DistributionConfig']
    etag = response['ETag']
    
    old_origin = config['Origins']['Items'][0]['DomainName']
    print(f"   Current origin: {old_origin}")
    
    # Update origin to ALB
    print(f"\n🔧 Updating origin to ALB...")
    config['Origins']['Items'][0]['DomainName'] = alb_dns
    config['Origins']['Items'][0]['Id'] = 'alb-origin'
    
    # Update custom origin config for ALB
    config['Origins']['Items'][0]['CustomOriginConfig'] = {
        'HTTPPort': 80,
        'HTTPSPort': 443,
        'OriginProtocolPolicy': 'http-only',  # ALB listens on HTTP
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
    
    # Update default cache behavior
    config['DefaultCacheBehavior']['TargetOriginId'] = 'alb-origin'
    
    # Apply update
    print(f"\n✅ Applying configuration...")
    update_response = cloudfront.update_distribution(
        Id=distribution_id,
        DistributionConfig=config,
        IfMatch=etag
    )
    
    new_etag = update_response['ETag']
    status = update_response['Distribution']['Status']
    domain_name = update_response['Distribution']['DomainName']
    
    print(f"\n✅ CloudFront updated successfully!")
    print(f"   Distribution ID: {distribution_id}")
    print(f"   Old origin: {old_origin}")
    print(f"   New origin: {alb_dns}")
    print(f"   Status: {status}")
    print(f"   CloudFront URL: https://{domain_name}")
    
    print(f"\n⏳ Deployment in progress...")
    print(f"   This will take 5-15 minutes to propagate globally.")
    
    # Save results
    timestamp = int(time.time())
    results = {
        'timestamp': datetime.now().isoformat(),
        'distribution_id': distribution_id,
        'old_origin': old_origin,
        'new_origin': alb_dns,
        'alb_name': alb_name,
        'status': status,
        'domain_name': domain_name,
        'url': f'https://{domain_name}'
    }
    
    filename = f'cloudfront-alb-switch-{timestamp}.json'
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Results saved to: {filename}")
    
    print("\n" + "=" * 80)
    print("WHY ALB IS BETTER THAN NLB FOR CLOUDFRONT")
    print("=" * 80)
    print()
    print("✅ ALB Advantages:")
    print("   - Designed for HTTP/HTTPS traffic")
    print("   - Better health checks for web applications")
    print("   - Path-based routing support")
    print("   - WebSocket support")
    print("   - Better integration with CloudFront")
    print()
    print("❌ NLB Limitations:")
    print("   - Designed for TCP/UDP traffic")
    print("   - No HTTP-level health checks")
    print("   - No path-based routing")
    print("   - Less suitable for web applications")
    
    return results

if __name__ == '__main__':
    print("This script will switch CloudFront from NLB to ALB.")
    print("ALBs are better suited for HTTP/HTTPS traffic with CloudFront.")
    print()
    
    switch_cloudfront_to_alb()
