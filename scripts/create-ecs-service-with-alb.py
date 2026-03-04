#!/usr/bin/env python3
"""
Create New ECS Service with ALB Target Group

This script creates a new ECS service configured to use the ALB target group.
This is necessary because AWS does not allow changing the load balancer on an
existing ECS service.

Blue-Green Deployment Strategy:
- Blue (old): multimodal-lib-prod-service with NLB
- Green (new): multimodal-lib-prod-service-alb with ALB

Usage:
    python scripts/create-ecs-service-with-alb.py --target-group-arn <arn>
"""

import boto3
import json
import sys
import time
from datetime import datetime
from typing import Dict, Any

def get_current_service_config(cluster_name: str, service_name: str) -> Dict[str, Any]:
    """Get configuration from current service"""
    ecs = boto3.client('ecs')
    
    print(f"Getting configuration from service: {service_name}...")
    
    response = ecs.describe_services(
        cluster=cluster_name,
        services=[service_name]
    )
    
    if not response['services']:
        raise Exception(f"Service {service_name} not found")
    
    service = response['services'][0]
    
    print(f"✅ Found service: {service_name}")
    print(f"   Task Definition: {service['taskDefinition']}")
    print(f"   Desired Count: {service['desiredCount']}")
    print(f"   Launch Type: {service['launchType']}")
    
    return service

def validate_target_group(target_group_arn: str) -> Dict[str, Any]:
    """Validate ALB target group exists and is configured correctly"""
    elbv2 = boto3.client('elbv2')
    
    print(f"\nValidating target group: {target_group_arn}...")
    
    response = elbv2.describe_target_groups(
        TargetGroupArns=[target_group_arn]
    )
    
    if not response['TargetGroups']:
        raise Exception(f"Target group {target_group_arn} not found")
    
    target_group = response['TargetGroups'][0]
    
    # Validate configuration
    if target_group['Protocol'] != 'HTTP':
        raise Exception(f"Target group must use HTTP protocol, found: {target_group['Protocol']}")
    
    if target_group['Port'] != 8000:
        raise Exception(f"Target group must be on port 8000, found: {target_group['Port']}")
    
    if target_group['TargetType'] != 'ip':
        raise Exception(f"Target group must use 'ip' target type, found: {target_group['TargetType']}")
    
    print(f"✅ Target group validated:")
    print(f"   Protocol: {target_group['Protocol']}")
    print(f"   Port: {target_group['Port']}")
    print(f"   Target Type: {target_group['TargetType']}")
    print(f"   VPC: {target_group['VpcId']}")
    
    return target_group

def create_service_with_alb(
    cluster_name: str,
    old_service_name: str,
    new_service_name: str,
    target_group_arn: str,
    current_service: Dict[str, Any]
) -> Dict[str, Any]:
    """Create new ECS service with ALB target group"""
    ecs = boto3.client('ecs')
    
    print(f"\nCreating new service: {new_service_name}...")
    
    # Build service configuration
    service_config = {
        'cluster': cluster_name,
        'serviceName': new_service_name,
        'taskDefinition': current_service['taskDefinition'],
        'loadBalancers': [
            {
                'targetGroupArn': target_group_arn,
                'containerName': 'multimodal-lib-prod-app',
                'containerPort': 8000
            }
        ],
        'desiredCount': 1,  # Start with 1, scale up after verification
        'launchType': 'FARGATE',
        'platformVersion': 'LATEST',
        'networkConfiguration': {
            'awsvpcConfiguration': {
                'subnets': current_service['networkConfiguration']['awsvpcConfiguration']['subnets'],
                'securityGroups': current_service['networkConfiguration']['awsvpcConfiguration']['securityGroups'],
                'assignPublicIp': 'DISABLED'
            }
        },
        'healthCheckGracePeriodSeconds': 300,  # 5 minutes for startup
        'deploymentConfiguration': {
            'maximumPercent': 200,
            'minimumHealthyPercent': 100,
            'deploymentCircuitBreaker': {
                'enable': True,
                'rollback': True
            }
        },
        'tags': [
            {'key': 'Name', 'value': new_service_name},
            {'key': 'Environment', 'value': 'production'},
            {'key': 'LoadBalancer', 'value': 'ALB'},
            {'key': 'MigrationDate', 'value': datetime.now().isoformat()},
            {'key': 'Purpose', 'value': 'Blue-Green-Deployment'}
        ]
    }
    
    # Create service
    response = ecs.create_service(**service_config)
    
    service = response['service']
    
    print(f"✅ Service created successfully!")
    print(f"   Service Name: {service['serviceName']}")
    print(f"   Service ARN: {service['serviceArn']}")
    print(f"   Status: {service['status']}")
    print(f"   Desired Count: {service['desiredCount']}")
    
    return service

