#!/usr/bin/env python3
"""
Fix Log Configuration and Redeploy

This script fixes the log configuration issue and redeploys with the correct settings.
"""

import boto3
import json
from datetime import datetime

def fix_and_redeploy():
    """Fix log configuration and create new task definition."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("=" * 80)
    print("FIXING LOG CONFIGURATION AND REDEPLOYING")
    print("=" * 80)
    
    # Get current task definition
    print("\n1. Getting current task definition...")
    response = ecs.describe_task_definition(taskDefinition='multimodal-lib-prod-app:21')
    task_def = response['taskDefinition']
    
    print(f"Current task definition: {task_def['family']}:{task_def['revision']}")
    print(f"Current log group: {task_def['containerDefinitions'][0]['logConfiguration']['options']['awslogs-group']}")
    
    # Create new task definition with correct log group
    print("\n2. Creating new task definition with correct log configuration...")
    
    container_def = task_def['containerDefinitions'][0].copy()
    
    # Fix log configuration
    container_def['logConfiguration']['options']['awslogs-group'] = '/ecs/multimodal-lib-prod-app'
    
    # Remove fields that can't be in registerTaskDefinition
    fields_to_remove = ['taskDefinitionArn', 'revision', 'status', 'requiresAttributes', 
                       'compatibilities', 'registeredAt', 'registeredBy']
    for field in fields_to_remove:
        task_def.pop(field, None)
    
    # Register new task definition
    response = ecs.register_task_definition(
        family=task_def['family'],
        taskRoleArn=task_def.get('taskRoleArn'),
        executionRoleArn=task_def.get('executionRoleArn'),
        networkMode=task_def['networkMode'],
        containerDefinitions=[container_def],
        volumes=task_def.get('volumes', []),
        placementConstraints=task_def.get('placementConstraints', []),
        requiresCompatibilities=task_def.get('requiresCompatibilities', ['FARGATE']),
        cpu=task_def['cpu'],
        memory=task_def['memory']
    )
    
    new_task_def_arn = response['taskDefinition']['taskDefinitionArn']
    new_revision = response['taskDefinition']['revision']
    
    print(f"✓ Created new task definition: {task_def['family']}:{new_revision}")
    print(f"✓ Fixed log group: /ecs/multimodal-lib-prod-app")
    
    # Update service
    print("\n3. Updating service with new task definition...")
    response = ecs.update_service(
        cluster='multimodal-lib-prod-cluster',
        service='multimodal-lib-prod-service',
        taskDefinition=new_task_def_arn,
        forceNewDeployment=True
    )
    
    print(f"✓ Service updated successfully")
    print(f"✓ New deployment initiated")
    
    # Save deployment info
    deployment_info = {
        "timestamp": datetime.now().isoformat(),
        "action": "fix_log_configuration",
        "old_task_definition": f"{task_def['family']}:21",
        "new_task_definition": f"{task_def['family']}:{new_revision}",
        "fix_applied": "Changed log group from /ecs/multimodal-lib-prod to /ecs/multimodal-lib-prod-app",
        "status": "deployed"
    }
    
    filename = f"log-config-fix-{int(datetime.now().timestamp())}.json"
    with open(filename, 'w') as f:
        json.dump(deployment_info, f, indent=2)
    
    print(f"\n✓ Deployment info saved to {filename}")
    
    print("\n" + "=" * 80)
    print("DEPLOYMENT SUMMARY")
    print("=" * 80)
    print(f"Task Definition: {task_def['family']}:{new_revision}")
    print(f"Docker Image: {container_def['image']}")
    print(f"Log Group: /ecs/multimodal-lib-prod-app")
    print(f"Health Check: {container_def['healthCheck']['command']}")
    print(f"Start Period: {container_def['healthCheck']['startPeriod']}s")
    print("\nNext steps:")
    print("1. Monitor deployment: python3 scripts/monitor-deployment-progress.py")
    print("2. Check logs: aws logs tail /ecs/multimodal-lib-prod-app --follow")
    print("3. Verify health: curl http://<load-balancer-url>/health")
    print("=" * 80)

if __name__ == "__main__":
    fix_and_redeploy()
