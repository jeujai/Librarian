#!/usr/bin/env python3
"""
Deploy Task Definition 71 with Corrected Health Check Path

This script updates the ECS service to use task definition revision 71,
which fixes the health check path to /api/health/simple (with the /api prefix).
"""

import boto3
import json
import time
from datetime import datetime

# Configuration
CLUSTER_NAME = "multimodal-lib-prod-cluster"
SERVICE_NAME = "multimodal-lib-prod-service-alb"
TASK_DEFINITION_ARN = "arn:aws:ecs:us-east-1:591222106065:task-definition/multimodal-lib-prod-app:71"
REGION = "us-east-1"

def get_current_service_config(ecs_client, cluster, service):
    """Get current service configuration"""
    print(f"\n{'='*60}")
    print("STEP 1: Getting current service configuration")
    print(f"{'='*60}")
    
    response = ecs_client.describe_services(
        cluster=cluster,
        services=[service]
    )
    
    if not response['services']:
        raise Exception(f"Service {service} not found in cluster {cluster}")
    
    service_config = response['services'][0]
    current_task_def = service_config['taskDefinition']
    
    print(f"✓ Current task definition: {current_task_def}")
    print(f"✓ Service status: {service_config['status']}")
    print(f"✓ Desired count: {service_config['desiredCount']}")
    print(f"✓ Running count: {service_config['runningCount']}")
    
    return service_config

def update_service(ecs_client, cluster, service, task_definition_arn):
    """Update service to use new task definition"""
    print(f"\n{'='*60}")
    print("STEP 2: Updating service with new task definition")
    print(f"{'='*60}")
    
    print(f"Updating service to use: {task_definition_arn}")
    
    response = ecs_client.update_service(
        cluster=cluster,
        service=service,
        taskDefinition=task_definition_arn,
        forceNewDeployment=True
    )
    
    print(f"✓ Service update initiated")
    print(f"✓ Deployment ID: {response['service']['deployments'][0]['id']}")
    
    return response['service']

def monitor_deployment(ecs_client, cluster, service, timeout_minutes=15):
    """Monitor the deployment progress"""
    print(f"\n{'='*60}")
    print("STEP 3: Monitoring deployment progress")
    print(f"{'='*60}")
    
    start_time = time.time()
    timeout_seconds = timeout_minutes * 60
    
    print(f"Monitoring deployment (timeout: {timeout_minutes} minutes)")
    print(f"Health check start period: 5 minutes (300 seconds)")
    print(f"Expected deployment time: 6-8 minutes\n")
    
    last_status = None
    
    while True:
        elapsed = time.time() - start_time
        
        if elapsed > timeout_seconds:
            print(f"\n⚠ Deployment monitoring timeout after {timeout_minutes} minutes")
            print("The deployment may still be in progress. Check AWS Console for status.")
            break
        
        response = ecs_client.describe_services(
            cluster=cluster,
            services=[service]
        )
        
        service_info = response['services'][0]
        deployments = service_info['deployments']
        
        # Get primary deployment
        primary_deployment = next((d for d in deployments if d['status'] == 'PRIMARY'), None)
        
        if primary_deployment:
            running_count = primary_deployment['runningCount']
            desired_count = primary_deployment['desiredCount']
            task_def = primary_deployment['taskDefinition'].split('/')[-1]
            
            status_msg = f"[{int(elapsed)}s] Task Def: {task_def} | Running: {running_count}/{desired_count}"
            
            if status_msg != last_status:
                print(status_msg)
                last_status = status_msg
            
            # Check if deployment is complete
            if running_count == desired_count and len(deployments) == 1:
                print(f"\n✓ Deployment completed successfully!")
                print(f"✓ All {desired_count} tasks are running with task definition 71")
                return True
        
        time.sleep(10)
    
    return False

def verify_health_check_path(ecs_client, task_definition_arn):
    """Verify the health check path in the task definition"""
    print(f"\n{'='*60}")
    print("STEP 4: Verifying health check configuration")
    print(f"{'='*60}")
    
    response = ecs_client.describe_task_definition(
        taskDefinition=task_definition_arn
    )
    
    task_def = response['taskDefinition']
    container = task_def['containerDefinitions'][0]
    health_check = container.get('healthCheck', {})
    
    if health_check:
        command = ' '.join(health_check['command'])
        print(f"✓ Health check command: {command}")
        
        if '/api/health/simple' in command:
            print(f"✓ Health check path is correctly set to /api/health/simple")
            return True
        else:
            print(f"⚠ Warning: Health check path may not be /api/health/simple")
            return False
    else:
        print(f"⚠ Warning: No health check found in task definition")
        return False

