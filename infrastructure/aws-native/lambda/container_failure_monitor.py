"""
AWS Lambda Function: Container Failure Monitor

Detects kernel/container-level failures (OOM kills, segfaults, etc.) by checking
ECS task exit codes and stop reasons. Sends alerts via SNS when failures are detected.

This function runs on a schedule (e.g., every 5 minutes) to continuously monitor
for infrastructure-level failures that don't appear in application logs.
"""

import boto3
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any

# Environment variables
CLUSTER_NAME = os.environ.get('ECS_CLUSTER_NAME', 'multimodal-lib-prod-cluster')
SERVICE_NAME = os.environ.get('ECS_SERVICE_NAME', 'multimodal-lib-prod-service')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')
CHECK_WINDOW_MINUTES = int(os.environ.get('CHECK_WINDOW_MINUTES', '5'))

# Exit code meanings
EXIT_CODES = {
    0: "Success",
    1: "General error",
    137: "OOM Kill (SIGKILL - Out of Memory)",
    139: "Segmentation Fault",
    143: "Terminated by orchestrator (SIGTERM)",
}

def lambda_handler(event, context):
    """Main Lambda handler."""
    print(f"Starting container failure check for {CLUSTER_NAME}/{SERVICE_NAME}")
    
    try:
        failures = check_container_failures()
        
        if failures['infrastructure_failures']:
            send_alert(failures)
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'ALERT_SENT',
                    'failures_detected': len(failures['infrastructure_failures']),
                    'failure_types': failures['failure_counts']
                })
            }
        else:
            print("No infrastructure failures detected")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'status': 'OK',
                    'message': 'No infrastructure failures detected'
                })
            }
            
    except Exception as e:
        print(f"Error in container failure check: {e}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'status': 'ERROR',
                'error': str(e)
            })
        }

def check_container_failures() -> Dict[str, Any]:
    """Check for container-level failures."""
    ecs = boto3.client('ecs')
    
    # Get stopped tasks from the last CHECK_WINDOW_MINUTES (timezone-aware)
    cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=CHECK_WINDOW_MINUTES)
    
    response = ecs.list_tasks(
        cluster=CLUSTER_NAME,
        serviceName=SERVICE_NAME,
        desiredStatus='STOPPED',
        maxResults=100
    )
    
    if not response['taskArns']:
        return {
            'infrastructure_failures': [],
            'failure_counts': {},
            'all_failures': []
        }
    
    # Describe tasks
    response = ecs.describe_tasks(
        cluster=CLUSTER_NAME,
        tasks=response['taskArns']
    )
    
    # Analyze failures
    infrastructure_failures = []
    all_failures = []
    failure_counts = {}
    
    for task in response['tasks']:
        # Only check tasks stopped within our window
        stopped_at = task.get('stoppedAt')
        if stopped_at and stopped_at < cutoff_time:
            continue
        
        analysis = analyze_task_failure(task)
        all_failures.append(analysis)
        
        # Track failure types
        failure_type = analysis['failure_type']
        failure_counts[failure_type] = failure_counts.get(failure_type, 0) + 1
        
        # Collect infrastructure failures
        if analysis['is_infrastructure_failure']:
            infrastructure_failures.append(analysis)
    
    return {
        'infrastructure_failures': infrastructure_failures,
        'failure_counts': failure_counts,
        'all_failures': all_failures
    }

