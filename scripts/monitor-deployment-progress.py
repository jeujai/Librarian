#!/usr/bin/env python3
"""
Monitor ECS Deployment Progress

This script monitors the progress of an ECS service deployment,
tracking task status, health checks, and providing real-time updates.
"""

import boto3
import time
import json
from datetime import datetime
from typing import Dict, Any, List

def get_service_status(cluster: str, service: str) -> Dict[str, Any]:
    """Get current service status."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    response = ecs.describe_services(
        cluster=cluster,
        services=[service]
    )
    
    if not response['services']:
        return None
    
    service_data = response['services'][0]
    
    return {
        'running_count': service_data['runningCount'],
        'desired_count': service_data['desiredCount'],
        'pending_count': service_data['pendingCount'],
        'deployments': service_data['deployments'],
        'events': service_data['events'][:5]
    }

def get_task_details(cluster: str, task_arns: List[str]) -> List[Dict[str, Any]]:
    """Get details for specific tasks."""
    if not task_arns:
        return []
    
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    response = ecs.describe_tasks(
        cluster=cluster,
        tasks=task_arns
    )
    
    tasks = []
    for task in response['tasks']:
        container = task['containers'][0] if task['containers'] else {}
        
        tasks.append({
            'task_id': task['taskArn'].split('/')[-1],
            'task_definition': task['taskDefinitionArn'].split('/')[-1],
            'last_status': task['lastStatus'],
            'health_status': task.get('healthStatus', 'UNKNOWN'),
            'created_at': task['createdAt'].isoformat() if 'createdAt' in task else None,
            'started_at': task.get('startedAt').isoformat() if task.get('startedAt') else None,
            'container_status': container.get('lastStatus', 'UNKNOWN'),
            'container_health': container.get('healthStatus', 'UNKNOWN')
        })
    
    return tasks

def get_running_tasks(cluster: str, service: str) -> List[str]:
    """Get list of running task ARNs."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    response = ecs.list_tasks(
        cluster=cluster,
        serviceName=service,
        desiredStatus='RUNNING'
    )
    
    return response['taskArns']

def check_target_health(target_group_arn: str) -> Dict[str, Any]:
    """Check target group health."""
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    
    response = elbv2.describe_target_health(
        TargetGroupArn=target_group_arn
    )
    
    health_summary = {
        'healthy': 0,
        'unhealthy': 0,
        'initial': 0,
        'draining': 0,
        'unavailable': 0
    }
    
    for target in response['TargetHealthDescriptions']:
        state = target['TargetHealth']['State']
        health_summary[state] = health_summary.get(state, 0) + 1
    
    return health_summary

def monitor_deployment(cluster: str, service: str, target_group_arn: str, duration_minutes: int = 10):
    """Monitor deployment progress."""
    print(f"Monitoring deployment for {service} in cluster {cluster}")
    print(f"Will monitor for {duration_minutes} minutes")
    print("=" * 80)
    
    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)
    
    iteration = 0
    while time.time() < end_time:
        iteration += 1
        current_time = datetime.now().strftime("%H:%M:%S")
        elapsed = int(time.time() - start_time)
        
        print(f"\n[{current_time}] Update #{iteration} (Elapsed: {elapsed}s)")
        print("-" * 80)
        
        # Get service status
        service_status = get_service_status(cluster, service)
        if not service_status:
            print("ERROR: Service not found")
            break
        
        print(f"Service Status:")
        print(f"  Running: {service_status['running_count']}/{service_status['desired_count']}")
        print(f"  Pending: {service_status['pending_count']}")
        
        # Get task details
        task_arns = get_running_tasks(cluster, service)
        if task_arns:
            print(f"\nTasks ({len(task_arns)}):")
            tasks = get_task_details(cluster, task_arns)
            for task in tasks:
                print(f"  Task {task['task_id'][:8]}...")
                print(f"    Definition: {task['task_definition']}")
                print(f"    Status: {task['last_status']} / Health: {task['health_status']}")
                print(f"    Container: {task['container_status']} / Health: {task['container_health']}")
                if task['started_at']:
                    print(f"    Started: {task['started_at']}")
        else:
            print("\nNo running tasks")
        
        # Get target health
        try:
            target_health = check_target_health(target_group_arn)
            print(f"\nTarget Group Health:")
            for state, count in target_health.items():
                if count > 0:
                    print(f"  {state.capitalize()}: {count}")
        except Exception as e:
            print(f"\nTarget Group Health: Error - {e}")
        
        # Show recent events
        print(f"\nRecent Events:")
        for event in service_status['events'][:3]:
            event_time = event['createdAt'].strftime("%H:%M:%S")
            message = event['message'][:100]
            print(f"  [{event_time}] {message}")
        
        # Check if deployment is complete
        if (service_status['running_count'] == service_status['desired_count'] and
            service_status['pending_count'] == 0):
            print("\n" + "=" * 80)
            print("DEPLOYMENT COMPLETE!")
            print(f"All {service_status['desired_count']} tasks are running")
            
            # Final health check
            target_health = check_target_health(target_group_arn)
            if target_health.get('healthy', 0) > 0:
                print(f"✓ {target_health['healthy']} healthy targets")
                return True
            else:
                print(f"⚠ No healthy targets yet")
                print("Waiting for health checks to pass...")
        
        # Wait before next check
        time.sleep(30)
    
    print("\n" + "=" * 80)
    print("Monitoring period ended")
    return False

if __name__ == "__main__":
    CLUSTER = "multimodal-lib-prod-cluster"
    SERVICE = "multimodal-lib-prod-service"
    TARGET_GROUP = "arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg/4fcfbdac0243c773"
    
    success = monitor_deployment(CLUSTER, SERVICE, TARGET_GROUP, duration_minutes=10)
    
    if success:
        print("\n✓ Deployment successful!")
        exit(0)
    else:
        print("\n⚠ Deployment monitoring completed - check status manually")
        exit(1)
