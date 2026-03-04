#!/usr/bin/env python3
"""
Fix subnet mismatch between ECS service and load balancer.
"""

import boto3
import json
import sys
import time
from datetime import datetime

def fix_subnet_mismatch():
    """Fix subnet mismatch between ECS service and load balancer."""
    
    try:
        # Initialize clients
        ecs_client = boto3.client('ecs', region_name='us-east-1')
        elb_client = boto3.client('elbv2', region_name='us-east-1')
        ec2_client = boto3.client('ec2', region_name='us-east-1')
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'current_configuration': {},
            'fix_actions': [],
            'success': False
        }
        
        print("🔧 Fixing Subnet Mismatch Between ECS Service and Load Balancer")
        print("=" * 65)
        
        cluster_name = 'multimodal-lib-prod-cluster'
        service_name = 'multimodal-lib-prod-service'
        
        # 1. Get current configurations
        print("\n1. Analyzing Current Configuration:")
        print("-" * 38)
        
        # Get service configuration
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
        
        print(f"📋 ECS Service Subnets: {len(service_subnets)}")
        for subnet in service_subnets:
            print(f"   - {subnet}")
        
        # Get load balancer configuration
        lb_response = elb_client.describe_load_balancers()
        multimodal_lb = None
        
        for lb in lb_response['LoadBalancers']:
            if 'multimodal' in lb['LoadBalancerName'].lower():
                multimodal_lb = lb
                break
        
        if not multimodal_lb:
            print("❌ Load balancer not found")
            return result
        
        lb_subnets = multimodal_lb.get('AvailabilityZones', [])
        lb_subnet_ids = [az['SubnetId'] for az in lb_subnets]
        
        print(f"🔗 Load Balancer Subnets: {len(lb_subnet_ids)}")
        for subnet in lb_subnet_ids:
            print(f"   - {subnet}")
        
        result['current_configuration'] = {
            'service_subnets': service_subnets,
            'lb_subnets': lb_subnet_ids,
            'service_security_groups': service_security_groups
        }
        
        # 2. Find compatible subnets
        print("\n2. Finding Compatible Subnets:")
        print("-" * 32)
        
        # Get all subnets in the VPC
        vpc_id = multimodal_lb['VpcId']
        
        subnets_response = ec2_client.describe_subnets(
            Filters=[
                {'Name': 'vpc-id', 'Values': [vpc_id]},
                {'Name': 'state', 'Values': ['available']}
            ]
        )
        
        # Find private subnets that are in the same AZs as load balancer subnets
        lb_azs = [az['ZoneName'] for az in lb_subnets]
        compatible_subnets = []
        
        print(f"🌐 Load Balancer AZs: {lb_azs}")
        
        for subnet in subnets_response['Subnets']:
            subnet_id = subnet['SubnetId']
            subnet_az = subnet['AvailabilityZone']
            
            # Check if it's a private subnet (no internet gateway route)
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
            
            # If subnet is in same AZ as load balancer and is private, it's compatible
            if subnet_az in lb_azs and is_private:
                compatible_subnets.append(subnet_id)
                print(f"✅ Compatible subnet found: {subnet_id} (AZ: {subnet_az})")
        
        if not compatible_subnets:
            print("❌ No compatible private subnets found")
            result['fix_actions'].append("No compatible private subnets found")
            return result
        
        # 3. Update service configuration
        print("\n3. Updating Service Configuration:")
        print("-" * 35)
        
        # Use the compatible subnets (limit to 2-3 for cost efficiency)
        new_subnets = compatible_subnets[:2]  # Use first 2 compatible subnets
        
        print(f"🔄 Updating service to use subnets: {new_subnets}")
        
        try:
            # Update service network configuration
            update_response = ecs_client.update_service(
                cluster=cluster_name,
                service=service_name,
                networkConfiguration={
                    'awsvpcConfiguration': {
                        'subnets': new_subnets,
                        'securityGroups': service_security_groups,
                        'assignPublicIp': 'DISABLED'
                    }
                },
                forceNewDeployment=True  # Force new deployment to apply changes
            )
            
            print("✅ Service configuration updated")
            print("🔄 Forcing new deployment to apply changes")
            
            result['fix_actions'].append(f"Updated service subnets to: {new_subnets}")
            result['fix_actions'].append("Forced new deployment")
            
            # 4. Wait for deployment to stabilize
            print("\n4. Waiting for Deployment to Stabilize:")
            print("-" * 40)
            
            print("⏳ Waiting for service to stabilize (this may take 5-10 minutes)...")
            
            # Wait for deployment to start
            time.sleep(30)
            
            # Check deployment status
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
            
            if attempt >= max_attempts:
                print("⚠️  Service deployment taking longer than expected")
                result['fix_actions'].append("Service deployment in progress but not yet stable")
            
            # 5. Check target group health
            print("\n5. Checking Target Group Health:")
            print("-" * 33)
            
            # Get target group
            tg_response = elb_client.describe_target_groups(
                LoadBalancerArn=multimodal_lb['LoadBalancerArn']
            )
            
            if tg_response['TargetGroups']:
                target_group = tg_response['TargetGroups'][0]
                tg_arn = target_group['TargetGroupArn']
                
                # Wait a bit for health checks
                print("⏳ Waiting for health checks (60 seconds)...")
                time.sleep(60)
                
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
                    elif health_state in ['unhealthy', 'initial', 'draining']:
                        reason = target_health['TargetHealth'].get('Reason', 'Unknown')
                        description = target_health['TargetHealth'].get('Description', '')
                        print(f"     Reason: {reason}")
                        if description:
                            print(f"     Description: {description}")
                
                print(f"\n📈 Health Summary: {healthy_targets}/{total_targets} targets healthy")
                
                if healthy_targets > 0:
                    result['success'] = True
                    result['fix_actions'].append(f"Successfully registered {healthy_targets} healthy targets")
                    print("🎉 Subnet mismatch fixed! Load balancer now has healthy targets")
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
    result = fix_subnet_mismatch()
    
    # Save result to file
    result_file = f"subnet-mismatch-fix-{int(datetime.now().timestamp())}.json"
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 Fix results saved to: {result_file}")
    
    if result.get('success'):
        print("\n✅ Subnet mismatch successfully fixed!")
        print("🌐 Production service should now be accessible via load balancer")
        sys.exit(0)
    else:
        print("\n⚠️  Subnet mismatch fix in progress or needs attention")
        sys.exit(1)