#!/usr/bin/env python3
"""
Fix ALB to ECS connectivity issue.

The problem: ALB can't reach ECS tasks on port 8000, even though:
- Application is listening on 0.0.0.0:8000
- Security groups allow traffic
- They're in the same VPC

Root cause: The ECS task and ALB are using the SAME security group, but the
security group rule allows traffic from itself. However, for this to work,
the SOURCE of the traffic must be identified as coming from that security group.

Solution: Create a separate security group for ECS tasks that explicitly allows
traffic from the ALB security group.
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
    print("ALB to ECS Connectivity Fix")
    print("=" * 80)
    
    # Step 1: Get current configuration
    print("\n1. Analyzing current configuration...")
    
    # Get ALB info
    alb_response = elbv2.describe_load_balancers(
        Names=['multimodal-lib-prod-alb-v2']
    )
    alb = alb_response['LoadBalancers'][0]
    alb_sg = alb['SecurityGroups'][0]
    vpc_id = alb['VpcId']
    
    print(f"   ALB: {alb['LoadBalancerName']}")
    print(f"   ALB Security Group: {alb_sg}")
    print(f"   VPC: {vpc_id}")
    
    # Step 2: Create new security group for ECS tasks
    print("\n2. Creating dedicated security group for ECS tasks...")
    
    try:
        ecs_sg_response = ec2.create_security_group(
            GroupName='multimodal-lib-prod-ecs-tasks-sg',
            Description='Security group for ECS tasks - allows traffic from ALB',
            VpcId=vpc_id
        )
        ecs_sg_id = ecs_sg_response['GroupId']
        print(f"   ✓ Created ECS security group: {ecs_sg_id}")
    except ec2.exceptions.ClientError as e:
        if 'already exists' in str(e):
            print("   Security group already exists, finding it...")
            sg_response = ec2.describe_security_groups(
                Filters=[
                    {'Name': 'group-name', 'Values': ['multimodal-lib-prod-ecs-tasks-sg']},
                    {'Name': 'vpc-id', 'Values': [vpc_id]}
                ]
            )
            ecs_sg_id = sg_response['SecurityGroups'][0]['GroupId']
            print(f"   ✓ Found existing ECS security group: {ecs_sg_id}")
        else:
            raise
    
    # Step 3: Add ingress rule to ECS security group (allow from ALB)
    print("\n3. Configuring ECS security group rules...")
    
    try:
        ec2.authorize_security_group_ingress(
            GroupId=ecs_sg_id,
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 8000,
                    'ToPort': 8000,
                    'UserIdGroupPairs': [
                        {
                            'GroupId': alb_sg,
                            'Description': 'Allow traffic from ALB on port 8000'
                        }
                    ]
                }
            ]
        )
        print(f"   ✓ Added ingress rule: Allow port 8000 from ALB SG ({alb_sg})")
    except ec2.exceptions.ClientError as e:
        if 'already exists' in str(e):
            print(f"   Rule already exists")
        else:
            raise
    
    # Add egress rule (allow all outbound)
    try:
        ec2.authorize_security_group_egress(
            GroupId=ecs_sg_id,
            IpPermissions=[
                {
                    'IpProtocol': '-1',
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                }
            ]
        )
        print(f"   ✓ Added egress rule: Allow all outbound traffic")
    except ec2.exceptions.ClientError as e:
        if 'already exists' in str(e):
            print(f"   Egress rule already exists")
        else:
            # Egress rules might already exist by default
            pass
    
    # Step 4: Update ECS service to use new security group
    print("\n4. Updating ECS service with new security group...")
    
    cluster_name = 'multimodal-lib-prod-cluster'
    service_name = 'multimodal-lib-prod-service-alb'
    
    # Get current service configuration
    service_response = ecs.describe_services(
        cluster=cluster_name,
        services=[service_name]
    )
    
    if not service_response['services']:
        print(f"   ✗ Service {service_name} not found!")
        return
    
    service = service_response['services'][0]
    network_config = service['networkConfiguration']['awsvpcConfiguration']
    
    # Update service with new security group
    print(f"   Current security groups: {network_config['securityGroups']}")
    print(f"   New security group: {ecs_sg_id}")
    
    ecs.update_service(
        cluster=cluster_name,
        service=service_name,
        networkConfiguration={
            'awsvpcConfiguration': {
                'subnets': network_config['subnets'],
                'securityGroups': [ecs_sg_id],  # Replace with new SG
                'assignPublicIp': network_config.get('assignPublicIp', 'ENABLED')
            }
        },
        forceNewDeployment=True
    )
    
    print(f"   ✓ Updated service to use new security group")
    print(f"   ✓ Triggered new deployment")
    
    # Step 5: Monitor deployment
    print("\n5. Monitoring deployment...")
    print("   Waiting for new tasks to start (this may take 2-3 minutes)...")
    
    for i in range(12):  # Wait up to 2 minutes
        time.sleep(10)
        
        # Check service status
        service_response = ecs.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        service = service_response['services'][0]
        running_count = service['runningCount']
        desired_count = service['desiredCount']
        
        print(f"   Tasks: {running_count}/{desired_count} running")
        
        if running_count == desired_count and running_count > 0:
            print("   ✓ New tasks are running")
            break
    
    # Step 6: Check target health
    print("\n6. Checking target health...")
    time.sleep(30)  # Wait for health checks
    
    tg_response = elbv2.describe_target_groups(
        Names=['multimodal-lib-prod-tg-v2']
    )
    tg_arn = tg_response['TargetGroups'][0]['TargetGroupArn']
    
    health_response = elbv2.describe_target_health(TargetGroupArn=tg_arn)
    
    for target in health_response['TargetHealthDescriptions']:
        ip = target['Target']['Id']
        state = target['TargetHealth']['State']
        reason = target['TargetHealth'].get('Reason', 'N/A')
        print(f"   Target {ip}: {state} ({reason})")
    
    print("\n" + "=" * 80)
    print("FIX APPLIED")
    print("=" * 80)
    print("\nWhat was fixed:")
    print("1. Created dedicated security group for ECS tasks")
    print("2. Configured security group to allow traffic from ALB")
    print("3. Updated ECS service to use new security group")
    print("4. Triggered new deployment with correct network configuration")
    print("\nNext steps:")
    print("- Wait 2-3 minutes for health checks to pass")
    print("- Monitor target health in AWS Console")
    print("- Test ALB endpoint once targets are healthy")
    
    # Save results
    timestamp = int(time.time())
    results = {
        'timestamp': datetime.now().isoformat(),
        'alb_security_group': alb_sg,
        'ecs_security_group': ecs_sg_id,
        'vpc_id': vpc_id,
        'service_updated': True,
        'deployment_triggered': True
    }
    
    filename = f'alb-ecs-connectivity-fix-{timestamp}.json'
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"\nResults saved to: {filename}")

if __name__ == '__main__':
    main()