def wait_for_service_stable(cluster_name: str, service_name: str, timeout_minutes: int = 10):
    """Wait for service to become stable"""
    ecs = boto3.client('ecs')
    
    print(f"\nWaiting for service {service_name} to become stable...")
    print(f"This may take up to {timeout_minutes} minutes...")
    
    try:
        waiter = ecs.get_waiter('services_stable')
        waiter.wait(
            cluster=cluster_name,
            services=[service_name],
            WaiterConfig={
                'Delay': 15,  # Check every 15 seconds
                'MaxAttempts': timeout_minutes * 4  # 15s * 4 = 1 minute
            }
        )
        print(f"✅ Service {service_name} is stable")
        return True
    except Exception as e:
        print(f"⚠️  Service did not stabilize within {timeout_minutes} minutes")
        print(f"   Error: {e}")
        return False

def check_target_health(target_group_arn: str) -> bool:
    """Check if targets are healthy"""
    elbv2 = boto3.client('elbv2')
    
    print(f"\nChecking target health...")
    
    response = elbv2.describe_target_health(
        TargetGroupArn=target_group_arn
    )
    
    if not response['TargetHealthDescriptions']:
        print("⚠️  No targets registered yet")
        return False
    
    for target in response['TargetHealthDescriptions']:
        target_id = target['Target']['Id']
        state = target['TargetHealth']['State']
        reason = target['TargetHealth'].get('Reason', 'N/A')
        description = target['TargetHealth'].get('Description', 'N/A')
        
        if state == 'healthy':
            print(f"✅ Target {target_id}: {state}")
        else:
            print(f"❌ Target {target_id}: {state}")
            print(f"   Reason: {reason}")
            print(f"   Description: {description}")
    
    healthy_count = sum(1 for t in response['TargetHealthDescriptions']
                       if t['TargetHealth']['State'] == 'healthy')
    
    return healthy_count > 0

def get_alb_dns(target_group_arn: str) -> str:
    """Get ALB DNS name from target group"""
    elbv2 = boto3.client('elbv2')
    
    # Get target group details
    target_group = elbv2.describe_target_groups(
        TargetGroupArns=[target_group_arn]
    )['TargetGroups'][0]
    
    # Get load balancer ARN
    if not target_group['LoadBalancerArns']:
        raise Exception("Target group is not attached to any load balancer")
    
    alb_arn = target_group['LoadBalancerArns'][0]
    
    # Get load balancer details
    alb = elbv2.describe_load_balancers(
        LoadBalancerArns=[alb_arn]
    )['LoadBalancers'][0]
    
    return alb['DNSName']

