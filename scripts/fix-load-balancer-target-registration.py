#!/usr/bin/env python3
"""
Fix load balancer target registration for the production service.
"""

import boto3
import json
import sys
import time
from datetime import datetime

def fix_load_balancer_target_registration():
    """Fix load balancer target registration."""
    
    try:
        # Initialize clients
        ecs_client = boto3.client('ecs', region_name='us-east-1')
        elb_client = boto3.client('elbv2', region_name='us-east-1')
        
        result = {
            'timestamp': datetime.now().isoformat(),
            'service_analysis': {},
            'load_balancer_analysis': {},
            'target_group_analysis': {},
            'fix_actions': [],
            'success': False
        }
        
        print("🔧 Fixing Load Balancer Target Registration")
        print("=" * 50)
        
        # 1. Find the production service
        print("\n1. Analyzing Production Service:")
        print("-" * 35)
        
        cluster_name = 'multimodal-lib-prod-cluster'
        service_name = 'multimodal-lib-prod-service'
        
        service_details = ecs_client.describe_services(
            cluster=cluster_name,
            services=[service_name]
        )
        
        if not service_details['services']:
            print(f"❌ Service {service_name} not found in cluster {cluster_name}")
            return result
        
        service = service_details['services'][0]
        
        print(f"✅ Service Found: {service_name}")
        print(f"   - Status: {service['status']}")
        print(f"   - Running: {service['runningCount']}")
        print(f"   - Desired: {service['desiredCount']}")
        
        # Check current load balancer configuration
        load_balancers = service.get('loadBalancers', [])
        
        result['service_analysis'] = {
            'cluster': cluster_name,
            'service': service_name,
            'status': service['status'],
            'running_count': service['runningCount'],
            'desired_count': service['desiredCount'],
            'current_load_balancers': load_balancers
        }
        
        print(f"   - Current Load Balancers: {len(load_balancers)}")
        for lb in load_balancers:
            print(f"     - Target Group: {lb.get('targetGroupArn', 'N/A')}")
            print(f"     - Container: {lb.get('containerName', 'N/A')}:{lb.get('containerPort', 'N/A')}")
        
        # 2. Find the correct load balancer and target group
        print("\n2. Finding Correct Load Balancer:")
        print("-" * 35)
        
        # Get all load balancers
        lb_response = elb_client.describe_load_balancers()
        multimodal_lb = None
        
        for lb in lb_response['LoadBalancers']:
            if 'multimodal' in lb['LoadBalancerName'].lower():
                multimodal_lb = lb
                break
        
        if not multimodal_lb:
            print("❌ No multimodal load balancer found")
            return result
        
        lb_name = multimodal_lb['LoadBalancerName']
        lb_arn = multimodal_lb['LoadBalancerArn']
        
        print(f"✅ Load Balancer Found: {lb_name}")
        print(f"   - ARN: {lb_arn}")
        print(f"   - State: {multimodal_lb['State']['Code']}")
        
        result['load_balancer_analysis'] = {
            'name': lb_name,
            'arn': lb_arn,
            'state': multimodal_lb['State']['Code'],
            'dns_name': multimodal_lb['DNSName']
        }
        
        # Get target groups for this load balancer
        tg_response = elb_client.describe_target_groups(
            LoadBalancerArn=lb_arn
        )
        
        if not tg_response['TargetGroups']:
            print("❌ No target groups found for load balancer")
            return result
        
        target_group = tg_response['TargetGroups'][0]  # Use first target group
        tg_arn = target_group['TargetGroupArn']
        tg_name = target_group['TargetGroupName']
        
        print(f"✅ Target Group Found: {tg_name}")
        print(f"   - ARN: {tg_arn}")
        print(f"   - Port: {target_group['Port']}")
        print(f"   - Protocol: {target_group['Protocol']}")
        
        result['target_group_analysis'] = {
            'name': tg_name,
            'arn': tg_arn,
            'port': target_group['Port'],
            'protocol': target_group['Protocol']
        }
        
        # 3. Check if service is already configured with this target group
        print("\n3. Checking Current Configuration:")
        print("-" * 38)
        
        service_has_correct_tg = False
        for lb_config in load_balancers:
            if lb_config.get('targetGroupArn') == tg_arn:
                service_has_correct_tg = True
                break
        
        if service_has_correct_tg:
            print("✅ Service is already configured with correct target group")
            print("   - Issue may be with task health checks or networking")
            
            # Check target health
            health_response = elb_client.describe_target_health(
                TargetGroupArn=tg_arn
            )
            
            print("   - Target Health:")
            for target_health in health_response['TargetHealthDescriptions']:
                target_id = target_health['Target']['Id']
                health_state = target_health['TargetHealth']['State']
                reason = target_health['TargetHealth'].get('Reason', 'N/A')
                description = target_health['TargetHealth'].get('Description', 'N/A')
                
                print(f"     - Target {target_id}: {health_state}")
                if health_state != 'healthy':
                    print(f"       Reason: {reason}")
                    print(f"       Description: {description}")
            
            result['fix_actions'].append("Service already configured - check task health and networking")
            
        else:
            print("⚠️  Service is NOT configured with correct target group")
            print("   - Need to update service configuration")
            
            # 4. Update service configuration
            print("\n4. Updating Service Configuration:")
            print("-" * 38)
            
            try:
                # Update service with correct load balancer configuration
                update_response = ecs_client.update_service(
                    cluster=cluster_name,
                    service=service_name,
                    loadBalancers=[
                        {
                            'targetGroupArn': tg_arn,
                            'containerName': 'multimodal-lib-prod-app',  # Container name from task definition
                            'containerPort': 8000
                        }
                    ]
                )
                
                print("✅ Service configuration updated")
                print(f"   - Target Group: {tg_name}")
                print(f"   - Container: multimodal-lib-prod-app:8000")
                
                result['fix_actions'].append(f"Updated service with target group {tg_name}")
                
                # Wait for deployment to stabilize
                print("\n5. Waiting for Deployment to Stabilize:")
                print("-" * 42)
                
                print("⏳ Waiting for service to stabilize (this may take a few minutes)...")
                
                waiter = ecs_client.get_waiter('services_stable')
                waiter.wait(
                    cluster=cluster_name,
                    services=[service_name],
                    WaiterConfig={
                        'Delay': 15,
                        'MaxAttempts': 20  # 5 minutes max
                    }
                )
                
                print("✅ Service deployment stabilized")
                
                # Check target health after update
                print("\n6. Checking Target Health After Update:")
                print("-" * 42)
                
                time.sleep(30)  # Wait for health checks
                
                health_response = elb_client.describe_target_health(
                    TargetGroupArn=tg_arn
                )
                
                healthy_targets = 0
                total_targets = len(health_response['TargetHealthDescriptions'])
                
                for target_health in health_response['TargetHealthDescriptions']:
                    target_id = target_health['Target']['Id']
                    health_state = target_health['TargetHealth']['State']
                    
                    print(f"   - Target {target_id}: {health_state}")
                    
                    if health_state == 'healthy':
                        healthy_targets += 1
                    else:
                        reason = target_health['TargetHealth'].get('Reason', 'N/A')
                        description = target_health['TargetHealth'].get('Description', 'N/A')
                        print(f"     Reason: {reason}")
                        print(f"     Description: {description}")
                
                print(f"\n📊 Health Summary: {healthy_targets}/{total_targets} targets healthy")
                
                if healthy_targets > 0:
                    result['success'] = True
                    result['fix_actions'].append(f"Successfully registered {healthy_targets} healthy targets")
                    print("🎉 Load balancer target registration fixed!")
                else:
                    result['fix_actions'].append("Service updated but targets not yet healthy - may need more time")
                    print("⚠️  Targets registered but not yet healthy - may need more time")
                
            except Exception as e:
                print(f"❌ Error updating service: {e}")
                result['fix_actions'].append(f"Error updating service: {e}")
        
        return result
        
    except Exception as e:
        print(f"❌ Error during fix: {e}")
        return {'error': str(e)}

if __name__ == "__main__":
    result = fix_load_balancer_target_registration()
    
    # Save result to file
    result_file = f"load-balancer-fix-{int(datetime.now().timestamp())}.json"
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    print(f"\n📄 Fix results saved to: {result_file}")
    
    if result.get('success'):
        print("\n✅ Load balancer target registration successfully fixed!")
        print("🌐 Production service should now be accessible via load balancer")
        sys.exit(0)
    else:
        print("\n⚠️  Load balancer target registration needs attention")
        sys.exit(1)