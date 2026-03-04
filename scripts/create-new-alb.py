#!/usr/bin/env python3
"""
Create new Application Load Balancer for ALB connectivity fix.

This script creates a new ALB with proper configuration to resolve
the connectivity issue between ALB and ECS tasks.
"""

import boto3
import json
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional

def get_target_group_arn() -> Optional[str]:
    """
    Get the ARN of the newly created target group.
    
    Returns:
        Target group ARN or None if not found
    """
    client = boto3.client('elbv2', region_name='us-east-1')
    
    try:
        response = client.describe_target_groups(
            Names=['multimodal-lib-prod-tg-v2']
        )
        
        if response['TargetGroups']:
            return response['TargetGroups'][0]['TargetGroupArn']
        else:
            return None
            
    except client.exceptions.TargetGroupNotFoundException:
        return None
    except Exception as e:
        print(f"⚠️  Warning: Could not retrieve target group: {str(e)}")
        return None

def create_load_balancer() -> Dict[str, Any]:
    """
    Create new Application Load Balancer.
    
    Returns:
        Dict containing creation results and ALB details
    """
    client = boto3.client('elbv2', region_name='us-east-1')
    
    # ALB configuration from design document
    config = {
        'name': 'multimodal-lib-prod-alb-v2',
        'subnets': [
            'subnet-0c352188f5398a718',  # us-east-1a
            'subnet-02f4d9ecb751beb27',  # us-east-1b
            'subnet-02fe694f061238d5a'   # us-east-1c
        ],
        'security_groups': ['sg-0135b368e20b7bd01'],
        'scheme': 'internet-facing',
        'type': 'application',
        'ip_address_type': 'ipv4'
    }
    
    print("=" * 80)
    print("Creating New Application Load Balancer: multimodal-lib-prod-alb-v2")
    print("=" * 80)
    print(f"\nConfiguration:")
    print(f"  Name: {config['name']}")
    print(f"  Type: {config['type']}")
    print(f"  Scheme: {config['scheme']}")
    print(f"  IP Address Type: {config['ip_address_type']}")
    print(f"  Subnets:")
    for subnet in config['subnets']:
        print(f"    - {subnet}")
    print(f"  Security Groups:")
    for sg in config['security_groups']:
        print(f"    - {sg}")
    print()
    
    try:
        # Create load balancer
        print("Creating Application Load Balancer...")
        response = client.create_load_balancer(
            Name=config['name'],
            Subnets=config['subnets'],
            SecurityGroups=config['security_groups'],
            Scheme=config['scheme'],
            Type=config['type'],
            IpAddressType=config['ip_address_type'],
            Tags=[
                {'Key': 'Name', 'Value': config['name']},
                {'Key': 'Environment', 'Value': 'production'},
                {'Key': 'Application', 'Value': 'multimodal-librarian'},
                {'Key': 'Version', 'Value': 'v2'},
                {'Key': 'CreatedDate', 'Value': datetime.now().strftime('%Y-%m-%d')},
                {'Key': 'Purpose', 'Value': 'ALB-connectivity-fix'}
            ]
        )
        
        load_balancer = response['LoadBalancers'][0]
        alb_arn = load_balancer['LoadBalancerArn']
        alb_dns = load_balancer['DNSName']
        
        print(f"✅ Application Load Balancer created successfully!")
        print(f"\nLoad Balancer Details:")
        print(f"  ARN: {alb_arn}")
        print(f"  Name: {load_balancer['LoadBalancerName']}")
        print(f"  DNS Name: {alb_dns}")
        print(f"  State: {load_balancer['State']['Code']}")
        print(f"  Type: {load_balancer['Type']}")
        print(f"  Scheme: {load_balancer['Scheme']}")
        print(f"  VPC ID: {load_balancer['VpcId']}")
        
        # Wait for ALB to become active
        print("\n" + "=" * 80)
        print("Waiting for ALB to become active...")
        print("=" * 80)
        print("\nThis may take 2-3 minutes...")
        
        waiter = client.get_waiter('load_balancer_available')
        try:
            waiter.wait(
                LoadBalancerArns=[alb_arn],
                WaiterConfig={
                    'Delay': 15,
                    'MaxAttempts': 20
                }
            )
            print("✅ ALB is now active!")
        except Exception as e:
            print(f"⚠️  Warning: Waiter timed out, but ALB may still be provisioning: {str(e)}")
        
        # Get updated status
        describe_response = client.describe_load_balancers(
            LoadBalancerArns=[alb_arn]
        )
        
        updated_alb = describe_response['LoadBalancers'][0]
        current_state = updated_alb['State']['Code']
        
        print(f"\nCurrent State: {current_state}")
        
        # Prepare results
        results = {
            'success': True,
            'timestamp': datetime.now().isoformat(),
            'load_balancer': {
                'arn': alb_arn,
                'name': load_balancer['LoadBalancerName'],
                'dns_name': alb_dns,
                'state': current_state,
                'type': load_balancer['Type'],
                'scheme': load_balancer['Scheme'],
                'vpc_id': load_balancer['VpcId'],
                'availability_zones': [
                    {
                        'zone_name': az['ZoneName'],
                        'subnet_id': az['SubnetId']
                    }
                    for az in load_balancer['AvailabilityZones']
                ],
                'security_groups': load_balancer['SecurityGroups']
            },
            'configuration_used': config,
            'listener_created': False,
            'listener_arn': None
        }
        
        # Get target group ARN for listener creation
        target_group_arn = get_target_group_arn()
        
        if target_group_arn:
            print("\n" + "=" * 80)
            print("Creating HTTP Listener")
            print("=" * 80)
            print(f"\nTarget Group ARN: {target_group_arn}")
            print("Creating listener on port 80...")
            
            try:
                listener_response = client.create_listener(
                    LoadBalancerArn=alb_arn,
                    Protocol='HTTP',
                    Port=80,
                    DefaultActions=[
                        {
                            'Type': 'forward',
                            'TargetGroupArn': target_group_arn
                        }
                    ]
                )
                
                listener = listener_response['Listeners'][0]
                listener_arn = listener['ListenerArn']
                
                print(f"✅ HTTP Listener created successfully!")
                print(f"\nListener Details:")
                print(f"  ARN: {listener_arn}")
                print(f"  Protocol: {listener['Protocol']}")
                print(f"  Port: {listener['Port']}")
                print(f"  Default Action: Forward to target group")
                
                results['listener_created'] = True
                results['listener_arn'] = listener_arn
                results['listener'] = {
                    'arn': listener_arn,
                    'protocol': listener['Protocol'],
                    'port': listener['Port'],
                    'target_group_arn': target_group_arn
                }
                
            except Exception as e:
                print(f"⚠️  Warning: Could not create listener: {str(e)}")
                print("You can create the listener manually later.")
        else:
            print("\n⚠️  Warning: Target group not found. Listener not created.")
            print("Create the target group first, then create the listener manually.")
        
        # Save results to file
        timestamp = int(datetime.now().timestamp())
        output_file = f'alb-v2-creation-{timestamp}.json'
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"\n✅ Results saved to: {output_file}")
        
        # Test DNS resolution
        print("\n" + "=" * 80)
        print("Testing DNS Resolution")
        print("=" * 80)
        print(f"\nALB DNS Name: {alb_dns}")
        print("\nTesting DNS resolution...")
        
        import socket
        try:
            ip_addresses = socket.gethostbyname_ex(alb_dns)[2]
            print(f"✅ DNS resolves to: {', '.join(ip_addresses)}")
        except Exception as e:
            print(f"⚠️  DNS resolution test: {str(e)}")
            print("Note: DNS may take a few minutes to propagate")
        
        print("\n" + "=" * 80)
        print("Next Steps")
        print("=" * 80)
        print(f"\n1. ALB ARN (use in next task):")
        print(f"   {alb_arn}")
        print(f"\n2. ALB DNS Name:")
        print(f"   {alb_dns}")
        
        if results['listener_created']:
            print(f"\n3. Listener ARN:")
            print(f"   {listener_arn}")
            print(f"\n4. Ready to update ECS service with target group")
        else:
            print(f"\n3. Create listener manually:")
            print(f"   aws elbv2 create-listener \\")
            print(f"     --load-balancer-arn {alb_arn} \\")
            print(f"     --protocol HTTP \\")
            print(f"     --port 80 \\")
            print(f"     --default-actions Type=forward,TargetGroupArn=<target-group-arn>")
        
        print(f"\n5. Test ALB endpoint (once active):")
        print(f"   curl -v http://{alb_dns}/api/health/simple")
        print()
        
        return results
        
    except client.exceptions.DuplicateLoadBalancerNameException:
        print(f"❌ Error: Load balancer '{config['name']}' already exists!")
        print(f"\nTo use the existing load balancer, run:")
        print(f"  aws elbv2 describe-load-balancers --names {config['name']}")
        print(f"\nTo delete the existing load balancer first, run:")
        print(f"  aws elbv2 delete-load-balancer --load-balancer-arn <arn>")
        
        # Try to get existing ALB info
        try:
            existing = client.describe_load_balancers(Names=[config['name']])
            if existing['LoadBalancers']:
                alb = existing['LoadBalancers'][0]
                print(f"\nExisting Load Balancer ARN: {alb['LoadBalancerArn']}")
                print(f"DNS Name: {alb['DNSName']}")
                print(f"State: {alb['State']['Code']}")
        except Exception:
            pass
        
        return {
            'success': False,
            'error': 'DuplicateLoadBalancerName',
            'message': f"Load balancer '{config['name']}' already exists"
        }
        
    except Exception as e:
        print(f"❌ Error creating load balancer: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': type(e).__name__,
            'message': str(e)
        }