def print_next_steps(alb_dns: str, service_name: str):
    """Print next steps for user"""
    print("\n" + "="*70)
    print("✅ NEW SERVICE CREATED SUCCESSFULLY")
    print("="*70)
    print(f"\nService Name: {service_name}")
    print(f"ALB DNS: {alb_dns}")
    print(f"\nNext Steps:")
    print(f"\n1. Test ALB endpoint directly:")
    print(f"   curl http://{alb_dns}/api/health/simple")
    print(f"   curl http://{alb_dns}/")
    print(f"\n2. Validate service:")
    print(f"   python scripts/validate-alb-service.py")
    print(f"\n3. Update CloudFront origin to ALB DNS:")
    print(f"   python scripts/update-cloudfront-to-working-lb.py \\")
    print(f"     --distribution-id E3NVIH7ET1R4G9 \\")
    print(f"     --origin-dns {alb_dns}")
    print(f"\n4. Test HTTPS URL:")
    print(f"   curl https://d3a2xw711pvw5j.cloudfront.net/api/health/simple")
    print(f"\n5. After 24 hours of stability, scale up new service:")
    print(f"   aws ecs update-service \\")
    print(f"     --cluster multimodal-lib-prod-cluster \\")
    print(f"     --service {service_name} \\")
    print(f"     --desired-count 2")
    print(f"\n6. Scale down old service:")
    print(f"   aws ecs update-service \\")
    print(f"     --cluster multimodal-lib-prod-cluster \\")
    print(f"     --service multimodal-lib-prod-service \\")
    print(f"     --desired-count 0")
    print(f"\n7. After verification, delete old service:")
    print(f"   aws ecs delete-service \\")
    print(f"     --cluster multimodal-lib-prod-cluster \\")
    print(f"     --service multimodal-lib-prod-service \\")
    print(f"     --force")
    print("\n" + "="*70)

def main():
    """Main execution"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Create new ECS service with ALB target group'
    )
    parser.add_argument(
        '--target-group-arn',
        required=True,
        help='ARN of the ALB target group'
    )
    parser.add_argument(
        '--cluster',
        default='multimodal-lib-prod-cluster',
        help='ECS cluster name (default: multimodal-lib-prod-cluster)'
    )
    parser.add_argument(
        '--old-service',
        default='multimodal-lib-prod-service',
        help='Name of existing service (default: multimodal-lib-prod-service)'
    )
    parser.add_argument(
        '--new-service',
        default='multimodal-lib-prod-service-alb',
        help='Name for new service (default: multimodal-lib-prod-service-alb)'
    )
    parser.add_argument(
        '--skip-wait',
        action='store_true',
        help='Skip waiting for service to stabilize'
    )
    
    args = parser.parse_args()
    
    try:
        print("="*70)
        print("CREATE NEW ECS SERVICE WITH ALB")
        print("="*70)
        print(f"\nCluster: {args.cluster}")
        print(f"Old Service: {args.old_service}")
        print(f"New Service: {args.new_service}")
        print(f"Target Group: {args.target_group_arn}")
        
        # Step 1: Get current service configuration
        current_service = get_current_service_config(args.cluster, args.old_service)
        
        # Step 2: Validate target group
        target_group = validate_target_group(args.target_group_arn)
        
        # Step 3: Create new service
        new_service = create_service_with_alb(
            args.cluster,
            args.old_service,
            args.new_service,
            args.target_group_arn,
            current_service
        )
        
        # Step 4: Wait for service to stabilize (unless skipped)
        if not args.skip_wait:
            stable = wait_for_service_stable(args.cluster, args.new_service, timeout_minutes=10)
            
            if not stable:
                print("\n⚠️  Service did not stabilize. Check ECS console for details.")
                print("   You can continue monitoring with:")
                print(f"   aws ecs describe-services --cluster {args.cluster} --services {args.new_service}")
                sys.exit(1)
        
        # Step 5: Check target health
        healthy = check_target_health(args.target_group_arn)
        
        if not healthy:
            print("\n⚠️  Targets are not healthy yet. This may take a few more minutes.")
            print("   Monitor target health with:")
            print(f"   aws elbv2 describe-target-health --target-group-arn {args.target_group_arn}")
        
        # Step 6: Get ALB DNS and print next steps
        alb_dns = get_alb_dns(args.target_group_arn)
        print_next_steps(alb_dns, args.new_service)
        
        # Save results to file
        timestamp = int(time.time())
        result_file = f"ecs-service-alb-creation-{timestamp}.json"
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "cluster": args.cluster,
            "old_service": args.old_service,
            "new_service": args.new_service,
            "target_group_arn": args.target_group_arn,
            "alb_dns": alb_dns,
            "service_arn": new_service['serviceArn'],
            "status": "created",
            "healthy": healthy
        }
        
        with open(result_file, 'w') as f:
            json.dump(result, f, indent=2)
        
        print(f"\nResults saved to: {result_file}")
        
        sys.exit(0 if healthy else 1)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
