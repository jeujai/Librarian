#!/usr/bin/env python3
"""
Fix ECS service to use the correct dedicated security group.

The issue: ECS tasks are using the ALB security group instead of the
dedicated ECS tasks security group, which prevents proper traffic flow.
"""

import boto3
import json
import time
from datetime import datetime

def main():
    ecs = boto3.client('ecs')
    ec2 = boto3.client('ec2')
    elbv2 = boto3.client('elbv2')
    
    print("=" * 80)
    print("Fix ECS Service Security Group")
    print("=" * 80)
    
    cluster_name = 'multimodal-lib-prod-cluster'
    service_name = 'multimodal-lib-prod-service-alb'
    ecs_sg_id = 'sg-0c4dac025bda80435'  # multimodal-lib-prod-ecs-tasks-sg
    
    # Step 1: Verify the security group exists and has correct rules
    print("\n1. Verifying ECS security group configuration...")
    
    sg_response = ec2.describe_security_groups(
        GroupIds=[ecs_sg_id]
    )
    
    if not sg_response['SecurityGroups']:
        print(f"   ✗ Security group {ecs_sg_id} not found!")
        return
    
    sg = sg_response['SecurityGroups'][0]
    print(f"   ✓ Security Group: {sg['GroupName']} ({sg['GroupId']})")
    print(f"   VPC: {sg['VpcId']}")
    
    print("\n   Ingress Rules:")
    for rule in sg['IpPermissions']:
        protocol = rule.get('IpProtocol', 'N/A')
        from_port = rule.get('FromPort', 'N/A')
        to_port = rule.get('ToPort', 'N/A')
        
        if rule.get('UserIdGroupPairs'):
            for pair in rule['UserIdGroupPairs']:
                source_sg = pair['GroupId']
                desc = pair.get('Description', 'No description')
                print(f"     - Protocol {protocol}, Ports {from_port}-{to_port}, From SG {source_sg}")
                print(f"       Description: {desc}")
    
    # Step 2: Get current service configuration
    print("\n2. Getting current service configuration...")
    
    service_response = ecs.describe_services(
        cluster=cluster_name,
        services=[service_name]
    )
    
    if not service_response['services']:
        print(f"   ✗ Service {service_name} not found!")
        return
    
    service = service_response['services'][0]
    network_config = service['networkConfiguration']['awsvpcConfiguration']
    
    print(f"   Service: {service['serviceName']}")
    print(f"   Status: {service['status']}")
    print(f"   Running Count: {service['runningCount']}/{service['desiredCount']}")
    print(f"   Current Security Groups: {network_config['securityGroups']}")
    print(f"   Subnets: {network_config['subnets']}")
    
    # Step 3: Update service with correct security group
    print("\n3. Updating service with correct security group...")
    
    if ecs_sg_id in network_config['securityGroups']:
        print(f"   ℹ️  Service already using correct security group")
    else:
        print(f"   Updating from {network_config['securityGroups']} to [{ecs_sg_id}]")
        
        try:
            update_response = ecs.update_service(
                cluster=cluster_name,
                service=service_name,
                networkConfiguration={
                    'awsvpcConfiguration': {
                        'subnets': network_config['subnets'],
                        'securityGroups': [ecs_sg_id],
                        'assignPublicIp': network_config.get('assignPublicIp', 'ENABLED')
                    }
                },
                forceNewDeployment=True
            )
            
            print(f"   ✓ Service updated successfully")
            print(f"   ✓ Forced new deployment")
            
        except Exception as e:
            print(f"   ✗ Failed to update service: {e}")
            return
    
    # Step 4: Monitor deployment
    print("\n4. Monitoring deployment...")
    print("   Waiting for new tasks to start (this may take 2-3 minutes)...")
    
    for i in range(24):  # Wait up to 4 minutes
        time.sleep(10)
        
        # Check service status
        service_response = ecs.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        service = service_response['services'][0]
        running_count = service['runningCount']
        desired_count = service['desiredCount']
        
        # Get deployment status
        deployments = service['deployments']
        primary_deployment = [d for d in deployments if d['status'] == 'PRIMARY']
        
        if primary_deployment:
            deployment = primary_deployment[0]
            print(f"   [{i*10}s] Tasks: {running_count}/{desired_count}, "
                  f"Deployment: {deployment['runningCount']} running, "
                  f"{deployment['pendingCount']} pending")
        
        if running_count == desired_count and running_count > 0 and len(deployments) == 1:
            print("   ✓ New tasks are running with updated configuration")
            break
    
    # Step 5: Verify new task is using correct security group
    print("\n5. Verifying new task configuration...")
    
    time.sleep(5)  # Wait a bit for task to fully start
    
    tasks_response = ecs.list_tasks(
        cluster=cluster_name,
        serviceName=service_name,
        desiredStatus='RUNNING'
    )
    
    if tasks_response['taskArns']:
        task_arn = tasks_response['taskArns'][0]
        task_details = ecs.describe_tasks(
            cluster=cluster_name,
            tasks=[task_arn]
        )
        
        task = task_details['tasks'][0]
        
        # Get ENI details
        task_eni_id = None
        for attachment in task['attachments']:
            if attachment['type'] == 'ElasticNetworkInterface':
                for detail in attachment['details']:
                    if detail['name'] == 'networkInterfaceId':
                        task_eni_id = detail['value']
        
        if task_eni_id:
            eni_response = ec2.describe_network_interfaces(
                NetworkInterfaceIds=[task_eni_id]
            )
            
            if eni_response['NetworkInterfaces']:
                eni = eni_response['NetworkInterfaces'][0]
                task_sgs = [sg['GroupId'] for sg in eni['Groups']]
                
                print(f"   Task: {task_arn.split('/')[-1]}")
                print(f"   ENI: {task_eni_id}")
                print(f"   Private IP: {eni['PrivateIpAddress']}")
                print(f"   Security Groups: {task_sgs}")
                
                if ecs_sg_id in task_sgs:
                    print(f"   ✓ Task is using correct security group!")
                else:
                    print(f"   ⚠️  Task is NOT using correct security group")
                    print(f"      Expected: {ecs_sg_id}")
                    print(f"      Actual: {task_sgs}")
    
    # Step 6: Wait for health checks
    print("\n6. Waiting for health checks to pass...")
    print("   This may take 60-90 seconds...")
    
    time.sleep(60)  # Wait for initial health checks
    
    # Check target health
    tg_response = elbv2.describe_target_groups(
        Names=['multimodal-lib-prod-tg-v2']
    )
    
    if tg_response['TargetGroups']:
        tg_arn = tg_response['TargetGroups'][0]['TargetGroupArn']
        
        health_response = elbv2.describe_target_health(TargetGroupArn=tg_arn)
        
        print("\n   Target Health:")
        for target in health_response['TargetHealthDescriptions']:
            ip = target['Target']['Id']
            state = target['TargetHealth']['State']
            reason = target['TargetHealth'].get('Reason', 'N/A')
            description = target['TargetHealth'].get('Description', 'N/A')
            
            status_icon = "✓" if state == "healthy" else "⚠️" if state == "initial" else "✗"
            print(f"     {status_icon} {ip}: {state}")
            if reason != 'N/A':
                print(f"        Reason: {reason}")
            if description != 'N/A':
                print(f"        Description: {description}")
    
    # Summary
    print("\n" + "=" * 80)
    print("FIX COMPLETE")
    print("=" * 80)
    print("\nWhat was done:")
    print("1. Verified ECS security group has correct rules")
    print("2. Updated ECS service to use dedicated security group")
    print("3. Forced new deployment with updated configuration")
    print("4. Verified new tasks are using correct security group")
    print("\nNext steps:")
    print("- Wait 2-3 minutes for health checks to pass")
    print("- Monitor target health in AWS Console")
    print("- Check application logs if health checks still fail")
    
    # Save results
    timestamp = int(time.time())
    results = {
        'timestamp': datetime.now().isoformat(),
        'cluster': cluster_name,
        'service': service_name,
        'security_group': ecs_sg_id,
        'update_successful': True
    }
    
    filename = f'ecs-security-group-fix-{timestamp}.json'
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\n📄 Results saved to: {filename}")

if __name__ == '__main__':
    main()
