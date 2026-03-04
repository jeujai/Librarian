#!/usr/bin/env python3
"""
Diagnose Health Endpoint Issues

This script helps diagnose why the ECS health check is failing by:
1. Testing the health endpoint from within the container
2. Checking if curl is available
3. Testing different endpoint variations
4. Analyzing the response
"""

import boto3
import json
import time
from datetime import datetime

def get_running_task():
    """Get the currently running task."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    # List tasks
    response = ecs.list_tasks(
        cluster='multimodal-lib-prod-cluster',
        serviceName='multimodal-lib-prod-service',
        desiredStatus='RUNNING'
    )
    
    if not response['taskArns']:
        print("❌ No running tasks found")
        return None
    
    task_arn = response['taskArns'][0]
    
    # Get task details
    task_details = ecs.describe_tasks(
        cluster='multimodal-lib-prod-cluster',
        tasks=[task_arn]
    )
    
    task = task_details['tasks'][0]
    return {
        'task_arn': task_arn,
        'task_id': task_arn.split('/')[-1],
        'status': task['lastStatus'],
        'health_status': task.get('healthStatus', 'UNKNOWN'),
        'started_at': task.get('startedAt'),
        'container_name': task['containers'][0]['name']
    }

def test_health_endpoints():
    """Test various health endpoint configurations."""
    print("\n" + "="*80)
    print("HEALTH ENDPOINT DIAGNOSTIC")
    print("="*80)
    
    task = get_running_task()
    if not task:
        return
    
    print(f"\n📋 Task Information:")
    print(f"   Task ID: {task['task_id']}")
    print(f"   Status: {task['status']}")
    print(f"   Health Status: {task['health_status']}")
    print(f"   Started: {task['started_at']}")
    
    # Get task definition to see health check configuration
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    # Extract task definition from task ARN
    task_def_arn = task['task_arn'].replace(task['task_id'], '').rstrip('/')
    
    print(f"\n🔍 Checking Health Check Configuration...")
    
    # Get the service to find the task definition
    service_response = ecs.describe_services(
        cluster='multimodal-lib-prod-cluster',
        services=['multimodal-lib-prod-service']
    )
    
    task_def = service_response['services'][0]['taskDefinition']
    
    # Get task definition details
    task_def_response = ecs.describe_task_definition(
        taskDefinition=task_def
    )
    
    health_check = task_def_response['taskDefinition']['containerDefinitions'][0].get('healthCheck')
    
    if health_check:
        print(f"\n✅ Health Check Configuration Found:")
        print(f"   Command: {' '.join(health_check['command'])}")
        print(f"   Interval: {health_check['interval']}s")
        print(f"   Timeout: {health_check['timeout']}s")
        print(f"   Retries: {health_check['retries']}")
        print(f"   Start Period: {health_check['startPeriod']}s")
    else:
        print(f"\n❌ No health check configuration found")
    
    # Check CloudWatch logs for health check attempts
    print(f"\n📊 Checking CloudWatch Logs for Health Check Activity...")
    
    logs = boto3.client('logs', region_name='us-east-1')
    
    try:
        # Get recent logs
        log_events = logs.filter_log_events(
            logGroupName='/ecs/multimodal-lib-prod-app',
            startTime=int((time.time() - 600) * 1000),  # Last 10 minutes
            filterPattern='HEALTH CHECK CALLED'
        )
        
        if log_events['events']:
            print(f"\n✅ Found {len(log_events['events'])} health check log entries:")
            for event in log_events['events'][:5]:
                timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                print(f"   {timestamp}: {event['message'][:100]}")
        else:
            print(f"\n❌ No 'HEALTH CHECK CALLED' logs found")
            print(f"   This suggests the health endpoint is not being reached")
    except Exception as e:
        print(f"\n⚠️  Error checking logs: {e}")
    
    # Provide recommendations
    print(f"\n💡 Recommendations:")
    print(f"   1. Use ECS Exec to access the container and test curl manually:")
    print(f"      aws ecs execute-command --cluster multimodal-lib-prod-cluster \\")
    print(f"        --task {task['task_id']} \\")
    print(f"        --container {task['container_name']} \\")
    print(f"        --interactive --command '/bin/bash'")
    print(f"")
    print(f"   2. Once inside, test the health endpoint:")
    print(f"      curl -v http://localhost:8000/api/health/minimal")
    print(f"      curl -v http://localhost:8000/health/simple")
    print(f"      curl -v http://localhost:8000/health/minimal")
    print(f"")
    print(f"   3. Check if curl is available:")
    print(f"      which curl")
    print(f"      curl --version")
    print(f"")
    print(f"   4. Try alternative health check command:")
    print(f"      python -c 'import urllib.request; urllib.request.urlopen(\"http://localhost:8000/api/health/minimal\")'")
    
    # Save results
    results = {
        'timestamp': datetime.now().isoformat(),
        'task': task,
        'health_check_config': health_check if health_check else None,
        'logs_found': len(log_events['events']) if 'log_events' in locals() else 0
    }
    
    output_file = f'health-endpoint-diagnosis-{int(time.time())}.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n📝 Results saved to: {output_file}")
    print("="*80)

if __name__ == '__main__':
    test_health_endpoints()
