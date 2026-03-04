#!/usr/bin/env python3
"""
Diagnose ECS task startup issues.
"""

import boto3
import json
import sys
from datetime import datetime

def diagnose_task_startup_issues():
    """Diagnose why ECS tasks are not starting."""
    
    try:
        # Initialize clients
        ecs_client = boto3.client('ecs', region_name='us-east-1')
        logs_client = boto3.client('logs', region_name='us-east-1')
        
        diagnosis = {
            'timestamp': datetime.now().isoformat(),
            'task_analysis': {},
            'service_events': [],
            'recommendations': []
        }
        
        print("🔍 Diagnosing ECS Task Startup Issues")
        print("=" * 40)
        
        cluster_name = 'multimodal-lib-prod-cluster'
        service_name = 'multimodal-lib-prod-service'
        
        # 1. Get service events
        print("\n1. Service Events Analysis:")
        print("-" * 28)
        
        service_details = ecs_client.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        if service_details['services']:
            service = service_details['services'][0]
            events = service.get('events', [])[:10]  # Last 10 events
            
            print(f"📋 Recent Service Events:")
            for i, event in enumerate(events, 1):
                timestamp = event['createdAt'].strftime('%Y-%m-%d %H:%M:%S')
                message = event['message']
                print(f"   {i}. [{timestamp}] {message}")
                
                diagnosis['service_events'].append({
                    'timestamp': timestamp,
                    'message': message
                })
        
        # 2. Get task details
        print("\n2. Task Details Analysis:")
        print("-" * 27)
        
        tasks_response = ecs_client.list_tasks(
            cluster=cluster_name,
            serviceName=service_name
        )
        
        if not tasks_response['taskArns']:
            print("❌ No tasks found")
            diagnosis['recommendations'].append("No tasks found - service may be failing to start tasks")
            return diagnosis
        
        task_details = ecs_client.describe_tasks(
            cluster=cluster_name,
            tasks=tasks_response['taskArns']
        )
        
        for task in task_details['tasks']:
            task_arn = task['taskArn']
            task_id = task_arn.split('/')[-1]
            
            print(f"\n📋 Task: {task_id}")
            print(f"   - Status: {task['lastStatus']}")
            print(f"   - Desired Status: {task['desiredStatus']}")
            print(f"   - Health: {task.get('healthStatus', 'UNKNOWN')}")
            print(f"   - Created: {task['createdAt']}")
            
            # Check stop reason if stopped
            if task.get('stoppedReason'):
                print(f"   - Stop Reason: {task['stoppedReason']}")
                diagnosis['recommendations'].append(f"Task {task_id} stopped: {task['stoppedReason']}")
            
            # Check container status
            containers = task.get('containers', [])
            print(f"   - Containers: {len(containers)}")
            
            for container in containers:
                container_name = container['name']
                container_status = container['lastStatus']
                
                print(f"     - {container_name}: {container_status}")
                
                if container_status != 'RUNNING':
                    reason = container.get('reason', 'Unknown')
                    exit_code = container.get('exitCode')
                    
                    print(f"       Reason: {reason}")
                    if exit_code is not None:
                        print(f"       Exit Code: {exit_code}")
                    
                    diagnosis['recommendations'].append(f"Container {container_name} not running: {reason}")
            
            # Get task definition details
            task_def_arn = task['taskDefinitionArn']
            task_def_response = ecs_client.describe_task_definition(
                taskDefinition=task_def_arn
            )
            
            task_def = task_def_response['taskDefinition']
            
            print(f"   - Task Definition: {task_def['family']}:{task_def['revision']}")
            print(f"   - CPU: {task_def.get('cpu', 'N/A')}")
            print(f"   - Memory: {task_def.get('memory', 'N/A')}")
            print(f"   - Network Mode: {task_def.get('networkMode', 'N/A')}")
            
            # Check container definitions
            container_defs = task_def.get('containerDefinitions', [])
            for container_def in container_defs:
                container_name = container_def['name']
                image = container_def['image']
                
                print(f"     - Container: {container_name}")
                print(f"       Image: {image}")
                
                # Check if image exists and is accessible
                if 'amazonaws.com' in image:
                    print(f"       ✅ Using ECR image")
                else:
                    print(f"       ⚠️  Using external image")
                
                # Check environment variables
                env_vars = container_def.get('environment', [])
                if env_vars:
                    print(f"       Environment Variables: {len(env_vars)}")
                
                # Check log configuration
                log_config = container_def.get('logConfiguration', {})
                if log_config:
                    log_driver = log_config.get('logDriver')
                    log_group = log_config.get('logOptions', {}).get('awslogs-group')
                    
                    print(f"       Log Driver: {log_driver}")
                    print(f"       Log Group: {log_group}")
                    
                    # Try to get recent logs
                    if log_group and log_driver == 'awslogs':
                        try:
                            print(f"       📄 Recent Logs:")
                            
                            # Get log streams
                            streams_response = logs_client.describe_log_streams(
                                logGroupName=log_group,
                                orderBy='LastEventTime',
                                descending=True,
                                limit=5
                            )
                            
                            for stream in streams_response['logStreams']:
                                stream_name = stream['logStreamName']
                                if task_id in stream_name:
                                    # Get recent log events
                                    events_response = logs_client.get_log_events(
                                        logGroupName=log_group,
                                        logStreamName=stream_name,
                                        limit=10,
                                        startFromHead=False
                                    )
                                    
                                    for event in events_response['events'][-5:]:  # Last 5 events
                                        timestamp = datetime.fromtimestamp(event['timestamp'] / 1000)
                                        message = event['message'].strip()
                                        print(f"         [{timestamp}] {message}")
                                    break
                        
                        except Exception as log_error:
                            print(f"       ⚠️  Could not retrieve logs: {log_error}")
            
            diagnosis['task_analysis'][task_id] = {
                'status': task['lastStatus'],
                'desired_status': task['desiredStatus'],
                'health': task.get('healthStatus', 'UNKNOWN'),
                'containers': [
                    {
                        'name': c['name'],
                        'status': c['lastStatus'],
                        'reason': c.get('reason', 'N/A')
                    }
                    for c in containers
                ]
            }
        
        # 3. Check cluster capacity
        print("\n3. Cluster Capacity Analysis:")
        print("-" * 30)
        
        cluster_details = ecs_client.describe_clusters(
            clusters=[cluster_name],
            include=['CAPACITY_PROVIDERS']
        )
        
        if cluster_details['clusters']:
            cluster = cluster_details['clusters'][0]
            
            print(f"📊 Cluster: {cluster['clusterName']}")
            print(f"   - Status: {cluster['status']}")
            print(f"   - Active Services: {cluster['activeServicesCount']}")
            print(f"   - Running Tasks: {cluster['runningTasksCount']}")
            print(f"   - Pending Tasks: {cluster['pendingTasksCount']}")
            
            # Check capacity providers
            capacity_providers = cluster.get('capacityProviders', [])
            if capacity_providers:
                print(f"   - Capacity Providers: {capacity_providers}")
            else:
                print(f"   - Using default capacity provider")
        
        # 4. Summary and Recommendations
        print("\n4. Summary and Recommendations:")
        print("-" * 35)
        
        if diagnosis['recommendations']:
            print("🚨 Issues Found:")
            for i, rec in enumerate(diagnosis['recommendations'], 1):
                print(f"   {i}. {rec}")
        else:
            print("✅ No obvious issues found in task startup")
        
        return diagnosis
        
    except Exception as e:
        print(f"❌ Error during diagnosis: {e}")
        return {'error': str(e)}

if __name__ == "__main__":
    result = diagnose_task_startup_issues()
    
    # Save diagnosis to file
    diagnosis_file = f"task-startup-diagnosis-{int(datetime.now().timestamp())}.json"
    with open(diagnosis_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 Diagnosis saved to: {diagnosis_file}")
    
    if result.get('recommendations'):
        sys.exit(1)
    else:
        sys.exit(0)