#!/usr/bin/env python3
"""Check ECS container logs for health check issues"""

import boto3
from datetime import datetime, timedelta

def check_logs():
    ecs = boto3.client('ecs')
    logs = boto3.client('logs')
    
    cluster = 'multimodal-lib-prod-cluster'
    service = 'multimodal-lib-prod-service'
    
    print("=" * 80)
    print("CONTAINER LOGS ANALYSIS")
    print("=" * 80)
    
    # Get running tasks
    tasks = ecs.list_tasks(cluster=cluster, serviceName=service)['taskArns']
    
    if not tasks:
        print("❌ No running tasks found")
        return
    
    task_details = ecs.describe_tasks(cluster=cluster, tasks=tasks)['tasks']
    
    for task in task_details:
        task_id = task['taskArn'].split('/')[-1]
        print(f"\nTask: {task_id}")
        print(f"Status: {task['lastStatus']}")
        
        # Get task definition
        task_def_arn = task['taskDefinitionArn']
        task_def = ecs.describe_task_definition(taskDefinition=task_def_arn)['taskDefinition']
        
        # Find log configuration
        for container in task_def['containerDefinitions']:
            if 'logConfiguration' in container:
                log_config = container['logConfiguration']
                if log_config['logDriver'] == 'awslogs':
                    log_group = log_config['options']['awslogs-group']
                    log_stream_prefix = log_config['options']['awslogs-stream-prefix']
                    
                    print(f"\nLog Group: {log_group}")
                    print(f"Log Stream Prefix: {log_stream_prefix}")
                    
                    # Find log streams
                    try:
                        streams = logs.describe_log_streams(
                            logGroupName=log_group,
                            logStreamNamePrefix=f"{log_stream_prefix}/{container['name']}/{task_id}",
                            limit=5
                        )
                        
                        if streams['logStreams']:
                            stream_name = streams['logStreams'][0]['logStreamName']
                            print(f"Log Stream: {stream_name}")
                            
                            # Get recent logs
                            end_time = datetime.now()
                            start_time = end_time - timedelta(minutes=5)
                            
                            events = logs.get_log_events(
                                logGroupName=log_group,
                                logStreamName=stream_name,
                                startTime=int(start_time.timestamp() * 1000),
                                endTime=int(end_time.timestamp() * 1000),
                                limit=50
                            )
                            
                            print(f"\nRecent Logs (last 5 minutes):")
                            print("-" * 80)
                            
                            if events['events']:
                                for event in events['events'][-20:]:  # Last 20 events
                                    timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                                    message = event['message'].strip()
                                    print(f"[{timestamp.strftime('%H:%M:%S')}] {message}")
                            else:
                                print("No recent log events found")
                    
                    except Exception as e:
                        print(f"Error reading logs: {e}")

if __name__ == '__main__':
    check_logs()
