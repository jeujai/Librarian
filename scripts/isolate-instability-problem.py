#!/usr/bin/env python3
"""
Isolate Instability Problem

This script performs a comprehensive diagnosis to isolate the root cause
of the persistent task instability in multimodal-lib-prod-service-alb.

It checks:
1. Current service and task status
2. Recent task stop reasons
3. Health check configuration
4. CloudWatch logs for errors
5. Network connectivity
6. Resource utilization
"""

import boto3
import json
import time
from datetime import datetime, timedelta
from collections import Counter

# AWS clients
ecs_client = boto3.client('ecs', region_name='us-east-1')
logs_client = boto3.client('logs', region_name='us-east-1')
elbv2_client = boto3.client('elbv2', region_name='us-east-1')

# Configuration
CLUSTER_NAME = 'multimodal-lib-prod-cluster'
SERVICE_NAME = 'multimodal-lib-prod-service-alb'
LOG_GROUP = '/ecs/multimodal-lib-prod-task'


def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def get_service_status():
    """Get current service status."""
    print_section("1. SERVICE STATUS")
    
    response = ecs_client.describe_services(
        cluster=CLUSTER_NAME,
        services=[SERVICE_NAME]
    )
    
    if not response['services']:
        print("❌ Service not found!")
        return None
    
    service = response['services'][0]
    
    print(f"Service: {service['serviceName']}")
    print(f"Status: {service['status']}")
    print(f"Desired Count: {service['desiredCount']}")
    print(f"Running Count: {service['runningCount']}")
    print(f"Pending Count: {service['pendingCount']}")
    
    # Deployments
    print(f"\nDeployments: {len(service['deployments'])}")
    for deployment in service['deployments']:
        print(f"  - Status: {deployment['status']}")
        print(f"    Task Definition: {deployment['taskDefinition'].split('/')[-1]}")
        print(f"    Desired: {deployment['desiredCount']}, Running: {deployment['runningCount']}, Pending: {deployment['pendingCount']}")
    
    # Events
    print(f"\nRecent Events (last 5):")
    for event in service['events'][:5]:
        print(f"  [{event['createdAt']}] {event['message']}")
    
    return service


def analyze_stopped_tasks():
    """Analyze recently stopped tasks."""
    print_section("2. STOPPED TASKS ANALYSIS")
    
    # Get stopped tasks from last hour
    response = ecs_client.list_tasks(
        cluster=CLUSTER_NAME,
        serviceName=SERVICE_NAME,
        desiredStatus='STOPPED',
        maxResults=100
    )
    
    if not response['taskArns']:
        print("✅ No stopped tasks found")
        return
    
    print(f"Found {len(response['taskArns'])} stopped tasks")
    
    # Get task details
    tasks_response = ecs_client.describe_tasks(
        cluster=CLUSTER_NAME,
        tasks=response['taskArns']
    )
    
    # Analyze stop reasons
    stop_reasons = []
    stop_codes = []
    
    print("\nRecent Task Failures:")
    for task in tasks_response['tasks'][:10]:  # Show last 10
        stopped_at = task.get('stoppedAt', 'Unknown')
        stop_reason = task.get('stoppedReason', 'Unknown')
        stop_code = task.get('stopCode', 'Unknown')
        
        stop_reasons.append(stop_reason)
        stop_codes.append(stop_code)
        
        print(f"\n  Task: {task['taskArn'].split('/')[-1]}")
        print(f"  Stopped At: {stopped_at}")
        print(f"  Stop Code: {stop_code}")
        print(f"  Stop Reason: {stop_reason}")
        
        # Check container exit codes
        for container in task.get('containers', []):
            if 'exitCode' in container:
                print(f"  Container '{container['name']}' Exit Code: {container['exitCode']}")
            if 'reason' in container:
                print(f"  Container Reason: {container['reason']}")
    
    # Summary
    print("\n" + "-" * 80)
    print("STOP REASON SUMMARY:")
    reason_counts = Counter(stop_reasons)
    for reason, count in reason_counts.most_common():
        print(f"  {count}x: {reason}")
    
    print("\nSTOP CODE SUMMARY:")
    code_counts = Counter(stop_codes)
    for code, count in code_counts.most_common():
        print(f"  {count}x: {code}")


