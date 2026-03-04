#!/usr/bin/env python3
"""
Monitor the 20GB memory deployment progress.
"""

import boto3
import time
import sys
from datetime import datetime

def monitor_deployment():
    """Monitor the deployment of the 20GB memory task."""
    
    CLUSTER_NAME = "multimodal-lib-prod-cluster"
    SERVICE_NAME = "multimodal-lib-prod-service"
    
    ecs = boto3.client('ecs')
    
    print("=" * 80)
    print("MONITORING 20GB DEPLOYMENT")
    print("=" * 80)
    print()
    
    start_time = time.time()
    max_wait = 600  # 10 minutes
    
    while time.time() - start_time < max_wait:
        try:
            # Get service status
            service_response = ecs.describe_services(
                cluster=CLUSTER_NAME,
                services=[SERVICE_NAME]
            )
            
            service = service_response['services'][0]
            deployments = service['deployments']
            
            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Deployment Status:")
            print("-" * 80)
            
            for deployment in deployments:
                task_def = deployment['taskDefinition'].split('/')[-1]
                status = deployment['status']
                running = deployment['runningCount']
                desired = deployment['desiredCount']
                
                print(f"  {status:8} | {task_def:30} | Running: {running}/{desired}")
            
            # Get task details
            tasks_response = ecs.list_tasks(
                cluster=CLUSTER_NAME,
                serviceName=SERVICE_NAME
            )
            
            if tasks_response['taskArns']:
                tasks_detail = ecs.describe_tasks(
                    cluster=CLUSTER_NAME,
                    tasks=tasks_response['taskArns']
                )
                
                print()
                print("  Task Details:")
                for task in tasks_detail['tasks']:
                    task_id = task['taskArn'].split('/')[-1][:12]
                    last_status = task['lastStatus']
                    health_status = task.get('healthStatus', 'UNKNOWN')
                    memory = task.get('memory', 'N/A')
                    cpu = task.get('cpu', 'N/A')
                    
                    print(f"    {task_id}: {last_status:10} | Health: {health_status:10} | Mem: {memory} MB | CPU: {cpu}")
                    
                    # Show container status
                    for container in task.get('containers', []):
                        container_status = container.get('lastStatus', 'UNKNOWN')
                        container_health = container.get('healthStatus', 'UNKNOWN')
                        print(f"      └─ Container: {container_status:10} | Health: {container_health}")
            
            # Check if deployment is complete
            primary_deployment = next((d for d in deployments if d['status'] == 'PRIMARY'), None)
            if primary_deployment:
                if (primary_deployment['runningCount'] == primary_deployment['desiredCount'] and
                    primary_deployment['taskDefinition'].endswith(':37')):
                    print()
                    print("=" * 80)
                    print("✓ DEPLOYMENT COMPLETE!")
                    print("=" * 80)
                    print()
                    print("The service is now running with 20GB memory.")
                    print("Monitor for OOM kills - they should be eliminated now.")
                    print()
                    return True
            
            time.sleep(15)
            
        except KeyboardInterrupt:
            print()
            print("Monitoring interrupted by user.")
            sys.exit(0)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(15)
    
    print()
    print("=" * 80)
    print("⚠️  DEPLOYMENT STILL IN PROGRESS")
    print("=" * 80)
    print()
    print("The deployment is taking longer than expected.")
    print("Check the AWS Console for detailed status and logs.")
    print()
    return False

if __name__ == "__main__":
    monitor_deployment()
