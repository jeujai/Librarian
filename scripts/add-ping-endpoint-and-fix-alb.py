#!/usr/bin/env python3
"""
Add Simple Ping Endpoint and Fix ALB Health Check

This script:
1. Adds a super simple /ping endpoint to the health router
2. Updates the ALB target group to use /ping instead of /api/health/minimal
3. Monitors the health check status

The /ping endpoint is the simplest possible health check that just returns OK.
"""

import boto3
import json
import time
from datetime import datetime

def add_ping_endpoint_to_code():
    """Add a simple /ping endpoint to the health router."""
    print("\n" + "="*80)
    print("STEP 1: Adding /ping endpoint to health router")
    print("="*80)
    
    # The ping endpoint code to add
    ping_endpoint = '''

@router.get("/ping")
async def ping_health_check():
    """
    Ultra-simple ping endpoint for ALB health checks.
    
    This is the simplest possible health check that just returns OK
    without any dependencies on application state.
    
    Returns:
        Simple OK response
    """
    return {"status": "ok", "timestamp": datetime.now().isoformat()}
'''
    
    print("\n✅ Ping endpoint code prepared")
    print("\nNOTE: You need to manually add this to src/multimodal_librarian/api/routers/health.py:")
    print(ping_endpoint)
    print("\nOr we can update the ALB to use an existing simple endpoint like /api/health/simple")
    
    return True

def update_alb_health_check():
    """Update ALB target group to use simpler health check."""
    print("\n" + "="*80)
    print("STEP 2: Updating ALB Health Check Configuration")
    print("="*80)
    
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    
    # Find the target group
    print("\n🔍 Finding target group...")
    response = elbv2.describe_target_groups(
        Names=['multimodal-lib-prod-tg']
    )
    
    if not response['TargetGroups']:
        print("❌ Target group not found")
        return False
    
    target_group = response['TargetGroups'][0]
    target_group_arn = target_group['TargetGroupArn']
    
    print(f"✅ Found target group: {target_group_arn}")
    
    # Update health check to use /api/health/simple (which already exists)
    print("\n🔧 Updating health check configuration...")
    print("   Path: /api/health/minimal → /api/health/simple")
    print("   Timeout: 29s (keeping)")
    print("   Interval: 30s (keeping)")
    print("   Healthy threshold: 2 (keeping)")
    print("   Unhealthy threshold: 2 (keeping)")
    
    try:
        elbv2.modify_target_group(
            TargetGroupArn=target_group_arn,
            HealthCheckPath='/api/health/simple',
            HealthCheckIntervalSeconds=30,
            HealthCheckTimeoutSeconds=29,
            HealthyThresholdCount=2,
            UnhealthyThresholdCount=2,
            Matcher={'HttpCode': '200'}
        )
        
        print("✅ Health check configuration updated successfully")
        return True
        
    except Exception as e:
        print(f"❌ Failed to update health check: {e}")
        return False

def check_target_health(wait_time=120):
    """Monitor target health status."""
    print("\n" + "="*80)
    print("STEP 3: Monitoring Target Health")
    print("="*80)
    
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    
    # Get target group ARN
    response = elbv2.describe_target_groups(
        Names=['multimodal-lib-prod-tg']
    )
    target_group_arn = response['TargetGroups'][0]['TargetGroupArn']
    
    print(f"\n⏱️  Monitoring for {wait_time} seconds...")
    print("   (Health checks run every 30 seconds, need 2 consecutive successes)")
    
    start_time = time.time()
    last_status = None
    
    while time.time() - start_time < wait_time:
        try:
            response = elbv2.describe_target_health(
                TargetGroupArn=target_group_arn
            )
            
            if response['TargetHealthDescriptions']:
                target = response['TargetHealthDescriptions'][0]
                status = target['TargetHealth']['State']
                reason = target['TargetHealth'].get('Reason', 'N/A')
                description = target['TargetHealth'].get('Description', 'N/A')
                
                if status != last_status:
                    elapsed = int(time.time() - start_time)
                    print(f"\n[{elapsed}s] Status: {status}")
                    if reason != 'N/A':
                        print(f"       Reason: {reason}")
                    if description != 'N/A':
                        print(f"       Description: {description}")
                    last_status = status
                
                if status == 'healthy':
                    print("\n✅ Target is HEALTHY!")
                    return True
            
            time.sleep(10)
            
        except Exception as e:
            print(f"❌ Error checking health: {e}")
            time.sleep(10)
    
    print(f"\n⏱️  Monitoring period ended after {wait_time} seconds")
    print("   Check status manually if needed")
    return False

def get_cloudfront_url():
    """Get the CloudFront URL for the application."""
    print("\n" + "="*80)
    print("APPLICATION ACCESS INFORMATION")
    print("="*80)
    
    cloudfront = boto3.client('cloudfront', region_name='us-east-1')
    
    try:
        response = cloudfront.list_distributions()
        
        for dist in response.get('DistributionList', {}).get('Items', []):
            if 'multimodal' in dist.get('Comment', '').lower():
                domain = dist['DomainName']
                status = dist['Status']
                
                print(f"\n🌐 CloudFront Distribution")
                print(f"   URL: https://{domain}")
                print(f"   Status: {status}")
                print(f"\n📱 Chat Interface:")
                print(f"   https://{domain}/")
                print(f"\n🔍 Health Check:")
                print(f"   https://{domain}/api/health/simple")
                
                return domain
    except Exception as e:
        print(f"⚠️  Could not retrieve CloudFront info: {e}")
    
    return None

def main():
    """Main execution function."""
    print("\n" + "="*80)
    print("ALB HEALTH CHECK FIX - SIMPLE ENDPOINT APPROACH")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'steps': {}
    }
    
    # Step 1: Explain the ping endpoint (optional)
    add_ping_endpoint_to_code()
    results['steps']['ping_endpoint'] = 'explained'
    
    # Step 2: Update ALB health check to use /api/health/simple
    if update_alb_health_check():
        results['steps']['alb_update'] = 'success'
        
        # Step 3: Monitor health
        if check_target_health(wait_time=120):
            results['steps']['health_check'] = 'healthy'
            results['status'] = 'success'
        else:
            results['steps']['health_check'] = 'monitoring_timeout'
            results['status'] = 'pending'
    else:
        results['steps']['alb_update'] = 'failed'
        results['status'] = 'failed'
    
    # Get CloudFront URL
    cloudfront_url = get_cloudfront_url()
    if cloudfront_url:
        results['cloudfront_url'] = f"https://{cloudfront_url}"
    
    # Save results
    output_file = f"health-check-fix-{int(time.time())}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print(f"\n✅ Results saved to: {output_file}")
    
    if results['status'] == 'success':
        print("\n🎉 ALB health check fix completed successfully!")
        print(f"\n🌐 Your application should now be accessible at:")
        print(f"   {results.get('cloudfront_url', 'https://d1c3ih7gvhogu1.cloudfront.net')}")
    elif results['status'] == 'pending':
        print("\n⏱️  Health check update applied, monitoring in progress")
        print("   Check status in a few minutes")
    else:
        print("\n❌ Health check fix encountered issues")
        print("   Review the output above for details")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    main()
