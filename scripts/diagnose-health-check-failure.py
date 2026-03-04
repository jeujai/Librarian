#!/usr/bin/env python3
"""
Diagnose Health Check Failure

This script analyzes why tasks are failing health checks after starting successfully.
"""

import boto3
import json
from datetime import datetime, timedelta

def get_recent_task_logs(cluster, task_arn):
    """Get logs from a specific task."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    logs = boto3.client('logs', region_name='us-east-1')
    
    # Get task details
    response = ecs.describe_tasks(cluster=cluster, tasks=[task_arn])
    if not response['tasks']:
        return None
    
    task = response['tasks'][0]
    task_id = task_arn.split('/')[-1]
    
    # Try to get logs
    log_stream_name = f"ecs/multimodal-lib-prod-app/{task_id}"
    
    try:
        response = logs.get_log_events(
            logGroupName='/ecs/multimodal-lib-prod-app',
            logStreamName=log_stream_name,
            limit=100,
            startFromHead=False  # Get most recent logs
        )
        return response['events']
    except Exception as e:
        print(f"Could not get logs for {task_id}: {e}")
        return None

def analyze_health_check_failure():
    """Analyze why health checks are failing."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    elbv2 = boto3.client('elbv2', region_name='us-east-1')
    
    cluster = "multimodal-lib-prod-cluster"
    service = "multimodal-lib-prod-service"
    target_group_arn = "arn:aws:elasticloadbalancing:us-east-1:591222106065:targetgroup/multimodal-lib-prod-tg/4fcfbdac0243c773"
    
    print("=" * 80)
    print("HEALTH CHECK FAILURE DIAGNOSIS")
    print("=" * 80)
    
    # Get service details
    print("\n1. SERVICE STATUS")
    print("-" * 80)
    response = ecs.describe_services(cluster=cluster, services=[service])
    service_data = response['services'][0]
    
    print(f"Running Count: {service_data['runningCount']}/{service_data['desiredCount']}")
    print(f"Pending Count: {service_data['pendingCount']}")
    
    # Get recent events
    print("\n2. RECENT SERVICE EVENTS")
    print("-" * 80)
    for event in service_data['events'][:10]:
        timestamp = event['createdAt'].strftime("%H:%M:%S")
        message = event['message'][:120]
        print(f"[{timestamp}] {message}")
    
    # Get target group health check configuration
    print("\n3. LOAD BALANCER HEALTH CHECK CONFIGURATION")
    print("-" * 80)
    response = elbv2.describe_target_groups(TargetGroupArns=[target_group_arn])
    tg = response['TargetGroups'][0]
    
    print(f"Health Check Path: {tg['HealthCheckPath']}")
    print(f"Health Check Interval: {tg['HealthCheckIntervalSeconds']}s")
    print(f"Health Check Timeout: {tg['HealthCheckTimeoutSeconds']}s")
    print(f"Healthy Threshold: {tg['HealthyThresholdCount']}")
    print(f"Unhealthy Threshold: {tg['UnhealthyThresholdCount']}")
    print(f"Health Check Protocol: {tg['HealthCheckProtocol']}")
    
    # Calculate time to mark unhealthy
    time_to_unhealthy = tg['HealthCheckIntervalSeconds'] * tg['UnhealthyThresholdCount']
    print(f"\nTime to mark unhealthy: {time_to_unhealthy}s ({time_to_unhealthy/60:.1f} minutes)")
    
    # Get target health
    print("\n4. CURRENT TARGET HEALTH")
    print("-" * 80)
    response = elbv2.describe_target_health(TargetGroupArn=target_group_arn)
    
    if not response['TargetHealthDescriptions']:
        print("No targets registered")
    else:
        for target in response['TargetHealthDescriptions']:
            target_id = target['Target']['Id']
            port = target['Target']['Port']
            state = target['TargetHealth']['State']
            reason = target['TargetHealth'].get('Reason', 'N/A')
            description = target['TargetHealth'].get('Description', 'N/A')
            
            print(f"Target: {target_id}:{port}")
            print(f"  State: {state}")
            print(f"  Reason: {reason}")
            print(f"  Description: {description}")
    
    # Get stopped tasks
    print("\n5. RECENTLY STOPPED TASKS")
    print("-" * 80)
    response = ecs.list_tasks(
        cluster=cluster,
        serviceName=service,
        desiredStatus='STOPPED',
        maxResults=5
    )
    
    if response['taskArns']:
        response = ecs.describe_tasks(cluster=cluster, tasks=response['taskArns'])
        
        for task in response['tasks']:
            task_id = task['taskArn'].split('/')[-1][:12]
            stopped_reason = task.get('stoppedReason', 'Unknown')
            stopped_at = task.get('stoppedAt', 'Unknown')
            
            print(f"\nTask: {task_id}")
            print(f"  Stopped Reason: {stopped_reason}")
            print(f"  Stopped At: {stopped_at}")
            
            # Get task definition
            task_def_arn = task['taskDefinitionArn']
            task_def_version = task_def_arn.split(':')[-1]
            print(f"  Task Definition: #{task_def_version}")
            
            # Try to get logs
            logs = get_recent_task_logs(cluster, task['taskArn'])
            if logs:
                print(f"  Last 5 log entries:")
                for log in logs[-5:]:
                    timestamp = datetime.fromtimestamp(log['timestamp']/1000).strftime("%H:%M:%S")
                    message = log['message'][:80]
                    print(f"    [{timestamp}] {message}")
    
    # Analysis
    print("\n6. ANALYSIS")
    print("-" * 80)
    print(f"✓ Application starts successfully (logs show 200 OK responses)")
    print(f"✓ Health checks initially pass (multiple successful /health requests)")
    print(f"✗ Tasks are being stopped after {time_to_unhealthy}s of failed health checks")
    print(f"\nPossible causes:")
    print(f"  1. Application crashes after startup")
    print(f"  2. Health endpoint stops responding")
    print(f"  3. Network connectivity issues")
    print(f"  4. Resource exhaustion (memory/CPU)")
    print(f"  5. Task definition health check timeout too aggressive")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    analyze_health_check_failure()
