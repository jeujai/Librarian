#!/usr/bin/env python3
"""
Switch ECS service from NLB to ALB target group.

This updates the ECS service to register tasks with the ALB target group
instead of the NLB target group.
"""

import boto3
import json
import time
from datetime import datetime

def switch_ecs_to_alb():
    """Switch ECS service to use ALB target group."""
    
    ecs = boto3.client('ecs')
    elbv2 = boto3.client('elbv2')
    
    cluster_name = 'multimodal-lib-prod-cluster'
    service_name = 'multimodal-lib-prod-service'
    
    print("=" * 80)
    print("Switch ECS Service from NLB to ALB")
    print("=" * 80)
    
    # Get ALB target group
    print("\n📋 Finding ALB target group...")
    alb_arn = elbv2.describe_load_balancers(
        Names=['multimodal-lib-prod-alb-v2']
    )['LoadBalancers'][0]['LoadBalancerArn']
    
    tgs = elbv2.describe_target_groups(LoadBalancerArn=alb_arn)
    alb_tg_arn = tgs['TargetGroups'][0]['TargetGroupArn']
    alb_tg_name = tgs['TargetGroups'][0]['TargetGroupName']
    
    print(f"   ALB Target Group: {alb_tg_name}")
    print(f"   ARN: {alb_tg_arn}")
    
    # Get current service configuration
    print("\n📋 Getting current service configuration...")
    service = ecs.describe_services(
        cluster=cluster_name,
        services=[service_name]
    )['services'][0]
    
    current_tg = service['loadBalancers'][0]['targetGroupArn']
    container_name = service['loadBalancers'][0]['containerName']
    container_port = service['loadBalancers'][0]['containerPort']
    
    print(f"   Current Target Group: {current_tg}")
    print(f"   Container: {container_name}:{container_port}")
    
    # Update service
    print(f"\n🔧 Updating service to use ALB...")
    
    response = ecs.update_service(
        cluster=cluster_name,
        service=service_name,
        loadBalancers=[
            {
                'targetGroupArn': alb_tg_arn,
                'containerName': container_name,
                'containerPort': container_port
            }
        ],
        forceNewDeployment=True
    )
    
    print(f"\n✅ Service updated successfully!")
    print(f"   Service: {service_name}")
    print(f"   Old Target Group: {current_tg.split('/')[-2]}")
    print(f"   New Target Group: {alb_tg_name}")
    print(f"   Status: {response['service']['status']}")
    
    print(f"\n⏳ Deployment in progress...")
    print(f"   ECS will drain old tasks and start new ones")
    print(f"   This typically takes 2-5 minutes")
    
    # Save results
    timestamp = int(time.time())
    results = {
        'timestamp': datetime.now().isoformat(),
        'cluster': cluster_name,
        'service': service_name,
        'old_target_group': current_tg,
        'new_target_group': alb_tg_arn,
        'container': f'{container_name}:{container_port}'
    }
    
    filename = f'ecs-alb-switch-{timestamp}.json'
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n💾 Results saved to: {filename}")
    
    return results

if __name__ == '__main__':
    switch_ecs_to_alb()
