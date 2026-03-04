#!/usr/bin/env python3
"""
Validate ALB Service

Comprehensive validation of the new ECS service with ALB target group.

Usage:
    python scripts/validate-alb-service.py --target-group-arn <arn>
"""

import boto3
import requests
import time
import sys
import json
from datetime import datetime
from typing import Dict, Tuple

def check_service_status(cluster_name: str, service_name: str) -> Dict[str, bool]:
    """Check ECS service status"""
    ecs = boto3.client('ecs')
    
    print("1. Checking service status...")
    
    checks = {}
    
    try:
        response = ecs.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        if not response['services']:
            print(f"   ❌ Service {service_name} not found")
            checks['service_exists'] = False
            return checks
        
        service = response['services'][0]
        
        checks['service_exists'] = True
        checks['service_active'] = service['status'] == 'ACTIVE'
        checks['desired_count_met'] = service['runningCount'] == service['desiredCount']
        
        print(f"   ✅ Service exists: {service_name}")
        print(f"   {'✅' if checks['service_active'] else '❌'} Status: {service['status']}")
        print(f"   {'✅' if checks['desired_count_met'] else '❌'} Running: {service['runningCount']}/{service['desiredCount']}")
        
    except Exception as e:
        print(f"   ❌ Error checking service: {e}")
        checks['service_exists'] = False
    
    return checks

def check_target_health(target_group_arn: str) -> Dict[str, bool]:
    """Check target health"""
    elbv2 = boto3.client('elbv2')
    
    print("\n2. Checking target health...")
    
    checks = {}
    
    try:
        response = elbv2.describe_target_health(
            TargetGroupArn=target_group_arn
        )
        
        if not response['TargetHealthDescriptions']:
            print("   ❌ No targets registered")
            checks['targets_registered'] = False
            checks['targets_healthy'] = False
            return checks
        
        checks['targets_registered'] = True
        
        healthy_targets = []
        for target in response['TargetHealthDescriptions']:
            target_id = target['Target']['Id']
            state = target['TargetHealth']['State']
            
            if state == 'healthy':
                healthy_targets.append(target_id)
                print(f"   ✅ Target {target_id}: {state}")
            else:
                reason = target['TargetHealth'].get('Reason', 'Unknown')
                print(f"   ❌ Target {target_id}: {state} ({reason})")
        
        checks['targets_healthy'] = len(healthy_targets) > 0
        
    except Exception as e:
        print(f"   ❌ Error checking target health: {e}")
        checks['targets_registered'] = False
        checks['targets_healthy'] = False
    
    return checks

def get_alb_dns(target_group_arn: str) -> str:
    """Get ALB DNS name"""
    elbv2 = boto3.client('elbv2')
    
    target_group = elbv2.describe_target_groups(
        TargetGroupArns=[target_group_arn]
    )['TargetGroups'][0]
    
    if not target_group['LoadBalancerArns']:
        raise Exception("Target group not attached to load balancer")
    
    alb_arn = target_group['LoadBalancerArns'][0]
    alb = elbv2.describe_load_balancers(
        LoadBalancerArns=[alb_arn]
    )['LoadBalancers'][0]
    
    return alb['DNSName']

def test_http_endpoints(alb_dns: str) -> Dict[str, bool]:
    """Test HTTP endpoints"""
    print(f"\n3. Testing HTTP endpoints (DNS: {alb_dns})...")
    
    checks = {}
    
    # Test health endpoint
    try:
        print("   Testing /api/health/simple...")
        response = requests.get(f"http://{alb_dns}/api/health/simple", timeout=10)
        checks['http_health_check'] = response.status_code == 200
        print(f"   {'✅' if checks['http_health_check'] else '❌'} Health check: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Health check failed: {e}")
        checks['http_health_check'] = False
    
    # Test application endpoint
    try:
        print("   Testing / (root)...")
        response = requests.get(f"http://{alb_dns}/", timeout=10)
        checks['http_application'] = response.status_code == 200
        print(f"   {'✅' if checks['http_application'] else '❌'} Application: {response.status_code}")
    except Exception as e:
        print(f"   ❌ Application test failed: {e}")
        checks['http_application'] = False
    
    return checks

def check_application_logs() -> Dict[str, bool]:
    """Check application logs for requests"""
    logs = boto3.client('logs')
    
    print("\n4. Checking application logs...")
    
    checks = {}
    
    try:
        events = logs.filter_log_events(
            logGroupName='/ecs/multimodal-lib-prod-app',
            startTime=int((time.time() - 300) * 1000),  # Last 5 minutes
            filterPattern='GET /api/health'
        )
        
        checks['logs_show_requests'] = len(events['events']) > 0
        
        if checks['logs_show_requests']:
            print(f"   ✅ Found {len(events['events'])} health check requests in logs")
        else:
            print("   ❌ No health check requests found in logs")
            
    except Exception as e:
        print(f"   ❌ Error checking logs: {e}")
        checks['logs_show_requests'] = False
    
    return checks

def print_results(all_checks: Dict[str, bool], alb_dns: str):
    """Print validation results"""
    print("\n" + "="*70)
    print("VALIDATION RESULTS")
    print("="*70)
    
    for check, passed in all_checks.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        check_name = check.replace('_', ' ').title()
        print(f"{status}: {check_name}")
    
    all_passed = all(all_checks.values())
    
    print("="*70)
    
    if all_passed:
        print("✅ ALL CHECKS PASSED - Service is ready for production")
        print(f"\nALB DNS: {alb_dns}")
        print("\nNext steps:")
        print("1. Update CloudFront origin to ALB DNS")
        print("2. Test HTTPS URL: https://d3a2xw711pvw5j.cloudfront.net/")
        print("3. Monitor for 24 hours")
        print("4. Scale up new service and scale down old service")
    else:
        print("❌ SOME CHECKS FAILED - Investigate before proceeding")
        print("\nFailed checks need to be resolved before migration")
    
    print("="*70)
    
    return all_passed

def main():
    """Main execution"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Validate ALB service')
    parser.add_argument('--target-group-arn', required=True, help='ALB target group ARN')
    parser.add_argument('--cluster', default='multimodal-lib-prod-cluster', help='ECS cluster')
    parser.add_argument('--service', default='multimodal-lib-prod-service-alb', help='Service name')
    
    args = parser.parse_args()
    
    try:
        print("="*70)
        print("ALB SERVICE VALIDATION")
        print("="*70)
        
        all_checks = {}
        
        # Run all checks
        all_checks.update(check_service_status(args.cluster, args.service))
        all_checks.update(check_target_health(args.target_group_arn))
        
        alb_dns = get_alb_dns(args.target_group_arn)
        all_checks.update(test_http_endpoints(alb_dns))
        all_checks.update(check_application_logs())
        
        # Print results
        all_passed = print_results(all_checks, alb_dns)
        
        # Save results
        timestamp = int(time.time())
        result_file = f"alb-service-validation-{timestamp}.json"
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "cluster": args.cluster,
            "service": args.service,
            "target_group_arn": args.target_group_arn,
            "alb_dns": alb_dns,
            "checks": all_checks,
            "all_passed": all_passed
        }
        
        with open(result_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"\nResults saved to: {result_file}")
        
        sys.exit(0 if all_passed else 1)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
