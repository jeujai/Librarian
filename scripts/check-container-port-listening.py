#!/usr/bin/env python3
"""
Check if the container is actually listening on port 8000 by executing commands inside it.
"""

import boto3
import json
import time
from datetime import datetime

def get_task_arn():
    """Get the running task ARN."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    tasks_response = ecs.list_tasks(
        cluster='multimodal-lib-prod-cluster'
    )
    
    if not tasks_response['taskArns']:
        return None
    
    return tasks_response['taskArns'][0]

def execute_command(task_arn, command):
    """Execute a command in the container."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    try:
        response = ecs.execute_command(
            cluster='multimodal-lib-prod-cluster',
            task=task_arn,
            container='multimodal-lib-prod-app',
            interactive=False,
            command=command
        )
        return response
    except Exception as e:
        return {'error': str(e)}

def main():
    print("=" * 80)
    print("Container Port Listening Check")
    print("=" * 80)
    print()
    
    # Get task ARN
    print("1. Getting task ARN...")
    task_arn = get_task_arn()
    
    if not task_arn:
        print("ERROR: No running tasks found")
        return
    
    print(f"   Task: {task_arn}")
    print()
    
    # Commands to check
    commands_to_check = [
        {
            'name': 'Check if port 8000 is listening',
            'command': 'netstat -tlnp | grep 8000'
        },
        {
            'name': 'Check all listening ports',
            'command': 'netstat -tlnp'
        },
        {
            'name': 'Check if uvicorn process is running',
            'command': 'ps aux | grep uvicorn'
        },
        {
            'name': 'Check if python process is running',
            'command': 'ps aux | grep python'
        },
        {
            'name': 'Test local connection to port 8000',
            'command': 'curl -v http://localhost:8000/health/simple'
        }
    ]
    
    print("2. Checking container state...")
    print()
    print("NOTE: ECS Execute Command must be enabled on the service.")
    print("If you see errors, the service may not have execute command enabled.")
    print()
    
    for cmd_info in commands_to_check:
        print(f"   {cmd_info['name']}:")
        print(f"   Command: {cmd_info['command']}")
        
        result = execute_command(task_arn, cmd_info['command'])
        
        if 'error' in result:
            print(f"   ERROR: {result['error']}")
        else:
            print(f"   Response: {json.dumps(result, indent=2)}")
        
        print()
    
    print("=" * 80)
    print("ALTERNATIVE: Check from CloudWatch Logs")
    print("=" * 80)
    print()
    print("Since ECS Execute Command may not be enabled, let's check the logs instead.")
    print()
    
    # Check logs for any errors
    logs = boto3.client('logs', region_name='us-east-1')
    
    try:
        log_events = logs.filter_log_events(
            logGroupName='/ecs/multimodal-lib-prod-app',
            limit=50,
            startTime=int((time.time() - 600) * 1000)  # Last 10 minutes
        )
        
        print("Recent log entries:")
        for event in log_events['events'][-20:]:
            timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
            message = event['message']
            print(f"   [{timestamp}] {message[:200]}")
        
    except Exception as e:
        print(f"   ERROR reading logs: {str(e)}")

if __name__ == '__main__':
    main()
