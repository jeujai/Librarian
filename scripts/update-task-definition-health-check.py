#!/usr/bin/env python3
"""
Update ECS Task Definition Health Check Path

This script updates the health check path in the ECS task definition
from /health/simple to /api/health/simple and registers a new revision.
"""

import boto3
import json
import sys
from datetime import datetime

def update_task_definition_health_check():
    """Update the task definition health check path."""
    
    ecs_client = boto3.client('ecs', region_name='us-east-1')
    
    task_definition_name = 'multimodal-lib-prod-app'
    
    print(f"Fetching current task definition: {task_definition_name}")
    
    # Get the current task definition
    response = ecs_client.describe_task_definition(
        taskDefinition=task_definition_name
    )
    
    task_def = response['taskDefinition']
    current_revision = task_def['revision']
    
    print(f"Current revision: {current_revision}")
    
    # Check current health check configuration
    container_def = task_def['containerDefinitions'][0]
    current_health_check = container_def.get('healthCheck', {})
    
    print(f"\nCurrent health check configuration:")
    print(json.dumps(current_health_check, indent=2))
    
    # Update the health check command
    if 'command' in current_health_check:
        current_command = current_health_check['command']
        print(f"\nCurrent health check command: {current_command}")
        
        # Update the command to use /api/health/simple
        new_command = [
            "CMD-SHELL",
            "curl -f http://127.0.0.1:8000/api/health/simple || exit 1"
        ]
        
        print(f"New health check command: {new_command}")
        
        # Check if update is needed
        if current_command == new_command:
            print("\n✓ Health check path is already set to /api/health/simple")
            print("No update needed.")
            return
        
        # Update the health check
        container_def['healthCheck']['command'] = new_command
    else:
        print("\n⚠ No health check found in task definition")
        print("Adding health check with /api/health/simple")
        
        container_def['healthCheck'] = {
            'command': [
                "CMD-SHELL",
                "curl -f http://127.0.0.1:8000/api/health/simple || exit 1"
            ],
            'interval': 30,
            'timeout': 5,
            'retries': 3,
            'startPeriod': 60
        }
    
    # Prepare the new task definition (remove read-only fields)
    new_task_def = {
        'family': task_def['family'],
        'taskRoleArn': task_def.get('taskRoleArn'),
        'executionRoleArn': task_def.get('executionRoleArn'),
        'networkMode': task_def.get('networkMode'),
        'containerDefinitions': task_def['containerDefinitions'],
        'volumes': task_def.get('volumes', []),
        'requiresCompatibilities': task_def.get('requiresCompatibilities', []),
        'cpu': task_def.get('cpu'),
        'memory': task_def.get('memory'),
    }
    
    # Remove None values
    new_task_def = {k: v for k, v in new_task_def.items() if v is not None}
    
    print(f"\nRegistering new task definition revision...")
    
    # Register the new task definition
    register_response = ecs_client.register_task_definition(**new_task_def)
    
    new_revision = register_response['taskDefinition']['revision']
    new_task_def_arn = register_response['taskDefinition']['taskDefinitionArn']
    
    print(f"✓ New task definition registered: {task_definition_name}:{new_revision}")
    print(f"  ARN: {new_task_def_arn}")
    
    # Save the update details
    update_details = {
        'timestamp': datetime.now().isoformat(),
        'task_definition': task_definition_name,
        'old_revision': current_revision,
        'new_revision': new_revision,
        'new_task_definition_arn': new_task_def_arn,
        'health_check_update': {
            'old_path': '/health/simple',
            'new_path': '/api/health/simple',
            'command': new_command
        }
    }
    
    output_file = f'task-definition-health-check-update-{int(datetime.now().timestamp())}.json'
    with open(output_file, 'w') as f:
        json.dump(update_details, f, indent=2)
    
    print(f"\n✓ Update details saved to: {output_file}")
    
    print("\n" + "=" * 80)
    print("NEXT STEPS:")
    print("=" * 80)
    print(f"1. Update the ECS service to use the new task definition:")
    print(f"   aws ecs update-service \\")
    print(f"     --cluster multimodal-lib-prod-cluster \\")
    print(f"     --service multimodal-lib-prod-service-alb \\")
    print(f"     --task-definition {task_definition_name}:{new_revision} \\")
    print(f"     --force-new-deployment \\")
    print(f"     --region us-east-1")
    print()
    print(f"2. Monitor the deployment:")
    print(f"   aws ecs describe-services \\")
    print(f"     --cluster multimodal-lib-prod-cluster \\")
    print(f"     --services multimodal-lib-prod-service-alb \\")
    print(f"     --region us-east-1")
    print("=" * 80)
    
    return update_details

if __name__ == '__main__':
    try:
        result = update_task_definition_health_check()
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
