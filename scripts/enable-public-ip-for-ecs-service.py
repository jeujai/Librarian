#!/usr/bin/env python3
"""
Enable public IP assignment for ECS service to fix internet connectivity.
"""

import boto3
import json
import time
from datetime import datetime

def main():
    ecs = boto3.client('ecs', region_name='us-east-1')
    
    print("=" * 80)
    print("ENABLE PUBLIC IP FOR ECS SERVICE")
    print("=" * 80)
    
    cluster = 'multimodal-lib-prod-cluster'
    service_name = 'multimodal-lib-prod-service-alb'
    
    # Get current service configuration
    print("\n1. Getting current service configuration...")
    service = ecs.describe_services(
        cluster=cluster,
        services=[service_name]
    )['services'][0]
    
    current_config = service['networkConfiguration']['awsvpcConfiguration']
    print(f"   Current assignPublicIp: {current_config.get('assignPublicIp', 'DISABLED')}")
    
    # Update service to enable public IP
    print("\n2. Updating service to enable public IP assignment...")
    
    response = ecs.update_service(
        cluster=cluster,
        service=service_name,
        networkConfiguration={
            'awsvpcConfiguration': {
                'subnets': current_config['subnets'],
                'securityGroups': current_config['securityGroups'],
                'assignPublicIp': 'ENABLED'
            }
        },
        forceNewDeployment=True  # Force new deployment to apply changes
    )
    
    print("   ✅ Service update initiated")
    print("   🔄 Forcing new deployment to apply changes...")
    
    # Wait for deployment to start
    print("\n3. Monitoring deployment...")
    for i in range(30):
        time.sleep(10)
        
        service = ecs.describe_services(
            cluster=cluster,
            services=[service_name]
        )['services'][0]
        
        deployments = service['deployments']
        print(f"\n   Deployment status (check {i+1}/30):")
        
        for deployment in deployments:
            status = deployment['status']
            desired = deployment['desiredCount']
            running = deployment['runningCount']
            pending = deployment['pendingCount']
            
            print(f"   - Status: {status}")
            print(f"     Desired: {desired}, Running: {running}, Pending: {pending}")
            
            if status == 'PRIMARY' and running == desired and pending == 0:
                print("\n   ✅ New deployment is running!")
                
                # Check if tasks have public IPs now
                print("\n4. Verifying tasks have public IPs...")
                tasks = ecs.list_tasks(
                    cluster=cluster,
                    serviceName=service_name
                )['taskArns']
                
                if tasks:
                    task_details = ecs.describe_tasks(
                        cluster=cluster,
                        tasks=tasks
                    )['tasks']
                    
                    ec2 = boto3.client('ec2', region_name='us-east-1')
                    
                    for task in task_details:
                        task_id = task['taskArn'].split('/')[-1]
                        
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
                                            print(f"   ✅ Task {task_id[:8]} has public IP: {public_ip}")
                                        else:
                                            print(f"   ⚠️  Task {task_id[:8]} has no public IP yet")
                
                results = {
                    'timestamp': datetime.now().isoformat(),
                    'cluster': cluster,
                    'service': service_name,
                    'update_status': 'success',
                    'public_ip_enabled': True
                }
                
                filename = f"ecs-public-ip-fix-{int(datetime.now().timestamp())}.json"
                with open(filename, 'w') as f:
                    json.dump(results, f, indent=2)
                
                print(f"\n📄 Results saved to: {filename}")
                print("\n" + "=" * 80)
                print("✅ PUBLIC IP ASSIGNMENT ENABLED")
                print("=" * 80)
                print("\nTasks should now be able to download ML models from the internet.")
                print("Monitor the application logs to verify model downloads succeed.")
                
                return results
    
    print("\n⚠️  Deployment is taking longer than expected.")
    print("   Check the ECS console for deployment status.")
    
    return {'status': 'timeout'}

if __name__ == '__main__':
    main()