def check_health_check_config():
    """Check ALB health check configuration."""
    print_section("3. HEALTH CHECK CONFIGURATION")
    
    # Get service to find target group
    service_response = ecs_client.describe_services(
        cluster=CLUSTER_NAME,
        services=[SERVICE_NAME]
    )
    
    if not service_response['services']:
        print("❌ Service not found")
        return
    
    service = service_response['services'][0]
    load_balancers = service.get('loadBalancers', [])
    
    if not load_balancers:
        print("❌ No load balancer configured")
        return
    
    target_group_arn = load_balancers[0]['targetGroupArn']
    
    # Get target group details
    tg_response = elbv2_client.describe_target_groups(
        TargetGroupArns=[target_group_arn]
    )
    
    tg = tg_response['TargetGroups'][0]
    
    print(f"Target Group: {tg['TargetGroupName']}")
    print(f"Protocol: {tg['Protocol']}")
    print(f"Port: {tg['Port']}")
    print(f"Health Check Protocol: {tg['HealthCheckProtocol']}")
    print(f"Health Check Path: {tg['HealthCheckPath']}")
    print(f"Health Check Interval: {tg['HealthCheckIntervalSeconds']}s")
    print(f"Health Check Timeout: {tg['HealthCheckTimeoutSeconds']}s")
    print(f"Healthy Threshold: {tg['HealthyThresholdCount']}")
    print(f"Unhealthy Threshold: {tg['UnhealthyThresholdCount']}")
    
    # Get target health
    health_response = elbv2_client.describe_target_health(
        TargetGroupArn=target_group_arn
    )
    
    print(f"\nTarget Health ({len(health_response['TargetHealthDescriptions'])} targets):")
    for target in health_response['TargetHealthDescriptions']:
        state = target['TargetHealth']['State']
        reason = target['TargetHealth'].get('Reason', 'N/A')
        description = target['TargetHealth'].get('Description', 'N/A')
        
        print(f"  Target {target['Target']['Id']}:{target['Target']['Port']}")
        print(f"    State: {state}")
        print(f"    Reason: {reason}")
        print(f"    Description: {description}")


def analyze_cloudwatch_logs():
    """Analyze recent CloudWatch logs for errors."""
    print_section("4. CLOUDWATCH LOGS ANALYSIS")
    
    # Get logs from last 10 minutes
    end_time = int(time.time() * 1000)
    start_time = end_time - (10 * 60 * 1000)  # 10 minutes ago
    
    try:
        # Get log streams
        streams_response = logs_client.describe_log_streams(
            logGroupName=LOG_GROUP,
            orderBy='LastEventTime',
            descending=True,
            limit=5
        )
        
        if not streams_response['logStreams']:
            print("❌ No log streams found")
            return
        
        print(f"Analyzing {len(streams_response['logStreams'])} most recent log streams...")
        
        error_patterns = [
            'error',
            'exception',
            'failed',
            'timeout',
            'unhealthy',
            'connection refused',
            'cannot connect',
            'opensearch',
            'neptune'
        ]
        
        errors_found = []
        
        for stream in streams_response['logStreams']:
            stream_name = stream['logStreamName']
            
            try:
                events_response = logs_client.get_log_events(
                    logGroupName=LOG_GROUP,
                    logStreamName=stream_name,
                    startTime=start_time,
                    endTime=end_time,
                    limit=100
                )
                
                for event in events_response['events']:
                    message = event['message'].lower()
                    
                    # Check for error patterns
                    for pattern in error_patterns:
                        if pattern in message:
                            errors_found.append({
                                'timestamp': datetime.fromtimestamp(event['timestamp'] / 1000),
                                'pattern': pattern,
                                'message': event['message'][:200]  # First 200 chars
                            })
                            break
            
            except Exception as e:
                print(f"  Warning: Could not read stream {stream_name}: {e}")
        
        if errors_found:
            print(f"\n⚠️  Found {len(errors_found)} error messages:")
            
            # Group by pattern
            pattern_counts = Counter([e['pattern'] for e in errors_found])
            print("\nError Pattern Summary:")
            for pattern, count in pattern_counts.most_common():
                print(f"  {count}x: {pattern}")
            
            print("\nRecent Errors (last 5):")
            for error in errors_found[-5:]:
                print(f"\n  [{error['timestamp']}] Pattern: {error['pattern']}")
                print(f"  {error['message']}")
        else:
            print("✅ No obvious errors found in recent logs")
    
    except Exception as e:
        print(f"❌ Error analyzing logs: {e}")