def analyze_task_failure(task: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze a stopped task for failure indicators."""
    task_id = task['taskArn'].split('/')[-1][:12]
    
    # Get container exit code
    exit_code = None
    container_reason = None
    
    if task.get('containers'):
        container = task['containers'][0]
        exit_code = container.get('exitCode')
        container_reason = container.get('reason', '')
    
    # Get task stop reason
    stop_reason = task.get('stoppedReason', 'Unknown')
    stopped_at = task.get('stoppedAt')
    started_at = task.get('startedAt')
    
    # Calculate runtime
    runtime_seconds = None
    if stopped_at and started_at:
        runtime_seconds = (stopped_at - started_at).total_seconds()
    
    # Determine failure type
    failure_type = "Unknown"
    is_infrastructure_failure = False
    
    if exit_code == 137:
        failure_type = "OOM Kill"
        is_infrastructure_failure = True
    elif exit_code == 139:
        failure_type = "Segmentation Fault"
        is_infrastructure_failure = True
    elif exit_code == 143:
        failure_type = "Orchestrator Termination"
        is_infrastructure_failure = True
    elif "OutOfMemory" in stop_reason or "OOM" in stop_reason:
        failure_type = "OOM Kill"
        is_infrastructure_failure = True
    elif "health checks failed" in stop_reason.lower():
        failure_type = "Health Check Failure"
    elif exit_code and exit_code != 0:
        failure_type = f"Application Error (Exit {exit_code})"
    
    return {
        'task_id': task_id,
        'exit_code': exit_code,
        'exit_code_meaning': EXIT_CODES.get(exit_code, "Unknown"),
        'stop_reason': stop_reason,
        'container_reason': container_reason,
        'stopped_at': stopped_at.isoformat() if stopped_at else None,
        'started_at': started_at.isoformat() if started_at else None,
        'runtime_seconds': runtime_seconds,
        'failure_type': failure_type,
        'is_infrastructure_failure': is_infrastructure_failure,
        'task_definition': task['taskDefinitionArn'].split('/')[-1]
    }

def send_alert(failures: Dict[str, Any]):
    """Send SNS alert about infrastructure failures."""
    if not SNS_TOPIC_ARN:
        print("No SNS topic configured, skipping alert")
        return
    
    sns = boto3.client('sns')
    
    infrastructure_failures = failures['infrastructure_failures']
    failure_counts = failures['failure_counts']
    
    # Build alert message
    subject = f"⚠️ Container Failures Detected: {CLUSTER_NAME}/{SERVICE_NAME}"
    
    message_lines = [
        "CONTAINER-LEVEL FAILURE ALERT",
        "=" * 60,
        f"Cluster: {CLUSTER_NAME}",
        f"Service: {SERVICE_NAME}",
        f"Time: {datetime.now(timezone.utc).isoformat()}",
        f"Check Window: Last {CHECK_WINDOW_MINUTES} minutes",
        "",
        "FAILURE SUMMARY",
        "-" * 60
    ]
    
    for failure_type, count in sorted(failure_counts.items(), key=lambda x: -x[1]):
        message_lines.append(f"  {failure_type}: {count}")
    
    message_lines.extend([
        "",
        "INFRASTRUCTURE FAILURES DETECTED",
        "-" * 60
    ])
    
    for failure in infrastructure_failures[:5]:  # Show first 5
        message_lines.extend([
            f"",
            f"Task: {failure['task_id']}",
            f"  Failure Type: {failure['failure_type']}",
            f"  Exit Code: {failure['exit_code']} ({failure['exit_code_meaning']})",
            f"  Stop Reason: {failure['stop_reason'][:100]}",
        ])
        
        if failure['runtime_seconds']:
            message_lines.append(f"  Runtime: {failure['runtime_seconds']:.1f} seconds")
        
        if failure['stopped_at']:
            message_lines.append(f"  Stopped At: {failure['stopped_at']}")
    
    if len(infrastructure_failures) > 5:
        message_lines.append(f"\n... and {len(infrastructure_failures) - 5} more failures")
    
    # Add recommendations
    message_lines.extend([
        "",
        "RECOMMENDED ACTIONS",
        "-" * 60
    ])
    
    oom_count = sum(1 for f in infrastructure_failures if f['failure_type'] == 'OOM Kill')
    
    if oom_count > 0:
        message_lines.extend([
            f"⚠️ {oom_count} OOM Kill(s) detected",
            "",
            "OOM kills indicate containers are exceeding memory limits.",
            "Solutions:",
            "  1. Increase container memory limits in task definition",
            "  2. Reduce number of Uvicorn workers",
            "  3. Optimize application memory usage",
            "  4. Use progressive model loading",
            "",
            "Investigation:",
            f"  aws ecs describe-task-definition --task-definition {infrastructure_failures[0]['task_definition']}",
            f"  python scripts/diagnose-container-failures.py",
        ])
    
    segfault_count = sum(1 for f in infrastructure_failures if f['failure_type'] == 'Segmentation Fault')
    
    if segfault_count > 0:
        message_lines.extend([
            "",
            f"⚠️ {segfault_count} Segmentation Fault(s) detected",
            "",
            "Segfaults indicate memory corruption or invalid memory access.",
            "Solutions:",
            "  1. Check for native library issues (PyTorch, NumPy, etc.)",
            "  2. Update dependencies to latest stable versions",
            "  3. Review any C extensions or native code",
        ])
    
    message = "\n".join(message_lines)
    
    # Send SNS notification
    try:
        response = sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message
        )
        print(f"Alert sent successfully: {response['MessageId']}")
    except Exception as e:
        print(f"Failed to send SNS alert: {e}")
        raise
