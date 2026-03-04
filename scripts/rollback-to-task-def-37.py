#!/usr/bin/env python3
"""
Rollback to task definition 37 (the working one without curl).
Task definition 38 failed because it uses curl which isn't installed.
"""

import boto3
import json
from datetime import datetime

def rollback_to_task_37():
    """Rollback ECS service to task definition 37."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("=" * 80)
    print("Rolling Back to Task Definition 37")
    print("=" * 80)
    print()
    print("Task Definition 38 failed because it uses curl in health check")
    print("Task Definition 37 is the working version (Python-based health check)")
    print()
    
    # Update service to use task definition 37
    print("1. Updating service to use task definition 37...")
    try:
        response = ecs.update_service(
            cluster='multimodal-lib-prod-cluster',
            service='multimodal-lib-prod-service',
            taskDefinition='multimodal-lib-prod-task:37',
            forceNewDeployment=True
        )
        
        print("   ✓ Service updated")
        print(f"   Task Definition: {response['service']['taskDefinition']}")
        print(f"   Desired Count: {response['service']['desiredCount']}")
        print(f"   Running Count: {response['service']['runningCount']}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False
    
    # Wait a moment and check status
    print("\n2. Checking deployment status...")
    import time
    time.sleep(5)
    
    try:
        service = ecs.describe_services(
            cluster='multimodal-lib-prod-cluster',
            services=['multimodal-lib-prod-service']
        )['services'][0]
        
        print(f"   Status: {service['status']}")
        print(f"   Running: {service['runningCount']}/{service['desiredCount']}")
        print(f"   Deployments: {len(service['deployments'])}")
        
        for deployment in service['deployments']:
            print(f"\n   Deployment:")
            print(f"     Task Definition: {deployment['taskDefinition'].split('/')[-1]}")
            print(f"     Status: {deployment['status']}")
            print(f"     Desired: {deployment['desiredCount']}")
            print(f"     Running: {deployment['runningCount']}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n" + "=" * 80)
    print("Rollback initiated successfully!")
    print()
    print("The service will now deploy task definition 37.")
    print("This version uses Python for health checks (no curl required).")
    print()
    print("Monitor deployment with:")
    print("  aws ecs describe-services --cluster multimodal-lib-prod-cluster --services multimodal-lib-prod-service")
    print()
    print("Test connectivity after deployment:")
    print("  curl http://multimodal-lib-prod-nlb-9f03ee5dda51903f.elb.us-east-1.amazonaws.com/api/health/simple")
    print("=" * 80)
    
    return True

if __name__ == '__main__':
    success = rollback_to_task_37()
    exit(0 if success else 1)
