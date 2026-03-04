#!/usr/bin/env python3
"""
Test Health Check Endpoint

This script tests the health check endpoint directly to diagnose why ECS health checks are failing.
"""

import boto3
import json
import time
from datetime import datetime

def get_task_ip(cluster_name, task_arn):
    """Get the private IP address of a task."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    response = ecs.describe_tasks(
        cluster=cluster_name,
        tasks=[task_arn]
    )
    
    if not response['tasks']:
        return None
    
    task = response['tasks'][0]
    containers = task.get('containers', [])
    
    if not containers:
        return None
    
    network_interfaces = containers[0].get('networkInterfaces', [])
    if not network_interfaces:
        return None
    
    return network_interfaces[0].get('privateIpv4Address')

def check_health_endpoint(task_ip, port=8000):
    """Check if the health endpoint is responding."""
    import urllib.request
    import urllib.error
    
    url = f"http://{task_ip}:{port}/api/health/minimal"
    
    try:
        print(f"Testing health endpoint: {url}")
        req = urllib.request.Request(url, method='GET')
        
        start_time = time.time()
        with urllib.request.urlopen(req, timeout=10) as response:
            response_time = (time.time() - start_time) * 1000
            status_code = response.status
            body = response.read().decode('utf-8')
            
            print(f"✓ Health check successful!")
            print(f"  Status Code: {status_code}")
            print(f"  Response Time: {response_time:.2f}ms")
            print(f"  Response Body: {body}")
            
            return True, status_code, body
            
    except urllib.error.HTTPError as e:
        print(f"✗ HTTP Error: {e.code} - {e.reason}")
        body = e.read().decode('utf-8') if e.fp else None
        print(f"  Response Body: {body}")
        return False, e.code, body
        
    except urllib.error.URLError as e:
        print(f"✗ URL Error: {e.reason}")
        return False, None, str(e.reason)
        
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False, None, str(e)

def main():
    """Main function."""
    cluster_name = "multimodal-lib-prod-cluster"
    
    # Get running tasks
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("=" * 80)
    print("HEALTH CHECK ENDPOINT DIAGNOSTIC")
    print("=" * 80)
    print()
    
    # List tasks
    print("Finding running tasks...")
    response = ecs.list_tasks(
        cluster=cluster_name,
        desiredStatus='RUNNING'
    )
    
    task_arns = response.get('taskArns', [])
    
    if not task_arns:
        print("✗ No running tasks found")
        return
    
    print(f"✓ Found {len(task_arns)} running task(s)")
    print()
    
    # Test each task
    for i, task_arn in enumerate(task_arns, 1):
        task_id = task_arn.split('/')[-1]
        print(f"Task {i}/{len(task_arns)}: {task_id}")
        print("-" * 80)
        
        # Get task details
        response = ecs.describe_tasks(
            cluster=cluster_name,
            tasks=[task_arn]
        )
        
        if not response['tasks']:
            print("✗ Could not get task details")
            continue
        
        task = response['tasks'][0]
        
        # Print task info
        print(f"  Status: {task['lastStatus']}")
        print(f"  Health: {task.get('healthStatus', 'UNKNOWN')}")
        print(f"  Started: {task.get('startedAt', 'Unknown')}")
        
        # Get IP address
        task_ip = get_task_ip(cluster_name, task_arn)
        
        if not task_ip:
            print("  ✗ Could not get task IP address")
            continue
        
        print(f"  IP Address: {task_ip}")
        print()
        
        # Test health endpoint
        print("  Testing health endpoint...")
        success, status_code, body = check_health_endpoint(task_ip)
        
        print()
        
        # Check if curl is available in the container
        print("  Checking if curl is available in container...")
        try:
            # Execute command in container
            response = ecs.execute_command(
                cluster=cluster_name,
                task=task_arn,
                container='multimodal-lib-prod-app',
                interactive=False,
                command='which curl'
            )
            print("  ✓ curl is available")
        except Exception as e:
            print(f"  ✗ Could not check curl availability: {e}")
        
        print()
    
    print("=" * 80)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 80)

if __name__ == '__main__':
    main()
