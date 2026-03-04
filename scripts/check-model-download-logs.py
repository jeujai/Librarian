#!/usr/bin/env python3
"""
Check application logs for model download progress.
"""

import boto3
import time

def main():
    ecs = boto3.client('ecs', region_name='us-east-1')
    logs = boto3.client('logs', region_name='us-east-1')
    
    cluster = 'multimodal-lib-prod-cluster'
    service_name = 'multimodal-lib-prod-service-alb'
    
    print("=" * 80)
    print("CHECKING MODEL DOWNLOAD LOGS")
    print("=" * 80)
    
    # Get task
    tasks = ecs.list_tasks(
        cluster=cluster,
        serviceName=service_name
    )['taskArns']
    
    if not tasks:
        print("No tasks found")
        return
    
    task_id = tasks[0].split('/')[-1]
    print(f"\nTask: {task_id}")
    
    # Get logs
    log_group = '/ecs/multimodal-lib-prod-app'
    log_stream = f"ecs/multimodal-lib-prod-app/{task_id}"
    
    print(f"Log stream: {log_stream}")
    print("\n" + "=" * 80)
    print("RECENT LOGS")
    print("=" * 80 + "\n")
    
    try:
        response = logs.get_log_events(
            logGroupName=log_group,
            logStreamName=log_stream,
            startFromHead=False,
            limit=50
        )
        
        for event in response['events']:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(event['timestamp']/1000))
            message = event['message'].strip()
            print(f"[{timestamp}] {message}")
            
    except logs.exceptions.ResourceNotFoundException:
        print(f"Log stream not found yet. Task may still be starting...")
        print("Wait a minute and try again.")

if __name__ == '__main__':
    main()
