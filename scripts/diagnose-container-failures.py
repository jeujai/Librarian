#!/usr/bin/env python3
"""
Diagnose Container-Level Failures

This script detects kernel/container-level failures that don't appear in application logs:
- OOM kills (Exit Code 137)
- Segmentation faults (Exit Code 139)
- Killed by orchestrator (Exit Code 143)
- Resource exhaustion issues

These failures happen at the kernel/container level, below the application logging layer,
so they only appear in ECS task status and exit codes, not in CloudWatch logs.

Usage:
    python scripts/diagnose-container-failures.py
    python scripts/diagnose-container-failures.py --cluster my-cluster --service my-service
"""

import boto3
import argparse
from datetime import datetime, timedelta
from typing import Dict, List, Any

# Exit code meanings
EXIT_CODES = {
    0: "Success",
    1: "General error",
    126: "Command cannot execute",
    127: "Command not found",
    128: "Invalid exit argument",
    130: "Terminated by Ctrl+C",
    137: "OOM Kill (SIGKILL - Out of Memory)",
    139: "Segmentation Fault",
    143: "Terminated by orchestrator (SIGTERM)",
    255: "Exit status out of range"
}

def get_stopped_tasks(cluster: str, service: str, max_results: int = 20) -> List[str]:
    """Get recently stopped tasks."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    response = ecs.list_tasks(
        cluster=cluster,
        serviceName=service,
        desiredStatus='STOPPED',
        maxResults=max_results
    )
    
    return response['taskArns']

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
        'stopped_at': stopped_at,
        'started_at': started_at,
        'runtime_seconds': runtime_seconds,
        'failure_type': failure_type,
        'is_infrastructure_failure': is_infrastructure_failure,
        'task_definition': task['taskDefinitionArn'].split('/')[-1]
    }

def get_task_resource_limits(task_definition_arn: str) -> Dict[str, Any]:
    """Get memory and CPU limits from task definition."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    response = ecs.describe_task_definition(taskDefinition=task_definition_arn)
    task_def = response['taskDefinition']
    
    # Get task-level resources
    task_memory = task_def.get('memory')
    task_cpu = task_def.get('cpu')
    
    # Get container-level resources
    container_resources = []
    for container in task_def.get('containerDefinitions', []):
        container_resources.append({
            'name': container['name'],
            'memory': container.get('memory'),
            'memory_reservation': container.get('memoryReservation'),
            'cpu': container.get('cpu')
        })
    
    return {
        'task_memory': task_memory,
        'task_cpu': task_cpu,
        'containers': container_resources
    }

