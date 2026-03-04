#!/usr/bin/env python3
"""
Check if ECS service is configured to assign public IPs to tasks.
"""

import boto3
import json
from datetime import datetime

def main():
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("=" * 80)
    print("ECS PUBLIC IP ASSIGNMENT CHECK")
    print("=" * 80)
    
    # Get service details
    print("\nChecking service configuration...")
    service = ecs.describe_services(
        cluster='multimodal-lib-prod-cluster',
        services=['multimodal-lib-prod-service-alb']
    )['services'][0]
    
    network_config = service['networkConfiguration']['awsvpcConfiguration']
    assign_public_ip = network_config.get('assignPublicIp', 'DISABLED')
    
    print(f"\nService: multimodal-lib-prod-service-alb")
    print(f"Assign Public IP: {assign_public_ip}")
    print(f"Subnets: {network_config['subnets']}")
    
    if assign_public_ip == 'DISABLED':
        print("\n❌ PROBLEM FOUND!")
        print("   Tasks are in PUBLIC subnets but assignPublicIp is DISABLED")
        print("   Tasks cannot reach the internet without public IPs")
        print("\n🔧 SOLUTION:")
        print("   Option 1: Enable assignPublicIp=ENABLED for the service")
        print("   Option 2: Move tasks to private subnets with NAT Gateway")
    else:
        print("\n✅ Public IP assignment is enabled")
    
    # Check running tasks
    print("\n" + "=" * 80)
    print("CHECKING RUNNING TASKS")
    print("=" * 80)
    
    tasks = ecs.list_tasks(
        cluster='multimodal-lib-prod-cluster',
        serviceName='multimodal-lib-prod-service-alb'
    )['taskArns']
    
    if tasks:
        task_details = ecs.describe_tasks(
            cluster='multimodal-lib-prod-cluster',
            tasks=tasks
        )['tasks']
        
        for task in task_details:
            task_id = task['taskArn'].split('/')[-1]
            print(f"\nTask: {task_id}")
            
            # Check network interfaces
            for attachment in task.get('attachments', []):
                if attachment['type'] == 'ElasticNetworkInterface':
                    for detail in attachment['details']:
                        if detail['name'] == 'networkInterfaceId':
                            eni_id = detail['value']
                            print(f"  ENI: {eni_id}")
                        elif detail['name'] == 'privateIPv4Address':
                            private_ip = detail['value']
                            print(f"  Private IP: {private_ip}")
                        elif detail['name'] == 'subnetId':
                            subnet_id = detail['value']
                            print(f"  Subnet: {subnet_id}")
            
            # Check if task has public IP
            ec2 = boto3.client('ec2', region_name='us-east-1')
            for attachment in task.get('attachments', []):
                if attachment['type'] == 'ElasticNetworkInterface':
                    for detail in attachment['details']:
                        if detail['name'] == 'networkInterfaceId':
                            eni_id = detail['value']
                            eni = ec2.describe_network_interfaces(
                                NetworkInterfaceIds=[eni_id]
                            )['NetworkInterfaces'][0]
                            
                            public_ip = eni.get('Association', {}).get('PublicIp')
                            if public_ip:
                                print(f"  Public IP: {public_ip} ✅")
                            else:
                                print(f"  Public IP: None ❌")
    
    results = {
        'timestamp': datetime.now().isoformat(),
        'service': 'multimodal-lib-prod-service-alb',
        'assign_public_ip': assign_public_ip,
        'needs_fix': assign_public_ip == 'DISABLED'
    }
    
    filename = f"ecs-public-ip-check-{int(datetime.now().timestamp())}.json"
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\n📄 Results saved to: {filename}")

if __name__ == '__main__':
    main()
