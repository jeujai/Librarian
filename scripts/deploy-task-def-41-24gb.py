#!/usr/bin/env python3
"""
Deploy task definition 41 with 24GB memory.
Increases memory from 20GB to 24GB (24576 MB).
"""

import boto3
import json
from datetime import datetime

def deploy_task_def_41():
    """Create and deploy task definition 41 with 24GB memory."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("=" * 80)
    print("Deploying Task Definition 41 with 24GB Memory")
    print("=" * 80)
    print()
    print("Upgrading from 20GB to 24GB memory")
    print("Creating task definition with increased memory allocation...")
    print()
    
    # Get current task definition as base
    print("1. Getting current task definition...")
    try:
        current_task_def = ecs.describe_task_definition(
            taskDefinition='multimodal-lib-prod-app:40'
        )['taskDefinition']
        
        print(f"   ✓ Retrieved task definition 40 as base")
        print(f"   Current Memory: {current_task_def['memory']} MB")
        print(f"   Current CPU: {current_task_def['cpu']} units")
    except Exception as e:
        print(f"   ✗ Error: {e}")
        return False
    
    # Create new task definition with 24GB memory
    print("\n2. Creating new task definition with 24GB memory...")
    
    # Copy container definition and update if needed
    container_def = current_task_def['containerDefinitions'][0].copy()
    
    # Memory is 24GB = 24576 MB
    # CPU stays at 4096 (4 vCPU) - valid pairing for 24GB
    new_memory = "24576"
    new_cpu = "4096"
    
    try:
        response = ecs.register_task_definition(
            family='multimodal-lib-prod-app',
            taskRoleArn=current_task_def['taskRoleArn'],
            executionRoleArn=current_task_def['executionRoleArn'],
            networkMode=current_task_def['networkMode'],
            containerDefinitions=[container_def],
            requiresCompatibilities=current_task_def['requiresCompatibilities'],
            cpu=new_cpu,
            memory=new_memory
        )
        
        new_revision = response['taskDefinition']['revision']
        print(f"   ✓ Created task definition revision {new_revision}")
        print(f"\n   Configuration:")
        print(f"     Memory: {new_memory} MB (24 GB)")
        print(f"     CPU: {new_cpu} units (4 vCPU)")
        print(f"     Network Mode: {current_task_def['networkMode']}")
        
        # Show health check configuration if present
        if 'healthCheck' in container_def:
            health_check = container_def['healthCheck']
            print(f"\n   Health Check:")
            print(f"     Command: {' '.join(health_check['command'])}")
            print(f"     Start Period: {health_check.get('startPeriod', 'N/A')}s")
        
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
    print("  - Memory: 24 GB (24576 MB)")
    print("  - CPU: 4 vCPU (4096 units)")
    print("  - Increased capacity for model loading and processing")
    print()
    print("Monitor deployment with:")
    print("  aws ecs describe-services --cluster multimodal-lib-prod-cluster --services multimodal-lib-prod-service")
    print()
    print("Check task status:")
    print("  aws ecs list-tasks --cluster multimodal-lib-prod-cluster --service-name multimodal-lib-prod-service")
    print()
    print("Check logs:")
    print("  aws logs tail /ecs/multimodal-lib-prod-app --follow")
    print("=" * 80)
    
    return True

if __name__ == '__main__':
    success = deploy_task_def_41()
    exit(0 if success else 1)
