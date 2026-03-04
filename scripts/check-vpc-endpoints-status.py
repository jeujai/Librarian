#!/usr/bin/env python3
"""
Check VPC endpoints status and connectivity.
"""

import boto3
import json
import sys
from datetime import datetime

def check_vpc_endpoints_status():
    """Check VPC endpoints status."""
    
    try:
        # Initialize clients
        ec2_client = boto3.client('ec2', region_name='us-east-1')
        ecs_client = boto3.client('ecs', region_name='us-east-1')
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'endpoints_status': {},
            'recommendations': []
        }
        
        print("🔍 Checking VPC Endpoints Status")
        print("=" * 35)
        
        # Get target VPC ID
        elb_client = boto3.client('elbv2', region_name='us-east-1')
        lb_response = elb_client.describe_load_balancers()
        
        target_vpc_id = None
        for lb in lb_response['LoadBalancers']:
            if 'multimodal' in lb['LoadBalancerName'].lower():
                target_vpc_id = lb['VpcId']
                break
        
        if not target_vpc_id:
            print("❌ Could not find target VPC")
            return result
        
        print(f"🌐 Target VPC: {target_vpc_id}")
        
        # 1. Check VPC endpoints
        print("\n1. VPC Endpoints Status:")
        print("-" * 25)
        
        endpoints_response = ec2_client.describe_vpc_endpoints(
            Filters=[
                {'Name': 'vpc-id', 'Values': [target_vpc_id]}
            ]
        )
        
        required_services = [
            'com.amazonaws.us-east-1.secretsmanager',
            'com.amazonaws.us-east-1.ecr.dkr',
            'com.amazonaws.us-east-1.ecr.api',
            'com.amazonaws.us-east-1.logs'
        ]
        
        found_services = set()
        
        for endpoint in endpoints_response['VpcEndpoints']:
            service_name = endpoint['ServiceName']
            endpoint_id = endpoint['VpcEndpointId']
            state = endpoint['State']
            creation_timestamp = endpoint['CreationTimestamp']
            
            print(f"📍 {service_name}")
            print(f"   - ID: {endpoint_id}")
            print(f"   - State: {state}")
            print(f"   - Created: {creation_timestamp}")
            
            if state == 'available':
                print(f"   ✅ Available")
                found_services.add(service_name)
            else:
                print(f"   ⚠️  Not available: {state}")
                result['recommendations'].append(f"Endpoint {endpoint_id} is {state}")
            
            # Check DNS names
            dns_entries = endpoint.get('DnsEntries', [])
            if dns_entries:
                print(f"   - DNS Entries: {len(dns_entries)}")
                for dns_entry in dns_entries[:2]:  # Show first 2
                    dns_name = dns_entry.get('DnsName')
                    print(f"     - {dns_name}")
            
            result['endpoints_status'][service_name] = {
                'id': endpoint_id,
                'state': state,
                'dns_entries': len(dns_entries)
            }
        
        # Check for missing services
        missing_services = set(required_services) - found_services
        if missing_services:
            print(f"\n❌ Missing VPC Endpoints:")
            for service in missing_services:
                print(f"   - {service}")
                result['recommendations'].append(f"Missing VPC endpoint for {service}")
        else:
            print(f"\n✅ All required VPC endpoints found")
        
        # 2. Check current task status
        print("\n2. Current Task Status:")
        print("-" * 22)
        
        cluster_name = 'multimodal-lib-prod-cluster'
        service_name = 'multimodal-lib-prod-service'
        
        tasks_response = ecs_client.list_tasks(
            cluster=cluster_name,
            serviceName=service_name
        )
        
        if tasks_response['taskArns']:
            task_details = ecs_client.describe_tasks(
                cluster=cluster_name,
                tasks=tasks_response['taskArns']
            )
            
            for task in task_details['tasks']:
                task_id = task['taskArn'].split('/')[-1]
                status = task['lastStatus']
                created_at = task['createdAt']
                
                print(f"📋 Task: {task_id}")
                print(f"   - Status: {status}")
                print(f"   - Created: {created_at}")
                
                # Check containers
                containers = task.get('containers', [])
                for container in containers:
                    container_name = container['name']
                    container_status = container['lastStatus']
                    
                    print(f"   - Container {container_name}: {container_status}")
                    
                    if container_status == 'RUNNING':
                        print(f"     ✅ Container is running")
                    elif container_status in ['PENDING', 'PROVISIONING']:
                        print(f"     ⏳ Container is starting")
                    else:
                        reason = container.get('reason', 'Unknown')
                        print(f"     ❌ Container issue: {reason}")
        else:
            print("📋 No current tasks found")
        
        # 3. Test connectivity (if we can)
        print("\n3. Connectivity Test:")
        print("-" * 20)
        
        # Check if we can resolve ECR DNS names
        import socket
        
        ecr_endpoints = [
            '591222106065.dkr.ecr.us-east-1.amazonaws.com',
            'api.ecr.us-east-1.amazonaws.com'
        ]
        
        for endpoint in ecr_endpoints:
            try:
                ip = socket.gethostbyname(endpoint)
                print(f"✅ {endpoint} resolves to {ip}")
            except Exception as e:
                print(f"❌ {endpoint} resolution failed: {e}")
                result['recommendations'].append(f"DNS resolution failed for {endpoint}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error during check: {e}")
        return {'error': str(e)}

if __name__ == "__main__":
    result = check_vpc_endpoints_status()
    
    # Save result to file
    result_file = f"vpc-endpoints-status-{int(datetime.now().timestamp())}.json"
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 Status check saved to: {result_file}")
    
    if result.get('recommendations'):
        sys.exit(1)
    else:
        sys.exit(0)