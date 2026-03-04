#!/usr/bin/env python3
"""
Recreate service with ALB configuration (with proper waiting)
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

def wait_for_service_to_drain():
    """Wait for service to finish draining."""
    log("Waiting for service to finish draining...")
    
    max_wait = 300  # 5 minutes
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        try:
            response = ecs.describe_services(
                cluster=CLUSTER_NAME,
                services=[SERVICE_NAME]
            )
            
            if not response['services'] or response['services'][0]['status'] == 'INACTIVE':
                log("Service is fully drained")
                return True
            
            log(f"Service status: {response['services'][0]['status']}, waiting...")
            time.sleep(10)
            
        except Exception as e:
            log(f"Service not found (good): {e}")
            return True
    
    log("WARNING: Timeout waiting for service to drain")
    return False

def create_service_with_alb(config_file, tg_arn):
    """Create service with ALB configuration."""
    log(f"Loading configuration from {config_file}...")
    
    with open(config_file, 'r') as f:
        config = json.load(f)
    
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
        services=[SERVICE_NAME],
        WaiterConfig={'Delay': 15, 'MaxAttempts': 40}
    )
    
    log("Service is now stable")

def main():
    """Main execution function."""
    log("=" * 80)
    log("Recreating Service with ALB")
    log("=" * 80)
    
    if len(sys.argv) < 2:
        log("Usage: python scripts/recreate-service-with-alb.py <config-backup-file>")
        log("Example: python scripts/recreate-service-with-alb.py service-config-backup-1768465018.json")
        return 1
    
    config_file = sys.argv[1]
    
    try:
        # Step 1: Get target group ARN
        tg_arn = get_target_group_arn()
        log(f"Target Group ARN: {tg_arn}")
        
        # Step 2: Wait for service to drain
        if not wait_for_service_to_drain():
            log("Service may still be draining, but proceeding anyway...")
        
        # Step 3: Create service with ALB
        create_service_with_alb(config_file, tg_arn)
        
        log("=" * 80)
        log("Service successfully recreated with ALB!")
        log("=" * 80)
        log("Your application is now accessible through the load balancer")
        log("=" * 80)
        
        return 0
        
    except Exception as e:
        log(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
