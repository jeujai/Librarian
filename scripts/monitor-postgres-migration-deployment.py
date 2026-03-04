#!/usr/bin/env python3
"""
Monitor PostgreSQL Migration Deployment

Monitors the ECS service deployment after PostgreSQL migration.
"""

import boto3
import time
import sys

ECS_CLUSTER = "multimodal-lib-prod-cluster"
ECS_SERVICE = "multimodal-lib-prod-service"
NEW_TASK_DEF_REVISION = 49

ecs = boto3.client('ecs')
logs = boto3.client('logs')

def check_deployment_status():
    """Check the current deployment status."""
    response = ecs.describe_services(
        cluster=ECS_CLUSTER,
        services=[ECS_SERVICE]
    )
    
    service = response['services'][0]
    deployments = service['deployments']
    
    print(f"\n{'='*70}")
    print(f"Deployment Status - {time.strftime('%H:%M:%S')}")
    print(f"{'='*70}")
    
    print(f"\nService: {service['serviceName']}")
    print(f"Status: {service['status']}")
    print(f"Running Count: {service['runningCount']}/{service['desiredCount']}")
    
    print(f"\nDeployments:")
    for deployment in deployments:
        task_def = deployment['taskDefinition'].split('/')[-1]
        print(f"  - {deployment['status']}: {task_def}")
        print(f"    Running: {deployment['runningCount']}/{deployment['desiredCount']}")
        if 'rolloutState' in deployment:
            print(f"    Rollout State: {deployment['rolloutState']}")
    
    # Check if new task definition is running
    new_deployment = next(
        (d for d in deployments if f":{NEW_TASK_DEF_REVISION}" in d['taskDefinition']),
        None
    )
    
    if new_deployment:
        if new_deployment['runningCount'] == new_deployment['desiredCount']:
            print(f"\n✓ New task definition (revision {NEW_TASK_DEF_REVISION}) is fully deployed!")
            return True
        else:
            print(f"\n⏳ Waiting for new task definition to reach desired count...")
    
    return False

def check_task_health():
    """Check the health of running tasks."""
    response = ecs.list_tasks(
        cluster=ECS_CLUSTER,
        serviceName=ECS_SERVICE,
        desiredStatus='RUNNING'
    )
    
    if not response['taskArns']:
        print("\n⚠ No running tasks found")
        return
    
    tasks_response = ecs.describe_tasks(
        cluster=ECS_CLUSTER,
        tasks=response['taskArns']
    )
    
    print(f"\nTasks:")
    for task in tasks_response['tasks']:
        task_id = task['taskArn'].split('/')[-1]
        task_def = task['taskDefinitionArn'].split('/')[-1]
        print(f"  - Task: {task_id[:8]}...")
        print(f"    Task Definition: {task_def}")
        print(f"    Last Status: {task['lastStatus']}")
        print(f"    Health Status: {task.get('healthStatus', 'UNKNOWN')}")
        
        for container in task['containers']:
            print(f"    Container: {container['name']}")
            print(f"      Status: {container['lastStatus']}")
            print(f"      Health: {container.get('healthStatus', 'UNKNOWN')}")

def check_recent_logs():
    """Check recent logs for database connectivity."""
    log_group = '/ecs/multimodal-librarian'
    
    try:
        # Get recent log streams
        response = logs.describe_log_streams(
            logGroupName=log_group,
            orderBy='LastEventTime',
            descending=True,
            limit=3
        )
        
        if not response['logStreams']:
            print("\n⚠ No log streams found")
            return
        
        print(f"\nRecent Logs:")
        for stream in response['logStreams'][:1]:  # Check most recent stream
            stream_name = stream['logStreamName']
            
            # Get recent log events
            events_response = logs.get_log_events(
                logGroupName=log_group,
                logStreamName=stream_name,
                limit=20,
                startFromHead=False
            )
            
            # Look for database-related messages
            db_messages = []
            for event in events_response['events']:
                message = event['message']
                if any(keyword in message.lower() for keyword in ['postgres', 'database', 'connection', 'error']):
                    db_messages.append(message)
            
            if db_messages:
                print(f"  Database-related messages:")
                for msg in db_messages[-5:]:  # Show last 5
                    print(f"    {msg[:100]}...")
            else:
                print(f"  No database-related messages in recent logs")
    
    except Exception as e:
        print(f"\n⚠ Could not fetch logs: {e}")

def main():
    """Monitor deployment progress."""
    print("="*70)
    print("PostgreSQL Migration Deployment Monitor")
    print("="*70)
    print(f"\nMonitoring deployment of task definition revision {NEW_TASK_DEF_REVISION}")
    print("Press Ctrl+C to stop monitoring\n")
    
    try:
        iteration = 0
        while True:
            # Check deployment status
            is_complete = check_deployment_status()
            
            # Check task health
            check_task_health()
            
            # Check logs every 3rd iteration
            if iteration % 3 == 0:
                check_recent_logs()
            
            if is_complete:
                print("\n" + "="*70)
                print("✓ Deployment Complete!")
                print("="*70)
                print("\nNext steps:")
                print("  1. Test application endpoints")
                print("  2. Verify database connectivity")
                print("  3. Check application logs for any errors")
                break
            
            iteration += 1
            print(f"\nWaiting 30 seconds before next check...")
            time.sleep(30)
    
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user")
        sys.exit(0)

if __name__ == "__main__":
    main()
