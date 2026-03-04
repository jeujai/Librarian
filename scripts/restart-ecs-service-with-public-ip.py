#!/usr/bin/env python3
"""
Restart ECS service to get fresh tasks with public IPs.
"""

import boto3
import time
from datetime import datetime

def main():
    ecs = boto3.client('ecs', region_name='us-east-1')
    ec2 = boto3.client('ec2', region_name='us-east-1')
    
    cluster = 'multimodal-lib-prod-cluster'
    service_name = 'multimodal-lib-prod-service-alb'
    
    print("=" * 80)
    print("RESTART ECS SERVICE WITH PUBLIC IP")
    print("=" * 80)
    
    # Scale to 0
    print("\n1. Scaling service to 0...")
    ecs.update_service(
        cluster=cluster,
        service=service_name,
        desiredCount=0
    )
    
    print("   Waiting for tasks to stop...")
    time.sleep(30)
    
    # Scale back to 1
    print("\n2. Scaling service back to 1...")
    ecs.update_service(
        cluster=cluster,
        service=service_name,
        desiredCount=1
    )
    
    print("   Waiting for new task to start...")
    
    # Monitor for new tasks
    for i in range(20):
        time.sleep(15)
        
        tasks = ecs.list_tasks(
            cluster=cluster,
            serviceName=service_name
        )['taskArns']
        
        if tasks:
            print(f"\n   Check {i+1}/20: Found {len(tasks)} task(s)")
            
            task_details = ecs.describe_tasks(
                cluster=cluster,
                tasks=tasks
            )['tasks']
            
            for task in task_details:
                task_id = task['taskArn'].split('/')[-1]
                last_status = task['lastStatus']
                
                print(f"   Task {task_id[:8]}: {last_status}")
                
                if last_status == 'RUNNING':
                    # Check for public IP
                    for attachment in task.get('attachments', []):
                        if attachment['type'] == 'ElasticNetworkInterface':
                            for detail in attachment['details']:
                                if detail['name'] == 'networkInterfaceId':
                                    eni_id = detail['value']
                                    eni = ec2.describe_network_interfaces(
                                        NetworkInterfaceIds=[eni_id]
                                    )['NetworkInterfaces'][0]
                                    
                                    public_ip = eni.get('Association', {}).get('PublicIp')
                                    private_ip = eni.get('PrivateIpAddress')
                                    
                                    print(f"   - Private IP: {private_ip}")
                                    if public_ip:
                                        print(f"   - Public IP: {public_ip} ✅")
                                        print("\n✅ Task has public IP! Internet connectivity should work now.")
                                        print("\n📋 Next steps:")
                                        print("   1. Check application logs for model download progress")
                                        print("   2. Wait for health checks to pass")
                                        print("   3. Verify ALB target health")
                                        return
                                    else:
                                        print(f"   - Public IP: None ❌")
        else:
            print(f"\n   Check {i+1}/20: No tasks yet...")
    
    print("\n⚠️  Timeout waiting for task with public IP")

if __name__ == '__main__':
    main()
