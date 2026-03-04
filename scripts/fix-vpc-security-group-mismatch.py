#!/usr/bin/env python3
"""
Fix VPC and security group mismatch for ECS service and load balancer.
"""

import boto3
import json
import sys
import time
from datetime import datetime

def fix_vpc_security_group_mismatch():
    """Fix VPC and security group mismatch."""
    
    try:
        # Initialize clients
        ecs_client = boto3.client('ecs', region_name='us-east-1')
        elb_client = boto3.client('elbv2', region_name='us-east-1')
        ec2_client = boto3.client('ec2', region_name='us-east-1')
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'vpc_analysis': {},
            'security_group_analysis': {},
            'fix_actions': [],
            'success': False
        }
        
        print("🔧 Fixing VPC and Security Group Mismatch")
        print("=" * 45)
        
        cluster_name = 'multimodal-lib-prod-cluster'
        service_name = 'multimodal-lib-prod-service'
        
        # 1. Analyze VPC configuration
        print("\n1. Analyzing VPC Configuration:")
        print("-" * 33)
        
        # Get load balancer VPC
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
        
        print(f"🔗 Load Balancer VPC: {lb_vpc_id}")
        print(f"🔗 Load Balancer Subnets: {lb_subnet_ids}")
        
        # Get current service configuration
        service_details = ecs_client.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        if not service_details['services']:
            print(f"❌ Service {service_name} not found")
            return result
        
        service = service_details['services'][0]
        network_config = service.get('networkConfiguration', {})
        awsvpc_config = network_config.get('awsvpcConfiguration', {})
        service_subnets = awsvpc_config.get('subnets', [])
        service_security_groups = awsvpc_config.get('securityGroups', [])
        
        # Get service subnet VPCs
        if service_subnets:
            subnet_response = ec2_client.describe_subnets(SubnetIds=service_subnets[:1])
            service_vpc_id = subnet_response['Subnets'][0]['VpcId']
            
            print(f"📋 Service VPC: {service_vpc_id}")
            print(f"📋 Service Subnets: {service_subnets}")
            print(f"📋 Service Security Groups: {service_security_groups}")
            
            result['vpc_analysis'] = {
                'lb_vpc_id': lb_vpc_id,
                'service_vpc_id': service_vpc_id,
                'vpc_match': lb_vpc_id == service_vpc_id
            }
            
            if lb_vpc_id != service_vpc_id:
                print("❌ VPC mismatch detected!")
                print(f"   Load Balancer VPC: {lb_vpc_id}")
                print(f"   Service VPC: {service_vpc_id}")
                result['fix_actions'].append("VPC mismatch detected - need to use load balancer VPC")
            else:
                print("✅ VPCs match")
        
        # 2. Find or create appropriate security group
        print("\n2. Security Group Analysis:")
        print("-" * 30)
        
        # Look for existing security groups in the load balancer VPC that allow port 8000
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
                    print(f"✅ Found suitable security group: {sg_name} ({sg_id})")
                    break
            
            if suitable_sg:
                break
        
        if not suitable_sg:
            print("⚠️  No suitable security group found, will create one")
            
            # Create a new security group
            try:
                create_sg_response = ec2_client.create_security_group(
                    GroupName=f'multimodal-lib-ecs-{int(datetime.now().timestamp())}',
                    Description='Security group for Multimodal Librarian ECS service',
                    VpcId=lb_vpc_id
                )
                
                suitable_sg = create_sg_response['GroupId']
                print(f"✅ Created new security group: {suitable_sg}")
                
                # Add inbound rule for port 8000
                ec2_client.authorize_security_group_ingress(
                    GroupId=suitable_sg,
                    IpPermissions=[
                        {
                            'IpProtocol': 'tcp',
                            'FromPort': 8000,
                            'ToPort': 8000,
                            'IpRanges': [{'CidrIp': '10.0.0.0/8', 'Description': 'Allow port 8000 from VPC'}]
                        }
                    ]
                )
                
                print("✅ Added inbound rule for port 8000")
                result['fix_actions'].append(f"Created new security group {suitable_sg} with port 8000 access")
                
            except Exception as e:
                print(f"❌ Error creating security group: {e}")
                result['fix_actions'].append(f"Error creating security group: {e}")
                return result
        
        result['security_group_analysis'] = {
            'suitable_sg': suitable_sg,
            'vpc_id': lb_vpc_id
        }
        
        # 3. Find compatible subnets in the load balancer VPC
        print("\n3. Finding Compatible Subnets:")
        print("-" * 32)
        
        # Get private subnets in the load balancer VPC
        subnets_response = ec2_client.describe_subnets(
            Filters=[
                {'Name': 'vpc-id', 'Values': [lb_vpc_id]},
                {'Name': 'state', 'Values': ['available']}
            ]
        )
        
        # Find private subnets (no direct internet gateway route)
        compatible_subnets = []
        
        for subnet in subnets_response['Subnets']:
            subnet_id = subnet['SubnetId']
            subnet_az = subnet['AvailabilityZone']
            
            # Check if it's a private subnet
            route_tables = ec2_client.describe_route_tables(
                Filters=[
                    {'Name': 'association.subnet-id', 'Values': [subnet_id]}
                ]
            )
            
            is_private = True
            for rt in route_tables['RouteTables']:
                for route in rt['Routes']:
                    if route.get('GatewayId', '').startswith('igw-'):
                        is_private = False
                        break
            
            if is_private:
                compatible_subnets.append(subnet_id)
                print(f"✅ Compatible private subnet: {subnet_id} (AZ: {subnet_az})")
        
        if not compatible_subnets:
            print("❌ No compatible private subnets found")
            result['fix_actions'].append("No compatible private subnets found")
            return result
        
        # Use first 2 subnets for cost efficiency
        new_subnets = compatible_subnets[:2]
        
        # 4. Update service configuration
        print("\n4. Updating Service Configuration:")
        print("-" * 35)
        
        print(f"🔄 Updating service configuration:")
        print(f"   - Subnets: {new_subnets}")
        print(f"   - Security Group: {suitable_sg}")
        
        try:
            # Update service network configuration
            update_response = ecs_client.update_service(
                cluster=cluster_name,
                service=service_name,
                networkConfiguration={
                    'awsvpcConfiguration': {
                        'subnets': new_subnets,
                        'securityGroups': [suitable_sg],
                        'assignPublicIp': 'DISABLED'
                    }
                },
                forceNewDeployment=True
            )
            
            print("✅ Service configuration updated")
            print("🔄 Forcing new deployment to apply changes")
            
            result['fix_actions'].append(f"Updated service subnets to: {new_subnets}")
            result['fix_actions'].append(f"Updated security group to: {suitable_sg}")
            result['fix_actions'].append("Forced new deployment")
            
            # 5. Wait for deployment to stabilize
            print("\n5. Waiting for Deployment to Stabilize:")
            print("-" * 40)
            
            print("⏳ Waiting for service to stabilize (this may take 5-10 minutes)...")
            
            # Wait for deployment to start
            time.sleep(30)
            
            # Monitor deployment progress
            max_attempts = 20  # 10 minutes max
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
                    print("✅ Service deployment stabilized")
                    break
                
                time.sleep(30)
            
            # 6. Check target group health
            print("\n6. Checking Target Group Health:")
            print("-" * 33)
            
            # Get target group
            tg_response = elb_client.describe_target_groups(
                LoadBalancerArn=multimodal_lb['LoadBalancerArn']
            )
            
            if tg_response['TargetGroups']:
                target_group = tg_response['TargetGroups'][0]
                tg_arn = target_group['TargetGroupArn']
                
                # Wait for health checks
                print("⏳ Waiting for health checks (90 seconds)...")
                time.sleep(90)
                
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
                
                print(f"\n📈 Health Summary: {healthy_targets}/{total_targets} targets healthy")
                
                if healthy_targets > 0:
                    result['success'] = True
                    result['fix_actions'].append(f"Successfully registered {healthy_targets} healthy targets")
                    print("🎉 VPC and security group mismatch fixed! Load balancer now has healthy targets")
                elif total_targets > 0:
                    result['fix_actions'].append("Targets registered but not yet healthy - may need more time")
                    print("⏳ Targets registered but not yet healthy - health checks may need more time")
                else:
                    result['fix_actions'].append("No targets registered yet - deployment may still be in progress")
                    print("⚠️  No targets registered yet - deployment may still be in progress")
            
        except Exception as e:
            print(f"❌ Error updating service: {e}")
            result['fix_actions'].append(f"Error updating service: {e}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error during fix: {e}")
        return {'error': str(e)}

if __name__ == "__main__":
    result = fix_vpc_security_group_mismatch()
    
    # Save result to file
    result_file = f"vpc-security-group-fix-{int(datetime.now().timestamp())}.json"
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 Fix results saved to: {result_file}")
    
    if result.get('success'):
        print("\n✅ VPC and security group mismatch successfully fixed!")
        print("🌐 Production service should now be accessible via load balancer")
        sys.exit(0)
    else:
        print("\n⚠️  VPC and security group fix in progress or needs attention")
        sys.exit(1)