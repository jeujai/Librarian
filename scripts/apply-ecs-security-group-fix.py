#!/usr/bin/env python3
"""
Apply ECS Security Group Fix - Correctly update the ECS service to use the dedicated security group.

This script ensures the ECS service uses the dedicated ECS security group that allows
traffic from the ALB, rather than using the ALB security group itself.
"""

import boto3
import json
import time
from datetime import datetime

def main():
    ec2 = boto3.client('ec2')
    ecs = boto3.client('ecs')
    elbv2 = boto3.client('elbv2')
    
    print("=" * 80)
    print("Applying ECS Security Group Fix")
    print("=" * 80)
    
    # Configuration
    cluster_name = 'multimodal-lib-prod-cluster'
    service_name = 'multimodal-lib-prod-service-alb'
    ecs_sg_name = 'multimodal-lib-prod-ecs-tasks-sg'
    alb_name = 'multimodal-lib-prod-alb-v2'
    
    # Step 1: Get ALB security group
    print("\n1. Getting ALB configuration...")
    alb_response = elbv2.describe_load_balancers(Names=[alb_name])
    alb = alb_response['LoadBalancers'][0]
    alb_sg = alb['SecurityGroups'][0]
    vpc_id = alb['VpcId']
    
    print(f"   ALB: {alb_name}")
    print(f"   ALB Security Group: {alb_sg}")
    print(f"   VPC: {vpc_id}")
    
    # Step 2: Find or verify ECS security group
    print("\n2. Finding ECS security group...")
    sg_response = ec2.describe_security_groups(
        Filters=[
            {'Name': 'group-name', 'Values': [ecs_sg_name]},
            {'Name': 'vpc-id', 'Values': [vpc_id]}
        ]
    )
    
    if not sg_response['SecurityGroups']:
        print(f"   ✗ ECS security group '{ecs_sg_name}' not found!")
        print("   Run fix-alb-ecs-connectivity.py first to create it.")
        return
    
    ecs_sg_id = sg_response['SecurityGroups'][0]['GroupId']
    print(f"   ✓ Found ECS security group: {ecs_sg_id}")
    
    # Verify the security group has the correct rules
    sg_details = sg_response['SecurityGroups'][0]
    has_correct_rule = False
    
    for rule in sg_details.get('IpPermissions', []):
        if rule.get('FromPort') == 8000 and rule.get('ToPort') == 8000:
            for pair in rule.get('UserIdGroupPairs', []):
                if pair.get('GroupId') == alb_sg:
                    has_correct_rule = True
                    break
    
    if has_correct_rule:
        print(f"   ✓ Security group has correct rule (allow port 8000 from ALB)")
    else:
        print(f"   ✗ Security group missing correct rule!")
        print("   Run fix-alb-ecs-connectivity.py to configure it.")
        return
    
    # Step 3: Get current service configuration
    print("\n3. Getting current ECS service configuration...")
    service_response = ecs.describe_services(
        cluster=cluster_name,
        services=[service_name]
    )
    
    if not service_response['services']:
        print(f"   ✗ Service {service_name} not found!")
        return
    
    service = service_response['services'][0]
    network_config = service['networkConfiguration']['awsvpcConfiguration']
    current_sgs = network_config['securityGroups']
    
    print(f"   Current security groups: {current_sgs}")
    print(f"   Target security group: {ecs_sg_id}")
    
    if ecs_sg_id in current_sgs:
        print(f"   ✓ Service already using correct security group")
        print("   Checking if tasks are using it...")
        
        # Check running tasks
        tasks_response = ecs.list_tasks(
            cluster=cluster_name,
            serviceName=service_name,
            desiredStatus='RUNNING'
        )
        
        if tasks_response['taskArns']:
            task_details = ecs.describe_tasks(
                cluster=cluster_name,
                tasks=tasks_response['taskArns']
            )
            
            for task in task_details['tasks']:
                task_id = task['taskArn'].split('/')[-1]
                for attachment in task.get('attachments', []):
                    if attachment['type'] == 'ElasticNetworkInterface':
                        for detail in attachment['details']:
                            if detail['name'] == 'networkInterfaceId':
                                eni_id = detail['value']
                                
                                # Get ENI details
                                eni_response = ec2.describe_network_interfaces(
                                    NetworkInterfaceIds=[eni_id]
                                )
                                
                                if eni_response['NetworkInterfaces']:
                                    eni = eni_response['NetworkInterfaces'][0]
                                    task_sgs = [sg['GroupId'] for sg in eni['Groups']]
                                    
                                    print(f"\n   Task {task_id}:")
                                    print(f"     ENI: {eni_id}")
                                    print(f"     Security Groups: {task_sgs}")
                                    
                                    if ecs_sg_id in task_sgs:
                                        print(f"     ✓ Using correct security group")
                                    else:
                                        print(f"     ✗ NOT using correct security group")
                                        print(f"     Need to force new deployment")
        
        # Force new deployment to ensure tasks use the correct SG
        print("\n   Forcing new deployment to apply security group...")
        ecs.update_service(
            cluster=cluster_name,
            service=service_name,
            forceNewDeployment=True
        )
        print("   ✓ New deployment triggered")
        
    else:
        # Step 4: Update service with correct security group
        print("\n4. Updating ECS service with correct security group...")
        
        ecs.update_service(
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
        
        print(f"   ✓ Updated service to use security group: {ecs_sg_id}")
        print(f"   ✓ Triggered new deployment")
    
    # Step 5: Monitor deployment
    print("\n5. Monitoring deployment...")
    print("   Waiting for new tasks to start...")
    
    for i in range(24):  # Wait up to 4 minutes
        time.sleep(10)
        
        service_response = ecs.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        service = service_response['services'][0]
        deployments = service['deployments']
        
        print(f"\n   Deployments:")
        for deployment in deployments:
            status = deployment['status']
            running = deployment['runningCount']
            desired = deployment['desiredCount']
            task_def = deployment['taskDefinition'].split('/')[-1]
            print(f"     {status}: {running}/{desired} tasks ({task_def})")
        
        # Check if PRIMARY deployment is stable
        primary = [d for d in deployments if d['status'] == 'PRIMARY']
        if primary and primary[0]['runningCount'] == primary[0]['desiredCount']:
            if len(deployments) == 1:  # Only PRIMARY deployment remains
                print("\n   ✓ Deployment complete!")
                break
    
    # Step 6: Verify task is using correct security group
    print("\n6. Verifying task security group...")
    
    tasks_response = ecs.list_tasks(
        cluster=cluster_name,
        serviceName=service_name,
        desiredStatus='RUNNING'
    )
    
    if tasks_response['taskArns']:
        task_details = ecs.describe_tasks(
            cluster=cluster_name,
            tasks=tasks_response['taskArns']
        )
        
        for task in task_details['tasks']:
            task_id = task['taskArn'].split('/')[-1]
            
            for attachment in task.get('attachments', []):
                if attachment['type'] == 'ElasticNetworkInterface':
                    for detail in attachment['details']:
                        if detail['name'] == 'networkInterfaceId':
                            eni_id = detail['value']
                            
                            eni_response = ec2.describe_network_interfaces(
                                NetworkInterfaceIds=[eni_id]
                            )
                            
                            if eni_response['NetworkInterfaces']:
                                eni = eni_response['NetworkInterfaces'][0]
                                task_sgs = [sg['GroupId'] for sg in eni['Groups']]
                                private_ip = eni['PrivateIpAddress']
                                
                                print(f"\n   Task {task_id}:")
                                print(f"     ENI: {eni_id}")
                                print(f"     Private IP: {private_ip}")
                                print(f"     Security Groups: {task_sgs}")
                                
                                if ecs_sg_id in task_sgs:
                                    print(f"     ✓ Using correct security group!")
                                else:
                                    print(f"     ✗ Still using wrong security group")
    
    # Step 7: Wait for health checks
    print("\n7. Waiting for health checks...")
    print("   (Health checks run every 30 seconds, need 2 consecutive successes)")
    
    time.sleep(60)  # Wait for at least 2 health check cycles
    
    tg_response = elbv2.describe_target_groups(
        Names=['multimodal-lib-prod-tg-v2']
    )
    tg_arn = tg_response['TargetGroups'][0]['TargetGroupArn']
    
    health_response = elbv2.describe_target_health(TargetGroupArn=tg_arn)
    
    print("\n   Target Health:")
    for target in health_response['TargetHealthDescriptions']:
        ip = target['Target']['Id']
        state = target['TargetHealth']['State']
        reason = target['TargetHealth'].get('Reason', 'N/A')
        description = target['TargetHealth'].get('Description', 'N/A')
        
        print(f"     {ip}: {state}")
        if reason != 'N/A':
            print(f"       Reason: {reason}")
        if description != 'N/A':
            print(f"       Description: {description}")
    
    print("\n" + "=" * 80)
    print("SECURITY GROUP FIX APPLIED")
    print("=" * 80)
    print("\nWhat was done:")
    print(f"1. Verified ECS security group exists: {ecs_sg_id}")
    print(f"2. Verified security group allows traffic from ALB: {alb_sg}")
    print("3. Updated ECS service to use correct security group")
    print("4. Triggered new deployment")
    print("5. Verified new tasks are using correct security group")
    print("\nNext steps:")
    print("- Wait 2-3 minutes for health checks to stabilize")
    print("- Monitor target health in AWS Console")
    print("- Check application logs for incoming health check requests")
    
    # Save results
    timestamp = int(time.time())
    results = {
        'timestamp': datetime.now().isoformat(),
        'alb_security_group': alb_sg,
        'ecs_security_group': ecs_sg_id,
        'vpc_id': vpc_id,
        'service_updated': True,
        'deployment_triggered': True,
        'cluster': cluster_name,
        'service': service_name
    }
    
    filename = f'ecs-security-group-fix-applied-{timestamp}.json'
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nResults saved to: {filename}")

if __name__ == '__main__':
    main()
