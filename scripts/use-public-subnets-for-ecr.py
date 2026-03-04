#!/usr/bin/env python3
"""
Use public subnets for ECR connectivity.
"""

import boto3
import json
import sys
import time
from datetime import datetime

def use_public_subnets_for_ecr():
    """Use public subnets for ECR connectivity."""
    
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
        
        print("🔧 USING PUBLIC SUBNETS FOR ECR CONNECTIVITY")
        print("=" * 50)
        
        cluster_name = 'multimodal-lib-prod-cluster'
        service_name = 'multimodal-lib-prod-service'
        
        # 1. Get VPC information
        print("\n1. FINDING PUBLIC SUBNETS:")
        print("-" * 28)
        
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
        
        # Find public subnets (subnets with internet gateway routes)
        all_subnets = ec2_client.describe_subnets(
            Filters=[
                {'Name': 'vpc-id', 'Values': [target_vpc_id]},
                {'Name': 'state', 'Values': ['available']}
            ]
        )
        
        public_subnets = []
        
        for subnet in all_subnets['Subnets']:
            subnet_id = subnet['SubnetId']
            subnet_az = subnet['AvailabilityZone']
            
            # Check if subnet has internet gateway route
            route_tables = ec2_client.describe_route_tables(
                Filters=[
                    {'Name': 'association.subnet-id', 'Values': [subnet_id]}
                ]
            )
            
            # If no explicit association, check main route table
            if not route_tables['RouteTables']:
                route_tables = ec2_client.describe_route_tables(
                    Filters=[
                        {'Name': 'vpc-id', 'Values': [target_vpc_id]},
                        {'Name': 'association.main', 'Values': ['true']}
                    ]
                )
            
            has_igw = False
            for rt in route_tables['RouteTables']:
                for route in rt['Routes']:
                    if route.get('GatewayId', '').startswith('igw-'):
                        has_igw = True
                        break
            
            if has_igw:
                public_subnets.append(subnet_id)
                print(f"✅ Public subnet: {subnet_id} (AZ: {subnet_az})")
        
        if not public_subnets:
            print("❌ No public subnets found!")
            result['fix_actions'].append("No public subnets found in VPC")
            return result
        
        # Use first 2 public subnets
        selected_subnets = public_subnets[:2]
        print(f"📋 Selected subnets: {selected_subnets}")
        
        # 2. Get current service configuration
        print("\n2. UPDATING SERVICE CONFIGURATION:")
        print("-" * 36)
        
        service_details = ecs_client.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        service = service_details['services'][0]
        network_config = service.get('networkConfiguration', {})
        awsvpc_config = network_config.get('awsvpcConfiguration', {})
        current_sgs = awsvpc_config.get('securityGroups', [])
        
        print(f"🔄 Updating service configuration:")
        print(f"   - New subnets: {selected_subnets}")
        print(f"   - Security groups: {current_sgs}")
        print(f"   - Public IP: ENABLED")
        
        try:
            update_response = ecs_client.update_service(
                cluster=cluster_name,
                service=service_name,
                networkConfiguration={
                    'awsvpcConfiguration': {
                        'subnets': selected_subnets,
                        'securityGroups': current_sgs,
                        'assignPublicIp': 'ENABLED'
                    }
                },
                forceNewDeployment=True
            )
            
            print("✅ Service configuration updated")
            result['fix_actions'].append(f"Updated service to use public subnets: {selected_subnets}")
            result['fix_actions'].append("Enabled public IP assignment")
            
        except Exception as e:
            print(f"❌ Error updating service: {e}")
            result['fix_actions'].append(f"Error updating service: {e}")
            return result
        
        # 3. Wait for deployment
        print("\n3. MONITORING DEPLOYMENT:")
        print("-" * 26)
        
        print("⏳ Waiting for new deployment...")
        time.sleep(60)
        
        # Monitor deployment progress
        max_attempts = 15
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
                result['fix_actions'].append("Service deployment successful with public subnets")
                break
            
            # Check for recent errors
            recent_events = service.get('events', [])[:2]
            for event in recent_events:
                message = event['message']
                if 'unable to place' in message.lower():
                    if 'cannot pull' in message.lower():
                        print(f"   ❌ Still ECR connectivity issues")
                    else:
                        print(f"   ⚠️  Other issue: {message[:60]}...")
                elif 'started' in message.lower():
                    print(f"   ✅ Task started successfully")
            
            time.sleep(30)
        
        if attempt >= max_attempts:
            print("⚠️  Deployment taking longer than expected")
            result['fix_actions'].append("Deployment in progress but not yet complete")
            
            # Check if we're making progress
            service_details = ecs_client.describe_services(
                cluster=cluster_name,
                services=[service_name]
            )
            
            service = service_details['services'][0]
            if service['runningCount'] > 0:
                result['success'] = True
                result['fix_actions'].append("Partial success - some tasks running")
        
        return result
        
    except Exception as e:
        print(f"❌ Error during public subnet fix: {e}")
        return {'error': str(e)}

if __name__ == "__main__":
    result = use_public_subnets_for_ecr()
    
    # Save result to file
    result_file = f"public-subnets-ecr-fix-{int(datetime.now().timestamp())}.json"
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 Fix results saved to: {result_file}")
    
    if result.get('success'):
        print("\n✅ Public subnets ECR fix successful!")
        print("🚀 Production environment should now be ready for testing")
        sys.exit(0)
    else:
        print("\n⚠️  Public subnets ECR fix needs attention")
        sys.exit(1)