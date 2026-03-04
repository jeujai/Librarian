#!/usr/bin/env python3
"""
Fix ECR connectivity issue preventing container pulls.
"""

import boto3
import json
import sys
import time
from datetime import datetime

def fix_ecr_connectivity_issue():
    """Fix ECR connectivity issue."""
    
    try:
        # Initialize clients
        ecs_client = boto3.client('ecs', region_name='us-east-1')
        ec2_client = boto3.client('ec2', region_name='us-east-1')
        elb_client = boto3.client('elbv2', region_name='us-east-1')
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'fix_actions': [],
            'success': False
        }
        
        print("🔧 FIXING ECR CONNECTIVITY ISSUE")
        print("=" * 40)
        
        cluster_name = 'multimodal-lib-prod-cluster'
        service_name = 'multimodal-lib-prod-service'
        
        # 1. Get VPC information
        print("\n1. ANALYZING VPC CONFIGURATION:")
        print("-" * 35)
        
        # Get VPC from load balancer
        lb_response = elb_client.describe_load_balancers()
        target_vpc_id = None
        
        for lb in lb_response['LoadBalancers']:
            if 'multimodal' in lb['LoadBalancerName'].lower():
                target_vpc_id = lb['VpcId']
                break
        
        if not target_vpc_id:
            print("❌ Cannot find target VPC")
            return result
        
        print(f"🌐 Target VPC: {target_vpc_id}")
        
        # Get VPC CIDR
        vpc_response = ec2_client.describe_vpcs(VpcIds=[target_vpc_id])
        vpc_cidr = vpc_response['Vpcs'][0]['CidrBlock']
        print(f"   CIDR: {vpc_cidr}")
        
        # 2. Check current service network configuration
        print("\n2. CHECKING SERVICE NETWORK CONFIG:")
        print("-" * 37)
        
        service_details = ecs_client.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        service = service_details['services'][0]
        network_config = service.get('networkConfiguration', {})
        awsvpc_config = network_config.get('awsvpcConfiguration', {})
        
        current_subnets = awsvpc_config.get('subnets', [])
        current_sgs = awsvpc_config.get('securityGroups', [])
        assign_public_ip = awsvpc_config.get('assignPublicIp', 'DISABLED')
        
        print(f"📋 Current Configuration:")
        print(f"   Subnets: {current_subnets}")
        print(f"   Security Groups: {current_sgs}")
        print(f"   Public IP: {assign_public_ip}")
        
        # 3. Check if subnets have internet access
        print("\n3. CHECKING SUBNET INTERNET ACCESS:")
        print("-" * 38)
        
        subnet_has_internet = False
        
        for subnet_id in current_subnets:
            # Get route table for subnet
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
            
            subnet_type = "Public" if has_igw else ("Private with NAT" if has_nat else "Private isolated")
            print(f"   {subnet_id}: {subnet_type}")
            
            if has_igw or has_nat:
                subnet_has_internet = True
        
        if not subnet_has_internet:
            print("❌ No subnets have internet access!")
            result['fix_actions'].append("No subnets have internet access for ECR")
            
            # Find subnets with internet access
            print("\n   🔍 Finding subnets with internet access...")
            
            all_subnets = ec2_client.describe_subnets(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [target_vpc_id]},
                    {'Name': 'state', 'Values': ['available']}
                ]
            )
            
            internet_subnets = []
            
            for subnet in all_subnets['Subnets']:
                subnet_id = subnet['SubnetId']
                subnet_az = subnet['AvailabilityZone']
                
                # Check route table
                route_tables = ec2_client.describe_route_tables(
                    Filters=[
                        {'Name': 'association.subnet-id', 'Values': [subnet_id]}
                    ]
                )
                
                has_internet = False
                for rt in route_tables['RouteTables']:
                    for route in rt['Routes']:
                        if route.get('GatewayId', '').startswith('igw-') or route.get('NatGatewayId'):
                            has_internet = True
                            break
                
                if has_internet:
                    internet_subnets.append(subnet_id)
                    print(f"   ✅ Found: {subnet_id} (AZ: {subnet_az})")
            
            if internet_subnets:
                # Update service to use subnets with internet access
                print(f"\n   🔄 Updating service to use internet-accessible subnets...")
                
                new_subnets = internet_subnets[:2]  # Use first 2
                
                try:
                    update_response = ecs_client.update_service(
                        cluster=cluster_name,
                        service=service_name,
                        networkConfiguration={
                            'awsvpcConfiguration': {
                                'subnets': new_subnets,
                                'securityGroups': current_sgs,
                                'assignPublicIp': 'ENABLED'  # Enable public IP for ECR access
                            }
                        },
                        forceNewDeployment=True
                    )
                    
                    print(f"   ✅ Updated service to use subnets: {new_subnets}")
                    print(f"   ✅ Enabled public IP assignment")
                    
                    result['fix_actions'].append(f"Updated service subnets to: {new_subnets}")
                    result['fix_actions'].append("Enabled public IP assignment for ECR access")
                    
                except Exception as e:
                    print(f"   ❌ Error updating service: {e}")
                    result['fix_actions'].append(f"Error updating service: {e}")
                    return result
            else:
                print("   ❌ No subnets with internet access found!")
                result['fix_actions'].append("No subnets with internet access found")
                return result
        else:
            print("✅ Subnets have internet access")
            
            # Check if public IP is enabled
            if assign_public_ip == 'DISABLED':
                print("⚠️  Public IP assignment is disabled - enabling for ECR access")
                
                try:
                    update_response = ecs_client.update_service(
                        cluster=cluster_name,
                        service=service_name,
                        networkConfiguration={
                            'awsvpcConfiguration': {
                                'subnets': current_subnets,
                                'securityGroups': current_sgs,
                                'assignPublicIp': 'ENABLED'
                            }
                        },
                        forceNewDeployment=True
                    )
                    
                    print("✅ Enabled public IP assignment")
                    result['fix_actions'].append("Enabled public IP assignment for ECR access")
                    
                except Exception as e:
                    print(f"❌ Error enabling public IP: {e}")
                    result['fix_actions'].append(f"Error enabling public IP: {e}")
                    return result
        
        # 4. Check security group rules
        print("\n4. CHECKING SECURITY GROUP RULES:")
        print("-" * 36)
        
        for sg_id in current_sgs:
            sg_response = ec2_client.describe_security_groups(GroupIds=[sg_id])
            sg = sg_response['SecurityGroups'][0]
            
            print(f"🔒 Security Group: {sg['GroupName']} ({sg_id})")
            
            # Check outbound rules for HTTPS
            outbound_rules = sg['IpPermissionsEgress']
            https_allowed = False
            
            for rule in outbound_rules:
                protocol = rule.get('IpProtocol')
                from_port = rule.get('FromPort')
                to_port = rule.get('ToPort')
                
                if protocol == 'tcp' and from_port <= 443 <= to_port:
                    https_allowed = True
                    print(f"   ✅ HTTPS outbound allowed: {protocol}:{from_port}-{to_port}")
                elif protocol == '-1':  # All traffic
                    https_allowed = True
                    print(f"   ✅ All outbound traffic allowed")
            
            if not https_allowed:
                print(f"   ❌ HTTPS outbound not allowed - adding rule")
                
                try:
                    ec2_client.authorize_security_group_egress(
                        GroupId=sg_id,
                        IpPermissions=[
                            {
                                'IpProtocol': 'tcp',
                                'FromPort': 443,
                                'ToPort': 443,
                                'IpRanges': [{'CidrIp': '0.0.0.0/0', 'Description': 'HTTPS for ECR access'}]
                            }
                        ]
                    )
                    print(f"   ✅ Added HTTPS outbound rule")
                    result['fix_actions'].append(f"Added HTTPS outbound rule to {sg_id}")
                    
                except Exception as e:
                    print(f"   ❌ Error adding HTTPS rule: {e}")
                    result['fix_actions'].append(f"Error adding HTTPS rule to {sg_id}: {e}")
        
        # 5. Wait for deployment and check
        print("\n5. MONITORING DEPLOYMENT:")
        print("-" * 26)
        
        print("⏳ Waiting for new deployment...")
        time.sleep(60)
        
        # Check service status
        max_attempts = 10
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
                print("✅ Service deployment successful!")
                result['success'] = True
                result['fix_actions'].append("Service deployment successful")
                break
            
            # Check for recent errors
            recent_events = service.get('events', [])[:2]
            for event in recent_events:
                message = event['message']
                if 'unable to place' in message.lower() or 'cannot pull' in message.lower():
                    print(f"   ⚠️  Recent issue: {message[:80]}...")
            
            time.sleep(30)
        
        if attempt >= max_attempts:
            print("⚠️  Deployment taking longer than expected")
            result['fix_actions'].append("Deployment in progress but not yet complete")
        
        return result
        
    except Exception as e:
        print(f"❌ Error during ECR connectivity fix: {e}")
        return {'error': str(e)}

if __name__ == "__main__":
    result = fix_ecr_connectivity_issue()
    
    # Save result to file
    result_file = f"ecr-connectivity-fix-{int(datetime.now().timestamp())}.json"
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 Fix results saved to: {result_file}")
    
    if result.get('success'):
        print("\n✅ ECR connectivity issue successfully fixed!")
        print("🚀 Production environment should now be ready for testing")
        sys.exit(0)
    else:
        print("\n⚠️  ECR connectivity fix needs attention")
        sys.exit(1)