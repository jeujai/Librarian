#!/usr/bin/env python3
"""
Get logs from the running ECS container to see what's actually happening.
"""

import boto3
from datetime import datetime, timedelta

REGION = 'us-east-1'
CLUSTER_NAME = 'multimodal-lib-prod-cluster'
SERVICE_NAME = 'multimodal-lib-prod-service-alb'
LOG_GROUP = '/ecs/multimodal-lib-prod-app'

ecs = boto3.client('ecs', region_name=REGION)
logs = boto3.client('logs', region_name=REGION)

def get_running_task():
    """Get a running task"""
    tasks = ecs.list_tasks(
        cluster=CLUSTER_NAME,
        serviceName=SERVICE_NAME,
        desiredStatus='RUNNING'
    )
    
    if not tasks['taskArns']:
        print("❌ No running tasks found")
        return None
    
    return tasks['taskArns'][0]

def get_task_logs(task_arn):
    """Get logs for a specific task"""
    task_id = task_arn.split('/')[-1]
    
    print(f"\n📋 Task ID: {task_id}")
    print(f"📝 Log Group: {LOG_GROUP}")
    
    # Find log stream for this task
    try:
        streams = logs.describe_log_streams(
            logGroupName=LOG_GROUP,
            logStreamNamePrefix=f'ecs/multimodal-lib-prod-app/{task_id}',
            limit=5
        )
        
        if not streams['logStreams']:
            print(f"\n⚠️  No log streams found for task {task_id}")
            print("   The container may not have started yet or logging is not configured")
            return
        
        stream_name = streams['logStreams'][0]['logStreamName']
        print(f"📊 Log Stream: {stream_name}")
        
        # Get recent logs
        end_time = datetime.now()
        start_time = end_time - timedelta(minutes=30)
        
        events = logs.get_log_events(
            logGroupName=LOG_GROUP,
            logStreamName=stream_name,
            startTime=int(start_time.timestamp() * 1000),
            endTime=int(end_time.timestamp() * 1000),
            limit=100,
            startFromHead=False  # Get most recent logs
        )
        
        print(f"\n📊 Recent Log Events (last 30 minutes, showing last 100):")
        print("=" * 70)
        
        if not events['events']:
            print("ℹ️  No log events found in the last 30 minutes")
        else:
            for event in events['events']:
                timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                message = event['message'].strip()
                print(f"[{timestamp.strftime('%H:%M:%S')}] {message}")
        
    except Exception as e:
        print(f"❌ Error reading logs: {str(e)}")

def main():
    print("=" * 70)
    print("CONTAINER LOGS")
    print("=" * 70)
    
    task_arn = get_running_task()
    if not task_arn:
        return 1
    
    get_task_logs(task_arn)
    
    return 0

if __name__ == '__main__':
    exit(main())
