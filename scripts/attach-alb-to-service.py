#!/usr/bin/env python3
"""
Attach ALB to existing ECS service by recreating it

This script:
1. Gets current service configuration
2. Scales service to 0
3. Deletes the service
4. Recreates service with ALB configuration
"""

import boto3
import json
import time
import sys
from datetime import datetime

# AWS clients
ecs = boto3.client('ecs', region_name='us-east-1')
elbv2 = boto3.client('elbv2', region_name='us-east-1')

# Configuration
CLUSTER_NAME = "multimodal-lib-prod-cluster"
SERVICE_NAME = "multimodal-lib-prod-service"
TARGET_GROUP_NAME = "multimodal-lib-prod-tg"
CONTAINER_NAME = "multimodal-lib-prod-app"
CONTAINER_PORT = 8000

def log(message):
    """Print timestamped log message."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)

def get_target_group_arn():
    """Get target group ARN."""
    try:
        response = elbv2.describe_target_groups(
            Names=[TARGET_GROUP_NAME]
        )
        if response['TargetGroups']:
            return response['TargetGroups'][0]['TargetGroupArn']
        else:
            raise Exception(f"Target group {TARGET_GROUP_NAME} not found")
    except Exception as e:
        log(f"Error getting target group: {e}")
        raise

def get_service_config():
    """Get current service configuration."""
    log("Getting current service configuration...")
    
    response = ecs.describe_services(
        cluster=CLUSTER_NAME,
        services=[SERVICE_NAME]
    )
    
    if not response['services']:
        raise Exception(f"Service {SERVICE_NAME} not found")
    
    service = response['services'][0]
    
    config = {
        'taskDefinition': service['taskDefinition'],
        'desiredCount': service['desiredCount'],
        'launchType': service.get('launchType', 'FARGATE'),
        'platformVersion': service.get('platformVersion', 'LATEST'),
        'networkConfiguration': service['networkConfiguration'],
        'deploymentConfiguration': service.get('deploymentConfiguration', {}),
        'placementConstraints': service.get('placementConstraints', []),
        'placementStrategy': service.get('placementStrategy', []),
        'schedulingStrategy': service.get('schedulingStrategy', 'REPLICA'),
        'enableECSManagedTags': service.get('enableECSManagedTags', False),
        'propagateTags': service.get('propagateTags', 'NONE'),
        'enableExecuteCommand': service.get('enableExecuteCommand', False)
    }
    
    log(f"Current configuration:")
    log(f"  Task Definition: {config['taskDefinition']}")
    log(f"  Desired Count: {config['desiredCount']}")
    log(f"  Launch Type: {config['launchType']}")
    
    return config

def scale_service_to_zero():
    """Scale service to 0 tasks."""
    log("Scaling service to 0 tasks...")
    
    ecs.update_service(
        cluster=CLUSTER_NAME,
        service=SERVICE_NAME,
        desiredCount=0
    )
    
    log("Waiting for tasks to stop...")
    time.sleep(10)
    
    # Wait for all tasks to stop
    while True:
        response = ecs.list_tasks(
            cluster=CLUSTER_NAME,
            serviceName=SERVICE_NAME
        )
        
        if not response['taskArns']:
            log("All tasks stopped")
            break
        
        log(f"Waiting for {len(response['taskArns'])} tasks to stop...")
        time.sleep(5)

def delete_service():
    """Delete the service."""
    log("Deleting service...")
    
    ecs.delete_service(
        cluster=CLUSTER_NAME,
        service=SERVICE_NAME,
        force=True
    )
    
    log("Service deleted")
    log("Waiting for service to be fully removed...")
    time.sleep(10)

def create_service_with_alb(config, tg_arn):
    """Create service with ALB configuration."""
    log("Creating service with ALB configuration...")
    
    create_params = {
        'cluster': CLUSTER_NAME,
        'serviceName': SERVICE_NAME,
        'taskDefinition': config['taskDefinition'],
        'loadBalancers': [
            {
                'targetGroupArn': tg_arn,
                'containerName': CONTAINER_NAME,
                'containerPort': CONTAINER_PORT
            }
        ],
        'desiredCount': config['desiredCount'],
        'launchType': config['launchType'],
        'platformVersion': config['platformVersion'],
        'networkConfiguration': config['networkConfiguration'],
        'healthCheckGracePeriodSeconds': 120,
        'schedulingStrategy': config['schedulingStrategy'],
        'enableECSManagedTags': config['enableECSManagedTags'],
        'propagateTags': config['propagateTags'],
        'enableExecuteCommand': config['enableExecuteCommand']
    }
    
    # Add optional parameters if they exist
    if config.get('deploymentConfiguration'):
        create_params['deploymentConfiguration'] = config['deploymentConfiguration']
    
    if config.get('placementConstraints'):
        create_params['placementConstraints'] = config['placementConstraints']
    
    if config.get('placementStrategy'):
        create_params['placementStrategy'] = config['placementStrategy']
    
    response = ecs.create_service(**create_params)
    
    log(f"Service created: {response['service']['serviceArn']}")
    log("Waiting for service to stabilize...")
    
    # Wait for service to stabilize
    waiter = ecs.get_waiter('services_stable')
    waiter.wait(
        cluster=CLUSTER_NAME,
        services=[SERVICE_NAME]
    )
    
    log("Service is now stable")

def main():
    """Main execution function."""
    log("=" * 80)
    log("Attaching ALB to ECS Service")
    log("=" * 80)
    log("")
    log("WARNING: This will recreate your service!")
    log("The service will be unavailable for a few minutes.")
    log("")
    
    response = input("Do you want to continue? (yes/no): ")
    if response.lower() != 'yes':
        log("Aborted by user")
        return 0
    
    try:
        # Step 1: Get target group ARN
        tg_arn = get_target_group_arn()
        log(f"Target Group ARN: {tg_arn}")
        
        # Step 2: Get current service configuration
        config = get_service_config()
        
        # Save configuration backup
        backup_file = f'service-config-backup-{int(time.time())}.json'
        with open(backup_file, 'w') as f:
            json.dump(config, f, indent=2)
        log(f"Configuration backed up to {backup_file}")
        
        # Step 3: Scale service to 0
        scale_service_to_zero()
        
        # Step 4: Delete service
        delete_service()
        
        # Step 5: Recreate service with ALB
        create_service_with_alb(config, tg_arn)
        
        log("=" * 80)
        log("Service successfully recreated with ALB!")
        log("=" * 80)
        log("Your application is now accessible through the load balancer")
        log("Check the ALB DNS name from the previous setup script output")
        log("=" * 80)
        
        return 0
        
    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        log("")
        log("If the service was deleted but not recreated, you can restore it using:")
        log(f"  python scripts/restore-service-from-backup.py {backup_file}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
