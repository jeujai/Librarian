#!/usr/bin/env python3
"""
Test if the application container is actually listening on port 8000
by attempting to connect from within the VPC.
"""

import boto3
import json
import time
from datetime import datetime

def get_task_details():
    """Get the running task details."""
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    # List tasks
    tasks_response = ecs.list_tasks(
        cluster='multimodal-lib-prod-cluster'
    )
    
    if not tasks_response['taskArns']:
        print("No tasks found")
        return None
    
    task_arn = tasks_response['taskArns'][0]
    
    # Describe task
    task_details = ecs.describe_tasks(
        cluster='multimodal-lib-prod-cluster',
        tasks=[task_arn]
    )
    
    task = task_details['tasks'][0]
    
    # Get ENI details
    for attachment in task['attachments']:
        if attachment['type'] == 'ElasticNetworkInterface':
            for detail in attachment['details']:
                if detail['name'] == 'networkInterfaceId':
                    eni_id = detail['value']
                elif detail['name'] == 'privateIPv4Address':
                    private_ip = detail['value']
    
    return {
        'task_arn': task_arn,
        'eni_id': eni_id,
        'private_ip': private_ip,
        'last_status': task['lastStatus'],
        'desired_status': task['desiredStatus'],
        'health_status': task.get('healthStatus', 'UNKNOWN')
    }

def test_port_connection(private_ip):
    """Test if we can connect to port 8000."""
    import socket
    
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((private_ip, 8000))
        sock.close()
        
        if result == 0:
            return True, "Port 8000 is open"
        else:
            return False, f"Port 8000 is closed (error code: {result})"
    except Exception as e:
        return False, f"Connection failed: {str(e)}"

def test_http_endpoint(private_ip):
    """Test if the HTTP endpoint responds."""
    import urllib.request
    import urllib.error
    
    endpoints = [
        '/api/health/simple',
        '/health',
        '/api/health',
        '/'
    ]
    
    results = {}
    
    for endpoint in endpoints:
        url = f"http://{private_ip}:8000{endpoint}"
        try:
            req = urllib.request.Request(url, method='GET')
            req.add_header('User-Agent', 'AWS-Health-Check')
            
            with urllib.request.urlopen(req, timeout=5) as response:
                status_code = response.getcode()
                body = response.read().decode('utf-8')
                results[endpoint] = {
                    'success': True,
                    'status_code': status_code,
                    'body': body[:200]  # First 200 chars
                }
        except urllib.error.HTTPError as e:
            results[endpoint] = {
                'success': False,
                'error': f"HTTP {e.code}: {e.reason}"
            }
        except Exception as e:
            results[endpoint] = {
                'success': False,
                'error': str(e)
            }
    
    return results

def main():
    print("=" * 80)
    print("Container Port 8000 Connectivity Test")
    print("=" * 80)
    print()
    
    # Get task details
    print("1. Getting task details...")
    task_info = get_task_details()
    
    if not task_info:
        print("ERROR: No running tasks found")
        return
    
    print(f"   Task ARN: {task_info['task_arn']}")
    print(f"   Private IP: {task_info['private_ip']}")
    print(f"   ENI ID: {task_info['eni_id']}")
    print(f"   Last Status: {task_info['last_status']}")
    print(f"   Health Status: {task_info['health_status']}")
    print()
    
    # Test port connection
    print("2. Testing TCP connection to port 8000...")
    port_open, port_message = test_port_connection(task_info['private_ip'])
    print(f"   {port_message}")
    print()
    
    if not port_open:
        print("ERROR: Cannot connect to port 8000")
        print()
        print("This confirms the issue: The application is NOT listening on port 8000")
        print("even though Uvicorn logs say it is.")
        print()
        print("Possible causes:")
        print("  1. Uvicorn is binding to 127.0.0.1 instead of 0.0.0.0")
        print("  2. The application is crashing after startup")
        print("  3. A firewall or security group is blocking the connection")
        print("  4. The container's network namespace is misconfigured")
        return
    
    # Test HTTP endpoints
    print("3. Testing HTTP endpoints...")
    http_results = test_http_endpoint(task_info['private_ip'])
    
    for endpoint, result in http_results.items():
        if result['success']:
            print(f"   ✓ {endpoint}: HTTP {result['status_code']}")
            print(f"     Response: {result['body']}")
        else:
            print(f"   ✗ {endpoint}: {result['error']}")
    print()
    
    # Summary
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    if port_open:
        working_endpoints = [ep for ep, res in http_results.items() if res['success']]
        if working_endpoints:
            print(f"✓ Application IS listening on port 8000")
            print(f"✓ Working endpoints: {', '.join(working_endpoints)}")
            print()
            print("The application is working correctly!")
            print("The ALB connectivity issue must be in the network path.")
        else:
            print(f"⚠ Port 8000 is open but no HTTP endpoints are responding")
            print()
            print("The application may be listening but not serving HTTP requests.")
    else:
        print(f"✗ Application is NOT listening on port 8000")
        print()
        print("This is the root cause of the ALB connectivity issue.")
    
    # Save results
    results = {
        'timestamp': datetime.now().isoformat(),
        'task_info': task_info,
        'port_test': {
            'open': port_open,
            'message': port_message
        },
        'http_tests': http_results
    }
    
    output_file = f"container-port-test-{int(time.time())}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print()
    print(f"Results saved to: {output_file}")

if __name__ == '__main__':
    main()
