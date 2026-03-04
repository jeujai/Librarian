#!/usr/bin/env python3
"""
Deploy task definition 39 with curl-based health check.
Curl is already installed in the Dockerfile, so we can use it.
"""

import boto3
import json
from datetime import datetime

def deploy_task_def_39():
    """Create and deploy task definition 39 with curl health check."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("=" * 80)
    print("Deploying Task Definition 39 with Curl Health Check")
    print("=" * 80)
    print()
    print("Curl is already installed in the Dockerfile (line 28)")
    print("Creating task definition with curl-based health check...")
    print()
    
    # Get current task definition as base
    print("1. Getting current task definition...")
    try:
        current_task_def = ecs.describe_task_definition(
            taskDefinition='multimodal-lib-prod-app:37'
        )['taskDefinition']
        
        print(f"   ✓ Retrieved task definition 37 as base")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False
    
    # Create new task definition with curl health check
    print("\n2. Creating new task definition with curl health check...")
    
    # Update health check to use curl
    container_def = current_task_def['containerDefinitions'][0].copy()
    container_def['healthCheck'] = {
        'command': [
            'CMD-SHELL',
            'curl -f http://localhost:8000/api/health/simple || exit 1'
        ],
        'interval': 30,
        'timeout': 15,
        'retries': 5,
        'startPeriod': 300
    }
    
    try:
        response = ecs.register_task_definition(
            family='multimodal-lib-prod-app',
            taskRoleArn=current_task_def['taskRoleArn'],
            executionRoleArn=current_task_def['executionRoleArn'],
            networkMode=current_task_def['networkMode'],
            containerDefinitions=[container_def],
            requiresCompatibilities=current_task_def['requiresCompatibilities'],
            cpu=current_task_def['cpu'],
            memory=current_task_def['memory']
        )
        
        new_revision = response['taskDefinition']['revision']
        print(f"   ✓ Created task definition revision {new_revision}")
        
        # Show health check configuration
        health_check = response['taskDefinition']['containerDefinitions'][0]['healthCheck']
        print(f"\n   Health Check Configuration:")
        print(f"     Command: {' '.join(health_check['command'])}")
        print(f"     Interval: {health_check['interval']}s")
        print(f"     Timeout: {health_check['timeout']}s")
        print(f"     Retries: {health_check['retries']}")
        print(f"     Start Period: {health_check['startPeriod']}s")
        
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False
    
    # Update service to use new task definition
    print(f"\n3. Updating service to use task definition {new_revision}...")
    try:
        response = ecs.update_service(
            cluster='multimodal-lib-prod-cluster',
            service='multimodal-lib-prod-service',
            taskDefinition=f'multimodal-lib-prod-app:{new_revision}',
            forceNewDeployment=True
        )
        
        print("   ✓ Service updated")
        print(f"   Task Definition: {response['service']['taskDefinition']}")
        print(f"   Desired Count: {response['service']['desiredCount']}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False
    
    print("\n" + "=" * 80)
    print("Deployment initiated successfully!")
    print()
    print(f"Task definition {new_revision} is now deploying with:")
    print("  - Curl-based health check")
    print("  - Health check path: /api/health/simple")
    print("  - 5 minute start period for model loading")
    print()
    print("Monitor deployment with:")
    print("  aws ecs describe-services --cluster multimodal-lib-prod-cluster --services multimodal-lib-prod-service")
    print()
    print("Check logs:")
    print("  aws logs tail /ecs/multimodal-lib-prod-app --follow")
    print()
    print("Test connectivity after deployment:")
    print("  curl http://multimodal-lib-prod-nlb-9f03ee5dda51903f.elb.us-east-1.amazonaws.com/api/health/simple")
    print("=" * 80)
    
    return True

if __name__ == '__main__':
    success = deploy_task_def_39()
    exit(0 if success else 1)
