#!/usr/bin/env python3
"""
Deploy Health Check Update

This script updates the task definition health check path and deploys it to the ECS service.
"""

import boto3
import json
import sys
import time
from datetime import datetime

def wait_for_deployment(ecs_client, cluster_name, service_name, timeout=600):
    """Wait for the service deployment to complete."""
    
    print(f"\nMonitoring deployment progress...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        response = ecs_client.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        if not response['services']:
            print("✗ Service not found")
            return False
        
        service = response['services'][0]
        deployments = service['deployments']
        
        # Check if there's only one deployment (the new one)
        if len(deployments) == 1:
            deployment = deployments[0]
            if deployment['status'] == 'PRIMARY':
                running_count = deployment['runningCount']
                desired_count = deployment['desiredCount']
                
                print(f"✓ Deployment complete: {running_count}/{desired_count} tasks running")
                return True
        
        # Print current status
        for deployment in deployments:
            status = deployment['status']
            running = deployment['runningCount']
            desired = deployment['desiredCount']
            print(f"  {status}: {running}/{desired} tasks running")
        
        time.sleep(10)
    
    print(f"✗ Deployment timeout after {timeout} seconds")
    return False

def deploy_health_check_update():
    """Deploy the health check update to the ECS service."""
    
    ecs_client = boto3.client('ecs', region_name='us-east-1')
    
    cluster_name = 'multimodal-lib-prod-cluster'
    service_name = 'multimodal-lib-prod-service-alb'
    task_definition_name = 'multimodal-lib-prod-app'
    
    print("=" * 80)
    print("DEPLOYING HEALTH CHECK UPDATE")
    print("=" * 80)
    
    # Step 1: Update the task definition
    print("\nStep 1: Updating task definition health check path...")
    
    # Get the current task definition
    response = ecs_client.describe_task_definition(
        taskDefinition=task_definition_name
    )
    
    task_def = response['taskDefinition']
    current_revision = task_def['revision']
    
    print(f"Current task definition: {task_definition_name}:{current_revision}")
    
    # Check current health check
    container_def = task_def['containerDefinitions'][0]
    current_health_check = container_def.get('healthCheck', {})
    current_command = current_health_check.get('command', [])
    
    print(f"Current health check command: {current_command}")
    
    # Update the health check command
    new_command = [
        "CMD-SHELL",
        "curl -f http://127.0.0.1:8000/api/health/simple || exit 1"
    ]
    
    if current_command == new_command:
        print("✓ Health check path is already set to /api/health/simple")
        print(f"Using existing task definition: {task_definition_name}:{current_revision}")
        new_revision = current_revision
        new_task_def_arn = task_def['taskDefinitionArn']
    else:
        print(f"Updating health check command to: {new_command}")
        
        # Update the health check
        container_def['healthCheck']['command'] = new_command
        
        # Prepare the new task definition
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
        
        # Register the new task definition
        register_response = ecs_client.register_task_definition(**new_task_def)
        
        new_revision = register_response['taskDefinition']['revision']
        new_task_def_arn = register_response['taskDefinition']['taskDefinitionArn']
        
        print(f"✓ New task definition registered: {task_definition_name}:{new_revision}")
    
    # Step 2: Update the ECS service
    print(f"\nStep 2: Updating ECS service to use new task definition...")
    
    update_response = ecs_client.update_service(
        cluster=cluster_name,
        service=service_name,
        taskDefinition=f"{task_definition_name}:{new_revision}",
        forceNewDeployment=True
    )
    
    print(f"✓ Service update initiated")
    print(f"  Service: {service_name}")
    print(f"  Task Definition: {task_definition_name}:{new_revision}")
    
    # Step 3: Wait for deployment to complete
    print(f"\nStep 3: Waiting for deployment to complete...")
    
    success = wait_for_deployment(ecs_client, cluster_name, service_name)
    
    # Save deployment details
    deployment_details = {
        'timestamp': datetime.now().isoformat(),
        'cluster': cluster_name,
        'service': service_name,
        'task_definition': f"{task_definition_name}:{new_revision}",
        'task_definition_arn': new_task_def_arn,
        'health_check_update': {
            'old_path': '/health/simple',
            'new_path': '/api/health/simple',
            'command': new_command
        },
        'deployment_success': success
    }
    
    output_file = f'health-check-deployment-{int(datetime.now().timestamp())}.json'
    with open(output_file, 'w') as f:
        json.dump(deployment_details, f, indent=2)
    
    print(f"\n✓ Deployment details saved to: {output_file}")
    
    if success:
        print("\n" + "=" * 80)
        print("✓ DEPLOYMENT SUCCESSFUL")
        print("=" * 80)
        print(f"The service is now using task definition: {task_definition_name}:{new_revision}")
        print(f"Health check endpoint: /api/health/simple")
        print("=" * 80)
    else:
        print("\n" + "=" * 80)
        print("⚠ DEPLOYMENT IN PROGRESS")
        print("=" * 80)
        print("The deployment is still in progress. Monitor it with:")
        print(f"  aws ecs describe-services \\")
        print(f"    --cluster {cluster_name} \\")
        print(f"    --services {service_name} \\")
        print(f"    --region us-east-1")
        print("=" * 80)
    
    return deployment_details

if __name__ == '__main__':
    try:
        result = deploy_health_check_update()
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
