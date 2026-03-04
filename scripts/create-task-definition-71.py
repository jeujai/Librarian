#!/usr/bin/env python3
"""
Create Task Definition 71 with Corrected Health Check Path

This script creates task definition revision 71 by cloning revision 70
and fixing the health check path to include the /api prefix.

Change: /health/simple → /api/health/simple
"""

import boto3
import json
from datetime import datetime

REGION = "us-east-1"
SOURCE_TASK_DEF = "multimodal-lib-prod-app:70"

def create_task_definition_71():
    """Create task definition 71 with corrected health check path"""
    
    print(f"\n{'='*70}")
    print("CREATE TASK DEFINITION 71")
    print(f"{'='*70}")
    print(f"Source: {SOURCE_TASK_DEF}")
    print(f"Change: Health check path /health/simple → /api/health/simple")
    print(f"{'='*70}\n")
    
    ecs_client = boto3.client('ecs', region_name=REGION)
    
    # Get task definition 70
    print("Step 1: Retrieving task definition 70...")
    response = ecs_client.describe_task_definition(
        taskDefinition=SOURCE_TASK_DEF
    )
    
    task_def = response['taskDefinition']
    print(f"✓ Retrieved task definition: {task_def['family']}:{task_def['revision']}")
    
    # Show current health check
    current_health_check = task_def['containerDefinitions'][0]['healthCheck']
    current_command = ' '.join(current_health_check['command'])
    print(f"\nCurrent health check command:")
    print(f"  {current_command}")
    
    # Prepare new task definition
    print("\nStep 2: Preparing new task definition...")
    
    new_task_def = {
        'family': task_def['family'],
        'taskRoleArn': task_def['taskRoleArn'],
        'executionRoleArn': task_def['executionRoleArn'],
        'networkMode': task_def['networkMode'],
        'containerDefinitions': task_def['containerDefinitions'],
        'volumes': task_def.get('volumes', []),
        'requiresCompatibilities': task_def['requiresCompatibilities'],
        'cpu': task_def['cpu'],
        'memory': task_def['memory']
    }
    
    # Update health check command
    new_health_check_command = [
        "CMD-SHELL",
        "curl -f http://localhost:8000/api/health/simple || exit 1"
    ]
    
    new_task_def['containerDefinitions'][0]['healthCheck']['command'] = new_health_check_command
    
    print(f"✓ Updated health check command:")
    print(f"  {' '.join(new_health_check_command)}")
    
    # Register new task definition
    print("\nStep 3: Registering new task definition...")
    
    response = ecs_client.register_task_definition(**new_task_def)
    
    new_task_def_info = response['taskDefinition']
    new_revision = new_task_def_info['revision']
    new_arn = new_task_def_info['taskDefinitionArn']
    
    print(f"✓ Successfully created task definition revision {new_revision}")
    print(f"✓ ARN: {new_arn}")
    
    # Verify the health check
    print("\nStep 4: Verifying health check configuration...")
    verified_command = ' '.join(new_task_def_info['containerDefinitions'][0]['healthCheck']['command'])
    print(f"  {verified_command}")
    
    if '/api/health/simple' in verified_command:
        print(f"✓ Health check path is correctly set to /api/health/simple")
    else:
        print(f"⚠ Warning: Health check path verification failed")
    
    # Save creation record
    timestamp = int(datetime.now().timestamp())
    record = {
        "timestamp": datetime.now().isoformat(),
        "source_revision": 70,
        "new_revision": new_revision,
        "task_definition_arn": new_arn,
        "changes": {
            "health_check_path": {
                "old": "/health/simple",
                "new": "/api/health/simple",
                "reason": "Fixed missing /api prefix in health check path"
            }
        },
        "preserved_settings": {
            "family": new_task_def_info['family'],
            "cpu": new_task_def_info['cpu'],
            "memory": new_task_def_info['memory'],
            "network_mode": new_task_def_info['networkMode'],
            "image": new_task_def_info['containerDefinitions'][0]['image']
        }
    }
    
    filename = f"task-definition-71-creation.json"
    with open(filename, 'w') as f:
        json.dump(record, f, indent=2)
    
    print(f"\n✓ Creation record saved to: {filename}")
    
    # Summary
    print(f"\n{'='*70}")
    print("TASK DEFINITION 71 CREATED SUCCESSFULLY")
    print(f"{'='*70}")
    print(f"Revision: {new_revision}")
    print(f"ARN: {new_arn}")
    print(f"Health Check: /api/health/simple")
    print(f"\nNext step: Deploy this task definition to your ECS service")
    print(f"{'='*70}\n")
    
    return new_arn

if __name__ == "__main__":
    try:
        create_task_definition_71()
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        exit(1)
