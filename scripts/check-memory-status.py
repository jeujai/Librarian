#!/usr/bin/env python3
"""
Quick status check for memory configuration and health.
"""

import boto3
from datetime import datetime, timedelta

def check_memory_status():
    """Check current memory status and recent OOM kills."""
    
    CLUSTER_NAME = "multimodal-lib-prod-cluster"
    SERVICE_NAME = "multimodal-lib-prod-service"
    
    ecs = boto3.client('ecs')
    cloudwatch = boto3.client('cloudwatch')
    
    print("=" * 80)
    print("MEMORY STATUS CHECK")
    print("=" * 80)
    print()
    
    # Get current task
    print("📊 Current Task Configuration:")
    print("-" * 80)
    
    tasks_response = ecs.list_tasks(
        cluster=CLUSTER_NAME,
        serviceName=SERVICE_NAME,
        desiredStatus='RUNNING'
    )
    
    if tasks_response['taskArns']:
        tasks_detail = ecs.describe_tasks(
            cluster=CLUSTER_NAME,
            tasks=tasks_response['taskArns']
        )
        
        for task in tasks_detail['tasks']:
            task_id = task['taskArn'].split('/')[-1][:12]
            memory = task.get('memory', 'N/A')
            cpu = task.get('cpu', 'N/A')
            status = task['lastStatus']
            health = task.get('healthStatus', 'UNKNOWN')
            started = task.get('startedAt', 'N/A')
            
            print(f"  Task ID: {task_id}")
            print(f"  Memory: {memory} MB ({int(memory)/1024:.1f} GB)")
            print(f"  CPU: {cpu} units ({int(cpu)/1024:.1f} vCPUs)")
            print(f"  Status: {status}")
            print(f"  Health: {health}")
            print(f"  Started: {started}")
            print()
    else:
        print("  ⚠️  No running tasks found")
        print()
    
    # Check for recent OOM kills
    print("🔍 Recent OOM Kill Check (Last 1 Hour):")
    print("-" * 80)
    
    # Get stopped tasks
    stopped_tasks = ecs.list_tasks(
        cluster=CLUSTER_NAME,
        serviceName=SERVICE_NAME,
        desiredStatus='STOPPED'
    )
    
    if stopped_tasks['taskArns']:
        stopped_detail = ecs.describe_tasks(
            cluster=CLUSTER_NAME,
            tasks=stopped_tasks['taskArns'][:5]  # Check last 5 stopped tasks
        )
        
        oom_count = 0
        for task in stopped_detail['tasks']:
            stopped_at = task.get('stoppedAt')
            if stopped_at and (datetime.now(stopped_at.tzinfo) - stopped_at) < timedelta(hours=1):
                stop_code = task.get('stopCode', 'N/A')
                containers = task.get('containers', [])
                
                for container in containers:
                    exit_code = container.get('exitCode')
                    if exit_code == 137:  # OOM kill
                        oom_count += 1
                        task_id = task['taskArn'].split('/')[-1][:12]
                        print(f"  ⚠️  OOM Kill detected: Task {task_id}")
                        print(f"      Stopped: {stopped_at}")
                        print(f"      Exit Code: {exit_code}")
                        print()
        
        if oom_count == 0:
            print("  ✅ No OOM kills in the last hour")
            print()
    else:
        print("  ✅ No stopped tasks found")
        print()
    
    # Get memory utilization from CloudWatch
    print("📈 Memory Utilization (Last 1 Hour):")
    print("-" * 80)
    
    try:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=1)
        
        response = cloudwatch.get_metric_statistics(
            Namespace='AWS/ECS',
            MetricName='MemoryUtilization',
            Dimensions=[
                {'Name': 'ClusterName', 'Value': CLUSTER_NAME},
                {'Name': 'ServiceName', 'Value': SERVICE_NAME}
            ],
            StartTime=start_time,
            EndTime=end_time,
            Period=300,  # 5 minutes
            Statistics=['Average', 'Maximum']
        )
        
        if response['Datapoints']:
            datapoints = sorted(response['Datapoints'], key=lambda x: x['Timestamp'])
            
            avg_values = [dp['Average'] for dp in datapoints]
            max_values = [dp['Maximum'] for dp in datapoints]
            
            avg_memory = sum(avg_values) / len(avg_values)
            max_memory = max(max_values)
            
            print(f"  Average: {avg_memory:.1f}%")
            print(f"  Maximum: {max_memory:.1f}%")
            print()
            
            if max_memory > 90:
                print("  ⚠️  WARNING: Memory usage is very high (>90%)")
                print("     Consider increasing memory further")
            elif max_memory > 80:
                print("  ⚠️  CAUTION: Memory usage is high (>80%)")
                print("     Monitor closely for potential issues")
            else:
                print("  ✅ Memory usage is healthy (<80%)")
            print()
        else:
            print("  ℹ️  No metrics available yet (task may be newly started)")
            print()
            
    except Exception as e:
        print(f"  ⚠️  Could not fetch CloudWatch metrics: {e}")
        print()
    
    # Service health
    print("🏥 Service Health:")
    print("-" * 80)
    
    service_response = ecs.describe_services(
        cluster=CLUSTER_NAME,
        services=[SERVICE_NAME]
    )
    
    service = service_response['services'][0]
    running = service['runningCount']
    desired = service['desiredCount']
    
    print(f"  Running Tasks: {running}/{desired}")
    
    if running == desired:
        print("  ✅ Service is healthy")
    else:
        print("  ⚠️  Service is not at desired capacity")
    print()
    
    # Recent events
    print("📝 Recent Service Events:")
    print("-" * 80)
    
    events = service.get('events', [])[:3]
    for event in events:
        timestamp = event['createdAt']
        message = event['message']
        print(f"  [{timestamp.strftime('%H:%M:%S')}] {message}")
    print()
    
    print("=" * 80)
    print("Status check complete!")
    print()
    print("💡 Tips:")
    print("  • Run this script regularly to monitor memory health")
    print("  • Watch for OOM kills (should be zero with 20GB)")
    print("  • Keep memory utilization below 80% for safety")
    print("  • Check CloudWatch for detailed metrics and trends")
    print()

if __name__ == "__main__":
    check_memory_status()