def get_task_health_status(ecs_client, cluster, service):
    """Get health status of running tasks"""
    print(f"\n{'='*60}")
    print("STEP 5: Checking task health status")
    print(f"{'='*60}")
    
    # Get tasks for the service
    response = ecs_client.list_tasks(
        cluster=cluster,
        serviceName=service,
        desiredStatus='RUNNING'
    )
    
    task_arns = response['taskArns']
    
    if not task_arns:
        print("No running tasks found")
        return
    
    # Describe tasks
    response = ecs_client.describe_tasks(
        cluster=cluster,
        tasks=task_arns
    )
    
    print(f"Found {len(response['tasks'])} running task(s):\n")
    
    for task in response['tasks']:
        task_id = task['taskArn'].split('/')[-1]
        health_status = task.get('healthStatus', 'UNKNOWN')
        last_status = task.get('lastStatus', 'UNKNOWN')
        
        container = task['containers'][0]
        container_health = container.get('healthStatus', 'UNKNOWN')
        
        print(f"Task: {task_id}")
        print(f"  Status: {last_status}")
        print(f"  Health: {health_status}")
        print(f"  Container Health: {container_health}")
        print()

def save_deployment_record():
    """Save deployment record"""
    timestamp = int(time.time())
    record = {
        "timestamp": datetime.now().isoformat(),
        "task_definition": "multimodal-lib-prod-app:71",
        "task_definition_arn": TASK_DEFINITION_ARN,
        "cluster": CLUSTER_NAME,
        "service": SERVICE_NAME,
        "change": "Fixed health check path to /api/health/simple (added /api prefix)",
        "deployment_method": "ECS service update with force new deployment"
    }
    
    filename = f"task-definition-71-deployment-{timestamp}.json"
    with open(filename, 'w') as f:
        json.dump(record, f, indent=2)
    
    print(f"\n✓ Deployment record saved to: {filename}")

def main():
    print(f"\n{'='*60}")
    print("TASK DEFINITION 71 DEPLOYMENT")
    print(f"{'='*60}")
    print(f"Cluster: {CLUSTER_NAME}")
    print(f"Service: {SERVICE_NAME}")
    print(f"New Task Definition: {TASK_DEFINITION_ARN}")
    print(f"Change: Health check path → /api/health/simple")
    print(f"Fix: Added missing /api prefix")
    print(f"{'='*60}\n")
    
    # Initialize AWS clients
    ecs_client = boto3.client('ecs', region_name=REGION)
    
    try:
        # Step 1: Get current service configuration
        current_config = get_current_service_config(ecs_client, CLUSTER_NAME, SERVICE_NAME)
        
        # Step 2: Verify health check path in new task definition
        verify_health_check_path(ecs_client, TASK_DEFINITION_ARN)
        
        # Step 3: Update service
        updated_service = update_service(ecs_client, CLUSTER_NAME, SERVICE_NAME, TASK_DEFINITION_ARN)
        
        # Step 4: Monitor deployment
        success = monitor_deployment(ecs_client, CLUSTER_NAME, SERVICE_NAME, timeout_minutes=15)
        
        # Step 5: Check task health status
        time.sleep(5)  # Wait a bit for tasks to stabilize
        get_task_health_status(ecs_client, CLUSTER_NAME, SERVICE_NAME)
        
        # Step 6: Save deployment record
        save_deployment_record()
        
        # Final summary
        print(f"\n{'='*60}")
        print("DEPLOYMENT SUMMARY")
        print(f"{'='*60}")
        
        if success:
            print("✓ Deployment completed successfully")
            print("✓ Service is now using task definition 71")
            print("✓ Health check path fixed to /api/health/simple")
            print("\nNext steps:")
            print("1. Monitor CloudWatch logs for health check requests")
            print("2. Verify ALB target health in AWS Console")
            print("3. Test the /api/health/simple endpoint directly")
        else:
            print("⚠ Deployment monitoring timed out")
            print("Please check AWS Console for current deployment status")
            print("\nTo check status manually:")
            print(f"  aws ecs describe-services --cluster {CLUSTER_NAME} --services {SERVICE_NAME}")
        
        print(f"{'='*60}\n")
        
    except Exception as e:
        print(f"\n❌ Error during deployment: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
