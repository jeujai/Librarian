#!/usr/bin/env python3
"""
Patch script to fix the time import issue in the running ECS container
"""

import boto3
import json
import time

def patch_running_container():
    """Patch the running container with the time import fix"""
    
    # Get the running task
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    # List running tasks
    tasks = ecs.list_tasks(
        cluster='multimodal-librarian-learning',
        serviceName='multimodal-librarian-learning-web'
    )
    
    if not tasks['taskArns']:
        print("No running tasks found")
        return False
    
    task_arn = tasks['taskArns'][0]
    print(f"Found running task: {task_arn}")
    
    # Get task details
    task_details = ecs.describe_tasks(
        cluster='multimodal-librarian-learning',
        tasks=[task_arn]
    )
    
    task = task_details['tasks'][0]
    
    # Get the container instance
    container_instance_arn = task['containerInstanceArn']
    
    # Get container instance details
    container_instances = ecs.describe_container_instances(
        cluster='multimodal-librarian-learning',
        containerInstances=[container_instance_arn]
    )
    
    if not container_instances['containerInstances']:
        print("Container instance not found")
        return False
    
    ec2_instance_id = container_instances['containerInstances'][0]['ec2InstanceId']
    print(f"Container running on EC2 instance: {ec2_instance_id}")
    
    # Since we can't directly patch Fargate containers, we need to update the task definition
    # and force a new deployment
    
    print("Creating updated task definition with the fix...")
    
    # Get current task definition
    task_def_arn = task['taskDefinitionArn']
    task_def_response = ecs.describe_task_definition(taskDefinition=task_def_arn)
    task_def = task_def_response['taskDefinition']
    
    # Create new task definition (this will trigger a new deployment)
    new_task_def = {
        'family': task_def['family'],
        'taskRoleArn': task_def.get('taskRoleArn'),
        'executionRoleArn': task_def.get('executionRoleArn'),
        'networkMode': task_def.get('networkMode'),
        'requiresCompatibilities': task_def.get('requiresCompatibilities'),
        'cpu': task_def.get('cpu'),
        'memory': task_def.get('memory'),
        'containerDefinitions': task_def['containerDefinitions']
    }
    
    # Add a small environment variable to force a new deployment
    for container in new_task_def['containerDefinitions']:
        if 'environment' not in container:
            container['environment'] = []
        
        # Add timestamp to force new deployment
        container['environment'].append({
            'name': 'PATCH_TIMESTAMP',
            'value': str(int(time.time()))
        })
    
    # Register new task definition
    response = ecs.register_task_definition(**new_task_def)
    new_task_def_arn = response['taskDefinition']['taskDefinitionArn']
    
    print(f"Created new task definition: {new_task_def_arn}")
    
    # Update service to use new task definition
    ecs.update_service(
        cluster='multimodal-librarian-learning',
        service='multimodal-librarian-learning-web',
        taskDefinition=new_task_def_arn,
        forceNewDeployment=True
    )
    
    print("Service update initiated. This will create a new container with the latest code.")
    print("The fix should be applied when the new container starts.")
    
    return True

if __name__ == "__main__":
    print("🔧 Patching running container with time import fix...")
    
    if patch_running_container():
        print("✅ Patch deployment initiated successfully!")
        print("Monitor the service deployment with: aws ecs describe-services --cluster multimodal-librarian-learning --services multimodal-librarian-learning-web")
    else:
        print("❌ Failed to patch container")