def verify_alb_status(alb_name: str = 'multimodal-lib-prod-alb-v2') -> None:
    """
    Verify the status of the newly created ALB.
    
    Args:
        alb_name: Name of the ALB to verify
    """
    client = boto3.client('elbv2', region_name='us-east-1')
    
    print("\n" + "=" * 80)
    print("Verifying ALB Status")
    print("=" * 80)
    
    try:
        response = client.describe_load_balancers(Names=[alb_name])
        
        if response['LoadBalancers']:
            alb = response['LoadBalancers'][0]
            
            print(f"\nLoad Balancer: {alb['LoadBalancerName']}")
            print(f"  State: {alb['State']['Code']}")
            print(f"  DNS Name: {alb['DNSName']}")
            print(f"  Type: {alb['Type']}")
            print(f"  Scheme: {alb['Scheme']}")
            print(f"  VPC: {alb['VpcId']}")
            
            # Check listeners
            listeners_response = client.describe_listeners(
                LoadBalancerArn=alb['LoadBalancerArn']
            )
            
            if listeners_response['Listeners']:
                print(f"\n  Listeners:")
                for listener in listeners_response['Listeners']:
                    print(f"    - {listener['Protocol']}:{listener['Port']}")
            else:
                print(f"\n  ⚠️  No listeners configured")
            
            return True
        else:
            print(f"❌ Load balancer '{alb_name}' not found")
            return False
            
    except Exception as e:
        print(f"❌ Error verifying ALB: {str(e)}")
        return False

def main():
    """Main execution function."""
    print("\n" + "=" * 80)
    print("ALB Connectivity Fix - Task 1: Create New Application Load Balancer")
    print("=" * 80)
    print()
    
    # Check if target group exists first
    target_group_arn = get_target_group_arn()
    if not target_group_arn:
        print("⚠️  Warning: Target group 'multimodal-lib-prod-tg-v2' not found!")
        print("The target group should be created first.")
        print("\nContinuing with ALB creation anyway...")
        print("You can create the listener after creating the target group.")
        print()
    
    results = create_load_balancer()
    
    if results['success']:
        print("\n✅ Task completed successfully!")
        
        # Verify status
        verify_alb_status()
        
        sys.exit(0)
    else:
        print("\n❌ Task failed!")
        sys.exit(1)

if __name__ == '__main__':
    main()
