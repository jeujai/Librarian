#!/usr/bin/env python3
"""Test the health endpoint directly using the task's private IP"""

import boto3
import requests
from requests.exceptions import RequestException

def test_health_endpoint():
    ecs = boto3.client('ecs')
    ec2 = boto3.client('ec2')
    
    cluster = 'multimodal-lib-prod-cluster'
    service = 'multimodal-lib-prod-service'
    
    print("=" * 80)
    print("DIRECT HEALTH ENDPOINT TEST")
    print("=" * 80)
    
    # Get running tasks
    tasks = ecs.list_tasks(cluster=cluster, serviceName=service)['taskArns']
    
    if not tasks:
        print("❌ No running tasks found")
        return
    
    task_details = ecs.describe_tasks(cluster=cluster, tasks=tasks)['tasks']
    
    for task in task_details:
        if task['lastStatus'] != 'RUNNING':
            continue
            
        task_id = task['taskArn'].split('/')[-1]
        print(f"\nTask: {task_id}")
        
        # Get private IP
        private_ip = None
        for attachment in task.get('attachments', []):
            if attachment['type'] == 'ElasticNetworkInterface':
                for detail in attachment['details']:
                    if detail['name'] == 'privateIPv4Address':
                        private_ip = detail['value']
                        break
        
        if not private_ip:
            print("❌ Could not find private IP")
            continue
        
        print(f"Private IP: {private_ip}")
        
        # Test health endpoint
        health_url = f"http://{private_ip}:8000/api/health/minimal"
        print(f"\nTesting: {health_url}")
        
        try:
            response = requests.get(health_url, timeout=5)
            print(f"✅ Status Code: {response.status_code}")
            print(f"Response: {response.text[:200]}")
        except RequestException as e:
            print(f"❌ Request failed: {e}")
            print("\nThis is expected if running from outside AWS VPC")
            print("The health check timeout suggests the application might not be listening on port 8000")
            print("or the /api/health/minimal endpoint doesn't exist")

if __name__ == '__main__':
    test_health_endpoint()