def check_task_definition():
    """Check current task definition configuration."""
    print_section("5. TASK DEFINITION CONFIGURATION")
    
    # Get service to find task definition
    service_response = ecs_client.describe_services(
        cluster=CLUSTER_NAME,
        services=[SERVICE_NAME]
    )
    
    if not service_response['services']:
        print("❌ Service not found")
        return
    
    task_def_arn = service_response['services'][0]['taskDefinition']
    
    # Get task definition
    task_def_response = ecs_client.describe_task_definition(
        taskDefinition=task_def_arn
    )
    
    task_def = task_def_response['taskDefinition']
    
    print(f"Task Definition: {task_def['family']}:{task_def['revision']}")
    print(f"CPU: {task_def['cpu']}")
    print(f"Memory: {task_def['memory']}")
    print(f"Network Mode: {task_def['networkMode']}")
    
    # Check container definition
    container = task_def['containerDefinitions'][0]
    
    print(f"\nContainer: {container['name']}")
    print(f"Image: {container['image']}")
    
    # Check for database-related environment variables
    print("\nDatabase-Related Environment Variables:")
    db_vars = [
        'SKIP_OPENSEARCH_INIT',
        'SKIP_NEPTUNE_INIT',
        'ENABLE_VECTOR_SEARCH',
        'OPENSEARCH_ENDPOINT',
        'NEPTUNE_ENDPOINT',
        'OPENSEARCH_TIMEOUT',
        'NEPTUNE_TIMEOUT'
    ]
    
    env_vars = {env['name']: env['value'] for env in container.get('environment', [])}
    
    for var in db_vars:
        value = env_vars.get(var, 'NOT SET')
        print(f"  {var}: {value}")
    
    # Check health check
    if 'healthCheck' in container:
        hc = container['healthCheck']
        print(f"\nContainer Health Check:")
        print(f"  Command: {' '.join(hc['command'])}")
        print(f"  Interval: {hc.get('interval', 'N/A')}s")
        print(f"  Timeout: {hc.get('timeout', 'N/A')}s")
        print(f"  Retries: {hc.get('retries', 'N/A')}")
    else:
        print("\n⚠️  No container health check configured")


def diagnose_problem():
    """Main diagnosis function."""
    print("=" * 80)
    print("INSTABILITY PROBLEM ISOLATION")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Cluster: {CLUSTER_NAME}")
    print(f"Service: {SERVICE_NAME}")
    
    # Run all checks
    service = get_service_status()
    
    if service:
        analyze_stopped_tasks()
        check_health_check_config()
        check_task_definition()
        analyze_cloudwatch_logs()
        
        # Final diagnosis
        print_section("DIAGNOSIS SUMMARY")
        
        # Determine most likely cause
        if service['runningCount'] == 0 and service['desiredCount'] > 0:
            print("🔴 CRITICAL: No tasks running despite desired count > 0")
            print("\nMost Likely Causes:")
            print("  1. Health check failing immediately")
            print("  2. Application crashing on startup")
            print("  3. Resource constraints (CPU/Memory)")
            print("  4. Network connectivity issues")
        elif service['runningCount'] < service['desiredCount']:
            print("⚠️  WARNING: Running count less than desired")
            print("\nMost Likely Causes:")
            print("  1. Tasks failing health checks")
            print("  2. Tasks crashing intermittently")
            print("  3. Deployment in progress")
        else:
            print("✅ Service appears stable (running == desired)")
        
        print("\nRecommended Actions:")
        print("  1. Check CloudWatch logs for specific error messages")
        print("  2. Verify health check endpoint responds quickly")
        print("  3. Check if databases are blocking startup")
        print("  4. Review task stop reasons for patterns")
        print("  5. Test health endpoint manually: curl http://<ALB>/health/simple")


if __name__ == '__main__':
    try:
        diagnose_problem()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