def diagnose_container_failures(cluster: str, service: str):
    """Main diagnostic function."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("=" * 80)
    print("CONTAINER-LEVEL FAILURE DIAGNOSIS")
    print("=" * 80)
    print(f"Cluster: {cluster}")
    print(f"Service: {service}")
    print()
    
    # Get stopped tasks
    print("1. RETRIEVING STOPPED TASKS")
    print("-" * 80)
    
    task_arns = get_stopped_tasks(cluster, service, max_results=20)
    
    if not task_arns:
        print("✓ No stopped tasks found - service is running cleanly!")
        print()
        return True
    
    print(f"Found {len(task_arns)} stopped tasks")
    print()
    
    # Describe tasks
    response = ecs.describe_tasks(cluster=cluster, tasks=task_arns)
    tasks = response['tasks']
    
    # Analyze each task
    print("2. ANALYZING TASK FAILURES")
    print("-" * 80)
    
    failures = []
    for task in tasks:
        analysis = analyze_task_failure(task)
        failures.append(analysis)
    
    # Group by failure type
    failure_counts = {}
    infrastructure_failures = []
    
    for failure in failures:
        failure_type = failure['failure_type']
        failure_counts[failure_type] = failure_counts.get(failure_type, 0) + 1
        
        if failure['is_infrastructure_failure']:
            infrastructure_failures.append(failure)
    
    # Print summary
    print("Failure Summary:")
    for failure_type, count in sorted(failure_counts.items(), key=lambda x: -x[1]):
        print(f"  {failure_type}: {count}")
    print()
    
    # Detailed analysis of infrastructure failures
    if infrastructure_failures:
        print("3. INFRASTRUCTURE-LEVEL FAILURES DETECTED")
        print("-" * 80)
        print()
        
        for failure in infrastructure_failures[:5]:  # Show first 5
            print(f"Task: {failure['task_id']}")
            print(f"  Failure Type: {failure['failure_type']}")
            print(f"  Exit Code: {failure['exit_code']} ({failure['exit_code_meaning']})")
            print(f"  Stop Reason: {failure['stop_reason']}")
            
            if failure['runtime_seconds']:
                print(f"  Runtime: {failure['runtime_seconds']:.1f} seconds")
            
            if failure['stopped_at']:
                print(f"  Stopped At: {failure['stopped_at'].strftime('%Y-%m-%d %H:%M:%S')}")
            
            print()
        
        # Get resource limits for OOM analysis
        if any(f['failure_type'] == 'OOM Kill' for f in infrastructure_failures):
            print("4. RESOURCE LIMIT ANALYSIS")
            print("-" * 80)
            
            # Get task definition from most recent failure
            task_def_arn = infrastructure_failures[0]['task_definition']
            resources = get_task_resource_limits(task_def_arn)
            
            print(f"Task Definition: {task_def_arn}")
            print(f"Task Memory Limit: {resources['task_memory']} MB")
            print(f"Task CPU: {resources['task_cpu']}")
            print()
            
            print("Container Resources:")
            for container in resources['containers']:
                print(f"  {container['name']}:")
                print(f"    Hard Limit: {container['memory']} MB")
                print(f"    Soft Limit: {container['memory_reservation']} MB")
                print(f"    CPU: {container['cpu']}")
            print()
        
        # Recommendations
        print("5. RECOMMENDATIONS")
        print("-" * 80)
        
        oom_count = sum(1 for f in infrastructure_failures if f['failure_type'] == 'OOM Kill')
        
        if oom_count > 0:
            print(f"⚠ {oom_count} OOM Kill(s) detected")
            print()
            print("OOM kills happen when containers exceed memory limits.")
            print("The Linux kernel terminates the process with SIGKILL (exit 137).")
            print()
            print("Solutions:")
            print("  1. Increase container memory limits in task definition")
            print("  2. Reduce number of Uvicorn workers (--workers flag)")
            print("  3. Optimize application memory usage")
            print("  4. Use progressive model loading to spread memory usage")
            print()
            print("Current configuration check:")
            print("  - Review task definition memory limits")
            print("  - Check Uvicorn worker count in Dockerfile CMD")
            print("  - Monitor memory usage with CloudWatch Container Insights")
            print()
        
        segfault_count = sum(1 for f in infrastructure_failures if f['failure_type'] == 'Segmentation Fault')
        
        if segfault_count > 0:
            print(f"⚠ {segfault_count} Segmentation Fault(s) detected")
            print()
            print("Segfaults indicate memory corruption or invalid memory access.")
            print()
            print("Solutions:")
            print("  1. Check for native library issues (PyTorch, NumPy, etc.)")
            print("  2. Update dependencies to latest stable versions")
            print("  3. Review any C extensions or native code")
            print()
        
        return False
    
    else:
        print("3. NO INFRASTRUCTURE FAILURES DETECTED")
        print("-" * 80)
        print()
        print("All failures are application-level (health checks, app errors).")
        print("These should be visible in CloudWatch logs.")
        print()
        print("Use these scripts to investigate:")
        print("  - scripts/check-startup-logs.py")
        print("  - scripts/diagnose-health-check-failure.py")
        print()
        
        return True

def main():
    parser = argparse.ArgumentParser(
        description='Diagnose container-level failures (OOM, segfaults, etc.)'
    )
    parser.add_argument(
        '--cluster',
        default='multimodal-lib-prod-cluster',
        help='ECS cluster name'
    )
    parser.add_argument(
        '--service',
        default='multimodal-lib-prod-service',
        help='ECS service name'
    )
    
    args = parser.parse_args()
    
    success = diagnose_container_failures(args.cluster, args.service)
    
    print("=" * 80)
    if success:
        print("✓ No critical infrastructure failures detected")
    else:
        print("⚠ Infrastructure failures detected - see recommendations above")
    print("=" * 80)

if __name__ == "__main__":
    main()
