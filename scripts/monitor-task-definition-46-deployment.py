#!/usr/bin/env python3
"""
Monitor Task Definition 46 Deployment

Monitors the deployment of task definition 46 with fixed secret ARNs
to verify tasks start successfully and pass health checks.
"""

import boto3
import time
from datetime import datetime

def monitor_deployment():
    """Monitor ECS deployment progress."""
    
    print("🔍 Monitoring Task Definition 46 Deployment")
    print("=" * 60)
    print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    ecs = boto3.client('ecs', region_name='us-east-1')
    cluster_name = "multimodal-lib-prod-cluster"
    service_name = "multimodal-lib-prod-service"
    
    print("⏳ Waiting for tasks to start (this may take 2-3 minutes)...")
    print()
    
    for i in range(20):  # Monitor for up to 10 minutes
        try:
            # Get service status
            service_response = ecs.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            
            if not service_response['services']:
                print("❌ Service not found")
                return
            
            service = service_response['services'][0]
            
            # Get task information
            running_count = service['runningCount']
            desired_count = service['desiredCount']
            pending_count = service['pendingCount']
            
            # Get deployments
            deployments = service['deployments']
            primary_deployment = None
            for deployment in deployments:
                if deployment['status'] == 'PRIMARY':
                    primary_deployment = deployment
                    break
            
            # Display status
            timestamp = datetime.now().strftime('%H:%M:%S')
            print(f"[{timestamp}] Service Status:")
            print(f"  Running: {running_count}/{desired_count}")
            print(f"  Pending: {pending_count}")
            
            if primary_deployment:
                print(f"  Task Definition: {primary_deployment['taskDefinition'].split('/')[-1]}")
                print(f"  Rollout State: {primary_deployment.get('rolloutState', 'N/A')}")
            
            # List tasks
            tasks_response = ecs.list_tasks(
                cluster=cluster_name,
                serviceName=service_name,
                desiredStatus='RUNNING'
            )
            
            if tasks_response['taskArns']:
                tasks_detail = ecs.describe_tasks(
                    cluster=cluster_name,
                    tasks=tasks_response['taskArns']
                )
                
                print(f"\n  Tasks:")
                for task in tasks_detail['tasks']:
                    task_id = task['taskArn'].split('/')[-1]
                    task_def = task['taskDefinitionArn'].split('/')[-1]
                    last_status = task['lastStatus']
                    health_status = task.get('healthStatus', 'UNKNOWN')
                    
                    print(f"    - {task_id[:8]}... ({task_def})")
                    print(f"      Status: {last_status}, Health: {health_status}")
                    
                    # Check for stopped reason
                    if 'stoppedReason' in task:
                        print(f"      ⚠️  Stopped: {task['stoppedReason']}")
                    
                    # Check container status
                    for container in task.get('containers', []):
                        if container.get('lastStatus') == 'STOPPED':
                            print(f"      ⚠️  Container stopped: {container.get('reason', 'Unknown')}")
            
            print()
            
            # Check if deployment is complete
            if running_count == desired_count and running_count > 0:
                if primary_deployment and primary_deployment.get('rolloutState') == 'COMPLETED':
                    print("✅ Deployment completed successfully!")
                    print(f"✅ {running_count} task(s) running with task definition 46")
                    return
            
            # Wait before next check
            time.sleep(30)
            
        except Exception as e:
            print(f"❌ Error monitoring deployment: {e}")
            time.sleep(30)
    
    print("⏰ Monitoring timeout reached (10 minutes)")
    print("Check AWS Console for detailed task status")

if __name__ == "__main__":
    monitor_deployment()
