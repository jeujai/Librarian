#!/usr/bin/env python3
"""
Fix AWS Secrets Manager connectivity for ECS tasks.
"""

import boto3
import json
import sys
import time
from datetime import datetime

def fix_secrets_manager_connectivity():
    """Fix connectivity to AWS Secrets Manager."""
    
    try:
        # Initialize clients
        ec2_client = boto3.client('ec2', region_name='us-east-1')
        ecs_client = boto3.client('ecs', region_name='us-east-1')
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'vpc_analysis': {},
            'endpoint_analysis': {},
            'fix_actions': [],
            'success': False
        }
        
        print("🔧 Fixing AWS Secrets Manager Connectivity")
        print("=" * 45)
        
        # 1. Get VPC information
        print("\n1. Analyzing VPC Configuration:")
        print("-" * 33)
        
        # Get the VPC ID from the load balancer (which is the target VPC)
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
        
        # Get VPC details
        vpc_response = ec2_client.describe_vpcs(VpcIds=[target_vpc_id])
        vpc = vpc_response['Vpcs'][0]
        vpc_cidr = vpc['CidrBlock']
        
        print(f"   - CIDR: {vpc_cidr}")
        
        result['vpc_analysis'] = {
            'vpc_id': target_vpc_id,
            'cidr_block': vpc_cidr
        }
        
        # 2. Check existing VPC endpoints
        print("\n2. Checking VPC Endpoints:")
        print("-" * 26)
        
        endpoints_response = ec2_client.describe_vpc_endpoints(
            Filters=[
                {'Name': 'vpc-id', 'Values': [target_vpc_id]}
            ]
        )
        
        existing_endpoints = {}
        
        for endpoint in endpoints_response['VpcEndpoints']:
            service_name = endpoint['ServiceName']
            endpoint_id = endpoint['VpcEndpointId']
            state = endpoint['State']
            
            print(f"📍 Endpoint: {service_name}")
            print(f"   - ID: {endpoint_id}")
            print(f"   - State: {state}")
            
            existing_endpoints[service_name] = {
                'id': endpoint_id,
                'state': state
            }
        
        # Check for required endpoints
        required_services = [
            'com.amazonaws.us-east-1.secretsmanager',
            'com.amazonaws.us-east-1.ecr.dkr',
            'com.amazonaws.us-east-1.ecr.api',
            'com.amazonaws.us-east-1.logs'
        ]
        
        missing_endpoints = []
        for service in required_services:
            if service not in existing_endpoints:
                missing_endpoints.append(service)
                print(f"❌ Missing endpoint: {service}")
            else:
                print(f"✅ Found endpoint: {service}")
        
        result['endpoint_analysis'] = {
            'existing_endpoints': existing_endpoints,
            'missing_endpoints': missing_endpoints
        }
        
        # 3. Create missing VPC endpoints
        if missing_endpoints:
            print("\n3. Creating Missing VPC Endpoints:")
            print("-" * 35)
            
            # Get private subnets for endpoint placement
            subnets_response = ec2_client.describe_subnets(
                Filters=[
                    {'Name': 'vpc-id', 'Values': [target_vpc_id]},
                    {'Name': 'state', 'Values': ['available']}
                ]
            )
            
            private_subnets = []
            for subnet in subnets_response['Subnets']:
                subnet_id = subnet['SubnetId']
                
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
                    private_subnets.append(subnet_id)
            
            if not private_subnets:
                print("❌ No private subnets found for endpoint placement")
                result['fix_actions'].append("No private subnets found")
                return result
            
            print(f"📍 Using subnets for endpoints: {private_subnets[:2]}")  # Use first 2 subnets
            
            # Create security group for VPC endpoints
            try:
                sg_response = ec2_client.create_security_group(
                    GroupName=f'vpc-endpoints-{int(datetime.now().timestamp())}',
                    Description='Security group for VPC endpoints',
                    VpcId=target_vpc_id
                )
                
                endpoint_sg_id = sg_response['GroupId']
                print(f"✅ Created security group for endpoints: {endpoint_sg_id}")
                
                # Add inbound rule for HTTPS
                ec2_client.authorize_security_group_ingress(
                    GroupId=endpoint_sg_id,
                    IpPermissions=[
                        {
                            'IpProtocol': 'tcp',
                            'FromPort': 443,
                            'ToPort': 443,
                            'IpRanges': [{'CidrIp': vpc_cidr, 'Description': 'Allow HTTPS from VPC'}]
                        }
                    ]
                )
                
                result['fix_actions'].append(f"Created security group {endpoint_sg_id} for VPC endpoints")
                
            except Exception as e:
                print(f"❌ Error creating security group: {e}")
                result['fix_actions'].append(f"Error creating security group: {e}")
                return result
            
            # Create VPC endpoints
            created_endpoints = []
            
            for service in missing_endpoints:
                try:
                    print(f"🔧 Creating endpoint for {service}...")
                    
                    endpoint_response = ec2_client.create_vpc_endpoint(
                        VpcId=target_vpc_id,
                        ServiceName=service,
                        VpcEndpointType='Interface',
                        SubnetIds=private_subnets[:2],  # Use first 2 subnets
                        SecurityGroupIds=[endpoint_sg_id],
                        PrivateDnsEnabled=True,
                        PolicyDocument=json.dumps({
                            "Version": "2012-10-17",
                            "Statement": [
                                {
                                    "Effect": "Allow",
                                    "Principal": "*",
                                    "Action": "*",
                                    "Resource": "*"
                                }
                            ]
                        })
                    )
                    
                    endpoint_id = endpoint_response['VpcEndpoint']['VpcEndpointId']
                    created_endpoints.append(endpoint_id)
                    
                    print(f"✅ Created endpoint: {endpoint_id}")
                    result['fix_actions'].append(f"Created VPC endpoint {endpoint_id} for {service}")
                    
                except Exception as e:
                    print(f"❌ Error creating endpoint for {service}: {e}")
                    result['fix_actions'].append(f"Error creating endpoint for {service}: {e}")
            
            if created_endpoints:
                print(f"\n⏳ Waiting for endpoints to become available...")
                time.sleep(60)  # Wait for endpoints to be ready
                
                # Check endpoint status
                for endpoint_id in created_endpoints:
                    endpoint_details = ec2_client.describe_vpc_endpoints(
                        VpcEndpointIds=[endpoint_id]
                    )
                    
                    if endpoint_details['VpcEndpoints']:
                        endpoint = endpoint_details['VpcEndpoints'][0]
                        state = endpoint['State']
                        service_name = endpoint['ServiceName']
                        
                        print(f"   - {service_name}: {state}")
        
        else:
            print("\n3. All Required Endpoints Present:")
            print("-" * 35)
            print("✅ All required VPC endpoints already exist")
        
        # 4. Test connectivity and restart service
        print("\n4. Restarting ECS Service:")
        print("-" * 26)
        
        cluster_name = 'multimodal-lib-prod-cluster'
        service_name = 'multimodal-lib-prod-service'
        
        try:
            # Force new deployment to test connectivity
            print("🔄 Forcing new deployment to test connectivity...")
            
            update_response = ecs_client.update_service(
                cluster=cluster_name,
                service=service_name,
                forceNewDeployment=True
            )
            
            print("✅ Service deployment initiated")
            result['fix_actions'].append("Forced new deployment to test connectivity")
            
            # Wait for deployment to start
            print("⏳ Waiting for deployment to start...")
            time.sleep(60)
            
            # Check service events for connectivity issues
            service_details = ecs_client.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            
            if service_details['services']:
                service = service_details['services'][0]
                recent_events = service.get('events', [])[:3]  # Last 3 events
                
                print("📋 Recent Service Events:")
                connectivity_fixed = True
                
                for event in recent_events:
                    message = event['message']
                    timestamp = event['createdAt'].strftime('%Y-%m-%d %H:%M:%S')
                    
                    print(f"   [{timestamp}] {message[:100]}...")
                    
                    if 'unable to retrieve secret' in message.lower() or 'secrets manager' in message.lower():
                        connectivity_fixed = False
                
                if connectivity_fixed:
                    print("✅ No recent connectivity errors detected")
                    result['success'] = True
                    result['fix_actions'].append("Secrets Manager connectivity appears to be fixed")
                else:
                    print("⚠️  Still seeing connectivity issues - may need more time")
                    result['fix_actions'].append("Connectivity issues may still persist")
            
        except Exception as e:
            print(f"❌ Error restarting service: {e}")
            result['fix_actions'].append(f"Error restarting service: {e}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error during fix: {e}")
        return {'error': str(e)}

if __name__ == "__main__":
    result = fix_secrets_manager_connectivity()
    
    # Save result to file
    result_file = f"secrets-manager-connectivity-fix-{int(datetime.now().timestamp())}.json"
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 Fix results saved to: {result_file}")
    
    if result.get('success'):
        print("\n✅ Secrets Manager connectivity successfully fixed!")
        print("🚀 ECS tasks should now be able to start properly")
        sys.exit(0)
    else:
        print("\n⚠️  Secrets Manager connectivity fix needs attention")
        sys.exit(1)