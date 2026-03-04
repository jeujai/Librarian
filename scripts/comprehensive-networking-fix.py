#!/usr/bin/env python3
"""
Comprehensive networking fix for ECS service and load balancer connectivity.
"""

import boto3
import json
import sys
import time
from datetime import datetime

def comprehensive_networking_fix():
    """Comprehensive fix for networking issues."""
    
    try:
        # Initialize clients
        ecs_client = boto3.client('ecs', region_name='us-east-1')
        elb_client = boto3.client('elbv2', region_name='us-east-1')
        ec2_client = boto3.client('ec2', region_name='us-east-1')
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'analysis': {},
            'fix_actions': [],
            'success': False
        }
        
        print("🔧 Comprehensive Networking Fix")
        print("=" * 35)
        
        cluster_name = 'multimodal-lib-prod-cluster'
        service_name = 'multimodal-lib-prod-service'
        
        # 1. Stop all old tasks to force fresh deployment
        print("\n1. Stopping Old Tasks:")
        print("-" * 22)
        
        tasks_response = ecs_client.list_tasks(
            cluster=cluster_name,
            serviceName=service_name
        )
        
        if tasks_response['taskArns']:
            print(f"🛑 Stopping {len(tasks_response['taskArns'])} old tasks")
            
            for task_arn in tasks_response['taskArns']:
                task_id = task_arn.split('/')[-1]
                print(f"   - Stopping task: {task_id}")
                
                ecs_client.stop_task(
                    cluster=cluster_name,
                    task=task_arn,
                    reason='Networking configuration update'
                )
            
            result['fix_actions'].append(f"Stopped {len(tasks_response['taskArns'])} old tasks")
            
            # Wait for tasks to stop
            print("⏳ Waiting for tasks to stop...")
            time.sleep(30)
        
        # 2. Get load balancer configuration
        print("\n2. Analyzing Load Balancer Configuration:")
        print("-" * 42)
        
        lb_response = elb_client.describe_load_balancers()
        multimodal_lb = None
        
        for lb in lb_response['LoadBalancers']:
            if 'multimodal' in lb['LoadBalancerName'].lower():
                multimodal_lb = lb
                break
        
        if not multimodal_lb:
            print("❌ Load balancer not found")
            return result
        
        lb_vpc_id = multimodal_lb['VpcId']
        lb_subnets = multimodal_lb.get('AvailabilityZones', [])
        lb_subnet_ids = [az['SubnetId'] for az in lb_subnets]
        lb_azs = [az['ZoneName'] for az in lb_subnets]
        
        print(f"🔗 Load Balancer VPC: {lb_vpc_id}")
        print(f"🔗 Load Balancer AZs: {lb_azs}")
        print(f"🔗 Load Balancer Subnets: {lb_subnet_ids}")
        
        # Check if load balancer subnets are public or private
        lb_subnet_details = ec2_client.describe_subnets(SubnetIds=lb_subnet_ids)
        
        print("🔍 Load Balancer Subnet Analysis:")
        for subnet in lb_subnet_details['Subnets']:
            subnet_id = subnet['SubnetId']
            subnet_az = subnet['AvailabilityZone']
            
            # Check if subnet has internet gateway route
            route_tables = ec2_client.describe_route_tables(
                Filters=[
                    {'Name': 'association.subnet-id', 'Values': [subnet_id]}
                ]
            )
            
            has_igw = False
            for rt in route_tables['RouteTables']:
                for route in rt['Routes']:
                    if route.get('GatewayId', '').startswith('igw-'):
                        has_igw = True
                        break
            
            subnet_type = "Public" if has_igw else "Private"
            print(f"   - {subnet_id} ({subnet_az}): {subnet_type}")
        
        # 3. Find appropriate private subnets for ECS service
        print("\n3. Finding Private Subnets for ECS Service:")
        print("-" * 43)
        
        # Get all subnets in the load balancer VPC
        all_subnets = ec2_client.describe_subnets(
            Filters=[
                {'Name': 'vpc-id', 'Values': [lb_vpc_id]},
                {'Name': 'state', 'Values': ['available']}
            ]
        )
        
        # Find private subnets in same AZs as load balancer
        private_subnets = []
        
        for subnet in all_subnets['Subnets']:
            subnet_id = subnet['SubnetId']
            subnet_az = subnet['AvailabilityZone']
            
            # Skip if not in same AZ as load balancer
            if subnet_az not in lb_azs:
                continue
            
            # Check if it's a private subnet
            route_tables = ec2_client.describe_route_tables(
                Filters=[
                    {'Name': 'association.subnet-id', 'Values': [subnet_id]}
                ]
            )
            
            has_igw = False
            has_nat = False
            
            for rt in route_tables['RouteTables']:
                for route in rt['Routes']:
                    if route.get('GatewayId', '').startswith('igw-'):
                        has_igw = True
                    elif route.get('NatGatewayId'):
                        has_nat = True
            
            # We want private subnets with NAT gateway for outbound connectivity
            if not has_igw and has_nat:
                private_subnets.append(subnet_id)
                print(f"✅ Private subnet with NAT: {subnet_id} (AZ: {subnet_az})")
            elif not has_igw:
                private_subnets.append(subnet_id)
                print(f"⚠️  Private subnet without NAT: {subnet_id} (AZ: {subnet_az})")
        
        if not private_subnets:
            print("❌ No suitable private subnets found")
            result['fix_actions'].append("No suitable private subnets found")
            return result
        
        # Use first 2 private subnets
        ecs_subnets = private_subnets[:2]
        
        # 4. Find or verify security group
        print("\n4. Security Group Configuration:")
        print("-" * 33)
        
        # Look for existing security group that allows port 8000
        sg_response = ec2_client.describe_security_groups(
            Filters=[
                {'Name': 'vpc-id', 'Values': [lb_vpc_id]}
            ]
        )
        
        suitable_sg = None
        
        for sg in sg_response['SecurityGroups']:
            sg_id = sg['GroupId']
            sg_name = sg['GroupName']
            
            # Check if this security group allows port 8000
            for rule in sg['IpPermissions']:
                from_port = rule.get('FromPort', 0)
                to_port = rule.get('ToPort', 65535)
                
                if from_port <= 8000 <= to_port:
                    suitable_sg = sg_id
                    print(f"✅ Using security group: {sg_name} ({sg_id})")
                    break
            
            if suitable_sg:
                break
        
        if not suitable_sg:
            print("❌ No suitable security group found")
            result['fix_actions'].append("No suitable security group found")
            return result
        
        # 5. Update service configuration with correct networking
        print("\n5. Updating Service Network Configuration:")
        print("-" * 42)
        
        print(f"🔄 Configuring service with:")
        print(f"   - VPC: {lb_vpc_id}")
        print(f"   - Subnets: {ecs_subnets}")
        print(f"   - Security Group: {suitable_sg}")
        
        try:
            # Update service network configuration
            update_response = ecs_client.update_service(
                cluster=cluster_name,
                service=service_name,
                networkConfiguration={
                    'awsvpcConfiguration': {
                        'subnets': ecs_subnets,
                        'securityGroups': [suitable_sg],
                        'assignPublicIp': 'DISABLED'
                    }
                },
                forceNewDeployment=True
            )
            
            print("✅ Service network configuration updated")
            result['fix_actions'].append(f"Updated service to use subnets: {ecs_subnets}")
            result['fix_actions'].append(f"Updated security group to: {suitable_sg}")
            
            # 6. Wait for new deployment
            print("\n6. Waiting for New Deployment:")
            print("-" * 31)
            
            print("⏳ Waiting for service to deploy new tasks...")
            
            # Wait for deployment to start
            time.sleep(45)
            
            # Monitor deployment progress
            max_attempts = 15  # 7.5 minutes max
            attempt = 0
            
            while attempt < max_attempts:
                attempt += 1
                
                service_details = ecs_client.describe_services(
                    cluster=cluster_name,
                    services=[service_name]
                )
                
                service = service_details['services'][0]
                running_count = service['runningCount']
                desired_count = service['desiredCount']
                
                print(f"   Attempt {attempt}: Running {running_count}/{desired_count} tasks")
                
                if running_count == desired_count and running_count > 0:
                    print("✅ Service deployment completed")
                    break
                
                time.sleep(30)
            
            # 7. Verify task networking
            print("\n7. Verifying Task Networking:")
            print("-" * 30)
            
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
                    
                    print(f"📋 Task: {task_id}")
                    print(f"   - Status: {task['lastStatus']}")
                    
                    # Get network interface details
                    attachments = task.get('attachments', [])
                    for attachment in attachments:
                        if attachment['type'] == 'ElasticNetworkInterface':
                            for detail in attachment['details']:
                                if detail['name'] == 'networkInterfaceId':
                                    eni_id = detail['value']
                                    
                                    # Get ENI details
                                    eni_response = ec2_client.describe_network_interfaces(
                                        NetworkInterfaceIds=[eni_id]
                                    )
                                    
                                    if eni_response['NetworkInterfaces']:
                                        eni = eni_response['NetworkInterfaces'][0]
                                        private_ip = eni.get('PrivateIpAddress')
                                        subnet_id = eni.get('SubnetId')
                                        vpc_id = eni.get('VpcId')
                                        
                                        print(f"   - Private IP: {private_ip}")
                                        print(f"   - Subnet: {subnet_id}")
                                        print(f"   - VPC: {vpc_id}")
                                        
                                        if vpc_id == lb_vpc_id:
                                            print("   ✅ Task is in correct VPC")
                                        else:
                                            print("   ❌ Task is in wrong VPC")
            
            # 8. Check target group registration
            print("\n8. Checking Target Group Registration:")
            print("-" * 38)
            
            # Get target group
            tg_response = elb_client.describe_target_groups(
                LoadBalancerArn=multimodal_lb['LoadBalancerArn']
            )
            
            if tg_response['TargetGroups']:
                target_group = tg_response['TargetGroups'][0]
                tg_arn = target_group['TargetGroupArn']
                
                # Wait for registration
                print("⏳ Waiting for target registration and health checks (2 minutes)...")
                time.sleep(120)
                
                health_response = elb_client.describe_target_health(
                    TargetGroupArn=tg_arn
                )
                
                healthy_targets = 0
                total_targets = len(health_response['TargetHealthDescriptions'])
                
                print(f"📊 Target Health Status:")
                for target_health in health_response['TargetHealthDescriptions']:
                    target_id = target_health['Target']['Id']
                    health_state = target_health['TargetHealth']['State']
                    
                    print(f"   - Target {target_id}: {health_state}")
                    
                    if health_state == 'healthy':
                        healthy_targets += 1
                    else:
                        reason = target_health['TargetHealth'].get('Reason', 'Unknown')
                        description = target_health['TargetHealth'].get('Description', '')
                        print(f"     Reason: {reason}")
                        if description:
                            print(f"     Description: {description}")
                
                print(f"\n📈 Final Health Summary: {healthy_targets}/{total_targets} targets healthy")
                
                if healthy_targets > 0:
                    result['success'] = True
                    result['fix_actions'].append(f"Successfully registered {healthy_targets} healthy targets")
                    print("🎉 Comprehensive networking fix successful!")
                    print(f"🌐 Load balancer DNS: {multimodal_lb['DNSName']}")
                elif total_targets > 0:
                    result['fix_actions'].append("Targets registered but not yet healthy")
                    print("⏳ Targets registered but health checks may need more time")
                else:
                    result['fix_actions'].append("No targets registered")
                    print("⚠️  No targets registered - may need manual investigation")
            
        except Exception as e:
            print(f"❌ Error updating service: {e}")
            result['fix_actions'].append(f"Error updating service: {e}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error during comprehensive fix: {e}")
        return {'error': str(e)}

if __name__ == "__main__":
    result = comprehensive_networking_fix()
    
    # Save result to file
    result_file = f"comprehensive-networking-fix-{int(datetime.now().timestamp())}.json"
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 Fix results saved to: {result_file}")
    
    if result.get('success'):
        print("\n✅ Comprehensive networking fix successful!")
        print("🚀 Production environment is now ready for end-to-end testing")
        sys.exit(0)
    else:
        print("\n⚠️  Comprehensive networking fix needs attention")
        sys.exit(1)